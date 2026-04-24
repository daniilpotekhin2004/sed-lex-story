def test_telemetry_event_flow(client):
    payload = {"event_name": "ui_action", "payload": {"action": "click", "detail": "generate"}}
    resp = client.post("/api/telemetry/events", json=payload)
    assert resp.status_code == 200
    created = resp.json()
    assert created["event_name"] == "ui_action"

    list_resp = client.get("/api/telemetry/events")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert any(ev["id"] == created["id"] for ev in items)
