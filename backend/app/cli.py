"""Command-line tasks.

    uv run python -m app.cli seed-demo [--school NAME] [--admin-email E] [--teacher-email E]

Passwords come from DEMO_ADMIN_PASSWORD and DEMO_TEACHER_PASSWORD, set in the environment or
in .env. If one isn't set, a random password is generated and printed once.
"""

import argparse
import asyncio
import secrets
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import SecretStr, TypeAdapter, ValidationError
from pydantic_settings import BaseSettings
from sqlalchemy import select

from app.core.config import Settings
from app.core.constants import MAX_PASSWORD_LENGTH
from app.core.security import hash_password
from app.db.session import create_engine, create_session_factory
from app.models import School, User, UserRole
from app.models.school import SCHOOL_NAME_MAX_LENGTH
from app.repositories.users import get_user_by_email
from app.schemas.auth import EmailAddress, contains_category

# NIST SP 800-63B (revision 4): at least 15 characters when a password is the only factor.
MIN_PASSWORD_LENGTH = 15
_EMAIL = TypeAdapter(EmailAddress)


def _email(value: str) -> str:
    try:
        return _EMAIL.validate_python(value.strip())
    except ValidationError:
        raise argparse.ArgumentTypeError(
            "must be 3 to 320 characters with no control characters"
        ) from None


def _school_name(value: str) -> str:
    name = value.strip()
    # Cs: invalid UTF-8 in a command-line argument arrives as a lone surrogate.
    if not name or len(name) > SCHOOL_NAME_MAX_LENGTH or contains_category(name, "Cc", "Cs"):
        raise argparse.ArgumentTypeError(
            f"must be 1 to {SCHOOL_NAME_MAX_LENGTH} characters of valid text with no control"
            " characters"
        )
    return name


class DemoPasswords(BaseSettings):
    """Read like the app's own settings: from the environment, or from .env."""

    model_config = Settings.model_config

    demo_admin_password: SecretStr | None = None
    demo_teacher_password: SecretStr | None = None


def _password_problem(env_name: str, password: str) -> str | None:
    """Why login could never accept this password, if it couldn't."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"{env_name} must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"{env_name} must be at most {MAX_PASSWORD_LENGTH} characters."
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return f"{env_name} contains characters that can't be encoded."
    return None


@dataclass(frozen=True)
class DemoAccount:
    email: str
    role: UserRole
    password_env: str
    given_password: str | None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("seed-demo", help="Create a demo school with an admin and a teacher")
    seed.add_argument("--school", type=_school_name, default="Demo School")
    seed.add_argument("--admin-email", type=_email, default="admin@demo.example")
    seed.add_argument("--teacher-email", type=_email, default="teacher@demo.example")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.admin_email.casefold() == args.teacher_email.casefold():
        parser.error("--admin-email and --teacher-email must be different")
    try:
        settings = Settings()  # values come from the environment
    except ValidationError:
        print(
            "Settings are incomplete: check APP_ENV, JWT_SECRET and DATABASE_URL.", file=sys.stderr
        )
        return 1
    if settings.app_env == "production":
        print("Refusing to create demo accounts in production.", file=sys.stderr)
        return 1

    passwords = DemoPasswords()
    accounts = [
        DemoAccount(
            args.admin_email,
            UserRole.ADMIN,
            "DEMO_ADMIN_PASSWORD",
            _reveal(passwords.demo_admin_password),
        ),
        DemoAccount(
            args.teacher_email,
            UserRole.TEACHER,
            "DEMO_TEACHER_PASSWORD",
            _reveal(passwords.demo_teacher_password),
        ),
    ]
    for account in accounts:
        if account.given_password is None:
            continue
        problem = _password_problem(account.password_env, account.given_password)
        if problem:
            print(problem, file=sys.stderr)
            return 1

    for line in asyncio.run(_seed_demo(settings, args.school, accounts)):
        print(line)
    return 0


def _reveal(secret: SecretStr | None) -> str | None:
    return secret.get_secret_value() if secret is not None else None


async def _seed_demo(
    settings: Settings, school_name: str, accounts: list[DemoAccount]
) -> list[str]:
    """Creates missing accounts only. Existing accounts are never changed, so running this
    again can't reset anyone's password."""
    engine = create_engine(settings)
    report: list[str] = []
    try:
        async with create_session_factory(engine)() as session:
            # Names aren't unique, so always reuse the oldest school with this name.
            school = await session.scalar(
                select(School)
                .where(School.name == school_name)
                .order_by(School.created_at, School.id)
                .limit(1)
            )
            if school is None:
                school = School(name=school_name)
                session.add(school)
                await session.flush()

            for account in accounts:
                if await get_user_by_email(session, account.email) is not None:
                    report.append(f"{account.role:7} {account.email} already exists; unchanged")
                    continue
                given = account.given_password
                password = given or secrets.token_urlsafe(18)
                session.add(
                    User(
                        school_id=school.id,
                        email=account.email,
                        password_hash=hash_password(password),
                        role=account.role,
                    )
                )
                if given:
                    report.append(
                        f"{account.role:7} {account.email} created ({account.password_env})"
                    )
                else:
                    report.append(f"{account.role:7} {account.email}  password: {password}")
            await session.commit()
    finally:
        await engine.dispose()
    return report


if __name__ == "__main__":
    sys.exit(main())
