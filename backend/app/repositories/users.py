import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Case-insensitive lookup that uses the unique index on lower(email).

    Both sides are lowercased by Postgres: Python's str.lower() differs for some letters
    (for example the dotted capital I), which would make those accounts unreachable.
    """
    return await session.scalar(select(User).where(func.lower(User.email) == func.lower(email)))


async def get_user_by_id(session: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await session.get(User, user_id)


async def set_password_hash(session: AsyncSession, user_id: uuid.UUID, password_hash: str) -> None:
    await session.execute(
        update(User).where(User.id == user_id).values(password_hash=password_hash)
    )
