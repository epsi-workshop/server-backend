"""Protection de l'API de la carte : python -m pytest tests (depuis hardware-embedded/uno-q)."""
import base64
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "api"))
from security import Guard, authorized, token_from  # noqa: E402

app = FastAPI()
app.add_middleware(Guard, token="s3cret", allow_simulation=False)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/sensors")
def sensors():
    return {"pir": True}


@app.post("/sensors/rfid/simulate/{uid}")
def simulate(uid: str):
    return {"uid": uid}


@app.websocket("/ws/pir")
async def ws(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json({"motion": True})
    await websocket.close()


client = TestClient(app)
BEARER = {"Authorization": "Bearer s3cret"}


def test_health_stays_public():
    assert client.get("/health").status_code == 200


def test_token_required():
    assert client.get("/sensors").status_code == 401
    assert client.get("/sensors", headers={"Authorization": "Bearer faux"}).status_code == 401
    assert client.get("/sensors", headers=BEARER).status_code == 200


def test_basic_auth_with_token_as_password():
    basic = base64.b64encode(b"sentinel:s3cret").decode()
    assert client.get("/sensors", headers={"Authorization": f"Basic {basic}"}).status_code == 200
    assert token_from("Basic !!!pas-du-base64") == ""


def test_simulation_closed_even_with_token():
    assert client.post("/sensors/rfid/simulate/1BE2E34A", headers=BEARER).status_code == 403


def test_websocket_needs_token():
    with client.websocket_connect("/ws/pir", headers=BEARER) as ws:
        assert ws.receive_json() == {"motion": True}
    try:
        with client.websocket_connect("/ws/pir") as ws:
            ws.receive_json()
        raise AssertionError("WebSocket accepté sans jeton")
    except Exception as e:  # WebSocketDisconnect (code 4401)
        assert getattr(e, "code", None) == 4401


def test_empty_token_means_open_api():
    assert authorized("", token="")
