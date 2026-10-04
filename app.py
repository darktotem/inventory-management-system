import copy

from flask import Flask
from flask_bcrypt import Bcrypt
from flask import Flask, render_template, request, jsonify, session, make_response
 
app = Flask(__name__)
bcrypt = Bcrypt(app)

# Flask uses SECRET_KEY to sign the session cookie.
# This helps Flask detect if someone has tampered with the session data.
# In a real application, this value should come from an environment variable.
app.secret_key = "inventory-demo-secret"


OFF_BASE = "https://world.openfoodfacts.org"
OFF_HEADERS = {"User-Agent": "RetailInventoryAdmin/1.0 (student project)"}
OFF_TIMEOUT = 5 

# -----------------------------------------------------------------------------
# PASSWORD HASHING (bcrypt)
# -----------------------------------------------------------------------------

def hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
 
 
def verify_password(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError: 
        return False
 

# -----------------------------------------------------------------------------
# IN-MEMORY DATA
# -----------------------------------------------------------------------------
# We are using Python lists so that students can focus on Flask concepts first.
# Restarting the app will reset the data. A database can be introduced later.

users = [
    {
        "id": 1, 
        "username": "admin", 
        "password_hash": hash_password("admin123")
        
    }
]
 
SEED_INVENTORY = [
    {
        "id": 1, "barcode": "3017620422003", 
        "status": 1, 
        "price": 850.00, 
        "stock": 40,
        "product": {
            "product_name": "Nutella", 
            "brands": "Ferrero",
            "ingredients_text": "Sugar, palm oil, hazelnuts, skimmed milk powder, cocoa, lecithin, vanillin",
            "categories": "Spreads, Sweet spreads, Hazelnut spreads",
            "quantity": "400 g", "nutriscore_grade": "e",
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
            "quantity": "330 ml", "nutriscore_grade": "e",
        },
    },
    {
        "id": 3, "barcode": "0025293600232", 
        "status": 1, 
        "price": 650.00, 
        "stock": 25,
        "product": {
            "product_name": "Organic Almond Milk", "brands": "Silk",
            "ingredients_text": "Filtered water, almonds, cane sugar, sea salt, locust bean gum, sunflower lecithin",
            "categories": "Beverages, Plant-based milks, Almond milks",
            "quantity": "1.89 L", "nutriscore_grade": "c",
        },
    },
    {
        "id": 4, "barcode": 
        "7622210449283", "status": 1, 
        "price": 250.25, 
        "stock": 60,
        "product": {
            "product_name": "Prince Chocolate Biscuits", "brands": "LU",
            "ingredients_text": "Wheat flour, sugar, vegetable oils, cocoa powder, glucose syrup, salt",
            "categories": "Snacks, Sweet snacks, Biscuits",
            "quantity": "300 g", "nutriscore_grade": "d",
        },
    },
    {
        "id": 5, "barcode": "8076800195057", 
        "status": 1, 
        "price": 220.00, 
        "stock": 8,
        "product": {
            "product_name": "Spaghetti n.5", "brands": "Barilla",
            "ingredients_text": "Durum wheat semolina, water",
            "categories": "Cereals and potatoes, Pasta, Spaghetti",
            "quantity": "500 g", "nutriscore_grade": "a",
        },
    },
]
 
inventory = copy.deepcopy(SEED_INVENTORY)

# Fields a client may change with PATCH.
TOP_LEVEL_FIELDS = ["price", "stock"]
PRODUCT_FIELDS = ["product_name", "brands", "ingredients_text", "categories", "quantity"]

#Restore the seed data. Used by the unit tests.
def reset_data():
    inventory[:] = copy.deepcopy(SEED_INVENTORY)

# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------
def current_username():
    return session.get("username")
 
 
def login_required_json():
    if not current_username():
        return jsonify({"error": "Login required"}), 401 #No user logged in
    return None
 
#Linear search by ID: worst case O(n) for n items.
def find_item(item_id):
    for item in inventory:
        if item["id"] == item_id:
            return item
    return None
 
 
def next_id():
    return max([item["id"] for item in inventory], default=0) + 1
 
#Return a non-negative float rounded to 2 decimals, or None if invalid.
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
 
#Return a non-negative int, or None if invalid.
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
# PAGE ROUTES
# -----------------------------------------------------------------------------
@app.route("/")
def home():
    return render_template("index.html")

# -----------------------------------------------------------------------------
# AUTHENTICATION ROUTES
# -----------------------------------------------------------------------------

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    password = str(data.get("password", ""))
 
    user = next((u for u in users if u["username"] == username), None)

    if not user["username"] or not verify_password(password, user["password_hash"]):
        return jsonify({"error": "Invalid username or password"}), 401
 
    session["username"] = username  # Flask remembers this across requests
    return jsonify({"message": "Login successful", "username": username}), 200
 

  # -------------------------------------------------------------------------
    # SESSION EXAMPLE
    # -------------------------------------------------------------------------
    # A session helps Flask remember information across multiple requests.
    # After login, we save the username in the session.
    # On later requests, Flask can read session["username"] and know who is using
    # the application without asking for the username again on every request.
    # Flask's default session is stored in a signed cookie in the browser.
@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("username", None)
    return jsonify({"message": "Logged out successfully"}), 200
 
 
@app.route("/api/me", methods=["GET"])
def me():
    username = current_username()
    return jsonify({"logged_in": bool(username), "username": username}), 200


# -----------------------------------------------------------------------------
# CRUD ROUTES - HELP DESK TICKETS
# -----------------------------------------------------------------------------

@app.route("/api/inventory", methods=["GET"])
def get_inventory():
    auth_error = login_required_json()
    if auth_error:
        return auth_error
 
    # Optional search: GET /inventory?q=milk matches product name or brand.
    q = request.args.get("q", "").strip().lower()
    if q:
        items = [i for i in inventory
                 if q in i["product"].get("product_name", "").lower()
                 or q in i["product"].get("brands", "").lower()]
    else:
        items = inventory
    return jsonify(items), 200

@app.route("/api/inventory/<int:item_id>", methods=["GET"])
def get_item(item_id):
    auth_error = login_required_json()
    if auth_error:
        return auth_error
 
    item = find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404
    return jsonify(item), 200
 
 
@app.route("/api/inventory", methods=["POST"])
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
    response = dict(new_item)
    if warning:
        response["warning"] = warning
    return jsonify(response), 201
 
 
@app.route("/api/inventory/<int:item_id>", methods=["PATCH"])
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
    return jsonify(item), 200
 
 
@app.route("/api/inventory/<int:item_id>", methods=["DELETE"])
def delete_item(item_id):
    auth_error = login_required_json()
    if auth_error:
        return auth_error
 
    item = find_item(item_id)
    if not item:
        return jsonify({"error": "Item not found"}), 404
 
    inventory.remove(item)
    return jsonify({"message": "Item deleted successfully"}), 200


# -----------------------------------------------------------------------------
# EXTERNAL API ROUTES
# -----------------------------------------------------------------------------
@app.route("/api/external/search", methods=["GET"])
def external_search():
    """GET /api/external/search?barcode=... or ?name=... (does NOT change inventory)."""
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
 
 
@app.route("/api/inventory/<int:item_id>/enrich", methods=["POST"])
def enrich_item(item_id):
    """Fill empty details of a stored item from OpenFoodFacts (barcode, else name)."""
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


@app.route("/api/preferences", methods=["GET"])
def get_preferences():
    """Read the saved stock filter from the browser's cookie."""
    stock_filter = request.cookies.get("stock_filter", "All")
    if stock_filter not in STOCK_FILTERS:  # never trust a cookie value blindly
        stock_filter = "All"
    return jsonify({"stock_filter": stock_filter}), 200


@app.route("/api/preferences", methods=["POST"])
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
# -----------------------------------------------------------------------------
# CLIENT-SERVER / REQUEST INSPECTOR
# -----------------------------------------------------------------------------
@app.route("/api/request-info", methods=["GET", "POST"])
def request_info():
    """Return information Flask received from the client/browser."""
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