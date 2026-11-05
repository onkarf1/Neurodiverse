import logging
import uuid
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import PasswordWorker, PasswordWorkerBusy, password_needs_rehash
from app.models import User
from app.repositories.users import get_user_by_email, set_password_hash

logger = logging.getLogger(__name__)

FailureReason = Literal["unknown_email", "wrong_password", "disabled_account"]


class AuthenticationFailed(Exception):
    """Login failed. The reason is for logs only; callers must show one generic message."""

    def __init__(self, reason: FailureReason) -> None:
        super().__init__(reason)
        self.reason = reason


async def authenticate(
    session: AsyncSession, passwords: PasswordWorker, email: str, password: str
) -> User:
    user = await get_user_by_email(session, email.strip())
    # End the lookup transaction before the slow password check, so this login doesn't hold
    # a pooled database connection while it waits; other requests would otherwise starve.
    await session.commit()
    if user is not None:
        # Detached, so a later rollback can't expire the fields this function still reads.
        session.expunge(user)

    if user is None:
        await passwords.verify_against_dummy(password)
        _log_failure("unknown_email")
        raise AuthenticationFailed("unknown_email")

    # The password is checked before the account status, so a disabled account takes
    # the same time and gets the same answer as a wrong password.
    if not await passwords.verify(password, user.password_hash):
        _log_failure("wrong_password", user)
        raise AuthenticationFailed("wrong_password")
    if not user.is_active:
        _log_failure("disabled_account", user)
        raise AuthenticationFailed("disabled_account")

    if password_needs_rehash(user.password_hash):
        await _upgrade_password_hash(session, passwords, user.id, password)

    logger.info("Login succeeded", extra={"user_id": str(user.id)})
    return user


async def _upgrade_password_hash(
    session: AsyncSession, passwords: PasswordWorker, user_id: uuid.UUID, password: str
) -> None:
    """Best effort: the password is already verified, so a failure here must not block the
    login. The upgrade is simply retried at the next login."""
    try:
        new_hash = await passwords.hash(password)  # computed before taking a connection
        await set_password_hash(session, user_id, new_hash)
        await session.commit()
    except (SQLAlchemyError, OSError, PasswordWorkerBusy) as exc:
        await session.rollback()
        logger.warning(
            "Password hash upgrade failed",
            extra={"user_id": str(user_id), "error_type": type(exc).__name__},
        )


def _log_failure(reason: FailureReason, user: User | None = None) -> None:
    extra = {"reason": reason, "user_id": str(user.id) if user else None}
    logger.warning("Login failed", extra=extra)
