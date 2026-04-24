from app.schemas.scenario import ScenarioGraphRead


def test_project_graph_scene_flow(client, auth_session):
    author = auth_session("projects-author", role="author")

    # Create project
    project_resp = client.post("/api/v1/projects", json={"name": "Demo Project"}, headers=author["headers"])
    assert project_resp.status_code == 201
    project = project_resp.json()

    # Create legal concept
    concept_resp = client.post(
        "/api/v1/legal",
        json={"code": "LC-1", "title": "Contract law basics"},
    )
    assert concept_resp.status_code == 201
    concept_id = concept_resp.json()["id"]

    # Create graph
    graph_resp = client.post(
        f"/api/v1/projects/{project['id']}/graphs",
        json={"project_id": project["id"], "title": "Main graph"},
        headers=author["headers"],
    )
    assert graph_resp.status_code == 201
    graph = graph_resp.json()

    # Add scenes
    scene1_resp = client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={
            "title": "Intro",
            "content": "You arrive at the campus.",
            "scene_type": "story",
            "legal_concept_ids": [concept_id],
        },
        headers=author["headers"],
    )
    assert scene1_resp.status_code == 201
    scene1 = scene1_resp.json()

    scene2_resp = client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={
            "title": "Decision",
            "content": "Do you sign the document?",
            "scene_type": "decision",
        },
        headers=author["headers"],
    )
    assert scene2_resp.status_code == 201
    scene2 = scene2_resp.json()

    # Link scenes with edge
    edge_resp = client.post(
        f"/api/v1/graphs/{graph['id']}/edges",
        json={"from_scene_id": scene1["id"], "to_scene_id": scene2["id"], "choice_label": "Continue"},
        headers=author["headers"],
    )
    assert edge_resp.status_code == 201

    # Retrieve graph with scenes and edges
    graph_get = client.get(f"/api/v1/graphs/{graph['id']}", headers=author["headers"])
    assert graph_get.status_code == 200
    graph_data: ScenarioGraphRead = graph_get.json()
    assert len(graph_data["scenes"]) == 2
    assert len(graph_data["edges"]) == 1
    # Scene1 should have attached legal concept
    scene1_with_legal = next(s for s in graph_data["scenes"] if s["id"] == scene1["id"])
    assert len(scene1_with_legal["legal_concepts"]) == 1


def test_project_owner_isolation(client, auth_session):
    owner = auth_session("owner-author", role="author")
    other = auth_session("other-author", role="author")

    project_resp = client.post("/api/v1/projects", json={"name": "Private Project"}, headers=owner["headers"])
    assert project_resp.status_code == 201
    project = project_resp.json()

    owner_list = client.get("/api/v1/projects", headers=owner["headers"])
    assert owner_list.status_code == 200
    assert any(item["id"] == project["id"] for item in owner_list.json()["items"])

    other_list = client.get("/api/v1/projects", headers=other["headers"])
    assert other_list.status_code == 200
    assert all(item["id"] != project["id"] for item in other_list.json()["items"])

    other_get = client.get(f"/api/v1/projects/{project['id']}", headers=other["headers"])
    assert other_get.status_code == 404
