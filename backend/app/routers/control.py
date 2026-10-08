"""Commandes : armement, buzzer, caméra, redémarrages, état des services."""
import contextlib
import os
import time
from collections.abc import AsyncIterator
from datetime import timedelta

import psutil
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from .. import supervisor
from ..camera import camera
from ..config import VERSION, config
from ..db import UserRow
from ..deps import Admin, Db, Lecteur, Operateur, client_ip
from ..journal import write_audit, write_log
from ..live import live
from ..arming import apply_armed
from ..mqtt import Command, CommandError, send_command
from ..schemas import BuzzerIn, OverrideIn, RestartIn, RestartTarget, ServiceHealth
from ..sensor_api import sensor_api
from ..util import clean, utcnow

router = APIRouter(prefix="/api", tags=["commande"])

STARTED = time.monotonic()
_process = psutil.Process(os.getpid())


def _check_device(device_id: str) -> None:
    if device_id != config.device_id:
        raise HTTPException(404, "Boîtier inconnu.")


async def _command(cmd: Command, action: str, user: UserRow, request: Request) -> None:
    """Envoie la commande au boîtier ; l'échec est audité et remonté au dashboard."""
    try:
        sent = await send_command(cmd)
    except CommandError:
        await write_audit(user.username, action, client_ip(request), success=False)
        await write_log("error", "backend", f"Commande « {cmd} » non transmise : broker MQTT injoignable")
        raise HTTPException(503, "Boîtier injoignable : commande non transmise.") from None
    if not sent:
        await write_log("warn", "backend", f"MQTT désactivé : commande « {cmd} » non transmise au boîtier")


@router.post("/devices/{device_id}/arm", status_code=204)
async def arm(device_id: str, request: Request, user: Operateur) -> None:
    _check_device(device_id)
    await _command("arm", "Système armé", user, request)
    await apply_armed(True)
    await write_audit(user.username, "Système armé", client_ip(request))
    await write_log("info", "admin", f"Système armé par {user.username}")


@router.post("/devices/{device_id}/disarm", status_code=204)
async def disarm(device_id: str, request: Request, user: Operateur) -> None:
    _check_device(device_id)
    await _command("disarm", "Système désarmé", user, request)
    await apply_armed(False)
    await write_audit(user.username, "Système désarmé", client_ip(request))
    await write_log("info", "admin", f"Système désarmé par {user.username}")


@router.post("/devices/{device_id}/buzzer", status_code=204)
async def buzzer(device_id: str, body: BuzzerIn, request: Request, user: Operateur) -> None:
    _check_device(device_id)
    action = "Test du buzzer" if body.on else "Arrêt du buzzer"
    await _command("buzzer_on" if body.on else "buzzer_off", action, user, request)
    await write_audit(user.username, action, client_ip(request))
    await write_log("info", "boitier", f"{action} depuis le dashboard ({user.username})")


@router.post("/camera/override", status_code=204)
async def camera_override(body: OverrideIn, request: Request, user: Admin) -> None:
    reason = clean(body.reason, 500)
    if len(reason) < 10:
        raise HTTPException(422, "Motif trop court : 10 caractères minimum.")
    live.state.camera.override_until = utcnow() + timedelta(seconds=60)
    live.publish()
    await write_audit(user.username, f"Accès caméra forcé (60 s) : {reason}", client_ip(request))
    await write_log("warn", "admin", f"Accès caméra forcé par {user.username} : {reason}")


@router.get("/stream")
async def stream(_: Lecteur) -> StreamingResponse:
    # La règle d'accès est vérifiée ici, pas seulement dans le dashboard.
    if not live.camera_unlocked():
        raise HTTPException(403, "Caméra verrouillée : aucune détection en cours.")

    async def body() -> AsyncIterator[bytes]:
        async with contextlib.aclosing(camera.frames()) as frames:
            async for jpeg in frames:
                if not live.camera_unlocked():  # fin de la détection ou de l'accès forcé : on coupe
                    return
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpeg)).encode()
                       + b"\r\n\r\n" + jpeg + b"\r\n")

    return StreamingResponse(body(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


# Redémarrage complet : le backend en dernier (il se redémarre lui-même), la caméra est ignorée si indisponible.
RESTART_ORDER: tuple[RestartTarget, ...] = ("box", "camera", "vision", "anomaly", "mosquitto", "backend")


async def _restart_one(target: RestartTarget, user: UserRow, request: Request) -> None:
    action = f"Redémarrage demandé : {target}"
    if target == "box":
        await _command("reboot", action, user, request)
    elif target == "camera":
        await write_audit(user.username, action, client_ip(request), success=False)
        raise HTTPException(503, "Redémarrage de la caméra indisponible : couper puis rétablir son alimentation.")
    else:
        # Jamais de docker.sock dans le backend : le superviseur n'accepte qu'une liste fermée de services.
        try:
            await supervisor.restart(target)
        except supervisor.SupervisorError as e:
            await write_audit(user.username, action, client_ip(request), success=False)
            raise HTTPException(503, f"Redémarrage de « {target} » impossible : {e}.") from None
    await write_audit(user.username, action, client_ip(request))
    await write_log("warn", "admin", f"Redémarrage de « {target} » demandé par {user.username}")


@router.post("/system/restart", status_code=204)
async def restart(body: RestartIn, request: Request, user: Admin) -> None:
    if body.target != "all":
        await _restart_one(body.target, user, request)
        return
    failed = []
    for target in RESTART_ORDER:
        try:
            await _restart_one(target, user, request)
        except HTTPException as e:  # reprise sur erreur : les suivants sont quand même redémarrés
            failed.append(f"{target} ({e.detail})")
    if failed:
        await write_log("warn", "admin", "Redémarrage complet, non redémarrés : " + " ; ".join(failed))


@router.get("/system/services")
async def services(_: Admin, db: Db) -> list[ServiceHealth]:
    out = [ServiceHealth(
        name="backend", target="backend", status="ok", uptime_s=int(time.monotonic() - STARTED),
        cpu=round(_process.cpu_percent(), 1), mem_mb=round(_process.memory_info().rss / 2**20, 1), version=VERSION,
    )]
    try:
        db_version = (await db.execute(text("SHOW server_version"))).scalar_one()
        db_status = "ok"
    except Exception:  # noqa: BLE001 (on rapporte l'état, quelle que soit l'erreur)
        db_version, db_status = "?", "arrete"
    out.append(ServiceHealth(name="db (TimescaleDB)", target=None, status=db_status, uptime_s=0, cpu=0, mem_mb=0,
                             version=str(db_version).split(" ")[0]))
    if sensor_api:
        host = sensor_api.base_url.split("://", 1)[-1]
        out.append(ServiceHealth(name=f"API capteurs ({host})", target=None,
                                 status="ok" if sensor_api.http_ok else "arrete",
                                 uptime_s=sensor_api.uptime_s if sensor_api.http_ok else 0, cpu=0, mem_mb=0,
                                 version=sensor_api.version))
    # Autres conteneurs de la pile : état fourni par le superviseur (backend et base déjà décrits ci-dessus).
    try:
        for s in await supervisor.services():
            if s["name"] in ("backend", "db"):
                continue
            out.append(ServiceHealth(
                name=s["name"], target=s["name"] if s["restartable"] else None, status=s["status"],
                uptime_s=s["uptime_s"], cpu=s["cpu"], mem_mb=s["mem_mb"], version=s["version"]))
    except (supervisor.SupervisorError, KeyError, TypeError, ValueError) as e:
        out.append(ServiceHealth(name=f"superviseur ({e})"[:60], target=None, status="arrete", uptime_s=0, cpu=0,
                                 mem_mb=0, version="?"))
    return out
