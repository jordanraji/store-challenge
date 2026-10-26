from collections.abc import Iterable
from typing import Any

from sqlalchemy import RowMapping, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product


class ProductRepository:
    async def get_active(self, session: AsyncSession, product_id: int) -> Product | None:
        return await session.scalar(select(Product).where(Product.id == product_id, Product.active))

    async def create(self, session: AsyncSession, values: dict[str, Any]) -> Product:
        product = Product(**values)
        session.add(product)
        await session.flush()
        return product

    async def update(
        self, session: AsyncSession, product_id: int, version: int, values: dict[str, Any]
    ) -> Product | None:
        product = await session.scalar(
            update(Product)
            .where(Product.id == product_id, Product.active, Product.version == version)
            .values(**values, version=Product.version + 1)
            .returning(Product)
            .execution_options(populate_existing=True)
        )
        await session.flush()
        return product

    async def deactivate(self, session: AsyncSession, product_id: int, version: int) -> bool:
        return (
            await session.scalar(
                update(Product)
                .where(Product.id == product_id, Product.active, Product.version == version)
                .values(active=False, version=Product.version + 1)
                .returning(Product.id)
            )
            is not None
        )

    async def deduct_stock(
        self, session: AsyncSession, product_id: int, quantity: int
    ) -> RowMapping | None:
        return (
            (
                await session.execute(
                    update(Product)
                    .where(Product.id == product_id, Product.active, Product.stock >= quantity)
                    .values(stock=Product.stock - quantity, version=Product.version + 1)
                    .returning(Product.id, Product.sku, Product.name, Product.price)
                )
            )
            .mappings()
            .one_or_none()
        )

    async def existing_skus(self, session: AsyncSession, skus: Iterable[str]) -> set[str]:
        return set(
            (await session.scalars(select(Product.sku).where(Product.sku.in_(list(skus))))).all()
        )

    async def search(
        self, session: AsyncSession, query: str, page: int, page_size: int, category: str = ""
    ) -> dict[str, Any]:
        statement = select(Product).where(Product.active)
        if category:
            statement = statement.where(Product.category == category)
        if query:
            normalized = func.unaccent(func.lower(query))
            document = Product.search_document
            terms = func.plainto_tsquery("simple", normalized)
            name = Product.search_name
            sku_match = Product.sku == query.upper()
            similarity = func.similarity(name, normalized)
            statement = statement.where(
                or_(sku_match, document.op("@@")(terms), name.bool_op("%")(normalized))
            )
            statement = statement.order_by(
                case((sku_match, 1), else_=0).desc(),
                func.ts_rank_cd(document, terms).desc(),
                similarity.desc(),
            )
        total = await session.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        products = (
            await session.scalars(
                statement.order_by(Product.id).offset((page - 1) * page_size).limit(page_size)
            )
        ).all()
        return {"items": products, "total": total, "page": page, "page_size": page_size}

    async def list_categories(self, session: AsyncSession) -> list[str]:
        return list(
            (
                await session.scalars(
                    select(Product.category)
                    .where(Product.active)
                    .distinct()
                    .order_by(Product.category)
                )
            ).all()
        )
