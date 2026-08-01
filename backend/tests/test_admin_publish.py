from __future__ import annotations

import json

import pytest

from app.content import drafts as draft_store
from app.content import publish, repository
from app.content.models import DraftCreateRequest


@pytest.fixture
def isolated_item_admin(monkeypatch, tmp_path):
    source = tmp_path / "items.json"
    source.write_text(json.dumps({"schema_version": 1, "items": {
        "test_sword": {"name": "测试剑", "type": "weapon", "allowed_slots": ["right_hand"], "occupied_slots": [], "effects": {}},
    }}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setitem(repository.KEYED_TYPES, "item", (source, "items"))
    monkeypatch.setattr(draft_store, "DRAFT_DIR", tmp_path / "drafts")
    monkeypatch.setattr(publish, "REVISION_DIR", tmp_path / "revisions")
    monkeypatch.setattr(publish, "LOCK_PATH", tmp_path / "publish.lock")
    monkeypatch.setattr(publish, "AUDIT_PATH", tmp_path / "audit.jsonl")
    monkeypatch.setattr(publish, "WORK_DIR", tmp_path / "work")
    monkeypatch.setattr(publish, "_reload_local_registry", lambda: None)
    monkeypatch.setattr(publish, "_notify_game_reload", lambda: True)
    return source


def _draft_with_name(name: str):
    draft = draft_store.create_draft(DraftCreateRequest(content_type="item", content_id="test_sword", operation="update"))
    document = dict(draft["document"]); document["name"] = name
    return draft_store.update_draft(draft["id"], document, draft["revision"])


def test_publish_is_atomic_and_revision_can_rollback(isolated_item_admin):
    draft = _draft_with_name("新测试剑")
    result = publish.publish_draft(draft["id"], expected_revision=draft["revision"], summary="测试发布")
    assert result["published"] is True
    assert json.loads(isolated_item_admin.read_text(encoding="utf-8"))["items"]["test_sword"]["name"] == "新测试剑"
    rollback = publish.rollback_revision(result["revision_id"], "测试回滚")
    assert rollback["published"] is True
    assert json.loads(isolated_item_admin.read_text(encoding="utf-8"))["items"]["test_sword"]["name"] == "测试剑"


def test_second_publisher_from_stale_base_gets_conflict(isolated_item_admin):
    first = _draft_with_name("先发布")
    second = _draft_with_name("后发布")
    publish.publish_draft(first["id"], expected_revision=first["revision"])
    with pytest.raises(Exception) as exc:
        publish.publish_draft(second["id"], expected_revision=second["revision"])
    assert getattr(exc.value, "status_code", None) == 409


def test_write_failure_restores_published_bytes(isolated_item_admin, monkeypatch):
    before = isolated_item_admin.read_bytes()
    draft = _draft_with_name("不应留下")
    real_write = publish.atomic_write_json

    def fail_source(path, value):
        if path == isolated_item_admin:
            raise OSError("injected write failure")
        return real_write(path, value)

    monkeypatch.setattr(publish, "atomic_write_json", fail_source)
    with pytest.raises(OSError, match="injected"):
        publish.publish_draft(draft["id"], expected_revision=draft["revision"])
    assert isolated_item_admin.read_bytes() == before


def test_publish_idempotency_returns_same_revision(isolated_item_admin):
    draft = _draft_with_name("只发布一次")
    first = publish.publish_draft(draft["id"], expected_revision=draft["revision"], idempotency_key="same-request")
    second = publish.publish_draft(draft["id"], expected_revision=draft["revision"], idempotency_key="same-request")
    assert second == first
    assert len(publish.revision_entries()) == 1
