# 数据链路自检清单

本文档是**字段链路参考手册**，记录每个 AI 生成字段从「生成 → 存储 → 格式化 → 消费」的完整流转路径。
当 AI 执行 `docs/verify_protocol.md` 中的验证项时，需要查阅此文档了解链路细节。

> **接到需求时不要从这里开始读** —— 先读 `docs/workflow.md`（流程总纲）。本文件是事实底稿，不是执行流程。

**与其他文档的分工**：
- 参数值/硬编码常量/CSV 字段映射 → `docs/parameters.md`（权威来源）
- 流程图/数据流向图 → `docs/flowchart.md`
- AI 验证协议 → `docs/verify_protocol.md`
- 字段链路细节（生成→消费）→ 本文档

**覆盖范围**：
1. **AI 生成数据链路**：追踪字段从"AI 生成 → Pipeline 存储 → 格式化器提取 → 下游 Agent 消费"的全链路
2. **用户输入校验**：每个用户输入点的校验、防御和安全处理
3. **硬编码内容审计**：prompt 模板、常量字典、配置映射的正确性和一致性

> **维护规则**：每章末尾标注「最后验证时间」。每次代码变更并执行 verify_protocol 后，AI 必须更新对应章节的"最后验证时间"。

---

## 使用方法

1. 修改了 Agent prompt、pipeline 存储、context_manager 格式化、tracker 数据流中的任何一环后，按对应章节逐项检查
2. 每项检查包含：字段名 → 生成位置 → 存储位置 → 格式化位置 → 消费位置
3. **任何一环断裂（缺定义、缺存储、缺提取、缺注入），即为一类 bug**
4. **本文档与代码不一致时，以代码为准**——读者应当把本文档当成"路标"而非"事实"

---

## 一、Director 输出字段链路

> *最后验证：2026-05-21*

Director 输出 JSON 包含 5 个顶级 key：`world`、`characters`、`locations`、`outline`、`style`。

### 1.1 `world` 字段

| 子字段 | Prompt 定义 | Pipeline 存储 | _condense_world 提取 | 消费者 |
|--------|-----------|--------------|---------------------|--------|
| `setting` | director_system.txt `setting` | `state.world_data["setting"]` | ✅ `背景：{...}` | writer, reviewer, editor |
| `narrative_perspective` | director_system.txt `narrative_perspective` | `state.world_data["narrative_perspective"]` | ✅ `叙事视角：{...}` | writer（通过 `_build_system_prompt` 中 `style_guide.worldbuilding.exposition_style` 覆盖） |
| `unique_elements` | director_system.txt `unique_elements` | `state.world_data["unique_elements"]` | ✅ `世界特色：{...}`（最多 5 个） | writer |
| `rules` | director_system.txt `rules` | `state.world_data["rules"]` | ✅ `世界规则：{...}` | writer |
| `social_structure` | director_system.txt `social_structure` | `state.world_data["social_structure"]` | ✅ 提取 4 子字段 | writer |
| `geography.main_locations` | director_system.txt `geography` | `state.world_data["geography"]` | ✅ 提取地点名称（最多 5 个） | writer, tracker init |
| `geography.travel_routes` | director_system.txt `geography` | `state.world_data["geography"]` | ❌ 不在 _condense_world（由 tracker `_init_timeline` → `_extract_travel_routes` 提取到 `timeline.timeLogic.travelTimes.routes`） | tracker init |
| `factions` | director_system.txt `factions` | `state.world_data["factions"]` | ✅ 提取势力名称（最多 5 个） | writer |
| `history` | director_system.txt `history` | `state.world_data["history"]` | ✅ 提取前 3 条事件 | writer |
| `daily_life` | director_system.txt `daily_life` | `state.world_data["daily_life"]` | ✅ 提取所有非空子字段 | writer |
| `tone` | director_system.txt `tone` | `state.world_data["tone"]` | ✅ `整体基调：{...}` | writer, reviewer |
| `name` | director_system.txt `name` | `state.world_data["name"]` | ✅ `世界观：{...}`（_condense_world 首行） | writer |

### 1.2 `characters` 字段

| 子字段 | Prompt 定义 | Pipeline 存储 | _condense_world 提取 | 消费者 |
|--------|-----------|--------------|---------------------|--------|
| `name` | ✅ | `state.world_data["characters"][].name` | ✅ `角色：` 列表 | writer, reviewer, tracker |
| `role` | ✅ | `state.world_data["characters"][].role` | ✅ `（{role}）` 前缀 | writer |
| `aliases` | ✅ | `state.world_data["characters"][].aliases` | ❌ 不在 context 中（由 tracker 用于 auto_fix） | tracker `auto_fix` |
| `personality` | ✅ | `state.world_data["characters"][].personality` | ✅ 角色描述行 | writer, reviewer |
| `false_belief` | ✅ | `state.world_data["characters"][].false_belief` | ❌ 不在 _condense_world（由 tracker 心理深度模块使用） | tracker psychology |
| `want` | ✅ | `state.world_data["characters"][].want` | ❌ 同上 | tracker psychology |
| `need` | ✅ | `state.world_data["characters"][].need` | ❌ 同上 | tracker psychology |
| `ghost` | ✅ | `state.world_data["characters"][].ghost` | ❌ 同上 | tracker psychology |
| `voice` | ✅ | `state.world_data["characters"][].voice` | ❌ 不在 _condense_world（由 tracker `consistency.speechPatterns` 使用） | tracker |
| `appearance` | ✅ | `state.world_data["characters"][].appearance` | ❌ 不在 _condense_world（由 tracker `consistency.physicalTraits` 使用） | tracker |
| `growth_plan` | ✅ | `state.world_data["characters"][].growth_plan` | ❌ 不在 _condense_world（由 tracker L3 分析参考） | tracker |
| `abilities` | ✅ | `state.world_data["characters"][].abilities` | ❌ 不在 _condense_world（由 tracker `consistency` 参考技能/能力一致性） | tracker |
| `background` | ✅ | `state.world_data["characters"][].background` | ✅ `_condense_world` 角色行末 `[背景：childhood；growth；key_events；turning_point]` | writer, reviewer |

### 1.3 `locations` 字段

| 子字段 | Prompt 定义 | Pipeline 存储 | context 流转 | 消费者 |
|--------|-----------|--------------|-------------|--------|
| `name` | ✅ | `state.world_data["locations"][].name` | tracker `get_tracking_context` → `场景地点` 块 | writer, editor |
| `type` | ✅ | 同上 | ✅ | writer |
| `five_senses` | ✅ | 同上 | ✅ 匹配当前地点时输出 | writer |
| `atmosphere` | ✅ | 同上 | ✅ | writer |
| `function` | ✅ | 同上 | ✅ | writer |

**检查点**：`pipeline.py` Phase 1 中 `if "locations" in result` 是否存在。

### 1.4 `outline` 字段

| 子字段 | Prompt 定义 | Pipeline 存储 | _condense_outline 提取 | 消费者 |
|--------|-----------|--------------|----------------------|--------|
| `theme` | ✅ | `state.outline["theme"]` | ✅ `主题：{...}` | writer |
| `three_act` | ✅ | `state.outline["three_act"]` | ✅ 逐幕输出 | writer |
| `ending` | ✅ | `state.outline["ending"]` | ✅ `结局方向：{...}` | writer |
| `key_turning_points` | ✅ | `state.outline["key_turning_points"]` | ✅ `关键转折点：{...}` | writer |

### 1.5 `style` 字段

| 子字段 | Pipeline 存储 | 说明 |
|--------|-------------|------|
| `style.target_words_per_chapter` | `state.outline["style"]` | 仅保存，不直接消费 |

---

## 二、Plotter 输出字段链路

> *最后验证：2026-05-21*

Plotter 为每章生成一个 JSON 对象，存入 `state.chapter_plans[]`。

### 2.1 章节计划字段

| 字段 | Prompt 定义 | _format_chapter_plan 提取 | 消费者 |
|------|-----------|--------------------------|--------|
| `chapter_number` | ✅ | ❌（不在 context 文本中，由 pipeline 索引使用） | pipeline |
| `title` | ✅ | ✅ `章节标题：{...}` | writer |
| `summary` | ✅ | ✅ `概要：{...}` | writer |
| `plot_points` | ✅ | ✅ `剧情要点：` 列表 | writer, tracker (L1 `appearanceTracking`) |
| `emotional_arc` | ✅ | ✅ `情绪线：{...}` | writer |
| `emotional_type` | ✅ | ✅ `情绪类型：{...}` | writer |
| `emotional_intensity` | ✅ | ✅ `情绪强度：{...}` | writer |
| `characters_involved` | ✅ | ✅ `出场角色：{...}` | writer, tracker (同场角色双向关系) |
| `foreshadowing` | ✅ | ✅ `伏笔：` 列表（含 visibility + planned_reveal） | writer |
| `active_plotlines` | ✅ | ✅ `活跃线索：{...}` | writer |
| `act` | ✅ | ✅ `所属幕：{...}` | writer |
| `cliffhanger` | ✅ | ✅ `章节钩子：{...}` | writer |
| `scene_structure` | ✅ | ✅ `场景结构：{...}` | writer |
| `tension_level` | ✅ | ✅ `张力等级：{...}` | writer, tracker (L1 checkpoints) |
| `location` | ✅ | ✅ `场景地点：{...}` | writer, tracker (L1 currentState) |
| `time` | ✅ | ✅ `故事时间：{...}` | writer, tracker (L1 timeline) |
| `duration` | ✅ | ❌（不在 _format_chapter_plan，但被 tracker `_init_timeline` 消费为 `timeline.events[].duration`） | tracker |

**检查点**：新增 plotter 输出字段后，需同步检查：
1. `plotter_system.txt` 的 JSON schema 是否包含该字段
2. `_format_chapter_plan` 是否格式化该字段
3. tracker 的 `update_tracking` 是否消费该字段

---

## 三、Tracker 数据链路

> *最后验证：2026-05-21*

### 3.1 追踪文件初始化

pipeline.py Phase 2.5 检查 **全部 6 个** `_TRACKING_FILES` + 独立检查 `config.json`：

```
_TRACKING_FILES: character_state.json, timeline.json, plot_tracker.json,
relationships.json, validation_rules.json, locations.json

独立检查: config.json（不在 _TRACKING_FILES 中，不在 snapshot 范围内，但初始化必须生成）
```

**检查点**：`missing = [f for f in Tracker._TRACKING_FILES if not tracker._read_json(f)]` + `config_missing = not tracker._read_json("config.json")` 是否覆盖全部文件。

### 3.2 L1 零成本更新（update_tracking）

从 `chapter_plan` 和 `chapter_text` 字符串匹配提取：

| 目标 | 来源 | 方法 |
|------|------|------|
| `appearanceTracking.significance` | 角色名在 `plot_points` 中出现 | 字符串匹配 |
| `currentState.location/timepoint/mainPlotStage` | `chapter_plan` 字段 | 字段直接读取 |
| `checkpoints.majorEvents` | `tension_level == "high"` | 条件判断 |
| `timeline.events` | `chapter_plan.time` + `chapter_plan.summary` | 字段提取 |
| `character_state.lastSeen` | 角色名在正文中出现 | 字符串包含检查 |
| `locations` 匹配更新 | `chapter_plan.location` 匹配已有地点 | 字符串匹配更新 `lastSeen` |
| `relationships.dynamicRelations` | 同场 `characters_involved` 角色对 | 双向关系自动记录 |
| `protagonist skills/knowledge` | 正文中的技能/知识使用 | 无（仅 L3 分析时更新） |

**检查点**：新增 chapter_plan 字段后，`update_tracking` 是否读取并写入对应追踪文件。

### 3.3 L2 Reviewer 输出消费（_consume_review）

`_consume_review` 接收 reviewer 输出的 `tracking_updates` 字段，更新 5 个追踪文件：

| 目标文件 | reviewer 输出源 | 写入触发 |
|---------|----------------|---------|
| `character_state` | `tracking_updates.character_changes` | `char_changed` 标记 |
| `plot_tracker` | `tracking_updates.conflict_updates` / `foreshadowing_updates` | `plot_changed` 标记 |
| `timeline` | `tracking_updates.timeline_updates` | `timeline_changed` 标记 |
| `relationships` | `tracking_updates.relationship_changes` | `rel_changed` 标记 |
| `validation_rules` | `reviewer.consistency_checks` | `rules_changed` 标记 |

**检查点**：
- 每个追踪文件只在对应 `*_changed` 标记为 True 时写入（避免无效 I/O）
- timeline 写入在循环外（避免重复写入）

### 3.4 get_tracking_context 输出块

该方法构建追踪上下文字符串，注入 writer/reviewer/editor/critic。输出块清单：

| 输出块 | 数据源 | 受 disabled_checks 控制 |
|--------|--------|----------------------|
| 角色状态追踪 | `character_state.json` | ✅ `character` |
| 角色状态分组 | `character_state.characterGroups` | ✅ `character` |
| 一致性警告 | `character_state.consistency.warnings` | ✅ `character` |
| 角色详细状态 | `character_state.consistency.{physicalTraits,personalityTraits,speechPatterns}` | ✅ `character` |
| 角色心理深度 | `character_state.psychology` | ✅ `character` |
| 近期时间线 | `timeline.events` | ✅ `timeline` |
| 时间异常 | `timeline.anomalies.issues` | ✅ `timeline` |
| 时间约束 | `timeline.timeLogic` | ✅ `timeline` |
| 活跃伏笔 | `plot_tracker.foreshadowing` | ✅ `worldbuilding` |
| 活跃冲突 | `plot_tracker.conflicts.active` | ✅ `worldbuilding` |
| 已解决冲突 | `plot_tracker.conflicts.resolved` | ✅ `worldbuilding` |
| 剧情问题记录 | `plot_tracker.notes` | ✅ `worldbuilding` |
| 角色关系 | `relationships.characters` | ❌ 始终输出 |
| 动态关系变化 | `relationships.dynamicRelations` | ❌ 始终输出 |
| 审核严格度 | `config.strictness` | ❌ 始终输出 |
| 场景地点 | `locations.json` | ✅ `locations` |
| 场景五感参考 | `locations[].five_senses`（匹配当前地点） | ✅ `locations` |
| 场景氛围指南 | `locations.scene_atmosphere_guide` | ✅ `locations` |

---

## 四、Context 构建链路

> *最后验证：2026-05-21*

### 4.1 build_running_context 组装

```
FULL_CONTEXT_TEMPLATE:
  ## 世界观与角色参考    ← _condense_world(world_data)
  ## 故事主线            ← _condense_outline(outline)
  ## 前文摘要            ← _format_summaries(completed_summaries)
  ## 追踪数据            ← get_tracking_context(chapter_num)
  ## 当前章节剧情要点    ← _format_chapter_plan(plan)
```

**检查点**：新增字段时，确认它在上述哪个环节被提取。如果字段在 `_condense_*` 或 `_format_*` 中缺失，下游 Agent 永远看不到它。

### 4.2 上下文注入点

`tracking_context` 注入以下 Agent：

| Agent | 注入方式 | 位置 |
|-------|---------|------|
| Writer | `running_context` 的一部分 | pipeline.py `_write_chapters` → `writer.run(plan, running_ctx)` |
| Reviewer | 独立参数 `tracking_context` | pipeline.py `_write_chapters` → `reviewer.run(..., tracking_context=tracking_ctx)` |
| Editor | 独立参数 `tracking_context` | pipeline.py `_edit_chapters` → `editor.run(..., tracking_context=tracking_ctx)` |
| Critic | 独立参数 `tracking_context` | pipeline.py `revise_chapter` → `critic.run(..., tracking_context=tracking_ctx)` |

---

## 五、Style Guide 分发链路

> *最后验证：2026-05-21*

> **本节内容已迁移至 `docs/parameters.md` 第四章「风格指南」+「STYLE_FIELDS 分发过滤」表格**。
> 那里是 STYLE_FIELDS 字段分发的权威来源，含每个 Agent 收到的字段列表。
>
> 检查点（保留在此处）：
> - `_agent_name()` 返回值是否在 `STYLE_FIELDS` 中有对应条目
> - PlotAgent 的 `_agent_name()` 应返回 `"plotter"`（由 `_AGENT_CONFIG_KEYS` 映射，而不是 `"plot"`）
> - 修改 STYLE_FIELDS 后，需同步更新 parameters.md 第四章

---

## 六、Writer 特殊链路

> *最后验证：2026-05-21*

### 6.1 叙事视角

```
数据流：director_system.txt 生成 narrative_perspective
  → state.world_data["narrative_perspective"]
  → _condense_world 提取到 running_context
  → 同时：style_guide.worldbuilding.exposition_style（由 StyleAdvisor 生成）
  → writer._build_system_prompt 中优先使用 style_guide 版本
```

**检查点**：`narrative_perspective` 有两条路径传递给 writer——context 文本和 system prompt 占位符。确保两条路径数据一致。

### 6.2 字数续写

```
writer.run → chat() → 检查 len(text) < words_min * 0.9 → chat_with_history 续写
```

**检查点**：`0.9` 阈值硬编码在 `writer.py` 中。

### 6.3 重写续写

```
writer.rewrite → _build_system_prompt(is_rewrite=True) → chat(temperature=min(base+0.15, 0.9))
              → 检查 len(text) < words_min * 0.9 → chat_with_history 续写（同 rewrite_temp）
```

**说明**：`rewrite` 方法同样具备字数不足续写逻辑，与 `run` 方法一致。重写时因上下文精简（只传审稿意见+草稿，不重复传 running_context），续写时可能偏离原文风格。

**rewrite 三重组合（#62 修复）**：
1. **System 增强**：`_build_system_prompt(is_rewrite=True)` 在 system prompt 尾部追加"## 重写专项要求"段，强调实质性改写被指出问题的段落而非字面微调，并严格保留 strengths 标注的优秀内容
2. **User msg 增强**：尾部追加"请实际修复问题，避免只做表面调整"示例（如"对话单调"需重新设计对话表达）
3. **升温**：`rewrite_temp = min(self._temperature() + 0.15, 0.9)`，比初稿温度上调 0.15（封顶 0.9，防止过度发散导致风格漂移）

**检查点**：重写后的续写质量是否受精简上下文影响；rewrite 温度上限 0.9 是硬编码在 `agents/writer.py` `rewrite()` 中。

---

## 七、程序化检查链路

> *最后验证：2026-05-21*

### 7.1 写作循环中的检查（pipeline `_write_chapters`）

| 检查 | 数据来源 | 修改/仅报告 |
|------|---------|-----------|
| `auto_fix`（角色名别名修正） | `tracker.auto_fix(draft, ch_num)` | 修改文本 |
| `auto_fix_banned_words`（禁用AI词） | `tracker.auto_fix_banned_words(draft, style_guide)` | 修改文本 |
| `check_cliches`（陈词滥调） | `tracker.check_cliches(draft)` | 仅报告 |
| `check_sentence_patterns`（句式） | `tracker.check_sentence_patterns(draft)` | 仅报告 |
| `check_abstract_nouns`（抽象名词） | `tracker.check_abstract_nouns(draft)` | 仅报告 |

### 7.2 修订流程中的检查（pipeline `_execute_revise`）

应包含与写作循环相同的 5 项检查。**检查点**：确认修订流程不遗漏任何检查。

---

## 八、修订流程数据链路

> *最后验证：2026-05-21*

```
revise_chapter → critic.run → _select_idea → _execute_revise
  → writer.rewrite → reviewer.run → [retry once] → editor.run
  → auto_fix → auto_fix_banned_words → check_cliches/sentence/abstract
  → update_tracking(review=review) → update_from_review → log_changes_csv
```

**检查点**：
- `update_tracking` 是否传入 `review` 参数（L2 消费）
- 程序化检查（auto_fix 等）是否完整
- `ch.review_status` / `ch.review_notes` 是否更新
- `ch.summary` 是否重新生成
- `log_changes_csv` source 参数是否为 `"revise"`

---

## 九、变更自检操作步骤

> *最后验证：2026-05-21*

### 步骤 1：Prompt 变更检查

如果修改了 `prompts/*.txt`：

1. 在 prompt JSON schema 中找到新增/修改的字段名
2. 到 `pipeline.py` 找到该 Agent 的 Phase，确认输出被存储（搜索 `state.xxx`）
3. 到 `context_manager.py` 找到对应 `_condense_*` / `_format_*` 方法，确认新字段被提取
4. 到消费 Agent 的 prompt 确认它确实需要这个字段

### 步骤 2：Pipeline 存储变更检查

如果修改了 `pipeline.py` 的存储逻辑：

1. 确认 `state.world_data` / `state.outline` / `state.chapter_plans` 的写入点
2. 确认 `state_mgr.save(state)` 在正确的位置被调用
3. 确认 JSON 文件（world.json / outline.json / chapters.json）同步写入

### 步骤 3：格式化器变更检查

如果修改了 `context_manager.py`：

1. 在 `_condense_world` 中按字段逐一确认：是否有 `if "xxx" in world_data` 保护
2. 在 `_format_chapter_plan` 中确认字段列表与 plotter prompt schema 一致
3. 在 `_condense_outline` 中确认与 director prompt schema 一致
4. 测试：传入空 dict，确认不会 KeyError

### 步骤 4：Tracker 变更检查

如果修改了 `tracker.py`：

1. `_consume_review`：每个追踪文件的写入是否有布尔标记控制（避免无效写入）
2. `update_tracking`：`char_state` 等文件是否只读取一次（避免重复读取）
3. `get_tracking_context`：新增输出块是否受 `disabled_checks` 控制
4. `init_tracking`：所有必要字段是否从 world_data / outline / chapter_plans 初始化

### 步骤 5：全链路验证

对每个新增/修改字段，回答以下 4 个问题：

```
[ ] ① Prompt 中是否要求 AI 输出该字段？
[ ] ② Pipeline 是否存储该字段到 state / JSON 文件？
[ ] ③ 格式化器是否提取该字段到 context 文本？
[ ] ④ 下游 Agent（writer/reviewer/editor）是否能消费到该字段？
```

**任何一项为 ❌ 即为 bug。**

### 步骤 5.1：死字段判定规则（关键）

当发现字段"有生成、有存储，但无消费者"时：

```
⛔ 禁止：直接从 prompt 中删除该字段
✅ 正确：分析该字段应在哪里被消费，然后补全消费逻辑
```

**判断流程**：

```
发现无消费字段
  ↓
1. 该字段是否对 Writer/Reviewer/Editor 有用？
   → 是：在 _condense_world / _format_chapter_plan 中添加提取
   ↓
2. 该字段是否属于追踪系统范畴？
   → 是：在 tracker 的 init / update / _consume_review 中添加写入
   ↓
3. 该字段是否属于 pipeline 流程控制？
   → 是：在 pipeline.py 的对应阶段添加消费逻辑
   ↓
4. 确认无人需要 → 在 prompt 中标注"仅供存档"，
   或在 self_check.md 中记录为"有意不消费"并说明理由
```

**原则**：AI 生成的每个字段都是 token 成本。如果值得让 AI 生成，就值得被正确消费。只有经过上述 4 步确认后，才可标记为"有意不消费"。

### 步骤 6：文档同步检查

代码变更完成后，逐项确认以下文档是否需要同步更新：

| 文档 | 触发条件 | 需要更新的内容 |
|------|---------|--------------|
| `docs/parameters.md` | 新增/修改 config 参数、新增 bug fix、新增追踪字段、新增常量 | 参数表 + bug fix 记录 + 字段数 + CSV 格式 |
| `docs/flowchart.md` | 修改数据流、新增存储环节、新增 Agent 交互 | 数据流图 + 写作循环图 + 文件结构 |
| `README.md` | 新增功能、修改架构、修复 bug、修改依赖 | 架构图 + 核心特性 + 变更日志 + 项目结构 + 配置说明 |
| `requirements.txt` | 新增/升级依赖 | 添加包 + 版本约束 |
| `docs/self_check.md` | 新增追踪文件、新增硬编码字典、新增 prompt schema、新增输入点 | 对应章节的清单更新 |

**快速判断规则**：

```
改了 prompt schema？      → parameters.md + self_check.md (十八章)
改了 pipeline 存储？      → flowchart.md + parameters.md
改了 context_manager？    → self_check.md (第一~四章) + parameters.md (字段数)
改了 tracker？           → self_check.md (第三/七/十八章) + parameters.md
改了 config.yaml？       → parameters.md + README.md
新增了依赖？             → requirements.txt + README.md
修复了 bug？             → parameters.md (bug fix 记录) + README.md (变更日志)
新增了用户输入点？        → self_check.md (第十七章)
新增了硬编码字典/常量？   → self_check.md (第十八章) + parameters.md
改了 ui.py / name_generator.py？ → self_check.md (第十九章) + parameters.md (第八章硬编码) + README.md
```

#### 自检文档自评

代码变更后还需要回过头检查：**本次变更是否暴露了自检文档本身的覆盖盲区？**

| 变更类型 | 自检文档是否需要新增/调整章节 |
|---------|---------------------------|
| 新增 Agent | 需要新建字段链路章节（参照第一/二章格式），更新第五章 STYLE_FIELDS、第十八章 schema 对齐表 |
| 新增追踪文件 | 需要更新第三章追踪链路表、第十六章速查表、第十八章 `_TRACKING_FILES` 检查点 |
| 新增用户输入点 | 需要更新第十七章输入点全览表 |
| 新增硬编码字典 | 需要更新第十八章同步维护点列表、第十六章速查表 |
| 新增故障模式 | 需要补充到第十六章速查表 |
| 修改了阶段/流程 | 需要更新第十二章状态机转换图、第十五章边界场景 |
| 新增了文档文件 | 需要更新本表的文档列表 |

如果以上任一项为"是"，说明自检文档本身需要先更新，再用于后续自检。

---

## 十、LLM 输出健壮性

> *最后验证：2026-05-21*

AI 不一定严格按 schema 输出，每个 Agent 的 LLM 调用点都需要防御性处理。

### 10.1 JSON 返回类型校验

| Agent | 调用方法 | 期望类型 | 当前防护 |
|-------|---------|---------|---------|
| StyleAdvisor | `chat_json` | `dict` | ✅ `if not isinstance(result, dict)` → return `{}` |
| Director | `chat_json` | `dict` | ✅ `if not isinstance(result, dict)` → return `{}`（#50） |
| Plotter | `chat_json` | `list[dict]` | ✅ `if isinstance(result, dict) and "chapters" in result` 解包；`if not isinstance(result, list)` raise |
| Reviewer | `chat_json` | `dict` | ✅ `if not isinstance(result, dict)` → 返回安全默认 dict（含 approved/issues/consistency_checks 等字段）（#50） |
| Critic | `chat_json` | `dict` | ✅ `if isinstance(result, dict)` 检查 |

**检查点**：新增 Agent 使用 `chat_json` 时，必须验证返回类型。

### 10.2 JSON 截断处理

`chat_json` 检测 `stop_reason == "max_tokens"` 时调用 `_continue_json`。

`_continue_json` 的策略是**要求完整重试**（不是拼接），最多重试 `max_continuations=3` 次。

**风险点**：
- 如果 LLM 反复截断（超长输出），3 次重试后返回截断的原文 → `parse_json` 失败 → ValueError 向上传播
- Director 输出结构庞大（世界观+角色+地点+大纲），最容易被截断

**检查点**：如果 prompt schema 变得更复杂，评估是否需要在 prompt 中强调"输出简洁 JSON"。

### 10.3 文本续写上下文拼接

`_continue_text` 通过 `chat_with_history` 拼接：

```
messages = [
  {"role": "user", "content": 原始prompt},
  {"role": "assistant", "content": 已有文本},
  {"role": "user", "content": "请继续写..."},
]
```

**风险点**：续写时 context 不再包含 running_context 全文（只有 system_prompt），如果 writer 的 system_prompt 不够完整，续写可能偏题。

### 10.4 parse_json 容错

```
parse_json 处理链：
  1. 去除 markdown code fence
  2. 尝试直接 json.loads
  3. 提取第一个 { 到最后一个 } 之间的文本再试
  4. 提取第一个 [ 到最后一个 ] 之间的文本再试
  5. 全部失败 → raise ValueError
```

**检查点**：如果 LLM 在 JSON 前后输出了解释文字，步骤 3/4 能兜住。但如果 JSON 本身语法错误（缺逗号、多余逗号），parse_json 不会修复。

---

## 十一、状态持久化完整性

> *最后验证：2026-05-21*

### 11.1 NovelState save/load 往返

`NovelState` 是 dataclass，通过 `asdict()` 序列化、`NovelState(**data)` 反序列化。

**兼容性风险**：

| 场景 | 行为 | 影响 |
|------|------|------|
| 新增字段（有默认值） | ✅ 旧 state 无该字段，`__init__` 使用默认值 | 安全 |
| 新增字段（无默认值） | ❌ `NovelState(**data)` 缺少参数 → TypeError | 必须加默认值 |
| 删除字段 | ❌ `NovelState(**data)` 收到未知参数 → TypeError | 必须在 `StateManager.load` 中过滤掉旧字段 |
| 重命名字段 | ❌ 旧 state 中旧名字段被忽略，新名字段取默认值 | 数据丢失 |

**检查点**：修改 `NovelState` 或 `ChapterState` 的字段时：
- 新增字段必须给默认值
- 删除字段需要在 `StateManager.load` 中过滤（已修复：load 使用 `__dataclass_fields__` 白名单过滤）
- 重命名字段需要迁移逻辑（在 `StateManager.load` 中处理）

### 11.2 原子写入

```python
# state_manager.py save()
tmp_path.write_text(...)
tmp_path.replace(state_path)  # 原子 rename
```

**检查点**：所有关键写入是否都用了 tmp + rename 模式。当前 state 用了，但 `world.json` / `outline.json` / `chapters.json` 是直接写入——如果写入过程中断电，文件可能损坏。

### 11.3 断点续写覆盖检查

| Phase 入口 | 恢复条件 | 前置依赖 |
|-----------|---------|---------|
| `styling` | `state.phase == "styling"` | 无 |
| `collecting_params` | `state.phase == "collecting_params"` | `state.style_guide` |
| `directing` | `state.phase == "directing"` | `state.style_guide` + `state.total_chapters` |
| `plotting` | `state.phase == "plotting"` | `state.world_data` + `state.outline` |
| `writing` | `state.phase == "writing"` | `state.chapter_plans` + 追踪文件 |
| `editing` | `state.phase == "editing"` | `state.chapters[].draft_path` 存在 |

**风险点**：`resume_novel` 调用 `_apply_style_temperatures`（恢复温度覆盖），但不恢复 `_apply_strictness`（严格度在 Phase 2.5 设置）。如果从 writing 中段恢复，严格度已在 tracking/config.json 中持久化，不会丢失。

**检查点**：新增 phase 时确认 `resume_novel` 能正确恢复所有前置状态。

---

## 十二、Pipeline 状态机

> *最后验证：2026-05-21*

### 12.1 阶段转换图

```
styling → collecting_params → directing → refining → plotting → writing → editing → complete
                                              ↑                     ↑
                                         Phase 1.5            Phase 2.5
                                       (用户分块打磨)         (追踪初始化)
```

每个 phase 用 `if state.phase == "xxx"` 守卫，顺序排列在 `_run_pipeline` 中。通过后设置 `state.phase = "next_phase"` 并 save。

### 12.2 阶段跳跃安全性

`resume_novel` 从任意 phase 入口恢复。**跳跃规则**：

| 跳到 | 是否安全 | 原因 |
|------|---------|------|
| styling | ✅ | 重新生成 style_guide |
| collecting_params | ✅ | 重新收集参数 |
| directing | ✅ | 重新生成世界观 |
| refining | ✅ | 已确认的 block 通过 `state.refined_blocks` 跳过，未确认的从断点续上 |
| plotting | ✅ | 重新生成章节计划 |
| writing（从中间章节） | ✅ | `current_chapter` 索引从 i 继续 |
| editing（从中间章节） | ✅ | 同上 |

**风险点**：不能跳过 writing 直接进入 editing——draft 文件不存在。

### 12.3 Phase 2.5 幂等性

Phase 2.5 的初始化检查：

```python
missing = [f for f in Tracker._TRACKING_FILES if not tracker._read_json(f)]
config_missing = not tracker._read_json("config.json")
if missing or config_missing:
    targets = list(missing) + (["config.json"] if config_missing else [])
    tracker.init_tracking(state.world_data, state.outline, state.chapter_plans, missing=targets)
    tracker._apply_validation_level(...)  # 根据 genre strictness 设置校验严格度
```

**检查点**：
- 已存在的文件不会被覆盖（幂等）
- ✅ **已修复 #49**：`init_tracking(missing=None)` 时仅初始化磁盘上不存在的文件；pipeline 显式传入 missing 列表，确保从 writing 中段恢复且部分文件缺失时已存在文件不被覆盖
- `_apply_validation_level` 根据 `_GENRE_STRICTNESS` 映射设置 `config.json` 的 `strictness` 和 `disabled_checks`

### 12.4 写作循环中断恢复

```python
for i in range(state.current_chapter, state.total_chapters):
    ch = state.chapters[i]
    # Stage 1: Writer draft（ch.stage in {drafted, reviewed, tracked} 且草稿文件存在 → 跳过）
    ...
    ch.stage = "drafted"; self.state_mgr.save(state)
    # Stage 2: Review loop（ch.stage in {reviewed, tracked} → 跳过，复用 review_notes）
    ...
    ch.stage = "reviewed"; self.state_mgr.save(state)
    # Stage 3: Summary + update_tracking + L3 + log_changes_csv（ch.stage == "tracked" → 跳过）
    ...
    ch.stage = "tracked"; self.state_mgr.save(state)

    state.current_chapter = i + 1
    state.phase = "writing"
    self.state_mgr.save(state)
```

**章内 stage 状态机**（`ChapterState.stage`）：

```
pending → drafted → reviewed → tracked
            ↑          ↑          ↑
         writer 完成 审核循环结束 update_tracking 完成
```

每段完成后保存 state（包含 stage 字段），保证中断恢复时可以从最细粒度跳过已完成段。

**检查点**：如果中断发生在 `update_tracking` 之后、`ch.stage = "tracked"` 之前——下次恢复会进入 Stage 3 重跑 `update_tracking`。`tracker.update_tracking` 已对 `appearanceTracking / majorEvents / completedNodes / locations.events` 加入"同章不重复追加"检查（`any(e.get("chapter") == chapter_num for e in lst)`），重跑幂等无副作用。

---

## 十三、Config 消费审计

> *最后验证：2026-05-21*

> **本节内容已迁移至 `docs/parameters.md`**：
> - config.yaml 字段消费清单 → `parameters.md` 第一章 + 第二章 + 第三章
> - 硬编码常量审计 → `parameters.md` 第八章「LLM 客户端与 pipeline 行为参数」
>
> 修改 config.yaml 或硬编码常量后，需同步更新 parameters.md 对应章节。

---

## 十四、Reviewer 输出全量消费

> *最后验证：2026-05-21*

Reviewer 返回一个完整 JSON，包含 7 个顶级字段。每个字段都必须被正确消费。

### 14.1 字段消费清单

| 字段 | 类型 | 消费位置 | 消费方式 |
|------|------|---------|---------|
| `approved` | bool | `pipeline.py` `_write_chapters` | 控制 rewrite 循环退出 |
| `issues[]` | list | `pipeline.py` `_write_chapters` | 提取 major → 构建 feedback → 传给 `writer.rewrite` |
| `consistency_checks` | dict | `tracker.py` `_consume_review` | 6 个子字段逐一消费（见下表） |
| `consistency_score` | int | `pipeline.py` `_write_chapters` | 被 `tracker.calculate_consistency_score` 重写覆盖 |
| `auto_fix_suggestions[]` | list | `pipeline.py` `_write_chapters` | confidence ≥ 0.9 时执行 `replace(original, suggested, 1)` |
| `overall_quality` | int | `pipeline.py` `_write_chapters` | 仅打印展示，不进入后续逻辑 |
| `strengths[]` | list | `pipeline.py` `_write_chapters` + `_execute_revise` | 注入 rewrite 反馈，告诉 writer 哪些部分要保留 |
| `tracking_updates` | dict | `tracker.py` `update_from_review` | 5 个子字段逐一消费（见下表） |

### 14.2 consistency_checks 子字段消费

| 子字段 | tracker 消费 | 写入目标 |
|--------|-------------|---------|
| `character_issues` | `_consume_review` | `plot_tracker.notes` + `character_state.consistency.warnings` |
| `world_issues` | `_consume_review` | `plot_tracker.notes.plotHoles/inconsistencies` |
| `timeline_issues` | `_consume_review` | `timeline.anomalies.issues` |
| `physical_traits_issues` | `_consume_review` | `character_state.consistency.warnings` |
| `personality_issues` | `_consume_review` | `character_state.consistency.warnings` |
| `knowledge_state_issues` | `_consume_review` | `character_state.consistency.warnings` |

**检查点**：如果 reviewer prompt 新增 consistency_checks 子字段，需确认 `_consume_review` 有对应处理。

### 14.2.1 auto_fix_suggestions 消费详情

`auto_fix_suggestions` 在 pipeline `_write_chapters` 中被消费：

```python
for fix in review.get("auto_fix_suggestions", []):
    if fix.get("confidence", 0) >= 0.9:
        text = text.replace(fix["original"], fix["suggested"], 1)
```

- 仅 `confidence ≥ 0.9` 的建议会被自动执行（高置信度）
- `replace` 使用 `count=1` 避免全局替换误伤
- 修复类型包括：`character_name`（角色名修正）、`address`（称呼修正）、`timeline`（时间标记）、`physical_trait`（外貌特征）

**注意**：`auto_fix_suggestions` 同时进入 tracker——`_consume_review` 会将其写入 `validation_rules.json` 的 `common_errors` 中，供后续章节 `auto_fix` 参考。即：文本修改 + 规则记录双路消费。

### 14.3 tracking_updates 子字段消费

| 子字段 | tracker 消费 | 写入目标 |
|--------|-------------|---------|
| `character_changes[]` | `update_from_review` | `character_state.protagonist/supporting` |
| `relationship_changes[]` | `update_from_review` | `relationships.dynamicRelations/history/conflicts/relationshipMatrix` |
| `conflict_updates` | `update_from_review` | `plot_tracker.conflicts.active/resolved` |
| `foreshadowing_updates` | `update_from_review` | `plot_tracker.foreshadowing[].hints/revealed` |
| `timeline_updates` | `update_from_review` | `timeline.storyTime.current/timeLogic.travelTimes` |

### 14.4 双重评分体系

Reviewer prompt 要求输出 `consistency_score`（0-100），但 pipeline 中**仅在审核通过时**被 `tracker.calculate_consistency_score(review)` 覆盖：

```python
# pipeline.py _write_chapters（仅在 review.get("approved") 为 True 时执行）
calc_score = tracker.calculate_consistency_score(review)
review["consistency_score"] = calc_score  # 覆盖 reviewer 原始分数
```

审核未通过时，`consistency_score` 保留 reviewer 原始值。

`calculate_consistency_score` 的计算规则：基于 `issues` 的 severity 加权（major -15, warning -5, note -2）。

**检查点**：两套评分体系是否应该统一。当前 pipeline 覆盖了 reviewer 的分数，以程序化计算为准。

---

## 十五、边界场景

> *最后验证：2026-05-21*

### 15.1 极端章节数

| 场景 | 风险点 | 当前处理 |
|------|--------|---------|
| 1 章小说 | Plotter `BATCH_SIZE=5`，但 `if num_chapters <= BATCH_SIZE` 走单批 | ✅ 安全 |
| 100 章小说 | Plotter 分 20 批，`existing_summaries` 可能很长 | ⚠️ summaries 累积可能导致 token 溢出 |
| 0 章 | `_collect_params` 中 `_read_int` 返回 0 | ⚠️ `range(0, 0)` 为空，直接跳到 editing → 可能崩溃 |

**检查点**：`total_chapters` 应有最小值校验（≥1）。

### 15.2 Plotter 章节不匹配

如果 Plotter 返回的章节数 ≠ `total_chapters`：

```python
all_plans.extend(batch)  # 累积所有批次结果
```

`state.chapters` 的创建基于 `chapter_plans` 列表长度，后续 `for i in range(state.current_chapter, state.total_chapters)` 基于 `state.total_chapters`。

**风险点**：如果 `len(chapter_plans) < total_chapters`，`state.chapter_plans[i]` 会 IndexError。

**检查点**：`_write_chapters` 应加 `if i >= len(state.chapter_plans): break` 保护。

### 15.3 审核永远不通过

```python
while not review.get("approved", False) and retries < max_retries:
    retries += 1
    ...
```

`max_retries = config["novel"]["review_max_retries"]` 默认 2。循环最多 2 次后退出，**不会无限循环**。

退出后逻辑：
```python
if review.get("approved", False):
    ch.review_status = "passed"
else:
    ch.review_status = "needs_revision"
    print("达到最大重试次数，接受当前版本")
```

**结论**：✅ 安全，有兜底。

### 15.4 首章 / 末章衔接

`_get_adjacent_text` 处理：

```python
if i > 0:    → prev_ending = 上一章结尾 800 字
else:         → prev_ending = ""          # 首章无上文

if i < total - 1: → next_opening = 下一章开头 800 字
else:               → next_opening = ""     # 末章无下文
```

**结论**：✅ 边界安全。

### 15.5 空追踪文件

`get_tracking_context` 中每个块都有数据存在性检查：

```python
if events: ...        # timeline
if active_fs: ...     # foreshadowing
if groups.get("inactive") or groups.get("deceased"): ...
```

**结论**：✅ 空 JSON 不会导致异常。

### 15.6 章节正文为空

如果 LLM 返回空字符串或极短文本：

- `len(text) < words_min * 0.9` → 触发续写 → 续写也可能返回空
- 续写后仍可能为空 → 保存空文件 → reviewer 审核空文本
- 空文本可能导致 `check_cliches` / `check_sentence_patterns` 等无内容可分析

**检查点**：应在 `writer.run` 返回后加最小长度保护。

---

## 十六、常见故障模式速查

> *最后验证：2026-05-21*

| 故障现象 | 可能原因 | 排查位置 |
|---------|---------|---------|
| 追踪文件全空 / 部分缺失 | Phase 2.5 仅检查了部分文件 | pipeline.py Phase 2.5 的 `missing` 列表 |
| 上下文中看不到世界观细节 | `_condense_world` 缺少该字段提取 | context_manager.py `_condense_world` |
| 章节计划字段丢失 | `_format_chapter_plan` 缺少该字段 | context_manager.py `_format_chapter_plan` |
| 追踪数据不更新 | `_consume_review` 对 dict 类型误判为 True | tracker.py `_consume_review` 的布尔标记 |
| 角色名修正不生效 | Director 未生成 aliases 数据 | prompts/director_system.txt + tracker auto_fix |
| 审核严格度设置后被覆盖 | `_init_config` 在 `_apply_strictness` 之后执行 | tracker.py `_init_config` 调用顺序 |
| Plotter 字段被 STYLE_FIELDS 过滤掉 | `_agent_name()` 返回值不匹配 | agents/base.py `_AGENT_CONFIG_KEYS` |
| 修订后追踪不更新 | `_execute_revise` 未传 `review` 参数 | pipeline.py `_execute_revise` |
| Director/Reviewer 返回 list 导致崩溃 | `chat_json` 返回 list，下游 `.get()` 报错 | 各 Agent 的类型检查 |
| 新增 state 字段后旧项目无法加载 | NovelState 新字段无默认值 | state_manager.py load + dataclass 默认值 |
| 100 章小说 Plotter summaries 溢出 | `existing_summaries` 累积过长 | plotter.py `_generate_batch` |
| 章节正文为空导致下游异常 | Writer 返回空字符串 | writer.py → pipeline.py 长度检查 |
| 续写后文风偏离 | 续写时 context 不含完整 running_context | llm_client.py `_continue_text` |
| JSON 反复截断最终 parse 失败 | `_continue_json` 3 次重试后返回截断原文 | llm_client.py `_continue_json` |
| world.json 写入中断电损坏 | 直接 write_text 无 tmp+rename 保护 | pipeline.py Phase 1 JSON 写入 |
| 小说名称含特殊字符导致目录创建失败 | `name` 无白名单过滤 | main.py `cmd_new` |
| 总章数输入 0 导致直接跳到 editing | `_read_int` 不校验范围 | pipeline.py `_collect_params` |
| 禁用词只改了代码没改 prompt | 5 处同步维护点遗漏 | tracker.py + prompts/*.txt |
| 新增题材在 strictness 映射中缺失 | 新题材走默认 strict | pipeline.py `_GENRE_STRICTNESS` |
| 追踪字段新增但 CSV 含义列为空 | `_FIELD_MEANINGS` 未同步更新 | tracker.py `_FIELD_MEANINGS` |

---

## 十七、用户输入校验清单

> *最后验证：2026-05-21（含 prompt_utils 跨平台输入封装重构）*

### 17.1 输入点全览与校验现状

> 自 2026-05-21 起所有交互输入统一改用 `core/prompt_utils.py`（基于 prompt_toolkit），
> 跨平台支持 Win/Mac/Linux，原生支持退格、方向键、Home/End、Alt+Backspace 删词、多行光标自由移动，
> 不再依赖系统 readline（Windows 无该模块）。Ctrl+C 抛 `UserAbort` 而非 KeyboardInterrupt，便于上层精准捕获。

| 输入点 | 位置 | 校验现状 | 风险 |
|--------|------|---------|------|
| 故事灵感 `idea` | main.py `cmd_new` | ✅ `prompt_multiline` 多行 + 非空检查 + UserAbort | 已修复（原跨行光标错乱、无法删除字符） |
| 小说名称 `name` | main.py `cmd_new` → `_pick_novel_name` | ✅ AI 起名（`suggest_novel_names` 3 候选 / 再生成 / 自输）+ `_sanitize_novel_name` validator；输入顺序：火花 → 名字 → 风格 | 已修复（#48 / #57） |
| 风格描述 `style` | main.py `cmd_new` | ✅ `prompt_single`，可留空 → None | 安全 |
| Braindump 各节反馈 | main.py `_braindump_section` | ✅ `prompt_choice` 三选一 + adjust 时进入 `prompt_multiline` | 安全 |
| 总章数 | pipeline.py `_collect_params` | ✅ `prompt_int(min_val=1)` 范围校验 | 已修复（原可输 0） |
| 每章最少字数 | pipeline.py `_collect_params` | ✅ `prompt_int(min_val=500)` | 已修复（原无下限） |
| 每章最多字数 | pipeline.py `_collect_params` | ✅ `prompt_int(min_val=words_min)` | 已修复（max<min 无检查） |
| ~~遗忘阈值（3 个）~~ | ~~pipeline.py `_collect_params`~~ | **已移除**（2026-05-21 #60）：AI 推荐值默认采纳，不再让用户输入；`show_param_confirmed` 仍展示 | — |
| ~~禁用检查类别~~ | ~~pipeline.py `_collect_params`~~ | **已移除**（2026-05-21 #60）：`config["disabled_checks"]` 保持空列表（全部启用） | — |
| 精修阶段三选一 | pipeline.py `_confirm_refine`（refining phase） | ✅ `prompt_choice("yes/adjust/rewrite")`；adjust 后进入 `prompt_multiline`；UserAbort 视为 yes 继续 | 安全 |
| 精修阶段调整意见 | pipeline.py `_confirm_refine` → adjust 分支 | ✅ `prompt_multiline`，空字符串视为 yes | 安全 |
| 退休元素选择 | pipeline.py `_handle_retire` | ✅ `prompt_single` + isdigit + 范围检查 | 安全 |
| 修订意见 | pipeline.py `_collect_user_feedback` | ✅ `prompt_multiline` Ctrl+D 提交 | 已修复（原 END 终止符不直观） |
| 修订思路选择 | pipeline.py `_select_idea` | ✅ `prompt_single` + isdigit + 范围检查 + 默认回退 | 安全 |
| 修订确认 y/n | pipeline.py `_execute_revise` | ✅ `prompt_yes_no(default=True)` | 安全 |
| 继续创作小说名 | main.py `cmd_continue` | ✅ `prompt_choice` 列表选择，不再手输 | 已修复（原拼错就找不到） |
| 修订小说名 / 章节编号 | main.py `cmd_revise` | ✅ 两个 `prompt_choice` 列表选择 | 已修复（同上） |
| checkpoint 继续/退出 | pipeline.py `_checkpoint` | ✅ `prompt_choice` 二选一 default=continue | 安全 |

### 17.2 必须修复的校验缺口

#### 小说名称路径安全 ✅ 已修复（#48）

`name` 直接用于 `OUTPUT_DIR / name` 创建目录和文件。`main.py` 中 `_sanitize_novel_name` 已实现以下校验：

```
name = ""              → 非空检查
name = "test:bad"      → 非法字符 \\/:*?"<>| 拦截
name = "CON"           → Windows 保留名拦截（CON/PRN/AUX/NUL/COM1-9/LPT1-9，含 CON.txt 等带扩展名变体）
name = "a."            → 尾部 '.' 或空格拦截
len(name) > 64         → 长度上限拦截
```

注：`../` 路径穿越被"非法字符 `/`"覆盖；Linux 下的 `..` 单独路径名仍可创建但不会穿越（因为 `OUTPUT_DIR / "../"` 在 Path 拼接时是字面量子目录名）。如需进一步加固，可加 `if ".." in Path(name).parts:` 检查。

#### 参数范围校验 ✅ 已修复（prompt_int min_val/max_val）

```
total_chapters = 0   → prompt_int(min_val=1)
words_min = 0        → prompt_int(min_val=500)
words_min > words_max → prompt_int(min_val=words_min) 保证 max ≥ min
```

### 17.3 用户输入导致的中断恢复

| 中断场景 | 处理 |
|---------|------|
| Braindump 中 Ctrl+C | ✅ `prompt_*` 抛 `UserAbort` → 上层 catch 后打印"已取消"，return |
| `_collect_params` 中 Ctrl+C | ✅ 包裹 `try/except UserAbort` → 设置 `_interrupted` 后 return |
| `_write_chapters` 中 Ctrl+C | ✅ `signal.SIGINT` handler → 保存 state → 设置 `_interrupted` |
| `_edit_chapters` 中 Ctrl+C | ✅ 同上 |
| 修订中 Ctrl+C | ✅ `prompt_*` 抛 `UserAbort` → 多层 catch → 打印提示后退出 |

**检查点**：新增交互式输入时必须使用 `core/prompt_utils.py` 的 `prompt_*` 函数，并在调用处 `try/except UserAbort` 给出合理的退出/默认行为。禁止再直接使用 `input()`（Windows 无 readline 会出现光标 bug）。

---

## 十八、硬编码内容审计

> *最后验证：2026-05-21*

### 18.1 Prompt 模板占位符一致性

| Prompt 文件 | 占位符 | 替换方式 | 替换位置 |
|------------|--------|---------|---------|
| writer_system.txt | `{words_min}` | 手动 replace（非 .format） | writer.py `_build_system_prompt` |
| writer_system.txt | `{words_max}` | 手动 replace | writer.py `_build_system_prompt` |
| writer_system.txt | `{tone_guidance}` | 手动 replace | writer.py `_build_system_prompt` |
| writer_system.txt | `{narrative_perspective}` | 手动 replace | writer.py `_build_system_prompt` |

**检查点**：
- 使用手动 `replace` 而非 `.format()`（因为 constitution.md 可能含花括号）
- prompt 中出现的任何花括号如果不是占位符，必须先被转义（`{` → `{{`）
- 如果新增 prompt 需要占位符，**必须同样使用手动 replace + 花括号转义**

### 18.2 Prompt JSON Schema 与代码消费对齐

| Prompt | Schema 顶级字段 | 消费者 |
|--------|----------------|--------|
| style_advisor | style_name, tone, pacing, plot, character, worldbuilding, review, editing, suggestions, setting, requirements, style_presets, agent_temperatures | pipeline + agents |
| director | world, characters, locations, outline, style | pipeline → context_manager |
| plotter | 17 个章节字段（见第二章） | context_manager `_format_chapter_plan` |
| reviewer | approved, issues, consistency_checks(6), consistency_score, auto_fix_suggestions, overall_quality, strengths, tracking_updates(5) | pipeline + tracker |
| critic | ideas[].title/description/scope/expected_effect/consistency_notes | pipeline `_select_idea` |
| editor | （纯文本输出，无 JSON schema） | pipeline 保存 |

**检查点**：修改 prompt 的 JSON schema 时，必须同步更新对应的 Agent 代码 + context_manager 格式化 + tracker 数据消费 + 本文档对应章节。

### 18.3 硬编码字典正确性

> **本节字典内容已迁移至 `docs/parameters.md`**：
> - `_BANNED_REPLACEMENTS` / `_EMPTY_PHRASES` / `_ABSTRACT_NOUNS` / `_CLICHE_PAIRS` → `parameters.md` 第七章「程序化检查规则」
> - `_GENRE_STRICTNESS` → `parameters.md` 第五章「审核严格度」
> - `_FIELD_MEANINGS`（~130 条完整列表）→ `parameters.md` 第九章「tracking_changes.csv 字段映射」
> - `_TRACKING_FILES` → `parameters.md` 第八章
>
> **同步维护要求**（保留在此处）：
> - 新增 `_BANNED_REPLACEMENTS` → 5 处同步（tracker.py + writer / editor / reviewer / style_advisor prompt）
> - 新增 `_CLICHE_PAIRS` → 3 处同步（tracker.py + reviewer prompt + editor prompt）
> - 新增 `_GENRE_STRICTNESS` → 检查 style_advisor_system.txt 题材关键词是否覆盖
> - 新增追踪字段 → 同步 `_FIELD_MEANINGS`，否则 CSV 含义列为空
> - 新增追踪文件 → 5 处同步（`_TRACKING_FILES` + `init_tracking` + `get_tracking_context` + `_consume_review` / `update_tracking` + `disabled_checks`）

### 18.4 硬编码变更检查步骤

1. **Prompt 变更** → 搜索所有引用该 prompt 的代码文件，确认 schema 对齐
2. **字典新增条目** → 检查 5 处同步点（代码/Writer/Editor/Reviewer/StyleAdvisor）
3. **常量修改** → 确认所有读取该常量的代码逻辑是否仍然正确
4. **新增映射** → 确认反向映射是否存在（如 strictness → validation_level）
5. **新增追踪文件** → 确认 5 个消费点全部更新

---

## 十九、CLI 渲染层（core/ui.py）

> *最后验证：2026-05-21*

### 19.1 输入/输出职责分离

| 维度 | 模块 | 说明 |
|------|------|------|
| 输出（展示） | `core/ui.py`（rich 13.x） | banner / section / Panel / Table / 颜色 / spinner |
| 输入（收集） | `core/prompt_utils.py`（prompt_toolkit 3.x） | prompt_single / prompt_multiline / prompt_choice / prompt_yes_no / prompt_int |

**原则**：所有 `print` 必须改用 `ui.*`；输入必须改用 `prompt_*`。这两个模块互不依赖，未来要换渲染库（如 textual）只动 ui.py，不影响输入。

### 19.2 ui.py 导出函数清单

| 类别 | 函数 | 用途 |
|------|------|------|
| 横幅 | `banner(title, subtitle)` | 命令入口大横幅（cmd_new / cmd_continue / start_new_novel / resume_novel） |
| 阶段 | `section(title, body, style)` | 阶段小标题（Phase 0-5 + 章节头） |
| 分割 | `divider(label, style)` | Braindump 节之间的轻量分割线 |
| Braindump | `show_braindump_intro / show_braindump_result / show_braindump_summary` | 立项问答 4 节的展示 |
| 起名 | `show_name_candidates(candidates)` | AI 推荐的 3 候选展示 |
| 参数 | `show_param_suggestions / show_param_confirmed` | _collect_params 的建议表 + 确认表 |
| 章节 | `ChapterProgress` 类（**当前未启用**，见 #59） | Live 进度条上下文管理器 |
| 完成 | `show_completion(novel_name, final_dir)` | Phase 5 完成提示 |
| 列表 | `show_novel_list(rows)` | cmd_status 小说项目列表 |
| 消息 | `info / warn / success / error / hint` | 滚动输出（ℹ / ⚠ / ✓ / ✗ / · 前缀） |

### 19.3 Windows 平台兼容

```python
# core/ui.py 顶部（rich 导入之前）
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
```

**原因**：Windows 控制台默认 GBK 编码，无法编码 ✓ / ⚠ / ℹ / Panel 边框等 Unicode 符号，会抛 `UnicodeEncodeError`。reconfigure 后 stdout/stderr 切到 UTF-8，errors="replace" 兜底无法编码字符。

**检查点**：如果未来在 ui.py 之外又引入了新的 stdout 写入点，确认该写入点也走 console（即 `from core.ui import console; console.print(...)`），避免绕过 UTF-8 切换。

### 19.4 ChapterProgress 设计权衡（未启用）

原 plan 设计的 `ChapterProgress`（基于 `rich.progress.Progress` 的 Live 进度条）会与 `_handle_retire` 等使用 prompt_toolkit 输入的环节抢占终端控制权——rich 的 Live 渲染会持续重绘终端底部，而 prompt_toolkit 同样需要独占终端。两者冲突会导致进度条卡死或输入框错乱。

**当前方案**：`_write_chapters` / `_edit_chapters` 改用 `ui.section()` 渲染章节头 + `ui.info/warn/success/hint` 滚动输出 stage 进展。视觉上不如 Live 进度条紧凑，但稳定可靠。

**保留 `ChapterProgress` 类**：以便未来非交互场景（如批量 CI 生成，不存在 prompt_toolkit 输入）使用。

### 19.5 main.py / pipeline.py 输出点全览

| 文件 | 函数 | 主要 ui.* 调用 |
|------|------|---------------|
| main.py | `cmd_new` | banner + （prompt_*） + `_braindump` |
| main.py | `_pick_novel_name` | console.status spinner + show_name_candidates + prompt_choice |
| main.py | `_braindump` / `_braindump_section` | show_braindump_intro + divider + show_braindump_result + show_braindump_summary + info |
| main.py | `cmd_continue` / `cmd_revise` | banner + prompt_choice + warn/error |
| main.py | `cmd_status` | show_novel_list |
| pipeline.py | `start_new_novel` / `resume_novel` | banner + error/hint |
| pipeline.py | `_run_pipeline` Phase 0-5 | info / success / warn / show_completion |
| pipeline.py | `_collect_params` | show_param_suggestions + section + show_param_confirmed |
| pipeline.py | `_write_chapters` / `_edit_chapters` | section（章节头）+ info / warn / success / hint（stage 进展） |
| pipeline.py | `_checkpoint` | section |
| pipeline.py | `_handle_interrupt` / `_apply_strictness` | warn / success / hint / info |

**检查点**：新增 print 输出时必须改用 `ui.*` 等价函数；不要直接 `print(...)` 或 `console.print(...)`（绕过统一 prefix 风格）。

---

## 二十、精修阶段链路（Phase 1.5 refining）

> *最后验证：2026-05-21*

### 20.1 触发与编排

`directing` 完成后 `state.phase = "refining"`；`_run_pipeline` 进入 `_refine_director_output(state)`。
全部确认后 `state.phase = "plotting"`，落盘 `world.json` 和 `outline.json` 覆盖 Director 初版。

### 20.2 4 个 block 的字段范围

| 方法 | 操作字段 | label | system_prompt（在 `core/refine_prompts.py`） |
|------|---------|-------|--------------------------------------------|
| `_refine_world` | `state.world_data` 中除 `characters`/`locations` 外的全部键（name / setting / rules / unique_elements / tone / narrative_perspective / geography / social_structure / factions / history / daily_life 等） | `"世界观"` | `REFINE_WORLD_PROMPT` |
| `_refine_characters` | `state.world_data["characters"][]` 逐张 | `"核心角色：<name>"` | `REFINE_CHARACTER_PROMPT` |
| `_refine_locations` | `state.world_data["locations"][]` 逐张 | `"场景地点：<name>"` | `REFINE_LOCATION_PROMPT` |
| `_refine_outline` | `state.outline` 整块（含 theme / three_act / ending / key_turning_points / subplots / key_conflicts） | `"大纲（主题、三幕、关键转折）"` | `REFINE_OUTLINE_PROMPT` |

### 20.3 三选一循环（`_refine_block`）

```
展示 Panel → prompt_choice(yes / adjust / rewrite)
  ├─ yes      → 返回当前 result
  ├─ adjust   → prompt_multiline 收反馈 → _llm_refine(current, feedback) → 再次展示 → 内层继续
  └─ rewrite  → _llm_refine(current=None) → 完整重生成 → 重新展示
```

UserAbort 在 `_confirm_refine` 中视为 "yes"（保留当前版本继续往下走）；signal SIGINT 触发 `self._interrupted = True`，各 `_refine_*` 立即 return。

### 20.4 断点续传（`state.refined_blocks`）

- `NovelState.refined_blocks: list[str]`（dataclass 默认 `[]`）
- 命名规则：`"world"` / `"outline"` / `f"character:{name}"` / `f"location:{name}"`
- 每个 block 确认后立即 append 并 `state_mgr.save(state)`
- 各 `_refine_*` 入口检查 `tag in state.refined_blocks` 跳过
- 旧 state.json 无此字段时，`StateManager.load` 的 `__dataclass_fields__` 白名单过滤（#43）保证向后兼容，默认值 `[]` 自动注入

### 20.5 落盘策略

- 每个 block 确认 → 立即 save 到 `novel_state.json`（确保中断不丢进度）
- 全部 4 类完成 → 重写 `world.json`（拼回 characters / locations）和 `outline.json`
- world.json 拼接逻辑：`{除 characters/locations 外字段} + characters + locations`（防止 `_refine_world` 写回 state.world_data 时遗漏 list 字段）

### 20.6 LLM 契约（`_llm_refine`）

签名：`_llm_refine(system_prompt, *, label, current, user_feedback, context, rewrite=False, previous=None)`

| 路径 | 入参 | system 拼接 | user msg 结构 | 温度 |
|------|------|-------------|---------------|------|
| 调整 (adjust) | `current=<dict\|list>, user_feedback=<str>, rewrite=False` | `system_prompt`（原 4 个 PROMPT 之一） | 上下文 + 当前版本 + 用户反馈 + "结构与当前版本一致" | `0.7` |
| 完整重写 (rewrite) | `current=None, rewrite=True, previous=<dict\|list>` | `system_prompt + REFINE_REWRITE_DIRECTIVE` | 上下文 + **之前的版本（请勿沿用此方向）** + "彻底换一种思路重新生成，结构一致但内容方向、风格、设定明显不同" | `0.9` |
| 兜底初版 | `current=None, rewrite=False`（保留路径，目前未被 `_refine_block` 调用） | `system_prompt` | 上下文 + "请重新生成完整内容" | `0.7` |

- `_refine_block` 外层 rewrite 改传 `rewrite=True, previous=result`（旧版传 `current=None`，无反上下文导致无实质变化，#62 已修复）
- 使用 `self.llm.chat_json`，依赖 `parse_json` 自动剥离 Markdown 围栏 / 提取首 `{` 到末 `}`
- 解析失败时 `_llm_refine` 返回 `None`；`_refine_block` 接到 `None` 后 `ui.warn("打磨失败，保留当前版本")` 并继续循环

### 20.7 上下文裁剪（`_build_refine_context`）

- 故事火花：600 字
- 世界观摘要（非 world block 时）：800 字
- 大纲摘要（非 outline block 时）：600 字
- 角色 / 地点 block 还会注入"其他角色/地点名"列表，提示 LLM 保持设定一致

### 20.8 用户体验保留

- `_collect_params` 简化（#60）后用户在参数确认面板看不到"自定义阈值/禁用类别"两步；阈值仍在 `show_param_confirmed` 中展示（仅查看，不可改）
- 进入 refining phase 后 `ui.banner("精修阶段", ...)` + `ui.hint("[恢复] 已确认 N 个 block")` 告知用户已通过的 block

**检查点**：新增 refining block 时必须：(1) 在 `core/refine_prompts.py` 加 system_prompt；(2) 在 `_refine_director_output` 编排顺序中插入；(3) 在 `state.refined_blocks` 用稳定命名规则（避免与已有 tag 冲突）；(4) 文档同步本表。

---
