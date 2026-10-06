from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import config
from .db import SessionRow, UserRow, get_db
from .schemas import Role
from .security import hash_token
from .util import ROLE_RANK, utcnow

SESSION_COOKIE = "sx_session"

Db = Annotated[AsyncSession, Depends(get_db)]


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "inconnue"


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, token, max_age=config.session_ttl_hours * 3600, path="/",
        httponly=True, secure=config.cookie_secure, samesite="strict",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/", httponly=True, secure=config.cookie_secure, samesite="strict")


async def lookup_session(db: AsyncSession, token: str | None) -> tuple[SessionRow, UserRow] | None:
    """Session valide (non expirée, compte actif) correspondant au jeton du cookie."""
    if not token:
        return None
    row = (await db.execute(
        select(SessionRow, UserRow)
        .join(UserRow, UserRow.id == SessionRow.user_id)
        .where(SessionRow.token_hash == hash_token(token), SessionRow.expires_at > utcnow(), UserRow.active.is_(True))
    )).first()
    return (row[0], row[1]) if row else None


async def pending_user(request: Request, db: Db) -> UserRow:
    """Utilisateur connecté, même s'il doit encore changer son mot de passe."""
    found = await lookup_session(db, request.cookies.get(SESSION_COOKIE))
    if not found:
        raise HTTPException(401, "Non authentifié.")
    return found[1]


async def current_user(user: Annotated[UserRow, Depends(pending_user)]) -> UserRow:
    if user.must_change_password:
        raise HTTPException(403, "Changement de mot de passe obligatoire avant toute autre action.")
    return user


def require(role: Role) -> Callable[[UserRow], Awaitable[UserRow]]:
    async def check(user: Annotated[UserRow, Depends(current_user)]) -> UserRow:
        if ROLE_RANK[user.role] < ROLE_RANK[role]:
            raise HTTPException(403, f"Action réservée au rôle {role}.")
        return user
    return check


PendingUser = Annotated[UserRow, Depends(pending_user)]
Lecteur = Annotated[UserRow, Depends(require("lecteur"))]
Operateur = Annotated[UserRow, Depends(require("operateur"))]
Admin = Annotated[UserRow, Depends(require("admin"))]
