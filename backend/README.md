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
uv run alembic upgrade head        # create or update tables
uv run uvicorn --factory app.main:create_app --reload
```

Health checks: `/v1/health` (process is alive, never checks dependencies) and `/v1/ready`
(database reachable; returns 503 otherwise, so load balancers stop routing traffic). The
readiness check uses its own connection, so a busy instance is never reported unhealthy.

Interactive API docs (not served in production): http://localhost:8000/docs

## Database migrations

```bash
uv run alembic revision --autogenerate -m "describe the change"   # after editing models
uv run alembic upgrade head                                        # apply
uv run alembic downgrade -1                                        # undo the last one
docker compose run --rm api alembic upgrade head                   # inside Docker
```

Always review a generated migration before committing it. Tests catch drift between
models and migrations: new or removed tables, columns, indexes and constraints, type and
length changes, nullability, foreign key rules, and server defaults (via `alembic check`),
plus new user roles (a test saves every role) and CHECK constraints (compared by name).
Alembic can't detect every change, so for anything else (for example, a renamed column)
write and review the migration by hand.

`updated_at` is set automatically on ORM updates only; bulk updates and raw SQL must set it.

## Test and check

Database tests use a separate `goalfit_test` database and are skipped if Postgres isn't
running. Set `CI` or `REQUIRE_DB_TESTS` to `true` to make that a failure instead; the CI
workflow does this. They refuse to run against any database whose name doesn't end in `_test`.

```bash
docker compose up -d postgres
docker compose exec postgres createdb -U goalfit goalfit_test   # once
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
    security.py     Password hashing and access tokens
  api/v1/         Thin HTTP layer: validate input, call a service, return a response
  api/deps.py     Shared request dependencies: session, settings, signed-in user
  db/             Base model and mixins, engine and sessions, readiness check
  models/         Tables: School, User, Goal, Accommodation, Worksheet
  repositories/   Database queries
  services/       Business rules (for example, login)
  schemas/        Request and response formats
alembic/          Database migrations
tests/            Pytest suite (tests are written before each feature)
```

Planned as features need it: `ai/` (provider, prompts, redaction, guards).

## Authentication

`POST /v1/auth/login` with `{"email": ..., "password": ...}` returns a bearer token. Send it as
`Authorization: Bearer <token>`. `GET /v1/auth/me` returns the signed-in user.

- Passwords are hashed with Argon2id (RFC 9106 settings) after Unicode normalization, and
  weaker hashes are upgraded at the next login. Hashing runs on worker threads, at most
  `PASSWORD_HASH_CONCURRENCY` at a time per process with at most `PASSWORD_HASH_QUEUE_LIMIT`
  waiting, because each hash uses 64 MiB.
- Tokens are HS256 JWTs signed with `JWT_SECRET` and valid for `ACCESS_TOKEN_TTL_MINUTES`
  (default 30). Signature, algorithm, issuer, audience, expiry, not-before and token type
  are all checked. Changing `JWT_SECRET` signs everyone out; there is no key rotation yet.
- The user is reloaded on every request, so disabling an account takes effect immediately.
  Tokens can't otherwise be revoked before they expire, so keep their lifetime short.
- Failed logins return the same 401 and run the same password check whether the email is
  unknown, the password is wrong, or the account is disabled.
- A login releases its database connection before the password check, so a burst of logins
  can't use up the connection pool and slow down other requests. Upgrading an outdated hash
  is best effort: if saving it fails, the login still succeeds and it's retried next time.
- Emails are matched case-insensitively by Postgres, the same way the unique index compares
  them.
- Logins are logged with outcome, reason and user ID, never with email or password.

**Not yet implemented:** 503 answers when the password queue is full or the database is
down, and rejecting unstorable text in emails and passwords (BE-3a-3); role-based access and
a way to create users (BE-3b); login rate limiting (BE-3c); password reset.

## Data model

Every school-owned row has a `school_id`. Composite foreign keys make the database itself
reject links across schools (for example, a worksheet pointing at another school's goal).
Goals have no learner name or identifier fields, but free text could still contain them.
**Not yet implemented:** personal data must be redacted before any text is sent to an AI
model (issue #7). Emails are unique across all schools regardless of case, because sign-in
identifies a person by email alone. Roles are limited to `teacher` and `admin` by a database
check.

## Security and operations

- Errors use one JSON format, include the request ID, and never expose stack traces or
  submitted values.
- Every response carries `X-Request-ID`, and the same ID appears in every related log line.
  Exception: CORS preflight (`OPTIONS`) replies have no request ID or access-log entry,
  because CORS runs first so that error responses stay readable by the browser.
- Access logs record method, path, status, and duration, never query strings.
- In production, error logs keep exception types and stack traces but drop exception
  messages, which can quote database rows (student data). The database driver also hides
  query parameters from its error messages.
- Request bodies over `MAX_REQUEST_BODY_BYTES` (default 1 MB) are rejected with 413.
- Security headers on every response; production adds CSP and HSTS and disables `/docs`.
- Production refuses to start with a wildcard CORS origin, and `APP_ENV` must be set
  explicitly, so a deployment can't silently run in development mode.
- CORS headers are added to error responses too, so the frontend can read the request ID.
- The container runs as a non-root user, hides the server header, and shuts down gracefully.
- Base images are pinned by digest for reproducible builds.

## Attribution

- Libraries: FastAPI, Uvicorn, Pydantic, pydantic-settings, SQLAlchemy, asyncpg, Alembic,
  argon2-cffi, PyJWT, AnyIO; dev tools pytest, httpx2, Ruff, mypy. See `pyproject.toml` for
  versions.
- AI assistance: initial scaffolding drafted with an AI coding assistant, then reviewed,
  tested, and edited by the team. Each pull request notes where AI assistance was used.
