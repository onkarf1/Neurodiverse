import enum

from sqlalchemy import Enum, Index, String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SchoolScopedMixin, TimestampMixin


class UserRole(enum.StrEnum):
    TEACHER = "teacher"
    ADMIN = "admin"


class User(IdMixin, TimestampMixin, SchoolScopedMixin, Base):
    __tablename__ = "users"
    # Lets other tables require that a referenced user belongs to the same school.
    __table_args__ = (UniqueConstraint("id", "school_id"),)

    email: Mapped[str] = mapped_column(String(320))
    password_hash: Mapped[str] = mapped_column(String(255))
    # Stored as text with a CHECK constraint. Adding a role needs a migration that updates
    # the constraint; Alembic can't detect this, so a test saves every role to catch it.
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            length=20,
            values_callable=lambda roles: [role.value for role in roles],
        )
    )
    is_active: Mapped[bool] = mapped_column(server_default=true())


# Defined after the class so it indexes the email column, not the literal string "email".
Index("uq_users_email_lower", func.lower(User.email), unique=True)
