#Shared pytest fixtures for the inventory project.
import os
import sys

import pytest

# Let the tests import app.py and cli.py from the project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402


@pytest.fixture
# A Flask test client with fresh sample data, NOT logged in.
def client(tmp_path, monkeypatch):
    # Save to a temporary file so tests never touch the real data/inventory.json.
    monkeypatch.setattr(app_module, "DATA_FILE", str(tmp_path / "data" / "inventory.json"))
    app_module.app.config["TESTING"] = True
    app_module.reset_data()
    with app_module.app.test_client() as test_client:
        yield test_client

# A Flask test client that is already logged in as admin.
@pytest.fixture
def auth_client(client):
    response = client.post("/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return client