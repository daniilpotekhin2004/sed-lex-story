import pytest
from fastapi.testclient import TestClient


def test_register_user(client: TestClient):
    """Test user registration."""
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpassword123",
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["username"] == "testuser"
    assert data["email"] == "test@example.com"
    assert data["role"] == "player"
    assert data["is_active"] is True
    assert "id" in data


def test_register_duplicate_username(client: TestClient):
    """Test registration with duplicate username."""
    # First registration
    client.post(
        "/api/auth/register",
        json={
            "username": "duplicate",
            "email": "user1@example.com",
            "password": "password123",
        },
    )
    
    # Second registration with same username
    response = client.post(
        "/api/auth/register",
        json={
            "username": "duplicate",
            "email": "user2@example.com",
            "password": "password123",
        },
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_login_success(client: TestClient):
    """Test successful login."""
    # Register user
    client.post(
        "/api/auth/register",
        json={
            "username": "loginuser",
            "email": "login@example.com",
            "password": "password123",
        },
    )
    
    # Login
    response = client.post(
        "/api/auth/login",
        json={
            "username": "loginuser",
            "password": "password123",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_wrong_password(client: TestClient):
    """Test login with wrong password."""
    # Register user
    client.post(
        "/api/auth/register",
        json={
            "username": "wrongpass",
            "email": "wrongpass@example.com",
            "password": "correctpassword",
        },
    )
    
    # Login with wrong password
    response = client.post(
        "/api/auth/login",
        json={
            "username": "wrongpass",
            "password": "wrongpassword",
        },
    )
    assert response.status_code == 401


def test_get_current_user(client: TestClient):
    """Test getting current user info."""
    # Register and login
    client.post(
        "/api/auth/register",
        json={
            "username": "currentuser",
            "email": "current@example.com",
            "password": "password123",
        },
    )
    
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "currentuser",
            "password": "password123",
        },
    )
    token = login_response.json()["access_token"]
    
    # Get current user
    response = client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "currentuser"
    assert data["email"] == "current@example.com"


def test_refresh_token(client: TestClient):
    """Test token refresh."""
    # Register and login
    client.post(
        "/api/auth/register",
        json={
            "username": "refreshuser",
            "email": "refresh@example.com",
            "password": "password123",
        },
    )
    
    login_response = client.post(
        "/api/auth/login",
        json={
            "username": "refreshuser",
            "password": "password123",
        },
    )
    refresh_token = login_response.json()["refresh_token"]
    
    # Refresh token
    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_unauthorized_access(client: TestClient):
    """Test accessing protected endpoint without token."""
    response = client.get("/api/auth/me")
    assert response.status_code == 403  # No credentials provided
