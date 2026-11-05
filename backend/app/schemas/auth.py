import unicodedata
import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, SecretStr, field_validator

from app.core.constants import MAX_PASSWORD_LENGTH
from app.models import UserRole


def contains_category(value: str, *categories: str) -> bool:
    """True if any character is in one of the Unicode categories, for example "Cc" (control
    characters, including NUL) or "Cs" (lone surrogates, which can't be encoded as UTF-8)."""
    return any(unicodedata.category(char) in categories for char in value)


def _reject_control_characters(value: str) -> str:
    # Control characters (including NUL, which Postgres rejects) never belong in an email.
    # Lone surrogates are already refused by Pydantic for length-limited strings; tests
    # cover both, so a change in either would be caught.
    if contains_category(value, "Cc"):
        raise ValueError("Email contains characters that aren't allowed.")
    return value


# One definition for every place an email enters the system (login and account creation),
# so an account can never be created with an email that login would refuse.
EmailAddress = Annotated[
    str, Field(min_length=3, max_length=320), AfterValidator(_reject_control_characters)
]


class LoginRequest(BaseModel):
    email: EmailAddress
    # SecretStr keeps the password out of reprs and logs; the length cap bounds hashing work.
    password: SecretStr = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("password", mode="before")
    @classmethod
    def _password_is_encodable(cls, value: object) -> object:
        if isinstance(value, str) and contains_category(value, "Cs"):
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
