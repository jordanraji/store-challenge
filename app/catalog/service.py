from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.catalog.schemas import ProductInput, ProductUpdate
from app.core.errors import DomainError


def get_product(session: Session, product_id: int) -> Product:
    product = session.scalar(select(Product).where(Product.id == product_id, Product.active))
    if product is None:
        raise DomainError(404, "product_not_found", "Product not found")
    return product


def create_product(session: Session, data: ProductInput) -> Product:
    product = Product(**data.model_dump())
    session.add(product)
    try:
        session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError(409, "duplicate_sku", "SKU already exists") from exc
        raise
    return product


def update_product(session: Session, product_id: int, data: ProductUpdate) -> Product:
    get_product(session, product_id)
    try:
        product = session.scalar(
            update(Product)
            .where(Product.id == product_id, Product.active, Product.version == data.version)
            .values(**data.model_dump(exclude={"version"}), version=Product.version + 1)
            .returning(Product)
            .execution_options(populate_existing=True)
        )
        session.flush()
    except IntegrityError as exc:
        if getattr(exc.orig, "sqlstate", None) == "23505":
            raise DomainError(409, "duplicate_sku", "SKU already exists") from exc
        raise
    if product is None:
        raise DomainError(409, "stale_product", "Product changed; reload before editing")
    return product


def delete_product(session: Session, product_id: int, version: int) -> None:
    get_product(session, product_id)
    result = session.scalar(
        update(Product)
        .where(Product.id == product_id, Product.active, Product.version == version)
        .values(active=False, version=Product.version + 1)
        .returning(Product.id)
    )
    if result is None:
        raise DomainError(409, "stale_product", "Product changed; reload before deleting")


def search_products(
    session: Session, query: str, page: int, page_size: int, category: str = ""
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
    total = session.scalar(select(func.count()).select_from(statement.order_by(None).subquery()))
    products = session.scalars(
        statement.order_by(Product.id).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {"items": products, "total": total, "page": page, "page_size": page_size}


def consume_stock(session: Session, product_id: int, quantity: int) -> dict[str, Any]:
    row = (
        session.execute(
            update(Product)
            .where(Product.id == product_id, Product.active, Product.stock >= quantity)
            .values(stock=Product.stock - quantity, version=Product.version + 1)
            .returning(Product.id, Product.sku, Product.name, Product.price)
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        get_product(session, product_id)
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


def list_categories(session: Session) -> list[str]:
    return list(
        session.scalars(
            select(Product.category).where(Product.active).distinct().order_by(Product.category)
        ).all()
    )
