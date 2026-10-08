"""Moteur de corrélation (#16) : score de menace, niveaux, création et escalade des alertes.

Portage de computeThreat et maybeAlert (frontend/src/api/mock.ts), qui servent de spécification.
Les fonctions pures (compute_threat, title_for, plan_alert…) sont testées dans tests/test_correlation.py.
"""
import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .config import config
from .convert import to_alert
from .db import AlertRow, SessionLocal
from .hub import hub
from .journal import write_log
from .live import live
from .mqtt import CommandError, send_command
from .notify import notify
from .schemas import Settings, SystemState, Threat, ThreatLevel, dump
from .util import utcnow

Signal = Literal["pir", "proximite", "anomalie", "vision", "choc", "muet", "capot", "badge_refuse"]

WINDOW = timedelta(seconds=60)  # chaque type de signal compte une fois sur cette fenêtre
ESCALATE = timedelta(seconds=90)  # une alerte ouverte plus récente est mise à jour au lieu d'être dupliquée
VALID_BADGE = timedelta(minutes=2)
EVAL_INTERVAL_S = 2

LABELS: dict[Signal, str] = {
    "pir": "Mouvement PIR",
    "proximite": "Objet à moins de 50 cm",
    "anomalie": "Anomalie environnementale",
    "vision": "Détection de la caméra",  # personne confirmée, visage inconnu (ou mouvement sans YOLOX)
    "choc": "Choc ou déplacement du boîtier",
    "muet": "Boîtier muet",
    "capot": "Capot ouvert",
    "badge_refuse": "Badge refusé",
}

# Titre de l'alerte selon le signal le plus prioritaire présent.
TITLES: list[tuple[set[Signal], str, int]] = [
    ({"vision"}, "Intrusion détectée", 6),
    ({"capot", "choc"}, "Sabotage du boîtier", 5),
    ({"pir", "proximite"}, "Présence détectée", 4),
    ({"muet"}, "Boîtier muet", 3),
    ({"badge_refuse"}, "Badge refusé", 2),
    ({"anomalie"}, "Anomalie environnementale", 1),
]
LEVEL_RANK: dict[ThreatLevel, int] = {"info": 0, "alerte": 1, "critique": 2}

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- fonctions pures
def fr_number(x: float) -> str:
    return f"{x:g}".replace(".", ",")


def in_occupancy(settings: Settings, local: datetime) -> bool:
    """Heure locale dans les horaires d'occupation (jours 1 = lundi … 7 = dimanche)."""
    hm = local.strftime("%H:%M")
    occ = settings.occupancy
    return local.isoweekday() in occ.days and occ.start <= hm < occ.end


def compute_threat(kinds: set[Signal], settings: Settings, armed: bool, occupied: bool,
                   recent_valid_badge: bool) -> Threat:
    base = 0
    reasons: list[str] = []
    for kind in sorted(kinds, key=list(LABELS).index):
        weight: int = getattr(settings.weights, kind)
        base += weight
        reasons.append(f"{LABELS[kind]} (+{weight})")
    mult = 1.0
    if base > 0 and (armed or not occupied):
        mult *= settings.armed_multiplier
        reasons.append(f"Hors horaires ou armé (× {fr_number(settings.armed_multiplier)})")
    if base > 0 and recent_valid_badge:
        mult *= 0.3
        reasons.append("Badge valide présenté récemment (× 0,3)")
    score = round(base * mult)
    t = settings.thresholds
    level: ThreatLevel = "critique" if score >= t.critique else "alerte" if score >= t.alerte else "info"
    return Threat(score=score, level=level, reasons=reasons)


def title_for(kinds: set[Signal]) -> tuple[str, int]:
    for signals, title, prio in TITLES:
        if signals & kinds:
            return title, prio
    return "Activité inhabituelle", 0


def prio_of(title: str) -> int:
    return next((p for _, t, p in TITLES if t == title), 0)


@dataclass
class AlertPlan:
    create: bool = False
    raise_level: bool = False
    better_title: bool = False
    attach_snapshot: bool = False

    @property
    def changes(self) -> bool:
        return self.create or self.raise_level or self.better_title or self.attach_snapshot


def plan_alert(level: ThreatLevel, last_level: ThreatLevel, title: str, has_snapshot: bool,
               recent: AlertRow | None) -> AlertPlan:
    """Créer une alerte, escalader l'alerte récente, ou ne rien faire."""
    if level == "info":
        return AlertPlan()
    if recent is not None:
        return AlertPlan(
            raise_level=LEVEL_RANK[level] > LEVEL_RANK[recent.level],  # type: ignore[index]
            better_title=prio_of(title) > prio_of(recent.title),
            attach_snapshot=has_snapshot and not recent.snapshot_path,
        )
    # Pas d'alerte récente : on n'en crée une que si le niveau vient de monter.
    return AlertPlan(create=LEVEL_RANK[level] > LEVEL_RANK[last_level])


# ---------------------------------------------------------------- moteur
class Correlator:
    def __init__(self) -> None:
        self.signals: list[tuple[Signal, datetime]] = []
        self.last_level: ThreatLevel = "info"
        self.valid_badge_at: datetime | None = None
        self.snapshot: tuple[str, datetime] | None = None  # dernière capture de la caméra
        self._lock = asyncio.Lock()

    def signal(self, kind: Signal, at: datetime | None = None, snapshot: str | None = None) -> None:
        at = at or utcnow()
        self.signals.append((kind, at))
        if snapshot:
            self.snapshot = (snapshot, at)

    def active_kinds(self, state: SystemState, now: datetime) -> set[Signal]:
        self.signals = [(k, t) for k, t in self.signals if now - t < WINDOW]
        kinds: set[Signal] = {k for k, _ in self.signals}
        if state.sensors.lid.open:
            kinds.add("capot")
        # Boîtier muet seulement s'il a déjà donné signe de vie (pas de fausse alerte avant le premier heartbeat).
        if not state.device.online and state.device.last_heartbeat is not None:
            kinds.add("muet")
        if state.anomaly.is_anomaly:
            kinds.add("anomalie")
        return kinds

    async def evaluate(self) -> None:
        async with self._lock:
            now = utcnow()
            settings = live.settings
            state = live.state
            kinds = self.active_kinds(state, now)
            occupied = in_occupancy(settings, now.astimezone(ZoneInfo(config.timezone)))
            badge = self.valid_badge_at is not None and now - self.valid_badge_at < VALID_BADGE
            state.threat = compute_threat(kinds, settings, state.device.armed, occupied, badge)
            await self._maybe_alert(kinds, now)
            self.last_level = state.threat.level

    async def _maybe_alert(self, kinds: set[Signal], now: datetime) -> None:
        threat = live.state.threat
        if threat.level == "info":
            return
        title, _ = title_for(kinds)
        snapshot = self.snapshot[0] if self.snapshot and "vision" in kinds and now - self.snapshot[1] < WINDOW else None

        async with SessionLocal() as db:
            recent = (await db.execute(
                select(AlertRow).where(AlertRow.status == "ouverte", AlertRow.ts > now - ESCALATE)
                .order_by(AlertRow.ts.desc()).limit(1)
            )).scalar_one_or_none()
            plan = plan_alert(threat.level, self.last_level, title, snapshot is not None, recent)
            if not plan.changes:
                return
            if plan.create:
                alert = AlertRow(ts=now, level=threat.level, score=threat.score, title=title,
                                 reasons=list(threat.reasons), snapshot_path=snapshot, status="ouverte")
                db.add(alert)
            else:
                alert = recent  # type: ignore[assignment]
                if plan.raise_level:
                    alert.level = threat.level
                if plan.better_title:
                    alert.title = title
                if threat.score > alert.score:
                    alert.score, alert.reasons = threat.score, list(threat.reasons)
                if plan.attach_snapshot:
                    alert.snapshot_path = snapshot
            await db.commit()

        hub.broadcast({"type": "alert", "data": dump(to_alert(alert))})
        if plan.create:
            await write_log("critical" if threat.level == "critique" else "warn", "backend",
                            f"Alerte créée : {alert.title} (score {alert.score})")
        elif plan.raise_level or plan.better_title:
            await write_log("critical" if threat.level == "critique" else "warn", "backend",
                            f"Alerte escaladée : {alert.title} (score {alert.score})")
        if plan.create or plan.raise_level:
            notify(alert, escalated=not plan.create)  # push Alerte et Critique (EF-09), capture jointe
        if (plan.create or plan.raise_level) and threat.level == "critique" and live.state.device.armed:
            try:
                if await send_command("buzzer_on"):
                    await write_log("info", "boitier", "Buzzer déclenché")
            except CommandError as e:
                await write_log("error", "backend", f"Buzzer non déclenché : {e}")

    async def run(self) -> None:
        """Réévaluation périodique : les signaux expirent, le niveau redescend."""
        while True:
            try:
                await self.evaluate()
            except Exception:  # noqa: BLE001 (le moteur ne doit jamais s'arrêter)
                log.exception("Erreur du moteur de corrélation")
            await asyncio.sleep(EVAL_INTERVAL_S)


correlator = Correlator()
