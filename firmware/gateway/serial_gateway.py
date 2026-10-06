"""Passerelle série -> MQTT, sur le PC où l'Arduino est branché en USB.

Lit les lignes JSON du sketch (firmware/pir_serial), ajoute device, seq et ts, et publie sur
sentinel/<device>/<topic> du broker du PC serveur. Publie aussi le statut online/offline
(retenu, Last Will) comme le fera l'agent de l'UNO Q (#6).

Dans l'autre sens, reçoit les commandes du backend (sentinel/<device>/cmd), les vérifie
(équipement, anti-rejeu) et les transmet à l'Arduino sous la forme {"cmd":"buzzer_on"}.

    python serial_gateway.py                 # configuration dans gateway.env
    python serial_gateway.py --list-ports    # trouver le port COM de l'Arduino
"""
import argparse
import json
import logging
import ssl
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

HERE = Path(__file__).resolve().parent
TOPICS = {"telemetry": 0, "event": 1, "heartbeat": 0}  # topic -> QoS (contrat MQTT)
EVENT_TYPES = {"pir", "lid_open", "imu_shock", "rfid_ok", "rfid_refused"}
COMMANDS = {"arm", "disarm", "buzzer_on", "buzzer_off", "reboot"}
# Une commande est exécutée tout de suite : plus courte que la fenêtre des mesures (5 min côté backend).
CMD_MAX_AGE = timedelta(seconds=30)
CMD_MAX_FUTURE = timedelta(minutes=1)  # tolérance de décalage d'horloge (NTP)

log = logging.getLogger("gateway")


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Sequencer:
    """seq en millisecondes, strictement croissant même après un redémarrage (anti-rejeu du backend)."""

    def __init__(self) -> None:
        self.last = 0

    def next(self) -> int:
        self.last = max(time.time_ns() // 1_000_000, self.last + 1)
        return self.last


def to_message(line: str, device: str, seq: int, now: datetime) -> tuple[str, int, dict[str, Any]] | None:
    """Ligne du sketch -> (topic, QoS, message du contrat). None si la ligne n'est pas un message valide."""
    try:
        msg = json.loads(line)
    except ValueError:
        return None
    if not isinstance(msg, dict):
        return None
    topic, kind, data = msg.get("topic"), msg.get("type"), msg.get("data", {})
    if topic not in TOPICS or not isinstance(kind, str) or not isinstance(data, dict):
        return None
    if topic == "event" and kind not in EVENT_TYPES:
        return None
    return f"sentinel/{device}/{topic}", TOPICS[topic], {
        "device": device, "seq": seq, "ts": iso(now), "type": kind, "data": data,
    }


class CommandGuard:
    """Vérifie une commande reçue du backend avant de la transmettre à l'Arduino.

    Même principe que l'anti-rejeu du backend (app/ingest.py) : le seq doit être strictement plus
    grand que le dernier accepté, et l'horodatage récent. Un message capturé puis renvoyé
    (attaque de rejeu) est donc ignoré.
    """

    def __init__(self, device: str) -> None:
        self.device = device
        self.last_seq: int | None = None

    def check(self, payload: bytes, now: datetime) -> tuple[str | None, str]:
        """(commande, "") si elle est acceptée, sinon (None, raison du refus)."""
        try:
            msg = json.loads(payload)
            device, seq, kind = msg["device"], msg["seq"], msg["type"]
            ts = datetime.fromisoformat(msg["ts"].replace("Z", "+00:00"))
        except (ValueError, KeyError, TypeError, AttributeError):
            return None, "format invalide"
        if device != self.device:
            return None, f"destinée à {device!r}"
        if kind not in COMMANDS:
            return None, f"commande inconnue {kind!r}"
        if not isinstance(seq, int) or ts.tzinfo is None:
            return None, "seq ou ts invalide"
        if ts < now - CMD_MAX_AGE:
            return None, "trop ancienne"
        if ts > now + CMD_MAX_FUTURE:
            return None, "horodatage dans le futur"
        if self.last_seq is not None and seq <= self.last_seq:
            return None, f"seq déjà reçu ({seq} ≤ {self.last_seq}), rejeu possible"
        self.last_seq = seq
        return kind, ""


class SerialLink:
    """Port série partagé : lu par la boucle principale, écrit par le thread MQTT (commandes)."""

    def __init__(self) -> None:
        self._ser: Any = None
        self._lock = threading.Lock()

    def attach(self, ser: Any) -> None:
        with self._lock:
            self._ser = ser

    def write_line(self, line: str) -> bool:
        with self._lock:
            if self._ser is None:
                return False
            try:
                self._ser.write((line + "\n").encode())
            except OSError:  # SerialException en hérite : Arduino débranché pendant l'écriture
                return False
            return True


def tls_context(env: dict[str, str]) -> ssl.SSLContext:
    """mTLS : vérifie le certificat du broker (signé par notre CA) et présente celui du boîtier.

    Le broker lit le CN du certificat client (« box01 ») et l'utilise comme identifiant pour l'ACL :
    plus besoin de mot de passe.
    """
    def path(key: str) -> str:
        p = Path(env[key])
        return str(p if p.is_absolute() else HERE / p)

    ctx = ssl.create_default_context(cafile=path("MQTT_CA"))
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(path("MQTT_CERT"), path("MQTT_KEY"))
    return ctx


def connect_mqtt(env: dict[str, str], device: str, link: SerialLink) -> mqtt.Client:
    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id=f"{device}-gateway")
    use_tls = env.get("MQTT_TLS", "false").lower() == "true"
    host, port = env["MQTT_HOST"], int(env.get("MQTT_PORT", "8883" if use_tls else "1884"))
    if use_tls:
        client.tls_set_context(tls_context(env))
    if env.get("MQTT_USER"):
        client.username_pw_set(env["MQTT_USER"], env.get("MQTT_PASSWORD", ""))
    status = f"sentinel/{device}/status"
    cmd_topic = f"sentinel/{device}/cmd"
    client.will_set(status, "offline", qos=1, retain=True)  # publié par le broker si la passerelle disparaît
    guard = CommandGuard(device)

    def on_connect(c: mqtt.Client, _u: Any, _f: Any, rc: Any, _p: Any) -> None:
        if rc.is_failure:
            log.error("Connexion MQTT refusée : %s (%s ?)", rc, "certificat" if use_tls else "identifiant ou mot de passe")
            return
        log.info("Connecté au broker %s:%s%s", host, port, " (TLS)" if use_tls else " (sans TLS)")
        c.publish(status, "online", qos=1, retain=True)
        c.subscribe(cmd_topic, qos=1)  # à refaire à chaque reconnexion (session non persistante)

    def on_message(_c: mqtt.Client, _u: Any, msg: mqtt.MQTTMessage) -> None:
        cmd, reason = guard.check(msg.payload, datetime.now(UTC))
        if cmd is None:
            log.warning("Commande refusée : %s", reason)
        elif link.write_line(json.dumps({"cmd": cmd}, separators=(",", ":"))):
            log.info("Commande transmise à l'Arduino : %s", cmd)
        else:
            log.warning("Commande %s perdue : Arduino non connecté", cmd)

    client.on_connect = on_connect
    client.on_message = on_message
    client.on_disconnect = lambda c, u, f, rc, p: rc.is_failure and log.warning("Broker perdu : %s", rc)
    client.reconnect_delay_set(1, 30)
    client.connect_async(host, port, keepalive=30)
    client.loop_start()
    return client


def run(env: dict[str, str]) -> None:
    import serial  # pyserial

    device = env.get("DEVICE", "box01")
    port, baud = env["SERIAL_PORT"], int(env.get("SERIAL_BAUD", "115200"))
    link = SerialLink()
    client = connect_mqtt(env, device, link)
    seq = Sequencer()
    try:
        while True:
            try:
                with serial.Serial(port, baud, timeout=1) as ser:
                    log.info("Arduino connecté sur %s (%d bauds)", port, baud)
                    link.attach(ser)
                    while True:
                        raw = ser.readline()
                        if not raw:
                            continue
                        line = raw.decode(errors="replace").strip()
                        message = to_message(line, device, seq.next(), datetime.now(UTC))
                        if message is None:
                            log.debug("Ligne ignorée : %s", line)
                            continue
                        topic, qos, payload = message
                        info = client.publish(topic, json.dumps(payload), qos=qos)
                        if info.rc != mqtt.MQTT_ERR_SUCCESS:
                            log.warning("Non publié (broker injoignable) : %s", line)
                        elif topic.endswith("/event"):
                            log.info("%s %s", payload["type"], payload["data"])
            except serial.SerialException as e:
                link.attach(None)
                log.warning("Port %s indisponible (%s), nouvel essai dans 3 s", port, e)
                time.sleep(3)
    except KeyboardInterrupt:
        pass
    finally:
        client.publish(f"sentinel/{device}/status", "offline", qos=1, retain=True).wait_for_publish(2)
        client.disconnect()
        client.loop_stop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Passerelle série -> MQTT Sentinel-X")
    parser.add_argument("--list-ports", action="store_true", help="lister les ports série disponibles")
    parser.add_argument("--env", default=str(HERE / "gateway.env"), help="fichier de configuration")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s : %(message)s")

    if args.list_ports:
        from serial.tools import list_ports
        for p in list_ports.comports():
            print(f"{p.device:8} {p.description}")
        return
    env = load_env(Path(args.env))
    missing = [k for k in ("SERIAL_PORT", "MQTT_HOST") if not env.get(k)]
    if missing:
        sys.exit(f"À renseigner dans {args.env} : {', '.join(missing)} (modèle : gateway.env.example)")
    run(env)


if __name__ == "__main__":
    main()
