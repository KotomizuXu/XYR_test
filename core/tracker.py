"""Tracking system for story consistency, forgotten elements, and timeline management."""

import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default thresholds for forgotten elements detection
DEFAULT_THRESHOLDS = {
    "character": 10,
    "plotline": 12,
    "foreshadowing": 20,
}


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
        path = self.tracking_dir / name
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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

    def init_tracking(self, world_data: dict, outline: dict, chapter_plans: list[dict]) -> None:
        self._init_character_state(world_data)
        self._init_timeline(chapter_plans)
        self._init_plot_tracker(outline, chapter_plans)
        self._init_relationships(world_data)
        self._init_validation_rules(world_data)
        self._init_locations(world_data)
        self._init_config()
        logger.info("Tracking system initialized")

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
        }
        self._write_json("character_state.json", state)

    def _init_timeline(self, chapter_plans: list[dict]) -> None:
        now = self._now()
        events = []
        for plan in chapter_plans:
            events.append({
                "chapter": plan.get("chapter_number", 0),
                "date": "",
                "event": plan.get("title", ""),
                "duration": "",
                "participants": [],
            })

        timeline = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "storyTime": {
                "start": "",
                "current": "",
                "end": "",
                "format": "故事内时间标记方式",
            },
            "events": events,
            "parallelEvents": {"timepoints": {}},
            "historicalContext": {"events": []},
            "timeLogic": {
                "travelTimes": {"routes": {}},
                "constraints": [],
            },
            "anomalies": {"issues": []},
        }
        self._write_json("timeline.json", timeline)

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
                foreshadowing.append({
                    "id": f"fs_{fs_idx:03d}",
                    "content": fs,
                    "planted": {"chapter": plan.get("chapter_number"), "description": ""},
                    "hints": [],
                    "plannedReveal": {"chapter": None, "description": ""},
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
                for other in all_chars:
                    other_name = other.get("name", "")
                    if not other_name or other_name == name:
                        continue
                    if other_name not in rel_text:
                        continue
                    # Classify based on surrounding context
                    context = rel_text.lower()
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
                    "leader": "",
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

        rules = {
            "version": "1.0",
            "characters": {
                "protagonist": {
                    "name": protag_name,
                    "aliases": protag_aliases,
                    "forbidden": protag_forbidden,
                    "traits": {},
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
                "character_substitution": [],
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
        config = {
            "thresholds": dict(DEFAULT_THRESHOLDS),
            "strictness": "strict",
            "retired": {"characters": [], "plotlines": [], "foreshadowing": []},
            "disabled_checks": [],
        }
        self._write_json("config.json", config)

    # --- Update: called after each chapter is written ---

    def update_tracking(self, chapter_num: int, chapter_text: str, chapter_plan: dict) -> dict:
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
                appearances.append({
                    "character": name,
                    "role": "主角" if name == protag_name else "配角",
                    "significance": "",
                })

        # Append appearance tracking
        char_state.setdefault("appearanceTracking", []).append({
            "chapter": chapter_num,
            "appearances": appearances,
        })
        char_state["lastUpdated"] = now
        self._write_json("character_state.json", char_state)
        report["characters_updated"] = updated_chars

        # --- All tracking updates consolidated below ---

        # Update plot_tracker: advance currentNode, update notes from plan
        plot_tracker = self._read_json("plot_tracker.json")
        plot_tracker["currentState"]["chapter"] = chapter_num
        # Update currentNode based on chapter title
        title = chapter_plan.get("title", "")
        if title:
            plot_tracker["plotlines"]["main"]["currentNode"] = title
            plot_tracker["plotlines"]["main"].setdefault("completedNodes", []).append(title)
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
                # Try to extract time from chapter plan
                time_info = chapter_plan.get("time", chapter_plan.get("story_time", ""))
                if time_info:
                    event["date"] = str(time_info)
                    timeline["storyTime"]["current"] = str(time_info)
                event["duration"] = chapter_plan.get("duration", "")
        timeline["lastUpdated"] = now
        self._write_json("timeline.json", timeline)

        # Update location tracking if plan has location info
        loc_data = self._read_json("locations.json")
        location_info = chapter_plan.get("location", "")
        if location_info and loc_data.get("locations"):
            for loc in loc_data["locations"]:
                if loc.get("name") and loc["name"] in str(location_info):
                    loc.setdefault("events", []).append({
                        "chapter": chapter_num,
                        "event": title,
                        "characters": updated_chars[:5],
                    })
            loc_data["lastUpdated"] = now
            self._write_json("locations.json", loc_data)

        # Update protagonist state from chapter plan
        char_state = self._read_json("character_state.json")
        protag = char_state.get("protagonist", {})
        if protag.get("name"):
            # Update location from plan
            if location_info:
                protag["currentStatus"]["location"] = str(location_info)
            # Extract new skills/knowledge from plan
            for point in chapter_plan.get("plot_points", []):
                pt = str(point)
                if "学会" in pt or "获得" in pt or "领悟" in pt or "掌握" in pt:
                    protag["currentStatus"].setdefault("skills", []).append(pt[:50])
                if "发现" in pt or "得知" in pt or "知道" in pt or "意识到" in pt:
                    protag["currentStatus"].setdefault("knowledge", []).append(pt[:50])
            # Record consistency warning for suspicious patterns
            if "性格" in chapter_text or "人设" in chapter_text:
                char_state.setdefault("consistency", {}).setdefault("warnings", []).append(
                    f"第{chapter_num}章：出现显式性格描述，建议检查是否符合已建立的性格设定"
                )
        char_state["lastUpdated"] = now
        self._write_json("character_state.json", char_state)

        logger.info(f"Tracking updated for chapter {chapter_num}")
        return report

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
            if self._is_retired("foreshadowing", fs.get("content", "")):
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
        import re
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

        # Active foreshadowing and conflicts
        if "worldbuilding" not in disabled:
            plot_tracker = self._read_json("plot_tracker.json")
            foreshadowing = plot_tracker.get("foreshadowing", [])
            active_fs = [f for f in foreshadowing if isinstance(f.get("planted"), dict) and f["planted"].get("chapter") and f.get("status") not in ("revealed", "resolved")]
            if active_fs:
                lines = ["## 活跃伏笔"]
                for f in active_fs:
                    ch = f["planted"].get("chapter", "?")
                    lines.append(f"- [{f.get('id', '')}] 第{ch}章埋设：{f.get('content', '')}")
                parts.append("\n".join(lines))

            # Active conflicts
            conflicts = plot_tracker.get("conflicts", {}).get("active", [])
            if conflicts:
                lines = ["## 活跃冲突"]
                for c in conflicts[:5]:
                    lines.append(f"- {c}")
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

        return "\n\n".join(parts) if parts else ""
