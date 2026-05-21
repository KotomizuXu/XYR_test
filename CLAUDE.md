# XYR_test 项目协作约定（AI 必读）

## 第一条：先读 execution_workflow.md

接到任何代码变更需求时，**第一份要读的文档是 `docs/execution_workflow.md`**，再按它定义的 6 个阶段（对齐 → 拆任务 → 实现 → 验证 → 文档同步 → 回告）依次执行。

跳过文档同步阶段 = 任务未完成。

## 第二条：文档同步是硬性要求

每次代码变更**必须同步更新**以下文档（按 execution_workflow.md 第 5 章同步矩阵逐行判断）：

- `docs/parameters_and_changelog.md` ——参数 / 常量 / Bug fix 记录的权威来源
- `docs/system_reference.md` ——字段链路（生成→消费）参考手册
- `docs/flowchart.md` ——主流程 Mermaid 图（如适用）
- `README.md` ——架构 / 核心特性 / 变更日志
- `requirements.txt` ——依赖（双向同步：改了就更新 README 环境要求）
- `docs/verification_protocol.md` ——发现验证协议本身有盲区时

特殊情况：

- **CSV 字段映射** —— 新增 / 修改追踪字段必须同步 `_FIELD_MEANINGS`（tracker.py）+ `docs/parameters_and_changelog.md` 第九章 CSV 字段映射表（~130 条）
- **硬编码字典** —— `_BANNED_REPLACEMENTS` / `_CLICHE_PAIRS` / `_GENRE_STRICTNESS` 等改动有多处同步点，见 `docs/system_reference.md` 第十八章
- **CLI 渲染层** —— ui.py / name_generator.py 改动需同步 system_reference.md 第十九章 + parameters_and_changelog.md 第八章硬编码常量 + README 变更日志

## 第三条：Python 版本

- 固定使用 **Python 3.10**（`py -3.10`），不要使用 3.14
- 验证命令模板：`py -3.10 -c "import ast; [ast.parse(open(p,encoding='utf-8').read()) for p in [...]]; from xxx import yyy; print('ok')"`

## 第四条：CLI 输出走 core/ui.py

- 任何新增 `print` 必须改用 `core/ui.py` 的 `ui.info/warn/success/error/hint/section/banner/...`
- 输入仍走 `core/prompt_utils.py`（基于 prompt_toolkit）
- 输入/输出职责分离，不要混用
- Windows GBK 控制台兼容靠 `core/ui.py` 顶部的 `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`，不要绕过

## 第五条：禁止事项

- ❌ 改完代码直接报告"完成"，不跑任何验证
- ❌ 跳过文档同步承诺"下次一起更新"
- ❌ 在 bug 修复任务中"顺手"做风格清理 / 重构
- ❌ 写无用注释解释"代码做什么"（well-named code already does that）
- ❌ 在用户没批准的情况下做破坏性操作（git reset --hard / rm -rf / force push）

---

详细流程见 [`docs/execution_workflow.md`](docs/execution_workflow.md)。
