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
                continue
    raise ValueError(f"Failed to parse JSON from response: {text[:200]}...")


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

    def _call_api(self, system_prompt: str, messages: list[dict], temperature: float, max_tokens: int, label: str = "思考中") -> anthropic.types.Message:
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
                if e.status_code >= 500 and attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Server error {e.status_code}, retrying in {wait}s")
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
        """Chat expecting JSON response. Auto-continues on truncation, retries on API errors."""
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
                    logger.warning(f"JSON response truncated at {len(text)} chars, requesting continuation...")
                    text = self._continue_json(system_prompt, user_message, text, temp, tokens)

                return parse_json(text)
            except (anthropic.APIConnectionError, anthropic.RateLimitError) as e:
                if attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"API error (attempt {attempt+1}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise
            except anthropic.APIStatusError as e:
                if e.status_code >= 500 and attempt < max_retries - 1:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"Server error {e.status_code}, retrying in {wait}s")
                    time.sleep(wait)
                else:
                    raise

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
        """Continue a truncated text response."""
        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": existing_text},
            {"role": "user", "content": "请继续写，不要重复已写的内容，直接从上文结尾处继续："},
        ]
        text = existing_text
        for _ in range(max_continuations):
            response = self._call_api(system_prompt, messages, temperature, max_tokens, "续写中")
            continuation = response.content[0].text
            text += continuation
            if response.stop_reason != "max_tokens":
                break
            logger.warning("Text continuation still truncated, requesting more...")
            messages.append({"role": "assistant", "content": continuation})
            messages.append({"role": "user", "content": "继续："})
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
