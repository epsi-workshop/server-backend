"""Notifications push (ntfy, #16) : alertes de niveau Alerte et Critique, avec la capture de la caméra.

Publication sur NTFY_URL/NTFY_TOPIC avec un jeton en écriture seule (scripts/setup-ntfy.sh). Les champs
passent en paramètres d'URL, qui acceptent l'UTF-8 (pas les en-têtes HTTP) ; la capture est le corps de la
requête, reçue en pièce jointe par l'application ntfy des opérateurs. L'envoi ne bloque jamais le moteur de
corrélation : tâche en arrière-plan, échec journalisé.
"""
import asyncio
from pathlib import Path

import httpx

from .config import config
from .db import AlertRow
from .journal import write_log
from .util import SNAPSHOT_RE

PRIORITY = {"alerte": "high", "critique": "urgent"}
TAGS = {"alerte": "warning", "critique": "rotating_light"}
MAX_ATTACHMENT = 5 * 1024 * 1024
TIMEOUT = httpx.Timeout(8, connect=3)

_tasks: set[asyncio.Task[None]] = set()


def build(alert: AlertRow, escalated: bool) -> dict[str, str]:
    """Paramètres de la notification (sans la capture)."""
    level = "CRITIQUE" if alert.level == "critique" else "Alerte"
    params = {
        "title": f"{level} : {alert.title}" + (" (escaladée)" if escalated else ""),
        "message": f"Score {alert.score}. " + (", ".join(alert.reasons) or "Aucun détail."),
        "priority": PRIORITY.get(alert.level, "default"),
        "tags": TAGS.get(alert.level, "bell"),
    }
    if config.dashboard_url:
        params["click"] = f"{config.dashboard_url.rstrip('/')}/#/alertes"
    return params


def snapshot_file(name: str | None, directory: Path) -> Path | None:
    """Capture jointe : nom conforme au contrat, fichier présent et de taille raisonnable."""
    if not name or not SNAPSHOT_RE.fullmatch(name):
        return None
    path = directory / name
    try:
        return path if path.is_file() and path.stat().st_size <= MAX_ATTACHMENT else None
    except OSError:
        return None


async def _send(params: dict[str, str], snapshot: Path | None) -> None:
    headers = {"Authorization": f"Bearer {config.ntfy_token}"} if config.ntfy_token else {}
    url = f"{config.ntfy_url.rstrip('/')}/{config.ntfy_topic}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            if snapshot is not None:
                body = await asyncio.to_thread(snapshot.read_bytes)
                r = await client.put(url, params={**params, "filename": snapshot.name}, content=body, headers=headers)
            else:
                r = await client.post(url, params=params, headers=headers)
            r.raise_for_status()
    except (httpx.HTTPError, OSError) as e:
        await write_log("warn", "backend", f"Notification push non envoyée : {type(e).__name__}"
                        + (f" ({e.response.status_code})" if isinstance(e, httpx.HTTPStatusError) else ""))


def notify(alert: AlertRow, escalated: bool = False) -> None:
    """Envoie la notification en arrière-plan. Sans effet si NTFY_URL est vide."""
    if not config.ntfy_url:
        return
    task = asyncio.create_task(_send(build(alert, escalated), snapshot_file(alert.snapshot_path, config.snapshot_dir)))
    _tasks.add(task)  # référence gardée jusqu'à la fin : une tâche sans référence peut être détruite
    task.add_done_callback(_tasks.discard)
