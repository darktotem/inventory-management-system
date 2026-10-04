# CLI Inventory Management System

An inventory management system and administrator portal for a small retail company. Employees can add, view, edit and delete stock items through a **Flask REST API**, a **command-line interface (CLI)**, or a **web page**. Product details are enriched with live data from the **OpenFoodFacts API**. Prices are in **KES** (Kenyan shillings).

## Features

- Flask REST API with full CRUD for inventory (`GET`, `POST`, `PATCH`, `DELETE`)
- Session-based admin login with **bcrypt**-hashed passwords
- OpenFoodFacts lookup by barcode or product name, plus "enrich" to fill in missing details
- Interactive CLI menu and one-line CLI commands
- Single-page web UI (login, add, search, edit price/stock, delete, find on OpenFoodFacts)
- Data kept in an in-memory array and saved to `data/inventory.json` so it survives restarts
- Cookie that remembers the stock filter, and a request inspector route for debugging
- Unit tests with `pytest` and `unittest.mock` (the real OpenFoodFacts API is never called in tests)

## Project structure

```
cli-inventory-management-system/
├── app.py                 # Flask API: routes, mock data, OpenFoodFacts functions
├── cli.py                 # CLI client (menu mode + one-line commands)
├── requirements.txt       # Python dependencies
├── README.md
├── .gitignore
├── data/
│   └── inventory.json     # Saved inventory (created automatically, not committed)
├── templates/
│   └── index.html         # Admin portal page
├── static/
│   ├── app.js             # Front-end logic (calls the API)
│   └── styles.css         # Styling
└── tests/
    ├── conftest.py        # Shared fixtures (test client, logged-in client)
    ├── test_api.py        # API endpoint tests
    ├── test_external.py   # OpenFoodFacts function tests (mocked)
    └── test_cli.py        # CLI tests (mocked)
```

## Installation and setup

**Requirements:** Python 3.9 or newer (developed on Python 3.14.4) and Git.

```bash
# 1. Clone the repository
git clone https://github.com/darktotem/cli-inventory-management-system.git
cd cli-inventory-management-system

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt
```

### Run the app

The CLI and the web page both talk to the Flask server, so the server must be running first. Use two terminals.

**Terminal 1: start the server (leave it open)**

```bash
source .venv/bin/activate
python app.py
```

Wait for `Running on http://127.0.0.1:5000`. Debug mode is on, so the server restarts when you save a `.py` file and shows a detailed traceback when something crashes.

**Web page:** open http://127.0.0.1:5000 in a browser.

**Terminal 2: start the CLI**

```bash
source .venv/bin/activate
python cli.py
```

### Login

| Username | Password |
|----------|----------|
| `admin`  | `admin123` |

This is a demo account created when the app starts. For a real deployment, load the secret key and the admin password from environment variables.

## API endpoints

All inventory and external-search routes require login (a session cookie from `POST /login`). Requests and responses use JSON.

| Method | Route | Login? | Purpose |
|--------|-------|--------|---------|
| `GET` | `/` | No | The web page |
| `POST` | `/login` | No | Log in and start a session |
| `POST` | `/logout` | No | End the session |
| `GET` | `/me` | No | Who is logged in |
| `GET` | `/inventory` | Yes | Fetch all items (optional `?q=` search) |
| `GET` | `/inventory/<id>` | Yes | Fetch one item |
| `POST` | `/inventory` | Yes | Add a new item |
| `PATCH` | `/inventory/<id>` | Yes | Update an item |
| `DELETE` | `/inventory/<id>` | Yes | Remove an item |
| `GET` | `/external/search` | Yes | Search OpenFoodFacts by `?barcode=` or `?name=` |
| `POST` | `/inventory/<id>/enrich` | Yes | Fill an item's empty details from OpenFoodFacts |
| `GET` / `POST` | `/preferences` | POST only | Read/save the stock filter cookie |
| `GET` / `POST` | `/request-info` | No | Show what Flask received from the client |

### Item format

Items follow the OpenFoodFacts shape (`status` + `product`) with our own `id`, `barcode`, `price` (KES) and `stock`:

```json
{
  "id": 3,
  "barcode": "0025293600232",
  "status": 1,
  "price": 650.0,
  "stock": 25,
  "product": {
    "product_name": "Organic Almond Milk",
    "brands": "Silk",
    "ingredients_text": "Filtered water, almonds, cane sugar, sea salt, ...",
    "categories": "Beverages, Plant-based milks, Almond milks",
    "quantity": "1.89 L",
    "nutriscore_grade": "c"
  }
}
```

### Route planning: inputs, outputs, effect and CLI trigger

| Route | Input | Output | What it changes | CLI trigger |
|-------|-------|--------|-----------------|-------------|
| `POST /login` | JSON `username`, `password` | `200`; `401` "Username not found" or "Incorrect password" | Starts a session | Automatic before every command |
| `GET /inventory` | Optional `?q=` | `200` list of items | Nothing | Menu 1, `python cli.py list [--search milk]` |
| `GET /inventory/<id>` | ID in URL | `200` item; `404` | Nothing | Menu 2, `python cli.py view 3` |
| `POST /inventory` | `price`, `stock`, and `product_name` or `barcode`; optional `brands`, `enrich` | `201` item (plus `warning` if the API failed); `400` | Appends a new item with a new ID | Menu 3, `python cli.py add ...` |
| `PATCH /inventory/<id>` | Any of `price`, `stock`, `product_name`, `brands`, `ingredients_text`, `categories`, `quantity` | `200` item; `400`; `404` | Changes only the fields sent | Menu 4, `python cli.py update 3 --price 700` |
| `DELETE /inventory/<id>` | ID in URL | `200` message; `404` | Removes the item | Menu 5, `python cli.py delete 3` |
| `GET /external/search` | `?barcode=` or `?name=` | `200` product; `400`; `404`; `502` API down | Nothing | Menu 6, `python cli.py find --barcode ...` |
| `POST /inventory/<id>/enrich` | ID in URL | `200` item; `404`; `502` | Fills only empty fields | Menu 7, `python cli.py enrich 3` |

Validation rules: `price` must be a number of 0 or more, and `stock` must be a whole number of 0 or more. An unknown item ID returns `404`. A failing OpenFoodFacts call never blocks adding an item. The item is saved and the response carries a `warning`.

### Example requests (curl)

```bash
# Log in and keep the session cookie
curl -c cookies.txt -X POST http://127.0.0.1:5000/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'

# View all items
curl -b cookies.txt http://127.0.0.1:5000/inventory

# Add an item (details fill in from the barcode)
curl -b cookies.txt -X POST http://127.0.0.1:5000/inventory \
  -H "Content-Type: application/json" \
  -d '{"barcode": "3017620422003", "price": 850, "stock": 10}'

# Update price and stock
curl -b cookies.txt -X PATCH http://127.0.0.1:5000/inventory/1 \
  -H "Content-Type: application/json" \
  -d '{"price": 900, "stock": 30}'

# Delete an item
curl -b cookies.txt -X DELETE http://127.0.0.1:5000/inventory/1
```

### Testing with Postman

1. Send `POST http://127.0.0.1:5000/login` with a JSON body of `{"username": "admin", "password": "admin123"}`.
2. Postman stores the session cookie automatically, so the other requests are logged in.
3. Try each route from the table above. Without logging in first, you get `401 Login required`.

## CLI usage

Start the server first (see [Run the app](#run-the-app)).

### Interactive menu

```bash
python cli.py
```

```
=== Inventory Admin ===
1. List items
2. View item
3. Add item
4. Update price/stock
5. Delete item
6. Find product on OpenFoodFacts
7. Enrich item from OpenFoodFacts
0. Exit
```

Type a number and press Enter. The menu asks for each value and asks again if the input is invalid.

### One-line commands

```bash
python cli.py list                                   # all items
python cli.py list --search milk                     # filter by name or brand
python cli.py view 3                                 # one item
python cli.py add --name "Tea" --price 120 --stock 40
python cli.py add --barcode 3017620422003 --price 850 --stock 10   # details fetched from OpenFoodFacts
python cli.py add --name "Tea" --price 120 --stock 40 --no-enrich  # skip the API lookup
python cli.py update 3 --price 700                   # update price only
python cli.py update 3 --price 700 --stock 12        # update price and stock
python cli.py delete 3                               # remove an item
python cli.py find --barcode 5449000000996           # search OpenFoodFacts by barcode
python cli.py find --name spaghetti                  # search OpenFoodFacts by name
python cli.py enrich 3                               # fill missing details from the API
```

### CLI settings

The CLI logs in as `admin` by default. Override the defaults with environment variables:

```bash
INVENTORY_API=http://127.0.0.1:5000 INVENTORY_USER=admin INVENTORY_PASS=admin123 python cli.py
```

## Running the tests

```bash
python -m pytest -v
```

| File | What it checks |
|------|----------------|
| `tests/test_api.py` | Login required, GET/POST/PATCH/DELETE, validation errors, 404s, search, enrich, bcrypt hashing, cookie route |
| `tests/test_external.py` | OpenFoodFacts lookup by barcode and name, "not found", timeouts, bad JSON (all mocked) |
| `tests/test_cli.py` | Each CLI command, error messages, unreachable API, interactive menu |

`unittest.mock` replaces the real network calls, so the tests are fast and work offline. The test client saves to a temporary file, so running the tests never touches your real `data/inventory.json`.

## Data storage

The `inventory` list in `app.py` is the working storage. After every add, update, delete or enrich, it is also written to `data/inventory.json`. On startup the app loads that file, or falls back to five sample products if the file is missing or damaged. To reset to the sample data, stop the server and delete `data/inventory.json`.

## Challenges and how they were fixed

| Challenge | What we saw | Fix |
|-----------|-------------|-----|
| Missing helper functions | HTTP 500 when adding an item; editor warnings saying "undefined" | `fetch_product`, `fill_missing_fields`, `_normalize_product` and `ExternalAPIError` were not defined in `app.py`. Defined them above the routes. |
| Login crash on unknown username | HTTP 500 when the username did not exist | `user["username"]` was read when `user` was `None`. Check `if not user` first, then return "Username not found" or "Incorrect password". |
| bcrypt name clash | `AttributeError: 'Bcrypt' object has no attribute 'hashpw'` | `bcrypt = Bcrypt(app)` (Flask-Bcrypt) hid the plain `bcrypt` package. Used the Flask-Bcrypt methods `generate_password_hash` and `check_password_hash`. |
| "Route not found" on login | Login failed with a 404 JSON message | The JavaScript called `/api/login` but Flask served `/login`. Made the front-end URLs match the Flask routes. |
| "Connection refused" in the CLI | `Cannot reach the API at http://127.0.0.1:5000` | The CLI does not start the server. Run `python app.py` in one terminal and the CLI in another. |
| Data lost on restart | New items vanished, especially when debug mode reloaded the server | Added `load_inventory()` and `save_inventory()` so the array is saved to `data/inventory.json`. |
| Tests overwriting real data | Running pytest could replace saved inventory | The test fixture points `DATA_FILE` at a temporary folder with `monkeypatch`. |


## Common mistakes to avoid

- **Forgetting to start the server.** The CLI and the web page need `python app.py` running in another terminal. "Connection refused" always means the server is down.
- **Running with the wrong Python.** Install packages and run the app inside the same virtual environment. If `flask_bcrypt` is "not found", you are using the system Python instead of `.venv`.
- **Mismatched URLs.** Every `fetch("/login")` in `app.js` and every URL in `cli.py` must match a `@app.route(...)` in `app.py` exactly, including any `/api/` prefix.
- **Naming a variable after a library.** `bcrypt = Bcrypt(app)` hides the `bcrypt` package. Check the imports when a method "does not exist".
- **Pasting code below `app.run(...)`.** Anything after `if __name__ == "__main__":` is not defined when the server starts. Put functions and routes above it.
- **Ignoring editor warnings.** A yellow "undefined" squiggle is a crash waiting to happen. Fix it before running.
- **Reading a key from a value that may be `None`.** Check that the item or user exists before reading from it. Return a clear error such as `404` instead of crashing with `500`.
- **Letting tests touch real data.** Point tests at a temporary file, and never let them write to `data/inventory.json`.
- **Committing secrets or local files.** Keep `.venv/`, `__pycache__/`, `.env` and `data/inventory.json` out of Git (see `.gitignore`). Do not commit real passwords or secret keys.
- **Trusting browser data.** Cookie values and request bodies can be edited by anyone. The app checks the stock filter against an allowed list and validates `price` and `stock` before using them.

## Code style and maintainability

- `app.py` is organised in clearly labelled sections: password hashing, data, helpers, external API, page routes, authentication, inventory CRUD, external API routes, cookies and request inspector.
- Small helpers (`find_item`, `next_id`, `parse_price`, `parse_stock`, `login_required_json`) keep the routes short and readable.
- `PATCH` validates every field before changing anything, so a bad field never leaves an item half updated.
- Comments explain why something is done (for example, why a failing API must not block adding an item), not just what the line does.
- `cli.py` has one function per command and one `call()` function that handles every HTTP request and error message.
- Tests mock the network and use temporary files, so they are safe to run at any time.

## Notes

- The Flask `secret_key` and the demo admin password are hard-coded for learning purposes only.
- Anyone who is logged in has full access to the inventory.
- Barcodes in the sample data are examples. OpenFoodFacts may not know all of them.
- Prices are stored as plain numbers and displayed as KES in the CLI and the web page.