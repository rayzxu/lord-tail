# Lord Tail

一个由 React 前端、Python 规则引擎与外部 LLM Agent 协作驱动的中世纪领地管理原型。

## 启动

终端一：

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

终端二：

```bash
cd frontend
npm install
npm run dev
```

访问 Vite 显示的地址（默认 `http://localhost:5173`）。开发环境会将 `/api` 自动转发至后端。

## Hermes Agent 接入

Hermes 不在本项目中管理。后端通过一个宽松的 HTTP 适配器连接它；设置下列环境变量即可启用：

```bash
export HERMES_AGENT_URL='https://your-agent.example/turn'
export HERMES_AGENT_TOKEN='optional-token'
```

后端会以 JSON 向该地址发送 `state`、`command` 和 `system_context`。未配置时，内置的确定性规则引擎会提供可玩的本地演示。

### Hermes Runs / SSE 接入

新接入优先使用 Hermes `/v1/runs`。Lord Tail 前端只连接本项目后端，不直接持有 Hermes 地址或 token。

```bash
export HERMES_RUNS_BASE_URL='http://127.0.0.1:8643'
export HERMES_RUNS_API_KEY='lord-tail-local-test'
export HERMES_AGENT_PROFILE='lord-tail-ollama-gemma4-31b'
export HERMES_RUNS_MODEL='deepseek-v4-flash'
export HERMES_APPROVAL_POLICY='auto-approve'
```

如果要使用 Lord Tail 专用 profile 独立运行真实 Hermes gateway，建议使用独立端口，避免占用默认 gateway：

```bash
hermes -p lord-tail-ollama-gemma4-31b gateway run
export HERMES_RUNS_BASE_URL='http://127.0.0.1:8643'
export HERMES_RUNS_API_KEY='lord-tail-local-test'
export HERMES_RUNS_MODEL='deepseek-v4-flash'
```

真实 Hermes profile 专项测试默认跳过。显式运行：

```bash
cd backend
LORD_TAIL_LIVE_HERMES=1 \
HERMES_RUNS_BASE_URL='http://127.0.0.1:8643' \
HERMES_RUNS_API_KEY='lord-tail-local-test' \
HERMES_AGENT_PROFILE='lord-tail-ollama-gemma4-31b' \
PYTHONPATH=. pytest tests/test_live_hermes_profile.py
```

保存真实调用 trace：

```bash
python tools/run_live_trace.py
```

输出会写入 `.reports/live_trace/`，包含：

- 期望调用的 API。
- 实际调用的 API。
- API 调用是否正确。
- 每步输入。
- 每步输出。
- Hermes SSE 事件与最终文本。

后端提供：

- `POST /api/agent/runs`：创建 `story_turn` 或 `describe_*` run。
- `GET /api/agent/runs/{run_id}`：读取本地 run 状态。
- `GET /api/agent/runs/{run_id}/events`：SSE 事件流，支持 `?since_seq=N` 重放。
- `POST /api/agent/runs/{run_id}/approval`：手动审批响应。
- `POST /api/agent/runs/{run_id}/clarify`：提交澄清回答。
- `POST /api/agent/runs/{run_id}/cancel`：取消 run。

MVP 使用内存 run store；后端重启后历史 run 会丢失。SSE 会转发 Hermes 的 `message.delta`、`reasoning.available`、`tool.started/completed`、`approval.*`、`clarify.*`、`run.completed/failed/cancelled`，并额外下发 `state.action_applied/state.action_rejected` 说明状态修改结果。

`story_turn` 的目标路径是：Hermes 在推理/执行过程中通过工具调用 Lord Tail HTTP API 修改状态；最终回答只返回玩家可读故事。结构化 `actions` 仅作为 legacy fallback 保留。`describe_realm / describe_lord / describe_tile / describe_item` 是只读描述模式，后端会拒绝状态 mutation。

### Hermes Agent profile / skill / tool API

本地 Hermes profile 位于：

```text
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b
```

该 profile 使用 `gemma4:31b`，并安装了 `skills/lord-tail-game`。skill 的职责是把 Hermes 固定为三类角色：故事讲述者、只读描述者、受控状态执行者。

给 Hermes 使用的上下文与工具接口：

- `GET /api/agent/context`：读取压缩领地状态、公开 catalog、允许的 action contract 与统一 mutation API 列表。
- `GET /api/agent/describe-context`：读取单个描述目标上下文，支持 `realm/lord/tile/resource/building/unit/diplomacy/army_status/item`。
- `POST /api/agent/events`：追加一条 `recent_events`，只用于记录剧情事件。

状态修改不再另建 Hermes 专用接口；Hermes、前端和调试工具统一使用 `/api/state/*`。这样可以保证所有 mutation 都经过同一组校验、clamp 与副作用处理。

Legacy fallback：Hermes 如果无法调用工具/API，后端仍兼容最终输出中的结构化 actions：

```json
{
  "narrative": "本轮叙事",
  "suggestions": ["在 E4 建造农田"],
  "actions": [
    {
      "type": "resources",
      "payload": {
        "changes": {
          "gold": 10
        }
      }
    },
    {
      "type": "diplomacy",
      "payload": {
        "faction": "金鳞",
        "status": "友善"
      }
    }
  ]
}
```

支持的 action type 与 `/api/state/*` 映射如下：

| action type | 对应接口 | payload |
|---|---|---|
| `resources` | `POST /api/state/resources` | `{ "changes": {...}, "values": {...} }` |
| `population` | `POST /api/state/population` | `{ "delta": 5 }` 或 `{ "value": 120 }` |
| `morale` | `POST /api/state/morale` | `{ "delta": -10 }` 或 `{ "value": 75 }` |
| `army` | `POST /api/state/army` | `{ "unit": "步兵", "delta": 10 }` |
| `diplomacy` | `POST /api/state/diplomacy` | `{ "faction": "金鳞", "status": "友善" }` |
| `buildings` | `POST /api/state/buildings` | `{ "building": "农田", "action": "build", "count": 1, "x": 5, "y": 4 }` |

只返回叙事也合法：

```json
{
  "narrative": "本轮叙事",
  "suggestions": ["..."]
}
```

Hermes、前端管理工具和调试脚本统一使用同一组状态变更接口：

- `GET /api/state`：读取当前游戏状态。
- `POST /api/state/resources`：批量增改资源，body 形如 `{ "changes": { "gold": 50 }, "values": { "food": 400 } }`。
- `POST /api/state/population`：增改人口，body 形如 `{ "delta": 5 }` 或 `{ "value": 120 }`。
- `POST /api/state/morale`：增改民心，body 形如 `{ "delta": -10 }` 或 `{ "value": 75 }`。
- `POST /api/state/army`：增改部队，body 形如 `{ "unit": "步兵", "delta": 10 }` 或 `{ "unit": "infantry", "value": 30 }`。
- `POST /api/state/diplomacy`：增改外交关系，body 形如 `{ "faction": "金鳞", "status": "友善" }`。
- `POST /api/state/buildings`：建立或摧毁建筑，body 形如 `{ "building": "农田", "action": "build", "count": 1, "x": 5, "y": 4 }` 或 `{ "building": "farm", "action": "destroy", "x": 5, "y": 4 }`。

旧的 `/api/hermes/*` 路由仍然保留为兼容别名；新代码应使用 `/api/state/*`。Hermes 返回 `state_patch` 也保留兼容，但这是 legacy 路径：只有没有 `actions` 时才会尝试应用，后续新能力不要继续扩展 `state_patch`。

`POST /api/game/turn` 会返回结构化 `events`，供前端、本地报告和 Hermes 调试使用：

```json
{
  "phase": "events",
  "kind": "food_depleted",
  "message": "粮仓见底，领民的不安开始蔓延。",
  "severity": "critical",
  "data": {
    "resource": "food",
    "amount": 0
  }
}
```

## 规则目录

游戏的数值配置集中在 [backend/app/data/catalog.json](backend/app/data/catalog.json)，[backend/app/catalog.py](backend/app/catalog.py) 只负责读取 JSON 并生成索引：

- `TALENTS`：天赋描述和可结算效果；开局时由后端校验、规范化并写入存档状态。
- `BUILDINGS`：成本、建设轮数、劳力、可建地形、完工后的产出和地图类型。
- `UNITS`：招募成本、维持费、训练时长与前置建筑。
- `resources`、`starting_buildings`、`diplomacy`：初始资源、初始建筑和默认外交状态。

前端通过 `GET /api/talents` 获得可选天赋；工具或管理界面可通过 `GET /api/catalog` 读取完整公开规则目录。建设和征兵均在后端再次校验资源、地形和前置条件，不能由前端篡改结算数值。
