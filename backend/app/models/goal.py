import uuid

from sqlalchemy import ForeignKeyConstraint, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SchoolScopedMixin, TimestampMixin


class Goal(IdMixin, TimestampMixin, SchoolScopedMixin, Base):
    """An approved learning goal. It has no learner name or identifier fields, but free-text
    fields could still contain them. Requirement (not yet implemented, issue #7): personal
    data must be redacted before any of this text is sent to an AI model."""

    __tablename__ = "goals"
    __table_args__ = (
        UniqueConstraint("id", "school_id"),
        # The author must belong to the goal's school; enforced by the database itself.
        ForeignKeyConstraint(
            ["created_by_id", "school_id"], ["users.id", "users.school_id"], ondelete="RESTRICT"
        ),
    )

    created_by_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    skill_description: Mapped[str] = mapped_column(Text)
    success_criteria: Mapped[str] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(server_default=false())


class Accommodation(IdMixin, TimestampMixin, SchoolScopedMixin, Base):
    """A support the learner must keep, such as visual step cards."""

    __tablename__ = "accommodations"
    __table_args__ = (
        ForeignKeyConstraint(
            ["goal_id", "school_id"], ["goals.id", "goals.school_id"], ondelete="CASCADE"
        ),
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(Text)
