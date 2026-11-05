from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin

SCHOOL_NAME_MAX_LENGTH = 200


class School(IdMixin, TimestampMixin, Base):
    """A tenant. All teacher and learner data belongs to exactly one school."""

    __tablename__ = "schools"

    name: Mapped[str] = mapped_column(String(SCHOOL_NAME_MAX_LENGTH))
