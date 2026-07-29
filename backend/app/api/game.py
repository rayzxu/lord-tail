from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import APIRouter, HTTPException

from ..catalog import TALENTS
from ..engine.history import append_history_entry, auto_record_turn_events
from ..engine.mutations import apply_state_patch, apply_structured_action
from ..engine import scenes
from ..engine.state import (
    get_current_state,
    load_current_state,
    make_state,
    require_state,
    result,
    save_current_state,
    set_current_state,
)
from ..engine.time import advance_scene_time, advance_scribe_time, current_time_summary, due_strategic_turns
from ..engine.turn import local_turn, run_strategic_turn
from ..engine.types import TurnContext
from ..systems import scheduled_events
from ..integrations.hermes import call_hermes
from .schemas import (
    SceneAdvanceTimeRequest,
    SceneEndRequest,
    SceneStartRequest,
    SceneStepRequest,
    StartRequest,
    StrategicTurnRequest,
    TimeAdvanceRequest,
    TurnRequest,
)

router = APIRouter()


@router.post("/game/start")
def start_game(request: StartRequest) -> dict[str, Any]:
    selected_ids = [talent.get("id") for talent in request.talents]
    if len(set(selected_ids)) != 2 or any(talent_id not in TALENTS for talent_id in selected_ids):
        raise HTTPException(422, "请选择后端目录中两项不重复的命运赐福")
    current_state = set_current_state(make_state(request))
    talent_names = "、".join(talent["name"] for talent in current_state["talents"])
    appearance = request.appearance or "尚未被书记官记下的面容"
    personality = request.personality or "尚未被臣仆摸清的性情"
    narrative = (
        f"第1轮｜春季｜细雨。春雨像灰色的麻布压在 {current_state['realm_name']} 上，"
        f"{request.lord_name} 领主站在泥泞的城堡阳台，俯瞰正中央的领主堡垒与 E6 旁几间破旧房屋。"
        f"他是{request.lord_gender}，外表{appearance}，性格{personality}；命运赐福在他身后低声作响：{talent_names}。"
        "仆人垂着头不敢直视，卫兵把铁手套贴在胸前，敬畏与恐惧像潮气一样贴住他们的喉咙。"
        "领主的小小领地在泥水中展开，而他心里盘算的不是怜悯，是税、劳役、惩戒与如何让每一粒粮食都服从自己的印章。"
    )
    entry = append_history_entry(
        current_state,
        title=f"{current_state['realm_name']}开局",
        summary_md=narrative,
        source="scribe",
        importance=4,
        tags=["opening", "lord_event", "realm"],
        related={"people": [current_state["lord_name"]], "tiles": ["5:5"], "buildings": ["领主堡垒"]},
        created_by="backend",
    )
    current_state["last_history_entries_created"] = [entry]
    return result(current_state, narrative, ["在 E4 建造农田", "派遣伐木队前往西北林地", "召集领民讨论春耕"], "rules")


@router.post("/game/turn")
async def take_turn(request: TurnRequest) -> dict[str, Any]:
    current_state = get_current_state()
    if current_state is None:
        raise HTTPException(409, "请先完成领主设定")
    agent = await call_hermes(deepcopy(current_state), request.command)
    if agent and isinstance(agent.get("narrative"), str):
        action_events: list[dict[str, Any]] = []
        actions = agent.get("actions", [])
        if isinstance(actions, list) and actions:
            for action in actions:
                if not isinstance(action, dict):
                    continue
                try:
                    result_item = apply_structured_action(current_state, action)
                    action_events.append({
                        "phase": "action",
                        "kind": "hermes_action_applied",
                        "message": f"差事已记入账册：{result_item['type']}",
                        "severity": "info",
                        "data": result_item,
                    })
                except (HTTPException, TypeError, ValueError):
                    action_events.append({
                        "phase": "action",
                        "kind": "hermes_action_rejected",
                        "message": "差事未通过账册校验。",
                        "severity": "warning",
                        "data": {"action": action},
                    })
        patch = agent.get("state_patch", {})
        if not action_events and isinstance(patch, dict):
            try:
                apply_state_patch(current_state, patch)
                action_events.append({
                    "phase": "action",
                    "kind": "legacy_state_patch_applied",
                    "message": "旧式书记官账册修订已兼容应用。",
                    "severity": "warning",
                    "data": {"keys": list(patch.keys())},
                })
            except (HTTPException, TypeError, ValueError):
                action_events.append({
                    "phase": "action",
                    "kind": "legacy_state_patch_rejected",
                    "message": "旧式书记官账册修订未通过校验。",
                    "severity": "warning",
                    "data": {"keys": list(patch.keys())},
                })
        from ..engine.time import advance_strategic_clock

        time_context = TurnContext(command=request.command, actor="hermes")
        advance_strategic_clock(current_state, time_context)
        time_context.events.extend(scheduled_events.activate_due_events(current_state, source="hermes_turn"))
        action_events.extend(event.model_dump() for event in time_context.events)
        return result(current_state, agent["narrative"], agent.get("suggestions", []), "hermes", action_events)
    try:
        narrative, suggestions, events = local_turn(current_state, request.command)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return result(current_state, narrative, suggestions, "rules", events)


@router.get("/time")
def read_time() -> dict[str, Any]:
    return current_time_summary(require_state())


@router.post("/state/time/advance")
@router.post("/hermes/time/advance")
def state_time_advance(request: TimeAdvanceRequest) -> dict[str, Any]:
    current_state = require_state()
    if request.days == 0 and request.hours == 0 and request.minutes == 0:
        raise HTTPException(422, "推进时间必须提供 days、hours 或 minutes")
    time_events = [event.model_dump() for event in advance_scribe_time(
        current_state,
        hours=request.hours,
        minutes=request.minutes,
        days=request.days,
        reason=request.reason,
    )]
    strategic_events: list[dict[str, Any]] = []
    if request.run_due_strategic_turns:
        due_turns = due_strategic_turns(current_state)
        for _ in range(due_turns):
            _, _, events = run_strategic_turn(
                current_state,
                request.reason or "书记官推进时间触发九天战略结算",
                actor=request.source or "hermes",
                advance_calendar_days=0,
            )
            strategic_events.extend(events)
    due_event_items = [event.model_dump() for event in scheduled_events.activate_due_events(current_state, source=request.source or "hermes_time")]
    event = {
        "phase": "time",
        "kind": "scribe_time_advanced",
        "severity": "info",
        "message": request.reason or "书记官推进了领地时间。",
        "data": {
            "days": request.days,
            "hours": request.hours,
            "minutes": request.minutes,
            "source": request.source,
            "time": current_state.get("time", {}),
            "active_scene": current_state.get("active_scene"),
        },
    }
    current_state.setdefault("recent_events", []).append(event)
    current_state["recent_events"] = current_state["recent_events"][-50:]
    return result(current_state, event["message"], ["继续叙事", "结束场景", "推进九天"], "state-api", time_events + strategic_events + due_event_items + [event])


@router.post("/game/strategic-turn")
def strategic_turn(request: StrategicTurnRequest) -> dict[str, Any]:
    current_state = require_state()
    if current_state.get("active_scene") is not None:
        if not request.force_end_scene:
            raise HTTPException(409, "当前有进行中的场景；请先结束场景或设置 force_end_scene=true")
        scenes.end_scene(current_state, summary="战略回合开始前，当前场景被强制归档。")
    try:
        narrative, suggestions, events = run_strategic_turn(
            current_state,
            request.command,
            actor=request.source,
            advance_calendar_days=current_state.get("time", {}).get("turn_days", 9),
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return result(current_state, narrative, suggestions, "rules", events)


@router.post("/game/scenes")
def start_scene(request: SceneStartRequest) -> dict[str, Any]:
    current_state = require_state()
    scene = scenes.start_scene(
        current_state,
        request.type,
        request.title,
        participants=request.participants,
        flags=request.flags,
    )
    event = {
        "phase": "scene",
        "kind": "scene_started",
        "severity": "info",
        "message": f"场景开始：{scene['title']}",
        "data": {"scene": scene},
    }
    current_state.setdefault("recent_events", []).append(event)
    current_state["recent_events"] = current_state["recent_events"][-50:]
    return result(current_state, event["message"], ["继续场景", "推进时间", "结束场景"], "state-api", [event])


@router.post("/game/scenes/current/step")
def scene_step(request: SceneStepRequest) -> dict[str, Any]:
    current_state = require_state()
    scene = scenes.require_active_scene(current_state)
    if request.input:
        scenes.append_scene_message(current_state, "player", request.input)
    if request.narrative:
        scenes.append_scene_message(current_state, "assistant", request.narrative)
    events = list(request.events)
    event = {
        "phase": "scene",
        "kind": "scene_step",
        "severity": "info",
        "message": request.narrative or request.input or f"场景继续：{scene['title']}",
        "data": {"scene_id": scene["id"]},
    }
    events.append(event)
    current_state.setdefault("recent_events", []).append(event)
    current_state["recent_events"] = current_state["recent_events"][-50:]
    return result(current_state, event["message"], ["继续追问", "推进时间", "结束场景"], "state-api", events)


@router.post("/game/scenes/current/advance-time")
def scene_advance_time(request: SceneAdvanceTimeRequest) -> dict[str, Any]:
    current_state = require_state()
    scenes.require_active_scene(current_state)
    time_events = [event.model_dump() for event in advance_scene_time(
        current_state,
        hours=request.hours,
        minutes=request.minutes,
        days=request.days,
        reason=request.reason,
    )]
    strategic_events: list[dict[str, Any]] = []
    if request.run_due_strategic_turns:
        due_turns = due_strategic_turns(current_state)
        for _ in range(due_turns):
            _, _, events = run_strategic_turn(
                current_state,
                request.reason or "场景时间累计触发九天战略结算",
                actor="system",
                advance_calendar_days=0,
            )
            strategic_events.extend(events)
    due_event_items = [event.model_dump() for event in scheduled_events.activate_due_events(current_state, source="scene_time")]
    message = request.reason or "场景时间已经推进。"
    return result(current_state, message, ["继续场景", "结束场景"], "state-api", time_events + strategic_events + due_event_items)


@router.post("/game/scenes/current/end")
def end_scene(request: SceneEndRequest) -> dict[str, Any]:
    current_state = require_state()
    scene = scenes.end_scene(current_state, summary=request.summary, outcome=request.outcome)
    event = {
        "phase": "scene",
        "kind": "scene_ended",
        "severity": "info",
        "message": request.summary or f"场景结束：{scene['title']}",
        "data": {"scene": scene},
    }
    created = []
    should_record = bool(request.summary) or bool(request.outcome.get("record_history")) or int(request.outcome.get("importance", 0) or 0) >= 3
    if should_record:
        created.append(append_history_entry(
            current_state,
            title=f"场景结束：{scene.get('title', '领主事件')}",
            summary_md=request.summary or scene.get("summary") or f"{scene.get('title', '领主事件')}已经结束。",
            source="scene",
            importance=int(request.outcome.get("importance", 3) or 3),
            tags=["scene", str(scene.get("type") or "daily")],
            related={"people": [str(item.get("name")) for item in scene.get("participants", []) if isinstance(item, dict) and item.get("name")]},
            created_by="backend",
        ))
    auto_created = [] if created else auto_record_turn_events(current_state, [event])
    current_state["last_history_entries_created"] = created + auto_created
    return result(current_state, event["message"], ["推进九天", "开始新场景"], "state-api", [event])


@router.post("/game/save")
def save_game() -> dict[str, str]:
    save_current_state()
    return {"message": "当前领地已保存"}


@router.post("/game/load")
def load_game() -> dict[str, Any]:
    current_state = load_current_state()
    return result(current_state, "书记官展开了存档卷宗，领地回到了被封存的时刻。", [], "rules")
