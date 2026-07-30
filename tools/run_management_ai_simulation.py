#!/usr/bin/env python3
"""Run a deterministic long-form management AI simulation without Hermes."""

from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from types import SimpleNamespace
from typing import Any

from app.ai.analysis import analyze_realm
from app.catalog import TALENTS
from app.engine import scenes
from app.engine.state import make_state
from app.engine.turn import run_strategic_turn
from app.systems import council, scheduled_events


def _start_state() -> dict[str, Any]:
    talent_ids = list(TALENTS)[:2]
    request = SimpleNamespace(
        lord_name="自动领主",
        lord_gender="未说明",
        realm_name="长局试验领",
        appearance="由账房略去",
        personality="审慎",
        talents=[{"id": talent_id} for talent_id in talent_ids],
        map_size=None,
        diplomacy=None,
        factions=None,
        realm_map=[],
        diplomacy_map=[],
    )
    return make_state(request)


def _resolve_blocker(state: dict[str, Any], mode: str) -> dict[str, Any] | None:
    meeting = council.current_meeting(state)
    if meeting:
        proposal = meeting["proposals"][0]
        result = council.resolve_meeting(state, meeting["id"], proposal["id"], mode)
        return {
            "kind": "council_resolved",
            "meeting_id": meeting["id"],
            "proposal_id": proposal["id"],
            "directive_id": result["directive"]["id"],
        }
    active = scheduled_events.active_events(state)
    if not active:
        return None
    event = active[0]
    scheduled_events.resolve_event(
        state,
        event["id"],
        result_md="长局模拟自动确认该计划事件已经处理。",
        outcome={"simulation": True},
        resolved_by="simulation",
    )
    active_scene = state.get("active_scene")
    if isinstance(active_scene, dict):
        scenes.end_scene(state, summary="长局模拟自动结束计划事件场景。")
    return {"kind": "scheduled_event_resolved", "event_id": event["id"], "event_type": event["type"]}


def _army_size(state: dict[str, Any]) -> int:
    return sum(max(0, int(value or 0)) for value in state.get("army", {}).values())


def _turn_record(
    state: dict[str, Any],
    events: list[dict[str, Any]],
    elapsed_ms: float,
) -> dict[str, Any]:
    decision = state.get("management_ai", {}).get("last_decision")
    executed = next(
        (item.get("data", {}).get("action") for item in events if item.get("kind") == "structured_action_executed"),
        None,
    )
    return {
        "kind": "strategic_turn",
        "turn": state.get("turn"),
        "time": state.get("time"),
        "directive": (state.get("strategic_directive") or {}).get("title"),
        "action": executed,
        "action_was_legal": isinstance(executed, dict),
        "decision_score": decision.get("score") if isinstance(decision, dict) else None,
        "candidate_scores": [
            {"action_id": item["action"]["action_id"], "score": item["score"]}
            for item in (decision.get("candidates", []) if isinstance(decision, dict) else [])
        ],
        "crises": [
            item["message"]
            for item in events
            if item.get("severity") == "warning"
            or item.get("kind") in {"food_depleted", "treasury_empty", "rebellion_risk", "war_warning"}
        ],
        "resources": {
            key: state.get("resources", {}).get(key)
            for key in ("gold", "food", "wood", "stone", "population", "morale", "authority")
        },
        "army_size": _army_size(state),
        "planning_and_turn_ms": round(elapsed_ms, 3),
    }


def run(turns: int, seed: int, mode: str) -> dict[str, Any]:
    random.seed(seed)
    state = _start_state()
    state["management_ai"]["planner_seed"] = seed
    completed = 0
    attempts = 0
    illegal_actions = 0
    elapsed_samples: list[float] = []
    records: list[dict[str, Any]] = []
    while completed < turns:
        attempts += 1
        if attempts > turns * 6 + 20:
            raise RuntimeError("模拟无法越过连续阻塞事件")
        blocker = _resolve_blocker(state, mode)
        if blocker:
            records.append({**blocker, "time": state.get("time")})
            print(json.dumps(records[-1], ensure_ascii=False))
            continue
        before_turn = int(state.get("turn", 1))
        started = time.perf_counter()
        _, _, events = run_strategic_turn(
            state,
            "按领主议会当前方针推进九天",
            actor="management_ai",
        )
        elapsed_ms = (time.perf_counter() - started) * 1000
        if int(state.get("turn", 1)) == before_turn:
            interruption = {
                "kind": "interruption",
                "time": state.get("time"),
                "events": [
                    {"kind": item.get("kind"), "message": item.get("message")}
                    for item in events
                    if "interrupt" in str(item.get("kind"))
                    or "blocked" in str(item.get("kind"))
                    or item.get("phase") == "scheduled_events"
                ],
            }
            records.append(interruption)
            print(json.dumps(interruption, ensure_ascii=False))
            continue
        completed += 1
        elapsed_samples.append(elapsed_ms)
        record = _turn_record(state, events, elapsed_ms)
        if not record["action_was_legal"]:
            illegal_actions += 1
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))

    analysis = analyze_realm(state)
    summary = {
        "kind": "simulation_summary",
        "requested_turns": turns,
        "completed_turns": completed,
        "seed": seed,
        "mode": mode,
        "final_time": state.get("time"),
        "final_directive": state.get("strategic_directive"),
        "final_resources": state.get("resources"),
        "final_population": state.get("resources", {}).get("population"),
        "final_morale": state.get("resources", {}).get("morale"),
        "final_army": state.get("army"),
        "final_army_size": _army_size(state),
        "final_diplomacy": state.get("diplomacy"),
        "final_analysis": analysis,
        "illegal_action_count": illegal_actions,
        "planning_and_turn_ms_average": round(statistics.fmean(elapsed_samples), 3) if elapsed_samples else 0,
        "planning_and_turn_ms_max": round(max(elapsed_samples), 3) if elapsed_samples else 0,
        "record_count": len(records),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="运行确定性的领地管理 AI 长局模拟")
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1901)
    parser.add_argument("--mode", choices=("delegated", "advisory", "manual"), default="delegated")
    args = parser.parse_args()
    if args.turns < 1:
        parser.error("--turns 必须大于 0")
    if args.mode != "delegated":
        parser.error("长局自动模拟目前只支持 --mode delegated；其他模式需要玩家确认行动")
    run(args.turns, args.seed, args.mode)


if __name__ == "__main__":
    main()
