# Plan 004: Military and Diplomacy Modules

## 目标

落地明确的 `military` 和 `diplomacy` 模块，补齐当前几乎不存在的战斗结算和外交结算。

本 plan 做 MVP，不追求复杂战争游戏，但必须从“字符串状态”升级成可演化的系统。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`
- `/Users/ray/raylab/lord-tail/backend/app/engine/turn.py`
- `/Users/ray/raylab/lord-tail/backend/app/systems/economy.py`
- `/Users/ray/raylab/lord-tail/backend/app/systems/construction.py`

如果 Plan 001、002、003 尚未执行，先执行它们。

## 输出文件

```text
/Users/ray/raylab/lord-tail/backend/app/systems/military.py
/Users/ray/raylab/lord-tail/backend/app/systems/diplomacy.py
```

## 状态字段

扩展 state：

```json
{
  "army": {
    "infantry": 0,
    "archers": 0,
    "cavalry": 0
  },
  "army_status": {
    "organization": 100,
    "routed": false,
    "last_loss_ratio": 0.0
  },
  "training_queue": [
    {
      "id": "training_1",
      "unit_id": "infantry",
      "quantity": 10,
      "remaining_turns": 1,
      "total_turns": 1
    }
  ],
  "battles": [],
  "diplomacy": {
    "金鳞": {
      "stance": "中立",
      "relation": 0,
      "treaties": [],
      "at_war": false
    }
  }
}
```

兼容要求：

- 旧存档里 `diplomacy["金鳞"] == "中立"` 的字符串格式必须能在 load 或 start 后被迁移成对象格式。
- `/api/state/diplomacy` 可以继续接受 `{ "faction": "金鳞", "status": "友善" }`，内部转成 `stance`。

## military MVP

### 组织度

组织度是军队能否保持阵形、响应命令和持续作战的核心状态。它不是兵种数量，而是整支领地军队当前的战斗秩序。

`systems/military.py` 实现：

- `normalize_army_status(state)`
- `change_organization(state, delta, reason, context)`
- `apply_organization_modifiers(base_attack, base_defense, organization)`
- `check_rout(state, battle_result, context)`

状态字段：

```json
{
  "army_status": {
    "organization": 100,
    "routed": false,
    "last_loss_ratio": 0.0
  }
}
```

组织度规则：

- `organization` 范围固定为 `0..100`。
- 新游戏默认 `100`。
- 战斗伤亡、缺粮欠饷、连续行军、夜战、恶劣地形可以降低组织度。
- 休整、胜利、补给充足、领主能力或事件可以恢复组织度。
- 旧存档缺少 `army_status` 时，`normalize_army_status(state)` 必须补默认值。

攻防惩罚规则：

| 组织度 | 攻击倍率 | 防御倍率 | 说明 |
|---|---:|---:|---|
| `>= 60` | `1.00` | `1.00` | 阵形完整 |
| `30..59` | `0.75` | `0.80` | 命令传递迟缓 |
| `1..29` | `0.40` | `0.50` | 阵形濒临崩溃 |
| `0` | `0.20` | `0.25` | 只剩零散抵抗 |

战斗力公式必须改为：

```text
attack_power = sum(count * combat.power) * organization_attack_multiplier
defense_power = sum(count * combat.defense) * organization_defense_multiplier
```

如果某兵种没有 `combat.defense`，默认 `defense = power`；如果 `power` 也缺失，默认 `1.0`。

### 兵种克制、攻击距离和速度

每个兵种的战术特性必须由 `catalog.units[*].combat` 管理，不允许硬编码在 `military.py`。

字段定义：

```json
{
  "combat": {
    "power": 1.0,
    "defense": 1.0,
    "morale": 1.0,
    "organization_damage": 1.0,
    "range": 1,
    "speed": 1.0,
    "counters": {
      "cavalry": 1.25
    }
  }
}
```

字段规则：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---:|---|
| `range` | int | `1` | 攻击距离，单位为战术格；近战为 `1`，弓兵可设为 `3` 或更高 |
| `speed` | float | `1.0` | 战术速度，用于先手、追击、撤退和距离控制 |
| `counters` | object | `{}` | 对特定敌方兵种 id 的克制倍率，key 必须是 `units` 的 id |

克制关系要求：

- `counters` 的 key 必须使用兵种 id，例如 `infantry`、`archers`、`cavalry`。
- 不允许使用中文名作为克制 key，例如不要写 `"骑兵": 1.25`。
- `counters[target_unit_id] = 1.25` 表示本兵种攻击该目标兵种时攻击贡献乘以 `1.25`。
- 如果没有命中克制关系，倍率为 `1.0`。
- 如果 catalog 中出现不存在的 target unit id，启动或测试时必须报错，不能静默忽略。

攻击距离规则：

- `range` 影响战斗轮中的有效输出。
- MVP 可以用“距离优势”简化处理：如果我方平均射程高于敌方平均射程，第一轮获得一次 `range_advantage_multiplier`，建议为 `1.10`。
- 远程单位在敌方速度明显更高时可能失去距离优势；MVP 规则：如果敌方平均 `speed >= 我方平均 speed + 0.75`，不应用射程优势。
- 后续战术地图落地后，`range` 必须直接接入格子距离判定。

速度规则：

- `speed` 影响先手、追击和撤退。
- MVP 公式：
  - 平均速度更高的一方获得 `initiative = true`。
  - 如果胜方平均速度高于败方 `0.5` 以上，败方额外损失 `5%`。
  - 如果败方平均速度高于胜方 `0.5` 以上，败方减少 `5%` 损失。
- 溃逃时速度差必须参与追击损失；MVP 可以复用上面的 `5%` 规则。

溃逃规则：

- 每次战斗后计算 `loss_ratio = casualties / max(1, pre_battle_total_units)`。
- 如果 `organization < 25` 且 `loss_ratio >= 0.15`，军队溃逃。
- 如果单次 `loss_ratio >= 0.35`，无论当前组织度多少，都必须进行溃逃判定；MVP 中直接设置 `routed = true`。
- 溃逃后：
  - `army_status.routed = true`
  - `organization = min(organization, 10)`
  - 本场后续追击/额外伤亡可以先不做，但必须追加 `TurnEvent(phase="military", kind="army_routed", severity="critical", ...)`
- `routed = true` 时，下一场战斗的攻击/防御倍率固定使用组织度 `0` 档，直到后续休整系统恢复。

### 训练

`systems/military.py` 实现：

- `start_training(state, unit_id, quantity, context)`
- `advance_training(state, context)`
- `apply_upkeep(state, context)`
- `resolve_battle(state, battle_request, context)`
- `apply_organization_modifiers(base_attack, base_defense, organization)`
- `unit_counter_multiplier(attacker_unit_id, defender_unit_id)`
- `average_range(units: dict[str, int])`
- `average_speed(units: dict[str, int])`
- `range_advantage_multiplier(attacker, defender)`
- `speed_casualty_modifier(winner, loser)`
- `check_rout(state, battle_result, context)`

训练规则：

- 校验 `requires_building`。
- 开始训练时扣 `cost * quantity`。
- 加入 `training_queue`。
- 每轮推进，完成后 `army[unit_id] += quantity`。

维持费规则：

- 每轮按 `catalog.units[*].upkeep * count` 扣资源。
- 如果粮食或金币不足，先扣到 0，再追加士气/民心惩罚事件；具体数值可以先写入 catalog 或常量 TODO，但不能无声失败。

### 战斗

MVP 战斗输入可以先是内部函数，不必立刻做 UI：

```json
{
  "enemy": {
    "infantry": 10,
    "archers": 3
  },
  "terrain": "grass",
  "stance": "balanced"
}
```

MVP 公式：

- 每个兵种从 `catalog.json` 读取或补充 `combat.power`。
- 我方攻击战力 = `sum(count * combat.power * counter_multiplier) * organization_attack_multiplier * range_multiplier`。
- 我方防御战力 = `sum(count * combat.defense) * organization_defense_multiplier`。
- 敌方战力同样支持组织度；如果 battle request 没有传入敌方组织度，默认 `100`。
- 克制关系必须按敌方实际兵种构成计算，不能只看总人数。
- 攻击距离影响第一轮或抽象总战力的 `range_multiplier`。
- 速度影响先手、追击、撤退和溃逃后的额外损失。
- 胜负按战力比判断。
- 伤亡按战力比和 stance 计算。
- 伤亡结算后必须更新 `army_status.last_loss_ratio`。
- 伤亡会降低组织度，MVP 建议：`organization_delta = -round(loss_ratio * 100)`。
- 组织度低于阈值或损失突破阈值时触发溃逃。
- 结果写入 `battles` 并追加 `TurnEvent(phase="military", kind="battle_resolved", ...)`。

## diplomacy MVP

`systems/diplomacy.py` 实现：

- `normalize_diplomacy_state(state)`
- `change_relation(state, faction, delta, reason, context)`
- `set_stance(state, faction, stance, context)`
- `add_treaty(state, faction, treaty, duration_turns, context)`
- `advance_treaties(state, context)`
- `run_diplomacy_phase(state, context)`

外交规则：

- `relation` 范围 `-100..100`。
- `stance` 从 relation 派生默认值：
  - `>= 60`: 友善
  - `-30..59`: 中立
  - `< -30`: 敌对
- `at_war=true` 时 stance 固定显示为敌对或战争。
- 条约每回合减少 duration，归零移除。

## catalog 扩展

在 `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json` 中为 units 补：

```json
{
  "combat": {
    "power": 1.0,
    "defense": 1.0,
    "morale": 1.0,
    "organization_damage": 1.0,
    "range": 1,
    "speed": 1.0,
    "counters": {
      "cavalry": 1.25
    }
  }
}
```

如果缺失，`military.py` 使用默认 `power=1.0`、`defense=power`、`organization_damage=1.0`、`range=1`、`speed=1.0`、`counters={}`，但应在 TODO 注释中说明要补全。

必须在 catalog loader 或 military 初始化校验：

- `combat.range >= 1`
- `combat.speed > 0`
- `combat.counters` 的所有 key 都存在于 `units`。
- `combat.counters` 的所有 value 都是正数。

## 步骤

1. 新增 `systems/military.py` 和 `systems/diplomacy.py`。
2. 修改 state 创建逻辑，加入 `training_queue`、`army_status` 和对象格式 diplomacy。
3. 增加旧 diplomacy 字符串格式的 normalize 函数，并在 load/start/turn 前调用。
4. 增加 `normalize_army_status(state)`，并在 load/start/turn 前调用；旧存档缺字段时补 `{ "organization": 100, "routed": false, "last_loss_ratio": 0.0 }`。
5. 修改招募命令：从“立即加兵”改为 `start_training`。
6. 修改 pipeline：
   - `run_military` 调用 `advance_training` 和 `apply_upkeep`
   - `run_diplomacy` 调用 `run_diplomacy_phase`
7. 修改 `/api/state/army`，继续允许直接改兵力，但内部走 `military` helper。
8. 修改 `/api/state/diplomacy`，让它更新对象格式 diplomacy。
9. 增加一个内部战斗 smoke test，可以通过临时 debug endpoint 或直接 import `resolve_battle` 测。
10. 增加一个组织度 smoke test，必须覆盖：
   - 低组织度降低攻击/防御。
   - 损失率达到阈值后触发 `routed = true`。
   - 触发 `army_routed` 事件。
11. 增加 `validate_unit_combat_catalog()`，校验所有 `range`、`speed`、`counters`。
12. 增加兵种克制 smoke test，必须覆盖：
   - `counters` 使用 unit id。
   - 步兵克制骑兵时，步兵攻击骑兵的贡献高于无克制情况。
   - 不存在的 counter target id 会报错。
13. 增加攻击距离和速度 smoke test，必须覆盖：
   - 高射程且速度未被压制时获得射程优势。
   - 高速胜方追击会增加败方损失。

## 不要做的事

- 不要在本 plan 做完整战术地图寻路。
- 不要做 AI 外交策略树。
- 不要让 diplomacy 同时存在字符串和对象两套活跃格式。
- 不要把训练时间配置硬编码在 military.py；读取 `catalog.json` 的 `training_turns`。
- 不要把组织度写进 `army["infantry"]` 这种兵种数量字段；组织度必须在 `army_status`。
- 不要让溃逃只存在 narrative 文本里；必须有机器可读的 `army_status.routed` 和 `army_routed` event。
- 不要用中文兵种名配置克制关系；克制 key 必须是兵种 id。
- 不要把攻击距离和速度写成 narrative-only 文案；它们必须参与战斗结算。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
client.post("/api/game/start", json={
    "lord_name": "Ray",
    "lord_gender": "未说明",
    "realm_name": "北境",
    "appearance": "",
    "personality": "",
    "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
})

client.post("/api/state/buildings", json={"building": "训练场", "action": "build", "count": 1})
train = client.post("/api/game/turn", json={"command": "训练 3 名步兵"})
assert train.status_code == 200, train.text
assert train.json()["state"]["training_queue"]

advance = client.post("/api/game/turn", json={"command": "巡视训练场"})
assert advance.status_code == 200, advance.text
assert advance.json()["state"]["army"]["infantry"] >= 3
assert advance.json()["state"]["army_status"]["organization"] == 100

dip = client.post("/api/state/diplomacy", json={"faction": "金鳞", "status": "友善"})
assert dip.status_code == 200, dip.text
assert isinstance(dip.json()["state"]["diplomacy"]["金鳞"], dict)
assert dip.json()["state"]["diplomacy"]["金鳞"]["stance"] == "友善"

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
```

组织度和溃逃的额外验证，允许直接 import `systems.military` 执行：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.systems.military import apply_organization_modifiers, check_rout

attack, defense = apply_organization_modifiers(100, 100, 20)
assert attack == 40
assert defense == 50

state = {
    "army_status": {"organization": 20, "routed": False, "last_loss_ratio": 0.0}
}
events = []
context = type("Context", (), {"events": events})()
check_rout(state, {"casualties": 15, "pre_battle_total_units": 100}, context)
assert state["army_status"]["routed"] is True
assert state["army_status"]["organization"] <= 10
assert any(event.kind == "army_routed" or getattr(event, "kind", None) == "army_routed" for event in events)

print("OK")
PY
```

兵种克制、攻击距离、速度的额外验证，允许直接 import `systems.military` 执行：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from app.systems.military import (
    average_range,
    average_speed,
    range_advantage_multiplier,
    speed_casualty_modifier,
    unit_counter_multiplier,
    validate_unit_combat_catalog,
)

validate_unit_combat_catalog()

assert unit_counter_multiplier("infantry", "cavalry") >= 1.0
assert unit_counter_multiplier("infantry", "unknown_unit") == 1.0

archer_force = {"archers": 10}
infantry_force = {"infantry": 10}
assert average_range(archer_force) > average_range(infantry_force)
assert average_speed({"cavalry": 10}) > average_speed({"infantry": 10})

assert range_advantage_multiplier(archer_force, infantry_force) >= 1.0
assert speed_casualty_modifier({"cavalry": 10}, {"infantry": 10}) >= 1.0

print("OK")
PY
```

## 完成判定

- 兵种训练不再立即完成，而是进入 `training_queue`。
- 部队维持费由 `systems/military.py` 每回合处理。
- 军队拥有 `army_status.organization`，并参与攻击/防御倍率。
- 组织度低且损失率突破阈值后会设置 `army_status.routed = true`。
- 溃逃必须产生机器可读 `army_routed` 事件。
- 每个兵种的 `combat.range`、`combat.speed`、`combat.counters` 由 `catalog.json` 管理。
- 克制关系使用 unit id 校验，不能使用中文名。
- 兵种克制、攻击距离和速度实际参与 `resolve_battle` 结算。
- diplomacy 内部统一为对象格式。
- 至少有一个可测试的 MVP 战斗结算函数。
- 验证命令输出 `OK`。
