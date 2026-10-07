"""Reconnaissance faciale : YuNet (détection) + SFace (empreinte), comparée à la galerie du backend.

La galerie (faces_dir/gallery.json) contient l'empreinte de chaque membre actif de l'équipe ; le backend
la réécrit à chaque ajout ou suppression, ce service la relit dès que le fichier change.
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import httpx
import numpy as np

from .tracking import IPV4_ONLY, TIMEOUT

log = logging.getLogger(__name__)

DETECTOR_MODEL = "face_detection_yunet_2023mar.onnx"
RECOGNIZER_MODEL = "face_recognition_sface_2021dec.onnx"
UNKNOWN = "?"  # clé des visages inconnus dans FaceEvents


@dataclass
class Face:
    box: tuple[int, int, int, int]  # x, y, largeur, hauteur
    score: float  # confiance de la détection
    member_id: str | None = None  # None : visage inconnu
    name: str | None = None
    similarity: float = 0.0  # cosinus avec le membre le plus proche

    @property
    def key(self) -> str:
        return self.member_id or UNKNOWN


class FaceRecognizer:
    def __init__(self, models_dir: Path, gallery: Path, threshold: float, min_face_px: int) -> None:
        self.detector = cv2.FaceDetectorYN.create(str(models_dir / DETECTOR_MODEL), "", (320, 320), 0.8)
        self.recognizer = cv2.FaceRecognizerSF.create(str(models_dir / RECOGNIZER_MODEL), "")
        self.gallery_path = gallery
        self.threshold = threshold
        self.min_face_px = min_face_px
        self._mtime = 0.0
        self._ids: list[str] = []
        self._names: list[str] = []
        self._matrix = np.zeros((0, 128), np.float32)
        self.reload()

    def reload(self) -> None:
        """Relit la galerie si le fichier a changé (appelé à chaque analyse : un simple stat)."""
        try:
            mtime = self.gallery_path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0.0
        if mtime == self._mtime:
            return
        self._mtime = mtime
        members = []
        if mtime:
            try:
                members = json.loads(self.gallery_path.read_text(encoding="utf-8"))["members"]
            except (OSError, ValueError, KeyError) as e:
                log.warning("Galerie illisible (%s) : tous les visages seront inconnus", e)
        self._ids = [m["id"] for m in members]
        self._names = [m["name"] for m in members]
        self._matrix = np.array([m["embedding"] for m in members], np.float32).reshape(-1, 128)
        log.info("Galerie : %d membre(s) %s", len(members), ", ".join(self._names))

    @property
    def size(self) -> int:
        return len(self._ids)

    def analyze(self, frame: np.ndarray) -> list[Face]:
        h, w = frame.shape[:2]
        self.detector.setInputSize((w, h))
        _, detections = self.detector.detect(frame)
        faces = []
        for d in [] if detections is None else detections:
            x, y, fw, fh = (int(v) for v in d[:4])
            if min(fw, fh) < self.min_face_px:
                continue  # trop loin : empreinte peu fiable, on ne conclut pas
            face = Face(box=(x, y, fw, fh), score=float(d[14]))
            if self.size:
                feature = self.recognizer.feature(self.recognizer.alignCrop(frame, d)).flatten()
                feature /= np.linalg.norm(feature)
                sims = self._matrix @ feature
                best = int(np.argmax(sims))
                face.similarity = float(sims[best])
                if face.similarity >= self.threshold:
                    face.member_id, face.name = self._ids[best], self._names[best]
            faces.append(face)
        return faces


@dataclass
class FaceEvents:
    """Transforme les analyses image par image en événements « visage reconnu » / « intrus ».

    Une identité doit être vue sur `confirm` analyses consécutives (évite les erreurs d'une seule image),
    puis n'est plus signalée pendant `cooldown_s`. Un visage inconnu demande `confirm_unknown` analyses,
    et n'est pas signalé pendant `known_grace_s` après un membre reconnu : un membre de profil ou flou
    donne souvent quelques images « inconnu ».
    """
    confirm: int = 2
    confirm_unknown: int = 4
    cooldown_s: float = 30.0
    known_grace_s: float = 5.0
    streak: dict[str, int] = field(default_factory=dict)
    last_event: dict[str, float] = field(default_factory=dict)
    last_known: float = -1e9

    def update(self, faces: list[Face], now: float | None = None) -> list[Face]:
        now = time.monotonic() if now is None else now
        seen: dict[str, Face] = {}
        for f in faces:
            # Un même membre vu deux fois sur l'image : on garde la meilleure correspondance.
            if f.key not in seen or f.similarity > seen[f.key].similarity:
                seen[f.key] = f
        self.streak = {k: self.streak.get(k, 0) + 1 for k in seen}
        if any(k != UNKNOWN for k in seen):
            self.last_known = now
        events = []
        for key, face in seen.items():
            if key == UNKNOWN:
                if self.streak[key] < self.confirm_unknown or now - self.last_known < self.known_grace_s:
                    continue
            elif self.streak[key] < self.confirm:
                continue
            if now - self.last_event.get(key, -1e9) >= self.cooldown_s:
                self.last_event[key] = now
                events.append(face)
        return events


def draw_faces(frame: np.ndarray, faces: list[Face]) -> None:
    for f in faces:
        x, y, w, h = f.box
        color = (90, 200, 90) if f.member_id else (60, 60, 230)
        label = f.name.upper() if f.name else "INCONNU"
        label = label.encode("ascii", "replace").decode()  # OpenCV n'affiche pas les accents
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, f"{label} {f.similarity:.2f}", (x, max(14, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)


class DisplayClient:
    """Affiche le résultat sur l'écran OLED de l'UNO Q (POST /display/face), dans un thread."""

    def __init__(self, base_url: str, seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.seconds = seconds
        self.client = httpx.Client(timeout=TIMEOUT, transport=httpx.HTTPTransport(local_address=IPV4_ONLY))
        self._cond = threading.Condition()
        self._pending: dict | None = None
        self._ok: bool | None = None
        threading.Thread(target=self._run, name="display", daemon=True).start()

    def show(self, face: Face) -> None:
        msg = {"kind": "known" if face.member_id else "unknown", "name": (face.name or "")[:16],
               "seconds": self.seconds}
        with self._cond:
            self._pending = msg  # seul le dernier message compte
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending is not None)
                msg, self._pending = self._pending, None
            try:
                self.client.post(f"{self.base_url}/display/face", json=msg).raise_for_status()
                self._ok = True
            except httpx.HTTPError as e:
                if self._ok is not False:
                    log.warning("Écran injoignable (%s : %s)", type(e).__name__, e)
                self._ok = False
