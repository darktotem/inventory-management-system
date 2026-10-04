import argparse
import os
import sys

import requests

BASE_URL = os.environ.get("INVENTORY_API", "http://127.0.0.1:5000")
USERNAME = os.environ.get("INVENTORY_USER", "admin")
PASSWORD = os.environ.get("INVENTORY_PASS", "admin123")


class CLIError(Exception):
    """Any problem we want to show the user as a one-line message."""


def get_session():
    """Log in and return a requests.Session that carries the session cookie."""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/login", json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    if resp.status_code != 200:
        raise CLIError("Login failed - check INVENTORY_USER / INVENTORY_PASS")
    return session


def call(method, path, **kwargs):
    """Send one request to the Flask API and return the decoded JSON body."""
    try:
        session = get_session()
        resp = session.request(method, f"{BASE_URL}{path}", timeout=10, **kwargs)
    except requests.RequestException as exc:
        raise CLIError(f"Cannot reach the API at {BASE_URL}: {exc}")

    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code >= 400:
        raise CLIError(body.get("error", f"Request failed (HTTP {resp.status_code})"))
    return body


def show_item(item):
    p = item["product"]
    print(f"[{item['id']}] {p.get('product_name', '')} ({p.get('brands', '')})")
    print(f"     barcode: {item.get('barcode') or '-'} | price: KES {item['price']:,.2f} | stock: {item['stock']}")
    if p.get("ingredients_text"):
        print(f"     ingredients: {p['ingredients_text']}")


def cmd_list(args):
    items = call("GET", "/inventory", params={"q": args.search} if args.search else None)
    if not items:
        print("No items found.")
    for item in items:
        print(f"[{item['id']}] {item['product']['product_name']:<30} KES {item['price']:>10,.2f}  stock: {item['stock']}")


def cmd_view(args):
    show_item(call("GET", f"/inventory/{args.id}"))


def cmd_add(args):
    payload = {"price": args.price, "stock": args.stock, "product_name": args.name or "",
               "brands": args.brand or "", "barcode": args.barcode or "", "enrich": not args.no_enrich}
    item = call("POST", "/inventory", json=payload)
    print("Item added:")
    show_item(item)
    if item.get("warning"):
        print(f"Warning: {item['warning']}")


def cmd_update(args):
    payload = {}
    if args.price is not None:
        payload["price"] = args.price
    if args.stock is not None:
        payload["stock"] = args.stock
    if not payload:
        raise CLIError("Nothing to update: pass --price and/or --stock")
    print("Item updated:")
    show_item(call("PATCH", f"/inventory/{args.id}", json=payload))


def cmd_delete(args):
    print(call("DELETE", f"/inventory/{args.id}")["message"])


def cmd_find(args):
    if not args.barcode and not args.name:
        raise CLIError("Provide --barcode or --name")
    result = call("GET", "/external/search", params={"barcode": args.barcode or "", "name": args.name or ""})
    p = result["product"]
    print(f"Found: {p['product_name']} ({p['brands']}) - barcode {result['barcode']}")
    print(f"  quantity: {p['quantity']} | nutriscore: {p['nutriscore_grade'] or '-'}")
    print(f"  ingredients: {p['ingredients_text'] or '-'}")


def cmd_enrich(args):
    print("Item enriched:")
    show_item(call("POST", f"/inventory/{args.id}/enrich"))


def build_parser():
    parser = argparse.ArgumentParser(description="Retail inventory CLI")
    sub = parser.add_subparsers(dest="command")  # no command -> interactive menu

    p = sub.add_parser("list", help="List all items")
    p.add_argument("--search", help="Filter by name or brand")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("view", help="View one item")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_view)

    p = sub.add_parser("add", help="Add an item")
    p.add_argument("--name")
    p.add_argument("--brand")
    p.add_argument("--barcode")
    p.add_argument("--price", type=float, required=True)
    p.add_argument("--stock", type=int, required=True)
    p.add_argument("--no-enrich", action="store_true", help="Skip OpenFoodFacts lookup")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("update", help="Update price and/or stock")
    p.add_argument("id", type=int)
    p.add_argument("--price", type=float)
    p.add_argument("--stock", type=int)
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("delete", help="Delete an item")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_delete)

    p = sub.add_parser("find", help="Search OpenFoodFacts")
    p.add_argument("--barcode")
    p.add_argument("--name")
    p.set_defaults(func=cmd_find)

    p = sub.add_parser("enrich", help="Fill missing details from OpenFoodFacts")
    p.add_argument("id", type=int)
    p.set_defaults(func=cmd_enrich)

    return parser


def ask(prompt, cast=str, required=True):
    """Keep asking until the input is valid. Optional fields return None when left blank."""
    while True:
        raw = input(prompt).strip()
        if not raw:
            if required:
                print("This field is required.")
                continue
            return None
        try:
            return cast(raw)
        except ValueError:
            print("Invalid value, try again.")


def run_menu():
    """Interactive mode: python cli.py (no arguments)."""
    ns = argparse.Namespace
    actions = {
        "1": ("List items", lambda: cmd_list(ns(search=ask("Search (blank for all): ", required=False)))),
        "2": ("View item", lambda: cmd_view(ns(id=ask("Item ID: ", int)))),
        "3": ("Add item", lambda: cmd_add(ns(
            name=ask("Name (blank to use barcode lookup): ", required=False),
            brand=ask("Brand (optional): ", required=False),
            barcode=ask("Barcode (optional): ", required=False),
            price=ask("Price (KES): ", float), stock=ask("Stock: ", int), no_enrich=False))),
        "4": ("Update price/stock", lambda: cmd_update(ns(
            id=ask("Item ID: ", int),
            price=ask("New price in KES (blank to skip): ", float, required=False),
            stock=ask("New stock (blank to skip): ", int, required=False)))),
        "5": ("Delete item", lambda: cmd_delete(ns(id=ask("Item ID: ", int)))),
        "6": ("Find product on OpenFoodFacts", lambda: cmd_find(ns(
            barcode=ask("Barcode (blank to search by name): ", required=False),
            name=ask("Name (blank if using barcode): ", required=False)))),
        "7": ("Enrich item from OpenFoodFacts", lambda: cmd_enrich(ns(id=ask("Item ID: ", int)))),
    }
    while True:
        print("\n=== Inventory Admin ===")
        for key, (label, _) in actions.items():
            print(f"{key}. {label}")
        print("0. Exit")
        try:
            choice = input("Choose an option: ").strip()
            if choice == "0":
                print("Goodbye.")
                return 0
            if choice not in actions:
                print("Please choose a number from the menu.")
                continue
            actions[choice][1]()
        except CLIError as exc:
            print(f"Error: {exc}")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return 0


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.command is None:
        return run_menu()
    try:
        args.func(args)
    except CLIError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
    