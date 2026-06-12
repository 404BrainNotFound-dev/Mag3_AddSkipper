from __future__ import annotations
import sys
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

from paths import (
    ensure_dirs,
    PHONE_SCREENS_PATH,
    DETECTION_ZONES_PATH,
    DATA_DIR,
    FAILED_DIR,
    EVAL_DIR,
    load_json,
    save_json,
    reset_all_data,
    profile_template_dir,
    global_template_dir,
    remove_images,
    list_images,
    slugify,
)
from config_store import load_settings, save_settings, reset_settings
from profile_manager import list_profiles, create_profile, delete_profile, clear_profile_templates
from runtime_cache import RuntimeCache
from automation_engine import AutomationEngine
from selection_tools import (
    select_phone_screens,
    select_detection_zones,
    save_cross_template,
    save_global_rectangle_template,
    save_rectangle_template_to_folder,
)
from hotkey_manager import CtrlAltSStopHotkey, BackspaceTripleHotkey
from conditional_actions import load_rules, add_rule, remove_rule, clear_rules, conditional_template_dir

APP_TITLE = "mag3_addskipper v7"
BG = "#0d1117"
PANEL = "#121821"
CARD = "#171f2b"
CARD_2 = "#1b2533"
TEXT = "#eef4ff"
MUTED = "#93a4b8"
ACCENT = "#5aa9ff"
GREEN = "#2ecc71"
RED = "#ff5d5d"
AMBER = "#f5b84b"
BORDER = "#26364a"
INPUT = "#0f1620"


class ScrollFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        self.vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._on_inner)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_inner(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas(self, event):
        self.canvas.itemconfigure(self.window, width=max(event.width, 980))

    def _on_wheel(self, event):
        if self.winfo_viewable():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


class MageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.title(APP_TITLE)
        self.geometry("1240x800")
        self.minsize(1040, 680)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.settings = load_settings()
        self.cache = RuntimeCache()
        self.engine = AutomationEngine(self.cache, self.log, self.set_status, self.set_runtime_info)
        self.profile_options = []
        self.profile_display_to_id = {}
        self.screen_vars = {}

        self.configure_styles()
        self.build_ui()
        self.refresh_profiles()
        self.refresh_all_counts()
        self.refresh_screen_list()
        self.set_status("Ready")
        self.install_hotkeys()

    def configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(22, 11), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", CARD)], foreground=[("selected", TEXT)])
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT, foreground=TEXT, arrowcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT)], foreground=[("readonly", TEXT)], selectbackground=[("readonly", INPUT)], selectforeground=[("readonly", TEXT)])
        style.configure("TEntry", fieldbackground=INPUT, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER)
        style.configure("Vertical.TScrollbar", background=CARD, troughcolor=BG, arrowcolor=TEXT)
        style.configure("Horizontal.TScrollbar", background=CARD, troughcolor=BG, arrowcolor=TEXT)
        style.configure("Treeview", background=INPUT, fieldbackground=INPUT, foreground=TEXT, rowheight=26, bordercolor=BORDER)
        style.configure("Treeview.Heading", background=CARD_2, foreground=TEXT, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#25435f")], foreground=[("selected", TEXT)])

    def install_hotkeys(self):
        try:
            if hasattr(self, "ctrl_alt_s_hotkey"):
                self.ctrl_alt_s_hotkey.stop()
            if hasattr(self, "backspace_hotkey"):
                self.backspace_hotkey.stop()
        except Exception:
            pass
        enabled = bool(self.settings.get("ctrl_alt_s_toggle_enabled", self.settings.get("ctrl_alt_s_stop_enabled", True)))
        self.ctrl_alt_s_hotkey = CtrlAltSStopHotkey(lambda: self.after(0, self.toggle_automation_hotkey), enabled)
        self.ctrl_alt_s_hotkey.start()
        self.backspace_hotkey = BackspaceTripleHotkey(lambda: self.after(0, self.stop_automation), self.settings.get("stop_backspace_presses", 3), self.settings.get("stop_backspace_window_seconds", 1.2), bool(self.settings.get("backspace_emergency_enabled", False)))
        self.backspace_hotkey.start()
        self.bind_all("<Control-Alt-s>", lambda event: self.toggle_automation_hotkey())
        self.bind_all("<Control-Alt-S>", lambda event: self.toggle_automation_hotkey())

    def build_ui(self):
        root = tk.Frame(self, bg=BG)
        root.pack(fill="both", expand=True, padx=18, pady=16)
        header = tk.Frame(root, bg=BG)
        header.pack(fill="x", pady=(0, 14))
        tk.Label(header, text="mag3_addskipper", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(side="left")
        tk.Label(header, text="Local screen automation for app testing", bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(14, 0), pady=(8, 0))
        self.status_var = tk.StringVar(value="Ready")
        tk.Label(header, textvariable=self.status_var, bg=BG, fg=ACCENT, font=("Segoe UI", 10, "bold")).pack(side="right", pady=(8, 0))

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)
        self.home = tk.Frame(self.tabs, bg=BG)
        self.settings_tab = ScrollFrame(self.tabs)
        self.conditions_tab = ScrollFrame(self.tabs)
        self.tabs.add(self.home, text="Home")
        self.tabs.add(self.settings_tab, text="Settings")
        self.tabs.add(self.conditions_tab, text="Conditionals")
        self.build_home()
        self.build_settings()
        self.build_conditions()

    def clay_card(self, parent, title=None, subtitle=None, pady=10):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="x", pady=pady)
        shadow = tk.Frame(outer, bg="#070a0f")
        shadow.pack(fill="x", padx=(7, 0), pady=(7, 0))
        glow = tk.Frame(shadow, bg="#1d2a3b")
        glow.pack(fill="x", padx=(0, 4), pady=(0, 4))
        card = tk.Frame(glow, bg=CARD, highlightthickness=1, highlightbackground=BORDER, padx=22, pady=20)
        card.pack(fill="x", padx=(1, 5), pady=(1, 5))
        if title:
            tk.Label(card, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(card, text=subtitle, bg=CARD, fg=MUTED, font=("Segoe UI", 9), wraplength=1020, justify="left").pack(anchor="w", pady=(4, 10))
        return card

    def section_card(self, parent, title, subtitle=None):
        card = tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground="#1e2a3a", padx=16, pady=14)
        card.pack(fill="x", pady=8)
        tk.Label(card, text=title, bg=PANEL, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w")
        if subtitle:
            tk.Label(card, text=subtitle, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=1040, justify="left").pack(anchor="w", pady=(3, 10))
        return card

    def _mix_color(self, color, amount=0.12):
        color = color.lstrip("#")
        try:
            r = int(color[0:2], 16)
            g = int(color[2:4], 16)
            b = int(color[4:6], 16)
        except Exception:
            return CARD_2
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate_button_color(self, button, start, end, steps=5, index=0):
        if index >= steps:
            try:
                button.configure(bg=end, activebackground=end)
            except Exception:
                pass
            return
        def rgb(c):
            c = c.lstrip("#")
            return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        try:
            sr, sg, sb = rgb(start)
            er, eg, eb = rgb(end)
            t = (index + 1) / steps
            color = f"#{int(sr + (er - sr) * t):02x}{int(sg + (eg - sg) * t):02x}{int(sb + (eb - sb) * t):02x}"
            button.configure(bg=color, activebackground=color)
            button.after(18, lambda: self._animate_button_color(button, start, end, steps, index + 1))
        except Exception:
            try:
                button.configure(bg=end, activebackground=end)
            except Exception:
                pass

    def button(self, parent, text, command, color=CARD_2, fg=TEXT, width=None):
        hover = self._mix_color(color, 0.16)
        press = self._mix_color(color, 0.26)
        btn = tk.Button(
            parent,
            text=text,
            command=command,
            bg=color,
            fg=fg,
            activebackground=press,
            activeforeground=fg,
            relief="flat",
            bd=0,
            padx=22,
            pady=12,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            width=width,
            highlightthickness=1,
            highlightbackground=self._mix_color(color, 0.22),
        )
        btn._normal_color = color
        btn._hover_color = hover
        btn.bind("<Enter>", lambda _e, b=btn: self._animate_button_color(b, b.cget("bg"), b._hover_color))
        btn.bind("<Leave>", lambda _e, b=btn: self._animate_button_color(b, b.cget("bg"), b._normal_color))
        return btn

    def small_button(self, parent, text, command, color=CARD_2):
        return self.button(parent, text, command, color=color, width=None)

    def build_home(self):
        wrap = tk.Frame(self.home, bg=BG, padx=18, pady=18)
        wrap.pack(fill="both", expand=True)

        profile_card = self.clay_card(wrap, "Active app profile", "Choose the app profile before starting. The selected app name is shown clearly below.")
        row = tk.Frame(profile_card, bg=CARD)
        row.pack(fill="x", pady=(2, 8))
        tk.Label(row, text="Select app", bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(side="left", padx=(0, 10))
        self.home_profile_var = tk.StringVar()
        self.home_profile_combo = ttk.Combobox(row, textvariable=self.home_profile_var, state="readonly", width=42, font=("Segoe UI", 10))
        self.home_profile_combo.pack(side="left", padx=(0, 8))
        self.home_profile_combo.bind("<<ComboboxSelected>>", lambda e: self.on_profile_selected())
        self.button(row, "New App", self.create_profile_dialog, color="#233449").pack(side="left", padx=5)
        self.button(row, "Refresh", self.refresh_profiles, color="#233449").pack(side="left", padx=5)
        self.active_profile_var = tk.StringVar(value="No app selected")
        tk.Label(profile_card, textvariable=self.active_profile_var, bg=CARD, fg=TEXT, font=("Segoe UI", 18, "bold")).pack(anchor="w", pady=(2, 4))
        self.template_count_var = tk.StringVar(value="Templates 0")
        tk.Label(profile_card, textvariable=self.template_count_var, bg=CARD, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        run_card = self.clay_card(wrap, "Control center", "Start normal automation or enable Slow Run in Settings to watch the process at a human pace.")
        runrow = tk.Frame(run_card, bg=CARD)
        runrow.pack(fill="x")
        self.start_btn = self.button(runrow, "START AUTOMATION", self.start_automation, color="#174d33", fg="#f2fff7", width=20)
        self.start_btn.pack(side="left", padx=(0, 12))
        self.stop_btn = self.button(runrow, "STOP AUTOMATION", self.stop_automation, color="#662525", fg="#fff5f5", width=20)
        self.stop_btn.pack(side="left", padx=(0, 12))
        self.button(runrow, "Open Settings", lambda: self.tabs.select(self.settings_tab), color="#22324a", width=16).pack(side="left", padx=(0, 10))
        self.button(runrow, "Conditionals", lambda: self.tabs.select(self.conditions_tab), color="#263a55", width=16).pack(side="left")
        self.slow_status_var = tk.StringVar(value="Slow Run Off")
        tk.Label(runrow, textvariable=self.slow_status_var, bg=CARD, fg=AMBER, font=("Segoe UI", 11, "bold")).pack(side="right")

        status_card = self.clay_card(wrap, "Live status", "The tool should only act when a trusted match is found. If nothing is detected it does nothing.")
        grid = tk.Frame(status_card, bg=CARD)
        grid.pack(fill="x")
        self.current_screen_var = tk.StringVar(value="None")
        self.last_action_var = tk.StringVar(value="Waiting")
        self.last_match_var = tk.StringVar(value="None")
        self.trust_var = tk.StringVar(value="")
        self.add_status_item(grid, 0, "Current screen", self.current_screen_var)
        self.add_status_item(grid, 1, "Last action", self.last_action_var)
        self.add_status_item(grid, 2, "Last match", self.last_match_var)
        self.add_status_item(grid, 3, "Trust", self.trust_var)

        log_card = self.clay_card(wrap, "Activity log", "Recent actions and rejected matches appear here.")
        self.log_box = tk.Text(log_card, height=10, bg="#0a0f16", fg="#d9e7f7", insertbackground=TEXT, relief="flat", font=("Consolas", 10), wrap="word")
        self.log_box.pack(fill="both", expand=True)

    def add_status_item(self, parent, row, label, var):
        parent.grid_columnconfigure(1, weight=1)
        tk.Label(parent, text=label, bg=CARD, fg=MUTED, font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=5, padx=(0, 14))
        tk.Label(parent, textvariable=var, bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(row=row, column=1, sticky="w", pady=5)

    def build_settings(self):
        parent = self.settings_tab.inner
        parent.configure(padx=18, pady=18, bg=BG)

        profile = self.section_card(parent, "App profiles", "Create or select the app you want to work on. App templates stay separate per app.")
        row = tk.Frame(profile, bg=PANEL)
        row.pack(fill="x")
        tk.Label(row, text="Selected app", bg=PANEL, fg=MUTED).pack(side="left", padx=(0, 10))
        self.settings_profile_var = tk.StringVar()
        self.settings_profile_combo = ttk.Combobox(row, textvariable=self.settings_profile_var, state="readonly", width=42, font=("Segoe UI", 10))
        self.settings_profile_combo.pack(side="left", padx=(0, 8))
        self.settings_profile_combo.bind("<<ComboboxSelected>>", lambda e: self.on_profile_selected(from_settings=True))
        self.button(row, "Create App", self.create_profile_dialog, color="#22324a").pack(side="left", padx=5)
        self.button(row, "Delete App", self.delete_profile_dialog, color="#4b2530").pack(side="left", padx=5)

        screens = self.section_card(parent, "Screen setup", "Select visible phone screens and detection zones. Each enabled screen is processed in order.")
        srow = tk.Frame(screens, bg=PANEL)
        srow.pack(fill="x", pady=(0, 10))
        self.button(srow, "Select Phone Screens", self.action_select_screens, color="#22324a").pack(side="left", padx=(0, 8))
        self.button(srow, "Select Detection Zones", self.action_select_zones, color="#22324a").pack(side="left", padx=(0, 8))
        self.button(srow, "Reset Regions", self.reset_regions, color="#4b2530").pack(side="left", padx=(0, 8))
        self.screen_list_frame = tk.Frame(screens, bg=PANEL)
        self.screen_list_frame.pack(fill="x")

        templates = self.section_card(parent, "Template setup", "App templates are only for the selected app. Global templates are shared across every app.")
        tk.Label(templates, text="Selected app templates", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(2, 6))
        trow1 = tk.Frame(templates, bg=PANEL)
        trow1.pack(fill="x", pady=3)
        self.button(trow1, "Add App Close By Cross", lambda: self.action_make_app_template("close"), color="#22324a").pack(side="left", padx=(0, 8))
        self.button(trow1, "Add App Back By Cross", lambda: self.action_make_app_template("back"), color="#22324a").pack(side="left", padx=(0, 8))
        self.button(trow1, "Add App Icon By Cross", lambda: self.action_make_app_template("icon"), color="#22324a").pack(side="left", padx=(0, 8))
        self.button(trow1, "Add App Negative By Rectangle", lambda: self.action_make_app_rectangle("negative"), color="#4a3c22").pack(side="left", padx=(0, 8))
        trow2 = tk.Frame(templates, bg=PANEL)
        trow2.pack(fill="x", pady=3)
        self.button(trow2, "Remove App Close", lambda: self.remove_app_templates("close"), color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(trow2, "Remove App Back", lambda: self.remove_app_templates("back"), color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(trow2, "Remove App Icon", lambda: self.remove_app_templates("icon"), color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(trow2, "Remove App Negative", lambda: self.remove_app_templates("negative"), color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(trow2, "Remove All App Templates", lambda: self.remove_app_templates(None), color="#662525").pack(side="left", padx=(0, 8))

        tk.Label(templates, text="Global templates", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(14, 6))
        grow1 = tk.Frame(templates, bg=PANEL)
        grow1.pack(fill="x", pady=3)
        self.button(grow1, "Add Global Close By Rectangle", lambda: self.action_make_global_template("close"), color="#22324a").pack(side="left", padx=(0, 8))
        self.button(grow1, "Add Global Negative By Rectangle", lambda: self.action_make_global_template("negative"), color="#4a3c22").pack(side="left", padx=(0, 8))
        self.button(grow1, "Remove Global Close", lambda: self.remove_global_templates("close"), color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(grow1, "Remove Global Negative", lambda: self.remove_global_templates("negative"), color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(grow1, "Remove All Global Templates", lambda: self.remove_global_templates(None), color="#662525").pack(side="left", padx=(0, 8))
        self.global_count_var = tk.StringVar(value="Global templates 0")
        tk.Label(templates, textvariable=self.global_count_var, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(8, 0))

        simulation = self.section_card(parent, "Simulation and learning", "Run one detection test. Mark a result correct to copy it as a trusted global reference. Mark it wrong to delete the matched reference template.")
        simrow = tk.Frame(simulation, bg=PANEL)
        simrow.pack(fill="x")
        self.button(simrow, "Run Detection Simulation", self.run_detection_simulation, color="#22324a").pack(side="left", padx=(0, 8))
        self.button(simrow, "Mark Last Correct", self.mark_last_simulation_correct, color="#174d33").pack(side="left", padx=(0, 8))
        self.button(simrow, "Mark Last Wrong", self.mark_last_simulation_wrong, color="#662525").pack(side="left", padx=(0, 8))
        self.simulation_status_var = tk.StringVar(value="No simulation run yet")
        tk.Label(simulation, textvariable=self.simulation_status_var, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=1020, justify="left").pack(anchor="w", pady=(8, 0))

        runtime = self.section_card(parent, "Runtime settings", "These settings control detection speed and safety.")
        grid = tk.Frame(runtime, bg=PANEL)
        grid.pack(fill="x")
        self.threshold_var = tk.DoubleVar(value=float(self.settings.get("template_threshold", 0.80)))
        self.min_trust_var = tk.DoubleVar(value=float(self.settings.get("minimum_trust_to_click", 0.80)))
        self.scan_delay_var = tk.DoubleVar(value=float(self.settings.get("scan_delay_seconds", 0.02)))
        self.screen_check_var = tk.DoubleVar(value=float(self.settings.get("screen_check_seconds", 3.0)))
        self.click_cooldown_var = tk.DoubleVar(value=float(self.settings.get("click_cooldown_seconds", 0.05)))
        self.post_close_delay_var = tk.DoubleVar(value=float(self.settings.get("post_close_click_delay_seconds", 0.12)))
        self.conditional_threshold_var = tk.DoubleVar(value=float(self.settings.get("conditional_threshold", 0.80)))
        self.speed_profile_var = tk.StringVar(value=str(self.settings.get("speed_profile", "human")))
        self.speed_level_var = tk.DoubleVar(value=float(self.settings.get("speed_level", 3)))
        self.auto_launch_var = tk.BooleanVar(value=bool(self.settings.get("auto_launch_app_icon", True)))
        self.save_failed_var = tk.BooleanVar(value=bool(self.settings.get("save_failed_detections", True)))
        self.negative_var = tk.BooleanVar(value=bool(self.settings.get("negative_protection_enabled", True)))
        self.slow_run_var = tk.BooleanVar(value=bool(self.settings.get("slow_run_enabled", False)))
        self.ctrl_alt_s_var = tk.BooleanVar(value=bool(self.settings.get("ctrl_alt_s_toggle_enabled", self.settings.get("ctrl_alt_s_stop_enabled", True))))
        self.conditional_enabled_var = tk.BooleanVar(value=bool(self.settings.get("conditional_actions_enabled", True)))
        tk.Label(grid, text="Speed profile", bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).grid(row=0, column=0, sticky="w", pady=7, padx=(0, 12))
        speed_combo = ttk.Combobox(grid, textvariable=self.speed_profile_var, state="readonly", values=["baby", "slow_human", "human", "fast_human", "computer", "custom"], width=24)
        speed_combo.grid(row=0, column=1, sticky="w", pady=7)
        self.add_slider(grid, 1, "Speed sub level", self.speed_level_var, 1, 5, 1, "1 safest and slowest inside the preset 5 fastest")
        self.add_slider(grid, 2, "Close match sensitivity", self.threshold_var, 0.80, 1.00, 0.01, "Higher means stricter close matching")
        self.add_slider(grid, 3, "Minimum trust to click", self.min_trust_var, 0.80, 1.00, 0.01, "Clicks only happen at or above this trust")
        self.add_slider(grid, 4, "Seconds to check each screen", self.screen_check_var, 0.50, 8.00, 0.10, "Default 3 seconds")
        self.add_slider(grid, 5, "Custom scan delay", self.scan_delay_var, 0.00, 0.50, 0.01, "Used when speed profile is custom")
        self.add_slider(grid, 6, "Custom click cooldown", self.click_cooldown_var, 0.18, 1.50, 0.01, "Used when speed profile is custom")
        self.add_slider(grid, 7, "Custom after click delay", self.post_close_delay_var, 0.00, 2.00, 0.05, "Used when speed profile is custom")
        self.add_slider(grid, 8, "Conditional image sensitivity", self.conditional_threshold_var, 0.80, 1.00, 0.01, "Trigger and target must pass this value")
        self.add_check(grid, 9, "Auto launch selected app by icon", self.auto_launch_var)
        self.add_check(grid, 10, "Save failed detection screenshots", self.save_failed_var)
        self.add_check(grid, 11, "Use negative templates for protection", self.negative_var)
        self.add_check(grid, 12, "Enable Slow Run", self.slow_run_var)
        self.add_check(grid, 13, "Ctrl Alt S toggles Start and Stop", self.ctrl_alt_s_var)
        self.add_check(grid, 14, "Enable conditional actions", self.conditional_enabled_var)
        self.button(grid, "Save Runtime Settings", self.save_all_settings, color="#174d33").grid(row=15, column=0, sticky="w", pady=(12, 0))

        recovery = self.section_card(parent, "Recovery settings", "Recovery is disabled by default so the app does nothing when no trusted match is found.")
        rgrid = tk.Frame(recovery, bg=PANEL)
        rgrid.pack(fill="x")
        self.recovery_enabled_var = tk.BooleanVar(value=bool(self.settings.get("inactivity_recovery_enabled", False)))
        self.recovery_var = tk.StringVar(value=str(self.settings.get("inactivity_recovery_action", "none")))
        self.idle_cycles_var = tk.DoubleVar(value=float(self.settings.get("inactivity_cycles", 3)))
        self.add_check(rgrid, 0, "Enable inactivity recovery", self.recovery_enabled_var)
        self.add_slider(rgrid, 1, "Idle cycles before recovery", self.idle_cycles_var, 1, 8, 1, "Default 3 cycles")
        tk.Label(rgrid, text="Recovery action", bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).grid(row=2, column=0, sticky="w", pady=7, padx=(0, 12))
        combo = ttk.Combobox(rgrid, textvariable=self.recovery_var, state="readonly", values=["none", "back_template", "press_key:esc", "press_key:backspace"], width=24)
        combo.grid(row=2, column=1, sticky="w", pady=7)

        danger = self.section_card(parent, "Reset", "Use this only when you want to delete profiles templates regions screenshots and settings.")
        self.button(danger, "Reset Everything", self.reset_everything, color="#662525").pack(anchor="w")

    def build_conditions(self):
        parent = self.conditions_tab.inner
        parent.configure(padx=18, pady=18, bg=BG)
        intro = self.section_card(parent, "Conditional actions", "Create rules in the form if this trigger image is visible then click this target image. These rules are separate from normal close detection and belong to the selected app profile.")
        row = tk.Frame(intro, bg=PANEL)
        row.pack(fill="x", pady=(0, 10))
        self.button(row, "Add Trigger Then Target Rule", self.add_conditional_rule_dialog, color="#22324a").pack(side="left", padx=(0, 8))
        self.button(row, "Remove Selected Rule", self.remove_selected_conditional_rule, color="#4b2530").pack(side="left", padx=(0, 8))
        self.button(row, "Remove All Rules", self.remove_all_conditional_rules, color="#662525").pack(side="left", padx=(0, 8))
        helper = (
            "Step 1 capture the trigger image. Step 2 capture the target image to click. "
            "When the trigger appears anywhere inside an enabled phone screen the engine searches the same screenshot for the target and clicks only if both pass the trust threshold."
        )
        tk.Label(intro, text=helper, bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=1080, justify="left").pack(anchor="w", pady=(0, 10))
        self.conditional_tree = ttk.Treeview(intro, columns=("name", "trigger", "target", "enabled"), show="headings", height=9)
        self.conditional_tree.heading("name", text="Rule")
        self.conditional_tree.heading("trigger", text="If this image appears")
        self.conditional_tree.heading("target", text="Then click this image")
        self.conditional_tree.heading("enabled", text="Enabled")
        self.conditional_tree.column("name", width=220, anchor="w")
        self.conditional_tree.column("trigger", width=320, anchor="w")
        self.conditional_tree.column("target", width=320, anchor="w")
        self.conditional_tree.column("enabled", width=90, anchor="center")
        self.conditional_tree.pack(fill="x", pady=(4, 0))
        details = self.section_card(parent, "How conditionals behave", "Conditionals do not make random clicks. If the trigger is missing the rule does nothing. If the target is missing the rule does nothing. Negative templates can still block the click.")
        tk.Label(details, text="Use this for specific app screens where one visual state should lead to one specific visual click target.", bg=PANEL, fg=TEXT, font=("Segoe UI", 10)).pack(anchor="w")

    def add_labeled_entry(self, parent, row, label, var, hint=""):
        tk.Label(parent, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=7, padx=(0, 12))
        ttk.Entry(parent, textvariable=var, width=16).grid(row=row, column=1, sticky="w", pady=7)
        if hint:
            tk.Label(parent, text=hint, bg=PANEL, fg="#7f8fa3", font=("Segoe UI", 9)).grid(row=row, column=2, sticky="w", pady=7, padx=(12, 0))

    def add_slider(self, parent, row, label, var, minimum, maximum, step, hint=""):
        tk.Label(parent, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).grid(row=row, column=0, sticky="w", pady=8, padx=(0, 12))
        holder = tk.Frame(parent, bg=PANEL)
        holder.grid(row=row, column=1, sticky="ew", pady=8)
        parent.grid_columnconfigure(1, weight=1)
        value_var = tk.StringVar()
        def format_value(value):
            value = round(float(value) / step) * step
            if step >= 1:
                return str(int(round(value)))
            if step >= 0.1:
                return f"{value:.1f}"
            return f"{value:.2f}"
        def on_change(value):
            value = round(float(value) / step) * step
            var.set(value)
            value_var.set(format_value(value))
        scale = ttk.Scale(holder, from_=minimum, to=maximum, variable=var, command=on_change)
        scale.pack(side="left", fill="x", expand=True)
        value_var.set(format_value(var.get()))
        tk.Label(holder, textvariable=value_var, bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold"), width=6).pack(side="left", padx=(10, 0))
        if hint:
            tk.Label(parent, text=hint, bg=PANEL, fg="#7f8fa3", font=("Segoe UI", 9)).grid(row=row, column=2, sticky="w", pady=8, padx=(12, 0))

    def add_check(self, parent, row, text, var):
        cb = tk.Checkbutton(parent, text=text, variable=var, bg=PANEL, fg=TEXT, selectcolor=INPUT, activebackground=PANEL, activeforeground=TEXT, font=("Segoe UI", 10))
        cb.grid(row=row, column=0, columnspan=3, sticky="w", pady=5)
        return cb

    def get_selected_profile_id(self) -> str:
        display = self.home_profile_var.get() or self.settings_profile_var.get()
        return self.profile_display_to_id.get(display) or self.settings.get("current_profile_id", "default_app")

    def refresh_profiles(self):
        profiles = list_profiles()
        self.profile_options = [p["name"] for p in profiles]
        self.profile_display_to_id = {p["name"]: p["profile_id"] for p in profiles}
        for combo in [getattr(self, "home_profile_combo", None), getattr(self, "settings_profile_combo", None)]:
            if combo:
                combo["values"] = self.profile_options
        current = self.settings.get("current_profile_id", "default_app")
        display = None
        for p in profiles:
            if p["profile_id"] == current:
                display = p["name"]
                break
        if display is None and profiles:
            display = profiles[0]["name"]
            self.settings["current_profile_id"] = profiles[0]["profile_id"]
            save_settings(self.settings)
        if display:
            self.home_profile_var.set(display)
            self.settings_profile_var.set(display)
            self.active_profile_var.set(display)
        self.refresh_all_counts()

    def on_profile_selected(self, from_settings=False):
        var = self.settings_profile_var if from_settings else self.home_profile_var
        display = var.get()
        pid = self.profile_display_to_id.get(display)
        if pid:
            self.settings["current_profile_id"] = pid
            save_settings(self.settings)
            self.home_profile_var.set(display)
            self.settings_profile_var.set(display)
            self.active_profile_var.set(display)
            self.cache.clear()
            self.refresh_all_counts()
            self.refresh_conditional_rules()
            self.log(f"Selected app profile {display}")

    def create_profile_dialog(self):
        name = simpledialog.askstring("Create App Profile", "Enter app name", parent=self)
        if not name:
            return
        profile = create_profile(name)
        self.settings["current_profile_id"] = profile["profile_id"]
        save_settings(self.settings)
        self.refresh_profiles()
        self.log(f"Created app profile {profile['name']}")

    def delete_profile_dialog(self):
        pid = self.get_selected_profile_id()
        if not messagebox.askyesno("Delete App", "Delete selected app profile and its templates"):
            return
        delete_profile(pid)
        self.settings["current_profile_id"] = "default_app"
        save_settings(self.settings)
        self.cache.clear()
        self.refresh_profiles()
        self.log("Selected app profile deleted")

    def save_all_settings(self):
        try:
            self.settings["template_threshold"] = max(0.80, float(self.threshold_var.get()))
            self.settings["minimum_trust_to_click"] = max(0.80, float(self.min_trust_var.get()))
            self.threshold_var.set(self.settings["template_threshold"])
            self.min_trust_var.set(self.settings["minimum_trust_to_click"])
            self.settings["speed_profile"] = str(self.speed_profile_var.get() or "human")
            self.settings["speed_level"] = int(round(float(self.speed_level_var.get())))
            self.settings["scan_delay_seconds"] = max(0.0, float(self.scan_delay_var.get()))
            self.settings["screen_check_seconds"] = max(0.1, float(self.screen_check_var.get()))
            self.settings["click_cooldown_seconds"] = max(0.18, float(self.click_cooldown_var.get()))
            self.settings["post_close_click_delay_seconds"] = max(0.0, float(self.post_close_delay_var.get()))
            self.settings["auto_launch_app_icon"] = bool(self.auto_launch_var.get())
            self.settings["save_failed_detections"] = bool(self.save_failed_var.get())
            self.settings["negative_protection_enabled"] = bool(self.negative_var.get())
            self.settings["slow_run_enabled"] = bool(self.slow_run_var.get())
            self.settings["ctrl_alt_s_toggle_enabled"] = bool(self.ctrl_alt_s_var.get())
            self.settings["conditional_actions_enabled"] = bool(self.conditional_enabled_var.get())
            self.settings["conditional_threshold"] = max(0.80, float(self.conditional_threshold_var.get()))
            self.conditional_threshold_var.set(self.settings["conditional_threshold"])
            self.settings["inactivity_recovery_enabled"] = bool(self.recovery_enabled_var.get())
            self.settings["inactivity_recovery_action"] = self.recovery_var.get()
            self.settings["inactivity_cycles"] = int(round(float(self.idle_cycles_var.get())))
            save_settings(self.settings)
            self.slow_status_var.set("Slow Run On" if self.settings["slow_run_enabled"] else "Slow Run Off")
            self.install_hotkeys()
            self.log("Settings saved")
        except ValueError as exc:
            messagebox.showerror("Invalid Setting", str(exc))

    def refresh_all_counts(self):
        self.refresh_template_counts()
        self.refresh_global_counts()
        self.refresh_conditional_rules()
        if hasattr(self, "slow_status_var"):
            self.slow_status_var.set("Slow Run On" if bool(self.settings.get("slow_run_enabled", False)) else "Slow Run Off")

    def refresh_template_counts(self):
        if not hasattr(self, "template_count_var"):
            return
        pid = self.get_selected_profile_id()
        counts = {}
        for typ in ["close", "back", "icon", "negative", "conditional_trigger", "conditional_target"]:
            counts[typ] = len(list_images(profile_template_dir(pid, typ)))
        self.template_count_var.set(
            f"App templates  close {counts['close']}  back {counts['back']}  icon {counts['icon']}  negative {counts['negative']}  condition triggers {counts['conditional_trigger']}  condition targets {counts['conditional_target']}"
        )

    def refresh_global_counts(self):
        if not hasattr(self, "global_count_var"):
            return
        close_count = len(list_images(global_template_dir("close")))
        neg_count = len(list_images(global_template_dir("negative")))
        self.global_count_var.set(f"Global templates  close {close_count}  negative {neg_count}")

    def refresh_conditional_rules(self):
        if not hasattr(self, "conditional_tree"):
            return
        for item in self.conditional_tree.get_children():
            self.conditional_tree.delete(item)
        pid = self.get_selected_profile_id()
        for rule in load_rules(pid):
            self.conditional_tree.insert(
                "",
                "end",
                iid=rule.get("rule_id"),
                values=(
                    rule.get("name", ""),
                    Path(rule.get("trigger_template", "")).name,
                    Path(rule.get("target_template", "")).name,
                    "Yes" if rule.get("enabled", True) else "No",
                ),
            )

    def refresh_screen_list(self):
        if not hasattr(self, "screen_list_frame"):
            return
        for child in self.screen_list_frame.winfo_children():
            child.destroy()
        screens = load_json(PHONE_SCREENS_PATH, {"screens": []}).get("screens", [])
        self.screen_vars.clear()
        if not screens:
            tk.Label(self.screen_list_frame, text="No screens selected", bg=PANEL, fg=MUTED).pack(anchor="w")
            return
        for screen in screens:
            var = tk.BooleanVar(value=bool(screen.get("enabled", True)))
            self.screen_vars[screen.get("screen_id")] = var
            cb = tk.Checkbutton(self.screen_list_frame, text=screen.get("screen_name", screen.get("screen_id")), variable=var, command=self.save_screen_enabled, bg=PANEL, fg=TEXT, selectcolor=INPUT, activebackground=PANEL, activeforeground=TEXT)
            cb.pack(anchor="w", pady=2)

    def save_screen_enabled(self):
        data = load_json(PHONE_SCREENS_PATH, {"screens": []})
        for screen in data.get("screens", []):
            sid = screen.get("screen_id")
            if sid in self.screen_vars:
                screen["enabled"] = bool(self.screen_vars[sid].get())
        save_json(PHONE_SCREENS_PATH, data)
        self.log("Screen enabled states saved")

    def hide_for_selection(self, action):
        self.withdraw()
        self.update_idletasks()
        try:
            result = action()
            return result
        finally:
            self.deiconify()
            self.lift()
            self.focus_force()

    def action_select_screens(self):
        try:
            screens = self.hide_for_selection(select_phone_screens)
            self.refresh_screen_list()
            self.log(f"Selected {len(screens)} phone screens")
        except Exception as exc:
            messagebox.showerror("Screen Selection Failed", str(exc))

    def action_select_zones(self):
        try:
            zones = self.hide_for_selection(select_detection_zones)
            self.log(f"Selected {len(zones)} detection zones")
        except Exception as exc:
            messagebox.showerror("Detection Zone Failed", str(exc))

    def action_make_app_template(self, template_type: str):
        pid = self.get_selected_profile_id()
        crop_size = int(self.settings.get(f"{template_type}_template_crop_size", self.settings.get("close_template_crop_size", 32)))
        if template_type == "back":
            crop_size = int(self.settings.get("back_template_crop_size", 40))
        if template_type == "icon":
            crop_size = int(self.settings.get("icon_template_crop_size", 96))
        try:
            path = self.hide_for_selection(lambda: save_cross_template(pid, template_type, crop_size))
            if path:
                self.cache.invalidate_templates()
                self.refresh_all_counts()
                self.log(f"Saved app {template_type} template {path.name}")
        except Exception as exc:
            messagebox.showerror("Template Failed", str(exc))

    def action_make_app_rectangle(self, template_type: str):
        pid = self.get_selected_profile_id()
        try:
            folder = profile_template_dir(pid, template_type)
            path = self.hide_for_selection(lambda: save_rectangle_template_to_folder(folder, f"app_{template_type}"))
            if path:
                self.cache.invalidate_templates()
                self.refresh_all_counts()
                self.log(f"Saved app {template_type} template {path.name}")
        except Exception as exc:
            messagebox.showerror("Template Failed", str(exc))

    def action_make_global_template(self, template_type: str):
        try:
            path = self.hide_for_selection(lambda: save_global_rectangle_template(template_type))
            if path:
                self.cache.invalidate_templates()
                self.refresh_all_counts()
                self.log(f"Saved global {template_type} template {path.name}")
        except Exception as exc:
            messagebox.showerror("Global Template Failed", str(exc))

    def remove_app_templates(self, template_type: str | None):
        pid = self.get_selected_profile_id()
        label = template_type or "all"
        if not messagebox.askyesno("Remove Templates", f"Remove {label} app templates for selected app"):
            return
        removed = clear_profile_templates(pid, template_type)
        self.cache.invalidate_templates()
        self.refresh_all_counts()
        self.log(f"Removed {removed} app template files")

    def remove_global_templates(self, template_type: str | None):
        label = template_type or "all"
        if not messagebox.askyesno("Remove Global Templates", f"Remove {label} global templates"):
            return
        removed = 0
        types = ["close", "skip", "back", "playstore", "negative"] if template_type is None else [template_type]
        for typ in types:
            removed += remove_images(global_template_dir(typ))
        self.cache.invalidate_templates()
        self.refresh_all_counts()
        self.log(f"Removed {removed} global template files")

    def add_conditional_rule_dialog(self):
        pid = self.get_selected_profile_id()
        name = simpledialog.askstring("Conditional Rule", "Rule name", parent=self)
        if not name:
            return
        try:
            messagebox.showinfo("Capture Trigger", "First select the image that should activate this rule")
            trigger_folder = conditional_template_dir(pid, "trigger")
            trigger_prefix = "trigger_" + slugify(name)
            trigger_path = self.hide_for_selection(lambda: save_rectangle_template_to_folder(trigger_folder, trigger_prefix))
            if not trigger_path:
                return
            messagebox.showinfo("Capture Target", "Now select the image that should be clicked when the trigger is visible")
            target_folder = conditional_template_dir(pid, "target")
            target_prefix = "target_" + slugify(name)
            target_path = self.hide_for_selection(lambda: save_rectangle_template_to_folder(target_folder, target_prefix))
            if not target_path:
                try:
                    trigger_path.unlink(missing_ok=True)
                except Exception:
                    pass
                return
            add_rule(pid, name, trigger_path, target_path, "click_target_template")
            self.cache.invalidate_templates()
            self.refresh_all_counts()
            self.log(f"Added conditional rule {name} trigger {trigger_path.name} target {target_path.name}")
        except Exception as exc:
            messagebox.showerror("Conditional Rule Failed", str(exc))

    def remove_selected_conditional_rule(self):
        if not hasattr(self, "conditional_tree"):
            return
        selected = self.conditional_tree.selection()
        if not selected:
            messagebox.showinfo("No Selection", "Select a condition rule first")
            return
        if not messagebox.askyesno("Remove Rule", "Remove selected condition rule and its template"):
            return
        pid = self.get_selected_profile_id()
        removed = 0
        for rule_id in selected:
            removed += remove_rule(pid, str(rule_id), True)
        self.cache.invalidate_templates()
        self.refresh_all_counts()
        self.log(f"Removed {removed} condition rule")

    def remove_all_conditional_rules(self):
        if not messagebox.askyesno("Remove Condition Rules", "Remove all condition rules for selected app"):
            return
        pid = self.get_selected_profile_id()
        removed = clear_rules(pid, True)
        self.cache.invalidate_templates()
        self.refresh_all_counts()
        self.log(f"Removed {removed} condition rules")

    def _enabled_screens_for_simulation(self):
        data = load_json(PHONE_SCREENS_PATH, {"screens": []})
        return [s for s in data.get("screens", []) if s.get("enabled", True)]

    def _simulation_candidate(self):
        pid = self.get_selected_profile_id()
        self.save_all_settings()
        settings = self.settings.copy()
        folders = self.engine._close_template_folders(pid)
        negatives = self.engine._negative_template_folders(pid)
        best = None
        best_img = None
        best_screen = None
        for screen in self._enabled_screens_for_simulation():
            zone = self.engine._zone_for_screen(screen)
            match, image = self.engine.vision.match_region(zone, folders, settings, negatives)
            if not match:
                continue
            if best is None or float(match.get("final_trust", 0)) > float(best.get("final_trust", 0)):
                best = match
                best_img = image
                best_screen = screen
        return best, best_img, best_screen

    def _save_simulation_preview(self, match, image, screen):
        import cv2
        from datetime import datetime
        EVAL_DIR.mkdir(parents=True, exist_ok=True)
        preview = image.copy()
        x1 = int(match.get("x", 0))
        y1 = int(match.get("y", 0))
        x2 = x1 + int(match.get("w", 0))
        y2 = y1 + int(match.get("h", 0))
        cv2.rectangle(preview, (x1, y1), (x2, y2), (0, 255, 0), 2)
        label = f"{match.get('template')} trust {float(match.get('final_trust', 0)):.3f}"
        cv2.putText(preview, label, (max(5, x1), max(24, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
        path = EVAL_DIR / f"simulation_{screen.get('screen_id', 'screen')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        cv2.imwrite(str(path), preview)
        return path

    def run_detection_simulation(self):
        try:
            match, image, screen = self._simulation_candidate()
            if not match:
                self.simulation_status_var.set("No close or cross candidate found on enabled screens")
                self.log("Simulation found no candidate")
                return
            path = self._save_simulation_preview(match, image, screen)
            self.last_simulation_candidate = {"match": match, "preview": str(path), "screen": screen}
            text = (
                f"Screen {screen.get('screen_name')}  Template {match.get('template')}  "
                f"Score {float(match.get('confidence', 0)):.3f}  Trust {float(match.get('final_trust', 0)):.3f}  "
                f"Accepted {match.get('accepted')}  Preview {path.name}"
            )
            self.simulation_status_var.set(text)
            self.log("Simulation result " + text)
            try:
                import os
                if sys.platform.startswith("win"):
                    os.startfile(str(path))
            except Exception:
                pass
            answer = messagebox.askyesnocancel("Rate Detection", "Was this close or cross detection correct")
            if answer is True:
                self.mark_last_simulation_correct()
            elif answer is False:
                self.mark_last_simulation_wrong()
        except Exception as exc:
            messagebox.showerror("Simulation Failed", str(exc))

    def mark_last_simulation_correct(self):
        data = getattr(self, "last_simulation_candidate", None)
        if not data:
            messagebox.showinfo("No Simulation", "Run a simulation first")
            return
        match = data.get("match", {})
        source = Path(str(match.get("template_path", "")))
        if not source.exists():
            messagebox.showerror("Missing Template", "The matched template file no longer exists")
            return
        target_dir = global_template_dir("close")
        target_dir.mkdir(parents=True, exist_ok=True)
        from datetime import datetime
        target = target_dir / f"trusted_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{source.name}"
        shutil.copy2(source, target)
        self.cache.invalidate_templates()
        self.refresh_all_counts()
        self.simulation_status_var.set(f"Marked correct and copied to global trusted template {target.name}")
        self.log(f"Simulation correct copied {source.name} to {target.name}")

    def mark_last_simulation_wrong(self):
        data = getattr(self, "last_simulation_candidate", None)
        if not data:
            messagebox.showinfo("No Simulation", "Run a simulation first")
            return
        match = data.get("match", {})
        source = Path(str(match.get("template_path", "")))
        if not source.exists():
            self.simulation_status_var.set("Wrong result noted but template file was already missing")
            return
        if not messagebox.askyesno("Delete Reference", f"Delete wrong reference template {source.name}"):
            return
        source.unlink(missing_ok=True)
        self.cache.invalidate_templates()
        self.refresh_all_counts()
        self.simulation_status_var.set(f"Marked wrong and deleted reference {source.name}")
        self.log(f"Simulation wrong deleted {source.name}")

    def reset_regions(self):
        if not messagebox.askyesno("Reset Regions", "Delete selected phone screens and detection zones"):
            return
        save_json(PHONE_SCREENS_PATH, {"screens": []})
        save_json(DETECTION_ZONES_PATH, {"zones": []})
        self.refresh_screen_list()
        self.log("Regions reset")

    def reset_everything(self):
        if not messagebox.askyesno("Reset Everything", "This deletes all profiles templates regions screenshots and settings. Continue"):
            return
        self.stop_automation()
        reset_all_data()
        reset_settings()
        self.settings = load_settings()
        self.cache.clear()
        self.refresh_profiles()
        self.refresh_screen_list()
        self.refresh_all_counts()
        self.log("Everything reset to default")

    def toggle_automation_hotkey(self):
        if self.engine.running:
            self.stop_automation()
            self.log("Ctrl Alt S toggle stopped automation")
        else:
            self.start_automation()
            self.log("Ctrl Alt S toggle started automation")

    def start_automation(self):
        self.save_all_settings()
        pid = self.get_selected_profile_id()
        self.cache.invalidate_templates()
        self.engine.start(pid, self.settings.copy())
        self.log("Start clicked")

    def stop_automation(self):
        self.engine.stop()
        self.set_status("Stopped")
        self.log("Stop command received")

    def set_status(self, text: str):
        if hasattr(self, "status_var"):
            self.status_var.set(text)

    def set_runtime_info(self, data: dict):
        def apply():
            if "current_screen" in data:
                self.current_screen_var.set(str(data.get("current_screen") or ""))
            if "last_action" in data:
                self.last_action_var.set(str(data.get("last_action") or ""))
            if "last_match" in data:
                self.last_match_var.set(str(data.get("last_match") or ""))
            if "trust" in data:
                self.trust_var.set(str(data.get("trust") or ""))
        try:
            self.after(0, apply)
        except Exception:
            pass

    def log(self, text: str):
        def write():
            if hasattr(self, "log_box"):
                self.log_box.insert("end", text + "\n")
                self.log_box.see("end")
        try:
            self.after(0, write)
        except Exception:
            pass

    def on_close(self):
        try:
            self.stop_automation()
            self.cache.clear()
            self.ctrl_alt_s_hotkey.stop()
            self.backspace_hotkey.stop()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = MageApp()
    app.mainloop()
