"""Le JSON produit doit correspondre aux noms de champs de frontend/src/types.ts."""
from datetime import UTC, datetime

from app.live import default_state
from app.schemas import DEFAULT_SETTINGS, Settings, User, dump


def test_user_is_camel_case_with_iso_dates() -> None:
    u = User(id="1", username="admin", role="admin", active=True,
             last_login=datetime(2026, 10, 5, 14, 32, 7, 512000, tzinfo=UTC), must_change_password=False)
    assert dump(u) == {
        "id": "1", "username": "admin", "role": "admin", "active": True,
        "lastLogin": "2026-10-05T14:32:07.512Z", "mustChangePassword": False,
    }


def test_system_state_keys() -> None:
    d = dump(default_state(datetime.now(UTC)))
    assert set(d) == {"device", "threat", "sensors", "camera", "anomaly"}
    assert set(d["device"]) == {"id", "online", "armed", "lastHeartbeat", "uptimeS", "rssi", "firmware"}
    assert set(d["sensors"]["imu"]) == {"accelG", "tiltDeg", "shock", "lastShock"}
    assert set(d["sensors"]["pir"]) == {"active", "lastTriggered", "countLastHour"}
    assert set(d["camera"]) == {"online", "detectionActive", "lastDetection", "overrideUntil", "masked"}
    assert set(d["anomaly"]) == {"score", "isAnomaly", "projectedTemp15", "features"}


def test_settings_roundtrip_from_dashboard_json() -> None:
    sent = {
        "weights": {"pir": 20, "proximite": 20, "anomalie": 30, "vision": 40, "choc": 40, "muet": 50, "capot": 60,
                    "badgeRefuse": 30},
        "thresholds": {"alerte": 30, "critique": 70},
        "armedMultiplier": 1.5,
        "occupancy": {"start": "08:00", "end": "19:00", "days": [1, 2, 3, 4, 5]},
        "cameraUnlockSeconds": 300,
        "retentionDays": 30,
    }
    assert dump(Settings.model_validate(sent)) == sent
    assert dump(DEFAULT_SETTINGS) == sent
