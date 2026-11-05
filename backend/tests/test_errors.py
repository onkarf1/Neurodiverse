import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.constants import PROBLEM_JSON, REQUEST_ID_HEADER


def test_unknown_route_returns_problem_details(client: TestClient) -> None:
    response = client.get("/v1/missing")

    assert response.status_code == 404
    assert response.headers["content-type"] == PROBLEM_JSON
    body = response.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["request_id"] == response.headers[REQUEST_ID_HEADER]


def test_validation_error_does_not_echo_submitted_values(app: FastAPI, client: TestClient) -> None:
    @app.get("/v1/test-validation")
    async def validated(age: int) -> dict[str, int]:
        return {"age": age}

    response = client.get("/v1/test-validation", params={"age": "private-value"})

    assert response.status_code == 422
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.json()["errors"][0]["loc"] == ["query", "age"]
    assert "private-value" not in response.text


def test_unhandled_error_returns_safe_500_with_request_id(
    app: FastAPI, client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    @app.get("/v1/test-crash")
    async def crash() -> None:
        raise RuntimeError("internal detail")

    caplog.set_level(logging.ERROR)
    response = client.get("/v1/test-crash", headers={REQUEST_ID_HEADER: "trace-500"})

    assert response.status_code == 500
    assert response.headers["content-type"] == PROBLEM_JSON
    assert response.headers[REQUEST_ID_HEADER] == "trace-500"
    assert response.json()["request_id"] == "trace-500"
    assert "internal detail" not in response.text
    error_logs = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert error_logs
    assert error_logs[0].__dict__["request_id"] == "trace-500"


def test_unhandled_error_is_readable_by_allowed_origin(app: FastAPI, client: TestClient) -> None:
    @app.get("/v1/test-crash")
    async def crash() -> None:
        raise RuntimeError("internal detail")

    response = client.get("/v1/test-crash", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert response.headers[REQUEST_ID_HEADER]
