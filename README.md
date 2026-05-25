# Novel Agent - AI 多角色协作小说写作框架

基于多 Agent 协作的 AI 小说生成系统。7 个专职 Agent 模拟真实出版流程，从风格分析到最终润色，全自动完成小说创作。

> **AI 协作者请先读 [`docs/execution_execution_workflow.md`](docs/execution_execution_workflow.md)** —— 它定义了接到需求时的执行流程（对齐 → 拆任务 → 实现 → 验证 → 文档同步 → 回告）。本项目要求每次代码变更后**同步更新所有受影响文档**（parameters / self_check / flowchart / requirements / README），execution_workflow.md 里有完整的同步矩阵。

## 架构设计

```
用户交互输入（故事灵感 + 风格偏好）
    ↓
StyleAdvisorAgent → 风格指南（题材探测 + 文风检测 + 写作规范 + 动态温度）
    ↓
用户确认写作参数（章数、字数、遗忘阈值）
    ↓
DirectorAgent  → 世界观 + 角色设定 + 场景地点 + 三幕大纲
    ↓
用户全量打磨（世界观+角色+地点+大纲完整 JSON，"是/调整/重写"三选一，每次 LLM 返回完整 JSON 确保一致性）
    ↓
PlotAgent      → 章节拆分 + 剧情要点 + 场景结构 + 情绪设计 + 张力管理 + 时空标记
    ↓
Tracking Init  → 角色状态 + 时间线 + 情节追踪 + 关系网络 + 校验规则 + 场景地点
    ↓
WriterAgent    → 撰写正文（含对话技巧 + 场景-续场模型 + 禁用词检查 + 角色名修正）
    ⇅
ReviewerAgent  → 三阶段一致性审核（不通过则打回重写）
    ↓
EditorAgent    → 文字润色 + 文风统一 + 章节衔接（含追踪数据注入）
    ↓
输出 TXT 文件（单章 + 全文合并）
```

## 核心特性

- **风格顾问**：根据用户描述自动探测题材类型、写作规范和文风，生成完整风格指南
- **动态温度**：根据题材自动为每个 Agent（含 Critic）推荐最佳温度参数
- **一致性追踪**：7 个追踪文件全程覆盖角色状态、时间线、伏笔、关系网络、场景地点（含同场角色双向关系自动记录）
- **程序化检查**：禁用AI词自动替换、角色名别名修正、陈词滥调检测、句式分析
- **多角色协作**：7 个 Agent 各司其职，模拟风格顾问→导演→编剧→作家→审稿→编辑→修订顾问的完整出版流程
- **Director 全量精修**：导演一次性产出世界观 + 角色 + 地点 + 大纲后，用户对完整 JSON 走 "是/调整/重写" 三选一循环，每次调整 LLM 返回完整 JSON 确保跨 block 一致性，打磨满意后再进入剧情拆章
- **审核循环**：自动检测逻辑矛盾、角色崩坏等问题，打回重写直到通过（最多 2 轮）
- **章节修订**：对已完成章节提供交互式修订流程，修订顾问分析意见并生成修改思路
- **长上下文管理**：每章完成后生成摘要，写后续章节时传入压缩上下文（世界观 9 类字段 + 大纲含转折点 + 章节计划 15 字段），保持全局一致性
- **断点续写**：每个关键步骤自动保存进度，中断后可从任意阶段恢复
- **可选分卷**：长篇小说（≥10 章）可选择按卷组织，带卷名和叙事焦点；卷信息贯穿 director → plotter → writer → tracker → 最终输出（卷标题页+单卷文件），不分卷时零影响
- **灵活配置**：每个 Agent 单独配置温度参数，支持风格指南动态覆盖
- **三层追踪更新**：L1 零成本字符串匹配 + L2 复用审核输出 + L3 独立 LLM 分析（每5章）
- **完整数据链路**：AI 生成的所有字段均经过存储→格式化→消费全链路验证，确保无静默丢字段
- **Web 可视化界面**：FastAPI + Vue3 SPA 暗色主题前端，易读结构化数据展示（世界观/大纲/风格指南智能渲染）、实时进度追踪、统一操作入口（详情页内联继续/修订），覆盖 new/continue/revise 全流程

## 环境要求

- Python 3.10+
- GLM-5.1 API（在 https://open.bigmodel.cn/ 申请）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Token

复制示例文件并填入你的 API Token：

```bash
cp .env.example .env
```

编辑 `.env`，将 `your_token_here` 替换为你的真实 Token：

```
GLM_API_TOKEN=your_real_token_here
```

如需修改模型或接口地址，编辑 `config.yaml`：

```yaml
api:
  base_url: "https://open.bigmodel.cn/api/anthropic"
  model: "glm-5.1"
```

### 3. 启动 Web 界面

```bash
python3 web_main.py
```

浏览器访问 `http://localhost:8000`，通过 Web 界面进行所有操作（创建小说、继续创作、修订章节）。

## 项目结构

```
Orchestra/
├── web_main.py              # Web 服务入口
├── config.yaml              # 全局配置（API参数 + 小说参数 + Agent温度）
├── .env                     # API Token
├── requirements.txt
│
├── agents/                  # Agent 实现
│   ├── base.py              # BaseAgent 抽象基类（温度覆盖 + 风格过滤）
│   ├── style_advisor.py     # 风格顾问：题材探测 + 文风检测 + 写作规范
│   ├── director.py          # 导演：世界观 + 角色 + 大纲
│   ├── plotter.py           # 编剧：章节拆分 + 剧情规划
│   ├── writer.py            # 作家：撰写正文 + 根据反馈重写
│   ├── reviewer.py          # 审核：逻辑一致性 + 角色合理性
│   ├── editor.py            # 编辑：文字润色 + 章节衔接
│   └── critic.py            # 修订顾问：分析修改意见 + 生成修改思路
│
├── prompts/                 # System Prompt 模板（可自由修改）
│   ├── constitution.md      # 共同创作准则（自动注入所有 Agent）
│   ├── style_advisor_system.txt
│   ├── director_system.txt
│   ├── plotter_system.txt
│   ├── writer_system.txt
│   ├── reviewer_system.txt
│   ├── editor_system.txt
│   ├── critic_system.txt
│   └── tracking_analysis.txt
│
├── core/                    # 基础设施
│   ├── llm_client.py        # API 客户端封装（重试 + JSON解析）
│   ├── state_manager.py     # 状态持久化（JSON）
│   ├── context_manager.py   # 长上下文管理（摘要 + 压缩 + 追踪数据注入）
│   ├── tracker.py           # 追踪系统（7个JSON文件 + 忘却检测 + 自动修复）
│   ├── pipeline.py          # 流程编排器（数据存储+格式化+消费全链路）
│   ├── braindump.py         # 立项问答 + 负面约束提取
│   ├── prompt_utils.py      # Web 输入封装（WebSocket 双向通信）
│   ├── ui.py                # Web 输出层（通过 WebSocket 推送前端）
│   └── name_generator.py    # AI 小说名生成 + 校验
│
├── web/                     # Web 服务层
│   ├── app.py               # FastAPI 应用（WebSocket + REST + SPA）
│   ├── bridge/
│   │   └── session.py       # 会话管理（线程隔离 + 队列通信）
│   └── routers/
│       └── novels.py        # REST API（小说列表/详情/章节）
│
├── frontend/                # Vue3 SPA 前端
│
├── docs/                    # 文档
│   ├── execution_workflow.md       # 需求执行工作流（AI 必读，第一份）
│   ├── flowchart.md                # 系统流程图（Mermaid）
│   ├── parameters_and_changelog.md # 参数/常量/CSV字段映射/Bug记录（权威来源）
│   ├── system_reference.md         # 系统参考手册（字段链路+状态机+边界场景+故障速查）
│   └── verification_protocol.md    # AI 可执行验证协议（大批量改代码后用）
│
└── output/<小说名>/         # 输出目录（自动创建）
    ├── novel_state.json     # 全局状态（用于断点续写）
    ├── world.json           # 世界观设定
    ├── outline.json         # 故事大纲
    ├── chapters.json        # 章节规划
    ├── tracking/            # 追踪数据
    │   ├── character_state.json
    │   ├── timeline.json
    │   ├── plot_tracker.json
    │   ├── relationships.json
    │   ├── validation_rules.json
    │   ├── locations.json
    │   ├── config.json
    │   └── tracking_changes.csv
    ├── drafts/              # 原始草稿
    ├── review_reports/      # 审核报告
    ├── edited/              # 润色后章节
    └── final/               # 最终版本 + 全文合并
```

## 配置说明

`config.yaml` 主要配置项：

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `api.model` | 使用的模型 | glm-5.1 |
| `api.max_tokens` | 单次请求最大 token | 131072 |
| `novel.default_chapters` | 默认章节数 | 20 |
| `novel.words_per_chapter.min` | 每章最少字数 | 3000 |
| `novel.words_per_chapter.max` | 每章最多字数 | 5000 |
| `novel.review_max_retries` | 审核不通过最大重写次数 | 2 |
| `agents.*.temperature` | 各 Agent 默认温度 | 被风格指南动态覆盖 |

## 自定义 Prompt

所有 Agent 的 system prompt 存放在 `prompts/` 目录下，是纯文本文件，可以直接编辑来调整写作风格、审核标准等。Writer prompt 中支持以下占位符：

- `{words_min}` / `{words_max}` — 每章字数范围
- `{tone_guidance}` — 文风指导
- `{narrative_perspective}` — 叙事视角

## 追踪系统

追踪系统维护 7 个 JSON 文件，通过三层机制保持数据活跃：

| 层级 | 机制 | LLM 调用 |
|------|------|----------|
| L1 | 字符串匹配（角色名出现检测、plot_points 提取） | 0 |
| L2 | 复用审核输出（tracking_updates 字段） | 0（额外） |
| L3 | 独立 LLM 角色成长分析 | 每5章1次 |

支持的检测功能：
- **遗忘检测**：角色N章未出场、支线停滞、伏笔未回收
- **自动修复**：角色名别名替换（Director 生成 aliases 初始数据）、禁用AI词替换（60+词条）
- **质量检查**：陈词滥调检测、连续长/短句告警、抽象名词标记
- **变更日志**：`tracking_changes.csv` 记录每章追踪数据变化

## 输出说明

创作完成后，`output/<小说名>/final/` 目录下包含：

- `chapter_01.txt` ~ `chapter_N.txt` — 每章最终版
- `<小说名>_全文.txt` — 全文合并版

## 注意事项

- 首次运行会联网调用 API，请确保网络畅通
- 20 章小说约需 1-2 小时完成（视 API 响应速度）
- 建议先用短篇（1-3章）跑一轮测试效果

## 变更日志

### 2026-05-23 剧情拆章大纲 + 章节正文展示（#171）

- **#171** 剧情拆章 Tab 展示 PlotAgent 完整章节计划（摘要/张力/情绪曲线/场景结构/情节点/出场角色/伏笔/悬念等）
- 章节进度/已完成 Tab 每章新增"阅读"按钮，右侧 Drawer 展示正文内容
- REST API `GET /novels/{name}` 返回值新增 `chapter_plans` 字段

### 2026-05-23 Tab 数据不刷新 + 精修中断 phase 跳转修复（#172-#173, #175-#176）

- **#172** 独立详情页有活跃会话时 Tab 数据停留在首次加载，新增 `watch(hasSession)` 在会话激活时启动 5s 定时刷新 REST API
- **#173** WebSocket 断连时精修循环误判为用户确认导致 phase 跳转，`_refine_block` 捕获 `UserAbort` 时设置 `_interrupted`，所有调用方保存已调整数据但不推进 phase
- **#175** `_confirm_refine` 两处 `except UserAbort: return "yes"` 吞掉异常导致 #173 修复无效（死代码），移除后异常正确传播到 `_refine_block`
- **#176** `watch(hasSession)` 写在 `const hasSession` 声明前导致 ReferenceError 白屏，调整声明顺序
- **#177** 精修调整后数据仅存在内存，Tab 不更新；`_refine_block` 新增 `on_update` 回调实时写盘

### 2026-05-25 自检修复（#178）

- **#178** `auto_fix` 返回值直接下标访问改为 `.get()` 防御式访问，避免结构不完整时 KeyError 崩溃

### 2026-05-23 阶段回滚功能（#174）

- **#174** 新增 `POST /api/novels/{name}/rollback` API，支持回滚到 collecting_params / directing / plotting / writing 四个阶段，自动清理后续阶段产出的磁盘文件和 state 数据
- 前端各已完成 Tab 添加"回滚到此阶段"按钮 + 确认框，回滚后页面自动刷新

### 2026-05-23 移除 CLI，统一 Web 架构（#170）

删除所有 CLI 端逻辑，统一为 Web-only 架构：

- 删除 `main.py`（CLI 入口），提取 braindump 逻辑到 `core/braindump.py`
- `core/prompt_utils.py` 从 prompt_toolkit CLI 实现改为 WebSocket 原生输入
- `core/ui.py` 从 Rich 终端渲染改为 WebSocket 原生输出
- `core/llm_client.py` Spinner 改为无操作（进度由 Web 层管理）
- `web/bridge/__init__.py` 猴子补丁逻辑不再需要（core 已是 Web 原生）
- 删除 `web/bridge/web_prompt.py` 和 `web/bridge/web_ui.py`（已合并到 core）
- 移除依赖 `prompt_toolkit` 和 `rich`
- 所有文档同步更新

### 2026-05-23 自检修复（#159-#166）

全量代码审计发现 8 个非阻断问题并修复：

- **#159** 禁用词五处同步：tracker.py `_BANNED_REPLACEMENTS` 补至 81 条，四个 prompt 统一标注
- **#160** Director `style` 死字段：从 prompt schema 删除，`_split_director_output` 清理残留
- **#161** plotter.py 防御性访问：`result["chapters"]` → `result.get("chapters", [])`
- **#162** dataclass 默认值：NovelState/ChapterState/VolumeDef 核心字段补默认值
- **#163** 小说名 Unicode 校验：sanitize_novel_name 增加控制字符/零宽字符检查
- **#164** holistic 白名单：`_split_director_output` 增加 known_world_keys 过滤意外字段
- **#165** 前端消息可见性：`param_confirmed` 从 displayMessages 过滤列表移除
- **#166** SessionManager 线程安全：`get()` 方法加锁

### 2026-05-22 用户需求传播修复（#101-#105）

修复用户需求（如"不要升级流""要有后宫情节"）在后续阶段丢失的问题：

- **#101** Writer/Editor 阶段丢失：`build_running_context` 新增 `story_idea` + STYLE_FIELDS 扩展 setting/review + StyleAdvisor 增加负面约束提取
- **#102** Director 阶段仍可能违反：StyleAdvisor 增加否定检测规则 + Director/Plotter 接收 requirements + 4 个 director prompt 增加负面约束遵守指令
- **#103** Braindump 阶段负面约束被软化：立项问答后增加 `_extract_negative_constraints` 显式提取负面约束追加到 style_description
- **#104** 上下文窗口溢出导致从第一章重新写：写作/编辑循环加 try/except，异常时保存 `current_chapter` 再退出
- **#105** CLI 展示截断过小：全面放宽各阈值（灵感预览 300 字、context 总预算 80K、JSON 截断 3-4K）

### 2026-05-22 Web 前端模式（#107）

新增 FastAPI + Vue3 SPA Web 前端，覆盖全流程可视化和交互：

- **#107** 新增 `web/` 桥接层（monkey-patch prompt_utils/ui → WebSocket 版），pipeline.py 无需修改
- 新增 `frontend/` Vue3 SPA（Naive UI 暗色主题 + 绿色强调），JSON 用 Tab 分页展示
- WebSocket 双向协议：output 消息流 + input_request 用户交互 + 生命周期管理
- REST API：小说列表/详情/章节内容（`/api/novels`）
- CLI（`main.py`）和 Web（`web_main.py`）双入口共存
- 启动方式：`py -3.10 web_main.py` → 浏览器访问 `http://localhost:8000`

### 2026-05-22 Web 端增强（#108-#137）

Web 前端体验全面优化：

- **#108-#109** 输入组件样式修复（PromptInt 对齐 + message 前导空格）
- **#110-#112** 补齐 AI 起名、名称校验、继续创作入口；`sanitize_novel_name` 移入 `core/name_generator.py`
- **#113-#119** NovelDetailView 独立详情模式 + 分阶段 Tabs + 章节子阶段流水线 + 左右布局
- **#120-#122** 统一用户行为路径：NovelDetailView 为唯一操作入口，AppHeader 精简
- **#123-#125** 小说名称必填 + Web 检查点自动继续 + 移除终止流程按钮
- **#126-#132** 修订流程 + 全量 `print()` → `ui.*` 转换（20 处），Web 端全部输出可见
- **#133-#137** 新增 JsonViewer 通用组件，替换 5 处原始 JSON 为易读格式（概要/列表/标签/折叠兜底）
- **#138-#141** JsonViewer 完全重写：修复世界观不显示（holistic `data.world` 嵌套解析）、角色字段堆叠（嵌套折叠+子维度展开）、地点/势力/历史详情缺失、样式错位

### 2026-05-22 可选分卷结构（#142-#150）

长篇小说可选按卷组织，带卷名和叙事焦点：

- **#142-#143** `VolumeDef` 数据类 + 参数收集阶段可选分卷流程（≥10 章时可启用，LLM 建议分卷方案+用户确认）
- **#144-#145** Director/Plotter 支持卷结构：大纲新增 `volumes` 键，批次生成对齐卷边界，卷末章收束指导
- **#146-#147** Tracker 激活预留的 `volume`/`volumeEnd` 字段；ContextManager 注入当前卷信息
- **#148** 全文合并输出卷标题页 + 每卷单独文件
- **#149-#150** 前端章节列表按卷分组显示；REST API 返回 volumes 字段
- `volumes=None` 时所有代码路径与无卷模式完全一致，零影响

### 2026-05-22 长篇上下文溢出防护 + 错误友好化（#151-#157）

300 章长篇小说全阶段上下文安全 + Web 端错误可读：

- **#151-#152** Writer 续写截断（40K）+ Plotter 摘要滑动窗口（最近 30 条完整 + 50 条简略）
- **#153-#154** `get_tracking_context` 总输出 15K 上限 + 伏笔 20 条上限；ContextManager tracking 硬限 10K
- **#155** Tracker JSON 数组（appearance/warnings/plotHoles/errors）滑动窗口裁剪（保留 30-50 条）
- **#156** Critic world_data 截断 2K + tracking 截断 10K，对齐 Reviewer 行为
- **#157** Web 端 LLM 错误分类中文提示（JSON 截断/网络断/限流/超时/认证），替代原始异常堆栈

### 2026-05-22 Writer 重写实质化（#158）

- **#158** Writer rewrite prompt 从保守改为 7 条强制实质性重写指令（major 必须大幅重写相关段落，warning 必须可感知改善），重写温度提高 +0.25（上限 0.95），解决审核循环中"重写后问题不变"的问题

### 2026-05-22 Director 精修策略改为全量（#106）

增量生成精修存在"改后不同步前"问题（精修角色B时无法反向更新已确认的角色A/世界观），恢复为一次性生成 + 全量精修：

- **#106** 恢复 `director.run()` 一次性生成，新增 `_run_directing_holistic` 全量精修方法
- 新增 `REFINE_HOLISTIC_PROMPT`，指导 LLM 接收并输出完整 JSON（world_data + characters + locations + outline）
- 每次调整/重写 LLM 返回完整 JSON，确保跨 block 一致性（角色关系双向对齐、大纲与设定对齐等）
- 断点续传标记简化为 `"holistic"`（单一标记替代多个 per-block 标记）

### 2026-05-22 Director 增量生成重构（#100，已由 #106 取代）

重构 Director 阶段架构，从"一次性生成全部→分块精修"改为"按层级增量生成+逐个确认"：

- **#100** 精修阶段前面的修改后面的内容感知不到 → 重构为增量生成架构：Director 按层级生成 world（含角色/地点规划）→ 逐个生成角色卡 → 逐个生成地点卡 → 生成大纲，每个 piece 生成时带完整已确认上下文，然后精修确认
- 新增 4 个 prompt 文件：`director_world.txt`、`director_character.txt`、`director_location.txt`、`director_outline.txt`
- 新增 `_build_director_context_json` 和 `_build_incremental_context` 方法，包含完整已确认数据（不剥离角色/地点，截断放宽至 2000 字符）
- 向后兼容：旧 `phase="refining"` 的 state 仍走旧精修流程

### 2026-05-22 全量自检修复（#94-#99，6 项）

全量代码自检发现 6 个数据链路/类型安全问题，逐一修复：

- **#94 A3** reviewer `quality_breakdown` 八维评分无消费 → pipeline._write_chapters 和 _execute_revise 中添加分维展示
- **#95 B4** plotter 5 个字段（previous_link / opening_hook_type / ending_hook_type / characters_on_stage / scene_list）无消费 → _format_chapter_plan 补全格式化
- **#96 F1** tracker.analyze_development 缺 isinstance 类型检查 → 补全 `isinstance(result, dict)` 防护
- **#97 I2** _FIELD_MEANINGS 缺 psychology 和 active_validation_level 映射 → 补全中文映射
- **#98 D3** _GENRE_STRICTNESS 未覆盖"都市"题材 → 添加 `"都市": "flexible"`
- **#99 J1** 验证协议盲区 → B3 表格更新 + 新增 J2 检查项（prompt schema 字段消费覆盖）

### 2026-05-21 融合 chinese-novelist-skill v2.0（A-J 十组共 30 项）

把 `chinese-novelist-skill/references/guides/*.md` 中的写作方法论批量注入到 prompts 与代码层，每项均与用户逐一确认（30 项融合 / 6 项跳过）：

- **A 组 Writer 强化（#64-#71，8 项）**：十种强力开头技巧、开头致命错误 6 条、悬念钩子十三式、章首引子七式、AI 高频词扩充（13 词）、章节节奏控制三条、中文文学技法 5 式（白描/留白/意象/草蛇灰线/蒙太奇）、打破读者预期 4 技。注入 `prompts/writer_system.txt`（12544 字）和 `prompts/editor_system.txt`（2754 字）
- **B 组 人物塑造（#72-#75，4 项）**：director 输出 characters 增加 `mbti / biggest_fear / fatal_flaw / inner_desire` 4 字段；新增缺陷致命化原则、反派镜像主角、配角功能性。注入 `prompts/director_system.txt`
- **C 组 对话技法（#76-#79，4 项）**：对话六目的表、潜台词四技、对话权力博弈表、对话五禁忌。注入 `prompts/writer_system.txt`
- **D 组 扩充/防注水（#80-#82，3 项）**：内容扩充 6 技巧、题材扩充 4 策略（动作/言情/悬疑/玄幻）、防注水检测表
- **E 组 评审体系（#83-#84，2 项）**：八维质量评分（opening_hook / plot_progression / character_depth / dialogue_quality / ending_hook / pacing / show_not_tell / language_quality，0-80 分）+ 阈值门（<60 必须 approved=false）；言情/都市 7 项 + 动作 5 项题材专项校验。JSON 新增 `quality_breakdown` 字段
- **F 组 大纲扩展（#85，1 项）**：plotter JSON 5 新字段（previous_link / opening_hook_type / ending_hook_type / characters_on_stage / scene_list）
- **G 组 起名增强（#86-#88，3 项）**：题材-风格映射表、五种标题创作技巧（核心冲突 / 主角命名 / 意象隐喻 / 反差 / 悬念留白）、AI 套路黑名单。注入 `core/name_generator.py _SYSTEM_PROMPT`
- **H 组 情节结构（#89，1 项）**：8 套结构模板（三幕 / 英雄之旅 / 悬疑 / 言情 / 惊悚 / 反转 / 多线叙事 / 网文升级流）+ 题材-结构决策表
- **I 组 工程机制（#90-#91，2 项）**：(I1) 中文字数统计 `_count_chinese_chars()` 替换 `len(text)`，续写阈值判断更准确；(I2) review-rewrite 循环硬上限 `review_max_retries=3`，到上限后接受当前版本，避免 reviewer 一直 reject 导致无限循环
- **J 组 硬约束（#92-#93，2 项）**：(J2) 每章 ≥2 个张力波峰（writer 写入 + editor 复核）；(J4) 每章 ≥1 处意外转折（writer 硬约束段）

跳过项（用户决策）：A0 自动检测题材 / B0 角色冲突矩阵 / C0 群戏调度 / I3 章节字数日志 / I4 写作日志格式 / J1 词汇丰富度自动检测 / J3 主题贯穿度自动检测。

### 2026-05-21 rewrite 实质变化 + braindump 格调适配 style

针对实际跑 `new` 后用户反馈的两个严重问题（#62-#63）：

- **#62 rewrite 三重组合**：三处 rewrite（braindump 章节重写 / writer 审稿打回 / refine 整块重写）原来"同 prompt + 同温度"再调一次 LLM，GLM-5.1 输出几乎不变。现统一升级为三重组合：(a) **反上下文** — rewrite 时把当前版本拼到 user msg 标注"请勿沿用此方向"；(b) **升温** — braindump/refine rewrite 升至 0.9，writer rewrite 升至 `min(初稿温度+0.15, 0.9)`；(c) **system 明示** — 新增 `_REWRITE_DIRECTIVE` / `REFINE_REWRITE_DIRECTIVE` / writer `is_rewrite=True` 三处尾部追加"重写专项要求"段。`_llm_refine` 签名加 `rewrite/previous` 参数，`_refine_block` 外层 rewrite 改传 `rewrite=True, previous=result`
- **#63 Braindump 格调适配 style**：原 `_SYSTEM_PROMPT` 写死"文学顾问 / 情感真相 / 深层主题 / 关键问题 / 英雄之旅 / 文学弧线"，对网文/言情/甜文/悬疑题材格调完全错位。现改为函数 `_build_braindump_system(style, is_rewrite)` 根据用户输入的 style 字符串动态拼接 `_BRAINDUMP_SYSTEM_BASE + _BRAINDUMP_STYLE_GUIDANCE.format(style) + _BRAINDUMP_NEUTRAL_TAIL`，guidance 中列出 4 类风格的措辞要求（网文/严肃文学/悬疑/玄幻），让 LLM 自己匹配格调；4 条 section prompts 全部改为"多选词"中性化（核心情感/核心冲突/核心钩子/核心爽点 按故事类型自动选），structure 增加"网文升级流 / 单元剧 / 双线交织"等候选

### 2026-05-21 参数收集精简 + Director 输出分块打磨循环

针对实际跑 `new` 后用户反馈的两个体验问题（#60-#61）：

- **#60 参数收集精简**：`_collect_params` 砍掉末尾"自定义遗忘阈值"和"禁用检查类别"两步对用户无意义的 `prompt_single` 交互。AI 已在 `style_guide.suggestions.tracking_thresholds` 给出推荐值，直接采纳；`config["disabled_checks"]` 保持空（全部启用）；尾部 `show_param_confirmed` 仍展示阈值，让用户知情
- **#61 Director 输出分块打磨**：在 `directing` 与 `plotting` 之间插入新 phase `refining`（Phase 1.5）。`core/pipeline.py` 新增 `_refine_director_output` 编排 4 个 block——世界观 / 每张角色卡 / 每张地点卡 / 大纲——逐块走 "是/调整/重写" 三选一循环（参考 braindump 模式）。`core/refine_prompts.py` 新建文件存放 4 个 system_prompt（要求 LLM 输出结构一致的 JSON）；`core/ui.py` 新增 `show_refine_block(label, content, modified)` 将 dict/list JSON 美化后塞入 Panel
- **断点续传**：`NovelState` 新增 `refined_blocks: list[str]`，每个 block 确认后 append（命名 `world` / `outline` / `character:<name>` / `location:<name>`）。中断后 resume 自动跳过已确认块；旧 state.json 无此字段时 `__dataclass_fields__` 白名单过滤（#43）保证默认 `[]` 注入
- **状态机扩展**：`main.py phase_names` 新增 `"refining": "精修世界观"`；`docs/flowchart.md` 主流程图在 Phase 1 与 Phase 2 之间插入 Phase 1.5；`docs/system_reference.md` 第十二章状态机 + 新第二十章「精修阶段链路」

### 2026-05-21 CLI 体验升级（Rich 渲染层 + AI 起名）

提升 CLI 视觉层级并新增 AI 起名辅助（#56-#59）：

- **#56 Rich 渲染层**：新建 `core/ui.py` 基于 rich 13.x，集中所有展示函数（`banner` / `section` / `divider` / `show_braindump_*` / `show_param_*` / `show_novel_list` / `show_completion` / `info/warn/success/error/hint`）。`main.py` 与 `core/pipeline.py` 中所有 print 全部迁移至 `ui.*`；输入仍由 `prompt_toolkit`（`core/prompt_utils.py`）处理，输入/输出职责分离
- **#57 AI 起名**：新建 `core/name_generator.py`，`suggest_novel_names(llm, idea, style, n=3)` 基于故事火花生成 3 个候选名（温度 0.9，规则化清洗编号 / 书名号 / 长度过滤），失败时返回空 list 由调用方降级。`main.py` 新增 `_pick_novel_name`：yes/no 询问 → AI 生成 → 选 / 再生成 / 自输 → `_sanitize_novel_name` 校验。`cmd_new` 输入顺序调整为「火花 → 名字 → 风格」以便起名能基于火花
- **#58 Windows GBK 兼容**：`core/ui.py` 在 `import rich` 之前对 win32 平台调用 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，解决 ✓ / ⚠ / ℹ 等 Unicode 符号在 GBK 控制台抛 UnicodeEncodeError 的问题
- **#59 设计权衡**：原 plan 设计的 `ChapterProgress`（rich.progress.Progress Live 进度条）会与 `_handle_retire` 等 prompt_toolkit 输入抢占终端控制权。**改用** `ui.section()` 渲染章节头 + `ui.info/warn/success/hint` 滚动输出 stage 进展；`ChapterProgress` 类保留在 `core/ui.py` 供未来非交互场景使用
- **新增依赖**：`rich>=13.0.0,<14.0.0`
- **文档同步**：`docs/parameters_and_changelog.md` 第八章新增 rich / name_generator 硬编码常量记录；第十章新增 #56-#59

### 2026-05-21 断点续写机制审计与修复

对断点续写机制进行全量审计，发现并修复 6 个问题（#51-#56）：

- **#51（严重）章内中断丢进度 + 追踪数据重复**：`_write_chapters` 在审核通过后才推进 `current_chapter`，章中段（writer 完成审核未完成 / 审核完成 tracker 未完成）中断重启会从同章开头重跑，导致 (a) 已通过审核的草稿被 writer 重写；(b) `update_tracking` 第二次为同章写入 `appearanceTracking / majorEvents / completedNodes / locations.events` 形成重复条目 — **已修复**：(1) `ChapterState` 新增 `stage` 字段（pending→drafted→reviewed→tracked），`_write_chapters` 拆分为 3 段，每段完成后落盘 state，恢复时按 stage 跳过已完成段；(2) `tracker.update_tracking` 4 处追加列表前增加 `any(e.get("chapter") == chapter_num for e in lst)` 幂等检查
- **#52（严重）resume 时严格度未应用**：`resume_novel` 只调用 `_apply_style_temperatures`，若 `styling` 阶段完成后但 `_apply_strictness` 调用前 crash，下次 resume 时审核严格度恢复默认 balanced（违反风格指南推荐） — **已修复**：`resume_novel` 在 `_apply_style_temperatures` 后追加 `_apply_strictness(state)`
- **#53（中等）validation_level 同步缺失**：Phase 2.5 中 `_apply_validation_level(tracker)` 嵌套在 `if missing or config_missing:` 内，追踪文件已存在时不会根据 strictness 同步 `active_validation_level` — **已修复**：移出 if 块，每次进入 Phase 2.5 均执行
- **#54（中等）revise 缺 phase 守卫**：`revise_chapter` 不检查 `state.phase`，对未完成创作流程的小说也允许修订 — **已修复**：头部新增 `if state.phase not in ("editing", "complete"): return` 守卫
- **#55（轻微）_collect_params UserAbort UX**：阈值 / 禁用类别两处 `prompt_single` 的 `UserAbort` 静默吞掉 — **已修复**：增加明确提示文案
- **验证**：tracker 幂等性测试通过（同章 2 次 `update_tracking` 不产生重复条目），全模块语法和导入正常

### 2026-05-21 录入流程跨平台重构

`new` 命令录入流程长期存在四类问题：①Windows 缺 `readline` 模块导致启动报错；②输入字符后退格 / 方向键行为在不同终端（PowerShell / cmd / iTerm2）下不一致；③多行输入超出终端宽度时光标乱跳；④小说名输错后必须重启命令。本次一并重构：

- **新建** `core/prompt_utils.py`：基于 `prompt_toolkit` 的统一交互层，提供 `prompt_single` / `prompt_multiline` / `prompt_choice` / `prompt_yes_no` / `prompt_int` 五个工具函数 + `UserAbort` 自定义异常 + `is_interactive` 上下文检测
- **删除** `main.py` 顶部 `import readline` + `readline.parse_and_bind`（Windows 启动崩溃根因）
- **重构 `cmd_new`** 录入流程为线性 3 步，每步独立可重试：小说名（错时原地重输不退命令）→ 风格（可留空）→ 故事灵感（多行 Ctrl+D 提交）
- **迁移所有 input()**：`main.py` 5 处 + `core/pipeline.py` 9 处全部改用 `prompt_utils`；参数边界校验交由 `prompt_int(min_val, max_val)` 处理（总章数 ≥1、最少字数 ≥500、最多字数 ≥words_min）
- **`cmd_continue` / `cmd_revise`** 改用 `prompt_choice` 列表选择，避免拼错小说名 / 章节号
- **Ctrl+C 统一抛 `UserAbort`** 而非 KeyboardInterrupt，上层精准 catch 后给出"已取消"提示，不再裸抛
- **新增依赖**：`prompt_toolkit>=3.0.0,<4.0.0`（纯 Python 包，Win/Mac/Linux 通用）

### 2026-05-21 闭环验证执行 + 全量修复

按 `docs/verification_protocol.md` 28 项验证项（A-J）执行闭环验证，发现 5 个非阻断问题（#46-#50）并全部修复：

- **#46（D3）**：`_GENRE_STRICTNESS` 缺 `武侠/奇幻/科幻` 题材映射 — **已修复**：补充 `武侠/奇幻 → flexible`、`科幻 → strict`
- **#47（G3）**：关键 JSON 文件非原子写入 — **已修复**：`state_manager.py` 新增 `atomic_write_json(path, data)` 工具函数（tmp+replace），pipeline 4 处直接写入 + tracker `_write_json` 全部改用该函数
- **#48（H2）**：`cmd_new` 小说名缺少安全校验 — **已修复**：`main.py` 新增 `_sanitize_novel_name`，校验非法字符 / Windows 保留名 / 长度上限 64 / 尾部 `.`/空格
- **#49（C5）**：`init_tracking` 全量重写 — **已修复**：`tracker.init_tracking` 新增 `missing` 参数，默认按"仅初始化磁盘不存在的文件"策略保护已有数据
- **#50（F1）**：`Director.run` / `Reviewer.run` 缺少类型检查 — **已修复**：返回安全默认 dict
- **协议盲区**：F3 通过条件补充明示 `_continue_json` fallback to existing_text → `parse_json` 抛 ValueError 的链路

### 2026-05-21 文档体系重构 + StateManager 兼容性修复

- **新建** `docs/verification_protocol.md`：AI 可执行验证协议，含 28 项检查（A-J）+ 标准报告格式 + 文档同步规则
- **重写** `docs/parameters_and_changelog.md`：所有参数/常量/Bug 记录的权威来源，新增完整 `tracking_changes.csv` 字段中文映射表（~130 条）
- **重构** `docs/system_reference.md`：聚焦字段链路参考手册，删除与 parameters_and_changelog.md 重叠章节，每章添加"最后验证时间"标记
- **更新** `docs/flowchart.md`：明确单一职责（仅 Mermaid 流程图）
- **修复 #43**：`StateManager.load` 增加 `__dataclass_fields__` 白名单过滤，state.json 含未知字段不再 TypeError
- **修复 self_check 4 处描述错误**：dataclass 删字段行为、init_tracking 全量重写已知 bug、auto_fix_suggestions 双路消费、consistency_score 覆盖条件

### 2026-05-21 数据链路全量修复

修复 9 个"AI 生成数据未正确流转到下游消费者"的严重/中等问题：

- Director 生成的 `locations` 现在正确存入 `world_data` 并通过 `_condense_world` 传递给所有后续 Agent
- `_condense_world` 从仅提取 2 类字段扩展为 9 类（setting、narrative_perspective、unique_elements、rules、social_structure、geography、factions、history、daily_life、characters 含角色前缀）
- `_format_chapter_plan` 从 7 字段扩展为 15 字段（新增 emotional_type/intensity、characters_involved、foreshadowing、active_plotlines、act、location、time、tension_level、scene_structure）
- Plotter prompt 新增 `location`/`time`/`duration` 输出字段
- Director prompt 新增角色 `aliases` 字段
- `_condense_outline` 新增 `key_turning_points` 提取
- Tracker 初始化改为检查全部 6 个追踪文件（而非仅 character_state）
- `_consume_review` 修复 timeline 重复写入和 dict 布尔判断问题
- `update_tracking` 合并 character_state 重复读取

### 2026-05-21 自检审计修复

修复 6 个代码 bug + 15 个文档偏差：

- Phase 2.5 新增 `config.json` 独立缺失检查（#35）
- `writer.rewrite` 添加字数不足续写逻辑（#36）
- `_consume_review` 中 `knowledge_state_issues` 改为写入 `consistency.warnings`（#37）
- `_init_timeline` 新增 `_extract_travel_routes` 从 world_data 提取旅行路线（#38）
- `_condense_world` 角色描述新增 `background` 子字段提取（#39）
- `_condense_world` 新增 `tone`/`name` 字段提取，消除死字段（#41）
- Reviewer `strengths[]` 注入 rewrite 反馈，指导 writer 保留优秀段落（#42）
- Reviewer prompt 新增 5 对陈词滥调具体检测列表（#40）
- 自检文档（`docs/system_reference.md`）修正 6 处与代码不符的描述，补充 9 处遗漏内容

### 2026-05-23 Web 精修数据无变化修复

修复 Web 模式下 director 精修阶段"调整"后数据不变的根因：

- `_send_input_request` 的 `break`/`continue` 逻辑错误导致 `WebUserAbort` 被误抛，精修反馈被静默忽略（#167）
- `_continue_json` 截断回退静默返回不完整数据（#168）
- `_split_director_output` 白名单过窄导致 LLM 生成的键被丢弃，改用排除法（#169）

## 致谢

本项目通过 `skills-lock.json` 锁定了两个外部 skill 作为方法论来源：

- [`penglonghuang/chinese-novelist-skill`](https://github.com/penglonghuang/chinese-novelist-skill) —— 2026-05-21 融合 A-J 十组 30 项（写作技法 / 人物 / 对话 / 评审八维 / 情节结构 / 起名 等，详见变更日志）
- [`junaid18183/novel-architect-skills`](https://github.com/junaid18183/novel-architect-skills) —— b443649 引入，提供场景结构 / 情节模板 / 共享创作准则等架构设计

本项目的追踪系统（角色状态、时间线、伏笔、关系网络、一致性校验、禁用词检查）融合自 [wordflowlab/novel-writer-skills](https://github.com/wordflowlab/novel-writer-skills) 的 `story-consistency-monitor` 技能。

场景结构规划、情绪曲线设计、线索分布管理等编剧方法论参考了 [wordflowlab/novel-architect-skills](https://github.com/wordflowlab/novel-architect-skills) 的架构设计理念。
