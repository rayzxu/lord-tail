from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from .models import CONTENT_TYPES

APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
PROJECT_DIR = APP_DIR.parents[1]
WORK_DIR = PROJECT_DIR / ".content-admin"
DRAFT_DIR = WORK_DIR / "drafts"
REVISION_DIR = WORK_DIR / "revisions"
AUDIT_PATH = WORK_DIR / "audit.jsonl"
LOCK_PATH = WORK_DIR / "publish.lock"
ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,119}$")

KEYED_TYPES: dict[str, tuple[Path, str]] = {
    "item": (DATA_DIR / "items.json", "items"),
    "character_kind": (DATA_DIR / "characters" / "registry.json", "kinds"),
    "character_component": (DATA_DIR / "characters" / "registry.json", "components"),
    "character_attribute": (DATA_DIR / "characters" / "registry.json", "attributes"),
    "body_part": (DATA_DIR / "characters" / "anatomy.json", "body_parts"),
    "equipment_slot": (DATA_DIR / "characters" / "equipment_slots.json", "slots"),
    "body_slot_preset": (DATA_DIR / "characters" / "equipment_slots.json", "presets"),
}

FILE_TYPES: dict[str, Path] = {
    "story_arc": DATA_DIR / "storylets",
    "storylet": DATA_DIR / "storylets",
    "preset_character": DATA_DIR / "characters" / "presets",
}


def ensure_work_dirs() -> None:
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    REVISION_DIR.mkdir(parents=True, exist_ok=True)


def validate_content_identity(content_type: str, content_id: str) -> None:
    if content_type not in CONTENT_TYPES:
        raise HTTPException(404, f"未知内容类型：{content_type}")
    if not ID_PATTERN.fullmatch(content_id) or ".." in content_id or "/" in content_id or "\\" in content_id:
        raise HTTPException(422, "内容 id 只能包含字母、数字、下划线和连字符")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON 根节点必须为对象：{path}")
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def revision_for(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _file_document_matches(content_type: str, document: dict[str, Any], path: Path) -> bool:
    version = int(document.get("schema_version", 1) or 1)
    if content_type == "story_arc":
        return version == 2 and str(document.get("id", "")) == path.stem
    if content_type == "storylet":
        return version == 1 and path.name not in {"director.json", "character_generation.json", "wardrobe_templates.json"}
    return content_type == "preset_character"


def list_documents(content_type: str) -> list[dict[str, Any]]:
    if content_type not in CONTENT_TYPES:
        raise HTTPException(404, f"未知内容类型：{content_type}")
    rows: list[dict[str, Any]] = []
    if content_type in KEYED_TYPES:
        path, root_key = KEYED_TYPES[content_type]
        for content_id, document in read_json(path).get(root_key, {}).items():
            if isinstance(document, dict):
                rows.append(_public_document(content_type, str(content_id), document, path))
    else:
        directory = FILE_TYPES[content_type]
        if not directory.exists():
            return []
        for path in sorted(directory.glob("*.json")):
            document = read_json(path)
            if not _file_document_matches(content_type, document, path):
                continue
            content_id = path.stem if content_type != "storylet" else str(document.get("chain_id") or path.stem)
            rows.append(_public_document(content_type, content_id, document, path))
    rows.sort(key=lambda item: item["id"])
    return rows


def _public_document(content_type: str, content_id: str, document: dict[str, Any], path: Path) -> dict[str, Any]:
    title = document.get("title") or document.get("name")
    if not title and content_type == "storylet":
        nodes = document.get("nodes", [])
        title = nodes[0].get("title") if isinstance(nodes, list) and nodes and isinstance(nodes[0], dict) else content_id
    try:
        source_file = str(path.relative_to(PROJECT_DIR))
    except ValueError:
        source_file = str(path)
    return {
        "content_type": content_type,
        "id": content_id,
        "title": str(title or content_id),
        "status": str(document.get("status", "published")),
        "schema_version": int(document.get("schema_version", 1) or 1),
        "content_version": int(document.get("content_version", document.get("version", 1)) or 1),
        "tags": document.get("tags", []) if isinstance(document.get("tags"), list) else [],
        "source_file": source_file,
        "revision": revision_for(document),
        "document": deepcopy(document),
    }


def get_document(content_type: str, content_id: str) -> dict[str, Any]:
    validate_content_identity(content_type, content_id)
    for item in list_documents(content_type):
        if item["id"] == content_id:
            return item
    raise HTTPException(404, "未找到内容定义")


def source_path(content_type: str, content_id: str) -> Path:
    validate_content_identity(content_type, content_id)
    if content_type in KEYED_TYPES:
        return KEYED_TYPES[content_type][0]
    return FILE_TYPES[content_type] / f"{content_id}.json"


def candidate_file_value(content_type: str, content_id: str, document: dict[str, Any], *, delete: bool = False) -> tuple[Path, dict[str, Any] | None]:
    path = source_path(content_type, content_id)
    if content_type in KEYED_TYPES:
        _, root_key = KEYED_TYPES[content_type]
        root = read_json(path)
        collection = root.setdefault(root_key, {})
        if delete:
            collection.pop(content_id, None)
        else:
            collection[content_id] = deepcopy(document)
        return path, root
    return path, None if delete else deepcopy(document)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def published_revision() -> str:
    payload = [(item["content_type"], item["id"], item["revision"]) for content_type in sorted(CONTENT_TYPES) for item in list_documents(content_type)]
    return revision_for(payload)


def content_type_metadata() -> list[dict[str, Any]]:
    labels = {
        "story_arc": "剧情图", "storylet": "Storylet", "preset_character": "预设人物",
        "character_kind": "人物类型", "character_component": "人物组件", "character_attribute": "人物属性",
        "body_part": "身体部位", "equipment_slot": "装备槽位", "body_slot_preset": "身体预设", "item": "物品与装备",
    }
    editors = {"story_arc": "graph", "storylet": "storylet", "preset_character": "character", "item": "item", "body_part": "anatomy", "equipment_slot": "anatomy", "body_slot_preset": "anatomy"}
    return [{"id": key, "label": labels[key], "editable": True, "editor": editors.get(key, "json"), "count": len(list_documents(key))} for key in sorted(CONTENT_TYPES)]
