"""Rétention des captures (ENF-09 : « images uniquement liées à une alerte ») et RGPD.

Le service vision enregistre une capture à chaque mouvement, personne ou visage. Seules les captures qu'une
alerte référence sont gardées, au plus retentionDays (la référence de l'alerte est alors effacée) ; les autres
sont supprimées après GRACE, le temps qu'une alerte s'y rattache ou que le bandeau « visage » l'affiche.
Le dossier appartient à vision ; le backend le partage par un groupe (docker-compose.yml, volumes-init).
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update

from .config import config
from .db import AlertRow, SessionLocal
from .journal import write_log
from .live import live
from .util import SNAPSHOT_RE, utcnow

GRACE = timedelta(minutes=15)
INTERVAL_S = 600

log = logging.getLogger(__name__)


def plan_purge(files: dict[str, datetime], kept: dict[str, datetime], now: datetime,
               retention: timedelta) -> tuple[list[str], list[str]]:
    """files : capture -> date du fichier ; kept : capture d'une alerte -> date de l'alerte.

    Renvoie (captures sans alerte à supprimer, captures d'alerte expirées à supprimer).
    """
    orphans = [n for n, mtime in files.items() if n not in kept and now - mtime > GRACE]
    expired = [n for n in files if n in kept and now - kept[n] > retention]
    return sorted(orphans), sorted(expired)


def _list(directory: Path) -> dict[str, datetime]:
    out = {}
    for p in directory.iterdir():
        if SNAPSHOT_RE.fullmatch(p.name):  # ni fichier temporaire (.nom.tmp) ni autre chose
            try:
                out[p.name] = datetime.fromtimestamp(p.stat().st_mtime, UTC)
            except FileNotFoundError:
                pass
    return out


def _delete(directory: Path, names: list[str]) -> int:
    n = 0
    for name in names:
        try:
            (directory / name).unlink()
            n += 1
        except FileNotFoundError:
            pass
    return n


async def purge_once() -> None:
    directory = config.snapshot_dir
    if not directory.is_dir():
        return
    files = await asyncio.to_thread(_list, directory)
    async with SessionLocal() as db:
        rows = await db.execute(select(AlertRow.snapshot_path, AlertRow.ts).where(AlertRow.snapshot_path.is_not(None)))
        kept = {path: ts for path, ts in rows}
    orphans, expired = plan_purge(files, kept, utcnow(), timedelta(days=live.settings.retention_days))
    if not orphans and not expired:
        return
    try:
        deleted = await asyncio.to_thread(_delete, directory, orphans + expired)
    except PermissionError:
        await write_log("error", "backend", "Rétention des captures impossible : dossier en lecture seule pour le backend")
        return
    if expired:
        async with SessionLocal() as db:
            await db.execute(update(AlertRow).where(AlertRow.snapshot_path.in_(expired)).values(snapshot_path=None))
            await db.commit()
    await write_log("info", "backend", f"Rétention : {deleted} capture(s) supprimée(s) "
                    f"({len(orphans)} sans alerte, {len(expired)} d'alertes de plus de {live.settings.retention_days} j)")


async def run() -> None:
    while True:
        try:
            await purge_once()
        except Exception:  # noqa: BLE001 (la rétention ne doit jamais s'arrêter)
            log.exception("Erreur de la rétention des captures")
        await asyncio.sleep(INTERVAL_S)
