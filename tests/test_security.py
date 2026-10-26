import csv
import io
import json
import re

import pytest
from sqlalchemy import func, select

from app.catalog.models import Product
from app.imports.models import ImportBatch

XSS = "<script>alert('xss')</script>"
SQL = "Robert'); DROP TABLE products;--"


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def csv_content(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=["name", "sku", "description", "category", "price", "stock", "weight_kg"]
    )
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


@pytest.mark.parametrize("field", ["name", "description", "category"])
@pytest.mark.parametrize(
    "payload",
    [
        XSS,
        '<img src=x onerror="alert(1)">',
        '</textarea><svg onload="alert(1)">',
        "<ScRiPt>alert(1)</ScRiPt>",
        '<a hx-get="/admin">Click</a>',
        "<![unexpected]>",
    ],
)
def test_api_rejects_html_on_create_and_update(client, product_data, field, payload):
    response = client.post("/api/products", json={**product_data, field: payload})
    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["field"] == f"body.{field}"
    assert client.get("/api/products").json()["total"] == 0
    product = client.post("/api/products", json=product_data).json()
    response = client.put(
        f"/api/products/{product['id']}", json={**product_data, field: payload, "version": 1}
    )
    assert response.status_code == 422
    assert client.get(f"/api/products/{product['id']}").json()[field] == product_data[field]


@pytest.mark.parametrize("payload", ["Bad\x00name", "Bad\x1bname", "Bad\ud800name"])
def test_invalid_database_text_is_422_not_server_failure(client, product_data, payload):
    response = client.post(
        "/api/products",
        content=json.dumps({**product_data, "name": payload}, ensure_ascii=True),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert client.get("/api/products").json()["total"] == 0


def test_form_rejects_and_escapes_xss(client, product_data):
    token = csrf(client.get("/admin/products/new"))
    response = client.post("/admin/products/new", data={**product_data, "name": XSS, "csrf": token})
    assert response.status_code == 422
    assert "plain text only" in response.text
    assert "&lt;script&gt;" in response.text
    assert XSS not in response.text
    assert client.get("/api/products").json()["total"] == 0


def test_sql_payload_is_parameterized_data_for_api_form_and_search(client, app, product_data):
    product = client.post("/api/products", json={**product_data, "name": SQL}).json()
    assert product["name"] == SQL
    token = csrf(client.get("/admin/products/new"))
    response = client.post(
        "/admin/products/new",
        data={
            **product_data,
            "sku": "FORM-SQL",
            "name": "O'Connor's notebook",
            "description": SQL,
            "csrf": token,
        },
    )
    assert response.status_code == 200
    for query in [SQL, "' OR 1=1 --", "'; SELECT pg_sleep(10); --"]:
        assert client.get("/api/products", params={"q": query}).status_code == 200
        assert client.get("/", params={"q": query, "category": query}).status_code == 200
    assert client.get("/api/products", params={"q": "' OR 1=1 --"}).json()["total"] == 0
    with app.state.test_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Product)) == 2
    assert client.get(f"/api/products/{product['id']}").json()["name"] == SQL


def test_csv_marks_html_invalid_and_sql_remains_inert_data(client, product_data):
    content = csv_content(
        [
            {**product_data, "name": XSS, "sku": "XSS"},
            {**product_data, "name": SQL, "sku": "SQL"},
            {**product_data, "name": "O'Connor's notebook", "sku": "SAFE"},
        ]
    )
    strict = client.post(
        "/api/imports/products", files={"file": ("security.csv", content, "text/csv")}
    )
    assert strict.status_code == 422
    assert strict.json()["error"]["details"][0]["row"] == 2
    assert strict.json()["error"]["details"][0]["errors"][0]["field"] == "name"
    assert client.get("/api/products").json()["total"] == 0
    token = csrf(client.get("/admin/import"))
    preview = client.post(
        "/admin/import", data={"csrf": token}, files={"file": ("security.csv", content, "text/csv")}
    )
    assert preview.status_code == 200
    assert "Import 2 valid rows" in preview.text
    assert "&lt;script&gt;" in preview.text
    assert XSS not in preview.text
    batch = re.search(r'name="batch_id" value="([^"]+)"', preview.text).group(1)
    confirmed = client.post("/admin/import/confirm", data={"csrf": token, "batch_id": batch})
    assert confirmed.status_code == 200
    products = client.get("/api/products").json()["items"]
    assert len(products) == 2
    assert SQL in {product["name"] for product in products}
    assert all(product["sku"] != "XSS" for product in products)


def test_old_reviews_are_revalidated_before_confirming(client, app, product_data):
    from uuid import UUID

    token = csrf(client.get("/admin/import"))
    content = csv_content(
        [{**product_data, "sku": "GOOD"}, {**product_data, "sku": "BAD", "price": "free"}]
    )
    review = client.post(
        "/admin/import", data={"csrf": token}, files={"file": ("old.csv", content, "text/csv")}
    )
    batch_id = re.search(r'name="batch_id" value="([^"]+)"', review.text).group(1)
    with app.state.test_session_factory.begin() as session:
        batch = session.get(ImportBatch, UUID(batch_id))
        batch.products = [{"row": 2, "data": {**product_data, "name": XSS}}]
    response = client.post("/admin/import/confirm", data={"csrf": token, "batch_id": batch_id})
    assert response.status_code == 409
    assert "no longer pass validation" in response.text
    assert client.get("/api/products").json()["total"] == 0


def test_legacy_content_is_escaped_without_breaking_reads(client, app, product_data):
    with app.state.test_session_factory.begin() as session:
        product = Product(
            **{
                **product_data,
                "name": XSS,
                "description": '</textarea><img src=x onerror="alert(1)">',
                "category": '<svg onload="alert(1)">',
            }
        )
        session.add(product)
        session.flush()
        product_id = product.id
    assert client.get("/api/products").status_code == 200
    for path in [
        "/",
        "/admin",
        f"/products/{product_id}",
        f"/admin/products/{product_id}/edit",
        f"/admin/products/{product_id}/delete",
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert XSS not in response.text
        assert "&lt;script&gt;" in response.text
    reflected = client.get("/", params={"q": '"><img src=x onerror="alert(1)">'})
    assert reflected.status_code == 200
    assert "<img src=x" not in reflected.text


def test_security_headers_and_nonce_protected_docs(client):
    for path in ["/", "/admin/import", "/api/products", "/products/999"]:
        response = client.get(path)
        policy = response.headers["content-security-policy"]
        assert "script-src 'self';" in policy
        assert "'unsafe-inline'" not in policy
        assert "'unsafe-eval'" not in policy
        assert "object-src 'none'" in policy
        assert "frame-ancestors 'none'" in policy
        assert response.headers["x-content-type-options"] == "nosniff"
    docs = client.get("/docs")
    assert docs.status_code == 200
    nonce = re.search(r'<script nonce="([^"]+)">', docs.text).group(1)
    assert f"'nonce-{nonce}'" in docs.headers["content-security-policy"]
    assert "script-src 'self' 'nonce-" in docs.headers["content-security-policy"]
    assert client.get("/redoc").status_code == 200
