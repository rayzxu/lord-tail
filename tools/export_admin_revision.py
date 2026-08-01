#!/usr/bin/env python3
"""Print an Admin revision manifest for review or archival."""
from __future__ import annotations

import argparse
import json

from app.content.publish import revision_entries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("revision_id", nargs="?", help="rev_...；省略时列出全部 revision 摘要")
    args = parser.parse_args()
    rows = revision_entries()
    if args.revision_id:
        row = next((item for item in rows if item.get("id") == args.revision_id), None)
        if row is None:
            parser.error(f"未找到 revision：{args.revision_id}")
        print(json.dumps(row, ensure_ascii=False, indent=2))
        return
    summaries = [{key: item.get(key) for key in ("id", "time", "action", "content_type", "content_id", "summary")} for item in rows]
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
