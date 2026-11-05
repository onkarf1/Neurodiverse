import pytest
from pydantic import ValidationError

from app.schemas.auth import LoginRequest

# Validated from Python values, not JSON, so these test our own rules directly rather than
# relying on how the JSON parser happens to treat these characters.


@pytest.mark.parametrize(
    "email",
    ["te\x00@example.com", "te\ud800@example.com", "teacher@example.com\n", "te\x1b@example.com"],
    ids=["NUL", "lone surrogate", "newline", "escape"],
)
def test_email_with_unstorable_characters_is_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"email": email, "password": "x"})


def test_password_that_cannot_be_encoded_is_rejected() -> None:
    with pytest.raises(ValidationError):
        LoginRequest.model_validate({"email": "a@example.com", "password": "pa\ud800ss"})


@pytest.mark.parametrize(
    "password",
    ["with spaces and \u00e9", "tab\there", "nul\x00inside"],
    ids=["unicode", "tab", "NUL"],
)
def test_unusual_but_encodable_passwords_are_accepted(password: str) -> None:
    # Only unencodable text is refused; any character a person can type stays allowed.
    assert LoginRequest.model_validate({"email": "a@example.com", "password": password})
