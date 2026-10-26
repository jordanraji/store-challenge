from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: int = Field(gt=0, strict=True)
    quantity: int = Field(gt=0, le=10000, strict=True)


class OrderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[OrderItem] = Field(min_length=1, max_length=100)


class OrderLineOutput(OrderItem):
    sku: str
    name: str
    unit_price: Decimal


class OrderOutput(BaseModel):
    id: UUID
    status: str
    currency: str
    total: Decimal
    items: list[OrderLineOutput]
