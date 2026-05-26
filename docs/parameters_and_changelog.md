# 参数参考表

本文档是项目中所有可配置参数、硬编码常量、数据链路分层、CSV 字段映射及 bug 修复记录的**权威来源**。
字段链路的消费细节请查阅 `docs/system_reference.md`；验证协议请查阅 `docs/verification_protocol.md`；**接到需求的执行流程请先读 `docs/execution_workflow.md`**。

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

决策链：🔧 config.yaml 默认值 → 🤖 AI 推荐值 → 👤 用户确认

| 参数 | 🔧 默认值 | 🤖 AI 来源 | 👤 确认位置 | 最终存储 |
|------|-----------|-----------|------------|---------|
| 总章数 | `20` (`novel.default_chapters`) | `style_guide.suggestions.total_chapters.recommended` | `_collect_params` input | `state.total_chapters` |
| 每章最少字数 | `3000` (`novel.words_per_chapter.min`) | `style_guide.suggestions.words_per_chapter.min` | `_collect_params` input | `state.novel_params` |
| 每章最多字数 | `5000` (`novel.words_per_chapter.max`) | `style_guide.suggestions.words_per_chapter.max` | `_collect_params` input | `state.novel_params` |
| 审核最大重写次数 | `2` | —（无 AI 推荐） | —（直接用默认值） | config.yaml `novel.review_max_retries`（I2 硬上限：从 3 降为 2，覆盖 90% 修复场景同时降低 token 消耗，#184） |
| 摘要最大字数 | `800` | —（无 AI 推荐） | —（直接用默认值） | config.yaml `novel.summary_max_length` |
| 卷级摘要最大字数 | `1200` | —（无 AI 推荐） | —（直接用默认值） | config.yaml `novel.volume_summary_max_length`（Level 3 宏观摘要长度上限，#184） |
| 卷级摘要触发最小章数 | `3` | —（无 AI 推荐） | —（直接用默认值） | config.yaml `novel.volume_summary_min_chapters`（卷内累计 ≥N 章才生成卷摘要，#184） |
| 上下文预算·输出预留 | `9000` 字 | — | — | config.yaml `context_budget.reserved_output_chars`（#184） |
| 上下文预算·Writer system 上限 | `40000` 字 | — | — | config.yaml `context_budget.writer_system_chars`（#184） |
| 上下文预算·running_context 上限 | `50000` 字 | — | — | config.yaml `context_budget.running_context_chars`（#184，原 80000 写死） |
| 上下文预算·tracking 上限 | `8000` 字 | — | — | config.yaml `context_budget.tracking_context_chars`（#184，原 15000 写死） |
| 上下文预算·rewrite ctx 上限 | `8000` 字 | — | — | config.yaml `context_budget.rewrite_ctx_cap`（#184，原 30000 写死） |
| 上下文预算·续写尾部字数 | `2000` 字 | — | — | config.yaml `context_budget.continuation_tail_chars`（#184） |
| 上下文预算·近端完整摘要章数 | `3` | — | — | config.yaml `context_budget.recent_chapters_full`（#184） |
| 上下文预算·中程精简摘要章数 | `7` | — | — | config.yaml `context_budget.recent_chapters_condensed`（#184） |
| 上下文预算·检索锚点数 | `8` | — | — | config.yaml `context_budget.foreshadowing_top_k`（#184） |

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

### STYLE_FIELDS 分发过滤（agents/base.py 权威来源）

| Agent | 收到的字段 |
|-------|----------|
| director | tone, pacing, plot, character, worldbuilding, setting, style_presets |
| plotter | tone, pacing, plot, character, worldbuilding, setting, style_presets |
| writer | tone, pacing, plot, character, worldbuilding, setting, style_presets, **requirements** |
| reviewer | tone, character, worldbuilding, review, requirements, setting |
| editor | tone, pacing, character, editing, style_presets, requirements |
| critic | character, worldbuilding, setting, requirements |

注：未在 `STYLE_FIELDS` 中明确列出的 Agent（如 style_advisor 自身）将接收完整 style_guide。

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
| 爽文、复仇、言情、甜文、虐文、网文、玄幻、仙侠、都市 | `flexible` |
| 未匹配 | `strict`（默认） |

### 退休元素与禁用检查

| 参数 | 来源 | 说明 |
|------|------|------|
| `config.retired.characters` | —（未融入，预留） | 标记不再追踪的角色 |
| `config.retired.plotlines` | —（未融入，预留） | 标记不再追踪的支线 |
| `config.retired.foreshadowing` | —（未融入，预留） | 标记不再追踪的伏笔 |
| `config.disabled_checks` | 👤 用户输入 | 在 `_collect_params` 阶段设置，控制 `get_tracking_context` 输出哪些块（character/timeline/worldbuilding/locations） |
| `config.active_validation_level` | 🔄 自动设置 | `validation_rules.json` 记录当前激活的验证级别 |

`config.strictness` 与 `active_validation_level` 的映射：strict→deep，flexible→standard

---

## 六、追踪数据流分层（🔄 自动流转 + 🤖 AI 生成）

追踪系统 6 个 JSON 文件的字段通过三层机制保持活跃。

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
| `timeline.timeLogic.travelTimes.routes` | `world_data.geography.travel_routes` | init (`_extract_travel_routes`) |
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
| `character_state.consistency.warnings` | `consistency_checks.knowledge_state_issues` | `_consume_review` |

### L3 独立 LLM 分析（每 5 章 1 次调用）

| 目标字段 | 说明 |
|---------|------|
| `protagonist.development.currentPhase` | 起点→成长→蜕变→成熟 |
| `protagonist.development.nextGoal` | 下一个目标预测 |
| `protagonist.development.milestones[]` | 关键转折点 |
| `supportingCharacters[].arc.current` | 配角发展现状 |
| `supportingCharacters[].motivations[]` | 配角动机推断 |
| `plotlines.main.plannedClimax` | 高潮位置预测 |

### get_tracking_context 输出块

| 输出块 | 数据源 | 受 disabled_checks 控制 | 消费者 |
|--------|--------|----------------------|--------|
| 角色状态追踪 | `character_state.protagonist + supportingCharacters` | `"character"` | writer, editor |
| 分组、警告、详细状态、心理深度 | `character_state.characterGroups + consistency` | `"character"` | writer, editor |
| 近期时间线、时间异常、时间约束 | `timeline.events + anomalies + timeLogic` | `"timeline"` | writer, reviewer |
| 活跃伏笔、活跃冲突、已解决冲突、剧情问题 | `plot_tracker.foreshadowing + conflicts + notes` | `"worldbuilding"` | writer, reviewer |
| 角色关系、动态关系变化 | `relationships.*` | ❌ 始终输出 | writer, editor |
| 场景地点、五感参考、氛围指南 | `locations.locations + scene_atmosphere_guide` | `"locations"` | writer |
| 审核严格度描述 | `config.strictness` | ❌ 始终输出 | reviewer |

注：`validation_rules.json` **不在** `get_tracking_context` 输出中，仅供 `auto_fix` 内部使用。

---

## 七、程序化检查规则（⚙️ 代码硬编码）

这些规则在 Tracker 中实现，每章写完后自动执行，不需要 AI 或用户干预。

| 规则 | 定义位置 | 作用 |
|------|---------|------|
| `_BANNED_REPLACEMENTS`（81 个词） | tracker.py | AI 高频词自动替换（如"然而"→"但是"） |
| `_EMPTY_PHRASES`（6 个短语） | tracker.py | 空洞短语自动删除（如"广泛关注"） |
| `_ABSTRACT_NOUNS`（8 个词） | tracker.py | 抽象名词检测报告（如"价值"、"认知"） |
| `_SENTENCE_RULES` | tracker.py | 连续长句≥4句/连续短句≥5句告警 |
| `max_run_long` | `4` | 连续超过 35 字的句子数量上限 |
| `max_run_short` | `5` | 连续不足 12 字的句子数量上限 |
| `short_threshold` | `12` 字 | 短句判定阈值 |
| `long_threshold` | `35` 字 | 长句判定阈值 |
| `_CLICHE_PAIRS`（5 对） | tracker.py | 陈词滥调检测（如"坚持就是胜利"→具体描写建议） |

硬编码与 prompt 的同步要求：

| 列表 | prompt 同步点 |
|------|-------------|
| `_BANNED_REPLACEMENTS` | writer_system.txt、editor_system.txt、reviewer_system.txt、style_advisor_system.txt |
| `_EMPTY_PHRASES` | editor_system.txt、reviewer_system.txt |
| `_CLICHE_PAIRS` | reviewer_system.txt（陈词滥调具体列表）、editor_system.txt |

---

## 八、LLM 客户端与 pipeline 行为参数（⚙️ 代码硬编码）

| 参数 | 值 | 定义位置 |
|------|-----|---------|
| API 重试次数 | `3` | llm_client.py `max_retries` |
| 文本续写最大次数 | `3` | llm_client.py `max_continuations` |
| JSON 续写最大次数 | `3` | llm_client.py `max_continuations` |
| 重试退避基数 | `2`（2s → 4s → 8s） | llm_client.py `wait = 2 ** (attempt + 1)` |
| 摘要截取首尾字数 | `3000` 字 | context_manager.py |
| 上下文总字符预算 | 动态（默认 `50000` 字，配置驱动） | context_manager.py `max_context_chars`（来源 `context_budget.running_context_chars`，#184 从 80000 硬编码改为配置） |
| 上下文压缩：保留最近 | `3` 章完整摘要（配置驱动） | context_manager.py `recent_chapters_full`（#184） |
| 上下文压缩：压缩范围 | 中程 `7` 章一句话摘要 + 更早聚合到卷级（配置驱动） | context_manager.py `recent_chapters_condensed`（#184，原硬编码"4-10 章缩略"） |
| 三级金字塔摘要 | Level 3 卷级（卷末生成） + Level 2 章节（近 3 全/再 7 简） + Level 1 原文片段（近 3 章首尾各 750 字） | context_manager.py + pipeline.py `_collect_recent_excerpts` / `_maybe_generate_volume_summary`（#184） |
| 检索锚点（伏笔/角色） | 按当前章节计划做相关度检索，top_k=8 注入 | tracker.py `query_relevant`（#184） |
| Tracker 输出上限 | `8000` 字（调用方可传 `max_chars` 覆盖） | tracker.py `get_tracking_context(max_chars=...)`（#184，原硬编码 15000） |
| 续写滑窗 | 仅回传 `plan_anchor (≤1500 字)` + 草稿尾部 `2000` 字 + 继续指令；不再无限累加 messages | llm_client.py `_continue_text` + writer.py `_plan_anchor`（#184，原 messages.append 累加会再次溢出） |
| Token 估算系数 | 中文 1.5 token/字 / 英文 0.3 token/字 | llm_client.py `estimate_tokens`（#184） |
| 调用前预算预警 | `est_input + reserved_output > max_tokens` 时 warn 日志 | llm_client.py `_check_budget`（#184） |
| Writer rewrite ctx 上限 | `8000` 字（配置驱动） | writer.py `rewrite_ctx_cap`（来源 `context_budget.rewrite_ctx_cap`，#184，原硬编码 30000） |
| 自动修复置信度阈值 | `0.9` | pipeline.py（reviewer 建议修复门槛） |
| 短文续写触发比例 | `0.9`（90%） | writer.py（字数不足 words_min*90% 时续写） |
| 世界观数据截断 | `2000` 字 | reviewer.py |
| 前后章节衔接参考 | `800` 字 | pipeline.py |
| Critic 章节截断 | `8000` 字 | critic.py |
| 场景氛围指南 | 4 种（欢快/紧张/神秘/浪漫） | tracker.py |
| L3 分析频率 | 每 5 章 | pipeline.py `ch_num % 5 == 0` |
| `_condense_world` 提取字段数 | 11 类（name, tone, setting, narrative_perspective, unique_elements, rules, social_structure, geography, factions, history, daily_life, characters 含 background） | context_manager.py |
| `_condense_outline` 提取字段数 | 4 个（theme, three_act, ending, key_turning_points） | context_manager.py |
| `_format_chapter_plan` 格式化字段数 | 15 个（title, summary, plot_points, emotional_arc, emotional_type/intensity, characters_involved, foreshadowing, active_plotlines, act, cliffhanger, scene_structure, tension_level, location, time） | context_manager.py |
| 追踪文件初始化检查范围 | 全部 6 个 `_TRACKING_FILES` + `config.json` | pipeline.py Phase 2.5 |
| 追踪文件初始化策略 | 仅初始化磁盘上不存在的文件（保护已有数据） | tracker.py `init_tracking(missing=None)` |
| JSON 原子写入 | tmp+replace 模式（state.json / world.json / outline.json / chapters.json / tracking/*.json / review_reports/*.json） | state_manager.py `atomic_write_json` |
| 小说名长度上限 | 64 字符 | core/name_generator.py `_MAX_NAME_LENGTH` |
| 小说名非法字符 | `\\ / : * ? " < > \|` + Windows 保留名（CON/PRN/AUX/NUL/COM1-9/LPT1-9） + 尾部 `.`/空格 + Unicode 控制字符 | core/name_generator.py `sanitize_novel_name` |
| 交互输入层 | WebSocket 双向通信（`_send_input_request` → 前端 → 响应匹配） | core/prompt_utils.py |
| 用户中断信号 | `UserAbort` 异常（前端取消 / WebSocket 断开时触发） | core/prompt_utils.py `UserAbort` |
| 会话管理 | `threading.local()` 绑定当前线程的 BridgeSession | core/prompt_utils.py |
| 输出层 | WebSocket 输出队列（`_send_output` → `output_queue` → 前端） | core/ui.py |
| AI 小说名候选数量 | `3` | core/name_generator.py `suggest_novel_names(..., n=3)` |
| AI 起名温度 | `0.9` | core/name_generator.py `suggest_novel_names` |
| AI 起名候选最长字符数 | `12` | core/name_generator.py `_clean_candidate` |
| Braindump 章节温度 | `0.7`（初版/调整）/ `0.9`（rewrite） | core/braindump.py `_braindump_section` |
| Braindump system 构造 | `_build_braindump_system(style, is_rewrite)` 拼三段：`_BRAINDUMP_SYSTEM_BASE` + 可选 `_BRAINDUMP_STYLE_GUIDANCE`（style 注入）+ `_BRAINDUMP_NEUTRAL_TAIL` + 可选 `_REWRITE_DIRECTIVE` | core/braindump.py |
| Braindump rewrite 反上下文 | rewrite 分支把 `prev_result` 拼到 user_msg "之前生成的{label}（用户不满意，请勿沿用此方向）" | core/braindump.py `_braindump_section` |
| Writer rewrite 温度 | `min(self._temperature() + 0.15, 0.9)`（基于初稿温度上调） | agents/writer.py `rewrite` |
| Writer rewrite system 增强 | `_build_system_prompt(..., is_rewrite=True)` 在 system 尾部追加"## 重写专项要求"段（强调实质性改写，不能字面微调） | agents/writer.py |
| 精修阶段 system_prompt | 5 个常量：4 个 per-block（world/character/location/outline）+ `REFINE_HOLISTIC_PROMPT`（全量精修）+ `REFINE_REWRITE_DIRECTIVE`（rewrite 时拼接到 system） | core/refine_prompts.py |
| 精修策略 | 全量精修（holistic）：每次调整将完整 director JSON（world_data + characters + locations + outline）发送给 LLM，确保跨 block 一致性 | core/pipeline.py `_run_directing_holistic` |
| 精修 LLM 温度 | `0.7`（初版/调整）/ `0.9`（rewrite） | core/pipeline.py `_llm_refine` |
| 精修 rewrite 反上下文 | rewrite=True 时 user_msg 含"之前的版本（用户不满意，请勿沿用此方向）" + previous JSON | core/pipeline.py `_llm_refine` |
| 精修 block 类型 | `world` / `character:<name>` / `location:<name>` / `outline` | core/pipeline.py `_refine_*` |
| 精修上下文裁剪 | 故事火花 600 字 / 世界观 800 字 / 大纲 600 字 | core/pipeline.py `_build_refine_context` |
| Web 服务端口 | `0.0.0.0:8000`（uvicorn 默认） | web_main.py |
| WebSocket 路径 | `/ws`（双向 JSON 协议：output / input_request / session_started / session_ended） | web/app.py |
| REST API 前缀 | `/api`（novels 列表/详情/章节内容） | web/routers/novels.py |
| 前端静态文件 | `frontend/dist/`（Vue3 SPA 构建产物，由 FastAPI 直接服务） | web/app.py |
| 桥接层 | 猴子补丁已移除，core/prompt_utils.py 和 core/ui.py 已是 Web 原生实现 | web/bridge/__init__.py |
| 会话线程隔离 | `threading.local()` 绑定当前线程的 BridgeSession | web/bridge/session.py |

---

## 九、tracking_changes.csv 字段映射

`tracking_changes.csv` 记录每章追踪数据变化，CSV 格式（UTF-8 BOM）：

### CSV 列定义

| 列名 | 说明 |
|------|------|
| `章节` | 章节编号 |
| `字段路径` | 变更字段的 JSON 路径（如 `protagonist.currentStatus.location`） |
| `含义` | 字段中文含义（由 `_lookup_field_meaning` 自动填充） |
| `变化` | 变更内容（新值 或 `旧值 → 新值`） |
| `来源` | 变更来源（L1/L2/L3） |

### 字段路径 → 中文映射（tracker.py `_FIELD_MEANINGS` 权威来源）

匹配规则：`_lookup_field_meaning` 按"最长前缀匹配"原则，优先匹配更具体的字段路径。

#### character_state.json

| 字段路径 | 中文含义 |
|---------|---------|
| `character_state.novel` | 小说名称 |
| `character_state.lastUpdated` | 最后更新时间 |
| `character_state.protagonist.name` | 主角姓名 |
| `character_state.protagonist.currentStatus.alive` | 主角是否存活 |
| `character_state.protagonist.currentStatus.health` | 主角健康状况 |
| `character_state.protagonist.currentStatus.mentalState` | 主角精神状态 |
| `character_state.protagonist.currentStatus.location` | 主角当前位置 |
| `character_state.protagonist.currentStatus.chapter` | 主角最后出现章节 |
| `character_state.protagonist.currentStatus.age` | 主角年龄 |
| `character_state.protagonist.currentStatus.position` | 主角身份/职位 |
| `character_state.protagonist.currentStatus.possessions` | 主角持有物品 |
| `character_state.protagonist.currentStatus.skills` | 主角技能列表 |
| `character_state.protagonist.currentStatus.knowledge` | 主角已知信息 |
| `character_state.protagonist.development.arc` | 主角成长弧线 |
| `character_state.protagonist.development.milestones` | 主角成长里程碑 |
| `character_state.protagonist.development.currentPhase` | 主角当前成长阶段 |
| `character_state.protagonist.development.nextGoal` | 主角下一目标 |
| `character_state.supportingCharacters` | 配角数据 |
| `character_state.characterGroups.active` | 活跃角色列表 |
| `character_state.characterGroups.inactive` | 不活跃角色列表 |
| `character_state.characterGroups.deceased` | 已死亡角色列表 |
| `character_state.appearanceTracking` | 角色出场追踪记录 |
| `character_state.consistency.physicalTraits` | 外貌一致性（角色→外貌描述） |
| `character_state.consistency.personalityTraits` | 性格一致性（角色→性格特征） |
| `character_state.consistency.speechPatterns` | 语言风格一致性（角色→说话习惯） |
| `character_state.consistency.warnings` | 一致性警告列表 |

#### timeline.json

| 字段路径 | 中文含义 |
|---------|---------|
| `timeline.novel` | 小说名称 |
| `timeline.lastUpdated` | 最后更新时间 |
| `timeline.storyTime.start` | 故事起始时间 |
| `timeline.storyTime.current` | 故事当前时间 |
| `timeline.storyTime.end` | 故事结束时间 |
| `timeline.storyTime.format` | 时间标记方式 |
| `timeline.events` | 故事事件时间线 |
| `timeline.parallelEvents.timepoints` | 并行事件时间点 |
| `timeline.historicalContext.events` | 历史背景事件 |
| `timeline.timeLogic.travelTimes.routes` | 旅行时间（路线→耗时） |
| `timeline.timeLogic.constraints` | 时间逻辑约束 |
| `timeline.anomalies.issues` | 时间线异常/矛盾 |

#### plot_tracker.json

| 字段路径 | 中文含义 |
|---------|---------|
| `plot_tracker.novel` | 小说名称 |
| `plot_tracker.lastUpdated` | 最后更新时间 |
| `plot_tracker.currentState.chapter` | 当前进度章节 |
| `plot_tracker.currentState.volume` | 当前卷数 |
| `plot_tracker.currentState.mainPlotStage` | 主线阶段（开端/发展/高潮/结局） |
| `plot_tracker.currentState.location` | 当前场景地点 |
| `plot_tracker.currentState.timepoint` | 当前时间点 |
| `plot_tracker.plotlines.main.name` | 主线名称 |
| `plot_tracker.plotlines.main.description` | 主线描述 |
| `plot_tracker.plotlines.main.status` | 主线状态（active/completed） |
| `plot_tracker.plotlines.main.currentNode` | 主线当前剧情节点 |
| `plot_tracker.plotlines.main.completedNodes` | 已完成剧情节点 |
| `plot_tracker.plotlines.main.upcomingNodes` | 即将到来的剧情节点 |
| `plot_tracker.plotlines.main.plannedClimax.chapter` | 计划高潮章节 |
| `plot_tracker.plotlines.main.plannedClimax.description` | 计划高潮描述 |
| `plot_tracker.plotlines.subplots` | 支线剧情 |
| `plot_tracker.foreshadowing` | 伏笔列表 |
| `plot_tracker.conflicts.active` | 进行中的冲突 |
| `plot_tracker.conflicts.resolved` | 已解决的冲突 |
| `plot_tracker.conflicts.upcoming` | 即将到来的冲突 |
| `plot_tracker.checkpoints.volumeEnd` | 卷末检查点 |
| `plot_tracker.checkpoints.majorEvents` | 重大事件记录 |
| `plot_tracker.notes.plotHoles` | 剧情漏洞记录 |
| `plot_tracker.notes.inconsistencies` | 剧情不一致记录 |
| `plot_tracker.notes.reminders` | 剧情提醒 |

#### relationships.json

| 字段路径 | 中文含义 |
|---------|---------|
| `relationships.novel` | 小说名称 |
| `relationships.lastUpdated` | 最后更新时间 |
| `relationships.characters` | 角色关系数据 |
| `relationships.factions` | 势力/阵营 |
| `relationships.relationshipMatrix.matrix` | 角色关系矩阵 |
| `relationships.conflicts.personal` | 个人冲突 |
| `relationships.conflicts.factional` | 阵营冲突 |
| `relationships.conflicts.ideological` | 理念冲突 |
| `relationships.history` | 关系变化历史 |
| `relationships.predictions.likely` | 高概率关系变化预测 |
| `relationships.predictions.possible` | 可能的关系变化预测 |

#### validation_rules.json

| 字段路径 | 中文含义 |
|---------|---------|
| `validation_rules.version` | 规则版本 |
| `validation_rules.characters.protagonist.name` | 主角姓名（验证用） |
| `validation_rules.characters.protagonist.aliases` | 主角别名 |
| `validation_rules.characters.protagonist.forbidden` | 主角禁用称呼 |
| `validation_rules.characters.protagonist.traits` | 主角特征（外貌/能力/年龄） |
| `validation_rules.characters.supporting` | 配角验证规则 |
| `validation_rules.relationships.fixed_addresses.rules` | 固定称呼规则 |
| `validation_rules.relationships.forbidden_addresses.rules` | 禁用称呼规则 |
| `validation_rules.validation_tasks.character_consistency` | 角色一致性检查 |
| `validation_rules.validation_tasks.character_consistency.checks` | 检查项（姓名/特征/行为） |
| `validation_rules.validation_tasks.relationship_validation` | 关系验证检查 |
| `validation_rules.validation_tasks.relationship_validation.checks` | 检查项（称呼/发展/交互） |
| `validation_rules.validation_tasks.world_rules` | 世界规则检查 |
| `validation_rules.validation_tasks.world_rules.checks` | 检查项（力量体系/地理/时间线） |
| `validation_rules.validation_tasks` | 验证任务开关 |
| `validation_rules.auto_fix.character_names` | 自动修复角色名称 |
| `validation_rules.auto_fix.character_names.confidence_threshold` | 自动修复置信度阈值 |
| `validation_rules.auto_fix.addresses` | 自动修复称呼 |
| `validation_rules.auto_fix.simple_typos` | 自动修复简单拼写错误 |
| `validation_rules.auto_fix.complex_issues` | 自动修复复杂问题 |
| `validation_rules.common_errors.character_substitution` | 常见角色混淆错误 |
| `validation_rules.common_errors.address_mistakes` | 常见称呼错误 |
| `validation_rules.validation_levels.quick` | 快速验证级别 |
| `validation_rules.validation_levels.quick.checks` | 快速验证检查项 |
| `validation_rules.validation_levels.quick.time_estimate` | 预计耗时 |
| `validation_rules.validation_levels.standard` | 标准验证级别 |
| `validation_rules.validation_levels.standard.checks` | 标准验证检查项 |
| `validation_rules.validation_levels.standard.time_estimate` | 预计耗时 |
| `validation_rules.validation_levels.deep` | 深度验证级别 |
| `validation_rules.validation_levels.deep.checks` | 深度验证检查项 |
| `validation_rules.validation_levels.deep.time_estimate` | 预计耗时 |

#### locations.json

| 字段路径 | 中文含义 |
|---------|---------|
| `locations.novel` | 小说名称 |
| `locations.lastUpdated` | 最后更新时间 |
| `locations.locations` | 场景地点列表 |
| `locations.scene_atmosphere_guide` | 场景氛围写作指南 |

#### 通用后缀映射（适用于多个文件的嵌套字段）

| 后缀路径 | 中文含义 |
|---------|---------|
| `.role` | 角色定位（如反派/导师） |
| `.importance` | 重要性 |
| `.status.alive` | 角色是否存活 |
| `.status.lastSeen.chapter` | 角色最后出现章节 |
| `.status.lastSeen.location` | 角色最后出现位置 |
| `.status.currentLocation` | 角色当前位置 |
| `.status.occupation` | 角色职业 |
| `.arc.planned` | 角色预设成长弧线 |
| `.arc.current` | 角色当前成长状态 |
| `.secrets` | 角色秘密 |
| `.motivations` | 角色动机 |
| `.significance` | 出场重要性 |
| `.chapter` | 所在章节 |
| `.date` | 事件日期 |
| `.event` | 事件标题 |
| `.duration` | 持续时长 |
| `.participants` | 参与者 |
| `.name` | 名称 |
| `.description` | 描述 |
| `.status` | 状态 |
| `.content` | 伏笔内容 |
| `.planted.chapter` | 伏笔埋设章节 |
| `.planted.description` | 伏笔埋设描述 |
| `.hints` | 伏笔提示/呼应 |
| `.plannedReveal.chapter` | 计划揭示章节 |
| `.plannedReveal.description` | 计划揭示描述 |
| `.relationships.allies` | 盟友 |
| `.relationships.enemies` | 敌人 |
| `.relationships.romantic` | 恋爱关系 |
| `.relationships.family` | 家人 |
| `.relationships.mentors` | 师徒关系 |
| `.relationships.neutral` | 中立关系 |
| `.relationships.unknown` | 未知关系 |
| `.dynamicRelations` | 动态关系变化记录 |
| `.leader` | 势力领袖 |
| `.members` | 势力成员 |
| `.goals` | 势力目标 |
| `.alliedWith` | 盟友势力 |
| `.opposedTo` | 敌对势力 |
| `.aliases` | 别名 |
| `.addresses_to` | 称呼方式 |
| `.enabled` | 是否启用 |
| `.type` | 地点类型 |
| `.scale` | 地点规模 |
| `.position` | 地理位置 |
| `.first_appearance` | 首次出现 |
| `.five_senses` | 场景五感描述 |
| `.function` | 地点功能/用途 |
| `.atmosphere` | 场景氛围 |
| `.related_characters` | 关联角色 |
| `.events` | 地点相关事件 |

> **同步要求**：每次新增追踪字段时，必须在 `tracker.py _FIELD_MEANINGS` 中追加映射，并同步更新本文档此章节。

---

## 十、已修复问题记录

### 2026-05-20 第一轮代码审查

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #1 | 严重 | `_apply_strictness` 设置的审核严格度在 `_init_config` 中被覆盖丢失 | tracker.py `_init_config` |
| #2 | 严重 | `_consume_review` 当 `consistency_checks` 为空时提前返回，跳过 issues 和 auto_fix 处理 | tracker.py `_consume_review` |
| #3 | 中等 | `_init_relationships` 关系分类检查整段文本导致错误分类 | tracker.py `_init_relationships`（改用分句匹配） |
| #4 | 中等 | Style advisor prompt 缺少 `critic` 温度推荐，CriticAgent 永远不会获得动态温度 | prompts/style_advisor_system.txt |
| #5 | 中等 | `update_from_review` 新建伏笔状态为 `active` 而非 `planted`，导致遗忘检测永远不触发 | tracker.py `update_from_review` |
| #6 | 轻微 | `auto_fix_suggestions` 用 `str.replace()` 替换所有匹配而非仅第一个 | pipeline.py `_write_chapters` |
| #7 | 轻微 | editor.py 切片语法 `[:500:]` 多余冒号 | agents/editor.py |
| #8 | 严重 | `PlotAgent._agent_name()` 返回 `"plot"` 而非 `"plotter"` | agents/base.py `_AGENT_CONFIG_KEYS` |
| #9 | 严重 | `_truncate_context` 中 `pop(0)` 优先删除最新3章摘要而非最旧的压缩版 | context_manager.py `_truncate_context` |
| #10 | 中等 | `NovelState.__post_init__` 每次加载都覆盖 `updated_at` | state_manager.py `__post_init__` |
| #11 | 中等 | `revise_chapter` 中 `chapter_plans[chapter_number - 1]` 无边界检查 | pipeline.py `revise_chapter` |
| #12 | 中等 | `style_advisor.py` 未处理 `chat_json` 返回 list 的情况 | agents/style_advisor.py `run` |
| #13 | 中等 | `llm_client.py` 的 `chat()` 末尾 `return text` 是死代码且 `text` 变量可能未绑定 | llm_client.py `chat` |
| #14 | 中等 | `reviewer.py` 世界观数据截断到 2000 字时可能截断在 JSON 结构中间 | agents/reviewer.py |
| #15 | 轻微 | `tracker.py` 中 `import re` 放在函数体内两处，应移至文件顶部 | tracker.py |

### 2026-05-20 第二轮审查

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #16 | 严重 | `_execute_revise` 不传 `review` 给 `update_tracking`，修订后追踪数据不消费 reviewer 输出 | pipeline.py `_execute_revise` |
| #17 | 严重 | `_execute_revise` 不执行 `auto_fix` 和 `auto_fix_banned_words`，修订章节缺少程序化修复 | pipeline.py `_execute_revise` |
| #18 | 严重 | 伏笔退休用 ID 但遗忘检测用 content 匹配，导致退休操作无效 | tracker.py `check_forgotten` |
| #19 | 中等 | `_execute_revise` 不更新 `ch.review_status` 和 `ch.review_notes` | pipeline.py `_execute_revise` |

### 2026-05-26 错误展示修复

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #20 | 严重 | 同一异常被 phase handler、top-level handler、web handler 三层重复展示，用户看到 3xERROR + 3xHINT | pipeline.py 阶段/top-level handler + web/app.py |
| #21 | 中等 | phase/top-level handler 将原始 JSON 片段拼入 `ui.error` 暴露给用户 | pipeline.py 三处 phase handler |
| #22 | 轻微 | pipeline.py 4 处引用已废弃的 `python main.py continue` CLI 命令（项目已迁移至 Web） | pipeline.py `_handle_interrupt` + 三处 phase handler |
| #20 | 中等 | `_execute_revise` 不执行质量检查（陈词滥调、句式、抽象名词） | pipeline.py `_execute_revise` |
| #21 | 中等 | `update_tracking` 缺少同场角色双向 dynamicRelations 记录 | tracker.py `update_tracking` |
| #22 | 中等 | 主角 skills/knowledge 列表无去重，多章累积导致数据膨胀 | tracker.py `update_tracking` |
| #23 | 中等 | `writer.py` `.format()` 如果 constitution.md 含花括号会崩溃 | agents/writer.py |
| #24 | 轻微 | `_truncate_context` "省略N章"计数包含设计上本就排除的章节 | context_manager.py `_truncate_context` |
| #25 | 轻微 | `get_tracking_context` 重复读取 `plot_tracker.json`，浪费 I/O | tracker.py `get_tracking_context` |

### 2026-05-21 数据链路审查

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #26 | 严重 | Director 输出 `locations` 未存入 `world_data` | pipeline.py Phase 1 |
| #27 | 严重 | `_condense_world` 仅提取 setting 和 characters，丢失 8 类关键字段 | context_manager.py `_condense_world` |
| #28 | 严重 | `_condense_outline` 未提取 `key_turning_points` | context_manager.py `_condense_outline` |
| #29 | 严重 | `_format_chapter_plan` 仅格式化 7 个字段，丢失 8 个字段 | context_manager.py `_format_chapter_plan` |
| #30 | 中等 | Plotter prompt 缺少 `location`/`time`/`duration` 输出字段定义 | prompts/plotter_system.txt |
| #31 | 中等 | Director prompt 缺少角色 `aliases` 字段 | prompts/director_system.txt |
| #32 | 中等 | `_consume_review` 中 timeline 在循环内重复写入；`if notes:` 对 dict 类型永远为 True | tracker.py `_consume_review` |
| #33 | 中等 | `update_tracking` 中 character_state 被重复读取两次 | tracker.py `update_tracking` |
| #34 | 中等 | Tracker 初始化仅检查 `character_state.json`，不检查其余 5 个追踪文件 | pipeline.py Phase 2.5 |

### 2026-05-21 自检审计

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #35 | 严重 | `config.json` 不在 `_TRACKING_FILES` 中，Phase 2.5 不验证其存在 | pipeline.py Phase 2.5 |
| #36 | 严重 | `writer.rewrite` 缺少字数续写逻辑，审核打回重写后可能产出极短文本 | agents/writer.py `rewrite` |
| #37 | 中等 | `_consume_review` 中 `knowledge_state_issues` 写入 `supportingCharacters[].secrets` 而非 `consistency.warnings` | tracker.py `_consume_review` |
| #38 | 中等 | Director 生成的 `geography.travel_routes` 无人消费 | tracker.py `_init_timeline`（新增 `_extract_travel_routes`） |
| #39 | 轻微 | Director 角色 schema 中 `background` 字段无消费者 | context_manager.py `_condense_world` |
| #40 | 轻微 | `_CLICHE_PAIRS` 5 对陈词滥调未在 reviewer prompt 中列出 | prompts/reviewer_system.txt |
| #41 | 中等 | Director 生成的 `tone` 和 `name` 字段无消费者 | context_manager.py `_condense_world` |
| #42 | 中等 | Reviewer 输出的 `strengths[]` 无人消费 | pipeline.py `_write_chapters` + `_execute_revise` |

### 2026-05-21 文档体系重构

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #43 | 严重 | `StateManager.load` 直接 `NovelState(**data)`，若 state.json 含未知字段会 TypeError | state_manager.py `load`（添加 `__dataclass_fields__` 白名单过滤） |
| #44 | 文档 | docs/ 三份文档职责重叠，无 AI 可执行的验证协议 | 新建 `docs/verification_protocol.md`，重构 parameters.md / self_check.md / flowchart.md |
| #45 | 文档 | `tracking_changes.csv` 字段中文映射仅在 `_FIELD_MEANINGS` 代码中，文档无记录 | parameters.md 第九章新增完整映射表 |

### 2026-05-21 闭环验证发现并修复

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #46 | 中等 | `_GENRE_STRICTNESS` 缺少 `武侠/奇幻/科幻` 三个题材的映射 | **已修复**：pipeline.py `_GENRE_STRICTNESS` 补充 `武侠/奇幻 → flexible`、`科幻 → strict`（D3） |
| #47 | 中等 | `world.json / outline.json / chapters.json / tracking/*.json / review_reports/*.json` 直接 `write_text`，写入瞬间被中断会损坏文件 | **已修复**：state_manager.py 新增 `atomic_write_json(path, data)` 工具函数（tmp+replace），pipeline.py 4 处直接 write_text 和 tracker.py `_write_json` 全部改用该函数（G3） |
| #48 | 中等 | `cmd_new` 小说名缺少文件系统安全校验 | **已修复**：main.py 新增 `_sanitize_novel_name`，校验非法字符（`\\/:*?"<>\|`）、Windows 保留名（CON/PRN/AUX/NUL/COM1-9/LPT1-9）、长度上限 64、尾部 `.`/空格（H2） |
| #49 | 严重 | `init_tracking` 为全量重写，writing 中段恢复时会重置全部追踪数据 | **已修复**：tracker.py `init_tracking` 新增 `missing` 参数，默认按"仅初始化磁盘不存在的文件"策略；pipeline.py Phase 2.5 显式传入 missing 列表（C5） |
| #50 | 轻微 | `Director.run` / `Reviewer.run` 缺少 `isinstance(result, dict)` 检查 | **已修复**：agents/director.py 返回空 dict、agents/reviewer.py 返回安全默认 dict（含 approved/issues/consistency_checks 等字段）（F1） |
| #51 | 严重 | `_write_chapters` 章内中断丢失进度，重启后从同章开头重跑：(a) 已通过审核的草稿被 writer 重写；(b) `update_tracking` 第二次写入 `appearanceTracking / majorEvents / completedNodes / locations.events`，导致同章重复条目 | **已修复**：(1) `ChapterState` 新增 `stage` 字段（pending→drafted→reviewed→tracked），`_write_chapters` 拆分为 3 段，每段完成后保存 state，恢复时按 stage 跳过已完成段；(2) `tracker.update_tracking` 4 处追加列表前增加 `any(e.get("chapter") == chapter_num for e in lst)` 幂等检查 |
| #52 | 严重 | `resume_novel` 只调用 `_apply_style_temperatures`，未调用 `_apply_strictness`：若 `styling` 阶段完成后但 `_apply_strictness` 调用前 crash，下次 resume 时严格度恢复默认（balanced） | **已修复**：pipeline.py `resume_novel` 在 `_apply_style_temperatures` 后追加 `self._apply_strictness(state)`，确保任何恢复都重应用题材严格度 |
| #53 | 中等 | Phase 2.5 中 `_apply_validation_level(tracker)` 嵌套在 `if missing or config_missing:` 内，导致追踪文件已存在时不再根据 strictness 同步 `active_validation_level` | **已修复**：pipeline.py `_apply_validation_level(tracker)` 移出 if 块，每次进入 Phase 2.5 均执行 |
| #54 | 中等 | `revise_chapter` 不检查 `state.phase`，对未完成创作流程的小说（如 phase=writing）也允许修订，可能损坏未润色的草稿链路 | **已修复**：pipeline.py `revise_chapter` 头部新增 `if state.phase not in ("editing", "complete"): return` 守卫 |
| #55 | 轻微 | `_collect_params` 中阈值 / 禁用类别两处 `prompt_single` 的 `UserAbort` 静默吞掉，用户不知道发生了什么 | **已修复**：pipeline.py 两处 `except UserAbort:` 增加明确提示文案（"已保留建议阈值" / "已保留默认（全部启用）"） |

### 2026-05-21 CLI 体验升级（Rich 渲染层 + AI 起名）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #56 | 体验 | CLI 输出为朴素 `print + ===` 文本，缺少视觉层级，且与"高端工具"定位不符 | **已新增**：core/ui.py 基于 rich 13.x 统一所有展示（banner / section / divider / Panel / Table / 颜色），main.py + pipeline.py 关键节点全部迁移到 `ui.*`；保留 prompt_toolkit 处理输入（输入/输出职责分离） |
| #57 | 体验 | `cmd_new` 仅支持手输小说名，缺少 AI 起名辅助 | **已新增**：core/name_generator.py `suggest_novel_names(llm, idea, style, n=3)`；main.py 新增 `_pick_novel_name`：先 yes/no 询问是否 AI 起名 → 是则基于已收集的火花生成 3 候选 → 选/再生成/自输 → 经 `_sanitize_novel_name` 校验；调整 cmd_new 输入顺序为「火花 → 名字 → 风格」以便起名能基于火花 |
| #58 | 体验 | Windows GBK 控制台无法编码 ✓/⚠/ℹ 等 Unicode 符号 + 中文，会抛 UnicodeEncodeError | **已修复**：core/ui.py 在 `import rich` 之前对 win32 平台调用 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，无法编码时 replace 兜底 |
| #59 | 设计权衡 | 原 plan 设计的 `ChapterProgress`（基于 rich.progress.Progress 的 Live 进度条）会与 `_handle_retire` 中 prompt_toolkit 的交互输入抢占终端控制权，导致进度条卡死或输入框错乱 | **已规避**：`_write_chapters` / `_edit_chapters` 不启用 Live 进度条，改用 `ui.section()` 渲染章节头 + `ui.info/warn/success/hint` 滚动输出 stage 进展。`ChapterProgress` 类保留在 `core/ui.py` 以便未来非交互场景使用，但当前主流程不调用 |

### 2026-05-21 参数收集精简 + Director 输出分块打磨循环

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #60 | 体验 | `_collect_params` 末尾"自定义遗忘阈值"和"禁用检查类别"两步对绝大多数用户无意义且过于宽泛（AI 已在 `style_guide.suggestions.tracking_thresholds` 给出推荐值），强制弹出输入框只是制造摩擦 | **已修复**：pipeline.py `_collect_params` 删除这两段 `prompt_single` 交互（原 L328-371），直接采纳 AI 推荐的 `rec_char / rec_plot / rec_foreshadow`，`config["disabled_checks"]` 保持默认空列表（全部启用）；尾部 `show_param_confirmed` Panel 仍展示阈值，让用户知情 |
| #61 | 体验 | Director 一次性生成世界观+角色卡+地点卡+大纲后直接进入 Plotter，用户即使发现"主角性格不对""走向想换"也只能事后修订，代价极高 | **已新增**：在 `directing` 与 `plotting` 之间插入新 phase `refining`（Phase 1.5）；core/pipeline.py 新增 `_refine_director_output` 编排 4 个 block（世界观 / 每张角色卡 / 每张地点卡 / 大纲）的 "是/调整/重写" 三选一循环（参考 braindump 模式）；新增 `_refine_block / _llm_refine / _confirm_refine` 工具方法；NovelState 新增 `refined_blocks: list[str]` 字段记录已确认 block（命名规则：`world` / `outline` / `character:<name>` / `location:<name>`），断点续传时自动跳过；core/refine_prompts.py 新建文件存放 4 个 system_prompt；core/ui.py 新增 `show_refine_block(label, content, modified)` 渲染 dict/list 为 JSON Panel；main.py `phase_names` 新增 `refining → 精修世界观` |

### 2026-05-21 rewrite 实质变化 + braindump 格调适配 style

针对用户实际跑 `new` 后反馈的两个严重问题：

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #62 | 严重 | 三处 rewrite（braindump 章节重写 / writer 审稿打回 / refine 整块重写）都是「同 system + 同 user msg + 同温度」再调一次 LLM，GLM-5.1 输出几乎不变，用户感受"按了重写但内容没变" | **已修复 三重组合**：(a) **反上下文** — rewrite 时把当前版本拼到 user msg 标注"用户不满意，请勿沿用此方向"；(b) **升温** — braindump/refine rewrite 升至 `0.9`，writer rewrite 升至 `min(初稿温度+0.15, 0.9)`；(c) **system 明示** — 新增 3 个常量 `main._REWRITE_DIRECTIVE` / `refine_prompts.REFINE_REWRITE_DIRECTIVE` / writer `_build_system_prompt(is_rewrite=True)` 追加的"重写专项要求"段；`_llm_refine` 签名加 `rewrite=False, previous=None` 参数；`_refine_block` 外层 rewrite 改传 `rewrite=True, previous=result` |
| #63 | 严重 | Braindump system prompt 和 4 个 section prompts 写死"文学顾问 / 情感真相 / 深层主题 / 关键问题 / 英雄之旅 / 文学弧线"等文学化措辞，对网文/言情/甜文/悬疑等题材格调完全错位（用户写"霸总爱上我"，AI 回"探索亲密关系中权力不对等的孤独"） | **已修复**：main.py 删除常量 `_SYSTEM_PROMPT`，改为函数 `_build_braindump_system(style, is_rewrite=False)`，根据传入的 `style` 字符串动态拼接 `_BRAINDUMP_SYSTEM_BASE + _BRAINDUMP_STYLE_GUIDANCE.format(style) + _BRAINDUMP_NEUTRAL_TAIL`，其中 `_BRAINDUMP_STYLE_GUIDANCE` 列出 4 类风格的措辞要求；4 条 section prompts 全部改为"多选词"中性化（核心情感/核心冲突/核心钩子/核心爽点，按故事类型自动选），structure 增加"网文升级流 / 单元剧 / 双线交织"等候选 |

### 2026-05-21 融合 chinese-novelist-skill v2.0（A-J 十组共 30 项）

把 `chinese-novelist-skill/references/guides/*.md` 中的写作方法论批量注入到 prompts 与代码层。30 项融合 / 6 项跳过，每项均已与用户逐一确认。

| 编号 | 组 | 内容 | 注入位置 |
|------|-----|------|----------|
| #64 A1 | 写作 | 十种强力开头技巧（动作开场 / 冲突开场 / 悬念开场 / 反差开场 / 倒叙开场 / 对话开场 / 意象开场 / 信息差开场 / 时间锚点开场 / 视觉冲击开场） | `prompts/writer_system.txt` 输出要求段后 |
| #65 A2 | 写作 | 开头致命错误 6 条（天气开篇 / 日常起床 / 大段回顾 / 缓慢铺垫 / 抽象议论 / 镜中描述自己） | `prompts/writer_system.txt` |
| #66 A3 | 写作 | 悬念钩子十三式（突然揭示 / 紧急危机 / 未完成动作 / 身份反转 / 两难选择 / 神秘物品 / 时间限制 / 承诺威胁 / 离奇消失 / 言外之意 / 意象钩子 / 回声钩子 / 留白钩子） | `prompts/writer_system.txt` |
| #67 A4 | 写作 | 章首引子七式（悬念对话 / 闪前碎片 / 倒计时 / 神秘独白 / 反差场景 / 未完成动作 / 意象伏笔） | `prompts/writer_system.txt` |
| #68 A5 | 编辑 | AI 高频词黑名单扩充（+13 词：此外 / 然而 / 值得注意的是 / 彰显 / 诠释 / 赋能 / 映射 等）+ 四字成语堆砌检测 + 句式单一检测 + "的"字密度规则 + 用词精确规则 | `prompts/editor_system.txt` |
| #69 A6 | 写作 | 章节节奏控制三条（长短句交替 / 段落呼吸 / 信息密度浪潮） | `prompts/writer_system.txt` |
| #70 A7 | 写作 | 中文文学技法 5 式（白描 / 留白 / 意象 / 草蛇灰线 / 蒙太奇） | `prompts/writer_system.txt` |
| #71 A8 | 写作 | 打破读者预期 4 技（预期反转 / 信息差 / 复杂动机 / 节外生枝） | `prompts/writer_system.txt` |
| #72 B1 | 人物 | 角色 MBTI 字段（director 输出 characters 时填 `mbti`，便于性格一致性追踪） | `prompts/director_system.txt` |
| #73 B2 | 人物 | 缺陷致命化原则 + fatal_flaw 字段（角色致命缺陷会在剧情高潮触发） | `prompts/director_system.txt` |
| #74 B3 | 人物 | 反派镜像主角原则（反派应共享主角某项核心信念，但用了不同方式去实现） | `prompts/director_system.txt` |
| #75 B4 | 人物 | 配角功能性原则（每个配角承担一种叙事功能：导师 / 对手 / 镜子 / 喜剧救济 / 牺牲推动） | `prompts/director_system.txt` |
| #76 C1 | 对话 | 对话六目的表（推进剧情 / 揭示性格 / 制造冲突 / 传递信息 / 营造氛围 / 暗示伏笔），每段对话至少满足一项 | `prompts/writer_system.txt` 特殊场景段后 |
| #77 C2 | 对话 | 潜台词四技（言不由衷 / 答非所问 / 沉默回避 / 反话正说） | `prompts/writer_system.txt` |
| #78 C3 | 对话 | 对话权力博弈表（主动 / 被动 / 试探 / 反击 / 退让 / 占据上风） | `prompts/writer_system.txt` |
| #79 C4 | 对话 | 对话五禁忌（双方都知道的信息 / 全是问答 / 全是同意 / 一句话超 30 字 / 无身体反应） | `prompts/writer_system.txt` |
| #80 D1 | 扩充 | 内容扩充 6 技巧（场景具象化 / 内心独白 / 感官细节 / 对话扩展 / 节奏放慢 / 多视角穿插） | `prompts/writer_system.txt` |
| #81 D2 | 扩充 | 题材扩充策略 4 种（动作类 / 言情类 / 悬疑类 / 玄幻类各自的有效扩充手段） | `prompts/writer_system.txt` |
| #82 D3 | 编辑 | 防注水检测表（无意义风景 / 凑字数回忆 / 重复已知信息 / 过渡冗长 / 对话注水 / 同义反复） | `prompts/editor_system.txt` 输出要求段前 |
| #83 E1 | 评审 | 八维质量评分（opening_hook / plot_progression / character_depth / dialogue_quality / ending_hook / pacing / show_not_tell / language_quality）+ 阈值门（<60 必须 approved=false） | `prompts/reviewer_system.txt`；JSON 新增 `quality_breakdown` 字段 |
| #84 E2 | 评审 | 题材专项校验（言情 / 都市 7 项 + 动作 / 武侠 5 项），追加在已有奇幻 / 悬疑校验之后 | `prompts/reviewer_system.txt` |
| #85 F1 | 大纲 | plotter JSON 5 新字段：`previous_link / opening_hook_type / ending_hook_type / characters_on_stage / scene_list` | `prompts/plotter_system.txt` |
| #86 G1 | 标题 | 题材-风格映射表（7 种题材：悬疑 / 言情 / 奇幻 / 科幻 / 历史 / 都市 / 惊悚） | `core/name_generator.py _SYSTEM_PROMPT` |
| #87 G2 | 标题 | 五种标题创作技巧（核心冲突提炼 / 主角命名 / 意象隐喻 / 反差 / 悬念留白），N 个候选必须用不同技巧 | `core/name_generator.py _SYSTEM_PROMPT` |
| #88 G3 | 标题 | AI 套路黑名单（"XX 之道 / XX 的觉醒 / 命运 / 真相 / 震惊"等） | `core/name_generator.py _SYSTEM_PROMPT` |
| #89 H1 | 结构 | 8 套情节结构模板（三幕 / 英雄之旅 / 悬疑结构 / 言情结构 / 惊悚结构 / 反转结构 / 多线叙事 / 网文升级流）+ 题材-结构决策表，要求 plotter 在第一章 plot_points 标注采用的骨架 | `prompts/plotter_system.txt` 开头 |
| #90 I1 | 工程 | 中文字数统计算法（统计 `[一-鿿]` 范围内汉字，排除 Markdown 标记），用于续写阈值判断比 `len(text)` 更准确 | `agents/writer.py _count_chinese_chars()` |
| #91 I2 | 工程 | review-rewrite 循环硬上限（≤3 轮重写），到上限后接受当前版本，避免 reviewer 一直 reject 导致无限循环 | `config.yaml novel.review_max_retries: 3` + `core/pipeline.py` 上限日志说明 |
| #92 J2 | 硬约束 | 每章必须至少出现 2 个张力波峰（中间有低谷缓冲） | `prompts/writer_system.txt` 章节硬约束段 + `prompts/editor_system.txt` 张力波峰核查段 |
| #93 J4 | 硬约束 | 每章必须至少 1 处意外转折（预期反转 / 信息差 / 角色反常 / 节外生枝 / 隐藏动机） | `prompts/writer_system.txt` 章节硬约束段 |
| #94 A3 | 数据链路 | reviewer `quality_breakdown` 八维评分字段无消费 → 在 pipeline._write_chapters 和 _execute_revise 中添加分维展示 | `core/pipeline.py` |
| #95 B4 | 数据链路 | plotter 5 个字段（previous_link / opening_hook_type / ending_hook_type / characters_on_stage / scene_list）无消费 → 在 _format_chapter_plan 中添加格式化 | `core/context_manager.py` |
| #96 F1 | 类型安全 | tracker.analyze_development 缺 isinstance 检查 → 补全 `isinstance(result, dict)` 防护 | `core/tracker.py` |
| #97 I2 | 映射 | _FIELD_MEANINGS 缺 character_state.psychology 和 validation_rules.active_validation_level 中文映射 → 补全 | `core/tracker.py` |
| #98 D3 | 映射 | _GENRE_STRICTNESS 未覆盖"都市"题材 → 添加 `"都市": "flexible"` | `core/pipeline.py` |
| #99 J1 | 协议 | 验证协议 B3 表格未覆盖新增字段 + 缺 prompt schema 消费检查项 → 添加 J2 检查项 + 更新 B3/A3/F1 表格 | `docs/verification_protocol.md` |

### 2026-05-22 Director 精修策略改为全量（holistic）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|---------|
| #106 | 架构 | 增量生成精修存在"改后不同步前"问题：精修角色B时无法反向更新已确认的角色A/世界观；全量反向同步开销等同于一次性生成 → 恢复一次性生成（`director.run()`）+ 全量精修（`_run_directing_holistic`）：每次调整发送完整 JSON（world_data + characters + locations + outline），LLM 输出同结构完整 JSON | `core/pipeline.py`、`core/refine_prompts.py`（新增 `REFINE_HOLISTIC_PROMPT`） |

### 2026-05-22 Director 增量生成重构（#100-#105，已由 #106 取代）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|---------|
| #100 | 架构 | Director 精修阶段前面的修改后面的内容感知不到（_build_refine_context 剥离 characters/locations + 角色间只共享名字 + 世界观截断 800 字符）→ 重构为增量生成+逐个确认架构：Director 按层级生成（world→角色逐个→地点逐个→outline），每个 piece 生成时带完整已确认上下文，然后精修确认 | `agents/director.py`、`core/pipeline.py`、`prompts/director_world.txt`（新建）、`prompts/director_character.txt`（新建）、`prompts/director_location.txt`（新建）、`prompts/director_outline.txt`（新建） |
| #101 | 数据链路 | 用户需求（如"不要升级流"）在 writing/editing 阶段丢失——story_idea 未注入 build_running_context + StyleAdvisor 无负面约束提取 + Editor 不接收 setting/review 字段 → 4 处修复：(1) build_running_context 新增 story_idea 参数（截断600字）；(2) Writer/Editor STYLE_FIELDS 扩展 setting 和 review；(3) pipeline 两处调用传入 story_idea；(4) style_advisor prompt 增加负面约束提取指令 | `core/context_manager.py`、`agents/base.py`、`core/pipeline.py`、`prompts/style_advisor_system.txt` |
| #102 | 数据链路 | 用户负面约束在 Director 阶段仍可能被违反——StyleAdvisor 触发词"升级"匹配"不要升级流"反向触发 fast-paced + Director/Plotter 不接收 requirements 字段 + Director prompt 无负面约束指令 → 3 处修复：(1) style_advisor 增加否定约束检测规则（否定词+触发词=不触发正面标准，写入 quality_gates+taboos）；(2) Director/Plotter STYLE_FIELDS 增加 requirements；(3) 4 个 director prompt 增加负面约束遵守段落 | `prompts/style_advisor_system.txt`、`agents/base.py`、`prompts/director_world.txt`、`prompts/director_character.txt`、`prompts/director_location.txt`、`prompts/director_outline.txt` |
| #103 | 数据链路 | braindump 立项问答中的负面约束可能被 LLM 软化为正面表述（如"不要升级流"→"追求自由"），导致 StyleAdvisor 否定检测无法匹配 → braindump 结束后增加 `_extract_negative_constraints` 一步 LLM 调用，显式提取所有负面约束追加到 style_description 末尾，确保 StyleAdvisor 一定能识别 | `main.py` |
| #104 | 健壮性 | API 上下文窗口溢出（400 BadRequest）直接 raise 不被重试，且写作循环无 try/except → 异常时当前章节进度未保存，resume 后从第一章重新写 → 在 `_run_pipeline` 调用 `_write_chapters`/`_edit_chapters` 处加 try/except，捕获异常时保存当前 `state.current_chapter` 和 `state.phase` 后再 raise，确保 resume 能从断点章节继续 | `core/pipeline.py` |
| #105 | 截断 | CLI 展示截断阈值过小（灵感 40-120 字、调整意见 60 字、修改思路 80 字等），20 万字规模下信息大量丢失 → 全面放宽：灵感预览 100/300 字、调整意见 120 字、修改思路描述 200 字、伏笔 60 字、写前检查 5 条、running context 总预算 60K→80K、各 JSON 截断 2K→3-4K | `core/ui.py`、`main.py`、`core/pipeline.py`、`core/context_manager.py` |

跳过项（用户决策）：A0 自动检测题材 / B0 角色冲突矩阵 / C0 群戏调度 / I3 章节字数日志 / I4 写作日志格式 / J1 词汇丰富度自动检测 / J3 主题贯穿度自动检测。

### 2026-05-22 Web 前端模式（#107）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|---------|
| #107 | 架构 | CLI 界面下 Director 全量精修 JSON 可读性差 + 用户交互不便 → 新增 FastAPI + Vue3 SPA Web 前端，覆盖 new/continue/revise/status 全流程 | `web/`（新增）、`frontend/`（新增）、`web_main.py`（新增） |

架构要点：
- 桥接层（`web/bridge/`）通过 monkey-patch 替换 `core.prompt_utils` 和 `core.ui`，pipeline.py 无需修改
- pipeline 在后台线程运行，通过 `queue.Queue` 与 WebSocket 双向通信
- 前端使用 Vue3 + Naive UI（暗色主题 + 绿色强调），JSON 用 Tab 分页展示
- CLI（`main.py`）和 Web（`web_main.py`）双入口共存，互不影响

### 2026-05-22 Web 输入组件样式修复

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #108 | 轻微 | `PromptInt.vue` 的 `n-input-number` 与 `n-button` 无 flex 布局，垂直方向错位 | `frontend/src/components/interaction/PromptInt.vue`（`.input-row { display: flex; align-items: center; gap: 8px }`） |
| #109 | 轻微 | `web_prompt_int` 传入的 message 带 CLI 前导空格（`"  总章数..."`），Web 端显示不协调 | `web/bridge/web_prompt.py` `web_prompt_int`（`message.lstrip()`） |

### 2026-05-22 Web 端流程补齐（AI 起名 + 校验 + 继续创作）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #110 | 功能 | Web 端新建小说缺少 AI 起名功能（CLI 有 `_pick_novel_name`），留空直接变 "untitled" | `web/routers/novels.py`（新增 `POST /api/suggest-names`）、`frontend/src/views/NewNovelView.vue`（AI 起名按钮 + 候选展示） |
| #111 | 功能 | Web 端缺少小说名安全校验（CLI 有 `_sanitize_novel_name`） | `core/name_generator.py`（移入公共函数 `sanitize_novel_name`）、`web/routers/novels.py`（新增 `POST /api/validate-name`）、`frontend/src/views/NewNovelView.vue`（前端校验） |
| #112 | 功能 | Web 端缺少"继续创作"入口（CLI 有 `cmd_continue`，后端 WebSocket 已支持 `mode == "continue"`，但前端无 UI） | `frontend/src/views/ContinueView.vue`（新建）、`frontend/src/router/index.ts`（`/continue` 路由）、`frontend/src/components/layout/AppHeader.vue`（导航按钮） |

架构变更：
- `_sanitize_novel_name` + 相关常量从 `main.py` 移至 `core/name_generator.py`（公共函数 `sanitize_novel_name`），`main.py` 改为导入

### 2026-05-22 NovelDetailView 独立详情模式

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #113 | 体验 | 从首页点击小说卡片进入 `/novel/:name`，NovelDetailView 只有会话模式，无 WebSocket 连接时显示"未连接"且无任何内容 | `frontend/src/views/NovelDetailView.vue` — 新增独立详情模式：通过 REST API 获取小说详情，展示基本信息/故事灵感/章节列表，根据阶段显示"继续创作"或"修订章节"操作按钮；会话模式仅在嵌入新建/继续/修订流程时激活 |
| #114 | 体验 | 独立详情页内容超出视口无滚动条，长文案和章节列表无法完整查看 | `frontend/src/App.vue` — `.app-layout` 改为 `height:100vh;overflow:hidden` 固定视口，`.app-main` 加 `overflow-y:auto` 独立滚动 |
| #115 | 体验 | 独立详情页所有阶段信息挤在一起，可读性差 | `frontend/src/views/NovelDetailView.vue` — 改为 `n-tabs` 分阶段展示（风格分析/参数确认/导演阶段/剧情拆章/章节进度/完成），当前阶段可操作，过去阶段只读展示，未来阶段置灰禁用 |
| #116 | 体验 | 写作和润色分两个 Tab 但操作同一批章节，来回切换不便 | `frontend/src/views/NovelDetailView.vue` — 合并为"章节进度"Tab，每章展示完整子阶段流水线 `草稿→审核→追踪→润色`，已完成步骤标绿 ✓，未完成步骤置灰；`PHASE_ORDER` 同步移除 `editing`；`normalizePhase` 将 `editing` 映射到 `writing`、`refining` 映射到 `directing`，确保 Tab 激活和状态判断正确 |
| #117 | 体验 | 从首页点击小说卡片进入详情页看不到 Tab，始终显示"未连接"会话视图 | `frontend/src/views/NovelDetailView.vue` — 独立详情模式判断条件从 `isStandalone && !hasSession` 改为仅 `isStandalone`（只看路由是否有 `:name` 参数），避免 store 残留旧会话数据导致 Tab 视图被跳过 |
| #118 | 体验 | 新建小说/继续创作/修订时只显示平铺消息流，无法按阶段查看进度 | `frontend/src/views/NovelDetailView.vue` — 统一为 Tab 视图：session 模式也展示分阶段 Tab，通过 `novelName` prop + 定时 REST API 刷新获取已完成阶段数据；当前阶段 Tab 下方嵌入实时消息流+输入组件；父组件 `NewNovelView`/`ContinueView`/`ReviseView` 传入 `novelName` prop |
| #119 | 体验 | 实时日志占位过多，Tab 数据和日志上下堆叠不便查看 | `frontend/src/views/NovelDetailView.vue` — 改为左右布局：左侧 14 列 Tab（阶段数据），右侧 10 列实时日志+进度条+输入组件；独立详情模式（无会话）Tab 占满 24 列 |

### 2026-05-22 统一用户行为路径（消除冗余导航）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #120 | 体验 | 继续创作/修订章节需要经过额外选择页面，用户从详情页点按钮→跳转中间页→重新选择同一小说→再开始，路径冗余 | `frontend/src/views/NovelDetailView.vue` — 统一为"点进即操作"：未完成小说在页面顶部显示"继续创作"CTA 按钮，直接在详情页内发起 WebSocket 会话；已完成小说在"完成"Tab 内直接展示章节列表+每章"修订"按钮，点击即启动修订会话 |
| #121 | 体验 | AppHeader 同时存在"首页""继续创作""修订""新建小说"四个导航，"继续创作"和"修订"与详情页内操作重复 | `frontend/src/components/layout/AppHeader.vue` — 移除"继续创作"和"修订"导航按钮，仅保留"首页"和"新建小说" |
| #122 | 体验 | ContinueView/ReviseView 作为独立页面存在，用户需手动选择小说再开始，与详情页内的直接操作形成两条冗余路径 | `frontend/src/views/ContinueView.vue`、`frontend/src/views/ReviseView.vue` — 改为小说列表入口，点击"进入"跳转到 `/novel/:name` 详情页，由详情页统一承载继续/修订操作 |

架构变更：
- NovelDetailView 成为唯一操作入口：独立详情模式自带"继续创作"（未完成）和"修订"（已完成）内联操作
- ContinueView/ReviseView 降级为小说列表入口，不再包含 WebSocket 会话逻辑

### 2026-05-22 表单必填 + Web 检查点自动继续 + 取消按钮移除

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #123 | 体验 | 新建小说时小说名称可留空，提交后变成 "untitled"，用户不可控 | `frontend/src/views/NewNovelView.vue` — 小说名称改为必填字段（`required`），提交按钮在名称为空时禁用，不再 fallback 到 "untitled" |
| #124 | 体验 | Web 模式下每个阶段之间弹出"保存并退出"确认框（CLI 设计），打断自动化流程，且已有断点续写兜底 | `core/pipeline.py` `_checkpoint` — 检测 Web session（`get_current_session()`），有则自动保存并继续，不弹确认框；CLI 行为不变 |
| #125 | 体验 | "终止流程"按钮只在等待用户输入时生效（`web_prompt.py` 的 cancel 检查），LLM 调用期间（最长 300s）无法取消，给用户虚假预期 | `frontend/src/views/NovelDetailView.vue` — 移除"终止流程"按钮，流程结束后显示"继续创作"（未完成）或"返回首页" |

### 2026-05-22 修订流程 Web 兼容修复

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #126 | 严重 | `revise_chapter` 全流程使用 `print()` 输出而非 `ui.*`，Web bridge 无法拦截，前端看不到任何修订进度和状态信息 | `core/pipeline.py` `revise_chapter` / `_execute_revise` / `_select_idea` — 全部 `print()` 替换为 `ui.info/warn/success/hint/error/section`，CLI 和 Web 端均可正常显示 |

### 2026-05-22 全量清除 Web 不可见 print() 输出

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #127 | 严重 | `_pre_write_check()` 7 处 `print()`（缺失数据警告、红线约束、风格信息、主角状态），每章写前执行，Web 端完全不可见 | `core/pipeline.py` — 替换为 `ui.warn/hint` |
| #128 | 严重 | `_report_forgotten()` 4 处 `print()`（角色失踪、支线停滞、伏笔未回收），遗忘检测信息 Web 端不可见 | `core/pipeline.py` — 替换为 `ui.warn` |
| #129 | 严重 | `_handle_retire()` 3 处 `print()`（退休菜单、选项列表、确认），用户收到无上下文的输入框 | `core/pipeline.py` — 替换为 `ui.hint/info/success` |
| #130 | 中等 | `_edit_chapters()` / `_combine_final()` 各 1 处 `print()`（润色完成、全文保存路径），里程碑信息 Web 端不可见 | `core/pipeline.py` — 替换为 `ui.success` |
| #131 | 中等 | `Plotter.run()` 1 处 `print()`（分批生成进度），多章节小说规划时 Web 端无进度反馈 | `agents/plotter.py` — 新增 `from core import ui`，替换为 `ui.info` |
| #132 | 中等 | `LLMClient.__init__()` 3 处 `print()`（API Token 缺失），进程直接 `sys.exit(1)`，Web 端只看到断连无错误信息 | `core/llm_client.py` — 改为先调 `ui.error/hint`（让 bridge 转发）再 exit |

### 2026-05-22 JSON 展示改为易读格式

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #133 | 体验 | 世界观、大纲、风格指南、refine_block 等数据全部以 `JSON.stringify` 原始代码块展示，用户需要自己解析 JSON 结构 | 新建 `frontend/src/components/display/JsonViewer.vue` — 通用易读 JSON 展示组件，根据数据类型智能选择渲染方式：概要用 `n-descriptions` 键值对，嵌套列表（角色/势力/历史）用 `n-list` 卡片，短数组用 `n-tag` 横排，原始 JSON 折叠兜底 |
| #134 | 体验 | NovelDetailView 风格分析 Tab 手动提取 3 个字段 + 折叠原始 JSON，其余大量风格信息不可读 | `frontend/src/views/NovelDetailView.vue` — 替换为 `JsonViewer type="style"`，自动提取 tone/pacing/plot/character/worldbuilding/review/editing 各子维度 |
| #135 | 体验 | NovelDetailView 导演阶段 Tab 世界观和大纲直接展示原始 JSON | `frontend/src/views/NovelDetailView.vue` — 替换为 `JsonViewer type="world"` / `type="outline"`，世界观展示名称/基调/规则/角色卡片/地点标签/势力列表/历史事件/日常生活 |
| #136 | 体验 | MessageLog 中 refine_block 内容以原始 JSON 展示 | `frontend/src/components/display/MessageLog.vue` — 替换为 `JsonViewer` |
| #137 | 体验 | RefineBlockViewer 5 个 tab 全部展示原始 JSON | `frontend/src/components/display/RefineBlockViewer.vue` — 替换为 `JsonViewer`，world/outline tab 自动使用对应模板 |

架构变更：
- 新增通用组件 `JsonViewer.vue`，支持 `world`/`outline`/`style`/`auto` 四种渲染模板
- 模板逻辑对齐 `core/context_manager.py` 的 `_condense_world` / `_condense_outline` 字段提取

### 2026-05-22 JsonViewer 完全重写

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #138 | 严重 | JsonViewer 世界观模板未解析 holistic directing 嵌套结构（`data.world`），导致世界观完全不显示 | `JsonViewer.vue` — 新增 `worldObj` computed 解析 `data.world` 嵌套；`charsList` computed 兼容 `data.characters` 和 `data.world.characters` |
| #139 | 严重 | 角色展示将 30+ 复杂嵌套字段（appearance/abilities/background/growth_plan/voice）平铺为扁平 key-value，字段堆叠不可读 | `JsonViewer.vue` — 角色改为 `n-collapse` 折叠面板：主层展示 personality/motivation/arc/fatal_flaw/aliases，嵌套折叠展示 appearance/abilities/background/growth_plan/voice 各子维度（`flattenObj()` 递归展开） |
| #140 | 中等 | 世界观地点只显示名称标签，缺少 description/climate/terrain；势力缺少 key_figures；历史缺少 cause/result | `JsonViewer.vue` — locations 改为 `n-list` + `n-thing` 卡片（含 climate/terrain 标签）；factions 增加 key_figures 标签；history 展示 cause + result |
| #141 | 中等 | 整体样式错位：子标题不统一、descriptions 嵌套层级不一致 | `JsonViewer.vue` — 统一 `.jv-sub-title` 类 + 间距；所有子区域使用一致的 `n-descriptions bordered label-placement="left"` + `n-list bordered` 组合 |

### 2026-05-22 可选分卷结构（卷名 + 卷级组织）

| 编号 | 类型 | 说明 | 位置 |
|------|------|------|------|
| #142 | 功能 | 新增 `VolumeDef` 数据类（number/title/start_chapter/end_chapter）和 `NovelState.volumes` 可选字段 | `core/state_manager.py` |
| #143 | 功能 | 参数收集阶段新增可选分卷流程：≥10 章时可选择启用，LLM 建议分卷方案 + 用户确认/调整 | `core/pipeline.py` — `_collect_volume_definitions()` |
| #144 | 功能 | Director 大纲输出新增 `volumes` 键（卷号/卷名/叙事焦点），prompt 条件注入卷结构 | `agents/director.py` + `prompts/director_system.txt` / `director_outline.txt` |
| #145 | 功能 | Plotter 批次生成对齐卷边界（不跨卷），每批次注入卷上下文，卷末章指导收束 | `agents/plotter.py` + `prompts/plotter_system.txt` |
| #146 | 功能 | 激活 tracker 预留的 `currentState.volume` 和 `checkpoints.volumeEnd` 字段，新增 `advance_volume()` | `core/tracker.py` |
| #147 | 功能 | ContextManager 注入当前卷信息（卷号/卷名/进度/是否卷末章），指导 writer 生成 | `core/context_manager.py` |
| #148 | 功能 | `_combine_final` 支持卷标题页 + 每卷单独输出文件 `{name}_卷N.txt` | `core/pipeline.py` |
| #149 | 功能 | 前端章节列表按卷分组显示（`n-divider` 卷标题 + 卷下章节），兼容无卷 flat 模式 | `frontend/src/views/NovelDetailView.vue` |
| #150 | 功能 | REST API 返回 `volumes` 字段（null 或 VolumeDef 列表） | `web/routers/novels.py` |

架构变更：
- 分卷为可选功能，`volumes=None` 时所有代码路径行为与当前完全一致
- 章节编号保持全局（不按卷重置），避免追踪系统混乱
- 向后兼容：`StateManager.load` 过滤未知字段，旧状态加载为 `volumes=None`

### 2026-05-22 长篇上下文溢出防护 + 错误友好化

| 编号 | 类型 | 说明 | 位置 |
|------|------|------|------|
| #151 | 稳定性 | Writer 续写时 `chat_with_history` 重发 80K running_context + 5K draft，300 章时溢出 128K token 窗口 | `agents/writer.py` — 续写时截断原始 context 到 40K 字符 |
| #152 | 稳定性 | Plotter `_build_existing_summaries` 300 章时累积 295 条摘要（~24K 字符）无截断 | `agents/plotter.py` — 最近 30 条完整 + 50 条简略 + `MAX_SUMMARY_FULL/SHORT` 常量 |
| #153 | 稳定性 | `get_tracking_context` 活跃伏笔列表无限增长（300 章 50+ 项），总输出无上限 | `core/tracker.py` — 伏笔上限 20 条 + 总输出硬限 15K 字符 |
| #154 | 稳定性 | `context_manager._truncate_context` 中 tracking_context 计入 fixed_len 但从不截断，可能吃光摘要预算 | `core/context_manager.py` — tracking 硬限 10K 字符 |
| #155 | 稳定性 | Tracker JSON 数组（appearanceTracking/consistency.warnings/plotHoles/common_errors 等）无限增长，300 章时文件膨胀 | `core/tracker.py` — `update_tracking` + `_consume_review` 添加滑动窗口裁剪（保留最近 30-50 条） |
| #156 | 稳定性 | Critic 发送完整 world_data JSON（~10-15K），Reviewer 会截断到 2K 但 Critic 不会 | `agents/critic.py` — 截断 world_data 到 2K + tracking 到 10K |
| #157 | 体验 | LLM 错误（JSON 截断/网络断/限流/超时/认证失败等）直接显示原始异常堆栈，用户无法理解 | `web/app.py` — `_format_user_error` 转中文友好消息 + `ui.error` 发到前端消息流 |

架构变更：
- 所有 Agent 的 LLM 输入现在有明确字符上限，300 章长篇不会溢出上下文窗口
- `get_tracking_context` 输出硬限 15K，`_truncate_context` 中 tracking 硬限 10K，plotter 摘要硬限 ~3K
- Web 端错误消息从原始 `str(exception)` 改为分类中文提示

### 2026-05-22 Writer 重写实质化

| 编号 | 类型 | 说明 | 位置 |
|------|------|------|------|
| #158 | Bug | Writer rewrite prompt 要求"保持原有好内容，只修改有问题的部分"，LLM 只做表面微调不解决实际问题，导致审核多次不通过但问题不变 | `agents/writer.py` — rewrite prompt 改为 7 条强制实质性重写指令，按 major/warning 区分处理力度；重写温度从 +0.15 提高到 +0.25（上限 0.95） |

### 2026-05-23 自检修复（#159-#166）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #159 | 中等 | tracker.py `_BANNED_REPLACEMENTS` 与 writer/editor/reviewer/style_advisor 四个 prompt 禁用词列表显著不同步，writer 仅 12 词而 tracker 有 60+ | `core/tracker.py` — 补入 writer 12 词 + editor 7 词（共 81 条）；四个 prompt 统一标注"完整列表由 tracker 自动替换" |
| #160 | 轻微 | director_system.txt 输出 `style` 顶级字段但无消费者（功能已被 StyleAdvisor 替代） | `prompts/director_system.txt` — 删除 style 字段定义；`core/pipeline.py` `_split_director_output` — pop legacy style field |
| #161 | 轻微 | `agents/plotter.py:81` 使用 `result["chapters"]` 直接访问 | `agents/plotter.py` — 改为 `result.get("chapters", [])` |
| #162 | 轻微 | `NovelState`/`ChapterState`/`VolumeDef` 部分核心字段无默认值 | `core/state_manager.py` — 全部字段补默认值 |
| #163 | 轻微 | `sanitize_novel_name` 未校验 Unicode 控制字符和零宽字符 | `core/name_generator.py` — 添加 `\x00-\x1f`/`\x7f`/零宽字符检查 |
| #164 | 轻微 | `_split_director_output` 使用整体赋值，未过滤 LLM 返回的意外字段 | `core/pipeline.py` — 增加 `known_world_keys` 白名单过滤 |
| #165 | 轻微 | `param_confirmed` 消息在前端被 displayMessages 过滤导致不可见 | `frontend/src/views/NovelDetailView.vue` — 从过滤列表中移除 |
| #166 | 轻微 | `SessionManager.get()` 未加锁，存在理论竞态条件 | `web/bridge/session.py` — get() 方法加 `with self._lock` |

### 2026-05-23 Web 精修数据无变化修复（#167-#169）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #167 | 严重 | Web 模式下 `_send_input_request` 收到不匹配 `request_id` 的响应后 `break` 退出循环并抛出 `WebUserAbort`，导致精修"调整"操作被静默转为"确认"（数据不变） | `web/bridge/web_prompt.py` — `break` 改 `continue`，删除循环后 `raise WebUserAbort()` |
| #168 | 中等 | `_continue_json` 重试耗尽后返回截断原文，`parse_json` 可能解析出看似完整但实际不完整的 JSON | `core/llm_client.py` — `return existing_text` 改为 `raise ValueError(...)` |
| #169 | 轻微 | `_split_director_output` 的 `known_world_keys` 白名单仅 11 键，LLM 生成的其他键（如 `theme`/`premise`）被静默丢弃；修订 #164 的白名单方案改为排除法 | `core/pipeline.py` — 白名单改为 `_EXCLUDE_KEYS` 排除法，保留所有非顶层键 |

### 2026-05-23 移除 CLI，统一 Web 架构（#170）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #170 | 重构 | 删除所有 CLI 端逻辑，统一为 Web-only 架构 | `main.py` — 删除；`core/braindump.py` — 新建（从 main.py 提取 braindump 逻辑）；`core/prompt_utils.py` — 重写为 WebSocket 原生输入；`core/ui.py` — 重写为 WebSocket 原生输出；`core/llm_client.py` — Spinner 改为无操作；`web/app.py` — 更新导入路径；`web/bridge/__init__.py` — 猴子补丁逻辑移除；`web/bridge/web_prompt.py` + `web/bridge/web_ui.py` — 删除（合并到 core）；`requirements.txt` — 移除 prompt_toolkit 和 rich |

### 2026-05-23 剧情拆章大纲 + 章节正文展示

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|---------|
| #171 | 体验 | 剧情拆章 Tab 仅显示章节号+标题，PlotAgent 生成的丰富计划数据（摘要/张力/情绪/场景/角色/伏笔等）不可见；章节正文无法在页面内查看 | `web/routers/novels.py` — `get_novel_detail` 返回值新增 `chapter_plans` 字段；`frontend/src/views/NovelDetailView.vue` — plotting Tab 改为完整大纲卡片（每章展示摘要/张力/情绪曲线/场景结构/情节点/角色/伏笔/悬念等），writing/complete Tab 每章新增"阅读"按钮，点击后右侧 Drawer 展示正文内容 |
| #172 | Bug | 独立详情页（`/novel/:name`）有会话时 Tab 数据不刷新，用户修改意见后实时日志更新但 Tab 停留在首次加载 | `frontend/src/views/NovelDetailView.vue` — 新增 `watch(hasSession)` 在会话激活时启动 5s 定时刷新 |
| #173 | 严重 | WebSocket 断连（刷新页面）时精修循环 `UserAbort` 被当作用户确认，phase 跳到下一阶段，用户失去继续精修机会 | `core/pipeline.py` — `_refine_block` 捕获 `UserAbort` 时设置 `self._interrupted = True`；所有 `_refine_*` 调用方在 `if self._interrupted` 分支保存已调整数据但不推进 phase |
| #174 | 功能 | 新增阶段回滚 API，支持将小说回滚到 collecting_params / directing / plotting / writing 任意阶段，清理后续阶段产出的文件和状态数据 | `web/routers/novels.py` — 新增 `POST /api/novels/{name}/rollback`；`frontend/src/views/NovelDetailView.vue` — 各已完成 Tab 添加回滚按钮 + 确认框 |
| #175 | 严重 | `_confirm_refine` 内部两处 `except UserAbort: return "yes"` 吞掉异常，导致 `_refine_block` 的 `except UserAbort: self._interrupted = True` 为死代码（#173 修复无效） | `core/pipeline.py` `_confirm_refine` — 移除两处 `except UserAbort`，让异常传播到 `_refine_block` 正确设置 `_interrupted` |
| #176 | Bug | `watch(hasSession)` 写在 `const hasSession` 之前，`const` 暂时性死区导致运行时 ReferenceError，页面白屏 | `frontend/src/views/NovelDetailView.vue` — 将 `watch(hasSession)` 移到 `hasSession` 定义之后 |
| #177 | Bug | 精修过程中调整后的数据只存在于内存，REST API 轮询读不到最新数据，Tab 不更新 | `core/pipeline.py` — `_refine_block` 新增 `on_update` 回调参数，每次调整/重写后调用；`_run_directing_holistic` 传入 `on_update=lambda r: self._split_director_output(state, r)` 实时写盘 |
| #178 | 防御 | `auto_fix` 返回值使用直接下标访问，若返回结构不完整将 KeyError 崩溃 | `core/pipeline.py` — 两处 `fix_result["fixes"]["applied"]` 改为 `.get("fixes", {}).get("applied", [])` 防御式访问（写章 + 精修各 1 处） |
| #179 | Bug | 精修调整后后端已写盘（#177 修复），但前端 Tab 仅靠 5s 轮询刷新，导致右侧消息日志已显示新 JSON 而左侧导演 Tab 仍显示旧数据，最多延迟 5 秒 | `frontend/src/views/NovelDetailView.vue` — 新增 `watch(store.messages.length)` 监听 WebSocket `refine_block` 消息，收到后立即调用 `fetchDetail()` 刷新 Tab 数据 |
| #180 | 体验 | 精修消息在右侧日志中用 `JsonViewer` 平铺渲染，与左侧导演 Tab 分 Tab 展示的世界观/大纲视觉结构不对应；`RefineBlockViewer.vue` 组件已创建但未接入；左侧导演 Tab `world_data` 内嵌套 `world` 对象导致内容藏在一层英文折叠项下不显眼；`JsonViewer.getTitle` 回退到数组索引显示为"0""1" | `frontend/src/components/display/MessageLog.vue` — `refine_block` 渲染改用 `RefineBlockViewer`（世界观/角色/地点/大纲/风格指南 5 子 Tab）；`frontend/src/components/display/RefineBlockViewer.vue` — 新增"风格指南"Tab（`style` key）和"其他"Tab 兜底，保证零丢失；新增 `bare` prop 支持无卡片嵌入；`frontend/src/views/NovelDetailView.vue` — 左侧导演 Tab 改为 `RefineBlockViewer :bare="true"`，`directingContent` computed 展平嵌套 `world` 对象；`frontend/src/components/display/JsonViewer.vue` — FIELD_LABELS 补全 86 个缺失字段 + `style` key；`getTitle` 扩展识别字段避免纯数字索引 |

### 2026-05-25 编剧断点续写（#181）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #181 | 严重 | 编剧阶段（plotting）API 报错后恢复时从头开始重新生成全部章节计划，已成功生成的批次被丢弃；写作/编辑阶段有 try/except + stage 标记但编剧阶段完全缺失断点续写机制 | `agents/plotter.py` — `run()` 新增 `existing_plans`（传入已有批次）和 `on_batch_complete`（每批次完成后回调保存）参数，按 `chapter_number` 跳过已完成批次，部分完成批次裁剪后重新生成；`core/pipeline.py` — plotting 阶段包裹 try/except，异常时保存已有 `chapter_plans`，恢复时作为 `existing_plans` 传入实现断点续写 |

### 2026-05-26 编剧 400 错误重试与断点续写补强（#182）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #182 | 严重 | 编剧阶段 API 返回 400 时三层缺陷叠加导致死循环：(1) `llm_client.py` 仅重试 500+ 错误，400 直接抛出；(2) `plotter.py` 批次级别无重试，首次批次 400 后 `on_batch_complete` 未被调用，`chapter_plans` 为 None；(3) 恢复时 `existing_plans=None` 等同新任务，从第 1 章重新开始并再次触发相同 400 | `core/llm_client.py` — `chat()`/`chat_json()` 对所有 `APIStatusError`（含 400）统一重试 `max_retries` 次；`agents/plotter.py` — `_generate_batch()` 新增批次级 3 次重试 + 400 时逐步裁剪上下文降级（先裁已规划摘要，再精简世界观），提取 `_build_batch_prompt`/`_trim_batch_prompt` 静态方法；`core/pipeline.py` — plotting except 块确保 `chapter_plans` 为空列表而非 None |

### 2026-05-26 审核循环重写机制优化（#183）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #183 | 中等 | 审核循环存在"反复打回但不修改内容"风险，5 层叠加：(1) feedback 丢弃 reviewer 的 location 字段，writer 不知道问题在哪；(2) `writer.rewrite()` 接收 chapter_plan/running_context 参数但不写入 user_msg，重写时无剧情目标和上下文；(3) 无重写变化检测，重写输出与原文高度相似时系统无感知；(4) 全章重写策略导致局部问题引发全局震荡；(5) 无升级策略，重写无效时不会换方式 | `core/pipeline.py` — feedback 构建保留 location 字段；审核循环新增 `difflib.SequenceMatcher` 相似度检测（>92% 标记为"几乎未修改"）；质量分趋势追踪（`quality_history`，连续两轮未上升则提前终止）；升级策略（上次未修改时追加高压提示）。`agents/writer.py` — `rewrite()` user_msg 新增 chapter_plan（剧情计划）和 running_context（精简至 30K 字符的写作上下文） |

### 2026-05-26 max_tokens 截断系统性治理（#184）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #184 | 严重 | 300 章规模下各阶段频繁因 max_tokens 截断，7 类根因叠加：(R1) Writer system prompt 31K+constitution+style ≈ 55K token 挤掉一大半预算；(R2) `MAX_CONTEXT_CHARS=80000` 写死且不与 system 联动，user 80K+system 35K 直接爆 131K；(R3) `_continue_text` 每轮把 `assistant(continuation)+user("继续")` append 到 messages，第 3 次续写时再次溢出；(R4) Plotter 已规划摘要拼接无上限（300 章可达 50K+ 字）；(R5) `get_tracking_context` 全局封顶 15K，writer 收到的还是未截断版；(R6) 摘要分层只保最近 10 章，290 章前完全丢失，长伏笔跨不过；(R7) review_max_retries=3 × writer/reviewer 重传完整 ctx，单章最差 9 次 LLM 调用 | **config.yaml** — 新增 `context_budget` 配置块（10 项预算参数）+ `volume_summary_max_length`/`volume_summary_min_chapters` + `review_max_retries: 3→2`；**core/llm_client.py** — 新增 `estimate_tokens`/`estimate_messages_tokens` token 估算 + `_check_budget` 调用前预警；`_continue_text` 改为滑窗（仅传 user_anchor+草稿尾部 2000 字+继续指令，不再累加）；**core/context_manager.py** — `MAX_CONTEXT_CHARS` 改为动态 `max_context_chars`（从 config 读取）；新增 `generate_volume_summary`（Level 3 卷级摘要，保留原作笔触）；`build_running_context` 改为三级金字塔（L3 卷宏观 + L2 章节摘要 + L1 原文片段 + 检索锚点），接受新参数 `volume_summaries`/`recent_chapter_excerpts`/`relevant_anchors`；**core/tracker.py** — `get_tracking_context(max_chars=...)` 支持调用方传截断上限；新增 `query_relevant(plan, current_chapter, top_k)` 按章节计划做相关度检索（伏笔/角色/关系），避免全量注入；**core/pipeline.py** — 章节循环传 `tracking_max_chars` + 调用 `query_relevant` 取锚点 + `_collect_recent_excerpts` 取 Level 1 片段；卷末调用 `_maybe_generate_volume_summary` 生成 Level 3 摘要；`_edit_chapters` 同步加 `max_chars`；**core/state_manager.py** — `NovelState` 新增 `volume_summaries: dict | None` 持久化字段，`load` 时还原 int key；**agents/writer.py** — 续写改用 `_plan_anchor` 锚点（≤1500 字）+ 草稿尾部，不再传完整 user_msg；`rewrite_ctx_cap` 从硬编码 30000 改为配置驱动默认 8000；**agents/plotter.py** — `_build_existing_summaries` 输出加 `EXISTING_SUMMARIES_CHAR_CAP=20000` 上限；**agents/base.py** — 新增 `_load_genre_fragment` 题材片段按需注入接口（prompts/fragments/<agent>/<genre>.txt 为空时 behavior 不变，为后续 prompt 瘦身保留扩展点）；**prompts/fragments/** — 新建目录 + README.md 说明片段拆分约定 |


### 2026-05-26 Refine/Braindump 调整无变化防御（#185）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #185 | 中等 | 北极星阶段（及 Director refine_block 四块）用户提"调整"意见后 LLM 返回与原版几乎一致的内容，体感"调整无效"。根因：adjust 路径 prompt 软弱（仅"请根据用户意见修改"），无升温也无相似度自检 | `core/braindump.py` — 新增 `_ADJUST_DIRECTIVE` system 段；`_build_braindump_system` 新增 `is_adjust` 参数；adjust 路径升温 0.75，自带 `_too_similar`（SequenceMatcher ≥0.9）相似度检测；无变化时自动升温 0.95 + rewrite-directive 重试 1 次。`core/pipeline.py` — `_llm_refine` 新增 `force_rewrite` 参数（升温 0.9 + 加"必须实质修改"约束）；`_refine_block` adjust 路径新增 `_refine_too_similar`（JSON 序列化后比对 ≥0.92），无变化时自动升温重试 1 次 |

### 2026-05-26 LLM JSON 解析失败重试（#186）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #186 | 严重 | GLM 偶发返回非法 JSON（字符串漏闭合引号 + 漏字段间逗号），`parse_json` 直接抛 `ValueError` 中断 plotter 阶段；`chat_json` 原仅重试 API 错误，解析错误不重试 | `core/llm_client.py` — `parse_json` 新增 `_repair_unclosed_string` 启发式修补：正则识别"字段内容 + 空格 + 下一个 `\"key\":`"模式，自动插入 `\", `；`chat_json` 捕获 `ValueError` 并重试（默认 3 次），把上次错误样本回灌给 LLM 并明确格式约束（双引号闭合 / 字段间逗号 / 不含代码块 / 不含 JSON 外文字） |

### 2026-05-26 分卷规划范围异常修复（#187）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #187 | 严重 | 用户看到"两个第二卷、缺第一卷/第三卷"，根因两层：(1) `_collect_volume_definitions` prompt 未约束 title 不含"第N卷"前缀，LLM 自加"第二卷·觉醒"→前端 `卷{number} {title}` 拼成"卷1 第二卷·觉醒"视觉重复；(2) 章节范围未连续覆盖 1..total，LLM 给 `[(11-15), (16-25)]` 时 1-10 漂浮，按 start_chapter 过滤后某些卷为空 | `core/pipeline.py` — prompt 加 5 条硬性约束（第一卷从 1 起、最后一卷到 total、连续不重叠、title 不含'第N卷'前缀、每卷 8-15 章）；新增 `_PREFIX_RE` 清洗 LLM 自加的'第N卷/卷X/第N幕/Volume N'前缀；新增 `_normalize_volume_ranges` 把 LLM 给的 start/end 按顺序重建为从 1 起、连续、最后一卷到 total 的区间，丢弃越界卷 |

### 2026-05-26 Plotter title 卷名前缀清洗（#188）

| 编号 | 严重度 | 问题 | 修复位置 |
|------|--------|------|----------|
| #188 | 中等 | Plotter 跨批次生成时偶发把卷名作为前缀拼进章节 `title`（如第 16 章 `"第二卷：虚假生路 - 沉溺"`、第 20 章 `"第二卷：虚假生路 - 献祭"`），前端展示 `第N章 {title}` 出现重复卷名；该小说本身 `volumes=null` 也会发生（LLM 自行脑补） | `prompts/plotter_system.txt` — title 字段约束改为"只写本章主题词组，4-12 字；禁止以'第N卷'/'卷X'/'第N幕'/'Volume N'/卷名/幕名作前缀"；`agents/plotter.py` — 新增 `_sanitize_title` 静态方法 + `_TITLE_PREFIX_RE`，`_generate_batch` 入 list 前自动清洗；**故意不清"第N章"前缀**——避免误杀"第三章隔间"这类合法剧情元素；存量 state 已 patch（`output/血色白纸鹤/novel_state.json` 第 16/20 章已修正，备份 `.bak`） |
