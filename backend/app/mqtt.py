"""Connexion MQTT permanente du backend (certificat client "backend").

paho-mqtt tourne dans son propre thread : cela fonctionne quelle que soit la boucle asyncio
(sous Windows, uvicorn --reload utilise une boucle Proactor, incompatible avec aiomqtt).
Les messages reçus sont transmis à la boucle asyncio du backend.
"""
import asyncio
import json
import logging
import secrets
import ssl
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .config import config
from .journal import write_log
from .util import iso, utcnow

Command = Literal["arm", "disarm", "buzzer_on", "buzzer_off", "reboot"]
Handler = Callable[[str, bytes], Awaitable[None]]

log = logging.getLogger(__name__)
PUBLISH_TIMEOUT_S = 5


class CommandError(Exception):
    pass


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(config.mqtt_ca))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(config.mqtt_cert), str(config.mqtt_key))
    return ctx


class Bus:
    def __init__(self) -> None:
        self._client: mqtt.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._handlers: dict[str, Handler] = {}

    def start(self, handlers: dict[str, Handler]) -> None:
        """Connexion en arrière-plan, reconnexion automatique. Sans effet si MQTT_ENABLED=false."""
        if not config.mqtt_enabled:
            return
        self._loop = asyncio.get_running_loop()
        self._handlers = handlers
        client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"backend-{secrets.token_hex(3)}")
        if config.mqtt_tls:
            client.tls_set_context(_tls_context())
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.reconnect_delay_set(1, 30)
        client.connect_async(config.mqtt_host, config.mqtt_port, keepalive=30)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if self._client:
            self._client.disconnect()
            self._client.loop_stop()
            self._client = None

    # ------------------------------------------------ rappels paho (thread MQTT)
    def _to_loop(self, coro: Awaitable[Any]) -> None:
        if self._loop:
            asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]

    def _on_connect(self, client: mqtt.Client, _u: Any, _f: Any, reason: Any, _p: Any) -> None:
        if reason.is_failure:
            self._to_loop(write_log("error", "backend", f"Connexion MQTT refusée : {reason}"))
            return
        for topic in self._handlers:
            client.subscribe(topic, qos=1)
        self._to_loop(write_log("info", "backend", f"Connecté au broker MQTT {config.mqtt_host}:{config.mqtt_port}"
                                + ("" if config.mqtt_tls else " (sans TLS, développement)")))

    def _on_disconnect(self, _c: mqtt.Client, _u: Any, _f: Any, reason: Any, _p: Any) -> None:
        if reason.is_failure:
            self._to_loop(write_log("warn", "backend", f"Connexion MQTT perdue : {reason}"))

    def _on_message(self, _c: mqtt.Client, _u: Any, msg: mqtt.MQTTMessage) -> None:
        handler = self._handlers.get(msg.topic)
        if handler:
            self._to_loop(self._safe(handler, msg.topic, msg.payload))

    @staticmethod
    async def _safe(handler: Handler, topic: str, payload: bytes) -> None:
        try:
            await handler(topic, payload)
        except Exception:  # noqa: BLE001 (un message ne doit jamais arrêter l'ingestion)
            log.exception("Erreur de traitement du message %s", topic)

    # ------------------------------------------------ publication
    async def publish(self, topic: str, payload: dict[str, Any], qos: int = 1) -> None:
        client = self._client
        if client is None or not client.is_connected():
            raise CommandError("broker MQTT injoignable")
        info = client.publish(topic, json.dumps(payload), qos=qos)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise CommandError(mqtt.error_string(info.rc))
        await asyncio.to_thread(info.wait_for_publish, PUBLISH_TIMEOUT_S)
        if not info.is_published():
            raise CommandError("pas d'accusé de réception du broker")


bus = Bus()


async def send_command(cmd: Command) -> bool:
    """Publie la commande. False si MQTT est désactivé (développement), CommandError si l'envoi échoue."""
    if not config.mqtt_enabled:
        return False
    await bus.publish(f"sentinel/{config.device_id}/cmd", {
        "device": config.device_id,
        "seq": time.time_ns() // 1_000_000,  # croissant même après un redémarrage du backend
        "ts": iso(utcnow()),
        "type": cmd,
        "data": {},
    })
    return True
