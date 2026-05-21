"""AI 小说名候选生成

基于故事火花（idea）+ 可选风格描述，让 LLM 推 N 个候选小说名。
LLM 失败时返回空 list，由调用方降级到手输。
"""

from __future__ import annotations

import logging
import re

from core.llm_client import LLMClient

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一位文学作品的命名专家。你的任务是根据用户提供的故事火花，给出富有意境、契合题材、容易记忆的小说名。

## 题材-风格映射（G1）

| 题材 | 风格特征 | 常用结构 | 示例 |
|------|----------|----------|------|
| 悬疑/推理 | 悬念感、未解之谜 | 谜/局/消失的X/第N个X | 《消失的第十一天》《第七个证人》 |
| 言情/甜宠 | 诗意/温暖感 | 意象/四字短语/对比结构 | 《半夏微凉》《你是迟来的欢喜》 |
| 奇幻/仙侠 | 宏大/古风感 | 录/传/纪/诀/歌 | 《九州风雷录》《沧溟诀》 |
| 科幻 | 未来感/哲思感 | 技术意象/悖论结构 | 《深空回响》《最后一个问题》 |
| 历史 | 厚重感/时代感 | 年代/地名/事件锚点 | 《长安十二时辰》《大明王朝》 |
| 都市/现实 | 接地气/生活化 | 口语化表达/反差结构 | 《都挺好》《人间烟火》 |
| 惊悚/恐怖 | 压迫感/禁忌感 | 暗示/未完成句式 | 《别回头》《十三楼》 |

跨题材（如"悬疑+言情"）优先匹配核心冲突对应的题材风格，同时融入次要题材元素。

## 五种标题创作技巧（G2，每个候选用不同的技巧）

1. **核心冲突提炼法**：从故事核心冲突中提炼关键词组合，标题直指核心矛盾。例《棋局未终》《造物者的困境》
2. **主角命名法**：以主角的特征/身份为核心，避免直接用全名。例《深夜掌勺人》《放逐者归来》
3. **意象隐喻法**：用核心意象暗示主题，留有解读空间。例《雾中灯塔》《镜中之镜》
4. **反差法**：制造认知反差，矛盾元素并置。例《盛世的裂缝》《小人物的大日子》
5. **悬念留白法**：指向具体事物但不解释。例《第三封信》《那年冬天的约定》

## 输出要求

1. 只输出候选名字本身，每行一个，不带任何编号、不带任何标点（书名号也不要）、不带解释。
2. 每个名字长度 2-8 字为主，特殊题材可到 10 字，绝不超过 10 字。
3. 名字应当贴合用户描述的题材和风格；如有风格提示，要紧扣风格特征。
4. N 个候选**必须使用不同的技巧**（不能 3 个都是意象隐喻法）。
5. 不要输出任何空行、任何说明文字、任何标题。直接给出 N 个名字。

## AI 套路黑名单（G3，绝对禁用）

- ❌ "XX 之道""XX 的觉醒""XX 纪元""XX 崛起""XX 之巅""XX 之主" 等 AI 味浓重的结构
- ❌ "命运""选择""真相""使命""归途" 等过于笼统的单/双字标题
- ❌ 直接剧透故事结局或核心转折的标题
- ❌ "震惊""竟然""不敢相信"等网络标题党风格
- ❌ 与知名作品标题雷同（如《三体》《盗墓笔记》《诛仙》等）
"""


_INVALID_CHARS = set('\\/:*?"<>|')


def _clean_candidate(line: str) -> str | None:
    """从 LLM 输出的一行里清洗出候选名。失败返回 None。"""
    if not line:
        return None
    s = line.strip()
    if not s:
        return None
    # 去掉常见编号前缀：1. / 1、 / 1) / （1） / 一、 / - / *
    s = re.sub(r'^[\(\（]?\d+[\)\）\.\、\:\：\s]+', '', s)
    s = re.sub(r'^[一二三四五六七八九十]+[\、\.\:\：\s]+', '', s)
    s = re.sub(r'^[\-\*\·\•]\s*', '', s)
    # 去掉书名号
    s = s.strip('《》「」"\'""''')
    s = s.strip()
    if not s:
        return None
    if len(s) > 12:
        return None
    if any(c in _INVALID_CHARS for c in s):
        return None
    if s.endswith('.') or s.endswith(' '):
        return None
    return s


def suggest_novel_names(llm: LLMClient, idea: str,
                         style: str | None = None, n: int = 3) -> list[str]:
    """请求 LLM 推 n 个候选小说名。

    Returns:
        候选名列表（去重、长度 ≤ n）。LLM 异常或全部不合法 → 空 list。
    """
    if not idea or not idea.strip():
        return []

    user_parts = [
        "## 故事火花",
        idea.strip(),
    ]
    if style:
        user_parts.append("")
        user_parts.append("## 风格偏好")
        user_parts.append(style.strip())
    user_parts.append("")
    user_parts.append(f"请给出 {n} 个候选小说名，每行一个。")
    user_msg = "\n".join(user_parts)

    try:
        raw = llm.chat(_SYSTEM_PROMPT, user_msg, temperature=0.9)
    except Exception as e:
        logger.warning(f"AI 起名调用失败：{e}")
        return []

    candidates: list[str] = []
    seen: set[str] = set()
    for line in raw.splitlines():
        cleaned = _clean_candidate(line)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        candidates.append(cleaned)
        if len(candidates) >= n:
            break
    return candidates
