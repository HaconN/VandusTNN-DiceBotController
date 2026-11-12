import inspect
import re

import pytest

from bot import errors
from bot.reporting import (
    REDACTED,
    CommandContext,
    format_error_log,
    format_user_error,
    redact,
)

DISCORD_TOKEN_SHAPED = "MTA5ODc2NTQzMjEwOTg3NjU0.GaBcDe.abcdefghijklmnopqrstuvwxyz0123456789AB"


def all_error_classes():
    return [
        cls
        for _, cls in inspect.getmembers(errors, inspect.isclass)
        if issubclass(cls, errors.BotUserError) and cls is not errors.BotUserError
    ]


def test_every_error_has_a_unique_well_formed_code():
    codes = [cls.code for cls in all_error_classes()]
    assert all(re.fullmatch(r"E\d{3}", code) for code in codes)
    reserved = {errors.UNEXPECTED_ERROR_CODE, errors.REPLY_FAILED_CODE}
    assert len(codes) == len(set(codes))
    assert not reserved & set(codes)


def test_user_message_carries_code_and_no_technical_detail():
    error = errors.StatValueError("STR", "3.5", "Play C", "S3003")
    text = format_user_error(error)
    assert text.startswith("❌ [E203] ")
    assert "Play C" in text and "STR" in text
    assert "3.5" not in text and "Final Sum" not in text


def test_unexpected_error_user_message_hides_exception_text():
    text = format_user_error(RuntimeError("database password is hunter2"))
    assert text.startswith("❌ [E900] ")
    assert "hunter2" not in text


@pytest.mark.parametrize(
    "text",
    [
        "key: -----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----\n done",
        '{"private_key": "-----BEGIN PRIVATE KEY-----\\nMIIEvQIBADANBg\\n-----END PRIVATE KEY-----\\n"}',
        "truncated -----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg",
        '{"private_key_id": "0123456789abcdef0123456789abcdef01234567"}',
        "Authorization: Bearer ya29.a0AfH6SMBx-secret-token",
        f"token was {DISCORD_TOKEN_SHAPED} oops",
    ],
)
def test_redact_removes_credentials(text):
    cleaned = redact(text)
    assert REDACTED in cleaned
    for fragment in ("MIIEvQIBADANBg", "0123456789abcdef", "a0AfH6SMBx", "GaBcDe"):
        assert fragment not in cleaned


def test_redact_removes_known_secret_values():
    assert redact("the token is s3cr3t-value-123", ["s3cr3t-value-123"]) == f"the token is {REDACTED}"


def test_redact_keeps_ordinary_text():
    text = "ERROR E403 /attack user=haconn client_email='dice-bot@demo.iam.gserviceaccount.com'"
    assert redact(text) == text


def test_error_log_redacts_a_secret_quoted_by_an_exception():
    try:
        raise RuntimeError(f"bad header Authorization: Bot {DISCORD_TOKEN_SHAPED}")
    except RuntimeError as exc:
        error = exc
    log = format_error_log(CommandContext("/roll", "haconn"), error)
    assert DISCORD_TOKEN_SHAPED not in log
    assert REDACTED in log


def test_error_log_layout():
    try:
        try:
            int("3.5")
        except ValueError as cause:
            raise errors.StatValueError("STR", "3.5", "Play C", "S3003") from cause
    except errors.StatValueError as exc:
        error = exc
    ctx = CommandContext("/attack", "haconn")
    ctx.add(weapon="ดาบใหญ่", type="adv")
    ctx.add(skill="Swordsmanship", attr="STR", char="S3003", name="Play C")

    lines = format_error_log(ctx, error).splitlines()

    assert lines[0] == "ERROR E203 /attack user=haconn char=S3003 name=Play C"
    assert lines[1] == "    weapon=ดาบใหญ่ skill=Swordsmanship attr=STR type=adv"
    assert lines[2] == "    stat cell is not a whole number: tab='Final Sum' column='STR' raw='3.5'"
    assert lines[3] == "    ValueError: invalid literal for int() with base 10: '3.5'"
    assert re.fullmatch(r"    \(test_reporting\.py:\d+ in test_error_log_layout\)", lines[4])


def test_error_log_quotes_blank_raw_value_and_keeps_windows_paths_readable():
    error = errors.GoogleAuthError(r"C:\keys\sa.json", None, "file not found")
    blank = errors.StatValueError("STR", "", "Aria", "S1")
    assert r"json_path='C:\keys\sa.json'" in format_error_log(CommandContext("/roll"), error)
    assert "raw=''" in format_error_log(CommandContext("/roll"), blank)
