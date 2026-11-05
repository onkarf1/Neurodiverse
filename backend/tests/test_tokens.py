import base64
import json
import uuid
import warnings
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest

from app.core.security import (
    TOKEN_LEEWAY_SECONDS,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
)
from tests.helpers import TEST_SECRET, make_settings

SETTINGS = make_settings()
USER_ID = uuid.uuid4()


def _claims(**overrides: Any) -> dict[str, Any]:
    now = datetime.now(UTC)
    claims: dict[str, Any] = {
        "sub": str(USER_ID),
        "iss": SETTINGS.jwt_issuer,
        "aud": SETTINGS.jwt_audience,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=5),
        "token_use": "access",
    }
    claims.update(overrides)
    return {key: value for key, value in claims.items() if value is not None}


def _sign(claims: dict[str, Any], key: str = TEST_SECRET, algorithm: str = "HS256") -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


def _signed_with_hs512(claims: dict[str, Any]) -> str:
    # PyJWT warns that this key is short for HS512; the token only needs to be rejected.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _sign(claims, algorithm="HS512")


def _unsigned(claims: dict[str, Any]) -> str:
    def part(data: dict[str, Any]) -> str:
        raw = json.dumps(data, default=lambda d: int(d.timestamp())).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part({'alg': 'none', 'typ': 'JWT'})}.{part(claims)}."


def test_token_round_trip_identifies_the_user() -> None:
    token = create_access_token(USER_ID, SETTINGS)

    assert decode_access_token(token.value, SETTINGS) == USER_ID
    assert token.expires_in == SETTINGS.access_token_ttl_minutes * 60


def test_token_is_valid_until_it_expires() -> None:
    issued = datetime.now(UTC) - timedelta(minutes=SETTINGS.access_token_ttl_minutes - 1)

    token = create_access_token(USER_ID, SETTINGS, now=issued)

    assert decode_access_token(token.value, SETTINGS) == USER_ID


def test_token_is_rejected_after_it_expires() -> None:
    issued = datetime.now(UTC) - timedelta(
        minutes=SETTINGS.access_token_ttl_minutes, seconds=TOKEN_LEEWAY_SECONDS + 1
    )

    token = create_access_token(USER_ID, SETTINGS, now=issued)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token.value, SETTINGS)


def test_token_expired_a_minute_ago_is_rejected() -> None:
    # Guards against widening the clock-skew allowance far beyond a few seconds.
    expired = _sign(_claims(exp=datetime.now(UTC) - timedelta(minutes=1)))

    with pytest.raises(InvalidTokenError):
        decode_access_token(expired, SETTINGS)


INVALID_TOKENS = {
    "wrong signing key": _sign(_claims(), key="a-different-secret-that-is-32-chars-long"),
    "wrong issuer": _sign(_claims(iss="someone-else")),
    "wrong audience": _sign(_claims(aud="another-app")),
    "missing expiry": _sign(_claims(exp=None)),
    "missing subject": _sign(_claims(sub=None)),
    "missing issued-at": _sign(_claims(iat=None)),
    "missing not-before": _sign(_claims(nbf=None)),
    "missing issuer": _sign(_claims(iss=None)),
    "missing audience": _sign(_claims(aud=None)),
    "not valid yet": _sign(_claims(nbf=datetime.now(UTC) + timedelta(minutes=5))),
    "other token type": _sign(_claims(token_use="refresh")),
    "missing token type": _sign(_claims(token_use=None)),
    "subject is not a user id": _sign(_claims(sub="admin")),
    "different algorithm": _signed_with_hs512(_claims()),
    "unsigned (alg none)": _unsigned(_claims()),
    "garbage": "not.a.token",
    "empty": "",
}


@pytest.mark.parametrize("token", INVALID_TOKENS.values(), ids=INVALID_TOKENS.keys())
def test_invalid_tokens_are_rejected(token: str) -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, SETTINGS)
