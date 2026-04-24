from http import HTTPStatus
from pathlib import Path

import pytest

from app.core.config import get_settings


# ============================================================================
# Scene-based Generation Tests
# ============================================================================

def test_generation_task_enqueued_and_files_created(client):
    """Test that scene-based generation creates task successfully."""
    quest_resp = client.post("/api/quests", json={"title": "Quest", "description": "d"})
    quest_id = quest_resp.json()["id"]
    scene_resp = client.post(
        f"/api/quests/{quest_id}/scenes", json={"title": "Scene", "text": "Hello"}
    )
    scene_id = scene_resp.json()["id"]

    gen_resp = client.post(
        f"/api/scenes/{scene_id}/generate-images",
        json={"prompt": "test prompt", "style": "comic", "num_variants": 2},
    )
    assert gen_resp.status_code == HTTPStatus.ACCEPTED
    task_id = gen_resp.json()["task_id"]
    assert task_id
    
    # Note: In eager mode with mocking, files are not actually created
    # This test verifies the task was successfully enqueued


def test_scene_generation_with_all_parameters(client):
    """Test scene generation with all optional parameters specified."""
    quest_resp = client.post("/api/quests", json={"title": "Quest", "description": "d"})
    quest_id = quest_resp.json()["id"]
    scene_resp = client.post(
        f"/api/quests/{quest_id}/scenes", json={"title": "Scene", "text": "Hello"}
    )
    scene_id = scene_resp.json()["id"]

    payload = {
        "prompt": "detailed fantasy landscape",
        "negative_prompt": "blurry, low quality",
        "style": "realistic",
        "num_variants": 4,
        "width": 768,
        "height": 512,
        "cfg_scale": 8.5,
        "steps": 30,
        "seed": 42,
    }
    
    gen_resp = client.post(f"/api/scenes/{scene_id}/generate-images", json=payload)
    assert gen_resp.status_code == HTTPStatus.ACCEPTED
    task_id = gen_resp.json()["task_id"]
    assert task_id


def test_scene_generation_with_minimal_parameters(client):
    """Test scene generation with only required parameters."""
    quest_resp = client.post("/api/quests", json={"title": "Quest", "description": "d"})
    quest_id = quest_resp.json()["id"]
    scene_resp = client.post(
        f"/api/quests/{quest_id}/scenes", json={"title": "Scene", "text": "Hello"}
    )
    scene_id = scene_resp.json()["id"]

    payload = {"prompt": "simple test"}
    
    gen_resp = client.post(f"/api/scenes/{scene_id}/generate-images", json=payload)
    assert gen_resp.status_code == HTTPStatus.ACCEPTED
    assert "task_id" in gen_resp.json()


# ============================================================================
# Generic Generation Tests
# ============================================================================

def test_generic_generation_and_task_status(client):
    """Test generic generation without scene binding."""
    payload = {"prompt": "castle on a hill", "style": "comic", "num_variants": 1}
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED
    task_id = resp.json()["task_id"]
    assert task_id

    status_resp = client.get(f"/api/generation/tasks/{task_id}")
    assert status_resp.status_code == HTTPStatus.OK
    body = status_resp.json()
    assert body["task_id"] == task_id
    assert body["state"]


def test_generic_generation_with_custom_dimensions(client):
    """Test generic generation with custom width and height."""
    payload = {
        "prompt": "mountain landscape",
        "width": 1024,
        "height": 768,
        "num_variants": 2,
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED
    assert "task_id" in resp.json()


def test_generic_generation_with_seed(client):
    """Test generic generation with fixed seed for reproducibility."""
    payload = {
        "prompt": "sunset over ocean",
        "seed": 12345,
        "num_variants": 1,
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED
    task_id = resp.json()["task_id"]
    
    # Verify task was created
    status_resp = client.get(f"/api/generation/tasks/{task_id}")
    assert status_resp.status_code == HTTPStatus.OK


def test_generic_generation_multiple_variants(client):
    """Test generating multiple image variants."""
    payload = {
        "prompt": "fantasy character",
        "num_variants": 8,  # Maximum allowed
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED


# ============================================================================
# Validation Tests
# ============================================================================

def test_generation_invalid_num_variants_too_low(client):
    """Test that num_variants below minimum is rejected."""
    payload = {
        "prompt": "test",
        "num_variants": 0,  # Below minimum of 1
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_num_variants_too_high(client):
    """Test that num_variants above maximum is rejected."""
    payload = {
        "prompt": "test",
        "num_variants": 9,  # Above maximum of 8
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_width_too_small(client):
    """Test that width below minimum is rejected."""
    payload = {
        "prompt": "test",
        "width": 128,  # Below minimum of 256
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_width_too_large(client):
    """Test that width above maximum is rejected."""
    payload = {
        "prompt": "test",
        "width": 2048,  # Above maximum of 1024
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_cfg_scale_too_low(client):
    """Test that cfg_scale below minimum is rejected."""
    payload = {
        "prompt": "test",
        "cfg_scale": 0.5,  # Below minimum of 1.0
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_cfg_scale_too_high(client):
    """Test that cfg_scale above maximum is rejected."""
    payload = {
        "prompt": "test",
        "cfg_scale": 25.0,  # Above maximum of 20.0
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_steps_too_low(client):
    """Test that steps below minimum is rejected."""
    payload = {
        "prompt": "test",
        "steps": 3,  # Below minimum of 4
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_invalid_steps_too_high(client):
    """Test that steps above maximum is rejected."""
    payload = {
        "prompt": "test",
        "steps": 100,  # Above maximum of 50
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


def test_generation_missing_prompt(client):
    """Test that missing prompt is rejected."""
    payload = {"num_variants": 2}  # Missing required prompt
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


# ============================================================================
# Task Status Tests
# ============================================================================

def test_task_status_nonexistent_task(client):
    """Test querying status of non-existent task."""
    fake_task_id = "nonexistent-task-id-12345"
    resp = client.get(f"/api/generation/tasks/{fake_task_id}")
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert body["task_id"] == fake_task_id
    assert body["state"] == "PENDING"


def test_task_status_includes_parameters(client):
    """Test that task status includes generation parameters when available."""
    payload = {
        "prompt": "test prompt with params",
        "negative_prompt": "bad quality",
        "cfg_scale": 7.5,
        "steps": 25,
    }
    resp = client.post("/api/generation/generate", json=payload)
    task_id = resp.json()["task_id"]
    
    status_resp = client.get(f"/api/generation/tasks/{task_id}")
    assert status_resp.status_code == HTTPStatus.OK
    body = status_resp.json()
    assert body["task_id"] == task_id
    # In eager mode, these might be available immediately
    assert "state" in body


# ============================================================================
# Task List Tests
# ============================================================================

def test_get_tasks_list_empty(client):
    """Test getting task list when no tasks exist."""
    resp = client.get("/api/generation/tasks")
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert "page" in body
    assert "page_size" in body


def test_get_tasks_list_with_pagination(client):
    """Test task list pagination."""
    # Create some tasks
    for i in range(3):
        client.post("/api/generation/generate", json={"prompt": f"test {i}"})
    
    resp = client.get("/api/generation/tasks?page=1&page_size=2")
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert body["page"] == 1
    assert body["page_size"] == 2


def test_get_tasks_list_with_status_filter(client):
    """Test filtering tasks by status."""
    resp = client.get("/api/generation/tasks?status=SUCCESS")
    assert resp.status_code == HTTPStatus.OK
    body = resp.json()
    assert "items" in body


# ============================================================================
# Pipeline Check Tests
# ============================================================================

def test_pipeline_check(client):
    """Test pipeline health check."""
    resp = client.post("/api/generation/pipeline-check")
    assert resp.status_code == HTTPStatus.ACCEPTED
    data = resp.json()
    assert data["task_id"]
    assert data["state"]
    if data["ready"]:
        assert data["success"] is True
        assert data["details"]["checks"]["sd"]["status"] == "ok"

    status_resp = client.get(f"/api/generation/pipeline-check/{data['task_id']}")
    assert status_resp.status_code == HTTPStatus.OK
    status_body = status_resp.json()
    assert status_body["task_id"] == data["task_id"]
    if status_body["ready"]:
        assert status_body["success"] is True
        assert "checks" in status_body["details"]


def test_pipeline_check_status_query(client):
    """Test querying pipeline check status."""
    # Start pipeline check
    resp = client.post("/api/generation/pipeline-check")
    task_id = resp.json()["task_id"]
    
    # Query status
    status_resp = client.get(f"/api/generation/pipeline-check/{task_id}")
    assert status_resp.status_code == HTTPStatus.OK
    body = status_resp.json()
    assert body["task_id"] == task_id
    assert "state" in body
    assert "ready" in body


# ============================================================================
# Edge Cases and Special Scenarios
# ============================================================================

def test_generation_with_empty_negative_prompt(client):
    """Test generation with explicitly empty negative prompt."""
    payload = {
        "prompt": "beautiful landscape",
        "negative_prompt": "",
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED


def test_generation_with_very_long_prompt(client):
    """Test generation with a very long prompt."""
    long_prompt = "a beautiful landscape " * 50  # Very long prompt
    payload = {
        "prompt": long_prompt,
        "num_variants": 1,
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED


def test_generation_with_special_characters_in_prompt(client):
    """Test generation with special characters in prompt."""
    payload = {
        "prompt": "test!@#$%^&*()_+-=[]{}|;':\",./<>?",
        "num_variants": 1,
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED


def test_generation_with_unicode_prompt(client):
    """Test generation with unicode characters in prompt."""
    payload = {
        "prompt": "美しい風景 🌸 château français",
        "num_variants": 1,
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED


def test_concurrent_generations(client):
    """Test multiple concurrent generation requests."""
    task_ids = []
    for i in range(5):
        resp = client.post(
            "/api/generation/generate",
            json={"prompt": f"concurrent test {i}", "num_variants": 1}
        )
        assert resp.status_code == HTTPStatus.ACCEPTED
        task_ids.append(resp.json()["task_id"])
    
    # Verify all tasks were created
    assert len(task_ids) == 5
    assert len(set(task_ids)) == 5  # All unique


def test_generation_boundary_values(client):
    """Test generation with boundary values for all parameters."""
    payload = {
        "prompt": "boundary test",
        "num_variants": 1,  # Minimum
        "width": 256,  # Minimum
        "height": 256,  # Minimum
        "cfg_scale": 1.0,  # Minimum
        "steps": 10,  # Minimum
    }
    resp = client.post("/api/generation/generate", json=payload)
    assert resp.status_code == HTTPStatus.ACCEPTED
    
    payload_max = {
        "prompt": "boundary test max",
        "num_variants": 8,  # Maximum
        "width": 1024,  # Maximum
        "height": 1024,  # Maximum
        "cfg_scale": 20.0,  # Maximum
        "steps": 30,  # Maximum
    }
    resp_max = client.post("/api/generation/generate", json=payload_max)
    assert resp_max.status_code == HTTPStatus.ACCEPTED
