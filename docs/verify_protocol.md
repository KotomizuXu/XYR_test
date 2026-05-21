# AI 代码验证协议

本文档是每次大批量代码变更后的**AI 执行型审查工具**。
参考手册请见 `docs/self_check.md`（字段链路细节）和 `docs/parameters.md`（参数与常量）。

> **接到需求时不要从这里开始读** —— 先读 `docs/workflow.md`（流程总纲），它会告诉你什么时候来跑本协议。

---

## 执行规则

1. **必须先读完全部文件清单**，不能只看 diff 或部分文件
2. **每项必须输出**：`✅ 通过 / ❌ 有问题 / ➖ 不适用`
3. **每个"通过"必须给出依据**（文件路径:行号 或 函数名）
4. **每个"有问题"必须说明**：断裂点在哪、影响什么、建议如何修复
5. **不适用**：仅用于"该 Agent/功能尚未实现"的情况，不能因为"没改这部分"而跳过
6. **验证完成后必须执行文档同步**（见本文件最后一章）

---

## 一、必读文件清单

执行验证前，必须读取以下全部文件：

**源码**
- `main.py`
- `config.yaml`
- `core/pipeline.py`
- `core/context_manager.py`
- `core/tracker.py`
- `core/state_manager.py`
- `core/llm_client.py`
- `agents/base.py`
- `agents/style_advisor.py`、`director.py`、`plotter.py`、`writer.py`、`reviewer.py`、`editor.py`、`critic.py`

**Prompts**
- `prompts/style_advisor_system.txt`
- `prompts/director_system.txt`
- `prompts/plotter_system.txt`
- `prompts/reviewer_system.txt`
- `prompts/critic_system.txt`
- `prompts/writer_system.txt`、`editor_system.txt`（纯文本输出，确认无占位符遗漏）
- `prompts/tracking_analysis.txt`（L3 分析 prompt）

**文档**
- `docs/self_check.md`（字段链路参考）
- `docs/parameters.md`（参数与常量参考）

---

## 二、验证项

### A. Prompt Schema → Agent → Pipeline 存储

> 目标：AI 结构化输出是否真的被 pipeline 正确接收并存入 state

---

**A1. Director 输出存储**

检查目标：`director_system.txt` 要求输出的 5 个顶级字段是否全部被 `pipeline.py` Phase 1 存入正确位置。

检查方法：
1. 列出 `director_system.txt` 中 JSON schema 的顶级字段
2. 在 `pipeline.py` `_run_pipeline` Phase 1 中逐一搜索 `result.get("字段名")`
3. 确认写入目标（`state.world_data` / `state.outline`）

通过条件：`world`→`state.world_data`，`characters`→`state.world_data["characters"]`，`locations`→`state.world_data["locations"]`，`outline`→`state.outline`，`style`→`state.outline["style"]` 均有 `if "xxx" in result` 保护

失败示例：字段直接 `result["xxx"]` 无保护，或某字段未存入 state

---

**A2. Plotter 输出存储**

检查目标：`plotter_system.txt` 中每个章节计划字段是否存入 `state.chapter_plans`，并写入 `chapters.json`。

检查方法：
1. 列出 `plotter_system.txt` schema 中所有章节字段（chapter_number、title、summary、plot_points、characters_involved、emotional_arc、emotional_type、emotional_intensity、foreshadowing、active_plotlines、scene_structure、tension_level、location、time、duration、cliffhanger、act）
2. 确认 `plotter.py` 返回值直接作为列表存入 `state.chapter_plans`
3. 确认 `chapters.json` 写入时包含完整 chapter_plans

通过条件：所有字段通过 plotter 原样存入 chapter_plans，无中途截断或过滤

---

**A3. Reviewer 输出消费**

检查目标：`reviewer_system.txt` 的 8 个顶级字段是否被 pipeline 和 tracker 完整消费，无死字段。

检查方法：逐字段追踪消费位置：

| 字段 | 预期消费位置 | 验证：代码中是否存在 |
|------|------------|-------------------|
| `approved` | `pipeline._write_chapters` while 循环 | |
| `issues[]` | `pipeline._write_chapters` feedback 构建 | |
| `consistency_checks` | `tracker._consume_review` | |
| `consistency_score` | `pipeline._write_chapters`（审核通过后被 calc_score 覆盖） | |
| `auto_fix_suggestions[]` | `pipeline._write_chapters` confidence≥0.9 替换 + `tracker._consume_review` 写入 validation_rules | |
| `overall_quality` | `pipeline._write_chapters` 打印展示 | |
| `strengths[]` | `pipeline._write_chapters` + `_execute_revise` 注入 rewrite 反馈 | |
| `tracking_updates` | `tracker.update_from_review` | |

通过条件：以上所有字段均有明确消费代码，无字段只被 `.get()` 取出但结果未使用

---

**A4. StyleAdvisor 输出消费链**

检查目标：`style_advisor_system.txt` 输出的所有字段是否都有消费者，无死字段。

检查方法：

| 字段 | 预期消费位置 |
|------|------------|
| `style_name` | pipeline 打印 |
| `tone/pacing/plot/character/worldbuilding/review/editing/setting/style_presets` | `BaseAgent.apply_style` 按 STYLE_FIELDS 分发 |
| `requirements` | writer/reviewer/editor 通过 STYLE_FIELDS 接收 |
| `requirements.anti_ai_banned_words` | `tracker.auto_fix_banned_words` |
| `agent_temperatures` | `pipeline._apply_style_temperatures` |
| `setting.genre` | `pipeline._apply_strictness` → `_GENRE_STRICTNESS` 映射 |
| `suggestions.total_chapters` | `pipeline._collect_params` 推荐值 |
| `suggestions.words_per_chapter` | `pipeline._collect_params` 推荐值 |
| `suggestions.tracking_thresholds` | `pipeline._collect_params` → `tracker.set_threshold` |

通过条件：所有字段均有消费，`STYLE_FIELDS` 中每个 Agent 接收的字段都是 style_guide 实际存在的字段

---

**A5. Critic 输出消费**

检查目标：`critic_system.txt` 输出的 `ideas[]` 是否被 `_select_idea` 和 `_execute_revise` 正确消费。

检查方法：
1. `critic_system.txt` schema：`ideas[].title/description/scope/expected_effect/consistency_notes`
2. `pipeline._select_idea`：是否读取了 title、description、expected_effect、consistency_notes
3. `pipeline._execute_revise`：是否读取了 selected_idea 的 title、description、scope、expected_effect

通过条件：所有 5 个子字段均被读取，没有只传 ideas[i] 但内部字段未使用的情况

---

### B. Pipeline 存储 → Context 格式化 → 下游消费

> 目标：存入 state 的数据是否真的出现在下游 Agent 的上下文中

---

**B1. world_data 字段格式化**

检查目标：`state.world_data` 的所有子字段是否在 `context_manager._condense_world` 或 tracker 初始化中有消费。

检查方法：列出 `world_data` 的所有子字段，对比 `_condense_world` 的提取列表：

| world_data 字段 | _condense_world 提取 | tracker init 消费 | 结论 |
|----------------|---------------------|------------------|------|
| `name` | `世界观：{name}` | — | |
| `tone` | `整体基调：{tone}` | — | |
| `setting` | `背景：{setting}` | — | |
| `narrative_perspective` | `叙事视角：{...}` | — | |
| `unique_elements` | `世界特色：{...}` 最多5个 | — | |
| `rules` | `世界规则：{...}` | — | |
| `social_structure` | 提取 4 子字段 | — | |
| `geography.main_locations` | 提取地点名 | tracker `_init_timeline` | |
| `geography.travel_routes` | ❌ 不在 _condense_world | tracker `_extract_travel_routes` | |
| `factions` | 提取势力名 | — | |
| `history` | 提取前3条事件 | — | |
| `daily_life` | 提取非空子字段 | — | |
| `characters` | 提取角色列表（含 background） | tracker `_init_*` 系列 | |
| `locations` | ❌ 不在 _condense_world | tracker `_init_locations` | |

通过条件：每个字段至少有一个消费点；标注"❌ 不在 _condense_world"的字段必须确认 tracker 消费路径存在

---

**B2. outline 字段格式化**

检查目标：`state.outline` 的所有字段是否在 `_condense_outline` 中提取。

预期字段：`theme`、`three_act`、`ending`、`key_turning_points`、`style`（仅存档，不格式化）

通过条件：前4个字段均在 `_condense_outline` 有提取代码；`style` 明确标注仅存档

---

**B3. chapter_plans 字段格式化**

检查目标：plotter 输出的每个章节字段是否在 `_format_chapter_plan`、`update_tracking`、`_init_timeline`、`_init_plot_tracker` 中至少有一个消费点。

| 字段 | `_format_chapter_plan` | tracker 消费 |
|------|----------------------|-------------|
| `title` | ✅ | update_tracking currentNode |
| `summary` | ✅ | — |
| `plot_points` | ✅ | update_tracking 主角 skills/knowledge |
| `emotional_arc` | ✅ | — |
| `emotional_type` | ✅ | — |
| `emotional_intensity` | ✅ | — |
| `characters_involved` | ✅ | update_tracking dynamicRelations |
| `foreshadowing` | ✅ | _init_plot_tracker |
| `active_plotlines` | ✅ | update_tracking subplot |
| `act` | ✅ | update_tracking mainPlotStage |
| `cliffhanger` | ✅ | — |
| `scene_structure` | ✅ | — |
| `tension_level` | ✅ | update_tracking majorEvents |
| `location` | ✅ | update_tracking currentState + locations |
| `time` | ✅ | update_tracking timeline |
| `duration` | ❌ 不在 _format_chapter_plan | _init_timeline events[].duration |
| `chapter_number` | ❌ 不在格式化文本 | pipeline 索引使用 |

通过条件：所有字段至少有一个消费点；`duration` 和 `chapter_number` 的"不在格式化"已在 self_check.md 中标注为"有意不消费"

---

**B4. 死字段判定**

对 B1-B3 中发现的任何"有生成、有存储、但在 _condense_world / _format_chapter_plan 中缺失"的字段，必须判定：

```
① 该字段对 Writer/Reviewer/Editor 有用？→ 补充到 _condense_world 或 _format_chapter_plan
② 属于 tracker 追踪范畴？→ 确认 tracker init/update/_consume_review 中有消费
③ 属于 pipeline 流程控制？→ 确认在 pipeline 的对应阶段有读取
④ 以上均否 → 在 self_check.md 中标注"有意不消费"并说明理由，或从 prompt 中删除该字段
```

通过条件：无字段处于"生成了但没有任何消费者且未标注"的状态

---

### C. Tracker 四环节完整性

> 目标：追踪系统不是"只初始化不生效"

---

**C1. 追踪文件初始化覆盖**

检查目标：`Tracker._TRACKING_FILES` 列表中的每个文件是否在 `init_tracking` 中被初始化。

检查方法：
1. 列出 `_TRACKING_FILES`：character_state.json、timeline.json、plot_tracker.json、relationships.json、validation_rules.json、locations.json
2. 确认 `init_tracking` 调用了：`_init_character_state`、`_init_timeline`、`_init_plot_tracker`、`_init_relationships`、`_init_validation_rules`、`_init_locations`
3. 确认 `config.json`（不在 `_TRACKING_FILES`）由 `_init_config` 单独初始化
4. 确认 Phase 2.5 同时检查 `_TRACKING_FILES` 和 `config.json`

通过条件：6个文件 + config.json 均有对应初始化方法，Phase 2.5 检查覆盖全部7个文件

---

**C2. 追踪文件更新覆盖**

检查目标：每个追踪文件是否至少有一个更新入口。

| 文件 | update_tracking | _consume_review | update_from_review | analyze_development |
|------|:-:|:-:|:-:|:-:|
| character_state.json | | | | |
| timeline.json | | | | |
| plot_tracker.json | | | | |
| relationships.json | | | | |
| validation_rules.json | | | | |
| locations.json | | | | |
| config.json | — | — | — | — |

通过条件：每个文件至少一列有 ✅；config.json 由 set_threshold/set_strictness/retire_element 等专用方法更新

---

**C3. 追踪文件输出覆盖**

检查目标：每个追踪文件是否在 `get_tracking_context` 中有可见输出。

| 文件 | get_tracking_context 输出块 | 受 disabled_checks 控制 |
|------|---------------------------|----------------------|
| character_state.json | 角色状态追踪、分组、警告、详细状态、心理深度 | `"character"` |
| timeline.json | 近期时间线、时间异常、时间约束 | `"timeline"` |
| plot_tracker.json | 活跃伏笔、活跃冲突、已解决冲突、剧情问题 | `"worldbuilding"` |
| relationships.json | 角色关系、动态关系变化 | ❌ 始终输出 |
| validation_rules.json | ❌ 不在输出（仅供 auto_fix 使用） | — |
| locations.json | 场景地点、五感参考、氛围指南 | `"locations"` |
| config.json | 审核严格度描述 | ❌ 始终输出 |

通过条件：上表与代码一致；`validation_rules.json` 明确标注"仅内部使用"

---

**C4. config.json 读写链**

检查目标：config.json 的所有字段是否都有完整的读写链路。

| 字段 | 写入方法 | 读取方法 | 消费位置 |
|------|---------|---------|---------|
| `thresholds.*` | `set_threshold` | `_get_thresholds` | `check_forgotten` |
| `strictness` | `set_strictness` / `_init_config` | `_get_strictness` | `get_tracking_context` + `_apply_validation_level` |
| `retired.*` | `retire_element` | `_is_retired` | `check_forgotten` |
| `disabled_checks` | `_collect_params` input | `get_tracking_context` | 各输出块条件判断 |

通过条件：所有字段均有写入和读取，无只写不读或只读不写的孤立字段

---

**C5. Phase 2.5 幂等性风险**

检查目标：从 writing 中段恢复时，Phase 2.5 是否会误覆盖已有追踪数据。

检查方法：
1. 确认 Phase 2.5 触发条件：`missing = [f for f in _TRACKING_FILES if not tracker._read_json(f)]`
2. 确认 `init_tracking` 是否区分"初始化缺失文件"还是"全量重写"
3. 当前实现：`init_tracking(world_data, outline, chapter_plans, missing=None)` — `missing=None` 时仅初始化磁盘不存在的文件；pipeline 显式传入 missing 列表

通过条件：`init_tracking` 不会覆盖磁盘上已存在的追踪文件；从 writing 中段恢复且部分文件缺失时，已有文件保持不变

---

### D. 映射完整性

> 目标：新增 Agent 或功能时，相关映射表必须同步

---

**D1. STYLE_FIELDS 覆盖**

检查目标：`agents/base.py` 中 `STYLE_FIELDS` 是否覆盖所有 Agent。

检查方法：
1. 列出 `agents/` 下所有 `*Agent` 类名，调用 `_agent_name()` 推导键名（去掉 Agent 后缀转小写，再查 `_AGENT_CONFIG_KEYS`）
2. 对比 `STYLE_FIELDS` 的键列表
3. 未在 STYLE_FIELDS 中的 Agent 将接收完整 style_guide（默认行为）

当前 Agent 列表：StyleAdvisorAgent→`style_advisor`，DirectorAgent→`director`，PlotAgent→`plotter`，WriterAgent→`writer`，ReviewerAgent→`reviewer`，EditorAgent→`editor`，CriticAgent→`critic`

通过条件：所有 Agent 要么在 STYLE_FIELDS 中有明确条目，要么明确说明"接收全量"是有意设计

---

**D2. 温度映射覆盖**

检查目标：`pipeline._apply_style_temperatures` 的 `agent_map` 是否覆盖所有 Agent。

检查方法：对比 D1 的 Agent 列表与 `agent_map` 的 key 列表

当前 agent_map 应包含：director、plotter、writer、reviewer、editor、style_advisor、critic

通过条件：agent_map 与实际 Agent 列表完全一致，且 `config.yaml agents.*` 也包含所有 Agent 的默认温度

---

**D3. 题材严格度映射覆盖**

检查目标：`pipeline._GENRE_STRICTNESS` 是否覆盖 `style_advisor_system.txt` 中列出的所有题材关键词。

检查方法：
1. 从 `style_advisor_system.txt` 提取所有题材关键词列表
2. 与 `_GENRE_STRICTNESS` 的 key 对比
3. 未覆盖的题材走默认 strict

通过条件：新增题材已加入 `_GENRE_STRICTNESS`；或明确标注"新题材走默认 strict，符合预期"

---

**D4. _TRACKING_FILES 与初始化一致性**

检查目标：`_TRACKING_FILES` 列表与 `init_tracking` 实际初始化的文件完全对应。

检查方法：
1. 列出 `_TRACKING_FILES` 的6个文件
2. 列出 `init_tracking` 调用的6个 `_init_*` 方法各自写入的文件名
3. 两个列表是否完全匹配

通过条件：一一对应，无遗漏也无多余

---

### E. 双路径一致性

> 目标：write 路径和 revise 路径必须执行相同的检查和更新

---

**E1. 程序化检查双路径**

检查目标：`_write_chapters` 和 `_execute_revise` 是否都包含全部 5 项程序化检查。

| 检查 | _write_chapters | _execute_revise |
|------|:-:|:-:|
| `tracker.auto_fix(draft, ch_num)` | | |
| `tracker.auto_fix_banned_words(draft, style_guide)` | | |
| `tracker.check_cliches(draft)` | | |
| `tracker.check_sentence_patterns(draft)` | | |
| `tracker.check_abstract_nouns(draft)` | | |

通过条件：两列均为 ✅

---

**E2. 追踪更新双路径**

检查目标：两条路径是否都执行完整的追踪更新。

| 步骤 | _write_chapters | _execute_revise |
|------|:-:|:-:|
| `tracker.update_tracking(ch_num, text, plan, review=review)` | | |
| `tracker.update_from_review(ch_num, review)` | | |
| `tracker.log_changes_csv(ch_num, before, after)` | | |
| `ch.review_status` 更新 | | |
| `ch.review_notes` 更新 | | |
| `ch.summary` 重新生成 | | |

通过条件：两列均为 ✅；`_execute_revise` 的 `log_changes_csv` source 参数为 `"revise"`

---

**E3. new 与 continue 状态恢复一致性**

检查目标：`cmd_new` 走 `start_new_novel`，`cmd_continue` 走 `resume_novel`，两者在进入 `_run_pipeline` 前是否都正确恢复了运行时状态。

| 状态 | start_new_novel | resume_novel |
|------|:-:|:-:|
| `_apply_style_temperatures` | ✅（phase 0 执行） | 需在 `_run_pipeline` 前调用 |
| `_apply_strictness` | ✅（phase 0 执行） | strictness 已在 config.json 持久化 |
| tracking 文件存在性 | Phase 2.5 检查 | Phase 2.5 检查 |

通过条件：`resume_novel` 在进入 pipeline 前已调用 `_apply_style_temperatures`；strictness 通过 config.json 持久化无需重设

---

**E4. editing 路径文件版本优先级**

检查目标：`_edit_chapters` 读取的是最终版草稿，而不是最初版本。

检查方法：确认 `_edit_chapters` 中读取草稿的逻辑：`ch.draft_path`（最后一次写入的版本，含重写版本路径）→ fallback 到 `drafts/chapter_xx.txt`

通过条件：`ch.draft_path` 在每次重写后都更新为最新路径；fallback 路径只在 `draft_path` 为空时触发

---

### F. LLM 输出类型安全

> 目标：AI 返回非预期结构时不会导致 pipeline 崩溃

---

**F1. chat_json 返回类型检查**

检查目标：每个调用 `chat_json` 的地方是否验证了返回类型。

| Agent/位置 | 预期类型 | 当前类型检查 |
|-----------|---------|------------|
| `StyleAdvisorAgent.run` | dict | |
| `DirectorAgent.run` | dict | |
| `PlotAgent.run` | list[dict] | |
| `ReviewerAgent.run` | dict | |
| `CriticAgent.run` | dict | |
| `tracker.analyze_development` | dict | |

通过条件：每行均有 `isinstance` 检查，返回错误类型时 raise 或返回安全默认值，不会让 `.get()` 在 list 上崩溃

---

**F2. schema 消费防御性访问**

检查目标：消费 chat_json 结果的代码是否都用 `.get()` 而非直接 `["key"]`。

检查方法：在 pipeline.py、tracker.py 中搜索 `result["` / `review["` / `tu["` 等直接访问模式

通过条件：所有外层字段均用 `.get(key, default)` 访问；嵌套字段有 `if xxx in result` 前置保护

---

**F3. 截断与 parse 失败传播**

检查目标：`chat_json` 在 JSON 截断或解析失败时的行为是否可控。

检查方法：在 `llm_client.py` 中确认：
1. `stop_reason == "max_tokens"` 时调用 `_continue_json` 最多重试3次
2. 3次均失败后 `parse_json` 抛出 `ValueError`
3. `ValueError` 是否被 pipeline 的 `try/except` 捕获，给出用户友好提示

通过条件：截断失败最终转化为可恢复错误提示，不会静默返回空 dict 或半截 JSON。明示链路：`_continue_json` 重试 3 次失败后落入 `parse_json` 抛 `ValueError`（半截 JSON 必然解析失败），`ValueError` 由 pipeline 顶层 `try/except Exception` 捕获并转为用户提示。

---

### G. 状态持久化安全

---

**G1. dataclass 字段默认值**

检查目标：`NovelState` 和 `ChapterState` 的所有字段是否都有默认值（确保旧 state 加载不会因缺失字段报 TypeError）。

检查方法：读取 `state_manager.py` 中两个 dataclass 的字段定义，标出无默认值的字段

通过条件：所有字段均有默认值（`= None`、`= ""`、`= 0`、`= field(default_factory=list)` 等均可）

---

**G2. StateManager.load 兼容性**

检查目标：`StateManager.load` 是否能正确处理字段增删场景。

检查方法：确认 `load` 方法使用 `__dataclass_fields__` 白名单过滤旧 state 的多余字段

通过条件：`load` 中包含类似 `{k: v for k, v in data.items() if k in NovelState.__dataclass_fields__}` 的过滤逻辑

---

**G3. 关键文件原子写入**

检查目标：哪些关键文件使用了 tmp+replace 原子写入，哪些没有。

| 文件 | 写入方式 | 风险 |
|------|---------|------|
| `novel_state.json` | `atomic_write_json`（tmp+replace） | 安全 |
| `world.json` | `atomic_write_json` | 安全 |
| `outline.json` | `atomic_write_json` | 安全 |
| `chapters.json` | `atomic_write_json` | 安全 |
| `review_reports/*.json` | `atomic_write_json` | 安全 |
| `tracking/*.json` | `atomic_write_json`（tracker `_write_json` 内部） | 安全 |

通过条件：报告中明确列出非原子写入的文件，及其实际风险（是否在长时间操作中写入）

---

### H. 用户输入边界

---

**H1. 输入中断保护**

检查目标：所有 `input()` 调用是否包裹了 `try/except (KeyboardInterrupt, EOFError)`。

检查方法：在 `main.py` 和 `pipeline.py` 中列出所有 `input()` 调用位置，逐一确认异常处理

通过条件：每个 `input()` 都在 try 块中，except 分支给出友好提示或安全退出

---

**H2. 参数边界校验**

检查目标：用户输入的关键参数是否有边界校验。

| 参数 | 校验规则 | 当前状态 |
|------|---------|---------|
| 小说名 `name` | 不含 `/\:*?"<>\|`，非 Windows 保留名（CON、NUL 等），非空 | |
| 总章数 `total_chapters` | ≥ 1 | |
| 每章最少字数 `words_min` | ≥ 500 | |
| 每章最多字数 `words_max` | ≥ words_min | |
| 遗忘阈值 | 格式错误时是否有安全 fallback | |

通过条件：以上均有校验；或明确记录已知缺口（见 self_check.md 17.2）

---

### I. 硬编码同步点

---

**I1. 禁用词/陈词滥调多处同步**

检查目标：`tracker.py` 中的硬编码列表是否与相关 prompt 保持一致。

| 列表 | 代码位置 | prompt 同步点 |
|------|---------|-------------|
| `_BANNED_REPLACEMENTS`（~60词） | tracker.py | writer_system.txt "AI高频词黑名单"、editor_system.txt、reviewer_system.txt "反AI腔检查"、style_advisor_system.txt |
| `_EMPTY_PHRASES`（6条） | tracker.py | editor_system.txt、reviewer_system.txt |
| `_CLICHE_PAIRS`（5对） | tracker.py | reviewer_system.txt 陈词滥调检测列表、editor_system.txt |

通过条件：代码与 prompt 中的词条完全一致；如有新增，5处/3处均已同步

---

**I2. _FIELD_MEANINGS 与追踪字段同步**

检查目标：tracker.py 的 `_FIELD_MEANINGS` 是否覆盖所有当前追踪文件的字段路径（影响 tracking_changes.csv 的"含义"列）。

检查方法：对比 6 个追踪文件的实际 JSON 结构（由 init_tracking 生成）与 `_FIELD_MEANINGS` 列表，找出无映射的字段路径

通过条件：所有追踪文件的常用字段路径均有中文映射；新增字段已同步到 `_FIELD_MEANINGS`

---

### J. 协议自检

---

**J1. 验证协议覆盖盲区**

检查目标：本次代码变更是否暴露了当前验证协议（本文件）的覆盖盲区。

判断标准：
- 发现某类 bug 但验证项中没有对应检查 → 需补充验证项
- 某段新增逻辑的正确性无法通过现有 A-I 项验证 → 需新增验证项
- 某个已有验证项的"通过条件"描述不够精确，导致 AI 可能给出错误结论 → 需修正

通过条件：明确列出"无盲区"或"发现 N 处盲区并已补充到本协议"

---

## 三、验证报告输出格式

每次执行后，按以下格式输出报告：

```markdown
## 验证报告 — [日期]

### 概要
- ✅ 通过：N 项
- ❌ 有问题：N 项
- ➖ 不适用：N 项
- 🔴 阻断级问题：N 个（必须修复后才能合并）
- 🟡 非阻断问题：N 个（建议修复）

### 阻断级问题
[每个问题：断裂点 + 影响范围 + 修复建议]

### 非阻断问题
[同上]

### 逐项结果
#### A1 Director 输出存储
结论：✅ 通过 / ❌ 有问题 / ➖ 不适用
依据：pipeline.py:184-190
说明：...

[以下每项同格式]
```

---

## 四、验证完成后的文档同步（必须执行）

验证报告输出后，AI 必须对照以下规则逐行判断是否需要更新文档，并**实际执行更新**。文档同步不是可选项，是验证流程的最后一步。

| 触发条件 | 必须更新的文档 | 更新内容 |
|---------|-------------|---------|
| 发现新 bug 并修复 | `docs/parameters.md` 第九章 | 追加 bug 记录行（编号、严重度、问题描述、修复位置） |
| 发现新 bug 并修复 | `README.md` 变更日志 | 追加修复摘要（日期 + 简述） |
| 新增或修改字段链路 | `docs/self_check.md` 对应章节 | 更新字段链路表，更新章节末"最后验证时间" |
| 新增或修改字段链路 | `docs/parameters.md` 第六章 | 更新 L1/L2/L3 追踪字段表 |
| 新增或修改 tracking 字段 | `docs/parameters.md` CSV 字段映射章节 | 更新字段路径与中文含义对照表 |
| `_FIELD_MEANINGS` 有增删 | `docs/parameters.md` CSV 字段映射章节 | 同步更新 |
| 新增或修改主流程/数据流 | `docs/flowchart.md` | 更新对应 Mermaid 图 |
| 新增或修改 config 参数 | `docs/parameters.md` 对应配置表 | 更新参数行 |
| 新增 Agent 或 Phase | `README.md` 架构图 + 核心特性 | 同步更新 |
| 新增或升级依赖 | `requirements.txt` + `README.md` 环境要求 | 同步更新 |
| 发现验证协议覆盖盲区 | `docs/verify_protocol.md` | 补充或修正验证项（J1 触发） |
| 以上均无 | 无需更新 | 在报告末尾注明"文档已是最新，无需同步" |

> **注意**：即使本次变更很小，也必须检查上表所有行。漏检某行等于放弃了文档与代码的同步保证。

---

*最后验证执行时间：2026-05-21（含 #46-#50 修复验证）*
*协议版本：1.1*
