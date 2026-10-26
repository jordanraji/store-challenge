import pytest


def test_crud_version_and_soft_delete(client, product_data):
    response = client.post("/api/products", json=product_data)
    assert response.status_code == 201
    product = response.json()
    assert product["sku"] == "CF-001"
    assert product["price"] == "12.50"
    assert client.get(f"/api/products/{product['id']}").status_code == 200
    payload = {**product_data, "version": 1, "name": "Updated"}
    response = client.put(f"/api/products/{product['id']}", json=payload)
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert client.put(f"/api/products/{product['id']}", json=payload).status_code == 409
    assert client.delete(f"/api/products/{product['id']}?version=1").status_code == 409
    assert client.delete(f"/api/products/{product['id']}?version=2").status_code == 204
    assert client.get(f"/api/products/{product['id']}").status_code == 404
    assert client.get("/api/products").json()["total"] == 0
    assert client.post("/api/products", json=product_data).status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("stock", -1),
        ("stock", True),
        ("stock", 1.5),
        ("price", "-1"),
        ("price", "1.001"),
        ("price", "NaN"),
        ("weight_kg", "-1"),
        ("name", " "),
        ("sku", "bad sku"),
        ("category", ""),
        ("unexpected", 1),
    ],
)
def test_invalid_product_is_422(client, product_data, field, value):
    response = client.post("/api/products", json={**product_data, field: value})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert client.get("/api/products").json()["total"] == 0


def test_duplicate_and_missing_product(client, product_data):
    assert client.post("/api/products", json=product_data).status_code == 201
    assert client.post("/api/products", json=product_data).status_code == 409
    assert client.get("/api/products/999").status_code == 404
    assert client.put("/api/products/999", json={**product_data, "version": 1}).status_code == 404


def test_search_rank_accents_typo_and_pagination(client, product_data):
    client.post("/api/products", json=product_data)
    client.post(
        "/api/products",
        json={**product_data, "sku": "OTHER", "name": "CF-001 Coffee", "description": "Other"},
    )
    exact = client.get("/api/products", params={"q": "cf-001"}).json()
    assert exact["items"][0]["sku"] == "CF-001"
    for query in ["cafe", "organic beans", "Food", "Café Premiun"]:
        result = client.get("/api/products", params={"q": query})
        assert result.status_code == 200, result.text
        assert any(item["sku"] == "CF-001" for item in result.json()["items"])
    assert client.get("/api/products?q=zzzzzzzz").json()["total"] == 0
    assert client.get("/api/products?page_size=1&page=2").json()["items"][0]["sku"] == "OTHER"
    assert client.get("/api/products?page=0").status_code == 422
