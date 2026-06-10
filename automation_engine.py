from __future__ import annotations
import threading
import time
from collections import deque

from paths import PHONE_SCREENS_PATH, DETECTION_ZONES_PATH, load_json, profile_template_dir
from vision_engine import VisionEngine, capture_region, fingerprint, fingerprint_diff
from runtime_cache import RuntimeCache
from mouse_controller import MouseController


class AutomationEngine:
    def __init__(self, cache: RuntimeCache, log_callback=None, status_callback=None):
        self.cache = cache
        self.vision = VisionEngine(cache)
        self.mouse = MouseController()
        self.log_callback = log_callback or (lambda msg: None)
        self.status_callback = status_callback or (lambda msg: None)
        self.thread = None
        self.stop_event = threading.Event()
        self.running = False
        self.click_times = deque(maxlen=1000)
        self.screen_index = 0

    def log(self, message: str) -> None:
        self.log_callback(message)

    def status(self, message: str) -> None:
        self.status_callback(message)

    def start(self, profile_id: str, settings: dict) -> None:
        if self.running:
            return
        self.stop_event.clear()
        self.running = True
        self.screen_index = 0
        self.thread = threading.Thread(target=self._run, args=(profile_id, settings.copy()), daemon=True)
        self.thread.start()
        self.status("Running")

    def stop(self) -> None:
        self.stop_event.set()
        self.running = False
        self.status("Stopped")

    def _load_enabled_screens(self) -> list[dict]:
        screens = load_json(PHONE_SCREENS_PATH, {"screens": []}).get("screens", [])
        result = []
        for s in screens:
            if s.get("enabled", True):
                result.append(s)
        return result

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
        return len(self.click_times) >= int(settings.get("max_clicks_per_minute", 600))

    def _record_click(self):
        self.click_times.append(time.time())

    def _try_click_match(self, match: dict, screen: dict, action: str, settings: dict) -> bool:
        if not match or match.get("confidence", 0) < float(settings.get("template_threshold", 0.78)):
            return False
        if self._rate_limited(settings):
            self.log("Click skipped because max clicks per minute was reached")
            return False

        x = int(match["absolute_x"])
        y = int(match["absolute_y"])

        ok = self.mouse.click(x, y, float(settings.get("click_cooldown_seconds", 0.05)))
        if ok:
            self._record_click()
            self.cache.note_click(screen.get("screen_id", "screen"), action)
            self.log(
                f"{action} clicked on {screen.get('screen_name')} "
                f"at {x} {y} using {match.get('template')} score {match.get('confidence'):.3f}"
            )
        return ok

    def _handle_inactivity(self, screen: dict, settings: dict, profile_id: str) -> None:
        screen_id = screen.get("screen_id", "screen")
        img = capture_region(screen)
        fp = fingerprint(img)
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
        action = settings.get("inactivity_recovery_action", "back_template")
        if action == "none":
            self.log(f"Inactive screen detected on {screen.get('screen_name')} but recovery is disabled")
            return

        if action == "back_template":
            folder = profile_template_dir(profile_id, "back")
            match, _ = self.vision.match_region(screen, folder, settings)
            if match and match.get("confidence", 0) >= float(settings.get("template_threshold", 0.78)):
                self._try_click_match(match, screen, "Recovery back", settings)
            else:
                self.log(f"Inactive screen on {screen.get('screen_name')} but no back template matched")
            return

        if action.startswith("press_key:"):
            key = action.split(":", 1)[1].strip()
            if key:
                self.mouse.press_key(key)
                self.log(f"Recovery key pressed {key}")

    def _scan_close_for_duration(self, screen: dict, profile_id: str, settings: dict) -> bool:
        """Search the selected zone of one screen for close templates for the full configured time."""
        zone = self._zone_for_screen(screen)
        close_folder = profile_template_dir(profile_id, "close")
        if not self.vision.templates(close_folder):
            self.log("Close scan skipped because no close templates exist for selected app")
            return False

        duration = max(0.1, float(settings.get("screen_check_seconds", 3.0)))
        delay = max(0.0, float(settings.get("scan_delay_seconds", 0.01)))
        post_click_delay = max(0.0, float(settings.get("post_close_click_delay_seconds", 0.12)))

        end_time = time.time() + duration
        clicked_any = False
        scan_count = 0

        while not self.stop_event.is_set() and time.time() < end_time:
            scan_count += 1
            close_match, _ = self.vision.match_region(zone, close_folder, settings)
            if close_match and close_match.get("confidence", 0) >= float(settings.get("template_threshold", 0.78)):
                clicked = self._try_click_match(close_match, screen, "Close", settings)
                if clicked:
                    clicked_any = True
                    time.sleep(post_click_delay)
                    continue
            if delay > 0:
                time.sleep(delay)

        if not clicked_any:
            self.log(f"No close match found on {screen.get('screen_name')} after {duration:.1f} seconds")
        return clicked_any

    def _try_launch_app_icon(self, screen: dict, profile_id: str, settings: dict, reason: str) -> bool:
        if not bool(settings.get("auto_launch_app_icon", True)):
            return False
        icon_folder = profile_template_dir(profile_id, "icon")
        icon_match, _ = self.vision.match_region(screen, icon_folder, settings)
        if icon_match and icon_match.get("confidence", 0) >= float(settings.get("template_threshold", 0.78)):
            clicked = self._try_click_match(icon_match, screen, reason, settings)
            if clicked:
                wait = max(0.0, float(settings.get("app_launch_wait_seconds", 0.45)))
                if wait > 0:
                    time.sleep(wait)
                return True
        return False

    def _startup_app_icon_check(self, screens: list[dict], profile_id: str, settings: dict) -> None:
        """When Start is clicked, check every enabled phone for the selected app icon first."""
        if not bool(settings.get("auto_launch_app_icon", True)):
            return
        icon_folder = profile_template_dir(profile_id, "icon")
        if not self.vision.templates(icon_folder):
            self.log("Start app check skipped because no app icon templates exist for selected app")
            return

        self.log("Start app check running on all enabled screens")
        for screen in screens:
            if self.stop_event.is_set():
                return
            self.status(f"Checking app icon on {screen.get('screen_name', screen.get('screen_id'))}")
            found = self._try_launch_app_icon(screen, profile_id, settings, "App icon start check")
            if not found:
                self.log(f"Selected app icon not visible on {screen.get('screen_name')}")
            time.sleep(max(0.0, float(settings.get("scan_delay_seconds", 0.01))))

    def _process_screen(self, screen: dict, profile_id: str, settings: dict) -> None:
        # Requirement v6.1:
        # Every enabled screen gets a full check window before moving to the next screen.
        # The same selected app close templates are used for every screen.
        self._scan_close_for_duration(screen, profile_id, settings)

        # After the close scan, check if this phone is on the launcher and the selected app icon is visible.
        self._try_launch_app_icon(screen, profile_id, settings, "App icon")

        # Inactivity recovery runs after the normal close and app icon checks.
        self._handle_inactivity(screen, settings, profile_id)

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
                    time.sleep(0.5)
                    continue

                if self.screen_index >= len(screens):
                    self.screen_index = 0

                screen = screens[self.screen_index]
                self.screen_index = (self.screen_index + 1) % len(screens)

                name = screen.get("screen_name", screen.get("screen_id"))
                self.status(f"Checking {name} for {settings.get('screen_check_seconds', 3.0)} seconds")
                try:
                    self._process_screen(screen, profile_id, settings)
                except Exception as e:
                    self.log(f"Screen error {screen.get('screen_name')} {e}")

        finally:
            self.running = False
            self.status("Stopped")
            self.log("Automation stopped")
