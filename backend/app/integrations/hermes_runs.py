from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx


def runs_base_url() -> str | None:
    value = os.getenv("HERMES_RUNS_BASE_URL", "").strip().rstrip("/")
    return value or None


def runs_headers() -> dict[str, str]:
    token = os.getenv("HERMES_RUNS_API_KEY", "").strip()
    return {"Authorization": f"Bearer {token}"} if token else {}


def runs_timeout() -> float:
    return float(os.getenv("HERMES_RUNS_TIMEOUT_SECONDS", "1800"))


async def create_run(payload: dict[str, Any]) -> dict[str, Any]:
    base_url = runs_base_url()
    if not base_url:
        raise RuntimeError("HERMES_RUNS_BASE_URL is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{base_url}/v1/runs", json=payload, headers=runs_headers())
        response.raise_for_status()
        return response.json()


async def get_run(hermes_run_id: str) -> dict[str, Any]:
    base_url = runs_base_url()
    if not base_url:
        raise RuntimeError("HERMES_RUNS_BASE_URL is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(f"{base_url}/v1/runs/{hermes_run_id}", headers=runs_headers())
        response.raise_for_status()
        return response.json()


async def stream_run_events(hermes_run_id: str) -> AsyncIterator[dict[str, Any]]:
    base_url = runs_base_url()
    if not base_url:
        raise RuntimeError("HERMES_RUNS_BASE_URL is not configured")
    timeout = httpx.Timeout(runs_timeout(), connect=10)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream("GET", f"{base_url}/v1/runs/{hermes_run_id}/events", headers=runs_headers()) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                payload = line.removeprefix("data:").strip()
                if payload == "[DONE]":
                    break
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(event, dict):
                    yield event


async def send_approval(hermes_run_id: str, choice: str) -> dict[str, Any]:
    base_url = runs_base_url()
    if not base_url:
        raise RuntimeError("HERMES_RUNS_BASE_URL is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/v1/runs/{hermes_run_id}/approval",
            json={"choice": choice},
            headers=runs_headers(),
        )
        response.raise_for_status()
        return response.json() if response.content else {"status": "ok"}


async def send_clarify(hermes_run_id: str, response_text: str) -> dict[str, Any]:
    base_url = runs_base_url()
    if not base_url:
        raise RuntimeError("HERMES_RUNS_BASE_URL is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/v1/runs/{hermes_run_id}/clarify",
            json={"response": response_text},
            headers=runs_headers(),
        )
        response.raise_for_status()
        return response.json() if response.content else {"status": "ok"}


async def cancel_run(hermes_run_id: str) -> dict[str, Any]:
    base_url = runs_base_url()
    if not base_url:
        raise RuntimeError("HERMES_RUNS_BASE_URL is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{base_url}/v1/runs/{hermes_run_id}/cancel", headers=runs_headers())
        if response.status_code == 404:
            response = await client.post(f"{base_url}/v1/runs/{hermes_run_id}/stop", headers=runs_headers())
        response.raise_for_status()
        return response.json() if response.content else {"status": "ok"}
