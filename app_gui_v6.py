from __future__ import annotations
import os
import sys
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path

from paths import (
    ensure_dirs,
    DATA_DIR,
    PHONE_SCREENS_PATH,
    DETECTION_ZONES_PATH,
    load_json,
    save_json,
    reset_all_data,
    profile_template_dir,
)
from config_store import load_settings, save_settings, reset_settings, DEFAULT_SETTINGS
from profile_manager import list_profiles, create_profile, delete_profile, clear_profile_templates
from runtime_cache import RuntimeCache
from automation_engine import AutomationEngine
from selection_tools import select_phone_screens, select_detection_zones, save_cross_template
from hotkey_manager import EmergencyHotkey

APP_TITLE = "mag3_addskipper V6.1"


class ScrollFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#101318")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._resize)

    def _resize(self, event):
        self.canvas.itemconfigure(self.canvas_window, width=event.width)


class MageApp(tk.Tk):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.title(APP_TITLE)
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(bg="#101318")
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.settings = load_settings()
        self.cache = RuntimeCache()
        self.engine = AutomationEngine(self.cache, self.log, self.set_status)
        self.hotkey = EmergencyHotkey(self.emergency_exit, self.settings.get("stop_backspace_presses", 3), self.settings.get("stop_backspace_window_seconds", 1.2))
        self.hotkey.start()
        self.bind("<BackSpace>", lambda e: self.hotkey.register_press())

        self.profile_options = []
        self.profile_display_to_id = {}
        self.screen_vars = {}

        self.apply_dark_style()
        self.build_ui()
        self.refresh_profiles()
        self.refresh_template_counts()
        self.refresh_screen_list()
        self.set_status("Ready")

    def apply_dark_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background="#101318")
        style.configure("Card.TFrame", background="#161b22", relief="flat")
        style.configure("TLabel", background="#101318", foreground="#e6edf3", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#101318", foreground="#8b949e", font=("Segoe UI", 9))
        style.configure("Card.TLabel", background="#161b22", foreground="#e6edf3", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#101318", foreground="#ffffff", font=("Segoe UI", 18, "bold"))
        style.configure("Section.TLabel", background="#161b22", foreground="#ffffff", font=("Segoe UI", 13, "bold"))
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8), background="#263241", foreground="#e6edf3")
        style.map("TButton", background=[("active", "#344456")])
        style.configure("Accent.TButton", background="#2f81f7", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.configure("Danger.TButton", background="#da3633", foreground="#ffffff", font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background="#101318", borderwidth=0)
        style.configure("TNotebook.Tab", background="#161b22", foreground="#8b949e", padding=(18, 10), font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", "#21262d")], foreground=[("selected", "#ffffff")])
        style.configure("TEntry", fieldbackground="#0d1117", foreground="#e6edf3", insertcolor="#e6edf3")
        style.configure("TCombobox", fieldbackground="#0d1117", background="#0d1117", foreground="#e6edf3")
        style.configure("TCheckbutton", background="#161b22", foreground="#e6edf3", font=("Segoe UI", 10))

    def build_ui(self):
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True, padx=18, pady=16)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.status_var, style="Muted.TLabel").pack(side="right", padx=8)

        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill="both", expand=True)
        self.home = ttk.Frame(self.tabs)
        self.settings_tab = ScrollFrame(self.tabs)
        self.tabs.add(self.home, text="Home")
        self.tabs.add(self.settings_tab, text="Settings")

        self.build_home()
        self.build_settings()

    def card(self, parent, title: str, desc: str | None = None):
        frame = ttk.Frame(parent, style="Card.TFrame", padding=16)
        frame.pack(fill="x", pady=8)
        ttk.Label(frame, text=title, style="Section.TLabel").pack(anchor="w")
        if desc:
            label = ttk.Label(frame, text=desc, style="Card.TLabel", wraplength=1000)
            label.pack(anchor="w", pady=(4, 10))
        else:
            ttk.Frame(frame, style="Card.TFrame", height=8).pack()
        return frame

    def build_home(self):
        container = ttk.Frame(self.home, padding=20)
        container.pack(fill="both", expand=True)

        intro = self.card(container, "Run automation", "Select the app profile you want to work on. Only templates from that app profile will be used.")
        row = ttk.Frame(intro, style="Card.TFrame")
        row.pack(fill="x", pady=6)
        ttk.Label(row, text="App profile", style="Card.TLabel").pack(side="left", padx=(0, 12))
        self.home_profile_var = tk.StringVar()
        self.home_profile_combo = ttk.Combobox(row, textvariable=self.home_profile_var, state="readonly", width=38)
        self.home_profile_combo.pack(side="left", padx=(0, 8))
        self.home_profile_combo.bind("<<ComboboxSelected>>", lambda e: self.on_profile_selected())
        ttk.Button(row, text="Refresh", command=self.refresh_profiles).pack(side="left", padx=4)
        ttk.Button(row, text="New App", command=self.create_profile_dialog).pack(side="left", padx=4)

        controls = ttk.Frame(intro, style="Card.TFrame")
        controls.pack(fill="x", pady=(14, 2))
        ttk.Button(controls, text="Start", style="Accent.TButton", command=self.start_automation).pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="Stop", command=self.stop_automation).pack(side="left", padx=(0, 10))
        ttk.Button(controls, text="Open Settings", command=lambda: self.tabs.select(self.settings_tab)).pack(side="left")

        runtime = self.card(container, "Essential runtime settings", "These are the only settings shown on Home. All other setup is inside Settings.")
        grid = ttk.Frame(runtime, style="Card.TFrame")
        grid.pack(fill="x")
        self.threshold_var = tk.StringVar(value=str(self.settings.get("template_threshold", 0.78)))
        self.scan_delay_var = tk.StringVar(value=str(self.settings.get("scan_delay_seconds", 0.01)))
        self.screen_check_var = tk.StringVar(value=str(self.settings.get("screen_check_seconds", 3.0)))
        self.idle_cycles_var = tk.StringVar(value=str(self.settings.get("inactivity_cycles", 3)))
        self.auto_launch_var = tk.BooleanVar(value=bool(self.settings.get("auto_launch_app_icon", True)))
        self.add_labeled_entry(grid, 0, "Template trust", self.threshold_var, "Example 0.78")
        self.add_labeled_entry(grid, 1, "Scan delay", self.scan_delay_var, "Example 0.01")
        self.add_labeled_entry(grid, 2, "Seconds per screen", self.screen_check_var, "Default 3")
        self.add_labeled_entry(grid, 3, "Idle cycles", self.idle_cycles_var, "Example 3")
        ttk.Checkbutton(grid, text="Auto launch selected app by icon", variable=self.auto_launch_var).grid(row=4, column=0, columnspan=3, sticky="w", pady=8)
        ttk.Button(grid, text="Save Runtime Settings", command=self.save_runtime_settings).grid(row=5, column=0, sticky="w", pady=(8, 0))

        log_card = self.card(container, "Activity log", "Recent actions and errors appear here.")
        self.log_box = tk.Text(log_card, height=12, bg="#0d1117", fg="#e6edf3", insertbackground="#e6edf3", relief="flat", font=("Consolas", 10))
        self.log_box.pack(fill="both", expand=True)

    def build_settings(self):
        parent = self.settings_tab.inner
        parent.configure(padding=18)

        profile = self.card(parent, "App setup", "Create or select the app you want to work on. Each app has its own close back and icon templates.")
        row = ttk.Frame(profile, style="Card.TFrame")
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="Selected app", style="Card.TLabel").pack(side="left", padx=(0, 12))
        self.settings_profile_var = tk.StringVar()
        self.settings_profile_combo = ttk.Combobox(row, textvariable=self.settings_profile_var, state="readonly", width=38)
        self.settings_profile_combo.pack(side="left", padx=(0, 8))
        self.settings_profile_combo.bind("<<ComboboxSelected>>", lambda e: self.on_profile_selected(from_settings=True))
        ttk.Button(row, text="Create App", command=self.create_profile_dialog).pack(side="left", padx=4)
        ttk.Button(row, text="Delete App", command=self.delete_profile_dialog).pack(side="left", padx=4)
        ttk.Button(row, text="Open Data Folder", command=self.open_data_folder).pack(side="left", padx=4)

        screens = self.card(parent, "Screen setup", "Select mobile screens once. Then select the small detection area where close buttons usually appear.")
        btns = ttk.Frame(screens, style="Card.TFrame")
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Select Mobile Screens", command=self.action_select_screens).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Select Detection Zones", command=self.action_select_zones).pack(side="left", padx=(0, 8))
        ttk.Button(btns, text="Reset Regions", command=self.reset_regions).pack(side="left", padx=(0, 8))
        self.screen_list_frame = ttk.Frame(screens, style="Card.TFrame")
        self.screen_list_frame.pack(fill="x", pady=(12, 0))

        templates = self.card(parent, "Templates for selected app", "Use cross selection for precision. Put the cross at the exact center of the close back or app icon.")
        self.template_count_var = tk.StringVar(value="Templates not loaded")
        ttk.Label(templates, textvariable=self.template_count_var, style="Card.TLabel").pack(anchor="w", pady=(0, 8))
        trow1 = ttk.Frame(templates, style="Card.TFrame")
        trow1.pack(fill="x", pady=4)
        ttk.Button(trow1, text="Add Close By Cross", command=lambda: self.action_make_template("close")).pack(side="left", padx=(0, 8))
        ttk.Button(trow1, text="Add Back By Cross", command=lambda: self.action_make_template("back")).pack(side="left", padx=(0, 8))
        ttk.Button(trow1, text="Add App Icon By Cross", command=lambda: self.action_make_template("icon")).pack(side="left", padx=(0, 8))
        trow2 = ttk.Frame(templates, style="Card.TFrame")
        trow2.pack(fill="x", pady=4)
        ttk.Button(trow2, text="Remove Close Templates", command=lambda: self.remove_templates("close")).pack(side="left", padx=(0, 8))
        ttk.Button(trow2, text="Remove Back Templates", command=lambda: self.remove_templates("back")).pack(side="left", padx=(0, 8))
        ttk.Button(trow2, text="Remove App Icon Templates", command=lambda: self.remove_templates("icon")).pack(side="left", padx=(0, 8))
        ttk.Button(trow2, text="Remove All Templates", command=lambda: self.remove_templates(None)).pack(side="left", padx=(0, 8))

        advanced = self.card(parent, "Automation settings", "Advanced settings are kept here so the Home screen stays simple.")
        grid = ttk.Frame(advanced, style="Card.TFrame")
        grid.pack(fill="x")
        self.click_cooldown_var = tk.StringVar(value=str(self.settings.get("click_cooldown_seconds", 0.05)))
        self.early_accept_var = tk.StringVar(value=str(self.settings.get("early_accept_threshold", 0.92)))
        self.post_close_delay_var = tk.StringVar(value=str(self.settings.get("post_close_click_delay_seconds", 0.12)))
        self.app_launch_wait_var = tk.StringVar(value=str(self.settings.get("app_launch_wait_seconds", 0.45)))
        self.close_crop_var = tk.StringVar(value=str(self.settings.get("close_template_crop_size", 36)))
        self.back_crop_var = tk.StringVar(value=str(self.settings.get("back_template_crop_size", 44)))
        self.icon_crop_var = tk.StringVar(value=str(self.settings.get("icon_template_crop_size", 96)))
        self.recovery_var = tk.StringVar(value=str(self.settings.get("inactivity_recovery_action", "back_template")))
        self.add_labeled_entry(grid, 0, "Click cooldown", self.click_cooldown_var, "Example 0.05")
        self.add_labeled_entry(grid, 1, "Early accept score", self.early_accept_var, "Example 0.92")
        self.add_labeled_entry(grid, 2, "After close delay", self.post_close_delay_var, "Example 0.12")
        self.add_labeled_entry(grid, 3, "App launch wait", self.app_launch_wait_var, "Example 0.45")
        self.add_labeled_entry(grid, 4, "Close crop size", self.close_crop_var, "Default 36")
        self.add_labeled_entry(grid, 5, "Back crop size", self.back_crop_var, "Default 44")
        self.add_labeled_entry(grid, 6, "Icon crop size", self.icon_crop_var, "Pixels")
        ttk.Label(grid, text="Idle recovery", style="Card.TLabel").grid(row=7, column=0, sticky="w", pady=6)
        ttk.Combobox(grid, textvariable=self.recovery_var, state="readonly", values=["back_template", "none", "press_key:esc", "press_key:backspace"], width=24).grid(row=7, column=1, sticky="w", pady=6)
        ttk.Button(grid, text="Save All Settings", command=self.save_all_settings).grid(row=8, column=0, sticky="w", pady=(12, 0))

        danger = self.card(parent, "Reset", "This deletes all app profiles templates regions screenshots and custom settings. The app returns to default empty setup.")
        ttk.Button(danger, text="Reset Everything", style="Danger.TButton", command=self.reset_everything).pack(anchor="w")

    def add_labeled_entry(self, parent, row, label, var, hint=""):
        ttk.Label(parent, text=label, style="Card.TLabel").grid(row=row, column=0, sticky="w", pady=6, padx=(0, 12))
        ttk.Entry(parent, textvariable=var, width=18).grid(row=row, column=1, sticky="w", pady=6)
        if hint:
            ttk.Label(parent, text=hint, style="Card.TLabel").grid(row=row, column=2, sticky="w", pady=6, padx=(12, 0))

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
        self.refresh_template_counts()

    def on_profile_selected(self, from_settings=False):
        var = self.settings_profile_var if from_settings else self.home_profile_var
        display = var.get()
        pid = self.profile_display_to_id.get(display)
        if pid:
            self.settings["current_profile_id"] = pid
            save_settings(self.settings)
            self.home_profile_var.set(display)
            self.settings_profile_var.set(display)
            self.cache.clear()
            self.refresh_template_counts()
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

    def save_runtime_settings(self):
        try:
            self.settings["template_threshold"] = float(self.threshold_var.get())
            self.settings["scan_delay_seconds"] = float(self.scan_delay_var.get())
            self.settings["screen_check_seconds"] = float(self.screen_check_var.get())
            self.settings["inactivity_cycles"] = int(float(self.idle_cycles_var.get()))
            self.settings["auto_launch_app_icon"] = bool(self.auto_launch_var.get())
            save_settings(self.settings)
            self.log("Runtime settings saved")
        except ValueError as e:
            messagebox.showerror("Invalid Setting", str(e))

    def save_all_settings(self):
        try:
            self.save_runtime_settings()
            self.settings["click_cooldown_seconds"] = float(self.click_cooldown_var.get())
            self.settings["early_accept_threshold"] = float(self.early_accept_var.get())
            self.settings["post_close_click_delay_seconds"] = float(self.post_close_delay_var.get())
            self.settings["app_launch_wait_seconds"] = float(self.app_launch_wait_var.get())
            self.settings["close_template_crop_size"] = int(float(self.close_crop_var.get()))
            self.settings["back_template_crop_size"] = int(float(self.back_crop_var.get()))
            self.settings["icon_template_crop_size"] = int(float(self.icon_crop_var.get()))
            self.settings["inactivity_recovery_action"] = self.recovery_var.get()
            save_settings(self.settings)
            self.log("All settings saved")
        except ValueError as e:
            messagebox.showerror("Invalid Setting", str(e))

    def refresh_template_counts(self):
        pid = self.get_selected_profile_id() if hasattr(self, "home_profile_var") else self.settings.get("current_profile_id", "default_app")
        counts = {}
        for typ in ["close", "back", "icon"]:
            folder = profile_template_dir(pid, typ)
            counts[typ] = len([p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in [".png", ".jpg", ".jpeg", ".bmp", ".webp"]])
        text = f"Close {counts['close']}    Back {counts['back']}    App icon {counts['icon']}"
        if hasattr(self, "template_count_var"):
            self.template_count_var.set(text)

    def refresh_screen_list(self):
        if not hasattr(self, "screen_list_frame"):
            return
        for child in self.screen_list_frame.winfo_children():
            child.destroy()
        screens = load_json(PHONE_SCREENS_PATH, {"screens": []}).get("screens", [])
        self.screen_vars.clear()
        if not screens:
            ttk.Label(self.screen_list_frame, text="No screens selected", style="Card.TLabel").pack(anchor="w")
            return
        ttk.Label(self.screen_list_frame, text="Enabled screens", style="Card.TLabel").pack(anchor="w", pady=(0, 4))
        for screen in screens:
            var = tk.BooleanVar(value=bool(screen.get("enabled", True)))
            self.screen_vars[screen.get("screen_id")] = var
            cb = ttk.Checkbutton(self.screen_list_frame, text=screen.get("screen_name", screen.get("screen_id")), variable=var, command=self.save_screen_enabled)
            cb.pack(anchor="w", pady=2)

    def save_screen_enabled(self):
        data = load_json(PHONE_SCREENS_PATH, {"screens": []})
        for screen in data.get("screens", []):
            sid = screen.get("screen_id")
            if sid in self.screen_vars:
                screen["enabled"] = bool(self.screen_vars[sid].get())
        save_json(PHONE_SCREENS_PATH, data)
        self.log("Screen enable list saved")

    def action_select_screens(self):
        self.run_visible_task("Select mobile screens", lambda: select_phone_screens(), after=self.refresh_screen_list)

    def action_select_zones(self):
        self.run_visible_task("Select detection zones", lambda: select_detection_zones())

    def action_make_template(self, template_type: str):
        pid = self.get_selected_profile_id()
        try:
            sizes = {
                "close": int(float(self.close_crop_var.get())),
                "back": int(float(self.back_crop_var.get())),
                "icon": int(float(self.icon_crop_var.get())),
            }
        except Exception:
            sizes = {
                "close": int(self.settings.get("close_template_crop_size", 36)),
                "back": int(self.settings.get("back_template_crop_size", 44)),
                "icon": int(self.settings.get("icon_template_crop_size", 96)),
            }
        self.run_visible_task(
            f"Add {template_type} template",
            lambda: save_cross_template(pid, template_type, sizes.get(template_type, 72)),
            after=self.refresh_template_counts,
        )

    def run_visible_task(self, title: str, func, after=None):
        try:
            self.withdraw()
            result = func()
            self.deiconify()
            self.lift()
            self.focus_force()
            if after:
                after()
            if result is not None:
                self.log(f"{title} completed")
            else:
                self.log(f"{title} cancelled")
        except Exception as e:
            try:
                self.deiconify()
                self.lift()
            except Exception:
                pass
            messagebox.showerror(title, str(e))
            self.log(f"{title} failed {e}")

    def remove_templates(self, template_type):
        pid = self.get_selected_profile_id()
        if template_type is None:
            msg = "Remove all templates for the selected app"
        else:
            msg = f"Remove all {template_type} templates for the selected app"
        if not messagebox.askyesno("Remove Templates", msg):
            return
        clear_profile_templates(pid, template_type)
        self.cache.clear()
        self.refresh_template_counts()
        self.log(msg)

    def reset_regions(self):
        if not messagebox.askyesno("Reset Regions", "Delete all selected screens and detection zones"):
            return
        save_json(PHONE_SCREENS_PATH, {"screens": []})
        save_json(DETECTION_ZONES_PATH, {"zones": []})
        self.cache.clear()
        self.refresh_screen_list()
        self.log("Regions reset")

    def reset_everything(self):
        if self.engine.running:
            messagebox.showerror("Stop Automation", "Stop automation before resetting")
            return
        first = messagebox.askyesno("Reset Everything", "This will delete all app profiles templates regions screenshots and settings")
        if not first:
            return
        second = messagebox.askyesno("Confirm Reset", "Are you sure you want a clean default app with no templates")
        if not second:
            return
        self.cache.clear()
        reset_all_data()
        reset_settings()
        self.settings = load_settings()
        self.threshold_var.set(str(self.settings.get("template_threshold")))
        self.scan_delay_var.set(str(self.settings.get("scan_delay_seconds")))
        self.screen_check_var.set(str(self.settings.get("screen_check_seconds")))
        self.idle_cycles_var.set(str(self.settings.get("inactivity_cycles")))
        self.click_cooldown_var.set(str(self.settings.get("click_cooldown_seconds")))
        self.early_accept_var.set(str(self.settings.get("early_accept_threshold")))
        self.post_close_delay_var.set(str(self.settings.get("post_close_click_delay_seconds")))
        self.app_launch_wait_var.set(str(self.settings.get("app_launch_wait_seconds")))
        self.close_crop_var.set(str(self.settings.get("close_template_crop_size")))
        self.back_crop_var.set(str(self.settings.get("back_template_crop_size")))
        self.icon_crop_var.set(str(self.settings.get("icon_template_crop_size")))
        self.recovery_var.set(str(self.settings.get("inactivity_recovery_action")))
        self.auto_launch_var.set(bool(self.settings.get("auto_launch_app_icon")))
        self.refresh_profiles()
        self.refresh_screen_list()
        self.refresh_template_counts()
        self.log("Application reset to default empty setup")

    def start_automation(self):
        self.save_runtime_settings()
        pid = self.get_selected_profile_id()
        screens = load_json(PHONE_SCREENS_PATH, {"screens": []}).get("screens", [])
        enabled = [s for s in screens if s.get("enabled", True)]
        if not enabled:
            messagebox.showerror("No Screens", "Select and enable at least one mobile screen")
            return
        self.cache.clear()
        self.engine.start(pid, self.settings)
        self.log("Automation started. The selected app icon is checked on every enabled screen first.")

    def stop_automation(self):
        self.engine.stop()
        self.log("Automation stop requested")

    def emergency_exit(self):
        try:
            self.engine.stop()
            self.cache.clear()
            self.hotkey.stop()
        except Exception:
            pass
        os._exit(0)

    def open_data_folder(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(DATA_DIR)
        except Exception:
            messagebox.showinfo("Data Folder", str(DATA_DIR))

    def set_status(self, message: str):
        def update():
            self.status_var.set(message)
        try:
            self.after(0, update)
        except Exception:
            pass

    def log(self, message: str):
        def update():
            try:
                self.log_box.insert("end", message + "\n")
                self.log_box.see("end")
            except Exception:
                pass
        try:
            self.after(0, update)
        except Exception:
            pass

    def on_close(self):
        try:
            self.engine.stop()
            self.cache.clear()
            self.hotkey.stop()
        except Exception:
            pass
        self.destroy()


def main():
    ensure_dirs()
    app = MageApp()
    app.mainloop()


if __name__ == "__main__":
    main()
