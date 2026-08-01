from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

CONTENT_TYPES = {
    "story_arc", "storylet", "preset_character", "character_kind",
    "character_component", "character_attribute", "body_part",
    "equipment_slot", "body_slot_preset", "item",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ValidationIssue(BaseModel):
    severity: Literal["error", "warning", "info"] = "error"
    code: str
    path: str = ""
    message: str
    reference: dict[str, Any] | None = None
    suggestion: str = ""


class DraftCreateRequest(BaseModel):
    content_type: str
    content_id: str = Field(min_length=1, max_length=120)
    operation: Literal["create", "update"] = "update"
    document: dict[str, Any] | None = None


class DraftUpdateRequest(BaseModel):
    document: dict[str, Any]
    expected_revision: str = ""


class PublishRequest(BaseModel):
    expected_revision: str = ""
    summary: str = Field(default="", max_length=500)
    idempotency_key: str = Field(default="", max_length=120)


class ArchiveRequest(BaseModel):
    expected_revision: str = ""
    summary: str = Field(default="", max_length=500)


class DeleteRequest(BaseModel):
    expected_revision: str
    proposal_token: str
    confirmation: str


class RollbackRequest(BaseModel):
    summary: str = Field(default="", max_length=500)
