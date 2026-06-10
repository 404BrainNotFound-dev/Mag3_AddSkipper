from __future__ import annotations
from typing import Any
from paths import SETTINGS_PATH, ensure_dirs, load_json, save_json, DEFAULT_PROFILE_ID

DEFAULT_SETTINGS: dict[str, Any] = {
    "current_profile_id": DEFAULT_PROFILE_ID,
    "template_threshold": 0.78,
    "early_accept_threshold": 0.92,
    "scan_delay_seconds": 0.01,
    "screen_check_seconds": 3.0,
    "post_close_click_delay_seconds": 0.12,
    "app_launch_wait_seconds": 0.45,
    "click_cooldown_seconds": 0.05,
    "max_clicks_per_minute": 600,
    "multi_scale_matching": False,
    "template_scales": [0.90, 1.00, 1.10],
    "close_template_crop_size": 36,
    "back_template_crop_size": 44,
    "icon_template_crop_size": 96,
    "inactivity_cycles": 3,
    "unchanged_threshold": 3.0,
    "inactivity_recovery_action": "back_template",
    "auto_launch_app_icon": True,
    "stop_backspace_presses": 3,
    "stop_backspace_window_seconds": 1.2,
    "save_debug_images": False,
}


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    data = load_json(SETTINGS_PATH, {})
    merged = DEFAULT_SETTINGS.copy()
    if isinstance(data, dict):
        merged.update(data)
    return merged


def save_settings(settings: dict[str, Any]) -> None:
    ensure_dirs()
    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings)
    save_json(SETTINGS_PATH, merged)


def reset_settings() -> None:
    ensure_dirs()
    save_json(SETTINGS_PATH, DEFAULT_SETTINGS.copy())
