from __future__ import annotations
import time
import threading

class BackspaceTripleHotkey:
    def __init__(self, callback, presses: int = 3, window_seconds: float = 1.2, enabled: bool = False):
        self.callback = callback
        self.presses = presses
        self.window_seconds = window_seconds
        self.enabled = enabled
        self.times = []
        self.listener = None
        self.available = False
        self.lock = threading.Lock()

    def start(self) -> bool:
        if not self.enabled:
            return False
        try:
            from pynput import keyboard
        except Exception:
            self.available = False
            return False
        def on_press(key):
            try:
                if key == keyboard.Key.backspace:
                    self.register_press()
            except Exception:
                pass
        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.daemon = True
        self.listener.start()
        self.available = True
        return True

    def register_press(self) -> None:
        if not self.enabled:
            return
        now = time.time()
        with self.lock:
            self.times = [t for t in self.times if now - t <= self.window_seconds]
            self.times.append(now)
            if len(self.times) >= self.presses:
                self.times.clear()
                self.callback()

    def stop(self) -> None:
        try:
            if self.listener:
                self.listener.stop()
        except Exception:
            pass

class CtrlAltSStopHotkey:
    def __init__(self, callback, enabled: bool = True):
        self.callback = callback
        self.enabled = enabled
        self.listener = None
        self.available = False
        self._pressed = set()
        self._lock = threading.Lock()
        self._combo_active = False

    def start(self) -> bool:
        if not self.enabled:
            return False
        try:
            from pynput import keyboard
        except Exception:
            self.available = False
            return False
        self.keyboard = keyboard
        def on_press(key):
            should_call = False
            with self._lock:
                self._pressed.add(key)
                if self._is_combo_down() and not self._combo_active:
                    self._combo_active = True
                    should_call = True
            if should_call:
                self.callback()
        def on_release(key):
            with self._lock:
                self._pressed.discard(key)
                if not self._is_combo_down():
                    self._combo_active = False
        self.listener = keyboard.Listener(on_press=on_press, on_release=on_release)
        self.listener.daemon = True
        self.listener.start()
        self.available = True
        return True

    def _is_combo_down(self) -> bool:
        keyboard = self.keyboard
        ctrl = keyboard.Key.ctrl_l in self._pressed or keyboard.Key.ctrl_r in self._pressed or keyboard.Key.ctrl in self._pressed
        alt = keyboard.Key.alt_l in self._pressed or keyboard.Key.alt_r in self._pressed or keyboard.Key.alt in self._pressed
        s_down = False
        for k in self._pressed:
            try:
                if getattr(k, "char", None) and k.char.lower() == "s":
                    s_down = True
                    break
            except Exception:
                pass
        return ctrl and alt and s_down

    def stop(self) -> None:
        try:
            if self.listener:
                self.listener.stop()
        except Exception:
            pass
