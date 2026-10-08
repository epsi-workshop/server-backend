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


def test_door_state_translated_on_change(sent: list[tuple[str, dict[str, Any]]]) -> None:
    """Valeurs d'exemple : porte fermée, ouverte deux fois de suite (une seule transmission), refermée."""
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        for is_open in (False, True, True, False):
            await api._apply_sensors({"lid": {"open": is_open, "source": "capteur"}})

    run(scenario())
    assert sent == [("lid_open", {"state": 0}), ("lid_open", {"state": 1}), ("lid_open", {"state": 0})]


def test_door_absent_or_malformed_ignored(sent: list[tuple[str, dict[str, Any]]]) -> None:
    run(sensor_api.SensorApi("http://x")._apply_sensors({"lid": {"open": "oui"}}))
    run(sensor_api.SensorApi("http://x")._apply_sensors({"lid": None}))
    assert sent == []


def test_badge_passes_translated(sent: list[tuple[str, dict[str, Any]]]) -> None:
    """Valeurs d'exemple : référence au démarrage (pas rejouée), deux passages, relecture identique ignorée."""
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        for seq, uid in ((3, "DEADBEEF"), (4, "04a1b2c3"), (4, "04a1b2c3"), (5, "04A1B2C3")):
            await api._apply_sensors({"rfid": {"seq": seq, "uid": uid, "source": "lecteur"}})

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


@pytest.fixture
def journal(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    lines: list[str] = []

    async def spy(_level: str, _source: str, message: str) -> None:
        lines.append(message)

    monkeypatch.setattr(sensor_api, "write_log", spy)
    return lines


def test_simulated_badge_is_ignored(sent: list[tuple[str, dict[str, Any]]], journal: list[str]) -> None:
    """Route /sensors/rfid/simulate de la carte (sans authentification) : le badge ne doit rien désarmer."""
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        await api._set_rfid(15, "1BE2E34A", "lecteur")  # référence au démarrage
        await api._set_rfid(16, "1BE2E34A", "simulation")
        await api._set_rfid(17, "1BE2E34A", "lecteur")

    run(scenario())
    assert sent == [("rfid_ok", {"uid": "1B:E2:E3:4A"})]
    assert any("simulé" in line for line in journal)


def test_simulated_door_keeps_last_real_state(sent: list[tuple[str, dict[str, Any]]], journal: list[str]) -> None:
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        await api._set_lid(True, "capteur")  # porte réellement ouverte
        await api._set_lid(False, "simulation")  # quelqu'un la fait passer pour fermée
        await api._set_lid(False, "simulation")
        await api._set_lid(False, "capteur")  # vraie fermeture

    run(scenario())
    assert sent == [("lid_open", {"state": 1}), ("lid_open", {"state": 0})]
    assert sum("simulation" in line for line in journal) == 1  # signalé une seule fois


def test_simulation_allowed_for_tests(sent: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch,
                                      journal: list[str]) -> None:
    monkeypatch.setattr(sensor_api.config, "sensor_api_allow_simulation", True)
    api = sensor_api.SensorApi("http://x")

    async def scenario() -> None:
        await api._set_rfid(1, "1BE2E34A", "simulation")
        await api._set_rfid(2, "1BE2E34A", "simulation")

    run(scenario())
    assert sent == [("rfid_ok", {"uid": "1B:E2:E3:4A"})]


def test_token_sent_to_the_card(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sensor_api.config, "sensor_api_token", "s3cret")
    assert sensor_api.SensorApi("http://x").headers == {"Authorization": "Bearer s3cret"}
    monkeypatch.setattr(sensor_api.config, "sensor_api_token", "")
    assert sensor_api.SensorApi("http://x").headers == {}


def test_card_readings_relayed_to_anomaly_service(sent: list[tuple[str, dict[str, Any]]],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    published: list[tuple[str, dict[str, Any]]] = []

    async def publish(topic: str, payload: dict[str, Any], qos: int = 1) -> None:
        published.append((topic, payload))

    monkeypatch.setattr(sensor_api.config, "mqtt_enabled", True)
    monkeypatch.setattr(sensor_api.bus, "publish", publish)
    run(sensor_api.SensorApi("http://x")._apply_sensors({"temperature_c": 22.4, "humidity_pct": 41,
                                                           "pir": {"motion": True}}))
    topics = [t for t, _ in published]
    assert topics == ["sentinel/box01/relay/telemetry", "sentinel/box01/relay/event"]
    assert published[0][1]["device"] == "box01" and published[0][1]["data"]["temperature"] == 22.4
