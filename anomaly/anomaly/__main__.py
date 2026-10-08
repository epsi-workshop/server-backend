"""Service anomaly : python -m anomaly

Lit sentinel/<boîtier>/telemetry et sentinel/<boîtier>/event, publie sur sentinel/ai/anomaly à chaque mesure.
"""
import json
import logging
import queue
import signal
import ssl
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from .config import VERSION, config
from .detector import SECONDS_PER_DAY, Analyzer, Result
from .history import History

TOPIC = "sentinel/ai/anomaly"
DEVICE = "anomaly"
MAX_AGE = timedelta(minutes=5)
MAX_FUTURE = timedelta(minutes=1)

log = logging.getLogger("anomaly")


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def number(value: Any, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not low <= value <= high:
        return None
    return float(value)


class Inbox:
    """Messages du boîtier : format, identité (topic = champ device) et anti-rejeu, comme le backend."""

    def __init__(self, device: str) -> None:
        self.device = device
        self.last_seq = -1

    def parse(self, topic: str, payload: bytes, now: datetime) -> dict[str, Any] | None:
        try:
            msg = json.loads(payload)
            ts = datetime.fromisoformat(msg["ts"])
            seq = msg["seq"]
        except (ValueError, KeyError, TypeError):
            log.warning("Message rejeté sur %s : format invalide", topic)
            return None
        if msg.get("device") != self.device or not isinstance(seq, int) or ts.tzinfo is None \
                or not isinstance(msg.get("data", {}), dict):
            log.warning("Message rejeté sur %s : enveloppe invalide", topic)
            return None
        if not now - MAX_AGE <= ts <= now + MAX_FUTURE:
            log.warning("Message rejeté sur %s : horodatage hors fenêtre", topic)
            return None
        if seq <= self.last_seq:
            log.warning("Message rejeté sur %s : séquence déjà reçue (%d ≤ %d)", topic, seq, self.last_seq)
            return None
        self.last_seq = seq
        msg["ts"] = ts
        return msg


class Publisher:
    def __init__(self, client: mqtt.Client) -> None:
        self.client = client
        self._last_seq = 0

    def anomaly(self, result: Result, analyzer: Analyzer) -> None:
        # seq en millisecondes : croissant même après un redémarrage du service (anti-rejeu du backend).
        seq = max(time.time_ns() // 1_000_000, self._last_seq + 1)
        self._last_seq = seq
        model = analyzer.model
        payload = {
            "device": DEVICE, "seq": seq, "ts": iso(datetime.now(UTC)), "type": "anomaly",
            "data": {
                "score": result.score, "is_anomaly": result.is_anomaly,
                "projected_temp15": result.projected_temp15, "features": result.features,
                "model_trained_at": iso(datetime.fromtimestamp(model.trained_at, UTC)) if model else None,
                "model_hours": round(model.hours, 1) if model else None,
            },
        }
        info = self.client.publish(TOPIC, json.dumps(payload), qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            log.warning("Résultat non publié (broker injoignable) : %s", mqtt.error_string(info.rc))


def connect(inbox: "queue.Queue[tuple[str, bytes]]") -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=DEVICE)
    if config.mqtt_tls:
        ctx = ssl.create_default_context(cafile=str(config.mqtt_ca))
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.load_cert_chain(str(config.mqtt_cert), str(config.mqtt_key))
        client.tls_set_context(ctx)
    box = f"sentinel/{config.device_id}"

    def on_connect(c: mqtt.Client, _u: Any, _f: Any, rc: Any, _p: Any) -> None:
        log.log(logging.ERROR if rc.is_failure else logging.INFO, "MQTT %s:%d : %s",
                config.mqtt_host, config.mqtt_port, rc)
        if not rc.is_failure:
            c.subscribe([(f"{box}/telemetry", 1), (f"{box}/event", 1)])

    def on_message(_c: mqtt.Client, _u: Any, msg: mqtt.MQTTMessage) -> None:
        try:
            inbox.put_nowait((msg.topic, msg.payload))
        except queue.Full:
            log.warning("File pleine, message ignoré")

    client.on_connect = on_connect
    client.on_message = on_message
    client.reconnect_delay_set(1, 30)
    client.connect_async(config.mqtt_host, config.mqtt_port, keepalive=30)
    client.loop_start()
    return client


def train(analyzer: Analyzer, now: float) -> None:
    model = analyzer.train(now)
    if model:
        log.info("Isolation Forest entraîné sur %d mesures (%.1f h), variables : %s",
                 model.samples, model.hours, ", ".join(dict.fromkeys(model.columns)))
    else:
        log.info("Apprentissage en cours : moins de %g h de mesures, pas encore de modèle", config.min_train_hours)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
    log.info("Service anomaly %s, boîtier %s", VERSION, config.device_id)
    config.data_dir.mkdir(parents=True, exist_ok=True)
    history = History(config.data_dir / "history.db")
    analyzer = Analyzer(history, config)
    train(analyzer, time.time())
    next_train = time.time() + config.retrain_minutes * 60

    messages: queue.Queue[tuple[str, bytes]] = queue.Queue(maxsize=1000)
    client = connect(messages)
    publisher = Publisher(client)
    box_inbox = Inbox(config.device_id)
    temp = hum = None
    was_anomaly = False
    running = True

    def stop(*_: Any) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    try:
        while running:
            if time.time() >= next_train:
                history.prune(time.time() - config.retention_days * SECONDS_PER_DAY)
                train(analyzer, time.time())
                next_train = time.time() + config.retrain_minutes * 60
            try:
                topic, payload = messages.get(timeout=1)
            except queue.Empty:
                continue
            msg = box_inbox.parse(topic, payload, datetime.now(UTC))
            if msg is None:
                continue
            ts = msg["ts"].timestamp()
            data = msg.get("data", {})

            if topic.endswith("/event"):
                if msg.get("type") == "pir" and data.get("state") == 1:
                    history.add_pir(ts)
                continue

            t = number(data.get("temperature"), -40, 125)
            h = number(data.get("humidity"), 0, 100)
            temp = t if t is not None else temp
            hum = h if h is not None else hum
            if (t is None and h is None) or temp is None or hum is None:
                continue  # télémesure sans température ni humidité (distance seule)
            history.add_sample(ts, temp, hum)
            result = analyzer.evaluate(ts, temp, hum)
            publisher.anomaly(result, analyzer)
            if result.is_anomaly != was_anomaly:
                if result.is_anomaly:
                    log.warning("Anomalie environnementale (score %.2f) : %s", result.score, ", ".join(result.features))
                else:
                    log.info("Retour à la normale")
                was_anomaly = result.is_anomaly
    finally:
        client.disconnect()
        client.loop_stop()
        history.close()


if __name__ == "__main__":
    main()
