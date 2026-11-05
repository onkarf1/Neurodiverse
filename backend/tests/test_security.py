from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.constants import PROBLEM_JSON, REQUEST_ID_HEADER
from app.main import create_app
from tests.helpers import make_settings


class Payload(BaseModel):
    text: str


@pytest.fixture
def small_limit_client() -> TestClient:
    app = create_app(make_settings(max_request_body_bytes=100))

    @app.post("/v1/test-echo")
    async def echo(payload: Payload) -> Payload:
        return payload

    return TestClient(app)


def test_security_headers_are_set(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
    # Development omits the strict CSP so the interactive /docs page still loads.
    assert "Content-Security-Policy" not in response.headers


def test_docs_are_available_in_development(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200


def test_production_hides_docs_and_adds_strict_headers() -> None:
    client = TestClient(create_app(make_settings(app_env="production")))

    response = client.get("/v1/health")

    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "max-age=" in response.headers["Strict-Transport-Security"]
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    allowed = client.get("/v1/health", headers={"Origin": "http://localhost:5173"})
    blocked = client.get("/v1/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_cors_preflight_is_answered_without_request_id(client: TestClient) -> None:
    # Documented tradeoff: CORS runs before RequestContext so error responses stay readable,
    # which means preflight replies get no request ID and no access-log entry.
    response = client.options(
        "/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert REQUEST_ID_HEADER not in response.headers


def test_body_within_limit_is_accepted(small_limit_client: TestClient) -> None:
    response = small_limit_client.post("/v1/test-echo", json={"text": "hi"})

    assert response.status_code == 200


def test_declared_oversized_body_is_rejected(small_limit_client: TestClient) -> None:
    response = small_limit_client.post("/v1/test-echo", json={"text": "x" * 200})

    assert response.status_code == 413
    assert response.headers["content-type"] == PROBLEM_JSON


def test_oversized_body_error_is_readable_by_allowed_origin(
    small_limit_client: TestClient,
) -> None:
    response = small_limit_client.post(
        "/v1/test-echo",
        json={"text": "x" * 200},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_streamed_oversized_body_is_rejected(small_limit_client: TestClient) -> None:
    # A streamed body has no Content-Length, so the limit must be enforced while reading.
    def chunks() -> Iterator[bytes]:
        yield b'{"text": "'
        yield b"x" * 200
        yield b'"}'

    response = small_limit_client.post(
        "/v1/test-echo", content=chunks(), headers={"Content-Type": "application/json"}
    )

    assert response.status_code == 413
