"""API capteurs pour Arduino UNO Q.

Température/humidité : DHT11 ou DHT22 sur D2 (modèle détecté), lu par le MCU via le Bridge.
PIR HC-SR501 : sortie sur D7, lue par le MCU ; temps réel sur /ws/pir.
Caméra : ESP32-CAM en Wi-Fi, relayée sur /camera/stream et /camera/snapshot.
Servo SG90 (rotation caméra) : signal sur D9, piloté via /servo.
Écran OLED : reconnaissance faciale via /display/face, badges via /display/badge.
Haut-parleur (module MOS sur D5) : bips et sirène via /sound/{nom}, /sound/stop.
Enceinte Bluetooth : /audio (recherche, connexion, volume), mêmes sons plus des messages parlés.
"""
import socket
import threading
import time
from contextlib import asynccontextmanager
import pathlib

from fastapi import FastAPI, HTTPException, Path, Query, WebSocket
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

from bridge import BridgeError, call, read_float, read_int
from camera import camera_hub
from realtime import pir_broadcaster
import audio


@asynccontextmanager
async def lifespan(app):
    audio.generate_sounds()
    threading.Thread(target=audio.reconnect_loop, name="bt-reconnect", daemon=True).start()
    await pir_broadcaster.start()
    yield
    await pir_broadcaster.stop()
    await camera_hub.stop()


app = FastAPI(title="UNO Q Sensor API", version="0.3.0", lifespan=lifespan)
# Autorise les dashboards servis depuis une autre origine (autre PC du réseau)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST", "DELETE"], allow_headers=["*"])
START = time.time()


@app.get("/health")
def health():
    return {"status": "ok", "host": socket.gethostname(), "uptime_s": round(time.time() - START)}


def pir_data():
    state = read_int("get_pir")
    last_ms = read_int("get_pir_last")
    return {
        "motion": None if state is None else bool(state),
        "last_motion_s_ago": None if last_ms is None or last_ms < 0 else round(last_ms / 1000, 1),
        "detections": read_int("get_pir_count"),
    }


def pir_hold():
    ms = read_int("get_pir_hold")
    if ms is None:
        raise HTTPException(503, "microcontrôleur injoignable via le Bridge")
    return {"hold_s": ms / 1000}


def lid_data():
    state, source = read_int("get_lid"), read_int("get_lid_source")
    return {
        "open": None if state is None else bool(state),
        "source": None if source is None else ("simulation" if source else "capteur"),
    }


@app.get("/sensors/lid")
def lid():
    """Porte du pot (capteur infrarouge HW-201 sur D4) ; source = capteur ou simulation."""
    return lid_data()


LID_SIM = {"open": 1, "closed": 0, "off": -1}

# Passages de badge : numérotés ici pour fusionner le lecteur RC522 et les badges simulés.
# Le backend repère un nouveau passage quand seq augmente.
_rfid_lock = threading.Lock()
_rfid = {"seq": 0, "uid": None, "source": None, "mcu_seq": None}


def rfid_data():
    mcu_seq = read_int("get_rfid_seq")
    with _rfid_lock:
        if mcu_seq is not None and mcu_seq != _rfid["mcu_seq"]:
            if _rfid["mcu_seq"] is not None and mcu_seq > 0:  # premier relevé = référence, pas un passage
                try:
                    uid = call("get_rfid_uid")
                except (BridgeError, OSError):
                    uid = None
                if uid:
                    _rfid.update(seq=_rfid["seq"] + 1, uid=str(uid).upper(), source="lecteur")
            _rfid["mcu_seq"] = mcu_seq
        return {"seq": _rfid["seq"], "uid": _rfid["uid"], "source": _rfid["source"]}


@app.get("/sensors/rfid")
def rfid():
    """Dernier badge présenté (lecteur RC522 ou simulation) ; seq augmente à chaque passage."""
    return rfid_data()


@app.post("/sensors/rfid/simulate/{uid}")
def rfid_simulate(uid: str = Path(..., pattern="^[0-9A-Fa-f]{8,20}$", description="UID du badge en hexadécimal, ex. 04A1B2C3")):
    """Simule le passage d'un badge, pour tester sans lecteur."""
    with _rfid_lock:
        _rfid.update(seq=_rfid["seq"] + 1, uid=uid.upper(), source="simulation")
    return rfid_data()


@app.get("/system")
def system():
    """Armement imposé par le backend ; armé = porte verrouillée (sortie D3 à l'état haut)."""
    armed = read_int("get_armed")
    return {"armed": None if armed is None else bool(armed), "locked": None if armed is None else bool(armed)}


@app.post("/system/armed/{state}")
def system_armed(state: str = Path(..., pattern="^(on|off)$", description="on = armé et verrouillé, off = désarmé")):
    """Appelé par le backend à chaque changement d'armement (badge ou dashboard)."""
    try:
        call("set_armed", 1 if state == "on" else 0)
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return system()


@app.post("/sensors/lid/simulate/{state}")
def lid_simulate(state: str = Path(..., pattern="^(open|closed|off)$", description="open, closed, ou off pour revenir au capteur")):
    """Impose une valeur d'exemple (open / closed) pour tester sans capteur ; off revient au capteur réel."""
    try:
        call("set_lid_sim", LID_SIM[state])
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return lid_data()


@app.get("/sensors")
def sensors():
    return {
        "temperature_c": read_float("get_temperature"),
        "humidity_pct": read_float("get_humidity"),
        "pir": pir_data(),
        "lid": lid_data(),
        "rfid": rfid_data(),
        "armed": None if (a := read_int("get_armed")) is None else bool(a),
        "motion": None,
        "timestamp": time.time(),
    }


def dht_model():
    model = read_int("get_dht_model")
    return f"DHT{model}" if model else None


@app.get("/sensors/temperature")
def temperature():
    return {"temperature_c": read_float("get_temperature"), "sensor": dht_model()}


@app.get("/sensors/humidity")
def humidity():
    return {"humidity_pct": read_float("get_humidity"), "sensor": dht_model()}


@app.get("/sensors/pir")
def pir():
    return pir_data()


@app.get("/sensors/pir/hold")
def pir_hold_get():
    """Durée pendant laquelle l'état « mouvement » est maintenu après le dernier signal du capteur."""
    return pir_hold()


@app.post("/sensors/pir/hold/{seconds}")
def pir_hold_set(seconds: float = Path(..., ge=0, le=60, description="Maintien en secondes (0 = signal brut du capteur)")):
    """Règle le lissage du PIR : le HC-SR501 alterne HIGH/LOW pendant un mouvement continu."""
    try:
        call("set_pir_hold", int(seconds * 1000))
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return pir_hold()


@app.get("/sensors/motion")
def motion():
    return {"motion": None}


@app.get("/camera/snapshot")
async def camera_snapshot():
    try:
        jpeg = await camera_hub.snapshot()
    except Exception as e:
        return JSONResponse({"error": f"camera unreachable: {e}"}, status_code=503)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@app.get("/camera/stream")
async def camera_stream():
    return StreamingResponse(
        camera_hub.frames(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/camera/status")
async def camera_status():
    return await camera_hub.status()


SERVO_DEFAULT_SPEED = 180  # degrés/seconde ; le SG90 monte à environ 600


class ServoMove(BaseModel):
    angle: int = Field(..., ge=0, le=180, description="Angle cible en degrés (0 à 180, 90 = centre)")
    speed: int = Field(SERVO_DEFAULT_SPEED, ge=1, le=600, description="Vitesse en degrés/seconde")


def servo_state():
    angle, target = read_int("get_servo"), read_int("get_servo_target")
    if angle is None or target is None:
        raise HTTPException(503, "microcontrôleur injoignable via le Bridge")
    return {"angle": angle, "target": target, "moving": angle != target}


@app.get("/servo")
def servo_get():
    """Position actuelle du servo et position visée."""
    return servo_state()


def move_servo(angle: int, speed: int):
    try:
        call("set_servo", angle, speed)
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return servo_state()


@app.post("/servo")
def servo_move(move: ServoMove):
    """Oriente le servo (corps JSON) ; le mouvement est progressif, la réponse n'attend pas la fin."""
    return move_servo(move.angle, move.speed)


@app.post("/servo/{angle}")
def servo_move_path(
    angle: int = Path(..., ge=0, le=180, description="Angle cible en degrés (0 à 180, 90 = centre)"),
    speed: int = Query(SERVO_DEFAULT_SPEED, ge=1, le=600, description="Vitesse en degrés/seconde"),
):
    """Oriente le servo avec l'angle dans l'URL, ex. POST /servo/45?speed=300."""
    return move_servo(angle, speed)


FACE_KINDS = {"known": 1, "unknown": 2}


class DisplayFace(BaseModel):
    kind: str = Field(..., pattern="^(known|unknown)$", description="known : BONJOUR <nom> ; unknown : INTRU DÉTECTÉ")
    name: str = Field("", max_length=16, description="Prénom affiché pour un visage reconnu")
    seconds: int = Field(5, ge=1, le=30, description="Durée d'affichage")


BADGE_RESULTS = {"ok": 2, "refused": 3, "enroll": 4}


class DisplayBadge(BaseModel):
    result: str = Field(..., pattern="^(ok|refused|enroll)$", description="ok : accepté ; refused : refusé ; enroll : lu pour enregistrement")
    uid: str = Field(..., max_length=32, description="UID lu, ex. AB:0C:A4:CA")
    name: str = Field("", max_length=16, description="Titulaire (badge accepté)")
    armed: bool = Field(False, description="État après un badge accepté")
    seconds: int = Field(4, ge=1, le=30)


@app.post("/display/badge")
def display_badge(msg: DisplayBadge):
    """Décision du backend pour un badge, affichée sur l'écran OLED."""
    try:
        call("show_badge", BADGE_RESULTS[msg.result], msg.uid.upper(), msg.name.upper(), int(msg.armed), msg.seconds)
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    audio.player.play({"ok": "ok", "refused": "refused", "enroll": "test"}[msg.result])
    return msg


SOUNDS = {"ok": 1, "refused": 2, "hello": 3, "siren": 4, "test": 5}


MOTOR_MAX_MS = 30000
MOTOR_DIR = {-1: "left", 0: "stopped", 1: "right"}


def motor_state():
    d = read_int("get_motor")
    if d is None:
        raise HTTPException(503, "microcontrôleur injoignable via le Bridge")
    return {"direction": MOTOR_DIR.get(d, "stopped"), "running": d != 0}


def motor_move(direction: int, ms: int):
    try:
        call("move_motor", direction, ms)
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return {**motor_state(), "ms": ms}


@app.get("/motor")
def motor_get():
    """Tête de la citrouille (pont en H, relais D8 / A2) : left, right ou stopped."""
    return motor_state()


@app.post("/motor/left")
def motor_left(ms: int = Query(500, ge=1, le=MOTOR_MAX_MS, description="Durée de rotation en millisecondes")):
    """Tourne la tête vers la gauche pendant ms millisecondes (relais 1)."""
    return motor_move(-1, ms)


@app.post("/motor/right")
def motor_right(ms: int = Query(500, ge=1, le=MOTOR_MAX_MS, description="Durée de rotation en millisecondes")):
    """Tourne la tête vers la droite pendant ms millisecondes (relais 2)."""
    return motor_move(1, ms)


@app.post("/motor/run")
def motor_run(seconds: int = Query(5, ge=1, le=MOTOR_MAX_MS // 1000)):
    """Compatibilité : vers la gauche pendant N secondes."""
    return motor_move(-1, seconds * 1000)


@app.post("/motor/stop")
def motor_stop():
    return motor_move(0, 0)


@app.post("/sound/stop")
def sound_stop():
    """Coupe le son en cours (sirène comprise)."""
    audio.player.stop()
    try:
        call("stop_sound")
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return {"playing": None}


@app.post("/sound/{name}")
def sound_play(
    name: str = Path(..., pattern="^(ok|refused|hello|siren|test)$", description="ok, refused, hello, siren ou test"),
    seconds: int = Query(10, ge=1, le=120, description="Durée de la sirène"),
):
    """Joue un son sur le haut-parleur (D5, module MOS) et sur l'enceinte Bluetooth si elle est connectée."""
    bluetooth = audio.player.play(name, seconds)
    try:
        call("play_sound", SOUNDS[name], seconds)
    except (BridgeError, OSError) as e:
        if not bluetooth:
            raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return {"playing": name, "seconds": seconds if name == "siren" else None, "bluetooth": bluetooth}


# ---------------------------------------------------------------- enceinte Bluetooth
class SpeakerConnect(BaseModel):
    mac: str | None = Field(None, pattern="^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", description="Adresse, ex. 12:34:56:78:9A:BC")
    name: str | None = Field(None, min_length=1, max_length=64, description="Nom de l'enceinte (recherche si pas d'adresse)")


def _audio(fn, *args):
    try:
        return fn(*args)
    except audio.AudioError as e:
        raise HTTPException(409, str(e))


@app.get("/audio")
def audio_status():
    """Enceinte mémorisée, connexion, volume et sons disponibles."""
    return audio.status()


@app.get("/audio/devices")
def audio_devices(seconds: int = Query(8, ge=3, le=20, description="Durée de la recherche")):
    """Recherche les appareils Bluetooth à portée (enceintes en premier). Mettre l'enceinte en mode appairage."""
    return _audio(audio.scan, seconds)


@app.post("/audio/connect")
def audio_connect(body: SpeakerConnect):
    """Appaire et connecte l'enceinte (adresse, ou nom recherché), puis la mémorise pour la reconnexion."""
    return _audio(audio.connect, body.mac, body.name)


@app.post("/audio/disconnect")
def audio_disconnect():
    return _audio(audio.disconnect)


@app.delete("/audio/speaker")
def audio_forget():
    """Oublie l'enceinte (plus de reconnexion automatique)."""
    return _audio(audio.forget)


@app.post("/audio/volume/{pct}")
def audio_volume(pct: int = Path(..., ge=0, le=100)):
    return _audio(audio.set_volume, pct)


@app.post("/display/face")
def display_face(msg: DisplayFace):
    """Résultat de la reconnaissance faciale (service vision), affiché par-dessus l'écran de surveillance."""
    try:
        call("show_face", FACE_KINDS[msg.kind], msg.name.upper(), msg.seconds)
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    audio.player.play("hello" if msg.kind == "known" else "intruder")
    return {"kind": msg.kind, "name": msg.name.upper(), "seconds": msg.seconds}


@app.websocket("/ws/pir")
async def ws_pir(ws: WebSocket):
    await pir_broadcaster.handle(ws)


@app.get("/live", response_class=HTMLResponse)
def live():
    return (pathlib.Path(__file__).parent / "live.html").read_text()
