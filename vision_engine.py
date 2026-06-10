from __future__ import annotations
import cv2
import mss
import numpy as np
from pathlib import Path
from runtime_cache import RuntimeCache


def capture_region(region: dict):
    monitor = {
        "left": int(region["x"]),
        "top": int(region["y"]),
        "width": max(1, int(region["w"])),
        "height": max(1, int(region["h"])),
    }
    with mss.mss() as sct:
        raw = np.array(sct.grab(monitor))
    return cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)


def fingerprint(img) -> np.ndarray:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    return small


def fingerprint_diff(a, b) -> float:
    if a is None or b is None:
        return 999.0
    return float(np.mean(cv2.absdiff(a, b)))


class VisionEngine:
    def __init__(self, cache: RuntimeCache):
        self.cache = cache

    def templates(self, folder: Path) -> list[dict]:
        return self.cache.get_templates(folder)

    def match_templates(self, image_bgr, folder: Path, settings: dict) -> dict | None:
        templates = self.templates(folder)
        if not templates:
            return None
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        threshold = float(settings.get("template_threshold", 0.78))
        early_accept = float(settings.get("early_accept_threshold", 0.92))
        use_scales = bool(settings.get("multi_scale_matching", False))
        scales = settings.get("template_scales", [1.0]) if use_scales else [1.0]
        best = None
        for t in templates:
            base = t["gray"]
            for scale in scales:
                tw = int(t["width"] * float(scale))
                th = int(t["height"] * float(scale))
                if tw < 6 or th < 6 or tw >= w or th >= h:
                    continue
                temp = base if abs(float(scale) - 1.0) < 0.001 else cv2.resize(base, (tw, th), interpolation=cv2.INTER_AREA)
                result = cv2.matchTemplate(gray, temp, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)
                item = {
                    "template": t["name"],
                    "confidence": float(max_val),
                    "x": int(max_loc[0]),
                    "y": int(max_loc[1]),
                    "w": int(tw),
                    "h": int(th),
                    "scale": float(scale),
                }
                if best is None or item["confidence"] > best["confidence"]:
                    best = item
                if item["confidence"] >= early_accept:
                    item["accepted"] = True
                    return item
        if best and best["confidence"] >= threshold:
            best["accepted"] = True
            return best
        return best if best else None

    def match_region(self, region: dict, folder: Path, settings: dict) -> tuple[dict | None, object]:
        img = capture_region(region)
        match = self.match_templates(img, folder, settings)
        if match and match.get("confidence", 0) >= float(settings.get("template_threshold", 0.78)):
            match["absolute_x"] = int(region["x"] + match["x"] + match["w"] // 2)
            match["absolute_y"] = int(region["y"] + match["y"] + match["h"] // 2)
            match["region"] = region
        return match, img
