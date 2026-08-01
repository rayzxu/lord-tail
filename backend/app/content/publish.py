from __future__ import annotations

import difflib
import fcntl
import hashlib
import hmac
import json
import os
import shutil
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
from fastapi import HTTPException

from .drafts import draft_by_id
from .models import now_iso
from .references import reference_report
from .repository import (
    AUDIT_PATH, LOCK_PATH, REVISION_DIR, WORK_DIR, atomic_write_json, candidate_file_value,
    canonical_json, ensure_work_dirs, get_document, published_revision, revision_for, source_path,
)
from .validation import validation_payload


def _current_revision(content_type: str, content_id: str) -> str:
    try:
        return str(get_document(content_type, content_id)["revision"])
    except HTTPException as exc:
        if exc.status_code == 404:
            return "missing"
        raise


def draft_diff(draft: dict[str, Any]) -> str:
    try:
        before = get_document(draft["content_type"], draft["content_id"])["document"]
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        before = {}
    left = json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    right = json.dumps(draft["document"], ensure_ascii=False, indent=2, sort_keys=True).splitlines()
    return "\n".join(difflib.unified_diff(left, right, fromfile="published", tofile="draft", lineterm=""))


def _audit(entry: dict[str, Any]) -> None:
    ensure_work_dirs()
    with AUDIT_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def audit_entries(limit: int = 200) -> list[dict[str, Any]]:
    if not AUDIT_PATH.exists():
        return []
    rows = []
    for line in AUDIT_PATH.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows[-max(1, min(limit, 1000)):][::-1]


def _reload_local_registry() -> None:
    from ..catalog import reload_catalog, validate_map_tile_kinds_catalog
    from ..storylets.config import load_arc_definitions, load_definitions, validate_storylet_catalog
    from ..systems.characters import reload_character_registry

    reload_catalog()
    reload_character_registry()
    load_definitions.cache_clear(); load_arc_definitions.cache_clear()
    validate_map_tile_kinds_catalog()
    validate_storylet_catalog()


def _notify_game_reload() -> bool:
    reload_url = os.getenv("LORD_TAIL_GAME_RELOAD_URL", "http://127.0.0.1:8000/internal/content/reload")
    token = os.getenv("LORD_TAIL_INTERNAL_CONTENT_TOKEN", "")
    if not token:
        return False
    try:
        response = httpx.post(reload_url, headers={"X-Lord-Tail-Internal-Token": token}, timeout=5)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


def publish_draft(draft_id: str, *, expected_revision: str = "", summary: str = "", idempotency_key: str = "") -> dict[str, Any]:
    draft = draft_by_id(draft_id)
    if expected_revision and expected_revision != draft.get("revision"):
        raise HTTPException(409, detail={"code": "draft_revision_conflict", "server_revision": draft.get("revision")})
    published_document = deepcopy(draft["document"])
    if draft["content_type"] == "story_arc":
        try:
            current_document = get_document(draft["content_type"], draft["content_id"])["document"]
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
            current_document = {}
        published_document["version"] = max(
            int(published_document.get("version", 1)), int(current_document.get("version", 0)) + 1,
        )
    validation = validation_payload(draft["content_type"], draft["content_id"], published_document)
    if not validation["valid"]:
        raise HTTPException(422, detail={"code": "content_validation_failed", **validation})
    ensure_work_dirs()
    with LOCK_PATH.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        idempotency_path: Path | None = None
        if idempotency_key:
            idempotency_path = WORK_DIR / "idempotency" / f"{hashlib.sha256(idempotency_key.encode()).hexdigest()}.json"
            if idempotency_path.exists():
                cached = json.loads(idempotency_path.read_text(encoding="utf-8"))
                if cached.get("draft_id") != draft_id or cached.get("draft_revision") != draft.get("revision"):
                    raise HTTPException(409, detail={"code": "idempotency_key_conflict"})
                return deepcopy(cached["result"])
        current_revision = _current_revision(draft["content_type"], draft["content_id"])
        if current_revision != draft.get("base_revision"):
            raise HTTPException(409, detail={"code": "content_revision_conflict", "server_revision": current_revision, "base_revision": draft.get("base_revision")})
        path, candidate = candidate_file_value(draft["content_type"], draft["content_id"], published_document)
        before_bytes = path.read_bytes() if path.exists() else None
        revision_id = f"rev_{uuid.uuid4().hex}"
        revision_path = REVISION_DIR / revision_id
        revision_path.mkdir(parents=True, exist_ok=False)
        manifest = {
            "id": revision_id, "time": now_iso(), "action": "publish",
            "content_type": draft["content_type"], "content_id": draft["content_id"],
            "before_revision": current_revision, "draft_revision": draft["revision"],
            "summary": summary, "source_file": str(path), "before_existed": before_bytes is not None,
            "before_document": get_document(draft["content_type"], draft["content_id"])["document"] if current_revision != "missing" else None,
            "after_document": deepcopy(published_document),
        }
        atomic_write_json(revision_path / "manifest.json", manifest)
        try:
            if candidate is None:
                raise HTTPException(500, "publish candidate 不能为空")
            atomic_write_json(path, candidate)
            _reload_local_registry()
        except Exception:
            if before_bytes is None:
                path.unlink(missing_ok=True)
            else:
                temporary = path.with_suffix(path.suffix + ".rollback")
                temporary.write_bytes(before_bytes)
                os.replace(temporary, path)
            _reload_local_registry()
            shutil.rmtree(revision_path, ignore_errors=True)
            raise
        game_reloaded = _notify_game_reload()
        draft["status"] = "published"
        draft["document"] = deepcopy(published_document)
        draft["published_revision"] = revision_for(published_document)
        draft["published_at"] = now_iso()
        from .drafts import _write
        _write(draft)
        registry_revision = published_revision()
        _audit({
            "id": f"audit_{uuid.uuid4().hex}", "time": now_iso(), "actor": "local-admin",
            "action": "publish", "content_type": draft["content_type"], "content_id": draft["content_id"],
            "from_revision": current_revision, "to_revision": draft["published_revision"],
            "summary": summary, "result": "success", "revision_id": revision_id,
        })
        result = {
            "published": True, "revision_id": revision_id, "content_revision": draft["published_revision"],
            "registry_revision": registry_revision, "registry_reloaded": True,
            "game_registry_reloaded": game_reloaded, "restart_required": not game_reloaded,
            "migration_required": False, "warnings": [] if game_reloaded else ["游戏 API 未确认热重载；请重启游戏 API。"],
        }
        if idempotency_path is not None:
            atomic_write_json(idempotency_path, {"draft_id": draft_id, "draft_revision": draft["revision"], "result": result})
        return result


def revision_entries() -> list[dict[str, Any]]:
    ensure_work_dirs()
    rows = []
    for path in REVISION_DIR.glob("rev_*/manifest.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            rows.append(value)
    rows.sort(key=lambda item: str(item.get("time", "")), reverse=True)
    return rows


def delete_proposal(content_type: str, content_id: str, secret: str) -> dict[str, Any]:
    item = get_document(content_type, content_id)
    report = reference_report(content_type, content_id)
    payload = f"{content_type}:{content_id}:{item['revision']}"
    token = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {**report, "revision": item["revision"], "proposal_token": token if report["can_hard_delete"] else None}


def archive_content(content_type: str, content_id: str, *, expected_revision: str, archived: bool, summary: str = "") -> dict[str, Any]:
    item = get_document(content_type, content_id)
    if expected_revision and item["revision"] != expected_revision:
        raise HTTPException(409, detail={"code": "content_revision_conflict", "server_revision": item["revision"]})
    document = deepcopy(item["document"]); document["status"] = "archived" if archived else "published"
    from .drafts import create_draft
    from .models import DraftCreateRequest

    draft = create_draft(DraftCreateRequest(content_type=content_type, content_id=content_id, operation="update", document=document))
    return publish_draft(draft["id"], expected_revision=draft["revision"], summary=summary or ("归档内容" if archived else "恢复内容"))


def hard_delete(content_type: str, content_id: str, *, expected_revision: str, proposal_token: str, confirmation: str, secret: str) -> dict[str, Any]:
    item = get_document(content_type, content_id)
    proposal = delete_proposal(content_type, content_id, secret)
    if proposal["incoming"]:
        raise HTTPException(409, detail={"code": "content_has_references", "references": proposal["incoming"]})
    if item["revision"] != expected_revision or proposal.get("proposal_token") != proposal_token:
        raise HTTPException(409, "删除提案已经过期")
    if confirmation != f"DELETE {content_type}/{content_id}":
        raise HTTPException(422, "确认文本不匹配")
    path, candidate = candidate_file_value(content_type, content_id, {}, delete=True)
    before_bytes = path.read_bytes() if path.exists() else None
    if content_type in {"story_arc", "storylet", "preset_character"}:
        path.unlink()
    elif candidate is not None:
        atomic_write_json(path, candidate)
    try:
        _reload_local_registry()
    except Exception:
        if before_bytes is not None:
            path.write_bytes(before_bytes)
        _reload_local_registry()
        raise
    _notify_game_reload()
    _audit({"id": f"audit_{uuid.uuid4().hex}", "time": now_iso(), "actor": "local-admin", "action": "delete", "content_type": content_type, "content_id": content_id, "from_revision": item["revision"], "to_revision": "deleted", "summary": "硬删除未引用内容", "result": "success"})
    return {"deleted": True, "content_type": content_type, "content_id": content_id}


def rollback_revision(revision_id: str, summary: str = "") -> dict[str, Any]:
    if not revision_id.startswith("rev_") or any(char in revision_id for char in "/\\."):
        raise HTTPException(422, "无效 revision id")
    path = REVISION_DIR / revision_id / "manifest.json"
    if not path.exists():
        raise HTTPException(404, "未找到 revision")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    before = manifest.get("before_document")
    if before is None:
        raise HTTPException(409, "该 revision 的回滚会删除新内容，请使用安全删除流程")
    from .drafts import create_draft
    from .models import DraftCreateRequest

    draft = create_draft(DraftCreateRequest(content_type=manifest["content_type"], content_id=manifest["content_id"], operation="update", document=before))
    return publish_draft(draft["id"], expected_revision=draft["revision"], summary=summary or f"回滚 {revision_id}")
