from __future__ import annotations
import math


def _center(match: dict) -> tuple[float, float]:
    return (float(match.get("x", 0)) + float(match.get("w", 0)) / 2.0, float(match.get("y", 0)) + float(match.get("h", 0)) / 2.0)


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


def close_to_negative(match: dict, negative_match: dict | None, max_distance: float = 70.0) -> bool:
    if not match or not negative_match:
        return False
    return _distance(_center(match), _center(negative_match)) <= max_distance


def location_bonus(match: dict, region: dict) -> tuple[float, str]:
    w = max(1, int(region.get("w", 1)))
    h = max(1, int(region.get("h", 1)))
    cx, cy = _center(match)
    x_ratio = cx / w
    y_ratio = cy / h
    if y_ratio <= 0.28 and x_ratio >= 0.66:
        return 0.08, "top right"
    if y_ratio <= 0.28 and x_ratio <= 0.34:
        return 0.06, "top left"
    if y_ratio >= 0.70 and x_ratio >= 0.60:
        return 0.04, "bottom right"
    if y_ratio >= 0.70 and 0.30 <= x_ratio <= 0.70:
        return 0.03, "bottom center"
    return 0.0, "neutral"


def size_bonus(match: dict) -> tuple[float, str]:
    w = int(match.get("w", 0))
    h = int(match.get("h", 0))
    if 8 <= w <= 72 and 8 <= h <= 72:
        return 0.04, "expected small button"
    if w > 140 or h > 140:
        return -0.08, "large risky match"
    return 0.0, "normal size"


def calculate_trust(match: dict, region: dict, settings: dict, negative_match: dict | None = None) -> dict:
    raw = float(match.get("confidence", 0.0))
    trust = raw
    reasons = [f"raw {raw:.3f}"]
    lb, lname = location_bonus(match, region)
    sb, sname = size_bonus(match)
    trust += lb
    trust += sb
    boost = float(match.get("trust_boost", 0.0))
    if boost:
        trust += boost
        reasons.append(f"trusted reference {boost:+.2f}")
    if lb:
        reasons.append(f"location {lname} {lb:+.2f}")
    if sb:
        reasons.append(f"size {sname} {sb:+.2f}")

    negative_enabled = bool(settings.get("negative_protection_enabled", True))
    blocked_by_negative = False
    if negative_enabled and negative_match and close_to_negative(match, negative_match, float(settings.get("negative_avoid_margin_pixels", 90))):
        trust -= 0.65
        blocked_by_negative = True
        reasons.append("negative template matched same area avoid")

    minimum = max(0.80, float(settings.get("minimum_trust_to_click", 0.80)))
    raw_min = max(0.80, float(settings.get("template_threshold", 0.80)))
    accepted = (not blocked_by_negative) and raw >= raw_min and trust >= minimum
    trust = max(0.0, min(1.0, trust))
    if accepted:
        reasons.append("accepted")
    else:
        reasons.append("rejected")
    return {
        "raw_confidence": raw,
        "final_trust": trust,
        "accepted": accepted,
        "reason": "; ".join(reasons),
    }
