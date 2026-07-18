from __future__ import annotations

from pydantic import BaseModel, Field


class TurnEvent(BaseModel):
    phase: str
    kind: str
    message: str
    severity: str = "info"
    data: dict = Field(default_factory=dict)


class TurnContext(BaseModel):
    command: str = ""
    actor: str = "player"
    advance_calendar_days: int = 9
    events: list[TurnEvent] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
