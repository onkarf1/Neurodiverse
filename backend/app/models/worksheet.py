import uuid

from sqlalchemy import ForeignKeyConstraint, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SchoolScopedMixin, TimestampMixin


class Worksheet(IdMixin, TimestampMixin, SchoolScopedMixin, Base):
    __tablename__ = "worksheets"
    __table_args__ = (
        # A worksheet can only link to a goal from its own school.
        ForeignKeyConstraint(
            ["goal_id", "school_id"], ["goals.id", "goals.school_id"], ondelete="RESTRICT"
        ),
    )

    goal_id: Mapped[uuid.UUID] = mapped_column(index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
