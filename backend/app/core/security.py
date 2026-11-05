"""Password hashing and access tokens."""

import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache

import anyio
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings

# Argon2id with the RFC 9106 recommended settings (3 passes, 64 MiB, 4 lanes).
_hasher = PasswordHasher()

TOKEN_ALGORITHM = "HS256"  # noqa: S105  (algorithm name, not a secret)
TOKEN_LEEWAY_SECONDS = 10
_TOKEN_USE = "access"  # noqa: S105  (claim value, not a secret)
# PyJWT already requires "iss" and "aud" because we pass an issuer and audience;
# they are listed too so the full set of required claims is visible in one place.
_REQUIRED_CLAIMS = ["sub", "iss", "aud", "iat", "nbf", "exp", "token_use"]


def _normalize(password: str) -> str:
    # NIST SP 800-63B: normalize so the same password typed differently still matches.
    return unicodedata.normalize("NFKC", password)


def hash_password(password: str) -> str:
    """Raises ValueError for text that can't be encoded, such as a lone surrogate."""
    try:
        return _hasher.hash(_normalize(password))
    except UnicodeError as exc:
        raise ValueError("Password contains characters that can't be encoded.") from exc


def verify_password(password: str, password_hash: str) -> bool:
    """False for any mismatch, including a damaged hash or text that can't be encoded."""
    try:
        return _hasher.verify(password_hash, _normalize(password))
    except (VerificationError, InvalidHashError, UnicodeError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@cache
def _dummy_hash() -> str:
    return hash_password("placeholder used only to make failed logins take equal time")


class PasswordWorkerBusy(Exception):
    """Too many password checks are already queued; the caller should retry shortly."""


class PasswordWorker:
    """Runs password hashing on worker threads, at most `max_concurrent` at a time, with
    at most `max_waiting` more queued behind them.

    Argon2 is deliberately slow and memory-hungry, so it must not block the event loop,
    unbounded parallel hashing could exhaust memory, and an unbounded queue would let a
    flood of login attempts make every real login wait.
    """

    def __init__(self, max_concurrent: int, max_waiting: int) -> None:
        self._max_concurrent = max_concurrent
        self._max_waiting = max_waiting
        self._limiter = anyio.CapacityLimiter(max_concurrent)
        self._max_in_flight = max_concurrent + max_waiting
        self._in_flight = 0
        _dummy_hash()  # computed now so the first unknown-email login isn't slower

    @property
    def max_concurrent(self) -> int:
        return self._max_concurrent

    @property
    def max_waiting(self) -> int:
        return self._max_waiting

    async def verify(self, password: str, password_hash: str) -> bool:
        return await self._run(lambda: verify_password(password, password_hash))

    async def verify_against_dummy(self, password: str) -> None:
        """Spends the same time as a real check, for emails that don't exist."""
        await self.verify(password, _dummy_hash())

    async def hash(self, password: str) -> str:
        return await self._run(lambda: hash_password(password))

    async def _run[T](self, work: Callable[[], T]) -> T:
        # Single event loop: no await between the check and the increment, so no race.
        if self._in_flight >= self._max_in_flight:
            raise PasswordWorkerBusy
        self._in_flight += 1
        try:
            return await anyio.to_thread.run_sync(work, limiter=self._limiter)
        finally:
            self._in_flight -= 1


class InvalidTokenError(Exception):
    """The token is missing, malformed, expired, or not one we issued."""


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_in: int


def create_access_token(
    user_id: uuid.UUID, settings: Settings, *, now: datetime | None = None
) -> AccessToken:
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.access_token_ttl_minutes)
    claims = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + lifetime,
        "token_use": _TOKEN_USE,
    }
    value = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=TOKEN_ALGORITHM)
    return AccessToken(value=value, expires_in=int(lifetime.total_seconds()))


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Returns the user ID in a valid token, or raises InvalidTokenError."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            # Only our algorithm is accepted, which blocks "alg: none" and algorithm swaps.
            algorithms=[TOKEN_ALGORITHM],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            leeway=TOKEN_LEEWAY_SECONDS,
            options={"require": _REQUIRED_CLAIMS},
        )
        if claims["token_use"] != _TOKEN_USE:
            raise InvalidTokenError
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError, TypeError) as exc:
        raise InvalidTokenError from exc
