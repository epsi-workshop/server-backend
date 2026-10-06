"""Audit (actions des utilisateurs) et journal applicatif (page Journaux).

Chaque écriture utilise sa propre session SQL : un échec de connexion reste journalisé
même si la requête qui l'a provoqué se termine en erreur.
"""
from .convert import to_log
from .db import AuditRow, LogRow, SessionLocal
from .hub import hub
from .schemas import LogLevel, LogSource, dump
from .util import clean


async def write_audit(user: str, action: str, ip: str, success: bool = True) -> None:
    async with SessionLocal() as db:
        db.add(AuditRow(username=clean(user, 64), action=clean(action, 500), ip=ip, success=success))
        await db.commit()


async def write_log(level: LogLevel, source: LogSource, message: str) -> None:
    async with SessionLocal() as db:
        row = LogRow(level=level, source=source, message=clean(message, 1000))
        db.add(row)
        await db.commit()
    # Les journaux ne sont visibles qu'à partir du rôle opérateur.
    hub.broadcast({"type": "log", "data": dump(to_log(row))}, min_role="operateur")
