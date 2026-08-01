from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CONTENT_TYPES
from .repository import PROJECT_DIR, list_documents


def _walk(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from _walk(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")
    else:
        yield path, value


def incoming_references(content_type: str, content_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_type in sorted(CONTENT_TYPES):
        for item in list_documents(source_type):
            if source_type == content_type and item["id"] == content_id:
                continue
            for path, value in _walk(item["document"]):
                if value == content_id:
                    rows.append({
                        "source_type": source_type, "source_id": item["id"],
                        "path": path, "source_file": item["source_file"], "kind": "content",
                    })
    save_paths = [PROJECT_DIR / "backend" / ".lord-tail-save.json"]
    for save_path in save_paths:
        if not save_path.exists():
            continue
        try:
            value = json.loads(save_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for path, child in _walk(value):
            if child == content_id:
                rows.append({
                    "source_type": "save", "source_id": save_path.name,
                    "path": path, "source_file": str(save_path.relative_to(PROJECT_DIR)), "kind": "save",
                })
    return rows


def outgoing_references(content_type: str, content_id: str) -> list[dict[str, Any]]:
    source = next((item for item in list_documents(content_type) if item["id"] == content_id), None)
    if not source:
        return []
    known = {(kind, item["id"]) for kind in CONTENT_TYPES for item in list_documents(kind)}
    rows: list[dict[str, Any]] = []
    for path, value in _walk(source["document"]):
        for target_type, target_id in known:
            if value == target_id and not (target_type == content_type and target_id == content_id):
                rows.append({"target_type": target_type, "target_id": target_id, "path": path})
    return rows


def reference_report(content_type: str, content_id: str) -> dict[str, Any]:
    incoming = incoming_references(content_type, content_id)
    outgoing = outgoing_references(content_type, content_id)
    return {"content_type": content_type, "content_id": content_id, "incoming": incoming, "outgoing": outgoing, "can_hard_delete": not incoming}
