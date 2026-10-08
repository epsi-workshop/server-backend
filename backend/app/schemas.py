"""Modèles Pydantic : traduction à l'identique de frontend/src/types.ts (le contrat).

Les champs sont en snake_case côté Python et sérialisés en camelCase (lastLogin, uptimeS…).
Toute modification ici doit être répercutée dans types.ts dans la même PR.
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer
from pydantic.alias_generators import to_camel

from .util import iso

Ts = Annotated[datetime, PlainSerializer(iso, return_type=str)]

Role = Literal["lecteur", "operateur", "admin"]
ThreatLevel = Literal["info", "alerte", "critique"]
LogLevel = Literal["info", "warn", "error", "critical"]
LogSource = Literal["boitier", "camera", "vision", "anomaly", "backend", "auth", "admin"]
RestartTarget = Literal["box", "camera", "vision", "anomaly", "mosquitto", "backend"]
RestartRequest = RestartTarget | Literal["all"]
HistorySensor = Literal["temperature", "humidity", "distance"]
HistoryRange = Literal["1h", "6h", "24h", "7d"]


class Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def dump(model: BaseModel) -> dict[str, Any]:
    """Sérialisation JSON au format du contrat (pour le WebSocket)."""
    return model.model_dump(mode="json", by_alias=True)


class User(Camel):
    id: str
    username: str
    role: Role
    active: bool
    last_login: Ts | None
    must_change_password: bool


# ---------------------------------------------------------------- SystemState
class Device(Camel):
    id: str
    online: bool
    armed: bool
    last_heartbeat: Ts | None
    uptime_s: int
    rssi: int
    firmware: str


class Threat(Camel):
    score: int
    level: ThreatLevel
    reasons: list[str]


class Reading(Camel):
    value: float
    ts: Ts


class Pir(Camel):
    active: bool
    last_triggered: Ts | None
    count_last_hour: int


class Distance(Camel):
    cm: float
    ts: Ts


class Imu(Camel):
    accel_g: float
    tilt_deg: float
    shock: bool
    last_shock: Ts | None


class Lid(Camel):
    open: bool
    last_change: Ts | None


class Rfid(Camel):
    last_uid: str | None
    last_name: str | None
    accepted: bool | None
    ts: Ts | None


class Sensors(Camel):
    temperature: Reading
    humidity: Reading
    pir: Pir
    distance: Distance
    imu: Imu
    lid: Lid
    rfid: Rfid


class Detection(Camel):
    ts: Ts
    confidence: float


class FaceSighting(Camel):
    """Dernier visage vu par la caméra : membre reconnu (name) ou inconnu."""
    ts: Ts
    known: bool
    name: str | None
    confidence: float
    snapshot_url: str | None


class Camera(Camel):
    online: bool
    detection_active: bool
    last_detection: Detection | None
    last_face: FaceSighting | None = None
    override_until: Ts | None
    masked: bool


class Anomaly(Camel):
    score: float
    is_anomaly: bool
    projected_temp15: float
    features: list[str]


class SystemState(Camel):
    device: Device
    threat: Threat
    sensors: Sensors
    camera: Camera
    anomaly: Anomaly


# ---------------------------------------------------------------- autres entités
class Alert(Camel):
    id: str
    ts: Ts
    level: ThreatLevel
    score: int
    title: str
    reasons: list[str]
    snapshot_url: str | None
    status: Literal["ouverte", "acquittee"]
    ack_by: str | None
    ack_at: Ts | None
    comment: str | None


class LogEntry(Camel):
    id: str
    ts: Ts
    level: LogLevel
    source: LogSource
    message: str


class AuditEntry(Camel):
    id: str
    ts: Ts
    user: str
    action: str
    ip: str
    success: bool


class ServiceHealth(Camel):
    name: str
    target: RestartTarget | None
    status: Literal["ok", "degrade", "arrete"]
    uptime_s: int
    cpu: float
    mem_mb: float
    version: str


class Badge(Camel):
    id: str
    uid: str
    owner: str
    active: bool
    last_used: Ts | None


Weight = Annotated[int, Field(ge=0, le=200)]
HourMinute = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


class Weights(Camel):
    pir: Weight
    proximite: Weight
    anomalie: Weight
    vision: Weight
    choc: Weight
    muet: Weight
    capot: Weight
    badge_refuse: Weight


class Thresholds(Camel):
    alerte: Annotated[int, Field(ge=1, le=1000)]
    critique: Annotated[int, Field(ge=1, le=1000)]


class Occupancy(Camel):
    start: HourMinute
    end: HourMinute
    days: list[Annotated[int, Field(ge=1, le=7)]]  # 1 = lundi


class Settings(Camel):
    weights: Weights
    thresholds: Thresholds
    armed_multiplier: Annotated[float, Field(ge=1, le=5)]
    occupancy: Occupancy
    camera_unlock_seconds: Annotated[int, Field(ge=5, le=300)]
    retention_days: Annotated[int, Field(ge=1, le=365)]


DEFAULT_SETTINGS = Settings(
    weights=Weights(pir=20, proximite=20, anomalie=30, vision=40, choc=40, muet=50, capot=60, badge_refuse=30),
    thresholds=Thresholds(alerte=30, critique=70),
    armed_multiplier=1.5,
    occupancy=Occupancy(start="08:00", end="19:00", days=[1, 2, 3, 4, 5]),
    camera_unlock_seconds=300,  # 5 min après le dernier mouvement
    retention_days=30,
)


class Point(Camel):
    ts: Ts
    value: float


# ---------------------------------------------------------------- corps de requêtes
class LoginIn(Camel):
    username: Annotated[str, Field(max_length=64)]
    password: Annotated[str, Field(max_length=256)]


class PasswordChangeIn(Camel):
    current: Annotated[str, Field(max_length=256)]
    password: Annotated[str, Field(max_length=256)]


class AckIn(Camel):
    comment: Annotated[str, Field(max_length=1000)]


class BuzzerIn(Camel):
    on: bool


class RestartIn(Camel):
    target: RestartRequest


class OverrideIn(Camel):
    reason: Annotated[str, Field(max_length=500)]


class UserCreate(Camel):
    username: Annotated[str, Field(max_length=64)]
    role: Role
    password: Annotated[str, Field(max_length=256)]


class UserPatch(Camel):
    role: Role | None = None
    active: bool | None = None


class PasswordResetIn(Camel):
    password: Annotated[str, Field(max_length=256)]


class BadgeCreate(Camel):
    uid: Annotated[str, Field(max_length=32)]
    owner: Annotated[str, Field(max_length=64)]


class TeamMember(Camel):
    id: str
    name: str
    photo: str  # miniature en data URL (JPEG 160 px)
    active: bool
    created_at: Ts
    last_seen: Ts | None


class TeamMemberCreate(Camel):
    name: Annotated[str, Field(min_length=1, max_length=32)]
    photo: Annotated[str, Field(max_length=15_000_000)]  # JPEG ou PNG en base64 (data URL acceptée)


class TeamMemberPatch(Camel):
    name: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    active: bool | None = None


class BadgeEnrollState(Camel):
    """Enregistrement par lecture : listening tant qu'aucun badge n'a été passé avant until."""
    listening: bool
    until: Ts | None
    uid: str | None
    owner: str | None  # titulaire actuel si le badge lu est déjà enregistré


class BadgePatch(Camel):
    active: bool | None = None
    owner: Annotated[str, Field(max_length=64)] | None = None
