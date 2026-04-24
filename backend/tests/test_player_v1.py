from http import HTTPStatus


def _create_playable_project(client, headers):
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Mobile Story", "description": "Playable package"},
        headers=headers,
    )
    assert project_response.status_code == HTTPStatus.CREATED
    project_id = project_response.json()["id"]

    graph_response = client.post(
        f"/api/v1/projects/{project_id}/graphs",
        json={"project_id": project_id, "title": "Main Graph", "description": "Runtime graph"},
        headers=headers,
    )
    assert graph_response.status_code == HTTPStatus.CREATED
    graph_id = graph_response.json()["id"]

    first_scene = client.post(
        f"/api/v1/graphs/{graph_id}/scenes",
        json={
            "title": "Intro",
            "content": "Start here",
            "scene_type": "story",
            "order_index": 1,
            "context": {"sequence": {"choice_key": "path"}},
        },
        headers=headers,
    )
    assert first_scene.status_code == HTTPStatus.CREATED
    first_scene_id = first_scene.json()["id"]

    second_scene = client.post(
        f"/api/v1/graphs/{graph_id}/scenes",
        json={"title": "Finish", "content": "The end", "scene_type": "story", "order_index": 2},
        headers=headers,
    )
    assert second_scene.status_code == HTTPStatus.CREATED
    second_scene_id = second_scene.json()["id"]

    edge_response = client.post(
        f"/api/v1/graphs/{graph_id}/edges",
        json={
            "from_scene_id": first_scene_id,
            "to_scene_id": second_scene_id,
            "choice_label": "Continue",
            "edge_metadata": {"choice_value": "continue"},
        },
        headers=headers,
    )
    assert edge_response.status_code == HTTPStatus.CREATED
    edge_id = edge_response.json()["id"]

    patch_response = client.patch(
        f"/api/v1/graphs/{graph_id}",
        json={"root_scene_id": first_scene_id},
        headers=headers,
    )
    assert patch_response.status_code == HTTPStatus.OK

    return {
        "project_id": project_id,
        "graph_id": graph_id,
        "first_scene_id": first_scene_id,
        "second_scene_id": second_scene_id,
        "edge_id": edge_id,
    }


def _publish_release(client, project_id: str, token: str, graph_id: str | None = None):
    payload = {}
    if graph_id is not None:
        payload["graph_id"] = graph_id
    response = client.post(
        f"/api/v1/projects/{project_id}/releases/publish",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
    )
    assert response.status_code == HTTPStatus.CREATED
    return response.json()


def _replace_release_access(
    client,
    project_id: str,
    release_id: str,
    token: str,
    user_ids: list[str],
    cohort_codes: list[str] | None = None,
):
    response = client.put(
        f"/api/v1/projects/{project_id}/releases/{release_id}/access",
        headers={"Authorization": f"Bearer {token}"},
        json={"user_ids": user_ids, "cohort_codes": cohort_codes or []},
    )
    assert response.status_code == HTTPStatus.OK
    return response.json()


def test_player_release_catalog_access_and_stats(client, auth_session):
    publisher = auth_session("publisher", role="author")
    assigned_user = auth_session("assigned-player", role="player")
    other_user = auth_session("other-player", role="player")
    ids = _create_playable_project(client, publisher["headers"])

    assigned_headers = assigned_user["headers"]
    other_headers = other_user["headers"]

    # Unpublished projects must stay out of the mobile catalog.
    catalog_response = client.get("/api/v1/player/projects", headers=assigned_headers)
    assert catalog_response.status_code == HTTPStatus.OK
    assert all(item["project_id"] != ids["project_id"] for item in catalog_response.json()["items"])

    release_v1 = _publish_release(client, ids["project_id"], publisher["token"], ids["graph_id"])
    assert release_v1["manifest"]["scene_count"] == 2
    assert release_v1["assigned_users"] == []

    _replace_release_access(
        client,
        ids["project_id"],
        release_v1["id"],
        publisher["token"],
        [assigned_user["id"]],
    )

    catalog_response = client.get("/api/v1/player/projects", headers=assigned_headers)
    assert catalog_response.status_code == HTTPStatus.OK
    catalog_items = catalog_response.json()["items"]
    catalog_item = next(item for item in catalog_items if item["project_id"] == ids["project_id"])
    assert catalog_item["graph_id"] == ids["graph_id"]
    assert catalog_item["scene_count"] == 2
    assert catalog_item["choice_count"] == 1

    other_catalog_response = client.get("/api/v1/player/projects", headers=other_headers)
    assert other_catalog_response.status_code == HTTPStatus.OK
    assert all(item["project_id"] != ids["project_id"] for item in other_catalog_response.json()["items"])

    package_response = client.get(f"/api/v1/player/projects/{ids['project_id']}/package", headers=assigned_headers)
    assert package_response.status_code == HTTPStatus.OK
    package_body = package_response.json()
    assert package_body["manifest"]["package_version"] == catalog_item["package_version"]
    assert len(package_body["export"]["graph"]["scenes"]) == 2

    forbidden_package = client.get(f"/api/v1/player/projects/{ids['project_id']}/package", headers=other_headers)
    assert forbidden_package.status_code == HTTPStatus.NOT_FOUND

    active_sync_response = client.post(
        f"/api/v1/player/projects/{ids['project_id']}/runs/sync",
        headers=assigned_headers,
        json={
            "run_id": "run-mobile-resume",
            "graph_id": ids["graph_id"],
            "package_version": package_body["manifest"]["package_version"],
            "current_node_id": ids["second_scene_id"],
            "status": "active",
            "events": [
                {
                    "id": "evt-session-started-v1",
                    "type": "session_started",
                    "timestamp": "2026-03-12T09:00:00Z",
                    "payload": {"source": "remote"},
                },
                {
                    "id": "evt-node-intro-v1",
                    "type": "node_entered",
                    "timestamp": "2026-03-12T09:00:01Z",
                    "payload": {"node_id": ids["first_scene_id"], "reason": "initial"},
                },
                {
                    "id": "evt-choice-v1",
                    "type": "choice_selected",
                    "timestamp": "2026-03-12T09:00:02Z",
                    "payload": {
                        "choice_id": ids["edge_id"],
                        "from_node_id": ids["first_scene_id"],
                        "to_node_id": ids["second_scene_id"],
                        "value": "continue",
                    },
                },
                {
                    "id": "evt-node-finish-v1",
                    "type": "node_entered",
                    "timestamp": "2026-03-12T09:00:03Z",
                    "payload": {"node_id": ids["second_scene_id"], "reason": "choice"},
                },
            ],
        },
    )
    assert active_sync_response.status_code == HTTPStatus.OK

    resume_response = client.get(f"/api/v1/player/projects/{ids['project_id']}/resume", headers=assigned_headers)
    assert resume_response.status_code == HTTPStatus.OK
    resume_body = resume_response.json()
    assert resume_body["available"] is True
    assert resume_body["run_id"] == "run-mobile-resume"
    assert resume_body["package_version"] == package_body["manifest"]["package_version"]
    assert resume_body["current_node_id"] == ids["second_scene_id"]
    assert resume_body["scene_history"] == [ids["first_scene_id"], ids["second_scene_id"]]
    assert resume_body["session_values"]["last_choice"] == "continue"
    assert resume_body["session_values"]["path"] == "continue"

    # Editing the working graph after publish must not mutate the published package snapshot.
    third_scene = client.post(
        f"/api/v1/graphs/{ids['graph_id']}/scenes",
        json={"title": "Aftermath", "content": "Post-release scene", "scene_type": "story", "order_index": 3},
        headers=publisher["headers"],
    )
    assert third_scene.status_code == HTTPStatus.CREATED
    third_scene_id = third_scene.json()["id"]

    extra_edge = client.post(
        f"/api/v1/graphs/{ids['graph_id']}/edges",
        json={
            "from_scene_id": ids["second_scene_id"],
            "to_scene_id": third_scene_id,
            "choice_label": "Inspect",
            "edge_metadata": {"choice_value": "inspect"},
        },
        headers=publisher["headers"],
    )
    assert extra_edge.status_code == HTTPStatus.CREATED

    still_v1_package = client.get(f"/api/v1/player/projects/{ids['project_id']}/package", headers=assigned_headers)
    assert still_v1_package.status_code == HTTPStatus.OK
    assert len(still_v1_package.json()["export"]["graph"]["scenes"]) == 2

    release_v2 = _publish_release(client, ids["project_id"], publisher["token"], ids["graph_id"])
    assert release_v2["version"] == 2
    assert release_v2["manifest"]["scene_count"] == 3
    assert release_v2["assigned_users"][0]["id"] == assigned_user["id"]

    updated_catalog = client.get("/api/v1/player/projects", headers=assigned_headers)
    assert updated_catalog.status_code == HTTPStatus.OK
    updated_item = next(item for item in updated_catalog.json()["items"] if item["project_id"] == ids["project_id"])
    assert updated_item["scene_count"] == 3
    assert updated_item["package_version"] == release_v2["package_version"]

    resume_after_publish = client.get(f"/api/v1/player/projects/{ids['project_id']}/resume", headers=assigned_headers)
    assert resume_after_publish.status_code == HTTPStatus.OK
    resume_after_publish_body = resume_after_publish.json()
    assert resume_after_publish_body["available"] is True
    assert resume_after_publish_body["package_version"] == release_v1["package_version"]
    assert resume_after_publish_body["current_node_id"] == ids["second_scene_id"]

    resume_package_response = client.get(
        f"/api/v1/player/projects/{ids['project_id']}/package?package_version={release_v1['package_version']}",
        headers=assigned_headers,
    )
    assert resume_package_response.status_code == HTTPStatus.OK
    assert len(resume_package_response.json()["export"]["graph"]["scenes"]) == 2

    sync_response = client.post(
        f"/api/v1/player/projects/{ids['project_id']}/runs/sync",
        headers=assigned_headers,
        json={
            "run_id": "run-mobile-resume",
            "graph_id": ids["graph_id"],
            "package_version": release_v1["package_version"],
            "current_node_id": ids["second_scene_id"],
            "status": "completed",
            "events": [
                {
                    "id": "evt-session-complete-v1",
                    "type": "session_completed",
                    "timestamp": "2026-03-12T09:00:04Z",
                    "payload": {"node_id": ids["second_scene_id"]},
                }
            ],
        },
    )
    assert sync_response.status_code == HTTPStatus.OK
    assert sync_response.json()["accepted_count"] == 1

    resume_after_completion = client.get(f"/api/v1/player/projects/{ids['project_id']}/resume", headers=assigned_headers)
    assert resume_after_completion.status_code == HTTPStatus.OK
    assert resume_after_completion.json()["available"] is False

    sync_response_v2 = client.post(
        f"/api/v1/player/projects/{ids['project_id']}/runs/sync",
        headers=assigned_headers,
        json={
            "run_id": "run-mobile-002",
            "graph_id": ids["graph_id"],
            "package_version": updated_item["package_version"],
            "current_node_id": third_scene_id,
            "status": "completed",
            "events": [
                {
                    "id": "evt-session-started",
                    "type": "session_started",
                    "timestamp": "2026-03-12T10:00:00Z",
                    "payload": {"source": "cache"},
                },
                {
                    "id": "evt-node-intro",
                    "type": "node_entered",
                    "timestamp": "2026-03-12T10:00:01Z",
                    "payload": {"node_id": ids["first_scene_id"], "reason": "initial"},
                },
                {
                    "id": "evt-choice-1",
                    "type": "choice_selected",
                    "timestamp": "2026-03-12T10:00:02Z",
                    "payload": {
                        "choice_id": ids["edge_id"],
                        "from_node_id": ids["first_scene_id"],
                        "to_node_id": ids["second_scene_id"],
                        "value": "continue",
                    },
                },
                {
                    "id": "evt-node-finish",
                    "type": "node_entered",
                    "timestamp": "2026-03-12T10:00:03Z",
                    "payload": {"node_id": ids["second_scene_id"], "reason": "choice"},
                },
                {
                    "id": "evt-choice-2",
                    "type": "choice_selected",
                    "timestamp": "2026-03-12T10:00:04Z",
                    "payload": {
                        "choice_id": extra_edge.json()["id"],
                        "from_node_id": ids["second_scene_id"],
                        "to_node_id": third_scene_id,
                        "value": "inspect",
                    },
                },
                {
                    "id": "evt-session-complete",
                    "type": "session_completed",
                    "timestamp": "2026-03-12T10:00:05Z",
                    "payload": {"node_id": third_scene_id},
                },
            ],
        },
    )
    assert sync_response_v2.status_code == HTTPStatus.OK
    assert sync_response_v2.json()["accepted_count"] == 6

    stats_response = client.get(f"/api/v1/player/projects/{ids['project_id']}/stats", headers=assigned_headers)
    assert stats_response.status_code == HTTPStatus.OK
    stats_body = stats_response.json()
    assert stats_body["total_runs"] == 2
    assert stats_body["completed_runs"] == 2
    assert stats_body["unique_players"] == 1
    assert stats_body["mine"]["completed_runs"] == 2
    assert {item["choice_id"] for item in stats_body["choices"]} == {ids["edge_id"], extra_edge.json()["id"]}

    archive_response = client.post(
        f"/api/v1/projects/{ids['project_id']}/releases/{release_v2['id']}/archive",
        headers=publisher["headers"],
    )
    assert archive_response.status_code == HTTPStatus.OK
    assert archive_response.json()["status"] == "archived"

    rollback_catalog = client.get("/api/v1/player/projects", headers=assigned_headers)
    assert rollback_catalog.status_code == HTTPStatus.OK
    rollback_item = next(item for item in rollback_catalog.json()["items"] if item["project_id"] == ids["project_id"])
    assert rollback_item["scene_count"] == 2
    assert rollback_item["package_version"] == release_v1["package_version"]


def test_player_release_catalog_access_via_cohort(client, auth_session):
    publisher = auth_session("cohort-publisher", role="author")
    matching_player = auth_session("cohort-player", role="player", cohort_code="school-a")
    other_player = auth_session("cohort-other", role="player", cohort_code="school-b")
    ids = _create_playable_project(client, publisher["headers"])

    release = _publish_release(client, ids["project_id"], publisher["token"], ids["graph_id"])
    _replace_release_access(
        client,
        ids["project_id"],
        release["id"],
        publisher["token"],
        [],
        cohort_codes=["SCHOOL-A"],
    )

    matching_catalog = client.get("/api/v1/player/projects", headers=matching_player["headers"])
    assert matching_catalog.status_code == HTTPStatus.OK
    assert any(item["project_id"] == ids["project_id"] for item in matching_catalog.json()["items"])

    other_catalog = client.get("/api/v1/player/projects", headers=other_player["headers"])
    assert other_catalog.status_code == HTTPStatus.OK
    assert all(item["project_id"] != ids["project_id"] for item in other_catalog.json()["items"])
