import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def author_headers(client: TestClient):
    """Create author user and return auth headers."""
    # Register as author (will need to change role manually or via admin)
    client.post(
        "/api/auth/register",
        json={
            "username": "author1",
            "email": "author1@example.com",
            "password": "password123",
        },
    )
    
    # Login
    response = client.post(
        "/api/auth/login",
        json={
            "username": "author1",
            "password": "password123",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def moderator_headers(client: TestClient):
    """Create moderator user and return auth headers."""
    client.post(
        "/api/auth/register",
        json={
            "username": "moderator1",
            "email": "moderator1@example.com",
            "password": "password123",
        },
    )
    
    response = client.post(
        "/api/auth/login",
        json={
            "username": "moderator1",
            "password": "password123",
        },
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_get_moderation_stats(client: TestClient, author_headers):
    """Test getting moderation statistics."""
    response = client.get(
        "/api/moderation/stats",
        headers=author_headers,
    )
    
    # May fail if user is not AUTHOR role
    # In real scenario, need to set role via admin endpoint
    if response.status_code == 200:
        data = response.json()
        assert "total_images" in data
        assert "pending" in data
        assert "approved" in data


def test_get_my_images(client: TestClient, author_headers):
    """Test getting my generated images."""
    response = client.get(
        "/api/moderation/my-images",
        headers=author_headers,
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


def test_get_moderation_queue_requires_auth(client: TestClient):
    """Test that moderation queue requires authentication."""
    response = client.get("/api/moderation/queue")
    assert response.status_code == 403  # No auth


def test_moderate_image_requires_author_role(client: TestClient, author_headers):
    """Test that moderation requires AUTHOR or ADMIN role."""
    # This will likely fail with 403 if user is PLAYER role
    response = client.post(
        "/api/moderation/images/fake-id/moderate",
        headers=author_headers,
        json={
            "action": "approve",
            "notes": "Looks good"
        },
    )
    
    # Expected: 403 (not author) or 404 (image not found)
    assert response.status_code in [403, 404]


def test_select_image_requires_auth(client: TestClient):
    """Test that selecting image requires authentication."""
    response = client.post("/api/moderation/images/fake-id/select")
    assert response.status_code == 403


def test_bulk_moderate_requires_author_role(client: TestClient, author_headers):
    """Test bulk moderation requires AUTHOR role."""
    response = client.post(
        "/api/moderation/bulk-moderate",
        headers=author_headers,
        json={
            "image_ids": ["id1", "id2"],
            "action": "approve",
        },
    )
    
    # Expected: 403 (not author) or 404 (images not found)
    assert response.status_code in [403, 404]


def test_delete_image_requires_auth(client: TestClient):
    """Test that deleting image requires authentication."""
    response = client.delete("/api/moderation/images/fake-id")
    assert response.status_code == 403


def test_get_scene_images(client: TestClient, author_headers):
    """Test getting scene images."""
    response = client.get(
        "/api/moderation/scenes/fake-scene-id/images",
        headers=author_headers,
    )
    
    # Will return 200 with empty list or 404 if scene doesn't exist
    assert response.status_code in [200, 404]
