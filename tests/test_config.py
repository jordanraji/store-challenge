import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "postgresql://user:secret@localhost/store",
        "postgresql+psycopg://user:secret@localhost/store",
        "postgresql+asyncpg://localhost/store",
        "postgresql+asyncpg://user:secret@localhost",
        "postgresql+asyncpg://user:secret@localhost:0/store",
        "postgresql+asyncpg://user:secret@localhost:65536/store",
        "postgresql+asyncpg://user:secret@localhost:invalid/store",
        " postgresql+asyncpg://user:secret@localhost/store",
    ],
)
def test_invalid_connection_config_is_rejected_without_exposing_password(url, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_url=url)
    assert "secret" not in str(error.value)
    assert "DATABASE_URL must be" in str(error.value)


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="Field required"):
        Settings(_env_file=None)


def test_environment_url_and_explicit_factory_override(monkeypatch):
    url = "postgresql+asyncpg://reader:p%40ss@127.0.0.1:5432/catalog"
    monkeypatch.setenv("DATABASE_URL", url)
    settings = Settings(_env_file=None)
    assert settings.database_url == url
    assert "p%40ss" not in repr(settings)
    monkeypatch.setenv("DATABASE_URL", "invalid")
    assert create_app(url).state.database_url == url


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan")])
def test_pool_wait_must_be_finite_and_positive(value):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:password@localhost/store",
            db_pool_timeout_seconds=value,
        )
