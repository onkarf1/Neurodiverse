import json
import logging
import logging.config
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG

from app.core.constants import ACCESS_LOGGER, REQUEST_ID_HEADER
from app.core.log_config import JsonFormatter, configure_logging


def test_json_formatter_includes_request_id_and_extra_fields() -> None:
    record = logging.makeLogRecord(
        {"msg": "hello", "levelname": "INFO", "name": "test", "request_id": "abc", "path": "/x"}
    )

    output = json.loads(JsonFormatter().format(record))

    assert output["message"] == "hello"
    assert output["request_id"] == "abc"
    assert output["path"] == "/x"


def test_log_level_also_applies_to_uvicorn_logs() -> None:
    # Apply Uvicorn's real startup logging config, which sets its own loggers to INFO.
    logging.config.dictConfig(UVICORN_LOGGING_CONFIG)

    configure_logging("WARNING")

    for name in ("uvicorn", "uvicorn.error"):
        assert not logging.getLogger(name).isEnabledFor(logging.INFO)
        assert logging.getLogger(name).isEnabledFor(logging.WARNING)


def test_extra_fields_cannot_overwrite_core_fields() -> None:
    record = logging.makeLogRecord(
        {"msg": "boom", "levelname": "ERROR", "name": "real", "level": "INFO", "logger": "fake"}
    )

    output = json.loads(JsonFormatter().format(record))

    assert output["level"] == "ERROR"
    assert output["logger"] == "real"


def test_core_fields_come_first_for_readable_logs() -> None:
    record = logging.makeLogRecord({"msg": "m", "levelname": "INFO", "name": "t", "path": "/x"})

    output = json.loads(JsonFormatter().format(record))

    assert list(output)[:5] == ["time", "level", "logger", "message", "request_id"]
    assert output["path"] == "/x"


def test_failure_after_response_started_is_logged_as_500(
    app: FastAPI, caplog: pytest.LogCaptureFixture
) -> None:
    @app.get("/v1/test-stream-crash")
    async def stream_crash() -> StreamingResponse:
        async def chunks() -> AsyncIterator[bytes]:
            yield b"partial"
            raise RuntimeError("failed mid-stream")

        return StreamingResponse(chunks())

    caplog.set_level(logging.INFO, logger=ACCESS_LOGGER)

    TestClient(app, raise_server_exceptions=False).get("/v1/test-stream-crash")

    record = next(r for r in caplog.records if r.name == ACCESS_LOGGER)
    assert record.__dict__["status"] == 500


def test_access_log_records_request_without_query_string(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger=ACCESS_LOGGER)

    client.get("/v1/health?email=someone@example.com", headers={REQUEST_ID_HEADER: "trace-log"})

    record = next(r for r in caplog.records if r.name == ACCESS_LOGGER)
    assert record.__dict__["path"] == "/v1/health"
    assert record.__dict__["status"] == 200
    assert record.__dict__["request_id"] == "trace-log"
    # Check only the app's log line; the test client logs its own full URL separately.
    assert "someone@example.com" not in JsonFormatter().format(record)
