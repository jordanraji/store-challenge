from decimal import Decimal
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.catalog.repository import ProductRepository
from app.catalog.schemas import ProductInput, ProductUpdate
from app.core.errors import DomainError

repository = ProductRepository()


async def get_product(session: AsyncSession, product_id: int) -> Product:
    product = await repository.get_active(session, product_id)
    if product is None:
        raise DomainError(404, "product_not_found", "Product not found")
    return product


async def create_product(session: AsyncSession, data: ProductInput) -> Product:
    try:
        product = await repository.create(session, data.model_dump())
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError(409, "duplicate_sku", "SKU already exists") from exc
        raise
    return product


async def update_product(session: AsyncSession, product_id: int, data: ProductUpdate) -> Product:
    await get_product(session, product_id)
    try:
        product = await repository.update(
            session, product_id, data.version, data.model_dump(exclude={"version"})
        )
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError(409, "duplicate_sku", "SKU already exists") from exc
        raise
    if product is None:
        raise DomainError(409, "stale_product", "Product changed; reload before editing")
    return product


async def delete_product(session: AsyncSession, product_id: int, version: int) -> None:
    await get_product(session, product_id)
    if not await repository.deactivate(session, product_id, version):
        raise DomainError(409, "stale_product", "Product changed; reload before deleting")


async def search_products(
    session: AsyncSession, query: str, page: int, page_size: int, category: str = ""
) -> dict[str, Any]:
    return await repository.search(session, query, page, page_size, category)


async def consume_stock(session: AsyncSession, product_id: int, quantity: int) -> dict[str, Any]:
    row = await repository.deduct_stock(session, product_id, quantity)
    if row is None:
        await get_product(session, product_id)
        raise DomainError(
            409, "insufficient_stock", "Insufficient stock", {"product_id": product_id}
        )
    return {
        "product_id": row["id"],
        "sku": row["sku"],
        "name": row["name"],
        "unit_price": Decimal(row["price"]),
        "quantity": quantity,
    }


async def list_categories(session: AsyncSession) -> list[str]:
    return await repository.list_categories(session)


async def existing_skus(session: AsyncSession, skus: list[str]) -> set[str]:
    return await repository.existing_skus(session, skus)
