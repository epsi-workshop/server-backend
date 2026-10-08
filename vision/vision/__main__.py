"""Service vision : python -m vision"""
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import cv2

from .config import VERSION, config
from .faces import DisplayClient, FaceEvents, FaceRecognizer, draw_faces
from .motion import MotionDetector, MotionResult, annotate
from .person import Confirmer, PersonDetector, PersonWorker, draw_persons
from .publisher import Publisher
from .source import camera_frames
from .stream import FrameHub, serve
from .tracking import ServoClient, Tracker, largest

log = logging.getLogger("vision")
JPEG_QUALITY = [cv2.IMWRITE_JPEG_QUALITY, 80]
MASK_CONFIRM_S = 2.0  # image uniforme pendant 2 s avant de signaler l'objectif masqué (pas sur un flash)
MASK_REPUBLISH_S = 10.0  # état republié tant que ça dure : le backend le retrouve après un redémarrage


def save_snapshot(directory: Path, jpeg: bytes, now: datetime, prefix: str = "motion") -> str:
    """Écriture atomique (fichier temporaire puis renommage) : le backend ne lit jamais une image incomplète."""
    name = f"{prefix}-{now:%Y%m%d-%H%M%S}-{now.microsecond // 1000:03d}.jpg"
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
    was_moving = was_masked = masked_raw = False
    masked_since = last_masked_publish = 0.0

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

    faces = face_events = display = None
    if config.face_models_dir:
        faces = FaceRecognizer(config.face_models_dir, config.faces_dir / "gallery.json",
                               config.face_threshold, config.face_min_px)
        face_events = FaceEvents(cooldown_s=config.face_cooldown_s)
        if config.display_api_url:
            display = DisplayClient(config.display_api_url, config.display_seconds)
        log.info("Reconnaissance faciale active (seuil %.3f)%s", config.face_threshold,
                 f", écran {config.display_api_url}" if display else "")
    last_face_check = 0.0
    seen_faces: list = []

    persons = person_confirm = None
    if config.person_model:
        persons = PersonWorker(PersonDetector(config.person_model, config.person_input_size, config.person_conf))
        person_confirm = Confirmer(config.person_confirm, config.person_window)
        publisher.person_detection = True
        log.info("Détection de personnes active (YOLOX-S, %d px, confiance %.2f, %d sur %d)", config.person_input_size,
                 config.person_conf, config.person_confirm, config.person_window)
    last_person_submit = last_person_analysis = last_person_snapshot = last_person_publish = 0.0
    seen_persons: list = []
    person_present = False
    person_conf = 0.0

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
            new_faces = []
            if faces and mono - last_face_check >= config.face_interval_s and not (tracker and tracker.frozen(mono)):
                last_face_check = mono
                faces.reload()
                seen_faces = faces.analyze(frame)
                new_faces = face_events.update(seen_faces, mono)
            elif faces and mono - last_face_check > 1.0:
                seen_faces = []  # pas d'analyse récente (rotation) : on n'affiche plus de cadre périmé
            if persons and person_confirm:
                # Analyse pendant un mouvement (pré-filtre) ou tant qu'une personne est présente.
                if (result.moving or person_present) and mono - last_person_submit >= config.person_interval_s \
                        and not (tracker and tracker.frozen(mono)):
                    persons.submit(frame.copy())
                    last_person_submit = mono
                if (analysis := persons.take()) is not None:
                    last_person_analysis = analysis.at
                    seen_persons = analysis.persons
                    present = person_confirm.update(bool(analysis.persons))
                    if analysis.persons:
                        person_conf = max(p.confidence for p in analysis.persons)
                    if present != person_present:
                        if present:
                            log.warning("Personne détectée (confiance %.2f, analyse en %.0f ms)", person_conf, analysis.ms)
                        else:
                            log.info("Plus de personne dans le champ")
                        person_present = present
                if mono - last_person_analysis > 2.0:
                    # Plus d'analyse depuis 2 s (fin du mouvement, rotation) : rien de confirmé ni d'affiché.
                    seen_persons = []
                    person_confirm.reset()
                    if person_present:
                        log.info("Plus de personne dans le champ")
                        person_present = False
            label = None  # OpenCV n'affiche pas « ° »
            if tracker:
                label = f"SUIVI {tracker.angle} deg" + (" ..." if tracker.frozen(mono) else "")
            out = annotate(frame, result, now, label, focus)
            if seen_faces:
                draw_faces(out, seen_faces)
            if seen_persons:
                draw_persons(out, seen_persons)
            ok, buf = cv2.imencode(".jpg", out, JPEG_QUALITY)
            if not ok:
                continue
            jpeg = buf.tobytes()
            hub.publish(jpeg)

            for face in new_faces:
                snap = save_snapshot(config.snapshot_dir, jpeg, now, "face")
                if face.member_id:
                    log.info("Visage reconnu : %s (similarité %.2f)", face.name, face.similarity)
                    publisher.detection("face_known", face.similarity, snap, face.member_id)
                else:
                    log.warning("Intrus : visage inconnu (meilleure similarité %.2f)", face.similarity)
                    publisher.detection("face_unknown", face.score, snap)
                if display:
                    display.show(face)

            if person_present:
                t = now.timestamp()
                snap = None
                if t - last_person_snapshot >= config.snapshot_interval_s:
                    snap = save_snapshot(config.snapshot_dir, jpeg, now, "person")
                    last_person_snapshot = t
                if snap or t - last_person_publish >= config.publish_interval_s:
                    publisher.detection("person", person_conf, snap)
                    last_person_publish = t

            # Objectif masqué : confirmé après MASK_CONFIRM_S d'image uniforme (pendant une rotation du servo,
            # l'image n'est pas analysée : l'état précédent est conservé).
            frame_masked = masked_raw if tracker and tracker.frozen(mono) else result.masked
            if frame_masked != masked_raw:
                masked_raw, masked_since = frame_masked, mono
            if masked_raw != was_masked and mono - masked_since >= MASK_CONFIRM_S:
                was_masked = masked_raw
                log.warning("Objectif masqué ou image uniforme" if was_masked else "Image de nouveau normale")
                publisher.masked(was_masked)
                last_masked_publish = mono
            elif was_masked and mono - last_masked_publish >= MASK_REPUBLISH_S:
                publisher.masked(True)
                last_masked_publish = mono
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
