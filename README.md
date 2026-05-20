# Novel Agent - AI 多角色协作小说写作框架

基于多 Agent 协作的 AI 小说生成系统。7 个专职 Agent 模拟真实出版流程，从风格分析到最终润色，全自动完成小说创作。

## 架构设计

```
用户交互输入（故事灵感 + 风格偏好）
    ↓
StyleAdvisorAgent → 风格指南（题材探测 + 文风检测 + 写作规范 + 动态温度）
    ↓
用户确认写作参数（章数、字数、遗忘阈值）
    ↓
DirectorAgent  → 世界观 + 角色设定 + 三幕大纲
    ↓
PlotAgent      → 章节拆分 + 剧情要点 + 场景结构 + 张力管理
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
- **一致性追踪**：7 个追踪文件全程覆盖角色状态、时间线、伏笔、关系网络、场景地点
- **程序化检查**：禁用AI词自动替换、角色名别名修正、陈词滥调检测、句式分析
- **多角色协作**：7 个 Agent 各司其职，模拟风格顾问→导演→编剧→作家→审稿→编辑→修订顾问的完整出版流程
- **审核循环**：自动检测逻辑矛盾、角色崩坏等问题，打回重写直到通过（最多 2 轮）
- **章节修订**：对已完成章节提供交互式修订流程，修订顾问分析意见并生成修改思路
- **长上下文管理**：每章完成后生成摘要，写后续章节时传入压缩上下文，保持全局一致性
- **断点续写**：每个关键步骤自动保存进度，中断后可从任意阶段恢复
- **灵活配置**：每个 Agent 单独配置温度参数，支持风格指南动态覆盖
- **三层追踪更新**：L1 零成本字符串匹配 + L2 复用审核输出 + L3 独立 LLM 分析（每5章）

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

### 3. 开始创作

所有命令均为交互式，运行后程序会逐步引导输入：

```bash
# 创建新小说（引导输入：故事灵感、小说名称、风格偏好）
python3 main.py new

# 继续创作（列出已有小说，选择后继续）
python3 main.py continue

# 修订章节（列出小说和章节，选择后输入修改意见）
python3 main.py revise

# 查看所有小说进度
python3 main.py status
```

## 项目结构

```
XYR_test/
├── main.py                  # CLI 入口
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
│   ├── llm_client.py        # API 客户端封装（重试 + JSON解析 + Spinner）
│   ├── state_manager.py     # 状态持久化（JSON）
│   ├── context_manager.py   # 长上下文管理（摘要 + 压缩 + 追踪数据注入）
│   ├── tracker.py           # 追踪系统（7个JSON文件 + 忘却检测 + 自动修复）
│   └── pipeline.py          # 流程编排器
│
├── docs/                    # 文档
│   ├── flowchart.md         # 完整流程图（Mermaid）
│   └── parameters.md        # 参数参考表
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
- **自动修复**：角色名别名替换、禁用AI词替换（60+词条）
- **质量检查**：陈词滥调检测、连续长/短句告警、抽象名词标记
- **变更日志**：`tracking_changes.csv` 记录每章追踪数据变化

## 输出说明

创作完成后，`output/<小说名>/final/` 目录下包含：

- `chapter_01.txt` ~ `chapter_N.txt` — 每章最终版
- `<小说名>_全文.txt` — 全文合并版

## 注意事项

- 首次运行会联网调用 API，请确保网络畅通
- 20 章小说约需 1-2 小时完成（视 API 响应速度）
- 中途可随时 `Ctrl+C` 中断，进度自动保存
- 建议先用短篇（1-3章）跑一轮测试效果

## 致谢

本项目的追踪系统（角色状态、时间线、伏笔、关系网络、一致性校验、禁用词检查）融合自 [wordflowlab/novel-writer-skills](https://github.com/wordflowlab/novel-writer-skills) 的 `story-consistency-monitor` 技能：

```bash
npx skills add https://github.com/wordflowlab/novel-writer-skills --skill story-consistency-monitor
```

后续更新时可重新运行上述命令获取最新版本，对比差异后手动合入。
