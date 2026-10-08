"""Règles de corrélation : mêmes résultats que computeThreat / maybeAlert de frontend/src/api/mock.ts."""
from datetime import UTC, datetime, timedelta

from app.correlation import compute_threat, in_occupancy, plan_alert, title_for
from app.db import AlertRow
from app.ingest import HEARTBEAT_TIMEOUT, ReplayGuard, count_recent, is_mute
from app.schemas import DEFAULT_SETTINGS as S

MONDAY_10H = datetime(2026, 10, 5, 10, 0)  # lundi, dans les horaires 08:00-19:00
SUNDAY_10H = datetime(2026, 10, 4, 10, 0)


def test_occupancy() -> None:
    assert in_occupancy(S, MONDAY_10H)
    assert not in_occupancy(S, SUNDAY_10H)
    assert not in_occupancy(S, MONDAY_10H.replace(hour=19))  # fin exclue
    assert in_occupancy(S, MONDAY_10H.replace(hour=8))


def test_nothing_is_info() -> None:
    t = compute_threat(set(), S, armed=True, occupied=False, recent_valid_badge=False)
    assert (t.score, t.level, t.reasons) == (0, "info", [])  # pas de multiplicateur sur un score nul


def test_camera_motion_alone_during_office_hours_is_alerte() -> None:
    t = compute_threat({"vision"}, S, armed=False, occupied=True, recent_valid_badge=False)
    assert (t.score, t.level) == (40, "alerte")
    assert t.reasons == ["Détection de la caméra (+40)"]


def test_armed_multiplier() -> None:
    t = compute_threat({"vision"}, S, armed=True, occupied=True, recent_valid_badge=False)
    assert (t.score, t.level) == (60, "alerte")
    assert t.reasons[-1] == "Hors horaires ou armé (× 1,5)"


def test_intrusion_is_critique() -> None:
    # Alerte « Intrusion détectée » du simulateur : PIR + proximité + caméra, armé = 120.
    t = compute_threat({"pir", "proximite", "vision"}, S, armed=True, occupied=True, recent_valid_badge=False)
    assert (t.score, t.level) == (120, "critique")


def test_valid_badge_lowers_score() -> None:
    t = compute_threat({"vision", "pir"}, S, armed=False, occupied=True, recent_valid_badge=True)
    assert (t.score, t.level) == (18, "info")


def test_title_priority() -> None:
    assert title_for({"badge_refuse", "vision", "capot"})[0] == "Intrusion détectée"
    assert title_for({"choc", "pir"})[0] == "Sabotage du boîtier"
    assert title_for({"anomalie"})[0] == "Anomalie environnementale"


def _open(level: str, title: str, snapshot: str | None = None) -> AlertRow:
    return AlertRow(level=level, title=title, score=40, reasons=[], snapshot_path=snapshot, status="ouverte")


def test_alert_created_when_level_rises() -> None:
    assert plan_alert("alerte", "info", "Intrusion détectée", True, None).create
    # Le niveau reste à alerte après 90 s : pas de nouvelle alerte à chaque évaluation.
    assert not plan_alert("alerte", "alerte", "Intrusion détectée", True, None).changes
    assert not plan_alert("info", "info", "Intrusion détectée", False, None).changes


def test_recent_alert_is_escalated_not_duplicated() -> None:
    plan = plan_alert("critique", "alerte", "Intrusion détectée", True, _open("alerte", "Badge refusé"))
    assert not plan.create
    assert plan.raise_level and plan.better_title and plan.attach_snapshot


def test_recent_alert_unchanged_when_nothing_new() -> None:
    plan = plan_alert("alerte", "alerte", "Intrusion détectée", True,
                      _open("alerte", "Intrusion détectée", snapshot="a.jpg"))
    assert not plan.changes


def test_replay_guard() -> None:
    g = ReplayGuard()
    now = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    assert g.check("vision", 10, now, now) is None
    assert "déjà reçu" in (g.check("vision", 10, now, now) or "")
    assert "déjà reçu" in (g.check("vision", 9, now, now) or "")
    assert g.check("vision", 11, now, now) is None
    assert g.check("box01", 1, now, now) is None  # compteur propre à chaque équipement
    assert "ancien" in (g.check("vision", 12, now - timedelta(minutes=6), now) or "")
    assert "futur" in (g.check("vision", 13, now + timedelta(minutes=2), now) or "")


def test_mute_after_three_missed_heartbeats() -> None:
    now = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    assert not is_mute(True, now - timedelta(seconds=30), now)
    assert is_mute(True, now - HEARTBEAT_TIMEOUT - timedelta(seconds=1), now)
    assert not is_mute(True, None, now)  # jamais vu : pas « muet »
    assert not is_mute(False, now - timedelta(hours=1), now)  # déjà signalé hors ligne


def test_pir_count_last_hour() -> None:
    from collections import deque
    now = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
    times = deque([now - timedelta(minutes=m) for m in (70, 50, 5)])
    assert count_recent(times, now, timedelta(hours=1)) == 2
    assert len(times) == 2  # l'ancien est retiré


def test_masked_camera_is_sabotage() -> None:
    t = compute_threat({"masque"}, S, armed=True, occupied=True, recent_valid_badge=False)
    assert t.score == 75 and t.level == "critique"
    assert t.reasons[0] == "Caméra masquée (+50)"
    assert title_for({"masque"})[0] == "Sabotage du boîtier"
