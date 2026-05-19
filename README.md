<<<<<<< HEAD
# XYR_test
=======
# Novel Agent - AI 多角色协作小说写作框架

基于多 Agent 协作的 AI 小说生成系统。5 个专职 Agent 模拟真实出版流程，从世界观搭建到最终润色，全自动完成小说创作。

## 架构设计

```
用户输入(故事灵感)
    ↓
DirectorAgent  → 世界观 + 角色设定 + 三幕大纲
    ↓
PlotAgent      → 章节拆分 + 剧情要点 + 伏笔规划
    ↓
WriterAgent    → 撰写正文（3000-5000字/章）
    ⇅
ReviewerAgent  → 逻辑审核 + 一致性检查（不通过则打回重写）
    ↓
EditorAgent    → 文字润色 + 文风统一 + 章节衔接
    ↓
输出 TXT 文件（单章 + 全文合并）
```

## 核心特性

- **多角色协作**：5 个 Agent 各司其职，模拟导演→编剧→作家→审稿→编辑的完整出版流程
- **审核循环**：自动检测逻辑矛盾、角色崩坏等问题，打回重写直到通过（最多 2 轮）
- **长上下文管理**：每章完成后生成摘要，写后续章节时传入压缩上下文，保持全局一致性
- **断点续写**：每个关键步骤自动保存进度，中断后可从任意阶段恢复
- **灵活配置**：每个 Agent 单独配置温度参数，适配不同任务需求

## 环境要求

- Python 3.10
- GLM-5.1 API（通过 Anthropic 兼容接口调用）

## 快速开始

### 1. 安装依赖

```bash
py -3.10 -m pip install -r requirements.txt
```

### 2. 配置 API

复制 `.env` 模板并填入你的 API Token：

```bash
# .env 中的 token 需要替换为你自己的真实 token
GLM_API_TOKEN=your_token_here
```

如需修改模型或接口地址，编辑 `config.yaml`：

```yaml
api:
  base_url: "https://open.bigmodel.cn/api/anthropic"
  model: "glm-5.1"
```

### 3. 开始创作

```bash
# 新建小说（交互式输入灵感）
py -3.10 main.py new

# 指定灵感、名称和章节数
py -3.10 main.py new --idea "一个程序员穿越到修仙世界" --name "代码修仙" --chapters 20

# 断点续写
py -3.10 main.py continue --name "代码修仙"

# 查看所有小说进度
py -3.10 main.py status
```

## 项目结构

```
novel_agent/
├── main.py                  # CLI 入口
├── config.yaml              # 全局配置（API参数 + 小说参数 + Agent温度）
├── .env                     # API Token
├── requirements.txt
│
├── agents/                  # Agent 实现
│   ├── base.py              # BaseAgent 抽象基类
│   ├── director.py          # 导演：世界观 + 角色 + 大纲
│   ├── plotter.py           # 编剧：章节拆分 + 剧情规划
│   ├── writer.py            # 作家：撰写正文 + 根据反馈重写
│   ├── reviewer.py          # 审核：逻辑一致性 + 角色合理性
│   └── editor.py            # 编辑：文字润色 + 章节衔接
│
├── prompts/                 # System Prompt 模板（可自由修改）
│   ├── director_system.txt
│   ├── plotter_system.txt
│   ├── writer_system.txt
│   ├── reviewer_system.txt
│   └── editor_system.txt
│
├── core/                    # 基础设施
│   ├── llm_client.py        # API 客户端封装（重试 + JSON解析）
│   ├── state_manager.py     # 状态持久化（JSON）
│   ├── context_manager.py   # 长上下文管理（摘要 + 压缩）
│   └── pipeline.py          # 流程编排器
│
└── output/<小说名>/         # 输出目录（自动创建）
    ├── novel_state.json     # 全局状态（用于断点续写）
    ├── world.json           # 世界观设定
    ├── outline.json         # 故事大纲
    ├── chapters.json        # 章节规划
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
| `api.max_tokens` | 单次请求最大 token | 8192 |
| `novel.default_chapters` | 默认章节数 | 20 |
| `novel.words_per_chapter.min` | 每章最少字数 | 3000 |
| `novel.words_per_chapter.max` | 每章最多字数 | 5000 |
| `novel.review_max_retries` | 审核不通过最大重写次数 | 2 |
| `agents.writer.temperature` | 作家温度（越高越有创意） | 0.85 |
| `agents.reviewer.temperature` | 审核温度（越低越严谨） | 0.3 |

## 自定义 Prompt

所有 Agent 的 system prompt 存放在 `prompts/` 目录下，是纯文本文件，可以直接编辑来调整写作风格、审核标准等。Writer prompt 中支持以下占位符：

- `{words_min}` / `{words_max}` — 每章字数范围
- `{tone_guidance}` — 文风指导
- `{narrative_perspective}` — 叙事视角

## 输出说明

创作完成后，`output/<小说名>/final/` 目录下包含：

- `chapter_01.txt` ~ `chapter_N.txt` — 每章最终版
- `<小说名>_全文.txt` — 全文合并版

## 注意事项

- 首次运行会联网调用 API，请确保网络畅通
- 20 章小说约需 1-2 小时完成（视 API 响应速度）
- 中途可随时 `Ctrl+C` 中断，进度自动保存
- 建议先用 `--chapters 3` 跑一轮测试效果
>>>>>>> ebe8233 (feat: init novel agent - AI multi-role novel writing framework)
