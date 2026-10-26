from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.community.postgres import PostgresContainer

from app.main import create_app


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17.6", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(command.upgrade, config, "head").result(timeout=30)
        yield url


@pytest.fixture
def app(database_url, monkeypatch):
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-shared-across-isolated-apps")
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE import_batches, idempotency_records, order_lines, orders, products RESTART IDENTITY CASCADE"
            )
        )
    application = create_app(database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://"))
    application.state.test_session_factory = sessionmaker(engine, expire_on_commit=False)
    yield application
    engine.dispose()


@pytest.fixture
def client(app) -> Iterator[TestClient]:
    with TestClient(app) as client:
        yield client


@pytest.fixture
def product_data():
    return {
        "name": "Café Premium",
        "sku": "cf-001",
        "description": "Organic coffee beans",
        "category": "Food",
        "price": "12.50",
        "stock": 5,
        "weight_kg": "1.000",
    }
