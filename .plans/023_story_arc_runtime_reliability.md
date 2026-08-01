# Plan 023：剧情图运行时可靠性修复与 StoryArcRun 聚合

## 目标

修复 Plan 021 剧情图运行时 code review 中发现的可靠性缺陷，并在不混淆静态 Definition 与运行实例的前提下，将 schema v2 的重复 `Storylet Instance` 收拢为：

```text
StoryArcDefinition  静态、经过校验的作者定义
StoryArcRun         一次剧情发生的唯一聚合根
NodeVisit           Run 内部节点访问、幂等和 Scene 关联记录
```

本 Plan 的首要目标不是改名或整理目录，而是保证以下场景都不会丢事件、追溯改写存档或重复结算：

1. 计划事件到期时已有其他场景占用。
2. 服务端完成最终选择，但客户端没有收到响应并重试。
3. 进行中的剧情 Definition 被 Admin 更新、归档或重载。
4. Hermes 或直接 API 调用超过自由交互预算。
5. 同时存在等待 timed node 和占用当前 Scene 的多个剧情图。
6. automatic 节点有重要剧情文案，但同步推进后前端没有展示。

优先级：**P0**。

## 执行状态

已完成（2026-08-01）：

- 入口与 timed node 使用 detached transaction，Scene 冲突进入可恢复队列；
- Definition 快照/hash、终局幂等、后端交互预算与严格条件校验已落地；
- focused arc、automatic/terminal transition log 与前端 Markdown 展示已接入；
- schema v2 已切换到 `StoryArcRun + NodeVisit`，保留 schema v1 和 legacy instance API；
- Admin automatic Inspector、作者文档、迁移/可靠性测试与只读 debug 投影已补齐。

## Code Review 结论与处理决策

| 问题 | 当前风险 | 本 Plan 决策 |
|---|---|---|
| 入口事件先标记 `active`，Scene 冲突后永久卡死 | P1 / 丢事件 | 入口激活使用 detached transaction；Scene 被占用时保持 `due + queued_for_scene` |
| `definition_version` 不参与读取 | P1 / 旧存档被新 JSON 追溯修改 | Run 创建时冻结规范化 Definition 快照和 hash；之后只从 Run 读取 |
| 最终选择无法幂等重试 | P1 / 成功被报告为失败 | 在检查 Run 状态前按 `visit_id/legacy_instance_id` 搜索全部 NodeVisit |
| 自由交互预算只由 UI 限制 | 可无限拖延 | API 写消息前硬拒绝；空输入不计数 |
| 条件操作有占位实现，`any` 破坏 AND 语义 | 错误分支或运行时 500 | 缩小白名单、定义严格 schema、确定性优先级 |
| `current_arc()` 按字符串最小 ID 返回 | 前端展示错误剧情 | 引入 `focused_arc_id`，优先 Scene，其次显式 focus，再其次等待 Run |
| automatic 文案被同步吞掉 | 子事件在玩家视角消失 | NodeVisit 记录 narrative，选择响应返回 `transition_log` |
| Chain 与 v2 Storylet Instance 重复 cast/facts | 状态分散、迁移困难 | P1 修复验收后再迁移为 `StoryArcRun + NodeVisit` |

准确边界：

> `StoryArcDefinition` 与 `StoryArcRun` 不能合并。Definition 是静态内容，Run 是存档中的一次发生；Run 可以冻结 Definition 快照，但不能反向成为可编辑 Definition。

## 强制不变量

实现后必须始终满足：

1. 入口 ScheduledEvent 只有在 entry node 成功激活后才能变为 `active`。
2. Scene 被占用不是失败；入口事件保持 `due` 并带 `queued_for_scene=true`。
3. 任意激活异常不得在正式 state 留下半个 Run、半个 NodeVisit、active 事件或已扣资源。
4. Run 一旦创建，后续选择、投影、恢复、automatic、terminal 和 series 调度都使用同一冻结 Definition。
5. 同一个 `visit_id + choice_id` 可以安全重复提交，并返回第一次成功结果。
6. 同一个已完成 visit 改交其他 choice 必须返回明确的 `409 choice_conflict`。
7. 幂等查询发生在 `run.status == completed` 和 `transition_seq` 检查之前。
8. 自由交互预算由后端控制；超过上限时 Scene 消息、计数器、历史和 recent events 均不改变。
9. 一个 Scene 最多聚焦一个 Run；一个 Run 同一时间最多有一个 `awaiting_choice` NodeVisit。
10. NodeVisit 不复制 Run 的完整 cast、cast_snapshots 和 facts。
11. automatic 节点要么显式 `presentation: silent`，要么出现在 `transition_log`；禁止默默丢失作者文案。
12. schema v1 Storylet 在本 Plan 中继续兼容，不被不完整地强制迁移。

## 非目标

本 Plan 不实现：

- 允许剧情图循环或通用 Quest 系统。
- 让 Hermes 选择 transition、生成 choice 或修改当前 node。
- 将静态 Definition 直接存成可变 Run 对象。
- 一次性把所有 schema v1 Storylet 改写为 schema v2。
- 任意脚本语言、表达式、JSON Patch、Python 函数路径或 `eval`。
- 多个阻塞剧情同时占用一个 active Scene。
- 用 prompt 重试掩盖后端事务和幂等问题。

## 目标数据模型

### StoryArcDefinition

正式 JSON 仍由 Content Repository 和 Admin 管理。进入运行时前生成只包含剧情语义的规范化快照：

```json
{
  "schema_version": 2,
  "id": "spring_caravan_visit",
  "version": 2,
  "title": "春季末商队到访",
  "entry_node": "arrival_gate",
  "roles": {},
  "parameters": {},
  "interaction_budget": {},
  "nodes": {},
  "series": {}
}
```

`editor_layout`、Admin metadata 和 `_source_file` 不进入运行快照 hash。

### StoryArcRun

在 `state.storylets.arc_runs` 中保存：

```json
{
  "id": "story_run_31",
  "runtime_version": 3,
  "definition_id": "spring_caravan_visit",
  "definition_version": 2,
  "definition_hash": "sha256:...",
  "definition_snapshot": {},
  "status": "active",
  "entry_scheduled_event_id": "event_12",
  "current_node_id": "trade_hearing",
  "current_visit_id": "visit_3",
  "focused": true,
  "cast": {},
  "cast_snapshots": {},
  "facts": {},
  "seed": 2001,
  "transition_seq": 3,
  "pending_node_event_id": null,
  "node_visits": [],
  "started_time": {},
  "resolved_time": null
}
```

### NodeVisit

```json
{
  "visit_id": "visit_3",
  "node_id": "trade_hearing",
  "node_kind": "choice",
  "status": "awaiting_choice",
  "choice_id": null,
  "scene_id": "scene_17",
  "scheduled_event_id": null,
  "freeform_steps_used": 0,
  "narrative_md": "...",
  "effects_result": null,
  "transition_to": null,
  "transition_seq": 3,
  "activated_time": {},
  "resolved_time": null,
  "legacy_instance_id": "story_event_44"
}
```

`legacy_instance_id` 只用于旧 API、旧前端和旧存档映射，不能继续承载第二份 cast/facts。

## Definition 冻结策略

本 Plan 选择“Run 内冻结快照”，不要求运行时访问 `.content-admin/revisions`：

1. 新 Run 开始前读取当前已发布 Definition。
2. 运行完整 `analyze_graph()` 和 domain validation。
3. 去除 `editor_layout`、`status`、`_source_file` 等非运行字段。
4. 规范化 JSON 并计算 `definition_hash`。
5. 把深拷贝后的 snapshot、version、hash 一次性写入 detached Run。
6. 后续统一调用 `definition_for_run(run)`，禁止再次按 id 读取最新文件。

需要替换 `runtime.py` 中所有以下调用：

```python
get_arc_definition(run["definition_id"])
get_definition(run["definition_id"], node_id)
```

包括但不限于：

- `_instance_for_node` / 后续 NodeVisit factory；
- `_activate_node`；
- `choose_arc_node`；
- `_resolve_terminal` 与 `_schedule_series`；
- `public_arc`、timeline 和 legal choices；
- save/load consistency audit；
- Hermes context 和前端投影。

旧 runtime v2 chain 缺少 snapshot 时，在 save migration 中：

- 用当前可找到的 Definition 冻结一次；
- 标记 `definition_snapshot_origin=migrated_current_definition`；
- 保存 warning，说明历史版本无法从旧存档恢复；
- 此后不再随热重载变化。

Admin 发布 Story Arc 更新时自动递增 `version`，但运行时隔离以 `definition_hash + snapshot` 为准，version 只用于作者审计和诊断。

## 计划事件入口事务

### 状态机

```text
scheduled
  -> due
  -> due + queued_for_scene=true       Scene 被占用
  -> active + story_arc_run_id         entry scene 与 Run 均成功
  -> resolved                          terminal 成功
```

禁止：

```text
due -> active -> start_arc 失败
```

### 激活服务

新增统一结果类型：

```python
ArcActivationResult(
    status="activated" | "queued" | "idempotent" | "ignored",
    run_id=None,
    event_id="...",
    reason=None,
)
```

实现 `try_activate_arc_entry(state, event_id, seed)`：

1. 验证事件仍为 `due`，或已经 queued。
2. 若已有相同 `entry_scheduled_event_id` 的 Run，返回 idempotent，并修复事件引用。
3. 若 `active_scene` 非空，在 detached state 中写入：
   - `status=due`；
   - `flags.queued_for_scene=true`；
   - `flags.activation_state=queued`；
   - 不创建 Run/NodeVisit；
   - 提交 queue 标记后返回。
4. Scene 空闲时，从原 state 创建完整 deepcopy。
5. 在 detached state 内冻结 Definition、创建 Run、创建 entry NodeVisit，并按节点类型开启 Scene、安排 timed event 或执行 automatic 链。
6. 所有步骤成功后才把 entry event 改为 `active` 并写入 `story_arc_run_id`。
7. 最后一次性 `state.clear(); state.update(detached)`。
8. 任意异常直接丢弃 detached state。

`activate_due_events()` 不再预先把 authored arc entry 改为 active。

`activate_queued_nodes()` 必须同时处理：

- `story_arc_node` timed event：现有 queued node；
- 普通入口事件：`story_arc_definition_id` 存在、status 为 due、`queued_for_scene=true`。

Scene 结束后只激活一条最高优先级、最早 due 的 queued event；其余保持 queued，防止同一时刻抢占 Scene。

单个 timed node 激活也改为 detached transaction，避免 event active 但 Scene/Visit 未激活。

## 选择幂等与并发顺序

选择入口调整为：

```python
visit = find_visit_by_public_id(run, visit_or_legacy_instance_id)

if visit and visit.status == "completed":
    if visit.choice_id == choice_id:
        return replay_idempotent_success(run, visit)
    raise HTTPException(409, "choice_conflict")

if run.status == "completed":
    raise HTTPException(409, "arc_already_resolved")

check_current_visit()
check_expected_transition_seq()
execute_detached_transaction()
```

幂等成功响应至少包含：

```json
{
  "idempotent": true,
  "run_id": "story_run_31",
  "visit_id": "visit_3",
  "choice_id": "approve_trade",
  "transition": {"from": "trade_hearing", "to": "market_day"},
  "terminal": true,
  "events": [],
  "result": {}
}
```

第一次成功时把足以重放的 outcome 摘要保存在 NodeVisit；幂等重试不得重新执行 effects、追加历史、安排下次商队或递增 transition sequence。

## 后端自由交互预算

`POST /api/game/scenes/current/step` 对 Story Arc Scene 的处理顺序改为：

1. 对 `input` 与 `narrative` 做 trim。
2. 两者都为空且没有 events 时返回 `422 empty_scene_step`。
3. 从 focused Run 当前 NodeVisit 读取 `used/maximum`。
4. `used >= maximum` 时，在任何 mutation 前返回 `409 interaction_budget_exhausted`。
5. 成功写入 Scene message 后才递增一次计数。
6. 同一请求同时含 input 与 narrative 仍只消耗一个 step。
7. 结构化 choice API 不消耗自由交互预算，也不受预算耗尽阻止。

Hermes、玩家前端和直接 HTTP 调用必须经过同一检查，不能保留绕过接口。

前端继续禁用 textarea，但 UI 只作为提示，不能作为安全边界。

## 条件系统收敛

### 第一版正式支持

```text
fact_equals            object<string, scalar>
fact_gte               object<string, number>
fact_lte               object<string, number>
choice_was             string
resource_minimum       object<resource_id, number>
season_any             non-empty array<string>
any                    non-empty array<condition object>
```

暂时从 `CONDITION_OPS`、Admin schema 和作者指南移除：

```text
relationship_minimum
character_trait_minimum
```

以后只有在真实接入 relationship service 和 character component 查询后才能重新开放，禁止保留“永远 False”或偷读 `merchant_attitude` 的占位实现。

### 组合语义

- 同一 condition object 的不同 key 是 AND。
- `any` 只负责其内部 OR，不得提前 return 并忽略同级条件。
- 空 condition 只允许作为 automatic 唯一 fallback。
- 所有数值必须是有限数，禁止 bool、NaN 和 Infinity 冒充 number。

### 多条 automatic 条件同时满足

静态校验无法对任意世界状态证明条件互斥，因此改为显式优先级：

```json
{"to": "high_trust", "priority": 100, "when": {"fact_gte": {"trust": 80}}}
```

规则：

1. conditional transition 必须提供唯一整数 priority。
2. fallback 不允许 priority，且必须恰好一条。
3. 静态校验拒绝重复 priority 和完全相同的 condition。
4. 运行时在所有匹配项中选择 priority 最大者；不再因多条满足返回 500。
5. Admin 图编辑器需要展示和编辑 automatic edge priority/condition。

### Effect 校验

`schedule_followup` 和 `transition_to` 必须在 schema v2 的所有 effect 位置被拒绝：

- choice.effects；
- automatic.effects；
- timed.effects；
- terminal.effects。

effect 数组本身、每个 effect object 和必填参数都必须进行 domain validation，不能只验证 `op` 名称。

## focused arc 与多 Run 投影

新增：

```python
focused_arc_id(state) -> str | None
list_active_arcs(state) -> list[public run]
```

聚焦顺序：

1. `active_scene.flags.story_arc_run_id` / 兼容 `story_arc_chain_id`；
2. `state.storylets.focused_arc_id`；
3. `state.storylets.current_instance_id` 映射的 Run；
4. 已到期并 queued 的 Run；
5. 其他 active Run，按 due_time、started_time、id 排序。

API：

```text
GET /api/story-arcs/current
  -> {focused_arc_id, arc, active_arcs}

GET /api/story-arcs/{run_id}
  -> 单个 Run 的权威投影
```

保留响应中的 `chain` 和 `current_instance` 兼容字段一个迁移周期，但新增正式字段：

```text
run
current_visit
focused_arc_id
transition_log
```

前端不能再假设“字符串最小 chain id 就是当前剧情”。

## automatic 节点文案与 transition log

schema v2 automatic 节点增加：

```json
"presentation": "transition_log" | "silent"
```

默认值为 `transition_log`。`silent` 必须由作者显式设置，只适合纯规则路由节点。

每次 automatic/terminal 访问写入 NodeVisit，并向本次选择响应追加：

```json
{
  "visit_id": "visit_4",
  "node_id": "market_day",
  "kind": "automatic",
  "title": "开市",
  "narrative_md": "...",
  "effects_summary": "金币 +30，民心 +1",
  "transition_to": "visit_resolved",
  "activated_time": {}
}
```

前端事件弹窗/本轮报告按顺序渲染 `transition_log`，确保：

```text
抵达 -> 登记 -> 贸易听证 -> 开市 -> 离境
```

不会在玩家视角退化为“抵达 -> 听证 -> 离境”。

Hermes context 可以读取 transition log 作为已经发生的事实，但不能修改或重放其中 effects。

## StoryArcRun 聚合迁移

此阶段必须在三个 P1 和预算测试全部通过后开始。

### 存储迁移

`normalize_storylet_state()` 增加版本迁移：

```text
runtime v2 chain + schema v2 StoryEventInstances
  -> runtime v3 StoryArcRun + NodeVisits
```

迁移规则：

- chain 的 cast、cast_snapshots、facts、entry event、sequence 移到 Run；
- 每个属于 v2 chain 的 instance 转换为 NodeVisit；
- `instance.id` 保存为 `legacy_instance_id`；
- `selected_choice_id/result/scene_id/time` 移入对应 visit；
- v2 instances 从顶层 active instance 集合移除，或标记 `migrated_to_visit_id` 后不再参与查询；
- schema v1 instance 完全保留；
- migration 必须幂等，多次 normalize 不重复生成 visit；
- 保存后使用新的 `save_schema_version`。

### Effect 执行上下文

当前 `execute_effects()` 依赖完整 StoryEventInstance。新增不持久化的执行上下文：

```python
StoryExecutionContext(
    execution_id=visit_id,
    definition_id=run.definition_id,
    node_id=visit.node_id,
    cast=run.cast,
    cast_snapshots=run.cast_snapshots,
    facts=run.facts,
    scheduled_event_id=run.entry_scheduled_event_id,
)
```

effects 读取 Run facts，并把 `set_arc_fact/increment_arc_fact` 写回 detached Run；不能为了兼容 executor 再持久化一份 instance cast/facts。

### API 兼容

以下旧入口暂时保留：

```text
POST /api/storylets/{legacy_instance_id}/choose
GET  /api/storylets/{legacy_instance_id}
```

内部先映射到 NodeVisit。新增正式入口：

```text
POST /api/story-arcs/{run_id}/visits/{visit_id}/choose
GET  /api/story-arcs/{run_id}
```

两条选择入口调用同一个 application service 和同一个幂等键逻辑，禁止复制结算代码。

## 实施阶段

### 阶段 0：先补失败用例

先新增失败测试，确认修复前能稳定复现：

1. Scene 占用时春季商队入口变 active 后永久不再触发。
2. 最终 choice 成功后相同请求重试得到 409。
3. Run 中途替换 Definition 后路线/effect 被追溯修改。
4. 第三个自由交互仍被接受。
5. timed 等待 Run 抢占 `current_arc()`。
6. registration/market_day narrative 不出现在响应或报告。

### 阶段 1：P1 入口事务

1. 把入口激活从 `activate_due_events()` 的预先 active mutation 中拆出。
2. 实现 `try_activate_arc_entry()` detached transaction。
3. 扩展 `activate_queued_nodes()` 处理 queued entry。
4. timed node 激活改为同样的事务边界。
5. 增加 failure injection，验证任何异常下正式 state 字节级不变，queue 标记场景除外。

### 阶段 2：P1 Definition 冻结

1. 增加 Definition canonicalizer/hash。
2. Run 创建时保存 snapshot/version/hash。
3. 增加 `definition_for_run()` 并替换所有动态 lookup。
4. 加入旧 v2 chain snapshot migration。
5. Admin 发布 Story Arc 时自动递增 version。

### 阶段 3：P1 幂等与预算

1. 调整 choose 检查顺序并保存 replay outcome。
2. 最终 terminal 后仍可按原 visit 幂等返回。
3. 不同 choice 返回 `choice_conflict`。
4. scene step 在 mutation 前执行预算和空输入检查。
5. 更新前端错误提示和测试，不再把 used=3/maximum=2 视为成功。

### 阶段 4：条件、聚焦与文案

1. 收缩 CONDITION_OPS 并实现严格 schema。
2. 修正 `any` 与同级条件 AND 语义。
3. automatic transition 使用 priority 确定性决策。
4. 全位置拒绝 schema v2 followup/transition effects。
5. 引入 focused arc 投影。
6. 增加 transition log 并在前端依次渲染 automatic 文案。

### 阶段 5：StoryArcRun + NodeVisit

1. 新增 runtime v3 模型和 factory。
2. 把新 Run 切换到 v3，不再创建顶层 v2 instance。
3. 重构 effects execution context。
4. 增加 v2 save migration 和旧 API adapter。
5. 全部专项测试通过后，删除 runtime.py 中只服务 v2 instance duplication 的私有路径。

### 阶段 6：文档、Admin 与观测

1. 更新作者指南的条件白名单、priority 和 presentation。
2. Admin graph validator 使用同一后端 schema，不维护第二份规则。
3. Admin automatic edge Inspector 增加 condition/priority。
4. 状态审计输出 Run、Visit、Scene、ScheduledEvent 对应关系。
5. 增加 structured logs 和 debug endpoint。

## 文件修改范围

主要后端：

```text
backend/app/storylets/runtime.py
backend/app/storylets/graph.py
backend/app/storylets/config.py
backend/app/storylets/service.py
backend/app/storylets/instances.py
backend/app/storylets/effects.py
backend/app/storylets/runs.py                 # 新增
backend/app/storylets/migrations.py           # 新增或并入 state migration
backend/app/systems/scheduled_events.py
backend/app/engine/scenes.py
backend/app/engine/state.py
backend/app/api/game.py
backend/app/api/storylets.py
backend/app/api/schemas.py
```

内容与 Admin：

```text
backend/app/data/storylets/spring_caravan_visit.json
backend/app/content/validation.py
admin/src/editors/StoryArcEditor.tsx
admin/src/api.ts
```

玩家前端：

```text
frontend/src/api.ts
frontend/src/App.tsx
frontend/src/styles.css
```

文档：

```text
.docs/预编剧情图事件手工维护指南.md
.docs/Storylet事件手工维护与扩展.md
.docs/Admin内容管理后台使用与扩展.md
```

测试：

```text
backend/tests/test_story_arc_activation_transaction.py
backend/tests/test_story_arc_definition_snapshot.py
backend/tests/test_story_arc_idempotency.py
backend/tests/test_story_arc_interaction_budget.py
backend/tests/test_story_arc_conditions.py
backend/tests/test_story_arc_focus.py
backend/tests/test_story_arc_transition_log.py
backend/tests/test_story_arc_run_migration.py
backend/tests/test_story_arc_runtime.py
backend/tests/test_spring_caravan_arc.py
admin/e2e/content-management.spec.ts
```

## 专项测试

### 入口与事务

- active Scene 存在时，入口事件保持 due、queued，不创建 Run。
- Scene 结束后自动激活最早 queued entry。
- entry Scene 创建失败时不留下 active event、Run、Visit 或资源变化。
- 同一 occurrence 重复激活只产生一个 Run。
- 两条同时到期的阻塞剧情只启动一条，另一条继续 queued。
- queued timed node 和 queued entry 都能在 Scene 释放后按顺序继续。

### Definition 冻结

- Run 启动后替换 choice effect，旧 Run 仍执行快照中的 effect。
- Run 启动后替换 transition，旧 Run 仍沿原路线。
- Run 启动后删除当前 node，旧 Run 仍可完成。
- 保存、重启、热重载后 hash 和 snapshot 不变。
- 新 Run 使用新版本，新旧 Run 可同时存在。
- `editor_layout` 改动不改变运行 Definition hash。

### 选择幂等

- 中间节点相同 choice 重试返回 idempotent。
- choice 自动经过多个 automatic node 到 terminal 后，相同请求仍返回 idempotent。
- 重试不重复资源、历史、关系、series event 或 transition_seq。
- 同 visit 改交另一个 choice 返回 `409 choice_conflict`。
- 过期 visit 且无成功记录返回 `409 node_not_current`。

### 自由交互预算

- maximum=2 时前两次成功，第三次返回 409。
- 第三次失败后 used 仍为 2，Scene 消息和 recent events 数量不变。
- 空 input/narrative 返回 422 且不消耗预算。
- 同一 step 同时写 input 和 narrative 只消耗一次。
- 预算用尽后合法 choice 仍可提交。

### 条件与校验

- 每种正式条件有 shape、类型和边界测试。
- `any` 与同级条件按 AND 组合。
- unsupported character/relationship 条件在发布前失败。
- automatic priority 重复或 condition 完全重复时静态失败。
- 多条条件同时满足时稳定选择最高 priority，不返回 500。
- automatic/terminal node effects 中的 `schedule_followup` 静态失败。

### 聚焦与文案

- active Scene 所属 Run 始终是 focused arc。
- 旧 timed Run 不会遮住当前 Scene Run。
- Scene 结束后 focus 移交下一 queued Run。
- registration 和 market_day 出现在 transition_log 且顺序正确。
- `presentation=silent` 节点不显示 narrative，但仍保留最小审计 visit。

### Run 迁移

- v2 chain/instances 能无损迁移为一个 v3 Run 和多个 NodeVisit。
- 迁移不重复，二次 normalize 结果相同。
- schema v1 instances 不受影响。
- legacy instance choose API 与新 visit API 返回相同结果。
- NodeVisit 中不存在 cast、cast_snapshots 和 facts 的重复副本。
- 旧存档加载后人物、事件、Scene、资源和下一次商队日期保持一致。

## 可观测性

`audit_arc_consistency()` 扩展检查：

```text
entry_event_missing
entry_event_active_without_run
queued_entry_has_run
run_definition_hash_mismatch
current_visit_missing
multiple_awaiting_visits
scene_run_mismatch
scene_visit_mismatch
completed_run_has_current_visit
completed_entry_event_not_resolved
duplicate_visit_id
duplicate_series_occurrence
```

Debug 投影必须只读，输出：

```text
focused_arc_id
active run ids
queued entry/timed event ids
current visit id
definition id/version/hash
transition_seq
consistency errors
```

日志中不写完整 Definition snapshot、人物秘密或 Hermes/API 凭证。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail

PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend tools
PYTHONPATH=backend backend/.venv/bin/python tools/validate_content_registry.py

PYTHONPATH=backend backend/.venv/bin/pytest -q \
  backend/tests/test_story_arc_activation_transaction.py \
  backend/tests/test_story_arc_definition_snapshot.py \
  backend/tests/test_story_arc_idempotency.py \
  backend/tests/test_story_arc_interaction_budget.py \
  backend/tests/test_story_arc_conditions.py \
  backend/tests/test_story_arc_focus.py \
  backend/tests/test_story_arc_transition_log.py \
  backend/tests/test_story_arc_run_migration.py \
  backend/tests/test_story_arc_graph.py \
  backend/tests/test_story_arc_runtime.py \
  backend/tests/test_spring_caravan_arc.py

PYTHONPATH=backend backend/.venv/bin/pytest -q backend/tests
npm --prefix frontend run build
npm --prefix admin run test
npm --prefix admin run build
npm --prefix admin run e2e
git diff --check
```

## 完成判定

- Scene 被占用时任何 authored arc 入口都不会从调度队列永久丢失。
- 入口、timed node、choice 和 terminal 的 mutation 具有明确事务边界。
- 进行中的 Run 完全不受已发布 Definition 更新影响。
- 最终 choice 在响应丢失后可以安全重试，且不会重复 effects。
- 自由交互预算在后端强制执行，空请求不计数。
- 条件操作与作者文档一致，不再存在永远 False 或偷读错误字段的占位实现。
- focused arc 与 active Scene 一致，多 Run 投影不再按字符串最小 ID 猜测。
- automatic narrative 能按顺序进入 transition log 或被作者显式标记 silent。
- schema v2 运行时由一个 StoryArcRun 聚合，NodeVisit 不复制 cast/facts。
- v2 旧存档和旧 choice API 有经过测试的兼容迁移。
- 春季商队所有分支仍可到达 terminal，并正确安排或取消下一次 occurrence。
- 后端全量测试、玩家前端构建、Admin 测试/构建/E2E 全部通过。

## 不要做的事

- 不要先把事件设为 active，再尝试创建 Run 或 Scene。
- 不要在 Run 推进中再次按 definition id 读取最新 JSON。
- 不要只修 `public_arc()`，遗漏 effects、terminal、series 和 instance factory 的动态读取。
- 不要在 completed 检查之后才做幂等查找。
- 不要依赖前端 disabled 或 Hermes prompt 执行 interaction budget。
- 不要保留返回固定 False 的条件操作。
- 不要用运行时 500 作为正常的 conditional transition 冲突策略。
- 不要让 NodeVisit 再保存一份 Run cast/facts。
- 不要把 Definition snapshot 暴露为 Admin 可编辑的 Run 状态。
- 不要在 P1 失败用例尚未通过时开始大规模 runtime v3 清理。
- 不要为了统一 schema v1/v2 而破坏现有 Storylet 事件。
