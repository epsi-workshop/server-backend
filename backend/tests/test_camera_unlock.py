from datetime import timedelta

import pytest

from app.live import LiveState
from app.schemas import Detection
from app.util import utcnow


@pytest.fixture
def live() -> LiveState:
    state = LiveState()
    assert state.settings.camera_unlock_seconds == 300  # 5 min par défaut
    return state


def test_locked_without_motion(live: LiveState) -> None:
    assert not live.camera_unlocked()


def test_open_while_pir_sees_motion(live: LiveState) -> None:
    live.state.sensors.pir.active = True
    live.state.camera.last_detection = Detection(ts=utcnow() - timedelta(minutes=30), confidence=1.0)
    assert live.camera_unlocked()  # mouvement en cours, même commencé il y a longtemps


def test_open_4_minutes_after_last_motion(live: LiveState) -> None:
    live.state.camera.last_detection = Detection(ts=utcnow() - timedelta(minutes=4), confidence=1.0)
    assert live.camera_unlocked()
    assert live.snapshot().camera.detection_active  # marquée active sur le dashboard


def test_closed_5_minutes_after_last_motion(live: LiveState) -> None:
    live.state.camera.last_detection = Detection(ts=utcnow() - timedelta(minutes=5, seconds=1), confidence=1.0)
    assert not live.camera_unlocked()
