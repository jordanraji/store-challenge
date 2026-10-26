import re

from sqlalchemy import func, select

from app.orders.models import Order


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"', response.text).group(1)


def test_store_empty_and_form_csrf(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "The collection starts here." in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.post("/admin/products/new", data={"name": "Anything"}).status_code == 403
    assert client.get("/products/999").status_code == 404
    assert "Product not found." in client.get("/products/999").text
    assert client.get("/?page=0").status_code == 422


def test_product_form_errors_and_version_conflict(client, product_data):
    token = csrf(client.get("/admin/products/new"))
    data = {**product_data, "csrf": token}
    invalid = client.post("/admin/products/new", data={**data, "price": "-1"})
    assert invalid.status_code == 422
    assert "Check the highlighted fields" in invalid.text
    assert 'value="Café Premium"' in invalid.text
    response = client.post("/admin/products/new", data=data)
    assert response.status_code == 200
    assert "Product created." in response.text
    product = client.get("/api/products").json()["items"][0]
    assert client.get(f"/admin/products/{product['id']}/edit").status_code == 200
    assert (
        client.post(
            f"/admin/products/{product['id']}/edit", data={**data, "version": 999}
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/admin/products/{product['id']}/edit", data={**data, "version": 1}
        ).status_code
        == 200
    )
    assert client.get(f"/admin/products/{product['id']}/delete").status_code == 200
    assert (
        client.post(
            f"/admin/products/{product['id']}/delete", data={"csrf": token, "version": 2}
        ).status_code
        == 200
    )
    assert client.get(f"/products/{product['id']}").status_code == 404


def test_cart_checkout_repeated_submission_and_stock(client, app, product_data):
    product = client.post("/api/products", json=product_data).json()
    token = csrf(client.get("/"))
    response = client.post(
        f"/bag/items/{product['id']}", data={"csrf": token}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert "added to your bag" in response.text
    page = client.get("/bag")
    key = re.search(r'name="purchase_key" value="([^"]+)"', page.text).group(1)
    payload = {"csrf": token, "purchase_key": key}
    receipt = client.post("/checkout", data=payload)
    assert receipt.status_code == 200
    assert "Your simulated order is confirmed" in receipt.text
    assert client.post("/checkout", data=payload).status_code == 200
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 4
    with app.state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1


def test_unavailable_stock_preserves_bag_and_remove_works(client, product_data):
    product = client.post("/api/products", json={**product_data, "stock": 1}).json()
    token = csrf(client.get("/"))
    client.post(f"/bag/items/{product['id']}", data={"csrf": token})
    assert (
        client.post(
            f"/bag/items/{product['id']}", data={"csrf": token}, headers={"HX-Request": "true"}
        ).status_code
        == 409
    )
    key = re.search(r'name="purchase_key" value="([^"]+)"', client.get("/bag").text).group(1)
    client.put(f"/api/products/{product['id']}", json={**product_data, "stock": 0, "version": 1})
    failure = client.post("/checkout", data={"csrf": token, "purchase_key": key})
    assert failure.status_code == 409
    assert "Insufficient stock" in failure.text
    assert product["name"] in failure.text
    assert (
        client.post(
            "/bag/update", data={"csrf": token, "product_id": product["id"], "quantity": 0}
        ).status_code
        == 200
    )
    assert "Your bag is ready" in client.get("/bag").text


def test_import_form_and_partial_search(client, product_data):
    token = csrf(client.get("/admin/import"))
    response = client.post(
        "/admin/import",
        data={"csrf": token},
        files={"file": ("bad.csv", "name,sku\nA,B", "text/csv")},
    )
    assert response.status_code == 422
    assert "Nothing was imported" in response.text
    content = "name,sku,description,category,price,stock,weight_kg\nCoffee,C-1,Dark roast,Food,12.50,5,1\n"
    success = client.post(
        "/admin/import", data={"csrf": token}, files={"file": ("good.csv", content, "text/csv")}
    )
    assert success.status_code == 200
    assert "1 product imported" in success.text
    response = client.get("/?q=coffee&category=Food", headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert "Coffee" in response.text
    assert "<!doctype" not in response.text
    full = client.get(
        "/?q=coffee", headers={"HX-Request": "true", "HX-History-Restore-Request": "true"}
    )
    assert "<!doctype" in full.text


def test_category_filters_and_escaping(client, app, product_data):
    client.post("/api/products", json=product_data)
    from app.catalog.models import Product

    with app.state.session_factory.begin() as session:
        session.add(
            Product(
                **{
                    **product_data,
                    "sku": "OTHER",
                    "name": "<script>alert(1)</script>",
                    "category": "Other",
                }
            )
        )
    page = client.get("/?category=Food")
    assert "Café Premium" in page.text
    assert "&lt;script&gt;" not in page.text
    assert "&lt;script&gt;" in client.get("/").text
    assert "<script>alert(1)</script>" not in client.get("/").text
