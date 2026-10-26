from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from testcontainers.community.postgres import PostgresContainer

from app.main import create_app


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17.6", driver="psycopg") as postgres:
        url = postgres.get_connection_url()
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", url)
        command.upgrade(config, "head")
        yield url


@pytest.fixture
def app(database_url):
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE import_batches, idempotency_records, order_lines, orders, products RESTART IDENTITY CASCADE"
            )
        )
    engine.dispose()
    return create_app(database_url)


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
