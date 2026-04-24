import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def auth_headers(client: TestClient):
    """Create user and return auth headers."""
    # Register
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


def test_create_character_preset(client: TestClient, auth_headers):
    """Test creating a character preset."""
    response = client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "Detective John",
            "description": "A seasoned detective",
            "character_type": "protagonist",
            "appearance_prompt": "middle-aged man, detective coat, serious expression",
            "negative_prompt": "young, smiling",
            "lora_models": [
                {"name": "detective_lora", "weight": 0.8}
            ],
            "embeddings": ["detective_style"],
            "style_tags": ["realistic", "detailed"],
            "default_pose": "standing",
            "is_public": False,
        },
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Detective John"
    assert data["character_type"] == "protagonist"
    assert len(data["lora_models"]) == 1
    assert data["lora_models"][0]["name"] == "detective_lora"
    assert "id" in data


def test_list_character_presets_public(client: TestClient, auth_headers):
    """Test listing public character presets."""
    # Create a public preset
    client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "Public Character",
            "appearance_prompt": "generic person",
            "character_type": "supporting",
            "is_public": True,
        },
    )
    
    # List without auth (should see public only)
    response = client.get("/api/characters/presets?only_public=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1


def test_get_character_preset(client: TestClient, auth_headers):
    """Test getting a character preset by ID."""
    # Create preset
    create_response = client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "Test Character",
            "appearance_prompt": "test appearance",
            "character_type": "supporting",
        },
    )
    preset_id = create_response.json()["id"]
    
    # Get preset
    response = client.get(
        f"/api/characters/presets/{preset_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == preset_id
    assert data["name"] == "Test Character"


def test_update_character_preset(client: TestClient, auth_headers):
    """Test updating a character preset."""
    # Create preset
    create_response = client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "Original Name",
            "appearance_prompt": "original appearance",
            "character_type": "supporting",
        },
    )
    preset_id = create_response.json()["id"]
    
    # Update preset
    response = client.put(
        f"/api/characters/presets/{preset_id}",
        headers=auth_headers,
        json={
            "name": "Updated Name",
            "description": "New description",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Name"
    assert data["description"] == "New description"


def test_delete_character_preset(client: TestClient, auth_headers):
    """Test deleting a character preset."""
    # Create preset
    create_response = client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "To Delete",
            "appearance_prompt": "test",
            "character_type": "supporting",
        },
    )
    preset_id = create_response.json()["id"]
    
    # Delete preset
    response = client.delete(
        f"/api/characters/presets/{preset_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204
    
    # Verify deleted
    get_response = client.get(
        f"/api/characters/presets/{preset_id}",
        headers=auth_headers,
    )
    assert get_response.status_code == 404


def test_generate_combined_prompt(client: TestClient, auth_headers):
    """Test generating combined prompt with multiple characters."""
    # Create two character presets
    char1_response = client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "Character 1",
            "appearance_prompt": "tall man with beard",
            "character_type": "protagonist",
            "lora_models": [{"name": "lora1", "weight": 0.7}],
            "embeddings": ["embed1"],
        },
    )
    char1_id = char1_response.json()["id"]
    
    char2_response = client.post(
        "/api/characters/presets",
        headers=auth_headers,
        json={
            "name": "Character 2",
            "appearance_prompt": "young woman with glasses",
            "character_type": "supporting",
            "lora_models": [{"name": "lora2", "weight": 0.8}],
            "embeddings": ["embed2"],
        },
    )
    char2_id = char2_response.json()["id"]
    
    # Generate combined prompt
    response = client.post(
        "/api/characters/generate-prompt",
        headers=auth_headers,
        json={
            "prompt": "office scene",
            "character_ids": [char1_id, char2_id],
            "style": "realistic",
            "num_variants": 1,
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "office scene" in data["prompt"]
    assert "tall man with beard" in data["prompt"]
    assert "young woman with glasses" in data["prompt"]
    assert len(data["lora_models"]) == 2
    assert len(data["embeddings"]) == 2


def test_unauthorized_create_preset(client: TestClient):
    """Test that creating preset requires authentication."""
    response = client.post(
        "/api/characters/presets",
        json={
            "name": "Test",
            "appearance_prompt": "test",
            "character_type": "supporting",
        },
    )
    assert response.status_code == 403  # No auth
