from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.security import validate_plain_text

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Sku = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$"
    ),
]
Category = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2, allow_inf_nan=False)]
Weight = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3, allow_inf_nan=False)]


class ProductFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: Name
    sku: Sku
    description: str = Field(default="", max_length=5000)
    category: Category
    price: Money
    stock: int = Field(ge=0, le=2147483647, strict=True)
    weight_kg: Weight

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.upper()


class ProductInput(ProductFields):
    @field_validator("name", "description", "category")
    @classmethod
    def plain_text_only(cls, value: str) -> str:
        return validate_plain_text(value)


class ProductUpdate(ProductInput):
    version: int = Field(gt=0, strict=True)


class ProductOutput(ProductFields):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    active: bool


class ProductPage(BaseModel):
    items: list[ProductOutput]
    total: int
    page: int
    page_size: int
