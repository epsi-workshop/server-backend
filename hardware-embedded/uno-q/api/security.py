"""Protection de l'API de la carte : jeton obligatoire, routes de simulation fermées, origines web limitées.

Sans elle, n'importe quel appareil du Wi-Fi (ou une page web ouverte par un opérateur, grâce au CORS « * »)
peut simuler un badge et désarmer le système, faire passer la porte pour fermée, regarder la caméra,
piloter le servo et l'écran. À activer dans main.py, à la place du CORSMiddleware :

    from security import install
    install(app)

Variables (fichier ~/sensor-api/.env, chargé par sensor-api.service) :
    API_TOKEN=<jeton>     même valeur que UNOQ_API_TOKEN du serveur ; vide = API ouverte (déconseillé)
    ALLOW_SIMULATION=0    1 = routes /simulate autorisées (essais sans matériel uniquement)
    ALLOWED_ORIGINS=      origines web autorisées à lire l'API (CORS), séparées par des virgules ; vide = aucune
    ESP32CAM_PASSWORD=    mot de passe de la caméra (CAM_PASSWORD de son secrets.h), utilisé par camera.py

Le jeton est accepté en « Authorization: Bearer <jeton> » (backend, service vision) ou en authentification
Basic, identifiant quelconque et jeton comme mot de passe (navigateur sur /live, lecteurs MJPEG de /camera/stream).
Middleware ASGI : il couvre aussi le WebSocket /ws/pir, que @app.middleware("http") laisserait passer.
"""
import base64
import binascii
import hmac
import json
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

TOKEN = os.environ.get("API_TOKEN", "")
ALLOW_SIMULATION = os.environ.get("ALLOW_SIMULATION", "0") == "1"
ORIGINS = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
PUBLIC = frozenset({"/health"})  # supervision : ne révèle rien

log = logging.getLogger("security")


def token_from(authorization: str) -> str:
    """Jeton d'un en-tête Authorization (Bearer, ou Basic avec le jeton comme mot de passe)."""
    scheme, _, value = authorization.strip().partition(" ")
    if scheme.lower() == "bearer":
        return value.strip()
    if scheme.lower() == "basic":
        try:
            return base64.b64decode(value.strip(), validate=True).decode().partition(":")[2]
        except (binascii.Error, UnicodeDecodeError):
            return ""
    return ""


def authorized(authorization: str, token: str = TOKEN) -> bool:
    if not token:
        return True
    return hmac.compare_digest(token_from(authorization).encode(), token.encode())


def is_simulation(path: str) -> bool:
    return "/simulate" in path


class Guard:
    def __init__(self, app, token: str = TOKEN, allow_simulation: bool = ALLOW_SIMULATION) -> None:
        self.app, self.token, self.allow_simulation = app, token, allow_simulation

    async def __call__(self, scope, receive, send):
        if scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        path = scope.get("path", "")
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        if is_simulation(path) and not self.allow_simulation:
            return await _deny(scope, receive, send, 403, "simulation désactivée (ALLOW_SIMULATION=1 pour un essai)")
        if path not in PUBLIC and not authorized(headers.get("authorization", ""), self.token):
            return await _deny(scope, receive, send, 401, "jeton manquant ou invalide")
        return await self.app(scope, receive, send)


async def _deny(scope, receive, send, status: int, detail: str) -> None:
    client = (scope.get("client") or ("?", 0))[0]
    log.warning("Refusé (%d) : %s %s depuis %s", status, scope.get("method", "WS"), scope.get("path"), client)
    if scope["type"] == "websocket":
        await receive()  # websocket.connect
        await send({"type": "websocket.close", "code": 4401 if status == 401 else 4403})
        return
    body = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    if status == 401:
        headers.append((b"www-authenticate", b'Basic realm="sentinel-x"'))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


def install(app: FastAPI) -> None:
    # Ordre : le dernier ajouté est le plus extérieur. CORS doit répondre aux pré-requêtes (OPTIONS, sans jeton).
    app.add_middleware(Guard)
    if ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=ORIGINS, allow_methods=["GET", "POST"],
                           allow_headers=["Authorization", "Content-Type"])
    if not TOKEN:
        log.warning("API_TOKEN vide : API ouverte à tout le réseau (déconseillé)")
    if ALLOW_SIMULATION:
        log.warning("ALLOW_SIMULATION=1 : badges et porte simulables, à réserver aux essais")
