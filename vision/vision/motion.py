"""Détection de mouvement pour une caméra fixe : soustraction de fond (MOG2) puis zones en mouvement."""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime

import cv2
import numpy as np

Box = tuple[int, int, int, int]  # x, y, largeur, hauteur (pixels de l'image d'origine)

WORK_WIDTH = 320  # analyse sur une image réduite : plus rapide, moins sensible au bruit du capteur
SHADOW_CUT = 200  # MOG2 marque les ombres à 127 : on ne garde que le vrai premier plan (255)
MASKED_STD = 6.0  # écart-type des niveaux de gris en dessous duquel l'image est uniforme (objectif masqué)

RED = (40, 40, 230)
WHITE = (255, 255, 255)
AMBER = (20, 170, 240)


@dataclass
class MotionResult:
    moving: bool  # mouvement confirmé (motion_confirm images sur motion_window)
    raw: bool  # mouvement sur cette image seule
    boxes: list[Box] = field(default_factory=list)
    area: float = 0.0  # fraction de l'image en mouvement
    confidence: float = 0.0  # part des dernières images en mouvement
    masked: bool = False


class MotionDetector:
    def __init__(self, min_area: float, confirm: int, window: int, warmup: int) -> None:
        self.min_area = min_area
        self.confirm = confirm
        self.warmup = warmup
        self.frames = 0
        self.history: deque[bool] = deque(maxlen=window)
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=32, detectShadows=True)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

    def relearn(self, frames: int) -> None:
        """Repart d'un fond vierge (la caméra vient de tourner) avec un court apprentissage de `frames` images.

        Un MOG2 neuf apprend vite ses premières images ; l'historique de confirmation est conservé, pour
        que l'état « mouvement » ne retombe pas pendant un suivi.
        """
        self.bg = cv2.createBackgroundSubtractorMOG2(history=300, varThreshold=32, detectShadows=True)
        self.frames = max(0, self.warmup - frames)

    def update(self, frame: np.ndarray) -> MotionResult:
        h, w = frame.shape[:2]
        scale = WORK_WIDTH / w
        small = cv2.resize(frame, (WORK_WIDTH, max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        masked = float(gray.std()) < MASKED_STD

        mask = self.bg.apply(small)
        _, mask = cv2.threshold(mask, SHADOW_CUT, 255, cv2.THRESH_BINARY)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kernel)  # retire les pixels isolés
        mask = cv2.dilate(mask, self.kernel, iterations=2)  # recolle les morceaux d'un même objet
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        total = mask.shape[0] * mask.shape[1]
        boxes: list[Box] = []
        moving_px = 0.0
        for c in contours:
            a = cv2.contourArea(c)
            if a >= self.min_area * total:
                x, y, bw, bh = cv2.boundingRect(c)
                boxes.append((round(x / scale), round(y / scale), round(bw / scale), round(bh / scale)))
                moving_px += a

        self.frames += 1
        raw = bool(boxes) and self.frames > self.warmup
        self.history.append(raw)
        hits = sum(self.history)
        return MotionResult(
            moving=hits >= self.confirm, raw=raw, boxes=boxes if raw else [],
            area=moving_px / total, confidence=hits / self.history.maxlen if self.history.maxlen else 0.0,
            masked=masked,
        )


def annotate(frame: np.ndarray, result: MotionResult, now: datetime,
             tracking: str | None = None, focus: Box | None = None) -> np.ndarray:
    """Copie de l'image avec les zones en mouvement encadrées, l'horodatage et l'état du suivi.

    tracking : texte affiché à droite du bandeau (ex. « SUIVI 72° ») ; focus : zone suivie.
    """
    out = frame.copy()
    for x, y, w, h in result.boxes:
        cv2.rectangle(out, (x, y), (x + w, y + h), RED, 2)
    if focus is not None:
        x, y, w, h = focus
        cv2.drawMarker(out, (x + w // 2, y + h // 2), AMBER, cv2.MARKER_CROSS, 24, 2)
    label = now.strftime("%d/%m/%Y %H:%M:%S")
    if result.moving:
        label += "  MOUVEMENT"
    cv2.rectangle(out, (0, 0), (out.shape[1], 22), (0, 0, 0), -1)
    cv2.putText(out, label, (6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, RED if result.moving else WHITE, 1, cv2.LINE_AA)
    if tracking:
        (tw, _), _ = cv2.getTextSize(tracking, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(out, tracking, (out.shape[1] - tw - 6, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, AMBER, 1, cv2.LINE_AA)
    return out
