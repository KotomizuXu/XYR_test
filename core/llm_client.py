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

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class Spinner:
    """Simple terminal spinner for long-running operations."""

    def __init__(self, message: str = "思考中"):
        self.message = message
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join()
        sys.stdout.write("\r" + " " * 60 + "\r")
        sys.stdout.flush()

    def _spin(self):
        i = 0
        start = time.time()
        while not self._stop.is_set():
            elapsed = int(time.time() - start)
            frame = SPINNER_FRAMES[i % len(SPINNER_FRAMES)]
            sys.stdout.write(f"\r  {frame} {self.message}... {elapsed}s")
            sys.stdout.flush()
            i += 1
            self._stop.wait(0.15)


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
        auth_token = os.environ.get(config["api"]["auth_token_env"], "")
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
        """Single-turn chat with retry logic. Retries from scratch on truncation."""
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
                    logger.warning(f"Response truncated at {len(text)} chars, retrying from scratch...")
                    continue

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

        logger.warning("Max retries reached, returning last response as-is")
        return text

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list:
        """Chat expecting JSON response. Auto-continues on truncation."""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        response = self._call_api(
            system_prompt, [{"role": "user", "content": user_message}],
            temp, tokens, "思考中",
        )
        text = response.content[0].text

        # Auto-continue truncated JSON
        if response.stop_reason == "max_tokens":
            logger.warning(f"JSON response truncated at {len(text)} chars, requesting continuation...")
            text = self._continue_json(system_prompt, user_message, text, temp, tokens)

        return parse_json(text)

    def _continue_json(self, system_prompt: str, user_message: str, existing_text: str, temperature: float, max_tokens: int, max_continuations: int = 3) -> str:
        """Continue a truncated JSON response."""
        messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": existing_text},
            {"role": "user", "content": "请继续输出，不要重复已输出的内容，直接从上文结尾处继续："},
        ]
        text = existing_text
        for _ in range(max_continuations):
            response = self._call_api(system_prompt, messages, temperature, max_tokens, "续写中")
            continuation = response.content[0].text
            text += continuation
            if response.stop_reason != "max_tokens":
                break
            logger.warning("Continuation still truncated, requesting more...")
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
        """Multi-turn conversation."""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        response = self._call_api(system_prompt, messages, temp, tokens, "思考中")
        return response.content[0].text
