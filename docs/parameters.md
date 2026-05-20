# 参数参考表

本文档列出项目中所有可配置参数及其来源，便于对号入座。

## 来源图例

| 标记 | 含义 | 说明 |
|------|------|------|
| 🔧 | config.yaml 写死 | 编辑 config.yaml 修改 |
| 🤖 | AI 生成 | 由 StyleAdvisor / Director 等 Agent 动态输出 |
| 👤 | 用户输入 | 运行时交互式输入 |
| ⚙️ | 代码硬编码 | 嵌在 Python 代码中的常量，需改代码 |
| 🔄 | 自动流转 | 代码自动计算/生成，无需人工干预 |

---

## 一、API 与模型配置

| 参数 | 值 | 来源 | 定义位置 |
|------|-----|------|---------|
| `api.base_url` | `https://open.bigmodel.cn/api/anthropic` | 🔧 | config.yaml:2 |
| `api.auth_token_env` | `GLM_API_TOKEN` | 🔧 | config.yaml:3 |
| `api.model` | `glm-5.1` | 🔧 | config.yaml:4 |
| `api.max_tokens` | `131072` | 🔧 | config.yaml:5 |
| `api.temperature` | `0.7` | 🔧 | config.yaml:6（全局默认温度） |
| `api.timeout` | `300` | 🔧 | config.yaml:7（秒） |

---

## 二、小说创作参数

这些参数的决策链：🔧 config.yaml 默认值 → 🤖 AI 推荐值 → 👤 用户确认

| 参数 | 🔧 默认值 | 🤖 AI 来源 | 👤 确认位置 | 最终存储 |
|------|-----------|-----------|------------|---------|
| 总章数 | `20` (`novel.default_chapters`) | `style_guide.suggestions.total_chapters.recommended` | `_collect_params` input | `state.total_chapters` |
| 每章最少字数 | `3000` (`novel.words_per_chapter.min`) | `style_guide.suggestions.words_per_chapter.min` | `_collect_params` input | `state.novel_params` |
| 每章最多字数 | `5000` (`novel.words_per_chapter.max`) | `style_guide.suggestions.words_per_chapter.max` | `_collect_params` input | `state.novel_params` |
| 审核最大重写次数 | `2` | —（无 AI 推荐） | —（直接用默认值） | config.yaml `novel.review_max_retries` |
| 摘要最大字数 | `800` | —（无 AI 推荐） | —（直接用默认值） | config.yaml `novel.summary_max_length` |

### 用户交互输入（cmd_new）

| 参数 | 来源 | 位置 |
|------|------|------|
| 故事灵感 `idea` | 👤 用户输入 | main.py cmd_new |
| 小说名称 `name` | 👤 用户输入 | main.py cmd_new |
| 风格描述 `style` | 👤 用户输入（可留空） | main.py cmd_new |

---

## 三、Agent 温度

决策链：🔧 config.yaml 默认值 → 🤖 StyleAdvisor 覆盖

| Agent | 🔧 默认温度 | 🤖 覆盖来源 |
|-------|-----------|------------|
| style_advisor | `0.5` | `style_guide.agent_temperatures.style_advisor` |
| director | `0.8` | `style_guide.agent_temperatures.director` |
| plotter | `0.7` | `style_guide.agent_temperatures.plotter` |
| writer | `0.85` | `style_guide.agent_temperatures.writer` |
| reviewer | `0.3` | `style_guide.agent_temperatures.reviewer` |
| editor | `0.5` | `style_guide.agent_temperatures.editor` |
| critic | `0.5` | `style_guide.agent_temperatures.critic` |

覆盖机制：`pipeline._apply_style_temperatures()` → `BaseAgent.set_temperature()` → 优先于 config.yaml

---

## 四、风格指南（🤖 AI 生成）

StyleAdvisor 输出的完整 JSON 结构，全量存入 `state.style_guide`，按 `STYLE_FIELDS` 过滤后分发给各 Agent。

| 字段 | 用途 | 消费者 |
|------|------|--------|
| `style_name` | 风格名称，打印展示 | pipeline |
| `tone.*` | 基调/语言/句式/意象 | writer, reviewer |
| `pacing.*` | 节奏/钩子/悬念风格 | writer, plotter |
| `plot.*` | 冲突风格/推进方式/奖励密度 | plotter, writer |
| `character.*` | 对话风格/深度/成长节奏 | writer, reviewer |
| `worldbuilding.*` | 细节密度/展现方式 | writer, director |
| `review.*` | 审核优先级/红线/宽容项 | reviewer |
| `editing.*` | 润色重点/保留特征 | editor |
| `setting.genre` | 题材识别 | pipeline（严格度映射） |
| `setting.genre_knowledge` | 题材专业知识 | plotter, writer |
| `requirements.detected` | 识别到的写作规范 | pipeline（打印） |
| `requirements.anti_ai_banned_words` | 禁用词列表 | tracker（自动替换） |
| `style_presets.*` | 文风规则/对话规则/叙述规则 | writer, editor |
| `agent_temperatures.*` | 各 Agent 温度推荐 | pipeline（覆盖 config） |
| `suggestions.total_chapters` | 推荐章数+理由 | pipeline（用户确认） |
| `suggestions.words_per_chapter` | 推荐字数范围+理由 | pipeline（用户确认） |
| `suggestions.tracking_thresholds` | 推荐遗忘阈值+理由 | pipeline（用户确认） |

### STYLE_FIELDS 分发过滤

| Agent | 收到的字段 |
|-------|----------|
| director | tone, pacing, plot, character, worldbuilding, setting, style_presets |
| plotter | tone, pacing, plot, character, worldbuilding, setting, style_presets |
| writer | tone, pacing, plot, character, worldbuilding, setting, style_presets, **requirements** |
| reviewer | tone, character, worldbuilding, review, requirements, setting |
| editor | tone, pacing, character, editing, style_presets, requirements |
| critic | character, worldbuilding, setting, requirements |

---

## 五、追踪系统配置

### 遗忘检测阈值

决策链：⚙️ 硬编码默认值 → 🤖 AI 推荐值 → 👤 用户确认

| 参数 | ⚙️ 默认值 | 🤖 AI 来源 | 👤 确认位置 | 最终存储 |
|------|-----------|-----------|------------|---------|
| 角色遗忘阈值 | `10` 章 | `style_guide.suggestions.tracking_thresholds.character` | `_collect_params` input | `tracking/config.json` |
| 支线停滞阈值 | `12` 章 | `style_guide.suggestions.tracking_thresholds.plotline` | `_collect_params` input | `tracking/config.json` |
| 伏笔回收阈值 | `20` 章 | `style_guide.suggestions.tracking_thresholds.foreshadowing` | `_collect_params` input | `tracking/config.json` |

fallback 计算（AI 未输出时）：角色=max(3, 总章数/3)，支线=max(4, 总章数*2/5)，伏笔=max(5, 总章数/2)

### 审核严格度

| 参数 | 来源 | 设置时机 |
|------|------|---------|
| `config.strictness` | ⚙️ 题材映射表自动设置 | styling 阶段完成后 |

映射规则（`pipeline._GENRE_STRICTNESS`）：

| 题材关键词 | 严格度 |
|-----------|--------|
| 悬疑、推理、历史、严肃 | `strict` |
| 爽文、复仇、言情、甜文、虐文、网文、玄幻、仙侠 | `flexible` |
| 未匹配 | `strict`（默认） |

### 退休元素

| 参数 | 来源 | 说明 |
|------|------|------|
| `config.retired.characters` | —（未融入，预留） | 标记不再追踪的角色 |
| `config.retired.plotlines` | —（未融入，预留） | 标记不再追踪的支线 |
| `config.retired.foreshadowing` | —（未融入，预留） | 标记不再追踪的伏笔 |

### 禁用检查

| 参数 | 来源 | 说明 |
|------|------|------|
| `config.disabled_checks` | 👤 用户输入 | 在 `_collect_params` 阶段设置，控制追踪上下文输出哪些数据（character/timeline/worldbuilding/locations） |
| `config.strictness` | ⚙️ 题材映射 | strict→deep 验证级别，flexible→standard 验证级别 |
| `config.active_validation_level` | 🔄 自动设置 | `validation_rules.json` 中记录当前激活的验证级别 |

---

## 六、追踪数据流（🔄 自动流转 + 🤖 AI 生成）

追踪系统 6 个 JSON 文件的字段通过三层机制保持活跃：

### L1 零成本（从已有数据提取，0 次 LLM 调用）

| 目标字段 | 数据来源 | 触发时机 |
|---------|---------|---------|
| `character_state.consistency.physicalTraits` | `world_data.characters[].appearance` + `reviewer.consistency_checks.physical_traits_issues` | init + 每章 |
| `character_state.consistency.personalityTraits` | `world_data.characters[].personality` + `reviewer.consistency_checks.personality_issues` | init + 每章 |
| `character_state.consistency.speechPatterns` | `world_data.characters[].voice` | init |
| `character_state.appearanceTracking[].significance` | 角色名在 `plot_points` 中出现 | 每章 |
| `plot_tracker.currentState.location/timepoint/mainPlotStage` | `chapter_plan` 字段匹配 | 每章 |
| `plot_tracker.checkpoints.majorEvents[]` | `tension_level == "high"` | 每章 |
| `plot_tracker.notes.plotHoles/inconsistencies` | `reviewer.consistency_checks.world_issues` | 每章 |
| `timeline.anomalies.issues[]` | `reviewer.consistency_checks.timeline_issues` | 每章 |
| `timeline.storyTime.start` | 第一条 `chapter_plan.time` | init |
| `relationships.factions[].leader` | `world_data.factions[].key_figures[0]` | init |
| `validation_rules.characters.protagonist.traits` | `world_data.characters[0]` appearance/abilities/age | init |
| `validation_rules.common_errors.character_substitution[]` | 角色别名交叉生成 + reviewer auto_fix_suggestions | init + 每章 |

### L2 扩展 reviewer（🤖 AI 生成，0 次额外调用）

| 目标字段 | reviewer 输出源 | 写入方法 |
|---------|----------------|---------|
| `protagonist.currentStatus.health/mentalState/location/alive/position` | `tracking_updates.character_changes` | `update_from_review` |
| `supportingCharacters[].status.alive/currentLocation` | `tracking_updates.character_changes` | `update_from_review` |
| `protagonist.development.milestones[]` | `tracking_updates.character_changes` | `update_from_review` |
| `relationships.dynamicRelations[]` | `tracking_updates.relationship_changes` | `update_from_review` |
| `relationships.history[]` | `tracking_updates.relationship_changes` | `update_from_review` |
| `relationships.conflicts.personal/factional/ideological[]` | `tracking_updates.relationship_changes` | `update_from_review` |
| `relationships.relationshipMatrix` | `tracking_updates.relationship_changes` | `update_from_review` |
| `plot_tracker.conflicts.active/resolved[]` | `tracking_updates.conflict_updates` | `update_from_review` |
| `plot_tracker.foreshadowing[].hints/revealed` | `tracking_updates.foreshadowing_updates` | `update_from_review` |
| `timeline.storyTime.current` | `tracking_updates.timeline_updates.time_markers` | `update_from_review` |
| `timeline.timeLogic.travelTimes.routes` | `tracking_updates.timeline_updates.travel_events` | `update_from_review` |

### L3 独立 LLM 分析（每 5 章 1 次调用）

| 目标字段 | 说明 |
|---------|------|
| `protagonist.development.currentPhase` | 起点→成长→蜕变→成熟 |
| `protagonist.development.nextGoal` | 下一个目标预测 |
| `protagonist.development.milestones[]` | 关键转折点 |
| `supportingCharacters[].arc.current` | 配角发展现状 |
| `supportingCharacters[].motivations[]` | 配角动机推断 |
| `plotlines.main.plannedClimax` | 高潮位置预测 |

### get_tracking_context 新增输出块

| 输出块 | 数据源 | 消费者 |
|--------|--------|--------|
| 角色详细状态 | `consistency.physicalTraits/personalityTraits/speechPatterns` | writer, editor |
| 已解决冲突 | `plot_tracker.conflicts.resolved`（最近 3 条） | writer |
| 剧情问题记录 | `plot_tracker.notes.plotHoles + inconsistencies` | writer, reviewer |
| 动态关系变化 | `relationships.dynamicRelations`（最近 5 条） | writer, editor |
| 场景五感参考 | `locations[].five_senses`（匹配当前地点） | writer |
| 场景氛围指南 | `scene_atmosphere_guide`（4 种氛围） | writer |
| 时间约束 | `timeline.timeLogic.constraints + travelTimes` | writer, reviewer |
| 伏笔提示 | `foreshadowing[].hints`（非空 hints 的伏笔） | writer |

---

## 七、程序化检查规则（⚙️ 代码硬编码）

这些规则在 Tracker 中实现，每章写完后自动执行，不需要 AI 或用户干预。

| 规则 | 定义位置 | 作用 |
|------|---------|------|
| `_BANNED_REPLACEMENTS`（约 60 个词） | tracker.py | AI 高频词自动替换（如"然而"→"但是"） |
| `_EMPTY_PHRASES`（6 个短语） | tracker.py | 空洞短语自动删除（如"广泛关注"） |
| `_ABSTRACT_NOUNS`（8 个词） | tracker.py | 抽象名词检测报告（如"价值"、"认知"） |
| `_SENTENCE_RULES` | tracker.py | 连续长句≥4句/连续短句≥5句告警 |
| `max_run_long` | `4` | 连续超过 35 字的句子数量上限 |
| `max_run_short` | `5` | 连续不足 12 字的句子数量上限 |
| `short_threshold` | `12` 字 | 短句判定阈值 |
| `long_threshold` | `35` 字 | 长句判定阈值 |
| `_CLICHE_PAIRS`（5 对） | tracker.py | 陈词滥调检测（如"坚持就是胜利"→具体描写建议） |

---

## 八、LLM 客户端行为参数（⚙️ 代码硬编码）

| 参数 | 值 | 定义位置 |
|------|-----|---------|
| API 重试次数 | `3` | llm_client.py `max_retries` |
| 文本续写最大次数 | `3` | llm_client.py `max_continuations` |
| JSON 重试最大次数 | `3` | llm_client.py `max_continuations` |
| 重试退避基数 | `2`（2s → 4s → 8s） | llm_client.py `wait = 2 ** (attempt + 1)` |
| 摘要截取首尾字数 | `3000` 字 | context_manager.py |
| 上下文总字符预算 | `60000` 字 | context_manager.py `MAX_CONTEXT_CHARS` |
| 上下文压缩：保留最近 | `3` 章完整摘要 | context_manager.py |
| 上下文压缩：压缩范围 | 第 4-10 章缩略 | context_manager.py |
| 自动修复置信度阈值 | `0.9` | pipeline.py（reviewer 建议修复门槛） |
| 短文续写触发比例 | `0.9`（90%） | writer.py（字数不足 words_min*90% 时续写） |
| 世界观数据截断 | `2000` 字 | reviewer.py |
| 前后章节衔接参考 | `800` 字 | pipeline.py |
| Critic 章节截断 | `8000` 字 | critic.py |
| 场景氛围指南 | 4 种（欢快/紧张/神秘/浪漫） | tracker.py |
| L3 分析频率 | 每 5 章 | pipeline.py `ch_num % 5 == 0` |

---

## 九、已修复问题记录

以下问题在 2026-05-20 代码审查中发现并修复：

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #1 | 严重 | `_apply_strictness` 设置的审核严格度在 `_init_config` 中被覆盖丢失 | tracker.py `_init_config` |
| #2 | 严重 | `_consume_review` 当 `consistency_checks` 为空时提前返回，跳过 issues 和 auto_fix 处理 | tracker.py `_consume_review` |
| #3 | 中等 | `_init_relationships` 关系分类检查整段文本导致错误分类 | tracker.py `_init_relationships`（改用分句匹配） |
| #4 | 中等 | Style advisor prompt 缺少 `critic` 温度推荐，CriticAgent 永远不会获得动态温度 | prompts/style_advisor_system.txt |
| #5 | 中等 | `update_from_review` 新建伏笔状态为 `active` 而非 `planted`，导致遗忘检测永远不触发 | tracker.py `update_from_review` |
| #6 | 轻微 | `auto_fix_suggestions` 用 `str.replace()` 替换所有匹配而非仅第一个 | pipeline.py `_write_chapters`（改为 `replace(..., 1)`） |
| #7 | 轻微 | editor.py 切片语法 `[:500:]` 多余冒号 | agents/editor.py |
