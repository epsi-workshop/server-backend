"""Badges : enregistrement par lecture et retour sur l'écran du boîtier.

Enregistrement : l'administrateur lance une écoute (ENROLL_SECONDS) ; le prochain badge passé sur le
lecteur n'est ni accepté ni refusé, son UID est capturé et proposé dans le formulaire du dashboard.

Écran : chaque décision (accepté, refusé, nouveau badge) est poussée aux boîtiers abonnés (hooks) ;
l'API capteurs de l'UNO Q s'y inscrit (route /display/badge).
"""
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .util import utcnow

log = logging.getLogger(__name__)

ENROLL_SECONDS = 30
BadgeResult = Literal["ok", "refused", "enroll"]
DisplayHook = Callable[[BadgeResult, str, str | None], Awaitable[None]]
hooks: list[DisplayHook] = []


@dataclass
class Enrollment:
    until: datetime | None = None
    uid: str | None = None
    owner: str | None = None  # titulaire si le badge lu est déjà enregistré

    def active(self, now: datetime | None = None) -> bool:
        return self.until is not None and self.uid is None and (now or utcnow()) < self.until

    def start(self) -> None:
        self.until, self.uid, self.owner = utcnow() + timedelta(seconds=ENROLL_SECONDS), None, None

    def stop(self) -> None:
        self.until = None


enrollment = Enrollment()


async def show(result: BadgeResult, uid: str, name: str | None) -> None:
    """Affiche le résultat sur les boîtiers ; une panne d'écran n'empêche jamais la décision."""
    for hook in hooks:
        try:
            await hook(result, uid, name)
        except Exception as e:  # noqa: BLE001
            log.warning("Résultat du badge non affiché sur le boîtier : %s", e)
