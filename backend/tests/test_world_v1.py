def test_world_library_flow(client, auth_session):
    author = auth_session("world-author", role="author")
    project = client.post("/api/v1/projects", json={"name": "World Project"}, headers=author["headers"]).json()

    bible_payload = {
        "tone": "formal",
        "glossary": {"plaintiff": "истец"},
        "constraints": ["no slang"],
        "dialogue_format": {"speaker_prefix": "—"},
    }
    bible = client.put(f"/api/v1/projects/{project['id']}/style-bible", json=bible_payload).json()
    assert bible["project_id"] == project["id"]

    location = client.post(
        f"/api/v1/projects/{project['id']}/locations",
        json={"name": "Courtroom 3", "description": "Classic courtroom"},
    ).json()
    artifact = client.post(
        f"/api/v1/projects/{project['id']}/artifacts",
        json={"name": "Contract", "artifact_type": "document"},
    ).json()
    template = client.post(
        f"/api/v1/projects/{project['id']}/document-templates",
        json={"name": "Summons", "template_type": "summons"},
    ).json()

    locations = client.get(f"/api/v1/projects/{project['id']}/locations").json()
    artifacts = client.get(f"/api/v1/projects/{project['id']}/artifacts").json()
    templates = client.get(f"/api/v1/projects/{project['id']}/document-templates").json()
    assert len(locations["items"]) == 1
    assert len(artifacts["items"]) == 1
    assert len(templates["items"]) == 1

    graph = client.post(
        f"/api/v1/projects/{project['id']}/graphs",
        json={"project_id": project["id"], "title": "Main"},
        headers=author["headers"],
    ).json()
    scene = client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={
            "title": "Scene 1",
            "content": "A legal hearing begins.",
            "scene_type": "story",
            "location_id": location["id"],
            "artifacts": [{"artifact_id": artifact["id"]}],
        },
        headers=author["headers"],
    ).json()
    assert scene["location_id"] == location["id"]
    assert scene["artifacts"][0]["artifact_id"] == artifact["id"]


def test_graph_validation_reports_issues(client, auth_session):
    author = auth_session("validation-author", role="author")
    project = client.post("/api/v1/projects", json={"name": "Validation Project"}, headers=author["headers"]).json()
    graph = client.post(
        f"/api/v1/projects/{project['id']}/graphs",
        json={"project_id": project["id"], "title": "Graph"},
        headers=author["headers"],
    ).json()
    client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={"title": "Intro", "content": "Start", "scene_type": "story"},
        headers=author["headers"],
    )
    client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={"title": "Second", "content": "Branch", "scene_type": "story"},
        headers=author["headers"],
    )
    report = client.get(f"/api/v1/graphs/{graph['id']}/validate", headers=author["headers"]).json()
    codes = {issue["code"] for issue in report["issues"]}
    assert "dead_end" in codes
    assert "unreachable_scene" in codes
