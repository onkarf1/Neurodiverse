import json
import logging
import logging.config
import sys
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from uvicorn.config import LOGGING_CONFIG as UVICORN_LOGGING_CONFIG

from app.core.constants import ACCESS_LOGGER, REQUEST_ID_HEADER
from app.core.log_config import JsonFormatter, configure_logging
from app.main import create_app
from tests.helpers import make_settings


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


def _record_with_chained_exception() -> logging.LogRecord:
    # Sensitive values come from variables so they don't appear in the traceback's source lines.
    email, name = "jane.doe@example.com", "Jane Doe"
    try:
        try:
            raise ValueError(f"Key (email)=({email}) already exists")
        except ValueError as cause:
            raise RuntimeError(f"insert failed for {name}") from cause
    except RuntimeError:
        return logging.makeLogRecord(
            {"msg": "failed", "levelname": "ERROR", "name": "t", "exc_info": sys.exc_info()}
        )


def test_redacted_logs_keep_exception_types_and_stack_but_hide_messages() -> None:
    record = _record_with_chained_exception()

    trace = json.loads(JsonFormatter(redact_exception_messages=True).format(record))["exc_info"]

    assert "RuntimeError" in trace
    assert "ValueError" in trace
    assert "test_logging.py" in trace
    assert "jane.doe@example.com" not in trace
    assert "Jane Doe" not in trace


def test_development_logs_keep_exception_messages() -> None:
    record = _record_with_chained_exception()

    trace = json.loads(JsonFormatter().format(record))["exc_info"]

    assert "Jane Doe" in trace


def test_production_app_redacts_exception_messages() -> None:
    create_app(make_settings(app_env="production"))

    formatter = logging.getLogger().handlers[0].formatter

    assert isinstance(formatter, JsonFormatter)
    assert formatter.redact_exception_messages is True


def _redacted_trace(record: logging.LogRecord) -> str:
    return str(json.loads(JsonFormatter(redact_exception_messages=True).format(record))["exc_info"])


def _record_from_current_exception() -> logging.LogRecord:
    return logging.makeLogRecord(
        {"msg": "failed", "levelname": "ERROR", "name": "t", "exc_info": sys.exc_info()}
    )


def test_redaction_follows_exceptions_raised_while_handling_another() -> None:
    try:
        try:
            raise KeyError("first")
        except KeyError:
            raise LookupError("second")  # noqa: B904  (implicit chaining is the point here)
    except LookupError:
        trace = _redacted_trace(_record_from_current_exception())

    assert "KeyError" in trace
    assert "LookupError" in trace


def test_redaction_respects_raise_from_none() -> None:
    try:
        try:
            raise KeyError("hidden context")
        except KeyError:
            raise LookupError("shown") from None
    except LookupError:
        trace = _redacted_trace(_record_from_current_exception())

    assert "LookupError" in trace
    assert "KeyError" not in trace


def test_ai_sdk_request_logging_stays_off_even_at_debug_level() -> None:
    # The openai SDK can log full request bodies (student text) when OPENAI_LOG=debug is set.
    configure_logging("DEBUG")

    assert logging.getLogger("openai").getEffectiveLevel() >= logging.WARNING
