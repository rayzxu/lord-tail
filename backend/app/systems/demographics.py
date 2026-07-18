from __future__ import annotations

from math import floor
from typing import Any

from ..catalog import BUILDINGS, POPULATION_CLASSES
from ..engine.mutations import change_resource
from ..engine.types import TurnContext, TurnEvent

AGE_KEYS = ("child", "working", "elder")
SEX_KEYS = ("female", "male")
PREGNANCY_MONTHS = [str(month) for month in range(1, 11)]


def _int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _split_total(total: int, ratios: dict[str, Any], keys: tuple[str, ...]) -> dict[str, int]:
    total = max(0, int(total))
    if total == 0:
        return {key: 0 for key in keys}
    raw = {key: float(ratios.get(key, 0)) for key in keys}
    ratio_sum = sum(max(0.0, value) for value in raw.values()) or 1.0
    values = {key: floor(total * max(0.0, raw[key]) / ratio_sum) for key in keys}
    remainder = total - sum(values.values())
    if remainder:
        values[keys[0]] += remainder
    return values


def _class_config(class_id: str) -> dict[str, Any]:
    return POPULATION_CLASSES.get(class_id, {})


def _initial_class_state(class_id: str, config: dict[str, Any], default_morale: int = 50) -> dict[str, Any]:
    population = _int(config.get("initial_population"))
    return {
        "name": config.get("name", class_id),
        "population": population,
        "wealth_per_capita": _int(config.get("initial_wealth_per_capita")),
        "morale": _int(config.get("initial_morale", default_morale)),
        "age": _split_total(population, config.get("age_distribution", {}), AGE_KEYS),
        "sex": _split_total(population, config.get("sex_distribution", {}), SEX_KEYS),
        "pregnancy": {month: 0 for month in PREGNANCY_MONTHS},
        "last_births": 0,
        "last_migration": 0,
        "last_outflow": 0,
        "last_wealth_delta": 0,
    }


def initialize_demographics(state: dict[str, Any]) -> None:
    default_morale = _int(state.get("resources", {}).get("morale"), 50)
    classes = {
        class_id: _initial_class_state(class_id, config, default_morale)
        for class_id, config in POPULATION_CLASSES.items()
    }
    state["demographics"] = {
        "classes": classes,
        "housing": {"by_type": {}, "total_capacity": 0, "total_occupied": 0, "total_vacant": 0},
        "last_births": 0,
        "last_migration": 0,
        "last_outflow": 0,
        "last_wealth_delta": 0,
    }
    recalculate_housing(state)
    sync_total_population(state)


def normalize_demographics(state: dict[str, Any]) -> None:
    if "demographics" not in state or not isinstance(state["demographics"], dict):
        initialize_demographics(state)
        return

    demographics = state["demographics"]
    classes = demographics.setdefault("classes", {})
    for class_id, config in POPULATION_CLASSES.items():
        if class_id not in classes or not isinstance(classes[class_id], dict):
            classes[class_id] = _initial_class_state(class_id, config, _int(state.get("resources", {}).get("morale"), 50))
            continue
        class_state = classes[class_id]
        population = _int(class_state.get("population"), _int(config.get("initial_population")))
        class_state["name"] = config.get("name", class_state.get("name", class_id))
        class_state["population"] = population
        class_state["wealth_per_capita"] = _int(
            class_state.get("wealth_per_capita"),
            _int(config.get("initial_wealth_per_capita")),
        )
        class_state["morale"] = min(100, _int(class_state.get("morale"), 50))
        class_state["age"] = _normalize_bucket(class_state.get("age"), population, config.get("age_distribution", {}), AGE_KEYS)
        class_state["sex"] = _normalize_bucket(class_state.get("sex"), population, config.get("sex_distribution", {}), SEX_KEYS)
        pregnancy = class_state.setdefault("pregnancy", {})
        for month in PREGNANCY_MONTHS:
            pregnancy[month] = _int(pregnancy.get(month))
        for key in ("last_births", "last_migration", "last_outflow", "last_wealth_delta"):
            class_state.setdefault(key, 0)
    demographics.setdefault("housing", {"by_type": {}})
    recalculate_housing(state)
    sync_total_population(state)


def _normalize_bucket(bucket: Any, population: int, ratios: dict[str, Any], keys: tuple[str, ...]) -> dict[str, int]:
    if not isinstance(bucket, dict):
        return _split_total(population, ratios, keys)
    values = {key: _int(bucket.get(key)) for key in keys}
    current_total = sum(values.values())
    if current_total == population:
        return values
    if current_total <= 0:
        return _split_total(population, ratios, keys)
    scale = population / current_total
    scaled = {key: floor(values[key] * scale) for key in keys}
    remainder = population - sum(scaled.values())
    if remainder:
        scaled[keys[0]] += remainder
    return scaled


def _iter_housing_specs(building: dict[str, Any]) -> list[dict[str, Any]]:
    housing = building.get("housing")
    if housing is None:
        return []
    if isinstance(housing, list):
        return [item for item in housing if isinstance(item, dict)]
    if isinstance(housing, dict):
        return [housing]
    return []


def _empty_housing_type() -> dict[str, int]:
    return {"capacity": 0, "occupied": 0, "vacant": 0, "quality": 0}


def recalculate_housing(state: dict[str, Any]) -> None:
    demographics = state.setdefault("demographics", {})
    housing = demographics.setdefault("housing", {})
    by_type: dict[str, dict[str, int]] = {}

    for building in BUILDINGS.values():
        count = _int(state.get("buildings", {}).get(building["name"]))
        if not count:
            continue
        for spec in _iter_housing_specs(building):
            housing_type = str(spec.get("type", "generic"))
            entry = by_type.setdefault(housing_type, _empty_housing_type())
            entry["capacity"] += _int(spec.get("capacity")) * count
            entry["quality"] = max(entry["quality"], _int(spec.get("quality")))

    by_type.setdefault("open_land_shelter", _empty_housing_type())
    for class_id, class_state in demographics.get("classes", {}).items():
        config = _class_config(class_id)
        remaining = _int(class_state.get("population"))
        for housing_type in config.get("housing_types", []):
            entry = by_type.setdefault(str(housing_type), _empty_housing_type())
            if housing_type == "open_land_shelter" and config.get("can_self_build_shelter") and remaining:
                entry["capacity"] += remaining
            available = max(0, entry["capacity"] - entry["occupied"])
            occupied = min(available, remaining)
            entry["occupied"] += occupied
            remaining -= occupied
            if remaining <= 0:
                break

    total_capacity = 0
    total_occupied = 0
    for entry in by_type.values():
        entry["vacant"] = max(0, entry["capacity"] - entry["occupied"])
        total_capacity += entry["capacity"]
        total_occupied += entry["occupied"]

    housing["by_type"] = by_type
    housing["total_capacity"] = total_capacity
    housing["total_occupied"] = total_occupied
    housing["total_vacant"] = max(0, total_capacity - total_occupied)


def sync_total_population(state: dict[str, Any]) -> None:
    total = sum(_int(class_state.get("population")) for class_state in state.get("demographics", {}).get("classes", {}).values())
    state.setdefault("resources", {})["population"] = total


def set_total_population(state: dict[str, Any], value: int) -> None:
    normalize_demographics(state)
    target = max(0, int(value))
    current = sum(_int(class_state.get("population")) for class_state in state["demographics"]["classes"].values())
    delta = target - current
    if delta == 0:
        sync_total_population(state)
        return
    classes = state["demographics"]["classes"]
    primary = "serfs" if "serfs" in classes else next(iter(classes), None)
    if primary is None:
        state["resources"]["population"] = target
        return
    if delta > 0:
        _add_population(classes[primary], delta)
    else:
        remaining = -delta
        for class_state in sorted(classes.values(), key=lambda item: _int(item.get("population")), reverse=True):
            remaining -= _remove_population(class_state, remaining)
            if remaining <= 0:
                break
    recalculate_housing(state)
    sync_total_population(state)


def change_total_population(state: dict[str, Any], delta: int) -> None:
    normalize_demographics(state)
    current = sum(_int(class_state.get("population")) for class_state in state["demographics"]["classes"].values())
    set_total_population(state, current + int(delta))


def class_vacant_housing(housing: dict[str, Any], housing_types: list[str]) -> int:
    by_type = housing.get("by_type", {})
    return sum(_int(by_type.get(housing_type, {}).get("vacant")) for housing_type in housing_types)


def employment_effect(state: dict[str, Any], class_id: str, working_population: int) -> dict[str, float | int]:
    slots = 0
    explicit_bonus = 0.0
    for building in BUILDINGS.values():
        count = _int(state.get("buildings", {}).get(building["name"]))
        if not count:
            continue
        employment = building.get("employment", {})
        if not isinstance(employment, dict):
            continue
        if employment.get("class_id") == class_id:
            slots += _int(employment.get("slots")) * count
            explicit_bonus += float(employment.get("productivity_bonus", 0)) * count
            continue
        if class_id in employment:
            slots += _int(employment.get(class_id)) * count
    employed = min(max(0, working_population), slots)
    utilization_bonus = 0.0 if working_population <= 0 else min(0.5, employed / working_population * 0.25)
    return {
        "slots": slots,
        "employed": employed,
        "productivity_bonus": explicit_bonus + utilization_bonus,
    }


def calculate_housing_pull(vacant_housing: int, class_morale: int, class_requirement: int) -> int:
    if class_morale <= class_requirement or vacant_housing <= 0:
        return 0
    return max(0, int((vacant_housing / 4) / max(1, class_morale - class_requirement)))


def calculate_outflow(population: int, authority: int, class_morale: int) -> int:
    if class_morale >= authority:
        return 0
    pressure = authority - class_morale
    return max(1, int(population * min(0.12, pressure / 1000)))


def _add_population(class_state: dict[str, Any], amount: int) -> None:
    if amount <= 0:
        return
    class_state["population"] = _int(class_state.get("population")) + amount
    class_state.setdefault("age", {}).setdefault("working", 0)
    class_state.setdefault("sex", {}).setdefault("female", 0)
    class_state.setdefault("sex", {}).setdefault("male", 0)
    class_state["age"]["working"] += amount
    female = amount // 2
    class_state["sex"]["female"] += female
    class_state["sex"]["male"] += amount - female


def _remove_population(class_state: dict[str, Any], amount: int) -> int:
    amount = min(amount, _int(class_state.get("population")))
    if amount <= 0:
        return 0
    class_state["population"] -= amount
    for bucket_name, preferred_keys in (("age", ("working", "child", "elder")), ("sex", ("female", "male"))):
        remaining = amount
        bucket = class_state.setdefault(bucket_name, {})
        for key in preferred_keys:
            take = min(remaining, _int(bucket.get(key)))
            bucket[key] = _int(bucket.get(key)) - take
            remaining -= take
            if remaining <= 0:
                break
    return amount


def settle_class_wealth(state: dict[str, Any], context: TurnContext) -> None:
    resources, changes = state["resources"], state["changes"]
    total_gold = 0
    total_delta = 0
    for class_id, class_state in state["demographics"]["classes"].items():
        config = _class_config(class_id)
        population = _int(class_state.get("population"))
        working_population = _int(class_state.get("age", {}).get("working"))
        employment = employment_effect(state, class_id, working_population)
        productivity = _float(config.get("productivity")) + float(employment["productivity_bonus"])
        tax = _float(config.get("tax"))
        expense = _float(config.get("expense"))
        wealth_delta = productivity - tax - expense
        class_state["wealth_per_capita"] = max(0, _int(class_state.get("wealth_per_capita")) + wealth_delta)
        class_state["last_wealth_delta"] = wealth_delta
        class_state["last_employed"] = employment["employed"]
        class_state["effective_productivity"] = round(productivity, 3)
        total_delta += int(wealth_delta * population)
        tax_income = int(max(0.0, tax) * population)
        production_value = max(0, int(working_population * productivity))
        total_gold += tax_income + production_value
    if total_gold:
        change_resource(resources, changes, "gold", total_gold)
    state["demographics"]["last_wealth_delta"] = total_delta
    context.events.append(TurnEvent(
        phase="demographics",
        kind="class_wealth",
        message="各阶级财富、税金与支出已经结算。",
        data={"gold": total_gold, "wealth_delta": total_delta},
    ))


def advance_pregnancy_and_births(state: dict[str, Any], context: TurnContext) -> None:
    total_births = 0
    for class_id, class_state in state["demographics"]["classes"].items():
        config = _class_config(class_id)
        pregnancy = class_state.setdefault("pregnancy", {month: 0 for month in PREGNANCY_MONTHS})
        births = _int(pregnancy.get("10"))
        for month in reversed(range(2, 11)):
            pregnancy[str(month)] = _int(pregnancy.get(str(month - 1)))
        working_females = int(_int(class_state.get("age", {}).get("working")) * 0.5)
        pregnant_now = sum(_int(pregnancy.get(month)) for month in PREGNANCY_MONTHS)
        fertile = max(0, min(_int(class_state.get("sex", {}).get("female")), working_females) - pregnant_now)
        monthly_rate = float(config.get("annual_birth_rate", 0)) / 12
        new_pregnancies = max(0, int(fertile * monthly_rate))
        pregnancy["1"] = new_pregnancies
        if births:
            class_state["population"] = _int(class_state.get("population")) + births
            class_state.setdefault("age", {}).setdefault("child", 0)
            class_state.setdefault("sex", {}).setdefault("female", 0)
            class_state.setdefault("sex", {}).setdefault("male", 0)
            class_state["age"]["child"] += births
            female = births // 2
            class_state["sex"]["female"] += female
            class_state["sex"]["male"] += births - female
        class_state["last_births"] = births
        total_births += births
    state["demographics"]["last_births"] = total_births
    context.events.append(TurnEvent(
        phase="demographics",
        kind="births",
        message=f"本轮共有 {total_births} 名新生儿登记入册。",
        data={"births": total_births},
    ))


def apply_population_flow(state: dict[str, Any], context: TurnContext) -> None:
    authority = _int(state.get("resources", {}).get("authority"))
    housing = state["demographics"].get("housing", {})
    total_migration = 0
    total_outflow = 0
    for class_id, class_state in state["demographics"]["classes"].items():
        config = _class_config(class_id)
        vacant = class_vacant_housing(housing, list(config.get("housing_types", [])))
        migration = calculate_housing_pull(vacant, _int(class_state.get("morale")), _int(config.get("requirement")))
        outflow = calculate_outflow(_int(class_state.get("population")), authority, _int(class_state.get("morale")))
        if migration:
            _add_population(class_state, migration)
        removed = _remove_population(class_state, outflow)
        class_state["last_migration"] = migration
        class_state["last_outflow"] = removed
        total_migration += migration
        total_outflow += removed
    state["demographics"]["last_migration"] = total_migration
    state["demographics"]["last_outflow"] = total_outflow
    context.events.append(TurnEvent(
        phase="demographics",
        kind="population_flow",
        message=f"迁入 {total_migration} 人，流失 {total_outflow} 人。",
        data={"migration": total_migration, "outflow": total_outflow},
    ))


def run_demographics_phase(state: dict[str, Any], context: TurnContext) -> None:
    normalize_demographics(state)
    recalculate_housing(state)
    settle_class_wealth(state, context)
    advance_pregnancy_and_births(state, context)
    apply_population_flow(state, context)
    recalculate_housing(state)
    sync_total_population(state)
