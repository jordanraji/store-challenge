import asyncio
import hashlib
import json
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.catalog.service import consume_stock
from app.core.errors import DomainError
from app.orders.repository import OrderRepository
from app.orders.schemas import OrderInput, OrderLineOutput, OrderOutput

repository = OrderRepository()


async def create_order(
    factory: async_sessionmaker[AsyncSession], client_id: str, key: str, data: OrderInput
) -> dict[str, Any]:
    quantities: dict[int, int] = defaultdict(int)
    for item in data.items:
        quantities[item.product_id] += item.quantity
    if any(quantity > 10000 for quantity in quantities.values()):
        raise DomainError(422, "invalid_quantity", "Combined quantity exceeds 10000")
    payload = sorted(quantities.items())
    fingerprint = hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
    for attempt in range(3):
        try:
            async with factory.begin() as session:
                return await _purchase(session, client_id, key, fingerprint, quantities)
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) not in {"40P01", "40001"}:
                raise
            if attempt == 2:
                raise DomainError(
                    503, "transaction_busy", "Please retry with the same idempotency key"
                ) from exc
            await asyncio.sleep(0.02 * (attempt + 1))
    raise RuntimeError("Unreachable retry state")


async def _purchase(
    session: AsyncSession, client_id: str, key: str, fingerprint: str, quantities: dict[int, int]
) -> dict[str, Any]:
    record_id = await repository.reserve_key(session, client_id, key, fingerprint)
    if record_id is None:
        existing = await repository.find_key(session, client_id, key)
        if existing is None or existing.response is None:
            raise DomainError(409, "request_in_progress", "Retry with the same key")
        if existing.request_hash != fingerprint:
            raise DomainError(
                409, "idempotency_conflict", "Key already used with different content"
            )
        return existing.response
    lines = [
        await consume_stock(session, product_id, quantities[product_id])
        for product_id in sorted(quantities)
    ]
    total = sum((line["unit_price"] * line["quantity"] for line in lines), Decimal("0.00"))
    order = await repository.create(session, client_id, total, lines)
    result = OrderOutput(
        id=order.id,
        status=order.status,
        currency=order.currency,
        total=total,
        items=[OrderLineOutput.model_validate(line) for line in lines],
    ).model_dump(mode="json")
    await repository.save_response(session, record_id, result)
    return result
