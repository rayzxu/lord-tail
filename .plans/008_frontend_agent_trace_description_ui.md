# Plan 008: Frontend Agent Trace, Story Turn, and Description UI

## 目标

前端接入 Plan 007 的 `/api/agent/runs` + SSE，把用户与 Hermes Agent 的交互做成“故事推进 + 执行过程可观察 + 可交互描述”的 UI。

Hermes Agent 在前端表现为三种角色：

1. **故事讲述者**：主输入框发起 `story_turn`，输出本轮故事。
2. **执行者**：运行中展示工具/skill/API 调用过程，完成后折叠。
3. **描述者**：用户点击人物、领地、地图格、建筑、资源、军队、外交等 item 时，可请求 Hermes 生成描述。

## 输入

- `/Users/ray/raylab/lord-tail/frontend/src/App.tsx`
- `/Users/ray/raylab/lord-tail/frontend/src/api.ts`
- `/Users/ray/raylab/lord-tail/frontend/src/styles.css`
- `/Users/ray/raylab/lord-tail/.docs/前端_界面`
- `/Users/ray/GD/wam_demo/.plans/05-hermes-runs-codex-style-ui.md`

依赖：

- Plan 007 提供 `/api/agent/runs` 和 `/api/agent/runs/{run_id}/events`。
- Plan 006 已提供结构化 `events`。

## 输出文件

```text
/Users/ray/raylab/lord-tail/frontend/src/api.ts
/Users/ray/raylab/lord-tail/frontend/src/App.tsx
/Users/ray/raylab/lord-tail/frontend/src/styles.css
```

建议拆分：

```text
/Users/ray/raylab/lord-tail/frontend/src/components/agent-trace/types.ts
/Users/ray/raylab/lord-tail/frontend/src/components/agent-trace/AgentTracePanel.tsx
/Users/ray/raylab/lord-tail/frontend/src/components/agent-trace/AgentReasoningBlock.tsx
/Users/ray/raylab/lord-tail/frontend/src/components/agent-trace/AgentToolRow.tsx
/Users/ray/raylab/lord-tail/frontend/src/components/agent-trace/AgentApprovalRow.tsx
/Users/ray/raylab/lord-tail/frontend/src/components/agent-trace/AgentClarifyRow.tsx
/Users/ray/raylab/lord-tail/frontend/src/components/description/DescriptionDrawer.tsx
```

## 前端类型

新增：

```ts
export type AgentRunMode =
  | 'story_turn'
  | 'describe_realm'
  | 'describe_lord'
  | 'describe_tile'
  | 'describe_item'

export type AgentRunStartRequest = {
  mode: AgentRunMode
  input: string
  client_context?: Record<string, unknown>
}

export type AgentRunStartResponse = {
  run_id: string
  hermes_run_id?: string
  status: string
}

export type AgentTraceEvent =
  | {
      id: string
      kind: 'reasoning'
      text: string
      status: 'running' | 'complete'
      timestamp?: number
    }
  | {
      id: string
      kind: 'tool'
      toolName: string
      title: string
      preview?: string
      status: 'running' | 'complete' | 'error'
      duration?: number
      error?: string | boolean
      timestamp?: number
    }
  | {
      id: string
      kind: 'approval'
      command?: string
      description?: string
      choices?: string[]
      status: 'waiting' | 'responded' | 'denied'
      choice?: string
      timestamp?: number
    }
  | {
      id: string
      kind: 'clarify'
      question: string
      choices?: string[] | null
      status: 'waiting' | 'responded'
      response?: string
      timestamp?: number
    }
  | {
      id: string
      kind: 'state_action'
      title: string
      status: 'complete' | 'error'
      payload?: Record<string, unknown>
      timestamp?: number
    }
```

扩展 `TurnResult`：

```ts
export type TurnResult = {
  state: GameState
  narrative: string
  suggestions: string[]
  source: 'rules' | 'hermes' | 'state-api'
  events?: TurnEvent[]
  run_id?: string
  trace?: AgentTraceEvent[]
}
```

## API 客户端

`api.ts` 新增：

```ts
agent: {
  startRun: (request: AgentRunStartRequest) => Promise<AgentRunStartResponse>
  runStatus: (runId: string) => Promise<AgentRunStatus>
  eventsUrl: (runId: string, sinceSeq?: number) => string
  cancel: (runId: string) => Promise<void>
  approval: (runId: string, choice: string) => Promise<void>
  clarify: (runId: string, response: string) => Promise<void>
}
```

SSE 使用浏览器 `EventSource`。

如果需要 POST body 才能创建 run：

1. `POST /agent/runs` 创建。
2. `new EventSource(api.agent.eventsUrl(run_id))` 监听。

## Story Turn UI

当前游戏主界面左侧已有：

- 本轮报告
- 命令输入框
- suggestions

改造为：

```text
本轮报告
├── AgentTracePanel（运行中展开，完成后默认收起）
└── StoryText（Hermes message.delta 累积文本）

命令输入框
└── 发送后创建 story_turn run
```

状态机：

```ts
type AgentRunUiState =
  | { status: 'idle' }
  | { status: 'starting' }
  | { status: 'running'; runId: string }
  | { status: 'waiting_for_clarify'; runId: string }
  | { status: 'waiting_for_approval'; runId: string }
  | { status: 'completed'; runId: string }
  | { status: 'failed'; runId: string; error: string }
```

SSE 事件处理：

| event | 前端行为 |
|---|---|
| `message.delta` | append 到当前 story text |
| `reasoning.available` | append 到 reasoning block |
| `tool.started` | upsert tool row running |
| `tool.completed` | complete 最近同名 running tool row |
| `approval.request` | 显示 approval row；MVP 如果后端 auto-deny，则只展示 |
| `approval.responded` | 更新 approval row |
| `clarify.request` | 显示 clarify UI；暂停输入 |
| `clarify.responded` | 更新 clarify row |
| `state.action_applied` | 显示状态变更 row，并刷新 state |
| `state.action_rejected` | 显示 warning/error row |
| `run.completed` | 收束文本，trace 默认折叠，刷新 `/api/state` |
| `run.failed` | 显示错误，允许重试 |
| `run.cancelled` | 标记取消 |

## Description UI

新增描述入口：

| 前端 item | mode | client_context |
|---|---|---|
| 领地名字/详情 | `describe_realm` | `{ scope: "realm" }` |
| 领主详情 | `describe_lord` | `{ scope: "lord" }` |
| 地图格 | `describe_tile` | `{ tile: { x, y, kind, label } }` |
| 建筑统计项 | `describe_item` | `{ item_type: "building", name }` |
| 资源 | `describe_item` | `{ item_type: "resource", key, value, delta }` |
| 军事状态 | `describe_item` | `{ item_type: "army_status" }` |
| 外交势力 | `describe_item` | `{ item_type: "diplomacy", faction }` |

UI 形态：

```text
DescriptionDrawer / Modal
├── 标题：正在描述：E4 农田
├── AgentTracePanel（可折叠）
└── 描述正文
```

要求：

- 描述请求不改变回合、不修改 state。
- 描述 drawer 可以并发地与主 story turn 分离，但 MVP 建议同一时间只允许一个 run。
- 地图格点击时显示本地基础信息，再提供“让 Hermes 描述”按钮，避免每次 hover 都触发 run。

## 视觉约束

沿用 `.docs/前端_界面` 的中世纪 UI：

- Trace panel 不要像现代 IDE 大面积白底，应该像书记官边注/羊皮纸边栏。
- tool row 使用小号字体、低对比色，避免盖过故事正文。
- 运行中显示“书记官正在核对/执行”。
- 完成后默认折叠，标题类似：

```text
思考与执行 · 4 步 · 已完成
```

## 不要做的事

- 不要把 reasoning 混进最终故事正文。
- 不要在描述请求里推进 turn。
- 不要让用户看不见状态变更；Hermes 修改资源/外交/建筑时必须有 trace row。
- 不要在每个 UI hover 上自动发起 Hermes run。
- 不要把 approval UI 做成假按钮；MVP 如果后端 auto-deny，就只展示自动拒绝结果。

## 步骤

1. `api.ts` 增加 agent run API、SSE URL helper、类型定义。
2. 新建 `components/agent-trace` 组件。
3. 修改 `GameScreen`：
   - 命令发送优先调用 `/api/agent/runs`。
   - 监听 SSE，流式更新 story text 和 trace。
   - `run.completed` 后刷新 `/api/state`。
   - 如果 `/api/agent/runs` 返回 404/未配置，则 fallback 到旧 `/api/game/turn`。
4. 新增 `DescriptionDrawer`。
5. 给领地、领主、地图格、资源、建筑、外交等 item 加描述入口。
6. 样式写入 `styles.css` 或拆分 CSS。
7. 前端 build 验证。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail/frontend
npm run build
```

手工验证：

1. 启动后端和前端。
2. 发起一次 `story_turn`。
3. SSE 流式期间能看到：
   - trace 展开
   - story text 逐步增长
   - tool/state action 行
4. run 完成后：
   - trace 默认收起
   - state 刷新
   - suggestions 更新或保留 fallback
5. 点击地图格：
   - 本地显示基础信息
   - 点击“描述”后调用 `describe_tile`
   - 不推进 turn，不修改资源

## 完成判定

- 前端可以消费 Plan 007 SSE。
- 故事推进和描述请求走同一套 Agent run UI。
- Trace 和最终故事分离。
- 描述者不会改变游戏状态。

