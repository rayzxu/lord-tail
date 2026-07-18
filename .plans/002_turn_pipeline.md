# Plan 002: Unified Turn Settlement Pipeline

## 目标

引入统一回合结算 pipeline，替代当前 `local_turn()` 里“解析命令、执行动作、经济结算、建筑推进、天气推进”混在一起的流程。

完成后，每一轮都按固定阶段执行：

```text
start_turn
player_or_agent_action
construction
economy
military
diplomacy
events
end_turn
```

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/engine/turn.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/commands.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/mutations.py`
- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`

如果 Plan 001 尚未执行，先执行 Plan 001。

## 输出 schema

新增内部结算结果结构，建议放在 `/Users/ray/raylab/lord-tail/backend/app/engine/types.py`：

```python
from pydantic import BaseModel, Field

class TurnEvent(BaseModel):
    phase: str
    kind: str
    message: str
    data: dict = Field(default_factory=dict)

class TurnContext(BaseModel):
    command: str = ""
    actor: str = "player"
    events: list[TurnEvent] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
```

HTTP response 仍保持当前：

```json
{
  "state": {},
  "narrative": "string",
  "suggestions": [],
  "source": "rules"
}
```

## Pipeline 约定

每个阶段函数统一签名：

```python
def run_phase(state: dict, context: TurnContext) -> None:
    ...
```

阶段函数只允许：

- 读取 `catalog.json` 生成的 catalog。
- 通过 `engine.mutations` 修改状态。
- 向 `context.events` 追加结构化事件。

阶段函数不允许：

- 直接返回 narrative 字符串。
- 直接写 HTTP response。
- 直接调用 Hermes。

## 步骤

1. 新增 `engine/types.py`，定义 `TurnEvent` 和 `TurnContext`。
2. 在 `engine/turn.py` 中新增：
   ```python
   TURN_PHASES = [
       run_start_turn,
       run_player_action,
       run_construction,
       run_economy,
       run_military,
       run_diplomacy,
       run_events,
       run_end_turn,
   ]
   ```
3. 把当前 `local_turn()` 改成：
   - 创建 `TurnContext(command=request.command)`。
   - 依次执行 `TURN_PHASES`。
   - 根据 `context.events` 生成临时 narrative。
4. `run_player_action` 先复用当前关键词解析：
   - 建造命令只创建 construction project。
   - 招募命令先保持直接加兵，后续 Plan 004 改为训练队列。
   - 贸易/外交/税法令先产生结构化 event，后续 Plan 004/005 细化。
5. `run_end_turn` 负责：
   - `state["turn"] += 1`
   - 天气推进
   - `state["changes"]` 收口
6. 保留 `take_turn()` 的 Hermes 调用路径，但 Hermes 如果不返回 narrative，就走统一 pipeline。
7. 删除旧的散装 `settle_economy()` 直接调用路径，改成 pipeline 的 `run_economy` 阶段调用。

## 不要做的事

- 不要在本 plan 实现复杂战斗公式。
- 不要重写前端。
- 不要改变 `/api/game/turn` response shape。
- 不要让阶段函数依赖 FastAPI 的 `HTTPException`；内部错误优先抛 `ValueError`，router 层再转 HTTP。

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

first = client.post("/api/game/turn", json={"command": "在 E4 建造农田"})
assert first.status_code == 200, first.text
data = first.json()
assert data["state"]["turn"] == 2
assert data["source"] == "rules"
assert data["state"]["construction_queue"]

second = client.post("/api/game/turn", json={"command": "巡视领地"})
assert second.status_code == 200, second.text
assert second.json()["state"]["turn"] == 3

print("OK")
PY
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
```

## 完成判定

- `/api/game/turn` 只通过统一 pipeline 推进本地规则。
- 每个阶段至少产生一种 `TurnEvent` 或明确空操作。
- 原有开局、建造、资源变化功能保持可用。
- 验证命令输出 `OK`。
