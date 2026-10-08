import copy
import json
import os

import requests
from flask import Flask, render_template, request, jsonify, session, make_response
from flask_bcrypt import Bcrypt

app = Flask(__name__)
bcrypt = Bcrypt(app)

# Flask uses SECRET_KEY to sign the session cookie.
# This helps Flask detect if someone has tampered with the session data.
# In a real application, this value should come from an environment variable.
app.secret_key = "inventory-demo-secret"


OFF_BASE = "https://world.openfoodfacts.org"
OFF_HEADERS = {"User-Agent": "RetailInventoryAdmin/1.0 (student project)"}
OFF_TIMEOUT = 5  # seconds - never let an outside API hang our server


class ExternalAPIError(Exception):
    """Raised when OpenFoodFacts cannot be reached or returns bad data."""


# -----------------------------------------------------------------------------
# PASSWORD HASHING (bcrypt)
# -----------------------------------------------------------------------------
def hash_password(password):
    return bcrypt.generate_password_hash(password).decode("utf-8")


def verify_password(password, password_hash):
    try:
        return bcrypt.check_password_hash(password_hash, password)
    except ValueError:  # e.g. password longer than bcrypt's 72-byte limit
        return False


# -----------------------------------------------------------------------------
# IN-MEMORY DATA
# -----------------------------------------------------------------------------
# The inventory list is our working storage. It is also saved to
# data/inventory.json after every change so it survives a restart.

users = [
    {
        "id": 1,
        "username": "admin",
        "password_hash": hash_password("admin123"),
    }
]

SEED_INVENTORY = [
    {
        "id": 1,
        "barcode": "3017620422003",
        "status": 1,
        "price": 850.00,
        "stock": 40,
        "product": {
            "product_name": "Nutella",
            "brands": "Ferrero",
            "ingredients_text": "Sugar, palm oil, hazelnuts, skimmed milk powder, cocoa, lecithin, vanillin",
            "categories": "Spreads, Sweet spreads, Hazelnut spreads",
            "quantity": "400 g",
            "nutriscore_grade": "e",
        },
    },
    {
        "id": 2,
        "barcode": "5449000000996",
        "status": 1,
        "price": 50.00,
        "stock": 120,
        "product": {
            "product_name": "Coca-Cola",
            "brands": "Coca-Cola",
            "ingredients_text": "Carbonated water, sugar, permitted food colour, acids, artificial flavouring",
            "categories": "Beverages, Carbonated drinks, Sodas",
            "quantity": "330 ml",
            "nutriscore_grade": "e",
        },
    },
    {
        "id": 3,
        "barcode": "0025293600232",
        "status": 1,
        "price": 650.00,
        "stock": 25,
        "product": {
            "product_name": "Organic Almond Milk",
            "brands": "Silk",
            "ingredients_text": "Filtered water, almonds, cane sugar, sea salt, locust bean gum, sunflower lecithin",
            "categories": "Beverages, Plant-based milks, Almond milks",
            "quantity": "1.89 L",
            "nutriscore_grade": "c",
        },
    },
    {
        "id": 4,
        "barcode": "7622210449283",
        "status": 1,
        "price": 250.25,
        "stock": 60,
        "product": {
            "product_name": "Prince Chocolate Biscuits",
            "brands": "LU",
            "ingredients_text": "Wheat flour, sugar, vegetable oils, cocoa powder, glucose syrup, salt",
            "categories": "Snacks, Sweet snacks, Biscuits",
            "quantity": "300 g",
            "nutriscore_grade": "d",
        },
    },
    {
        "id": 5,
        "barcode": "8076800195057",
        "status": 1,
        "price": 220.00,
        "stock": 8,
        "product": {
            "product_name": "Spaghetti n.5",
            "brands": "Barilla",
            "ingredients_text": "Durum wheat semolina, water",
            "categories": "Cereals and potatoes, Pasta, Spaghetti",
            "quantity": "500 g",
            "nutriscore_grade": "a",
        },
    },
]

# The JSON file lives in a data/ folder next to app.py.
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "inventory.json")


def load_inventory():
    #Load items from data/inventory.json, or fall back to the seed data.
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            items = json.load(f)
        if isinstance(items, list):
            return items
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return copy.deepcopy(SEED_INVENTORY)


def save_inventory():
    """Write the current array to data/inventory.json."""
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)  # create data/ if it's missing
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(inventory, f, indent=2)


inventory = load_inventory()

# Fields a client may change with PATCH.
TOP_LEVEL_FIELDS = ["price", "stock"]
PRODUCT_FIELDS = ["product_name", "brands", "ingredients_text", "categories", "quantity"]


# Restore the seed data. Used by the unit tests.
def reset_data():
    inventory[:] = copy.deepcopy(SEED_INVENTORY)


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def current_username():
    return session.get("username")


def login_required_json():
    if not current_username():
        return jsonify({"error": "Login required"}), 401  # No user logged in
    return None


# Linear search by ID: worst case O(n) for n items.
def find_item(item_id):
    for item in inventory:
        if item["id"] == item_id:
            return item
    return None


def next_id():
    return max([item["id"] for item in inventory], default=0) + 1


# Return a non-negative float rounded to 2 decimals, or None if invalid.
def parse_price(value):
    if isinstance(value, bool):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price != price or price < 0:  # price != price catches NaN
        return None
    return round(price, 2)


# Return a non-negative int, or None if invalid.
def parse_stock(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and not value.is_integer():
        return None
    try:
        stock = int(value)
    except (TypeError, ValueError):
        return None
    return stock if stock >= 0 else None


# -----------------------------------------------------------------------------
# EXTERNAL API (OpenFoodFacts)
# -----------------------------------------------------------------------------
def _normalize_product(raw):
    # Keep only the fields we care about from an OpenFoodFacts product.
    return {
        "product_name": raw.get("product_name", "") or "",
        "brands": raw.get("brands", "") or "",
        "ingredients_text": raw.get("ingredients_text", "") or "",
        "categories": raw.get("categories", "") or "",
        "quantity": raw.get("quantity", "") or "",
        "nutriscore_grade": raw.get("nutriscore_grade", "") or "",
    }


def fetch_product(barcode=None, name=None):
    """Look a product up on OpenFoodFacts by barcode (preferred) or by name. 
    Returns {"status": 1, "barcode": "...", "product": {...}} or None if not found. 
    Raises ExternalAPIError if the network/API fails, ValueError if no input given."""

    if not barcode and not name:
        raise ValueError("barcode or name is required")

    try:
        if barcode:
            resp = requests.get(
                f"{OFF_BASE}/api/v0/product/{barcode}.json",
                headers=OFF_HEADERS, timeout=OFF_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") != 1:
                return None
            raw = payload.get("product", {})
            return {"status": 1, "barcode": raw.get("code", barcode),
                    "product": _normalize_product(raw)}

        resp = requests.get(
            f"{OFF_BASE}/cgi/search.pl",
            params={"search_terms": name, "search_simple": 1, "action": "process",
                    "json": 1, "page_size": 1},
            headers=OFF_HEADERS, timeout=OFF_TIMEOUT,
        )
        resp.raise_for_status()
        products = resp.json().get("products", [])
        if not products:
            return None
        return {"status": 1, "barcode": products[0].get("code", ""),
                "product": _normalize_product(products[0])}
    except (requests.RequestException, ValueError) as exc:
        raise ExternalAPIError(str(exc)) from exc


def fill_missing_fields(item, api_result):
    #Copy API details into an item, but never overwrite what we already have.
    for key, value in api_result["product"].items():
        if value and not item["product"].get(key):
            item["product"][key] = value
    if api_result.get("barcode") and not item.get("barcode"):
        item["barcode"] = api_result["barcode"]


# -----------------------------------------------------------------------------
# PAGE ROUTES
# -----------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")


# -----------------------------------------------------------------------------
# AUTHENTICATION ROUTES
# -----------------------------------------------------------------------------
@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))

    user = next((u for u in users if u["username"] == username), None)
    if not user:
        return jsonify({"error": "Username not found"}), 401

    if not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Incorrect password"}), 401

    # -------------------------------------------------------------------------
    # SESSION EXAMPLE
    # -------------------------------------------------------------------------
    # A session helps Flask remember information across multiple requests.
    # After login, we save the username in the session.
    # On later requests, Flask can read session["username"] and know who is using
    # the application without asking for the username again on every request.
    # Flask's default session is stored in a signed cookie in the browser.
    session["username"] = username
    return jsonify({"message": "Login successful", "username": username}), 200


@app.route("/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    return jsonify({"message": "Logged out successfully"}), 200


@app.route("/me", methods=["GET"])
def me():
    username = current_username()
    return jsonify({"logged_in": True, "username": username}), 200


# -----------------------------------------------------------------------------
# CRUD ROUTES - INVENTORY
# -----------------------------------------------------------------------------
@app.route("/inventory", methods=["GET"])
def get_inventory():
    auth_error = login_required_json()
    if auth_error:
        return auth_error


@app.route("/inventory/<int:item_id>", methods=["GET"])
def get_item(item_id):
    auth_error = login_required_json()
    if auth_error:
        return auth_error
    
    # READ one item using the O(n) linear search helper above
    item = find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404
    
    return jsonify(item), 200


@app.route("/inventory", methods=["POST"])
def create_item():
    auth_error = login_required_json()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}

    price = parse_price(data.get("price"))
    stock = parse_stock(data.get("stock"))
    if price is None:
        return jsonify({"error": "price must be a number >= 0"}), 400
    if stock is None:
        return jsonify({"error": "stock must be a whole number >= 0"}), 400

    barcode = str(data.get("barcode", "")).strip()
    new_item = {
        "id": next_id(), "barcode": barcode, "status": 1, "price": price, "stock": stock,
        "product": {f: str(data.get(f, "")).strip() for f in PRODUCT_FIELDS},
    }

    # Enrich from OpenFoodFacts when a barcode is given. A failing API must not
    # block the employee, so we add the item anyway and return a warning.
    warning = None
    if barcode and data.get("enrich", True):
        try:
            result = fetch_product(barcode=barcode)
            if result:
                fill_missing_fields(new_item, result)
            else:
                warning = "Barcode not found on OpenFoodFacts"
        except ExternalAPIError:
            warning = "OpenFoodFacts is unavailable; item saved without extra details"

    if not new_item["product"]["product_name"]:
        return jsonify({"error": "product_name is required (or a barcode OpenFoodFacts knows)"}), 400

    inventory.append(new_item)
    save_inventory()
    response = dict(new_item)
    if warning:
        response["warning"] = warning
    return jsonify(response), 201


@app.route("/inventory/<int:item_id>", methods=["PATCH"])
def update_item(item_id):
    auth_error = login_required_json()
    if auth_error:
        return auth_error

    item = find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    data = request.get_json(silent=True) or {}

    # Validate everything first so a bad field never leaves a half-updated item.
    updates = {}
    if "price" in data:
        updates["price"] = parse_price(data["price"])
        if updates["price"] is None:
            return jsonify({"error": "price must be a number >= 0"}), 400
    if "stock" in data:
        updates["stock"] = parse_stock(data["stock"])
        if updates["stock"] is None:
            return jsonify({"error": "stock must be a whole number >= 0"}), 400
    product_updates = {f: str(data[f]).strip() for f in PRODUCT_FIELDS if f in data}

    if not updates and not product_updates:
        return jsonify({"error": "No valid fields to update"}), 400
    if "product_name" in product_updates and not product_updates["product_name"]:
        return jsonify({"error": "product_name cannot be empty"}), 400

    item.update(updates)
    item["product"].update(product_updates)
    save_inventory()
    return jsonify(item), 200


@app.route("/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    auth_error = login_required_json()
    if auth_error:
        return auth_error

    item = find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    inventory.remove(item)
    save_inventory()
    return jsonify({"message": "Item deleted successfully"}), 200


# -----------------------------------------------------------------------------
# EXTERNAL API ROUTES
# -----------------------------------------------------------------------------
@app.route("/external/search", methods=["GET"])
def external_search():
    #GET /external/search?barcode=... or ?name=... (does NOT change inventory)
    auth_error = login_required_json()
    if auth_error:
        return auth_error

    barcode = request.args.get("barcode", "").strip()
    name = request.args.get("name", "").strip()
    if not barcode and not name:
        return jsonify({"error": "Provide a barcode or a name"}), 400

    try:
        result = fetch_product(barcode=barcode or None, name=name or None)
    except ExternalAPIError:
        return jsonify({"error": "OpenFoodFacts is unavailable, try again later"}), 502

    if not result:
        return jsonify({"error": "Product not found on OpenFoodFacts"}), 404
    return jsonify(result), 200


@app.route("/inventory/<int:item_id>/enrich", methods=["POST"])
def enrich_item(item_id):
    #Fill empty details of a stored item from OpenFoodFacts (barcode, else name).
    auth_error = login_required_json()
    if auth_error:
        return auth_error

    item = find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404

    try:
        result = fetch_product(
            barcode=item.get("barcode") or None,
            name=None if item.get("barcode") else item["product"].get("product_name"),
        )
    except ExternalAPIError:
        return jsonify({"error": "OpenFoodFacts is unavailable, try again later"}), 502

    if not result:
        return jsonify({"error": "Product not found on OpenFoodFacts"}), 404

    fill_missing_fields(item, result)
    save_inventory()
    return jsonify(item), 200


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"error": "Route not found"}), 404


@app.errorhandler(405)
def method_not_allowed(_error):
    return jsonify({"error": "Method not allowed"}), 405


# -----------------------------------------------------------------------------
# COOKIE ROUTES
# -----------------------------------------------------------------------------
STOCK_FILTERS = ["All", "Low", "Out"]


@app.route("/preferences", methods=["GET"])
def get_preferences():
    #Read the saved stock filter from the browser's cookie.
    stock_filter = request.cookies.get("stock_filter", "All")
    if stock_filter not in STOCK_FILTERS:  # never trust a cookie value blindly
        stock_filter = "All"
    return jsonify({"stock_filter": stock_filter}), 200


@app.route("/preferences", methods=["POST"])
def save_preferences():
    auth_error = login_required_json()
    if auth_error:
        return auth_error

    data = request.get_json(silent=True) or {}
    stock_filter = data.get("stock_filter", "All")
    if stock_filter not in STOCK_FILTERS:
        return jsonify({"error": "stock_filter must be All, Low or Out"}), 400

    response = make_response(
        jsonify({"message": "Preference saved", "stock_filter": stock_filter})
    )

    # -------------------------------------------------------------------------
    # COOKIE EXAMPLE
    # -------------------------------------------------------------------------
    # set_cookie() tells the browser to remember a value.
    # The browser sends this cookie back automatically on later requests.
    # We use max_age so it can remain after the browser is refreshed/reopened.
    # We are NOT storing a password or other sensitive information here.
    response.set_cookie("stock_filter", stock_filter, max_age=60 * 60 * 24 * 7)

    return response, 200


# -----------------------------------------------------------------------------
# CLIENT-SERVER / REQUEST INSPECTOR
# -----------------------------------------------------------------------------
@app.route("/request-info", methods=["GET", "POST"])
def request_info():
    #turn information Flask received from the client/browser.
    return jsonify(
        {
            "method": request.method,
            "path": request.path,
            "query_parameters": request.args.to_dict(),
            "json_body": request.get_json(silent=True),
            "cookies": request.cookies.to_dict(),
            "logged_in_user": current_username(),
            "user_agent": request.headers.get("User-Agent"),
        }
    ), 200


if __name__ == "__main__":
    app.run(debug=True)