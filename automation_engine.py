from __future__ import annotations
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
import cv2

from paths import (
    PHONE_SCREENS_PATH,
    DETECTION_ZONES_PATH,
    FAILED_DIR,
    load_json,
    profile_template_dir,
    global_template_dir,
)
from runtime_cache import RuntimeCache
from vision_engine import VisionEngine, capture_region, fingerprint, fingerprint_diff, crop_from_parent
from mouse_controller import MouseController
from conditional_actions import load_rules


SPEED_PRESETS = {
    "baby": {
        "scan_delay": 0.35,
        "click_lockout": 2.00,
        "pre_click": 0.65,
        "post_click": 1.00,
        "screen_check": 4.50,
        "mouse_move_duration": 0.35,
        "verify_wait": 0.70,
    },
    "slow_human": {
        "scan_delay": 0.20,
        "click_lockout": 1.40,
        "pre_click": 0.35,
        "post_click": 0.70,
        "screen_check": 4.00,
        "mouse_move_duration": 0.20,
        "verify_wait": 0.50,
    },
    "human": {
        "scan_delay": 0.10,
        "click_lockout": 0.90,
        "pre_click": 0.12,
        "post_click": 0.35,
        "screen_check": 3.00,
        "mouse_move_duration": 0.08,
        "verify_wait": 0.30,
    },
    "fast_human": {
        "scan_delay": 0.045,
        "click_lockout": 0.55,
        "pre_click": 0.04,
        "post_click": 0.20,
        "screen_check": 2.50,
        "mouse_move_duration": 0.03,
        "verify_wait": 0.18,
    },
    "computer": {
        "scan_delay": 0.015,
        "click_lockout": 0.28,
        "pre_click": 0.00,
        "post_click": 0.08,
        "screen_check": 2.00,
        "mouse_move_duration": 0.00,
        "verify_wait": 0.10,
    },
}


def _profile_key(settings: dict) -> str:
    value = str(settings.get("speed_profile", "human")).strip().lower().replace(" ", "_")
    return value if value in SPEED_PRESETS or value == "custom" else "human"


def speed_values(settings: dict) -> dict:
    if bool(settings.get("slow_run_enabled", False)):
        key = "slow_human"
    else:
        key = _profile_key(settings)
    if key == "custom":
        base = {
            "scan_delay": max(0.0, float(settings.get("scan_delay_seconds", 0.05))),
            "click_lockout": max(0.18, float(settings.get("click_cooldown_seconds", 0.30))),
            "pre_click": max(0.0, float(settings.get("custom_pre_click_delay_seconds", 0.00))),
            "post_click": max(0.0, float(settings.get("post_close_click_delay_seconds", 0.15))),
            "screen_check": max(0.50, float(settings.get("screen_check_seconds", 3.0))),
            "mouse_move_duration": max(0.0, float(settings.get("custom_mouse_move_duration_seconds", 0.00))),
            "verify_wait": max(0.05, float(settings.get("custom_verify_wait_seconds", 0.15))),
        }
    else:
        base = SPEED_PRESETS[key].copy()
    level = int(round(float(settings.get("speed_level", 3))))
    level = max(1, min(5, level))
    # Level 1 is safest inside the selected preset. Level 5 is fastest inside the selected preset.
    multiplier = {1: 1.45, 2: 1.18, 3: 1.00, 4: 0.82, 5: 0.68}[level]
    for k in ["scan_delay", "click_lockout", "pre_click", "post_click", "mouse_move_duration", "verify_wait"]:
        base[k] = max(0.0, base[k] * multiplier)
    base["screen_check"] = max(0.50, float(settings.get("screen_check_seconds", base["screen_check"])))
    # Never allow unsafe zero lockout because this is real desktop mouse control.
    base["click_lockout"] = max(0.18, base["click_lockout"])
    return base


class AutomationEngine:
    def __init__(self, cache: RuntimeCache, log_callback=None, status_callback=None, runtime_callback=None):
        self.cache = cache
        self.vision = VisionEngine(cache)
        self.mouse = MouseController()
        self.log_callback = log_callback or (lambda msg: None)
        self.status_callback = status_callback or (lambda msg: None)
        self.runtime_callback = runtime_callback or (lambda data: None)
        self.thread = None
        self.stop_event = threading.Event()
        self.running = False
        self.click_times = deque(maxlen=1000)
        self.screen_index = 0
        self.screen_lock_until: dict[str, float] = {}
        self.last_failed_save: dict[str, float] = {}
        self.last_no_template_log = 0.0

    def log(self, message: str) -> None:
        self.log_callback(message)

    def status(self, message: str) -> None:
        self.status_callback(message)

    def runtime(self, **data) -> None:
        self.runtime_callback(data)

    def start(self, profile_id: str, settings: dict) -> None:
        if self.running:
            self.log("Automation is already running")
            return
        self.stop_event.clear()
        self.running = True
        self.screen_index = 0
        self.thread = threading.Thread(target=self._run, args=(profile_id, settings.copy()), daemon=True)
        self.thread.start()
        self.status("Running")

    def stop(self) -> None:
        self.stop_event.set()
        self.status("Stopping")

    def _load_enabled_screens(self) -> list[dict]:
        screens = load_json(PHONE_SCREENS_PATH, {"screens": []}).get("screens", [])
        return [s for s in screens if s.get("enabled", True)]

    def _zone_for_screen(self, screen: dict) -> dict:
        zones = load_json(DETECTION_ZONES_PATH, {"zones": []}).get("zones", [])
        for z in zones:
            if z.get("screen_id") == screen.get("screen_id"):
                return z
        return {
            "x": screen["x"],
            "y": screen["y"],
            "w": screen["w"],
            "h": screen["h"],
            "screen_id": screen.get("screen_id"),
            "screen_name": screen.get("screen_name"),
        }

    def _rate_limited(self, settings: dict) -> bool:
        now = time.time()
        while self.click_times and now - self.click_times[0] > 60:
            self.click_times.popleft()
        return len(self.click_times) >= int(settings.get("max_clicks_per_minute", 300))

    def _record_click(self):
        self.click_times.append(time.time())

    def _is_locked(self, screen: dict) -> bool:
        sid = screen.get("screen_id", "screen")
        return time.time() < self.screen_lock_until.get(sid, 0.0)

    def _lock_screen(self, screen: dict, settings: dict) -> None:
        values = speed_values(settings)
        sid = screen.get("screen_id", "screen")
        self.screen_lock_until[sid] = time.time() + values["click_lockout"]

    def _try_click_match(self, match: dict, screen: dict, action: str, settings: dict, before_image=None) -> bool:
        if not match:
            return False
        if not bool(match.get("accepted", False)):
            self.log(
                f"Rejected {action} on {screen.get('screen_name')} "
                f"score {match.get('confidence', 0):.3f} trust {match.get('final_trust', 0):.3f} "
                f"reason {match.get('reason', '')}"
            )
            return False
        if self._rate_limited(settings):
            self.log("Click skipped because max clicks per minute was reached")
            return False
        values = speed_values(settings)
        x = int(match["absolute_x"])
        y = int(match["absolute_y"])
        ok = self.mouse.click(
            x,
            y,
            cooldown=values["click_lockout"],
            pre_delay=values["pre_click"],
            post_delay=values["post_click"],
            move_duration=values["mouse_move_duration"],
        )
        if ok:
            self._record_click()
            self._lock_screen(screen, settings)
            self.cache.note_click(screen.get("screen_id", "screen"), action)
            self.runtime(
                current_screen=screen.get("screen_name", "Screen"),
                last_action=f"{action} clicked",
                last_match=match.get("template", ""),
                trust=f"{match.get('final_trust', 0):.3f}",
            )
            self.log(
                f"{action} clicked on {screen.get('screen_name')} at {x} {y} "
                f"template {match.get('template')} score {match.get('confidence'):.3f} "
                f"trust {match.get('final_trust', 0):.3f}"
            )
            self._verify_screen_change(screen, before_image, values)
        return ok

    def _verify_screen_change(self, screen: dict, before_image, values: dict) -> None:
        if before_image is None:
            return
        wait = float(values.get("verify_wait", 0.15))
        if wait > 0:
            time.sleep(wait)
        try:
            after = capture_region(screen)
            diff = fingerprint_diff(fingerprint(before_image), fingerprint(after))
            sid = screen.get("screen_id", "screen")
            if diff <= 1.5:
                self.log(f"Click verification on {screen.get('screen_name')} showed little screen change diff {diff:.2f}")
                self.cache.unchanged_counts[sid] = self.cache.unchanged_counts.get(sid, 0) + 1
            else:
                self.cache.unchanged_counts[sid] = 0
        except Exception as exc:
            self.log(f"Screen verification skipped {exc}")

    def _close_template_folders(self, profile_id: str) -> list[Path]:
        return [
            profile_template_dir(profile_id, "close"),
            profile_template_dir(profile_id, "skip"),
            global_template_dir("close"),
            global_template_dir("skip"),
        ]

    def _negative_template_folders(self, profile_id: str) -> list[Path]:
        return [
            profile_template_dir(profile_id, "negative"),
            global_template_dir("negative"),
        ]

    def _conditional_settings(self, settings: dict) -> dict:
        threshold = max(0.80, float(settings.get("conditional_threshold", 0.80)))
        return {
            **settings,
            "template_threshold": threshold,
            "minimum_trust_to_click": threshold,
            "early_accept_threshold": max(0.95, threshold),
        }

    def _check_conditionals_on_image(self, screen_image, screen: dict, profile_id: str, settings: dict) -> bool:
        if not bool(settings.get("conditional_actions_enabled", True)):
            return False
        rules = [r for r in load_rules(profile_id) if r.get("enabled", True)]
        if not rules:
            return False
        local_settings = self._conditional_settings(settings)
        negatives = self._negative_template_folders(profile_id)
        for rule in rules:
            name = str(rule.get("name") or "Condition")
            trigger_path = Path(str(rule.get("trigger_template") or ""))
            target_path = Path(str(rule.get("target_template") or ""))
            if not trigger_path.exists() or not target_path.exists():
                continue
            trigger = self.vision.match_image_template(screen_image, screen, trigger_path, local_settings, negatives)
            if not trigger or trigger.get("negative_template") or float(trigger.get("confidence", 0.0)) < float(local_settings["template_threshold"]):
                continue
            self.log(f"Conditional {name} trigger matched score {trigger.get('confidence', 0):.3f}")
            target = self.vision.match_image_template(screen_image, screen, target_path, local_settings, negatives)
            if not target:
                self.log(f"Conditional {name} trigger found but target was not visible")
                continue
            if target.get("negative_template"):
                self.log(f"Conditional {name} target avoided because negative template matched nearby")
                continue
            if float(target.get("confidence", 0.0)) < float(local_settings["template_threshold"]):
                self.log(f"Conditional {name} target rejected score {target.get('confidence', 0):.3f}")
                continue
            target["accepted"] = bool(target.get("accepted", False)) and float(target.get("final_trust", 0.0)) >= float(local_settings["minimum_trust_to_click"])
            if not target["accepted"]:
                self.log(f"Conditional {name} target rejected trust {target.get('final_trust', 0):.3f}")
                continue
            return self._try_click_match(target, screen, f"Conditional {name}", settings, before_image=screen_image)
        return False

    def _check_close_on_image(self, screen_image, screen: dict, profile_id: str, settings: dict) -> tuple[bool, dict | None, object | None]:
        zone = self._zone_for_screen(screen)
        folders = self._close_template_folders(profile_id)
        negatives = self._negative_template_folders(profile_id)
        if not self.vision.has_templates(folders):
            now = time.time()
            if now - self.last_no_template_log > 10:
                self.log("Close scan skipped because no app or global close templates exist")
                self.last_no_template_log = now
            return False, None, None
        zone_img = crop_from_parent(screen_image, screen, zone)
        match = self.vision.match_image(zone_img, zone, folders, settings, negatives)
        if match:
            self.cache.note_detection({
                "screen": screen.get("screen_name"),
                "template": match.get("template"),
                "score": match.get("confidence"),
                "trust": match.get("final_trust"),
                "accepted": match.get("accepted"),
            })
            self.runtime(
                current_screen=screen.get("screen_name", "Screen"),
                last_action="Checking templates",
                last_match=match.get("template", ""),
                trust=f"{match.get('final_trust', 0):.3f}",
            )
            if match.get("accepted"):
                return self._try_click_match(match, screen, "Close", settings, before_image=screen_image), match, zone_img
        return False, match, zone_img

    def _save_failed_detection(self, screen: dict, image) -> None:
        try:
            sid = screen.get("screen_id", "screen")
            now = time.time()
            if now - self.last_failed_save.get(sid, 0.0) < 15:
                return
            self.last_failed_save[sid] = now
            FAILED_DIR.mkdir(parents=True, exist_ok=True)
            name = f"failed_{sid}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            cv2.imwrite(str(FAILED_DIR / name), image)
        except Exception as exc:
            self.log(f"Failed screenshot save error {exc}")

    def _try_launch_app_icon(self, screen: dict, profile_id: str, settings: dict, reason: str) -> bool:
        if not bool(settings.get("auto_launch_app_icon", True)):
            return False
        icon_folder = profile_template_dir(profile_id, "icon")
        if not self.vision.has_templates([icon_folder]):
            return False
        image = capture_region(screen)
        match = self.vision.match_image(image, screen, [icon_folder], settings, [])
        if match and match.get("accepted"):
            clicked = self._try_click_match(match, screen, reason, settings, before_image=image)
            if clicked:
                wait = max(0.0, float(settings.get("app_launch_wait_seconds", 0.45)))
                if wait > 0:
                    time.sleep(wait)
                return True
        return False

    def _startup_app_icon_check(self, screens: list[dict], profile_id: str, settings: dict) -> None:
        if not bool(settings.get("auto_launch_app_icon", True)):
            return
        icon_folder = profile_template_dir(profile_id, "icon")
        if not self.vision.has_templates([icon_folder]):
            self.log("Start app check skipped because no app icon templates exist for selected app")
            return
        self.log("Start app check running on all enabled screens")
        for screen in screens:
            if self.stop_event.is_set():
                return
            self.status(f"Checking selected app icon on {screen.get('screen_name', screen.get('screen_id'))}")
            found = self._try_launch_app_icon(screen, profile_id, settings, "App icon start check")
            if not found:
                self.log(f"Selected app icon not visible on {screen.get('screen_name')}")
            time.sleep(max(0.0, speed_values(settings)["scan_delay"]))

    def _handle_inactivity_from_image(self, screen: dict, settings: dict, profile_id: str, image) -> None:
        if not bool(settings.get("inactivity_recovery_enabled", False)):
            return
        screen_id = screen.get("screen_id", "screen")
        fp = fingerprint(image)
        old = self.cache.fingerprints.get(screen_id)
        diff = fingerprint_diff(old, fp)
        self.cache.fingerprints[screen_id] = fp
        if diff <= float(settings.get("unchanged_threshold", 3.0)):
            self.cache.unchanged_counts[screen_id] = self.cache.unchanged_counts.get(screen_id, 0) + 1
        else:
            self.cache.unchanged_counts[screen_id] = 0
        count = self.cache.unchanged_counts.get(screen_id, 0)
        needed = int(settings.get("inactivity_cycles", 3))
        if count < needed:
            return
        self.cache.unchanged_counts[screen_id] = 0
        action = settings.get("inactivity_recovery_action", "none")
        if action == "none":
            self.log(f"Inactive screen detected on {screen.get('screen_name')} but recovery is disabled")
            return
        if action == "back_template":
            folders = [profile_template_dir(profile_id, "back"), global_template_dir("back")]
            match = self.vision.match_image(image, screen, folders, settings, self._negative_template_folders(profile_id))
            if match and match.get("accepted"):
                self._try_click_match(match, screen, "Recovery back", settings, before_image=image)
            else:
                self.log(f"Inactive screen on {screen.get('screen_name')} but no trusted back template matched")
            return
        if action.startswith("press_key:"):
            key = action.split(":", 1)[1].strip()
            if key:
                self.mouse.press_key(key)
                self.log(f"Recovery key pressed {key}")

    def _process_screen(self, screen: dict, profile_id: str, settings: dict) -> None:
        if self._is_locked(screen):
            self.runtime(current_screen=screen.get("screen_name", "Screen"), last_action="Locked after recent click", last_match="", trust="")
            return
        values = speed_values(settings)
        duration = max(0.5, float(values["screen_check"]))
        delay = max(0.0, float(values["scan_delay"]))
        end_time = time.time() + duration
        best_seen = None
        last_image = None
        while not self.stop_event.is_set() and time.time() < end_time:
            screen_image = capture_region(screen)
            last_image = screen_image
            if self._check_conditionals_on_image(screen_image, screen, profile_id, settings):
                return
            clicked, match, _zone_img = self._check_close_on_image(screen_image, screen, profile_id, settings)
            if match:
                best_seen = match if best_seen is None or match.get("final_trust", 0) > best_seen.get("final_trust", 0) else best_seen
            if clicked:
                return
            if delay > 0:
                time.sleep(delay)
        if best_seen:
            self.log(
                f"No trusted action on {screen.get('screen_name')} after {duration:.1f} seconds "
                f"best {best_seen.get('template')} score {best_seen.get('confidence', 0):.3f} "
                f"trust {best_seen.get('final_trust', 0):.3f}"
            )
        else:
            self.log(f"No condition or close match on {screen.get('screen_name')} after {duration:.1f} seconds")
        if bool(settings.get("save_failed_detections", False)) and last_image is not None:
            self._save_failed_detection(screen, last_image)
        if last_image is not None:
            self._handle_inactivity_from_image(screen, settings, profile_id, last_image)

    def _run(self, profile_id: str, settings: dict) -> None:
        self.log(f"Automation started for profile {profile_id}")
        try:
            screens = self._load_enabled_screens()
            if screens:
                self._startup_app_icon_check(screens, profile_id, settings)
            while not self.stop_event.is_set():
                screens = self._load_enabled_screens()
                if not screens:
                    self.status("No enabled screens")
                    self.runtime(current_screen="None", last_action="No enabled screens", last_match="", trust="")
                    time.sleep(0.5)
                    continue
                if self.screen_index >= len(screens):
                    self.screen_index = 0
                screen = screens[self.screen_index]
                self.screen_index = (self.screen_index + 1) % len(screens)
                name = screen.get("screen_name", screen.get("screen_id"))
                self.status(f"Checking {name}")
                self.runtime(current_screen=name, last_action="Capture then conditionals then templates", last_match="", trust="")
                try:
                    self._process_screen(screen, profile_id, settings)
                except Exception as exc:
                    self.log(f"Screen error {screen.get('screen_name')} {exc}")
        finally:
            self.running = False
            self.status("Stopped")
            self.runtime(last_action="Stopped")
            self.log("Automation stopped")
