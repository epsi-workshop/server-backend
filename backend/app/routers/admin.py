"""Administration : comptes, badges, équipe (reconnaissance faciale), paramètres de détection."""
import base64
import binascii
import re
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import delete, select

from ..convert import to_badge, to_member, to_user
from ..db import BadgeRow, SessionRow, SettingsRow, TeamMemberRow, UserRow, apply_retention
from ..deps import Admin, Db, client_ip
from ..faces import EnrollError, enroll, write_gallery
from ..hub import hub
from ..journal import write_audit, write_log
from ..live import live
from ..schemas import (
    Badge, BadgeCreate, BadgePatch, PasswordResetIn, Settings, TeamMember, TeamMemberCreate, TeamMemberPatch,
    User, UserCreate, UserPatch, dump,
)
from ..security import check_password_policy, hash_password
from ..util import clean

router = APIRouter(prefix="/api", tags=["administration"])

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")
BADGE_UID_RE = re.compile(r"^([0-9A-F]{2}:){3,6}[0-9A-F]{2}$")


# ---------------------------------------------------------------- comptes
async def _get_user(db: Db, user_id: uuid.UUID) -> UserRow:
    user = await db.get(UserRow, user_id)
    if user is None:
        raise HTTPException(404, "Utilisateur introuvable.")
    return user


@router.get("/users")
async def list_users(_: Admin, db: Db) -> list[User]:
    return [to_user(u) for u in (await db.execute(select(UserRow).order_by(UserRow.username))).scalars()]


@router.post("/users")
async def create_user(body: UserCreate, request: Request, admin: Admin, db: Db) -> User:
    if not USERNAME_RE.fullmatch(body.username):
        raise HTTPException(422, "Identifiant : 3 à 32 caractères parmi a-z, 0-9, . _ -")
    check_password_policy(body.password)
    if (await db.execute(select(UserRow.id).where(UserRow.username == body.username))).first():
        raise HTTPException(409, "Cet identifiant existe déjà.")
    user = UserRow(username=body.username, role=body.role, active=True, must_change_password=True,
                   password_hash=await run_in_threadpool(hash_password, body.password))
    db.add(user)
    await db.commit()
    await write_audit(admin.username, f"Utilisateur créé : {user.username} ({user.role})", client_ip(request))
    return to_user(user)


@router.patch("/users/{user_id}")
async def update_user(user_id: uuid.UUID, body: UserPatch, request: Request, admin: Admin, db: Db) -> User:
    user = await _get_user(db, user_id)
    if user.id == admin.id and ((body.role and body.role != "admin") or body.active is False):
        raise HTTPException(409, "Vous ne pouvez pas retirer vos propres droits d'administration.")
    changes = []
    if body.role is not None and body.role != user.role:
        user.role = body.role
        changes.append(f"rôle {body.role}")
    if body.active is not None and body.active != user.active:
        user.active = body.active
        changes.append("activé" if body.active else "désactivé")
        if not body.active:
            await db.execute(delete(SessionRow).where(SessionRow.user_id == user.id))
    await db.commit()
    if changes:
        # Le WebSocket garde le rôle de l'ouverture : on le ferme pour qu'il se rouvre avec les nouveaux droits.
        hub.drop_user(user.id)
        await write_audit(admin.username, f"Utilisateur modifié : {user.username} ({', '.join(changes)})",
                          client_ip(request))
    return to_user(user)


@router.post("/users/{user_id}/password", status_code=204)
async def reset_password(user_id: uuid.UUID, body: PasswordResetIn, request: Request, admin: Admin, db: Db) -> None:
    user = await _get_user(db, user_id)
    check_password_policy(body.password)
    user.password_hash = await run_in_threadpool(hash_password, body.password)
    user.must_change_password = True
    await db.execute(delete(SessionRow).where(SessionRow.user_id == user.id))
    await db.commit()
    hub.drop_user(user.id)
    await write_audit(admin.username, f"Mot de passe réinitialisé : {user.username}", client_ip(request))


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(user_id: uuid.UUID, request: Request, admin: Admin, db: Db) -> None:
    user = await _get_user(db, user_id)
    if user.id == admin.id:
        raise HTTPException(409, "Vous ne pouvez pas supprimer votre propre compte.")
    await db.delete(user)
    await db.commit()
    hub.drop_user(user.id)
    await write_audit(admin.username, f"Utilisateur supprimé : {user.username}", client_ip(request))


# ---------------------------------------------------------------- badges
async def _get_badge(db: Db, badge_id: uuid.UUID) -> BadgeRow:
    badge = await db.get(BadgeRow, badge_id)
    if badge is None:
        raise HTTPException(404, "Badge introuvable.")
    return badge


@router.get("/badges")
async def list_badges(_: Admin, db: Db) -> list[Badge]:
    return [to_badge(b) for b in (await db.execute(select(BadgeRow).order_by(BadgeRow.owner))).scalars()]


@router.post("/badges")
async def create_badge(body: BadgeCreate, request: Request, admin: Admin, db: Db) -> Badge:
    uid = body.uid.strip().upper()
    if not BADGE_UID_RE.fullmatch(uid):
        raise HTTPException(422, "UID attendu au format 04:A3:1F:6B.")
    if (await db.execute(select(BadgeRow.id).where(BadgeRow.uid == uid))).first():
        raise HTTPException(409, "Ce badge est déjà enregistré.")
    badge = BadgeRow(uid=uid, owner=clean(body.owner, 64) or "Sans titulaire", active=True)
    db.add(badge)
    await db.commit()
    await write_audit(admin.username, f"Badge ajouté : {badge.uid} ({badge.owner})", client_ip(request))
    return to_badge(badge)


@router.patch("/badges/{badge_id}")
async def update_badge(badge_id: uuid.UUID, body: BadgePatch, request: Request, admin: Admin, db: Db) -> Badge:
    badge = await _get_badge(db, badge_id)
    changes = []
    if body.owner is not None and clean(body.owner, 64) and clean(body.owner, 64) != badge.owner:
        badge.owner = clean(body.owner, 64)
        changes.append(f"titulaire {badge.owner}")
    if body.active is not None and body.active != badge.active:
        badge.active = body.active
        changes.append("activé" if body.active else "désactivé")
    await db.commit()
    if changes:
        await write_audit(admin.username, f"Badge modifié : {badge.uid} ({', '.join(changes)})", client_ip(request))
    return to_badge(badge)


@router.delete("/badges/{badge_id}", status_code=204)
async def delete_badge(badge_id: uuid.UUID, request: Request, admin: Admin, db: Db) -> None:
    badge = await _get_badge(db, badge_id)
    await db.delete(badge)
    await db.commit()
    await write_audit(admin.username, f"Badge supprimé : {badge.uid}", client_ip(request))


# ---------------------------------------------------------------- équipe (reconnaissance faciale)
async def sync_gallery(db: Db) -> None:
    """Réécrit la galerie du service vision : empreintes des membres actifs uniquement."""
    rows = (await db.execute(select(TeamMemberRow).where(TeamMemberRow.active))).scalars()
    members = [{"id": str(m.id), "name": m.name, "embedding": m.embedding} for m in rows]
    await run_in_threadpool(write_gallery, members)


async def _get_member(db: Db, member_id: uuid.UUID) -> TeamMemberRow:
    member = await db.get(TeamMemberRow, member_id)
    if member is None:
        raise HTTPException(404, "Membre introuvable.")
    return member


def _decode_photo(data: str) -> bytes:
    if data.startswith("data:"):
        data = data.partition(",")[2]
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Photo invalide : image encodée en base64 attendue.") from None


@router.get("/team")
async def list_team(_: Admin, db: Db) -> list[TeamMember]:
    return [to_member(m) for m in (await db.execute(select(TeamMemberRow).order_by(TeamMemberRow.name))).scalars()]


@router.post("/team")
async def create_member(body: TeamMemberCreate, request: Request, admin: Admin, db: Db) -> TeamMember:
    name = clean(body.name, 32)
    if not name:
        raise HTTPException(422, "Prénom requis.")
    try:
        face = await run_in_threadpool(enroll, _decode_photo(body.photo))
    except EnrollError as e:
        raise HTTPException(422, str(e)) from None
    member = TeamMemberRow(name=name, embedding=face.embedding, photo=face.thumbnail, active=True)
    db.add(member)
    await db.commit()
    await sync_gallery(db)
    await write_audit(admin.username, f"Membre de l'équipe ajouté : {member.name}", client_ip(request))
    return to_member(member)


@router.patch("/team/{member_id}")
async def update_member(member_id: uuid.UUID, body: TeamMemberPatch, request: Request, admin: Admin,
                        db: Db) -> TeamMember:
    member = await _get_member(db, member_id)
    changes = []
    if body.name is not None and clean(body.name, 32) and clean(body.name, 32) != member.name:
        member.name = clean(body.name, 32)
        changes.append(f"prénom {member.name}")
    if body.active is not None and body.active != member.active:
        member.active = body.active
        changes.append("activé" if body.active else "désactivé")
    await db.commit()
    if changes:
        await sync_gallery(db)
        await write_audit(admin.username, f"Membre modifié : {member.name} ({', '.join(changes)})",
                          client_ip(request))
    return to_member(member)


@router.delete("/team/{member_id}", status_code=204)
async def delete_member(member_id: uuid.UUID, request: Request, admin: Admin, db: Db) -> None:
    member = await _get_member(db, member_id)
    await db.delete(member)
    await db.commit()
    await sync_gallery(db)
    await write_audit(admin.username, f"Membre de l'équipe supprimé : {member.name}", client_ip(request))


# ---------------------------------------------------------------- paramètres
@router.get("/settings")
async def get_settings(_: Admin) -> Settings:
    return live.settings


@router.put("/settings")
async def save_settings(body: Settings, request: Request, admin: Admin, db: Db) -> Settings:
    if body.thresholds.alerte >= body.thresholds.critique:
        raise HTTPException(422, "Le seuil Alerte doit être inférieur au seuil Critique.")
    body.occupancy.days = sorted(set(body.occupancy.days))
    row = await db.get(SettingsRow, 1)
    if row is None:
        db.add(SettingsRow(id=1, data=dump(body)))
    else:
        row.data = dump(body)
    await db.commit()

    retention_changed = body.retention_days != live.settings.retention_days
    live.settings = body
    if retention_changed:
        await apply_retention(body.retention_days)
    await write_audit(admin.username, f"Paramètres de détection modifiés (alerte {body.thresholds.alerte}, "
                                      f"critique {body.thresholds.critique})", client_ip(request))
    await write_log("info", "admin", f"Paramètres de détection modifiés par {admin.username}")
    return body
