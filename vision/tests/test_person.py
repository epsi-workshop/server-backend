"""Détection de personnes : décodage de la sortie YOLOX, mise à l'échelle, confirmation sur plusieurs analyses."""
import os
from pathlib import Path

import numpy as np
import pytest

from vision.person import MODEL, STRIDES, Confirmer, PersonDetector, decode, letterbox

SIZE = 416
CELLS = sum((SIZE // s) ** 2 for s in STRIDES)


def raw_output(cell: int, dx: float, dy: float, w: float, h: float, obj: float, person: float) -> np.ndarray:
    """Sortie YOLOX (1, N, 85) avec une seule prédiction non nulle, dans la cellule `cell` (stride 8)."""
    out = np.zeros((1, CELLS, 85), np.float32)
    out[0, :, 2:4] = -10  # boîtes minuscules partout ailleurs
    out[0, cell, :4] = [dx, dy, np.log(w / 8), np.log(h / 8)]
    out[0, cell, 4] = obj
    out[0, cell, 5] = person
    return out


def test_letterbox_keeps_aspect_ratio_and_pads() -> None:
    frame = np.full((480, 640, 3), 200, np.uint8)
    blob, ratio = letterbox(frame, SIZE)
    assert blob.shape == (1, 3, SIZE, SIZE) and blob.dtype == np.float32
    assert ratio == pytest.approx(SIZE / 640)
    assert blob[0, :, -1, 0].tolist() == [114, 114, 114]  # bande de remplissage en bas


def test_decode_maps_box_back_to_original_image() -> None:
    n = SIZE // 8
    cell = 10 * n + 20  # ligne 10, colonne 20 de la grille de stride 8
    out = raw_output(cell, dx=0.5, dy=0.5, w=80, h=160, obj=0.95, person=0.9)
    persons = decode(out, SIZE, ratio=0.5, conf=0.5, nms=0.45)
    assert len(persons) == 1
    x, y, w, h = persons[0].box
    # Centre (20,5 ; 10,5) x 8 = (164 ; 84) dans l'image réduite, soit (328 ; 168) dans l'originale.
    assert (x + w / 2, y + h / 2) == pytest.approx((328, 168), abs=1)
    assert (w, h) == pytest.approx((160, 320), abs=1)
    assert persons[0].confidence == pytest.approx(0.855, abs=1e-3)


def test_decode_ignores_weak_or_other_classes() -> None:
    assert decode(raw_output(5, 0, 0, 50, 50, obj=0.9, person=0.3), SIZE, 1.0, 0.5, 0.45) == []
    out = raw_output(5, 0, 0, 50, 50, obj=0.9, person=0.0)
    out[0, 5, 5 + 2] = 0.99  # une voiture, pas une personne
    assert decode(out, SIZE, 1.0, 0.5, 0.45) == []


def test_decode_rejects_unexpected_output_shape() -> None:
    with pytest.raises(ValueError):
        decode(np.zeros((1, 100, 85), np.float32), SIZE, 1.0, 0.5, 0.45)


def test_confirmer_three_of_five_then_reset() -> None:
    c = Confirmer(3, 5)
    assert [c.update(x) for x in (True, False, True, False, True)] == [False, False, False, False, True]
    c.reset()
    assert not c.update(True)


MODEL_PATH = Path(os.environ.get("MODELS_DIR", Path(__file__).resolve().parents[2] / "models")) / MODEL


@pytest.mark.skipif(not MODEL_PATH.exists(), reason="modèle absent (scripts/download-face-models.sh)")
def test_real_model_finds_nobody_in_an_empty_room() -> None:
    rng = np.random.default_rng(0)
    room = np.clip(np.linspace(40, 180, 640)[None, :, None] + rng.integers(0, 30, (480, 640, 3)), 0, 255)
    assert PersonDetector(MODEL_PATH, SIZE).detect(room.astype(np.uint8)) == []
