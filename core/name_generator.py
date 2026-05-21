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

要求：
1. 只输出候选名字本身，每行一个，不带任何编号、不带任何标点（书名号也不要）、不带解释。
2. 每个名字长度不超过 10 个汉字（含字母数字）。
3. 名字应当贴合用户描述的题材和风格；如有风格提示，要紧扣风格特征。
4. 避免使用与他人著名作品相同的书名。
5. 不要输出任何空行、任何说明文字、任何标题。直接给出 N 个名字。
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
