import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..config import config
from ..db import SessionLocal
from ..deps import SESSION_COOKIE, lookup_session
from ..hub import WS_UNAUTHORIZED, Client, hub
from ..live import live
from ..schemas import dump
from ..security import hash_token

router = APIRouter()

WS_FORBIDDEN = 4403


@router.websocket("/ws/live")
async def live_socket(ws: WebSocket) -> None:
    # On accepte avant de vérifier : c'est le seul moyen d'envoyer un code de fermeture (4401) au navigateur.
    await ws.accept()
    origin = (ws.headers.get("origin") or "").rstrip("/")
    if origin not in config.origins:  # protection contre le détournement de WebSocket inter-sites
        await ws.close(WS_FORBIDDEN)
        return
    token = ws.cookies.get(SESSION_COOKIE)
    async with SessionLocal() as db:
        found = await lookup_session(db, token)
    if not found or found[1].must_change_password or not token:
        await ws.close(WS_UNAUTHORIZED)
        return
    session, user = found

    client = Client(ws=ws, user_id=user.id, token_hash=hash_token(token), role=user.role,
                    expires_at=session.expires_at)
    hub.add(client)
    client.queue.put_nowait({"type": "state", "data": dump(live.snapshot())})

    async def sender() -> None:
        while (msg := await client.queue.get()) is not None:
            await ws.send_json(msg)
        await ws.close(client.close_code)

    async def receiver() -> None:
        # Le dashboard n'envoie rien : on lit seulement pour détecter la déconnexion.
        with contextlib.suppress(WebSocketDisconnect):
            while True:
                await ws.receive_text()

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        hub.remove(client)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
