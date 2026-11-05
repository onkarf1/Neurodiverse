import json
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import literal, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.constants import PROBLEM_JSON
from app.core.security import (
    PasswordWorker,
    PasswordWorkerBusy,
    create_access_token,
    password_needs_rehash,
)
from app.main import create_app
from app.services import auth as auth_service
from tests.auth_fixtures import (
    TEST_PASSWORD,
    SeedUser,
    read_password_hash,
    run_in_database,
    update_user,
)
from tests.helpers import make_settings

LOGIN = "/v1/auth/login"
ME = "/v1/auth/me"


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _login(client: TestClient, email: str, password: str = TEST_PASSWORD) -> str:
    response = client.post(LOGIN, json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return str(response.json()["access_token"])


def test_login_returns_a_token_that_identifies_the_user(
    auth_client: TestClient, seed_user: SeedUser
) -> None:
    user = seed_user()

    response = auth_client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    me = auth_client.get(ME, headers=_bearer(response.json()["access_token"]))

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"
    assert response.json()["expires_in"] == 30 * 60
    assert me.status_code == 200
    assert me.json() == {
        "id": str(user.id),
        "email": user.email,
        "role": "teacher",
        "school_id": str(user.school_id),
    }


def test_login_ignores_email_case_and_surrounding_spaces(
    auth_client: TestClient, seed_user: SeedUser
) -> None:
    seed_user("teacher@example.com")

    assert _login(auth_client, "  Teacher@Example.COM ")


def test_failed_logins_are_indistinguishable(auth_client: TestClient, seed_user: SeedUser) -> None:
    seed_user("active@example.com")
    seed_user("disabled@example.com", is_active=False)
    attempts = {
        "wrong password": ("active@example.com", "not the right password"),
        "unknown email": ("nobody@example.com", TEST_PASSWORD),
        "disabled account": ("disabled@example.com", TEST_PASSWORD),
    }

    responses = {
        name: auth_client.post(LOGIN, json={"email": email, "password": password})
        for name, (email, password) in attempts.items()
    }

    for response in responses.values():
        assert response.status_code == 401
        assert response.headers["content-type"] == PROBLEM_JSON
        assert response.headers["WWW-Authenticate"] == "Bearer"
    bodies = [{k: v for k, v in r.json().items() if k != "request_id"} for r in responses.values()]
    assert all(body == bodies[0] for body in bodies)


@pytest.mark.parametrize("email", ["nobody@example.com", "disabled@example.com"])
def test_every_failed_login_runs_one_password_check(
    auth_client: TestClient, seed_user: SeedUser, monkeypatch: pytest.MonkeyPatch, email: str
) -> None:
    # Without this, unknown emails or disabled accounts would answer faster than a wrong
    # password, revealing which accounts exist.
    seed_user("disabled@example.com", is_active=False)
    calls: list[str] = []
    real_verify = security.verify_password

    def counting_verify(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return real_verify(password, password_hash)

    monkeypatch.setattr(security, "verify_password", counting_verify)

    response = auth_client.post(LOGIN, json={"email": email, "password": TEST_PASSWORD})

    assert response.status_code == 401
    assert len(calls) == 1


def test_login_upgrades_an_outdated_password_hash(
    auth_client: TestClient, seed_user: SeedUser, clean_database: str
) -> None:
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(TEST_PASSWORD)
    user = seed_user(password_hash=weak_hash)

    _login(auth_client, user.email)

    upgraded = read_password_hash(clean_database, user.id)
    assert upgraded != weak_hash
    assert not password_needs_rehash(upgraded)


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Basic dXNlcjpwYXNz"}, {"Authorization": "Bearer not-a-token"}],
    ids=["no header", "wrong scheme", "malformed token"],
)
def test_me_requires_a_valid_token(auth_client: TestClient, headers: dict[str, str]) -> None:
    response = auth_client.get(ME, headers=headers)

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_rejects_an_expired_token(auth_client: TestClient, seed_user: SeedUser) -> None:
    user = seed_user()
    settings = auth_client.app.state.settings  # type: ignore[attr-defined]
    issued = datetime.now(UTC) - timedelta(minutes=settings.access_token_ttl_minutes + 5)
    token = create_access_token(user.id, settings, now=issued)

    assert auth_client.get(ME, headers=_bearer(token.value)).status_code == 401


def test_me_rejects_a_token_after_the_account_is_disabled(
    auth_client: TestClient, seed_user: SeedUser, clean_database: str
) -> None:
    user = seed_user()
    token = _login(auth_client, user.email)

    update_user(clean_database, user.id, is_active=False)

    assert auth_client.get(ME, headers=_bearer(token)).status_code == 401


def test_me_rejects_a_token_for_a_user_that_does_not_exist(auth_client: TestClient) -> None:
    settings = auth_client.app.state.settings  # type: ignore[attr-defined]
    token = create_access_token(uuid.uuid4(), settings)

    assert auth_client.get(ME, headers=_bearer(token.value)).status_code == 401


def test_overlong_email_is_rejected(auth_client: TestClient) -> None:
    email = "a" * 309 + "@example.com"  # 321 characters, one over the column limit

    response = auth_client.post(LOGIN, json={"email": email, "password": "x"})

    assert response.status_code == 422


def test_overlong_password_is_rejected_without_echoing_it(auth_client: TestClient) -> None:
    password = "p" * 129

    response = auth_client.post(LOGIN, json={"email": "a@example.com", "password": password})

    assert response.status_code == 422
    assert password not in response.text


def test_logins_are_logged_without_credentials(
    auth_client: TestClient, seed_user: SeedUser, caplog: pytest.LogCaptureFixture
) -> None:
    user = seed_user("logged@example.com")
    caplog.set_level(logging.INFO, logger="app.services.auth")

    _login(auth_client, user.email)
    auth_client.post(LOGIN, json={"email": user.email, "password": "wrong-password-value"})

    records = [r for r in caplog.records if r.name == "app.services.auth"]
    assert [r.getMessage() for r in records] == ["Login succeeded", "Login failed"]
    assert records[0].__dict__["user_id"] == str(user.id)
    assert records[1].__dict__["reason"] == "wrong_password"
    logged = " ".join(str(vars(r)) for r in records)
    for secret in (TEST_PASSWORD, "wrong-password-value", user.email):
        assert secret not in logged


@pytest.mark.parametrize(
    "stored, typed",
    [
        ("\u0130lker@example.com", "\u0130lker@example.com"),  # dotted capital I, typed as stored
        ("\u00c4nne@example.com", "\u00e4nne@example.com"),  # Ä stored, ä typed
    ],
    ids=["dotted capital I", "umlaut"],
)
def test_non_ascii_emails_match_like_the_unique_index(
    auth_client: TestClient, seed_user: SeedUser, stored: str, typed: str
) -> None:
    seed_user(stored)

    assert _login(auth_client, typed)


def test_password_worker_uses_the_configured_limits() -> None:
    app = create_app(make_settings(password_hash_concurrency=3, password_hash_queue_limit=7))

    worker = app.state.password_worker
    assert (worker.max_concurrent, worker.max_waiting) == (3, 7)


def test_login_does_not_hold_a_database_connection_during_the_password_check(
    seed_user: SeedUser, clean_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # One pooled connection and a password check slower than the pool timeout: if a login
    # kept its connection while hashing, the second login would fail with a 500.
    seed_user()
    real_verify = security.verify_password

    def slow_verify(password: str, password_hash: str) -> bool:
        time.sleep(1.5)
        return real_verify(password, password_hash)

    monkeypatch.setattr(security, "verify_password", slow_verify)
    settings = make_settings(
        database_url=clean_database, db_pool_size=1, db_max_overflow=0, db_pool_timeout_seconds=0.5
    )

    with TestClient(create_app(settings)) as client, ThreadPoolExecutor(max_workers=2) as pool:
        attempts = [
            pool.submit(client.post, LOGIN, json={"email": "nobody@example.com", "password": "x"})
            for _ in range(2)
        ]
        statuses = [attempt.result().status_code for attempt in attempts]

    assert statuses == [401, 401]


def test_login_succeeds_even_if_saving_an_upgraded_hash_fails(
    auth_client: TestClient,
    seed_user: SeedUser,
    clean_database: str,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(TEST_PASSWORD)
    user = seed_user(password_hash=weak_hash)
    caplog.set_level(logging.WARNING, logger="app.services.auth")
    real_commit = AsyncSession.commit
    commits = 0

    async def commit_fails_on_upgrade(self: AsyncSession) -> None:
        nonlocal commits
        commits += 1
        if commits == 2:  # the first commit ends the lookup; the second saves the new hash
            raise OperationalError("UPDATE users", {}, ConnectionError("connection lost"))
        await real_commit(self)

    monkeypatch.setattr(AsyncSession, "commit", commit_fails_on_upgrade)

    assert _login(auth_client, user.email)
    assert read_password_hash(clean_database, user.id) == weak_hash  # retried next login
    assert any(r.getMessage() == "Password hash upgrade failed" for r in caplog.records)


def test_session_stays_usable_after_a_failed_hash_upgrade(
    seed_user: SeedUser, clean_database: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A real database error aborts the transaction; without a rollback, any later query on
    # the same session would fail with "current transaction is aborted".
    weak_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(TEST_PASSWORD)
    user = seed_user(password_hash=weak_hash)

    async def failing_update(session: AsyncSession, *_args: object) -> None:
        await session.execute(text("SELECT 1 / 0"))

    monkeypatch.setattr(auth_service, "set_password_hash", failing_update)

    async def login_then_query(session: AsyncSession) -> int | None:
        await auth_service.authenticate(session, PasswordWorker(1, 1), user.email, TEST_PASSWORD)
        return await session.scalar(select(literal(1)))

    assert run_in_database(clean_database, login_then_query) == 1


def _post_raw(client: TestClient, body: dict[str, object]) -> Response:
    # json.dumps escapes lone surrogates (\ud800), exactly as an attacker's client would.
    return client.post(
        LOGIN, content=json.dumps(body), headers={"Content-Type": "application/json"}
    )


@pytest.mark.parametrize(
    "body",
    [
        {"email": "te\x00@example.com", "password": TEST_PASSWORD},
        {"email": "te\ud800@example.com", "password": TEST_PASSWORD},
        {"email": "teacher@example.com", "password": "\ud800"},
        {"email": "teacher@example.com\n", "password": TEST_PASSWORD},
    ],
    ids=["NUL in email", "surrogate in email", "surrogate in password", "newline in email"],
)
def test_unstorable_text_is_rejected_before_reaching_the_database(
    auth_client: TestClient, body: dict[str, object]
) -> None:
    response = _post_raw(auth_client, body)

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON


def test_busy_password_worker_answers_503_with_retry_after(
    auth_client: TestClient, seed_user: SeedUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_user()

    async def busy(*_args: object) -> bool:
        raise PasswordWorkerBusy

    monkeypatch.setattr(PasswordWorker, "verify", busy)

    response = auth_client.post(LOGIN, json={"email": "teacher@example.com", "password": "x"})

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["Retry-After"] == "1"


@pytest.mark.parametrize(
    "host", ["127.0.0.1:1", "no-such-host.invalid:5432"], ids=["refused", "unknown host"]
)
def test_database_outage_answers_503_without_error_traceback(
    host: str, caplog: pytest.LogCaptureFixture
) -> None:
    settings = make_settings(
        database_url=f"postgresql+asyncpg://user:db-secret@{host}/goalfit_test",
        db_pool_timeout_seconds=1,
    )
    app = create_app(settings)
    # create_app replaces the root log handlers, so reattach pytest's capture handler.
    logging.getLogger().addHandler(caplog.handler)
    caplog.set_level(logging.WARNING)

    with TestClient(app) as client:
        response = client.post(LOGIN, json={"email": "a@example.com", "password": "x"})

    assert response.status_code == 503
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers["Retry-After"] == "5"
    assert "db-secret" not in response.text
    # A one-line warning, not an error traceback per request during an outage.
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert any(r.getMessage() == "Dependency unavailable" for r in caplog.records)


def test_hung_database_answers_503_within_the_connect_timeout(silent_server_port: int) -> None:
    # Without a connect timeout the driver waits 60 seconds, then the request fails with 500.
    settings = make_settings(
        database_url=f"postgresql+asyncpg://u:p@127.0.0.1:{silent_server_port}/goalfit_test",
        db_connect_timeout_seconds=1,
    )

    with TestClient(create_app(settings)) as client:
        started = time.monotonic()
        response = client.post(LOGIN, json={"email": "a@example.com", "password": "x"})
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
    assert elapsed < 3


def test_exhausted_connection_pool_answers_503(clean_database: str) -> None:
    settings = make_settings(
        database_url=clean_database, db_pool_size=1, db_max_overflow=0, db_pool_timeout_seconds=0.5
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.portal is not None
        held = client.portal.call(app.state.engine.connect().start)
        try:
            response = client.post(LOGIN, json={"email": "a@example.com", "password": "x"})
        finally:
            client.portal.call(held.close)

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "5"
