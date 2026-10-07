"""Armement du système, seule porte d'entrée pour le changer (dashboard ou badge).

Armé = porte du pot verrouillée. Chaque changement est poussé aux boîtiers abonnés (hooks) :
l'API capteurs de l'UNO Q s'y inscrit pour mettre à jour l'écran et la sortie « verrou ».
"""
import logging
from collections.abc import Awaitable, Callable

from .live import live

log = logging.getLogger(__name__)

ArmedHook = Callable[[bool], Awaitable[None]]
hooks: list[ArmedHook] = []


async def apply_armed(armed: bool) -> None:
    """Met à jour l'état, le diffuse au dashboard, puis le pousse aux boîtiers (une panne n'empêche rien)."""
    live.state.device.armed = armed
    live.publish()
    for hook in hooks:
        try:
            await hook(armed)
        except Exception as e:  # noqa: BLE001 (boîtier injoignable : journalisé par le hook, l'état reste appliqué)
            log.warning("Armement non transmis au boîtier : %s", e)
