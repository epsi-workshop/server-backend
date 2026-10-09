"""Détection de mouvement sur des images synthétiques : fond fixe, puis un carré qui se déplace."""
import numpy as np

from vision.motion import MotionDetector
from vision.source import split_jpegs

W, H = 640, 480
rng = np.random.default_rng(0)
# Fond fixe contrasté, comme une salle : dégradé (murs, éclairage) plus une texture.
_gradient = np.linspace(30, 170, W, dtype=np.float64)[None, :, None]
BACKGROUND = np.clip(_gradient + rng.integers(0, 40, (H, W, 3)), 0, 255).astype(np.uint8)


def scene(square_x: int | None = None) -> np.ndarray:
    img = BACKGROUND.copy()
    noise = rng.integers(-3, 4, img.shape)  # bruit du capteur
    img = np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)
    if square_x is not None:
        img[200:320, square_x:square_x + 90] = (230, 230, 230)
    return img


def detector() -> MotionDetector:
    return MotionDetector(min_area=0.004, confirm=3, window=5, warmup=30)


def test_static_scene_never_moves() -> None:
    d = detector()
    results = [d.update(scene()) for _ in range(80)]
    assert not any(r.moving for r in results)
    assert not any(r.raw for r in results)


def test_moving_object_detected_and_boxed() -> None:
    d = detector()
    for _ in range(40):
        d.update(scene())
    results = [d.update(scene(50 + 25 * i)) for i in range(6)]
    assert results[0].raw and not results[0].moving  # une seule image : pas encore confirmé
    assert results[2].moving  # confirmé à la 3e image
    x, y, w, h = results[-1].boxes[0]
    assert 140 < y + h // 2 < 380  # la zone encadrée est bien autour du carré
    assert results[-1].confidence >= 0.6


def test_no_detection_during_warmup() -> None:
    d = detector()
    results = [d.update(scene(50 + 10 * (i % 20))) for i in range(30)]
    assert not any(r.moving for r in results)


def test_masked_camera() -> None:
    d = detector()
    assert d.update(np.zeros((H, W, 3), np.uint8)).masked
    assert not d.update(scene()).masked


def test_split_jpegs() -> None:
    a = b"\xff\xd8A\xff\xd9"
    frames, rest = split_jpegs(b"--x\r\n\r\n" + a + b"\r\n--x\r\n\r\n\xff\xd8B")
    assert frames == [a] and rest == b"\xff\xd8B"


def test_latest_frame_drops_stale_images():
    from vision.source import LatestFrame
    latest = LatestFrame()
    for jpeg in (b"1", b"2", b"3"):
        latest.put(jpeg)
    assert latest.take() == b"3"
    assert latest.dropped == 2
    assert latest.take(timeout=0.01) is None
