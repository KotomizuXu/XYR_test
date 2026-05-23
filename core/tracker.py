"""Tracking system for story consistency, forgotten elements, and timeline management."""

import csv
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from .state_manager import atomic_write_json

logger = logging.getLogger(__name__)

# Default thresholds for forgotten elements detection
DEFAULT_THRESHOLDS = {
    "character": 10,
    "plotline": 12,
    "foreshadowing": 20,
}

# 字段路径 → 中文语义映射（前缀匹配，按长度降序排列以优先匹配更具体的路径）
_FIELD_MEANINGS = [
    # --- character_state ---
    ("character_state.novel", "小说名称"),
    ("character_state.lastUpdated", "最后更新时间"),
    ("character_state.protagonist.name", "主角姓名"),
    ("character_state.protagonist.currentStatus.alive", "主角是否存活"),
    ("character_state.protagonist.currentStatus.health", "主角健康状况"),
    ("character_state.protagonist.currentStatus.mentalState", "主角精神状态"),
    ("character_state.protagonist.currentStatus.location", "主角当前位置"),
    ("character_state.protagonist.currentStatus.chapter", "主角最后出现章节"),
    ("character_state.protagonist.currentStatus.age", "主角年龄"),
    ("character_state.protagonist.currentStatus.position", "主角身份/职位"),
    ("character_state.protagonist.currentStatus.possessions", "主角持有物品"),
    ("character_state.protagonist.currentStatus.skills", "主角技能列表"),
    ("character_state.protagonist.currentStatus.knowledge", "主角已知信息"),
    ("character_state.protagonist.development.arc", "主角成长弧线"),
    ("character_state.protagonist.development.milestones", "主角成长里程碑"),
    ("character_state.protagonist.development.currentPhase", "主角当前成长阶段"),
    ("character_state.protagonist.development.nextGoal", "主角下一目标"),
    ("character_state.supportingCharacters", "配角数据"),
    (".role", "角色定位（如反派/导师）"),
    (".importance", "角色重要性（high/medium）"),
    (".status.alive", "角色是否存活"),
    (".status.lastSeen.chapter", "角色最后出现章节"),
    (".status.lastSeen.location", "角色最后出现位置"),
    (".status.currentLocation", "角色当前位置"),
    (".status.occupation", "角色职业"),
    (".arc.planned", "角色预设成长弧线"),
    (".arc.current", "角色当前成长状态"),
    (".secrets", "角色秘密"),
    (".motivations", "角色动机"),
    ("character_state.characterGroups.active", "活跃角色列表"),
    ("character_state.characterGroups.inactive", "不活跃角色列表"),
    ("character_state.characterGroups.deceased", "已死亡角色列表"),
    ("character_state.appearanceTracking", "角色出场追踪记录"),
    (".significance", "出场重要性"),
    ("character_state.consistency.physicalTraits", "外貌一致性（角色→外貌描述）"),
    ("character_state.consistency.personalityTraits", "性格一致性（角色→性格特征）"),
    ("character_state.consistency.speechPatterns", "语言风格一致性（角色→说话习惯）"),
    ("character_state.consistency.warnings", "一致性警告列表"),
    ("character_state.psychology", "角色心理深度"),
    (".false_belief", "角色错误信念"),
    (".want", "角色表面渴望"),
    (".need", "角色深层需求"),
    (".ghost", "角色心魔/旧伤"),
    # --- timeline ---
    ("timeline.novel", "小说名称"),
    ("timeline.lastUpdated", "最后更新时间"),
    ("timeline.storyTime.start", "故事起始时间"),
    ("timeline.storyTime.current", "故事当前时间"),
    ("timeline.storyTime.end", "故事结束时间"),
    ("timeline.storyTime.format", "时间标记方式"),
    ("timeline.events", "故事事件时间线"),
    (".chapter", "所在章节"),
    (".date", "事件日期"),
    (".event", "事件标题"),
    (".duration", "持续时长"),
    (".participants", "参与者"),
    ("timeline.parallelEvents.timepoints", "并行事件时间点"),
    ("timeline.historicalContext.events", "历史背景事件"),
    ("timeline.timeLogic.travelTimes.routes", "旅行时间（路线→耗时）"),
    ("timeline.timeLogic.constraints", "时间逻辑约束"),
    ("timeline.anomalies.issues", "时间线异常/矛盾"),
    # --- plot_tracker ---
    ("plot_tracker.novel", "小说名称"),
    ("plot_tracker.lastUpdated", "最后更新时间"),
    ("plot_tracker.currentState.chapter", "当前进度章节"),
    ("plot_tracker.currentState.volume", "当前卷数"),
    ("plot_tracker.currentState.mainPlotStage", "主线阶段（开端/发展/高潮/结局）"),
    ("plot_tracker.currentState.location", "当前场景地点"),
    ("plot_tracker.currentState.timepoint", "当前时间点"),
    ("plot_tracker.plotlines.main.name", "主线名称"),
    ("plot_tracker.plotlines.main.description", "主线描述"),
    ("plot_tracker.plotlines.main.status", "主线状态（active/completed）"),
    ("plot_tracker.plotlines.main.currentNode", "主线当前剧情节点"),
    ("plot_tracker.plotlines.main.completedNodes", "已完成剧情节点"),
    ("plot_tracker.plotlines.main.upcomingNodes", "即将到来的剧情节点"),
    ("plot_tracker.plotlines.main.plannedClimax.chapter", "计划高潮章节"),
    ("plot_tracker.plotlines.main.plannedClimax.description", "计划高潮描述"),
    ("plot_tracker.plotlines.subplots", "支线剧情"),
    (".name", "名称"),
    (".description", "描述"),
    (".status", "状态"),
    ("plot_tracker.foreshadowing", "伏笔列表"),
    (".content", "伏笔内容"),
    (".planted.chapter", "伏笔埋设章节"),
    (".planted.description", "伏笔埋设描述"),
    (".hints", "伏笔提示/呼应"),
    (".plannedReveal.chapter", "计划揭示章节"),
    (".plannedReveal.description", "计划揭示描述"),
    (".importance", "重要性"),
    ("plot_tracker.conflicts.active", "进行中的冲突"),
    ("plot_tracker.conflicts.resolved", "已解决的冲突"),
    ("plot_tracker.conflicts.upcoming", "即将到来的冲突"),
    ("plot_tracker.checkpoints.volumeEnd", "卷末检查点"),
    ("plot_tracker.checkpoints.majorEvents", "重大事件记录"),
    ("plot_tracker.notes.plotHoles", "剧情漏洞记录"),
    ("plot_tracker.notes.inconsistencies", "剧情不一致记录"),
    ("plot_tracker.notes.reminders", "剧情提醒"),
    # --- relationships ---
    ("relationships.novel", "小说名称"),
    ("relationships.lastUpdated", "最后更新时间"),
    ("relationships.characters", "角色关系数据"),
    (".relationships.allies", "盟友"),
    (".relationships.enemies", "敌人"),
    (".relationships.romantic", "恋爱关系"),
    (".relationships.family", "家人"),
    (".relationships.mentors", "师徒关系"),
    (".relationships.neutral", "中立关系"),
    (".relationships.unknown", "未知关系"),
    (".dynamicRelations", "动态关系变化记录"),
    ("relationships.factions", "势力/阵营"),
    (".leader", "势力领袖"),
    (".members", "势力成员"),
    (".goals", "势力目标"),
    (".alliedWith", "盟友势力"),
    (".opposedTo", "敌对势力"),
    ("relationships.relationshipMatrix.matrix", "角色关系矩阵"),
    ("relationships.conflicts.personal", "个人冲突"),
    ("relationships.conflicts.factional", "阵营冲突"),
    ("relationships.conflicts.ideological", "理念冲突"),
    ("relationships.history", "关系变化历史"),
    ("relationships.predictions.likely", "高概率关系变化预测"),
    ("relationships.predictions.possible", "可能的关系变化预测"),
    # --- validation_rules ---
    ("validation_rules.version", "规则版本"),
    ("validation_rules.characters.protagonist.name", "主角姓名（验证用）"),
    ("validation_rules.characters.protagonist.aliases", "主角别名"),
    ("validation_rules.characters.protagonist.forbidden", "主角禁用称呼"),
    ("validation_rules.characters.protagonist.traits", "主角特征（外貌/能力/年龄）"),
    ("validation_rules.characters.supporting", "配角验证规则"),
    (".aliases", "别名"),
    (".addresses_to", "称呼方式"),
    ("validation_rules.relationships.fixed_addresses.rules", "固定称呼规则"),
    ("validation_rules.relationships.forbidden_addresses.rules", "禁用称呼规则"),
    ("validation_rules.validation_tasks.character_consistency", "角色一致性检查"),
    ("validation_rules.validation_tasks.character_consistency.checks", "检查项（姓名/特征/行为）"),
    ("validation_rules.validation_tasks.relationship_validation", "关系验证检查"),
    ("validation_rules.validation_tasks.relationship_validation.checks", "检查项（称呼/发展/交互）"),
    ("validation_rules.validation_tasks.world_rules", "世界规则检查"),
    ("validation_rules.validation_tasks.world_rules.checks", "检查项（力量体系/地理/时间线）"),
    ("validation_rules.validation_tasks", "验证任务开关"),
    (".enabled", "是否启用"),
    ("validation_rules.auto_fix.character_names", "自动修复角色名称"),
    ("validation_rules.auto_fix.character_names.confidence_threshold", "自动修复置信度阈值"),
    ("validation_rules.auto_fix.addresses", "自动修复称呼"),
    ("validation_rules.auto_fix.simple_typos", "自动修复简单拼写错误"),
    ("validation_rules.auto_fix.complex_issues", "自动修复复杂问题"),
    ("validation_rules.common_errors.character_substitution", "常见角色混淆错误"),
    ("validation_rules.common_errors.address_mistakes", "常见称呼错误"),
    ("validation_rules.validation_levels.quick", "快速验证级别"),
    ("validation_rules.validation_levels.quick.checks", "快速验证检查项"),
    ("validation_rules.validation_levels.quick.time_estimate", "预计耗时"),
    ("validation_rules.validation_levels.standard", "标准验证级别"),
    ("validation_rules.validation_levels.standard.checks", "标准验证检查项"),
    ("validation_rules.validation_levels.standard.time_estimate", "预计耗时"),
    ("validation_rules.validation_levels.deep", "深度验证级别"),
    ("validation_rules.validation_levels.deep.checks", "深度验证检查项"),
    ("validation_rules.validation_levels.deep.time_estimate", "预计耗时"),
    ("validation_rules.active_validation_level", "当前激活的验证级别（quick/standard/deep）"),
    # --- locations ---
    ("locations.novel", "小说名称"),
    ("locations.lastUpdated", "最后更新时间"),
    ("locations.locations", "场景地点列表"),
    (".type", "地点类型"),
    (".scale", "地点规模"),
    (".position", "地理位置"),
    (".first_appearance", "首次出现"),
    (".five_senses", "场景五感描述"),
    (".function", "地点功能/用途"),
    (".atmosphere", "场景氛围"),
    (".related_characters", "关联角色"),
    (".events", "地点相关事件"),
    ("locations.scene_atmosphere_guide", "场景氛围写作指南"),
]


def _lookup_field_meaning(field_path: str) -> str:
    """根据字段路径查找中文含义，优先匹配最长前缀。"""
    best = ""
    best_len = 0
    for prefix, meaning in _FIELD_MEANINGS:
        if field_path.endswith(prefix) or prefix in field_path:
            if len(prefix) > best_len:
                best = meaning
                best_len = len(prefix)
    return best


class Tracker:
    def __init__(self, novel_dir: Path, novel_name: str = ""):
        self.novel_name = novel_name
        self.tracking_dir = novel_dir / "tracking"
        self.tracking_dir.mkdir(parents=True, exist_ok=True)

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    # --- File I/O ---

    def _read_json(self, name: str) -> dict:
        path = self.tracking_dir / name
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return {}

    def _write_json(self, name: str, data: dict) -> None:
        atomic_write_json(self.tracking_dir / name, data)

    # --- Config ---

    def _get_thresholds(self) -> dict:
        config = self._read_json("config.json")
        thresholds = dict(DEFAULT_THRESHOLDS)
        if "thresholds" in config:
            thresholds.update(config["thresholds"])
        return thresholds

    def set_threshold(self, element_type: str, value: int) -> None:
        config = self._read_json("config.json")
        if "thresholds" not in config:
            config["thresholds"] = {}
        config["thresholds"][element_type] = value
        self._write_json("config.json", config)

    def retire_element(self, element_type: str, name: str) -> None:
        config = self._read_json("config.json")
        if "retired" not in config:
            config["retired"] = {}
        if element_type not in config["retired"]:
            config["retired"][element_type] = []
        if name not in config["retired"][element_type]:
            config["retired"][element_type].append(name)
        self._write_json("config.json", config)

    def _is_retired(self, element_type: str, name: str) -> bool:
        config = self._read_json("config.json")
        return name in config.get("retired", {}).get(element_type, [])

    def _get_strictness(self) -> str:
        config = self._read_json("config.json")
        return config.get("strictness", "strict")

    def set_strictness(self, level: str) -> None:
        config = self._read_json("config.json")
        config["strictness"] = level
        self._write_json("config.json", config)

    # --- Init: called after Director completes ---

    def init_tracking(self, world_data: dict, outline: dict, chapter_plans: list[dict], missing: list[str] | None = None) -> None:
        """初始化追踪文件。
        missing=None 时仅初始化磁盘上不存在的文件（保护已有数据）；
        显式传入列表则只初始化列表中的文件，list 中允许包含 config.json。
        """
        init_map = {
            "character_state.json": lambda: self._init_character_state(world_data),
            "timeline.json": lambda: self._init_timeline(chapter_plans, world_data),
            "plot_tracker.json": lambda: self._init_plot_tracker(outline, chapter_plans),
            "relationships.json": lambda: self._init_relationships(world_data),
            "validation_rules.json": lambda: self._init_validation_rules(world_data),
            "locations.json": lambda: self._init_locations(world_data),
            "config.json": self._init_config,
        }
        if missing is None:
            targets = [f for f in init_map if not self._read_json(f)]
        else:
            targets = [f for f in missing if f in init_map]

        for fname in targets:
            init_map[fname]()
        logger.info(f"Tracking system initialized: {targets or 'no-op'}")

    def _parse_characters(self, world_data: dict) -> tuple[list[dict], list[dict], list[dict]]:
        """Parse characters from world_data, return (all_chars, protagonists, supporting)."""
        characters = world_data.get("characters", [])
        if isinstance(characters, dict):
            characters = list(characters.values()) if characters else []
        characters = [c for c in characters if isinstance(c, dict)]
        # Fallback: treat first character as protagonist if none have role field
        protagonists = [c for c in characters if c.get("role", "") in ("主角", "主人公", "protagonist")]
        if not protagonists and characters:
            protagonists = [characters[0]]
        supporting = [c for c in characters if c not in protagonists]
        return characters, protagonists, supporting

    def _init_character_state(self, world_data: dict) -> None:
        all_chars, protagonists, supporting = self._parse_characters(world_data)
        now = self._now()

        # Protagonist
        protag_data = {}
        if protagonists:
            p = protagonists[0]
            name = p.get("name", "")
            protag_data = {
                "name": name,
                "currentStatus": {
                    "alive": True,
                    "health": "良好",
                    "mentalState": "正常",
                    "location": "",
                    "chapter": 0,
                    "age": p.get("age"),
                    "position": p.get("position", p.get("occupation", "")),
                    "possessions": [],
                    "skills": [],
                    "knowledge": [],
                },
                "development": {
                    "arc": p.get("arc", p.get("personality", "")),
                    "milestones": [],
                    "currentPhase": "起点",
                    "nextGoal": "",
                },
            }

        # Supporting characters
        supporting_data = {}
        for ch in supporting:
            name = ch.get("name", "")
            if not name:
                continue
            importance = "high" if ch.get("role", "") in ("重要配角", "反派", "导师") else "medium"
            supporting_data[name] = {
                "role": ch.get("role", ""),
                "importance": importance,
                "status": {
                    "alive": True,
                    "lastSeen": {"chapter": None, "location": ""},
                    "currentLocation": "",
                    "occupation": ch.get("occupation", ""),
                },
                "arc": {
                    "planned": ch.get("arc", ""),
                    "current": "",
                },
                "secrets": [],
                "motivations": [],
            }

        all_names = [c.get("name", "") for c in all_chars if c.get("name")]
        psychology = {}
        for ch in all_chars:
            ch_name = ch.get("name", "")
            if ch_name and any(ch.get(k) for k in ("false_belief", "want", "need", "ghost")):
                psychology[ch_name] = {
                    "false_belief": ch.get("false_belief", ""),
                    "want": ch.get("want", ""),
                    "need": ch.get("need", ""),
                    "ghost": ch.get("ghost", ""),
                }
        state = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "protagonist": protag_data,
            "supportingCharacters": supporting_data,
            "characterGroups": {
                "active": all_names,
                "inactive": [],
                "deceased": [],
            },
            "appearanceTracking": [],
            "consistency": {
                "physicalTraits": {},
                "personalityTraits": {},
                "speechPatterns": {},
                "warnings": [],
            },
            "psychology": psychology,
        }

        # Pre-populate consistency from world_data
        if protagonists:
            p = protagonists[0]
            if p.get("appearance"):
                state["consistency"]["physicalTraits"][p.get("name", "主角")] = p["appearance"]
            if p.get("personality"):
                state["consistency"]["personalityTraits"][p.get("name", "主角")] = p["personality"]
            if p.get("voice"):
                state["consistency"]["speechPatterns"][p.get("name", "主角")] = p["voice"]
        for ch in supporting:
            name = ch.get("name", "")
            if not name:
                continue
            if ch.get("appearance"):
                state["consistency"]["physicalTraits"][name] = ch["appearance"]
            if ch.get("personality"):
                state["consistency"]["personalityTraits"][name] = ch["personality"]
            if ch.get("voice"):
                state["consistency"]["speechPatterns"][name] = ch["voice"]

        self._write_json("character_state.json", state)

    def _init_timeline(self, chapter_plans: list[dict], world_data: dict | None = None) -> None:
        now = self._now()
        events = []
        start_time = ""
        for plan in chapter_plans:
            time_info = plan.get("time", plan.get("story_time", ""))
            events.append({
                "chapter": plan.get("chapter_number", 0),
                "date": str(time_info) if time_info else "",
                "event": plan.get("title", ""),
                "duration": plan.get("duration", ""),
                "participants": [],
            })
            if not start_time and time_info:
                start_time = str(time_info)

        timeline = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "storyTime": {
                "start": start_time,
                "current": start_time,
                "end": "",
                "format": "故事内时间标记方式",
            },
            "events": events,
            "parallelEvents": {"timepoints": {}},
            "historicalContext": {"events": []},
            "timeLogic": {
                "travelTimes": {"routes": self._extract_travel_routes(world_data)},
                "constraints": [],
            },
            "anomalies": {"issues": []},
        }
        self._write_json("timeline.json", timeline)

    @staticmethod
    def _extract_travel_routes(world_data: dict | None) -> dict:
        routes = {}
        if world_data:
            for r in world_data.get("geography", {}).get("travel_routes", []):
                key = f"{r.get('from', '?')}→{r.get('to', '?')}"
                routes[key] = r.get("distance", "")
        return routes

    def _init_plot_tracker(self, outline: dict, chapter_plans: list[dict]) -> None:
        now = self._now()

        # Main plot from outline
        main_plot = {
            "name": outline.get("theme", ""),
            "description": "",
            "status": "active",
            "currentNode": "",
            "completedNodes": [],
            "upcomingNodes": [],
            "plannedClimax": {"chapter": None, "description": ""},
        }

        # Foreshadowing from chapter plans
        foreshadowing = []
        fs_idx = 1
        for plan in chapter_plans:
            for fs in plan.get("foreshadowing", []):
                if isinstance(fs, dict):
                    content = fs.get("content", str(fs))
                    visibility = fs.get("visibility", "subtle")
                    planned_reveal = fs.get("planned_reveal")
                else:
                    content = str(fs)
                    visibility = "subtle"
                    planned_reveal = None
                reveal_chapter = None
                if planned_reveal:
                    try:
                        reveal_chapter = int(str(planned_reveal))
                    except (ValueError, TypeError):
                        pass
                foreshadowing.append({
                    "id": f"fs_{fs_idx:03d}",
                    "content": content,
                    "visibility": visibility,
                    "planted": {"chapter": plan.get("chapter_number"), "description": ""},
                    "hints": [],
                    "plannedReveal": {"chapter": reveal_chapter, "description": ""},
                    "status": "active",
                    "importance": "medium",
                })
                fs_idx += 1

        tracker = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "currentState": {
                "chapter": 0,
                "volume": 1,
                "mainPlotStage": "开端",
                "location": "",
                "timepoint": "",
            },
            "plotlines": {
                "main": main_plot,
                "subplots": [],
            },
            "foreshadowing": foreshadowing,
            "conflicts": {
                "active": [],
                "resolved": [],
                "upcoming": [],
            },
            "checkpoints": {
                "volumeEnd": [],
                "majorEvents": [],
            },
            "notes": {
                "plotHoles": [],
                "inconsistencies": [],
                "reminders": [],
            },
        }
        self._write_json("plot_tracker.json", tracker)

    def advance_volume(self, chapter_num: int, volumes: list) -> None:
        """检查当前章节是否到达卷末边界，更新 plot_tracker 中的卷信息。"""
        from core.state_manager import VolumeDef
        tracker = self._read_json("plot_tracker.json")
        for vol in volumes:
            if chapter_num == vol.end_chapter:
                tracker["checkpoints"]["volumeEnd"].append({
                    "volume": vol.number,
                    "title": vol.title,
                    "chapter": chapter_num,
                })
                next_vol = vol.number + 1
                tracker["currentState"]["volume"] = next_vol
                self._write_json("plot_tracker.json", tracker)
                return

    def _init_relationships(self, world_data: dict) -> None:
        all_chars, _, _ = self._parse_characters(world_data)
        now = self._now()

        # Keywords for classifying relationship types
        _ENEMY_KEYWORDS = ["敌人", "仇人", "对手", "反派", "对立", "死对头", "宿敌"]
        _ROMANTIC_KEYWORDS = ["爱", "恋", "情", "妻", "夫", "男友", "女友", "暗恋", "CP", "暧昧", "情人", "爱人"]
        _FAMILY_KEYWORDS = ["父", "母", "兄", "弟", "姐", "妹", "家人", "亲人", "父亲", "母亲", "哥哥", "弟弟", "姐姐", "妹妹", "儿子", "女儿", "叔", "伯", "姑", "姨", "舅"]
        _MENTOR_KEYWORDS = ["师", "导师", "师父", "老师", "前辈", "教导", "传授"]

        characters = {}
        for ch in all_chars:
            name = ch.get("name", "")
            if not name:
                continue

            rel_text = ch.get("relationships", "")
            allies, enemies, family, romantic, mentors = [], [], [], [], []

            if isinstance(rel_text, str) and rel_text:
                # Split relationship text by common delimiters to get per-person segments
                segments = re.split(r'[，,；;。.\n]', rel_text)
                for other in all_chars:
                    other_name = other.get("name", "")
                    if not other_name or other_name == name:
                        continue
                    # Find segments that mention this specific character
                    matching = [s for s in segments if other_name in s]
                    if not matching:
                        continue
                    context = " ".join(matching).lower()
                    if any(kw in context for kw in _ENEMY_KEYWORDS):
                        enemies.append(other_name)
                    elif any(kw in context for kw in _ROMANTIC_KEYWORDS):
                        romantic.append(other_name)
                    elif any(kw in context for kw in _FAMILY_KEYWORDS):
                        family.append(other_name)
                    elif any(kw in context for kw in _MENTOR_KEYWORDS):
                        mentors.append(other_name)
                    else:
                        allies.append(other_name)

            characters[name] = {
                "relationships": {
                    "allies": allies,
                    "enemies": enemies,
                    "romantic": romantic,
                    "family": family,
                    "mentors": mentors,
                    "neutral": [],
                    "unknown": [],
                },
                "dynamicRelations": [],
            }

        # Extract factions from world_data
        factions = {}
        for faction in world_data.get("factions", []):
            if isinstance(faction, dict) and faction.get("name"):
                factions[faction["name"]] = {
                    "description": faction.get("purpose", faction.get("nature", "")),
                    "leader": faction.get("key_figures", [""])[0] if faction.get("key_figures") else "",
                    "members": faction.get("key_figures", []),
                    "goals": faction.get("purpose", ""),
                    "alliedWith": [],
                    "opposedTo": [],
                    "status": "active",
                }

        relationships = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "characters": characters,
            "factions": factions,
            "relationshipMatrix": {"matrix": {}},
            "conflicts": {
                "personal": [],
                "factional": [],
                "ideological": [],
            },
            "history": [],
            "predictions": {
                "likely": [],
                "possible": [],
            },
        }
        self._write_json("relationships.json", relationships)

    def _init_validation_rules(self, world_data: dict) -> None:
        all_chars, protagonists, supporting = self._parse_characters(world_data)

        # Protagonist rules
        protag_name = ""
        protag_aliases = []
        protag_forbidden = ["主角", "男主", "女主"]
        if protagonists:
            p = protagonists[0]
            protag_name = p.get("name", "")
            protag_aliases = p.get("aliases", [])
            protag_forbidden.extend([protag_name + "（错误写法）"])

        # Supporting rules
        supporting_rules = {}
        for ch in supporting:
            name = ch.get("name", "")
            if not name:
                continue
            supporting_rules[name] = {
                "aliases": ch.get("aliases", []),
                "addresses_to": {},
            }

        # Pre-populate protagonist traits from world_data
        protag_traits = {}
        if protagonists:
            p = protagonists[0]
            if p.get("appearance"):
                protag_traits["appearance"] = p["appearance"]
            if p.get("abilities"):
                protag_traits["abilities"] = p["abilities"] if isinstance(p["abilities"], list) else [p["abilities"]]
            if p.get("age"):
                protag_traits["age"] = p["age"]

        # Generate character_substitution cross-references from aliases
        char_subs = []
        for ch in all_chars:
            name = ch.get("name", "")
            aliases = ch.get("aliases", [])
            if name and aliases:
                for alias in aliases:
                    if alias and alias != name:
                        char_subs.append({"wrong": alias, "correct": name})

        rules = {
            "version": "1.0",
            "characters": {
                "protagonist": {
                    "name": protag_name,
                    "aliases": protag_aliases,
                    "forbidden": protag_forbidden,
                    "traits": protag_traits,
                },
                "supporting": supporting_rules,
            },
            "relationships": {
                "fixed_addresses": {"rules": {}},
                "forbidden_addresses": {"rules": {}},
            },
            "validation_tasks": {
                "character_consistency": {
                    "enabled": True,
                    "checks": ["name_consistency", "trait_consistency", "behavior_consistency"],
                },
                "relationship_validation": {
                    "enabled": True,
                    "checks": ["address_accuracy", "relationship_development", "interaction_logic"],
                },
                "world_rules": {
                    "enabled": True,
                    "checks": ["power_system", "geography", "timeline"],
                },
            },
            "auto_fix": {
                "character_names": {
                    "enabled": True,
                    "confidence_threshold": 0.9,
                },
                "addresses": {
                    "enabled": True,
                    "confidence_threshold": 0.85,
                },
                "simple_typos": {
                    "enabled": True,
                },
                "complex_issues": {
                    "enabled": False,
                },
            },
            "common_errors": {
                "character_substitution": char_subs,
                "address_mistakes": [],
            },
            "validation_levels": {
                "quick": {
                    "checks": ["character_names", "basic_addresses"],
                    "time_estimate": "几秒钟",
                },
                "standard": {
                    "checks": ["character_consistency", "relationship_validation"],
                    "time_estimate": "1-2分钟",
                },
                "deep": {
                    "checks": ["all"],
                    "time_estimate": "5-10分钟",
                },
            },
        }
        self._write_json("validation_rules.json", rules)

    def _init_locations(self, world_data: dict) -> None:
        """Initialize location tracking from world_data.locations."""
        now = self._now()
        locations_data = world_data.get("locations", [])
        locations = []
        for loc in locations_data:
            if isinstance(loc, dict) and loc.get("name"):
                locations.append({
                    "name": loc.get("name", ""),
                    "type": loc.get("type", ""),
                    "scale": loc.get("scale", ""),
                    "position": loc.get("position", ""),
                    "first_appearance": loc.get("first_appearance", ""),
                    "five_senses": loc.get("five_senses", {}),
                    "function": loc.get("function", ""),
                    "atmosphere": loc.get("atmosphere", ""),
                    "related_characters": loc.get("related_characters", []),
                    "events": [],
                })
        location_data = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "locations": locations,
            "scene_atmosphere_guide": {
                "欢快": {"用词": "明亮、温暖、生机", "重点": "阳光、笑声、色彩"},
                "紧张": {"用词": "阴暗、压抑、不安", "重点": "阴影、寂静、细节"},
                "神秘": {"用词": "朦胧、诡异、未知", "重点": "雾气、光影、声响"},
                "浪漫": {"用词": "柔和、温馨、梦幻", "重点": "月光、花香、细语"},
            },
        }
        self._write_json("locations.json", location_data)

    def _init_config(self) -> None:
        existing = self._read_json("config.json")
        config = {
            "thresholds": dict(DEFAULT_THRESHOLDS),
            "strictness": existing.get("strictness", "strict"),
            "retired": {"characters": [], "plotlines": [], "foreshadowing": []},
            "disabled_checks": existing.get("disabled_checks", []),
        }
        if existing.get("thresholds"):
            config["thresholds"].update(existing["thresholds"])
        self._write_json("config.json", config)

    # --- Snapshot & CSV change log ---

    _TRACKING_FILES = [
        "character_state.json", "timeline.json", "plot_tracker.json",
        "relationships.json", "validation_rules.json", "locations.json",
    ]

    def snapshot(self) -> dict[str, str]:
        """Flatten all tracking JSONs into {dotted.path: serialized_value}."""
        flat = {}
        for fname in self._TRACKING_FILES:
            data = self._read_json(fname)
            prefix = fname.replace(".json", "")
            self._flatten(data, prefix, flat)
        return flat

    @staticmethod
    def _flatten(obj, prefix: str, out: dict) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                Tracker._flatten(v, f"{prefix}.{k}", out)
        elif isinstance(obj, list):
            # For lists, store length as summary and individual items by index
            out[prefix] = f"[{len(obj)}项]"
            for i, item in enumerate(obj):
                Tracker._flatten(item, f"{prefix}[{i}]", out)
        else:
            out[prefix] = str(obj) if obj is not None else ""

    def log_changes_csv(self, chapter_num: int, before: dict[str, str], after: dict[str, str], source: str = "") -> None:
        """Compare two snapshots and append changed fields to tracking_changes.csv."""
        csv_path = self.tracking_dir / "tracking_changes.csv"
        all_keys = sorted(set(before.keys()) | set(after.keys()))

        rows = []
        for key in all_keys:
            old_val = before.get(key, "")
            new_val = after.get(key, "")
            if old_val != new_val:
                # New field
                if not old_val:
                    change = new_val
                # Deleted field
                elif not new_val:
                    change = f"{old_val} → (删除)"
                # Changed
                else:
                    change = f"{old_val} → {new_val}"
                rows.append({
                    "章节": chapter_num,
                    "字段路径": key,
                    "含义": _lookup_field_meaning(key),
                    "变化": change,
                    "来源": source,
                })

        if not rows:
            return

        write_header = not csv_path.exists()
        with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["章节", "字段路径", "含义", "变化", "来源"])
            if write_header:
                writer.writeheader()
            writer.writerows(rows)

    # --- Update: called after each chapter is written ---

    def update_tracking(self, chapter_num: int, chapter_text: str, chapter_plan: dict, review: dict | None = None) -> dict:
        now = self._now()
        report = {}

        # Get all character names for appearance tracking
        char_state = self._read_json("character_state.json")
        all_names = list(char_state.get("supportingCharacters", {}).keys())
        protag_name = char_state.get("protagonist", {}).get("name", "")
        if protag_name:
            all_names.append(protag_name)

        # Update character last-seen and build appearance record
        appearances = []
        updated_chars = []
        plot_points_str = str(chapter_plan.get("plot_points", []))
        for name in all_names:
            if name in chapter_text:
                # Update supporting character lastSeen
                if name in char_state.get("supportingCharacters", {}):
                    char_state["supportingCharacters"][name]["status"]["lastSeen"] = {
                        "chapter": chapter_num,
                        "location": "",
                    }
                # Update protagonist chapter
                if name == protag_name:
                    char_state["protagonist"]["currentStatus"]["chapter"] = chapter_num

                updated_chars.append(name)
                sig = "重要" if name in plot_points_str else ""
                appearances.append({
                    "character": name,
                    "role": "主角" if name == protag_name else "配角",
                    "significance": sig,
                })

        # Append appearance tracking（同章只记一次）
        appearance_list = char_state.setdefault("appearanceTracking", [])
        if not any(e.get("chapter") == chapter_num for e in appearance_list):
            appearance_list.append({
                "chapter": chapter_num,
                "appearances": appearances,
            })
        report["characters_updated"] = updated_chars

        # Build bidirectional dynamicRelations for co-occurring characters
        if len(updated_chars) >= 2:
            relationships = self._read_json("relationships.json")
            pair_key = " 与 ".join(sorted(updated_chars[:6]))
            existing_dynamic = relationships.get("dynamicRelations", [])
            already_logged = any(
                d.get("chapter") == chapter_num and " 与 ".join(sorted(d.get("characters", []))) == pair_key
                for d in existing_dynamic
            )
            if not already_logged:
                existing_dynamic.append({
                    "characters": sorted(updated_chars[:6]),
                    "change": f"同场出现（第{chapter_num}章）",
                    "chapter": chapter_num,
                })
                relationships["dynamicRelations"] = existing_dynamic
                relationships["lastUpdated"] = now
                self._write_json("relationships.json", relationships)

        # --- L1.3: chapter_plan string matching updates ---

        # Update plot_tracker
        plot_tracker = self._read_json("plot_tracker.json")
        plot_tracker["currentState"]["chapter"] = chapter_num
        title = chapter_plan.get("title", "")

        # Update currentState location/timepoint/mainPlotStage from chapter_plan
        location_info = chapter_plan.get("location", "")
        if location_info:
            plot_tracker["currentState"]["location"] = str(location_info)
        time_info = chapter_plan.get("time", chapter_plan.get("story_time", ""))
        if time_info:
            plot_tracker["currentState"]["timepoint"] = str(time_info)
        act = chapter_plan.get("act", "")
        if act:
            act_map = {"第一幕": "开端", "第二幕": "发展", "第三幕": "高潮"}
            plot_tracker["currentState"]["mainPlotStage"] = act_map.get(str(act), str(act))

        # Track major events (high tension chapters)（同章只记一次）
        tension = chapter_plan.get("tension_level", "")
        if tension == "high" or tension == "高潮":
            major_events = plot_tracker.setdefault("checkpoints", {}).setdefault("majorEvents", [])
            if not any(e.get("chapter") == chapter_num for e in major_events):
                major_events.append({
                    "chapter": chapter_num,
                    "event": title or f"第{chapter_num}章高潮",
                })

        # Update currentNode based on chapter title（completedNodes 去重）
        if title:
            plot_tracker["plotlines"]["main"]["currentNode"] = title
            completed = plot_tracker["plotlines"]["main"].setdefault("completedNodes", [])
            if title not in completed:
                completed.append(title)
        # Extract subplot progress from plan's active_plotlines
        for line in chapter_plan.get("active_plotlines", []):
            line_str = str(line)
            for subplot in plot_tracker.get("plotlines", {}).get("subplots", []):
                if subplot.get("name", "") in line_str:
                    subplot["currentNode"] = title
                    subplot["lastUpdated"] = chapter_num
        # Mark foreshadowing items planted in this chapter
        for fs in plot_tracker.get("foreshadowing", []):
            planted_ch = fs.get("planted", {})
            if isinstance(planted_ch, dict) and planted_ch.get("chapter") == chapter_num:
                fs["planted"] = {"chapter": chapter_num, "description": f"第{chapter_num}章埋设"}
                fs["status"] = "planted"
        plot_tracker["lastUpdated"] = now
        self._write_json("plot_tracker.json", plot_tracker)

        # Update timeline: storyTime.current from plan
        timeline = self._read_json("timeline.json")
        for event in timeline.get("events", []):
            if event.get("chapter") == chapter_num:
                event["event"] = title or event.get("event", "")
                event["participants"] = updated_chars
                if time_info:
                    event["date"] = str(time_info)
                    timeline["storyTime"]["current"] = str(time_info)
                event["duration"] = chapter_plan.get("duration", "")
        timeline["lastUpdated"] = now
        self._write_json("timeline.json", timeline)

        # Update location tracking if plan has location info
        loc_data = self._read_json("locations.json")
        if location_info and loc_data.get("locations"):
            for loc in loc_data["locations"]:
                if loc.get("name") and loc["name"] in str(location_info):
                    loc_events = loc.setdefault("events", [])
                    if not any(e.get("chapter") == chapter_num for e in loc_events):
                        loc_events.append({
                            "chapter": chapter_num,
                            "event": title,
                            "characters": updated_chars[:5],
                        })
            loc_data["lastUpdated"] = now
            self._write_json("locations.json", loc_data)

        # Update protagonist state from chapter plan (reuse char_state, no second read)
        protag = char_state.get("protagonist", {})
        if protag.get("name"):
            if location_info:
                protag["currentStatus"]["location"] = str(location_info)
            for point in chapter_plan.get("plot_points", []):
                pt = str(point)
                truncated = pt[:50]
                if "学会" in pt or "获得" in pt or "领悟" in pt or "掌握" in pt:
                    skills = protag["currentStatus"].setdefault("skills", [])
                    if truncated not in skills:
                        skills.append(truncated)
                if "发现" in pt or "得知" in pt or "知道" in pt or "意识到" in pt:
                    knowledge = protag["currentStatus"].setdefault("knowledge", [])
                    if truncated not in knowledge:
                        knowledge.append(truncated)
            if "性格" in chapter_text or "人设" in chapter_text:
                char_state.setdefault("consistency", {}).setdefault("warnings", []).append(
                    f"第{chapter_num}章：出现显式性格描述，建议检查是否符合已建立的性格设定"
                )
        char_state["lastUpdated"] = now

        # Prune unbounded arrays to prevent file bloat
        appearance_list = char_state.get("appearanceTracking", [])
        if len(appearance_list) > 50:
            char_state["appearanceTracking"] = appearance_list[-50:]
        warnings = char_state.get("consistency", {}).get("warnings", [])
        if len(warnings) > 30:
            char_state["consistency"]["warnings"] = warnings[-30:]

        self._write_json("character_state.json", char_state)

        # --- L1.1: Consume reviewer output ---
        if review:
            self._consume_review(chapter_num, review)

        logger.info(f"Tracking updated for chapter {chapter_num}")
        return report

    def _consume_review(self, chapter_num: int, review: dict) -> None:
        """Extract data from reviewer's existing output into tracking fields."""
        consistency = review.get("consistency_checks", {})
        now = self._now()

        # --- Character issues ---
        char_state = self._read_json("character_state.json")
        char_changed = False
        consistency_block = char_state.setdefault("consistency", {})

        for issue in consistency.get("character_issues", []):
            consistency_block.setdefault("warnings", []).append(f"第{chapter_num}章 角色问题：{issue}")
            char_changed = True

        for issue in consistency.get("physical_traits_issues", []):
            consistency_block.setdefault("physicalTraits", {})[f"ch{chapter_num}"] = issue
            char_changed = True

        for issue in consistency.get("personality_issues", []):
            consistency_block.setdefault("personalityTraits", {})[f"ch{chapter_num}"] = issue
            char_changed = True

        for issue in consistency.get("knowledge_state_issues", []):
            consistency_block.setdefault("warnings", []).append(f"第{chapter_num}章 知识/状态问题：{issue}")
            char_changed = True

        if char_changed:
            char_state["lastUpdated"] = now
            self._write_json("character_state.json", char_state)

        # --- Plot tracker (world issues + issue-typed entries) ---
        plot_tracker = self._read_json("plot_tracker.json")
        plot_changed = False
        notes = plot_tracker.setdefault("notes", {})

        for issue in consistency.get("world_issues", []):
            notes.setdefault("plotHoles", []).append(f"第{chapter_num}章：{issue}")
            notes.setdefault("inconsistencies", []).append(f"第{chapter_num}章 世界观：{issue}")
            plot_changed = True

        # --- Timeline issues (collect first, write once) ---
        timeline = self._read_json("timeline.json")
        timeline_changed = False

        for issue in consistency.get("timeline_issues", []):
            timeline.setdefault("anomalies", {}).setdefault("issues", []).append(
                f"第{chapter_num}章：{issue}"
            )
            timeline_changed = True

        if timeline_changed:
            timeline["lastUpdated"] = now
            self._write_json("timeline.json", timeline)

        # --- Issues by type → relationships + plot_tracker ---
        relationships = self._read_json("relationships.json")
        rel_changed = False

        for issue in review.get("issues", []):
            issue_type = issue.get("type", "")
            desc = issue.get("description", "")
            entry = f"第{chapter_num}章：{desc}"
            if issue_type == "character":
                relationships.setdefault("conflicts", {}).setdefault("personal", []).append(entry)
                rel_changed = True
            elif issue_type == "worldbuilding":
                notes.setdefault("inconsistencies", []).append(entry)
                plot_changed = True

        if plot_changed:
            plot_tracker["lastUpdated"] = now
            self._write_json("plot_tracker.json", plot_tracker)

        if rel_changed:
            relationships["lastUpdated"] = now
            self._write_json("relationships.json", relationships)

        # --- Auto-fix suggestions → validation_rules ---
        rules = self._read_json("validation_rules.json")
        rules_changed = False

        for fix in review.get("auto_fix_suggestions", []):
            orig = fix.get("original", "")
            suggested = fix.get("suggested", "")
            fix_type = fix.get("type", "")
            if orig and suggested:
                target = "character_substitution" if "character" in fix_type else "address_mistakes"
                rules.setdefault("common_errors", {}).setdefault(target, []).append({
                    "wrong": orig,
                    "correct": suggested,
                    "chapter": chapter_num,
                })
                rules_changed = True

        if rules_changed:
            # Prune common_errors arrays
            for target in ("character_substitution", "address_mistakes"):
                arr = rules.get("common_errors", {}).get(target, [])
                if len(arr) > 30:
                    rules["common_errors"][target] = arr[-30:]
            self._write_json("validation_rules.json", rules)

        # Prune plot_tracker notes arrays
        if plot_changed or notes.get("plotHoles") or notes.get("inconsistencies"):
            for key in ("plotHoles", "inconsistencies"):
                arr = notes.get(key, [])
                if len(arr) > 30:
                    notes[key] = arr[-30:]
            if plot_changed:
                plot_tracker["lastUpdated"] = now
                self._write_json("plot_tracker.json", plot_tracker)

    # --- Forgotten elements check ---

    def check_forgotten(self, current_chapter: int) -> dict:
        thresholds = self._get_thresholds()
        forgotten = {"characters": [], "plotlines": [], "foreshadowing": []}

        # Characters not seen for too long
        char_state = self._read_json("character_state.json")

        # Check protagonist
        protag = char_state.get("protagonist", {})
        protag_name = protag.get("name", "")
        protag_ch = protag.get("currentStatus", {}).get("chapter") or 0
        if protag_name and protag_ch > 0 and (current_chapter - protag_ch) >= thresholds["character"]:
            forgotten["characters"].append({
                "name": protag_name,
                "role": "主角",
                "last_seen": protag_ch,
                "chapters_absent": current_chapter - protag_ch,
            })

        # Check supporting characters
        for name, data in char_state.get("supportingCharacters", {}).items():
            if self._is_retired("characters", name):
                continue
            importance = data.get("importance", "medium")
            if importance == "low":
                continue
            last_seen = data.get("status", {}).get("lastSeen", {}).get("chapter") or 0
            if last_seen > 0 and (current_chapter - last_seen) >= thresholds["character"]:
                forgotten["characters"].append({
                    "name": name,
                    "role": data.get("role", ""),
                    "last_seen": last_seen,
                    "chapters_absent": current_chapter - last_seen,
                })

        # Stale plotlines
        plot_tracker = self._read_json("plot_tracker.json")
        for subplot in plot_tracker.get("plotlines", {}).get("subplots", []):
            if self._is_retired("plotlines", subplot.get("name", "")):
                continue
            if subplot.get("status") in ("completed", "abandoned"):
                continue
            last_node = subplot.get("currentNode", "")
            if not last_node:
                forgotten["plotlines"].append({
                    "name": subplot.get("name", ""),
                    "status": subplot.get("status", ""),
                    "description": subplot.get("description", ""),
                })

        # Stale foreshadowing
        for fs in plot_tracker.get("foreshadowing", []):
            fs_id = fs.get("id", "")
            fs_content = fs.get("content", "")
            if self._is_retired("foreshadowing", fs_id) or self._is_retired("foreshadowing", fs_content):
                continue
            planted = fs.get("planted", {})
            planted_ch = planted.get("chapter") if isinstance(planted, dict) else planted
            if planted_ch and fs.get("status") == "planted":
                if (current_chapter - planted_ch) >= thresholds["foreshadowing"]:
                    forgotten["foreshadowing"].append({
                        "id": fs.get("id", ""),
                        "content": fs.get("content", ""),
                        "planted_chapter": planted_ch,
                        "chapters_since": current_chapter - planted_ch,
                    })

        has_issues = bool(forgotten["characters"] or forgotten["plotlines"] or forgotten["foreshadowing"])
        if has_issues:
            logger.info(f"Forgotten elements detected: {forgotten}")
        return forgotten if has_issues else {}

    # --- Consistency score calculation ---

    def calculate_consistency_score(self, review: dict) -> int:
        """Calculate consistency score from review issues.
        Formula: start at 100, note=-2, warning=-5, major=-15, min=0.
        """
        score = 100
        for issue in review.get("issues", []):
            severity = issue.get("severity", "")
            if severity == "note":
                score -= 2
            elif severity == "warning":
                score -= 5
            elif severity == "major":
                score -= 15
        # Also count consistency_checks issues
        consistency = review.get("consistency_checks", {})
        for _key, issues_list in consistency.items():
            if isinstance(issues_list, list):
                for _ in issues_list:
                    score -= 1  # Each consistency issue costs 1 point
        return max(0, score)

    # --- Auto-fix: automatic repair of simple issues ---

    # Core replacements for common AI clichés
    _BANNED_REPLACEMENTS = {
        "综上所述": "", "总而言之": "", "不仅如此": "而且", "值得一提的是": "",
        "在当今社会": "", "随着科技的发展": "", "不可否认": "", "众所周知": "",
        "毋庸置疑": "", "日新月异": "", "蓬勃发展": "", "息息相关": "",
        "举足轻重": "重要", "循序渐进": "一步步", "深入探讨": "讨论",
        "至关重要": "关键", "具有重要意义": "很重要",
        "标志着": "意味着", "体现了": "显示了", "反映了": "说明",
        "不仅...而且": "既...又",
        "五味杂陈": "心里复杂", "百感交集": "心里乱糟糟的",
        "心如刀绞": "心疼得要命", "肝肠寸断": "特别难过",
        "悲喜交加": "又高兴又难过", "欣喜若狂": "高兴坏了",
        "怒不可遏": "气死了", "忐忑不安": "心里没底",
        "惴惴不安": "一直担心", "如释重负": "总算松了口气",
        "心有余悸": "还有点怕", "不知所措": "不知道怎么办",
        "措手不及": "没反应过来", "无地自容": "尴尬死了",
        "极其": "很", "万分": "特别", "异常": "很",
        "颇为": "挺", "甚为": "很", "尤为": "特别", "格外": "特别",
        "然而": "但是", "殊不知": "", "岂料": "没想到",
        "不料": "没想到", "谁知": "没想到",
        "面面相觑": "你看看我我看看你", "目瞪口呆": "愣住了",
        "心照不宣": "谁都没说但都懂",
        "一言难尽": "说来话长",
        # audit-config connector_phrases
        "首先": "", "其次": "", "再次": "", "在某种程度上": "",
        "在当下": "", "随着": "",
        # writer/editor common AI clichés (synced from prompts)
        "唯一的": "只有一点", "直到": "等到", "弥漫着": "有股",
        "摇摇欲坠": "晃动", "空气凝固": "沉默", "话音未落": "",
        "猛地": "突然", "不禁": "", "顿时": "立刻",
        "心中暗想": "", "皱起眉头": "皱眉", "叹了口气": "叹气",
        # editor A5 expanded words
        "此外": "", "值得注意的是": "", "需要强调的是": "",
        "不可忽视": "", "彰显": "显出", "诠释": "表达",
        "赋能": "", "油然而生": "", "心潮澎湃": "",
        "这一刻": "", "仿佛": "像", "宛如": "如同",
    }

    # Empty phrases from audit-config.json
    _EMPTY_PHRASES = [
        "广泛关注", "引发热议", "影响深远", "有效提升",
        "具有一定的指导意义", "值得我们思考",
    ]

    # Abstract nouns to flag for review
    _ABSTRACT_NOUNS = [
        "价值", "意义", "认知", "体系", "模式", "路径", "方法论", "趋势",
    ]

    # Sentence length rules from audit-config.json
    _SENTENCE_RULES = {
        "max_run_long": 4,
        "max_run_short": 5,
        "short_threshold": 12,
        "long_threshold": 35,
    }

    # Cliché pairs: [cliché → suggested concrete alternative]
    _CLICHE_PAIRS = {
        "世界上没有轻松的成功": "说具体一次咬牙挺过去的时刻",
        "坚持就是胜利": "写出坚持里最难熬的那个动作和气味",
        "吃得苦中苦方为人上人": "写出那个苦到底是什么味道",
        "失败是成功之母": "写出失败那一刻具体失去了什么",
        "时间会证明一切": "写出等了多久，等来了什么",
    }

    def auto_fix_banned_words(self, text: str, style_guide: dict) -> tuple[str, list[str]]:
        """Auto-replace banned AI words with natural alternatives."""
        # Always apply built-in replacements; supplement with style_guide banned words
        banned_from_style = []
        if style_guide and "requirements" in style_guide:
            banned_from_style = style_guide["requirements"].get("anti_ai_banned_words", [])

        changes = []
        fixed = text

        # Apply built-in replacements first
        for word, replacement in self._BANNED_REPLACEMENTS.items():
            if word in fixed:
                fixed = fixed.replace(word, replacement)
                changes.append(f"'{word}' → '{replacement}'" if replacement else f"'{word}' → (删除)")

        # Apply style_guide extra banned words not already in built-in dict
        for word in banned_from_style:
            if word not in self._BANNED_REPLACEMENTS and word in fixed:
                fixed = fixed.replace(word, "")
                changes.append(f"'{word}' → (删除)")

        # Apply empty phrases cleanup
        for phrase in self._EMPTY_PHRASES:
            if phrase in fixed:
                fixed = fixed.replace(phrase, "")
                changes.append(f"'{phrase}' → (删除空洞短语)")

        return fixed, changes

    def check_cliches(self, text: str) -> list[str]:
        """Detect cliché phrases and return replacement suggestions."""
        found = []
        for cliche, replacement in self._CLICHE_PAIRS.items():
            if cliche in text:
                found.append(f"陈词滥调「{cliche}」→ 建议替换为「{replacement}」")
        return found

    def check_sentence_patterns(self, text: str) -> list[str]:
        """Check for consecutive long/short sentences exceeding thresholds."""
        issues = []
        rules = self._SENTENCE_RULES
        # Split text into sentences (Chinese-aware: split on 。！？)
        sentences = [s.strip() for s in re.split(r'[。！？]', text) if s.strip()]
        if len(sentences) < 3:
            return issues

        run_long = 0
        run_short = 0
        for s in sentences:
            char_count = len(s)
            if char_count > rules["long_threshold"]:
                run_long += 1
                run_short = 0
            elif char_count < rules["short_threshold"]:
                run_short += 1
                run_long = 0
            else:
                run_long = 0
                run_short = 0

            if run_long > rules["max_run_long"]:
                issues.append(f"连续{run_long}句长句（>{rules['long_threshold']}字），建议插入短句调节节奏")
                run_long = 0
            if run_short > rules["max_run_short"]:
                issues.append(f"连续{run_short}句极短句（<{rules['short_threshold']}字），建议适当合并")
                run_short = 0
        return issues

    def check_abstract_nouns(self, text: str) -> list[str]:
        """Detect abstract nouns that should be replaced with concrete expressions."""
        found = []
        for noun in self._ABSTRACT_NOUNS:
            if noun in text:
                found.append(f"抽象名词「{noun}」→ 建议替换为具体描述")
        return found

    def auto_fix(self, chapter_text: str, chapter_num: int) -> dict:
        rules = self._read_json("validation_rules.json")
        fixes = {"applied": []}

        fixed_text = chapter_text

        # Fix character name alias variations
        auto_fix_config = rules.get("auto_fix", {})
        if auto_fix_config.get("character_names", {}).get("enabled", True):
            supporting = rules.get("characters", {}).get("supporting", {})
            protag = rules.get("characters", {}).get("protagonist", {})

            # Protagonist aliases
            protag_name = protag.get("name", "")
            for alias in protag.get("aliases", []):
                if alias in fixed_text and alias != protag_name:
                    fixed_text = fixed_text.replace(alias, protag_name)
                    fixes["applied"].append(f"角色名：'{alias}' → '{protag_name}'")

            # Supporting aliases
            for name, data in supporting.items():
                for alias in data.get("aliases", []):
                    if alias in fixed_text and alias != name:
                        fixed_text = fixed_text.replace(alias, name)
                        fixes["applied"].append(f"角色名：'{alias}' → '{name}'")

            # Common error fixes
            for error in rules.get("common_errors", {}).get("character_substitution", []):
                wrong = error.get("wrong", "")
                correct = error.get("correct", "")
                if wrong and correct and wrong in fixed_text:
                    fixed_text = fixed_text.replace(wrong, correct)
                    fixes["applied"].append(f"常见错误：'{wrong}' → '{correct}'")

        return {"text": fixed_text, "fixes": fixes}

    # --- Update from reviewer's tracking_updates (L2) ---

    def update_from_review(self, chapter_num: int, review: dict) -> None:
        """Extract tracking_updates from reviewer output into tracking fields."""
        tu = review.get("tracking_updates", {})
        if not tu:
            return

        now = self._now()

        # Character changes
        char_state = self._read_json("character_state.json")
        protag_name = char_state.get("protagonist", {}).get("name", "")
        for change in tu.get("character_changes", []):
            name = change.get("name", "")
            field = change.get("field", "")
            new_val = change.get("new", "")
            if not name or not field:
                continue

            if name == protag_name and "protagonist" in char_state:
                status = char_state["protagonist"].setdefault("currentStatus", {})
                field_map = {
                    "health": "health", "mentalState": "mentalState",
                    "location": "location", "alive": "alive", "position": "position",
                }
                if field in field_map:
                    status[field_map[field]] = new_val
                # Update development milestones
                dev = char_state["protagonist"].setdefault("development", {})
                milestones = dev.setdefault("milestones", [])
                milestones.append(f"第{chapter_num}章：{field} → {new_val}")
            elif name in char_state.get("supportingCharacters", {}):
                sup = char_state["supportingCharacters"][name]
                if field == "alive":
                    sup.setdefault("status", {})["alive"] = new_val
                elif field == "location":
                    sup.setdefault("status", {})["currentLocation"] = new_val
                elif field == "mentalState":
                    sup.setdefault("arc", {})["current"] = new_val

        char_state["lastUpdated"] = now
        self._write_json("character_state.json", char_state)

        # Relationship changes
        relationships = self._read_json("relationships.json")
        for rel_change in tu.get("relationship_changes", []):
            characters = rel_change.get("characters", [])
            change_desc = rel_change.get("change", "")
            rel_type = rel_change.get("type", "personal")
            if not characters or not change_desc:
                continue

            # Add to dynamicRelations
            relationships.setdefault("dynamicRelations", []).append({
                "characters": characters,
                "change": change_desc,
                "chapter": chapter_num,
            })

            # Add to history
            relationships.setdefault("history", []).append(
                f"第{chapter_num}章：{' 与 '.join(characters)} — {change_desc}"
            )

            # Add to conflicts if type matches
            conflict_map = {"personal": "personal", "factional": "factional", "ideological": "ideological"}
            if rel_type in conflict_map:
                conflicts = relationships.setdefault("conflicts", {})
                conflicts.setdefault(conflict_map[rel_type], []).append(
                    f"第{chapter_num}章：{' 与 '.join(characters)} — {change_desc}"
                )

            # Update relationshipMatrix
            matrix = relationships.setdefault("relationshipMatrix", {}).setdefault("matrix", {})
            for char_name in characters:
                if char_name not in matrix:
                    matrix[char_name] = {}
                for other in characters:
                    if other != char_name:
                        matrix[char_name][other] = change_desc

        relationships["lastUpdated"] = now
        self._write_json("relationships.json", relationships)

        # Conflict updates
        conflict_data = tu.get("conflict_updates", {})
        plot_tracker = self._read_json("plot_tracker.json")
        conflicts = plot_tracker.setdefault("conflicts", {})

        for new_conflict in conflict_data.get("new_active", []):
            desc = new_conflict.get("description", "")
            ctype = new_conflict.get("type", "personal")
            if desc:
                conflicts.setdefault("active", []).append({
                    "description": desc,
                    "type": ctype,
                    "chapter": chapter_num,
                })

        for resolved in conflict_data.get("resolved", []):
            desc = resolved.get("description", "")
            if desc:
                conflicts.setdefault("resolved", []).append({
                    "description": desc,
                    "chapter": chapter_num,
                })
                # Remove from active if present
                active = conflicts.get("active", [])
                conflicts["active"] = [a for a in active if a.get("description", "") != desc]

        plot_tracker["lastUpdated"] = now
        self._write_json("plot_tracker.json", plot_tracker)

        # Foreshadowing updates
        fs_data = tu.get("foreshadowing_updates", {})
        for hint in fs_data.get("hints_dropped", []):
            fs_id = hint.get("id", "")
            hint_text = hint.get("hint", "")
            if not hint_text:
                continue
            # Find existing foreshadowing by id, or create new
            found = False
            for fs in plot_tracker.get("foreshadowing", []):
                if fs.get("id") == fs_id:
                    fs.setdefault("hints", []).append(hint_text)
                    found = True
                    break
            if not found:
                plot_tracker.setdefault("foreshadowing", []).append({
                    "id": fs_id or f"fs_{len(plot_tracker.get('foreshadowing', [])) + 1:03d}",
                    "content": hint_text,
                    "planted": {"chapter": chapter_num, "description": ""},
                    "hints": [hint_text],
                    "plannedReveal": {"chapter": None, "description": ""},
                    "status": "planted",
                    "importance": "medium",
                })

        for revealed in fs_data.get("revealed", []):
            fs_id = revealed.get("id", "")
            how = revealed.get("how", "")
            for fs in plot_tracker.get("foreshadowing", []):
                if fs.get("id") == fs_id:
                    fs["status"] = "revealed"
                    fs["plannedReveal"] = {"chapter": chapter_num, "description": how}
                    break

        plot_tracker["lastUpdated"] = now
        self._write_json("plot_tracker.json", plot_tracker)

        # Timeline updates
        tl_data = tu.get("timeline_updates", {})
        timeline = self._read_json("timeline.json")

        time_markers = tl_data.get("time_markers", [])
        if time_markers:
            timeline["storyTime"]["current"] = time_markers[-1]

        for travel in tl_data.get("travel_events", []):
            from_loc = travel.get("from", "")
            to_loc = travel.get("to", "")
            duration = travel.get("duration", "")
            if from_loc and to_loc:
                route_key = f"{from_loc}→{to_loc}"
                timeline.setdefault("timeLogic", {}).setdefault("travelTimes", {}).setdefault("routes", {})[route_key] = {
                    "duration": duration,
                    "chapter": chapter_num,
                }

        timeline["lastUpdated"] = now
        self._write_json("timeline.json", timeline)

        logger.info(f"Tracking updated from review for chapter {chapter_num}")

    # --- L3: Independent LLM analysis ---

    def analyze_development(self, llm, chapter_summaries: list[str], total_chapters: int, chapter_num: int) -> None:
        """Call LLM to analyze character development arcs. Called every 5 chapters."""
        # Load prompt template
        prompt_path = Path(__file__).parent.parent / "prompts" / "tracking_analysis.txt"
        if not prompt_path.exists():
            logger.warning("tracking_analysis.txt not found, skipping development analysis")
            return
        system_prompt = prompt_path.read_text(encoding="utf-8")

        # Build context from tracking data
        char_state = self._read_json("character_state.json")
        plot_tracker = self._read_json("plot_tracker.json")

        context = {
            "chapter_summaries": chapter_summaries[-5:],
            "protagonist": char_state.get("protagonist", {}),
            "active_conflicts": plot_tracker.get("conflicts", {}).get("active", []),
            "active_foreshadowing": [f for f in plot_tracker.get("foreshadowing", [])
                                     if f.get("status") == "planted"][:5],
            "total_chapters": total_chapters,
            "current_chapter": chapter_num,
        }

        user_msg = f"已完成 {chapter_num}/{total_chapters} 章。\n\n"
        user_msg += f"章节摘要（最近5章）：\n"
        for i, summary in enumerate(context["chapter_summaries"]):
            user_msg += f"- {summary[:200]}\n"
        user_msg += f"\n追踪数据：\n{json.dumps(context, ensure_ascii=False, indent=2)[:3000]}\n\n"
        user_msg += "请分析角色成长弧线和剧情发展。"

        result = llm.chat_json(system_prompt, user_msg, temperature=0.3)

        if not isinstance(result, dict):
            logger.warning(f"Development analysis returned non-dict: {type(result).__name__}")
            return

        now = self._now()

        # Write protagonist analysis
        protag_analysis = result.get("protagonist_analysis", {})
        if protag_analysis and char_state.get("protagonist"):
            char_state = self._read_json("character_state.json")
            dev = char_state["protagonist"].setdefault("development", {})
            if protag_analysis.get("currentPhase"):
                dev["currentPhase"] = protag_analysis["currentPhase"]
            if protag_analysis.get("nextGoal"):
                dev["nextGoal"] = protag_analysis["nextGoal"]
            if protag_analysis.get("milestones"):
                existing = dev.get("milestones", [])
                existing_texts = {str(m) for m in existing}
                for m in protag_analysis["milestones"]:
                    m_str = f"第{m.get('chapter', '?')}章：{m.get('event', '')}"
                    if m_str not in existing_texts:
                        existing.append(m_str)
                dev["milestones"] = existing
            char_state["lastUpdated"] = now
            self._write_json("character_state.json", char_state)

        # Write supporting analysis
        for sup_analysis in result.get("supporting_analysis", []):
            name = sup_analysis.get("name", "")
            if not name:
                continue
            char_state = self._read_json("character_state.json")
            sup_data = char_state.get("supportingCharacters", {}).get(name)
            if sup_data:
                if sup_analysis.get("arc_current"):
                    sup_data.setdefault("arc", {})["current"] = sup_analysis["arc_current"]
                if sup_analysis.get("motivations"):
                    sup_data["motivations"] = sup_analysis["motivations"]
                char_state["lastUpdated"] = now
                self._write_json("character_state.json", char_state)

        # Write plot prediction
        plot_pred = result.get("plot_prediction", {})
        if plot_pred.get("plannedClimax"):
            plot_tracker = self._read_json("plot_tracker.json")
            plot_tracker.setdefault("plotlines", {}).setdefault("main", {})["plannedClimax"] = {
                "chapter": plot_pred["plannedClimax"].get("chapter"),
                "description": plot_pred["plannedClimax"].get("reason", ""),
            }
            plot_tracker["lastUpdated"] = now
            self._write_json("plot_tracker.json", plot_tracker)

        logger.info(f"Development analysis completed for chapter {chapter_num}")

    # --- Build tracking context for agents ---

    def get_tracking_context(self, current_chapter: int) -> str:
        parts = []
        strictness = self._get_strictness()
        disabled = self._read_json("config.json").get("disabled_checks", [])

        # Character states
        char_state = self._read_json("character_state.json")
        if char_state and "character" not in disabled:
            lines = ["## 角色状态追踪"]

            # Protagonist
            protag = char_state.get("protagonist", {})
            if protag.get("name"):
                status = protag.get("currentStatus", {})
                dev = protag.get("development", {})
                lines.append(
                    f"- {protag['name']}（主角）：位置 {status.get('location', '未知')}，"
                    f"状态 {status.get('health', '?')}/{status.get('mentalState', '?')}，"
                    f"阶段：{dev.get('currentPhase', '?')}"
                )

            # Supporting
            for name, data in char_state.get("supportingCharacters", {}).items():
                last_seen = data.get("status", {}).get("lastSeen", {})
                ch = last_seen.get("chapter", "未出场") if isinstance(last_seen, dict) else last_seen
                loc = data.get("status", {}).get("currentLocation", "")
                loc_str = f"，位置：{loc}" if loc else ""
                lines.append(f"- {name}：最后出场第{ch}章{loc_str}")

            parts.append("\n".join(lines))

            # Character groups
            groups = char_state.get("characterGroups", {})
            if groups.get("inactive") or groups.get("deceased"):
                g_lines = ["## 角色状态分组"]
                if groups.get("inactive"):
                    g_lines.append(f"- 非活跃：{', '.join(groups['inactive'][:5])}")
                if groups.get("deceased"):
                    g_lines.append(f"- 已死亡：{', '.join(groups['deceased'][:5])}")
                parts.append("\n".join(g_lines))

            # Consistency warnings
            warnings = char_state.get("consistency", {}).get("warnings", [])
            if warnings:
                w_lines = ["## 一致性警告"]
                for w in warnings[:5]:
                    w_lines.append(f"- {w}")
                parts.append("\n".join(w_lines))

            # L2.3: Character detail status
            consistency = char_state.get("consistency", {})
            detail_lines = []
            for trait_type, label in [("physicalTraits", "外貌特征"), ("personalityTraits", "性格特征"), ("speechPatterns", "言语模式")]:
                traits = consistency.get(trait_type, {})
                if traits:
                    detail_lines.append(f"### {label}")
                    for char_name, desc in traits.items():
                        if desc:
                            detail_lines.append(f"- {char_name}：{desc}")
            if detail_lines:
                parts.append("## 角色详细状态\n" + "\n".join(detail_lines))

            # Character psychology (false_belief/want/need/ghost)
            psychology = char_state.get("psychology", {})
            if psychology:
                psy_lines = ["## 角色心理深度"]
                for char_name, psy in psychology.items():
                    entries = []
                    if psy.get("false_belief"):
                        entries.append(f"错误信念：{psy['false_belief']}")
                    if psy.get("want"):
                        entries.append(f"表面渴望：{psy['want']}")
                    if psy.get("need"):
                        entries.append(f"深层需求：{psy['need']}")
                    if psy.get("ghost"):
                        entries.append(f"心魔/旧伤：{psy['ghost']}")
                    if entries:
                        psy_lines.append(f"- {char_name}：" + "；".join(entries))
                if len(psy_lines) > 1:
                    parts.append("\n".join(psy_lines))

        # Timeline
        if "timeline" not in disabled:
            timeline = self._read_json("timeline.json")
            events = timeline.get("events", [])
            if events:
                relevant = [e for e in events if 0 < e.get("chapter", 0) <= current_chapter][-5:]
                if relevant:
                    lines = ["## 近期时间线"]
                    for e in relevant:
                        parts_str = f"（{', '.join(e.get('participants', []))}）" if e.get("participants") else ""
                        lines.append(f"- 第{e['chapter']}章：{e.get('event', '')} {parts_str}")
                    parts.append("\n".join(lines))

            # Anomalies
            anomalies = timeline.get("anomalies", {}).get("issues", [])
            if anomalies:
                lines = ["## 时间异常"]
                for a in anomalies[:5]:
                    lines.append(f"- {a}")
                parts.append("\n".join(lines))

            # L2.3: Time constraints
            time_logic = timeline.get("timeLogic", {})
            constraints = time_logic.get("constraints", [])
            routes = time_logic.get("travelTimes", {}).get("routes", {})
            if constraints or routes:
                lines = ["## 时间约束"]
                for c in constraints[:5]:
                    lines.append(f"- {c}")
                for route, info in list(routes.items())[-5:]:
                    if isinstance(info, dict):
                        lines.append(f"- 旅行：{route}，耗时：{info.get('duration', '未知')}")
                    else:
                        lines.append(f"- 旅行：{route}，耗时：{info}")
                parts.append("\n".join(lines))

        # Active foreshadowing and conflicts
        plot_tracker = self._read_json("plot_tracker.json")
        if "worldbuilding" not in disabled:
            foreshadowing = plot_tracker.get("foreshadowing", [])
            active_fs = [f for f in foreshadowing if isinstance(f.get("planted"), dict) and f["planted"].get("chapter") and f.get("status") not in ("revealed", "resolved")]
            if active_fs:
                lines = ["## 活跃伏笔"]
                for f in active_fs[:20]:
                    ch = f["planted"].get("chapter", "?")
                    hint_str = ""
                    if f.get("hints"):
                        hint_str = f"（提示：{'; '.join(f['hints'][-3:])}）"
                    lines.append(f"- [{f.get('id', '')}] 第{ch}章埋设：{f.get('content', '')}{hint_str}")
                parts.append("\n".join(lines))

            # Active conflicts
            conflicts = plot_tracker.get("conflicts", {})
            active_conflicts = conflicts.get("active", [])
            if active_conflicts:
                lines = ["## 活跃冲突"]
                for c in active_conflicts[:5]:
                    if isinstance(c, dict):
                        lines.append(f"- [{c.get('type', '?')}] {c.get('description', str(c))}")
                    else:
                        lines.append(f"- {c}")
                parts.append("\n".join(lines))

            # L2.3: Resolved conflicts (recent 3)
            resolved = conflicts.get("resolved", [])
            if resolved:
                lines = ["## 已解决冲突"]
                for c in resolved[-3:]:
                    if isinstance(c, dict):
                        lines.append(f"- {c.get('description', str(c))}（第{c.get('chapter', '?')}章）")
                    else:
                        lines.append(f"- {c}")
                parts.append("\n".join(lines))

            # L2.3: Plot notes (plotHoles, inconsistencies)
            notes = plot_tracker.get("notes", {})
            note_items = notes.get("plotHoles", []) + notes.get("inconsistencies", [])
            if note_items:
                lines = ["## 剧情问题记录"]
                for n in note_items[-5:]:
                    lines.append(f"- {n}")
                parts.append("\n".join(lines))

        # Relationships
        relationships = self._read_json("relationships.json")
        if relationships.get("characters"):
            lines = ["## 角色关系"]
            for name, data in relationships["characters"].items():
                rels = data.get("relationships", {})
                active_rels = []
                for cat, members in rels.items():
                    if members and cat != "neutral" and cat != "unknown":
                        active_rels.append(f"{cat}：{', '.join(members[:3])}")
                if active_rels:
                    lines.append(f"- {name}：{'；'.join(active_rels[:3])}")
            if len(lines) > 1:
                parts.append("\n".join(lines))

        # L2.3: Dynamic relations
        dynamic = relationships.get("dynamicRelations", [])
        if dynamic:
            lines = ["## 动态关系变化"]
            for d in dynamic[-5:]:
                chars = d.get("characters", [])
                change = d.get("change", "")
                ch = d.get("chapter", "?")
                lines.append(f"- 第{ch}章：{' 与 '.join(chars)} — {change}")
            parts.append("\n".join(lines))

        # Strictness level
        strictness_desc = {
            "strict": "严格模式：标记所有矛盾，执行真实世界物理，时间线必须完全合乎逻辑",
            "flexible": "灵活模式：允许艺术许可，魔法/科技可以弯曲现实，但会通知",
            "minimal": "最小模式：只标记关键矛盾，让小的不一致通过",
        }
        if strictness in strictness_desc:
            parts.append(f"## 审核严格度\n{strictness_desc[strictness]}")

        # Locations
        if "locations" not in disabled:
            loc_data = self._read_json("locations.json")
            locs = loc_data.get("locations", [])
            if locs:
                lines = ["## 场景地点"]
                for loc in locs[:8]:
                    atm = f"，氛围：{loc['atmosphere']}" if loc.get("atmosphere") else ""
                    lines.append(f"- {loc['name']}（{loc.get('type', '?')}）：{loc.get('function', '')}{atm}")
                parts.append("\n".join(lines))

            # L2.3: Five senses for current location (reuse plot_tracker read earlier)
            current_loc = plot_tracker.get("currentState", {}).get("location", "")
            if current_loc:
                for loc in locs:
                    if loc.get("name") and loc["name"] in current_loc:
                        senses = loc.get("five_senses", {})
                        if senses:
                            sense_lines = [f"## 场景五感参考（{loc['name']}）"]
                            for sense_key, sense_desc in senses.items():
                                if sense_desc:
                                    sense_lines.append(f"- {sense_key}：{sense_desc}")
                            parts.append("\n".join(sense_lines))
                            break

            # L2.3: Scene atmosphere guide
            atm_guide = loc_data.get("scene_atmosphere_guide", {})
            if atm_guide:
                lines = ["## 场景氛围指南"]
                for mood, guide in atm_guide.items():
                    if isinstance(guide, dict):
                        words = guide.get("用词", "")
                        focus = guide.get("重点", "")
                        lines.append(f"- {mood}：用词「{words}」，重点「{focus}」")
                    else:
                        lines.append(f"- {mood}：{guide}")
                parts.append("\n".join(lines))

        result = "\n\n".join(parts) if parts else ""
        if len(result) > 15000:
            result = result[:15000] + "\n\n...(追踪数据已截断，仅保留最近内容)"
        return result
