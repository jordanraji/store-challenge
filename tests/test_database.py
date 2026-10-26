import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.catalog.models import Product
from app.core.config import Settings
from app.core.database import PostgreSQLClient
from app.main import create_app


def test_async_client_pool_limits_and_server_timeout(client, app):
    async def verify():
        settings = Settings(
            database_url=app.state.database_url,
            db_pool_size=1,
            db_max_overflow=0,
            db_pool_timeout_seconds=0.05,
            db_statement_timeout_ms=30,
        )
        database = PostgreSQLClient(app.state.database_url, settings)
        try:
            async with database.get_db() as first:
                await first.execute(text("SELECT 1"))
                assert database.engine.pool.size() == 1
                async with database.get_db() as second:
                    with pytest.raises(PoolTimeout):
                        await second.execute(text("SELECT 1"))
            async with database.get_db() as session:
                timeout = await session.scalar(text("SHOW statement_timeout"))
                assert timeout == "30ms"
                with pytest.raises(DBAPIError) as error:
                    await session.execute(text("SELECT pg_sleep(0.2)"))
                assert error.value.orig.sqlstate == "57014"
            assert database.engine.pool.checkedout() == 0
            async with database.get_db() as session:
                assert await session.scalar(text("SELECT 1")) == 1
        finally:
            await database.close()

    client.portal.call(verify)


def test_cancelled_transaction_rolls_back_and_releases_connection(client, app, product_data):
    async def verify():
        database = app.state.primary_db
        inserted = asyncio.Event()
        wait = asyncio.Event()

        async def write():
            async with database.transaction() as session:
                session.add(Product(**product_data))
                await session.flush()
                inserted.set()
                await wait.wait()

        task = asyncio.create_task(write())
        try:
            await asyncio.wait_for(inserted.wait(), timeout=5)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        async with database.get_db() as session:
            assert await session.scalar(select(Product)) is None
        assert database.engine.pool.checkedout() == 0

    client.portal.call(verify)
    assert client.get("/api/products").json()["total"] == 0


def test_lifespan_creates_and_disposes_pool(app):
    application = create_app(app.state.database_url)
    assert not hasattr(application.state, "primary_db")
    with TestClient(application) as client:
        assert client.get("/health/ready").status_code == 200
        database = application.state.primary_db
        pool = database.engine.pool
    assert database.engine.pool is not pool
    assert pool.checkedout() == 0
