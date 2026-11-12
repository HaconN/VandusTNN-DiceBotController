"""Text for player error replies and controller log entries.

Nothing here talks to Discord or Google: these functions only turn a
command's context plus an exception into text, so they can be unit-tested,
and every piece of text they return has been through redact(), so a
credential cannot reach the log box or a Discord message even if some
exception message happens to quote one.
"""

from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from pathlib import PureWindowsPath
from typing import Any, Iterable

from bot.dice import DISPLAY_LABELS
from bot.errors import (
    REPLY_FAILED_CODE,
    UNEXPECTED_ERROR_CODE,
    UNEXPECTED_ERROR_USER_MESSAGE,
    BotUserError,
)

REDACTED = "[REDACTED]"
INDENT = "    "
MAX_EXCEPTION_MESSAGE_CHARS = 400

# Patterns for credentials that must never be shown, whatever text they turn
# up in. Exact known secrets (the bot token) are passed to redact() as well.
_SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # PEM private key blocks (the service account "private_key"), raw or
    # JSON-escaped; then any leftover BEGIN marker with no matching END.
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL),
        REDACTED,
    ),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*", re.DOTALL), REDACTED),
    # Service account JSON fields.
    (re.compile(r'("private_key(?:_id)?"\s*:\s*")[^"]*(")'), r"\1" + REDACTED + r"\2"),
    # Google OAuth access tokens and Authorization headers.
    (re.compile(r"\bya29\.[\w.-]+"), REDACTED),
    (re.compile(r"(Bearer\s+)[\w.~+/-]+=*", re.IGNORECASE), r"\1" + REDACTED),
    # Discord bot tokens: three base64url parts joined by dots.
    (re.compile(r"\b[\w-]{23,28}\.[\w-]{6,7}\.[\w-]{27,}"), REDACTED),
]

# Context fields shown on the first line of an error entry; all others go on
# the second line, in this order first.
_HEADER_FIELDS = ("char", "name")
_DETAIL_ORDER = ("weapon", "skill", "attr", "type", "notation", "dice")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Replaces known secret values and anything shaped like a credential."""
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, REDACTED)
    for pattern, replacement in _SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


@dataclass
class CommandContext:
    """What is known about a command invocation so far; it grows as the
    command runs, so an error log shows everything known at the failure."""

    command: str
    user: str | None = None
    fields: dict[str, Any] = field(default_factory=dict)

    def add(self, **values: Any) -> None:
        for key, value in values.items():
            if value is not None:
                self.fields[key] = value


def error_code(error: BaseException) -> str:
    return error.code if isinstance(error, BotUserError) else UNEXPECTED_ERROR_CODE


def format_user_error(error: BaseException) -> str:
    """The ephemeral Thai reply for the player: code plus message, no
    technical detail."""
    if isinstance(error, BotUserError):
        text = f"❌ [{error.code}] {error.user_message}"
    else:
        text = f"❌ [{UNEXPECTED_ERROR_CODE}] {UNEXPECTED_ERROR_USER_MESSAGE}"
    return redact(text)


def format_error_log(ctx: CommandContext, error: BaseException) -> str:
    """One log entry for one error, e.g.

        ERROR E203 /attack user=haconn char=S3003 name=Play C
            weapon=ดาบใหญ่ skill=Swordsmanship attr=STR type=adv
            stat cell is not a whole number: tab='Final Sum' column='STR' raw='3.5'
            ValueError: invalid literal for int() with base 10: '3.5'
            (models.py:66 in attribute_value)

    An error without a code (a bug, or a library error nobody anticipated)
    gets E900 and its full traceback.
    """
    lines = [_header_line("ERROR", error_code(error), ctx)]
    context_line = _context_line(ctx)
    if context_line:
        lines.append(INDENT + context_line)

    if isinstance(error, BotUserError):
        cause = error.__cause__
        summary = error.log_message
        if error.details:
            summary += ": " + " ".join(f"{k}={_format_value(v)}" for k, v in error.details.items())
        if cause is None:
            lines.append(INDENT + f"{type(error).__name__}: {summary}")
        else:
            lines.append(INDENT + summary)
            lines.append(INDENT + describe_exception(cause))
        where = _where(cause if cause is not None else error)
        if where:
            lines.append(INDENT + where)
    else:
        lines.append(INDENT + describe_exception(error))
        trace = "".join(traceback.format_exception(error)).rstrip()
        lines.extend(INDENT + line for line in trace.splitlines())

    return redact("\n".join(lines))


def format_warning(ctx: CommandContext, error: BaseException, note: str) -> str:
    """A shorter entry for a failure the player never sees (autocomplete)."""
    lines = [_header_line("WARNING", error_code(error), ctx) + f": {note}"]
    if isinstance(error, BotUserError):
        lines.append(INDENT + f"{type(error).__name__}: {error.log_message}")
        if error.__cause__ is not None:
            lines.append(INDENT + describe_exception(error.__cause__))
    else:
        lines.append(INDENT + describe_exception(error))
    return redact("\n".join(lines))


def format_reply_failure(ctx: CommandContext, error: BaseException) -> str:
    """The bot could not answer the player at all (expired interaction,
    Discord outage, ...), so the log is the only place this shows up."""
    lines = [
        _header_line("ERROR", REPLY_FAILED_CODE, ctx) + ": could not send the reply to Discord",
        INDENT + describe_exception(error),
    ]
    where = _where(error)
    if where:
        lines.append(INDENT + where)
    return redact("\n".join(lines))


def format_roll_success(
    user: str | None,
    *,
    char_name: str | None,
    attribute: str | None,
    num_dice: int,
    faces: int,
    roll_type: str,
    sp: int,
) -> str:
    """e.g. "/roll haconn -> Play C, STR 5d6 Normal, SP 3" """
    dice_part = f"{num_dice}d{faces} {_label(roll_type)}"
    if attribute:
        dice_part = f"{attribute} {dice_part}"
    parts = [char_name, dice_part] if char_name else [dice_part]
    return redact(f"/roll {user} -> {', '.join(parts)}, SP {sp}")


def format_attack_success(
    user: str | None,
    *,
    char_name: str,
    weapon: str,
    num_dice: int,
    roll_type: str,
    sp: int,
) -> str:
    """e.g. "/attack haconn -> Play C, ดาบใหญ่, 5d6 ADV, SP 4" """
    return redact(f"/attack {user} -> {char_name}, {weapon}, {num_dice}d6 {_label(roll_type)}, SP {sp}")


def describe_exception(error: BaseException) -> str:
    """ "Type: message" on one line, without repeating the type when the
    message already starts with it (gspread's APIError does)."""
    name = type(error).__name__
    message = " ".join(str(error).split())
    if len(message) > MAX_EXCEPTION_MESSAGE_CHARS:
        message = message[:MAX_EXCEPTION_MESSAGE_CHARS] + " ..."
    if not message:
        return name
    if message.startswith(name + ":"):
        return message
    return f"{name}: {message}"


# ---- internals ------------------------------------------------------------


def _format_value(value: Any) -> str:
    """Quotes text so a blank or padded cell is visible (raw=''), without
    repr's escaping of Windows paths; text with control characters such as
    a newline falls back to repr."""
    if isinstance(value, str) and value.isprintable():
        return f"'{value}'"
    return repr(value)


def _label(roll_type: str) -> str:
    return DISPLAY_LABELS.get(roll_type.strip().lower(), roll_type)


def _header_line(level: str, code: str, ctx: CommandContext) -> str:
    parts = [level, code, ctx.command]
    if ctx.user:
        parts.append(f"user={ctx.user}")
    parts += [f"{key}={ctx.fields[key]}" for key in _HEADER_FIELDS if key in ctx.fields]
    return " ".join(parts)


def _context_line(ctx: CommandContext) -> str:
    keys = [key for key in _DETAIL_ORDER if key in ctx.fields]
    keys += [key for key in ctx.fields if key not in keys and key not in _HEADER_FIELDS]
    return " ".join(f"{key}={ctx.fields[key]}" for key in keys)


def _where(error: BaseException) -> str:
    """The two innermost frames of this bot's own code (caller -> callee),
    plus the frame that actually raised when that is inside a library, e.g.
    "(models.py:66 in attribute_value -> models.py:40 in parse_whole_number)"
    or "(sheets.py:233 in _fetch_values, raised in http_client.py:128 in request)"."""
    frames = traceback.extract_tb(error.__traceback__)
    if not frames:
        return ""
    last = frames[-1]
    own = [frame for frame in frames if _is_own_code(frame.filename)][-2:]
    parts = []
    if own:
        parts.append(" -> ".join(_frame_text(frame) for frame in own))
    if not own or own[-1] is not last:
        parts.append(("raised in " if own else "") + _frame_text(last))
    return "(" + ", ".join(parts) + ")"


def _is_own_code(filename: str) -> bool:
    # PureWindowsPath splits on both / and \, for dev runs and frozen builds.
    parts = PureWindowsPath(filename).parts
    return "site-packages" not in parts and any(part in ("bot", "gui") for part in parts[:-1])


def _frame_text(frame: traceback.FrameSummary) -> str:
    return f"{PureWindowsPath(frame.filename).name}:{frame.lineno} in {frame.name}"
