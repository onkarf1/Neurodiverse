import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Accommodation, Goal, School, User, UserRole, Worksheet

pytestmark = pytest.mark.anyio


async def _school(session: AsyncSession, name: str = "North Campus") -> School:
    school = School(name=name)
    session.add(school)
    await session.flush()
    return school


async def _teacher(session: AsyncSession, school: School, email: str = "t@example.com") -> User:
    user = User(school_id=school.id, email=email, password_hash="hash", role=UserRole.TEACHER)
    session.add(user)
    await session.flush()
    return user


async def _goal(session: AsyncSession, school: School, author: User) -> Goal:
    goal = Goal(
        school_id=school.id,
        created_by_id=author.id,
        title="Plan a three-step workplace task",
        skill_description="Orders the steps of a familiar task before starting.",
        success_criteria="Correct order in 4 of 5 trials.",
    )
    session.add(goal)
    await session.flush()
    return goal


async def test_school_data_round_trips(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    teacher = await _teacher(db_session, school)
    goal = await _goal(db_session, school, teacher)
    db_session.add_all(
        [
            Accommodation(school_id=school.id, goal_id=goal.id, description="Visual step cards"),
            Worksheet(school_id=school.id, goal_id=goal.id, title="Kit packing", content="..."),
        ]
    )
    await db_session.flush()
    db_session.expunge_all()

    saved = await db_session.scalar(select(Goal).where(Goal.id == goal.id))

    assert saved is not None
    assert isinstance(saved.id, uuid.UUID)
    assert saved.created_at is not None
    assert saved.is_archived is False
    accommodations = await db_session.scalars(
        select(Accommodation).where(Accommodation.goal_id == goal.id)
    )
    assert [a.description for a in accommodations] == ["Visual step cards"]


async def test_records_require_a_school(db_session: AsyncSession) -> None:
    db_session.add(User(email="x@example.com", password_hash="hash", role=UserRole.TEACHER))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_worksheet_cannot_link_to_another_schools_goal(db_session: AsyncSession) -> None:
    school_a = await _school(db_session, "School A")
    school_b = await _school(db_session, "School B")
    goal_a = await _goal(db_session, school_a, await _teacher(db_session, school_a))

    db_session.add(Worksheet(school_id=school_b.id, goal_id=goal_a.id, title="x", content="y"))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_goal_author_must_belong_to_the_same_school(db_session: AsyncSession) -> None:
    school_a = await _school(db_session, "School A")
    school_b = await _school(db_session, "School B")
    teacher_b = await _teacher(db_session, school_b)

    with pytest.raises(IntegrityError):
        await _goal(db_session, school_a, teacher_b)


async def test_emails_are_unique_ignoring_case(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    await _teacher(db_session, school, "Teacher@Example.com")

    with pytest.raises(IntegrityError):
        await _teacher(db_session, school, "teacher@example.com")


async def test_different_emails_can_coexist(db_session: AsyncSession) -> None:
    school = await _school(db_session)

    await _teacher(db_session, school, "first@example.com")
    await _teacher(db_session, school, "second@example.com")


@pytest.mark.parametrize("role", list(UserRole))
async def test_database_accepts_every_role_in_the_model(
    db_session: AsyncSession, role: UserRole
) -> None:
    # Alembic can't detect new values on non-native enums, so this catches a role added to
    # the model without a migration that updates the database CHECK constraint.
    school = await _school(db_session)
    db_session.add(
        User(school_id=school.id, email=f"{role}@example.com", password_hash="h", role=role)
    )

    await db_session.flush()


async def test_database_rejects_unknown_roles(db_session: AsyncSession) -> None:
    school = await _school(db_session)

    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO users (id, school_id, email, password_hash, role) "
                "VALUES (gen_random_uuid(), :school_id, 'x@example.com', 'hash', 'superuser')"
            ),
            {"school_id": school.id},
        )


async def test_deleting_a_goal_removes_its_accommodations(db_session: AsyncSession) -> None:
    school = await _school(db_session)
    goal = await _goal(db_session, school, await _teacher(db_session, school))
    db_session.add(Accommodation(school_id=school.id, goal_id=goal.id, description="Extra time"))
    await db_session.flush()

    await db_session.delete(goal)
    await db_session.flush()

    remaining = await db_session.scalars(
        select(Accommodation).where(Accommodation.goal_id == goal.id)
    )
    assert remaining.all() == []
