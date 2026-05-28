# 数据链路自检清单

本文档是**字段链路参考手册**，记录每个 AI 生成字段从「生成 → 存储 → 格式化 → 消费」的完整流转路径。
当 AI 执行 `docs/verification_protocol.md` 中的验证项时，需要查阅此文档了解链路细节。

> **接到需求时不要从这里开始读** —— 先读 `docs/execution_workflow.md`（流程总纲）。本文件是事实底稿，不是执行流程。

**与其他文档的分工**：
- 参数值/硬编码常量/CSV 字段映射 → `docs/parameters_and_changelog.md`（权威来源）
- 流程图/数据流向图 → `docs/flowchart.md`
- AI 验证协议 → `docs/verification_protocol.md`
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

| *最后验证：2026-05-23* —

Director 输出 JSON 包含 4 个顶级 key：`world`、`characters`、`locations`、`outline`（`style` 字段已于 #160 移除）。

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

> **已移除（#160）**：Director prompt 不再输出 `style` 字段（功能由 StyleAdvisor 完全替代）。`_split_director_output` 会 `pop("style", None)` 清理残留。

---

## 二、Plotter 输出字段链路

> *最后验证：2026-05-22*

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
| `previous_link` | ✅ | ✅ `承上启下：{...}` | writer |
| `opening_hook_type` | ✅ | ✅ `章首引子类型：{...}` | writer |
| `ending_hook_type` | ✅ | ✅ `章尾悬念类型：{...}` | writer |
| `characters_on_stage` | ✅ | ✅ `实际登场角色：{...}` | writer |
| `scene_list` | ✅ | ✅ `场景列表：` 逐场景输出 | writer |

**检查点**：新增 plotter 输出字段后，需同步检查：
1. `plotter_system.txt` 的 JSON schema 是否包含该字段
2. `_format_chapter_plan` 是否格式化该字段
3. tracker 的 `update_tracking` 是否消费该字段

---

## 二·补、大纲审计输出字段链路（Engine A→D）

> *最后验证：2026-05-28*

Plotting 阶段**边拆边审**：Plotter 每拆完一批（5 章）即触发 `pipeline._audit_one_batch`（B+C 逐章校验 + 重写循环 + D1+D2 批次检查），全部拆完后 `pipeline._finalize_outline_audit` 跑 D3+D4 全局检查。Engine A 能力矩阵在拆章前一次性提取。三个审计 Agent 的输出分别落入 `NovelState` 的 4 个字段，经 `web/routers/novels.py` 详情接口暴露，由前端 `MessageLog.vue`（实时消息流，batch/global 已抽为 `BatchAuditView.vue`/`GlobalAuditView.vue` 子组件）和 `NovelDetailView.vue`（Plotting Tab 每章折叠面板 + 章节列表下方批次/全局审计折叠区 + 顶部大纲入口）消费。

### 2补.1 Engine A — CapabilityExtractor → `state.capability_matrix`

| 顶层字段 | Prompt 定义（`capability_extract_system.txt`） | 消费者 |
|---------|-----------------------------------------------|--------|
| `characters` | ✅ 角色能力矩阵（`capabilities` 能力域分数 + `constraints` 物理/言语约束 + `growth_ceiling` 阶段天花板） | OutlineAuditor（能力超标检测）、OutlineGlobalChecker（遗忘/完整性遍历）、前端能力矩阵展示 |
| `world_rules` | ✅ 世界规则矩阵（`power_system` 等级体系 + `distance_matrix` 地点距离 + `factions` 势力 + 大事件年表） | OutlineAuditor（世界规则违反检测）、OutlineGlobalChecker（势力完整性） |
| `locations` | ✅ 地点约束矩阵（来源 `locations[]` 的 atmosphere/function/five_senses/scale/position） | OutlineAuditor（地点一致性检测） |

> 提取失败兜底：返回 `{"characters": {}, "world_rules": {}, "locations": {}}`（`capability_extractor.py:30`）。

### 2补.2 Engine B+C — OutlineAuditor → `state.chapter_audits[]`

每章一个对象，`outline_auditor.run` 返回 list。

| 字段 | Prompt 定义（`outline_audit_system.txt`） | 生产/约束 | 消费者 |
|------|------------------------------------------|-----------|--------|
| `chapter_number` | ✅ | 章节号 | pipeline（splice 回填）、前端 `auditByChapter` map key |
| `title` | ✅ | 章节标题 | 前端审计卡片标题 |
| `capability_manifest` | ✅ B1 | 角色能力表现 `{setting→actual, status}` | `ui.show_chapter_audit`、前端能力矩阵摘要 |
| `quality_scores` | ✅ C1 | 5 维评分（plot_progression/pacing/opening_hook/ending_hook/character_depth，各 0-10） | 前端质量评分条 |
| `total_quality` | ✅ | 5 维总分（0-50） | 前端 `{n}/50` 标签、pipeline 质量停滞检测 |
| `issues` | ✅ B1-B6+C1 汇总 | `[{severity: major\|warning\|note, type, detail, suggestion}]` | `_build_audit_feedback`（重写反馈）、前端问题列表 |
| `approved` | ✅ | `false` 当存在 major issue 或 `total_quality<35` | pipeline 重写循环判定、前端通过/打回标签 |
| `revision_count` | ⚙️ pipeline 写入 | 重写轮次（`_audit_one_batch` 对被重写章节回填） | 审计版本追溯 |

> 返回类型校验：非 list 时返回 `[]`（`outline_auditor.py:48`）。

### 2补.3 Engine D — OutlineGlobalChecker → `state.batch_audits[]` + `state.global_audit`

`run_batch`（每 5 章，scope=batch）→ append 到 `batch_audits[]`；`run_global`（拆章全部完成，scope=global）→ 存 `global_audit`。

| 字段 | Prompt 定义（`outline_global_check_system.txt`） | scope | 消费者 |
|------|------------------------------------------------|-------|--------|
| `forgotten_elements` | ✅ D1（characters/plotlines/foreshadowing 超阈值未出现） | batch+global | `ui.show_batch_audit`、前端遗忘曲线 |
| `pacing_curve` | ✅ D2（tension_sequence + warnings） | batch+global | 前端节奏曲线图 |
| `completeness` | ✅ D3（unused_characters/locations/factions + uncovered_turning_points/acts + coverage_rate） | **仅 global** | `ui.show_global_audit`、前端覆盖率圆环 |
| `cross_batch_issues` | ✅ D4（character_drift/plotline_drop 等，severity 标注） | **仅 global** | 前端跨批次一致性列表 |

> 遗忘检测阈值来源：`_get_audit_thresholds` 优先取 `style_guide.suggestions.tracking_thresholds`，缺省 character=10/plotline=12/foreshadowing=20。
> coverage_rate 百分比字段（`characters_pct` 等）为整数（71 而非 0.71）。

### 2补.4 链路检查点

新增/修改审计字段时需同步：
1. 对应 prompt（`capability_extract`/`outline_audit`/`outline_global_check`/`outline_rewrite`_system.txt）的 JSON schema
2. `core/ui.py` 的 `show_chapter_audit`/`show_batch_audit`/`show_global_audit` 透传字段
3. `web/routers/novels.py` 详情接口的 4 字段暴露
4. 前端：实时渲染 `MessageLog.vue` + 子组件 `BatchAuditView.vue`/`GlobalAuditView.vue`；持久化 `NovelDetailView.vue`（Plotting Tab 每章折叠面板消费 chapter_audits + 章节列表下方折叠区消费 batch_audits/global_audit）
5. `NovelState`（`state_manager.py`）字段定义

### 2补.5 边拆边审的进度不变量（关键）

边拆边审下 `chapter_plans` 与 `chapter_audits` 两条进度线必须对齐到同一批次边界。每批顺序：`Plotter 拆5章 → save(chapter_plans) → _audit_one_batch 审 → save(chapter_audits)`。

- **回调传播**：`_audit_one_batch` 的重写 splice 必须回填**传入的 plans**（= Plotter 的 `all_plans` 同一列表引用），下一批 `_build_existing_summaries(all_plans)` 才能带修正版 → 实现「前序影响后续」。误改 `state.chapter_plans` 副本则修正不传播。
- **跳过已审**：`_audit_one_batch` 开头 `if batch_start < len(state.chapter_audits): return`。
- **断点恢复对齐**：进入 plotting 调 `plotter.run` 前，`if len(chapter_plans) > len(chapter_audits): chapter_plans = chapter_plans[:audited_count]`，丢弃「拆了未审」尾部，Plotter 重拆+重审该批（≤5 章代价）。崩溃落在两次 save 之间也不会出现「拆了永不审」。
- **异常隔离**：审计异常在 `_on_batch` 内单独捕获，不被 plotting 的 try/except 误判为拆章失败。

---

## 三、Tracker 数据链路

> *最后验证：2026-05-22*

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

| *最后验证：2026-05-26* —

### 4.1 build_running_context 组装（#184 三级金字塔）

```
FULL_CONTEXT_TEMPLATE:
  ## 当前卷信息（如分卷）  ← _format_volume_info(volumes, chapter_number)
  ## 用户原始需求         ← story_idea[:1000]
  ## 世界观与角色参考     ← _condense_world(world_data)
  ## 故事主线             ← _condense_outline(outline)
  ## 前文摘要             ← _build_layered_summaries（三级金字塔）：
       ## 历史卷宏观结构（远端记忆）       ← volume_summaries（Level 3，卷末由 generate_volume_summary 生成，每卷 ≤1200 字）
       ## 中程章节梗概                     ← summaries[-recent_chapters_full-condensed:-recent_chapters_full]（一句话精简，默认 7 章）
       ## 最近章节摘要                     ← summaries[-recent_chapters_full:]（完整摘要，默认 3 章）
       ## 近端原文片段（保持文风延续）     ← recent_chapter_excerpts（Level 1，pipeline._collect_recent_excerpts 取每章首尾各 750 字）
       ## 相关锚点（按本章计划检索）       ← relevant_anchors（tracker.query_relevant，top_k=8 伏笔/角色/关系）
  ## 追踪数据             ← tracker.get_tracking_context(max_chars=8000)
  ## 当前章节剧情要点     ← _format_chapter_plan(plan)
```

**预算控制**：
- 总预算 `max_context_chars` 默认 50000 字（来源 `config.context_budget.running_context_chars`），超出会硬截断 + warn
- `tracking_context` 二次截断：调用方传入 `max_chars`，ContextManager 端再 cap 一次
- 续写场景：writer.py 不再传完整 user_msg，改用 `_plan_anchor(≤1500 字) + 草稿尾部 2000 字`（来源 `context_budget.continuation_tail_chars`）

**Level 3 卷级摘要生成时机**：
- pipeline `_maybe_generate_volume_summary` 在 `tracker.advance_volume` 触发后调用
- 仅在 `ch_num == cur_vol.end_chapter` 且本卷已累计 `volume_summary_min_chapters`（默认 3）章摘要时生成
- 结果存入 `state.volume_summaries: dict[int, str]`（持久化到 novel_state.json）

**检查点**：新增字段时，确认它在 `_condense_*` / `_format_*` / `_build_layered_summaries` 中被提取。如果字段在这些环节缺失，下游 Agent 永远看不到它。

### 4.2 上下文注入点

`tracking_context` 注入以下 Agent（均通过 `max_chars=context_budget.tracking_context_chars` 截断）：

| Agent | 注入方式 | 位置 |
|-------|---------|------|
| Writer | `running_context` 的一部分（含三级金字塔 + relevant_anchors） | pipeline.py `_write_chapters` → `writer.run(plan, running_ctx)` |
| Reviewer | 独立参数 `tracking_context` | pipeline.py `_write_chapters` → `reviewer.run(..., tracking_context=tracking_ctx)` |
| Editor | 独立参数 `tracking_context`（_edit_chapters 阶段同样按 `max_chars` 截断） | pipeline.py `_edit_chapters` → `editor.run(..., tracking_context=tracking_ctx)` |
| Critic | 独立参数 `tracking_context` | pipeline.py `revise_chapter` → `critic.run(..., tracking_context=tracking_ctx)` |

### 4.3 Token 预算预警链路（#184）

```
任意 LLMClient.chat/chat_json/chat_with_history
  → _call_api
  → _check_budget(system_prompt, messages)
     → estimate_messages_tokens（中文 1.5×字、英文 0.3×字 + 每条 4 token 元数据）
     → 若 est + reserved_output(9000×1.5) > max_tokens(131072) → logger.warning
```

**检查点**：日志中频繁出现 `[budget] ... 估算输入 ... 可能截断` → 说明上层 context 组装未按预算压缩，需检查 `context_budget.*` 配置是否过大或 system prompt 是否需要按题材剥离（见 prompts/fragments/）。

---

## 五、Style Guide 分发链路

| *最后验证：2026-05-23* —

> **本节内容已迁移至 `docs/parameters_and_changelog.md` 第四章「风格指南」+「STYLE_FIELDS 分发过滤」表格**。
> 那里是 STYLE_FIELDS 字段分发的权威来源，含每个 Agent 收到的字段列表。
>
> 检查点（保留在此处）：
> - `_agent_name()` 返回值是否在 `STYLE_FIELDS` 中有对应条目
> - PlotAgent 的 `_agent_name()` 应返回 `"plotter"`（由 `_AGENT_CONFIG_KEYS` 映射，而不是 `"plot"`）
> - 修改 STYLE_FIELDS 后，需同步更新 parameters_and_changelog.md 第四章

---

## 六、Writer 特殊链路

| *最后验证：2026-05-23* —

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
writer.run → chat() → 检查 _count_chinese_chars(text) < words_min * 0.9
          → chat_with_history(messages=[plan_anchor, draft_tail, "继续"]) 续写（#184 滑窗）
```

**检查点**：
- `0.9` 阈值硬编码在 `writer.py` 中
- **#90 I1**：原 `len(text)`（含 Markdown/标点）→ 改为 `_count_chinese_chars(text)`（剥离 Markdown 后只统计 `[一-鿿]` 中文字符）
- **#184 续写滑窗**：原实现回传完整 user_msg + draft，多轮续写会再次溢出 max_tokens；现仅传 `_plan_anchor(章节计划锚点 ≤1500 字)` + 草稿尾部 `continuation_tail_chars` 字（默认 2000）+ "继续"指令
- 日志输出格式：`Writer: chapter done. {中文字数} 中文字 / {总字符数} 字符。`

### 6.3 重写续写

```
writer.rewrite → _build_system_prompt(is_rewrite=True) → chat(temperature=min(base+0.25, 0.95))
              → user_msg 中 running_context 截断到 rewrite_ctx_cap（默认 8000 字，#184，原 30000）
              → 检查 _count_chinese_chars(text) < words_min * 0.9 → chat_with_history 同滑窗续写
```

**说明**：`rewrite` 方法同样具备字数不足续写逻辑，与 `run` 方法一致。重写时因上下文精简（只传审稿意见+草稿，不重复传 running_context），续写时可能偏离原文风格。

**rewrite 三重组合（#62 修复）**：
1. **System 增强**：`_build_system_prompt(is_rewrite=True)` 在 system prompt 尾部追加"## 重写专项要求"段，强调实质性改写被指出问题的段落而非字面微调，并严格保留 strengths 标注的优秀内容
2. **User msg 增强**：尾部追加"请实际修复问题，避免只做表面调整"示例（如"对话单调"需重新设计对话表达）
3. **升温**：`rewrite_temp = min(self._temperature() + 0.15, 0.9)`，比初稿温度上调 0.15（封顶 0.9，防止过度发散导致风格漂移）

**检查点**：重写后的续写质量是否受精简上下文影响；rewrite 温度上限 0.9 是硬编码在 `agents/writer.py` `rewrite()` 中。

---

## 七、程序化检查链路

| *最后验证：2026-05-23* —

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

| *最后验证：2026-05-23* —

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

| *最后验证：2026-05-23* —

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
   或在 system_reference.md 中记录为"有意不消费"并说明理由
```

**原则**：AI 生成的每个字段都是 token 成本。如果值得让 AI 生成，就值得被正确消费。只有经过上述 4 步确认后，才可标记为"有意不消费"。

### 步骤 6：文档同步检查

代码变更完成后，逐项确认以下文档是否需要同步更新：

| 文档 | 触发条件 | 需要更新的内容 |
|------|---------|--------------|
| `docs/parameters_and_changelog.md` | 新增/修改 config 参数、新增 bug fix、新增追踪字段、新增常量 | 参数表 + bug fix 记录 + 字段数 + CSV 格式 |
| `docs/flowchart.md` | 修改数据流、新增存储环节、新增 Agent 交互 | 数据流图 + 写作循环图 + 文件结构 |
| `README.md` | 新增功能、修改架构、修复 bug、修改依赖 | 架构图 + 核心特性 + 变更日志 + 项目结构 + 配置说明 |
| `requirements.txt` | 新增/升级依赖 | 添加包 + 版本约束 |
| `docs/system_reference.md` | 新增追踪文件、新增硬编码字典、新增 prompt schema、新增输入点 | 对应章节的清单更新 |

**快速判断规则**：

```
改了 prompt schema？      → parameters_and_changelog.md + system_reference.md (十八章)
改了 pipeline 存储？      → flowchart.md + parameters_and_changelog.md
改了 context_manager？    → system_reference.md (第一~四章) + parameters_and_changelog.md (字段数)
改了 tracker？           → system_reference.md (第三/七/十八章) + parameters_and_changelog.md
改了 config.yaml？       → parameters_and_changelog.md + README.md
新增了依赖？             → requirements.txt + README.md
修复了 bug？             → parameters_and_changelog.md (bug fix 记录) + README.md (变更日志)
新增了用户输入点？        → system_reference.md (第十七章)
新增了硬编码字典/常量？   → system_reference.md (第十八章) + parameters_and_changelog.md
改了 ui.py / name_generator.py？ → system_reference.md (第十九章) + parameters_and_changelog.md (第八章硬编码) + README.md
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

| *最后验证：2026-05-23* —

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

| *最后验证：2026-05-23* —

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

| *最后验证：2026-05-23* —

### 12.1 阶段转换图

```
styling → collecting_params → directing → plotting → writing → editing → complete
                                    ↑                  ↑
                              Phase 1              Phase 2.5
                         (一次性生成+全量精修)      (追踪初始化)
```

> 旧版 phase `refining` 仍被识别（向后兼容），走 `_refine_director_output()` 旧流程。
> 旧版增量生成的 state（含 `planned_cast`）由 `_run_directing_holistic` 自动剥离后走全量精修。

每个 phase 用 `if state.phase == "xxx"` 守卫，顺序排列在 `_run_pipeline` 中。通过后设置 `state.phase = "next_phase"` 并 save。

### 12.2 阶段跳跃安全性

`resume_novel` 从任意 phase 入口恢复。**跳跃规则**：

| 跳到 | 是否安全 | 原因 |
|------|---------|------|
| styling | ✅ | 重新生成 style_guide |
| collecting_params | ✅ | 重新收集参数 |
| directing | ✅ | 全量精修：`state.refined_blocks` 含 `"holistic"` 时跳过，否则重新生成或从已有数据进入精修 |
| refining（旧） | ✅ | 向后兼容旧 state，走 `_refine_director_output()` |
| plotting | ✅ | 断点续写：`state.chapter_plans` 含部分结果时作为 `existing_plans` 传入 Plotter，跳过已完成批次（#181） |
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

| *最后验证：2026-05-23* —

> **本节内容已迁移至 `docs/parameters_and_changelog.md`**：
> - config.yaml 字段消费清单 → `parameters_and_changelog.md` 第一章 + 第二章 + 第三章
> - 硬编码常量审计 → `parameters_and_changelog.md` 第八章「LLM 客户端与 pipeline 行为参数」
>
> 修改 config.yaml 或硬编码常量后，需同步更新 parameters_and_changelog.md 对应章节。

---

## 十四、Reviewer 输出全量消费

| *最后验证：2026-05-23* —

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
| `quality_breakdown` | dict | `pipeline.py` `_write_chapters` + `_execute_revise` | 8 维评分 + 总分打印展示 |

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

| *最后验证：2026-05-23* —

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

`max_retries = config["novel"]["review_max_retries"]` 默认 **3**（I2 硬上限调整：2 → 3）。循环最多 3 次后退出，**不会无限循环**；到上限后 `ch.review_status = "needs_revision"`，UI 输出"已达 review_max_retries=3 上限（I2 硬上限），接受当前版本进入下一阶段"。

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

| *最后验证：2026-05-23* —

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
| 编剧阶段 API 报错后从头开始 | plotting 无 try/except，异常后 `chapter_plans` 未保存 | pipeline.py plotting 阶段 + plotter.py `existing_plans` 参数（#181） |
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

> *最后验证：2026-05-23（含 #159-#166 自检修复）*

### 17.1 输入点全览与校验现状

> 自 2026-05-23 起所有交互输入统一通过 `core/prompt_utils.py`（WebSocket 双向通信），
> 由前端组件收集用户输入并通过 WebSocket 回传。`UserAbort` 在前端取消或 WebSocket 断开时触发。

| 输入点 | 位置 | 校验现状 | 风险 |
|--------|------|---------|------|
| 故事灵感 `idea` | web/app.py `_run_pipeline` (new) | ✅ 前端多行输入 + 非空检查 | 安全 |
| 小说名称 `name` | web/app.py `_run_pipeline` (new) | ✅ 前端 AI 起名（`/api/suggest-names`）+ `sanitize_novel_name` REST 校验 | 安全 |
| 风格描述 `style` | web/app.py `_run_pipeline` (new) | ✅ 前端单行输入，可留空 | 安全 |
| Braindump 各节反馈 | core/braindump.py `_braindump_section` | ✅ `prompt_choice` 三选一 + adjust 时进入 `prompt_multiline` | 安全 |
| 总章数 | pipeline.py `_collect_params` | ✅ `prompt_int(min_val=1)` 范围校验 | 已修复（原可输 0） |
| 每章最少字数 | pipeline.py `_collect_params` | ✅ `prompt_int(min_val=500)` | 已修复（原无下限） |
| 每章最多字数 | pipeline.py `_collect_params` | ✅ `prompt_int(min_val=words_min)` | 已修复（max<min 无检查） |
| ~~遗忘阈值（3 个）~~ | ~~pipeline.py `_collect_params`~~ | **已移除**（2026-05-21 #60）：AI 推荐值默认采纳，不再让用户输入；`show_param_confirmed` 仍展示 | — |
| ~~禁用检查类别~~ | ~~pipeline.py `_collect_params`~~ | **已移除**（2026-05-21 #60）：`config["disabled_checks"]` 保持空列表（全部启用） | — |
| 风格指南精修三选一 | pipeline.py `_refine_block`（styling phase） | ✅ 复用 `_confirm_refine`：`prompt_choice("yes/adjust/rewrite")`；adjust 后进入 `prompt_multiline`；UserAbort 传播到 `_refine_block` | 安全 |
| 精修阶段三选一 | pipeline.py `_confirm_refine`（refining phase） | ✅ `prompt_choice("yes/adjust/rewrite")`；adjust 后进入 `prompt_multiline`；UserAbort 视为 yes 继续 | 安全 |
| 精修阶段调整意见 | pipeline.py `_confirm_refine` → adjust 分支 | ✅ `prompt_multiline`，空字符串视为 yes | 安全 |
| 退休元素选择 | pipeline.py `_handle_retire` | ✅ `prompt_single` + isdigit + 范围检查 | 安全 |
| 修订意见 | pipeline.py `_collect_user_feedback` | ✅ `prompt_multiline` Ctrl+D 提交 | 已修复（原 END 终止符不直观） |
| 修订思路选择 | pipeline.py `_select_idea` | ✅ `prompt_single` + isdigit + 范围检查 + 默认回退 | 安全 |
| 修订确认 y/n | pipeline.py `_execute_revise` | ✅ `prompt_yes_no(default=True)` | 安全 |
| 继续创作小说名 | web/app.py `_run_pipeline` (continue) | ✅ 前端列表选择 | 安全 |
| 修订小说名 / 章节编号 | web/app.py `_run_pipeline` (revise) | ✅ 前端列表选择 | 安全 |
| checkpoint 继续/退出 | pipeline.py `_checkpoint` | ✅ `prompt_choice` 二选一 default=continue；Web 模式自动继续不弹确认（#124） | 安全 |

### 17.2 必须修复的校验缺口

#### 小说名称路径安全 ✅ 已修复（#48）

`name` 直接用于 `OUTPUT_DIR / name` 创建目录和文件。`core/name_generator.py` 中 `sanitize_novel_name` 已实现以下校验：

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

| *最后验证：2026-05-23* —

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

> **本节字典内容已迁移至 `docs/parameters_and_changelog.md`**：
> - `_BANNED_REPLACEMENTS` / `_EMPTY_PHRASES` / `_ABSTRACT_NOUNS` / `_CLICHE_PAIRS` → `parameters_and_changelog.md` 第七章「程序化检查规则」
> - `_GENRE_STRICTNESS` → `parameters_and_changelog.md` 第五章「审核严格度」
> - `_FIELD_MEANINGS`（~130 条完整列表）→ `parameters_and_changelog.md` 第九章「tracking_changes.csv 字段映射」
> - `_TRACKING_FILES` → `parameters_and_changelog.md` 第八章
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

## 十九、Web 输出层（core/ui.py + core/prompt_utils.py）

| *最后验证：2026-05-23（#170 移除 CLI）* |

### 19.1 输入/输出职责分离

| 维度 | 模块 | 说明 |
|------|------|------|
| 输出（展示） | `core/ui.py` | 通过 WebSocket output_queue 推送到前端，函数签名与 Rich 版一致 |
| 输入（收集） | `core/prompt_utils.py` | 通过 WebSocket 向前端发送 input_request，阻塞等待匹配响应 |

**原则**：所有输出必须使用 `ui.*`；所有输入必须使用 `prompt_*`。两个模块通过 `core/prompt_utils.get_current_session()` 共享会话上下文。

### 19.2 ui.py 导出函数清单

| 类别 | 函数 | 用途 |
|------|------|------|
| 横幅 | `banner(title, subtitle)` | 命令入口大横幅（start_new_novel / resume_novel） |
| 阶段 | `section(title, body, style)` | 阶段小标题（Phase 0-5 + 章节头） |
| 分割 | `divider(label, style)` | Braindump 节之间的轻量分割线 |
| Braindump | `show_braindump_intro / show_braindump_result / show_braindump_summary` | 立项问答 4 节的展示 |
| 起名 | `show_name_candidates(candidates)` | AI 推荐的 3 候选展示 |
| 参数 | `show_param_suggestions / show_param_confirmed` | _collect_params 的建议表 + 确认表 |
| 章节 | `ChapterProgress` 类 | 通过 WebSocket 推送进度事件（start/update/chapter_done） |
| 完成 | `show_completion(novel_name, final_dir)` | Phase 5 完成提示 |
| 列表 | `show_novel_list(rows)` | 小说项目列表 |
| 消息 | `info / warn / success / error / hint` | 滚动输出 |

### 19.3 pipeline.py 输出点全览

| 文件 | 函数 | 主要 ui.* 调用 |
|------|------|---------------|
| core/braindump.py | `braindump` / `_braindump_section` | show_braindump_intro + divider + show_braindump_result + show_braindump_summary + info |
| pipeline.py | `start_new_novel` / `resume_novel` | banner + error/hint |
| pipeline.py | `_run_pipeline` Phase 0-5 | info / success / warn / show_completion / section + show_refine_block（Phase 0 风格精修） |
| pipeline.py | `_audit_one_batch`（Phase 2 边拆边审：每批审计+重写循环）+ `_finalize_outline_audit`（D3+D4 全局收尾） | show_chapter_audit / show_batch_audit / show_global_audit + warn（重写/停滞/相似度）+ show_refine_block（用户决策） |
| pipeline.py | `_collect_params` | show_param_suggestions + section + show_param_confirmed |
| pipeline.py | `_write_chapters` / `_edit_chapters` | section（章节头）+ info / warn / success / hint（stage 进展） |
| pipeline.py | `_checkpoint` | section；Web 模式自动保存继续（#124） |
| pipeline.py | `_pre_write_check` | hint / warn（#127） |
| pipeline.py | `_report_forgotten` | warn（#128） |
| pipeline.py | `_handle_retire` | hint / info / success（#129） |
| pipeline.py | `revise_chapter` / `_execute_revise` / `_select_idea` | section / info / warn / success / hint（#126） |
| pipeline.py | `_handle_interrupt` / `_apply_strictness` | warn / success / hint / info |
| agents/plotter.py | `Plotter.run` | info（#131） |

**检查点**：新增输出时必须使用 `ui.*` 等价函数；不要直接 `print(...)`（绕过 WebSocket 通道）。

---

## 二十、精修阶段链路（Phase 1 一次性生成 + 全量精修）

> *最后验证：2026-05-22*

### 20.1 触发与编排

`collecting_params` 完成后 `state.phase = "directing"`；`_run_pipeline` 进入 `_run_directing_holistic(state)`。

**全量精修流程**（2026-05-22 重构）：
1. 若 `state.world_data` 为空 → `director.run()` 一次性生成全部设定 → 拆分到 `state.world_data` + `state.outline`
2. 合并 `world_data`（不含 characters/locations）+ characters + locations + outline → `full_json`
3. `_refine_block()` 传入 `REFINE_HOLISTIC_PROMPT` + `full_json` → 用户对整体做"是/调整/重写"三选一
4. 每次调整/重写 LLM 接收并返回完整 JSON，确保跨 block 一致性
5. 精修完成 → 拆回 `state.world_data` 和 `state.outline` → 落盘 `world.json`/`outline.json` → `state.phase = "plotting"`

> **Phase 0 风格指南也使用 `_refine_block`**（2026-05-28 新增）：StyleAdvisor 生成 `style_guide` 后，用户通过 `_refine_block(label="风格指南", system_prompt=REFINE_STYLE_PROMPT)` 做"是/调整/重写"三选一确认，每次调整通过 `on_update` 回调自动落盘。中断后恢复时若 `state.style_guide` 非空则跳过重新生成直接进入精修循环。

### 20.2 全量精修的 JSON 结构

`_merge_director_output` 将 state 合并为：
```json
{
  "world_data": { "..." },
  "characters": [ ... ],
  "locations": [ ... ],
  "outline": { "..." }
}
```

LLM 输出必须保持相同的顶层结构。`_split_director_output` 将结果拆回 `state.world_data` 和 `state.outline`。

### 20.3 三选一循环（`_refine_block`）

```
展示 Panel → prompt_choice(yes / adjust / rewrite)
  ├─ yes      → 返回当前 result
  ├─ adjust   → prompt_multiline 收反馈 → _llm_refine(current=full_json, feedback) → 再次展示 → 内层继续
  └─ rewrite  → _llm_refine(current=None) → 完整重生成 → 重新展示
```

UserAbort 在 `_confirm_refine` 中视为 "yes"（保留当前版本继续往下走）；signal SIGINT 触发 `self._interrupted = True`，各步骤立即 return。

### 20.4 断点续传（`state.refined_blocks`）

- `NovelState.refined_blocks: list[str]`（dataclass 默认 `[]`）
- 全量精修标记：`"holistic"`（一个标记代表整个 director 阶段已确认）
- 断点恢复时若 `"holistic" in state.refined_blocks` → 直接推进到 plotting
- 旧 state.json 无此字段时，`StateManager.load` 的 `__dataclass_fields__` 白名单过滤（#43）保证向后兼容，默认值 `[]` 自动注入

### 20.5 落盘策略

- 精修完成 → 拆回 state → save 到 `novel_state.json`
- `_advance_to_plotting` 重写 `world.json`（`{除 characters/locations 外字段} + characters + locations`）和 `outline.json`

### 20.6 LLM 契约（`_llm_refine`）

签名：`_llm_refine(system_prompt, *, label, current, user_feedback, context, rewrite=False, previous=None)`

| 路径 | 入参 | system 拼接 | user msg 结构 | 温度 |
|------|------|-------------|---------------|------|
| 调整 (adjust) | `current=<full_json>, user_feedback=<str>, rewrite=False` | `REFINE_HOLISTIC_PROMPT` | 上下文（故事火花+风格）+ 当前版本 + 用户反馈 + "结构与当前版本一致" | `0.7` |
| 完整重写 (rewrite) | `current=None, rewrite=True, previous=<full_json>` | `REFINE_HOLISTIC_PROMPT + REFINE_REWRITE_DIRECTIVE` | 上下文 + **之前的版本（请勿沿用此方向）** + "彻底换一种思路重新生成" | `0.9` |

### 20.7 向后兼容

- 旧 `phase="refining"` → 不再由主流程处理（已移除跳转），此类 state 需手动 reset
- 旧增量 state（含 `planned_cast`/`planned_locations`）→ `_run_directing_holistic` 自动剥离后走全量精修
- 旧 `_run_incremental_directing` 方法保留但不再被主流程调用，待确认稳定后删除

---

## 二十一、Web 架构

> *最后验证：2026-05-27（#170 移除 CLI + 全面自检确认 web-native）*

### 21.1 Web-only 架构

| 入口 | 命令 | 交互层 | 适用场景 |
|------|------|--------|---------|
| Web | `python3 web_main.py` | `core/prompt_utils` + `core/ui`（WebSocket 原生） | 浏览器访问 http://localhost:8000 |

`core/prompt_utils.py` 和 `core/ui.py` 直接通过 WebSocket 与前端通信，无需桥接层。`web/bridge/__init__.py` 不再包含 monkey-patch 逻辑（已在 #170 移除 CLI 时重构为 web-native）。

### 21.2 通信机制

`core/prompt_utils.py` 是 web-native 实现，通过 `threading.local()` 绑定当前线程的 `BridgeSession`（定义在 `web/bridge/session.py`）：

- `prompt_choice` → 构造 `input_request` 消息 → 放入 `session.output_queue` → 阻塞等 `session.input_queue` 响应
- `ui.info` → 构造 `output` 消息 → 放入 `session.output_queue` → 不阻塞
- `LLMClient.Spinner` → 空操作（进度由 Web 层管理）
- `web/bridge/web_prompt.py` 仅提供 `get_current_session` 函数供 `pipeline.py` 引用

### 21.3 WebSocket 协议

端点：`/ws`

消息格式（JSON）：

| 方向 | type | 用途 |
|------|------|------|
| S→C | `output` | 展示消息（info/warn/success/error/hint/banner/section/refine_block/progress/completion 等） |
| S→C | `input_request` | 请求用户输入（choice/yes_no/single/multiline/int），含 `request_id` |
| S→C | `session_started` | 会话创建 |
| S→C | `session_ended` | 会话结束（completed/error/cancelled） |
| C→S | `start` | 启动 pipeline（mode: new/continue/revise + params） |
| C→S | `input_response` | 回应输入请求（`request_id` + `value`） |
| C→S | `cancel` | 取消当前操作 |

### 21.4 REST API

| 路由 | 方法 | 用途 |
|------|------|------|
| `/api/novels` | GET | 小说列表（名称/阶段/进度/灵感预览/章节列表） |
| `/api/novels/{name}` | GET | 小说详情（含 world_data/outline/chapters/refined_blocks） |
| `/api/novels/{name}/chapter/{num}` | GET | 章节最终文本内容 |

### 21.5 会话管理

`web/bridge/session.py`：每个 WebSocket 连接创建一个 `BridgeSession`（含 `output_queue` + `input_queue` + `cancelled` Event），pipeline 在独立 daemon 线程中运行。`threading.local()` 绑定当前线程的会话引用，支持多会话并发。

### 21.6 前端

Vue3 SPA + Naive UI（暗色主题 + 绿色强调），Vite 构建，产物由 FastAPI 直接服务。

核心组件：
- `InputDispatcher` — 按 kind 分发到 PromptChoice/YesNo/Single/Multiline/Int
- `MessageLog` — 消息流展示（含 braindump_result/refine_block/progress 等）
- `RefineBlockViewer` — NTabs 分页展示设定详情（world_data/characters/locations/outline）
- `JsonViewer` — 通用易读 JSON 展示组件（#133-#141）。Props: `data`/`type`/`auto`。关键逻辑：`worldObj` 解析 holistic directing 的 `data.world` 嵌套结构；`charsList` 兼容顶层和嵌套角色数组。渲染策略：概要→n-descriptions，列表→n-list+n-thing 卡片，短数组→n-tag，角色→嵌套 n-collapse（主层关键字段+子维度折叠），原始 JSON 折叠兜底。统一 `.jv-sub-title` 样式类。
- 分卷结构（#142-#150）— `VolumeDef`（number/title/start_chapter/end_chapter）作为 `NovelState.volumes` 可选字段。参数收集阶段 ≥10 章时可选启用，LLM 建议分卷方案。Director outline 新增 `volumes` 键；Plotter 批次对齐卷边界；ContextManager 注入卷信息；tracker 激活预留的 `volume`/`volumeEnd`；`_combine_final` 输出卷标题页+单卷文件；前端按卷分组显示（`n-divider`+卷下章节列表）。`volumes=None` 时所有路径与无卷模式完全一致。
- 长篇上下文防护（#151-#157）— 所有 Agent LLM 输入增设字符上限：Plotter 摘要（`MAX_SUMMARY_FULL=30`/`MAX_SUMMARY_SHORT=50`）；`get_tracking_context` 总输出 15K + 伏笔上限 20 条；`_truncate_context` 中 tracking 硬限 10K；Writer 续写 context 截断到 40K；Critic world_data 截断 2K；Tracker JSON 数组滑动窗口裁剪（30-50 条）。Web 错误消息通过 `_format_user_error` 转中文友好提示。
- Writer 重写实质化（#158）— rewrite prompt 从保守（"保持原有好内容"）改为 7 条强制指令（major 必须大幅重写、warning 必须可感知改善），重写温度从 +0.15 提高到 +0.25（上限 0.95），解决审核重写循环中"改了等于没改"的问题。

### 21.7 文件结构

```
web/                        # Python 后端
├── app.py                  # FastAPI 应用入口
├── bridge/
│   ├── __init__.py         # 仅 docstring（monkey-patch 已移除）
│   ├── session.py          # BridgeSession + SessionManager
│   ├── web_prompt.py       # get_current_session 辅助函数
│   └── web_ui.py           # WebChapterProgress（ui.* 已迁入 core/ui.py）
└── routers/
    └── novels.py           # REST API

frontend/                   # Vue3 SPA
├── src/views/              # 4 个页面（Home/NewNovel/NovelDetail/Revise）
├── src/components/         # 交互组件 + 展示组件
├── src/store/              # Pinia 状态管理（WebSocket 消息流）
└── dist/                   # 构建产物（FastAPI 服务）
```
