"""Base agent class."""

from abc import ABC, abstractmethod
from pathlib import Path

from core.llm_client import LLMClient

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


class BaseAgent(ABC):
    PROMPT_TEMPLATE: str

    def __init__(self, llm: LLMClient, config: dict):
        self.llm = llm
        self.config = config
        self.system_prompt = self._load_prompt()

    def _load_prompt(self) -> str:
        path = PROMPTS_DIR / self.PROMPT_TEMPLATE
        return path.read_text(encoding="utf-8")

    def _agent_config(self) -> dict:
        name = self.__class__.__name__.replace("Agent", "").lower()
        return self.config.get("agents", {}).get(name, {})

    def _temperature(self) -> float:
        return self._agent_config().get("temperature", self.config["api"]["temperature"])

    def apply_style(self, prompt: str, style_guide: dict | None) -> str:
        if not style_guide:
            return prompt
        import json
        style_text = json.dumps(style_guide, ensure_ascii=False, indent=2)
        return f"{prompt}\n\n## 风格指南\n请严格遵循以下风格指南进行创作：\n{style_text}"

    @abstractmethod
    def run(self, **kwargs) -> dict | str:
        ...
