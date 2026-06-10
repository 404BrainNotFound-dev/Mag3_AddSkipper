from __future__ import annotations
import time
import pyautogui

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = True

class MouseController:
    def __init__(self) -> None:
        self.last_click_time = 0.0

    def click(self, x: int, y: int, cooldown: float = 0.0) -> bool:
        now = time.time()
        if cooldown > 0 and now - self.last_click_time < cooldown:
            return False
        pyautogui.click(int(x), int(y))
        self.last_click_time = time.time()
        return True

    def press_key(self, key: str) -> None:
        pyautogui.press(key)
