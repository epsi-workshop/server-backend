"""Lecture : état, historique, alertes, journaux, audit."""
import uuid
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, text

from .. import sound
from ..config import config
from ..ingest import SNAPSHOT_RE
from ..convert import to_alert, to_audit, to_log
from ..db import AlertRow, AuditRow, LogRow, events
from ..deps import Admin, Db, Lecteur, Operateur, client_ip
from ..hub import hub
from ..journal import write_audit, write_log
from ..live import live
from ..schemas import (
    AckIn, Alert, AuditEntry, HistoryRange, HistorySensor, LogEntry, LogLevel, LogSource, Point, SystemState, dump,
)
from ..util import utcnow

router = APIRouter(prefix="/api", tags=["supervision"])

RANGES = {"1h": timedelta(hours=1), "6h": timedelta(hours=6), "24h": timedelta(days=1), "7d": timedelta(days=7)}
POINTS_PER_CHART = 144


@router.get("/state")
async def get_state(_: Lecteur) -> SystemState:
    return live.snapshot()


@router.get("/measurements")
async def get_measurements(
    _: Lecteur, db: Db, sensor: HistorySensor, range_: Annotated[HistoryRange, Query(alias="range")],
) -> list[Point]:
    span = RANGES[range_]
    rows = await db.execute(
        text("""
            SELECT date_bin(CAST(:bucket AS interval), time, TIMESTAMPTZ '2000-01-01') AS bucket, avg(value) AS value
            FROM measurements
            WHERE device = :device AND sensor = :sensor AND time > now() - CAST(:span AS interval)
            GROUP BY bucket ORDER BY bucket
        """),
        {"bucket": span / POINTS_PER_CHART, "span": span, "device": config.device_id, "sensor": sensor},
    )
    return [Point(ts=r.bucket, value=round(r.value, 1)) for r in rows]


@router.get("/alerts")
async def get_alerts(_: Lecteur, db: Db) -> list[Alert]:
    rows = (await db.execute(select(AlertRow).order_by(AlertRow.ts.desc()).limit(200))).scalars()
    return [to_alert(a) for a in rows]


@router.get("/snapshots/{name}")
async def get_snapshot(name: str, _: Lecteur, db: Db) -> FileResponse:
    """Capture d'une alerte ou d'un visage vu par la caméra (bandeau « Bonjour … » / « Intrus »). Les autres
    images du volume (mouvements sans alerte) restent inaccessibles depuis le dashboard."""
    if not SNAPSHOT_RE.fullmatch(name):
        raise HTTPException(404, "Capture introuvable.")
    linked = (await db.execute(select(AlertRow.id).where(AlertRow.snapshot_path == name).limit(1))).first()
    if not linked and name.startswith("face-"):
        linked = (await db.execute(select(events.c.time).where(
            events.c.type.in_(("face_known", "face_unknown")), events.c.data["snapshot"].astext == name,
        ).limit(1))).first()
    path = config.snapshot_dir / name
    if not linked or not path.is_file():
        raise HTTPException(404, "Capture introuvable.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=86400"})


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(alert_id: uuid.UUID, body: AckIn, request: Request, user: Operateur, db: Db) -> Alert:
    alert = await db.get(AlertRow, alert_id)
    if alert is None:
        raise HTTPException(404, "Alerte introuvable.")
    comment = body.comment.strip()
    if not comment:
        raise HTTPException(422, "Un commentaire est obligatoire pour acquitter.")
    if alert.status == "acquittee":
        raise HTTPException(409, "Cette alerte est déjà acquittée.")
    alert.status, alert.ack_by, alert.ack_at, alert.comment = "acquittee", user.username, utcnow(), comment
    await db.commit()

    out = to_alert(alert)
    hub.broadcast({"type": "alert", "data": dump(out)})
    sound.stop()  # alerte prise en charge : la sirène s'arrête
    await write_audit(user.username, f"Alerte acquittée : {alert.title}", client_ip(request))
    await write_log("info", "admin", f"Alerte acquittée par {user.username} : {alert.title}")
    return out


@router.get("/logs")
async def get_logs(
    _: Operateur, db: Db,
    source: Annotated[list[LogSource], Query()] = [],  # noqa: B006 (FastAPI copie la valeur par défaut)
    level: Annotated[list[LogLevel], Query()] = [],  # noqa: B006
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[LogEntry]:
    stmt = select(LogRow).order_by(LogRow.ts.desc(), LogRow.id.desc()).limit(500)
    if source:
        stmt = stmt.where(LogRow.source.in_(source))
    if level:
        stmt = stmt.where(LogRow.level.in_(level))
    if q and q.strip():
        pattern = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(LogRow.message.ilike(f"%{pattern}%", escape="\\"))
    return [to_log(r) for r in (await db.execute(stmt)).scalars()]


@router.get("/audit")
async def get_audit(_: Admin, db: Db) -> list[AuditEntry]:
    rows = (await db.execute(select(AuditRow).order_by(AuditRow.ts.desc(), AuditRow.id.desc()).limit(500))).scalars()
    return [to_audit(r) for r in rows]
