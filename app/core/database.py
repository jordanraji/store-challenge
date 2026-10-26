from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import Settings


class Base(DeclarativeBase):
    pass


class PostgreSQLClient:
    def __init__(self, database_url: str, settings: Settings, echo: bool = False) -> None:
        self.engine = create_async_engine(
            database_url,
            echo=echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout_seconds,
            pool_pre_ping=True,
            pool_recycle=settings.db_pool_recycle_seconds,
            connect_args={
                "timeout": settings.db_connect_timeout_seconds,
                "command_timeout": settings.db_command_timeout_seconds,
                "server_settings": {"statement_timeout": str(settings.db_statement_timeout_ms)},
            },
        )
        self.sessionmaker = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.sessionmaker() as session:
            yield session

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.sessionmaker.begin() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()
