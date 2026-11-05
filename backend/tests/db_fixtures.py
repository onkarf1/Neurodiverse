"""Fixtures for tests that need a real Postgres database.

Tests run against TEST_DATABASE_URL (default: the docker compose Postgres). The database
name must end in "_test" so a dev or production database can never be wiped by accident.
"""

import asyncio
import os
from collections.abc import AsyncIterator, Mapping
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import make_url, pool, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://goalfit:goalfit@localhost:5432/goalfit_test"
ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"
_TRUE_VALUES = {"1", "true", "yes"}


def database_tests_required(environ: Mapping[str, str] = os.environ) -> bool:
    """True when a missing database should fail the run (CI) rather than skip tests.

    Only explicit true values count, so CI=false or CI=0 still skips.
    """
    return any(
        environ.get(name, "").strip().lower() in _TRUE_VALUES for name in ("CI", "REQUIRE_DB_TESTS")
    )


async def _can_connect(url: str) -> bool:
    engine = create_async_engine(url, poolclass=pool.NullPool)
    try:
        async with asyncio.timeout(3), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        return False
    finally:
        await engine.dispose()
    return True


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
    database = make_url(url).database or ""
    if not database.endswith("_test"):
        pytest.fail(f"Refusing to run tests against '{database}': name must end in '_test'.")
    if not asyncio.run(_can_connect(url)):
        message = "Postgres test database unreachable. Run: docker compose up -d postgres"
        # In CI a missing database is a failure, not a silent skip.
        if database_tests_required():
            pytest.fail(message)
        pytest.skip(message)
    return url


@pytest.fixture(scope="session")
def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["configure_logging"] = False
    return config


@pytest.fixture(scope="session")
def migrated_database_url(database_url: str, alembic_config: Config) -> str:
    command.upgrade(alembic_config, "head")
    return database_url


@pytest.fixture
async def db_session(migrated_database_url: str) -> AsyncIterator[AsyncSession]:
    """A session inside a transaction that is rolled back after each test."""
    engine = create_async_engine(migrated_database_url, poolclass=pool.NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()
