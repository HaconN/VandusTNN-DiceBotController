from bot.sheets import SheetsClient


def make_client_with_records(records_by_sheet: dict[str, list[dict]]) -> SheetsClient:
    client = SheetsClient("fake.json", "fake-sheet")
    client._worksheet_records = lambda name: records_by_sheet.get(name, [])  # type: ignore[method-assign]
    return client


def test_find_character_by_discord_username_found():
    client = make_client_with_records(
        {
            "Final Sum": [
                {
                    "Discord ID": "Haconn",
                    "ID": "S1001",
                    "Name": "Aria",
                    "Race": "Human",
                    "STR": 12,
                    "CON": 10,
                    "DEX": 14,
                    "INT": 8,
                    "WIS": 9,
                }
            ]
        }
    )

    char = client.find_character_by_discord_username("Haconn")

    assert char is not None
    assert char.char_id == "S1001"
    assert char.name == "Aria"
    assert char.attribute_value("DEX") == 14


def test_find_character_by_discord_username_not_found():
    client = make_client_with_records({"Final Sum": []})
    assert client.find_character_by_discord_username("nobody") is None


def test_find_character_by_discord_username_case_insensitive():
    client = make_client_with_records(
        {
            "Final Sum": [
                {
                    "Discord ID": "Haconn",
                    "ID": "S1001",
                    "Name": "Aria",
                    "Race": "Human",
                    "STR": 12,
                    "CON": 10,
                    "DEX": 14,
                    "INT": 8,
                    "WIS": 9,
                }
            ]
        }
    )

    char = client.find_character_by_discord_username("haconn")

    assert char is not None
    assert char.char_id == "S1001"


def test_find_skill_value():
    client = make_client_with_records(
        {
            "Player Skill": [
                {"ID": "S1001", "Name": "Aria", "Knife Fighting": 5, "Swordsmanship": 2},
            ]
        }
    )

    assert client.find_skill_value("S1001", "Knife Fighting") == 5
    assert client.find_skill_value("S1001", "Swordsmanship") == 2
    assert client.find_skill_value("S1001", "Unknown Skill") is None
    assert client.find_skill_value("S9999", "Knife Fighting") is None


def test_find_skill_value_blank_cell_is_zero():
    client = make_client_with_records(
        {"Player Skill": [{"ID": "S1001", "Name": "Aria", "Archery": ""}]}
    )
    assert client.find_skill_value("S1001", "Archery") == 0


def test_fetch_weapons_single_mode():
    client = make_client_with_records(
        {
            "Weapon Info": [
                {"Code": "W01", "Weapon Name": "Longsword", "Skill": "Swordsmanship", "Attribute": "STR"},
            ]
        }
    )

    weapons = client.fetch_weapons()

    assert len(weapons) == 1
    w = weapons[0]
    assert w.display_name == "Longsword"
    assert w.skill == "Swordsmanship"
    assert w.attribute == "STR"


def test_fetch_weapons_multiline_split_thrown():
    client = make_client_with_records(
        {
            "Weapon Info": [
                {
                    "Code": "W02",
                    "Weapon Name": "Knife",
                    "Skill": "Knife Fighting\nThrown Weapon Fighting",
                    "Attribute": "DEX\nSTR",
                },
            ]
        }
    )

    weapons = client.fetch_weapons()

    assert len(weapons) == 2

    melee = next(w for w in weapons if w.skill == "Knife Fighting")
    assert melee.display_name == "Knife"
    assert melee.attribute == "DEX"

    thrown = next(w for w in weapons if w.skill == "Thrown Weapon Fighting")
    assert thrown.display_name == "Knife (ขว้าง)"
    assert thrown.attribute == "STR"


def test_fetch_weapons_multiline_skill_single_shared_attribute():
    client = make_client_with_records(
        {
            "Weapon Info": [
                {
                    "Code": "W03",
                    "Weapon Name": "War Hammer",
                    "Skill": "Impact Weapon Fighting\nThrown Weapon Fighting",
                    "Attribute": "STR",
                },
            ]
        }
    )

    weapons = client.fetch_weapons()

    assert len(weapons) == 2

    melee = next(w for w in weapons if w.skill == "Impact Weapon Fighting")
    assert melee.display_name == "War Hammer"
    assert melee.attribute == "STR"

    thrown = next(w for w in weapons if w.skill == "Thrown Weapon Fighting")
    assert thrown.display_name == "War Hammer (ขว้าง)"
    assert thrown.attribute == "STR"


def test_fetch_weapons_skips_blank_rows():
    client = make_client_with_records(
        {
            "Weapon Info": [
                {"Code": "", "Weapon Name": "", "Skill": "", "Attribute": ""},
                {"Code": "W01", "Weapon Name": "Bow", "Skill": "Archery", "Attribute": "DEX"},
            ]
        }
    )

    weapons = client.fetch_weapons()

    assert len(weapons) == 1
    assert weapons[0].display_name == "Bow"
