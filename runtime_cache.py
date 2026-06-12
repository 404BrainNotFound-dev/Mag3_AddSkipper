from __future__ import annotations
import time
from pathlib import Path
from collections import deque
import cv2
from paths import IMAGE_EXTS

class RuntimeCache:
    def __init__(self) -> None:
        self.template_cache: dict[str, dict] = {}
        self.fingerprints: dict[str, object] = {}
        self.unchanged_counts: dict[str, int] = {}
        self.click_history = deque(maxlen=500)
        self.detection_history = deque(maxlen=300)
        self.benchmark_history = deque(maxlen=200)

    def clear(self) -> None:
        self.template_cache.clear()
        self.fingerprints.clear()
        self.unchanged_counts.clear()
        self.click_history.clear()
        self.detection_history.clear()
        self.benchmark_history.clear()

    def invalidate_templates(self) -> None:
        self.template_cache.clear()

    def folder_signature(self, folder: Path) -> tuple:
        if not folder.exists():
            return tuple()
        sig = []
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                try:
                    st = p.stat()
                    sig.append((p.name, st.st_size, int(st.st_mtime)))
                except OSError:
                    pass
        return tuple(sig)

    def _precision_crop(self, img, folder_name: str):
        name = folder_name.lower()
        max_size = None
        if name in {"close_templates", "close", "skip_templates", "skip"}:
            max_size = 32
        elif name in {"back_templates", "back"}:
            max_size = 40
        if max_size is None:
            return img
        h, w = img.shape[:2]
        if w <= max_size and h <= max_size:
            return img
        cx = w // 2
        cy = h // 2
        half = max_size // 2
        x1 = max(0, cx - half)
        y1 = max(0, cy - half)
        x2 = min(w, cx + half)
        y2 = min(h, cy + half)
        return img[y1:y2, x1:x2]

    def get_templates(self, folder: Path) -> list[dict]:
        key = str(folder.resolve())
        sig = self.folder_signature(folder)
        item = self.template_cache.get(key)
        if item and item.get("signature") == sig:
            return item["templates"]
        templates = []
        if folder.exists():
            for p in sorted(folder.iterdir()):
                if not p.is_file() or p.suffix.lower() not in IMAGE_EXTS:
                    continue
                img = cv2.imread(str(p), cv2.IMREAD_COLOR)
                if img is None:
                    continue
                img = self._precision_crop(img, p.parent.name)
                if img.size == 0:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                templates.append({
                    "name": p.name,
                    "path": str(p),
                    "folder": str(folder),
                    "gray": gray,
                    "width": gray.shape[1],
                    "height": gray.shape[0],
                    "trust_boost": 0.08 if p.name.lower().startswith("trusted_") else 0.0,
                })
        self.template_cache[key] = {"signature": sig, "templates": templates, "loaded_at": time.time()}
        return templates

    def note_click(self, screen_id: str, action: str) -> None:
        self.click_history.append({"time": time.time(), "screen_id": screen_id, "action": action})

    def note_detection(self, data: dict) -> None:
        item = dict(data)
        item["time"] = time.time()
        self.detection_history.append(item)

    def estimate_memory_mb(self) -> float:
        total = 0
        for item in self.template_cache.values():
            for t in item.get("templates", []):
                total += t["gray"].nbytes
        for fp in self.fingerprints.values():
            try:
                total += fp.nbytes
            except Exception:
                pass
        return total / (1024 * 1024)
