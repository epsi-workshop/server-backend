"""Détection d'anomalies sur des mesures synthétiques : salle stable, puis sèche-cheveux ou dérive lente."""
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from anomaly.config import Config
from anomaly.detector import Analyzer, Confirmer, deltas, feature_matrix, project, train
from anomaly.history import History

STEP = 5.0  # une télémesure toutes les 5 s
T0 = 1_791_000_000.0  # octobre 2026
rng = np.random.default_rng(0)


def cfg(**kw: object) -> Config:
    return Config(_env_file=None, **kw)  # type: ignore[call-arg]


def normal_room(hours: float, start: float = T0) -> list[tuple[float, float, float]]:
    """Salle serveur stable : 22 °C ± 0,3 (cycle lent), 45 % ± 1, bruit des capteurs."""
    n = int(hours * 3600 / STEP)
    ts = start + np.arange(n) * STEP
    temp = 22 + 0.3 * np.sin(2 * np.pi * ts / 86_400) + rng.normal(0, 0.05, n)
    hum = 45 + np.sin(2 * np.pi * ts / 43_200) + rng.normal(0, 0.2, n)
    return list(zip(ts.tolist(), temp.tolist(), hum.tolist(), strict=True))


def analyzer_with(rows: list[tuple[float, float, float]], **kw: object) -> Analyzer:
    history = History(":memory:")
    history.add_samples(rows)
    a = Analyzer(history, cfg(**kw))
    a.train(rows[-1][0])
    return a


def feed(a: Analyzer, rows: list[tuple[float, float, float]]) -> list:
    results = []
    for ts, temp, hum in rows:
        a.history.add_sample(ts, temp, hum)
        results.append(a.evaluate(ts, temp, hum))
    return results


def test_deltas_over_five_minutes() -> None:
    ts = np.arange(0, 900, STEP)
    temp = 20 + ts / 60  # +1 °C par minute
    d = deltas(ts, temp)
    assert d[0] == 0  # rien 5 min avant
    assert d[-1] == pytest.approx(5.0)


def test_no_model_before_min_hours() -> None:
    a = analyzer_with(normal_room(1.0))
    assert a.model is None


def test_time_features_only_when_history_covers_them() -> None:
    tz = ZoneInfo("Europe/Paris")
    short = np.array(normal_room(3))
    model = train(short, np.array([]), tz, cfg(), short[-1, 0])
    assert model is not None and not model.use_hour and not model.use_weekday
    long = np.array(normal_room(25))
    model = train(long, np.array([]), tz, cfg(), long[-1, 0])
    assert model is not None and model.use_hour and not model.use_weekday


def test_feature_matrix_counts_pir_over_last_hour() -> None:
    samples = np.array(normal_room(2))
    pir = np.array([samples[-1, 0] - 4000, samples[-1, 0] - 100, samples[-1, 0] - 50])
    X, names = feature_matrix(samples, pir, ZoneInfo("Europe/Paris"), False, False)
    assert X[-1, names.index("pir1h")] == 2


def test_normal_room_stays_normal() -> None:
    rows = normal_room(6)
    a = analyzer_with(rows[:-360])
    results = feed(a, rows[-360:])  # 30 dernières minutes, jamais vues à l'entraînement
    assert not any(r.is_anomaly for r in results)
    assert all(0 < r.score < 1 for r in results)


def test_hair_dryer_is_detected_with_its_cause() -> None:
    rows = normal_room(6)
    a = analyzer_with(rows)
    last = rows[-1][0]
    # Sèche-cheveux : +6 °C en une minute, humidité qui baisse.
    heat = [(last + (i + 1) * STEP, 22 + 0.5 * (i + 1), 45 - 0.4 * (i + 1)) for i in range(12)]
    results = feed(a, heat)
    assert results[-1].is_anomaly
    assert "variation de température sur 5 min" in results[-1].features
    assert results[-1].score > results[0].score


def test_single_outlier_is_not_confirmed() -> None:
    rows = normal_room(6)
    a = analyzer_with(rows)
    last = rows[-1][0]
    # Un relevé aberrant (au-dessus du seuil de 27 °C), puis des mesures normales : jamais confirmé.
    glitch = [(last + STEP, 30.0, 45.0)] + [(last + (i + 2) * STEP, 22.0, 45.0) for i in range(4)]
    results = feed(a, glitch)
    assert not any(r.is_anomaly for r in results)


def test_projection_follows_linear_trend() -> None:
    ts = T0 + np.arange(0, 1800, STEP)
    samples = np.column_stack([ts, 22 + (ts - T0) / 600, np.full(len(ts), 45.0)])  # +0,1 °C par minute
    projected = project(samples, ts[-1], 1800, 900)
    assert projected == pytest.approx(samples[-1, 1] + 1.5, abs=0.01)
    assert project(samples[:10], ts[9], 1800, 900) is None  # pas assez de mesures


def test_slow_drift_alerts_before_the_limit() -> None:
    a = analyzer_with(normal_room(6), temp_limit=27.0)
    last = a.history.samples()[-1, 0]
    drift = [(last + (i + 1) * STEP, 22 + (i + 1) * STEP / 300, 45.0) for i in range(300)]  # +0,2 °C par minute
    results = feed(a, drift)
    alerts = [(temp, r) for r, (_, temp, _) in zip(results, drift, strict=True) if r.is_anomaly]
    assert alerts and alerts[0][0] < 27.0  # alerte avant le dépassement du seuil
    # La projection à +15 min signale le dépassement avant qu'il n'ait lieu.
    assert any(temp < 27.0 and any("projection" in f for f in r.features) for temp, r in alerts)


def test_confirmer_needs_three_of_five() -> None:
    c = Confirmer(3, 5)
    assert [c.update(x) for x in (True, False, True, False, True)] == [False, False, False, False, True]
