from __future__ import annotations
from pathlib import Path
from datetime import datetime
import cv2
import mss
import numpy as np

from paths import (
    SCREENSHOTS_DIR,
    PHONE_SCREENS_PATH,
    DETECTION_ZONES_PATH,
    save_json,
    load_json,
    profile_template_dir,
    global_template_dir,
)


def capture_desktop():
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        raw = np.array(sct.grab(monitor))
        img = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
        bbox = {
            "left": int(monitor["left"]),
            "top": int(monitor["top"]),
            "width": int(monitor["width"]),
            "height": int(monitor["height"]),
        }
        return img, bbox


def fit_for_display(img, max_w=1600, max_h=900):
    h, w = img.shape[:2]
    scale = min(max_w / max(1, w), max_h / max(1, h), 1.0)
    if scale < 1.0:
        resized = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    else:
        resized = img.copy()
    return resized, scale


def save_context_image(name: str, img) -> None:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOTS_DIR / f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    cv2.imwrite(str(path), img)


def select_phone_screens():
    img, desktop = capture_desktop()
    display, scale = fit_for_display(img)
    base = display.copy()
    rectangles = []
    drawing = False
    start = None
    current = None
    win = "Select Mobile Screens"

    def draw_canvas():
        canvas = base.copy()
        lines = [
            "Drag around each mobile screen",
            "Release mouse to add screen",
            "U undo    R reset    Enter save    Esc cancel",
        ]
        y = 30
        for line in lines:
            cv2.putText(canvas, line, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 255, 255), 2)
            y += 34
        for idx, (x1, y1, x2, y2) in enumerate(rectangles, start=1):
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 220, 255), 3)
            cv2.putText(canvas, f"Screen {idx}", (x1 + 8, max(28, y1 - 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 220, 255), 2)
        if drawing and current:
            x1, y1, x2, y2 = current
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 2)
        return canvas

    def on_mouse(event, x, y, flags, param):
        nonlocal drawing, start, current, rectangles
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            start = (x, y)
            current = (x, y, x, y)
        elif event == cv2.EVENT_MOUSEMOVE and drawing and start:
            x1, y1 = start
            current = (min(x1, x), min(y1, y), max(x1, x), max(y1, y))
        elif event == cv2.EVENT_LBUTTONUP and drawing and start:
            drawing = False
            x1, y1 = start
            rect = (min(x1, x), min(y1, y), max(x1, x), max(y1, y))
            if rect[2] - rect[0] > 30 and rect[3] - rect[1] > 30:
                rectangles.append(rect)
            current = None
            start = None

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, display.shape[1], display.shape[0])
    cv2.setMouseCallback(win, on_mouse)
    saved = False
    while True:
        cv2.imshow(win, draw_canvas())
        key = cv2.waitKey(30) & 0xFF
        if key in (13, 10):
            saved = True
            break
        if key == 27:
            break
        if key in (ord("u"), ord("U")) and rectangles:
            rectangles.pop()
        if key in (ord("r"), ord("R")):
            rectangles.clear()
    cv2.destroyWindow(win)
    if not saved:
        return []

    screens = []
    for idx, (x1, y1, x2, y2) in enumerate(rectangles, start=1):
        ax1 = int(desktop["left"] + x1 / scale)
        ay1 = int(desktop["top"] + y1 / scale)
        ax2 = int(desktop["left"] + x2 / scale)
        ay2 = int(desktop["top"] + y2 / scale)
        screens.append({
            "screen_id": f"screen_{idx}",
            "screen_name": f"Screen {idx}",
            "x": ax1,
            "y": ay1,
            "w": max(1, ax2 - ax1),
            "h": max(1, ay2 - ay1),
            "enabled": True,
        })
    save_json(PHONE_SCREENS_PATH, {"screens": screens})
    save_context_image("phone_screens", img)
    return screens


def select_detection_zones():
    data = load_json(PHONE_SCREENS_PATH, {"screens": []})
    screens = data.get("screens", [])
    if not screens:
        raise RuntimeError("Select mobile screens first")
    desktop_img, desktop = capture_desktop()
    zones = []
    for screen in screens:
        sx = int(screen["x"] - desktop["left"])
        sy = int(screen["y"] - desktop["top"])
        sw = int(screen["w"])
        sh = int(screen["h"])
        crop = desktop_img[sy:sy + sh, sx:sx + sw]
        if crop.size == 0:
            continue
        display, scale = fit_for_display(crop, 1200, 820)
        base = display.copy()
        rect = None
        drawing = False
        start = None
        current = None
        screen_name = screen.get("screen_name", screen.get("screen_id", "Screen"))
        win = f"Detection Zone {screen_name}"

        def draw_canvas():
            canvas = base.copy()
            lines = [
                f"Select detection zone for {screen_name}",
                "Use only the area where close buttons should be searched",
                "Drag one rectangle    F full screen    Enter save    Esc cancel",
            ]
            y = 30
            for line in lines:
                cv2.putText(canvas, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)
                y += 30
            r = current or rect
            if r:
                x1, y1, x2, y2 = r
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 3)
            return canvas

        def on_mouse(event, x, y, flags, param):
            nonlocal drawing, start, current, rect
            if event == cv2.EVENT_LBUTTONDOWN:
                drawing = True
                start = (x, y)
                current = (x, y, x, y)
            elif event == cv2.EVENT_MOUSEMOVE and drawing and start:
                x1, y1 = start
                current = (min(x1, x), min(y1, y), max(x1, x), max(y1, y))
            elif event == cv2.EVENT_LBUTTONUP and drawing and start:
                drawing = False
                x1, y1 = start
                r = (min(x1, x), min(y1, y), max(x1, x), max(y1, y))
                if r[2] - r[0] > 20 and r[3] - r[1] > 20:
                    rect = r
                current = None
                start = None

        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, display.shape[1], display.shape[0])
        cv2.setMouseCallback(win, on_mouse)
        saved = False
        while True:
            cv2.imshow(win, draw_canvas())
            key = cv2.waitKey(30) & 0xFF
            if key in (13, 10):
                saved = True
                break
            if key in (ord("f"), ord("F")):
                rect = (0, 0, display.shape[1] - 1, display.shape[0] - 1)
            if key == 27:
                break
        cv2.destroyWindow(win)
        if not saved:
            continue
        if rect is None:
            rect = (0, 0, display.shape[1] - 1, display.shape[0] - 1)
        x1, y1, x2, y2 = rect
        rx1 = int(x1 / scale)
        ry1 = int(y1 / scale)
        rx2 = int(x2 / scale)
        ry2 = int(y2 / scale)
        zones.append({
            "zone_id": f"zone_{screen.get('screen_id')}",
            "screen_id": screen.get("screen_id"),
            "screen_name": screen_name,
            "x": int(screen["x"] + rx1),
            "y": int(screen["y"] + ry1),
            "w": max(1, rx2 - rx1),
            "h": max(1, ry2 - ry1),
        })
    save_json(DETECTION_ZONES_PATH, {"zones": zones})
    save_context_image("detection_zones", desktop_img)
    return zones


def save_cross_template(profile_id: str, template_type: str, crop_size: int) -> Path | None:
    img, _desktop = capture_desktop()
    display, scale = fit_for_display(img)
    win = f"Pick {template_type} template by cross"
    pos = [display.shape[1] // 2, display.shape[0] // 2]
    clicked = [False]

    def draw_canvas():
        canvas = display.copy()
        x, y = pos
        half = max(8, int((crop_size * scale) / 2))
        cv2.line(canvas, (x - 26, y), (x + 26, y), (0, 255, 0), 2)
        cv2.line(canvas, (x, y - 26), (x, y + 26), (0, 255, 0), 2)
        cv2.rectangle(canvas, (x - half, y - half), (x + half, y + half), (0, 255, 255), 2)
        cv2.putText(canvas, "Move cross to exact button center and left click", (24, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 255, 255), 2)
        cv2.putText(canvas, "Esc cancel", (24, 68), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (0, 255, 255), 2)
        return canvas

    def on_mouse(event, x, y, flags, param):
        pos[0], pos[1] = x, y
        if event == cv2.EVENT_LBUTTONDOWN:
            clicked[0] = True

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, display.shape[1], display.shape[0])
    cv2.setMouseCallback(win, on_mouse)
    cancelled = False
    while True:
        cv2.imshow(win, draw_canvas())
        key = cv2.waitKey(20) & 0xFF
        if clicked[0]:
            break
        if key == 27:
            cancelled = True
            break
    cv2.destroyWindow(win)
    if cancelled:
        return None

    cx = int(pos[0] / scale)
    cy = int(pos[1] / scale)
    half = max(4, int(crop_size // 2))
    x1 = max(0, cx - half)
    y1 = max(0, cy - half)
    x2 = min(img.shape[1], cx + half)
    y2 = min(img.shape[0], cy + half)
    crop = img[y1:y2, x1:x2]
    if crop.size == 0:
        raise RuntimeError("Template crop is empty")
    target_dir = profile_template_dir(profile_id, template_type)
    name = f"{template_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    path = target_dir / name
    cv2.imwrite(str(path), crop)
    save_context_image(f"template_context_{template_type}", img)
    return path


def save_rectangle_template_to_folder(target_dir: Path, prefix: str) -> Path | None:
    img, _desktop = capture_desktop()
    display, scale = fit_for_display(img)
    base = display.copy()
    rect = None
    drawing = False
    start = None
    current = None
    win = f"Capture {prefix} template by rectangle"

    def draw_canvas():
        canvas = base.copy()
        lines = [
            f"Drag a rectangle around the {prefix} icon",
            "Everything inside the rectangle will be saved as a template",
            "Enter save    Esc cancel",
        ]
        y = 30
        for line in lines:
            cv2.putText(canvas, line, (24, y), cv2.FONT_HERSHEY_SIMPLEX, 0.68, (0, 255, 255), 2)
            y += 32
        r = current or rect
        if r:
            x1, y1, x2, y2 = r
            cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 3)
        return canvas

    def on_mouse(event, x, y, flags, param):
        nonlocal drawing, start, current, rect
        if event == cv2.EVENT_LBUTTONDOWN:
            drawing = True
            start = (x, y)
            current = (x, y, x, y)
        elif event == cv2.EVENT_MOUSEMOVE and drawing and start:
            x1, y1 = start
            current = (min(x1, x), min(y1, y), max(x1, x), max(y1, y))
        elif event == cv2.EVENT_LBUTTONUP and drawing and start:
            drawing = False
            x1, y1 = start
            r = (min(x1, x), min(y1, y), max(x1, x), max(y1, y))
            if r[2] - r[0] >= 8 and r[3] - r[1] >= 8:
                rect = r
            current = None
            start = None

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, display.shape[1], display.shape[0])
    cv2.setMouseCallback(win, on_mouse)
    saved = False
    while True:
        cv2.imshow(win, draw_canvas())
        key = cv2.waitKey(30) & 0xFF
        if key in (13, 10):
            saved = True
            break
        if key == 27:
            break
    cv2.destroyWindow(win)
    if not saved or rect is None:
        return None
    x1, y1, x2, y2 = rect
    rx1 = int(x1 / scale)
    ry1 = int(y1 / scale)
    rx2 = int(x2 / scale)
    ry2 = int(y2 / scale)
    crop = img[ry1:ry2, rx1:rx2]
    if crop.size == 0:
        raise RuntimeError("Template crop is empty")
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    cv2.imwrite(str(path), crop)
    save_context_image(f"template_context_{prefix}", img)
    return path


def save_global_rectangle_template(template_type: str) -> Path | None:
    return save_rectangle_template_to_folder(global_template_dir(template_type), f"global_{template_type}")
