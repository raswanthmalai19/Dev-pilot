"""Tests for Flask sample application."""

import pytest
from app import app


@pytest.fixture
def client():
    """Create test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_home(client):
    """Test home endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert "message" in data
    assert data["version"] == "1.0.0"


def test_health(client):
    """Test health endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"


def test_get_items(client):
    """Test getting all items."""
    response = client.get("/api/items")
    assert response.status_code == 200
    data = response.get_json()
    assert "items" in data
    assert "count" in data


def test_get_item(client):
    """Test getting a specific item."""
    response = client.get("/api/items/1")
    assert response.status_code == 200
    data = response.get_json()
    assert data["id"] == 1


def test_get_item_not_found(client):
    """Test getting a non-existent item."""
    response = client.get("/api/items/999")
    assert response.status_code == 404


def test_create_item(client):
    """Test creating an item."""
    response = client.post(
        "/api/items",
        json={"name": "Test Item", "description": "A test"},
    )
    assert response.status_code == 201
    data = response.get_json()
    assert data["name"] == "Test Item"
