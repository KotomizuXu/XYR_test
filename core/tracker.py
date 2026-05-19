"""Tracking system for story consistency, forgotten elements, and timeline management."""

import json
import logging
import re
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
        self._init_config()
        logger.info("Tracking system initialized")

    def _parse_characters(self, world_data: dict) -> tuple[list[dict], list[dict]]:
        """Parse characters from world_data, return (all_chars, protagonists, supporting)."""
        characters = world_data.get("characters", [])
        if isinstance(characters, dict):
            characters = list(characters.values()) if characters else []
        characters = [c for c in characters if isinstance(c, dict)]
        protagonists = [c for c in characters if c.get("role", "") in ("主角", "主人公")]
        supporting = [c for c in characters if c.get("role", "") not in ("主角", "主人公")]
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
                    "planted": {"chapter": None, "description": ""},
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
                    if other_name and other_name != name and other_name in rel_text:
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

        relationships = {
            "novel": self.novel_name,
            "lastUpdated": now,
            "characters": characters,
            "factions": {},
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

        # Name map for quick lookups
        name_map = {}
        if protag_name:
            name_map[protag_name] = protag_name
        for ch in supporting:
            name = ch.get("name", "")
            if name:
                name_map[name] = name

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

        # Update timeline
        timeline = self._read_json("timeline.json")
        for event in timeline.get("events", []):
            if event.get("chapter") == chapter_num:
                event["event"] = chapter_plan.get("title", "") or event.get("event", "")
                event["participants"] = updated_chars
        timeline["lastUpdated"] = now
        self._write_json("timeline.json", timeline)

        # Update plot tracker
        plot_tracker = self._read_json("plot_tracker.json")
        plot_tracker["currentState"]["chapter"] = chapter_num
        for fs in plot_tracker.get("foreshadowing", []):
            if fs.get("planted", {}).get("chapter") == chapter_num or (
                isinstance(fs.get("planted"), dict) and fs.get("planted", {}).get("chapter") is None
                and fs.get("status") == "active"
            ):
                # Check if this foreshadowing was planned for this chapter
                pass
            # Mark foreshadowing as planted if content matches chapter text
            if isinstance(fs.get("planted"), dict):
                planned_ch = fs.get("plannedReveal", {})
                # Check if this was supposed to be planted in this chapter
                # (from chapter plans)
        # Mark foreshadowing items that were planned for this chapter
        for fs in plot_tracker.get("foreshadowing", []):
            planted_ch = fs.get("planted", {})
            if isinstance(planted_ch, dict) and planted_ch.get("chapter") == chapter_num:
                fs["planted"] = {"chapter": chapter_num, "description": f"第{chapter_num}章埋设"}
                fs["status"] = "planted"
        plot_tracker["lastUpdated"] = now
        self._write_json("plot_tracker.json", plot_tracker)

        # Update relationships: co-appearance history and dynamic relations
        relationships = self._read_json("relationships.json")
        if updated_chars:
            # Record co-appearance as relationship history
            changes = []
            for j, name_a in enumerate(updated_chars):
                for name_b in updated_chars[j + 1:]:
                    changes.append({
                        "type": "co-appearance",
                        "characters": [name_a, name_b],
                        "relation": f"第{chapter_num}章同场",
                        "impact": "low",
                    })
                    # Add to dynamicRelations for both directions
                    for na, nb in [(name_a, name_b), (name_b, name_a)]:
                        if na in relationships.get("characters", {}):
                            dynamics = relationships["characters"][na].setdefault("dynamicRelations", [])
                            existing = [d for d in dynamics if d.get("character") == nb]
                            if not existing:
                                dynamics.append({
                                    "character": nb,
                                    "initial": "陌生人",
                                    "current": "同场",
                                    "trajectory": "neutral",
                                    "keyEvents": [f"第{chapter_num}章首次同场"],
                                })
            if changes:
                relationships.setdefault("history", []).append({
                    "chapter": chapter_num,
                    "changes": changes,
                })
        relationships["lastUpdated"] = now
        self._write_json("relationships.json", relationships)

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

    # --- Auto-fix: automatic repair of simple issues ---

    def check_banned_words(self, text: str, style_guide: dict) -> dict:
        """Programmatic check for anti-AI banned words from style guide."""
        banned = []
        if style_guide and "requirements" in style_guide:
            banned = style_guide["requirements"].get("anti_ai_banned_words", [])
        if not banned:
            return {"found": [], "replaced": {}, "clean": True}

        found = []
        for word in banned:
            count = text.count(word)
            if count > 0:
                found.append({"word": word, "count": count})

        return {"found": found, "replaced": {}, "clean": len(found) == 0}

    def auto_fix_banned_words(self, text: str, style_guide: dict) -> tuple[str, list[str]]:
        """Auto-replace banned AI words with natural alternatives."""
        banned = []
        if style_guide and "requirements" in style_guide:
            banned = style_guide["requirements"].get("anti_ai_banned_words", [])
        if not banned:
            return text, []

        replacements = {
            "综上所述": "", "总而言之": "", "不仅如此": "而且", "值得一提的是": "",
            "在当今社会": "", "随着科技的发展": "", "不可否认": "", "众所周知": "",
            "毋庸置疑": "", "日新月异": "", "蓬勃发展": "", "息息相关": "",
            "举足轻重": "重要", "循序渐进": "一步步", "深入探讨": "讨论",
            "至关重要": "关键", "具有重要意义": "很重要",
            "标志着": "意味着", "体现了": "显示了", "反映了": "说明",
            "不仅...而且": "既...又",
        }

        changes = []
        fixed = text
        for word in banned:
            if word in fixed:
                replacement = replacements.get(word, "")
                if replacement:
                    fixed = fixed.replace(word, replacement)
                    changes.append(f"'{word}' → '{replacement}'")
                else:
                    changes.append(f"'{word}' — 需要手动改写")

        return fixed, changes

    def auto_fix(self, chapter_text: str, chapter_num: int) -> dict:
        rules = self._read_json("validation_rules.json")
        fixes = {"applied": [], "skipped": []}

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

        # Fix addresses if enabled
        if auto_fix_config.get("addresses", {}).get("enabled", True):
            fixed_addresses = rules.get("relationships", {}).get("fixed_addresses", {}).get("rules", {})
            for pattern, correct_list in fixed_addresses.items():
                for correct in correct_list:
                    pass  # Address fixing requires context-aware replacement

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

        # Character groups
        groups = char_state.get("characterGroups", {})
        if groups.get("inactive") or groups.get("deceased"):
            lines = ["## 角色状态分组"]
            if groups.get("inactive"):
                lines.append(f"- 非活跃：{', '.join(groups['inactive'][:5])}")
            if groups.get("deceased"):
                lines.append(f"- 已死亡：{', '.join(groups['deceased'][:5])}")
            parts.append("\n".join(lines))

        # Consistency warnings
        warnings = char_state.get("consistency", {}).get("warnings", [])
        if warnings:
            lines = ["## 一致性警告"]
            for w in warnings[:5]:
                lines.append(f"- {w}")
            parts.append("\n".join(lines))

        # Strictness level
        strictness_desc = {
            "strict": "严格模式：标记所有矛盾，执行真实世界物理，时间线必须完全合乎逻辑",
            "flexible": "灵活模式：允许艺术许可，魔法/科技可以弯曲现实，但会通知",
            "minimal": "最小模式：只标记关键矛盾，让小的不一致通过",
        }
        if strictness in strictness_desc:
            parts.append(f"## 审核严格度\n{strictness_desc[strictness]}")

        return "\n\n".join(parts) if parts else ""
