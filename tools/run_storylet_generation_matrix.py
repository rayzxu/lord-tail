#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

from app.engine.state import make_state
from app.storylets.service import instantiate_storylet


def fresh_state() -> dict:
    state = make_state(SimpleNamespace(
        lord_name="测试领主", lord_gender="未说明", realm_name="测试领地", appearance="", personality="",
        talents=[{"id": "harvest_hand"}, {"id": "charismatic_lord"}], map_size=10,
        diplomacy=None, factions=None, realm_map=[], diplomacy_map=[],
    ))
    state["council"]["current_meeting"] = None
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate deterministic Storylet previews without mutating a live game")
    parser.add_argument("--definition", default="petition_building_credit")
    parser.add_argument("--node-key", default="petition")
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--start-seed", type=int, default=1)
    args = parser.parse_args()
    rows = []
    for seed in range(args.start_seed, args.start_seed + max(1, args.seeds)):
        state = fresh_state()
        try:
            preview = instantiate_storylet(state, args.definition, node_key=args.node_key, seed=seed, commit=False)["instance"]
            rows.append({"seed": seed, "ok": True, "cast": preview["cast_snapshots"], "facts": preview["facts"], "choices": preview["choice_ids"]})
        except Exception as exc:  # diagnostic tool intentionally captures every rejected draft
            rows.append({"seed": seed, "ok": False, "error": str(exc)})
    print(json.dumps({"definition": args.definition, "node_key": args.node_key, "total": len(rows), "successes": sum(row["ok"] for row in rows), "rows": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
