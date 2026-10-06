"""Administration en ligne de commande.

    python -m app.cli create-admin admin
    python -m app.cli reset-password admin
    echo "mot de passe" | python -m app.cli create-admin admin --password-stdin
"""
import argparse
import asyncio
import getpass
import sys

from sqlalchemy import delete, select

from .db import SessionLocal, SessionRow, UserRow, engine, init_db
from .routers.admin import USERNAME_RE
from .security import PASSWORD_MAX, PASSWORD_MIN, hash_password


def read_password(from_stdin: bool) -> str:
    if from_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("Mot de passe : ")
        if getpass.getpass("Confirmation : ") != password:
            sys.exit("Les deux mots de passe ne correspondent pas.")
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX:
        sys.exit(f"Mot de passe : {PASSWORD_MIN} à {PASSWORD_MAX} caractères.")
    return password


async def create_admin(username: str, password: str) -> None:
    await init_db()
    async with SessionLocal() as db:
        if (await db.execute(select(UserRow.id).where(UserRow.username == username))).first():
            sys.exit(f"Le compte « {username} » existe déjà (utiliser reset-password).")
        db.add(UserRow(username=username, role="admin", active=True, must_change_password=False,
                       password_hash=hash_password(password)))
        await db.commit()
    await engine.dispose()
    print(f"Compte administrateur « {username} » créé.")


async def reset_password(username: str, password: str) -> None:
    await init_db()
    async with SessionLocal() as db:
        user = (await db.execute(select(UserRow).where(UserRow.username == username))).scalar_one_or_none()
        if user is None:
            sys.exit(f"Compte « {username} » introuvable.")
        user.password_hash = hash_password(password)
        user.active = True
        user.must_change_password = False
        await db.execute(delete(SessionRow).where(SessionRow.user_id == user.id))
        await db.commit()
    await engine.dispose()
    print(f"Mot de passe de « {username} » réinitialisé, sessions fermées.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("create-admin", "reset-password"):
        p = sub.add_parser(name)
        p.add_argument("username")
        p.add_argument("--password-stdin", action="store_true", help="lire le mot de passe sur l'entrée standard")
    args = parser.parse_args()

    if not USERNAME_RE.fullmatch(args.username):
        sys.exit("Identifiant : 3 à 32 caractères parmi a-z, 0-9, . _ -")
    password = read_password(args.password_stdin)
    action = create_admin if args.command == "create-admin" else reset_password
    asyncio.run(action(args.username, password))


if __name__ == "__main__":
    main()
