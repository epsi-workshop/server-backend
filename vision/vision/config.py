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

    # Suivi : le servo de l'UNO Q oriente la caméra vers le mouvement (tracking.py). Vide = caméra fixe.
    servo_api_url: str = ""  # ex. http://talos.local:8000 (même API que SENSOR_API_URL du backend)
    track_fov_deg: float = 60.0  # champ de vision horizontal de l'ESP32-CAM (OV2640, objectif d'origine)
    track_deadband: float = 0.15  # pas de rotation si le sujet est à moins de 15 % du centre (demi-largeur)
    track_gain: float = 0.8  # part de l'écart corrigée à chaque rotation (< 1 : pas d'oscillation)
    track_speed: int = 150  # vitesse de rotation en °/s
    track_settle_s: float = 0.6  # attente après la rotation, le temps que l'image se stabilise
    track_min_interval_s: float = 1.0  # au plus une rotation par seconde
    track_relearn_frames: int = 8  # apprentissage du fond après une rotation
    track_invert: bool = False  # true si la caméra tourne dans le mauvais sens
    track_home_angle: int = 90  # position de repos
    track_home_after_s: float = 20.0  # retour au repos sans mouvement (0 = jamais)

    # Détection de personnes (person.py, YOLOX-S). Vide = désactivée : le mouvement seul compte dans le score.
    person_model: Path | None = None  # ex. ../models/object_detection_yolox_2022nov.onnx
    person_input_size: int = 416  # 320 plus rapide, 640 plus précis (cahier : « résolution 320 ou 416 »)
    person_conf: float = 0.5  # confiance minimale d'une personne
    person_interval_s: float = 0.2  # au plus 5 analyses par seconde pendant un mouvement (ENF-04)
    person_confirm: int = 3  # personne confirmée sur 3 analyses…
    person_window: int = 5  # …parmi les 5 dernières

    # Reconnaissance faciale (faces.py). Vide = désactivée. Galerie écrite par le backend (même dossier).
    face_models_dir: Path | None = None  # ex. ../models (scripts/download-face-models.sh)
    faces_dir: Path = Path("/faces")
    face_threshold: float = 0.363  # cosinus SFace minimal pour reconnaître un membre (valeur OpenCV Zoo)
    face_min_px: int = 40  # visage plus petit (trop loin) ignoré
    face_interval_s: float = 0.3  # au plus une analyse toutes les 0,3 s
    face_cooldown_s: float = 30.0  # une même personne signalée au plus toutes les 30 s
    api_token: str = ""  # jeton de l'API de l'UNO Q (servo, écran), envoyé en « Authorization: Bearer »
    display_api_url: str = ""  # écran OLED de l'UNO Q, ex. http://talos.local:8000 ; vide = pas d'écran
    display_seconds: int = 5

    @field_validator("mqtt_ca", "mqtt_cert", "mqtt_key", "snapshot_dir", "face_models_dir", "faces_dir",
                     "person_model")
    @classmethod
    def relative_to_vision(cls, p: Path | None) -> Path | None:
        """Chemin relatif = relatif au dossier vision/, pas au dossier de lancement."""
        return p if p is None or p.is_absolute() else (VISION_DIR / p).resolve()


config = Config()
