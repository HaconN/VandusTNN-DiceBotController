"""tkinter desktop controller for the Discord dice bot.

Lets a non-technical user paste the bot token + service account JSON path
once (persisted locally), then start/stop the bot without a terminal, with
an optional auto-shutdown timer.
"""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime, time as dt_time
from tkinter import filedialog, messagebox, scrolledtext, ttk

from gui.bot_runner import BotRunner
from gui.config_store import ConfigStore

SHUTDOWN_MODE_LABELS = {
    "none": "ไม่ปิดอัตโนมัติ (ปิดเองด้วยปุ่ม Stop)",
    "hours": "ทำงาน N ชั่วโมงแล้วปิด",
    "at_time": "ปิดเมื่อถึงเวลา HH:MM",
}
LABEL_TO_MODE = {v: k for k, v in SHUTDOWN_MODE_LABELS.items()}


class ControllerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Discord Dice Bot Controller")
        self.root.resizable(False, False)

        self.config_store = ConfigStore()
        self.config = self.config_store.load()

        self.runner = BotRunner(log_callback=self._on_log, status_callback=self._on_status)

        self._build_widgets()
        self._load_into_widgets()
        self._update_shutdown_fields()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---- widget construction ------------------------------------------

    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(frame, text="Discord Bot Token:").grid(row=0, column=0, sticky="w", **pad)
        self.token_var = tk.StringVar()
        token_entry = ttk.Entry(frame, textvariable=self.token_var, show="*", width=40)
        token_entry.grid(row=0, column=1, sticky="we", **pad)
        self._add_paste_button(frame, token_entry, row=0, column=2)
        self._enable_paste(token_entry)

        ttk.Label(frame, text="Service Account JSON:").grid(row=1, column=0, sticky="w", **pad)
        self.json_path_var = tk.StringVar()
        json_entry = ttk.Entry(frame, textvariable=self.json_path_var, width=30)
        json_entry.grid(row=1, column=1, sticky="we", **pad)
        self._add_paste_button(frame, json_entry, row=1, column=2)
        self._enable_paste(json_entry)
        ttk.Button(frame, text="เลือกไฟล์...", command=self._pick_json_file).grid(row=1, column=3, **pad)

        ttk.Label(frame, text="Google Sheet Name/Key:").grid(row=2, column=0, sticky="w", **pad)
        self.sheet_name_var = tk.StringVar()
        sheet_entry = ttk.Entry(frame, textvariable=self.sheet_name_var, width=40)
        sheet_entry.grid(row=2, column=1, sticky="we", **pad)
        self._add_paste_button(frame, sheet_entry, row=2, column=2)
        self._enable_paste(sheet_entry)

        ttk.Label(frame, text="ปิดอัตโนมัติ:").grid(row=3, column=0, sticky="w", **pad)
        self.shutdown_mode_label_var = tk.StringVar(value=SHUTDOWN_MODE_LABELS["none"])
        mode_combo = ttk.Combobox(
            frame,
            textvariable=self.shutdown_mode_label_var,
            state="readonly",
            values=list(SHUTDOWN_MODE_LABELS.values()),
            width=32,
        )
        mode_combo.grid(row=3, column=1, sticky="w", **pad)
        mode_combo.bind("<<ComboboxSelected>>", lambda e: self._update_shutdown_fields())

        self.shutdown_hours_var = tk.StringVar(value="4")
        self.hours_entry = ttk.Entry(frame, textvariable=self.shutdown_hours_var, width=8)

        self.shutdown_time_var = tk.StringVar(value="23:00")
        self.time_entry = ttk.Entry(frame, textvariable=self.shutdown_time_var, width=8)

        self.status_var = tk.StringVar(value="Offline")
        self.status_label = ttk.Label(frame, textvariable=self.status_var, foreground="red")
        self.status_label.grid(row=4, column=0, sticky="w", **pad)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=1, columnspan=2, sticky="e", **pad)
        self.start_button = ttk.Button(btn_frame, text="Start", command=self._on_start)
        self.start_button.pack(side="left", padx=4)
        self.stop_button = ttk.Button(btn_frame, text="Stop", command=self._on_stop, state="disabled")
        self.stop_button.pack(side="left", padx=4)

        ttk.Label(frame, text="Log:").grid(row=5, column=0, sticky="nw", **pad)
        self.log_box = scrolledtext.ScrolledText(frame, height=12, width=68, state="disabled", wrap="word")
        self.log_box.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)

        frame.columnconfigure(1, weight=1)

    def _paste_into(self, entry: tk.Entry) -> None:
        entry.delete(0, "end")
        entry.focus_set()
        entry.event_generate("<<Paste>>")

    def _add_paste_button(self, parent: ttk.Frame, entry: tk.Entry, row: int, column: int) -> None:
        ttk.Button(parent, text="Paste", width=6, command=lambda: self._paste_into(entry)).grid(
            row=row, column=column, padx=8, pady=4
        )

    def _enable_paste(self, entry: tk.Entry) -> None:
        # ttk.Entry normally handles Ctrl+V/right-click-paste via its default
        # bindtags, but they're bound to *insert*, not *replace* — and there
        # was never a context menu wired up at all. Bind both explicitly so
        # Ctrl+V and right-click behave the same as the Paste button (clear
        # then paste), and so right-click actually offers a Paste option.
        def paste_and_break(event=None):
            self._paste_into(entry)
            return "break"

        entry.bind("<Control-v>", paste_and_break)
        entry.bind("<Control-V>", paste_and_break)

        menu = tk.Menu(entry, tearoff=0)
        menu.add_command(label="Paste", command=lambda: self._paste_into(entry))

        def show_context_menu(event):
            entry.focus_set()
            menu.tk_popup(event.x_root, event.y_root)

        entry.bind("<Button-3>", show_context_menu)

    def _update_shutdown_fields(self) -> None:
        mode = LABEL_TO_MODE.get(self.shutdown_mode_label_var.get(), "none")
        self.hours_entry.grid_forget()
        self.time_entry.grid_forget()
        if mode == "hours":
            self.hours_entry.grid(row=3, column=2, sticky="w", padx=8, pady=4)
        elif mode == "at_time":
            self.time_entry.grid(row=3, column=2, sticky="w", padx=8, pady=4)

    def _load_into_widgets(self) -> None:
        self.token_var.set(self.config.get("discord_bot_token", ""))
        self.json_path_var.set(self.config.get("service_account_json_path", ""))
        self.sheet_name_var.set(self.config.get("sheet_name", ""))
        mode = self.config.get("shutdown_mode", "none")
        self.shutdown_mode_label_var.set(SHUTDOWN_MODE_LABELS.get(mode, SHUTDOWN_MODE_LABELS["none"]))
        self.shutdown_hours_var.set(str(self.config.get("shutdown_hours", 4.0)))
        self.shutdown_time_var.set(self.config.get("shutdown_time", "23:00"))

    def _pick_json_file(self) -> None:
        path = filedialog.askopenfilename(
            title="เลือกไฟล์ Service Account JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if path:
            self.json_path_var.set(path)

    # ---- start/stop -----------------------------------------------------

    def _gather_config(self) -> dict:
        mode = LABEL_TO_MODE.get(self.shutdown_mode_label_var.get(), "none")
        return {
            "discord_bot_token": self.token_var.get().strip(),
            "service_account_json_path": self.json_path_var.get().strip(),
            "sheet_name": self.sheet_name_var.get().strip(),
            "shutdown_mode": mode,
            "shutdown_hours": self.shutdown_hours_var.get().strip(),
            "shutdown_time": self.shutdown_time_var.get().strip(),
        }

    def _on_start(self) -> None:
        cfg = self._gather_config()

        if not cfg["discord_bot_token"] or not cfg["service_account_json_path"] or not cfg["sheet_name"]:
            messagebox.showerror("ข้อมูลไม่ครบ", "กรุณากรอก Token, Service Account JSON, และชื่อ Sheet ให้ครบ")
            return

        shutdown_hours = None
        shutdown_time = None
        if cfg["shutdown_mode"] == "hours":
            try:
                shutdown_hours = float(cfg["shutdown_hours"])
                if shutdown_hours <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("ค่าไม่ถูกต้อง", "กรุณาใส่จำนวนชั่วโมงเป็นตัวเลขที่มากกว่า 0")
                return
        elif cfg["shutdown_mode"] == "at_time":
            try:
                parsed = datetime.strptime(cfg["shutdown_time"], "%H:%M")
                shutdown_time = dt_time(hour=parsed.hour, minute=parsed.minute)
            except ValueError:
                messagebox.showerror("ค่าไม่ถูกต้อง", "กรุณาใส่เวลาในรูปแบบ HH:MM เช่น 23:00")
                return

        # Persist settings (including the numeric/parsed hours as float for consistency).
        save_cfg = dict(cfg)
        if shutdown_hours is not None:
            save_cfg["shutdown_hours"] = shutdown_hours
        self.config_store.save(save_cfg)

        self.start_button.config(state="disabled")
        self.runner.start(
            token=cfg["discord_bot_token"],
            service_account_json_path=cfg["service_account_json_path"],
            sheet_name=cfg["sheet_name"],
            shutdown_mode=cfg["shutdown_mode"],
            shutdown_hours=shutdown_hours,
            shutdown_time=shutdown_time,
        )
        self.stop_button.config(state="normal")

    def _on_stop(self) -> None:
        self.stop_button.config(state="disabled")
        self._on_log("กำลังปิดการเชื่อมต่อ...")
        threading.Thread(target=self.runner.stop, daemon=True).start()

    def _on_close(self) -> None:
        if self.status_var.get() == "Online":
            should_stop = self._ask_yes_no_thai(
                "ยืนยันการปิดโปรแกรม",
                "กำลังรันบอทอยู่ ต้องหยุดการทำงานก่อน จะหยุดการทำงานแล้วปิดโปรแกรมไหม?",
            )
            if not should_stop:
                return
            self._on_log("กำลังปิดบอทก่อนออกจากโปรแกรม...")
            self.runner.stop()
        self.root.destroy()

    def _ask_yes_no_thai(self, title: str, message: str) -> bool:
        # messagebox.askyesno's button captions follow the OS/Tk locale (usually
        # English "Yes"/"No") and can't be overridden, so this is a small modal
        # Toplevel standing in for it with the exact Thai button labels required.
        result = {"value": False}
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.resizable(False, False)
        dialog.transient(self.root)

        ttk.Label(dialog, text=message, wraplength=320, justify="left").pack(padx=16, pady=16)

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 12))

        def on_yes() -> None:
            result["value"] = True
            dialog.destroy()

        def on_no() -> None:
            result["value"] = False
            dialog.destroy()

        ttk.Button(btn_frame, text="ใช่", width=10, command=on_yes).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="ไม่", width=10, command=on_no).pack(side="left", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", on_no)

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")

        dialog.grab_set()
        self.root.wait_window(dialog)
        return result["value"]

    # ---- callbacks (may run on background threads) ----------------------

    def _on_status(self, is_online: bool) -> None:
        self.root.after(0, lambda: self._set_status_ui(is_online))

    def _set_status_ui(self, is_online: bool) -> None:
        if is_online:
            self.status_var.set("Online")
            self.status_label.config(foreground="green")
            self.start_button.config(state="disabled")
            self.stop_button.config(state="normal")
        else:
            self.status_var.set("Offline")
            self.status_label.config(foreground="red")
            self.start_button.config(state="normal")
            self.stop_button.config(state="disabled")

    def _on_log(self, message: str) -> None:
        self.root.after(0, lambda: self._append_log(message))

    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.config(state="normal")
        self.log_box.insert("end", f"[{timestamp}] {message}\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")


def main() -> None:
    root = tk.Tk()
    ControllerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
