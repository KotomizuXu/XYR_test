# 需求执行工作流（AI 必读）

> 本文档是 XYR_test 项目内每次代码变更的**强制执行流程**。
> AI 在接到任何需求时，**必须先读完本文档**，再按下方 6 个阶段顺序执行。
> 跳过任意阶段（尤其是"文档同步"）等同于交付未完工的任务。
>
> *最后更新：2026-05-21*

---

## 适用范围

只要满足下列任一条件，就必须走本流程：

- 用户提出新功能 / 修复 / 重构需求
- 修改了任意 `*.py` / `*.yaml` / `prompts/*.txt` / `requirements.txt`
- 新增或删除了模块、Agent、追踪文件、用户输入点、硬编码字典/常量
- 修改了 CLI 输出 / 输入 / 进度展示

**不适用**：纯查询、纯解释、纯审计（不改文件）的场景。

---

## 流程总览

```
1. 对齐 → 2. 规划 → 3. 实现 → 4. 验证 → 5. 文档同步 → 6. 回告
   ↓        ↓        ↓         ↓         ↓             ↓
  问清     任务拆    动手改    语法+    全链路同步    向用户报告
  范围     和锁定    代码      冒烟      6 类文档      变更与下一步
```

每个阶段都有明确的**入口条件 / 输出物 / 完工判据**，下面逐一展开。

---

## 阶段 1：对齐需求

**入口条件**：收到用户需求。

**动作**：
1. 如果用户的需求**有多种合理实现方式**，先用 `AskUserQuestion` 把关键决策抛回（语气：列方案 + 给推荐 + 说权衡，让用户拍板）。
2. 把需求转写成一句"我将要做什么 + 为什么"的内部目标。这一句要能对得上用户原话——对不上就再问。
3. 如果需求范围较大（≥3 个文件 或 ≥30 行改动），**进入 plan mode**（`EnterPlanMode`），把方案落到 `plans/*.md`，由用户 `ExitPlanMode` 批准后再动手。

**完工判据**：
- 用户的需求已经被你**用具体文件名 / 函数名 / 字段名**复述过一次
- 没有遗留的"我以为他想要 X，其实他想要 Y"的可能

**反例**：用户说"帮我把 CLI 美化一下"——错误做法是直接动手；正确做法是先 AskUserQuestion 问"覆盖范围（横幅/进度/全部）？""新功能（AI 起名/章节进度条/状态着色）？""输入顺序是否调整？"。

---

## 阶段 2：规划与任务拆分

**入口条件**：阶段 1 完成。

**动作**：
1. 用 `TaskCreate` 把工作拆成**可独立验证**的任务条目（典型粒度：1 个任务对应 1 个文件或 1 个完整子功能）。
2. 任务间用 `addBlockedBy` 标注依赖（例如"文档同步"必须 blockedBy"语法验证"）。
3. 在开始动手前，用 `TaskUpdate` 把第一个任务设为 `in_progress`。

**完工判据**：
- TaskList 里有≥2 个任务（除非真的只改一行）
- 每个任务的 subject 是动词开头的祈使句，看一眼就知道在干什么

**反例**：用一个"实现 Rich + AI 起名"的笼统任务包住所有工作 → 进度无法追踪，文档同步必然漏。

---

## 阶段 3：实现

**入口条件**：阶段 2 完成，第一个任务已 `in_progress`。

**动作**：
1. **先读再改**：编辑任何已有文件前必须先 `Read`（Edit 工具强制要求，也避免覆盖陌生改动）。
2. **优先 Edit，少用 Write**：除非是新建文件，否则不要整文件覆写。
3. **并行调用工具**：独立的读取 / 搜索请放进同一条消息的多个 tool call 中。
4. **不夹带私货**：不顺手做"代码清理"，不引入"未来可能用到"的抽象，不擅自给已有功能加防御。bug 修复就修 bug。
5. **不写无用注释**：只写非显而易见的 why（约束 / workaround / 反直觉行为）。
6. 每完成一个任务，立刻 `TaskUpdate → completed`，再把下一个设为 `in_progress`。

**完工判据**：
- 所有 TaskList 中的代码任务都 completed（文档同步任务还没做）
- 没有半成品文件、没有调试用的 print、没有注释掉的旧代码

**反例**：完成 Rich 渲染后顺手把 prompt_utils.py 也改了一遍 → 范围失控，回头解释不清。

---

## 阶段 4：验证（写完即测）

**入口条件**：阶段 3 全部代码任务完成。

**动作（按需选用，至少跑 ① 和 ②）**：

| 验证项 | 命令 / 工具 | 何时必跑 |
|--------|------------|---------|
| ① 语法 + 导入 | `python3 -c "import ast; [ast.parse(open(p,encoding='utf-8').read()) for p in [...]]; from xxx import yyy; print('ok')"` | 任何代码变更 |
| ② Web 启动冒烟 | `python3 web_main.py`（确认无导入错误） | 改了 pipeline.py / ui.py / prompt_utils.py |
| ③ 单测 / Repl 验证 | `python3 -c "from xxx import f; assert f(...) == ..."` | 改了纯函数（如 `_clean_candidate`、`_sanitize_novel_name`） |
| ④ 数据链路追溯 | 按 `docs/verification_protocol.md` 第二章相关项执行 | 改了 prompt schema / context_manager / tracker |

**完工判据**：
- ① 必须输出 `ok` 才能继续
- ② 必须不抛 ImportError
- 验证失败 → 回阶段 3 修复，**不要直接进入文档同步**

**反例**：改完代码直接报告"完成"，不跑任何验证。

---

## 阶段 5：文档同步（核心）

**入口条件**：阶段 4 所有验证通过。

> **这是本流程最关键的一步。** 历史上文档与代码失同步几乎全部源于跳过此阶段。

### 5.1 同步矩阵（强制执行）

按下表**逐行判断**——即使你觉得"这次变更不影响 X"，也必须显式回答 ✅同步 / ➖不适用，不能默认跳过。

| 触发条件 | 需要更新的文档 | 更新内容 |
|---------|--------------|---------|
| **任何代码变更** | `docs/parameters_and_changelog.md` 第十章 bug fix 记录 | 追加一行（编号、严重度、问题描述、修复位置） |
| **任何代码变更** | `README.md` 变更日志 | 追加日期 + 简述章节（参考既有章节风格） |
| 新增 / 修改 prompt schema 字段 | `docs/system_reference.md` 对应章节 + 章末"最后验证时间" | 更新字段链路表 |
| 新增 / 修改 prompt schema 字段 | `docs/parameters_and_changelog.md` 第六章 L1/L2/L3 追踪字段表 | 更新对应行 |
| `_FIELD_MEANINGS` 增删 | `docs/parameters_and_changelog.md` 第九章 CSV 字段映射 | 同步字段路径 → 中文含义对照表 |
| 新增 / 修改 tracking 字段（任意 6 个文件）| `docs/parameters_and_changelog.md` 第六章 + 第九章 | 同时更新链路表和 CSV 字段映射 |
| 新增 / 修改 config.yaml 参数 | `docs/parameters_and_changelog.md` 第一~三章对应配置表 | 更新参数行 |
| 新增 / 修改硬编码字典（_BANNED / _CLICHE / _GENRE 等）| `docs/parameters_and_changelog.md` 第七章 + `docs/system_reference.md` 第十八章 | 同步条目 + 检查多处 prompt 同步点 |
| 新增 / 修改主流程 / 数据流 | `docs/flowchart.md` | 更新对应 Mermaid 图 |
| 新增 Agent 或 Phase | `README.md` 架构图 + 核心特性 | 同步更新 |
| 新增 / 升级 Python 依赖 | `requirements.txt` + `README.md` 环境要求 | 双向同步 |
| 新增用户输入点 | `docs/system_reference.md` 第十七章用户输入校验清单 | 追加一行（位置 / 校验 / 风险） |
| 新增输出点（ui.* 函数） | `docs/system_reference.md` 第十九章 19.5 输出点全览 | 追加一行 |
| 修改输出层（ui.py / name_generator.py）| `docs/system_reference.md` 第十九章 + `README.md` 变更日志 | 两处同步 |
| 发现验证协议本身有盲区 | `docs/verification_protocol.md` | 补充或修正验证项 |
| 以上均不适用 | — | 在阶段 6 回告时显式注明"文档已是最新，无需同步" |

### 5.2 同步顺序（推荐）

1. **parameters_and_changelog.md** 第十章 bug fix（最先做，因为是事实记录）
2. **parameters_and_changelog.md** 其余章节（参数/字段/常量）
3. **system_reference.md**（字段链路、输入点、输出点）
4. **flowchart.md**（如适用）
5. **README.md** 变更日志（最后做，等其他文档定稿后总结）
6. **requirements.txt**（依赖变更时）

### 5.3 自评：变更是否暴露了文档结构盲区

每次同步完后，问一次：

- 本次变更有没有引入一个**现有文档章节都装不下的内容**？
- 如果有 → 是不是该新增一个章节？（例：2026-05-21 新增"第十九章 CLI 渲染层"）

如果是，先补章节再写内容，不要塞进不相关章节凑数。

**完工判据**：
- 同步矩阵每一行都被显式判断过（✅ / ➖）
- 没有"我以为不影响"的潜规则跳过

---

## 阶段 6：回告用户

**入口条件**：阶段 5 全部完成。

**动作**：
- 用 1-3 句话简述：**改了什么 / 验证结果 / 文档同步范围**
- 列出**用户下一步可做的动作**（如"建议跑 `py -3.10 main.py new` 实测""测完记得 rotate token"）
- 如果有遗留 / 取舍 / 已知风险，明确说出来（不要藏）

**模板**：
```
完成的工作：
1. 代码：<改了哪些文件 + 关键函数>
2. 验证：<跑了哪些命令 + 结果>
3. 文档同步：<更新了哪几份文档 + 哪些章节>

下一步建议：
- <用户可执行的命令或检查项>

提醒：<安全 / 权限 / 后续要做的事，如适用>
```

---

## 反模式黑名单

下列做法在本项目中**禁止**：

1. ❌ 改完代码直接报告"完成"，不跑任何验证
2. ❌ 跳过文档同步，承诺"下次一起更新"
3. ❌ 用一个笼统的 TaskCreate 包住所有工作，进度无法追踪
4. ❌ 在 bug 修复任务中"顺手"做风格清理 / 重构 / 抽象
5. ❌ 在代码中使用 print() 直接输出，不通过 `core/ui.py`
6. ❌ 新增依赖只改 requirements.txt 不改 README，或反之
7. ❌ 新增追踪字段只改 tracker.py 不同步 `_FIELD_MEANINGS` / parameters_and_changelog.md CSV 映射
8. ❌ 改 prompt schema 只改 prompt 不查 context_manager / 下游 Agent 是否消费
9. ❌ 添加注释解释"代码做什么"而非"为什么这么做"
10. ❌ 在用户没批准的情况下做破坏性操作（`git reset --hard`、`rm -rf`、force push）

---

## 速查卡片（粘墙用）

```
收到需求
  ↓
对齐：复述 + 必要时 AskUserQuestion / EnterPlanMode
  ↓
拆任务：TaskCreate（≥2 条），第一条设 in_progress
  ↓
实现：先 Read 再 Edit；不夹带；TaskUpdate 推进
  ↓
验证：① 语法导入 ② Web 启动冒烟（必跑）；改了字段链路加 ④
  ↓
文档同步：parameters → self_check → flowchart → README → requirements
  逐行判断同步矩阵，不跳行
  ↓
回告：3 段格式（变更/验证/下一步）
```

---

## 与其他文档的关系

| 文档 | 角色 | 何时引用 |
|------|------|---------|
| `docs/execution_execution_workflow.md`（本文件）| 流程纲领 | **接到需求时第一份读** |
| `docs/verification_protocol.md` | 28 项 AI 执行型验证清单 | 阶段 4 验证项 ⑤ 数据链路追溯时 |
| `docs/parameters_and_changelog.md` | 参数 / 常量 / bug fix 历史的权威来源 | 阶段 5 同步矩阵首要目标 |
| `docs/system_reference.md` | 字段链路（生成→消费）参考手册 | 阶段 3 改代码前查链路 / 阶段 5 同步 |
| `docs/flowchart.md` | 主流程 Mermaid 图 | 阶段 5 主流程有变时同步 |
| `README.md` | 对外说明 + 变更日志 | 阶段 5 收尾同步 |

> **冲突仲裁规则**：本文件（execution_workflow.md）规定**做事顺序**；verification_protocol.md 规定**怎么验证**；parameters_and_changelog.md / system_reference.md 是**事实底稿**。
> 流程问题以 execution_workflow.md 为准；验证项以 verification_protocol.md 为准；数据/参数以代码为准（文档与代码不符以代码为准，但必须立刻把文档同步过来）。
