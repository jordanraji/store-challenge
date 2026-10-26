from alembic import context
from sqlalchemy import create_engine, pool

from app.catalog.models import Product
from app.core.config import Settings
from app.core.database import Base
from app.imports.models import ImportBatch
from app.orders.models import IdempotencyRecord, Order, OrderLine

__all__ = ["Product", "Order", "OrderLine", "IdempotencyRecord", "ImportBatch"]
config = context.config
url = config.get_main_option("sqlalchemy.url") or Settings().database_url

if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
