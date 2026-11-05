import json
import logging
import sys
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


class JsonFormatter(logging.Formatter):
    """One JSON object per line, including any `extra` fields passed to the logger."""

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
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: LogLevel) -> None:
    logging.setLogRecordFactory(_record_factory)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
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
