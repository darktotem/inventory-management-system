# Tests for the Flask API routes. OpenFoodFacts is always mocked.
import json
from pathlib import Path
from unittest import mock

import pytest

import app as app_module
from app import ExternalAPIError

# Build a fake OpenFoodFacts result in the shape fetch_product() returns.
def make_api_result(name="Mock Juice", barcode="123", **fields):
    product = {
        "product_name": name, "brands": "MockCo", "ingredients_text": "Water, apple",
        "categories": "Beverages", "quantity": "1 L", "nutriscore_grade": "b",
    }
    product.update(fields)
    return {"status": 1, "barcode": barcode, "product": product}

# Add an item without any API lookup and return the response.
def add_plain_item(client, **overrides):
    
    body = {"product_name": "Tea", "price": 120, "stock": 40, "enrich": False}
    body.update(overrides)
    return client.post("/inventory", json=body)

# Read what was written to the (temporary) JSON file.
def saved_file():
    with open(app_module.DATA_FILE, encoding="utf-8") as f:
        return json.load(f)



# Pages, errors and authentication
def test_home_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Inventory" in response.data


def test_unknown_route_returns_json_404(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Route not found"


def test_wrong_method_returns_json_405(client):
    response = client.delete("/login")
    assert response.status_code == 405
    assert response.get_json()["error"] == "Method not allowed"


PROTECTED_ROUTES = [
    ("get", "/inventory"),
    ("get", "/inventory/1"),
    ("post", "/inventory"),
    ("patch", "/inventory/1"),
    ("delete", "/inventory/1"),
    ("get", "/external/search?barcode=1"),
    ("post", "/inventory/1/enrich"),
    ("post", "/preferences"),
]


@pytest.mark.parametrize("method,url", PROTECTED_ROUTES)
def test_protected_routes_need_login(client, method, url):
    response = getattr(client, method)(url)
    assert response.status_code == 401
    assert response.get_json()["error"] == "Login required"


def test_login_success_starts_session(client):
    response = client.post("/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    assert response.get_json()["username"] == "admin"
    assert client.get("/me").get_json() == {"logged_in": True, "username": "admin"}


def test_login_ignores_spaces_around_username(client):
    response = client.post("/login", json={"username": "  admin  ", "password": "admin123"})
    assert response.status_code == 200


def test_login_unknown_username(client):
    response = client.post("/login", json={"username": "ghost", "password": "x"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "Username not found"


def test_login_wrong_password(client):
    response = client.post("/login", json={"username": "admin", "password": "nope"})
    assert response.status_code == 401
    assert response.get_json()["error"] == "Incorrect password"


def test_login_without_body(client):
    assert client.post("/login").status_code == 401


def test_me_when_logged_out(client):
    assert client.get("/me").get_json() == {"logged_in": False, "username": None}


def test_logout_ends_session(auth_client):
    assert auth_client.post("/logout").status_code == 200
    assert auth_client.get("/me").get_json()["logged_in"] is False
    assert auth_client.get("/inventory").status_code == 401


# Password hashing (bcrypt)
def test_passwords_are_bcrypt_hashed():
    stored = app_module.users[0]["password_hash"]
    assert stored.startswith("$2") and "admin123" not in stored


def test_hash_and_verify_password():
    hashed = app_module.hash_password("secret")
    assert hashed != "secret"
    assert app_module.verify_password("secret", hashed) is True
    assert app_module.verify_password("wrong", hashed) is False


def test_same_password_gets_different_hashes():
    assert app_module.hash_password("secret") != app_module.hash_password("secret")  # random salt


def test_overlong_password_is_rejected_not_a_crash():
    hashed = app_module.hash_password("secret")
    assert app_module.verify_password("x" * 100, hashed) is False


# Input parsing helpers
@pytest.mark.parametrize("value,expected", [
    (5, 5.0), ("120", 120.0), ("3.14159", 3.14), (0, 0.0),
    ("abc", None), (-1, None), (None, None), (True, None), (float("nan"), None),
])
def test_parse_price(value, expected):
    assert app_module.parse_price(value) == expected


@pytest.mark.parametrize("value,expected", [
    (5, 5), ("7", 7), (0, 0), (2.0, 2),
    (1.5, None), (-1, None), ("x", None), (True, None), (None, None),
])
def test_parse_stock(value, expected):
    assert app_module.parse_stock(value) == expected


# GET /inventory and GET /inventory/<id>
def test_get_all_items(auth_client):
    response = auth_client.get("/inventory")
    assert response.status_code == 200
    items = response.get_json()
    assert len(items) == 5
    assert all("id" in item for item in items)


def test_items_have_openfoodfacts_shape(auth_client):
    item = auth_client.get("/inventory/3").get_json()
    assert item["status"] == 1
    assert item["product"]["product_name"] == "Organic Almond Milk"
    assert item["product"]["brands"] == "Silk"
    assert "ingredients_text" in item["product"]


def test_search_by_name(auth_client):
    names = [i["product"]["product_name"] for i in auth_client.get("/inventory?q=almond").get_json()]
    assert names == ["Organic Almond Milk"]


def test_search_by_brand_ignores_case(auth_client):
    items = auth_client.get("/inventory?q=BARILLA").get_json()
    assert [i["id"] for i in items] == [5]


def test_search_with_no_match_returns_empty_list(auth_client):
    response = auth_client.get("/inventory?q=zzzz")
    assert response.status_code == 200 and response.get_json() == []


def test_get_one_item(auth_client):
    response = auth_client.get("/inventory/1")
    assert response.status_code == 200
    assert response.get_json()["product"]["product_name"] == "Nutella"


def test_get_missing_item_returns_404(auth_client):
    response = auth_client.get("/inventory/999")
    assert response.status_code == 404
    assert response.get_json()["error"] == "Item not found"


def test_non_numeric_id_returns_404(auth_client):
    assert auth_client.get("/inventory/abc").status_code == 404


# POST /inventory
def test_add_item(auth_client):
    response = add_plain_item(auth_client)
    assert response.status_code == 201
    body = response.get_json()
    assert body["id"] == 6
    assert body["product"]["product_name"] == "Tea"
    assert (body["price"], body["stock"]) == (120.0, 40)
    assert len(auth_client.get("/inventory").get_json()) == 6
    assert auth_client.get("/inventory/6").status_code == 200


def test_new_id_never_collides_after_a_delete(auth_client):
    auth_client.delete("/inventory/2")  # a gap in the middle must not cause a duplicate ID
    new_id = add_plain_item(auth_client).get_json()["id"]
    assert new_id == 6
    ids = [item["id"] for item in auth_client.get("/inventory").get_json()]
    assert len(ids) == len(set(ids))


def test_add_accepts_numbers_sent_as_text_and_rounds_price(auth_client):
    body = add_plain_item(auth_client, price="10.999", stock="5").get_json()
    assert (body["price"], body["stock"]) == (11.0, 5)


@pytest.mark.parametrize("bad_fields", [
    {"price": -1}, {"price": "abc"}, {"price": None},
    {"stock": 1.5}, {"stock": -2}, {"stock": "many"}, {"stock": None},
])
def test_add_rejects_invalid_price_or_stock(auth_client, bad_fields):
    response = add_plain_item(auth_client, **bad_fields)
    assert response.status_code == 400
    assert len(auth_client.get("/inventory").get_json()) == 5  # nothing was added


def test_add_requires_a_name_or_barcode(auth_client):
    response = auth_client.post("/inventory", json={"price": 5, "stock": 5})
    assert response.status_code == 400
    assert "product_name" in response.get_json()["error"]


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_add_with_barcode_fills_details_from_api(mock_fetch, auth_client):
    response = auth_client.post("/inventory", json={"barcode": "123", "price": 2, "stock": 5})
    body = response.get_json()
    assert response.status_code == 201
    assert body["product"]["product_name"] == "Mock Juice"
    assert body["product"]["ingredients_text"] == "Water, apple"
    assert "warning" not in body
    mock_fetch.assert_called_once_with(barcode="123")


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_add_keeps_what_the_employee_typed(_mock, auth_client):
    body = auth_client.post("/inventory", json={
        "barcode": "123", "product_name": "My Juice", "price": 2, "stock": 5}).get_json()
    assert body["product"]["product_name"] == "My Juice"  # typed value wins
    assert body["product"]["brands"] == "MockCo"           # empty field filled by the API


@mock.patch("app.fetch_product", return_value=None)
def test_add_with_unknown_barcode_warns(_mock, auth_client):
    response = add_plain_item(auth_client, barcode="000", enrich=True)
    assert response.status_code == 201
    assert "not found" in response.get_json()["warning"].lower()


@mock.patch("app.fetch_product", side_effect=ExternalAPIError("down"))
def test_add_survives_api_failure(_mock, auth_client):
    response = add_plain_item(auth_client, barcode="9", enrich=True)
    assert response.status_code == 201
    assert "unavailable" in response.get_json()["warning"].lower()
    assert len(auth_client.get("/inventory").get_json()) == 6


@mock.patch("app.fetch_product", side_effect=ExternalAPIError("down"))
def test_add_barcode_only_fails_cleanly_when_api_is_down(_mock, auth_client):
    response = auth_client.post("/inventory", json={"barcode": "9", "price": 2, "stock": 5})
    assert response.status_code == 400  # nothing to name the item with
    assert len(auth_client.get("/inventory").get_json()) == 5


@mock.patch("app.fetch_product")
def test_enrich_false_skips_the_api(mock_fetch, auth_client):
    add_plain_item(auth_client, barcode="123", enrich=False)
    mock_fetch.assert_not_called()


@mock.patch("app.fetch_product")
def test_no_barcode_means_no_api_call(mock_fetch, auth_client):
    add_plain_item(auth_client)
    mock_fetch.assert_not_called()


# PATCH /inventory/<id>
def test_patch_price_and_stock(auth_client):
    response = auth_client.patch("/inventory/1", json={"price": 900, "stock": 12})
    assert response.status_code == 200
    body = response.get_json()
    assert (body["price"], body["stock"]) == (900.0, 12)
    assert auth_client.get("/inventory/1").get_json()["price"] == 900.0


def test_patch_only_changes_the_fields_sent(auth_client):
    auth_client.patch("/inventory/1", json={"stock": 1})
    item = auth_client.get("/inventory/1").get_json()
    assert item["stock"] == 1 and item["price"] == 850.0


def test_patch_product_fields(auth_client):
    body = auth_client.patch("/inventory/1", json={"brands": "  New Brand  ", "quantity": "1 kg"}).get_json()
    assert body["product"]["brands"] == "New Brand"
    assert body["product"]["quantity"] == "1 kg"
    assert body["product"]["product_name"] == "Nutella"


@pytest.mark.parametrize("bad_fields", [{"price": "abc"}, {"price": -5}, {"stock": 2.5}, {"stock": -1}])
def test_patch_rejects_invalid_values(auth_client, bad_fields):
    assert auth_client.patch("/inventory/1", json=bad_fields).status_code == 400


def test_failed_patch_changes_nothing(auth_client):
    auth_client.patch("/inventory/1", json={"price": 1, "stock": "bad"})  # one good field, one bad
    item = auth_client.get("/inventory/1").get_json()
    assert (item["price"], item["stock"]) == (850.0, 40)


def test_patch_with_no_valid_fields(auth_client):
    assert auth_client.patch("/inventory/1", json={"unknown": 1}).status_code == 400
    assert auth_client.patch("/inventory/1", json={}).status_code == 400


def test_patch_cannot_blank_the_name(auth_client):
    assert auth_client.patch("/inventory/1", json={"product_name": "  "}).status_code == 400


def test_patch_cannot_change_the_id(auth_client):
    auth_client.patch("/inventory/1", json={"id": 99, "stock": 3})
    assert auth_client.get("/inventory/1").status_code == 200
    assert auth_client.get("/inventory/99").status_code == 404


def test_patch_missing_item_returns_404(auth_client):
    assert auth_client.patch("/inventory/999", json={"price": 1}).status_code == 404


# DELETE /inventory/<id>
def test_delete_item(auth_client):
    response = auth_client.delete("/inventory/2")
    assert response.status_code == 200
    assert "deleted" in response.get_json()["message"].lower()
    assert auth_client.get("/inventory/2").status_code == 404
    assert len(auth_client.get("/inventory").get_json()) == 4


def test_delete_twice_returns_404(auth_client):
    auth_client.delete("/inventory/2")
    assert auth_client.delete("/inventory/2").status_code == 404


# GET /external/search
def test_external_search_needs_barcode_or_name(auth_client):
    response = auth_client.get("/external/search")
    assert response.status_code == 400


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_external_search_by_barcode(mock_fetch, auth_client):
    response = auth_client.get("/external/search?barcode=123")
    assert response.status_code == 200
    assert response.get_json()["product"]["brands"] == "MockCo"
    mock_fetch.assert_called_once_with(barcode="123", name=None)


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_external_search_by_name(mock_fetch, auth_client):
    assert auth_client.get("/external/search?name=juice").status_code == 200
    mock_fetch.assert_called_once_with(barcode=None, name="juice")


@mock.patch("app.fetch_product", return_value=None)
def test_external_search_not_found(_mock, auth_client):
    response = auth_client.get("/external/search?barcode=0")
    assert response.status_code == 404
    assert "not found" in response.get_json()["error"].lower()


@mock.patch("app.fetch_product", side_effect=ExternalAPIError("down"))
def test_external_search_api_down(_mock, auth_client):
    response = auth_client.get("/external/search?barcode=1")
    assert response.status_code == 502
    assert "unavailable" in response.get_json()["error"].lower()


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_external_search_does_not_change_inventory(_mock, auth_client):
    auth_client.get("/external/search?barcode=123")
    assert len(auth_client.get("/inventory").get_json()) == 5


# POST /inventory/<id>/enrich
@mock.patch("app.fetch_product", return_value=make_api_result(name="Other Name", quantity="1 kg"))
def test_enrich_fills_only_empty_fields(mock_fetch, auth_client):
    add_plain_item(auth_client, barcode="123")  # item 6: only name, price, stock, barcode
    item = auth_client.post("/inventory/6/enrich").get_json()
    assert item["product"]["product_name"] == "Tea"       # kept
    assert item["product"]["quantity"] == "1 kg"          # filled
    assert item["product"]["brands"] == "MockCo"          # filled
    mock_fetch.assert_called_once_with(barcode="123", name=None)


@mock.patch("app.fetch_product", return_value=make_api_result(name="Other", quantity="9 kg"))
def test_enrich_never_overwrites_existing_details(_mock, auth_client):
    item = auth_client.post("/inventory/1/enrich").get_json()  # Nutella already has everything
    assert item["product"]["product_name"] == "Nutella"
    assert item["product"]["quantity"] == "400 g"


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_enrich_uses_the_name_when_there_is_no_barcode(mock_fetch, auth_client):
    add_plain_item(auth_client)  # no barcode
    auth_client.post("/inventory/6/enrich")
    mock_fetch.assert_called_once_with(barcode=None, name="Tea")


def test_enrich_missing_item_returns_404(auth_client):
    assert auth_client.post("/inventory/999/enrich").status_code == 404


@mock.patch("app.fetch_product", return_value=None)
def test_enrich_product_not_found(_mock, auth_client):
    assert auth_client.post("/inventory/1/enrich").status_code == 404


@mock.patch("app.fetch_product", side_effect=ExternalAPIError("down"))
def test_enrich_api_down(_mock, auth_client):
    assert auth_client.post("/inventory/1/enrich").status_code == 502


# Saving to data/inventory.json
def test_changes_are_saved_to_the_json_file(auth_client):
    add_plain_item(auth_client)
    assert saved_file()[-1]["product"]["product_name"] == "Tea"  # data/ folder was created too

    auth_client.patch("/inventory/6", json={"stock": 99})
    assert saved_file()[-1]["stock"] == 99

    auth_client.delete("/inventory/6")
    assert all(item["id"] != 6 for item in saved_file())


@mock.patch("app.fetch_product", return_value=make_api_result())
def test_enrich_is_saved_to_the_json_file(_mock, auth_client):
    add_plain_item(auth_client, barcode="123")
    auth_client.post("/inventory/6/enrich")
    assert saved_file()[-1]["product"]["brands"] == "MockCo"


def test_saved_file_can_be_loaded_again(auth_client):
    add_plain_item(auth_client)
    assert app_module.load_inventory()[-1]["product"]["product_name"] == "Tea"


def test_load_falls_back_to_sample_data_when_file_is_missing(client):
    assert app_module.load_inventory() == app_module.SEED_INVENTORY


@pytest.mark.parametrize("content", ["this is not json", "", '{"not": "a list"}'])
def test_load_falls_back_to_sample_data_when_file_is_bad(client, content):
    path = Path(app_module.DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    assert app_module.load_inventory() == app_module.SEED_INVENTORY


# Cookie route and request inspector
def test_preference_defaults_to_all(client):
    assert client.get("/preferences").get_json() == {"stock_filter": "All"}


def test_save_preference_sets_a_cookie(auth_client):
    response = auth_client.post("/preferences", json={"stock_filter": "Low"})
    assert response.status_code == 200
    cookie = response.headers["Set-Cookie"]
    assert "stock_filter=Low" in cookie and "Max-Age=604800" in cookie
    assert auth_client.get("/preferences").get_json()["stock_filter"] == "Low"  # browser sends it back


def test_save_preference_rejects_unknown_filter(auth_client):
    assert auth_client.post("/preferences", json={"stock_filter": "bad"}).status_code == 400


def test_tampered_preference_cookie_falls_back_to_all(client):
    client.set_cookie("stock_filter", "hacked")
    assert client.get("/preferences").get_json()["stock_filter"] == "All"


def test_request_info_shows_what_flask_received(auth_client):
    body = auth_client.post("/request-info?source=test", json={"x": 1}).get_json()
    assert body["method"] == "POST"
    assert body["path"] == "/request-info"
    assert body["query_parameters"] == {"source": "test"}
    assert body["json_body"] == {"x": 1}
    assert body["logged_in_user"] == "admin"


def test_request_info_when_logged_out(client):
    assert client.get("/request-info").get_json()["logged_in_user"] is None