# Plan 001: Backend Module Split

## 目标

把当前集中在 `/Users/ray/raylab/lord-tail/backend/app/main.py` 的后端逻辑拆成明确模块，为后续 `economy / construction / military / diplomacy / events` 和统一回合 pipeline 做结构准备。

本 plan 只做**行为不变的结构拆分**，不新增复杂玩法。

## 当前问题

`main.py` 同时承担：

- FastAPI app 和 HTTP 路由。
- 游戏状态创建、读取和保存。
- 资源变更、建筑解析、兵种解析。
- 本地命令解析和回合结算。
- Hermes HTTP 适配。
- 统一 `/api/state/*` 状态变更接口。

这会导致后续实现战斗、外交、事件时继续堆进一个文件，难以测试和复用。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/main.py`
- `/Users/ray/raylab/lord-tail/backend/app/catalog.py`
- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`

## 输出文件结构

在 `/Users/ray/raylab/lord-tail/backend/app/` 下新增或调整：

```text
app/
  main.py
  api/
    __init__.py
    game.py
    state.py
  engine/
    __init__.py
    state.py
    mutations.py
    commands.py
    turn.py
  integrations/
    __init__.py
    hermes.py
```

### 模块职责

| 文件 | 职责 |
|---|---|
| `main.py` | 只创建 FastAPI app、挂载 router、配置 CORS |
| `api/game.py` | `/api/game/start`、`/api/game/turn`、`/api/game/save`、`/api/game/load` |
| `api/state.py` | `/api/state/*` 和 `/api/hermes/*` 兼容别名 |
| `engine/state.py` | `current_state`、`make_state`、`require_state`、save/load |
| `engine/mutations.py` | 资源、人口、民心、部队、外交、建筑的状态变更函数 |
| `engine/commands.py` | 暂时保留当前关键词命令解析 |
| `engine/turn.py` | 暂时承接当前 `local_turn` 和 `settle_economy` |
| `integrations/hermes.py` | `call_hermes` |

## 不要做的事

- 不要改变现有 API response shape。
- 不要删除 `/api/hermes/*` 兼容路由。
- 不要新增复杂战斗或外交规则。
- 不要把配置从 `catalog.json` 移回 Python。
- 不要改前端 UI，除非 TypeScript build 明确失败。

## 步骤

1. 创建 `api/`、`engine/`、`integrations/` 目录和 `__init__.py`。
2. 把 Pydantic request models 从 `main.py` 移到相关 router 文件，或放到 `api/schemas.py`。选择一种，不要重复定义。
3. 把 `make_state`、`require_state`、`current_state`、`SAVE_PATH`、save/load 存档逻辑移到 `engine/state.py`。
4. 把 `clamp_resource`、`ensure_resource_key`、`change_resource`、`set_resource`、`resolve_unit`、`resolve_building`、`update_tile_for_building`、`apply_state_patch` 移到 `engine/mutations.py`。
5. 把 `command_coordinate`、`first_mentioned` 和当前 `local_turn` 的命令解析部分移到 `engine/commands.py`。
6. 把当前 `settle_economy` 和临时 `local_turn` 编排移到 `engine/turn.py`。
7. 把 `call_hermes` 移到 `integrations/hermes.py`。
8. `main.py` 中只保留：
   - FastAPI app 创建
   - CORS
   - `app.include_router(game.router, prefix="/api")`
   - `app.include_router(state.router, prefix="/api")`
   - `/api/health`
   - `/api/catalog`
   - `/api/talents`
9. 用 `rg "def .*turn|current_state|call_hermes|settle_economy" backend/app` 确认函数已经分布到目标模块。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
assert client.get("/api/health").status_code == 200
assert client.get("/api/catalog").status_code == 200

start = client.post("/api/game/start", json={
    "lord_name": "Ray",
    "lord_gender": "未说明",
    "realm_name": "北境",
    "appearance": "",
    "personality": "",
    "talents": [{"id": "harvest_hand"}, {"id": "charismatic_lord"}],
})
assert start.status_code == 200, start.text

turn = client.post("/api/game/turn", json={"command": "在 E4 建造农田"})
assert turn.status_code == 200, turn.text
assert "state" in turn.json()

state = client.post("/api/state/resources", json={"changes": {"gold": 1}})
assert state.status_code == 200, state.text

compat = client.post("/api/hermes/resources", json={"changes": {"gold": 1}})
assert compat.status_code == 200, compat.text

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

## 完成判定

- `main.py` 不再包含回合结算、状态 mutation、Hermes HTTP 逻辑。
- 现有启动、开局、回合、存档、`/api/state/*`、`/api/hermes/*` 均保持可用。
- 验证命令输出 `OK` 且退出码为 0。
