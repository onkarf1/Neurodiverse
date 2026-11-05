import json
import socket
import threading
import time
from collections.abc import Callable, Iterator

import anyio
import httpx2
import pytest

from app.ai.errors import AIProviderError, AIUnavailableError
from app.ai.provider import Message, OpenAICompatibleProvider, create_provider
from tests.helpers import make_settings

pytestmark = pytest.mark.anyio

MESSAGES = [Message("system", "You check worksheets."), Message("user", "Worksheet text")]


def _completion(content: str | None) -> dict[str, object]:
    return {
        "id": "chatcmpl-1",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
    }


def _provider(
    handler: Callable[[httpx2.Request], httpx2.Response], timeout: float = 5
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        base_url="https://gateway.example/v1",
        api_key="test-key",
        model="test-model",
        timeout_seconds=timeout,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )


async def test_sends_a_deterministic_chat_request_and_returns_the_reply() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=_completion('{"ok": true}'))

    reply = await _provider(handler).complete(MESSAGES)

    assert reply == '{"ok": true}'
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/v1/chat/completions"
    assert seen[0].headers["Authorization"] == "Bearer test-key"
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    assert body["messages"] == [
        {"role": "system", "content": "You check worksheets."},
        {"role": "user", "content": "Worksheet text"},
    ]


@pytest.mark.parametrize("status", [429, 500, 502, 503], ids=["rate limited", "500", "502", "503"])
async def test_temporary_gateway_failures_are_unavailable(status: int) -> None:
    calls: list[int] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(status)
        return httpx2.Response(status, json={"error": {"message": "try later"}})

    with pytest.raises(AIUnavailableError):
        await _provider(handler).complete(MESSAGES)
    assert len(calls) == 1  # no hidden SDK retries; callers decide


@pytest.mark.parametrize(
    "status", [400, 401, 403, 404], ids=["bad request", "bad key", "forbidden", "no model"]
)
async def test_rejected_requests_are_provider_errors(status: int) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json={"error": {"message": "rejected"}})

    with pytest.raises(AIProviderError):
        await _provider(handler).complete(MESSAGES)


@pytest.mark.parametrize("payload", [_completion(None), {**_completion("x"), "choices": []}])
async def test_empty_replies_come_back_as_empty_text(payload: dict[str, object]) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=payload)

    assert await _provider(handler).complete(MESSAGES) == ""


async def test_refused_connection_is_unavailable() -> None:
    provider = OpenAICompatibleProvider(
        base_url="http://127.0.0.1:1/v1", api_key="k", model="m", timeout_seconds=2
    )

    with pytest.raises(AIUnavailableError):
        await provider.complete(MESSAGES)


async def test_stuck_gateway_is_unavailable_within_the_timeout(silent_server_port: int) -> None:
    provider = OpenAICompatibleProvider(
        base_url=f"http://127.0.0.1:{silent_server_port}/v1",
        api_key="k",
        model="m",
        timeout_seconds=0.5,
    )
    started = time.monotonic()

    # fail_after: if the provider's own limit ever breaks, fail fast instead of hanging CI.
    with anyio.fail_after(5), pytest.raises(AIUnavailableError):
        await provider.complete(MESSAGES)

    assert time.monotonic() - started < 2


def test_provider_uses_settings() -> None:
    provider = create_provider(make_settings(asu_air_api_key="from-settings", ai_model="m-1"))

    assert provider.model == "m-1"


def test_missing_api_key_is_a_clear_configuration_error() -> None:
    with pytest.raises(AIProviderError, match="ASU_AIR_API_KEY"):
        create_provider(make_settings(asu_air_api_key=None))


async def test_unencodable_text_is_replaced_instead_of_crashing() -> None:
    # A retry resends the model's own reply, which can contain an escaped lone surrogate.
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=_completion("ok"))

    reply = await _provider(handler).complete([Message("user", "before \ud800 after")])

    assert reply == "ok"
    assert json.loads(seen[0].content)["messages"][0]["content"] == "before \ufffd after"


@pytest.fixture
def dripping_server_port() -> Iterator[int]:
    """Answers with headers, then sends the body one byte at a time. Per-read timeouts never
    fire against this, so only an overall time limit can stop the call."""
    stop = threading.Event()
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def serve() -> None:
        connection, _ = server.accept()
        with connection:
            connection.recv(65536)
            connection.sendall(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 1000\r\n\r\n"
            )
            while not stop.is_set():
                connection.sendall(b" ")
                time.sleep(0.1)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield server.getsockname()[1]
    stop.set()
    server.close()


async def test_slow_dripping_reply_is_cut_off_by_the_overall_timeout(
    dripping_server_port: int,
) -> None:
    provider = OpenAICompatibleProvider(
        base_url=f"http://127.0.0.1:{dripping_server_port}/v1",
        api_key="k",
        model="m",
        timeout_seconds=0.5,
    )
    started = time.monotonic()

    with anyio.fail_after(5), pytest.raises(AIUnavailableError):
        await provider.complete(MESSAGES)

    assert time.monotonic() - started < 2
