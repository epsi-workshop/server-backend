"""Service vision : python -m vision"""
import logging
import os
from datetime import datetime
from pathlib import Path

import cv2

from .config import VERSION, config
from .motion import MotionDetector, annotate
from .publisher import Publisher
from .source import camera_frames
from .stream import FrameHub, serve

log = logging.getLogger("vision")
JPEG_QUALITY = [cv2.IMWRITE_JPEG_QUALITY, 80]


def save_snapshot(directory: Path, jpeg: bytes, now: datetime) -> str:
    """Écriture atomique (fichier temporaire puis renommage) : le backend ne lit jamais une image incomplète."""
    name = f"motion-{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}.jpg"
    tmp = directory / f".{name}.tmp"
    tmp.write_bytes(jpeg)
    os.replace(tmp, directory / name)
    return name


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    log.info("Service vision %s, caméra %s", VERSION, config.camera_url)
    config.snapshot_dir.mkdir(parents=True, exist_ok=True)

    hub = FrameHub()
    serve(hub, config.stream_host, config.stream_port)
    publisher = Publisher(config)
    detector = MotionDetector(config.motion_min_area, config.motion_confirm, config.motion_window,
                              config.warmup_frames)
    last_snapshot = last_publish = 0.0
    was_moving = was_masked = False

    try:
        for frame in camera_frames(config.camera_url, config.camera_user, config.camera_password):
            now = datetime.now()
            result = detector.update(frame)
            ok, buf = cv2.imencode(".jpg", annotate(frame, result, now), JPEG_QUALITY)
            if not ok:
                continue
            jpeg = buf.tobytes()
            hub.publish(jpeg)

            if result.masked != was_masked:
                log.warning("Objectif masqué ou image uniforme" if result.masked else "Image de nouveau normale")
                was_masked = result.masked
            if result.moving != was_moving:
                log.info("Mouvement détecté" if result.moving else "Fin du mouvement")
                was_moving = result.moving
            if not result.moving:
                continue

            t = now.timestamp()
            snapshot = None
            if t - last_snapshot >= config.snapshot_interval_s and result.boxes:
                snapshot = save_snapshot(config.snapshot_dir, jpeg, now)
                last_snapshot = t
                log.info("Capture %s (%d zone(s), %.1f %% de l'image)", snapshot, len(result.boxes), result.area * 100)
            if snapshot or t - last_publish >= config.publish_interval_s:
                publisher.detection("motion", result.confidence, snapshot)
                last_publish = t
    except KeyboardInterrupt:
        pass
    finally:
        publisher.stop()


if __name__ == "__main__":
    main()
