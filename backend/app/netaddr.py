"""Résolution des noms en .local (mDNS), mise en cache.

Sous Windows, trouver l'adresse de talos.local prend 5 à 11 s à chaque connexion, et le nom annonce
aussi une adresse IPv6 sur laquelle l'API n'écoute pas. On résout donc le nom une fois, en IPv4
seulement, et on réutilise l'adresse pendant CACHE_S : l'URL devient http://172.20.10.2:8000/…
"""
import asyncio
import socket
import time
from urllib.parse import urlsplit, urlunsplit

CACHE_S = 300
RESOLVE_TIMEOUT_S = 20

_cache: dict[str, tuple[str, float]] = {}  # nom -> (IPv4, instant de la résolution)


async def ipv4_url(url: str) -> str:
    """URL avec l'IPv4 à la place d'un nom en .local ; l'URL d'origine si ce n'est pas un .local ou en cas d'échec."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    if not host.endswith(".local"):
        return url
    cached = _cache.get(host)
    if cached is None or time.monotonic() - cached[1] > CACHE_S:
        try:
            infos = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(host, parts.port, family=socket.AF_INET, type=socket.SOCK_STREAM),
                RESOLVE_TIMEOUT_S,
            )
        except (OSError, TimeoutError):
            return url
        cached = _cache[host] = (infos[0][4][0], time.monotonic())
    netloc = cached[0] + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))
