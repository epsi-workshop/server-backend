"""API capteurs pour Arduino UNO Q.

Température/humidité : DHT11 ou DHT22 sur D2 (modèle détecté), lu par le MCU via le Bridge.
PIR HC-SR501 : sortie sur D7, lue par le MCU ; temps réel sur /ws/pir.
Caméra : ESP32-CAM en Wi-Fi, relayée sur /camera/stream et /camera/snapshot.
Servo SG90 (rotation caméra) : signal sur D9, piloté via /servo.
Écran OLED : résultat de la reconnaissance faciale via /display/face.
"""
import socket
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


@asynccontextmanager
async def lifespan(app):
    await pir_broadcaster.start()
    yield
    await pir_broadcaster.stop()
    await camera_hub.stop()


app = FastAPI(title="UNO Q Sensor API", version="0.2.0", lifespan=lifespan)
# Autorise les dashboards servis depuis une autre origine (autre PC du réseau)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
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


@app.get("/sensors")
def sensors():
    return {
        "temperature_c": read_float("get_temperature"),
        "humidity_pct": read_float("get_humidity"),
        "pir": pir_data(),
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


@app.post("/display/face")
def display_face(msg: DisplayFace):
    """Résultat de la reconnaissance faciale (service vision), affiché par-dessus l'écran de surveillance."""
    try:
        call("show_face", FACE_KINDS[msg.kind], msg.name.upper(), msg.seconds)
    except (BridgeError, OSError) as e:
        raise HTTPException(503, f"microcontrôleur injoignable via le Bridge : {e}")
    return {"kind": msg.kind, "name": msg.name.upper(), "seconds": msg.seconds}


@app.websocket("/ws/pir")
async def ws_pir(ws: WebSocket):
    await pir_broadcaster.handle(ws)


@app.get("/live", response_class=HTMLResponse)
def live():
    return (pathlib.Path(__file__).parent / "live.html").read_text()
