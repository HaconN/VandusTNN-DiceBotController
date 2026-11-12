"""Local persistence for the controller GUI's settings (bot token, service
account JSON path, sheet name, auto-shutdown preference).

Stored as plain JSON in the user's per-user app data directory (NOT next to
the executable, so a clean rebuild or a replaced .exe never wipes it):
  Windows: %LOCALAPPDATA%\\DiceBotController\\gui_config.json
  Other platforms (no LOCALAPPDATA): ~/.dicebotcontroller/gui_config.json

Older builds stored this file next to the running executable/script. On
first load, if nothing exists yet at the new location but a config is found
at that legacy path, it's migrated forward automatically.

This file holds a secret (the bot token) so it must never be committed —
see .gitignore.
"""

from __future__ import annotations

import json
import os
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


def _app_data_dir() -> Path:
    """Per-user app settings directory, conventional per platform."""
    local_appdata = os.getenv("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "DiceBotController"
    return Path.home() / ".dicebotcontroller"


def _legacy_base_dir() -> Path:
    """Where older builds stored the config: next to the exe/script."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


class ConfigStore:
    def __init__(self):
        self.path = _app_data_dir() / CONFIG_FILENAME
        self.legacy_path = _legacy_base_dir() / CONFIG_FILENAME

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            migrated = self._migrate_legacy_config()
            if migrated is not None:
                return migrated
            return dict(DEFAULT_CONFIG)
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return dict(DEFAULT_CONFIG)
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        return merged

    def _migrate_legacy_config(self) -> dict[str, Any] | None:
        """One-time migration from the old next-to-exe location. Returns the
        migrated config on success, or None if there was nothing to migrate."""
        if self.legacy_path == self.path or not self.legacy_path.exists():
            return None
        try:
            with open(self.legacy_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        self.save(merged)
        return merged

    def save(self, config: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
