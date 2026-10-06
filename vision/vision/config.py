from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VERSION = "0.1.0"
VISION_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = VISION_DIR / ".env"


class Config(BaseSettings):
    """Configuration lue dans les variables d'environnement (ou vision/.env)."""

    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    # ESP32-CAM (exemple CameraWebServer). Le service vision est son seul client.
    camera_url: str = "http://192.168.50.21:81/stream"
    camera_user: str = ""
    camera_password: str = ""

    # Flux annoté rediffusé au backend. 127.0.0.1 en local ; 0.0.0.0 dans Docker (port non publié).
    stream_host: str = "127.0.0.1"
    stream_port: int = 8081

    snapshot_dir: Path = Path("/snapshots")

    mqtt_host: str = "mosquitto"
    mqtt_port: int = 8883
    mqtt_tls: bool = True
    mqtt_ca: Path = Path("/certs/ca.crt")
    mqtt_cert: Path = Path("/certs/vision.crt")
    mqtt_key: Path = Path("/certs/vision.key")

    # Détection de mouvement (caméra fixe)
    motion_min_area: float = 0.004  # plus petite zone en mouvement retenue, en fraction de l'image
    motion_confirm: int = 3  # mouvement confirmé sur motion_confirm images…
    motion_window: int = 5  # …parmi les motion_window dernières (évite les déclenchements sur un parasite)
    warmup_frames: int = 30  # apprentissage du fond au démarrage, sans détection
    snapshot_interval_s: float = 3.0  # au plus une capture toutes les N secondes pendant un mouvement
    publish_interval_s: float = 2.0  # republication pendant le mouvement : garde la caméra déverrouillée

    @field_validator("mqtt_ca", "mqtt_cert", "mqtt_key", "snapshot_dir")
    @classmethod
    def relative_to_vision(cls, p: Path) -> Path:
        """Chemin relatif = relatif au dossier vision/, pas au dossier de lancement."""
        return p if p.is_absolute() else (VISION_DIR / p).resolve()


config = Config()
