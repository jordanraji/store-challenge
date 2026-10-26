from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session
from starlette.datastructures import FormData, UploadFile
from starlette.responses import HTMLResponse, RedirectResponse, Response

from app.catalog import service as catalog
from app.catalog.schemas import ProductInput, ProductOutput, ProductUpdate
from app.core.dependencies import get_session
from app.core.errors import DomainError
from app.imports.service import (
    MAX_BYTES,
    cancel_import,
    confirm_import,
    import_products,
    preview_products,
    stage_import,
)
from app.orders.schemas import OrderInput
from app.orders.service import create_order
from app.web.presentation import render
from app.web.security import checked_form, initialize_session

router = APIRouter(include_in_schema=False)
SessionDependency = Annotated[Session, Depends(get_session, scope="function")]
FormDependency = Annotated[FormData, Depends(checked_form)]


def redirect(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def catalog_context(session: Session, q: str, category: str, page: int) -> dict[str, Any]:
    return {
        **catalog.search_products(session, q.strip(), page, 12, category),
        "q": q,
        "category": category,
        "categories": catalog.list_categories(session),
    }


@router.get("/", response_class=HTMLResponse)
def storefront(
    request: Request,
    session: SessionDependency,
    q: str = Query(default="", max_length=200),
    category: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=100000),
) -> HTMLResponse:
    template = (
        "partials/catalog.html"
        if request.headers.get("HX-Request")
        and not request.headers.get("HX-History-Restore-Request")
        else "store.html"
    )
    return render(request, template, **catalog_context(session, q, category, page))


@router.get("/products/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int, session: SessionDependency) -> HTMLResponse:
    return render(request, "product.html", product=catalog.get_product(session, product_id))


@router.post("/bag/items/{product_id}")
def add_to_bag(
    request: Request, product_id: int, session: SessionDependency, form: FormDependency
) -> Response:
    initialize_session(request)
    try:
        product = catalog.get_product(session, product_id)
        cart = dict(request.session["cart"])
        quantity = cart.get(str(product_id), 0) + 1
        if quantity > min(product.stock, 10000):
            raise DomainError(
                409, "insufficient_stock", "There are no more available units to add."
            )
        if len(cart) >= 100 and str(product_id) not in cart:
            raise DomainError(422, "cart_full", "Your bag can hold up to 100 different products.")
        cart[str(product_id)] = quantity
        request.session["cart"] = cart
        request.session.pop("purchase_key", None)
        message = f"{product.name} added to your bag."
        status = 200
    except DomainError as exc:
        message, status = exc.message, exc.status
    if request.headers.get("HX-Request"):
        return render(
            request, "partials/bag_update.html", status, message=message, failed=status != 200
        )
    request.session["notice"] = message
    return redirect("/bag")


def bag_context(request: Request, session: Session) -> dict[str, Any]:
    initialize_session(request)
    lines = []
    for product_id, quantity in request.session["cart"].items():
        try:
            product = catalog.get_product(session, int(product_id))
            lines.append(
                {
                    "product": product,
                    "product_id": int(product_id),
                    "quantity": quantity,
                    "subtotal": product.price * quantity,
                    "available": product.stock >= quantity,
                }
            )
        except DomainError:
            lines.append(
                {
                    "product": None,
                    "product_id": int(product_id),
                    "quantity": quantity,
                    "subtotal": Decimal("0.00"),
                    "available": False,
                }
            )
    total = sum((line["subtotal"] for line in lines), Decimal("0.00"))
    if "purchase_key" not in request.session:
        request.session["purchase_key"] = str(uuid4())
    return {
        "lines": lines,
        "total": total,
        "can_purchase": bool(lines) and all(line["available"] for line in lines),
        "purchase_key": request.session["purchase_key"],
    }


@router.get("/bag", response_class=HTMLResponse)
def bag(request: Request, session: SessionDependency) -> HTMLResponse:
    notice = request.session.pop("notice", None)
    return render(request, "bag.html", notice=notice, **bag_context(request, session))


@router.post("/bag/update")
def update_bag(request: Request, session: SessionDependency, form: FormDependency) -> Response:
    cart = dict(request.session.get("cart", {}))
    product_id = str(form.get("product_id", ""))
    raw_quantity = str(form.get("quantity", ""))
    if (
        product_id not in cart
        or not raw_quantity.isascii()
        or not raw_quantity.isdigit()
        or int(raw_quantity) > 10000
    ):
        return render(
            request,
            "bag.html",
            422,
            error_message="Enter a quantity from 0 to 10000.",
            **bag_context(request, session),
        )
    quantity = int(raw_quantity)
    if quantity:
        try:
            product = catalog.get_product(session, int(product_id))
            if quantity > product.stock:
                raise DomainError(
                    409,
                    "insufficient_stock",
                    "That quantity is no longer available. Choose a smaller amount.",
                )
        except DomainError as exc:
            return render(
                request,
                "bag.html",
                exc.status,
                error_message=exc.message,
                **bag_context(request, session),
            )
        cart[product_id] = quantity
    else:
        cart.pop(product_id)
    request.session["cart"] = cart
    request.session.pop("purchase_key", None)
    return redirect("/bag")


@router.post("/checkout")
def checkout(request: Request, form: FormDependency) -> Response:
    initialize_session(request)
    key = str(form.get("purchase_key", ""))
    if request.session.get("last_purchase_key") == key and "receipt" in request.session:
        return redirect("/receipt")
    if not request.session["cart"] or key != request.session.get("purchase_key"):
        raise DomainError(
            409, "invalid_checkout", "Your bag changed. Review it before placing your order."
        )
    data = OrderInput.model_validate(
        {
            "items": [
                {"product_id": int(product_id), "quantity": quantity}
                for product_id, quantity in request.session["cart"].items()
            ]
        }
    )
    try:
        result = create_order(
            request.app.state.session_factory, request.session["client_id"], key, data
        )
    except DomainError as exc:
        with request.app.state.session_factory() as session:
            return render(
                request,
                "bag.html",
                exc.status,
                error_message=exc.message,
                **bag_context(request, session),
            )
    request.session["receipt"] = {
        "id": result["id"],
        "total": result["total"],
        "currency": result["currency"],
        "count": sum(item["quantity"] for item in result["items"]),
    }
    request.session["last_purchase_key"] = key
    request.session["cart"] = {}
    request.session.pop("purchase_key", None)
    return redirect("/receipt")


@router.get("/receipt", response_class=HTMLResponse)
def receipt(request: Request) -> Response:
    if "receipt" not in request.session:
        return redirect("/")
    return render(request, "receipt.html", receipt=request.session["receipt"])


@router.get("/admin", response_class=HTMLResponse)
def administration(
    request: Request,
    session: SessionDependency,
    q: str = Query(default="", max_length=200),
    category: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1, le=100000),
) -> HTMLResponse:
    notice = request.session.pop("notice", None)
    template = (
        "partials/inventory.html"
        if request.headers.get("HX-Request")
        and not request.headers.get("HX-History-Restore-Request")
        else "admin.html"
    )
    return render(request, template, notice=notice, **catalog_context(session, q, category, page))


@router.get("/admin/products/new", response_class=HTMLResponse)
def new_product(request: Request) -> HTMLResponse:
    return render(request, "product_form.html", values={}, errors={}, editing=False)


@router.get("/admin/products/{product_id}/edit", response_class=HTMLResponse)
def edit_product(request: Request, product_id: int, session: SessionDependency) -> HTMLResponse:
    product = catalog.get_product(session, product_id)
    return render(
        request,
        "product_form.html",
        values=ProductOutput.model_validate(product).model_dump(exclude={"id", "active"}),
        errors={},
        editing=True,
        product_id=product_id,
    )


def parse_product(form: FormData, editing: bool) -> ProductInput:
    fields = ["name", "sku", "description", "category", "price", "stock", "weight_kg"]
    if editing:
        fields.append("version")
    values: dict[str, Any] = {field: str(form.get(field, "")) for field in fields}
    for field in ["stock", "version"]:
        if field in values and values[field].isascii() and values[field].isdigit():
            values[field] = int(values[field])
    return ProductUpdate.model_validate(values) if editing else ProductInput.model_validate(values)


def save_product(request: Request, form: FormData, product_id: int | None = None) -> Response:
    editing = product_id is not None
    try:
        data = parse_product(form, editing)
        with request.app.state.session_factory.begin() as session:
            if product_id is None:
                catalog.create_product(session, data)
            else:
                catalog.update_product(
                    session, product_id, ProductUpdate.model_validate(data.model_dump())
                )
        request.session["notice"] = "Product updated." if editing else "Product created."
        return redirect("/admin")
    except ValidationError as exc:
        errors = {str(error["loc"][0]): error["msg"] for error in exc.errors()}
        return render(
            request,
            "product_form.html",
            422,
            values=dict(form),
            errors=errors,
            editing=editing,
            product_id=product_id,
        )
    except DomainError as exc:
        return render(
            request,
            "product_form.html",
            exc.status,
            values=dict(form),
            errors={},
            error_message=exc.message,
            editing=editing,
            product_id=product_id,
        )


@router.post("/admin/products/new")
def create_product(request: Request, form: FormDependency) -> Response:
    return save_product(request, form)


@router.post("/admin/products/{product_id}/edit")
def update_product(request: Request, product_id: int, form: FormDependency) -> Response:
    return save_product(request, form, product_id)


@router.get("/admin/products/{product_id}/delete", response_class=HTMLResponse)
def delete_confirmation(
    request: Request, product_id: int, session: SessionDependency
) -> HTMLResponse:
    return render(request, "delete.html", product=catalog.get_product(session, product_id))


@router.post("/admin/products/{product_id}/delete")
def delete_product(request: Request, product_id: int, form: FormDependency) -> Response:
    version = str(form.get("version", ""))
    if not version.isascii() or not version.isdigit():
        raise DomainError(422, "invalid_version", "Reload the product and try again.")
    with request.app.state.session_factory.begin() as session:
        catalog.delete_product(session, product_id, int(version))
    request.session["notice"] = "Product removed from the store."
    return redirect("/admin")


@router.get("/admin/import", response_class=HTMLResponse)
def import_page(request: Request) -> HTMLResponse:
    return render(request, "import.html")


@router.post("/admin/import")
def import_file(request: Request, form: FormDependency) -> Response:
    uploaded = form.get("file")
    if not isinstance(uploaded, UploadFile):
        return render(request, "import.html", 422, error_message="Choose a CSV file to import.")
    initialize_session(request)
    try:
        content = uploaded.file.read(MAX_BYTES + 1)
        with request.app.state.session_factory.begin() as session:
            preview = preview_products(session, content)
            if preview.errors:
                batch = stage_import(
                    session,
                    request.session["client_id"],
                    uploaded.filename or "products.csv",
                    preview,
                )
            else:
                result = import_products(session, content)
                batch = None
        if batch is not None:
            return render(request, "import.html", preview=batch)
        return render(request, "import.html", imported=result["imported"])
    except DomainError as exc:
        return render(
            request, "import.html", exc.status, error_message=exc.message, import_errors=exc.details
        )
    finally:
        uploaded.file.close()


def batch_id_from_form(form: FormData) -> UUID:
    try:
        return UUID(str(form.get("batch_id", "")))
    except ValueError as exc:
        raise DomainError(
            422, "invalid_import", "Reload the import page and upload your CSV again."
        ) from exc


@router.post("/admin/import/confirm")
def import_confirmation(request: Request, form: FormDependency) -> Response:
    try:
        with request.app.state.session_factory.begin() as session:
            result = confirm_import(session, batch_id_from_form(form), request.session["client_id"])
        return render(
            request, "import.html", imported=result["imported"], skipped=result["skipped"]
        )
    except DomainError as exc:
        return render(
            request, "import.html", exc.status, error_message=exc.message, import_errors=exc.details
        )


@router.post("/admin/import/cancel")
def import_cancellation(request: Request, form: FormDependency) -> Response:
    with request.app.state.session_factory.begin() as session:
        cancel_import(session, batch_id_from_form(form), request.session["client_id"])
    return render(request, "import.html", cancelled=True)
