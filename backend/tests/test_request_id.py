from fastapi.testclient import TestClient

from app.core.constants import REQUEST_ID_HEADER as HEADER


def test_response_includes_generated_request_id(client: TestClient) -> None:
    response = client.get("/v1/health")

    assert response.headers.get(HEADER)


def test_valid_client_request_id_is_echoed(client: TestClient) -> None:
    response = client.get("/v1/health", headers={HEADER: "demo-123"})

    assert response.headers[HEADER] == "demo-123"


def test_unsafe_client_request_id_is_replaced(client: TestClient) -> None:
    # Prevents log injection through attacker-controlled IDs.
    unsafe = "bad id\twith tab"

    response = client.get("/v1/health", headers={HEADER: unsafe})

    assert response.headers[HEADER] != unsafe
    assert response.headers[HEADER]
