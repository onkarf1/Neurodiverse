import asyncio
import logging

from sqlalchemy import pool, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


class DatabaseProbe:
    """Readiness check for the database.

    Uses its own short-lived connection instead of the request pool, so an instance that is
    merely busy isn't reported unhealthy. Logs the full error only when the database first
    becomes unavailable, a one-line warning while it stays down, and once when it recovers.
    """

    def __init__(self, database_url: str, timeout_seconds: float) -> None:
        self._engine = create_async_engine(
            database_url, poolclass=pool.NullPool, hide_parameters=True
        )
        self._timeout_seconds = timeout_seconds
        self._available: bool | None = None

    async def check(self) -> bool:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await self._ping()
        # TimeoutError is a subclass of OSError; it is listed only to make the intent explicit.
        except (OSError, SQLAlchemyError, TimeoutError) as exc:
            if self._available is not False:
                logger.warning("Database became unavailable", exc_info=exc)
            else:
                logger.warning(
                    "Database still unavailable", extra={"error_type": type(exc).__name__}
                )
            self._available = False
            return False

        if self._available is False:
            logger.info("Database is available again")
        self._available = True
        return True

    async def _ping(self) -> None:
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self._engine.dispose()
