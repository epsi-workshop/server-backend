"""API capteurs de l'UNO Q : récupération des capteurs en HTTP/WebSocket au lieu de MQTT.

Adresse de base : SENSOR_API_URL (http://talos.local:8000), à laquelle on ajoute les routes :
  GET /health  -> {"status": "ok", "uptime_s": 429}                         heartbeat (boîtier en ligne)
  GET /sensors -> {"temperature_c", "humidity_pct", "pir": {"motion", …}}   télémesure, état du PIR
  WS  /ws/pir  -> {"event": "motion_start", "motion": true, …}             PIR en temps réel

Chaque réponse est traduite en message du contrat (Envelope) et traitée par les mêmes fonctions que
les messages MQTT (ingest.box_*) : base, état, corrélation et dashboard ne voient aucune différence.
Le WebSocket donne le PIR sans attendre ; l'interrogation de /sensors le rattrape s'il est coupé.
"""
import asyncio
import json
import logging
import socket
import time
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException

from .config import config
from .ingest import Envelope, box_event, box_heartbeat, box_telemetry
from .journal import write_log
from .util import utcnow

POLL_S = 5
HEALTH_EVERY = 3  # /health une fois sur 3, soit toutes les 15 s comme le heartbeat du contrat
RETRY_S = 3
# Connexion longue : sous Windows, la résolution d'un nom en .local (mDNS) peut prendre plus de 10 s.
TIMEOUT = httpx.Timeout(5.0, connect=20.0)
SOURCE = "l'API capteurs"
# IPv4 uniquement : talos.local annonce aussi une adresse IPv6 (partage de connexion du téléphone), mais
# l'API n'écoute qu'en IPv4. Sans cela, chaque connexion essaie d'abord l'IPv6 et attend son échec.
IPV4_ONLY = "0.0.0.0"

# Routes de l'API, ajoutées à SENSOR_API_URL (documentation : SENSOR_API_URL/docs).
ROUTE_HEALTH = "/health"
ROUTE_SENSORS = "/sensors"
ROUTE_WS_PIR = "/ws/pir"
ROUTE_OPENAPI = "/openapi.json"  # lue une fois, pour la version affichée dans l'administration

log = logging.getLogger(__name__)


def _number(x: Any) -> float | None:
    """Valeur numérique, ou None (capteur absent : l'API renvoie null)."""
    return float(x) if isinstance(x, int | float) and not isinstance(x, bool) else None


class SensorApi:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.motion: bool | None = None  # dernier état du PIR transmis
        self.http_ok: bool | None = None
        self.ws_ok: bool | None = None
        self.uptime_s = 0  # dernière valeur de /health, affichée dans l'administration
        self.version = "?"

    def _envelope(self, kind: str, data: dict[str, Any]) -> Envelope:
        return Envelope(device=config.device_id, seq=time.time_ns() // 1_000_000, ts=utcnow(), type=kind, data=data)

    async def _set_motion(self, motion: bool) -> None:
        """Ne transmet que les changements : le WebSocket et /sensors peuvent annoncer le même état."""
        if motion == self.motion:
            return
        self.motion = motion
        await box_event(self._envelope("pir", {"state": int(motion)}), SOURCE)

    async def _apply_sensors(self, s: dict[str, Any]) -> None:
        telemetry = {k: v for k, v in (("temperature", _number(s.get("temperature_c"))),
                                       ("humidity", _number(s.get("humidity_pct")))) if v is not None}
        if telemetry:
            await box_telemetry(self._envelope("telemetry", telemetry), SOURCE)
        pir = s.get("pir")
        if isinstance(pir, dict) and isinstance(pir.get("motion"), bool):
            await self._set_motion(pir["motion"])

    async def _http_state(self, ok: bool, error: str = "") -> None:
        """Journalise seulement les changements (pas un message toutes les 5 s pendant une panne)."""
        if ok != self.http_ok:
            self.http_ok = ok
            if ok:
                await write_log("info", "boitier", f"API capteurs joignable ({self.base_url})")
            else:
                await write_log("error", "boitier", f"API capteurs injoignable ({self.base_url}) : {error}")

    async def poll(self) -> None:
        """Heartbeat et télémesure. Sans réponse de /health, le boîtier passe « muet » au bout de 45 s."""
        # Un seul client, gardé ouvert : le nom talos.local n'est résolu qu'à la connexion, pas à chaque requête.
        transport = httpx.AsyncHTTPTransport(local_address=IPV4_ONLY)
        async with httpx.AsyncClient(base_url=self.base_url, timeout=TIMEOUT, transport=transport) as client:
            n = 0
            while True:
                try:
                    if n % HEALTH_EVERY == 0:
                        r = await client.get(ROUTE_HEALTH)
                        r.raise_for_status()
                        self.uptime_s = int(_number(r.json().get("uptime_s")) or 0)
                        await box_heartbeat(self._envelope("heartbeat", {"uptime": self.uptime_s}), SOURCE)
                        if self.version == "?":
                            r = await client.get(ROUTE_OPENAPI)
                            r.raise_for_status()
                            self.version = str(r.json().get("info", {}).get("version", "?"))[:16]
                    r = await client.get(ROUTE_SENSORS)
                    r.raise_for_status()
                    await self._apply_sensors(r.json())
                    await self._http_state(True)
                except (httpx.HTTPError, ValueError, AttributeError) as e:
                    await self._http_state(False, str(e) or type(e).__name__)
                except Exception:  # noqa: BLE001 (la lecture des capteurs ne doit jamais s'arrêter)
                    log.exception("Erreur de traitement de l'API capteurs")
                n += 1
                await asyncio.sleep(POLL_S)

    async def listen(self) -> None:
        """PIR en temps réel ; reconnexion automatique."""
        url = self.base_url.replace("http", "ws", 1) + ROUTE_WS_PIR  # http -> ws, https -> wss
        while True:
            try:
                async with connect(url, open_timeout=20, family=socket.AF_INET) as ws:
                    if not self.ws_ok:
                        self.ws_ok = True
                        log.info("WebSocket PIR connecté (%s)", url)
                    async for raw in ws:
                        msg = json.loads(raw)
                        if isinstance(msg, dict) and isinstance(msg.get("motion"), bool):
                            await self._set_motion(msg["motion"])
            except (OSError, TimeoutError, WebSocketException, ValueError) as e:
                if self.ws_ok is not False:
                    self.ws_ok = False
                    log.warning("WebSocket PIR perdu (%s), le PIR est lu toutes les %d s en attendant", e, POLL_S)
            except Exception:  # noqa: BLE001
                log.exception("Erreur du WebSocket PIR")
            await asyncio.sleep(RETRY_S)

    async def run(self) -> None:
        await write_log("info", "backend", f"Capteurs lus sur l'API {self.base_url}")
        await asyncio.gather(self.poll(), self.listen())


# Instance unique : démarrée par main.py, lue par l'état des services (routers/control.py).
sensor_api = SensorApi(config.sensor_api_url) if config.sensor_api_url else None
