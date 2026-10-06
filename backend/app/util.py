import re
from datetime import UTC, datetime

ROLE_RANK = {"lecteur": 0, "operateur": 1, "admin": 2}

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def utcnow() -> datetime:
    return datetime.now(UTC)


def iso(dt: datetime) -> str:
    """ISO 8601 UTC au format attendu par le dashboard : 2026-10-05T14:32:07.512Z."""
    return dt.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def clean(text: str, max_len: int = 200) -> str:
    """Retire les caractères de contrôle d'une saisie avant de l'écrire dans les journaux."""
    return _CONTROL.sub(" ", text).strip()[:max_len]
