"""Sons du boîtier déclenchés par le backend : alarme intrusion, « Bonjour <prénom> », arrêt, voix.

Règles (ingest.py, arming.py) : l'alarme ne part que pour un visage inconnu pendant que le système est
armé ; elle s'arrête sur un visage reconnu, un badge valide, le désarmement ou l'acquittement.

La sortie (haut-parleur du boîtier, enceinte Bluetooth, les deux) est choisie sur l'UNO Q : le backend
ne fait qu'envoyer l'événement. L'API capteurs s'inscrit dans `senders` (sensor_api.py).
"""
import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

log = logging.getLogger(__name__)

ALARM_SECONDS = 120  # durée maximale de la sirène sur la carte ; arrêtée avant par les règles ci-dessus
_alarm_until = 0.0
# Envoi d'une requête POST au boîtier : (route, paramètres, corps JSON)
Sender = Callable[[str, dict[str, Any] | None, dict[str, Any] | None], Awaitable[None]]
senders: list[Sender] = []
_tasks: set[asyncio.Task[None]] = set()


async def _send(path: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> None:
    for send in senders:
        try:
            await send(path, params, body)
        except Exception as e:  # noqa: BLE001 (boîtier injoignable : l'alerte reste enregistrée)
            log.warning("Son non transmis au boîtier (%s) : %s", path, e)


def _background(path: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> None:
    """Sans attendre la réponse : la synthèse vocale de la carte peut prendre quelques secondes."""
    task = asyncio.create_task(_send(path, params, body))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


def alarm(seconds: int = ALARM_SECONDS) -> None:
    """Intrusion : « Alerte. Intrusion détectée. » puis sirène."""
    global _alarm_until
    _alarm_until = time.monotonic() + seconds
    _background("/sound/alarm", {"seconds": seconds})


def alarm_active() -> bool:
    return time.monotonic() < _alarm_until


def stop() -> None:
    global _alarm_until
    _alarm_until = 0.0
    _background("/sound/stop")


def hello(name: str) -> None:
    """Visage reconnu : carillon et « Bonjour <prénom> » sur la sortie choisie."""
    _background("/sound/hello", {"name": name})


def prepare_voice(*texts: str) -> None:
    """Fait synthétiser les phrases à l'avance (ex. « Bonjour Léa » à l'ajout d'un membre)."""
    _background("/audio/voice/prepare", None, {"texts": list(texts)})
