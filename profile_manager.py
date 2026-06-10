from __future__ import annotations
import shutil
from pathlib import Path
from paths import PROFILES_DIR, ensure_dirs, ensure_profile, profile_dir, slugify, load_json, save_json, DEFAULT_PROFILE_ID, DEFAULT_PROFILE_NAME


def list_profiles() -> list[dict]:
    ensure_dirs()
    profiles = []
    for p in sorted(PROFILES_DIR.iterdir()):
        if not p.is_dir():
            continue
        meta = load_json(p / "profile.json", {})
        pid = meta.get("profile_id") or p.name
        name = meta.get("name") or pid
        profiles.append({"profile_id": pid, "name": name, "path": str(p)})
    if not profiles:
        create_profile(DEFAULT_PROFILE_NAME)
        return list_profiles()
    return profiles


def create_profile(name: str) -> dict:
    pid = slugify(name)
    p = ensure_profile(pid, name)
    meta = {"profile_id": pid, "name": name.strip() or DEFAULT_PROFILE_NAME}
    save_json(p / "profile.json", meta)
    return {"profile_id": pid, "name": meta["name"], "path": str(p)}


def delete_profile(profile_id: str) -> None:
    pid = slugify(profile_id)
    if pid == DEFAULT_PROFILE_ID:
        clear_profile_templates(pid)
        return
    p = profile_dir(pid)
    if p.exists():
        shutil.rmtree(p)
    if not list_profiles():
        create_profile(DEFAULT_PROFILE_NAME)


def clear_profile_templates(profile_id: str, template_type: str | None = None) -> None:
    p = profile_dir(profile_id)
    folders = {
        "close": "close_templates",
        "back": "back_templates",
        "icon": "app_icon_templates",
        "element": "element_templates",
        "screen": "screen_templates",
    }
    targets = [folders[template_type]] if template_type in folders else list(folders.values())
    for folder in targets:
        d = p / folder
        d.mkdir(parents=True, exist_ok=True)
        for item in d.iterdir():
            if item.is_file() and item.suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]:
                item.unlink(missing_ok=True)
