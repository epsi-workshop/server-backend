"""Superviseur : authentification, état des conteneurs, liste blanche."""
from datetime import UTC, datetime

import supervisor as sup


def test_token_required_and_compared(monkeypatch) -> None:
    monkeypatch.setattr(sup, "TOKEN", "s3cret")
    assert sup.authorized("Bearer s3cret")
    assert not sup.authorized("Bearer autre")
    assert not sup.authorized(None)
    assert not sup.authorized("s3cret")
    monkeypatch.setattr(sup, "TOKEN", "")
    assert not sup.authorized("Bearer ")  # jeton vide : tout est refusé


def test_health_status() -> None:
    assert sup.health_status({"Running": True}) == "ok"
    assert sup.health_status({"Running": True, "Health": {"Status": "healthy"}}) == "ok"
    assert sup.health_status({"Running": True, "Health": {"Status": "unhealthy"}}) == "degrade"
    assert sup.health_status({"Running": True, "Restarting": True}) == "degrade"
    assert sup.health_status({"Running": False}) == "arrete"


def test_uptime_and_version() -> None:
    now = datetime(2026, 10, 8, 12, 0, 0, tzinfo=UTC)
    assert sup.uptime_s({"Running": True, "StartedAt": "2026-10-08T11:58:20.123456789Z"}, now) == 99
    assert sup.uptime_s({"Running": False, "StartedAt": "2026-10-08T11:58:20Z"}, now) == 0
    assert sup.version_of("sentinel-x/vision:0.2.0") == "0.2.0"
    assert sup.version_of("binwiederhier/ntfy:v2.28.0") == "2.28.0"
    assert sup.version_of("localhost:5000/img") == "latest"


def test_cpu_percent_like_docker_stats() -> None:
    stats = {"cpu_stats": {"cpu_usage": {"total_usage": 3_000}, "system_cpu_usage": 100_000, "online_cpus": 4},
             "precpu_stats": {"cpu_usage": {"total_usage": 1_000}, "system_cpu_usage": 80_000}}
    assert sup.cpu_percent(stats) == 40.0
    assert sup.cpu_percent({}) == 0.0


def test_only_whitelisted_services_can_restart() -> None:
    assert sup.RESTARTABLE == ("vision", "anomaly", "mosquitto", "backend")
    assert "db" not in sup.RESTARTABLE and "supervisor" not in sup.RESTARTABLE
