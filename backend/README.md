# GoalFit Backend

FastAPI service that checks whether a learning activity actually practices a learner's
approved IEP goal, and helps teachers revise it without removing required supports.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker (for Postgres and Redis)

## Setup

```bash
cd backend
cp .env.example .env
# Set JWT_SECRET in .env (at least 32 characters):
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
uv sync
```

## Run

Everything in Docker:

```bash
docker compose up --build
curl http://localhost:8000/v1/health
```

API locally, databases in Docker:

```bash
docker compose up -d postgres redis
uv run uvicorn --factory app.main:create_app --reload
```

Interactive API docs (not served in production): http://localhost:8000/docs

## Test and check

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run mypy app tests
```

## Project layout

Each layer only calls the layer below it, so business rules can be tested without HTTP and
the database or AI provider can change without touching routes.

```
app/
  main.py         Application factory: middleware order, error handlers, routers
  core/           Cross-cutting concerns
    config.py       Settings from environment variables (secrets hidden when printed)
    context.py      Current request ID
    errors.py       Single error format (RFC 9457 problem details)
    log_config.py   JSON logs with request ID; Uvicorn logs routed through it
    middleware.py   Request ID and access log, security headers, body size limit
  api/v1/         Thin HTTP layer: validate input, call a service, return a response
tests/            Pytest suite (tests are written before each feature)
```

Added as features need them: `services/` (business rules), `repositories/` (database
queries filtered by school), `models/` (tables), `schemas/` (request and response formats),
and `ai/` (provider, prompts, redaction, guards).

## Security and operations

- Errors use one JSON format, include the request ID, and never expose stack traces or
  submitted values.
- Every response carries `X-Request-ID`, and the same ID appears in every related log line.
  Exception: CORS preflight (`OPTIONS`) replies have no request ID or access-log entry,
  because CORS runs first so that error responses stay readable by the browser.
- Access logs record method, path, status, and duration, never query strings.
- Request bodies over `MAX_REQUEST_BODY_BYTES` (default 1 MB) are rejected with 413.
- Security headers on every response; production adds CSP and HSTS and disables `/docs`.
- Production refuses to start with a wildcard CORS origin, and `APP_ENV` must be set
  explicitly, so a deployment can't silently run in development mode.
- CORS headers are added to error responses too, so the frontend can read the request ID.
- The container runs as a non-root user, hides the server header, and shuts down gracefully.
- Base images are pinned by digest for reproducible builds.

## Attribution

- Libraries: FastAPI, Uvicorn, Pydantic, pydantic-settings; dev tools pytest, httpx2,
  Ruff, mypy. See `pyproject.toml` for versions.
- AI assistance: initial scaffolding drafted with an AI coding assistant, then reviewed,
  tested, and edited by the team. Each pull request notes where AI assistance was used.
