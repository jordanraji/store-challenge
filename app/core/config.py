from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True, allow_inf_nan=False
    )
    database_url: str = Field(repr=False)

    session_secret: str = ""
    secure_cookies: bool = False

    db_pool_size: int = Field(default=5, ge=1)
    db_max_overflow: int = Field(default=5, ge=0)
    db_pool_timeout_seconds: float = Field(default=10, gt=0)
    db_pool_recycle_seconds: int = Field(default=1800, ge=1)
    db_connect_timeout_seconds: float = Field(default=10, gt=0)
    db_command_timeout_seconds: float = Field(default=30, gt=0)
    db_statement_timeout_ms: int = Field(default=15000, ge=1)

    @field_validator("database_url")
    @classmethod
    def valid_database_url(cls, value: str) -> str:
        message = (
            "DATABASE_URL must be a postgresql+asyncpg URL with user, password, host and database"
        )
        if not value or value != value.strip() or any(ord(char) < 32 for char in value):
            raise ValueError(message)
        try:
            url = make_url(value)
            port = url.port
        except (ValueError, TypeError, ArgumentError) as exc:
            raise ValueError(message) from exc
        if (
            url.drivername != "postgresql+asyncpg"
            or not url.username
            or not url.password
            or not url.host
            or not url.database
            or (port is not None and not 1 <= port <= 65535)
        ):
            raise ValueError(message)
        return value
