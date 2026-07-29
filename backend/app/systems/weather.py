from __future__ import annotations

import random
from typing import Any

from ..engine.time import normalize_time
from ..engine.types import TurnContext, TurnEvent


SEASONAL_WEATHER: dict[str, list[str]] = {
    "春季": ["细雨", "薄雾", "阴云", "晴朗", "骤雨"],
    "夏季": ["晴朗", "闷热", "雷雨", "阴云", "干热"],
    "秋季": ["阴云", "薄雾", "晴朗", "冷雨", "大风"],
    "冬季": ["阴云", "寒风", "雪", "冻雨", "晴冷"],
}


def weather_options_for_season(season: str) -> list[str]:
    return list(SEASONAL_WEATHER.get(season, SEASONAL_WEATHER["春季"]))


def choose_next_weather(state: dict[str, Any], *, rng: random.Random | None = None) -> str:
    normalize_time(state)
    generator = rng or random
    time_state = state.setdefault("time", {})
    season = str(time_state.get("season") or state.get("season") or "春季")
    options = weather_options_for_season(season)
    current = str(time_state.get("weather") or state.get("weather") or "")
    candidates = [item for item in options if item != current]
    return generator.choice(candidates or options)


def set_weather(state: dict[str, Any], weather: str) -> None:
    normalize_time(state)
    state["weather"] = weather
    state.setdefault("time", {})["weather"] = weather


def advance_weather(state: dict[str, Any], context: TurnContext, *, rng: random.Random | None = None) -> None:
    normalize_time(state)
    previous = str(state.get("weather") or state.get("time", {}).get("weather") or "细雨")
    next_weather = choose_next_weather(state, rng=rng)
    set_weather(state, next_weather)
    context.events.append(TurnEvent(
        phase="weather",
        kind="changed",
        message=f"天气由{previous}转为{next_weather}。",
        data={
            "previous_weather": previous,
            "weather": next_weather,
            "season": state.get("season"),
            "calendar_day": state.get("time", {}).get("calendar_day"),
        },
    ))
