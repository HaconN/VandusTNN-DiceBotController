import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from discord import app_commands

from bot import dice
from bot.commands import DiceCog
from bot.models import Character, WeaponOption


class StubSheetsClient:
    def __init__(self, character=None, skill_values=None, weapons=None):
        self.character = character
        self.skill_values = skill_values or {}
        self.weapons = weapons or []

    def find_character_by_discord_id(self, discord_id):
        return self.character

    def find_skill_value(self, char_id, skill_name):
        return self.skill_values.get(skill_name)

    def fetch_weapons(self):
        return self.weapons


def make_interaction(user_id=111, display_name="Aria"):
    interaction = SimpleNamespace()
    interaction.user = SimpleNamespace(id=user_id, display_name=display_name)
    interaction.response = SimpleNamespace(send_message=AsyncMock())
    return interaction


def choice(value: str) -> app_commands.Choice[str]:
    return app_commands.Choice(name=value, value=value)


def run(coro):
    return asyncio.run(coro)


def test_roll_without_attribute_always_6d6(monkeypatch):
    sequence = iter([3, 4, 4, 1, 6, 5])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    cog = DiceCog(bot=None, sheets_client=StubSheetsClient())
    interaction = make_interaction()

    run(cog.roll.callback(cog, interaction, choice("normal"), None))

    interaction.response.send_message.assert_awaited_once()
    (message,), kwargs = interaction.response.send_message.call_args
    assert message == "rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5\nSP: 4"
    assert kwargs.get("ephemeral") in (None, False)


def test_roll_with_attribute_looks_up_character(monkeypatch):
    sequence = iter([5, 5])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    character = Character(
        discord_id="111", char_id="S1001", name="Aria", race="Human",
        attributes={"STR": 2, "CON": 1, "DEX": 1, "INT": 1, "WIS": 1},
    )
    cog = DiceCog(bot=None, sheets_client=StubSheetsClient(character=character))
    interaction = make_interaction()

    run(cog.roll.callback(cog, interaction, choice("normal"), choice("STR")))

    (message,), kwargs = interaction.response.send_message.call_args
    assert "2d6" in message
    assert kwargs.get("ephemeral") in (None, False)


def test_roll_with_attribute_no_character_is_ephemeral_thai_error():
    cog = DiceCog(bot=None, sheets_client=StubSheetsClient(character=None))
    interaction = make_interaction()

    run(cog.roll.callback(cog, interaction, choice("normal"), choice("STR")))

    (message,), kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    assert "ไม่พบตัวละคร" in message


def test_attack_success_formats_breakdown(monkeypatch):
    sequence = iter([3, 4, 4, 1, 6, 5])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    character = Character(
        discord_id="111", char_id="S1001", name="Aria", race="Human",
        attributes={"STR": 4, "CON": 1, "DEX": 1, "INT": 1, "WIS": 1},
    )
    weapon = WeaponOption(
        display_name="Knife", base_name="Knife", code="W02", skill="Knife Fighting", attribute="STR"
    )
    sheets = StubSheetsClient(character=character, skill_values={"Knife Fighting": 2}, weapons=[weapon])
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = make_interaction(display_name="Aria")

    run(cog.attack.callback(cog, interaction, "Knife", choice("normal")))

    (message,), kwargs = interaction.response.send_message.call_args
    assert message == (
        "Aria use Knife\n"
        "rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5\n"
        "Knife Fighting 2 + STR 4 = 6d6\n"
        "SP: 4"
    )
    assert kwargs.get("ephemeral") in (None, False)


def test_attack_unknown_weapon_is_ephemeral_error():
    cog = DiceCog(bot=None, sheets_client=StubSheetsClient(weapons=[]))
    interaction = make_interaction()

    run(cog.attack.callback(cog, interaction, "Nonexistent Weapon", choice("normal")))

    (message,), kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True
    assert "ไม่พบอาวุธ" in message


def test_attack_zero_dice_is_ephemeral_error(monkeypatch):
    character = Character(
        discord_id="111", char_id="S1001", name="Aria", race="Human",
        attributes={"STR": 0, "CON": 0, "DEX": 0, "INT": 0, "WIS": 0},
    )
    weapon = WeaponOption(
        display_name="Fists", base_name="Fists", code="W00", skill="Unarmed Fighting", attribute="STR"
    )
    sheets = StubSheetsClient(character=character, skill_values={"Unarmed Fighting": 0}, weapons=[weapon])
    cog = DiceCog(bot=None, sheets_client=sheets)
    interaction = make_interaction()

    run(cog.attack.callback(cog, interaction, "Fists", choice("normal")))

    (message,), kwargs = interaction.response.send_message.call_args
    assert kwargs.get("ephemeral") is True


@pytest.mark.parametrize("current,expected_count", [("kni", 1), ("zzz", 0), ("", 2)])
def test_weapon_autocomplete_filters_case_insensitive(current, expected_count):
    weapons = [
        WeaponOption("Knife", "Knife", "W02", "Knife Fighting", "DEX"),
        WeaponOption("Bow", "Bow", "W03", "Archery", "DEX"),
    ]
    cog = DiceCog(bot=None, sheets_client=StubSheetsClient(weapons=weapons))
    interaction = make_interaction()

    results = run(cog.weapon_autocomplete(interaction, current))

    assert len(results) == expected_count
