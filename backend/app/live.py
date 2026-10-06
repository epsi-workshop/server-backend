"""État courant du système (SystemState) gardé en mémoire et poussé toutes les 2 s.

Pour l'instant seul le dashboard le modifie (armement, accès caméra forcé). L'ingestion MQTT (#15)
et le moteur de corrélation (#16) viendront mettre à jour capteurs, menace et caméra.
"""
import asyncio
from datetime import datetime

from sqlalchemy import select

from .config import config
from .db import SessionLocal, SettingsRow, measurements
from .hub import hub
from .schemas import (
    DEFAULT_SETTINGS, Anomaly, Camera, Device, Distance, Imu, Lid, Pir, Reading, Rfid, Sensors, Settings,
    SystemState, Threat, dump,
)
from .util import utcnow

PUSH_INTERVAL_S = 2


def default_state(now: datetime) -> SystemState:
    return SystemState(
        device=Device(id=config.device_id, online=False, armed=False, last_heartbeat=None, uptime_s=0, rssi=0,
                      firmware="inconnu"),
        threat=Threat(score=0, level="info", reasons=[]),
        sensors=Sensors(
            temperature=Reading(value=0, ts=now),
            humidity=Reading(value=0, ts=now),
            pir=Pir(active=False, last_triggered=None, count_last_hour=0),
            distance=Distance(cm=0, ts=now),
            imu=Imu(accel_g=1.0, tilt_deg=0, shock=False, last_shock=None),
            lid=Lid(open=False, last_change=None),
            rfid=Rfid(last_uid=None, last_name=None, accepted=None, ts=None),
        ),
        camera=Camera(online=False, detection_active=False, last_detection=None, override_until=None, masked=False),
        anomaly=Anomaly(score=0, is_anomaly=False, projected_temp15=0, features=[]),
    )


class LiveState:
    def __init__(self) -> None:
        self.state = default_state(utcnow())
        self.settings: Settings = DEFAULT_SETTINGS

    async def load(self) -> None:
        """Paramètres de détection et dernières mesures connues, lus en base au démarrage."""
        async with SessionLocal() as db:
            row = await db.get(SettingsRow, 1)
            if row is None:
                db.add(SettingsRow(id=1, data=dump(DEFAULT_SETTINGS)))
                await db.commit()
            else:
                self.settings = Settings.model_validate(row.data)

            for sensor in ("temperature", "humidity", "distance"):
                last = (await db.execute(
                    select(measurements.c.value, measurements.c.time)
                    .where(measurements.c.device == config.device_id, measurements.c.sensor == sensor)
                    .order_by(measurements.c.time.desc()).limit(1)
                )).first()
                if last is None:
                    continue
                if sensor == "distance":
                    self.state.sensors.distance = Distance(cm=last.value, ts=last.time)
                else:
                    setattr(self.state.sensors, sensor, Reading(value=last.value, ts=last.time))

    def refresh(self) -> None:
        """Expirations dépendant du temps : accès forcé, fenêtre de déverrouillage de la caméra.

        Flux ouvert tant que le PIR voit un mouvement, puis camera_unlock_seconds (5 min par défaut)
        après le dernier mouvement : last_detection est remis à jour à chaque événement du PIR (ingest.py).
        """
        now = utcnow()
        cam = self.state.camera
        if cam.override_until and cam.override_until <= now:
            cam.override_until = None
        det = cam.last_detection
        recent = bool(det and (now - det.ts).total_seconds() < self.settings.camera_unlock_seconds)
        cam.detection_active = self.state.sensors.pir.active or recent

    def camera_unlocked(self) -> bool:
        self.refresh()
        return self.state.camera.detection_active or self.state.camera.override_until is not None

    def snapshot(self) -> SystemState:
        self.refresh()
        return self.state.model_copy(deep=True)

    def publish(self) -> None:
        hub.broadcast({"type": "state", "data": dump(self.snapshot())})

    async def run(self) -> None:
        while True:
            await asyncio.sleep(PUSH_INTERVAL_S)
            hub.expire_sessions()
            self.publish()


live = LiveState()
