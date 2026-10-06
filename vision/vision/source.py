"""Lecture du flux MJPEG de l'ESP32-CAM, avec reconnexion automatique."""
import logging
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


def camera_frames(url: str, user: str = "", password: str = "") -> Iterator[np.ndarray]:
    """Images décodées (BGR), indéfiniment : se reconnecte si la caméra coupe ou redémarre."""
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
                    for jpeg in jpegs:
                        img = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                        if img is not None:
                            yield img
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
