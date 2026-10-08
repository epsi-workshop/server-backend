"""Suivi du mouvement : le servo de l'UNO Q oriente la caméra vers la plus grande zone en mouvement.

La détection (MOG2) suppose une caméra fixe : quand la caméra tourne, toute l'image « bouge ».
Le suivi gèle donc la détection pendant la rotation et la stabilisation (frozen), puis le fond est
réappris à la nouvelle position (MotionDetector.relearn).

Commande : POST {SERVO_API_URL}/servo/{angle}?speed={°/s}, envoyée dans un thread pour ne jamais
ralentir l'analyse des images.
"""
import logging
import threading

import httpx

from .motion import Box

log = logging.getLogger(__name__)

SERVO_MIN, SERVO_MAX = 0, 180
# Connexion longue : la résolution d'un nom en .local (mDNS) peut prendre plusieurs secondes.
TIMEOUT = httpx.Timeout(5.0, connect=20.0)
# IPv4 uniquement : talos.local annonce aussi une IPv6 sur laquelle l'API n'écoute pas (cf. backend/app/sensor_api.py).
IPV4_ONLY = "0.0.0.0"


def largest(boxes: list[Box]) -> Box | None:
    """Zone qui concentre le plus de mouvement : en général la personne."""
    return max(boxes, key=lambda b: b[2] * b[3], default=None)


class Tracker:
    """Décide des rotations. Logique pure (horloge passée en paramètre) : testable sans servo ni caméra."""

    def __init__(self, *, fov_deg: float, deadband: float, gain: float, speed: int, settle_s: float,
                 min_interval_s: float, invert: bool, home_angle: int, home_after_s: float, now: float) -> None:
        self.fov_deg = fov_deg  # champ de vision horizontal de la caméra
        self.deadband = deadband  # écart au centre toléré, en fraction de la demi-largeur
        self.gain = gain  # < 1 : corrige un peu moins que l'écart mesuré, pour ne pas osciller
        self.speed = speed
        self.settle_s = settle_s  # stabilisation de l'image après la rotation
        self.min_interval_s = min_interval_s
        self.invert = invert
        self.home_angle = home_angle
        self.home_after_s = home_after_s  # retour au centre sans mouvement (0 = jamais)
        self.angle = home_angle  # dernier angle commandé
        self.busy_until = 0.0
        self.last_move = -min_interval_s
        self.last_motion = now

    def frozen(self, now: float) -> bool:
        """Caméra en rotation ou en cours de stabilisation : la détection ne doit pas tourner."""
        return now < self.busy_until

    def home(self, now: float) -> int:
        """Retour au repos au démarrage : la position réelle est inconnue, on attend une course complète."""
        self.angle = self.home_angle
        self.busy_until = now + (SERVO_MAX - SERVO_MIN) / self.speed + self.settle_s
        self.last_move = now
        return self.home_angle

    def update(self, now: float, boxes: list[Box], frame_width: int) -> int | None:
        """Nouvel angle à commander, ou None. boxes : zones en mouvement confirmé (vide sinon)."""
        if self.frozen(now) or now - self.last_move < self.min_interval_s:
            if boxes:
                self.last_motion = now
            return None
        focus = largest(boxes)
        if focus is None:
            if self.home_after_s and now - self.last_motion >= self.home_after_s and self.angle != self.home_angle:
                log.info("Pas de mouvement depuis %.0f s : retour à %d°", self.home_after_s, self.home_angle)
                return self._move(now, self.home_angle)
            return None

        self.last_motion = now
        half = frame_width / 2
        offset = (focus[0] + focus[2] / 2 - half) / half  # -1 (bord gauche) … +1 (bord droit)
        if abs(offset) < self.deadband:
            return None
        # Sujet à droite de l'image : la caméra doit tourner vers la droite, soit un angle plus petit
        # pour un servo monté axe vers le haut (TRACK_INVERT=true si le montage est inversé).
        delta = offset * self.fov_deg / 2 * self.gain
        target = round(self.angle + (delta if self.invert else -delta))
        target = max(SERVO_MIN, min(SERVO_MAX, target))
        if target == self.angle:
            return None  # déjà en butée
        return self._move(now, target)

    def _move(self, now: float, target: int) -> int:
        self.busy_until = now + abs(target - self.angle) / self.speed + self.settle_s
        self.angle = target
        self.last_move = now
        return target


class ServoClient:
    """Envoie les commandes au servo dans un thread ; seule la plus récente compte."""

    def __init__(self, base_url: str, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=TIMEOUT, transport=httpx.HTTPTransport(local_address=IPV4_ONLY),
                                  headers={"Authorization": f"Bearer {token}"} if token else {})
        self._cond = threading.Condition()
        self._pending: tuple[int, int] | None = None
        self._ok: bool | None = None
        threading.Thread(target=self._run, name="servo", daemon=True).start()

    def move(self, angle: int, speed: int) -> None:
        with self._cond:
            self._pending = (angle, speed)
            self._cond.notify()

    def _run(self) -> None:
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._pending is not None)
                angle, speed = self._pending
                self._pending = None
            try:
                self.client.post(f"{self.base_url}/servo/{angle}", params={"speed": speed}).raise_for_status()
                if self._ok is not True:
                    log.info("Servo joignable sur %s", self.base_url)
                self._ok = True
                log.debug("Servo -> %d° à %d°/s", angle, speed)
            except httpx.HTTPError as e:
                if self._ok is not False:  # une ligne par panne, pas une par commande
                    log.warning("Servo injoignable (%s : %s) : la caméra reste fixe", type(e).__name__, e)
                self._ok = False
