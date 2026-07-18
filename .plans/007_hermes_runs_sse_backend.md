# Plan 007: Hermes Runs SSE Backend Integration

## 目标

把 Lord Tail 后端从当前“调用 Hermes 一次性 HTTP 返回 narrative/actions”的模式，升级为基于 Hermes `/v1/runs` 的长任务接入。

Hermes Agent 在本项目中的角色：

- **故事讲述者**：根据用户命令、领地状态、天赋、事件和历史，推进剧情并输出故事。
- **执行者**：在推理过程中通过受控接口修改领地状态，不能自由写 state。
- **描述者入口的后端支撑**：为 Plan 008 的人物/领地/地图格/item 描述请求提供同一套 runs/SSE 管道。

本 plan 只做后端：创建 run、桥接 SSE、接收 Hermes actions/tool 结果、保持本地规则 fallback。

## 输入

- `/Users/ray/raylab/lord-tail/backend/app/integrations/hermes.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/game.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/mutations.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/engine/types.py`
- `/Users/ray/GD/wam_demo/.plans/05-hermes-runs-codex-style-ui.md`

当前 Hermes profile：

```text
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b
model: gemma4:31b
provider: custom / Ollama OpenAI-compatible endpoint
skills: 当前为空，后续由 Plan 009 设计和安装
```

## 输出文件

```text
/Users/ray/raylab/lord-tail/backend/app/integrations/hermes_runs.py
/Users/ray/raylab/lord-tail/backend/app/api/runs.py
/Users/ray/raylab/lord-tail/backend/app/engine/hermes_context.py
/Users/ray/raylab/lord-tail/backend/app/engine/hermes_actions.py
/Users/ray/raylab/lord-tail/backend/tests/test_hermes_runs_backend.py
```

可选：

```text
/Users/ray/raylab/lord-tail/backend/app/engine/run_store.py
```

如果不引入数据库，先用内存 run store，明确标记为 MVP。

## 后端 API 设计

新增 Lord Tail 后端接口，而不是让前端直接访问 Hermes：

```text
POST /api/agent/runs
GET  /api/agent/runs/{run_id}
GET  /api/agent/runs/{run_id}/events
POST /api/agent/runs/{run_id}/cancel
POST /api/agent/runs/{run_id}/approval
POST /api/agent/runs/{run_id}/clarify
```

### `POST /api/agent/runs`

用途：创建一次 Hermes run。

请求：

```json
{
  "mode": "story_turn",
  "input": "玩家本轮命令",
  "client_context": {
    "selected_tile": { "x": 5, "y": 4 },
    "ui_language": "zh-CN"
  }
}
```

`mode` 取值：

| mode | 说明 | 是否允许修改状态 |
|---|---|---|
| `story_turn` | 推进剧情，讲述并执行用户命令 | 是 |
| `describe_realm` | 描述领地整体 | 否 |
| `describe_lord` | 描述领主/人物 | 否 |
| `describe_tile` | 描述地图格、建筑、事件 | 否 |
| `describe_item` | 描述任意前端可交互 item | 否 |

响应：

```json
{
  "run_id": "lt_run_xxx",
  "hermes_run_id": "run_xxx",
  "status": "started"
}
```

### `GET /api/agent/runs/{run_id}/events`

Lord Tail 后端对前端提供 SSE。

事件格式统一使用 `data: <json>`，不依赖 SSE event name：

```json
{
  "event": "message.delta",
  "run_id": "lt_run_xxx",
  "hermes_run_id": "run_xxx",
  "timestamp": 1720000000.0,
  "delta": "文本增量"
}
```

必须转发或映射 Hermes 事件：

| Hermes event | Lord Tail event | 用途 |
|---|---|---|
| `message.delta` | `message.delta` | 最终故事/描述文本增量 |
| `reasoning.available` | `reasoning.available` | 推理过程，前端 trace 展示 |
| `tool.started` | `tool.started` | skill/tool 调用开始 |
| `tool.completed` | `tool.completed` | skill/tool 调用完成 |
| `approval.request` | `approval.request` | 危险操作审批 |
| `approval.responded` | `approval.responded` | 审批响应 |
| `clarify.request` | `clarify.request` | 需要用户补充 |
| `clarify.responded` | `clarify.responded` | 用户已补充 |
| `run.completed` | `run.completed` | run 结束 |
| `run.failed` | `run.failed` | run 失败 |
| `run.cancelled` | `run.cancelled` | run 取消 |

Lord Tail 后端额外事件：

| event | 说明 |
|---|---|
| `state.action_applied` | Hermes 通过 action/API 修改状态成功 |
| `state.action_rejected` | Hermes action 未通过后端校验 |
| `state.snapshot` | 可选，状态关键摘要更新 |
| `local.fallback_started` | Hermes 不可用，切换本地规则 |
| `local.fallback_completed` | 本地规则完成 |

## Hermes `/v1/runs` 请求体

`hermes_runs.py` 负责调用 Hermes：

```text
POST {HERMES_RUNS_BASE_URL}/v1/runs
GET  {HERMES_RUNS_BASE_URL}/v1/runs/{hermes_run_id}
GET  {HERMES_RUNS_BASE_URL}/v1/runs/{hermes_run_id}/events
POST {HERMES_RUNS_BASE_URL}/v1/runs/{hermes_run_id}/approval
```

环境变量：

```bash
HERMES_RUNS_BASE_URL=http://127.0.0.1:8642
HERMES_RUNS_API_KEY=optional
HERMES_AGENT_PROFILE=lord-tail-ollama-gemma4-31b
HERMES_RUNS_TIMEOUT_SECONDS=1800
HERMES_APPROVAL_POLICY=auto-deny
```

创建 run 的 payload：

```json
{
  "input": "玩家命令或描述请求",
  "session_id": "lord-tail:<realm_id_or_memory_key>",
  "model": "gemma4:31b",
  "instructions": "...由 engine/hermes_context.py 生成...",
  "conversation_history": [],
  "metadata": {
    "app": "lord-tail",
    "mode": "story_turn",
    "profile": "lord-tail-ollama-gemma4-31b"
  }
}
```

如果 Hermes runs API 不支持 `metadata`，后端内部存储即可，不强依赖。

## Hermes context 设计

新增 `engine/hermes_context.py`：

- `build_story_turn_context(state, command) -> str`
- `build_description_context(state, request) -> str`
- `compact_state_for_agent(state) -> dict`
- `public_action_contract() -> dict`

传给 Hermes 的上下文必须包含：

```json
{
  "realm": {
    "name": "...",
    "turn": 3,
    "season": "春季",
    "weather": "细雨"
  },
  "lord": {
    "name": "...",
    "gender": "...",
    "appearance": "...",
    "personality": "...",
    "talents": []
  },
  "resources": {},
  "changes": {},
  "buildings": {},
  "army": {},
  "army_status": {},
  "diplomacy": {},
  "demographics": {},
  "map": {
    "selected_tile": {},
    "visible_tiles": []
  },
  "recent_events": [],
  "allowed_actions": {}
}
```

要求：

- 不要把完整大对象无脑塞给 Hermes；先做 compact。
- `describe_*` 模式必须明确写入：禁止修改状态，只能输出描述。
- `story_turn` 模式允许执行，但只能通过 Plan 009 的 Lord Tail API skill 或结构化 actions。

## 状态变更路径

保留 Plan 006 的 `actions` 兼容，但本 plan 要把它收敛成统一 helper。

新增 `engine/hermes_actions.py`：

- `apply_hermes_action(state, action) -> AppliedAction`
- `apply_hermes_actions(state, actions) -> list[AppliedAction]`
- `action_event(applied_action) -> TurnEvent-like dict`

支持 action type：

```text
resources
population
morale
army
diplomacy
buildings
turn_event
```

`turn_event` 只允许追加结构化事件，不允许直接改资源：

```json
{
  "type": "turn_event",
  "payload": {
    "phase": "events",
    "kind": "merchant_arrived",
    "severity": "info",
    "message": "一支商队抵达边境。",
    "data": {
      "scene": "caravan"
    }
  }
}
```

## Run store

MVP 可以用内存：

```python
RUNS = {
  "lt_run_xxx": {
    "hermes_run_id": "run_xxx",
    "mode": "story_turn",
    "status": "running",
    "events": [],
    "final_text": "",
    "created_at": 0,
    "updated_at": 0
  }
}
```

要求：

- `GET /events` 新连接时可以从已缓存事件重放，再接上 Hermes SSE。
- 每个事件要有递增 `seq`。
- 断线恢复使用 `?since_seq=N`。
- 当前无数据库时，重启丢失 run 是可接受的，但 README 必须说明。

## Approval 策略

MVP 使用：

```bash
HERMES_APPROVAL_POLICY=auto-deny
```

行为：

- 转发 `approval.request` 给前端。
- 后端立即向 Hermes POST `{"choice": "deny"}`。
- 再转发 `approval.responded`。

后续如果前端做 approval UI，再切换到：

```bash
HERMES_APPROVAL_POLICY=manual
```

## 不要做的事

- 不要让前端直接持有 Hermes API key。
- 不要让 Hermes 自由返回 `state_patch` 作为主路径。
- 不要把 Hermes reasoning 当成最终故事保存。
- 不要让描述模式修改状态。
- 不要一次性把完整地图和全部历史无限传给 Hermes。

## 步骤

1. 新增 `integrations/hermes_runs.py`：
   - create run
   - get run
   - stream events
   - send approval/clarify/cancel
2. 新增 `engine/hermes_context.py`，生成 story/description 两类 instructions。
3. 新增或迁移 `engine/hermes_actions.py`，统一 Plan 006 的 structured action 逻辑。
4. 新增 `api/runs.py`，提供 `/api/agent/runs*`。
5. `main.py` include 新 router。
6. 在 `game.py` 保留 `/api/game/turn` 非流式兼容：
   - 未启用 Hermes runs 时继续走本地规则。
   - 启用 Hermes runs 时可以返回 `run_id` 或继续 fallback 到一次性路径；不要破坏前端旧流程。
7. README 增加 Hermes runs 配置说明。
8. 新增 pytest：
   - mock Hermes `/v1/runs` 创建成功。
   - mock SSE `message.delta/run.completed`。
   - mock `approval.request` 自动 deny。
   - `describe_*` 模式不会调用状态 mutation。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_hermes_runs_backend.py
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

手工验证：

```bash
curl -N http://127.0.0.1:8000/api/agent/runs/<run_id>/events
```

必须能看到：

```text
data: {"event":"message.delta",...}
data: {"event":"run.completed",...}
```

## 完成判定

- 后端可以创建 Hermes run 并桥接 SSE。
- 前端无需直接访问 Hermes。
- `story_turn` 能通过 events 得到最终故事文本。
- `describe_*` 模式只输出描述，不修改状态。
- Hermes actions 仍走统一 mutation 校验。

