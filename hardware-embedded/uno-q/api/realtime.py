"""Diffusion temps réel des événements PIR par WebSocket.

Une tâche de fond interroge le MCU toutes les 100 ms via le Bridge et
pousse un message à tous les clients connectés dès que l'état change.
"""
import asyncio
import contextlib
import time

from fastapi import WebSocket, WebSocketDisconnect

from bridge import read_int

POLL_INTERVAL_S = 0.1
HEARTBEAT_S = 15


class PirBroadcaster:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.state = None
        self.detections = None
        self.last_motion_ts = None
        self._task = None

    def snapshot(self, event="state"):
        return {
            "type": "pir",
            "event": event,
            "motion": self.state,
            "detections": self.detections,
            "last_motion_ts": self.last_motion_ts,
            "ts": time.time(),
        }

    async def start(self):
        self._task = asyncio.create_task(self._poll())

    async def stop(self):
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _poll(self):
        last_heartbeat = time.monotonic()
        while True:
            raw = await asyncio.to_thread(read_int, "get_pir")
            count = await asyncio.to_thread(read_int, "get_pir_count")
            if raw is not None:
                state = bool(raw)
                if state != self.state and self.state is not None:
                    if state:
                        self.last_motion_ts = time.time()
                    self.state, self.detections = state, count
                    await self.broadcast(self.snapshot("motion_start" if state else "motion_end"))
                    last_heartbeat = time.monotonic()
                else:
                    self.state, self.detections = state, count
            if time.monotonic() - last_heartbeat >= HEARTBEAT_S:
                await self.broadcast(self.snapshot("heartbeat"))
                last_heartbeat = time.monotonic()
            await asyncio.sleep(POLL_INTERVAL_S)

    async def broadcast(self, message):
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def handle(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)
        try:
            await ws.send_json(self.snapshot("state"))
            while True:
                await ws.receive_text()  # on ignore les messages entrants
        except WebSocketDisconnect:
            pass
        finally:
            self.clients.discard(ws)


pir_broadcaster = PirBroadcaster()
