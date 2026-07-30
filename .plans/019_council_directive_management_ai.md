# Plan 019: 财政／军事／外交议会与领地管理 AI

## 目标

为 `lord-tail` 增加一套可解释、可预测、可由玩家约束的领地管理 AI：

> 领主议会根据真实领地状态提出财政、军事、外交方案；玩家选择一个持续约 90 天的战略方针；确定性管理 AI 在方针约束下，每个九日战略回合选择并执行一个合法行动。

系统采用混合式决策架构：

- 现有 economy / construction / military / diplomacy / demographics / events 规则负责真实结算。
- 结构化行动层负责生成合法行动并统一执行。
- 危机规则、Utility AI 和短期 Beam Search 负责经营决策。
- Hermes/LLM 只负责理解玩家意图、塑造大臣人格、润色发言和叙事，不负责计算数值、判定合法性或直接修改状态。

第一版完成以下闭环：

```text
召开领主议会
  -> 财政官、军事统帅、外交官各提出一个动态方案
  -> 玩家选择主要发展重点与管理模式
  -> 生成长期战略方针
  -> 管理 AI 每个战略回合规划并执行一个合法行动
  -> 展示依据、预测和执行结果
  -> 方针完成、到期或发生危机时重新议事
```

## 核心原则

### 1. 世界状态只有一个权威来源

- AI 不维护第二份领地资源、建筑、部队或外交状态。
- AI 读取正式 `state`，在 `deepcopy(state)` 上预测，并通过正式行动执行入口修改状态。
- 建筑成本、工期、劳力、生产、征兵和外交规则继续来自 catalog 和现有系统模块。
- 不允许在 AI 模块重复硬编码一套规则或资源价格。

### 2. 玩家、前端、Hermes 和管理 AI 共用行动服务

所有战略行动最终进入同一个后端服务：

```python
legal_actions(state, directive=None) -> list[Action]
validate_action(state, action, context) -> ActionValidation
execute_action(state, action, context) -> list[TurnEvent]
```

- 前端提交结构化 Action。
- 玩家自然语言命令先被解析为结构化 Action。
- Hermes 调用公开 Action API，不调用 AI 私有 mutation。
- 管理 AI 只能从 `legal_actions()` 返回的候选中选择。
- API 路由、Hermes tool 和管理 AI 不复制业务规则。

### 3. AI 不获得额外行动

每个九日战略回合最多有一个战略行动槽：

- `delegated`：管理 AI 使用行动槽。
- `advisory`：AI 给出候选，玩家选择后使用行动槽。
- `manual`：玩家自行使用行动槽。
- 委托模式下玩家当轮下达合法手动命令时，玩家命令覆盖 AI 行动；长期方针继续存在。
- 会议选择、查看建议、LLM 发言均不消耗或赠送资源和行动。

### 4. 关闭 Hermes 后仍可完整运行

- 会议提案、领地分析、规划、合法性判断、预测、行动执行全部是本地确定性功能。
- 大臣发言必须有模板化 fallback。
- Hermes 不可用时只影响语言表现，不影响会议和管理 AI。

## 与现有系统的衔接

本 plan 建立在以下已完成能力之上：

- Plan 002：统一九日回合 pipeline。
- Plan 003/005/005A：经济、建设、人口、住房和生产链。
- Plan 004/010：军事、外交和战斗结算。
- Plan 011：战略回合与场景故事模式。
- Plan 016：历史记忆。
- Plan 017：以游戏绝对时间为准的计划事件与到期中断。

议会不是新的平行时间系统：

- 首次议会安排在第 1 日 09:00。
- 常规议会按 `calendar_day + clock_24` 安排。
- 一个方针默认持续 90 游戏日，相当于 10 个九日战略回合。
- `executed_strategic_turns` 只用于统计进度，不能作为计划事件的到期依据。
- 到期、紧急会议和首次会议复用 `scheduled_events`，因此能够打断“推进九天”。

## 非目标

本 plan 第一版不实现：

- 强化学习训练。
- 运行时自动调整权重。
- CP-SAT、MILP 或复杂生产排期求解器。
- LLM 自行生成 JSON 状态补丁。
- LLM 自行决定资源数值或战斗结果。
- 每位大臣一个独立模型或长期自治 Agent。
- 多个并行战略方针。
- 完整的 NPC 领主自治；只为将来复用 planner 保留 `realm_id/actor_id` 上下文。
- 在故事场景的每轮对话中自动经营领地。

## 玩法规则

### 首次议会

- 新游戏创建时，安排第 1 日 09:00 的 `council_session`。
- 玩家首次点击“推进九天”时，现有计划事件中断机制将时钟推进至 09:00，激活会议并阻止九日结算。
- 会议解决前，不允许继续完整战略回合。

### 常规议会

- 方针解决时安排下一次常规会议，默认在 90 游戏日后 09:00。
- 不采用每回合无条件创建事件的方式。
- 同一方针只能有一个未结束的常规复议事件。

### 紧急议会

默认触发条件由 `council_policies.json` 配置：

- 粮食可维持时间低于 18 天。
- 金币可维持时间低于 18 天且净收入为负。
- 已处于战争状态且战备值低于 `0.8`。
- 最大外部威胁超过领地防御能力的 `1.5` 倍。
- 当前方针连续 2 个战略回合无法生成合法行动。

紧急会议要求：

- 使用稳定的 `trigger_key` 去重。
- 相同危机有冷却时间。
- 已存在开放会议时，只更新会议危机摘要，不再创建第二场会议。
- 紧急会议可以暂停当前方针，但不会在玩家选择前自动替换方针。

### 玩家主动复议

- 玩家可请求召开复议。
- 默认冷却为 18 游戏日。
- 请求只创建/激活会议，不直接更换方针。

## 三类提案和维持现状

每场会议最多展示四张卡：

1. 财政官从财政模板中选出当前适用性最高的一项。
2. 军事统帅从军事模板中选出当前适用性最高的一项。
3. 外交官从外交模板中选出当前适用性最高的一项。
4. 固定提供“维持现状”。

### 财政提案

- `finance_food_security`：粮食安全
  优先农田、养殖、狩猎、粮食库存、相应住房和劳力。

- `finance_treasury_recovery`：财政恢复
  限制新工程，降低维护压力，改善合法税收，允许等待积累。

- `finance_commercial_growth`：商业扩张
  优先原料链、手工作坊、商店、工匠和商人就业。

### 军事提案

- `military_border_defense`：边境防御
  优先守军、组织度、兵种组合和防御能力。

- `military_force_expansion`：扩充军力
  优先训练能力以及在财政和粮食可承受范围内征兵。

- `military_fortification`：要塞建设
  优先永久防御设施和领地地图上的合法战略地块。

### 外交提案

- `diplomacy_trade_opening`：开放商路
  优先可接触势力、贸易使团和关系维护。

- `diplomacy_appeasement`：缓和关系
  优先赠礼、改善关系、停战和降低近期战争风险。

- `diplomacy_alliance_building`：建立联盟
  优先友好势力、共同敌人、信誉和联盟准备。

### 保守提案

- `status_quo_reserve`：维持现状
  不启动高成本扩张，优先积累资源、完成在建项目和修复危机。

具体阈值、目标、预算、权重、标签和文案键全部放入：

```text
backend/app/data/council_policies.json
```

Python 只加载、校验和应用配置。

## 状态 schema

在正式 state 中新增：

```json
{
  "council": {
    "current_meeting": null,
    "history": [],
    "next_id": 1,
    "last_regular_time": null,
    "last_requested_review_time": null,
    "emergency_cooldowns": {}
  },
  "strategic_directive": null,
  "management_ai": {
    "enabled": true,
    "mode": "delegated",
    "last_decision": null,
    "pending_advice": null,
    "consecutive_no_action_turns": 0
  }
}
```

### CouncilMeeting

```json
{
  "id": "council_000001",
  "status": "open",
  "reason": "regular",
  "trigger_key": "regular:directive_000001",
  "opened_time": {
    "calendar_day": 1,
    "clock_24": "09:00"
  },
  "analysis_snapshot": {},
  "crisis_summary": [],
  "proposals": [],
  "resolved_proposal_id": null,
  "resolved_time": null,
  "management_mode": null
}
```

会议状态：

- `open`
- `resolved`
- `cancelled`

### StrategicDirective

```json
{
  "id": "directive_000001",
  "source_meeting_id": "council_000001",
  "proposal_id": "finance_food_security",
  "domain": "finance",
  "title": "确保粮食安全",
  "status": "active",
  "started_time": {
    "calendar_day": 1,
    "clock_24": "09:00"
  },
  "expires_time": {
    "calendar_day": 91,
    "clock_24": "09:00"
  },
  "duration_strategic_turns": 10,
  "executed_strategic_turns": 0,
  "targets": {
    "food_runway_days": 54
  },
  "budget_limits": {
    "gold_spend_ratio": 0.45,
    "minimum_gold_reserve": 100
  },
  "allowed_action_tags": [
    "food",
    "agriculture",
    "housing",
    "wait"
  ],
  "weights": {
    "survival": 10.0,
    "food_security": 2.0,
    "treasury": 0.8,
    "stability": 1.0
  },
  "progress": {},
  "completed_targets": [],
  "suspension_reason": null
}
```

方针状态：

- `active`
- `completed`
- `expired`
- `suspended`
- `replaced`

兼容要求：

- 所有字段加入 `normalize_state()`。
- 旧存档缺少字段时自动补默认值。
- normalize 不创建重复会议或重复计划事件。
- 历史只保留已解决会议的摘要；当前开放会议单独存储。

## 领地分析器

新增纯函数：

```python
analyze_realm(state: Mapping[str, Any]) -> RealmAnalysis
```

要求：

- 只读，不修改输入状态。
- 相同输入产生相同输出。
- 对旧存档和缺失字段安全。
- 指标附带原始依据，供 UI 和测试解释。
- 计算失败的指标返回 `unknown`/`None` 和原因，不伪造数值。

### 财政与民生指标

- 当前各资源。
- 每战略回合粮食预计净变化。
- `food_runway_days`。
- 每战略回合金币预计净变化。
- `gold_runway_days`。
- 建筑与军队维护负担。
- 在建工程的剩余成本、劳力和工期。
- 就业率。
- 各阶级住房余量。
- 生产链瓶颈。
- 民心、统治力和人口流失风险。

### 军事指标

- 各兵种数量、组织度和有效战斗力。
- 防御能力。
- 军队维护费。
- 训练容量。
- 邻近敌对势力与最大外部威胁。
- 战备值：

```python
military_readiness = defensive_power / max(external_threat, 1)
```

### 外交指标

- 可接触势力数量。
- 友好、敌对和交战势力数量。
- 平均关系。
- 外交孤立度。
- 可用贸易机会。
- 条约状态。
- 近期战争风险。

## 结构化行动系统

### Action 类型

第一版至少支持：

```python
BuildAction(building_id, x, y)
RecruitAction(unit_id, quantity)
TaxPolicyAction(policy_id)
SendEnvoyAction(faction_id, mission_type, offer=None)
WaitAction(reason)
```

每个 Action 都有：

```json
{
  "type": "build",
  "action_id": "build:farm:5:4",
  "actor": "management_ai",
  "tags": ["finance", "food", "agriculture"],
  "payload": {},
  "estimated_cost": {},
  "explanation_key": "build_food_capacity"
}
```

### 合法行动生成

```python
legal_actions(
    state,
    *,
    directive=None,
    actor="player"
) -> list[Action]
```

必须复用现有系统的合法性规则，并控制搜索规模：

- 每种建筑只生成评分最好的 3 个合法坐标。
- 征兵数量候选为 1、5、10、可承担上限，去重并过滤非法值。
- 外交行动只针对外交地图中可接触且非己方势力。
- 始终提供合法的 `WaitAction`。
- 第一版总候选数不超过 40。
- 方针允许标签只影响 AI 候选过滤，不限制玩家手动命令。

### 统一执行

新增 application service，而不是直接调用 API 路由：

```python
execute_action(state, action, context) -> list[TurnEvent]
```

路由、Hermes tool、玩家命令解析和 planner 都调用该服务。

执行前再次验证，防止“规划时合法、执行时状态已变化”：

- 资源、人口和劳力。
- 建筑前置和地块占用。
- 训练容量与兵种配置。
- 外交目标与关系状态。
- 方针预算保留线仅约束管理 AI。

自然语言 `run_player_action()` 迁移为：

```text
parse command -> Action | NoAction -> execute_action()
```

现有中文命令保持兼容，但不再在 `turn.py` 中直接实现贸易、税令等规则。

## 危机规则、Utility 和规划

### 第一层：硬约束

先淘汰会导致以下情况的候选：

- 非法资源、劳力、地块或建筑前置。
- 立即进入不可恢复的粮食短缺。
- 无法承担现有必要维护费。
- 战争中守军低于最低安全线。
- 外交目标不可接触或已失效。
- 突破方针最低储备和预算上限。

### 第二层：词典序危机目标

按顺序比较，前一层未满足时不以后一层收益抵消：

1. 生存。
2. 财政可持续。
3. 民心和稳定。
4. 防务。
5. 方针发展目标。

### 第三层：方针 Utility

在无立即危机时使用配置权重评分：

- 财政：粮食、金币、就业、住房、生产链。
- 军事：战斗力、防御、训练容量、组织度。
- 外交：关系、条约、贸易和战争风险。
- 维持现状：安全库存、低成本和完成现有工程。

### 第四层：成本与风险

目标贡献接近时优先：

- 成本较低。
- 工期较短。
- 劳力占用较少。
- 坏情景下更安全。
- 能在方针期限内完成。

每个候选输出分项评分，不只输出一个总分：

```json
{
  "action_id": "build:farm:5:4",
  "legal": true,
  "hard_constraint_failures": [],
  "score": 18.4,
  "score_breakdown": {
    "survival": 10.0,
    "directive_progress": 6.0,
    "stability": 1.5,
    "cost": -0.8,
    "risk": -0.3,
    "completion_bonus": 2.0
  },
  "reasons": []
}
```

## 无副作用预测器

新增：

```python
forecast(
    state,
    action_sequence,
    *,
    horizon=3,
    seed=0,
    scenarios=("baseline",),
) -> ForecastResult
```

要求：

- 使用 `deepcopy(state)`。
- 复用正式经济、建设、军事、外交、人口和维护规则。
- 不写 `current_state`、存档、run store、正式历史或请求审计。
- 不调用 Hermes。
- 天气和随机事件使用显式 seed，测试可复现。
- 预测模式产生本地 `TurnEvent`，但不进入正式历史。
- 默认不生成/处理需要玩家输入的叙事场景；以结构化风险结果返回。
- 预测结果包含每回合资源、指标、风险、失败原因和最终状态摘要。

第一版只做确定性基准情景。后续可以增加：

- `poor_harvest`
- `war_pressure`
- `normal_variance`

## Beam Search

第一版参数写入配置：

- 深度：3 个战略回合。
- Beam width：6。
- 每节点最多扩展 20 个预筛候选。
- 每次只执行最优序列的第一步。
- 下一战略回合读取真实新状态后重新规划。

规划器：

```python
plan_management_action(
    state,
    directive,
    *,
    mode,
    seed,
) -> ManagementDecision
```

返回：

- 最佳行动。
- 前 3 个候选。
- 最佳三回合行动序列。
- 预测摘要。
- 分项评分。
- 选择理由。
- 被拒绝的重要候选及原因。

如果没有非等待合法行动：

- 返回 `WaitAction`。
- 增加 `consecutive_no_action_turns`。
- 连续达到阈值后安排紧急复议。

## 管理模式

### 委托模式 `delegated`

- 战略回合没有玩家结构化行动时，planner 自动占用行动槽。
- UI 和历史展示 AI 的依据、候选和预测。

### 顾问模式 `advisory`

- planner 生成前三个候选，但战略推进保持阻塞。
- 玩家选择候选或改为手动行动后才能继续。
- `pending_advice` 必须绑定状态版本/摘要；状态变化后旧建议失效并重新规划。

### 手动模式 `manual`

- AI 不执行动作。
- 可以继续显示领地分析和当前方针进度。

## 议会提案生成

提案生成分两层：

1. 本地规则根据 `RealmAnalysis` 对各部门模板计算适用性、紧迫度、可行性和三回合预测。
2. 可选 Hermes 调用只将结构化提案转写成符合大臣身份的 Markdown 发言。

LLM 输入：

- 只读领地摘要。
- 当前危机。
- 已确定的提案标题、依据、成本、风险、目标和预测。
- 大臣角色设定。

LLM 输出：

- 发言 Markdown。
- 不接受资源 patch、Action、tool call 或方案数值。

LLM 输出失败、超时或越权时使用本地模板。

## 战略回合 pipeline 集成

建议顺序：

1. `start_turn`
2. 激活到期计划事件。
3. 检查开放议会、到期方针和紧急复议。
4. 如果存在阻塞型议会或待选顾问建议，停止战略推进。
5. `income`
6. 确定唯一行动来源：玩家 / 顾问选择 / 管理 AI / wait。
7. `execute_action`
8. `construction`
9. `military`
10. `diplomacy`
11. `demographics`
12. `weather`
13. `expenditure`
14. `events`
15. `end_turn`
16. 更新方针进度、完成/到期判定和紧急条件。
17. 写历史。

重要约束：

- 现有计划事件仍可在九天窗口内优先中断推进。
- 被事件中断且未完成正式九日结算时，不消耗管理 AI 行动槽，不增加方针执行回合。
- 场景故事模式不自动运行管理 AI。
- 会议解决本身不进入 economy 结算，不生成资源。

## 计划事件与历史集成

在 catalog 的事件类型配置中增加 `council_session`：

```json
{
  "label": "领主议会",
  "default_importance": 5,
  "default_visibility": "player",
  "default_scene_type": "council",
  "default_due_clock_24": "09:00",
  "turn_event_kind": "council_opened",
  "tags": [
    "council",
    "strategy",
    "finance",
    "military",
    "diplomacy"
  ]
}
```

历史记录：

- 会议召开时间和原因。
- 当时的危机与关键指标。
- 三位大臣提案和维持现状。
- 玩家选择与管理模式。
- 方针开始、暂停、替换、完成或到期。
- 每回合实际行动、行动来源、理由和预测偏差摘要。

历史正文可以是 Markdown，但结构化指标和 Action 必须保留为数据字段。

## 后端目录和修改范围

新增：

```text
backend/app/ai/__init__.py
backend/app/ai/actions.py
backend/app/ai/analysis.py
backend/app/ai/forecast.py
backend/app/ai/proposals.py
backend/app/ai/scoring.py
backend/app/ai/planner.py
backend/app/systems/council.py
backend/app/api/council.py
backend/app/data/council_policies.json
```

修改：

- `backend/app/engine/state.py`
  - 初始化并 normalize council / directive / management_ai。
  - 新游戏安排首次议会。

- `backend/app/engine/types.py`
  - 增加 Action、ActionValidation、RealmAnalysis、Proposal、Directive、ManagementDecision 类型。

- `backend/app/engine/commands.py`
  - 把自然语言命令解析为结构化 Action。

- `backend/app/engine/turn.py`
  - 接入统一行动服务、会议阻塞、AI 行动和方针进度。
  - 移除 `run_player_action()` 中重复的具体业务实现。

- `backend/app/systems/scheduled_events.py`
  - 支持 `council_session` 激活与稳定去重。

- `backend/app/engine/scenes.py`
  - 将 `council` 加入合法场景类型。

- `backend/app/engine/history.py`
  - 记录会议、方针和管理决策。

- `backend/app/engine/hermes_context.py`
  - 明确 Hermes 只可叙述议会结果，不替代 planner。

- `backend/app/api/schemas.py`
  - 增加会议、方针、管理模式和 Action 请求 schema。

- `backend/app/main.py`
  - 注册 council router。

- `backend/app/data/catalog.json`
  - 只补事件类型或已有 catalog 所需标签；政策数值放 `council_policies.json`。

## API

### 议会

```text
GET  /api/council/current
POST /api/council/{meeting_id}/resolve
POST /api/council/request-review
```

解决会议：

```json
{
  "proposal_id": "finance_food_security",
  "management_mode": "delegated"
}
```

校验：

- 会议存在且仍为 `open`。
- 提案属于该会议。
- 重复提交相同结果保持幂等。
- 不同的重复提交返回 `409`。
- 新方针正确替换旧方针。
- 下一次常规会议只安排一次。

### 方针和管理 AI

```text
GET  /api/strategy/current
GET  /api/strategy/analysis
POST /api/strategy/management-mode
GET  /api/strategy/advice
POST /api/strategy/advice/{decision_id}/accept
```

### 统一战略行动

```text
GET  /api/actions/legal
POST /api/actions/validate
POST /api/actions/execute
```

`/api/actions/execute` 不允许绕过“每战略回合一个行动槽”。Hermes、前端和管理 AI 使用同一 application service；管理 AI 内部调用服务函数，不通过 HTTP 回调自身。

所有 mutation 返回：

- 更新后的必要状态摘要。
- 结构化 `TurnEvent`。
- action id。
- actor/source。
- 审计信息。

## Hermes profile 和 skill

更新 Lord Tail 专属 profile：

- 增加 `council` 场景说明。
- 明确财政官、军事统帅、外交官是中世纪叙事角色，不是三个自治数值 Agent。
- 提供只读议会、方针、分析和建议接口说明。
- Hermes 在玩家明确下令时可以提交公开结构化 Action，但不能绕过行动槽。
- Hermes 不得自行改写 `analysis_snapshot`、proposal 数值、planner score 或 forecast。
- 大臣发言使用 Markdown，失败时允许后端模板直接显示。

不能让 Hermes 输出一段 JSON 让后端猜测或批量套用；真实互动继续通过公开 API/tool call 完成。

## 前端

当前前端以 `App.tsx` 为主，实施时新增组件并逐步拆出：

```text
frontend/src/components/CouncilDrawer.tsx
frontend/src/components/CouncilProposalCard.tsx
frontend/src/components/StrategicDirectivePanel.tsx
frontend/src/components/ManagementAdvicePanel.tsx
```

### 议会侧拉界面

显示：

- 召开原因与时间。
- 当前危机摘要。
- 财政、军事、外交、维持现状四张提案卡。
- 每项方案的状态依据。
- 目标、预算、风险和预计三回合结果。
- 大臣 Markdown 发言。
- 委托 / 顾问 / 手动模式选择。
- 最终确认。

开放会议必须有明显阻塞提示；玩家不能误以为“推进九天”已经结算。

### 方针面板

放入领地大盘或功能菜单可持续访问的位置，显示：

- 当前发展重点。
- 开始和到期游戏时间。
- 预计剩余九日回合数。
- 目标进度。
- 最近一次实际行动和行动来源。
- 选择理由与预测摘要。
- 管理模式切换。
- 暂停委托。
- 要求复议。

### 顾问面板

显示前三个候选：

- 行动。
- 合法性。
- 成本。
- 三回合预测。
- 分项评分。
- 主要风险。
- 接受或改为手动命令。

Markdown 继续使用现有支持 GFM table 的渲染组件。

## 配置校验

`council_policies.json` 启动时校验：

- proposal id 全局唯一。
- domain 合法。
- 所有权重为有限数。
- 阈值和预算范围合法。
- action tag 存在。
- building/unit/policy 引用能在 catalog 找到。
- 方针持续时间、搜索深度和 beam width 有安全上限。

配置错误时后端启动失败并指出精确 JSON 路径，不静默使用另一套 Python 默认值。

## 实施阶段

### 阶段 1：状态、配置与会议骨架

- 新增配置及校验。
- 新增 council / directive / management_ai 状态和旧存档迁移。
- 新增首次、常规、紧急和主动复议事件。
- 使用固定测试分析生成四张提案。
- 完成会议读取/解决 API。
- 完成基础议会 UI。

### 阶段 2：动态领地分析和提案

- 实现纯 `analyze_realm()`。
- 实现财政、军事、外交模板适用性评分。
- 每部门选择一个当前最相关提案。
- 加入依据、目标、预算和风险。
- 接入三回合基准预测摘要的接口占位。

### 阶段 3：结构化行动统一

- 定义 Action schema。
- 实现 `legal_actions/validate_action/execute_action`。
- 迁移建设、征兵、税政、外交和等待行动。
- 将玩家文本命令转入统一入口。
- 前端和 Hermes 改用相同公开 Action API。

### 阶段 4：Utility AI MVP

- 实现硬约束、危机优先级和方针权重。
- 逐个模拟单回合合法行动。
- 输出前三候选、分项评分与理由。
- 完成 delegated / advisory / manual。
- 确保每轮只有一个战略行动。

### 阶段 5：无副作用预测与滚动规划

- 抽取预测执行上下文。
- 实现可复现的三回合 forecast。
- 实现 Beam Search。
- 只执行第一步并在下一回合重算。
- 增加预测与实际差异记录。

### 阶段 6：完整 UI、历史和可选 LLM 润色

- 完成方针和顾问面板。
- 完成会议/方针历史。
- 加入模板化大臣发言。
- 最后接入可选 Hermes Markdown 润色。

### 阶段 7：平衡和长局回归

- 调整阈值、预算、权重、搜索宽度和会议周期。
- 使用固定 seed 运行至少 100 个战略回合的长局模拟。
- 覆盖粮食危机、财政危机、战争、和平发展和无合法行动。
- 记录 planner 时间和候选规模，避免前端等待不可控。

## 测试

新增至少：

```text
backend/tests/test_council.py
backend/tests/test_management_analysis.py
backend/tests/test_structured_actions.py
backend/tests/test_management_forecast.py
backend/tests/test_management_planner.py
backend/tests/test_management_turn_integration.py
```

### 状态和会议

- 新游戏只创建一次第 1 日 09:00 首次议会。
- 首次议会能中断推进九天。
- 旧存档 normalize 后可读取。
- 同一 trigger 不重复创建会议。
- 解决会议幂等。
- 方针到期后只安排一次常规复议。
- 紧急会议遵守冷却。

### 分析

- 相同 state 返回相同分析。
- 分析不修改输入。
- 粮食、金币、住房、就业、战备和外交指标有固定 fixture。
- 缺失字段不会崩溃，也不会生成虚假的零风险。

### 行动

- AI 返回的每个动作都通过正式验证器。
- 玩家、Hermes 和 AI 调用相同服务得到相同结果。
- 非法坐标、资源不足、非法兵种和非法外交目标被拒绝。
- Wait 始终合法。
- 候选规模不超过配置上限。

### AI 行为

- 粮食即将耗尽时优先解决生存，不盲目建昂贵军事设施。
- 财政恢复与商业扩张产生不同倾向。
- 战争威胁下军事方针保留最低守军。
- 外交方针只操作可接触势力。
- 手动命令覆盖当轮 AI，且没有第二个免费行动。
- 顾问模式在玩家选择前不结算。
- 无行动达到阈值后触发复议。

### 预测和搜索

- forecast 不修改正式 state、存档和历史。
- 相同 seed 结果一致。
- Beam Search 能形成“先建前置生产/训练设施，再生产/征兵”的短链。
- planner 只执行最佳序列第一步。
- 预测中的 Hermes 调用次数为零。

### API 和前端

- 会议、方针、分析、模式和建议 API smoke test。
- 重复/冲突 resolve 返回正确状态码。
- 前端 build 通过。
- Hermes 不可用时会议 UI 使用模板发言并可继续游戏。

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
npm --prefix frontend run build
```

长局模拟阶段增加：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python tools/run_management_ai_simulation.py \
  --turns 100 \
  --seed 1901 \
  --mode delegated
```

脚本至少输出：

- 每回合状态摘要。
- 当前方针。
- 选择行动和候选评分。
- 危机、复议和中断。
- 最终资源、人口、民心、军力和外交状态。
- 非法行动数。
- 单次规划耗时的平均值和最大值。

## 完成判定

- 玩家可以在财政、军事、外交和维持现状中选择主要发展重点。
- 选择会生成持续约 90 游戏日的正式战略方针。
- 会议由游戏时间安排并能够正确中断推进九天。
- 会议选择不会直接增加资源、建筑、部队或外交关系。
- 管理 AI 只执行正式合法行动。
- 玩家、前端、Hermes 和 AI 共用行动服务与规则校验。
- 每个战略回合最多执行一个战略行动。
- 玩家手动行动可覆盖当轮 AI，但不自动取消长期方针。
- delegated / advisory / manual 三种模式行为明确。
- 不同方针在固定测试状态中产生稳定且不同的行动倾向。
- AI 决策包含状态依据、三回合预测、评分拆分和风险说明。
- 方针能够完成、到期、暂停、替换和触发复议。
- 计划事件中断时不会错误消耗 AI 行动或方针回合。
- 关闭 Hermes 后，会议、规划、结算和 UI 仍可完整运行。
- 旧存档能加载，现有测试与新增测试全部通过。
