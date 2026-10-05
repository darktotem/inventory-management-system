# Tests for the Flask API routes. OpenFoodFacts is always mocked.
import json
from pathlib import Path
from unittest import mock

import pytest

import app as app_module
from app import ExternalAPIError

LOGIN = {"username": "admin", "password": "admin123"}


# Fake OpenFoodFacts result in the shape fetch_product() returns.
def make_api_result(name="Mock Juice", **fields):
    product = {"product_name": name, "brands": "MockCo", "ingredients_text": "Water, apple",
               "categories": "Beverages", "quantity": "1 L", "nutriscore_grade": "b", **fields}
    return {"status": 1, "barcode": "123", "product": product}


# Add an item without any API lookup (unless overridden).
def add_plain_item(client, **overrides):
    return client.post("/inventory", json={"product_name": "Tea", "price": 120, "stock": 40, "enrich": False, **overrides})


def inventory_count(client):
    return len(client.get("/inventory").get_json())


# Pages, authentication and errors
def test_home_page_loads(client):
    assert client.get("/").status_code == 200


@pytest.mark.parametrize("method,url,status,error", [
    ("get", "/does-not-exist", 404, "Route not found"),
    ("delete", "/login", 405, "Method not allowed"),
])
def test_errors_are_json(client, method, url, status, error):
    response = getattr(client, method)(url)
    assert response.status_code == status and response.get_json()["error"] == error


@pytest.mark.parametrize("method,url", [
    ("get", "/inventory"), ("get", "/inventory/1"), ("post", "/inventory"), ("patch", "/inventory/1"),
    ("delete", "/inventory/1"), ("get", "/external/search?barcode=1"), ("post", "/inventory/1/enrich"),
    ("post", "/preferences"),
])
def test_protected_routes_need_login(client, method, url):
    response = getattr(client, method)(url)
    assert response.status_code == 401 and response.get_json()["error"] == "Login required"


def test_login_and_logout(client):
    assert client.get("/me").get_json() == {"logged_in": False, "username": None}
    assert client.post("/login", json={**LOGIN, "username": "  admin  "}).status_code == 200  # spaces ignored
    assert client.get("/me").get_json() == {"logged_in": True, "username": "admin"}
    assert client.post("/logout").status_code == 200
    assert client.get("/inventory").status_code == 401


@pytest.mark.parametrize("body,error", [
    ({"username": "ghost", "password": "x"}, "Username not found"),
    ({"username": "admin", "password": "nope"}, "Incorrect password"),
    ({}, "Username not found"),
])
def test_login_failures(client, body, error):
    response = client.post("/login", json=body)
    assert response.status_code == 401 and response.get_json()["error"] == error


def test_bcrypt_hashing():
    assert app_module.users[0]["password_hash"].startswith("$2")
    hashed = app_module.hash_password("secret")
    assert app_module.verify_password("secret", hashed) is True
    assert app_module.verify_password("wrong", hashed) is False
    assert app_module.verify_password("x" * 100, hashed) is False  # over 72 bytes: rejected, not a crash
    assert hashed != app_module.hash_password("secret")            # random salt


# Read
def test_get_all_and_one_item(auth_client):
    assert len(auth_client.get("/inventory").get_json()) == 5
    item = auth_client.get("/inventory/3").get_json()  # OpenFoodFacts shape: status + product
    assert item["status"] == 1 and item["product"]["product_name"] == "Organic Almond Milk"


@pytest.mark.parametrize("query,expected_ids", [("almond", [3]), ("BARILLA", [5]), ("zzzz", [])])
def test_search_by_name_or_brand(auth_client, query, expected_ids):
    assert [i["id"] for i in auth_client.get(f"/inventory?q={query}").get_json()] == expected_ids


@pytest.mark.parametrize("method,url", [
    ("get", "/inventory/999"), ("get", "/inventory/abc"), ("patch", "/inventory/999"),
    ("delete", "/inventory/999"), ("post", "/inventory/999/enrich"),
])
def test_missing_item_returns_404(auth_client, method, url):
    assert getattr(auth_client, method)(url).status_code == 404


# Create
def test_add_item(auth_client):
    auth_client.delete("/inventory/2")  # a gap in the IDs must not cause a duplicate
    body = add_plain_item(auth_client, price="10.999", stock="5").get_json()  # text numbers are accepted
    assert (body["id"], body["price"], body["stock"]) == (6, 11.0, 5)
    assert auth_client.get("/inventory/6").get_json()["product"]["product_name"] == "Tea"


@pytest.mark.parametrize("body", [
    {"product_name": "X", "price": -1, "stock": 1}, {"product_name": "X", "price": "abc", "stock": 1},
    {"product_name": "X", "price": None, "stock": 1}, {"product_name": "X", "price": 1, "stock": 1.5},
    {"product_name": "X", "price": 1, "stock": -2}, {"product_name": "X", "price": 1, "stock": "many"},
    {"price": 5, "stock": 5},  # no name and no barcode
])
def test_add_rejects_bad_input(auth_client, body):
    assert auth_client.post("/inventory", json=body).status_code == 400
    assert inventory_count(auth_client) == 5


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_add_enriches_from_api(mock_fetch, auth_client):
    filled = auth_client.post("/inventory", json={"barcode": "123", "price": 2, "stock": 5}).get_json()
    typed = add_plain_item(auth_client, product_name="My Juice", barcode="123", enrich=True).get_json()
    assert filled["product"]["product_name"] == "Mock Juice" and "warning" not in filled
    assert typed["product"]["product_name"] == "My Juice"  # what the employee typed wins
    assert typed["product"]["brands"] == "MockCo"          # empty fields are filled by the API
    mock_fetch.assert_called_with(barcode="123")


@pytest.mark.parametrize("patch_args,word", [
    ({"return_value": None}, "not found"), ({"side_effect": ExternalAPIError("down")}, "unavailable"),
])
def test_add_still_saves_with_a_warning_when_api_has_no_answer(auth_client, patch_args, word):
    with mock.patch("app.fetch_product", **patch_args):
        response = add_plain_item(auth_client, barcode="9", enrich=True)
        barcode_only = auth_client.post("/inventory", json={"barcode": "9", "price": 2, "stock": 5})
    assert response.status_code == 201 and word in response.get_json()["warning"].lower()
    assert barcode_only.status_code == 400  # nothing to name the item with
    assert inventory_count(auth_client) == 6


@mock.patch("app.fetch_product")
@pytest.mark.parametrize("fields", [{"barcode": "123", "enrich": False}, {}])  # enrich off, or no barcode
def test_api_is_not_called_when_not_needed(mock_fetch, auth_client, fields):
    add_plain_item(auth_client, **fields)
    mock_fetch.assert_not_called()


# Update
def test_patch_updates_only_the_fields_sent(auth_client):
    body = auth_client.patch("/inventory/1", json={"price": 900, "stock": 12, "brands": " New Brand "}).get_json()
    assert (body["price"], body["stock"], body["product"]["brands"]) == (900.0, 12, "New Brand")
    assert body["product"]["product_name"] == "Nutella"  # untouched


@pytest.mark.parametrize("bad_fields", [
    {"price": "abc"}, {"price": -5}, {"stock": 2.5}, {"stock": -1},
    {"price": 1, "stock": "bad"},  # one good field + one bad: nothing may change
    {"unknown": 1}, {}, {"product_name": "  "},
])
def test_patch_rejects_bad_input_and_changes_nothing(auth_client, bad_fields):
    assert auth_client.patch("/inventory/1", json=bad_fields).status_code == 400
    item = auth_client.get("/inventory/1").get_json()
    assert (item["price"], item["stock"], item["product"]["product_name"]) == (850.0, 40, "Nutella")


# Delete
def test_delete_item(auth_client):
    assert auth_client.delete("/inventory/2").status_code == 200
    assert auth_client.get("/inventory/2").status_code == 404 and inventory_count(auth_client) == 4
    assert auth_client.delete("/inventory/2").status_code == 404  # already gone


# OpenFoodFacts routes
def test_external_search_needs_barcode_or_name(auth_client):
    assert auth_client.get("/external/search").status_code == 400


@mock.patch("app.fetch_product", return_value=make_api_result())
@pytest.mark.parametrize("query,expected_call", [
    ("barcode=123", {"barcode": "123", "name": None}), ("name=juice", {"barcode": None, "name": "juice"}),
])
def test_external_search_success(mock_fetch, auth_client, query, expected_call):
    response = auth_client.get(f"/external/search?{query}")
    assert response.status_code == 200 and response.get_json()["product"]["brands"] == "MockCo"
    mock_fetch.assert_called_once_with(**expected_call)
    assert inventory_count(auth_client) == 5  # searching never changes the inventory


@pytest.mark.parametrize("patch_args,status", [({"return_value": None}, 404), ({"side_effect": ExternalAPIError("x")}, 502)])
@pytest.mark.parametrize("call", [lambda c: c.get("/external/search?barcode=1"), lambda c: c.post("/inventory/1/enrich")])
def test_api_not_found_or_down(auth_client, call, patch_args, status):
    with mock.patch("app.fetch_product", **patch_args):
        assert call(auth_client).status_code == status


@mock.patch("app.fetch_product", return_value=make_api_result(name="Other Name", quantity="1 kg"))
def test_enrich_fills_only_empty_fields(mock_fetch, auth_client):
    add_plain_item(auth_client, barcode="123")  # item 6: looked up by barcode
    add_plain_item(auth_client)                 # item 7: no barcode, so looked up by name
    item = auth_client.post("/inventory/6/enrich").get_json()
    assert item["product"]["product_name"] == "Tea"                                        # kept
    assert (item["product"]["quantity"], item["product"]["brands"]) == ("1 kg", "MockCo")  # filled
    mock_fetch.assert_called_with(barcode="123", name=None)
    auth_client.post("/inventory/7/enrich")
    mock_fetch.assert_called_with(barcode=None, name="Tea")


# Saving to data/inventory.json
@mock.patch("app.fetch_product", return_value=make_api_result())
def test_every_change_is_saved_to_the_json_file(_mock, auth_client):
    def saved():
        return json.loads(Path(app_module.DATA_FILE).read_text(encoding="utf-8"))

    add_plain_item(auth_client, barcode="123")
    assert saved()[-1]["product"]["product_name"] == "Tea"  # data/ folder was created too
    assert app_module.load_inventory()[-1]["product"]["product_name"] == "Tea"  # and it loads again
    auth_client.patch("/inventory/6", json={"stock": 99})
    assert saved()[-1]["stock"] == 99
    auth_client.post("/inventory/6/enrich")
    assert saved()[-1]["product"]["brands"] == "MockCo"
    auth_client.delete("/inventory/6")
    assert all(item["id"] != 6 for item in saved())


@pytest.mark.parametrize("content", [None, "this is not json", "", '{"not": "a list"}'])  # None = no file
def test_load_falls_back_to_sample_data(client, content):
    if content is not None:
        path = Path(app_module.DATA_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    assert app_module.load_inventory() == app_module.SEED_INVENTORY


# Cookie route and request inspector
def test_preference_cookie(auth_client):
    assert auth_client.get("/preferences").get_json() == {"stock_filter": "All"}
    cookie = auth_client.post("/preferences", json={"stock_filter": "Low"}).headers["Set-Cookie"]
    assert "stock_filter=Low" in cookie and "Max-Age=604800" in cookie
    assert auth_client.get("/preferences").get_json()["stock_filter"] == "Low"  # browser sends it back
    assert auth_client.post("/preferences", json={"stock_filter": "bad"}).status_code == 400


def test_tampered_preference_cookie_falls_back_to_all(client):
    client.set_cookie("stock_filter", "hacked")
    assert client.get("/preferences").get_json()["stock_filter"] == "All"


def test_request_info(client):
    assert client.get("/request-info").get_json()["logged_in_user"] is None
    client.post("/login", json=LOGIN)
    body = client.post("/request-info?source=test", json={"x": 1}).get_json()
    assert (body["method"], body["query_parameters"], body["json_body"]) == ("POST", {"source": "test"}, {"x": 1})
    assert body["logged_in_user"] == "admin"