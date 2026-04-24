import asyncio

import pytest

from app.schemas.export import ProjectExport
from app.infra.db import SessionLocal
from app.domain.models import ImageVariant


def test_project_export_flow(client, auth_session):
    author = auth_session("export-author", role="author")

    # Create project
    project = client.post("/api/v1/projects", json={"name": "Exportable"}, headers=author["headers"]).json()
    # Create style profile to ensure export contains style
    style = client.post(
        "/api/v1/style-profiles",
        json={
            "project_id": project["id"],
            "name": "Film Noir",
            "base_prompt": "noir, cinematic lighting",
            "resolution": {"width": 512, "height": 512},
        },
    ).json()
    # Attach style to project
    client.patch(
        f"/api/v1/projects/{project['id']}",
        json={"style_profile_id": style["id"]},
        headers=author["headers"],
    )
    # Create graph
    graph = client.post(
        f"/api/v1/projects/{project['id']}/graphs",
        json={"project_id": project["id"], "title": "Graph"},
        headers=author["headers"],
    ).json()
    # Create scene
    scene = client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={"title": "S1", "content": "Courtroom scene", "scene_type": "story"},
        headers=author["headers"],
    ).json()
    # Attach legal concept
    concept = client.post("/api/v1/legal", json={"code": "LC1", "title": "Contract law"}).json()
    client.patch(
        f"/api/v1/scenes/{scene['id']}",
        json={"title": scene["title"], "content": scene["content"], "scene_type": "story", "legal_concept_ids": [concept["id"]]},
        headers=author["headers"],
    )
    # Generate to create variants and mark approved
    job = client.post(
        f"/api/v1/scenes/{scene['id']}/generate",
        json={"use_prompt_engine": False, "prompt": "Test", "num_variants": 1},
        headers=author["headers"],
    ).json()
    job_status = client.get(f"/api/v1/generation-jobs/{job['id']}").json()
    assert job_status["variants"]
    variant_id = job_status["variants"][0]["id"]
    # Manually mark approved
    async def approve():
        async with SessionLocal() as session:
            variant = await session.get(ImageVariant, variant_id)
            variant.is_approved = True
            await session.commit()
    asyncio.get_event_loop().run_until_complete(approve())

    resp = client.get(f"/api/v1/projects/{project['id']}/export")
    assert resp.status_code == 200
    data: ProjectExport = resp.json()
    assert data["project"]["id"] == project["id"]
    assert data["graph"]["id"] == graph["id"]
    assert len(data["scenes"]) >= 1
    assert data["legal_concepts"][0]["id"] == concept["id"]
    assert data["style_profile"]["id"] == style["id"]
    approved = [s for s in data["scenes"] if s["scene"]["id"] == scene["id"]][0]["approved_image"]
    assert approved is not None


def test_project_export_zip(client, auth_session):
    author = auth_session("zip-export-author", role="author")
    project = client.post("/api/v1/projects", json={"name": "ZipExport"}, headers=author["headers"]).json()
    graph = client.post(
        f"/api/v1/projects/{project['id']}/graphs",
        json={"project_id": project["id"], "title": "Graph"},
        headers=author["headers"],
    ).json()
    client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={"title": "S1", "content": "Zip scene", "scene_type": "story"},
        headers=author["headers"],
    ).json()
    resp = client.get(f"/api/v1/projects/{project['id']}/export?format=zip")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/zip"
