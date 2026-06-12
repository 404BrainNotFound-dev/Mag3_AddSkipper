from __future__ import annotations
import time

class MouseController:
    def __init__(self) -> None:
        self.last_click_time = 0.0
        self._pyautogui = None

    def _pyauto(self):
        if self._pyautogui is None:
            import pyautogui
            pyautogui.PAUSE = 0
            pyautogui.FAILSAFE = True
            self._pyautogui = pyautogui
        return self._pyautogui

    def click(self, x: int, y: int, cooldown: float = 0.0, pre_delay: float = 0.0, post_delay: float = 0.0, move_duration: float = 0.0) -> bool:
        now = time.time()
        if cooldown > 0 and now - self.last_click_time < cooldown:
            return False
        if pre_delay > 0:
            time.sleep(pre_delay)
        pyautogui = self._pyauto()
        if move_duration > 0:
            try:
                pyautogui.moveTo(int(x), int(y), duration=float(move_duration), tween=pyautogui.easeInOutQuad)
            except Exception:
                pyautogui.moveTo(int(x), int(y), duration=float(move_duration))
            pyautogui.click()
        else:
            pyautogui.click(int(x), int(y))
        self.last_click_time = time.time()
        if post_delay > 0:
            time.sleep(post_delay)
        return True

    def press_key(self, key: str) -> None:
        self._pyauto().press(key)
