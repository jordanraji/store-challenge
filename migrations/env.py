import asyncio

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from app.catalog.models import Product
from app.core.config import Settings
from app.core.database import Base
from app.imports.models import ImportBatch
from app.orders.models import IdempotencyRecord, Order, OrderLine

__all__ = ["Product", "Order", "OrderLine", "IdempotencyRecord", "ImportBatch"]
config = context.config
url = (config.get_main_option("sqlalchemy.url") or Settings().database_url).replace(
    "postgresql+psycopg://", "postgresql+asyncpg://"
)


def run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(run_online())
