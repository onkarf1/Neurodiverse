"""Fixtures for API tests that need real users in the database.

The app commits through its own connections, so these tests can't use a rolled-back
transaction. Instead every table is emptied before and after each test.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import Any, Protocol

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import pool, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

import app.models  # noqa: F401  (registers every model on Base.metadata)
from app.core.security import hash_password
from app.db.base import Base
from app.main import create_app
from app.models import School, User, UserRole
from tests.helpers import make_settings

TEST_PASSWORD = "correct horse battery staple 42"


@dataclass(frozen=True)
class SeededUser:
    id: uuid.UUID
    school_id: uuid.UUID
    email: str


class SeedUser(Protocol):
    def __call__(
        self,
        email: str = ...,
        *,
        role: UserRole = ...,
        is_active: bool = ...,
        password_hash: str | None = ...,
    ) -> SeededUser: ...


def run_in_database[T](url: str, work: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Runs `work` in its own committed transaction, outside the app."""

    async def main() -> T:
        engine = create_async_engine(url, poolclass=pool.NullPool)
        try:
            async with AsyncSession(engine, expire_on_commit=False) as session:
                result = await work(session)
                await session.commit()
                return result
        finally:
            await engine.dispose()

    return asyncio.run(main())


def update_user(url: str, user_id: uuid.UUID, **values: Any) -> None:
    async def work(session: AsyncSession) -> None:
        await session.execute(update(User).where(User.id == user_id).values(**values))

    run_in_database(url, work)


def read_password_hash(url: str, user_id: uuid.UUID) -> str:
    async def work(session: AsyncSession) -> str:
        return (await session.scalars(select(User.password_hash).where(User.id == user_id))).one()

    return run_in_database(url, work)


@pytest.fixture
def clean_database(migrated_database_url: str) -> Iterator[str]:
    # Table names come from our own models, not from user input.
    statement = text(f"TRUNCATE {', '.join(Base.metadata.tables)} CASCADE")  # noqa: S608

    async def truncate(session: AsyncSession) -> None:
        await session.execute(statement)

    run_in_database(migrated_database_url, truncate)
    yield migrated_database_url
    run_in_database(migrated_database_url, truncate)


@pytest.fixture
def seed_user(clean_database: str) -> SeedUser:
    school_ids: list[uuid.UUID] = []

    def seed(
        email: str = "teacher@example.com",
        *,
        role: UserRole = UserRole.TEACHER,
        is_active: bool = True,
        password_hash: str | None = None,
    ) -> SeededUser:
        async def work(session: AsyncSession) -> SeededUser:
            if not school_ids:
                school = School(name="Test School")
                session.add(school)
                await session.flush()
                school_ids.append(school.id)
            user = User(
                school_id=school_ids[0],
                email=email,
                password_hash=password_hash or hash_password(TEST_PASSWORD),
                role=role,
                is_active=is_active,
            )
            session.add(user)
            await session.flush()
            return SeededUser(user.id, school_ids[0], email)

        return run_in_database(clean_database, work)

    return seed


@pytest.fixture
def auth_client(clean_database: str) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(database_url=clean_database))) as client:
        yield client
