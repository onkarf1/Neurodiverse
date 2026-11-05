import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.helpers import TEST_DB_URL, TEST_SECRET, make_settings


def test_missing_jwt_secret_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="development", database_url=TEST_DB_URL)


def test_missing_app_env_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    # No silent fallback to development, which would expose /docs and drop strict headers.
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None, jwt_secret=TEST_SECRET, database_url=TEST_DB_URL)


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(log_level="LOUD")


def test_log_level_is_case_insensitive() -> None:
    assert make_settings(log_level="debug").log_level == "DEBUG"


def test_short_jwt_secret_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_settings(jwt_secret="too-short")


def test_ai_defaults_point_to_asu_gateway() -> None:
    settings = make_settings()

    assert settings.ai_base_url == "https://openai.rc.asu.edu/v1"
    assert settings.ai_model == "qwen3-235b-a22b-instruct-2507"


def test_secrets_are_hidden_when_settings_are_printed() -> None:
    settings = make_settings(redis_url="redis://:redis-password@localhost:6379/0")

    for text in (repr(settings), str(settings), settings.model_dump_json()):
        for secret in (TEST_SECRET, "test-db-password", "redis-password"):
            assert secret not in text


def test_production_rejects_wildcard_cors() -> None:
    with pytest.raises(ValidationError):
        make_settings(app_env="production", cors_origins=["*"])


def test_startup_validation_errors_do_not_reveal_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, jwt_secret=TEST_SECRET, database_url=TEST_DB_URL)

    message = str(error.value)
    assert TEST_SECRET[:8] not in message
    assert "test-db-password" not in message


def test_database_connect_timeout_defaults_to_five_seconds() -> None:
    assert make_settings().db_connect_timeout_seconds == 5
