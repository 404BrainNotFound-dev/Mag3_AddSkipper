from __future__ import annotations
import time
import threading

class EmergencyHotkey:
    def __init__(self, callback, presses: int = 3, window_seconds: float = 1.2):
        self.callback = callback
        self.presses = presses
        self.window_seconds = window_seconds
        self.times = []
        self.listener = None
        self.available = False
        self.lock = threading.Lock()

    def start(self) -> bool:
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
