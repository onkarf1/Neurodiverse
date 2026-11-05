"""Database failures triggered for real against Postgres, not raised by hand: the driver's
actual exception types are what decide between 503 (temporary) and 500 (bug or config)."""

import logging
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import make_url, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep
from app.core.constants import PROBLEM_JSON
from app.main import create_app
from tests.auth_fixtures import run_in_database
from tests.helpers import make_settings

LIMITED_ROLE = "goalfit_test_no_connections"
QUERIES = {
    "dropped connection": "SELECT pg_terminate_backend(pg_backend_pid())",
    "statement timeout": "SELECT pg_sleep(1)",
    "missing table": "SELECT * FROM no_such_table",
    "division by zero": "SELECT 1 / 0",
}


def _app_with_query_route(**settings: Any) -> FastAPI:
    app = create_app(make_settings(db_statement_timeout_ms=200, **settings))

    @app.get("/v1/test-query/{name}")
    async def run_query(name: str, session: SessionDep) -> None:
        await session.execute(text(QUERIES[name]))

    return app


def _login(app: FastAPI, caplog: pytest.LogCaptureFixture) -> tuple[int, str, bool]:
    # create_app replaces the root log handlers, so reattach pytest's capture handler.
    logging.getLogger().addHandler(caplog.handler)
    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.post("/v1/auth/login", json={"email": "a@example.com", "password": "x"})
    logged_error = any(r.levelno >= logging.ERROR for r in caplog.records)
    return response.status_code, response.headers.get("Retry-After", ""), logged_error


def _query(app: FastAPI, name: str, caplog: pytest.LogCaptureFixture) -> tuple[int, str, bool]:
    logging.getLogger().addHandler(caplog.handler)
    caplog.set_level(logging.WARNING)
    with TestClient(app) as client:
        response = client.get(f"/v1/test-query/{name}")
    logged_error = any(r.levelno >= logging.ERROR for r in caplog.records)
    if response.status_code == 503:
        assert response.headers["content-type"] == PROBLEM_JSON
    return response.status_code, response.headers.get("Retry-After", ""), logged_error


@pytest.fixture
def role_without_connections(migrated_database_url: str) -> Iterator[str]:
    """A login role allowed zero connections, so connecting fails with "too many connections"."""

    async def create(session: AsyncSession) -> None:
        await session.execute(text(f"DROP ROLE IF EXISTS {LIMITED_ROLE}"))
        await session.execute(
            text(f"CREATE ROLE {LIMITED_ROLE} LOGIN PASSWORD 'unused' CONNECTION LIMIT 0")
        )

    async def drop(session: AsyncSession) -> None:
        await session.execute(text(f"DROP ROLE IF EXISTS {LIMITED_ROLE}"))

    run_in_database(migrated_database_url, create)
    url = make_url(migrated_database_url).set(username=LIMITED_ROLE, password="unused")
    yield url.render_as_string(hide_password=False)
    run_in_database(migrated_database_url, drop)


# Temporary outages: 503 with Retry-After, and only a warning in the logs.


def test_refused_connection_via_localhost_answers_503(caplog: pytest.LogCaptureFixture) -> None:
    # "localhost" resolves to two addresses, so the driver raises a plain OSError.
    app = create_app(
        make_settings(database_url="postgresql+asyncpg://u:p@localhost:1/goalfit_test")
    )

    assert _login(app, caplog) == (503, "5", False)


def test_too_many_connections_answers_503(
    role_without_connections: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(make_settings(database_url=role_without_connections))

    assert _login(app, caplog) == (503, "5", False)


def test_dropped_connection_answers_503(
    migrated_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    # Same as a database restart or failover in the middle of a request.
    app = _app_with_query_route(database_url=migrated_database_url)

    assert _query(app, "dropped connection", caplog) == (503, "5", False)


# Bugs and misconfiguration: still 500 with an error log, so they get noticed.


@pytest.mark.parametrize(
    "credentials",
    [
        "goalfit:wrong-password@localhost:5432/goalfit_test",
        "goalfit:goalfit@localhost:5432/no_such_db",
    ],
    ids=["wrong password", "missing database"],
)
def test_database_misconfiguration_stays_500(
    credentials: str, caplog: pytest.LogCaptureFixture, migrated_database_url: str
) -> None:
    app = create_app(make_settings(database_url=f"postgresql+asyncpg://{credentials}"))

    assert _login(app, caplog) == (500, "", True)


@pytest.mark.parametrize("name", ["statement timeout", "missing table", "division by zero"])
def test_query_errors_stay_500(
    name: str, migrated_database_url: str, caplog: pytest.LogCaptureFixture
) -> None:
    app = _app_with_query_route(database_url=migrated_database_url)

    assert _query(app, name, caplog) == (500, "", True)


# Classification of database errors that can't safely be triggered for real in a test
# (restarting or shutting down the shared Postgres). The real failures above are the main
# evidence; these cover the remaining branches of the same decision.


class _DriverError(Exception):
    def __init__(self, sqlstate: str | None) -> None:
        super().__init__("driver error")
        self.sqlstate = sqlstate


@pytest.mark.parametrize(
    ("sqlstate", "invalidated", "expected"),
    [
        (None, True, 503),  # connection lost without a SQLSTATE
        ("08006", False, 503),  # connection failure
        ("53100", False, 503),  # disk full
        ("57P01", False, 503),  # server shutting down
        ("57P02", False, 503),  # server crashed
        ("57P03", False, 503),  # server still starting
        ("57014", False, 500),  # statement timeout: a slow query is a bug, not an outage
        ("28P01", False, 500),  # wrong password: misconfiguration
        (None, False, 500),  # unknown driver error
    ],
)
def test_database_errors_are_classified_by_sqlstate(
    app: FastAPI, client: TestClient, sqlstate: str | None, invalidated: bool, expected: int
) -> None:
    @app.get("/v1/test-driver-error")
    async def driver_error() -> None:
        raise DBAPIError("SELECT 1", {}, _DriverError(sqlstate), connection_invalidated=invalidated)

    assert client.get("/v1/test-driver-error").status_code == expected
