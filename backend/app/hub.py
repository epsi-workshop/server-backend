"""Diffusion des messages temps réel (LiveMessage) aux WebSockets connectés."""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from .util import ROLE_RANK, utcnow

WS_UNAUTHORIZED = 4401  # le dashboard renvoie alors à l'écran de connexion
WS_TOO_SLOW = 1013


@dataclass(eq=False)
class Client:
    ws: WebSocket
    user_id: uuid.UUID
    token_hash: str
    role: str
    expires_at: datetime
    queue: asyncio.Queue[dict[str, Any] | None] = field(default_factory=lambda: asyncio.Queue(maxsize=200))
    close_code: int = 1000


class Hub:
    def __init__(self) -> None:
        self.clients: set[Client] = set()

    def add(self, client: Client) -> None:
        self.clients.add(client)

    def remove(self, client: Client) -> None:
        self.clients.discard(client)

    def broadcast(self, message: dict[str, Any], min_role: str = "lecteur") -> None:
        """Non bloquant : chaque client a sa file, vidée par sa propre tâche d'envoi."""
        for c in list(self.clients):
            if ROLE_RANK[c.role] < ROLE_RANK[min_role]:
                continue
            try:
                c.queue.put_nowait(message)
            except asyncio.QueueFull:
                self.kick(c, WS_TOO_SLOW)

    def kick(self, client: Client, code: int) -> None:
        client.close_code = code
        while not client.queue.empty():
            client.queue.get_nowait()
        client.queue.put_nowait(None)
        self.clients.discard(client)

    def drop_user(self, user_id: uuid.UUID, keep_token_hash: str | None = None) -> None:
        for c in list(self.clients):
            if c.user_id == user_id and c.token_hash != keep_token_hash:
                self.kick(c, WS_UNAUTHORIZED)

    def drop_session(self, token_hash: str) -> None:
        for c in list(self.clients):
            if c.token_hash == token_hash:
                self.kick(c, WS_UNAUTHORIZED)

    def expire_sessions(self) -> None:
        now = utcnow()
        for c in list(self.clients):
            if c.expires_at <= now:
                self.kick(c, WS_UNAUTHORIZED)


hub = Hub()
