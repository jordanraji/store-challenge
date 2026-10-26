import re
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.imports.models import ImportBatch
from app.imports.service import preview_products
from app.main import create_app

HEADER = "name,sku,description,category,price,stock,weight_kg\n"
MIXED = (
    HEADER + "Coffee,CF-1,Dark roast,Food,12.50,5,1\nInvalid,BAD,Incorrect price,Food,free,2,1\n"
)


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def stage(client, content=MIXED):
    token = csrf(client.get("/admin/import"))
    response = client.post(
        "/admin/import", data={"csrf": token}, files={"file": ("products.csv", content, "text/csv")}
    )
    assert response.status_code == 200, response.text
    batch_id = re.search(r'name="batch_id" value="([^"]+)"', response.text).group(1)
    return response, {"csrf": token, "batch_id": batch_id}


def test_preview_and_explicit_confirmation(client):
    review, data = stage(client)
    assert "Do you want to import only the valid rows?" in review.text
    assert "Nothing has been imported yet." in review.text
    assert "free" in review.text
    assert "Row 3" in review.text
    assert client.get("/api/products").json()["total"] == 0
    confirmed = client.post("/admin/import/confirm", data=data)
    assert confirmed.status_code == 200
    assert "1 product imported successfully." in confirmed.text
    assert "1 row was skipped" in confirmed.text
    assert client.get("/api/products").json()["total"] == 1
    assert client.post("/admin/import/confirm", data=data).status_code == 200
    assert client.get("/api/products").json()["total"] == 1


def test_cancel_is_final_and_saves_no_products(client, app):
    _, data = stage(client)
    response = client.post("/admin/import/cancel", data=data)
    assert response.status_code == 200
    assert "Upload cancelled. No products were imported." in response.text
    assert client.get("/api/products").json()["total"] == 0
    assert client.post("/admin/import/confirm", data=data).status_code == 409
    with app.state.test_session_factory() as session:
        batch = session.get(ImportBatch, UUID(data["batch_id"]))
        assert batch.status == "cancelled"
        assert batch.products == []


def test_all_invalid_rows_have_no_continue_action(client):
    review, data = stage(client, HEADER + "Bad,A,desc,Food,free,-1,1\n")
    assert "No valid rows are available" in review.text
    assert 'action="/admin/import/confirm"' not in review.text
    assert "price" in review.text and "stock" in review.text
    assert client.post("/admin/import/confirm", data=data).status_code == 422
    assert client.get("/api/products").json()["total"] == 0


def test_confirmation_checks_owner_csrf_and_expiry(client, app):
    _, data = stage(client)
    assert client.post("/admin/import/confirm", data={**data, "csrf": "wrong"}).status_code == 403
    with TestClient(create_app(app.state.database_url)) as other:
        other_token = csrf(other.get("/admin/import"))
        assert (
            other.post("/admin/import/confirm", data={**data, "csrf": other_token}).status_code
            == 404
        )
    with app.state.test_session_factory.begin() as session:
        batch = session.get(ImportBatch, UUID(data["batch_id"]))
        batch.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.post("/admin/import/confirm", data=data).status_code == 410
    assert client.get("/api/products").json()["total"] == 0
    assert (
        client.post("/admin/import/confirm", data={**data, "batch_id": "not-a-uuid"}).status_code
        == 422
    )


def test_inventory_changes_between_review_and_confirm(client, product_data):
    _, data = stage(client)
    client.post("/api/products", json={**product_data, "sku": "CF-1"})
    response = client.post("/admin/import/confirm", data=data)
    assert response.status_code == 409
    assert "Inventory changed since review" in response.text
    assert client.get("/api/products").json()["total"] == 1


def test_partial_api_requires_explicit_opt_in(client):
    files = {"file": ("mixed.csv", MIXED, "text/csv")}
    assert client.post("/api/imports/products", files=files).status_code == 422
    assert client.get("/api/products").json()["total"] == 0
    response = client.post("/api/imports/products", files=files, data={"allow_partial": "true"})
    assert response.status_code == 200
    assert response.json() == {"imported": 1, "skipped": 1}


def test_first_valid_duplicate_is_kept(client):
    content = HEADER + "First,ONE,desc,Food,1,2,1\nSecond,one,desc,Food,2,5,1\n"
    review, data = stage(client, content)
    assert "first valid occurrence is row 2" in review.text
    assert client.post("/admin/import/confirm", data=data).status_code == 200
    products = client.get("/api/products").json()["items"]
    assert len(products) == 1
    assert products[0]["name"] == "First"


def test_original_challenge_csv_reports_errors_and_imports_only_valid_rows(client, app):
    content = Path("tests/fixtures/challenge-products.csv").read_bytes()

    async def preview_csv():
        async with app.state.primary_db.get_db() as session:
            return await preview_products(session, content)

    preview = client.portal.call(preview_csv)
    assert preview.products and preview.errors
    assert preview.total_rows == len(preview.products) + len(preview.errors)
    review, data = stage(client, content)
    assert f"Import {len(preview.products)} valid rows" in review.text
    assert client.get("/api/products").json()["total"] == 0
    response = client.post("/admin/import/confirm", data=data)
    assert response.status_code == 200
    assert client.get("/api/products").json()["total"] == len(preview.products)
    assert "free" in review.text


def test_repeated_concurrent_confirmation_does_not_duplicate_products(client, app):
    _, data = stage(client)
    barrier = Barrier(2)
    cookies = dict(client.cookies)

    def confirm(_):
        with TestClient(create_app(app.state.database_url)) as independent:
            independent.cookies.update(cookies)
            barrier.wait(timeout=10)
            return independent.post("/admin/import/confirm", data=data)

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(confirm, range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert client.get("/api/products").json()["total"] == 1
    with app.state.test_session_factory() as session:
        batch = session.scalar(select(ImportBatch))
        assert batch.status == "completed" and batch.imported == 1
