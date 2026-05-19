"""Anthropic-compatible API client wrapper for GLM models."""

import json
import logging
import os
import re
import time

import anthropic
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


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

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 3,
    ) -> str:
        """Single-turn chat with retry logic."""
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else self.default_max_tokens

        for attempt in range(max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=tokens,
                    temperature=temp,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                )
                return response.content[0].text
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

    def chat_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict | list:
        """Chat expecting JSON response."""
        text = self.chat(system_prompt, user_message, temperature=temperature, max_tokens=max_tokens)
        return parse_json(text)

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

        response = self.client.messages.create(
            model=self.model,
            max_tokens=tokens,
            temperature=temp,
            system=system_prompt,
            messages=messages,
        )
        return response.content[0].text
