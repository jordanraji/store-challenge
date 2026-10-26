from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request

from app.orders.schemas import OrderInput, OrderOutput
from app.orders.service import create_order

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOutput, status_code=201)
async def purchase(
    data: OrderInput,
    request: Request,
    client_id: Annotated[UUID, Header(alias="X-Client-ID")],
    key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=128, pattern="^[A-Za-z0-9._:-]+$"),
    ],
) -> Any:
    return await create_order(request.app.state.primary_db.sessionmaker, str(client_id), key, data)
