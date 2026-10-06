"""Suivi du mouvement : décisions du Tracker (horloge simulée) et réapprentissage du fond après rotation."""
import numpy as np

from vision.motion import MotionDetector
from vision.tracking import Tracker, largest

W = 640


def tracker(**kw) -> Tracker:
    params = dict(fov_deg=60, deadband=0.15, gain=0.8, speed=150, settle_s=0.6, min_interval_s=1.0,
                  invert=False, home_angle=90, home_after_s=20, now=0.0)
    params.update(kw)
    return Tracker(**params)


def box_at(cx: int, w: int = 80) -> tuple[int, int, int, int]:
    return (cx - w // 2, 150, w, 200)


def test_subject_right_turns_camera_right() -> None:
    t = tracker()
    # Sujet au bord droit (décalage +1) : 30° de demi-champ x 0,8 = 24°, angle plus petit.
    assert t.update(10.0, [box_at(W)], W) == 66
    assert t.angle == 66


def test_subject_left_turns_camera_left_and_invert() -> None:
    assert tracker().update(10.0, [box_at(0)], W) == 114
    assert tracker(invert=True).update(10.0, [box_at(0)], W) == 66


def test_centered_subject_does_not_move() -> None:
    t = tracker()
    assert t.update(10.0, [box_at(W // 2 + 30)], W) is None  # 30 px sur 320 : dans la zone morte
    assert t.angle == 90


def test_frozen_while_rotating_then_rate_limited() -> None:
    t = tracker()
    assert t.update(10.0, [box_at(W)], W) == 66  # 24° à 150°/s + 0,6 s de stabilisation = 0,76 s
    assert t.frozen(10.5)
    assert t.update(10.5, [box_at(W)], W) is None
    assert not t.frozen(10.8)
    assert t.update(10.8, [box_at(W)], W) is None  # moins d'une seconde depuis la dernière rotation
    assert t.update(11.1, [box_at(W)], W) == 42


def test_follows_largest_motion_zone() -> None:
    small_left, big_right = (0, 0, 40, 40), (500, 100, 120, 300)
    assert largest([small_left, big_right]) == big_right
    assert tracker().update(10.0, [small_left, big_right], W) < 90  # suit la grande zone, à droite


def test_clamped_to_servo_range() -> None:
    t = tracker(home_angle=10)
    assert t.update(10.0, [box_at(W)], W) == 0
    t2 = tracker(home_angle=0)
    assert t2.update(10.0, [box_at(W)], W) is None  # déjà en butée


def test_returns_home_after_quiet_period() -> None:
    t = tracker()
    assert t.update(10.0, [box_at(W)], W) == 66
    assert t.update(25.0, [], W) is None  # 15 s sans mouvement
    assert t.update(30.5, [], W) == 90  # 20 s : retour au repos
    assert t.update(60.0, [], W) is None  # déjà au repos


def test_home_at_startup_freezes_for_full_travel() -> None:
    t = tracker()
    assert t.home(0.0) == 90
    assert t.frozen(1.0)  # 180° à 150°/s + 0,6 s = 1,8 s
    assert not t.frozen(1.9)


def test_relearn_after_camera_rotation() -> None:
    """Après une rotation, l'image entière est décalée : sans réapprentissage tout serait « mouvement »."""
    rng = np.random.default_rng(1)
    wide = np.clip(np.linspace(20, 200, 960)[None, :, None] + rng.integers(0, 50, (480, 960, 3)), 0, 255)
    wide = wide.astype(np.uint8)

    def view(offset: int) -> np.ndarray:  # la caméra regarde une portion de la scène
        img = wide[:, offset:offset + W].astype(int) + rng.integers(-3, 4, (480, W, 3))
        return np.clip(img, 0, 255).astype(np.uint8)

    d = MotionDetector(min_area=0.004, confirm=3, window=5, warmup=30)
    for _ in range(40):
        d.update(view(0))
    assert d.update(view(160)).raw  # rotation sans réapprentissage : tout « bouge »

    d.relearn(8)
    results = [d.update(view(160)) for _ in range(20)]
    assert not any(r.raw for r in results)  # nouvelle vue apprise : plus de faux mouvement
