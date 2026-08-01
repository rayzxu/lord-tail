# Admin 内容管理后台使用与扩展

Lord Tail Admin 是独立于玩家前端与 Hermes 的本地内容工坊。它维护剧情图、Storylet、预设人物、人物类型/组件/属性、物品装备、身体部位、装备槽位和身体槽位预设；不会直接修改当前游戏存档。

## 启动

在项目根目录执行：

```bash
./start.sh
```

地址：

- 玩家界面：`http://127.0.0.1:5173`
- 游戏 API：`http://127.0.0.1:8000`
- 内容管理后台：`http://127.0.0.1:5174`
- Admin API 文档：`http://127.0.0.1:8001/admin-docs`

Admin 不再设置或要求登录 token，打开管理后台即可使用。为避免无鉴权写接口暴露到网络，Admin API 强制只接受本机请求，`start.sh` 也只允许绑定 `127.0.0.1`。可设置 `LORD_TAIL_ADMIN_ENABLED=false` 禁用管理端；端口通过 `LORD_TAIL_ADMIN_API_PORT` 和 `LORD_TAIL_ADMIN_UI_PORT` 修改。

## 日常维护流程

1. 在左侧选择内容类型，并打开正式内容详情确认引用影响。
2. 点击“编辑”创建草稿，或用稳定 id 新增内容。
3. 在图形/结构化表单中编辑；输入会自动保存到 `.content-admin/drafts/`，不会覆盖正式 JSON。
4. 点击“校验与预览”，修复所有阻止发布的错误，并检查剧情路径或人物/装备预览。
5. 查看 Diff，填写发布摘要，再发布。
6. 发布会取得文件锁、检查草稿和正式版本、重新校验、保留 revision 快照、原子替换 JSON 并通知游戏 API 热重载。
7. 将正式 JSON 的变化用 Git review/commit 保存。`.content-admin/` 是本地工作区，不提交到 Git。

如果另一草稿已先发布，同一 `base_revision` 的旧草稿会收到 `409 content_revision_conflict`，需要根据最新正式内容重新建立草稿后合并。

## 归档、删除与回滚

“归档”保留稳定 id，适合停用可能已被剧情、人物或存档引用的内容。硬删除必须先生成删除提案；只要全局定义或存档仍有入站引用，Admin 就会拒绝删除。不要用文件管理器绕过引用保护。

每次发布都写入 `.content-admin/revisions/rev_*/manifest.json`，审计写入 `.content-admin/audit.jsonl`。发布历史页可检查快照，API 支持把旧内容作为一个新的发布 revision 回滚。命令行可查看：

```bash
PYTHONPATH=backend backend/.venv/bin/python tools/export_admin_revision.py
PYTHONPATH=backend backend/.venv/bin/python tools/export_admin_revision.py rev_xxx
```

新建内容的首次发布若要撤销，应走引用安全删除，而不是回滚成“不存在”。

## 剧情图与 Storylet

剧情图使用 schema v2。图形编辑器采用可缩放、可平移的流程图画布，按拓扑 Level 将入口和根节点放在左侧、后续节点逐层向右、同层节点纵向排列；连接、断开或删除节点后会自动重新计算，也可点击“按 Level 排列”手动重排。画布仍支持拖动 `choice`、`automatic`、`timed`、`terminal` 节点微调位置；从节点或 choice 右侧的出口圆点拖到目标节点，会建立带箭头的连线并同步写入 `transition.to`。automatic Inspector 可维护过场展示方式、条件 JSON 和唯一整数 priority。选中箭头后按 Delete 可以断开连接。节点坐标保存在 `editor_layout`，不参与运行快照或 hash。发布前会复用游戏运行时 `analyze_graph()` 检查入口、条件、优先级、可达性、环、终点和关键裁断预算，并显示所有可选路径；发布 Story Arc 时版本号会自动递增。

Storylet 使用 schema v1。Admin 会把 `nodes` 自动渲染成节点导航和结构化表单，并按实际数据类型递归显示 `triggers`、角色选角规则、冻结参数、choices 和 effects；通常不再需要编辑 Nodes JSON。`triggers`、参数生成器、角色需求和 `effects.op` 必须来自后端白名单；`schedule_followup` 必须指向同 chain 存在的 `node_key`。预览只分析草稿，不推进时间、不改存档、不消耗 id。

扩展剧情 effect 时，先在确定性运行时注册并实现该操作，再加入配置；不要在 JSON 中放 Python/JavaScript 表达式或让 LLM 自由生成操作名。

## 人物、装备与身体

数据源如下：

- `backend/app/data/characters/registry.json`：六维属性、kind、component 默认值和人物系统枚举；
- `backend/app/data/characters/anatomy.json`：身体部位及父级/配对关系；
- `backend/app/data/characters/equipment_slots.json`：装备槽、别名和 common/male/female 预设；
- `backend/app/data/characters/presets/*.json`：预设人物；
- `backend/app/data/items.json`：物品与装备的正式定义。

装备的 `allowed_slots` 表示可以从哪个槽位发起装备，`occupied_slots` 表示最终同时占据的槽位。多槽装备、双手武器和依赖装备应完整声明；成人槽位装备必须显式设置 `adult_only: true`。预设人物只保存初始定义，不会追溯改写已经实例化的 NPC。

## 新增 ContentType

新增类型时需要同时完成：

1. 在 `backend/app/content/models.py` 注册稳定 type id；
2. 在 repository 的 keyed/file adapter 白名单中指定唯一落盘位置；
3. 在 `validation.py` 增加 schema、领域与跨引用校验；
4. 确保 Reference Index 能识别它引用和被引用的稳定 id；
5. 在 Admin `content-types`/schema 元数据中声明编辑器类型；
6. 在 `admin/src/editors/StructuredEditor.tsx` 增加专用 widget，仍保留高级 JSON 模式；
7. 增加本机访问限制、路径穿越、草稿冲突、失败回滚、存档兼容和 UI 测试。

Admin router 只能挂在 `app.admin_main`；禁止挂进 `app.main`，禁止加入 Hermes profile/tool/skill。

## 校验与排错

全注册表校验：

```bash
PYTHONPATH=backend backend/.venv/bin/python tools/validate_content_registry.py
```

若发布返回 `restart_required=true`，正式 JSON 已安全发布，但游戏 API 没确认热重载。检查游戏进程是否在 `8000`，以及 Admin 与游戏进程的 `LORD_TAIL_INTERNAL_CONTENT_TOKEN` 是否相同；修正后重启 `start.sh`。

若浏览器无法访问 Admin，检查进程是否监听 `127.0.0.1:8001`，不要改为局域网或公网地址。若配置校验失败，错误中的 `path` 会定位到字段；修改草稿，不要直接修 revision 快照。
