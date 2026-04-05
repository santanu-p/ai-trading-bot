from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from tradingbot.config import get_settings


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return "scrypt${}${}".format(
        base64.urlsafe_b64encode(salt).decode("utf-8"),
        base64.urlsafe_b64encode(derived).decode("utf-8"),
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        _, encoded_salt, encoded_digest = encoded_hash.split("$", maxsplit=2)
    except ValueError:
        return False

    salt = base64.urlsafe_b64decode(encoded_salt.encode("utf-8"))
    expected = base64.urlsafe_b64decode(encoded_digest.encode("utf-8"))
    actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return hmac.compare_digest(actual, expected)


def create_access_token(subject: str) -> str:
    settings = get_settings()
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": subject, "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except JWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None

