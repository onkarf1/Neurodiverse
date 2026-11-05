"""Fixtures for tests that need a real Postgres database.

Tests run against TEST_DATABASE_URL (default: the docker compose Postgres). The database
name must end in "_test" so a dev or production database can never be wiped by accident.
"""

import asyncio
import os
from collections.abc import Mapping

import pytest
from sqlalchemy import make_url, pool, text
from sqlalchemy.ext.asyncio import create_async_engine

DEFAULT_TEST_DATABASE_URL = "postgresql+asyncpg://goalfit:goalfit@localhost:5432/goalfit_test"
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
