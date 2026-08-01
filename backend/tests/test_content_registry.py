from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app import catalog
from app.content.character_config import validate_character_configs
from app.content.models import CONTENT_TYPES
from app.content.references import incoming_references
from app.content.repository import list_documents, validate_content_identity
from app.content.validation import validation_payload
from app.main import app as game_app


def test_all_registered_content_is_valid():
    validate_character_configs()
    count = 0
    for content_type in CONTENT_TYPES:
        for item in list_documents(content_type):
            count += 1
            result = validation_payload(content_type, item["id"], item["document"])
            assert result["valid"], (content_type, item["id"], result)
    assert count >= 90


def test_items_file_is_the_single_runtime_source():
    items_file = json.loads((Path(catalog.__file__).parent / "data" / "items.json").read_text(encoding="utf-8"))["items"]
    legacy_catalog = json.loads(catalog.DATA_PATH.read_text(encoding="utf-8"))
    assert "items" not in legacy_catalog
    assert set(items_file) == {
        "rusty_sword", "wooden_shield", "greatsword", "heavy_chainmail", "hunter_cloak",
        "steward_ring", "grain_tithe_seal", "nipple_chain", "nipple_ring",
        "female_chastity_belt", "male_chastity_device",
    }
    assert items_file["male_chastity_device"]["allowed_slots"] == ["penis"]
    assert catalog.ITEMS == items_file


@pytest.mark.parametrize("content_id", ["../catalog", "/tmp/value", "a/b", "a\\b", ""])
def test_content_identity_rejects_path_traversal(content_id):
    with pytest.raises(HTTPException) as exc:
        validate_content_identity("item", content_id)
    assert exc.value.status_code == 422


def test_reference_index_finds_item_dependency():
    rows = incoming_references("item", "nipple_ring")
    assert any(row["source_type"] == "item" and row["source_id"] == "nipple_chain" for row in rows)


def test_game_openapi_never_contains_admin_routes():
    assert not any(path.startswith("/admin-api") for path in game_app.openapi()["paths"])
