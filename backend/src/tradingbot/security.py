from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from tradingbot.config import get_settings


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _urlsafe_b64decode(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}".encode("utf-8"))


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


def _sign_payload(payload: dict[str, Any]) -> str:
    settings = get_settings()
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(settings.session_secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    return f"{_urlsafe_b64encode(payload_bytes)}.{_urlsafe_b64encode(signature)}"


def _decode_payload(token: str) -> dict[str, Any] | None:
    settings = get_settings()
    try:
        encoded_payload, encoded_signature = token.split(".", maxsplit=1)
    except ValueError:
        return None

    try:
        payload_bytes = _urlsafe_b64decode(encoded_payload)
        provided_signature = _urlsafe_b64decode(encoded_signature)
    except (ValueError, binascii.Error):
        return None

    expected_signature = hmac.new(settings.session_secret.encode("utf-8"), payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(provided_signature, expected_signature):
        return None

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError:
        return None

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    if datetime.now(UTC).timestamp() >= float(exp):
        return None
    return payload if isinstance(payload, dict) else None


def create_access_token(subject: str, *, role: str = "admin", session_id: str | None = None, expires_at: datetime | None = None) -> str:
    settings = get_settings()
    expiration = expires_at or (datetime.now(UTC) + timedelta(minutes=settings.session_expire_minutes))
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": int(expiration.timestamp())}
    if session_id:
        payload["sid"] = session_id
    return _sign_payload(payload)


def create_csrf_token(session_id: str, *, expires_at: datetime | None = None) -> str:
    settings = get_settings()
    expiration = expires_at or (datetime.now(UTC) + timedelta(minutes=settings.session_expire_minutes))
    return _sign_payload(
        {
            "kind": "csrf",
            "sid": session_id,
            "exp": int(expiration.timestamp()),
        }
    )


def decode_access_token(token: str) -> str | None:
    payload = _decode_payload(token)
    if not payload:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) else None


def decode_signed_session(token: str) -> dict[str, Any] | None:
    return _decode_payload(token)


def verify_csrf_token(token: str, *, session_id: str) -> bool:
    payload = _decode_payload(token)
    if not payload:
        return False
    kind = payload.get("kind")
    token_session_id = payload.get("sid")
    return kind == "csrf" and token_session_id == session_id
