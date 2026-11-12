"""Runs the Discord bot in a background thread with its own asyncio event
loop, since discord.py's bot.start() is a blocking coroutine that must not
run on the tkinter main thread. Also owns the auto-shutdown timer, and
forwards the bot's log records (command activity, coded errors, discord.py
warnings) to the controller's log box.

All callbacks (log_callback, status_callback) may be invoked from this
background thread, a worker thread or a threading.Timer thread; callers (the
tkinter controller) are responsible for marshaling UI updates back onto the
main thread. log_callback(message, level) gets level "info", "warning" or
"error"; every message has already been redacted.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import traceback
from datetime import datetime, time as dt_time, timedelta
from typing import Callable, Iterable

import discord

from bot.main import build_bot
from bot.reporting import CommandContext, error_code, format_error_log, redact
from bot.sheets import SheetsClient

BOT_LOGGER_NAME = "bot"
DISCORD_LOGGER_NAME = "discord"

startup_logger = logging.getLogger("bot.startup")


class CallbackLogHandler(logging.Handler):
    """Hands each log record to a callback as (redacted text, level name)."""

    def __init__(self, callback: Callable[[str, str], None], secrets: Iterable[str] = (), level: int = logging.INFO):
        super().__init__(level)
        self._callback = callback
        self._secrets = tuple(secret for secret in secrets if secret)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                trace = "".join(traceback.format_exception(*record.exc_info)).rstrip()
                message += "\n" + "\n".join("    " + line for line in trace.splitlines())
            self._callback(redact(message, self._secrets), record.levelname.lower())
        except Exception:
            self.handleError(record)


class BotRunner:
    def __init__(self, log_callback: Callable[..., None], status_callback: Callable[[bool], None]):
        self.log_callback = log_callback
        self.status_callback = status_callback

        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bot: discord.Client | None = None
        self._shutdown_timer: threading.Timer | None = None

        self._shutdown_mode = "none"
        self._shutdown_hours: float | None = None
        self._shutdown_time: dt_time | None = None

        self._secrets: tuple[str, ...] = ()
        self._log_handlers: list[tuple[logging.Logger, logging.Handler]] = []

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
            self._log("บอทกำลังทำงานอยู่แล้ว")
            return

        self._shutdown_mode = shutdown_mode
        self._shutdown_hours = shutdown_hours
        self._shutdown_time = shutdown_time
        self._secrets = (token,)
        self._attach_log_handlers()

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

    def _log(self, message: str, level: str = "info") -> None:
        self.log_callback(redact(message, self._secrets), level)

    def _attach_log_handlers(self) -> None:
        self._detach_log_handlers()
        bot_logger = logging.getLogger(BOT_LOGGER_NAME)
        bot_logger.setLevel(logging.INFO)
        # discord.py's own warnings (rate limits, gateway trouble, exceptions
        # it swallows) would otherwise go to a console the GUI doesn't have.
        for logger, level in ((bot_logger, logging.INFO), (logging.getLogger(DISCORD_LOGGER_NAME), logging.WARNING)):
            handler = CallbackLogHandler(self.log_callback, self._secrets, level)
            logger.addHandler(handler)
            self._log_handlers.append((logger, handler))

    def _detach_log_handlers(self) -> None:
        for logger, handler in self._log_handlers:
            logger.removeHandler(handler)
        self._log_handlers = []

    def _run(self, token: str, service_account_json_path: str, sheet_name: str) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        sheets_client = SheetsClient(service_account_json_path, sheet_name)
        bot = build_bot(sheets_client)
        self._bot = bot

        @bot.event
        async def on_ready():
            self.status_callback(True)
            self._log(f"เชื่อมต่อ Discord สำเร็จ: {bot.user}")
            await self._check_sheets(bot, sheets_client)

            if self._shutdown_mode == "hours" and self._shutdown_hours:
                target = datetime.now() + timedelta(hours=self._shutdown_hours)
                self._schedule_stop_at(target)

        try:
            self._log("กำลังเชื่อมต่อ Discord...")
            self._loop.run_until_complete(bot.start(token))
        except discord.LoginFailure:
            self._log("เชื่อมต่อล้มเหลว: Discord Bot Token ไม่ถูกต้อง", "error")
        except Exception as e:
            self._log(f"เกิดข้อผิดพลาด: {type(e).__name__}: {e}", "error")
        finally:
            self.status_callback(False)
            self._log("บอทออฟไลน์แล้ว")
            self._loop.close()
            self._loop = None
            self._bot = None
            self._detach_log_handlers()

    async def _check_sheets(self, bot, sheets_client: SheetsClient) -> None:
        """Reads the weapon list once so a sheet problem shows up in the log
        at startup, with its code, instead of at the first player's command."""
        email = sheets_client.service_account_email() or "อ่าน client_email จากไฟล์ไม่ได้"
        try:
            weapons = await bot.warm_up_sheets()
        except Exception as error:
            startup_logger.error(format_error_log(CommandContext("startup sheet check"), error))
            self._log(
                f"เชื่อมต่อ Google Sheet ล้มเหลว [{error_code(error)}] คำสั่งที่ใช้ชีตจะใช้ไม่ได้จนกว่าจะแก้ "
                f"(service account: {email})",
                "error",
            )
            return
        self._log(f"เชื่อมต่อ Google Sheet สำเร็จ: อาวุธ {len(weapons)} รายการ (service account: {email})")

    def _next_occurrence(self, target_time: dt_time) -> datetime:
        now = datetime.now()
        target = datetime.combine(now.date(), target_time)
        if target <= now:
            target += timedelta(days=1)
        return target

    def _schedule_stop_at(self, target: datetime) -> None:
        self._cancel_shutdown_timer()
        delay = max((target - datetime.now()).total_seconds(), 0)
        self._log(f"ตั้งเวลาปิดบอทอัตโนมัติ: {target.strftime('%Y-%m-%d %H:%M')}")
        self._shutdown_timer = threading.Timer(delay, self._auto_stop)
        self._shutdown_timer.daemon = True
        self._shutdown_timer.start()

    def _cancel_shutdown_timer(self) -> None:
        if self._shutdown_timer is not None:
            self._shutdown_timer.cancel()
            self._shutdown_timer = None

    def _auto_stop(self) -> None:
        self._log("ถึงเวลาปิดบอทอัตโนมัติ กำลังปิดการเชื่อมต่อ...")
        self.stop()
