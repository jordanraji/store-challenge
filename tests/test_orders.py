import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from app.main import create_app
from app.orders.models import IdempotencyRecord, Order


def headers(key="purchase-1", client_id=None):
    return {
        "X-Client-ID": client_id or "4ff6347d-4e5a-4ce9-9a21-ed89853b9d88",
        "Idempotency-Key": key,
    }


def test_order_price_snapshot_idempotency_and_stale_edit(client, product_data):
    product = client.post("/api/products", json=product_data).json()
    payload = {"items": [{"product_id": product["id"], "quantity": 2}]}
    response = client.post("/api/orders", json=payload, headers=headers())
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["total"] == "25.00"
    assert order["status"] == "paid"
    assert client.post("/api/orders", json=payload, headers=headers()).json() == order
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 3
    assert (
        client.put(
            f"/api/products/{product['id']}", json={**product_data, "version": 1}
        ).status_code
        == 409
    )
    different = {"items": [{"product_id": product["id"], "quantity": 1}]}
    assert client.post("/api/orders", json=different, headers=headers()).status_code == 409


def test_multiline_failure_rolls_back_everything(client, app, product_data):
    first = client.post("/api/products", json=product_data).json()
    second = client.post("/api/products", json={**product_data, "sku": "EMPTY", "stock": 0}).json()
    payload = {
        "items": [
            {"product_id": first["id"], "quantity": 1},
            {"product_id": second["id"], "quantity": 1},
        ]
    }
    assert client.post("/api/orders", json=payload, headers=headers()).status_code == 409
    assert client.get(f"/api/products/{first['id']}").json()["stock"] == 5
    with app.state.test_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 0
        assert session.scalar(select(func.count()).select_from(IdempotencyRecord)) == 0


def test_missing_product_and_invalid_order(client):
    assert (
        client.post(
            "/api/orders", json={"items": [{"product_id": 999, "quantity": 1}]}, headers=headers()
        ).status_code
        == 404
    )
    for payload in [
        {"items": []},
        {"items": [{"product_id": 1, "quantity": 0}]},
        {"items": [{"product_id": 1, "quantity": True}]},
    ]:
        assert client.post("/api/orders", json=payload, headers=headers()).status_code == 422
    assert (
        client.post("/api/orders", json={"items": [{"product_id": 1, "quantity": 1}]}).status_code
        == 422
    )


def parallel_requests(app, requests, locked_product=None):
    barrier = Barrier(len(requests))

    def send(arguments):
        path, payload, request_headers = arguments
        with TestClient(create_app(app.state.database_url)) as independent_client:
            barrier.wait(timeout=10)
            return independent_client.post(path, json=payload, headers=request_headers)

    with app.state.test_session_factory() as blocker:
        if locked_product is not None:
            blocker.execute(
                text("SELECT id FROM products WHERE id = :id FOR UPDATE"), {"id": locked_product}
            )
        with ThreadPoolExecutor(max_workers=len(requests)) as executor:
            futures = [executor.submit(send, arguments) for arguments in requests]
            if locked_product is not None:
                try:
                    deadline = time.monotonic() + 10
                    while time.monotonic() < deadline:
                        with app.state.test_session_factory() as observer:
                            waiting = observer.scalar(
                                text(
                                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
                                )
                            )
                        if waiting >= len(requests):
                            break
                        time.sleep(0.02)
                    else:
                        raise AssertionError("Concurrent database transactions did not overlap")
                finally:
                    blocker.rollback()
            return [future.result(timeout=15) for future in futures]


def test_concurrent_last_unit(app, client, product_data):
    product = client.post("/api/products", json={**product_data, "stock": 1}).json()
    payload = {"items": [{"product_id": product["id"], "quantity": 1}]}
    responses = parallel_requests(
        app,
        [("/api/orders", payload, headers(str(uuid4()))) for _ in range(2)],
        locked_product=product["id"],
    )
    assert sorted(response.status_code for response in responses) == [201, 409]
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 0
    with app.state.test_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1


def test_concurrent_same_key_and_reordered_payload(app, client, product_data):
    product = client.post("/api/products", json=product_data).json()
    payload = {
        "items": [
            {"product_id": product["id"], "quantity": 1},
            {"product_id": product["id"], "quantity": 1},
        ]
    }
    responses = parallel_requests(
        app, [("/api/orders", payload, headers()) for _ in range(2)], locked_product=product["id"]
    )
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json() == responses[1].json()
    equivalent = {"items": [{"product_id": product["id"], "quantity": 2}]}
    assert (
        client.post("/api/orders", json=equivalent, headers=headers()).json() == responses[0].json()
    )
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 3
    with app.state.test_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Order)) == 1


def test_concurrent_duplicate_sku(app, product_data):
    responses = parallel_requests(app, [("/api/products", product_data, {}) for _ in range(2)])
    assert sorted(response.status_code for response in responses) == [201, 409]


def test_idempotency_is_scoped_and_failed_attempt_can_retry(client, product_data):
    product = client.post("/api/products", json={**product_data, "stock": 0}).json()
    payload = {"items": [{"product_id": product["id"], "quantity": 1}]}
    assert client.post("/api/orders", json=payload, headers=headers()).status_code == 409
    assert (
        client.put(
            f"/api/products/{product['id']}", json={**product_data, "version": 1}
        ).status_code
        == 200
    )
    first = client.post("/api/orders", json=payload, headers=headers())
    second = client.post("/api/orders", json=payload, headers=headers(client_id=str(uuid4())))
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert client.get(f"/api/products/{product['id']}").json()["stock"] == 3


def test_maximum_valid_price_and_quantity_do_not_overflow(client, product_data):
    product = client.post(
        "/api/products", json={**product_data, "price": "9999999999.99", "stock": 10000}
    ).json()
    response = client.post(
        "/api/orders",
        json={"items": [{"product_id": product["id"], "quantity": 10000}]},
        headers=headers(),
    )
    assert response.status_code == 201, response.text
    assert response.json()["total"] == "99999999999900.00"


def test_order_snapshot_survives_product_edit_and_delete(app, client, product_data):
    product = client.post("/api/products", json=product_data).json()
    payload = {"items": [{"product_id": product["id"], "quantity": 1}]}
    original = client.post("/api/orders", json=payload, headers=headers()).json()
    updated = client.put(
        f"/api/products/{product['id']}",
        json={**product_data, "name": "Changed", "price": "99.00", "version": 2},
    )
    assert updated.status_code == 200
    assert client.delete(f"/api/products/{product['id']}?version=3").status_code == 204
    assert client.post("/api/orders", json=payload, headers=headers()).json() == original
    from app.orders.models import OrderLine

    with app.state.test_session_factory() as session:
        line = session.scalar(select(OrderLine))
        assert line.name == product_data["name"]
        assert str(line.unit_price) == "12.50"
