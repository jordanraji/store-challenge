HEADER = "name,sku,description,category,price,stock,weight_kg\n"


def upload(client, content):
    return client.post(
        "/api/imports/products", files={"file": ("products.csv", content, "text/csv")}
    )


def test_import_normalization_and_duplicate_rejection(client):
    content = HEADER + 'Coffee,CF-1,"Rich, dark",Food,$12.50,5,1\n'
    response = upload(client, content)
    assert response.status_code == 200, response.text
    assert response.json() == {"imported": 1}
    assert client.get("/api/products").json()["items"][0]["price"] == "12.50"
    assert upload(client, content).status_code == 422
    assert client.get("/api/products").json()["total"] == 1


def test_invalid_csv_rolls_back_and_reports_rows(client):
    response = upload(client, HEADER + "Good,A,desc,Food,1,2,1\nBad,B,desc,Food,1,-1,1\n")
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["row"] == 3
    assert client.get("/api/products").json()["total"] == 0


def test_duplicate_rows_and_malformed_files(client):
    for content in [
        HEADER + "A,a,desc,Food,1,2,1\nB,A,desc,Food,1,2,1\n",
        "name,sku\nA,B",
        HEADER,
        b"\xff",
        HEADER + "A,B,desc,Food,1,2,1,extra\n",
    ]:
        assert upload(client, content).status_code == 422
    assert upload(client, b"x" * (2 * 1024 * 1024 + 1)).status_code == 413
