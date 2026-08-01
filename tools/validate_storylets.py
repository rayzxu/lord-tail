#!/usr/bin/env python3
from __future__ import annotations

import json

from app.storylets.config import load_definitions, validate_storylet_catalog


def main() -> None:
    validate_storylet_catalog()
    definitions = load_definitions()
    print(json.dumps({
        "status": "ok",
        "definition_count": len(definitions),
        "definitions": [f"{definition_id}:{node_key}" for definition_id, node_key in definitions],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
