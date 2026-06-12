from __future__ import annotations
from typing import Any
from paths import SETTINGS_PATH, ensure_dirs, load_json, save_json, DEFAULT_PROFILE_ID

DEFAULT_SETTINGS: dict[str, Any] = {
    "current_profile_id": DEFAULT_PROFILE_ID,
    "template_threshold": 0.80,
    "minimum_trust_to_click": 0.80,
    "early_accept_threshold": 0.94,
    "negative_threshold": 0.80,
    "negative_avoid_margin_pixels": 90,
    "negative_protection_enabled": True,
    "save_failed_detections": False,
    "scan_delay_seconds": 0.02,
    "speed_profile": "human",
    "speed_level": 3,
    "screen_check_seconds": 3.0,
    "post_close_click_delay_seconds": 0.12,
    "app_launch_wait_seconds": 0.45,
    "click_cooldown_seconds": 0.05,
    "max_clicks_per_minute": 600,
    "multi_scale_matching": False,
    "template_scales": [0.90, 1.00, 1.10],
    "close_template_crop_size": 32,
    "back_template_crop_size": 40,
    "icon_template_crop_size": 96,
    "global_rectangle_min_size": 8,
    "inactivity_cycles": 3,
    "unchanged_threshold": 3.0,
    "inactivity_recovery_action": "none",
    "inactivity_recovery_enabled": False,
    "auto_launch_app_icon": True,
    "slow_run_enabled": False,
    "slow_scan_delay_seconds": 0.25,
    "slow_pre_click_delay_seconds": 0.75,
    "slow_post_click_delay_seconds": 0.75,
    "ctrl_alt_s_toggle_enabled": True,
    "stop_backspace_presses": 3,
    "stop_backspace_window_seconds": 1.2,
    "backspace_emergency_enabled": False,
    "save_debug_images": False,
    "conditional_actions_enabled": True,
    "conditional_threshold": 0.80,
    "conditional_action_delay_seconds": 0.20,
    "custom_pre_click_delay_seconds": 0.00,
    "custom_mouse_move_duration_seconds": 0.00,
    "custom_verify_wait_seconds": 0.15,
}


def load_settings() -> dict[str, Any]:
    ensure_dirs()
    data = load_json(SETTINGS_PATH, {})
    merged = DEFAULT_SETTINGS.copy()
    if isinstance(data, dict):
        merged.update(data)
    merged["template_threshold"] = max(0.80, float(merged.get("template_threshold", 0.80)))
    merged["minimum_trust_to_click"] = max(0.80, float(merged.get("minimum_trust_to_click", 0.80)))
    merged["conditional_threshold"] = max(0.80, float(merged.get("conditional_threshold", 0.80)))
    return merged


def save_settings(settings: dict[str, Any]) -> None:
    ensure_dirs()
    merged = DEFAULT_SETTINGS.copy()
    merged.update(settings)
    save_json(SETTINGS_PATH, merged)


def reset_settings() -> None:
    ensure_dirs()
    save_json(SETTINGS_PATH, DEFAULT_SETTINGS.copy())
