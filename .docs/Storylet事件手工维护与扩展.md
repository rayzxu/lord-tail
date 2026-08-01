# Storylet 事件手工维护与扩展

本文说明如何在不修改 Python 导演逻辑的前提下，维护和增加由领地状态、NPC 与长期后果驱动的剧情事件。Storylet 与“计划事件”不是同一层：计划事件负责“何时发生”，Storylet 负责“谁卷入、玩家能选什么、选择产生什么确定性后果”。

## 维护入口

配置目录：

```text
backend/app/data/storylets/
  director.json                 导演频率、预算和评分权重
  character_generation.json     姓名、阶级职业、财富带、选角评分
  wardrobe_templates.json       纯叙事衣着模板
  petition_building_credit.json 建设资助事件链
  village_grievance.json         第二个纯配置事件示例
```

核心 Python 注册表在 `backend/app/storylets/config.py`。只有需要一种全新的 trigger、参数生成器或 effect 时才修改 Python；普通新事件只增加 JSON。

Hermes 的只读叙事 skill 位于：

```text
~/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-storylet/
```

## 三层数据不要混用

1. Definition：版本库中的 JSON 规则，可以人工修改。
2. Draft：预览时临时生成的参数、选角和人物草稿，不写存档。
3. Instance：已经进入某局游戏的冻结事实。修改 JSON 不会追溯改写旧实例。

实例中的 `cast`、`cast_snapshots`、`facts`、`choice_ids` 是历史事实。不要直接编辑存档里的这些字段；需要纠错时应取消旧事件并创建新实例。

## 新增一个简单事件

复制 `village_grievance.json`，改成新的文件名。最小结构如下：

```json
{
  "schema_version": 1,
  "chain_id": "unique_chain_name",
  "nodes": [{
    "id": "unique_definition_id",
    "node_key": "petition",
    "title": "玩家看到的标题",
    "category": "daily",
    "source_kind": "realm",
    "priority": "major",
    "base_weight": 10,
    "cooldown_days": 45,
    "blocking": true,
    "scene_type": "court",
    "triggers": {
      "population_class_any": ["serfs", "free_peasants"],
      "minimum_class_population": 1
    },
    "roles": {
      "petitioner": {
        "required": true,
        "distinct": true,
        "class_any": ["serfs", "free_peasants"],
        "adult": true,
        "reuse_existing": true,
        "generate_if_missing": true
      }
    },
    "parameters": {
      "variant": {"weighted_values": {"ordinary": 80, "rare": 20}}
    },
    "narrative_template_md": "## 标题\n\n{petitioner_name}来到领主厅。",
    "choices": [{
      "id": "accept",
      "label": "接受",
      "description_md": "玩家能看懂的确定性后果。",
      "confirm": false,
      "effects": [
        {"op": "change_morale", "delta": 1},
        {"op": "append_character_memory", "role": "petitioner", "text": "领主接受了请求。"},
        {"op": "append_history"}
      ]
    }]
  }]
}
```

命名要求：

- `id + node_key` 全局唯一，使用小写 snake_case。
- 起始节点约定为 `node_key=petition`；导演只从起始节点选择。
- 后续节点保持相同 `id`，使用新的 `node_key`。
- choice id 在节点内唯一，发布后不要改名，否则旧存档无法解释。

## 可用触发条件

当前框架注册并校验以下名称：

```text
resource_minimum / resource_maximum
population_class_any / minimum_class_population
season_any / weather_any
directive_any / directive_domain_any
building_count_minimum
army_size_minimum / military_readiness_below
diplomacy_relation_below / at_war
character_hook_any / relationship_exists
history_tag_any / history_tag_none
requires_legal_building_any
chain_fact_equals
```

当前首个版本已经实际执行资源、人口阶级、季节、天气、战略方针、合法建筑/地块和 chain fact 条件。其他注册名属于扩展位：在使用前应先在 `triggers.py` 增加执行实现和测试，不能只把名字写进 JSON。

常用写法：

```json
"resource_minimum": {"gold": 50, "wood": 15}
```

```json
"requires_legal_building_any": ["farm", "shop", "handicraft_workshop", "homes"]
```

合法建筑检查会同时检查：catalog 建筑 id、领地地图合法地块、空闲劳力和非金币材料。不要在事件配置中复制建筑成本、工期或劳力。

## 人物角色与家庭

常用 role 约束：

```text
required / distinct / adult
class_any / kind_any
reuse_existing / generate_if_missing
relation_to / relation_any / generate_relation_if_missing
```

选角优先复用人物账册中的活跃 NPC；找不到才从人口阶级 cohort 具名化。具名化不会增加总人口或阶级人口。

需要配偶等关系时：

```json
"dependent": {
  "required": false,
  "distinct": true,
  "relation_to": "petitioner",
  "relation_any": ["spouse"],
  "adult": true,
  "generate_relation_if_missing": true
}
```

如果系统补生成人物，会在同一事务中创建 Household 和 Relationship；任一步失败都不会留下半个人物。第一版关系类型：

```text
parent/child, spouse, sibling, employer/employee, debtor/creditor,
guardian/ward, patron/client, rival, friend
```

配偶双方必须成年；父母与子女至少相差十四岁。不要用 Storylet 配置绕过成人和身体相关限制。

## 参数与文案占位符

已支持的参数生成器：

```text
constant
range
weighted_values
from_trigger_result
from_service
chain_fact_readonly（预留）
state_path_readonly（预留）
character_component_readonly（预留）
```

已在建设链使用的特殊来源：

```json
"building_id": {"from_trigger_result": "legal_buildings"},
"tile": {"from_service": "legal_build_tiles"}
```

建设事实自动从正式 catalog 生成 `building_name`、`building_cost`、`saved_gold`、`requested_support` 和 `tile_label`。本地 Markdown 模板可以使用这些占位符，也可以使用 `{petitioner_name}`、`{dependent_name}`。

未知占位符不会执行代码，只会原样保留，便于发现拼写错误。配置严禁包含 Python import、函数路径、shell 或任意代码。

## 可用效果

白名单：

```text
change_resources
change_resources_from_fact
change_morale / change_authority
start_construction_from_facts
patch_character_component
append_character_memory
create_relationship / update_relationship
create_obligation / settle_obligation
set_character_hook / clear_character_hook
schedule_followup
append_history
emit_turn_event
confiscate_saved_gold
```

重要规则：

- 数额只能写在 definition 或来自冻结 facts，客户端只能提交 `choice_id`。
- 多个 effect 在 state 副本上执行；任何一步失败，整次选择回滚。
- 建设必须用 `start_construction_from_facts`，它调用正式 construction service，照常扣资源、占劳力和进入建设队列。
- lasting consequence 应同时写人物 memory 和 history。
- 严厉选择设置 `"confirm": true`，前端会二次确认。
- `append_history` 应通常放在 choice effects 最后。

## 添加后续节点

在同一文件的 `nodes` 数组增加节点，然后在前序 choice 中安排：

```json
{"op": "schedule_followup", "node_key": "repayment_due", "in_days": 90}
```

后续节点复用相同 `chain_id`、cast snapshot 和 chain facts，使用绝对游戏日期生成计划事件。不要在文案里自行计算日期。

建筑完工是特殊后续：建设 choice 成功后会将正式 `project_id` 写入 chain facts；construction phase 发出 `project_completed` 时，框架自动创建 `construction_completed` 节点。

每条链必须最终有不再 `schedule_followup` 的终止选择，否则会形成无限事件链。

## Director 频率与选择

`director.json` 管理每回合 major/minor 上限、默认冷却和评分权重。生产默认：完整九日回合结束后最多创建一个 major；被议会、到期事件或顾问选择打断的回合不运行导演。

导演创建的是 `ready` 实例和“当前时刻到期”的计划事件。它不会打断刚完成的结算；玩家下一次推进时，计划事件先激活并打开 Storylet scene。

调低 `base_weight` 会降低相对优先级；`cooldown_days` 控制同模板再次出现的最短游戏日间隔。不要用极高权重强迫每个回合发生事件，导演允许返回 `None`。

## Hermes 文案边界

Hermes 只在 `storylet_opening` / `storylet_result` 模式润色冻结事实：

- 不调用 choose API；
- 不改变状态；
- 不创造人物、金额、关系或后果；
- Hermes 不可用时，`narrative_template_md` 仍能完整游玩。

修改 skill 后运行：

```bash
python /Users/ray/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-storylet
```

## 预览、验证与调试

每次改 JSON 后先执行：

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/python tools/validate_storylets.py
PYTHONPATH=backend backend/.venv/bin/python tools/run_storylet_generation_matrix.py \
  --definition petition_building_credit --seeds 100
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_storylet_*.py
npm --prefix frontend run build
```

手工调试 API：

```text
GET  /api/debug/storylets/definitions
POST /api/debug/storylets/preview
POST /api/debug/storylets/instantiate
POST /api/debug/storylets/run-director
```

preview 固定 `commit=false`，不会占 id、创建人物、写历史或调用 Hermes。生产 UI 不应调用 debug API。

长局频率与存档增长检查：

```bash
PYTHONPATH=backend backend/.venv/bin/python tools/run_storylet_long_simulation.py --turns 100 --seed 2001
```

## 常见失败

> 本文描述的 schema v1 Storylet 仍以顶层 Instance/Chain 运行。需要显式分支图、timed node、自动过场和可靠终局的事件应使用 schema v2 Story Arc；其运行状态是 `StoryArcRun + NodeVisit`，维护规则见 `.docs/预编剧情图事件手工维护指南.md`。不要在 schema v2 中使用 `schedule_followup` 或 `transition_to` 隐藏迁移边。

- 启动时报“未知 effect/trigger”：名字未进入白名单或拼写错误。
- 预览报“没有合法建筑与地块”：地图、材料或空闲劳力不满足，并非文案错误。
- 事件创建了但没有立即弹出：这是预期行为；回合末只创建 ready，下一次推进才激活。
- 下一次推进没有继续结算：blocking Storylet 正在等待玩家选择。
- 选择返回 `409`：实例未激活、已经解决或重复提交了不同选择；前端应重新读取实例。
- 选择返回 `422`：正式状态在事件创建后变化，导致资源、劳力、人物或地块不再合法；事务不会留下半成品。
- 修改 JSON 后旧事件仍显示旧数据：Instance 冻结是设计要求，只影响之后创建的事件。

## 发布检查表

- definition/node/choice id 稳定且唯一；
- 至少一个合法选择，每个选择都有 Markdown 说明；
- 所有金额和对象来自配置或冻结事实；
- 人物 role 有复用或生成路径；
- 未成年人不会进入成人/配偶/身体相关内容；
- 所有长期后果有 memory/history 或 followup；
- 链有终止节点；
- 100 seeds 预览无异常；
- Storylet 专项测试、全量后端测试和前端 build 通过。
