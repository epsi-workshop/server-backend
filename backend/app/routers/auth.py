from datetime import timedelta

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select

from ..config import config
from ..convert import to_user
from ..db import SessionRow, UserRow
from ..deps import (
    SESSION_COOKIE, Db, PendingUser, clear_session_cookie, client_ip, lookup_session, set_session_cookie,
)
from ..hub import hub
from ..journal import write_audit, write_log
from ..schemas import LoginIn, PasswordChangeIn, User
from ..security import (
    LoginLimiter, check_password_policy, hash_password, hash_token, needs_rehash, new_token, verify_password,
)
from ..util import clean, utcnow

router = APIRouter(prefix="/api/auth", tags=["authentification"])
limiter = LoginLimiter()


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: Db) -> User:
    ip = client_ip(request)
    username = clean(body.username, 64) or "(vide)"
    if limiter.blocked(ip, username):
        await write_audit(username, "Connexion refusée : trop de tentatives", ip, success=False)
        raise HTTPException(429, "Trop de tentatives de connexion. Réessayez dans 15 minutes.")

    user = (await db.execute(select(UserRow).where(UserRow.username == username))).scalar_one_or_none()
    ok = await run_in_threadpool(verify_password, user.password_hash if user else None, body.password)
    if not ok or user is None or not user.active:
        limiter.failure(ip, username)
        await write_audit(username, "Connexion", ip, success=False)
        await write_log("warn", "auth", f"Échec de connexion : {username}")
        raise HTTPException(401, "Identifiant ou mot de passe incorrect.")

    limiter.success(ip, username)
    if needs_rehash(user.password_hash):
        user.password_hash = await run_in_threadpool(hash_password, body.password)
    now = utcnow()
    user.last_login = now
    token = new_token()
    await db.execute(delete(SessionRow).where(SessionRow.user_id == user.id, SessionRow.expires_at <= now))
    db.add(SessionRow(token_hash=hash_token(token), user_id=user.id, ip=ip,
                      expires_at=now + timedelta(hours=config.session_ttl_hours)))
    await db.commit()

    set_session_cookie(response, token)
    await write_audit(user.username, "Connexion", ip)
    await write_log("info", "auth", f"Connexion réussie : {user.username}")
    return to_user(user)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: Db) -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        found = await lookup_session(db, token)
        await db.execute(delete(SessionRow).where(SessionRow.token_hash == hash_token(token)))
        await db.commit()
        hub.drop_session(hash_token(token))
        if found:
            await write_audit(found[1].username, "Déconnexion", client_ip(request))
    clear_session_cookie(response)


@router.get("/me")
async def me(user: PendingUser) -> User:
    return to_user(user)


@router.post("/password")
async def change_password(body: PasswordChangeIn, request: Request, user: PendingUser, db: Db) -> User:
    ip = client_ip(request)
    if not await run_in_threadpool(verify_password, user.password_hash, body.current):
        await write_audit(user.username, "Changement de mot de passe personnel", ip, success=False)
        raise HTTPException(403, "Mot de passe actuel incorrect.")
    check_password_policy(body.password)
    if body.password == body.current:
        raise HTTPException(422, "Le nouveau mot de passe doit être différent de l'actuel.")

    user.password_hash = await run_in_threadpool(hash_password, body.password)
    user.must_change_password = False
    # Les autres sessions de ce compte sont fermées, la session courante est conservée.
    current = hash_token(request.cookies.get(SESSION_COOKIE, ""))
    await db.execute(delete(SessionRow).where(SessionRow.user_id == user.id, SessionRow.token_hash != current))
    await db.commit()
    hub.drop_user(user.id, keep_token_hash=current)
    await write_audit(user.username, "Mot de passe personnel modifié", ip)
    return to_user(user)
