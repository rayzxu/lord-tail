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
    diplomacy: dict[str, Any] | None = None
    factions: dict[str, Any] | None = None
    realm_map: list[dict[str, Any]] = Field(default_factory=list)
    diplomacy_map: list[dict[str, Any]] = Field(default_factory=list)


class TurnRequest(BaseModel):
    command: str = Field(min_length=1, max_length=1000)


class StrategicTurnRequest(TurnRequest):
    source: str = Field(default="player", max_length=40)
    force_end_scene: bool = False


class CouncilResolveRequest(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=100)
    management_mode: str = Field(default="delegated", pattern="^(delegated|advisory|manual)$")


class ManagementModeRequest(BaseModel):
    mode: str = Field(pattern="^(delegated|advisory|manual)$")


class StrategicActionRequest(BaseModel):
    action: dict[str, Any]
    actor: str = Field(default="player", max_length=60)


class AdviceAcceptRequest(BaseModel):
    action_id: str = Field(default="", max_length=200)


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


class TimeAdvanceRequest(SceneAdvanceTimeRequest):
    source: str = Field(default="hermes", max_length=60)


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


class HistoryEntryRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    summary_md: str = Field(default="", max_length=8000)
    details_md: str = Field(default="", max_length=20000)
    source: str = Field(default="scene", max_length=60)
    importance: int = Field(default=3, ge=1, le=5)
    visibility: str = Field(default="player", max_length=40)
    tags: list[str] = Field(default_factory=list)
    related: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="hermes", max_length=60)


class HistoryPatchRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    summary_md: str | None = Field(default=None, max_length=8000)
    details_md: str | None = Field(default=None, max_length=20000)
    source: str | None = Field(default=None, max_length=60)
    importance: int | None = Field(default=None, ge=1, le=5)
    visibility: str | None = Field(default=None, max_length=40)
    tags: list[str] | None = None
    related: dict[str, Any] | None = None
    created_by: str | None = Field(default=None, max_length=60)


class CharacterUpsertRequest(BaseModel):
    id: str | None = Field(default=None, max_length=80)
    kind: str | None = Field(default=None, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default="", max_length=120)
    gender: str = Field(default="未说明", max_length=40)
    age: int | None = Field(default=None, ge=0, le=130)
    faction: str = Field(default="", max_length=80)
    location: str = Field(default="", max_length=120)
    status: str = Field(default="active", max_length=40)
    appearance_md: str = Field(default="", max_length=8000)
    personality_md: str = Field(default="", max_length=8000)
    description_md: str = Field(default="", max_length=12000)
    relationship_to_lord: str = Field(default="", max_length=1000)
    disposition: int = Field(default=0, ge=-100, le=100)
    traits: list[str] | None = None
    memories: list[str] | None = None
    identity: dict[str, Any] = Field(default_factory=dict)
    profile: dict[str, Any] = Field(default_factory=dict)
    relationship: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    components: dict[str, Any] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)


class CharacterPatchRequest(BaseModel):
    kind: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=120)
    gender: str | None = Field(default=None, max_length=40)
    age: int | None = Field(default=None, ge=0, le=130)
    faction: str | None = Field(default=None, max_length=80)
    location: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=40)
    appearance_md: str | None = Field(default=None, max_length=8000)
    personality_md: str | None = Field(default=None, max_length=8000)
    description_md: str | None = Field(default=None, max_length=12000)
    relationship_to_lord: str | None = Field(default=None, max_length=1000)
    disposition: int | None = Field(default=None, ge=-100, le=100)
    traits: list[str] | None = None
    memories: list[str] | None = None
    identity: dict[str, Any] | None = None
    profile: dict[str, Any] | None = None
    relationship: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    components: dict[str, Any] | None = None
    flags: dict[str, Any] | None = None


class CharacterMemoryAppendRequest(BaseModel):
    entry: str | None = Field(default=None, max_length=2000)
    entries: list[str] = Field(default_factory=list)
    created_by: str = Field(default="hermes", max_length=60)


class CharacterComponentPatchRequest(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="hermes", max_length=60)


class CharacterItemGrantRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=1000)
    created_by: str = Field(default="hermes", max_length=60)


class CharacterEquipItemRequest(BaseModel):
    item_id: str = Field(min_length=1, max_length=80)
    slot: str = Field(default="", max_length=80)
    auto_add: bool = True
    created_by: str = Field(default="hermes", max_length=60)


class CharacterUnequipItemRequest(BaseModel):
    slot: str = Field(default="", max_length=80)
    item_id: str = Field(default="", max_length=80)
    created_by: str = Field(default="hermes", max_length=60)


class CharacterSexualEncounterRequest(BaseModel):
    partner_character_id: str = Field(min_length=1, max_length=80)
    partner_name_snapshot: str = Field(default="", max_length=80)
    position_id: str = Field(min_length=1, max_length=80)
    count: int = Field(default=1, ge=1, le=1000)
    time: dict[str, Any] | None = None
    notes: list[str] = Field(default_factory=list)
    created_by: str = Field(default="hermes", max_length=60)


class CharacterReproductiveContentRequest(BaseModel):
    target: str = Field(pattern="^(stomach|intestine|uterus)$")
    content_type: str = Field(default="unknown", max_length=80)
    source_character_id: str = Field(min_length=1, max_length=80)
    source_name_snapshot: str = Field(default="", max_length=80)
    amount: int = Field(default=1, ge=1, le=1000)
    received_time: dict[str, Any] | None = None
    expires_time: dict[str, Any] | None = None
    fertility_context: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_by: str = Field(default="hermes", max_length=60)


class CharacterReproductiveContentsClearExpiredRequest(BaseModel):
    now: dict[str, Any] | None = None


class ScheduledEventScheduleRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    title: str | None = Field(default=None, max_length=160)
    description_md: str = Field(default="", max_length=8000)
    due_time: dict[str, Any] | None = None
    in_days: int | None = Field(default=None, ge=0, le=3650)
    in_hours: int | None = Field(default=None, ge=0, le=24 * 365)
    in_minutes: int | None = Field(default=None, ge=0, le=60 * 24 * 365)
    clock_24: str | None = Field(default=None, max_length=5)
    visibility: str | None = Field(default=None, max_length=40)
    importance: int | None = Field(default=None, ge=1, le=5)
    related: dict[str, Any] = Field(default_factory=dict)
    conditions: dict[str, Any] = Field(default_factory=dict)
    flags: dict[str, Any] = Field(default_factory=dict)
    created_by: str = Field(default="hermes", max_length=60)


class ScheduledEventCancelRequest(BaseModel):
    reason_md: str = Field(default="", max_length=8000)
    cancelled_by: str = Field(default="hermes", max_length=60)


class ScheduledEventRescheduleRequest(BaseModel):
    due_time: dict[str, Any] | None = None
    in_days: int | None = Field(default=None, ge=0, le=3650)
    in_hours: int | None = Field(default=None, ge=0, le=24 * 365)
    in_minutes: int | None = Field(default=None, ge=0, le=60 * 24 * 365)
    clock_24: str | None = Field(default=None, max_length=5)
    reason_md: str = Field(default="", max_length=8000)


class ScheduledEventResolveRequest(BaseModel):
    result_md: str = Field(default="", max_length=12000)
    outcome: dict[str, Any] = Field(default_factory=dict)
    resolved_by: str = Field(default="hermes", max_length=60)
