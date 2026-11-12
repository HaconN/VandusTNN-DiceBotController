import asyncio
import json
import logging
import threading
import time
from types import SimpleNamespace

import gspread
import pytest
from discord import app_commands

from bot import dice
from bot.commands import DiceCog, report_error
from bot.weapon_cache import WeaponCache
from tests.fakes import FakeInteraction, make_sheets


def choice(value: str) -> app_commands.Choice[str]:
    return app_commands.Choice(name=value, value=value)


def run(coro):
    return asyncio.run(coro)


def fixed_rolls(monkeypatch, values):
    sequence = iter(values)
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))


def roll(cog, interaction, roll_type="normal", attribute=None, notation=None):
    run(cog.roll.callback(cog, interaction, choice(roll_type), choice(attribute) if attribute else None, notation))


def attack(cog, interaction, weapon, roll_type="normal"):
    run(cog.attack.callback(cog, interaction, weapon, choice(roll_type)))


@pytest.fixture
def bot_log(caplog):
    caplog.set_level(logging.INFO, logger="bot")
    return caplog


def log_text(caplog, level=logging.ERROR) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.levelno == level)


def assert_ephemeral_error(interaction, code):
    reply = interaction.reply
    assert reply.ephemeral is True
    assert reply.content.startswith(f"❌ [{code}] ")
    assert "Traceback" not in reply.content
    return reply.content


# ---- /roll -----------------------------------------------------------------


def test_roll_without_attribute_always_6d6(monkeypatch):
    fixed_rolls(monkeypatch, [3, 4, 4, 1, 6, 5])
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    roll(cog, interaction)

    assert interaction.response.deferred
    assert interaction.reply.content == "rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5\nSP: 4"
    assert interaction.reply.ephemeral is False
    assert sheets.requests == []  # no sheet needed


def test_roll_with_attribute_looks_up_character(monkeypatch):
    fixed_rolls(monkeypatch, [5, 5])
    sheets = make_sheets(characters=[["haconn", "S1001", "Aria", "Human", "2", "1", "1", "1", "1"]])
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    roll(cog, interaction, attribute="STR")

    assert "2d6" in interaction.reply.content
    assert interaction.reply.ephemeral is False
    assert sheets.requests == [["Final Sum"]]


def test_roll_with_attribute_no_character_is_ephemeral_e201_after_defer():
    cog = DiceCog(bot=None, sheets_client=make_sheets(characters=[]))
    interaction = FakeInteraction()

    roll(cog, interaction, attribute="STR")

    content = assert_ephemeral_error(interaction, "E201")
    assert "ไม่พบตัวละคร" in content
    # The public "thinking..." message is removed so the error is private.
    assert interaction.deleted_original is True
    assert interaction.reply.via == "followup"


def test_roll_with_dice_notation(monkeypatch):
    fixed_rolls(monkeypatch, [5, 3])
    cog = DiceCog(bot=None, sheets_client=make_sheets())
    interaction = FakeInteraction()

    roll(cog, interaction, "adv", notation="2d8")

    assert interaction.reply.content == "rolled [ADV] 2d8: 5, 3\nSP: 1"
    assert interaction.reply.ephemeral is False


def test_roll_with_dice_notation_is_case_insensitive_and_trims_whitespace(monkeypatch):
    fixed_rolls(monkeypatch, [3, 4, 4])
    cog = DiceCog(bot=None, sheets_client=make_sheets())
    interaction = FakeInteraction()

    roll(cog, interaction, notation="  3D6  ")

    assert "3d6" in interaction.reply.content
    assert interaction.reply.ephemeral is False


@pytest.mark.parametrize(
    "attribute,notation,code",
    [
        ("STR", "3d6", "E101"),
        (None, "abc", "E102"),
        (None, "3x6", "E102"),
        (None, "d6", "E102"),
        (None, "3d", "E102"),
        (None, "3d7", "E103"),
        (None, "1d3", "E103"),
        (None, "5d100", "E103"),
        (None, "0d6", "E104"),
        (None, "101d6", "E104"),
    ],
)
def test_roll_input_errors_answer_at_once_without_defer(attribute, notation, code):
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    roll(cog, interaction, attribute=attribute, notation=notation)

    assert_ephemeral_error(interaction, code)
    assert interaction.response.deferred is False
    assert interaction.reply.via == "response"
    assert sheets.requests == []


def test_roll_with_blank_stat_is_e203():
    sheets = make_sheets(characters=[["haconn", "S1001", "Aria", "Human", "", "1", "1", "1", "1"]])
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    roll(cog, interaction, attribute="STR")

    content = assert_ephemeral_error(interaction, "E203")
    assert "ว่าง" in content


# ---- /attack ---------------------------------------------------------------


def test_attack_success_formats_breakdown(monkeypatch):
    fixed_rolls(monkeypatch, [3, 4, 4, 1, 6, 5])
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets)
    # Discord display name intentionally differs from the sheet's character name,
    # to prove the reply uses character.name and not interaction.user.display_name.
    interaction = FakeInteraction(display_name="SomeDiscordNick")

    attack(cog, interaction, "Knife")

    assert interaction.reply.content == (
        "Aria Silverleaf use Knife\n"
        "Knife Fighting 2 + STR 4 = 6d6\n"
        "rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5\n"
        "SP: 4"
    )
    assert interaction.reply.ephemeral is False


def test_attack_reads_the_sheet_once():
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets)

    attack(cog, FakeInteraction(), "Knife")

    assert sheets.requests == [["Final Sum", "Player Skill", "Weapon Info"]]


def test_attack_unknown_weapon_is_e105():
    cog = DiceCog(bot=None, sheets_client=make_sheets())
    interaction = FakeInteraction()

    attack(cog, interaction, "Nonexistent Weapon")

    content = assert_ephemeral_error(interaction, "E105")
    assert "ไม่พบอาวุธ" in content


def test_attack_zero_dice_is_e205():
    sheets = make_sheets(
        characters=[["haconn", "S1001", "Aria", "Human", "0", "0", "0", "0", "0"]],
        skills=[["S1001", "Aria", "", "", ""]],
    )
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    assert_ephemeral_error(interaction, "E205")


def test_attack_too_many_dice_is_e206():
    sheets = make_sheets(
        characters=[["haconn", "S1001", "Aria", "Human", "90", "1", "1", "1", "1"]],
        skills=[["S1001", "Aria", "20", "", ""]],
    )
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    assert_ephemeral_error(interaction, "E206")


def test_attack_with_decimal_stat_is_e203_and_logged_with_raw_value(bot_log):
    """The reported bug's shape: one player's STR cell breaks one weapon."""
    sheets = make_sheets(
        characters=[["haconn", "S3003", "Play C", "Human", "3.5", "2", "2", "2", "2"]],
        skills=[["S3003", "Play C", "1", "3", ""]],
    )
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    attack(cog, interaction, "ดาบใหญ่")

    content = assert_ephemeral_error(interaction, "E203")
    assert "STR" in content and "Play C" in content
    assert "3.5" not in content  # the raw value goes to the log, not the player

    log = log_text(bot_log)
    assert "ERROR E203 /attack user=haconn char=S3003 name=Play C" in log
    assert "weapon=ดาบใหญ่ skill=Swordsmanship attr=STR" in log
    assert "raw='3.5'" in log
    assert "ValueError: invalid literal for int() with base 10: '3.5'" in log
    assert "models.py:" in log and "in attribute_value" in log


def test_attack_with_invalid_weapon_attribute_is_e302_not_a_crash(bot_log):
    """This used to raise an uncaught KeyError: no reply, no log."""
    sheets = make_sheets(weapons=[["SWD(G)", "ดาบใหญ่", "Swordsmanship", "Strength"]])
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    attack(cog, interaction, "ดาบใหญ่")

    content = assert_ephemeral_error(interaction, "E302")
    assert "Strength" in content
    log = log_text(bot_log)
    assert "ERROR E302 /attack user=haconn" in log
    assert "raw='Strength'" in log


def test_attack_skill_column_missing_is_e301():
    sheets = make_sheets(skill_headers=["ID", "Name", "Knife Fighting", "Archery"], skills=[["S1001", "Aria", "2", ""]])
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    attack(cog, interaction, "ดาบใหญ่")

    assert_ephemeral_error(interaction, "E301")


def test_attack_skill_row_missing_is_e202():
    cog = DiceCog(bot=None, sheets_client=make_sheets(skills=[["S9999", "Someone", "1", "1", "1"]]))
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    assert_ephemeral_error(interaction, "E202")


def test_attack_decimal_skill_is_e204(bot_log):
    cog = DiceCog(bot=None, sheets_client=make_sheets(skills=[["S1001", "Aria", "2.5", "3", ""]]))
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    assert_ephemeral_error(interaction, "E204")
    assert "raw='2.5'" in log_text(bot_log)


def test_attack_blank_skill_counts_as_zero(monkeypatch):
    fixed_rolls(monkeypatch, [6, 6, 6, 6])
    cog = DiceCog(bot=None, sheets_client=make_sheets(skills=[["S1001", "Aria", "", "3", ""]]))
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    assert "Knife Fighting 0 + STR 4 = 4d6" in interaction.reply.content
    assert interaction.reply.ephemeral is False


def test_attack_character_not_found_is_e201():
    cog = DiceCog(bot=None, sheets_client=make_sheets())
    interaction = FakeInteraction(username="stranger")

    attack(cog, interaction, "Knife")

    assert "stranger" in assert_ephemeral_error(interaction, "E201")


# ---- failures outside the sheet data -----------------------------------------


def test_unexpected_exception_is_e900_with_traceback_in_log_only(bot_log):
    sheets = make_sheets()

    def explode(requested):
        raise RuntimeError("boom")

    sheets._fetch_values = explode
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    content = assert_ephemeral_error(interaction, "E900")
    assert "boom" not in content
    log = log_text(bot_log)
    assert "ERROR E900 /attack user=haconn" in log
    assert "Traceback (most recent call last)" in log
    assert "RuntimeError: boom" in log


def test_permission_error_is_e403_and_logs_client_email(bot_log):
    sheets = make_sheets()
    response = SimpleNamespace(
        status_code=403,
        text="denied",
        json=lambda: {"error": {"code": 403, "message": "The caller does not have permission", "status": "PERMISSION_DENIED"}},
    )

    def denied(requested):
        raise gspread.exceptions.APIError(response)

    sheets._fetch_values = denied
    sheets.service_account_email = lambda: "dice-bot@demo.iam.gserviceaccount.com"
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = FakeInteraction()

    roll(cog, interaction, attribute="DEX")

    assert_ephemeral_error(interaction, "E403")
    log = log_text(bot_log)
    assert "client_email='dice-bot@demo.iam.gserviceaccount.com'" in log
    assert "APIError: [403]: The caller does not have permission" in log


def test_slow_sheet_times_out_as_e408():
    sheets = make_sheets()

    def slow(requested):
        time.sleep(0.5)
        return {}

    sheets._fetch_values = slow
    cog = DiceCog(bot=None, sheets_client=sheets, sheets_timeout=0.05)
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    assert_ephemeral_error(interaction, "E408")


def test_sheet_calls_run_off_the_event_loop_thread():
    sheets = make_sheets()
    original = sheets._fetch_values
    seen = {}

    def recording(requested):
        seen["thread"] = threading.get_ident()
        return original(requested)

    sheets._fetch_values = recording
    cog = DiceCog(bot=None, sheets_client=sheets)

    async def go():
        seen["loop_thread"] = threading.get_ident()
        await cog.attack.callback(cog, FakeInteraction(), "Knife", choice("normal"))

    run(go())

    assert seen["thread"] != seen["loop_thread"]


def test_failure_to_reply_is_logged_e901_and_not_raised(bot_log):
    cog = DiceCog(bot=None, sheets_client=make_sheets())
    interaction = FakeInteraction(followup_error=RuntimeError("404 Not Found (error code: 10062): Unknown interaction"))

    attack(cog, interaction, "Knife")  # must not raise

    log = log_text(bot_log)
    assert "ERROR E901 /attack user=haconn" in log
    assert "Unknown interaction" in log


def test_auth_failure_never_logs_key_material(bot_log, tmp_path):
    key_file = tmp_path / "sa.json"
    key_file.write_text(
        json.dumps(
            {
                "type": "service_account",
                "private_key_id": "0123456789abcdef0123456789abcdef01234567",
                "private_key": "-----BEGIN PRIVATE KEY-----\nTOPSECRETKEYDATA\n-----END PRIVATE KEY-----\n",
                "client_email": "dice-bot@demo.iam.gserviceaccount.com",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        ),
        encoding="utf-8",
    )
    from bot.sheets import SheetsClient

    cog = DiceCog(bot=None, sheets_client=SheetsClient(str(key_file), "sheet"))
    interaction = FakeInteraction()

    attack(cog, interaction, "Knife")

    content = assert_ephemeral_error(interaction, "E401")
    log = log_text(bot_log)
    assert f"json_path='{key_file}'" in log
    assert "client_email='dice-bot@demo.iam.gserviceaccount.com'" in log
    for secret in ("TOPSECRETKEYDATA", "0123456789abcdef", "PRIVATE KEY"):
        assert secret not in log
        assert secret not in content


def test_report_error_backstop_replies_when_not_deferred(bot_log):
    from bot.reporting import CommandContext

    interaction = FakeInteraction()
    run(report_error(interaction, CommandContext("/attack", "haconn"), KeyError("STR")))

    assert_ephemeral_error(interaction, "E900")
    assert interaction.reply.via == "response"
    assert "KeyError: 'STR'" in log_text(bot_log)


def test_tree_on_error_reports_the_original_exception(bot_log):
    from bot.main import DiceBot

    bot = DiceBot(make_sheets())
    interaction = FakeInteraction()
    interaction.command = SimpleNamespace(qualified_name="attack")
    error = app_commands.AppCommandError("wrapper")
    error.original = ValueError("bad conversion")

    run(bot.tree.on_error(interaction, error))

    assert_ephemeral_error(interaction, "E900")
    assert "ERROR E900 /attack user=haconn" in log_text(bot_log)
    assert "ValueError: bad conversion" in log_text(bot_log)


# ---- activity log ------------------------------------------------------------


def test_successful_commands_are_logged_one_line_each(monkeypatch, bot_log):
    fixed_rolls(monkeypatch, [3, 4, 4, 1, 6, 5] + [6, 1, 5])
    cog = DiceCog(bot=None, sheets_client=make_sheets())

    attack(cog, FakeInteraction(), "Knife", "adv")
    roll(cog, FakeInteraction(), notation="3d8")

    lines = [r.getMessage() for r in bot_log.records if r.levelno == logging.INFO]
    assert lines == [
        "/attack haconn -> Aria Silverleaf, Knife, 6d6 ADV, SP 5",
        "/roll haconn -> 3d8 Normal, SP 2",
    ]


def test_roll_with_attribute_success_line_names_character(monkeypatch, bot_log):
    fixed_rolls(monkeypatch, [4, 4, 4, 4])
    cog = DiceCog(bot=None, sheets_client=make_sheets())

    roll(cog, FakeInteraction(), "dis", attribute="STR")

    assert [r.getMessage() for r in bot_log.records if r.levelno == logging.INFO] == [
        "/roll haconn -> Aria Silverleaf, STR 4d6 DIS, SP 0"
    ]


# ---- autocomplete --------------------------------------------------------------


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.mark.parametrize("current,expected_count", [("kni", 1), ("zzz", 0), ("", 3), ("ดาบ", 1)])
def test_weapon_autocomplete_filters_case_insensitive(current, expected_count):
    cog = DiceCog(bot=None, sheets_client=make_sheets())

    results = run(cog.weapon_autocomplete(FakeInteraction(), current))

    assert len(results) == expected_count


def test_autocomplete_uses_cache_within_ttl_and_refreshes_after():
    clock = FakeClock()
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets, weapon_cache=WeaponCache(ttl=60, clock=clock), clock=clock)

    run(cog.weapon_autocomplete(FakeInteraction(), "k"))
    run(cog.weapon_autocomplete(FakeInteraction(), "kn"))
    clock.now += 59
    run(cog.weapon_autocomplete(FakeInteraction(), "kni"))
    assert sheets.requests == [["Weapon Info"]]

    clock.now += 2
    run(cog.weapon_autocomplete(FakeInteraction(), "knif"))
    assert sheets.requests == [["Weapon Info"], ["Weapon Info"]]


def test_attack_refreshes_the_autocomplete_cache():
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets)

    attack(cog, FakeInteraction(), "Knife")
    run(cog.weapon_autocomplete(FakeInteraction(), "b"))

    assert sheets.requests == [["Final Sum", "Player Skill", "Weapon Info"]]


def test_autocomplete_failure_serves_stale_list_logs_once_and_backs_off(bot_log):
    clock = FakeClock()
    sheets = make_sheets()
    cog = DiceCog(bot=None, sheets_client=sheets, weapon_cache=WeaponCache(ttl=60, clock=clock), clock=clock)
    run(cog.weapon_autocomplete(FakeInteraction(), ""))  # fills the cache

    calls = []

    def failing(requested):
        calls.append(requested)
        raise ConnectionError("network down")

    sheets._fetch_values = failing
    clock.now += 61  # cache now stale

    first = run(cog.weapon_autocomplete(FakeInteraction(), ""))
    second = run(cog.weapon_autocomplete(FakeInteraction(), ""))

    assert len(first) == 3 and len(second) == 3  # stale list still offered
    assert len(calls) == 1  # no retry inside the back-off window
    warnings = [r.getMessage() for r in bot_log.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].startswith("WARNING E900 /attack autocomplete user=haconn: showing 3 cached weapons")
