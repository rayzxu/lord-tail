# Plan 009: Hermes Profile, Lord Tail Skills, Tools, and API Contract

## 目标

为 Lord Tail 专用 Hermes Agent profile 设计并落地 skills、tools 和后端暴露 API。

Hermes Agent 角色：

- **故事讲述者**：生成日常、商队、外交、军事、领主事件等场景叙事。
- **执行者**：根据用户命令推进剧情，并通过受控 API 修改资源、人口、民心、部队、外交、建筑和事件。
- **描述者**：描述人物、领地、单个地图格、建筑、前端 item，不改变状态。

当前 profile：

```text
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b
model: gemma4:31b
provider: custom / http://127.0.0.1:11434/v1
skills: 0
```

本 plan 定义这个 profile 最终应该具备的能力。

## 输入

- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/config.yaml`
- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/SOUL.md`
- `/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/`
- `/Users/ray/raylab/lord-tail/backend/app/api/state.py`
- `/Users/ray/raylab/lord-tail/backend/app/api/runs.py`（Plan 007）
- `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json`
- `/Users/ray/raylab/lord-tail/README.md`

## 输出文件

Hermes profile：

```text
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/SOUL.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/config.yaml
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/SKILL.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/api_contract.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/story_modes.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/action_schema.md
```

后端：

```text
/Users/ray/raylab/lord-tail/backend/app/api/agent_tools.py
/Users/ray/raylab/lord-tail/backend/tests/test_agent_tools_api.py
```

如果 Hermes 当前没有可直接调用 REST 的工具，优先做 MCP/HTTP bridge：

```text
/Users/ray/raylab/lord-tail/tools/lord_tail_mcp_server.py
```

## Profile tool 策略

推荐分两层：

### MVP：结构化 actions

Hermes 不直接调用工具修改状态，而是在 run 输出或中间事件中返回：

```json
{
  "actions": [
    {
      "type": "resources",
      "payload": {
        "changes": {
          "gold": 10
        }
      }
    }
  ]
}
```

后端通过 Plan 007/006 的 mutation helper 校验并应用。

优点：

- 不依赖 Hermes 本地工具调用能力。
- 安全、可测、容易回滚。

缺点：

- Hermes 推理过程中无法多步查询/修改，只能由后端在最终或阶段性 action 里应用。

### 标准版：Lord Tail API tool / MCP

Hermes profile 启用专用工具，让 Agent 在推理过程中调用：

```text
lord_tail_get_state
lord_tail_get_catalog
lord_tail_change_resources
lord_tail_change_population
lord_tail_change_morale
lord_tail_change_army
lord_tail_change_diplomacy
lord_tail_building_action
lord_tail_add_event
lord_tail_describe_context
```

这些工具内部调用后端 REST：

```text
GET  /api/state
GET  /api/catalog
POST /api/state/resources
POST /api/state/population
POST /api/state/morale
POST /api/state/army
POST /api/state/diplomacy
POST /api/state/buildings
POST /api/agent/events
GET  /api/agent/describe-context
```

实现路线二选一：

1. **MCP server**：`tools/lord_tail_mcp_server.py` 暴露 typed tools，Hermes profile `mcp_servers` 注册。
2. **Hermes skill + terminal/http tool**：skill 指导 Agent 用 HTTP 调用后端；需要 profile 启用对应 toolset。

推荐：MCP server。理由：schema 清晰、权限边界清晰、比让 Agent 自己 curl 更可控。

## 后端暴露 API

已有 `/api/state/*` 保留，新增 Agent 专用读接口和事件接口。

### `GET /api/agent/context`

返回给 Hermes 的 compact state：

```json
{
  "mode": "story_turn",
  "state": {
    "realm": {},
    "lord": {},
    "resources": {},
    "demographics": {},
    "buildings": {},
    "army": {},
    "diplomacy": {},
    "map_summary": {},
    "recent_events": []
  },
  "catalog_summary": {
    "resources": {},
    "buildings": {},
    "units": {}
  }
}
```

### `GET /api/agent/describe-context`

Query：

```text
?target_type=tile&x=5&y=4
?target_type=resource&key=food
?target_type=building&name=农田
?target_type=lord
?target_type=realm
```

返回：

```json
{
  "target_type": "tile",
  "target": {},
  "surrounding_state": {},
  "description_rules": {
    "allow_state_mutation": false,
    "style": "medieval grounded descriptive Chinese"
  }
}
```

### `POST /api/agent/events`

允许 Hermes 追加结构化剧情事件，但不直接改资源：

```json
{
  "phase": "events",
  "kind": "merchant_arrived",
  "severity": "info",
  "message": "一支来自南方的商队抵达。",
  "data": {
    "scene": "caravan",
    "participants": ["商队首领", "领主"]
  }
}
```

后端校验：

- `phase/kind/message/severity/data` 必填或有默认值。
- `severity` 只能是 `info/warning/critical`。
- 不允许 event payload 携带任意 `state_patch`。

### 状态变更接口

继续使用：

```text
POST /api/state/resources
POST /api/state/population
POST /api/state/morale
POST /api/state/army
POST /api/state/diplomacy
POST /api/state/buildings
```

要求：

- 所有接口必须返回统一 `TurnResult` 或 mutation result。
- 人口变更必须同步 demographics。
- 建筑变更必须刷新 housing。
- 外交变更必须保持 object 格式。

## Skill 设计

新增 skill：

```text
lord-tail-game
```

`SKILL.md` 内容结构：

```markdown
---
name: lord-tail-game
description: Lord Tail medieval domain-management game storyteller, describer, and executor.
---

# Role

You are the Lord Tail Hermes Agent.

You have three modes:

1. Storyteller
2. Executor
3. Describer

# Rules

- Never invent hidden state.
- Never mutate state in description mode.
- Mutate state only through Lord Tail tools/actions.
- Always emit player-facing Chinese prose.
- Use structured events for important scene outcomes.

# When to use tools

...
```

引用文件：

| 文件 | 内容 |
|---|---|
| `references/api_contract.md` | 后端 API、请求/响应 schema |
| `references/story_modes.md` | 日常、商队、外交、军事、领主事件的叙事规则 |
| `references/action_schema.md` | actions/tool payload schema |

## 场景模式

Hermes story output 必须标注或内部遵循 scene：

| scene | 说明 | 可用操作 |
|---|---|---|
| `daily` | 日常领地运营、民生、农事、市场 | 资源、民心、事件 |
| `caravan` | 商队、交易、外来商品、谣言 | 资源、外交、事件 |
| `diplomacy` | 使者、邻邦、条约、威胁 | 外交、事件 |
| `military` | 征兵、训练、巡逻、战斗前后 | 部队、组织度、事件 |
| `lord_event` | 领主个人事件、贵族、家庭、誓言 | 民心、统治力、事件 |

Skill 要求：

- 每个 story turn 至少输出一个可读故事段落。
- 如果执行了状态变更，要在故事里自然体现原因。
- 如果拒绝执行，要说明原因，例如资源不足、API 校验失败。
- 不要把工具调用 JSON 直接展示给玩家。

## Agent profile 配置

`config.yaml` 推荐：

```yaml
model:
  provider: custom
  default: gemma4:31b
  base_url: http://127.0.0.1:11434/v1
  api_key: ollama-local
  api_mode: chat_completions
  context_length: 64000

toolsets:
  - mcp

mcp_servers:
  lord-tail:
    command: /Users/ray/raylab/lord-tail/backend/.venv/bin/python
    args:
      - /Users/ray/raylab/lord-tail/tools/lord_tail_mcp_server.py
    env:
      LORD_TAIL_API_BASE: http://127.0.0.1:8000/api
```

如果 MCP 不可用，临时使用：

```yaml
toolsets:
  - terminal
```

并在 skill 中明确只允许调用：

```bash
curl http://127.0.0.1:8000/api/...
```

但这只是 fallback，不作为长期方案。

## 安全和边界

- Agent 不允许直接读写 `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json` 来改规则。
- Agent 不允许直接编辑存档文件。
- Agent 不允许调用 shell 修改项目代码，除非用户明确要求开发任务。
- 游戏运行中的状态变更必须走 API。
- 描述模式不能调用 mutation API。
- 所有 mutation API 必须可被后端测试覆盖。

## 不要做的事

- 不要把所有 Hermes 全局 skills 同步到这个 profile；这个 profile 应保持专用。
- 不要给 Agent 开浏览器、邮件、日历等无关工具。
- 不要让 Agent 使用未记录的 API。
- 不要让故事文本本身隐式改变状态。
- 不要让 Agent 生成与 catalog 冲突的建筑/兵种/资源 id。

## 步骤

1. 在 profile 下创建 `skills/lord-tail-game/`。
2. 写 `SKILL.md` 和 3 个 references。
3. 新增 `api/agent_tools.py`：
   - context
   - describe-context
   - event append
4. 如果选择 MCP：
   - 新增 `tools/lord_tail_mcp_server.py`
   - 给每个工具写 JSON schema。
   - profile `config.yaml` 注册 mcp server。
5. 更新 profile `SOUL.md`：
   - 指向 Lord Tail skill。
   - 说明三种角色和禁止事项。
6. 更新 README：
   - 如何启动 profile。
   - 如何配置 `LORD_TAIL_API_BASE`。
   - 如何测试 tool 调用。
7. 新增 pytest：
   - agent context API。
   - describe-context API 不修改状态。
   - append event API。
   - MCP server schema smoke test（如果实现 MCP）。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_agent_tools_api.py
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
```

Hermes profile 验证：

```bash
hermes profile show lord-tail-ollama-gemma4-31b
find /Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills -name SKILL.md
```

MCP 验证：

```bash
LORD_TAIL_API_BASE=http://127.0.0.1:8000/api \
/Users/ray/raylab/lord-tail/backend/.venv/bin/python \
/Users/ray/raylab/lord-tail/tools/lord_tail_mcp_server.py --self-test
```

## 完成判定

- profile 仍使用 `gemma4:31b`。
- profile 只包含 Lord Tail 相关 skill。
- Hermes 可以读取领地上下文。
- Hermes 可以通过受控 API/MCP 修改状态。
- 描述模式不会修改状态。
- README 写清楚 profile、tools、skills、API 的使用方式。

