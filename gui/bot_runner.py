"""Runs the Discord bot in a background thread with its own asyncio event
loop, since discord.py's bot.start() is a blocking coroutine that must not
run on the tkinter main thread. Also owns the auto-shutdown timer.

All callbacks (log_callback, status_callback) may be invoked from this
background thread or from a threading.Timer thread — callers (the tkinter
controller) are responsible for marshaling any UI updates back onto the main
thread (e.g. via root.after()).
"""

from __future__ import annotations

import asyncio
import threading
from datetime import datetime, time as dt_time, timedelta

import discord

from bot.main import build_bot
from bot.sheets import SheetsClient


class BotRunner:
    def __init__(self, log_callback, status_callback):
        self.log_callback = log_callback
        self.status_callback = status_callback

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bot: discord.Client | None = None
        self._shutdown_timer: threading.Timer | None = None

        self._shutdown_mode = "none"
        self._shutdown_hours: float | None = None
        self._shutdown_time: dt_time | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(
        self,
        token: str,
        service_account_json_path: str,
        sheet_name: str,
        shutdown_mode: str = "none",
        shutdown_hours: float | None = None,
        shutdown_time: dt_time | None = None,
    ) -> None:
        if self.is_running:
            self.log_callback("บอทกำลังทำงานอยู่แล้ว")
            return

        self._shutdown_mode = shutdown_mode
        self._shutdown_hours = shutdown_hours
        self._shutdown_time = shutdown_time

        self._thread = threading.Thread(
            target=self._run,
            args=(token, service_account_json_path, sheet_name),
            daemon=True,
        )
        self._thread.start()

        if shutdown_mode == "at_time" and shutdown_time is not None:
            target = self._next_occurrence(shutdown_time)
            self._schedule_stop_at(target)

    def stop(self) -> None:
        self._cancel_shutdown_timer()

        if not self.is_running or self._loop is None or self._bot is None:
            return

        asyncio.run_coroutine_threadsafe(self._bot.close(), self._loop)

        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=10)

    # ---- internals ----------------------------------------------------

    def _run(self, token: str, service_account_json_path: str, sheet_name: str) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        sheets_client = SheetsClient(service_account_json_path, sheet_name)
        self._bot = build_bot(sheets_client)

        @self._bot.event
        async def on_ready():
            self.status_callback(True)
            self.log_callback(f"เชื่อมต่อ Discord สำเร็จ: {self._bot.user}")

            try:
                sheets_client.fetch_weapons()
                self.log_callback("เชื่อมต่อ Google Sheet สำเร็จ")
            except Exception as e:
                self.log_callback(f"เชื่อมต่อ Google Sheet ล้มเหลว: {e}")

            if self._shutdown_mode == "hours" and self._shutdown_hours:
                target = datetime.now() + timedelta(hours=self._shutdown_hours)
                self._schedule_stop_at(target)

        try:
            self.log_callback("กำลังเชื่อมต่อ Discord...")
            self._loop.run_until_complete(self._bot.start(token))
        except discord.LoginFailure:
            self.log_callback("เชื่อมต่อล้มเหลว: Discord Bot Token ไม่ถูกต้อง")
        except Exception as e:
            self.log_callback(f"เกิดข้อผิดพลาด: {e}")
        finally:
            self.status_callback(False)
            self.log_callback("บอทออฟไลน์แล้ว")
            self._loop.close()
            self._loop = None
            self._bot = None

    def _next_occurrence(self, target_time: dt_time) -> datetime:
        now = datetime.now()
        target = datetime.combine(now.date(), target_time)
        if target <= now:
            target += timedelta(days=1)
        return target

    def _schedule_stop_at(self, target: datetime) -> None:
        self._cancel_shutdown_timer()
        delay = max((target - datetime.now()).total_seconds(), 0)
        self.log_callback(f"ตั้งเวลาปิดบอทอัตโนมัติ: {target.strftime('%Y-%m-%d %H:%M')}")
        self._shutdown_timer = threading.Timer(delay, self._auto_stop)
        self._shutdown_timer.daemon = True
        self._shutdown_timer.start()

    def _cancel_shutdown_timer(self) -> None:
        if self._shutdown_timer is not None:
            self._shutdown_timer.cancel()
            self._shutdown_timer = None

    def _auto_stop(self) -> None:
        self.log_callback("ถึงเวลาปิดบอทอัตโนมัติ กำลังปิดการเชื่อมต่อ...")
        self.stop()
