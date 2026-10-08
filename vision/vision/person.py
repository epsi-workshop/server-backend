"""Détection de personnes (EF-04) : YOLOX-S (OpenCV Zoo, licence Apache 2.0) en ONNX, sur le CPU avec OpenCV DNN.

- Le mouvement sert de pré-filtre : l'analyse ne tourne que pendant un mouvement, dans un thread dédié qui
  traite toujours l'image la plus récente, pour ne jamais ralentir le flux annoté.
- Image réduite à 416 px (environ 6 analyses par seconde sur le PC serveur, ENF-04), classe COCO « person » seule.
- Une personne est confirmée sur `confirm` analyses parmi les `window` dernières (3 sur 5) : un reflet ou une
  ombre isolés ne déclenchent rien.
"""
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

log = logging.getLogger(__name__)

MODEL = "object_detection_yolox_2022nov.onnx"
STRIDES = (8, 16, 32)
PAD_VALUE = 114  # gris de remplissage utilisé à l'entraînement de YOLOX
PERSON_CLASS = 0  # COCO


@dataclass
class Person:
    box: tuple[int, int, int, int]  # x, y, largeur, hauteur dans l'image d'origine
    confidence: float


def letterbox(frame: np.ndarray, size: int) -> tuple[np.ndarray, float]:
    """Image réduite sans déformation dans un carré size x size, au format d'entrée de YOLOX (NCHW, float32)."""
    ratio = min(size / frame.shape[0], size / frame.shape[1])
    resized = cv2.resize(frame, (int(frame.shape[1] * ratio), int(frame.shape[0] * ratio)),
                         interpolation=cv2.INTER_LINEAR)
    padded = np.full((size, size, 3), PAD_VALUE, np.uint8)
    padded[:resized.shape[0], :resized.shape[1]] = resized
    return padded.transpose(2, 0, 1)[None].astype(np.float32), ratio


def _grid(size: int) -> tuple[np.ndarray, np.ndarray]:
    grids, strides = [], []
    for s in STRIDES:
        n = size // s
        xv, yv = np.meshgrid(np.arange(n), np.arange(n))
        grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
        strides.append(np.full((n * n, 1), s))
    return np.concatenate(grids).astype(np.float32), np.concatenate(strides).astype(np.float32)


def decode(output: np.ndarray, size: int, ratio: float, conf: float, nms: float) -> list[Person]:
    """Sortie brute de YOLOX (1, N, 85) -> personnes dans l'image d'origine, après suppression des doublons."""
    grid, stride = _grid(size)
    det = output.reshape(-1, output.shape[-1])
    if len(det) != len(grid):
        raise ValueError(f"Sortie du modèle inattendue : {len(det)} prédictions pour {len(grid)} cellules")
    centers = (det[:, :2] + grid) * stride
    sizes = np.exp(det[:, 2:4]) * stride
    scores = det[:, 4] * det[:, 5 + PERSON_CLASS]  # objet x classe « personne »
    keep = scores >= conf
    if not keep.any():
        return []
    centers, sizes, scores = centers[keep] / ratio, sizes[keep] / ratio, scores[keep]
    boxes = np.column_stack([centers - sizes / 2, sizes])
    idx = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf, nms)
    return [Person(tuple(int(v) for v in boxes[i]), float(scores[i]))  # type: ignore[arg-type]
            for i in np.array(idx).flatten()]


class PersonDetector:
    def __init__(self, model: Path, size: int = 416, conf: float = 0.5, nms: float = 0.45) -> None:
        self.net = cv2.dnn.readNetFromONNX(str(model))
        self.size, self.conf, self.nms = size, conf, nms

    def detect(self, frame: np.ndarray) -> list[Person]:
        blob, ratio = letterbox(frame, self.size)
        self.net.setInput(blob)
        return decode(self.net.forward(), self.size, ratio, self.conf, self.nms)


class Confirmer:
    """Personne confirmée sur `confirm` analyses parmi les `window` dernières."""

    def __init__(self, confirm: int, window: int) -> None:
        self.confirm = confirm
        self.recent: deque[bool] = deque(maxlen=window)

    def update(self, found: bool) -> bool:
        self.recent.append(found)
        return sum(self.recent) >= self.confirm

    def reset(self) -> None:
        self.recent.clear()


@dataclass
class Analysis:
    persons: list[Person]
    at: float  # time.monotonic() de la fin de l'analyse
    ms: float  # durée de l'analyse


class PersonWorker:
    """Analyse en arrière-plan : une seule image en attente (la plus récente), un résultat à la fois."""

    def __init__(self, detector: PersonDetector) -> None:
        self.detector = detector
        self._frame: np.ndarray | None = None
        self._result: Analysis | None = None
        self._cond = threading.Condition()
        threading.Thread(target=self._run, name="personnes", daemon=True).start()

    def submit(self, frame: np.ndarray) -> None:
        with self._cond:
            self._frame = frame
            self._cond.notify()

    def take(self) -> Analysis | None:
        """Dernier résultat, une seule fois (None si aucune nouvelle analyse depuis le dernier appel)."""
        with self._cond:
            result, self._result = self._result, None
            return result

    def _run(self) -> None:
        while True:
            with self._cond:
                while self._frame is None:
                    self._cond.wait()
                frame, self._frame = self._frame, None
            start = time.monotonic()
            try:
                persons = self.detector.detect(frame)
            except cv2.error as e:  # image corrompue : on passe à la suivante
                log.warning("Analyse impossible : %s", e)
                continue
            end = time.monotonic()
            with self._cond:
                self._result = Analysis(persons, end, (end - start) * 1000)


def draw_persons(frame: np.ndarray, persons: list[Person]) -> None:
    for p in persons:
        x, y, w, h = p.box
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(frame, f"PERSONNE {p.confidence:.0%}", (x, max(14, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                    (0, 0, 255), 1, cv2.LINE_AA)
