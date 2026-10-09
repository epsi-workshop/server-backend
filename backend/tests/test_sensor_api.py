import asyncio
from typing import Any

import pytest

from app import sensor_api
from app.ingest import Envelope

# Réponse réelle de GET /sensors (capteur de température pas encore branché : null).
SENSORS = {"temperature_c": None, "humidity_pct": None,
           "pir": {"motion": False, "last_motion_s_ago": 136.8, "detections": 9}, "motion": None,
           "timestamp": 1791276146.458983}


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Remplace le traitement (base, état…) par un espion : on ne teste que la traduction."""
    calls: list[tuple[str, dict[str, Any]]] = []

    async def spy(env: Envelope, _source: str) -> None:
        calls.append((env.type, env.data))

    for name in ("box_event", "box_telemetry", "box_heartbeat"):
        monkeypatch.setattr(sensor_api, name, spy)
    return calls


def run(coro: Any) -> None:
    asyncio.run(coro)


def test_null_sensors_send_no_telemetry(sent: list[tuple[str, dict[str, Any]]]) -> None:
    run(sensor_api.SensorApi("http://x")._apply_sensors(SENSORS))
    assert sent == [("pir", {"state": 0})]


def test_telemetry_translated(sent: list[tuple[str, dict[str, Any]]]) -> None:
    run(sensor_api.SensorApi("http://x")._apply_sensors({"temperature_c": 21.5, "humidity_pct": 40}))
    assert sent == [("telemetry", {"temperature": 21.5, "humidity": 40.0})]


def test_motion_sent_only_on_change(sent: list[tuple[str, dict[str, Any]]]) -> None:
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        for motion in (False, True, True, True, False):  # WebSocket et /sensors répètent le même état
            await api._set_motion(motion)

    run(scenario())
    assert sent == [("pir", {"state": 0}), ("pir", {"state": 1}), ("pir", {"state": 0})]


def test_malformed_response_ignored(sent: list[tuple[str, dict[str, Any]]]) -> None:
    run(sensor_api.SensorApi("http://x")._apply_sensors({"temperature_c": "chaud", "pir": "oui", "humidity_pct": True}))
    assert sent == []



def test_badge_passes_translated(sent: list[tuple[str, dict[str, Any]]]) -> None:
    """Valeurs d'exemple : référence au démarrage (pas rejouée), deux passages, relecture identique ignorée."""
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        for seq, uid in ((3, "DEADBEEF"), (4, "04a1b2c3"), (4, "04a1b2c3"), (5, "04A1B2C3")):
            await api._apply_sensors({"rfid": {"seq": seq, "uid": uid, "source": "simulation"}})

    run(scenario())
    assert sent == [("rfid_ok", {"uid": "04:A1:B2:C3"}), ("rfid_ok", {"uid": "04:A1:B2:C3"})]


def test_badge_counter_reset_is_new_reference(sent: list[tuple[str, dict[str, Any]]]) -> None:
    """UNO Q redémarrée : le compteur repart de 0, ce n'est pas un passage."""
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        for seq in (7, 0, 1):
            await api._apply_sensors({"rfid": {"seq": seq, "uid": "04A1B2C3"}})

    run(scenario())
    assert sent == [("rfid_ok", {"uid": "04:A1:B2:C3"})]
