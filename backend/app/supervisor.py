"""Client du superviseur (supervisor/) : état des conteneurs et redémarrages à liste blanche.

Le backend n'a jamais accès au socket Docker : il demande au superviseur, sur le réseau interne
« supervision », avec un jeton partagé (SUPERVISOR_TOKEN).
"""
from typing import Any

import httpx

from .config import config

TIMEOUT = httpx.Timeout(15, connect=3)


class SupervisorError(Exception):
    pass


def _client() -> httpx.AsyncClient:
    if not config.supervisor_url or not config.supervisor_token:
        raise SupervisorError("superviseur non configuré")
    return httpx.AsyncClient(base_url=config.supervisor_url, timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {config.supervisor_token}"})


async def restart(service: str) -> None:
    """Redémarrage en arrière-plan côté superviseur (réponse 202 immédiate)."""
    try:
        async with _client() as client:
            r = await client.post(f"/restart/{service}")
    except httpx.HTTPError as e:
        raise SupervisorError(f"superviseur injoignable ({type(e).__name__})") from None
    if r.status_code != 202:
        raise SupervisorError(f"refusé par le superviseur ({r.status_code})")


async def services() -> list[dict[str, Any]]:
    try:
        async with _client() as client:
            r = await client.get("/services")
            r.raise_for_status()
            return r.json()
    except httpx.HTTPError as e:
        raise SupervisorError(f"superviseur injoignable ({type(e).__name__})") from None
