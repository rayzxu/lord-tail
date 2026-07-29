# Plan 018: Component-based Character System

## 目标

把当前 flat character 账册重构为更可扩展的 `kind + identity/profile/relationship/memory/components/flags` 模型。

核心目标：

1. 人物仍然存储在后端 `state.characters.entries[]`，随存档保存。
2. 不使用 Python 继承作为持久化模型；使用 JSON-compatible dict + component composition。
3. 通过工厂函数 `create_character(kind, payload)` 创建不同类型人物。
4. 不同人物类型通过 registry/template 定义默认 component。
5. 现有 API 保持兼容：旧 flat payload 仍能 POST/PATCH。
6. Hermes agent 可以读取、创建、更新不同人物类型，并知道每类人物有哪些可用状态。

## 当前问题

当前实现：

```json
{
  "id": "char_1",
  "name": "玛尔塔",
  "role": "管家",
  "gender": "女",
  "age": 42,
  "faction": "黑泥堡",
  "location": "领主堡垒",
  "status": "active",
  "appearance_md": "",
  "personality_md": "",
  "description_md": "",
  "relationship_to_lord": "",
  "disposition": -10,
  "traits": [],
  "memories": [],
  "flags": {}
}
```

问题：

- 适合 MVP，但后续管家、商人、骑士、俘虏、使者、工匠、间谍、伤员等会有不同状态。
- 如果继续在顶层加字段，会导致人物 schema 失控。
- 如果用 Python class inheritance，会导致持久化、Hermes API、前端展示变复杂。

## 目标数据结构

新结构：

```json
{
  "id": "char_1",
  "kind": "steward",
  "name": "玛尔塔",
  "identity": {
    "role": "管家",
    "gender": "女",
    "age": 42,
    "faction": "黑泥堡",
    "location": "领主堡垒",
    "status": "active"
  },
  "profile": {
    "appearance_md": "灰发，腰间挂钥匙。",
    "personality_md": "谨慎、记仇、擅长账目。",
    "description_md": "城堡里的老管家。",
    "traits": ["管家", "识字", "会算账"]
  },
  "relationship": {
    "to_lord": "畏惧领主，但依赖其权威维持秩序。",
    "disposition": -10,
    "loyalty": 40,
    "fear": 70,
    "trust": 20
  },
  "memory": {
    "entries": ["第1日被领主在阳台上斥责。"]
  },
  "components": {
    "court_official": {
      "rank": "管家",
      "access_level": 3,
      "manages": ["粮仓", "仆役"]
    },
    "economy_agent": {
      "wealth": 20,
      "income": 1,
      "debts": []
    },
    "health": {
      "condition": "healthy",
      "wounds": [],
      "stress": 0
    }
  },
  "flags": {},
  "created_time": {},
  "created_at": "...",
  "updated_at": "..."
}
```

## 人物 kind 初始集合

第一阶段只做下列 `kind`：

| kind | 用途 | 默认 components |
|---|---|---|
| `commoner` | 普通领民、临时 NPC | `health` |
| `steward` | 管家、账房、城堡管理者 | `court_official`, `economy_agent`, `health` |
| `merchant` | 商人、商队首领 | `merchant`, `economy_agent`, `health` |
| `envoy` | 外交使者、谈判代表 | `envoy`, `diplomacy_agent`, `health` |
| `knight` | 骑士、贵族武人 | `noble`, `combatant`, `health` |
| `soldier` | 士兵、护卫、雇佣兵 | `combatant`, `health` |
| `craftsman` | 铁匠、木匠、工匠 | `craftsman`, `economy_agent`, `health` |
| `prisoner` | 俘虏、囚犯 | `prisoner`, `health` |
| `spy` | 间谍、密探、线人 | `spy`, `health` |

`kind` 不是固定封死；未知 kind 降级为 `commoner` 并保留原始 kind 到 `flags.requested_kind`。

成人关系/性经历相关状态不随 kind 默认启用。只有在剧情明确需要、人物是成人、且该系统被开启时，才给人物添加 `sexual_history` 与 `reproductive_contents` components。

## component 初始 schema

### `health`

```json
{
  "condition": "healthy",
  "wounds": [],
  "stress": 0,
  "disease": ""
}
```

### `court_official`

```json
{
  "rank": "",
  "access_level": 1,
  "manages": []
}
```

### `economy_agent`

```json
{
  "wealth": 0,
  "income": 0,
  "debts": []
}
```

### `merchant`

```json
{
  "goods": [],
  "credit": 50,
  "route": "",
  "next_visit_hint": ""
}
```

### `envoy`

```json
{
  "home_faction": "",
  "authority": 0,
  "message": "",
  "negotiation_stance": "neutral"
}
```

### `diplomacy_agent`

```json
{
  "faction": "",
  "influence": 0,
  "grievances": [],
  "promises": []
}
```

### `noble`

```json
{
  "rank": "",
  "house": "",
  "honor": 0
}
```

### `combatant`

```json
{
  "unit_type": "",
  "skill": 20,
  "morale": 50,
  "equipment": []
}
```

### `craftsman`

```json
{
  "craft": "",
  "skill": 20,
  "workshop": "",
  "orders": []
}
```

### `prisoner`

```json
{
  "captor": "",
  "reason": "",
  "security_level": 1,
  "ransom": 0
}
```

### `spy`

```json
{
  "cover": "",
  "loyalty_to": "",
  "secrecy": 50,
  "known_secrets": []
}
```

### `sexual_history`

用途：统计人物的性经历和姿势统计。该 component 只记录结构化统计，不存放长篇情色文本；具体叙事仍由历史/事件系统记录。

```json
{
  "enabled": false,
  "adult_only": true,
  "total_partner_count": 0,
  "total_encounter_count": 0,
  "partners": {
    "char_2": {
      "character_id": "char_2",
      "name_snapshot": "奥托",
      "encounter_count": 0,
      "position_counts": {
        "missionary": 0,
        "standing": 0
      },
      "first_time": null,
      "last_time": null,
      "notes": []
    }
  },
  "position_totals": {
    "missionary": 0,
    "standing": 0
  },
  "last_encounter_time": null
}
```

字段要求：

- `total_partner_count`: 总共和多少人发生过关系，按 partner character id 去重。
- `total_encounter_count`: 总发生次数。
- `partners`: 所有发生过关系的人的分别记录。
- `partners.{id}.encounter_count`: 与该人物发生关系次数。
- `partners.{id}.position_counts`: 与该人物按姿势统计的次数。
- `position_totals`: 全部性爱姿势的总统计。
- `first_time/last_time/last_encounter_time`: 使用游戏内 `time_point`，不是现实时间。
- `notes`: 只记录简短事实标签或后果，不写长篇露骨文本。

姿势 id 第一阶段不硬编码在 Python 逻辑中，放到 registry/config：

```json
{
  "missionary": "正面",
  "standing": "站立",
  "rear": "背后",
  "oral": "口交",
  "anal": "肛交"
}
```

### `reproductive_contents`

用途：记录当前胃容物、肠道容物、子宫容物的来源，用于生育、怀孕、状态后果与描述一致性。该 component 只记录来源和时间，不做情色文本生成。

```json
{
  "stomach_contents": [
    {
      "content_type": "semen",
      "content_label": "精液",
      "source_character_id": "char_2",
      "source_name_snapshot": "奥托",
      "amount": 1,
      "received_time": null,
      "expires_time": null,
      "tags": []
    }
  ],
  "intestinal_contents": [
    {
      "content_type": "urine",
      "content_label": "尿液",
      "source_character_id": "char_2",
      "source_name_snapshot": "奥托",
      "amount": 1,
      "received_time": null,
      "expires_time": null,
      "tags": []
    }
  ],
  "uterine_contents": [
    {
      "content_type": "semen",
      "content_label": "精液",
      "source_character_id": "char_2",
      "source_name_snapshot": "奥托",
      "amount": 1,
      "received_time": null,
      "expires_time": null,
      "fertility_context": {
        "cycle_day": null,
        "pregnancy_check_due_time": null,
        "pregnancy_roll_resolved": false
      },
      "tags": []
    }
  ]
}
```

字段要求：

- `stomach_contents`: 当前胃容物，来源为其他人物 id。
- `intestinal_contents`: 当前肠道容物，来源为其他人物 id。
- `uterine_contents`: 当前子宫容物，来源为其他人物 id。
- `source_character_id`: 必须是人物账册中的非玩家人物 id，或允许特殊来源 id，例如 `external_unknown`。
- `content_type`: 当前内容物类型，必须来自 registry，MVP 包含：
  - `semen`: 精液
  - `urine`: 尿液
  - `food`: 食物
  - `water`: 水
  - `wine`: 酒
  - `medicine`: 药物
  - `poison`: 毒物
  - `blood`: 血液
  - `bile`: 胆汁
  - `parasite`: 寄生物
  - `unknown`: 未知内容物
- `amount`: MVP 用整数层级，不做体积单位。
- `expires_time`: 用于后续自动清理。
- `fertility_context`: 只对子宫容物有效，用于后续怀孕/生育系统衔接。

安全与一致性要求：

- `sexual_history` 与 `reproductive_contents` 只能用于成人人物；若 `identity.age < 18` 或 flags 标记为非成人，API 必须拒绝写入。
- 玩家/领主本人不在人物账册中，因此涉及玩家来源时不得伪造成 NPC；可使用 `source_character_id: "player_lord"` 作为特殊来源，但不得创建为 character entry。
- 所有统计更新必须通过专门 mutation 函数，不能由 Hermes 直接重写整块 component，避免计数不一致。

## 文件改动

### 新增目录

```text
backend/app/systems/characters/
  __init__.py
  schema.py
  registry.py
  factory.py
  selectors.py
  mutations.py
```

### 拆分职责

| 文件 | 职责 |
|---|---|
| `schema.py` | 默认字段、component normalize、旧 flat <-> 新结构兼容转换 |
| `registry.py` | `CHARACTER_KINDS`、`COMPONENT_DEFAULTS`、`SEX_POSITION_IDS`、成人内容默认过期策略 |
| `factory.py` | `create_character(state, kind, payload)`、`next_character_id` |
| `selectors.py` | list/get/find by name/faction/status/kind |
| `mutations.py` | update/patch/upsert、component patch、memory append、sexual encounter append、reproductive contents append/cleanup |
| `__init__.py` | 对外导出当前 `characters.py` 已有函数名，减少调用方改动 |

当前文件：

```text
backend/app/systems/characters.py
```

迁移后可删除，或保留为兼容 re-export shim：

```python
from .characters import *
```

如果 Python 包名和旧文件冲突，先创建 `backend/app/systems/character_system/`，再逐步迁移；完成后再移除旧文件。

## API 兼容要求

现有 API 必须继续可用：

```http
GET   /api/characters
GET   /api/characters/{character_id}
POST  /api/state/characters
PATCH /api/state/characters/{character_id}
```

新增 API：

```http
GET   /api/characters/kinds
POST  /api/state/characters/{character_id}/memory
PATCH /api/state/characters/{character_id}/components/{component_id}
POST  /api/state/characters/{character_id}/sexual-encounters
POST  /api/state/characters/{character_id}/reproductive-contents
POST  /api/state/characters/{character_id}/reproductive-contents/clear-expired
```

### `GET /api/characters/kinds`

返回：

```json
{
  "kinds": {
    "steward": {
      "label": "管家",
      "components": ["court_official", "economy_agent", "health"]
    }
  },
  "components": {
    "health": {
      "condition": "healthy",
      "wounds": [],
      "stress": 0,
      "disease": ""
    }
  }
}
```

### `POST /api/state/characters`

旧 payload 支持：

```json
{
  "name": "玛尔塔",
  "role": "管家",
  "description_md": "..."
}
```

### `POST /api/state/characters/{character_id}/sexual-encounters`

用途：追加一次性经历统计，并自动更新：

- `sexual_history.total_partner_count`
- `sexual_history.total_encounter_count`
- `sexual_history.partners.{partner_id}.encounter_count`
- `sexual_history.partners.{partner_id}.position_counts`
- `sexual_history.position_totals`
- `sexual_history.last_encounter_time`

请求：

```json
{
  "partner_character_id": "char_2",
  "partner_name_snapshot": "奥托",
  "position_id": "missionary",
  "count": 1,
  "time": null,
  "notes": ["剧情后果标签"],
  "created_by": "hermes"
}
```

规则：

- `character_id` 和 `partner_character_id` 不能相同。
- `partner_character_id` 可以是 `player_lord` 或 `external_unknown`，但真实 NPC 必须引用人物账册 id。
- 后端负责创建/初始化 `sexual_history` component。
- 后端负责累加计数，Hermes 不得直接 PATCH 整块统计来伪造累计结果。
- 如果 `position_id` 未知，API 拒绝或记录为 `unknown`，具体策略由 registry 配置决定。

### `POST /api/state/characters/{character_id}/reproductive-contents`

用途：追加当前胃容物、肠道容物、子宫容物。

请求：

```json
{
  "target": "uterus",
  "content_type": "semen",
  "source_character_id": "char_2",
  "source_name_snapshot": "奥托",
  "amount": 1,
  "received_time": null,
  "expires_time": null,
  "fertility_context": {
    "cycle_day": null,
    "pregnancy_check_due_time": null,
    "pregnancy_roll_resolved": false
  },
  "tags": [],
  "created_by": "hermes"
}
```

`target` 取值：

```text
stomach | intestine | uterus
```

写入映射：

| target | component 字段 |
|---|---|
| `stomach` | `reproductive_contents.stomach_contents` |
| `intestine` | `reproductive_contents.intestinal_contents` |
| `uterus` | `reproductive_contents.uterine_contents` |

规则：

- 后端负责初始化 `reproductive_contents` component。
- `amount` MVP 用整数层级。
- `uterus` 可附带 `fertility_context`；其他 target 忽略或拒绝该字段。
- 如果 `expires_time` 为空，后端可根据 target 使用默认过期时间。

### `POST /api/state/characters/{character_id}/reproductive-contents/clear-expired`

用途：按当前游戏时间清理已过期内容。

请求：

```json
{
  "now": null
}
```

返回清理数量：

```json
{
  "removed": {
    "stomach_contents": 1,
    "intestinal_contents": 0,
    "uterine_contents": 0
  }
}
```

新 payload 支持：

```json
{
  "kind": "steward",
  "name": "玛尔塔",
  "identity": {"role": "管家"},
  "profile": {"description_md": "..."},
  "components": {"court_official": {"access_level": 3}}
}
```

后端输出统一为新结构，但可以保留 flat alias 字段用于前端兼容：

```json
{
  "id": "char_1",
  "kind": "steward",
  "name": "玛尔塔",
  "identity": {},
  "profile": {},
  "relationship": {},
  "memory": {},
  "components": {},
  "flags": {},
  "role": "管家",
  "description_md": "..."
}
```

## Hermes profile / skill 更新

更新：

```text
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-character/SKILL.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-game/references/api_contract.md
/Users/ray/.hermes/profiles/lord-tail-ollama-gemma4-31b/skills/lord-tail-description/SKILL.md
```

要求：

- Hermes 创建人物时必须先判断 kind。
- 不知道 kind 时用 `commoner`。
- 更新人物状态时优先 PATCH 对应 component，不要重写整个人物。
- 重要记忆使用 memory append API，不要覆盖旧记忆。
- 描述人物时使用 `profile + relationship + memory + components`。
- 成人关系/性经历统计必须使用专门 API：
  - `POST /api/state/characters/{id}/sexual-encounters`
  - `POST /api/state/characters/{id}/reproductive-contents`
  - 不允许 Hermes 直接 PATCH `sexual_history` 计数，避免统计不一致。
- Hermes 在写入 `sexual_history` 或 `reproductive_contents` 前，必须确认目标人物是成人；不确定时不得写入，只能记录普通剧情事件或要求澄清。

## 前端改动

文件：

```text
frontend/src/api.ts
frontend/src/App.tsx
frontend/src/styles.css
```

要求：

- 人物面板展示 `kind`、`identity`、`relationship`、`components` 摘要。
- 兼容旧字段，不因为老存档没有新结构而崩溃。
- 增加 component 折叠展示，不做复杂编辑器。
- 成人关系/性经历 components 默认折叠显示。
- 前端第一阶段只做只读展示：
  - 总伴侣数
  - 总次数
  - 各姿势总统计
  - 各 partner 的次数/姿势次数
  - 当前胃容物/肠道容物/子宫容物的来源 id 摘要
- 不在第一阶段做手工编辑表单，所有写入由 Hermes 或后端 API 完成。

## 迁移规则

旧人物：

```json
{
  "role": "管家",
  "appearance_md": "...",
  "relationship_to_lord": "...",
  "memories": []
}
```

转换为：

```json
{
  "kind": "commoner",
  "identity": {
    "role": "管家"
  },
  "profile": {
    "appearance_md": "..."
  },
  "relationship": {
    "to_lord": "...",
    "disposition": 0
  },
  "memory": {
    "entries": []
  },
  "components": {
    "health": {
      "condition": "healthy",
      "wounds": [],
      "stress": 0,
      "disease": ""
    }
  }
}
```

如果 `role` 命中明显类型：

| role 包含 | kind |
|---|---|
| 管家 / 账房 / 总管 | `steward` |
| 商人 / 商队 | `merchant` |
| 使者 / 外交 | `envoy` |
| 骑士 / 贵族 | `knight` |
| 士兵 / 护卫 / 雇佣兵 | `soldier` |
| 工匠 / 铁匠 / 木匠 | `craftsman` |
| 俘虏 / 囚犯 | `prisoner` |
| 间谍 / 密探 / 线人 | `spy` |

## 实施步骤

1. 新建 character system 目录与 registry/component defaults。
2. 实现 `normalize_character_entry` 支持旧 flat 与新 structured 两种输入。
3. 实现 factory：
   - `create_character(state, kind, payload)`
   - `upsert_character`
   - `update_character`
4. 实现 selectors：
   - `list_characters`
   - `get_character`
   - `find_characters`
5. 实现 component mutation：
   - `patch_component`
   - `append_memory`
   - `append_sexual_encounter`
   - `append_reproductive_content`
   - `clear_expired_reproductive_contents`
6. 修改 `backend/app/api/schemas.py`：
   - 加 `kind`
   - 加 `identity/profile/relationship/memory/components`
   - 保留旧字段。
7. 修改 `backend/app/api/state.py`：
   - 接入 `GET /api/characters/kinds`
   - 接入 memory append
   - 接入 component patch
   - 接入 sexual encounter append
   - 接入 reproductive contents append/clear-expired
8. 修改 `backend/app/engine/hermes_context.py`：
   - context 中输出 compact characters structured 摘要。
   - action contract 加新增 API。
9. 修改 `backend/app/api/agent_tools.py`：
   - `describe-context target_type=character` 返回 structured character。
10. 修改前端人物面板，展示 structured 字段。
11. 修改 Hermes profile skill 与 API contract。
12. 补测试。

## 测试要求

新增或更新：

```text
backend/tests/test_characters.py
backend/tests/test_hermes_runs_backend.py
```

必须覆盖：

1. 旧 flat payload 创建后输出新结构。
2. 新 structured payload 创建 steward/merchant/knight。
3. 未知 kind 降级为 commoner。
4. PATCH 顶层 identity/profile/relationship。
5. PATCH 单个 component。
6. append memory 不覆盖旧记忆。
7. 禁止把领主本人写入人物账册。
8. `/api/agent/describe-context?target_type=character` 返回新结构。
9. sexual encounter API 能正确累计：
   - 总共和多少人发生过关系。
   - 总发生次数。
   - partner 分别次数。
   - partner 姿势次数。
   - 全局性爱姿势总统计。
10. reproductive contents API 能正确追加：
   - 当前胃容物。
   - 当前肠道容物。
   - 当前子宫容物。
   - 来源人物 id/name snapshot。
11. clear-expired 能按游戏时间清理过期内容。
12. 未成年或非成人标记人物写入 `sexual_history/reproductive_contents` 必须被拒绝。
13. Hermes auto approval 白名单允许：
   - `POST /api/state/characters`
   - `PATCH /api/state/characters/{id}`
   - `PATCH /api/state/characters/{id}/components/{component_id}`
   - `POST /api/state/characters/{id}/memory`
   - `POST /api/state/characters/{id}/sexual-encounters`
   - `POST /api/state/characters/{id}/reproductive-contents`
   - `POST /api/state/characters/{id}/reproductive-contents/clear-expired`

## 验证命令

```bash
cd /Users/ray/raylab/lord-tail
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests/test_characters.py backend/tests/test_hermes_runs_backend.py -q
PYTHONPATH=backend backend/.venv/bin/pytest backend/tests -q
cd frontend
npm run build
```

## 完成判定

- 当前 flat character API 不破坏。
- 新 structured character 输出稳定。
- Hermes context/profile 明确知道人物 kind、components、更新 API。
- 前端人物面板能展示旧人物与新人物。
- 全量后端测试通过，前端 build 通过。
