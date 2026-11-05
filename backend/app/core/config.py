from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class Settings(BaseSettings):
    """Runtime configuration, read from environment variables or a local .env file.

    Connection strings and keys are SecretStr so they never appear when settings are printed.
    APP_ENV has no default, so a deployment can't silently run in development mode.
    """

    # hide_input_in_errors keeps secrets out of the error printed when startup validation fails.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "test", "production"]
    log_level: LogLevel = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)

    jwt_secret: SecretStr = Field(min_length=32)
    database_url: SecretStr
    redis_url: SecretStr = SecretStr("redis://localhost:6379/0")

    ai_base_url: str = "https://openai.rc.asu.edu/v1"
    ai_model: str = "qwen3-235b-a22b-instruct-2507"
    asu_air_api_key: SecretStr | None = None

    @field_validator("log_level", mode="before")
    @classmethod
    def _uppercase_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _check_production_safety(self) -> Self:
        if self.app_env == "production" and "*" in self.cors_origins:
            raise ValueError("CORS_ORIGINS must list explicit origins in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()  # values come from the environment
