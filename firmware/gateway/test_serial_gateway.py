import json
from datetime import UTC, datetime

from serial_gateway import CommandGuard, Sequencer, to_message

NOW = datetime(2026, 10, 6, 9, 30, 0, 512000, tzinfo=UTC)


def test_pir_event() -> None:
    topic, qos, msg = to_message('{"topic":"event","type":"pir","data":{"state":1}}', "box01", 42, NOW)  # type: ignore[misc]
    assert (topic, qos) == ("sentinel/box01/event", 1)
    assert msg == {"device": "box01", "seq": 42, "ts": "2026-10-06T09:30:00.512Z", "type": "pir", "data": {"state": 1}}


def test_heartbeat_is_qos0() -> None:
    topic, qos, _ = to_message('{"topic":"heartbeat","type":"heartbeat","data":{"uptime":15}}', "box01", 1, NOW)  # type: ignore[misc]
    assert (topic, qos) == ("sentinel/box01/heartbeat", 0)


def test_rejected_lines() -> None:
    for line in ("", "démarrage...", "[1, 2]", '{"topic":"cmd","type":"reboot"}', '{"topic":"status","type":"x"}',
                 '{"topic":"event","type":"inconnu","data":{}}', '{"topic":"event","type":"pir","data":5}'):
        assert to_message(line, "box01", 1, NOW) is None, line


def test_sequence_strictly_increasing() -> None:
    s = Sequencer()
    values = [s.next() for _ in range(1000)]
    assert all(b > a for a, b in zip(values, values[1:]))


def _cmd(kind: str = "buzzer_on", seq: int = 100, ts: str = "2026-10-06T09:29:55.000Z", device: str = "box01") -> bytes:
    """Commande telle que publiée par le backend (app/mqtt.py, send_command)."""
    return json.dumps({"device": device, "seq": seq, "ts": ts, "type": kind, "data": {}}).encode()


def test_command_accepted() -> None:
    assert CommandGuard("box01").check(_cmd(), NOW) == ("buzzer_on", "")


def test_command_replay_rejected() -> None:
    guard = CommandGuard("box01")
    assert guard.check(_cmd(seq=100), NOW)[0] == "buzzer_on"
    assert guard.check(_cmd(seq=100), NOW)[0] is None  # même message renvoyé par un attaquant
    assert guard.check(_cmd(seq=99), NOW)[0] is None   # message plus ancien
    assert guard.check(_cmd(kind="disarm", seq=101), NOW)[0] == "disarm"


def test_command_rejected() -> None:
    guard = CommandGuard("box01")
    for payload in (b"pas du json", b"[]", _cmd(device="box02"), _cmd(kind="format_disk"),
                    _cmd(ts="2026-10-06T09:29:00.000Z"),   # 60 s : trop ancienne
                    _cmd(ts="2026-10-06T09:32:00.000Z"),   # futur
                    _cmd(ts="2026-10-06T09:29:55")):       # sans fuseau
        assert guard.check(payload, NOW)[0] is None, payload
