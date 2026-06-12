from pathlib import Path
import json
import shutil
import re

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "DATA_BACKUP_COPY_ME"
PROFILES_DIR = DATA_DIR / "profiles"
GLOBAL_TEMPLATES_DIR = DATA_DIR / "global_templates"
REGIONS_DIR = DATA_DIR / "regions"
SCREENSHOTS_DIR = DATA_DIR / "screen_detection_images"
DEBUG_DIR = DATA_DIR / "debug_screenshots"
EVAL_DIR = DATA_DIR / "evaluation_screenshots"
FAILED_DIR = DATA_DIR / "failed_detections"
CONDITIONAL_ACTIONS_PATH = DATA_DIR / "conditional_actions.json"
LOGS_DIR = DATA_DIR / "logs"
SETTINGS_PATH = DATA_DIR / "settings.json"
PHONE_SCREENS_PATH = REGIONS_DIR / "phone_screens.json"
DETECTION_ZONES_PATH = REGIONS_DIR / "detection_zones.json"

DEFAULT_PROFILE_ID = "default_app"
DEFAULT_PROFILE_NAME = "Default App"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}

PROFILE_TEMPLATE_FOLDERS = {
    "close": "close_templates",
    "skip": "skip_templates",
    "back": "back_templates",
    "icon": "app_icon_templates",
    "element": "element_templates",
    "screen": "screen_templates",
    "negative": "negative_templates",
    "conditional": "conditional_templates",
    "conditional_trigger": "conditional_trigger_templates",
    "conditional_target": "conditional_target_templates",
}

GLOBAL_TEMPLATE_FOLDERS = {
    "close": "close",
    "skip": "skip",
    "back": "back",
    "playstore": "playstore",
    "negative": "negative",
}


def load_json(path: Path, default):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def slugify(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", str(name).strip()).strip("_").lower()
    return value or DEFAULT_PROFILE_ID


def profile_dir(profile_id: str) -> Path:
    return PROFILES_DIR / slugify(profile_id)


def global_template_dir(template_type: str) -> Path:
    folder = GLOBAL_TEMPLATE_FOLDERS.get(template_type, template_type)
    path = GLOBAL_TEMPLATES_DIR / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_profile(profile_id: str, display_name: str | None = None) -> Path:
    pid = slugify(profile_id)
    p = profile_dir(pid)
    for sub in PROFILE_TEMPLATE_FOLDERS.values():
        (p / sub).mkdir(parents=True, exist_ok=True)
    notes = p / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    meta = p / "profile.json"
    if not meta.exists():
        save_json(meta, {"profile_id": pid, "name": display_name or profile_id})
    template_meta = p / "template_metadata.json"
    if not template_meta.exists():
        save_json(template_meta, {})
    return p


def profile_template_dir(profile_id: str, template_type: str) -> Path:
    folder = PROFILE_TEMPLATE_FOLDERS.get(template_type, template_type)
    path = profile_dir(profile_id) / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_dirs() -> None:
    for p in [
        DATA_DIR,
        PROFILES_DIR,
        GLOBAL_TEMPLATES_DIR,
        REGIONS_DIR,
        SCREENSHOTS_DIR,
        DEBUG_DIR,
        EVAL_DIR,
        FAILED_DIR,
        LOGS_DIR,
    ]:
        p.mkdir(parents=True, exist_ok=True)
    for template_type in GLOBAL_TEMPLATE_FOLDERS:
        global_template_dir(template_type)
    ensure_profile(DEFAULT_PROFILE_ID, DEFAULT_PROFILE_NAME)
    if not PHONE_SCREENS_PATH.exists():
        save_json(PHONE_SCREENS_PATH, {"screens": []})
    if not DETECTION_ZONES_PATH.exists():
        save_json(DETECTION_ZONES_PATH, {"zones": []})


def list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return [p for p in sorted(folder.iterdir()) if p.is_file() and p.suffix.lower() in IMAGE_EXTS]


def remove_images(folder: Path) -> int:
    count = 0
    folder.mkdir(parents=True, exist_ok=True)
    for p in list_images(folder):
        p.unlink(missing_ok=True)
        count += 1
    return count


def reset_all_data() -> None:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    ensure_dirs()
