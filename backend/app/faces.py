"""Reconnaissance faciale, côté backend : enrôlement des membres de l'équipe et galerie du service vision.

À l'ajout d'un membre, sa photo passe par YuNet (détection) puis SFace (empreinte de 128 valeurs).
Les empreintes des membres actifs sont écrites dans faces_dir/gallery.json, que le service vision
relit dès qu'il change. Modèles OpenCV Zoo : scripts/download-face-models.sh.
"""
import json
import os
import threading
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np

from .config import config

DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"
MAX_SIDE = 1280  # photo réduite avant détection (les photos de téléphone font 4000 px)
THUMB_SIDE = 160
MIN_FACE_PX = 60  # visage trop petit sur la photo d'enrôlement : empreinte peu fiable

_lock = threading.Lock()
_models: tuple[Any, Any] | None = None


class EnrollError(ValueError):
    """Photo refusée, avec un message lisible pour l'administrateur."""


@dataclass
class Enrollment:
    embedding: list[float]
    thumbnail: bytes  # JPEG carré centré sur le visage


def _load() -> tuple[Any, Any]:
    global _models
    if _models is None:
        det, rec = config.face_models_dir / DETECTOR_MODEL, config.face_models_dir / RECOGNIZER_MODEL
        if not det.exists() or not rec.exists():
            raise EnrollError(f"Modèles de reconnaissance absents de {config.face_models_dir} "
                              "(scripts/download-face-models.sh).")
        _models = (cv2.FaceDetectorYN.create(str(det), "", (320, 320), 0.8),
                   cv2.FaceRecognizerSF.create(str(rec), ""))
    return _models


def enroll(photo: bytes) -> Enrollment:
    """Empreinte du visage de la photo. Refuse une photo sans visage, avec plusieurs visages ou trop floue."""
    img = cv2.imdecode(np.frombuffer(photo, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise EnrollError("Image illisible : JPEG ou PNG attendu.")
    scale = MAX_SIDE / max(img.shape[:2])
    if scale < 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    h, w = img.shape[:2]
    with _lock:  # les objets OpenCV ne sont pas utilisables depuis plusieurs threads à la fois
        detector, recognizer = _load()
        detector.setInputSize((w, h))
        _, faces = detector.detect(img)
        faces = [] if faces is None else list(faces)
        if not faces:
            raise EnrollError("Aucun visage détecté : photo de face, bien éclairée, visage dégagé.")
        if len(faces) > 1:
            raise EnrollError(f"{len(faces)} visages sur la photo : une seule personne attendue.")
        face = faces[0]
        if min(face[2], face[3]) < MIN_FACE_PX:
            raise EnrollError("Visage trop petit : cadrez plus serré.")
        aligned = recognizer.alignCrop(img, face)
        feature = recognizer.feature(aligned).flatten()
    embedding = (feature / np.linalg.norm(feature)).astype(float)
    return Enrollment(embedding=[round(v, 6) for v in embedding.tolist()], thumbnail=_thumbnail(img, face))


def _thumbnail(img: np.ndarray, face: np.ndarray) -> bytes:
    x, y, fw, fh = (int(v) for v in face[:4])
    side = int(max(fw, fh) * 1.8)
    cx, cy = x + fw // 2, y + fh // 2
    h, w = img.shape[:2]
    x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
    crop = img[y0:min(h, y0 + side), x0:min(w, x0 + side)]
    crop = cv2.resize(crop, (THUMB_SIDE, THUMB_SIDE), interpolation=cv2.INTER_AREA)
    return cv2.imencode(".jpg", crop, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def write_gallery(members: list[dict[str, Any]]) -> None:
    """Écriture atomique : le service vision ne lit jamais une galerie à moitié écrite."""
    config.faces_dir.mkdir(parents=True, exist_ok=True)
    path = config.faces_dir / "gallery.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": 1, "members": members}), encoding="utf-8")
    os.replace(tmp, path)
