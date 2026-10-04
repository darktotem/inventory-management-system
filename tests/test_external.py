# Tests for the OpenFoodFacts functions. requests.get is mocked, so no internet is used.
from unittest import mock

import pytest
import requests

import app as app_module
from app import ExternalAPIError, fetch_product, fill_missing_fields


def fake_response(payload=None, json_error=None, http_error=None):
    """A stand-in for the object requests.get() returns."""
    response = mock.Mock()
    response.raise_for_status.side_effect = http_error
    if json_error:
        response.json.side_effect = json_error
    else:
        response.json.return_value = payload
    return response


# Lookup by barcode
@mock.patch("app.requests.get")
def test_fetch_by_barcode(mock_get):
    mock_get.return_value = fake_response({"status": 1, "product": {
        "code": "111", "product_name": "Organic Almond Milk", "brands": "Silk",
        "ingredients_text": "Water, almonds", "quantity": "1 L"}})

    result = fetch_product(barcode="111")

    assert result["status"] == 1 and result["barcode"] == "111"
    assert result["product"]["product_name"] == "Organic Almond Milk"
    assert result["product"]["brands"] == "Silk"
    assert result["product"]["nutriscore_grade"] == ""  # missing fields become ""


@mock.patch("app.requests.get")
def test_barcode_request_uses_timeout_and_user_agent(mock_get):
    mock_get.return_value = fake_response({"status": 1, "product": {"code": "111"}})
    fetch_product(barcode="111")
    assert mock_get.call_args.args[0].endswith("/api/v0/product/111.json")
    assert mock_get.call_args.kwargs["timeout"] == app_module.OFF_TIMEOUT
    assert "User-Agent" in mock_get.call_args.kwargs["headers"]


@mock.patch("app.requests.get")
def test_none_values_become_empty_strings(mock_get):
    mock_get.return_value = fake_response({"status": 1, "product": {
        "code": "1", "product_name": None, "brands": None}})
    product = fetch_product(barcode="1")["product"]
    assert product["product_name"] == "" and product["brands"] == ""


@mock.patch("app.requests.get")
def test_barcode_is_used_before_name(mock_get):
    mock_get.return_value = fake_response({"status": 1, "product": {"code": "111"}})
    fetch_product(barcode="111", name="milk")
    assert mock_get.call_count == 1
    assert "111.json" in mock_get.call_args.args[0]


@mock.patch("app.requests.get")
def test_barcode_not_found_returns_none(mock_get):
    mock_get.return_value = fake_response({"status": 0, "status_verbose": "product not found"})
    assert fetch_product(barcode="000") is None


# Lookup by name
@mock.patch("app.requests.get")
def test_fetch_by_name(mock_get):
    mock_get.return_value = fake_response({"products": [
        {"code": "222", "product_name": "Oat Milk", "brands": "Oatly"}]})

    result = fetch_product(name="oat milk")

    assert result["barcode"] == "222"
    assert result["product"]["product_name"] == "Oat Milk"
    params = mock_get.call_args.kwargs["params"]
    assert params["search_terms"] == "oat milk" and params["json"] == 1 and params["page_size"] == 1


@mock.patch("app.requests.get")
@pytest.mark.parametrize("payload", [{"products": []}, {}])
def test_name_with_no_results_returns_none(mock_get, payload):
    mock_get.return_value = fake_response(payload)
    assert fetch_product(name="zzzz") is None



# Failures
@pytest.mark.parametrize("error", [
    requests.Timeout("slow"),
    requests.ConnectionError("no internet"),
])
@mock.patch("app.requests.get")
def test_network_problems_raise_external_api_error(mock_get, error):
    mock_get.side_effect = error
    with pytest.raises(ExternalAPIError):
        fetch_product(barcode="1")
    with pytest.raises(ExternalAPIError):
        fetch_product(name="milk")


@mock.patch("app.requests.get")
def test_http_error_raises_external_api_error(mock_get):
    mock_get.return_value = fake_response(http_error=requests.HTTPError("500 Server Error"))
    with pytest.raises(ExternalAPIError):
        fetch_product(barcode="1")


@pytest.mark.parametrize("json_error", [ValueError("not json"), requests.exceptions.JSONDecodeError("bad", "doc", 0)])
@mock.patch("app.requests.get")
def test_bad_json_raises_external_api_error(mock_get, json_error):
    mock_get.return_value = fake_response(json_error=json_error)
    with pytest.raises(ExternalAPIError):
        fetch_product(barcode="1")


@mock.patch("app.requests.get")
def test_missing_input_raises_value_error(mock_get):
    with pytest.raises(ValueError):
        fetch_product()
    with pytest.raises(ValueError):
        fetch_product(barcode="", name=None)
    mock_get.assert_not_called()



# fill_missing_fields
def test_fill_missing_fields_only_fills_empty_values():
    item = {"barcode": "", "product": {"product_name": "Tea", "brands": "", "quantity": ""}}
    result = {"barcode": "555", "product": {"product_name": "Other", "brands": "Lipton", "quantity": "50 g"}}

    fill_missing_fields(item, result)

    assert item["product"] == {"product_name": "Tea", "brands": "Lipton", "quantity": "50 g"}
    assert item["barcode"] == "555"


def test_fill_missing_fields_keeps_existing_barcode():
    item = {"barcode": "111", "product": {}}
    fill_missing_fields(item, {"barcode": "999", "product": {}})
    assert item["barcode"] == "111"


def test_fill_missing_fields_skips_empty_api_values():
    item = {"barcode": "1", "product": {"brands": ""}}
    fill_missing_fields(item, {"barcode": "1", "product": {"brands": ""}})
    assert item["product"]["brands"] == ""