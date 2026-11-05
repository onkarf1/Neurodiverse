"""All models are imported here so Alembic and the app see the complete schema."""

from app.models.goal import Accommodation, Goal
from app.models.school import School
from app.models.user import User, UserRole
from app.models.worksheet import Worksheet

__all__ = ["Accommodation", "Goal", "School", "User", "UserRole", "Worksheet"]
