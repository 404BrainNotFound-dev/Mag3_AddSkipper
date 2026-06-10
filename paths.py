from pathlib import Path
import json
import shutil
import re

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "DATA_BACKUP_COPY_ME"
PROFILES_DIR = DATA_DIR / "profiles"
REGIONS_DIR = DATA_DIR / "regions"
SCREENSHOTS_DIR = DATA_DIR / "screen_detection_images"
DEBUG_DIR = DATA_DIR / "debug_screenshots"
EVAL_DIR = DATA_DIR / "evaluation_screenshots"
LOGS_DIR = DATA_DIR / "logs"
SETTINGS_PATH = DATA_DIR / "settings.json"
PHONE_SCREENS_PATH = REGIONS_DIR / "phone_screens.json"
DETECTION_ZONES_PATH = REGIONS_DIR / "detection_zones.json"

DEFAULT_PROFILE_ID = "default_app"
DEFAULT_PROFILE_NAME = "Default App"


def ensure_dirs() -> None:
    for p in [DATA_DIR, PROFILES_DIR, REGIONS_DIR, SCREENSHOTS_DIR, DEBUG_DIR, EVAL_DIR, LOGS_DIR]:
        p.mkdir(parents=True, exist_ok=True)
    ensure_profile(DEFAULT_PROFILE_ID, DEFAULT_PROFILE_NAME)
    if not PHONE_SCREENS_PATH.exists():
        save_json(PHONE_SCREENS_PATH, {"screens": []})
    if not DETECTION_ZONES_PATH.exists():
        save_json(DETECTION_ZONES_PATH, {"zones": []})


def slugify(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]+", "_", name.strip()).strip("_").lower()
    return value or DEFAULT_PROFILE_ID


def profile_dir(profile_id: str) -> Path:
    return PROFILES_DIR / slugify(profile_id)


def ensure_profile(profile_id: str, display_name: str | None = None) -> Path:
    pid = slugify(profile_id)
    p = profile_dir(pid)
    for sub in ["close_templates", "back_templates", "app_icon_templates", "element_templates", "screen_templates", "notes"]:
        (p / sub).mkdir(parents=True, exist_ok=True)
    meta = p / "profile.json"
    if not meta.exists():
        save_json(meta, {"profile_id": pid, "name": display_name or profile_id})
    return p


def profile_template_dir(profile_id: str, template_type: str) -> Path:
    mapping = {
        "close": "close_templates",
        "back": "back_templates",
        "icon": "app_icon_templates",
        "element": "element_templates",
        "screen": "screen_templates",
    }
    folder = mapping.get(template_type, template_type)
    path = profile_dir(profile_id) / folder
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def reset_all_data() -> None:
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR)
    ensure_dirs()
