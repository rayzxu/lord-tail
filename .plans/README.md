# Plans for Lord Tail Backend Engine

本目录的每个 plan 都是给后续 agent 或人工开发者直接执行的任务说明。

原则：

1. **明确**：每个 plan 写清楚要改哪些文件、生成哪些模块、保留哪些兼容行为。
2. **可执行**：步骤按顺序落地，避免只写抽象设计。
3. **可校验**：每个 plan 都给出验证命令和完成判定。

## 索引

| Plan | 目的 | 优先级 |
|---|---|---|
| [001_backend_module_split.md](./001_backend_module_split.md) | 把 `main.py` 中的状态、规则、路由、Hermes 适配拆成明确模块，建立后续系统边界 | P0 |
| [002_turn_pipeline.md](./002_turn_pipeline.md) | 引入统一回合结算 pipeline，替代当前 `local_turn + settle_economy` 的散装流程 | P0 |
| [003_economy_construction.md](./003_economy_construction.md) | 落地 economy / construction 模块，支持资源生产、消耗、建筑队列、劳力占用和建设事件 | P1 |
| [004_military_diplomacy.md](./004_military_diplomacy.md) | 落地 military / diplomacy 模块，补齐战斗结算、部队训练队列、外交关系数值和条约状态 | P1 |
| [005_medieval_demographics_economy.md](./005_medieval_demographics_economy.md) | 补强中世纪领地人口结构、阶级经济、怀孕出生、住房和民心人口流动 | P1 |
| [005A_livelihood_buildings_economy.md](./005A_livelihood_buildings_economy.md) | 补充民生建筑、地方资源产出、住房类型、就业和生产消耗链条 | P1 |
| [006_events_hermes_tests.md](./006_events_hermes_tests.md) | 落地 events 模块，统一 Hermes/前端状态变更接口，并补端到端测试 | P1 |
| [007_hermes_runs_sse_backend.md](./007_hermes_runs_sse_backend.md) | 接入 Hermes `/v1/runs`，后端桥接 SSE、run store、approval/clarify 和状态 actions | P0 |
| [008_frontend_agent_trace_description_ui.md](./008_frontend_agent_trace_description_ui.md) | 前端接入 Hermes run SSE，实现故事推进、执行 trace、描述者 drawer 和 Codex-style 两阶段 UI | P0 |
| [009_hermes_profile_skills_tools_api.md](./009_hermes_profile_skills_tools_api.md) | 设计 Lord Tail Hermes profile、专用 skill、MCP/API tools 和受控状态接口契约 | P0 |
| [010_battle_resolution_api.md](./010_battle_resolution_api.md) | 补齐公开战斗结算 API，让 Hermes/前端调用真实 battle resolve，而不是记录 battle_api_gap | P0 |
| [011_time_modes_scene_turns.md](./011_time_modes_scene_turns.md) | 建立 9 天战略回合与场景故事模式的双时间推进系统，补 scene/time API、Hermes context 和前端模式 UI | P0 |
| [012_diplomacy_map_ui.md](./012_diplomacy_map_ui.md) | 把战术地图升级为可配置 n×n 的外交地图：扩充地块类型、地块归属外交势力、前端结构化地块/势力详情面板 | P1 |
| [013_description_cache_invalidation.md](./013_description_cache_invalidation.md) | 建立描述缓存与过期策略：短期复用，长期/季节/当前格和周围 8 格变化时标记 stale，并向 Hermes 传邻域上下文 | P0 |
| [014_population_analysis_ui.md](./014_population_analysis_ui.md) | 新增只读居民分析页面，展示阶级人口、男女性别、年龄结构、孕妇月龄、生产力、税金、支出、住房和阶级经济 | P1 |
| [015_map_generation.md](./015_map_generation.md) | 自动生成领地地图与外交地图：领主堡垒居中，山丘/湖泊/河流只出现在外交地图，并隔离势力地产与经营建筑 | P1 |
| [016_history_memory_system.md](./016_history_memory_system.md) | 新增历史系统：书记官记录重要事情为结构化领地记忆，供前端编年史与 Hermes 上下文使用 | P0 |
| [017_scheduled_event_system.md](./017_scheduled_event_system.md) | 新增长期/计划事件系统：管理商队季末到访、敌军几回合后抵达、取消/改期/持续事件与事件面板 | P0 |
| [018_character_component_system.md](./018_character_component_system.md) | 把人物账册重构为 kind + components + factory/registry 的可扩展 NPC 系统 | P1 |
| [019_council_directive_management_ai.md](./019_council_directive_management_ai.md) | 新增财政／军事／外交领主议会、长期战略方针，以及危机规则 + Utility + 短期预测驱动的确定性领地管理 AI | P0 |

## 通用约定

- 项目根目录固定为 `/Users/ray/raylab/lord-tail/`。
- 后端源码根目录固定为 `/Users/ray/raylab/lord-tail/backend/app/`。
- 规则配置继续以 `/Users/ray/raylab/lord-tail/backend/app/data/catalog.json` 为主数据源。
- 不允许把新规则数值硬编码回 Python；Python 只做加载、校验、结算。
- `/api/state/*` 是前端、Hermes 和调试脚本的统一状态变更接口；`/api/hermes/*` 只作为兼容别名保留。
- 每完成一个 plan 后，至少运行：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python -m compileall -q backend
cd frontend && npm run build
```

如果 plan 涉及后端行为，必须补充对应的 FastAPI `TestClient` smoke test 或 pytest。
