# Plan 003: Economy and Construction Modules

## 目标

落地明确的 `economy` 和 `construction` 模块，让领地运营不再只是“建筑产出 + 人口扣粮”的简化逻辑。

本 plan 不实现战斗和外交，只负责：

- 资源生产。
- 资源消耗。
- 建筑队列。
- 劳力占用。
- 建筑完成/取消/摧毁事件。
- 经济报告事件。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`
- `/Users/ray/raylab/lord-tail/backend/app/engine/turn.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/mutations.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/types.py`

如果 Plan 001 和 Plan 002 尚未执行，先执行它们。

## 输出文件

```text
/Users/ray/raylab/lord-tail/backend/app/systems/economy.py
/Users/ray/raylab/lord-tail/backend/app/systems/construction.py
/Users/ray/raylab/lord-tail/backend/app/systems/__init__.py
```

## 状态字段

在游戏 state 中正式维护：

```json
{
  "resources": {},
  "changes": {},
  "buildings": {},
  "construction_queue": [
    {
      "id": "project_1",
      "building_id": "farm",
      "x": 5,
      "y": 4,
      "remaining_turns": 2,
      "total_turns": 2,
      "workforce": 8,
      "status": "active"
    }
  ],
  "workforce": {
    "available": 100,
    "assigned": 8
  }
}
```

`workforce.available` 可先等于 `population`，后续可被政策、伤亡、疾病影响。

## catalog 扩展

在 `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json` 中保持现有 building 字段，并允许扩展：

```json
{
  "maintenance": {
    "gold": 1
  },
  "morale_effect": 0
}
```

如果某建筑没有这些字段，默认 `{}` 和 `0`。

## 步骤

1. 新增 `systems/construction.py`。
2. 在 `construction.py` 中实现：
   - `start_project(state, building_id, x, y, context)`
   - `advance_projects(state, context)`
   - `complete_project(state, project, context)`
   - `cancel_project(state, project_id, context)`
   - `destroy_building(state, building_id_or_name, x, y, context)`
3. `start_project` 必须校验：
   - 建筑 id 存在。
   - 坐标存在。
   - 地形符合 `requires`。
   - 资源足够。
   - 可用劳力足够。
4. 建筑开工时扣成本，占用 workforce。
5. 建筑完工时：
   - `buildings[building.name] += 1`
   - 地图 tile 更新为 `tile_kind`
   - 释放 workforce
   - 追加 `TurnEvent(phase="construction", kind="project_completed", ...)`
6. 新增 `systems/economy.py`。
7. 在 `economy.py` 中实现：
   - `produce_resources(state, context)`
   - `consume_population_food(state, context)`
   - `apply_building_maintenance(state, context)`
   - `apply_tax_income(state, context)`
   - `run_economy_phase(state, context)`
8. 经济阶段必须把每项变化写入 `state["changes"]`，并追加结构化事件。
9. 修改 pipeline：
   - `run_construction` 调用 `advance_projects`
   - `run_economy` 调用 `run_economy_phase`
10. 修改当前建造命令处理逻辑，让它调用 `construction.start_project`，不要在 command parser 里手写扣资源和写队列。

## 不要做的事

- 不要在 command parser 中直接修改建筑队列。
- 不要在 economy 中处理部队维持费；部队维持费留给 Plan 004 的 `military`。
- 不要把 narrative 文案写死在 economy/construction；系统只产生事件。

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

turn1 = client.post("/api/game/turn", json={"command": "在 E4 建造农田"})
assert turn1.status_code == 200, turn1.text
state = turn1.json()["state"]
assert state["resources"]["gold"] == 450
assert state["construction_queue"][0]["building_id"] == "farm"
assert state["workforce"]["assigned"] >= 8

turn2 = client.post("/api/game/turn", json={"command": "巡视领地"})
assert turn2.status_code == 200, turn2.text
state = turn2.json()["state"]
assert state["buildings"].get("农田", 0) >= 1
assert state["workforce"]["assigned"] == 0

turn3 = client.post("/api/game/turn", json={"command": "巡视粮仓"})
assert turn3.status_code == 200, turn3.text
assert turn3.json()["state"]["changes"]["food"] != 0

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
```

## 完成判定

- 建筑开工、推进、完工由 `systems/construction.py` 管理。
- 资源生产、人口粮食消耗、建筑维护由 `systems/economy.py` 管理。
- `local_turn` 或 command parser 不再直接写 construction queue。
- 验证命令输出 `OK`。
