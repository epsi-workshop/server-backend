"""Lignes SQL -> modèles du contrat."""
from .db import AlertRow, AuditRow, BadgeRow, LogRow, UserRow
from .schemas import Alert, AuditEntry, Badge, LogEntry, User


def to_user(u: UserRow) -> User:
    return User.model_validate({
        "id": str(u.id), "username": u.username, "role": u.role, "active": u.active,
        "last_login": u.last_login, "must_change_password": u.must_change_password,
    })


def to_alert(a: AlertRow) -> Alert:
    return Alert.model_validate({
        "id": str(a.id), "ts": a.ts, "level": a.level, "score": a.score, "title": a.title,
        "reasons": list(a.reasons),
        "snapshot_url": f"/api/snapshots/{a.snapshot_path}" if a.snapshot_path else None,
        "status": a.status, "ack_by": a.ack_by, "ack_at": a.ack_at, "comment": a.comment,
    })


def to_log(r: LogRow) -> LogEntry:
    return LogEntry.model_validate({
        "id": str(r.id), "ts": r.ts, "level": r.level, "source": r.source, "message": r.message,
    })


def to_audit(r: AuditRow) -> AuditEntry:
    return AuditEntry.model_validate({
        "id": str(r.id), "ts": r.ts, "user": r.username, "action": r.action, "ip": r.ip, "success": r.success,
    })


def to_badge(b: BadgeRow) -> Badge:
    return Badge.model_validate({
        "id": str(b.id), "uid": b.uid, "owner": b.owner, "active": b.active, "last_used": b.last_used,
    })
