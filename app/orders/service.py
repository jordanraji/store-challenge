import hashlib
import json
import time
from collections import defaultdict
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.service import consume_stock
from app.core.errors import DomainError
from app.orders.models import IdempotencyRecord, Order, OrderLine
from app.orders.schemas import OrderInput, OrderLineOutput, OrderOutput


def create_order(
    factory: sessionmaker, client_id: str, key: str, data: OrderInput
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
            with factory.begin() as session:
                return _purchase(session, client_id, key, fingerprint, quantities)
        except OperationalError as exc:
            if getattr(exc.orig, "sqlstate", None) not in {"40P01", "40001"}:
                raise
            if attempt == 2:
                raise DomainError(
                    503, "transaction_busy", "Please retry with the same idempotency key"
                ) from exc
            time.sleep(0.02 * (attempt + 1))
    raise RuntimeError("Unreachable retry state")


def _purchase(
    session: Session, client_id: str, key: str, fingerprint: str, quantities: dict[int, int]
) -> dict[str, Any]:
    record_id = session.scalar(
        insert(IdempotencyRecord)
        .values(client_id=client_id, key=key, request_hash=fingerprint)
        .on_conflict_do_nothing(constraint="uq_idempotency_client_key")
        .returning(IdempotencyRecord.id)
    )
    if record_id is None:
        existing = session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.client_id == client_id, IdempotencyRecord.key == key
            )
        )
        if existing is None or existing.response is None:
            raise DomainError(409, "request_in_progress", "Retry with the same key")
        if existing.request_hash != fingerprint:
            raise DomainError(
                409, "idempotency_conflict", "Key already used with different content"
            )
        return existing.response
    lines = [
        consume_stock(session, product_id, quantities[product_id])
        for product_id in sorted(quantities)
    ]
    total = sum((line["unit_price"] * line["quantity"] for line in lines), Decimal("0.00"))
    order = Order(client_id=client_id, total=total)
    session.add(order)
    session.flush()
    session.add_all([OrderLine(order_id=order.id, **line) for line in lines])
    result = OrderOutput(
        id=order.id,
        status=order.status,
        currency=order.currency,
        total=total,
        items=[OrderLineOutput.model_validate(line) for line in lines],
    ).model_dump(mode="json")
    record = session.get(IdempotencyRecord, record_id)
    if record is None:
        raise RuntimeError("Missing idempotency record")
    record.response = result
    session.flush()
    return result
