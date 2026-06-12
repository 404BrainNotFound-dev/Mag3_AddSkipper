from __future__ import annotations
from datetime import datetime
from pathlib import Path
import uuid

from paths import DATA_DIR, profile_template_dir, slugify, load_json, save_json


def rules_path(profile_id: str) -> Path:
    return DATA_DIR / "profiles" / slugify(profile_id) / "conditional_actions.json"


def _normalize_rule(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    trigger = str(raw.get("trigger_template") or raw.get("template") or "")
    target = str(raw.get("target_template") or "")
    action = str(raw.get("action") or "click_target_template")
    if not trigger:
        return None
    # v6 4 primary rule type is trigger template then click target template.
    # Older rules are still loaded if they have only template plus action.
    if action == "click_target_template" and not target:
        return None
    return {
        "rule_id": str(raw.get("rule_id") or uuid.uuid4().hex[:10]),
        "name": str(raw.get("name") or "Condition"),
        "trigger_template": trigger,
        "target_template": target,
        "action": action,
        "enabled": bool(raw.get("enabled", True)),
        "created_at": str(raw.get("created_at") or ""),
        "correct_count": int(raw.get("correct_count", 0)),
        "wrong_count": int(raw.get("wrong_count", 0)),
    }


def load_rules(profile_id: str) -> list[dict]:
    data = load_json(rules_path(profile_id), {"rules": []})
    rules = data.get("rules", []) if isinstance(data, dict) else []
    clean = []
    for item in rules:
        normalized = _normalize_rule(item)
        if normalized:
            clean.append(normalized)
    return clean


def save_rules(profile_id: str, rules: list[dict]) -> None:
    save_json(rules_path(profile_id), {"rules": rules})


def add_rule(profile_id: str, name: str, trigger_template_path: Path, target_template_path: Path | None = None, action: str = "click_target_template") -> dict:
    rules = load_rules(profile_id)
    rule = {
        "rule_id": uuid.uuid4().hex[:10],
        "name": name.strip() or "Condition",
        "trigger_template": str(trigger_template_path),
        "target_template": str(target_template_path or ""),
        "action": action.strip() or "click_target_template",
        "enabled": True,
        "created_at": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "correct_count": 0,
        "wrong_count": 0,
    }
    rules.append(rule)
    save_rules(profile_id, rules)
    return rule


def remove_rule(profile_id: str, rule_id: str, delete_templates: bool = True) -> int:
    rules = load_rules(profile_id)
    kept = []
    removed = 0
    for rule in rules:
        if rule.get("rule_id") == rule_id:
            removed += 1
            if delete_templates:
                for key in ["trigger_template", "target_template"]:
                    try:
                        value = str(rule.get(key) or "")
                        if value:
                            Path(value).unlink(missing_ok=True)
                    except Exception:
                        pass
        else:
            kept.append(rule)
    save_rules(profile_id, kept)
    return removed


def clear_rules(profile_id: str, delete_templates: bool = True) -> int:
    rules = load_rules(profile_id)
    count = len(rules)
    if delete_templates:
        for rule in rules:
            for key in ["trigger_template", "target_template"]:
                try:
                    value = str(rule.get(key) or "")
                    if value:
                        Path(value).unlink(missing_ok=True)
                except Exception:
                    pass
    save_rules(profile_id, [])
    return count


def conditional_template_dir(profile_id: str, kind: str = "trigger") -> Path:
    if kind == "target":
        return profile_template_dir(profile_id, "conditional_target")
    if kind == "legacy":
        return profile_template_dir(profile_id, "conditional")
    return profile_template_dir(profile_id, "conditional_trigger")
