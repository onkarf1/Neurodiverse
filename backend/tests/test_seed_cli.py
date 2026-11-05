import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cli import main
from app.main import create_app
from app.models import School, User
from tests.auth_fixtures import run_in_database
from tests.helpers import TEST_SECRET, make_settings

ADMIN_PASSWORD = "admin password for the demo 1"
TEACHER_PASSWORD = "teacher password for the demo 2"
GENERATED = re.compile(r"(\S+@\S+)\s+password: (\S+)")


@pytest.fixture
def cli_env(clean_database: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Environment the CLI reads its settings from, pointed at the test database."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.setenv("DATABASE_URL", clean_database)
    for name in ("DEMO_ADMIN_PASSWORD", "DEMO_TEACHER_PASSWORD"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir("/")  # so a developer's local .env is never read
    return clean_database


def _login_role(database_url: str, email: str, password: str) -> str | None:
    with TestClient(create_app(make_settings(database_url=database_url))) as client:
        login = client.post("/v1/auth/login", json={"email": email, "password": password})
        if login.status_code != 200:
            return None
        token = login.json()["access_token"]
        me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        return str(me.json()["role"])


def _count(database_url: str, model: type[User] | type[School]) -> int:
    async def count(session: AsyncSession) -> int:
        return int(await session.scalar(select(func.count()).select_from(model)) or 0)

    return run_in_database(database_url, count)


def _user_count(database_url: str) -> int:
    return _count(database_url, User)


def test_seed_creates_an_admin_and_a_teacher_who_can_sign_in(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DEMO_TEACHER_PASSWORD", TEACHER_PASSWORD)

    assert main(["seed-demo"]) == 0

    output = capsys.readouterr().out
    assert _login_role(cli_env, "admin@demo.example", ADMIN_PASSWORD) == "admin"
    assert _login_role(cli_env, "teacher@demo.example", TEACHER_PASSWORD) == "teacher"
    # Passwords the operator supplied are never echoed back.
    assert ADMIN_PASSWORD not in output
    assert TEACHER_PASSWORD not in output


def test_seed_generates_and_prints_passwords_once_when_none_are_given(
    cli_env: str, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["seed-demo"]) == 0

    printed = dict(GENERATED.findall(capsys.readouterr().out))
    assert set(printed) == {"admin@demo.example", "teacher@demo.example"}
    # 18 random bytes give 24 URL-safe characters; each account gets its own password.
    assert all(len(password) >= 24 for password in printed.values())
    assert len(set(printed.values())) == 2
    assert _login_role(cli_env, "admin@demo.example", printed["admin@demo.example"]) == "admin"


def test_running_seed_twice_changes_nothing(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DEMO_TEACHER_PASSWORD", TEACHER_PASSWORD)
    assert main(["seed-demo"]) == 0
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "a different password entirely 3")

    assert main(["seed-demo"]) == 0

    assert "already exists" in capsys.readouterr().out
    assert _user_count(cli_env) == 2
    assert _count(cli_env, School) == 1  # the existing school is reused, not duplicated
    # Existing accounts keep their password; seeding never resets credentials.
    assert _login_role(cli_env, "admin@demo.example", ADMIN_PASSWORD) == "admin"


def test_seed_refuses_to_run_in_production(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("APP_ENV", "production")

    assert main(["seed-demo"]) != 0

    assert "production" in capsys.readouterr().err
    assert _user_count(cli_env) == 0


def test_seed_rejects_short_passwords(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", "too-short")

    assert main(["seed-demo"]) != 0

    assert "15 characters" in capsys.readouterr().err
    assert _user_count(cli_env) == 0


def test_custom_school_and_emails(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DEMO_TEACHER_PASSWORD", TEACHER_PASSWORD)
    unique = uuid.uuid4().hex[:6]

    code = main(
        [
            "seed-demo",
            "--school",
            f"Pilot {unique}",
            "--admin-email",
            f"lead-{unique}@pilot.example",
            "--teacher-email",
            f"t-{unique}@pilot.example",
        ]
    )

    assert code == 0
    assert _login_role(cli_env, f"lead-{unique}@pilot.example", ADMIN_PASSWORD) == "admin"


@pytest.mark.parametrize(
    ("argv", "flag"),
    [
        (["--admin-email", "bad\nadmin@demo.example"], "--admin-email"),
        (["--teacher-email", "a" * 330 + "@demo.example"], "--teacher-email"),
        (["--school", "S" * 201], "--school"),
        (["--school", "   "], "--school"),
        (["--school", "Demo\nSchool"], "--school"),
    ],
    ids=[
        "email with newline",
        "overlong email",
        "overlong school",
        "blank school",
        "control character in school",
    ],
)
def test_invalid_arguments_are_rejected_before_touching_the_database(
    cli_env: str, capsys: pytest.CaptureFixture[str], argv: list[str], flag: str
) -> None:
    # These would otherwise crash on a database limit or create an account no one could
    # sign in to (login rejects control characters).
    with pytest.raises(SystemExit) as exited:
        main(["seed-demo", *argv])

    assert exited.value.code == 2
    assert flag in capsys.readouterr().err
    assert _user_count(cli_env) == 0


@pytest.mark.parametrize(
    ("password", "message"),
    [("p" * 129, "128 characters"), ("long-enough-password\udcff", "can't be encoded")],
    ids=["longer than login allows", "invalid bytes in the environment"],
)
def test_passwords_login_could_not_accept_are_rejected(
    cli_env: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    password: str,
    message: str,
) -> None:
    monkeypatch.setenv("DEMO_TEACHER_PASSWORD", password)

    assert main(["seed-demo"]) != 0

    assert message in capsys.readouterr().err
    assert _user_count(cli_env) == 0


def test_passwords_in_a_dotenv_file_are_used(
    cli_env: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # .env.example tells developers to put these in .env, so that must work without Docker.
    (tmp_path / ".env").write_text(
        f"DEMO_ADMIN_PASSWORD={ADMIN_PASSWORD}\nDEMO_TEACHER_PASSWORD={TEACHER_PASSWORD}\n"
    )
    monkeypatch.chdir(tmp_path)

    assert main(["seed-demo"]) == 0

    assert _login_role(cli_env, "admin@demo.example", ADMIN_PASSWORD) == "admin"
    assert _login_role(cli_env, "teacher@demo.example", TEACHER_PASSWORD) == "teacher"


def test_admin_and_teacher_emails_must_differ(
    cli_env: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["seed-demo", "--admin-email", "x@demo.example", "--teacher-email", "X@Demo.example"])

    assert exited.value.code == 2
    assert "must be different" in capsys.readouterr().err
    assert _user_count(cli_env) == 0


def test_school_name_with_undecodable_bytes_is_rejected(
    cli_env: str, capsys: pytest.CaptureFixture[str]
) -> None:
    # Invalid UTF-8 in a command-line argument reaches Python as a lone surrogate.
    with pytest.raises(SystemExit) as exited:
        main(["seed-demo", "--school", "Demo \udcff School"])

    assert exited.value.code == 2
    assert "--school" in capsys.readouterr().err


def test_existing_school_with_a_duplicate_name_is_chosen_predictably(
    cli_env: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # School names aren't unique; the oldest matching school is always the one used. The
    # oldest is inserted second, so returning rows in insertion order would pick the wrong one.
    def add_school(created_at: datetime) -> uuid.UUID:
        async def work(session: AsyncSession) -> uuid.UUID:
            school = School(name="Demo School", created_at=created_at)
            session.add(school)
            await session.flush()
            return school.id

        return run_in_database(cli_env, work)

    add_school(datetime(2026, 6, 1, tzinfo=UTC))
    oldest = add_school(datetime(2026, 1, 1, tzinfo=UTC))
    monkeypatch.setenv("DEMO_ADMIN_PASSWORD", ADMIN_PASSWORD)
    monkeypatch.setenv("DEMO_TEACHER_PASSWORD", TEACHER_PASSWORD)

    assert main(["seed-demo"]) == 0

    async def admin_school(session: AsyncSession) -> uuid.UUID | None:
        return await session.scalar(
            select(User.school_id).where(User.email == "admin@demo.example")
        )

    assert run_in_database(cli_env, admin_school) == oldest
