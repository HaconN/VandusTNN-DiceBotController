import json
from types import SimpleNamespace

import google.auth.exceptions
import gspread
import pytest
import requests

from bot import errors
from bot.models import Character
from bot.sheets import (
    FINAL_SUM_SHEET,
    PLAYER_SKILL_SHEET,
    WEAPON_INFO_SHEET,
    SheetsClient,
    SheetTable,
    lookup_skill_value,
)

FINAL_SUM_HEADERS = ["Discord ID", "ID", "Name", "Race", "STR", "CON", "DEX", "INT", "WIS"]
WEAPON_HEADERS = ["Code", "Weapon Name", "Skill", "Attribute"]


def make_client(tabs: dict[str, list[list]]) -> SheetsClient:
    """A SheetsClient whose single batch request returns the given 2-D values."""
    client = SheetsClient("fake.json", "fake-sheet")
    client.requests = []  # type: ignore[attr-defined]

    def fake_fetch(requested):
        client.requests.append(list(requested))  # type: ignore[attr-defined]
        return {tab: tabs[tab] for tab in requested if tab in tabs}

    client._fetch_values = fake_fetch  # type: ignore[method-assign]
    return client


def final_sum(*rows):
    return {FINAL_SUM_SHEET: [FINAL_SUM_HEADERS, *rows]}


def api_error(status: int, message: str = "boom") -> gspread.exceptions.APIError:
    response = SimpleNamespace(
        status_code=status,
        text=message,
        json=lambda: {"error": {"code": status, "message": message, "status": "X"}},
    )
    return gspread.exceptions.APIError(response)


def failing_client(error: Exception) -> SheetsClient:
    client = SheetsClient("fake.json", "fake-sheet")

    def fail(requested):
        raise error

    client._fetch_values = fail  # type: ignore[method-assign]
    return client


# ---- characters ----------------------------------------------------------


def test_load_character_found():
    client = make_client(final_sum(["Haconn", "S1001", "Aria", "Human", "12", "10", "14", "8", "9"]))

    char = client.load_character("Haconn")

    assert char.char_id == "S1001"
    assert char.name == "Aria"
    assert char.attribute_value("DEX") == 14


def test_load_character_not_found_is_e201():
    client = make_client(final_sum())
    with pytest.raises(errors.CharacterNotFoundError) as info:
        client.load_character("nobody")
    assert info.value.code == "E201"
    assert "nobody" in info.value.user_message


def test_load_character_case_insensitive_and_trimmed():
    client = make_client(final_sum([" Haconn ", "S1001", "Aria", "Human", "1", "1", "1", "1", "1"]))
    assert client.load_character("haconn").char_id == "S1001"


def test_missing_required_column_is_e304():
    client = make_client({FINAL_SUM_SHEET: [["ID", "Name", "STR"], ["S1", "Aria", "3"]]})
    with pytest.raises(errors.ColumnMissingError) as info:
        client.load_character("haconn")
    assert info.value.code == "E304"
    assert info.value.details == {"tab": "Final Sum", "column": "Discord ID"}


def test_missing_stat_column_is_e304_when_that_stat_is_used():
    client = make_client({FINAL_SUM_SHEET: [["Discord ID", "ID", "Name", "DEX"], ["haconn", "S1", "Aria", "4"]]})
    char = client.load_character("haconn")
    assert char.attribute_value("DEX") == 4
    with pytest.raises(errors.ColumnMissingError) as info:
        char.attribute_value("STR")
    assert info.value.details["column"] == "STR"


@pytest.mark.parametrize("raw", ["3.5", "", "   ", "abc", "#REF!", "inf"])
def test_non_whole_stat_is_e203_with_raw_value(raw):
    char = Character("haconn", "S3003", "Play C", "Human", {"STR": raw})
    with pytest.raises(errors.StatValueError) as info:
        char.attribute_value("STR")
    error = info.value
    assert error.code == "E203"
    assert error.details == {"tab": "Final Sum", "column": "STR", "raw": raw}
    assert "STR" in error.user_message and "Play C" in error.user_message
    # The original int() failure is kept as the cause, for the log.
    assert isinstance(error.__cause__, ValueError)


def test_decimal_stat_cause_quotes_the_cell():
    char = Character("haconn", "S3003", "Play C", "Human", {"STR": "3.5"})
    with pytest.raises(errors.StatValueError) as info:
        char.attribute_value("STR")
    assert str(info.value.__cause__) == "invalid literal for int() with base 10: '3.5'"


def test_blank_stat_message_says_blank():
    char = Character("haconn", "S3003", "Play C", "Human", {"STR": ""})
    with pytest.raises(errors.StatValueError) as info:
        char.attribute_value("STR")
    assert "ว่าง" in info.value.user_message


@pytest.mark.parametrize("raw,expected", [("5", 5), (" 7 ", 7), ("5.0", 5), (4, 4), (6.0, 6), ("-2", -2)])
def test_whole_stat_values_parse(raw, expected):
    char = Character("haconn", "S1", "Aria", "Human", {"STR": raw})
    assert char.attribute_value("str") == expected


def test_one_bad_stat_does_not_break_the_others():
    char = Character("haconn", "S1", "Aria", "Human", {"STR": "oops", "DEX": "3"})
    assert char.attribute_value("DEX") == 3


# ---- skills --------------------------------------------------------------


def skill_table(*rows, headers=("ID", "Name", "Knife Fighting", "Swordsmanship")):
    return SheetTable.from_values(PLAYER_SKILL_SHEET, [list(headers), *rows])


ARIA = Character("haconn", "S1001", "Aria", "Human", {})


def test_lookup_skill_value():
    table = skill_table(["S1001", "Aria", "5", "2"])
    assert lookup_skill_value(table, ARIA, "Knife Fighting") == 5
    assert lookup_skill_value(table, ARIA, "Swordsmanship") == 2


def test_blank_skill_cell_is_zero():
    table = skill_table(["S1001", "Aria", "", "2"])
    assert lookup_skill_value(table, ARIA, "Knife Fighting") == 0


def test_short_row_skill_is_zero():
    # The API drops trailing blank cells, so the row is shorter than the header.
    table = skill_table(["S1001", "Aria", "5"])
    assert lookup_skill_value(table, ARIA, "Swordsmanship") == 0


def test_unknown_skill_column_is_e301():
    table = skill_table(["S1001", "Aria", "5", "2"])
    with pytest.raises(errors.SkillNotFoundError) as info:
        lookup_skill_value(table, ARIA, "Archery")
    assert info.value.code == "E301"


def test_missing_skill_row_is_e202():
    table = skill_table(["S9999", "Bob", "5", "2"])
    with pytest.raises(errors.CharacterSkillRowNotFoundError) as info:
        lookup_skill_value(table, ARIA, "Knife Fighting")
    assert info.value.code == "E202"


@pytest.mark.parametrize("raw", ["2.5", "two"])
def test_non_whole_skill_is_e204_with_raw_value(raw):
    table = skill_table(["S1001", "Aria", raw, "2"])
    with pytest.raises(errors.SkillValueError) as info:
        lookup_skill_value(table, ARIA, "Knife Fighting")
    assert info.value.code == "E204"
    assert info.value.details["raw"] == raw


# ---- weapons -------------------------------------------------------------


def weapons_client(*rows):
    return make_client({WEAPON_INFO_SHEET: [WEAPON_HEADERS, *rows]})


def test_fetch_weapons_single_mode():
    weapons = weapons_client(["W01", "Longsword", "Swordsmanship", "STR"]).fetch_weapons()

    assert len(weapons) == 1
    w = weapons[0]
    assert w.display_name == "Longsword"
    assert w.skill == "Swordsmanship"
    assert w.attribute == "STR"


def test_fetch_weapons_multiline_split_thrown():
    weapons = weapons_client(["W02", "Knife", "Knife Fighting\nThrown Weapon Fighting", "DEX\nSTR"]).fetch_weapons()

    assert len(weapons) == 2

    melee = next(w for w in weapons if w.skill == "Knife Fighting")
    assert melee.display_name == "Knife"
    assert melee.attribute == "DEX"

    thrown = next(w for w in weapons if w.skill == "Thrown Weapon Fighting")
    assert thrown.display_name == "Knife (ขว้าง)"
    assert thrown.attribute == "STR"


def test_fetch_weapons_multiline_skill_single_shared_attribute():
    weapons = weapons_client(
        ["W03", "War Hammer", "Impact Weapon Fighting\nThrown Weapon Fighting", "STR"]
    ).fetch_weapons()

    assert len(weapons) == 2

    melee = next(w for w in weapons if w.skill == "Impact Weapon Fighting")
    assert melee.display_name == "War Hammer"
    assert melee.attribute == "STR"

    thrown = next(w for w in weapons if w.skill == "Thrown Weapon Fighting")
    assert thrown.display_name == "War Hammer (ขว้าง)"
    assert thrown.attribute == "STR"


def test_fetch_weapons_skips_blank_rows():
    weapons = weapons_client(["", "", "", ""], ["W01", "Bow", "Archery", "DEX"]).fetch_weapons()

    assert len(weapons) == 1
    assert weapons[0].display_name == "Bow"


# ---- request shape -------------------------------------------------------


def test_load_attack_data_reads_all_three_tabs_in_one_request():
    client = make_client(
        {
            **final_sum(["haconn", "S1", "Aria", "Human", "1", "1", "1", "1", "1"]),
            PLAYER_SKILL_SHEET: [["ID", "Name"], ["S1", "Aria"]],
            WEAPON_INFO_SHEET: [WEAPON_HEADERS, ["W01", "Bow", "Archery", "DEX"]],
        }
    )

    data = client.load_attack_data()

    assert client.requests == [[FINAL_SUM_SHEET, PLAYER_SKILL_SHEET, WEAPON_INFO_SHEET]]
    assert [w.display_name for w in data.weapons] == ["Bow"]
    assert data.final_sum.rows[0]["Discord ID"] == "haconn"


class FakeSpreadsheet:
    def __init__(self, response=None, error=None, titles=()):
        self.response = response
        self.error = error
        self.titles = list(titles)
        self.batch_calls = []

    def values_batch_get(self, ranges):
        self.batch_calls.append(ranges)
        if self.error is not None:
            raise self.error
        return self.response

    def worksheets(self):
        return [SimpleNamespace(title=title) for title in self.titles]


def test_fetch_values_quotes_tab_names_and_maps_ranges():
    spreadsheet = FakeSpreadsheet(
        response={"valueRanges": [{"values": [["Discord ID", "ID", "Name"]]}, {}]}
    )
    client = SheetsClient("fake.json", "fake-sheet")
    client._spreadsheet_handle = lambda: spreadsheet  # type: ignore[method-assign]

    values = client._fetch_values([FINAL_SUM_SHEET, PLAYER_SKILL_SHEET])

    assert spreadsheet.batch_calls == [["'Final Sum'", "'Player Skill'"]]
    assert values == {FINAL_SUM_SHEET: [["Discord ID", "ID", "Name"]], PLAYER_SKILL_SHEET: []}


def test_missing_tab_is_e303_naming_the_tab():
    spreadsheet = FakeSpreadsheet(
        error=api_error(400, "Unable to parse range: 'Player Skill'"),
        titles=["Final Sum", "Weapon Info", "Notes"],
    )
    client = SheetsClient("fake.json", "fake-sheet")
    client._spreadsheet_handle = lambda: spreadsheet  # type: ignore[method-assign]

    with pytest.raises(errors.WorksheetMissingError) as info:
        client.load_attack_data()
    assert info.value.code == "E303"
    assert info.value.details["tab"] == "Player Skill"
    assert "Notes" in info.value.details["available"]


# ---- Google / network failures ---------------------------------------------


@pytest.mark.parametrize(
    "error,expected_code",
    [
        (api_error(403, "The caller does not have permission"), "E403"),
        (PermissionError(), "E403"),
        (api_error(404, "Requested entity was not found."), "E404"),
        (gspread.SpreadsheetNotFound(), "E404"),
        (api_error(429, "Quota exceeded"), "E429"),
        (api_error(401, "Request had invalid authentication credentials."), "E401"),
        (api_error(500, "Internal error"), "E499"),
        (api_error(503, "The service is currently unavailable."), "E499"),
        (google.auth.exceptions.RefreshError("invalid_grant: Invalid JWT Signature."), "E401"),
        (google.auth.exceptions.TransportError("connection refused"), "E450"),
        (requests.exceptions.ConnectionError("Max retries exceeded"), "E450"),
        (requests.exceptions.ConnectTimeout("connect timed out"), "E450"),
        (requests.exceptions.ReadTimeout("read timed out"), "E408"),
    ],
)
def test_google_errors_are_translated_to_codes(error, expected_code):
    client = failing_client(error)
    with pytest.raises(errors.BotUserError) as info:
        client.fetch_weapons()
    assert info.value.code == expected_code
    assert info.value.__cause__ is error


def test_unrelated_exception_is_not_disguised():
    client = failing_client(RuntimeError("bug"))
    with pytest.raises(RuntimeError):
        client.fetch_weapons()


# ---- service account file ---------------------------------------------------

FAKE_PRIVATE_KEY = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCSECRETSECRETSECRET\n-----END PRIVATE KEY-----\n"


def write_service_account(tmp_path, **overrides):
    data = {
        "type": "service_account",
        "project_id": "demo",
        "private_key_id": "0123456789abcdef0123456789abcdef01234567",
        "private_key": FAKE_PRIVATE_KEY,
        "client_email": "dice-bot@demo.iam.gserviceaccount.com",
        "client_id": "1234567890",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    data.update(overrides)
    path = tmp_path / "sa.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_missing_json_file_is_e401(tmp_path):
    path = tmp_path / "nope.json"
    client = SheetsClient(str(path), "sheet")
    with pytest.raises(errors.GoogleAuthError) as info:
        client.fetch_weapons()
    assert info.value.code == "E401"
    assert info.value.details == {"json_path": str(path)}


def test_corrupt_json_file_is_e401(tmp_path):
    path = tmp_path / "sa.json"
    path.write_text("{ this is not json", encoding="utf-8")
    client = SheetsClient(str(path), "sheet")
    with pytest.raises(errors.GoogleAuthError) as info:
        client.fetch_weapons()
    assert info.value.code == "E401"


def test_bad_key_is_e401_with_client_email_and_no_key_material(tmp_path):
    path = write_service_account(tmp_path)
    client = SheetsClient(str(path), "sheet")
    with pytest.raises(errors.GoogleAuthError) as info:
        client.fetch_weapons()
    error = info.value
    assert error.details["client_email"] == "dice-bot@demo.iam.gserviceaccount.com"
    everything = " ".join([error.user_message, error.log_message, repr(error.details), str(error.__cause__)])
    assert "SECRET" not in everything
    assert "0123456789abcdef" not in everything


def test_service_account_email_reads_only_that_field(tmp_path):
    client = SheetsClient(str(write_service_account(tmp_path)), "sheet")
    assert client.service_account_email() == "dice-bot@demo.iam.gserviceaccount.com"


def test_service_account_email_is_none_for_unreadable_file(tmp_path):
    client = SheetsClient(str(tmp_path / "missing.json"), "sheet")
    assert client.service_account_email() is None
