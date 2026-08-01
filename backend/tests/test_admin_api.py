from __future__ import annotations

from fastapi.testclient import TestClient

from app.admin_main import app
from app.content import drafts as draft_store


def test_admin_read_api_requires_no_token():
    client = TestClient(app)
    assert client.get("/admin-health").status_code == 200
    response = client.get("/admin-api/v1/content-types")
    assert response.status_code == 200
    assert any(item["id"] == "story_arc" for item in response.json()["content_types"])


def test_draft_lifecycle_and_optimistic_conflict(monkeypatch, tmp_path):
    monkeypatch.setattr(draft_store, "DRAFT_DIR", tmp_path / "drafts")
    client = TestClient(app)
    created = client.post("/admin-api/v1/drafts", json={
        "content_type": "item", "content_id": "admin_test_item", "operation": "create",
    })
    assert created.status_code == 200, created.text
    draft = created.json()
    before = client.get("/admin-api/v1/content/item/admin_test_item")
    assert before.status_code == 404

    changed = dict(draft["document"]); changed["name"] = "测试短剑"
    updated = client.put(f"/admin-api/v1/drafts/{draft['id']}", json={
        "document": changed, "expected_revision": draft["revision"],
    })
    assert updated.status_code == 200
    conflict = client.put(f"/admin-api/v1/drafts/{draft['id']}", json={
        "document": {**changed, "name": "过期写入"}, "expected_revision": draft["revision"],
    })
    assert conflict.status_code == 409
    assert client.delete(f"/admin-api/v1/drafts/{draft['id']}").status_code == 204
    assert client.get("/admin-api/v1/content/item/admin_test_item").status_code == 404


def test_story_arc_preview_uses_runtime_graph_analyzer(monkeypatch, tmp_path):
    monkeypatch.setattr(draft_store, "DRAFT_DIR", tmp_path / "drafts")
    client = TestClient(app)
    draft = client.post("/admin-api/v1/drafts", json={
        "content_type": "story_arc", "content_id": "admin_preview_arc", "operation": "create",
    }).json()
    response = client.post(f"/admin-api/v1/drafts/{draft['id']}/preview")
    assert response.status_code == 200, response.text
    assert response.json()["validation"]["valid"] is True
    assert response.json()["graph"]["paths"] == [["opening", "resolved"]]
