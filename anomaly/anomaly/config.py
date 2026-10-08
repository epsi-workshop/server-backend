from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "0.1.0"
ANOMALY_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ANOMALY_DIR / ".env"


class Config(BaseSettings):
    """Configuration lue dans les variables d'environnement (ou anomaly/.env)."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    device_id: str = "box01"
    # Heure et jour de la semaine sont calculés dans ce fuseau (horaires d'occupation de la salle).
    timezone: str = "Europe/Paris"
    # Historique des mesures (SQLite) : survit aux redémarrages, sert à l'entraînement.
    data_dir: Path = Path("/data")
    retention_days: int = 30

    mqtt_host: str = "mosquitto"
    mqtt_port: int = 8883
    mqtt_tls: bool = True
    mqtt_ca: Path = Path("/certs/ca.crt")
    mqtt_cert: Path = Path("/certs/anomaly.crt")
    mqtt_key: Path = Path("/certs/anomaly.key")

    # Isolation Forest
    min_train_hours: float = 2.0  # pas de modèle avant N heures de mesures normales
    retrain_minutes: int = 60  # réentraînement périodique sur tout l'historique
    contamination: float = 0.01  # part attendue de mesures atypiques dans l'historique
    confirm: int = 3  # anomalie confirmée sur `confirm` évaluations…
    window: int = 5  # …parmi les `window` dernières (une mesure isolée ne déclenche rien)
    # Heure et jour ne deviennent des variables que si l'historique les couvre : sinon chaque nouvelle
    # heure serait « inconnue » du modèle, donc anormale (fausses alertes).
    hour_feature_min_hours: float = 24.0
    weekday_feature_min_days: float = 7.0

    # Volet prédictif : régression linéaire sur les dernières minutes, projetée à +15 min.
    projection_window_min: float = 30.0
    projection_horizon_min: float = 15.0
    temp_limit: float = 27.0  # °C : salle serveur, haut de la plage recommandée ASHRAE
    humidity_limit: float = 80.0  # % HR

    @field_validator("mqtt_ca", "mqtt_cert", "mqtt_key", "data_dir")
    @classmethod
    def relative_to_anomaly(cls, p: Path) -> Path:
        """Chemin relatif = relatif au dossier anomaly/, pas au dossier de lancement."""
        return p if p.is_absolute() else (ANOMALY_DIR / p).resolve()


config = Config()
