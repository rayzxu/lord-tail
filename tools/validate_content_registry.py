#!/usr/bin/env python3
"""Validate every Lord Tail content document without changing published data."""
from __future__ import annotations

import json
import sys

from app.catalog import validate_map_tile_kinds_catalog
from app.content.character_config import validate_character_configs
from app.content.models import CONTENT_TYPES
from app.content.repository import list_documents, published_revision
from app.content.validation import validation_payload
from app.storylets.config import validate_storylet_catalog


def main() -> int:
    validate_character_configs()
    validate_map_tile_kinds_catalog()
    validate_storylet_catalog()
    failures: list[dict[str, object]] = []
    count = 0
    for content_type in sorted(CONTENT_TYPES):
        for item in list_documents(content_type):
            count += 1
            result = validation_payload(content_type, item["id"], item["document"])
            if not result["valid"]:
                failures.append({"content_type": content_type, "content_id": item["id"], **result})
    output = {
        "valid": not failures,
        "documents": count,
        "registry_revision": published_revision(),
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
