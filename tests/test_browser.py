import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, expect, sync_playwright


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def live_url(app) -> Iterator[str]:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("Test server failed to start")
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=10)
    listener.close()


def test_shopping_with_htmx_and_checkout(browser, live_url, client, product_data):
    client.post("/api/products", json=product_data)
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.goto(live_url)
    page.get_by_role("searchbox", name="Search products").fill("zzzzzzz")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_text("No products match this search.")).to_be_visible()
    page.get_by_role("searchbox", name="Search products").fill("cafe")
    page.get_by_role("button", name="Search", exact=True).click()
    expect(page.get_by_role("heading", name="Café Premium", exact=True)).to_be_visible()
    page.get_by_role("button", name="Add Café Premium to bag").click()
    expect(page.locator("#bag-control .bag-count")).to_have_text("1")
    expect(page.locator("#notification")).to_contain_text("added to your bag")
    page.locator("#bag-control").click()
    page.get_by_role("spinbutton", name="Quantity for Café Premium").fill("2")
    page.get_by_role("button", name="Update", exact=True).click()
    expect(page.locator(".summary-total")).to_contain_text("$25.00")
    page.get_by_role("button", name="Place order").click()
    expect(page.get_by_text("Your simulated order is confirmed.", exact=False)).to_be_visible()
    expect(page.locator("#bag-control .bag-count")).to_have_text("0")
    assert client.get("/api/products").json()["items"][0]["stock"] == 3
    context.close()


def test_management_forms_and_csv(browser, live_url):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.goto(f"{live_url}/admin")
    page.get_by_role("link", name="Add product", exact=True).first.click()
    for label, value in [
        ("Product name", "Daily Notebook"),
        ("SKU", "NOTE-1"),
        ("Category", "Stationery"),
        ("Price (USD)", "8.50"),
        ("Stock", "12"),
        ("Weight (kg)", "0.2"),
    ]:
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role("button", name="Create product").click()
    expect(page.get_by_text("Product created.", exact=True)).to_be_visible()
    page.get_by_role("link", name="Edit Daily Notebook", exact=True).click()
    page.get_by_label("Product name", exact=True).fill("Daily Notebook A5")
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_text("Daily Notebook A5", exact=True)).to_be_visible()
    page.get_by_role("link", name="Import CSV").click()
    page.get_by_label("Choose your product CSV").set_input_files(
        {"name": "bad.csv", "mimeType": "text/csv", "buffer": b"name,sku\nBad,BAD"}
    )
    page.get_by_role("button", name="Import products", exact=True).click()
    expect(page.get_by_text("Nothing was imported.", exact=True)).to_be_visible()
    content = b"name,sku,description,category,price,stock,weight_kg\nPencil,PEN-1,Graphite,Stationery,2.00,10,0.01\n"
    page.get_by_label("Choose your product CSV").set_input_files(
        {"name": "good.csv", "mimeType": "text/csv", "buffer": content}
    )
    page.get_by_role("button", name="Import products", exact=True).click()
    expect(page.get_by_text("1 product imported successfully.", exact=False)).to_be_visible()
    page.get_by_role("link", name="View inventory").click()
    page.get_by_role("link", name="Remove Daily Notebook A5", exact=True).click()
    page.get_by_role("button", name="Remove product", exact=True).click()
    expect(page.get_by_text("Product removed from the store.", exact=True)).to_be_visible()
    expect(page.get_by_text("Daily Notebook A5", exact=True)).to_have_count(0)
    context.close()


def test_mobile_unavailable_bag_and_no_javascript_fallback(browser, live_url, client, product_data):
    product = client.post("/api/products", json={**product_data, "stock": 1}).json()
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(live_url)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.get_by_role("button", name="Add Café Premium to bag").click()
    expect(page.locator("#bag-control .bag-count")).to_have_text("1")
    client.put(f"/api/products/{product['id']}", json={**product_data, "stock": 0, "version": 1})
    page.goto(f"{live_url}/bag")
    expect(page.get_by_role("button", name="Place order")).to_be_disabled()
    page.reload()
    expect(page.get_by_role("button", name="Place order")).to_be_disabled()
    page.get_by_role("button", name="Remove Café Premium").click()
    expect(page.get_by_text("Your bag is ready for a good find.")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    context.close()
    context = browser.new_context(java_script_enabled=False)
    page = context.new_page()
    page.goto(f"{live_url}/admin/products/new")
    expect(page.get_by_role("heading", name="Add a product", exact=True)).to_be_visible()
    context.close()


def test_responsive_layout_and_capture(browser, live_url, client):
    import os

    sample = Path("app/web/static/example-products.csv").read_bytes()
    imported = client.post(
        "/api/imports/products", files={"file": ("sample.csv", sample, "text/csv")}
    )
    assert imported.status_code == 200
    output = Path(".impeccable/review")
    capture = os.environ.get("STORE_CAPTURE_UI") == "1"
    if capture:
        output.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(live_url)
    page.evaluate("document.fonts.ready")
    expect(page.locator(".product-item")).to_have_count(9)
    for width in [320, 575, 576, 767, 768, 991, 992, 1280]:
        page.set_viewport_size({"width": width, "height": 1000})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), width
    for width, height, filename in [(1440, 1000, "desktop.png"), (390, 844, "mobile.png")]:
        page.set_viewport_size({"width": width, "height": height})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if capture:
            page.screenshot(path=str(output / filename), full_page=True, animations="disabled")
    page.set_viewport_size({"width": 1440, "height": 1000})
    for path, filename in [
        ("/admin", "admin.png"),
        ("/admin/products/new", "form.png"),
        ("/admin/import", "import.png"),
        ("/?q=zzzzzzzz", "empty-search.png"),
        ("/bag", "empty-bag.png"),
    ]:
        page.goto(live_url + path)
        page.evaluate("document.fonts.ready")
        if capture:
            page.screenshot(path=str(output / filename), full_page=True, animations="disabled")
    page.goto(live_url)
    page.get_by_role("button", name="Add Running Shoes to bag").click()
    expect(page.locator("#bag-control .bag-count")).to_have_text("1")
    page.goto(live_url + "/bag")
    if capture:
        page.screenshot(path=str(output / "bag.png"), full_page=True, animations="disabled")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    if capture:
        page.screenshot(path=str(output / "bag-mobile.png"), full_page=True, animations="disabled")
    assert not errors
    context.close()


def test_import_review_cancel_and_continue_in_browser(browser, live_url, client):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    content = b"name,sku,description,category,price,stock,weight_kg\nCoffee,CF-1,Dark roast,Food,12.50,5,1\nBad,BAD,Incorrect price,Food,free,2,1\n"
    page.goto(live_url + "/admin/import")
    page.get_by_label("Choose your product CSV").set_input_files(
        {"name": "mixed.csv", "mimeType": "text/csv", "buffer": content}
    )
    page.get_by_role("button", name="Import products", exact=True).click()
    expect(
        page.get_by_role("heading", name="Do you want to import only the valid rows?")
    ).to_be_visible()
    expect(page.get_by_text("free", exact=True)).to_be_visible()
    assert client.get("/api/products").json()["total"] == 0
    import os

    if os.environ.get("STORE_CAPTURE_IMPORT") == "1":
        output = Path(".impeccable/review")
        output.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(output / "import-review-desktop.png"), full_page=True, animations="disabled"
        )
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(
            path=str(output / "import-review-mobile.png"), full_page=True, animations="disabled"
        )
    page.get_by_role("button", name="Cancel upload", exact=True).click()
    expect(page.get_by_text("Upload cancelled. No products were imported.")).to_be_visible()
    assert client.get("/api/products").json()["total"] == 0
    page.get_by_label("Choose your product CSV").set_input_files(
        {"name": "mixed.csv", "mimeType": "text/csv", "buffer": content}
    )
    page.get_by_role("button", name="Import products", exact=True).click()
    page.get_by_role("button", name="Import 1 valid row", exact=True).click()
    expect(page.get_by_text("1 product imported successfully.", exact=False)).to_be_visible()
    assert client.get("/api/products").json()["total"] == 1
    context.close()


def test_browser_rejects_xss_from_forms_and_csv_and_keeps_sql_inert(
    browser, live_url, client, product_data
):
    import csv
    import io

    sql = "Robert'); DROP TABLE products;--"
    xss = "<script>alert('xss')</script>"
    context = browser.new_context()
    page = context.new_page()
    dialogs = []

    def dismiss_dialog(dialog):
        dialogs.append(dialog.message)
        dialog.dismiss()

    page.on("dialog", dismiss_dialog)
    page.goto(live_url + "/admin/products/new")
    for label, value in [
        ("Product name", xss),
        ("SKU", "FORM-XSS"),
        ("Category", "Security"),
        ("Price (USD)", "9.99"),
        ("Stock", "2"),
        ("Weight (kg)", "0.5"),
    ]:
        page.get_by_label(label, exact=True).fill(value)
    page.get_by_role("button", name="Create product", exact=True).click()
    expect(
        page.get_by_text("Use plain text only; HTML tags and markup are not allowed", exact=False)
    ).to_be_visible()
    expect(page.get_by_label("Product name", exact=True)).to_have_value(xss)
    assert not dialogs
    assert page.locator("script:not([src])").count() == 0
    page.goto(live_url + "/admin/import")
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(product_data))
    writer.writeheader()
    writer.writerows(
        [
            {**product_data, "sku": "CSV-XSS", "name": xss},
            {**product_data, "sku": "CSV-SQL", "name": sql},
        ]
    )
    page.get_by_label("Choose your product CSV").set_input_files(
        {"name": "security.csv", "mimeType": "text/csv", "buffer": stream.getvalue().encode()}
    )
    page.get_by_role("button", name="Import products", exact=True).click()
    expect(page.get_by_role("button", name="Import 1 valid row", exact=True)).to_be_visible()
    expect(page.get_by_text(xss, exact=True).first).to_be_visible()
    assert page.locator("script:not([src])").count() == 0
    assert not dialogs
    page.get_by_role("button", name="Import 1 valid row", exact=True).click()
    page.get_by_role("link", name="View inventory", exact=True).click()
    expect(page.get_by_text(sql, exact=True)).to_be_visible()
    assert client.get("/api/products").json()["total"] == 1
    assert not dialogs
    context.close()


def test_browser_legacy_data_remains_text_and_csp_blocks_inline_execution(
    browser, live_url, app, client, product_data
):
    from app.catalog.models import Product

    payload = '<script>alert("xss")</script>'
    with app.state.session_factory.begin() as session:
        product = Product(
            **{
                **product_data,
                "name": payload,
                "description": '<img src=x onerror="alert(1)">',
                "category": 'Security" onmouseover="alert(1)',
            }
        )
        session.add(product)
        session.flush()
        product_id = product.id
    context = browser.new_context()
    context.add_init_script(
        "window.__xssRan = 0; window.__violations = []; document.addEventListener('securitypolicyviolation', event => window.__violations.push(event.violatedDirective));"
    )
    page = context.new_page()
    dialogs = []
    page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.dismiss()))
    for path in ["/", "/admin", f"/products/{product_id}", f"/admin/products/{product_id}/edit"]:
        page.goto(live_url + path)
        assert page.locator("script:not([src])").count() == 0
        assert page.locator("[onerror], [onload], [onmouseover]").count() == 0
        assert not dialogs
    expect(page.get_by_label("Product name", exact=True)).to_have_value(payload)
    page.goto(live_url + "/")
    page.get_by_role("button", name=f"Add {payload} to bag", exact=True).click()
    expect(page.locator("#bag-control .bag-count")).to_have_text("1")
    expect(page.locator("#notification")).to_contain_text(payload)
    assert page.locator("script:not([src])").count() == 0
    assert not dialogs
    page.evaluate(
        "document.body.insertAdjacentHTML('beforeend', '<img src=\"/missing-security-probe-image\" onerror=\"window.__xssRan=1\">')"
    )
    page.wait_for_function("window.__violations.includes('script-src-attr')")
    page.evaluate(
        "const script = document.createElement('script'); script.textContent='window.__xssRan=2'; document.body.append(script)"
    )
    page.wait_for_function("window.__violations.includes('script-src-elem')")
    assert page.evaluate("window.__xssRan") == 0
    assert client.get("/api/products").status_code == 200
    context.close()
