# Tests for the CLI. The API is mocked, so the Flask server does not need to be running.
from unittest import mock

import pytest
import requests

import cli

# A stand-in for the logged-in requests.Session that returns one fixed response.
def fake_session(status=200, body=None):
    response = mock.Mock(status_code=status)
    response.json.return_value = body if body is not None else {}
    session = mock.Mock()
    session.request.return_value = response
    return session


ITEM = {"id": 1, "barcode": "123", "price": 850.0, "stock": 40,
        "product": {"product_name": "Nutella", "brands": "Ferrero", "ingredients_text": "Sugar, palm oil"}}

# Run the CLI with a fake API and return (exit code, the fake session)."""
def run(argv, session=None):
    session = session or fake_session(body=ITEM)
    with mock.patch("cli.get_session", return_value=session):
        code = cli.main(argv)
    return code, session

# The (method, url, kwargs) of the one request the CLI made.
def sent(session):

    call = session.request.call_args
    return call.args[0], call.args[1], call.kwargs


# One-line commands
def test_list_prints_items_in_kes(capsys):
    code, session = run(["list"], fake_session(body=[ITEM]))
    out = capsys.readouterr().out
    assert code == 0
    assert "Nutella" in out and "KES" in out and "850.00" in out
    assert sent(session)[:2] == ("GET", f"{cli.BASE_URL}/inventory")


def test_list_search_sends_query(capsys):
    _, session = run(["list", "--search", "milk"], fake_session(body=[]))
    assert sent(session)[2]["params"] == {"q": "milk"}
    assert "No items found" in capsys.readouterr().out


def test_view_prints_details(capsys):
    code, session = run(["view", "1"])
    out = capsys.readouterr().out
    assert code == 0
    assert sent(session)[:2] == ("GET", f"{cli.BASE_URL}/inventory/1")
    assert "[1] Nutella" in out and "KES 850.00" in out and "stock: 40" in out and "123" in out


def test_add_sends_the_right_payload(capsys):
    code, session = run(["add", "--name", "Tea", "--brand", "Lipton", "--price", "120", "--stock", "40"],
                        fake_session(201, ITEM))
    method, url, kwargs = sent(session)
    assert code == 0 and (method, url) == ("POST", f"{cli.BASE_URL}/inventory")
    assert kwargs["json"] == {"price": 120.0, "stock": 40, "product_name": "Tea",
                              "brands": "Lipton", "barcode": "", "enrich": True}
    assert "Item added" in capsys.readouterr().out


def test_add_with_barcode_only():
    _, session = run(["add", "--barcode", "3017620422003", "--price", "850", "--stock", "10"], fake_session(201, ITEM))
    payload = sent(session)[2]["json"]
    assert payload["barcode"] == "3017620422003" and payload["product_name"] == ""


def test_add_no_enrich_flag():
    _, session = run(["add", "--name", "Tea", "--price", "1", "--stock", "1", "--no-enrich"], fake_session(201, ITEM))
    assert sent(session)[2]["json"]["enrich"] is False


def test_add_prints_api_warning(capsys):
    body = dict(ITEM, warning="OpenFoodFacts is unavailable; item saved without extra details")
    run(["add", "--name", "Tea", "--price", "1", "--stock", "1"], fake_session(201, body))
    assert "Warning:" in capsys.readouterr().out


def test_add_requires_price_and_stock():
    with pytest.raises(SystemExit) as exc:
        cli.main(["add", "--name", "Tea"])
    assert exc.value.code == 2


def test_update_price_and_stock():
    code, session = run(["update", "1", "--price", "900", "--stock", "30"])
    method, url, kwargs = sent(session)
    assert code == 0 and (method, url) == ("PATCH", f"{cli.BASE_URL}/inventory/1")
    assert kwargs["json"] == {"price": 900.0, "stock": 30}


def test_update_sends_only_the_given_field():
    _, session = run(["update", "1", "--stock", "7"])
    assert sent(session)[2]["json"] == {"stock": 7}


def test_update_needs_at_least_one_field(capsys):
    code, session = run(["update", "1"])
    assert code == 1
    assert "Nothing to update" in capsys.readouterr().err
    session.request.assert_not_called()


def test_delete(capsys):
    code, session = run(["delete", "1"], fake_session(body={"message": "Item deleted successfully"}))
    assert code == 0 and sent(session)[:2] == ("DELETE", f"{cli.BASE_URL}/inventory/1")
    assert "deleted" in capsys.readouterr().out


FOUND = {"status": 1, "barcode": "123", "product": {
    "product_name": "Mock", "brands": "B", "quantity": "1 L", "nutriscore_grade": "a", "ingredients_text": "Water"}}


def test_find_by_barcode(capsys):
    code, session = run(["find", "--barcode", "123"], fake_session(body=FOUND))
    assert code == 0
    assert sent(session)[:2] == ("GET", f"{cli.BASE_URL}/external/search")
    assert sent(session)[2]["params"] == {"barcode": "123", "name": ""}
    assert "Mock" in capsys.readouterr().out


def test_find_by_name():
    _, session = run(["find", "--name", "spaghetti"], fake_session(body=FOUND))
    assert sent(session)[2]["params"] == {"barcode": "", "name": "spaghetti"}


def test_find_needs_barcode_or_name(capsys):
    code, session = run(["find"])
    assert code == 1 and "barcode" in capsys.readouterr().err
    session.request.assert_not_called()


def test_enrich(capsys):
    code, session = run(["enrich", "1"])
    assert code == 0 and sent(session)[:2] == ("POST", f"{cli.BASE_URL}/inventory/1/enrich")
    assert "enriched" in capsys.readouterr().out.lower()


def test_id_must_be_a_number():
    with pytest.raises(SystemExit) as exc:
        cli.main(["view", "abc"])
    assert exc.value.code == 2


# Errors
def test_api_error_message_is_shown(capsys):
    code, _ = run(["view", "99"], fake_session(404, {"error": "Item not found"}))
    assert code == 1
    assert "Item not found" in capsys.readouterr().err


def test_server_error_without_json_gets_a_generic_message(capsys):
    session = fake_session(500)
    session.request.return_value.json.side_effect = ValueError("not json")
    code, _ = run(["list"], session)
    assert code == 1 and "HTTP 500" in capsys.readouterr().err


def test_unreachable_api(capsys):
    with mock.patch("cli.get_session", side_effect=requests.ConnectionError("refused")):
        assert cli.main(["list"]) == 1
    assert "Cannot reach" in capsys.readouterr().err


def test_request_timeout(capsys):
    session = mock.Mock()
    session.request.side_effect = requests.Timeout("slow")
    code, _ = run(["list"], session)
    assert code == 1 and "Cannot reach" in capsys.readouterr().err


def test_get_session_logs_in():
    with mock.patch("cli.requests.Session") as session_class:
        session = session_class.return_value
        session.post.return_value = mock.Mock(status_code=200)
        assert cli.get_session() is session
    assert session.post.call_args.args[0].endswith("/login")
    assert session.post.call_args.kwargs["json"] == {"username": cli.USERNAME, "password": cli.PASSWORD}


def test_get_session_login_failure(capsys):
    with mock.patch("cli.requests.Session") as session_class:
        session_class.return_value.post.return_value = mock.Mock(status_code=401)
        with pytest.raises(cli.CLIError):
            cli.get_session()
        assert cli.main(["list"]) == 1
    assert "Login failed" in capsys.readouterr().err


# Interactive menu (python cli.py with no arguments)
# Run the menu, feeding it the given keyboard input in order.
def run_menu(inputs, session=None):

    session = session or fake_session(body=ITEM)
    with mock.patch("cli.get_session", return_value=session), \
            mock.patch("builtins.input", side_effect=inputs):
        code = cli.main([])
    return code, session


def test_menu_exit(capsys):
    code, _ = run_menu(["0"])
    out = capsys.readouterr().out
    assert code == 0 and "Inventory Admin" in out and "Goodbye" in out


def test_menu_list(capsys):
    code, session = run_menu(["1", "", "0"], fake_session(body=[ITEM]))
    assert code == 0 and "Nutella" in capsys.readouterr().out
    assert sent(session)[:2] == ("GET", f"{cli.BASE_URL}/inventory")


def test_menu_view():
    _, session = run_menu(["2", "1", "0"])
    assert sent(session)[:2] == ("GET", f"{cli.BASE_URL}/inventory/1")


def test_menu_add():
    _, session = run_menu(["3", "Tea", "Lipton", "", "120", "40", "0"], fake_session(201, ITEM))
    payload = sent(session)[2]["json"]
    assert payload["product_name"] == "Tea" and payload["brands"] == "Lipton"
    assert payload["price"] == 120.0 and payload["stock"] == 40


def test_menu_update_skips_blank_fields():
    _, session = run_menu(["4", "1", "900", "", "0"])
    assert sent(session)[2]["json"] == {"price": 900.0}


def test_menu_update_with_nothing_shows_error_and_keeps_running(capsys):
    code, session = run_menu(["4", "1", "", "", "0"])
    out = capsys.readouterr().out
    assert code == 0 and "Nothing to update" in out and "Goodbye" in out
    session.request.assert_not_called()


def test_menu_delete():
    _, session = run_menu(["5", "1", "0"], fake_session(body={"message": "Item deleted successfully"}))
    assert sent(session)[:2] == ("DELETE", f"{cli.BASE_URL}/inventory/1")


def test_menu_find():
    _, session = run_menu(["6", "123", "", "0"], fake_session(body=FOUND))
    assert sent(session)[2]["params"] == {"barcode": "123", "name": ""}


def test_menu_enrich():
    _, session = run_menu(["7", "1", "0"])
    assert sent(session)[:2] == ("POST", f"{cli.BASE_URL}/inventory/1/enrich")


def test_menu_rejects_invalid_choice(capsys):
    code, _ = run_menu(["9", "abc", "0"])
    assert code == 0 and capsys.readouterr().out.count("Please choose a number") == 2


def test_menu_asks_again_after_invalid_number(capsys):
    _, session = run_menu(["4", "1", "abc", "900", "", "0"])
    assert "Invalid value" in capsys.readouterr().out
    assert sent(session)[2]["json"] == {"price": 900.0}


def test_menu_asks_again_when_required_field_is_blank(capsys):
    _, session = run_menu(["2", "", "1", "0"])
    assert "required" in capsys.readouterr().out
    assert sent(session)[1].endswith("/inventory/1")


def test_menu_shows_api_errors_and_keeps_running(capsys):
    code, _ = run_menu(["2", "99", "0"], fake_session(404, {"error": "Item not found"}))
    out = capsys.readouterr().out
    assert code == 0 and "Error: Item not found" in out and "Goodbye" in out


@pytest.mark.parametrize("interrupt", [EOFError, KeyboardInterrupt])
def test_menu_exits_cleanly_on_ctrl_d_or_ctrl_c(interrupt, capsys):
    with mock.patch("builtins.input", side_effect=interrupt):
        assert cli.main([]) == 0
    assert "Goodbye" in capsys.readouterr().out