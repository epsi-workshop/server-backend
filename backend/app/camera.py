"""Relais du flux MJPEG annoté vers le dashboard (#17).

La source (CAMERA_URL) est le flux relayé par l'API de l'UNO Q (http://talos.local:8000/camera/stream)
ou celui du service vision. Le backend
ouvre une seule connexion, seulement tant qu'au moins un utilisateur regarde, et redistribue
chaque image. Il peut aussi lire directement une ESP32-CAM (qui n'accepte qu'un client à la fois).
"""
import asyncio
import contextlib
from collections.abc import AsyncIterator
from urllib.parse import urlsplit

import httpx

from .config import config
from .journal import write_log
from .live import live
from .netaddr import ipv4_url

SOI, EOI = b"\xff\xd8", b"\xff\xd9"  # début et fin d'une image JPEG
MAX_BUFFER = 2 * 2**20  # au-delà, le flux est corrompu : on repart de zéro
PROBE_INTERVAL_S = 10
PROBE_TIMEOUT_S = 5
_END = b""  # signal de fin envoyé aux spectateurs quand la connexion à la caméra tombe


def split_jpegs(buf: bytes) -> tuple[list[bytes], bytes]:
    """Images JPEG complètes contenues dans le tampon, et reste à compléter par la suite du flux.

    On ne s'appuie pas sur les en-têtes multipart de la caméra : les marqueurs SOI/EOI suffisent
    (FF D9 ne peut pas apparaître dans les données compressées, où FF est toujours suivi de 00).
    """
    frames: list[bytes] = []
    while True:
        start = buf.find(SOI)
        if start == -1:
            return frames, buf[-1:]  # un FF isolé peut être le début du prochain SOI
        end = buf.find(EOI, start + 2)
        if end == -1:
            return frames, buf[start:]
        frames.append(buf[start:end + 2])
        buf = buf[end + 2:]


def _push(q: asyncio.Queue[bytes], item: bytes) -> None:
    """Spectateur lent : on jette l'image la plus ancienne plutôt que de retarder le flux."""
    if q.full():
        q.get_nowait()
    q.put_nowait(item)


class CameraRelay:
    def __init__(self) -> None:
        self.viewers: set[asyncio.Queue[bytes]] = set()
        self._reader: asyncio.Task[None] | None = None

    @property
    def streaming(self) -> bool:
        return self._reader is not None and not self._reader.done()

    async def frames(self) -> AsyncIterator[bytes]:
        """Images JPEG successives ; s'arrête si la caméra devient injoignable."""
        q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2)
        self.viewers.add(q)
        if not self.streaming:
            self._reader = asyncio.create_task(self._read())
        try:
            while (jpeg := await q.get()) != _END:
                yield jpeg
        finally:
            self.viewers.discard(q)

    @staticmethod
    def _auth() -> httpx.BasicAuth | None:
        return httpx.BasicAuth(config.camera_user, config.camera_password) if config.camera_user else None

    async def _read(self) -> None:
        try:
            async with (
                httpx.AsyncClient(auth=self._auth(), timeout=httpx.Timeout(10, connect=5)) as client,
                client.stream("GET", await ipv4_url(config.camera_url)) as resp,
            ):
                resp.raise_for_status()
                buf = b""
                async for chunk in resp.aiter_bytes():
                    if not self.viewers:
                        return  # plus personne ne regarde : on libère la caméra
                    frames, buf = split_jpegs(buf + chunk)
                    for jpeg in frames:
                        for q in list(self.viewers):
                            _push(q, jpeg)
                    if len(buf) > MAX_BUFFER:
                        buf = b""
        except httpx.HTTPStatusError as e:
            await write_log("error", "camera", f"Flux caméra refusé : HTTP {e.response.status_code}"
                            + (" (identifiants CAMERA_USER/CAMERA_PASSWORD ?)" if e.response.status_code == 401 else ""))
        except (httpx.HTTPError, OSError) as e:
            await write_log("warn", "camera", f"Flux caméra interrompu : {type(e).__name__} {e}".strip())
        finally:
            for q in list(self.viewers):
                _push(q, _END)

    async def _first_frame(self) -> bool:
        """Une image complète arrive-t-elle ? (talos et le service vision acceptent plusieurs clients.)"""
        # Résolution du nom hors du délai de la sonde : elle peut prendre plus de PROBE_TIMEOUT_S (mDNS).
        url = await ipv4_url(config.camera_url)
        with contextlib.suppress(httpx.HTTPError, OSError, TimeoutError):
            async with asyncio.timeout(PROBE_TIMEOUT_S), httpx.AsyncClient(auth=self._auth()) as client, \
                    client.stream("GET", url) as resp:
                if resp.status_code != 200:
                    return False
                buf = b""
                async for chunk in resp.aiter_bytes():
                    frames, buf = split_jpegs(buf + chunk)
                    if frames:
                        return True
        return False

    async def probe(self) -> None:
        """camera.online : le flux délivre des images."""
        host = urlsplit(config.camera_url).netloc
        while True:
            online = self.streaming or await self._first_frame()
            if online != live.state.camera.online:
                live.state.camera.online = online
                live.publish()
                await write_log("info" if online else "warn", "camera",
                                f"Flux caméra {'disponible' if online else 'indisponible'} ({host})")
            await asyncio.sleep(PROBE_INTERVAL_S)


camera = CameraRelay()
