import uuid
from typing import Literal

from pydantic import BaseModel, Field, SecretStr

from app.models import UserRole


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    # SecretStr keeps the password out of reprs and logs; the length cap bounds hashing work.
    password: SecretStr = Field(min_length=1, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int = Field(description="Seconds until the token expires.")


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    school_id: uuid.UUID
