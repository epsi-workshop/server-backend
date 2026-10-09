"""Lecture du flux MJPEG de l'ESP32-CAM, avec reconnexion automatique.

La lecture tourne dans son propre thread et ne garde que l'image la plus récente : si l'analyse est plus
lente que la caméra (reconnaissance faciale sur l'UNO Q), les images en retard sont abandonnées au lieu de
s'accumuler, sans quoi le flux annoté prend plusieurs secondes de retard.
"""
import logging
import threading
import time
from collections.abc import Iterator

import cv2
import httpx
import numpy as np

log = logging.getLogger(__name__)

SOI, EOI = b"\xff\xd8", b"\xff\xd9"  # début et fin d'une image JPEG
MAX_BUFFER = 2 * 2**20


def split_jpegs(buf: bytes) -> tuple[list[bytes], bytes]:
    """Images JPEG complètes du tampon, et reste à compléter (même logique que backend/app/camera.py)."""
    frames: list[bytes] = []
    while True:
        start = buf.find(SOI)
        if start == -1:
            return frames, buf[-1:]
        end = buf.find(EOI, start + 2)
        if end == -1:
            return frames, buf[start:]
        frames.append(buf[start:end + 2])
        buf = buf[end + 2:]


class LatestFrame:
    """Dernière image JPEG reçue ; l'analyse attend la suivante sans jamais prendre de retard."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._jpeg: bytes | None = None
        self._id = 0
        self.dropped = 0  # images remplacées avant d'avoir été analysées

    def put(self, jpeg: bytes) -> None:
        with self._cond:
            if self._jpeg is not None:
                self.dropped += 1
            self._jpeg = jpeg
            self._id += 1
            self._cond.notify()

    def take(self, timeout: float = 1.0) -> bytes | None:
        with self._cond:
            if self._jpeg is None and not self._cond.wait_for(lambda: self._jpeg is not None, timeout):
                return None
            jpeg, self._jpeg = self._jpeg, None
            return jpeg


def camera_frames(url: str, user: str = "", password: str = "") -> Iterator[np.ndarray]:
    """Images décodées (BGR), indéfiniment, toujours la plus récente (voir LatestFrame)."""
    latest = LatestFrame()
    threading.Thread(target=_read_forever, args=(url, user, password, latest), name="camera", daemon=True).start()
    last_report, reported = time.monotonic(), 0
    while True:
        jpeg = latest.take()
        if jpeg is None:
            continue
        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            yield img
        if time.monotonic() - last_report >= 60 and latest.dropped > reported:
            log.info("%d image(s) en retard abandonnée(s) la dernière minute (analyse plus lente que la caméra)",
                     latest.dropped - reported)
            last_report, reported = time.monotonic(), latest.dropped


def _read_forever(url: str, user: str, password: str, latest: LatestFrame) -> None:
    """Lit le flux et dépose chaque image complète dans `latest` ; se reconnecte si la caméra coupe."""
    auth = httpx.BasicAuth(user, password) if user else None
    retry = 1.0
    while True:
        try:
            with httpx.stream("GET", url, auth=auth, timeout=httpx.Timeout(10, connect=5)) as resp:
                resp.raise_for_status()
                log.info("Connecté à la caméra %s", url)
                retry = 1.0
                buf = b""
                for chunk in resp.iter_bytes():
                    jpegs, buf = split_jpegs(buf + chunk)
                    if jpegs:
                        latest.put(jpegs[-1])  # seule la plus récente compte
                    if len(buf) > MAX_BUFFER:
                        buf = b""
            log.warning("La caméra a fermé le flux")
        except httpx.HTTPStatusError as e:
            log.error("Caméra : HTTP %s%s", e.response.status_code,
                      " (CAMERA_USER / CAMERA_PASSWORD ?)" if e.response.status_code == 401 else "")
        except (httpx.HTTPError, OSError) as e:
            log.warning("Caméra injoignable (%s : %s), nouvel essai dans %.0f s", type(e).__name__, e, retry)
        time.sleep(retry)
        retry = min(retry * 2, 30)
