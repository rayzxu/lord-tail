from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..ai.actions import execute_action, legal_actions, normalize_action, validate_action
from ..ai.analysis import analyze_realm
from ..ai.planner import plan_management_action
from ..engine.state import mutation_result, require_state
from ..engine.types import TurnContext
from ..systems import council
from .schemas import AdviceAcceptRequest, CouncilResolveRequest, ManagementModeRequest, StrategicActionRequest

router = APIRouter()


@router.get("/council/current")
def read_current_council() -> dict[str, Any]:
    state = require_state()
    council.normalize_council_state(state)
    return {
        "meeting": council.current_meeting(state),
        "history": state["council"]["history"],
        "directive": state.get("strategic_directive"),
        "management_ai": state["management_ai"],
    }


@router.post("/council/{meeting_id}/resolve")
def resolve_council(meeting_id: str, request: CouncilResolveRequest) -> dict[str, Any]:
    state = require_state()
    resolved = council.resolve_meeting(state, meeting_id, request.proposal_id, request.management_mode)
    response = mutation_result(state, f"议会已经裁定：{resolved['directive']['title']}。")
    return {**response, **resolved}


@router.post("/council/request-review")
def request_council_review() -> dict[str, Any]:
    state = require_state()
    requested = council.request_review(state)
    response = mutation_result(state, "大臣已经被召入领主厅，复议开始。")
    return {**response, **requested}


@router.get("/strategy/current")
def read_strategy() -> dict[str, Any]:
    state = require_state()
    council.normalize_council_state(state)
    return {
        "directive": state.get("strategic_directive"),
        "management_ai": state["management_ai"],
    }


@router.get("/strategy/analysis")
def read_strategy_analysis() -> dict[str, Any]:
    return {"analysis": analyze_realm(require_state())}


@router.post("/strategy/management-mode")
def change_management_mode(request: ManagementModeRequest) -> dict[str, Any]:
    state = require_state()
    management = council.set_management_mode(state, request.mode)
    response = mutation_result(state, f"领地管理模式已改为 {request.mode}。")
    return {**response, "management_ai": management}


def _cached_or_new_advice(state: dict[str, Any]) -> dict[str, Any]:
    council.normalize_council_state(state)
    directive = state.get("strategic_directive")
    if not isinstance(directive, dict) or directive.get("status") != "active":
        raise HTTPException(409, "当前没有生效的战略方针")
    pending = state["management_ai"].get("pending_advice")
    if isinstance(pending, dict) and int(pending.get("turn", -1)) == int(state.get("turn", 1)):
        return pending
    decision = plan_management_action(
        state,
        directive,
        mode="advisory",
        seed=int(state["management_ai"].get("planner_seed", 0)) + int(state.get("turn", 1)),
    )
    state["management_ai"]["pending_advice"] = decision
    return decision


@router.get("/strategy/advice")
def read_strategy_advice() -> dict[str, Any]:
    state = require_state()
    return {"decision": _cached_or_new_advice(state)}


@router.post("/strategy/advice/{decision_id}/accept")
def accept_strategy_advice(decision_id: str, request: AdviceAcceptRequest) -> dict[str, Any]:
    state = require_state()
    decision = _cached_or_new_advice(state)
    if decision.get("id") != decision_id:
        raise HTTPException(409, "该顾问方案已经过期")
    choices = [decision["selected_action"]] + [item["action"] for item in decision.get("candidates", [])]
    action_id = request.action_id or decision["selected_action"]["action_id"]
    action = next((item for item in choices if item.get("action_id") == action_id), None)
    if action is None:
        raise HTTPException(422, "所选行动不属于当前顾问方案")
    validation = validate_action(state, action, directive=state.get("strategic_directive"), enforce_budget=True)
    if not validation["legal"]:
        raise HTTPException(409, f"所选行动已经失效：{'；'.join(validation['errors'])}")
    state["management_ai"]["accepted_action"] = normalize_action(action, actor="management_ai")
    response = mutation_result(state, "顾问行动已经确认，将在本轮九日结算中执行。")
    return {**response, "decision": decision, "accepted_action": state["management_ai"]["accepted_action"]}


@router.get("/actions/legal")
def read_legal_actions() -> dict[str, Any]:
    state = require_state()
    return {
        "actions": legal_actions(
            state,
            directive=state.get("strategic_directive"),
            actor="player",
        )
    }


@router.post("/actions/validate")
def validate_strategic_action(request: StrategicActionRequest) -> dict[str, Any]:
    state = require_state()
    return validate_action(state, request.action, directive=state.get("strategic_directive"), enforce_budget=request.actor == "management_ai")


@router.post("/actions/execute")
def execute_strategic_action(request: StrategicActionRequest) -> dict[str, Any]:
    state = require_state()
    if council.current_meeting(state):
        raise HTTPException(409, "开放的领主议会必须先解决")
    context = TurnContext(command="", actor=request.actor)
    action = normalize_action(request.action, actor=request.actor)
    try:
        execute_action(
            state,
            action,
            context,
            directive=state.get("strategic_directive"),
            enforce_slot=True,
            enforce_budget=request.actor == "management_ai",
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    response = mutation_result(state, f"战略行动已经执行：{action['action_id']}", context.events)
    return {**response, "action": action}
