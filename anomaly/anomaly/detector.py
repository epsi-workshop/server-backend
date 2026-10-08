"""Détection d'anomalies environnementales (cahier des charges, 7.7).

- Isolation Forest : apprend le fonctionnement normal de la salle sans données étiquetées.
  Variables : température, humidité, leurs variations sur 5 min, déclenchements PIR sur 1 h, puis
  l'heure (sinus/cosinus) et le jour de la semaine dès que l'historique les couvre.
- Volet prédictif : régression linéaire de la température sur les 30 dernières minutes, projetée à +15 min,
  pour alerter avant le dépassement du seuil.
"""
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
from sklearn.ensemble import IsolationForest

from .config import Config
from .history import History

DELTA_S = 300  # variations sur 5 min
DELTA_TOLERANCE_S = 120  # mesure de référence acceptée jusqu'à 7 min en arrière (trous de télémesure)
PIR_WINDOW_S = 3600
MAX_TRAIN_ROWS = 50_000  # sous-échantillonnage : 30 jours à 5 s = 518 000 mesures
SECONDS_PER_DAY = 86_400

LABELS = {
    "temperature": "température",
    "humidity": "humidité",
    "dtemp5": "variation de température sur 5 min",
    "dhum5": "variation d'humidité sur 5 min",
    "pir1h": "déclenchements PIR sur 1 h",
    "hour": "heure de la journée",
    "weekday": "jour de la semaine",
}
# Écart minimal pris en compte pour expliquer une anomalie (bruit des capteurs), par variable.
MIN_SCALE = {"temperature": 0.3, "humidity": 1.0, "dtemp5": 0.2, "dhum5": 0.5, "pir1h": 1.0,
             "hour": 0.1, "weekday": 0.1}
EXPLAIN_Z = 3.0


def fr(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


# ---------------------------------------------------------------- variables
def local_seconds(ts: np.ndarray, tz: ZoneInfo) -> np.ndarray:
    """Heure locale en secondes epoch (le décalage n'est calculé qu'une fois par heure UTC distincte)."""
    hours = (ts // 3600).astype(np.int64)
    uniq, inv = np.unique(hours, return_inverse=True)
    offsets = np.array([datetime.fromtimestamp(h * 3600, tz).utcoffset().total_seconds() for h in uniq])
    return ts + offsets[inv]


def deltas(ts: np.ndarray, values: np.ndarray) -> np.ndarray:
    """Variation par rapport à la mesure d'il y a 5 min (0 si aucune mesure exploitable)."""
    idx = np.searchsorted(ts, ts - DELTA_S, side="right") - 1
    ok = idx >= 0
    ref = np.where(ok, idx, 0)
    ok &= ts[ref] >= ts - DELTA_S - DELTA_TOLERANCE_S
    return np.where(ok, values - values[ref], 0.0)


def feature_matrix(samples: np.ndarray, pir: np.ndarray, tz: ZoneInfo, use_hour: bool,
                   use_weekday: bool) -> tuple[np.ndarray, list[str]]:
    """Une ligne par mesure ; renvoie aussi la variable (clé de LABELS) de chaque colonne."""
    ts, temp, hum = samples[:, 0], samples[:, 1], samples[:, 2]
    pir1h = np.searchsorted(pir, ts, side="right") - np.searchsorted(pir, ts - PIR_WINDOW_S, side="right")
    cols = [temp, hum, deltas(ts, temp), deltas(ts, hum), pir1h.astype(np.float64)]
    names = ["temperature", "humidity", "dtemp5", "dhum5", "pir1h"]
    if use_hour or use_weekday:
        local = local_seconds(ts, tz)
        if use_hour:
            angle = 2 * np.pi * (local % SECONDS_PER_DAY) / SECONDS_PER_DAY
            cols += [np.sin(angle), np.cos(angle)]
            names += ["hour", "hour"]
        if use_weekday:
            day = ((local // SECONDS_PER_DAY) + 3) % 7  # 1970-01-01 était un jeudi ; 0 = lundi
            angle = 2 * np.pi * day / 7
            cols += [np.sin(angle), np.cos(angle)]
            names += ["weekday", "weekday"]
    return np.column_stack(cols), names


# ---------------------------------------------------------------- modèle
@dataclass
class Model:
    forest: IsolationForest
    columns: list[str]
    center: np.ndarray  # médiane de chaque colonne sur l'historique
    scale: np.ndarray  # dispersion robuste (MAD), bornée par MIN_SCALE
    trained_at: float
    hours: float
    samples: int

    @property
    def use_hour(self) -> bool:
        return "hour" in self.columns

    @property
    def use_weekday(self) -> bool:
        return "weekday" in self.columns

    def explain(self, x: np.ndarray) -> list[str]:
        """Variables en cause : les plus éloignées de leur valeur habituelle (écart robuste > 3), au plus 3.

        Liste vide : aucune variable ne s'écarte vraiment, l'avis de l'Isolation Forest n'est pas retenu
        (une mesure à peine hors de la plage apprise, par exemple au début de l'apprentissage, n'est pas une anomalie).
        """
        z = np.abs(x - self.center) / self.scale
        worst: dict[str, float] = {}
        for name, value in zip(self.columns, z, strict=True):
            worst[name] = max(worst.get(name, 0.0), float(value))
        causes = sorted((v, n) for n, v in worst.items() if v > EXPLAIN_Z)
        return [LABELS[n] for _, n in reversed(causes)][:3]


def train(samples: np.ndarray, pir: np.ndarray, tz: ZoneInfo, cfg: Config, now: float) -> Model | None:
    """Entraîne l'Isolation Forest sur l'historique, ou None s'il ne couvre pas encore min_train_hours."""
    if len(samples) < 2:
        return None
    hours = (samples[-1, 0] - samples[0, 0]) / 3600
    if hours < cfg.min_train_hours:
        return None
    X, names = feature_matrix(samples, pir, tz, use_hour=hours >= cfg.hour_feature_min_hours,
                              use_weekday=hours >= cfg.weekday_feature_min_days * 24)
    rng = np.random.default_rng(0)
    if len(X) > MAX_TRAIN_ROWS:
        X = X[rng.choice(len(X), MAX_TRAIN_ROWS, replace=False)]
    forest = IsolationForest(n_estimators=200, contamination=cfg.contamination, random_state=0).fit(X)
    center = np.median(X, axis=0)
    mad = 1.4826 * np.median(np.abs(X - center), axis=0)
    scale = np.maximum(mad, [MIN_SCALE[n] for n in names])
    return Model(forest, names, center, scale, trained_at=now, hours=hours, samples=len(samples))


# ---------------------------------------------------------------- volet prédictif
def project(samples: np.ndarray, now: float, window_s: float, horizon_s: float) -> float | None:
    """Température projetée à now + horizon_s par régression linéaire sur [now - window_s, now]."""
    recent = samples[samples[:, 0] >= now - window_s]
    if len(recent) < 20 or recent[-1, 0] - recent[0, 0] < 300:
        return None  # moins de 5 min de mesures : pas de tendance fiable
    slope, intercept = np.polyfit(recent[:, 0] - now, recent[:, 1], 1)
    return float(intercept + slope * horizon_s)


class Confirmer:
    """Anomalie confirmée sur `confirm` évaluations parmi les `window` dernières."""

    def __init__(self, confirm: int, window: int) -> None:
        self.confirm = confirm
        self.recent: deque[bool] = deque(maxlen=window)

    def update(self, raw: bool) -> bool:
        self.recent.append(raw)
        return sum(self.recent) >= self.confirm


@dataclass
class Result:
    score: float  # score d'anomalie de l'Isolation Forest, entre 0 et 1 (0 tant qu'aucun modèle)
    is_anomaly: bool
    projected_temp15: float | None
    features: list[str] = field(default_factory=list)


class Analyzer:
    def __init__(self, history: History, cfg: Config) -> None:
        self.history = history
        self.cfg = cfg
        self.tz = ZoneInfo(cfg.timezone)
        self.model: Model | None = None
        self.confirmer = Confirmer(cfg.confirm, cfg.window)

    def train(self, now: float) -> Model | None:
        since = now - self.cfg.retention_days * SECONDS_PER_DAY
        self.model = train(self.history.samples(since), self.history.pir_times(since), self.tz, self.cfg, now)
        return self.model

    def evaluate(self, now: float, temp: float, hum: float) -> Result:
        """Évalue la dernière mesure (déjà enregistrée dans l'historique)."""
        cfg = self.cfg
        lookback = max(PIR_WINDOW_S, DELTA_S + DELTA_TOLERANCE_S, cfg.projection_window_min * 60)
        samples = self.history.samples(now - lookback)
        causes: list[str] = []
        score = 0.0

        if self.model is not None and len(samples):
            X, _ = feature_matrix(samples, self.history.pir_times(now - PIR_WINDOW_S), self.tz,
                                  self.model.use_hour, self.model.use_weekday)
            x = X[-1:]
            score = float(-self.model.forest.score_samples(x)[0])
            if self.model.forest.decision_function(x)[0] < 0:
                causes = self.model.explain(x[0])

        projected = project(samples, now, cfg.projection_window_min * 60, cfg.projection_horizon_min * 60) \
            if len(samples) else None
        limits: list[str] = []
        if temp >= cfg.temp_limit:
            limits.append(f"température au-dessus de {fr(cfg.temp_limit)} °C")
        elif projected is not None and projected >= cfg.temp_limit:
            limits.append(f"projection à +{cfg.projection_horizon_min:g} min au-dessus de {fr(cfg.temp_limit)} °C"
                          f" ({fr(projected)} °C)")
        if hum >= cfg.humidity_limit:
            limits.append(f"humidité au-dessus de {cfg.humidity_limit:g} %")

        # Confirmation sur plusieurs mesures, seuils compris : un relevé aberrant isolé ne déclenche rien.
        confirmed = self.confirmer.update(bool(causes or limits))
        if projected is not None:
            projected = round(min(max(projected, -40.0), 125.0), 1)
        return Result(score=round(min(max(score, 0.0), 1.0), 3), is_anomaly=confirmed,
                      projected_temp15=projected, features=(limits + causes) if confirmed else [])
