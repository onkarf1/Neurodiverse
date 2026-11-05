import json
import logging
import sys
import traceback
from datetime import UTC, datetime
from typing import Any

from app.core.config import LogLevel
from app.core.context import request_id_var

# Uvicorn adds "color_message" (terminal color codes), which is noise in JSON logs.
_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {
    "message",
    "asctime",
    "request_id",
    "color_message",
}
_base_record_factory = logging.getLogRecordFactory()


def _record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    # Stamp the request ID when the record is created, while the request context still exists.
    record = _base_record_factory(*args, **kwargs)
    record.__dict__["request_id"] = request_id_var.get()
    return record


def _redacted_traceback(exc: BaseException) -> str:
    """Stack frames and exception types only. Messages are dropped because database and
    validation errors often quote row values, which here can be student data.

    Exception groups are summarized by their own type; their sub-exceptions are not listed.
    """
    parts: list[str] = []
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        frames = "".join(traceback.format_tb(current.__traceback__))
        name = f"{type(current).__module__}.{type(current).__qualname__}"
        parts.append(f"{frames}{name}: [message redacted]")
        # Follow the chain the way Python's own tracebacks do, including `raise ... from None`.
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return "\n\nCaused by:\n".join(parts)


class JsonFormatter(logging.Formatter):
    """One JSON object per line, including any `extra` fields passed to the logger."""

    def __init__(self, *, redact_exception_messages: bool = False) -> None:
        super().__init__()
        self.redact_exception_messages = redact_exception_messages

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": record.__dict__.get("request_id", "-"),
        }
        # Core fields stay first for readability, and extra fields can't overwrite them.
        extras = {k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS}
        payload.update({k: v for k, v in extras.items() if k not in payload})
        if record.exc_info and record.exc_info[1] is not None:
            payload["exc_info"] = (
                _redacted_traceback(record.exc_info[1])
                if self.redact_exception_messages
                else self.formatException(record.exc_info)
            )
        return json.dumps(payload, default=str)


def configure_logging(level: LogLevel, *, redact_exception_messages: bool = False) -> None:
    logging.setLogRecordFactory(_record_factory)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(redact_exception_messages=redact_exception_messages))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Send Uvicorn's logs through the JSON handler. Its access log is replaced by ACCESS_LOGGER,
    # which omits query strings because they can contain personal data.
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.handlers = []
    uvicorn_logger.propagate = True
    # Uvicorn sets both loggers to INFO at startup; NOTSET makes them follow LOG_LEVEL.
    uvicorn_logger.setLevel(logging.NOTSET)
    logging.getLogger("uvicorn.error").setLevel(logging.NOTSET)
    logging.getLogger("uvicorn.access").disabled = True
    # Requests to the AI contain student text. The openai SDK's debug logging (OPENAI_LOG=debug)
    # currently records only methods, status codes and request IDs, but older versions logged
    # full request bodies; capping it at WARNING keeps a future SDK change from leaking them.
    logging.getLogger("openai").setLevel(logging.WARNING)
