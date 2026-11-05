import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.constants import PROBLEM_JSON
from app.core.context import request_id_var
from app.core.security import PasswordWorkerBusy

logger = logging.getLogger(__name__)

# A dependency (currently the database) can't be reached right now: the request may succeed
# if retried shortly, so these become 503 with Retry-After instead of a 500.
#  - OSError: network failures, including refused connections (a plain OSError when a host
#    such as localhost has several addresses), unknown hosts, and connect timeouts. The app
#    does no file I/O, so an OSError here always comes from the network.
#  - PoolTimeoutError: every pooled connection is busy.
_DEPENDENCY_UNAVAILABLE: tuple[type[Exception], ...] = (OSError, PoolTimeoutError)

# Postgres SQLSTATE codes meaning "temporarily unavailable" rather than a bug or bad config:
# class 08 (connection lost), class 53 (insufficient resources, e.g. too many connections),
# and 57P01-57P03 (server shutting down, crashed, or still starting). Everything else, such
# as a wrong password, a missing table, or a statement timeout, stays a 500 so it's noticed.
_UNAVAILABLE_SQLSTATE_CLASSES = ("08", "53")
_UNAVAILABLE_SQLSTATES = frozenset({"57P01", "57P02", "57P03"})


def _database_temporarily_unavailable(exc: DBAPIError) -> bool:
    if exc.connection_invalidated:
        return True
    sqlstate = getattr(exc.orig, "sqlstate", None)
    return isinstance(sqlstate, str) and (
        sqlstate.startswith(_UNAVAILABLE_SQLSTATE_CLASSES) or sqlstate in _UNAVAILABLE_SQLSTATES
    )


def _title(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:
        return "Error"


def problem_response(
    status: int,
    detail: str | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Builds an RFC 9457 "problem details" error response, the API's single error format."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _title(status),
        "status": status,
        "request_id": request_id_var.get(),
    }
    if detail:
        body["detail"] = detail
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, headers=headers, media_type=PROBLEM_JSON)


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    detail: str | None = exc.detail if isinstance(exc.detail, str) else None
    if detail == _title(exc.status_code):
        detail = None
    return problem_response(exc.status_code, detail, headers=exc.headers)


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Only location, message, and type are returned; submitted values are never echoed back.
    errors = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return problem_response(422, "The request is invalid.", extra={"errors": errors})


async def _dependency_unavailable(request: Request, exc: Exception) -> JSONResponse:
    # One line per request: a traceback for every request during an outage would flood logs.
    logger.warning("Dependency unavailable", extra={"error_type": type(exc).__name__})
    return problem_response(
        503,
        "The service is temporarily unavailable. Try again shortly.",
        headers={"Retry-After": "5"},
    )


async def _database_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, DBAPIError) and _database_temporarily_unavailable(exc):
        return await _dependency_unavailable(request, exc)
    raise exc  # a real error: 500 and a logged traceback


async def _password_worker_busy(request: Request, exc: Exception) -> JSONResponse:
    logger.warning("Password worker busy")
    return problem_response(
        503,
        "Too many sign-in attempts are being processed. Try again shortly.",
        headers={"Retry-After": "1"},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(PasswordWorkerBusy, _password_worker_busy)
    for error_type in _DEPENDENCY_UNAVAILABLE:
        app.add_exception_handler(error_type, _dependency_unavailable)
    app.add_exception_handler(DBAPIError, _database_error)
