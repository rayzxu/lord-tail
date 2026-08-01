#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from types import SimpleNamespace

from app.engine.state import make_state
from app.engine.time import advance_strategic_clock
from app.engine.types import TurnContext
from app.storylets.director import run_director
from app.storylets.service import choose_storylet
from app.systems.scheduled_events import activate_due_events


def fresh_state() -> dict:
    state = make_state(SimpleNamespace(
        lord_name="测试领主", lord_gender="未说明", realm_name="测试领地", appearance="", personality="",
        talents=[{"id": "harvest_hand"}, {"id": "charismatic_lord"}], map_size=10,
        diplomacy=None, factions=None, realm_map=[], diplomacy_map=[],
    ))
    state["council"]["current_meeting"] = None
    state["scheduled_events"]["entries"] = []
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a deterministic Storylet frequency/save-growth simulation")
    parser.add_argument("--turns", type=int, default=100)
    parser.add_argument("--seed", type=int, default=2001)
    args = parser.parse_args()
    state = fresh_state()
    template_counts: Counter[str] = Counter()
    cast_counts: Counter[str] = Counter()
    decisions = []
    for index in range(max(1, args.turns)):
        activate_due_events(state, source="simulation")
        current_id = state["storylets"].get("current_instance_id")
        if current_id:
            instance = next(item for item in state["storylets"]["instances"] if item["id"] == current_id)
            choice_id = "refuse_petition" if "refuse_petition" in instance["choice_ids"] else instance["choice_ids"][0]
            choose_storylet(state, current_id, choice_id, actor="simulation")
        decision = run_director(state, seed=args.seed + index, commit=True)
        if decision.get("instance"):
            instance = decision["instance"]
            template_counts[instance["definition_id"]] += 1
            cast_counts.update(instance["cast"].values())
            decisions.append({"turn": index + 1, "day": state["time"]["calendar_day"], "instance_id": instance["id"], "definition_id": instance["definition_id"]})
        advance_strategic_clock(state, TurnContext(command="simulation", actor="system", advance_calendar_days=9), days=9)
    print(json.dumps({
        "turns": args.turns, "final_day": state["time"]["calendar_day"], "major_by_template": template_counts,
        "generated_characters": len(state["characters"]["entries"]), "relationships": len(state["character_relationships"]["edges"]),
        "households": len(state["households"]["entries"]), "instances": len(state["storylets"]["instances"]),
        "active_chains": sum(chain.get("status") == "active" for chain in state["storylets"]["chains"].values()),
        "max_character_appearances": max(cast_counts.values(), default=0), "decisions": decisions,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
