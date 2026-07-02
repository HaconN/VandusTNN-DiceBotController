"""Local persistence for the controller GUI's settings (bot token, service
account JSON path, sheet name, auto-shutdown preference).

Stored as plain JSON next to the running executable/script. This file holds a
secret (the bot token) so it must never be committed — see .gitignore.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "gui_config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "discord_bot_token": "",
    "service_account_json_path": "",
    "sheet_name": "",
    "shutdown_mode": "none",  # "none" | "hours" | "at_time"
    "shutdown_hours": 4.0,
    "shutdown_time": "23:00",  # HH:MM, used when shutdown_mode == "at_time"
}


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        # Running as a PyInstaller-built exe: config sits next to the exe.
        return Path(sys.executable).resolve().parent
    # Running from source: config sits at the project root.
    return Path(__file__).resolve().parent.parent


class ConfigStore:
    def __init__(self):
        self.path = _base_dir() / CONFIG_FILENAME

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_CONFIG)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged

    def save(self, config: dict[str, Any]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
