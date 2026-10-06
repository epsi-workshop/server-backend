from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "0.1.0"
BACKEND_DIR = Path(__file__).resolve().parent.parent
# backend/.env, quel que soit le dossier depuis lequel uvicorn est lancé.
ENV_FILE = BACKEND_DIR / ".env"


class Config(BaseSettings):
    """Configuration lue dans les variables d'environnement (ou backend/.env)."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://sentinel:sentinel@localhost:5432/sentinel"
    # Origines acceptées pour les requêtes modifiantes et le WebSocket, séparées par des virgules.
    allowed_origins: str = "https://192.168.50.10,https://sentinel.lan"
    cookie_secure: bool = True
    session_ttl_hours: int = 12
    expose_docs: bool = False
    device_id: str = "box01"
    # Fuseau des horaires d'occupation (le conteneur tourne en UTC).
    timezone: str = "Europe/Paris"

    mqtt_enabled: bool = False
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 8883
    # false uniquement avec le Mosquitto de développement (docker-compose.dev.yml), en attendant la PKI (#11, #12).
    mqtt_tls: bool = True
    mqtt_ca: Path = Path("/certs/ca.crt")
    mqtt_cert: Path = Path("/certs/backend.crt")
    mqtt_key: Path = Path("/certs/backend.key")

    # API capteurs de l'UNO Q (sensor_api.py), ex. http://talos.local:8000 (sans route : sensor_api.py les ajoute). Vide = désactivée.
    # Ne pas l'utiliser en même temps que la passerelle MQTT du même boîtier (deux sources pour un PIR).
    sensor_api_url: str = ""

    # Flux MJPEG annoté rediffusé par le service vision (seul lecteur de l'ESP32-CAM).
    camera_url: str = "http://vision:8081/stream"
    camera_user: str = ""  # authentification HTTP Basic, laissée vide s'il n'y en a pas
    camera_password: str = ""
    # Captures enregistrées par le service vision (volume partagé "snapshots").
    snapshot_dir: Path = Path("/snapshots")

    @field_validator("mqtt_ca", "mqtt_cert", "mqtt_key", "snapshot_dir")
    @classmethod
    def relative_to_backend(cls, p: Path) -> Path:
        """Chemin relatif = relatif au dossier backend/, pas au dossier de lancement."""
        return p if p.is_absolute() else (BACKEND_DIR / p).resolve()

    @property
    def origins(self) -> set[str]:
        return {o.strip().rstrip("/") for o in self.allowed_origins.split(",") if o.strip()}


config = Config()
