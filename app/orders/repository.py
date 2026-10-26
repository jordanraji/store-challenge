from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.orders.models import IdempotencyRecord, Order, OrderLine


class OrderRepository:
    async def reserve_key(
        self, session: AsyncSession, client_id: str, key: str, fingerprint: str
    ) -> int | None:
        return await session.scalar(
            insert(IdempotencyRecord)
            .values(client_id=client_id, key=key, request_hash=fingerprint)
            .on_conflict_do_nothing(constraint="uq_idempotency_client_key")
            .returning(IdempotencyRecord.id)
        )

    async def find_key(
        self, session: AsyncSession, client_id: str, key: str
    ) -> IdempotencyRecord | None:
        return await session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.client_id == client_id, IdempotencyRecord.key == key
            )
        )

    async def create(
        self, session: AsyncSession, client_id: str, total: Decimal, lines: list[dict[str, Any]]
    ) -> Order:
        order = Order(client_id=client_id, total=total)
        session.add(order)
        await session.flush()
        session.add_all([OrderLine(order_id=order.id, **line) for line in lines])
        return order

    async def save_response(
        self, session: AsyncSession, record_id: int, response: dict[str, Any]
    ) -> None:
        record = await session.get(IdempotencyRecord, record_id)
        if record is None:
            raise RuntimeError("Missing idempotency record")
        record.response = response
        await session.flush()
