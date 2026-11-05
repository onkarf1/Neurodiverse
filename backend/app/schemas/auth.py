import unicodedata
import uuid
from typing import Literal

from pydantic import BaseModel, Field, SecretStr, field_validator

from app.models import UserRole


def _has_category(value: str, categories: set[str]) -> bool:
    return any(unicodedata.category(char) in categories for char in value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    # SecretStr keeps the password out of reprs and logs; the length cap bounds hashing work.
    password: SecretStr = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _email_is_storable(cls, value: str) -> str:
        # Control characters (including NUL, which Postgres rejects) never belong in an email.
        # Lone surrogates are already refused by Pydantic for length-limited strings; tests
        # cover both, so a change in either would be caught.
        if _has_category(value, {"Cc"}):
            raise ValueError("Email contains characters that aren't allowed.")
        return value

    @field_validator("password", mode="before")
    @classmethod
    def _password_is_encodable(cls, value: object) -> object:
        if isinstance(value, str) and _has_category(value, {"Cs"}):
            raise ValueError("Password contains characters that can't be encoded.")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105  (OAuth2 token type, not a secret)
    expires_in: int = Field(description="Seconds until the token expires.")


class CurrentUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    school_id: uuid.UUID
