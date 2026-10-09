"""Ingestion MQTT (#15) : validation, anti-rejeu, écriture en base, mise à jour de l'état.

Topics : sentinel/vision/detection et sentinel/<boîtier>/{telemetry,event,heartbeat,status}.
"""
import asyncio
import json
import logging
import re
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, ValidationError
from sqlalchemy import select

from .arming import apply_armed
from . import badges, sound
from .config import config
from .correlation import correlator
from .db import BadgeRow, SessionLocal, TeamMemberRow, events, measurements
from .journal import write_log
from .live import live
from .mqtt import Handler
from .schemas import Detection, Distance, FaceSighting, Reading
from .util import clean, utcnow

SNAPSHOT_RE = re.compile(r"^[A-Za-z0-9_-]{1,80}\.jpg$")
MAX_AGE = timedelta(minutes=5)
MAX_FUTURE = timedelta(minutes=1)  # tolérance de décalage d'horloge (NTP)
HEARTBEAT_TIMEOUT = timedelta(seconds=45)  # 3 heartbeats manqués (un toutes les 15 s)
SHOCK_DISPLAY = timedelta(seconds=10)  # durée d'affichage de « choc » sur le dashboard
PROXIMITY_CM = 50
WATCHDOG_INTERVAL_S = 5

log = logging.getLogger(__name__)


class Envelope(BaseModel):
    """Enveloppe commune à tous les messages du contrat MQTT."""
    device: Annotated[str, Field(pattern=r"^[a-z0-9_-]{1,32}$")]
    seq: Annotated[int, Field(ge=0)]
    ts: AwareDatetime
    type: Annotated[str, Field(max_length=32)]
    data: dict[str, Any] = {}


class VisionData(BaseModel):
    confidence: Annotated[float, Field(ge=0, le=1)]
    snapshot: Annotated[str, Field(pattern=SNAPSHOT_RE.pattern)] | None = None
    member_id: uuid.UUID | None = None  # face_known : membre reconnu (le prénom vient de la base, pas du message)


class TelemetryData(BaseModel):
    temperature: Annotated[float, Field(ge=-40, le=125)] | None = None
    humidity: Annotated[float, Field(ge=0, le=100)] | None = None
    distance: Annotated[float, Field(ge=0, le=600)] | None = None


class HeartbeatData(BaseModel):
    uptime: Annotated[int, Field(ge=0)] = 0
    rssi: Annotated[int, Field(ge=-120, le=0)] = 0
    firmware: Annotated[str, Field(max_length=32)] | None = None


class StateData(BaseModel):
    state: Literal[0, 1]


class ShockData(BaseModel):
    accel_g: Annotated[float, Field(ge=0, le=32)] | None = None
    tilt_deg: Annotated[float, Field(ge=0, le=180)] | None = None


class RfidData(BaseModel):
    uid: Annotated[str, Field(pattern=r"^([0-9A-Fa-f]{2}:){3,6}[0-9A-Fa-f]{2}$")]


class ReplayGuard:
    """Rejette un message dont le seq a déjà été vu (ou est plus ancien) ou dont l'horodatage est hors fenêtre."""

    def __init__(self) -> None:
        self.last_seq: dict[str, int] = {}

    def check(self, device: str, seq: int, ts: datetime, now: datetime) -> str | None:
        if ts < now - MAX_AGE:
            return "horodatage trop ancien"
        if ts > now + MAX_FUTURE:
            return "horodatage dans le futur"
        last = self.last_seq.get(device)
        if last is not None and seq <= last:
            return f"numéro de séquence déjà reçu ({seq} ≤ {last}), rejeu possible"
        self.last_seq[device] = seq
        return None


def count_recent(times: deque[datetime], now: datetime, window: timedelta) -> int:
    """Retire les instants sortis de la fenêtre et compte ceux qui restent."""
    while times and now - times[0] > window:
        times.popleft()
    return len(times)


def is_mute(online: bool, last_heartbeat: datetime | None, now: datetime) -> bool:
    return online and last_heartbeat is not None and now - last_heartbeat > HEARTBEAT_TIMEOUT


guard = ReplayGuard()
pir_events: deque[datetime] = deque()


async def _parse(topic: str, payload: bytes, device: str | None = None) -> Envelope | None:
    try:
        env = Envelope.model_validate(json.loads(payload))
    except (ValueError, ValidationError):
        await write_log("warn", "backend", f"Message rejeté sur {topic} : format invalide")
        return None
    if device is not None and env.device != device:  # l'identité doit correspondre au topic
        await write_log("warn", "backend", f"Message rejeté sur {topic} : équipement {clean(env.device, 32)}")
        return None
    if reason := guard.check(env.device, env.seq, env.ts, utcnow()):
        await write_log("warn", "backend", f"Message rejeté sur {topic} ({env.device}) : {reason}")
        return None
    return env


async def _invalid(source: str, what: str) -> None:
    await write_log("warn", "backend", f"Message rejeté sur {source} : {what} invalide")


async def _store_event(env: Envelope, data: dict[str, Any]) -> None:
    async with SessionLocal() as db:
        await db.execute(events.insert().values(time=env.ts, device=env.device, type=env.type, data=data))
        await db.commit()


async def _update() -> None:
    await correlator.evaluate()
    live.publish()


# ---------------------------------------------------------------- vision
async def on_vision_detection(topic: str, payload: bytes) -> None:
    env = await _parse(topic, payload)
    if env is None:
        return
    if env.type in ("face_known", "face_unknown"):
        await on_face(env)
        return
    if env.type not in ("motion", "person"):
        await write_log("warn", "vision", f"Type de détection inconnu : {clean(env.type, 32)}")
        return
    try:
        data = VisionData.model_validate(env.data)
    except ValidationError:
        await _invalid(topic, "données de détection")
        return

    cam = live.state.camera
    new_episode = not cam.detection_active
    cam.last_detection = Detection(ts=env.ts, confidence=data.confidence)
    live.refresh()

    async with SessionLocal() as db:
        await db.execute(events.insert().values(time=env.ts, device=env.device, type=f"vision_{env.type}",
                                                data=data.model_dump()))
        await db.commit()

    correlator.signal("vision", env.ts, data.snapshot)
    if new_episode:
        what = "Personne détectée" if env.type == "person" else "Mouvement détecté devant la caméra"
        await write_log("warn", "vision", f"{what}, flux déverrouillé"
                        + (f", capture {data.snapshot}" if data.snapshot else ""))
    await _update()


async def on_face(env: Envelope) -> None:
    """Visage vu par la caméra : membre de l'équipe reconnu, ou intrus."""
    try:
        data = VisionData.model_validate(env.data)
    except ValidationError:
        await _invalid("sentinel/vision/detection", "données de visage")
        return
    member = None
    if env.type == "face_known" and data.member_id:
        async with SessionLocal() as db:
            member = await db.get(TeamMemberRow, data.member_id)
            if member is not None and member.active:
                member.last_seen = env.ts
                await db.commit()
            else:
                member = None
    known = member is not None
    live.state.camera.last_detection = Detection(ts=env.ts, confidence=data.confidence)  # déverrouille le flux
    live.state.camera.last_face = FaceSighting(
        ts=env.ts, known=known, name=member.name if member else None, confidence=data.confidence,
        snapshot_url=f"/api/snapshots/{data.snapshot}" if data.snapshot else None)
    live.refresh()
    await _store_event(env, {**data.model_dump(mode="json"), "name": member.name if member else None})
    if known:
        # Membre reconnu : même effet qu'un badge valide (score de menace atténué), et fin de l'alarme.
        correlator.valid_badge_at = env.ts
        if sound.alarm_active():
            sound.stop()
            await write_log("info", "vision", f"Alarme arrêtée : {member.name} reconnu")  # type: ignore[union-attr]
        sound.hello(member.name)  # type: ignore[union-attr]
        await write_log("info", "vision", f"Visage reconnu : bonjour {member.name}")  # type: ignore[union-attr]
    else:
        correlator.signal("vision", env.ts, data.snapshot)
        await write_log("critical", "vision", "Intrus détecté : visage inconnu"
                        + (f", capture {data.snapshot}" if data.snapshot else ""))
        # Seul cas où l'alarme sonne : un intrus pendant que le système est armé.
        if live.state.device.armed and not sound.alarm_active():
            sound.alarm()
            await write_log("critical", "vision", "Alarme intrusion déclenchée")
    await _update()


# ---------------------------------------------------------------- boîtier
# Chaque message du boîtier passe en deux temps : on_box_* lit et vérifie le message MQTT
# (format, identité, anti-rejeu), puis box_* le traite. box_* sert aussi à l'API capteurs (sensor_api.py).
async def on_box_telemetry(topic: str, payload: bytes) -> None:
    if (env := await _parse(topic, payload, config.device_id)) is not None:
        await box_telemetry(env, topic)


async def box_telemetry(env: Envelope, source: str) -> None:
    try:
        data = TelemetryData.model_validate(env.data)
    except ValidationError:
        await _invalid(source, "télémesure")
        return
    values = data.model_dump(exclude_none=True)
    if not values:
        return
    async with SessionLocal() as db:
        await db.execute(measurements.insert(), [
            {"time": env.ts, "device": env.device, "sensor": sensor, "value": value} for sensor, value in values.items()
        ])
        await db.commit()

    sensors = live.state.sensors
    if data.temperature is not None:
        sensors.temperature = Reading(value=round(data.temperature, 1), ts=env.ts)
    if data.humidity is not None:
        sensors.humidity = Reading(value=round(data.humidity, 1), ts=env.ts)
    if data.distance is not None:
        sensors.distance = Distance(cm=round(data.distance), ts=env.ts)
        if data.distance < PROXIMITY_CM:
            correlator.signal("proximite", env.ts)
    await _update()


async def on_box_event(topic: str, payload: bytes) -> None:
    if (env := await _parse(topic, payload, config.device_id)) is not None:
        await box_event(env, topic)


async def box_event(env: Envelope, source: str) -> None:
    s = live.state.sensors
    try:
        match env.type:
            case "pir":
                active = StateData.model_validate(env.data).state == 1
                if active or s.pir.active:
                    # Début ou fin d'un mouvement : la caméra reste ouverte jusqu'à
                    # camera_unlock_seconds après cet instant (live.refresh).
                    live.state.camera.last_detection = Detection(ts=env.ts, confidence=1.0)
                if active and not s.pir.active:
                    pir_events.append(env.ts)
                    s.pir.last_triggered = env.ts
                    correlator.signal("pir", env.ts)
                    await write_log("info", "boitier", "Mouvement détecté (PIR)")
                s.pir.active = active
                s.pir.count_last_hour = count_recent(pir_events, utcnow(), timedelta(hours=1))
            case "lid_open":
                is_open = StateData.model_validate(env.data).state == 1
                if is_open != s.lid.open:
                    s.lid.open, s.lid.last_change = is_open, env.ts
                    await write_log("critical" if is_open else "info", "boitier",
                                    "Capot du boîtier ouvert" if is_open else "Capot du boîtier refermé")
            case "imu_shock":
                shock = ShockData.model_validate(env.data)
                s.imu.shock, s.imu.last_shock = True, env.ts
                if shock.accel_g is not None:
                    s.imu.accel_g = shock.accel_g
                if shock.tilt_deg is not None:
                    s.imu.tilt_deg = shock.tilt_deg
                correlator.signal("choc", env.ts)
                await write_log("critical", "boitier", "Choc détecté sur le boîtier")
            case "rfid_ok" | "rfid_refused":
                await _on_badge(env, RfidData.model_validate(env.data).uid.upper())
            case _:
                await write_log("warn", "boitier", f"Événement inconnu : {clean(env.type, 32)}")
                return
    except ValidationError:
        await _invalid(source, f"événement {clean(env.type, 32)}")
        return
    await _store_event(env, env.data)
    await _update()


async def _on_badge(env: Envelope, uid: str) -> None:
    """Le boîtier ne fait que lire le badge : la décision vient de la table badges (gérée par l'admin)."""
    if badges.enrollment.active():
        # Enregistrement en cours depuis le dashboard : le badge est capturé, ni accepté ni refusé.
        async with SessionLocal() as db:
            known = (await db.execute(select(BadgeRow).where(BadgeRow.uid == uid))).scalar_one_or_none()
        badges.enrollment.uid, badges.enrollment.owner = uid, known.owner if known else None
        await write_log("info", "boitier", f"Badge lu pour enregistrement : {uid}"
                        + (f" (déjà enregistré : {known.owner})" if known else ""))
        await badges.show("enroll", uid, known.owner if known else None)
        return
    async with SessionLocal() as db:
        badge = (await db.execute(select(BadgeRow).where(BadgeRow.uid == uid))).scalar_one_or_none()
        accepted = badge is not None and badge.active
        if badge is not None and accepted:
            badge.last_used = env.ts
        await db.commit()
    live.state.sensors.rfid.last_uid = uid
    live.state.sensors.rfid.last_name = badge.owner if badge else None
    live.state.sensors.rfid.accepted = accepted
    live.state.sensors.rfid.ts = env.ts
    if accepted:
        correlator.valid_badge_at = env.ts
        await write_log("info", "boitier", f"Badge accepté : {badge.owner} ({uid})")  # type: ignore[union-attr]
        if sound.alarm_active():
            sound.stop()
            await write_log("info", "boitier", f"Alarme arrêtée par badge ({badge.owner})")  # type: ignore[union-attr]
        # Badge à deux états : un passage arme et verrouille, le suivant désarme et déverrouille.
        armed = not live.state.device.armed
        await apply_armed(armed)
        await badges.show("ok", uid, badge.owner)  # type: ignore[union-attr]
        await write_log("info", "boitier", f"Système {'armé, porte verrouillée' if armed else 'désarmé, porte déverrouillée'} "
                                           f"par badge ({badge.owner})")  # type: ignore[union-attr]
    else:
        correlator.signal("badge_refuse", env.ts)
        await write_log("warn", "boitier", f"Badge refusé : {'désactivé' if badge else 'UID inconnu'} {uid}")
        await badges.show("refused", uid, None)


async def on_box_heartbeat(topic: str, payload: bytes) -> None:
    if (env := await _parse(topic, payload, config.device_id)) is not None:
        await box_heartbeat(env, topic)


async def box_heartbeat(env: Envelope, source: str) -> None:
    try:
        data = HeartbeatData.model_validate(env.data)
    except ValidationError:
        await _invalid(source, "heartbeat")
        return
    d = live.state.device
    was_online = d.online
    d.online, d.last_heartbeat, d.uptime_s, d.rssi = True, utcnow(), data.uptime, data.rssi
    if data.firmware:
        d.firmware = clean(data.firmware, 32)
    if not was_online:
        await write_log("info", "boitier", f"Boîtier {env.device} en ligne")
        await _update()


async def on_box_status(topic: str, payload: bytes) -> None:
    """online/offline, publié retenu ; « offline » est le Last Will (message figé : pas de seq ni ts à jour)."""
    text = payload.decode(errors="replace").strip().strip('"').lower()
    if text not in ("online", "offline"):
        await _invalid(topic, "statut")
        return
    d = live.state.device
    if text == "offline" and d.online:
        d.online = False
        await write_log("error", "boitier", f"Boîtier {config.device_id} déconnecté (Last Will)")
        await _update()
    # « online » ne suffit pas : le boîtier passe en ligne à son premier heartbeat.


async def watchdog() -> None:
    """Boîtier muet (3 heartbeats manqués) et fin de l'affichage « choc »."""
    while True:
        await asyncio.sleep(WATCHDOG_INTERVAL_S)
        try:
            now = utcnow()
            d, imu = live.state.device, live.state.sensors.imu
            changed = False
            if is_mute(d.online, d.last_heartbeat, now):
                d.online = False
                changed = True
                await write_log("error", "boitier", f"Boîtier {config.device_id} muet : aucun heartbeat depuis 45 s")
            if imu.shock and imu.last_shock and now - imu.last_shock > SHOCK_DISPLAY:
                imu.shock = False
                changed = True
            if changed:
                await _update()
        except Exception:  # noqa: BLE001 (la surveillance ne doit jamais s'arrêter)
            log.exception("Erreur de la surveillance du boîtier")


_box = f"sentinel/{config.device_id}"
HANDLERS: dict[str, Handler] = {
    "sentinel/vision/detection": on_vision_detection,
    f"{_box}/telemetry": on_box_telemetry,
    f"{_box}/event": on_box_event,
    f"{_box}/heartbeat": on_box_heartbeat,
    f"{_box}/status": on_box_status,
}
