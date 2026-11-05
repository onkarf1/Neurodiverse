import time

from fastapi.testclient import TestClient
from sqlalchemy import make_url

from app.core.constants import PROBLEM_JSON
from app.main import create_app
from tests.helpers import make_settings


def test_ready_when_database_is_reachable(database_url: str) -> None:
    with TestClient(create_app(make_settings(database_url=database_url))) as client:
        response = client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_not_ready_when_database_is_unreachable() -> None:
    settings = make_settings(
        database_url="postgresql+asyncpg://user:db-secret@127.0.0.1:1/goalfit_test",
        readiness_timeout_seconds=1,
    )

    with TestClient(create_app(settings)) as client:
        ready = client.get("/v1/ready")
        health = client.get("/v1/health")

    assert ready.status_code == 503
    assert ready.headers["content-type"] == PROBLEM_JSON
    assert "db-secret" not in ready.text
    # Liveness must not depend on the database, or a database outage would restart the API.
    assert health.status_code == 200


def test_not_ready_when_database_rejects_credentials(database_url: str) -> None:
    wrong = make_url(database_url).set(password="wrong-password")
    settings = make_settings(database_url=wrong.render_as_string(hide_password=False))

    with TestClient(create_app(settings)) as client:
        response = client.get("/v1/ready")

    assert response.status_code == 503
    assert "wrong-password" not in response.text


def test_not_ready_within_timeout_when_database_hangs(silent_server_port: int) -> None:
    settings = make_settings(
        database_url=f"postgresql+asyncpg://u:p@127.0.0.1:{silent_server_port}/goalfit_test",
        readiness_timeout_seconds=0.5,
    )

    with TestClient(create_app(settings)) as client:
        started = time.monotonic()
        response = client.get("/v1/ready")
        elapsed = time.monotonic() - started

    assert response.status_code == 503
    assert elapsed < 1.5


def test_ready_while_request_pool_is_exhausted(database_url: str) -> None:
    # A busy instance must not be reported unhealthy, or the load balancer would shift its
    # traffic onto the other instances and overload them too.
    settings = make_settings(
        database_url=database_url,
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout_seconds=5,
        readiness_timeout_seconds=1,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        assert client.portal is not None
        held = client.portal.call(app.state.engine.connect().start)
        try:
            response = client.get("/v1/ready")
        finally:
            client.portal.call(held.close)

    assert response.status_code == 200
