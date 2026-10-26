import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.models import Product
from app.catalog.schemas import ProductInput
from app.catalog.service import create_product
from app.core.errors import DomainError
from app.imports.models import ImportBatch

COLUMNS = {"name", "sku", "description", "category", "price", "stock", "weight_kg"}
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 1000


@dataclass
class ImportPreview:
    products: list[tuple[int, ProductInput]]
    errors: list[dict[str, Any]]
    total_rows: int


def preview_products(session: Session, content: bytes) -> ImportPreview:
    if len(content) > MAX_BYTES:
        raise DomainError(413, "file_too_large", "CSV exceeds 2 MiB")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        if (
            reader.fieldnames is None
            or len(reader.fieldnames) != len(COLUMNS)
            or set(reader.fieldnames) != COLUMNS
        ):
            raise DomainError(
                422,
                "invalid_columns",
                "CSV must contain exactly the expected columns",
                sorted(COLUMNS),
            )
        products: list[tuple[int, ProductInput]] = []
        errors: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        total_rows = 0
        for number, row in enumerate(reader, start=2):
            total_rows += 1
            if total_rows > MAX_ROWS:
                raise DomainError(422, "too_many_rows", "CSV exceeds 1000 rows")
            identity = {
                "row": number,
                "sku": str(row.get("sku") or "")[:64],
                "name": str(row.get("name") or "")[:200],
            }
            try:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("Unexpected number of columns")
                stock = row["stock"].strip()
                row["stock"] = int(stock) if stock.isascii() and stock.isdigit() else stock
                row["price"] = row["price"].strip().removeprefix("$")
                product = ProductInput.model_validate(row)
                if product.sku in seen:
                    raise ValueError(
                        f"Duplicate SKU within CSV; first valid occurrence is row {seen[product.sku]}"
                    )
                seen[product.sku] = number
                products.append((number, product))
            except ValidationError as exc:
                errors.append(
                    {
                        **identity,
                        "errors": [
                            {
                                "field": ".".join(map(str, error["loc"])),
                                "value": str(error.get("input", ""))[:160],
                                "message": error["msg"],
                            }
                            for error in exc.errors()
                        ],
                    }
                )
            except ValueError as exc:
                errors.append({**identity, "message": str(exc)})
        if not total_rows:
            raise DomainError(422, "empty_csv", "CSV contains no products")
        existing = set(session.scalars(select(Product.sku).where(Product.sku.in_(seen))).all())
        errors.extend(
            {
                "row": number,
                "message": "SKU already exists",
                "sku": product.sku,
                "name": product.name,
            }
            for number, product in products
            if product.sku in existing
        )
        valid = [(number, product) for number, product in products if product.sku not in existing]
        return ImportPreview(valid, sorted(errors, key=lambda error: error["row"]), total_rows)
    except (UnicodeDecodeError, csv.Error) as exc:
        raise DomainError(422, "invalid_csv", "CSV must be valid UTF-8 with valid quoting") from exc


def import_products(
    session: Session, content: bytes, allow_partial: bool = False
) -> dict[str, int]:
    preview = preview_products(session, content)
    if preview.errors and (not allow_partial or not preview.products):
        raise DomainError(
            422, "invalid_csv", "No products imported; correct the reported rows", preview.errors
        )
    for _, product in preview.products:
        create_product(session, product)
    result = {"imported": len(preview.products)}
    if allow_partial:
        result["skipped"] = len(preview.errors)
    return result


def stage_import(
    session: Session, owner_id: str, filename: str, preview: ImportPreview
) -> ImportBatch:
    batch = ImportBatch(
        owner_id=owner_id,
        filename=filename[:255],
        products=[
            {"row": number, "data": product.model_dump(mode="json")}
            for number, product in preview.products
        ],
        errors=preview.errors,
        total_rows=preview.total_rows,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    session.add(batch)
    session.flush()
    return batch


def get_batch(session: Session, batch_id: UUID, owner_id: str) -> ImportBatch:
    batch = session.scalar(
        select(ImportBatch)
        .where(ImportBatch.id == batch_id, ImportBatch.owner_id == owner_id)
        .with_for_update()
    )
    if batch is None:
        raise DomainError(
            404, "import_not_found", "This import was not found. Upload your CSV again."
        )
    return batch


def confirm_import(session: Session, batch_id: UUID, owner_id: str) -> dict[str, int]:
    batch = get_batch(session, batch_id, owner_id)
    if batch.status == "completed":
        return {"imported": batch.imported, "skipped": len(batch.errors)}
    if batch.status == "cancelled":
        raise DomainError(
            409, "import_cancelled", "This import was cancelled. Upload your CSV again."
        )
    if batch.expires_at <= datetime.now(UTC):
        raise DomainError(
            410, "import_expired", "This review expired after 30 minutes. Upload your CSV again."
        )
    if not batch.products:
        raise DomainError(
            422,
            "no_valid_rows",
            "There are no valid rows to import. Correct your CSV and upload it again.",
        )
    try:
        products = [
            (row["row"], ProductInput.model_validate(row["data"])) for row in batch.products
        ]
    except ValidationError as exc:
        raise DomainError(
            409,
            "import_rules_changed",
            "Some reviewed rows no longer pass validation. Upload the CSV again to review the errors.",
        ) from exc
    existing = set(
        session.scalars(
            select(Product.sku).where(Product.sku.in_([product.sku for _, product in products]))
        ).all()
    )
    if existing:
        raise DomainError(
            409,
            "import_inventory_changed",
            "Inventory changed since review. Nothing was imported. Upload the CSV again to review the new errors.",
            [
                {"row": number, "sku": product.sku, "message": "SKU now exists"}
                for number, product in products
                if product.sku in existing
            ],
        )
    for _, product in products:
        create_product(session, product)
    batch.status = "completed"
    batch.imported = len(products)
    session.flush()
    return {"imported": batch.imported, "skipped": len(batch.errors)}


def cancel_import(session: Session, batch_id: UUID, owner_id: str) -> None:
    batch = get_batch(session, batch_id, owner_id)
    if batch.status == "completed":
        raise DomainError(
            409, "import_completed", "This import is already complete and cannot be cancelled."
        )
    batch.status = "cancelled"
    batch.products = []
