"""Base agent class."""

import json
from abc import ABC, abstractmethod
from pathlib import Path

from core.llm_client import LLMClient

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
FRAGMENTS_DIR = PROMPTS_DIR / "fragments"

# 各 Agent 需要的 style_guide 字段（未列出的 Agent 保留全量）
STYLE_FIELDS = {
    "director": ["tone", "pacing", "plot", "character", "worldbuilding", "setting", "style_presets", "requirements"],
    "plotter": ["tone", "pacing", "plot", "character", "worldbuilding", "setting", "style_presets", "requirements"],
    "writer": ["tone", "pacing", "plot", "character", "worldbuilding", "setting", "style_presets", "requirements"],
    "reviewer": ["tone", "character", "worldbuilding", "review", "requirements", "setting"],
    "editor": ["tone", "pacing", "character", "editing", "style_presets", "requirements", "setting", "review"],
    "critic": ["character", "worldbuilding", "setting", "requirements"],
}


_AGENT_CONFIG_KEYS = {
    "styleadvisor": "style_advisor",
    "plot": "plotter",
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
        prompt = path.read_text(encoding="utf-8")
        # Inject constitution at the top
        constitution_path = PROMPTS_DIR / "constitution.md"
        if constitution_path.exists():
            constitution = constitution_path.read_text(encoding="utf-8")
            prompt = f"{prompt}\n\n## 创作准则（必须遵循）\n{constitution}"
        return prompt

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

    def _load_genre_fragment(self, genre: str | None) -> str:
        """按题材加载 prompts/fragments/<agent>/<genre>.txt 片段（可选）。

        Why: 为 F1 prompt 瘦身预留扩展点——未来可把 writer_system.txt 中的
        题材专项段落（悬疑/言情/奇幻/古风）拆到 fragments 子目录，按 genre 按需注入，
        减小通用 system prompt 体积。当前默认 fragments 目录为空，behavior 不变。
        How to apply: 子类若需要题材片段，调用此方法并将结果拼到 system prompt 末尾。
        """
        if not genre:
            return ""
        agent_dir = FRAGMENTS_DIR / self._agent_name()
        if not agent_dir.exists():
            return ""
        # 简单匹配：取 genre 关键词与 fragment 文件名子串匹配
        for f in agent_dir.glob("*.txt"):
            stem = f.stem
            if stem and stem in genre:
                try:
                    return f"\n\n## 题材专项指引（{stem}）\n" + f.read_text(encoding="utf-8")
                except OSError:
                    return ""
        return ""

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
        result = f"{prompt}\n\n## 风格指南\n请严格遵循以下风格指南进行创作：\n{style_text}"
        # 按题材注入专项片段（若存在）
        genre = (style_guide.get("setting", {}) or {}).get("genre", "")
        fragment = self._load_genre_fragment(genre)
        if fragment:
            result += fragment
        return result

    @abstractmethod
    def run(self, **kwargs) -> dict | str:
        ...
