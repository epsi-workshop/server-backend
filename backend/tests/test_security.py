import pytest
from fastapi import HTTPException

from app.security import (
    LoginLimiter, check_password_policy, hash_password, hash_token, new_token, verify_password,
)


def test_password_roundtrip() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery")
    assert not verify_password(h, "mauvais mot de passe")


def test_unknown_user_never_verifies() -> None:
    assert not verify_password(None, "n'importe quoi")


def test_corrupted_hash_is_rejected() -> None:
    assert not verify_password("pas-un-hash", "x")


def test_password_policy() -> None:
    with pytest.raises(HTTPException) as e:
        check_password_policy("trop-court")
    assert e.value.status_code == 422
    check_password_policy("douze-car-ok")


def test_session_token_is_random_and_hashed() -> None:
    a, b = new_token(), new_token()
    assert a != b and len(a) >= 40
    assert hash_token(a) != a and len(hash_token(a)) == 64


def test_limiter_blocks_account_after_max_failures() -> None:
    lim = LoginLimiter(max_per_account=3, max_per_ip=100, window_s=60)
    for t in range(3):
        assert not lim.blocked("1.2.3.4", "admin", now=t)
        lim.failure("1.2.3.4", "admin", now=t)
    assert lim.blocked("1.2.3.4", "admin", now=3)
    assert not lim.blocked("1.2.3.4", "lecteur", now=3)
    assert not lim.blocked("1.2.3.4", "admin", now=3 + 61)  # fenêtre écoulée


def test_limiter_blocks_ip_spraying() -> None:
    lim = LoginLimiter(max_per_account=100, max_per_ip=5, window_s=60)
    for i in range(5):
        lim.failure("1.2.3.4", f"user{i}", now=0)
    assert lim.blocked("1.2.3.4", "autre", now=1)
    assert not lim.blocked("5.6.7.8", "autre", now=1)


def test_limiter_success_resets_account() -> None:
    lim = LoginLimiter(max_per_account=2, max_per_ip=100, window_s=60)
    lim.failure("ip", "admin", now=0)
    lim.failure("ip", "admin", now=0)
    lim.success("ip", "admin")
    assert not lim.blocked("ip", "admin", now=1)
