from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any

TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

_RUNS: dict[str, dict[str, Any]] = {}


def create_run(mode: str, input_text: str, hermes_run_id: str | None, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    run_id = f"lt_run_{uuid.uuid4().hex}"
    now = time.time()
    run = {
        "run_id": run_id,
        "hermes_run_id": hermes_run_id,
        "mode": mode,
        "input": input_text,
        "status": "started",
        "events": [],
        "final_text": "",
        "created_at": now,
        "updated_at": now,
        "metadata": metadata or {},
        "next_seq": 1,
    }
    _RUNS[run_id] = run
    return deepcopy(run)


def get_run(run_id: str) -> dict[str, Any] | None:
    run = _RUNS.get(run_id)
    return deepcopy(run) if run else None


def require_run(run_id: str) -> dict[str, Any]:
    run = get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    return run


def update_status(run_id: str, status: str) -> dict[str, Any]:
    run = _RUNS[run_id]
    run["status"] = status
    run["updated_at"] = time.time()
    return deepcopy(run)


def append_event(run_id: str, event: dict[str, Any]) -> dict[str, Any]:
    run = _RUNS[run_id]
    item = dict(event)
    item.setdefault("run_id", run_id)
    if run.get("hermes_run_id"):
        item.setdefault("hermes_run_id", run["hermes_run_id"])
    item.setdefault("timestamp", time.time())
    item["seq"] = run["next_seq"]
    run["next_seq"] += 1
    run["events"].append(item)
    run["updated_at"] = time.time()

    event_name = item.get("event")
    if event_name == "message.delta":
        run["final_text"] += str(item.get("delta", ""))
        run["status"] = "running"
    elif event_name == "run.completed":
        if item.get("output"):
            run["final_text"] = str(item["output"])
        run["status"] = "completed"
    elif event_name == "run.failed":
        run["status"] = "failed"
    elif event_name == "run.cancelled":
        run["status"] = "cancelled"
    elif event_name in {"approval.request", "clarify.request"}:
        run["status"] = "waiting_for_approval" if event_name == "approval.request" else "waiting_for_clarify"
    elif run.get("status") == "started":
        run["status"] = "running"
    return deepcopy(item)


def events_after(run_id: str, since_seq: int = 0) -> list[dict[str, Any]]:
    run = _RUNS[run_id]
    return [deepcopy(event) for event in run["events"] if int(event.get("seq", 0)) > since_seq]


def reset_runs_for_tests() -> None:
    _RUNS.clear()

