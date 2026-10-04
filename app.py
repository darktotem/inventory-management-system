import copy

from flask import Flask, render_template, request, jsonify, session
from werkzeug.security import generate_password_hash, check_password_hash
 
app = Flask(__name__)

# Flask uses SECRET_KEY to sign the session cookie.
# This helps Flask detect if someone has tampered with the session data.
# In a real application, this value should come from an environment variable.
app.secret_key = "inventory-demo-secret"


OFF_BASE = "https://world.openfoodfacts.org"
OFF_HEADERS = {"User-Agent": "RetailInventoryAdmin/1.0 (student project)"}
OFF_TIMEOUT = 5 

# -----------------------------------------------------------------------------
# IN-MEMORY DATA
# -----------------------------------------------------------------------------
# We are using Python lists so that students can focus on Flask concepts first.
# Restarting the app will reset the data. A database can be introduced later.

users = [
    {
        "id": 1, 
        "username": "admin", 
        "password_hash": generate_password_hash("admin123")
        
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


# -----------------------------------------------------------------------------
# HELPER FUNCTIONS
# -----------------------------------------------------------------------------



# -----------------------------------------------------------------------------
# PAGE ROUTES
# -----------------------------------------------------------------------------


# -----------------------------------------------------------------------------
# AUTHENTICATION ROUTES
# -----------------------------------------------------------------------------


  # -------------------------------------------------------------------------
    # SESSION EXAMPLE
    # -------------------------------------------------------------------------
    # A session helps Flask remember information across multiple requests.
    # After login, we save the username in the session.
    # On later requests, Flask can read session["username"] and know who is using
    # the application without asking for the username again on every request.
    # Flask's default session is stored in a signed cookie in the browser.



# -----------------------------------------------------------------------------
# CRUD ROUTES - HELP DESK TICKETS
# -----------------------------------------------------------------------------



# -----------------------------------------------------------------------------
# COOKIE ROUTES
# -----------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # COOKIE EXAMPLE
    # -------------------------------------------------------------------------
    # set_cookie() tells the browser to remember a value.
    # The browser sends this cookie back automatically on later requests.
    # We use max_age so it can remain after the browser is refreshed/reopened.
    # We are NOT storing a password or other sensitive information here.


# -----------------------------------------------------------------------------
# CLIENT-SERVER / REQUEST INSPECTOR
# -----------------------------------------------------------------------------