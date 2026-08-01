#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from app.engine.scenes import VALID_SCENE_TYPES
from app.storylets.config import EFFECT_OPS, load_arc_definitions, validate_storylet_catalog
from app.storylets.graph import analyze_graph


def main() -> None:
    parser = argparse.ArgumentParser(description="校验 Lord Tail schema v2 预编剧情图")
    parser.add_argument("--definition", help="只显示指定 definition id")
    parser.add_argument("--enumerate-paths", action="store_true", help="输出从 entry 到 terminal 的全部路径")
    args = parser.parse_args()

    validate_storylet_catalog()
    definitions = load_arc_definitions()
    if args.definition:
        if args.definition not in definitions:
            parser.error(f"未知 Story Arc：{args.definition}")
        definitions = {args.definition: definitions[args.definition]}

    rows = []
    for definition_id, definition in definitions.items():
        analysis = analyze_graph(definition, effect_ops=EFFECT_OPS, valid_scene_types=VALID_SCENE_TYPES)
        row = {
            "id": definition_id,
            "version": definition.get("version"),
            "entry_node": definition.get("entry_node"),
            "node_count": len(definition.get("nodes", {})),
            "terminal_nodes": sorted(analysis.terminal_nodes),
            "path_count": len(analysis.paths),
            "max_blocking_decisions": analysis.max_blocking_decisions,
        }
        if args.enumerate_paths:
            row["paths"] = [list(path) for path in analysis.paths]
        rows.append(row)
    print(json.dumps({"status": "ok", "story_arc_count": len(rows), "story_arcs": rows}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
