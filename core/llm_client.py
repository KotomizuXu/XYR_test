"""Anthropic-compatible API client wrapper for GLM models."""

import json
import logging
import os
import re
import sys
import threading
import time

import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Token 估算系数（中文 1.5 token/字、英文/数字 0.3 token/字、JSON 结构开销取中位）
_CN_TOKEN_PER_CHAR = 1.5
_EN_TOKEN_PER_CHAR = 0.3


def estimate_tokens(text: str) -> int:
    """近似估算字符串的 token 数。误差目标 < 10%（GLM/Anthropic 中文分词差异）。

    Why: 调用前判断是否会超 max_tokens，触发主动压缩，避免 API 端硬截断。
    """
    if not text:
        return 0
    cn = len(re.findall(r'[一-鿿]', text))
    other = len(text) - cn
    return int(cn * _CN_TOKEN_PER_CHAR + other * _EN_TOKEN_PER_CHAR)


def estimate_messages_tokens(system_prompt: str, messages: list[dict]) -> int:
    """估算 system + 多轮 messages 的总 token，含每条消息约 4 token 的元数据开销。"""
    total = estimate_tokens(system_prompt)
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content) + 4
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "text" in block:
                    total += estimate_tokens(block["text"]) + 4
    return total

class Spinner:
    """No-op spinner. Progress is handled by the Web output layer."""

    def __init__(self, message: str = "思考中"):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def parse_json(text: str) -> dict | list:
    """Parse JSON from LLM response, handling markdown fences and common issues."""
    text = text.strip()
    # Strip markdown code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    text = text.strip()
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting JSON block (first { to last } or first [ to last ])
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start = text.find(open_char)
        end = text.rfind(close_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                # Try a heuristic repair for the most common LLM mistake:
                # missing closing quote + comma between two string fields, e.g.
                #   "summary": "...句号。 "previous_link": "..."
                # → insert ", before the orphan key.
                snippet = text[start : end + 1]
                repaired = _repair_unclosed_string(snippet)
                if repaired != snippet:
                    try:
                        return json.loads(repaired)
                    except json.JSONDecodeError:
                        pass
                continue
    raise ValueError(f"Failed to parse JSON from response: {text[:200]}...")


_UNCLOSED_STRING_RE = re.compile(r'([^,{\[\s])\s+("[A-Za-z_][\w]*"\s*:)')


def _repair_unclosed_string(text: str) -> str:
    """启发式修复 LLM 偶发的"字符串未闭合 + 漏逗号"模式：
    在两个字段之间出现 `xxx "key":` 但缺少闭合引号和逗号时，
    在 key 前补 `", `。仅修复明显是字段分隔位置的场景，避免破坏正常文本。
    """
    return _UNCLOSED_STRING_RE.sub(r'\1", \2', text)


class LLMClient:
    def __init__(self, config: dict):
        token_env = config["api"]["auth_token_env"]
        auth_token = os.environ.get(token_env, "")
        if not auth_token:
            msg = f"未找到 API Token。请设置环境变量 {token_env}。"
            try:
                from core.ui import error, hint
                error(msg)
                hint("cp .env.example .env 然后填入真实 Token（https://open.bigmodel.cn/ 申请）")
            except ImportError:
                print(f"错误：{msg}")
            sys.exit(1)
        self.client = anthropic.Anthropic(
            base_url=config["api"]["base_url"],
            api_key=auth_token,
            timeout=config["api"].get("timeout", 300),
        )
        self.model = config["api"]["model"]
        self.default_max_tokens = config["api"]["max_tokens"]
        self.default_temperature = config["api"]["temperature"]
        # 用于 _check_budget 主动预警：当 estimated_input + reserved_output > model_window 时 warn
        ctx_budget = config.get("context_budget", {}) or {}
        self.reserved_output_chars = ctx_budget.get("reserved_output_chars", 9000)
        self.continuation_tail_chars = ctx_budget.get("continuation_tail_chars", 2000)

    def _check_budget(self, system_prompt: str, messages: list[dict], label: str = "") -> int:
        """调用前估算输入 token 占用，若逼近 max_tokens 输出 warn（不阻塞，让 API 自行处理）。

        Why: max_tokens 是输入+输出共享预算，输入逼近上限会导致输出被截断。提前 warn
        便于排查，并触发上层（context_manager / writer）压缩策略。
        """
        est = estimate_messages_tokens(system_prompt, messages)
        # output reserve 估算（按 reserved_output_chars 中文计）
        output_reserve_tokens = int(self.reserved_output_chars * _CN_TOKEN_PER_CHAR)
        if est + output_reserve_tokens > self.default_max_tokens:
            logger.warning(
                f"[budget] {label} 估算输入 {est} token + 输出预留 {output_reserve_tokens} "
                f"> max_tokens {self.default_max_tokens}，可能截断；建议压缩上下文。"
            )
        return est

    def _call_api(self, system_prompt: str, messages: list[dict], temperature: float, max_tokens: int, label: str = "思考中") -> anthropic.types.Message:
        self._check_budget(system_prompt, messages, label=label)
        spinner = Spinner(label)
        spinner.start()
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system_prompt,
                messages=messages,
            )
            return response
        finally:
            spinner.stop()

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> str:
        """Single-turn chat. Auto-continues on truncation, retries on API errors."""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        for attempt in range(max_retries):
            try:
                response = self._call_api(
                    system_prompt, [{"role": "user", "content": user_message}],
                    temp, tokens, "思考中",
                )
                text = response.content[0].text

                if response.stop_reason == "max_tokens":
                    logger.warning(f"Response truncated at {len(text)} chars, requesting continuation...")
                    text = self._continue_text(system_prompt, user_message, text, temp, tokens)

                return text
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"API error (attempt {attempt+1}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
            except anthropic.APIStatusError as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"API error {e.status_code} (attempt {attempt+1}), retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

        raise RuntimeError("Unexpected end of retry loop")

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> dict | list:
        """Chat expecting JSON response. Auto-continues on truncation, retries on API errors,
        and retries on JSON parse failure (LLM occasionally emits malformed JSON like missing
        quotes/commas — re-ask with a stricter directive)."""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        current_user_msg = user_message
        last_parse_error: ValueError | None = None

        for attempt in range(max_retries):
            try:
                response = self._call_api(
                    system_prompt, [{"role": "user", "content": current_user_msg}],
                    temp, tokens, "思考中",
                )
                text = response.content[0].text

                if response.stop_reason == "max_tokens":
                    logger.warning(f"JSON response truncated at {len(text)} chars, requesting continuation...")
                    text = self._continue_json(system_prompt, current_user_msg, text, temp, tokens)

                try:
                    return parse_json(text)
                except ValueError as ve:
                    last_parse_error = ve
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"JSON parse failed (attempt {attempt+1}/{max_retries}): {str(ve)[:200]}; "
                            f"retrying with stricter directive..."
                        )
                        current_user_msg = (
                            f"{user_message}\n\n"
                            f"## 上次输出的 JSON 解析失败\n"
                            f"上次返回的内容含有语法错误（可能漏引号、漏逗号或字符串未闭合），错误片段：\n"
                            f"{text[:300]}...\n\n"
                            f"请重新输出**完整合法**的 JSON。规则：\n"
                            f"1. 所有字符串值必须以双引号闭合\n"
                            f"2. 对象的键值对之间必须有逗号\n"
                            f"3. 不要在 JSON 之外输出任何说明文字\n"
                            f"4. 不要使用 ``` 等代码块标记"
                        )
                        continue
                    raise
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"API error (attempt {attempt+1}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
            except anthropic.APIStatusError as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"API error {e.status_code} (attempt {attempt+1}), retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

        if last_parse_error is not None:
            raise last_parse_error
        raise RuntimeError("Unexpected end of retry loop")

    def _continue_json(self, system_prompt: str, user_message: str, existing_text: str, temperature: float, max_tokens: int, max_continuations: int = 3) -> str:
        """Continue a truncated JSON response by asking for a complete retry."""
        # JSON续写拼接会产生无效JSON，改为要求重新输出完整JSON
        retry_msg = f"{user_message}\n\n（注意：请输出完整的JSON，不要截断）"
        messages = [{"role": "user", "content": retry_msg}]
        for _ in range(max_continuations):
            response = self._call_api(system_prompt, messages, temperature, max_tokens, "重新生成中")
            text = response.content[0].text
            if response.stop_reason != "max_tokens":
                return text
            logger.warning("JSON response still truncated after retry")
        raise ValueError(
            f"JSON response truncated after {max_continuations} retries "
            f"({len(existing_text)} chars received). "
            f"Consider increasing max_tokens or reducing output complexity."
        )

    def _continue_text(self, system_prompt: str, user_message: str, existing_text: str, temperature: float, max_tokens: int, max_continuations: int = 3) -> str:
        """Continue a truncated text response.

        Why: 旧实现把 [user, assistant1, user("继续"), assistant2, user("继续"), ...] 无限累加，
        多轮续写会再次溢出 max_tokens。改为滑窗：每轮只传"原 user 摘要 + 当前已写尾部 + 继续指令"，
        避免上下文叠加。
        """
        tail_chars = self.continuation_tail_chars
        # 原 user 信息压缩为简短锚点（保留首尾 1000 字便于 LLM 知道任务边界）
        user_anchor = user_message
        if len(user_message) > 4000:
            user_anchor = user_message[:2000] + "\n...(中略)...\n" + user_message[-2000:]

        text = existing_text
        for _ in range(max_continuations):
            tail = text[-tail_chars:] if len(text) > tail_chars else text
            messages = [
                {"role": "user", "content": user_anchor},
                {"role": "assistant", "content": tail},
                {"role": "user", "content": "请直接从上文结尾处继续写下去，不要重复已写内容，不要回顾前文："},
            ]
            response = self._call_api(system_prompt, messages, temperature, max_tokens, "续写中")
            continuation = response.content[0].text
            text += continuation
            if response.stop_reason != "max_tokens":
                break
            logger.warning("Text continuation still truncated, requesting more...")
        return text

    def chat_with_history(
        self,
        system_prompt: str,
        messages: list[dict],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Multi-turn conversation. Auto-continues on truncation."""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        response = self._call_api(system_prompt, messages, temp, tokens, "思考中")
        text = response.content[0].text
        if response.stop_reason == "max_tokens":
            # Extract the last user message to use as context for continuation
            last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            text = self._continue_text(system_prompt, last_user, text, temp, tokens)
        return text
