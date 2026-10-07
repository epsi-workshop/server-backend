"""Publication des détections sur sentinel/vision/detection (contrat MQTT)."""
import json
import logging
import ssl
import time
from datetime import UTC, datetime
from typing import Any, Literal

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .config import Config

TOPIC = "sentinel/vision/detection"
DEVICE = "vision"

log = logging.getLogger(__name__)


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Publisher:
    def __init__(self, cfg: Config) -> None:
        self.client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=DEVICE)
        if cfg.mqtt_tls:
            ctx = ssl.create_default_context(cafile=str(cfg.mqtt_ca))
            ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            ctx.load_cert_chain(str(cfg.mqtt_cert), str(cfg.mqtt_key))
            self.client.tls_set_context(ctx)
        self.client.on_connect = lambda c, u, f, rc, p: log.log(
            logging.ERROR if rc.is_failure else logging.INFO, "MQTT %s:%d : %s", cfg.mqtt_host, cfg.mqtt_port, rc)
        self.client.reconnect_delay_set(1, 30)
        self.client.connect_async(cfg.mqtt_host, cfg.mqtt_port, keepalive=30)
        self.client.loop_start()
        self._last_seq = 0

    def detection(self, kind: Literal["motion", "person", "face_known", "face_unknown"], confidence: float,
                  snapshot: str | None, member_id: str | None = None) -> None:
        # seq en millisecondes : croissant même après un redémarrage du service (anti-rejeu du backend).
        seq = max(time.time_ns() // 1_000_000, self._last_seq + 1)
        self._last_seq = seq
        payload: dict[str, Any] = {
            "device": DEVICE, "seq": seq, "ts": iso(datetime.now(UTC)), "type": kind,
            "data": {"confidence": round(confidence, 2), "snapshot": snapshot},
        }
        if member_id:
            payload["data"]["member_id"] = member_id
        info = self.client.publish(TOPIC, json.dumps(payload), qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("Détection non publiée (broker injoignable) : %s", mqtt.error_string(info.rc))

    def stop(self) -> None:
        self.client.disconnect()
        self.client.loop_stop()
