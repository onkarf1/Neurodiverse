from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class School(IdMixin, TimestampMixin, Base):
    """A tenant. All teacher and learner data belongs to exactly one school."""

    __tablename__ = "schools"

    name: Mapped[str] = mapped_column(String(200))
