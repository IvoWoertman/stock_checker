"""Integration tests for the Flask API against the fake db layer."""
import pytest

from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_health(client, fake_db):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_inventory_returns_products(client, fake_db):
    fake_db.rows_results = [[
        {"product_id": "p1", "name": "Ground beef", "category": "Meat",
         "lot_count": 2, "total_grams": 750.0, "oldest_added_date": "2026-11-01"},
    ]]
    response = client.get("/api/inventory")
    assert response.status_code == 200
    body = response.get_json()
    assert body[0]["name"] == "Ground beef"
    assert body[0]["lot_count"] == 2


def test_create_lot_requires_name(client):
    response = client.post("/api/lots", json={"qty_g": 500})
    assert response.status_code == 400


def test_create_lot_ok(client, fake_db):
    fake_db.cursor._fetchone = [None, None]
    response = client.post("/api/lots", json={"name": "Ground beef", "qty_g": 500})
    assert response.status_code == 201
    assert response.get_json()["duplicate"] is False


def test_use_overuse_returns_conflict(client, fake_db):
    fake_db.cursor._fetchone = [None, (200,)]  # dup check, then balance
    response = client.post("/api/lots/lot-1/use", json={"grams_used": 300})
    assert response.status_code == 409


def test_product_lookup(client, fake_db):
    fake_db.one_results = [{
        "product_id": "p1", "name": "Beef", "category": "Meat",
        "usual_package_size_g": 500.0, "default_best_before_days": None,
    }]
    response = client.get("/api/products/lookup?code=8712345678901")
    assert response.status_code == 200
    assert response.get_json()["product"]["name"] == "Beef"


def test_shopping_add_ok(client, fake_db):
    response = client.post("/api/shopping", json={"name": "Milk"})
    assert response.status_code == 201
    assert response.get_json()["item_id"]


def test_shopping_requires_name(client):
    response = client.post("/api/shopping", json={})
    assert response.status_code == 400
