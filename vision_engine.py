from __future__ import annotations
from pathlib import Path
import cv2
import mss
import numpy as np
from runtime_cache import RuntimeCache
from trust_engine import calculate_trust


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
    return cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)


def fingerprint_diff(a, b) -> float:
    if a is None or b is None:
        return 999.0
    return float(np.mean(cv2.absdiff(a, b)))


def crop_from_parent(parent_image, parent_region: dict, child_region: dict):
    px = int(parent_region.get("x", 0))
    py = int(parent_region.get("y", 0))
    x = int(child_region.get("x", px)) - px
    y = int(child_region.get("y", py)) - py
    w = int(child_region.get("w", parent_image.shape[1]))
    h = int(child_region.get("h", parent_image.shape[0]))
    x1 = max(0, x)
    y1 = max(0, y)
    x2 = min(parent_image.shape[1], x + max(1, w))
    y2 = min(parent_image.shape[0], y + max(1, h))
    if x2 <= x1 or y2 <= y1:
        return parent_image
    return parent_image[y1:y2, x1:x2]


class VisionEngine:
    def __init__(self, cache: RuntimeCache):
        self.cache = cache

    def templates(self, folder: Path) -> list[dict]:
        return self.cache.get_templates(folder)

    def has_templates(self, folders: list[Path]) -> bool:
        return any(self.templates(folder) for folder in folders)

    def _match_template_list(self, image_bgr, folders: list[Path], settings: dict, only_paths: set[str] | None = None) -> dict | None:
        if image_bgr is None or image_bgr.size == 0:
            return None
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        threshold = max(0.80, float(settings.get("template_threshold", 0.80)))
        early_accept = max(threshold, float(settings.get("early_accept_threshold", 0.94)))
        use_scales = bool(settings.get("multi_scale_matching", False))
        scales = settings.get("template_scales", [1.0]) if use_scales else [1.0]
        best = None

        for folder in folders:
            for t in self.templates(folder):
                if only_paths is not None and str(t.get("path")) not in only_paths:
                    continue
                base = t["gray"]
                for scale in scales:
                    scale = float(scale)
                    tw = int(t["width"] * scale)
                    th = int(t["height"] * scale)
                    if tw < 6 or th < 6 or tw >= w or th >= h:
                        continue
                    temp = base if abs(scale - 1.0) < 0.001 else cv2.resize(base, (tw, th), interpolation=cv2.INTER_AREA)
                    result = cv2.matchTemplate(gray, temp, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, max_loc = cv2.minMaxLoc(result)
                    item = {
                        "template": t["name"],
                        "template_path": t.get("path"),
                        "folder": str(folder),
                        "confidence": float(max_val),
                        "x": int(max_loc[0]),
                        "y": int(max_loc[1]),
                        "w": int(tw),
                        "h": int(th),
                        "scale": scale,
                        "trust_boost": float(t.get("trust_boost", 0.0)),
                    }
                    if best is None or item["confidence"] > best["confidence"]:
                        best = item
                    if item["confidence"] >= early_accept:
                        return item
        if best and best["confidence"] >= threshold:
            return best
        return best

    def _local_negative_match(self, image_bgr, match: dict, negative_folders: list[Path], settings: dict) -> dict | None:
        if not match or not negative_folders:
            return None
        margin = int(settings.get("negative_avoid_margin_pixels", 90))
        h, w = image_bgr.shape[:2]
        mx1 = int(match.get("x", 0))
        my1 = int(match.get("y", 0))
        mx2 = mx1 + int(match.get("w", 0))
        my2 = my1 + int(match.get("h", 0))
        x1 = max(0, mx1 - margin)
        y1 = max(0, my1 - margin)
        x2 = min(w, mx2 + margin)
        y2 = min(h, my2 + margin)
        if x2 <= x1 or y2 <= y1:
            return None
        local = image_bgr[y1:y2, x1:x2]
        negative_settings = {
            **settings,
            "template_threshold": max(0.80, float(settings.get("negative_threshold", 0.80))),
            "early_accept_threshold": 0.99,
        }
        negative_match = self._match_template_list(local, negative_folders, negative_settings)
        if negative_match and negative_match.get("confidence", 0) >= float(negative_settings["template_threshold"]):
            negative_match["x"] = int(negative_match.get("x", 0) + x1)
            negative_match["y"] = int(negative_match.get("y", 0) + y1)
            return negative_match
        return None

    def _finish_match(self, match: dict | None, image_bgr, region: dict, settings: dict, negative_folders: list[Path] | None):
        if not match:
            return None
        negative_match = None
        if negative_folders and bool(settings.get("negative_protection_enabled", True)):
            negative_match = self._local_negative_match(image_bgr, match, negative_folders, settings)
        trust = calculate_trust(match, region, settings, negative_match)
        match.update(trust)
        match["absolute_x"] = int(region["x"] + match["x"] + match["w"] // 2)
        match["absolute_y"] = int(region["y"] + match["y"] + match["h"] // 2)
        match["region"] = region
        if negative_match:
            match["negative_template"] = negative_match.get("template")
            match["negative_confidence"] = negative_match.get("confidence")
        return match

    def match_image(self, image_bgr, region: dict, folders: list[Path], settings: dict, negative_folders: list[Path] | None = None) -> dict | None:
        match = self._match_template_list(image_bgr, folders, settings)
        return self._finish_match(match, image_bgr, region, settings, negative_folders)

    def match_image_template(self, image_bgr, region: dict, template_path: Path, settings: dict, negative_folders: list[Path] | None = None) -> dict | None:
        template_path = Path(template_path)
        match = self._match_template_list(image_bgr, [template_path.parent], settings, {str(template_path)})
        return self._finish_match(match, image_bgr, region, settings, negative_folders)

    def match_region_template(self, region: dict, template_path: Path, settings: dict, negative_folders: list[Path] | None = None) -> tuple[dict | None, object]:
        image = capture_region(region)
        match = self.match_image_template(image, region, template_path, settings, negative_folders)
        return match, image

    def match_region(self, region: dict, folders: list[Path], settings: dict, negative_folders: list[Path] | None = None) -> tuple[dict | None, object]:
        image = capture_region(region)
        match = self.match_image(image, region, folders, settings, negative_folders)
        return match, image
