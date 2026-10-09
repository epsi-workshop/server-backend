"""Enceinte Bluetooth de l'UNO Q : recherche, connexion, volume et test des sons (administration).

Relais vers l'API capteurs (SENSOR_API_URL, routes /audio et /sound) : c'est la carte qui appaire l'enceinte.
"""
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from ..config import config
from ..deps import Admin, client_ip
from ..journal import write_audit
from ..schemas import Camel
from ..sensor_api import IPV4_ONLY
from ..util import clean

router = APIRouter(prefix="/api/audio", tags=["enceinte"])

Sound = Literal["test", "ok", "refused", "hello", "siren"]


class SpeakerConnectIn(Camel):
    mac: Annotated[str, Field(pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")] | None = None
    name: Annotated[str, Field(min_length=1, max_length=64)] | None = None


async def _board(method: str, path: str, timeout: float = 10, **kwargs: Any) -> Any:
    if not config.sensor_api_url:
        raise HTTPException(503, "API capteurs non configurée (SENSOR_API_URL).")
    try:
        async with httpx.AsyncClient(base_url=config.sensor_api_url.rstrip("/"),
                                     timeout=httpx.Timeout(timeout, connect=10),
                                     transport=httpx.AsyncHTTPTransport(local_address=IPV4_ONLY)) as client:
            r = await client.request(method, path, **kwargs)
    except httpx.HTTPError as e:
        raise HTTPException(503, f"Boîtier injoignable : {type(e).__name__}") from None
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = None
        raise HTTPException(409 if r.status_code == 409 else 502,
                            detail if isinstance(detail, str) else f"Erreur du boîtier ({r.status_code}).")
    return r.json()


@router.get("")
async def get_audio(_: Admin) -> Any:
    """Enceinte mémorisée, connexion, volume."""
    return await _board("GET", "/audio")


@router.get("/devices")
async def scan_devices(_: Admin, seconds: Annotated[int, Query(ge=3, le=20)] = 8) -> Any:
    """Appareils Bluetooth à portée, enceintes en premier (l'enceinte doit être en mode appairage)."""
    return await _board("GET", "/audio/devices", timeout=seconds + 20, params={"seconds": seconds})


@router.post("/connect")
async def connect_speaker(body: SpeakerConnectIn, request: Request, admin: Admin) -> Any:
    if not body.mac and not body.name:
        raise HTTPException(422, "Choisissez une enceinte ou saisissez son nom.")
    state = await _board("POST", "/audio/connect", timeout=90, json=body.model_dump(exclude_none=True))
    name = (state.get("speaker") or {}).get("name") or body.name or body.mac
    await write_audit(admin.username, f"Enceinte Bluetooth connectée : {clean(str(name), 64)}", client_ip(request))
    return state


@router.post("/disconnect")
async def disconnect_speaker(_: Admin) -> Any:
    return await _board("POST", "/audio/disconnect", timeout=20)


@router.delete("/speaker")
async def forget_speaker(request: Request, admin: Admin) -> Any:
    state = await _board("DELETE", "/audio/speaker", timeout=20)
    await write_audit(admin.username, "Enceinte Bluetooth oubliée", client_ip(request))
    return state


@router.post("/volume/{pct}")
async def set_volume(pct: int, _: Admin) -> Any:
    if not 0 <= pct <= 100:
        raise HTTPException(422, "Volume entre 0 et 100.")
    return await _board("POST", f"/audio/volume/{pct}")


@router.post("/sound/{sound}")
async def play_sound(sound: Sound, _: Admin, seconds: Annotated[int, Query(ge=1, le=60)] = 5) -> Any:
    """Test : joue un son sur l'enceinte et le haut-parleur du boîtier (sirène limitée à 60 s)."""
    return await _board("POST", f"/sound/{sound}", params={"seconds": seconds})


@router.post("/stop")
async def stop_sound(_: Admin) -> Any:
    return await _board("POST", "/sound/stop")
