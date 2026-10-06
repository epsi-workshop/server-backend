"""Service vision : python -m vision"""
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import cv2

from .config import VERSION, config
from .motion import MotionDetector, MotionResult, annotate
from .publisher import Publisher
from .source import camera_frames
from .stream import FrameHub, serve
from .tracking import ServoClient, Tracker, largest

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

    tracker = servo = None
    if config.servo_api_url:
        servo = ServoClient(config.servo_api_url)
        tracker = Tracker(
            fov_deg=config.track_fov_deg, deadband=config.track_deadband, gain=config.track_gain,
            speed=config.track_speed, settle_s=config.track_settle_s, min_interval_s=config.track_min_interval_s,
            invert=config.track_invert, home_angle=config.track_home_angle,
            home_after_s=config.track_home_after_s, now=time.monotonic(),
        )
        # Position de départ connue : retour au repos, sans attendre la réponse de l'API.
        servo.move(tracker.home(time.monotonic()), config.track_speed)
        log.info("Suivi actif : servo %s, repos à %d°", config.servo_api_url, tracker.angle)
    relearn_pending = False

    try:
        for frame in camera_frames(config.camera_url, config.camera_user, config.camera_password):
            now = datetime.now()
            mono = time.monotonic()
            focus = None
            if tracker and tracker.frozen(mono):
                # Caméra en rotation : l'image entière bouge, la détection n'a pas de sens.
                # L'état « mouvement » est conservé pour ne pas interrompre l'alerte en cours.
                result = MotionResult(moving=was_moving, raw=False)
                relearn_pending = True
            else:
                if relearn_pending:
                    detector.relearn(config.track_relearn_frames)
                    relearn_pending = False
                result = detector.update(frame)
                if tracker:
                    boxes = result.boxes if result.moving else []
                    focus = largest(boxes)
                    target = tracker.update(mono, boxes, frame.shape[1])
                    if target is not None:
                        servo.move(target, config.track_speed)
            label = None  # OpenCV n'affiche pas « ° »
            if tracker:
                label = f"SUIVI {tracker.angle} deg" + (" ..." if tracker.frozen(mono) else "")
            ok, buf = cv2.imencode(".jpg", annotate(frame, result, now, label, focus), JPEG_QUALITY)
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
