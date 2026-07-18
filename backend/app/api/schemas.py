from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    lord_name: str = Field(min_length=1, max_length=40)
    lord_gender: str = "未说明"
    realm_name: str = Field(min_length=1, max_length=40)
    appearance: str = Field(default="", max_length=600)
    personality: str = Field(default="", max_length=600)
    talents: list[dict[str, Any]] = Field(min_length=2, max_length=2)
    map_size: int | None = Field(default=None, ge=1)


class TurnRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


class StrategicTurnRequest(TurnRequest):
    source: str = Field(default="player", max_length=40)
    force_end_scene: bool = False


class SceneStartRequest(BaseModel):
    type: str = Field(default="daily", max_length=40)
    title: str = Field(default="领主事件", min_length=1, max_length=120)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    flags: dict[str, Any] = Field(default_factory=dict)


class SceneStepRequest(BaseModel):
    input: str = Field(default="", max_length=4000)
    narrative: str = Field(default="", max_length=8000)
    events: list[dict[str, Any]] = Field(default_factory=list)


class SceneAdvanceTimeRequest(BaseModel):
    hours: int = Field(default=0, ge=0, le=24 * 30)
    minutes: int = Field(default=0, ge=0, le=60 * 24 * 30)
    days: int = Field(default=0, ge=0, le=365)
    reason: str = Field(default="", max_length=500)
    run_due_strategic_turns: bool = True


class SceneEndRequest(BaseModel):
    summary: str = Field(default="", max_length=2000)
    outcome: dict[str, Any] = Field(default_factory=dict)


class ResourceMutationRequest(BaseModel):
    changes: dict[str, int] = Field(default_factory=dict)
    values: dict[str, int] = Field(default_factory=dict)


class ValueDeltaRequest(BaseModel):
    delta: int | None = None
    value: int | None = None


class ArmyMutationRequest(ValueDeltaRequest):
    unit: str = Field(min_length=1)


class DiplomacyMutationRequest(BaseModel):
    faction: str = Field(min_length=1, max_length=60)
    status: str = Field(min_length=1, max_length=60)


class BuildingMutationRequest(BaseModel):
    building: str = Field(min_length=1)
    action: str = Field(pattern="^(build|destroy)$")
    count: int = Field(default=1, ge=1, le=100)
    x: int | None = Field(default=None, ge=1)
    y: int | None = Field(default=None, ge=1)


class BattleResolveRequest(BaseModel):
    player: dict[str, int] | None = None
    enemy: dict[str, int] = Field(min_length=1)
    enemy_organization: int = Field(default=100, ge=0, le=100)
    terrain: str = Field(default="grass", max_length=40)
    stance: str = Field(default="balanced", pattern="^(cautious|balanced|aggressive)$")
    apply_to_state: bool = True
    source: str = Field(default="api", max_length=40)
    label: str = Field(default="", max_length=120)
    notes: str = Field(default="", max_length=1000)
