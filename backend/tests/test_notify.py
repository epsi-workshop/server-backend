"""Notifications push : contenu envoyé à ntfy et choix de la capture jointe."""
from pathlib import Path

from app.db import AlertRow
from app.notify import build, snapshot_file


def alert(level: str = "critique", snapshot: str | None = None) -> AlertRow:
    return AlertRow(level=level, score=90, title="Intrusion détectée",
                    reasons=["Mouvement PIR (+20)", "Personne détectée par la caméra (+40)"], snapshot_path=snapshot)


def test_critical_alert_is_urgent_with_reasons_and_link() -> None:
    p = build(alert(), escalated=False)
    assert p["title"] == "CRITIQUE : Intrusion détectée"
    assert p["priority"] == "urgent" and p["tags"] == "rotating_light"
    assert p["message"] == "Score 90. Mouvement PIR (+20), Personne détectée par la caméra (+40)"
    assert p["click"].endswith("/#/alertes")


def test_escalated_alert_level_is_high() -> None:
    p = build(alert("alerte"), escalated=True)
    assert p["title"] == "Alerte : Intrusion détectée (escaladée)"
    assert p["priority"] == "high"


def test_snapshot_must_be_a_plain_jpg_in_the_directory(tmp_path: Path) -> None:
    (tmp_path / "person-20261008-031500-123.jpg").write_bytes(b"\xff\xd8jpeg")
    assert snapshot_file("person-20261008-031500-123.jpg", tmp_path) == tmp_path / "person-20261008-031500-123.jpg"
    assert snapshot_file("absente.jpg", tmp_path) is None
    assert snapshot_file("../../etc/passwd", tmp_path) is None
    assert snapshot_file("x.png", tmp_path) is None
    assert snapshot_file(None, tmp_path) is None
