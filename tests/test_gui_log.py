import logging
import threading
import tkinter as tk

import pytest

import gui.controller as controller_module
from gui.bot_runner import CallbackLogHandler
from gui.config_store import DEFAULT_CONFIG

TOKEN = "MTA5ODc2NTQzMjEwOTg3NjU0.GaBcDe.abcdefghijklmnopqrstuvwxyz0123456789AB"


class InMemoryConfigStore:
    def load(self):
        return dict(DEFAULT_CONFIG)

    def save(self, config):
        pass


@pytest.fixture(scope="module")
def tk_root():
    # One Tk interpreter for the module: creating several in one process
    # intermittently fails on Windows ("Can't find a usable tk.tcl").
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"no Tk display: {exc}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def app(monkeypatch, tk_root):
    # Never read or write the real per-user config (it holds the real token).
    monkeypatch.setattr(controller_module, "ConfigStore", InMemoryConfigStore)
    window = tk.Toplevel(tk_root)
    window.withdraw()
    try:
        yield controller_module.ControllerApp(window)
    finally:
        window.destroy()


def log_lines(app):
    return app.log_box.get("1.0", "end-1c").splitlines()


def test_log_box_keeps_only_the_newest_lines(app):
    for i in range(controller_module.MAX_LOG_LINES + 20):
        app._append_log(f"line {i}")

    lines = log_lines(app)
    assert len(lines) == controller_module.MAX_LOG_LINES
    assert lines[0].endswith("line 20")
    assert lines[-1].endswith(f"line {controller_module.MAX_LOG_LINES + 19}")


def test_multi_line_error_entries_count_every_line(app):
    for i in range(controller_module.MAX_LOG_LINES):
        app._append_log(f"ERROR E900 entry {i}\n    detail a\n    detail b", "error")

    assert len(log_lines(app)) == controller_module.MAX_LOG_LINES


def test_error_entries_have_the_full_date_and_info_lines_the_time(app):
    app._append_log("routine")
    app._append_log("ERROR E203 /attack", "error")

    info, error = log_lines(app)
    assert len(info.split("]")[0]) == len("[21:05:33")
    assert len(error.split("]")[0]) == len("[2026-11-12 21:05:33")
    assert "error" in app.log_box.tag_names("2.0")


def test_messages_from_other_threads_arrive_through_the_queue(app):
    worker = threading.Thread(target=lambda: (app._on_log("from the bot thread"), app._on_status(True)))
    worker.start()
    worker.join()
    assert log_lines(app) == []  # nothing touches tkinter until the main thread drains

    app._drain_ui_queue()

    assert log_lines(app)[0].endswith("from the bot thread")
    assert app.status_var.get() == "Online"


def test_callback_handler_redacts_token_and_passes_level():
    received = []
    handler = CallbackLogHandler(lambda message, level: received.append((message, level)), secrets=[TOKEN])
    logger = logging.getLogger("bot.test_gui_log")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.error("ERROR E900 /roll token=%s", TOKEN)
        logger.info("/roll haconn -> 6d6 Normal, SP 3")
    finally:
        logger.removeHandler(handler)

    assert received[0] == ("ERROR E900 /roll token=[REDACTED]", "error")
    assert received[1] == ("/roll haconn -> 6d6 Normal, SP 3", "info")


def test_callback_handler_includes_library_tracebacks():
    received = []
    handler = CallbackLogHandler(lambda message, level: received.append(message), level=logging.WARNING)
    logger = logging.getLogger("discord.test_gui_log")
    logger.addHandler(handler)
    try:
        try:
            raise KeyError("STR")
        except KeyError:
            logger.exception("Ignoring exception in autocomplete")
    finally:
        logger.removeHandler(handler)

    assert received[0].startswith("Ignoring exception in autocomplete\n    Traceback")
    assert "KeyError: 'STR'" in received[0]
