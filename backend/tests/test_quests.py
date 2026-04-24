from http import HTTPStatus


def test_create_quest_and_scene(client):
    quest_payload = {"title": "Test Quest", "description": "Desc", "audience": "teen"}
    quest_resp = client.post("/api/quests", json=quest_payload)
    assert quest_resp.status_code == HTTPStatus.CREATED
    quest_body = quest_resp.json()
    quest_id = quest_body["id"]

    scene_payload = {"title": "Start", "text": "You enter a room", "order": 1}
    scene_resp = client.post(f"/api/quests/{quest_id}/scenes", json=scene_payload)
    assert scene_resp.status_code == HTTPStatus.CREATED
    scene_body = scene_resp.json()
    assert scene_body["text"] == scene_payload["text"]
    assert scene_body["quest_id"] == quest_id

    get_resp = client.get(f"/api/quests/{quest_id}")
    assert get_resp.status_code == HTTPStatus.OK
    body = get_resp.json()
    assert body["id"] == quest_id
    assert len(body["scenes"]) == 1
