from typing import Any

from app.core.config import Settings

TEST_SECRET = "test-secret-that-is-at-least-32-characters"
TEST_DB_URL = "postgresql+asyncpg://test:test-db-password@localhost:5432/test"


def make_settings(**overrides: Any) -> Settings:
    """Builds settings for tests without reading the developer's local .env file."""
    values: dict[str, Any] = {
        "app_env": "development",
        "jwt_secret": TEST_SECRET,
        "database_url": TEST_DB_URL,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)
