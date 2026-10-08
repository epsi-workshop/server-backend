"""Rétention des captures : seules celles d'une alerte restent, au plus retentionDays."""
from datetime import UTC, datetime, timedelta

from app.snapshots import GRACE, plan_purge

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
DAYS_30 = timedelta(days=30)


def test_capture_without_alert_is_kept_during_grace_then_deleted() -> None:
    files = {"motion-a.jpg": NOW - GRACE + timedelta(minutes=1), "motion-b.jpg": NOW - GRACE - timedelta(minutes=1)}
    assert plan_purge(files, {}, NOW, DAYS_30) == (["motion-b.jpg"], [])


def test_alert_capture_is_kept_until_retention() -> None:
    files = {"person-a.jpg": NOW - timedelta(days=3), "person-b.jpg": NOW - timedelta(days=40)}
    kept = {"person-a.jpg": NOW - timedelta(days=3), "person-b.jpg": NOW - timedelta(days=40)}
    assert plan_purge(files, kept, NOW, DAYS_30) == ([], ["person-b.jpg"])


def test_alert_whose_file_is_gone_changes_nothing() -> None:
    assert plan_purge({}, {"person-x.jpg": NOW - timedelta(days=90)}, NOW, DAYS_30) == ([], [])
