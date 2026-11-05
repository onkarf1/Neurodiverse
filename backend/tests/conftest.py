import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from tests.helpers import make_settings

_SHARED_LOGGERS = ("", "uvicorn", "uvicorn.error", "uvicorn.access")


def _is_pytest_handler(handler: logging.Handler) -> bool:
    return type(handler).__module__.startswith("_pytest")


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """Undoes global logging changes made by create_app() or tests, so tests stay independent.

    Pytest's own capture handlers are left alone; pytest adds and removes them per test phase.
    """
    record_factory = logging.getLogRecordFactory()
    saved = []
    for name in _SHARED_LOGGERS:
        logger = logging.getLogger(name)
        handlers = [h for h in logger.handlers if not _is_pytest_handler(h)]
        saved.append((logger, logger.level, handlers, logger.propagate, logger.disabled))

    yield

    logging.setLogRecordFactory(record_factory)
    for logger, level, handlers, propagate, disabled in saved:
        pytest_handlers = [h for h in logger.handlers if _is_pytest_handler(h)]
        logger.handlers = handlers + pytest_handlers
        logger.setLevel(level)
        logger.propagate = propagate
        logger.disabled = disabled


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
