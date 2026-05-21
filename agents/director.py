"""Director agent: world-building, character design, and outline."""

import json
import logging

from agents.base import BaseAgent, PROMPTS_DIR

logger = logging.getLogger(__name__)


class DirectorAgent(BaseAgent):
    PROMPT_TEMPLATE = "director_system.txt"

    def __init__(self, llm, config):
        super().__init__(llm, config)
        self._world_prompt = self._load_named_prompt("director_world.txt")
        self._character_prompt = self._load_named_prompt("director_character.txt")
        self._location_prompt = self._load_named_prompt("director_location.txt")
        self._outline_prompt = self._load_named_prompt("director_outline.txt")

    @staticmethod
    def _load_named_prompt(name: str) -> str:
        path = PROMPTS_DIR / name
        prompt = path.read_text(encoding="utf-8")
        constitution_path = PROMPTS_DIR / "constitution.md"
        if constitution_path.exists():
            constitution = constitution_path.read_text(encoding="utf-8")
            prompt = f"{prompt}\n\n## 创作准则（必须遵循）\n{constitution}"
        return prompt

    def run(self, story_idea: str, num_chapters: int = 20, style_guide: dict | None = None) -> dict:
        """Legacy: generate all director output in one call."""
        user_msg = (
            f"故事灵感：{story_idea}\n\n"
            f"计划章节数：{num_chapters}章\n\n"
            f"请根据以上灵感，生成完整的小说设定。"
        )
        system = self.apply_style(self.system_prompt, style_guide)
        logger.info("Director: generating world and outline...")
        result = self.llm.chat_json(system, user_msg, temperature=self._temperature())
        if not isinstance(result, dict):
            logger.error(f"Director: expected dict from chat_json, got {type(result).__name__}")
            return {}
        logger.info(f"Director: done. Characters: {len(result.get('characters', []))}")
        return result

    def run_world(self, story_idea: str, num_chapters: int, style_guide: dict | None = None) -> dict:
        """Generate world settings + planned_cast + planned_locations."""
        system = self.apply_style(self._world_prompt, style_guide)
        user_msg = (
            f"故事灵感：{story_idea}\n\n"
            f"计划章节数：{num_chapters}章\n\n"
            f"请生成世界观设定（含 planned_cast 和 planned_locations）。只输出 JSON。"
        )
        logger.info("Director: generating world + plan...")
        result = self.llm.chat_json(system, user_msg, temperature=self._temperature())
        if not isinstance(result, dict):
            logger.error(f"Director.run_world: expected dict, got {type(result).__name__}")
            return {}
        logger.info(f"Director.run_world: done. "
                     f"Planned cast: {len(result.get('planned_cast', []))}, "
                     f"Planned locations: {len(result.get('planned_locations', []))}")
        return result

    def run_character(self, character_hint: dict, world_context_json: str,
                      style_guide: dict | None = None) -> dict:
        """Generate a single character card based on confirmed context."""
        system = self.apply_style(self._character_prompt, style_guide)
        name = character_hint.get("name", "")
        role = character_hint.get("role", "角色")
        brief = character_hint.get("brief", "")
        user_msg = (
            f"## 已确认的世界观和其他角色\n{world_context_json}\n\n"
            f"## 生成任务\n请为「{name}」（{role}）生成完整的角色卡。"
            f"{brief}\n\n只输出该角色的 JSON。"
        )
        logger.info(f"Director.run_character: generating {name} ({role})...")
        result = self.llm.chat_json(system, user_msg, temperature=self._temperature())
        if not isinstance(result, dict):
            logger.error(f"Director.run_character: expected dict, got {type(result).__name__}")
            return {}
        logger.info(f"Director.run_character: done. Name: {result.get('name', name)}")
        return result

    def run_location(self, location_hint: dict, world_context_json: str,
                     style_guide: dict | None = None) -> dict:
        """Generate a single location card based on confirmed context."""
        system = self.apply_style(self._location_prompt, style_guide)
        name = location_hint.get("name", "")
        loc_type = location_hint.get("type", "地点")
        brief = location_hint.get("brief", "")
        user_msg = (
            f"## 已确认的世界观、角色和已有地点\n{world_context_json}\n\n"
            f"## 生成任务\n请为「{name}」（{loc_type}）生成完整的地点卡。"
            f"{brief}\n\n只输出该地点的 JSON。"
        )
        logger.info(f"Director.run_location: generating {name} ({loc_type})...")
        result = self.llm.chat_json(system, user_msg, temperature=self._temperature())
        if not isinstance(result, dict):
            logger.error(f"Director.run_location: expected dict, got {type(result).__name__}")
            return {}
        logger.info(f"Director.run_location: done. Name: {result.get('name', name)}")
        return result

    def run_outline(self, story_idea: str, num_chapters: int,
                    world_context_json: str, style_guide: dict | None = None) -> dict:
        """Generate outline + style based on all confirmed data."""
        system = self.apply_style(self._outline_prompt, style_guide)
        user_msg = (
            f"故事灵感：{story_idea}\n\n"
            f"计划章节数：{num_chapters}章\n\n"
            f"## 已确认的世界观、角色和地点\n{world_context_json}\n\n"
            f"请根据以上全部设定，生成故事大纲（含 style 字段）。只输出 JSON。"
        )
        logger.info("Director.run_outline: generating outline...")
        result = self.llm.chat_json(system, user_msg, temperature=self._temperature())
        if not isinstance(result, dict):
            logger.error(f"Director.run_outline: expected dict, got {type(result).__name__}")
            return {}
        logger.info("Director.run_outline: done.")
        return result
