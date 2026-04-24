def _setup_project_graph_scene(client, headers):
    project = client.post("/api/v1/projects", json={"name": "Gen Project"}, headers=headers).json()
    graph = client.post(
        f"/api/v1/projects/{project['id']}/graphs",
        json={"project_id": project["id"], "title": "Graph"},
        headers=headers,
    ).json()
    scene = client.post(
        f"/api/v1/graphs/{graph['id']}/scenes",
        json={"title": "Scene", "content": "A lawyer in court", "scene_type": "story"},
        headers=headers,
    ).json()
    return project, graph, scene


def test_generation_job_flow(client, auth_session):
    author = auth_session("generation-author", role="author")
    _, _, scene = _setup_project_graph_scene(client, author["headers"])

    payload = {
        "prompt": "A lawyer defending a client in court",
        "num_variants": 2,
        "width": 320,
        "height": 256,
        "use_prompt_engine": False,
    }
    job_resp = client.post(f"/api/v1/scenes/{scene['id']}/generate", json=payload, headers=author["headers"])
    assert job_resp.status_code == 202
    job = job_resp.json()

    status_resp = client.get(f"/api/v1/generation-jobs/{job['id']}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["scene_id"] == scene["id"]
    assert status_data["prompt"] == payload["prompt"]
    # In eager mode the job should be done immediately and have variants
    assert status_data["status"] in {"queued", "running", "done"}
    variants = status_data.get("variants") or []
    assert len(variants) == payload["num_variants"]

    images_resp = client.get(f"/api/v1/scenes/{scene['id']}/images")
    assert images_resp.status_code == 200
    images_data = images_resp.json()
    assert len(images_data["items"]) == payload["num_variants"]


def test_approve_image_variant(client, auth_session):
    author = auth_session("generation-approve-author", role="author")
    _, _, scene = _setup_project_graph_scene(client, author["headers"])
    job = client.post(
        f"/api/v1/scenes/{scene['id']}/generate",
        json={"prompt": "Courtroom", "num_variants": 1, "use_prompt_engine": False},
        headers=author["headers"],
    ).json()
    status = client.get(f"/api/v1/generation-jobs/{job['id']}").json()
    variant_id = status["variants"][0]["id"]

    resp = client.post(f"/api/v1/scenes/{scene['id']}/images/{variant_id}/approve")
    assert resp.status_code == 200
    approved = resp.json()
    assert approved["id"] == variant_id
    assert approved["is_approved"] is True
