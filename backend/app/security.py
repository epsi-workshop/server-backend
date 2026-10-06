import hashlib
import secrets
import time
from collections import defaultdict, deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import HTTPException

PASSWORD_MIN = 12
PASSWORD_MAX = 128

_ph = PasswordHasher()  # Argon2id, paramètres par défaut d'argon2-cffi (RFC 9106)
# Vérifié quand l'identifiant n'existe pas : même durée de réponse, pas d'énumération des comptes.
_DUMMY_HASH = _ph.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _ph.check_needs_rehash(password_hash)


def check_password_policy(password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise HTTPException(422, f"Mot de passe : {PASSWORD_MIN} caractères minimum.")
    if len(password) > PASSWORD_MAX:
        raise HTTPException(422, f"Mot de passe : {PASSWORD_MAX} caractères maximum.")


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class LoginLimiter:
    """Limitation des tentatives de connexion, en mémoire (un seul processus backend).

    Deux compteurs sur une fenêtre glissante : par couple (IP, identifiant) pour freiner
    le bruteforce d'un compte, et par IP pour freiner le password spraying.
    """

    def __init__(self, max_per_account: int = 5, max_per_ip: int = 20, window_s: float = 900) -> None:
        self.max_per_account = max_per_account
        self.max_per_ip = max_per_ip
        self.window_s = window_s
        self._fails: dict[str, deque[float]] = defaultdict(deque)

    def _count(self, key: str, now: float) -> int:
        q = self._fails.get(key)
        if q is None:
            return 0
        while q and now - q[0] > self.window_s:
            q.popleft()
        if not q:
            del self._fails[key]
            return 0
        return len(q)

    def blocked(self, ip: str, username: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        return (self._count(f"{ip}|{username}", now) >= self.max_per_account
                or self._count(ip, now) >= self.max_per_ip)

    def failure(self, ip: str, username: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        self._fails[f"{ip}|{username}"].append(now)
        self._fails[ip].append(now)

    def success(self, ip: str, username: str) -> None:
        self._fails.pop(f"{ip}|{username}", None)
