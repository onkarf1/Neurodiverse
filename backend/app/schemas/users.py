import uuid

from pydantic import BaseModel

from app.models import UserRole


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool


class UserPage(BaseModel):
    items: list[UserSummary]
    limit: int
    offset: int
