"""Base agent class."""

import json
from abc import ABC, abstractmethod
from pathlib import Path

from core.llm_client import LLMClient

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# 各 Agent 需要的 style_guide 字段（未列出的 Agent 保留全量）
STYLE_FIELDS = {
    "director": ["tone", "pacing", "plot", "character", "worldbuilding", "setting", "style_presets"],
    "plotter": ["tone", "pacing", "plot", "character", "worldbuilding", "setting", "style_presets"],
    "writer": ["tone", "pacing", "plot", "character", "worldbuilding", "setting", "style_presets", "requirements"],
    "reviewer": ["tone", "character", "worldbuilding", "review", "requirements", "setting"],
    "editor": ["tone", "pacing", "character", "editing", "style_presets", "requirements"],
    "critic": ["character", "worldbuilding", "setting", "requirements"],
}


_AGENT_CONFIG_KEYS = {
    "styleadvisor": "style_advisor",
    "plotagent": "plotter",
}

class BaseAgent(ABC):
    PROMPT_TEMPLATE: str

    def __init__(self, llm: LLMClient, config: dict):
        self.llm = llm
        self.config = config
        self.system_prompt = self._load_prompt()
        self._temperature_override = None

    def _load_prompt(self) -> str:
        path = PROMPTS_DIR / self.PROMPT_TEMPLATE
        return path.read_text(encoding="utf-8")

    def _agent_name(self) -> str:
        raw = self.__class__.__name__.replace("Agent", "").lower()
        return _AGENT_CONFIG_KEYS.get(raw, raw)

    def _agent_config(self) -> dict:
        return self.config.get("agents", {}).get(self._agent_name(), {})

    def _temperature(self) -> float:
        if self._temperature_override is not None:
            return self._temperature_override
        return self._agent_config().get("temperature", self.config["api"]["temperature"])

    def set_temperature(self, temp: float):
        self._temperature_override = temp

    def apply_style(self, prompt: str, style_guide: dict | None) -> str:
        if not style_guide:
            return prompt
        agent_name = self._agent_name()
        fields = STYLE_FIELDS.get(agent_name)
        if fields:
            filtered = {k: v for k, v in style_guide.items() if k in fields}
        else:
            filtered = style_guide
        style_text = json.dumps(filtered, ensure_ascii=False, indent=2)
        return f"{prompt}\n\n## 风格指南\n请严格遵循以下风格指南进行创作：\n{style_text}"

    @abstractmethod
    def run(self, **kwargs) -> dict | str:
        ...
