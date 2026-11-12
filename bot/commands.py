"""Slash commands: /roll and /attack."""

from __future__ import annotations

import re

import discord
from discord import app_commands
from discord.ext import commands

from bot import dice as dice_module
from bot.errors import (
    BotUserError,
    CharacterNotFoundError,
    DiceAndAttributeConflictError,
    InvalidDiceCountError,
    InvalidDiceCountRangeError,
    InvalidDiceNotationError,
    InvalidDieSizeError,
    SkillNotFoundError,
    WeaponNotFoundError,
)
from bot.models import ATTRIBUTE_NAMES
from bot.sheets import SheetsClient

ROLL_TYPE_CHOICES = [
    app_commands.Choice(name="Normal", value="normal"),
    app_commands.Choice(name="ADV", value="adv"),
    app_commands.Choice(name="DIS", value="dis"),
]

ATTRIBUTE_CHOICES = [app_commands.Choice(name=a, value=a) for a in ATTRIBUTE_NAMES]

DICE_NOTATION_RE = re.compile(r"^(\d+)\s*d\s*(\d+)$", re.IGNORECASE)


def parse_dice_notation(notation: str) -> tuple[int, int]:
    """Parses NdM dice notation (e.g. "3d6") into (count, faces).

    Raises InvalidDiceNotationError for malformed input, InvalidDiceCountRangeError
    if count is outside 1-100, and InvalidDieSizeError if faces isn't a supported size.
    """
    match = DICE_NOTATION_RE.match(notation.strip())
    if not match:
        raise InvalidDiceNotationError(notation)
    count, faces = int(match.group(1)), int(match.group(2))
    if not (1 <= count <= 100):
        raise InvalidDiceCountRangeError(count)
    if faces not in dice_module.SUPPORTED_FACES:
        raise InvalidDieSizeError(faces)
    return count, faces


class DiceCog(commands.Cog):
    def __init__(self, bot: commands.Bot, sheets_client: SheetsClient):
        self.bot = bot
        self.sheets = sheets_client

    @app_commands.command(name="roll", description="ทอยลูกเต๋าระบบ SP")
    @app_commands.describe(
        type="ประเภทการทอย",
        attribute="สเตตัสที่ใช้ (ไม่ระบุ = ทอย 6d6 ธรรมดา ไม่ต้องมีตัวละคร)",
        dice="สัญกรณ์ลูกเต๋า เช่น 3d6, 2d8, 4d20 (ใช้แทน attribute ไม่ได้พร้อมกัน)",
    )
    @app_commands.choices(type=ROLL_TYPE_CHOICES, attribute=ATTRIBUTE_CHOICES)
    async def roll(
        self,
        interaction: discord.Interaction,
        type: app_commands.Choice[str],
        attribute: app_commands.Choice[str] | None = None,
        dice: str | None = None,
    ):
        try:
            if dice is not None and attribute is not None:
                raise DiceAndAttributeConflictError()

            if dice is not None:
                num_dice, faces = parse_dice_notation(dice)
            elif attribute is not None:
                character = self.sheets.find_character_by_discord_username(interaction.user.name)
                if character is None:
                    raise CharacterNotFoundError()
                num_dice = character.attribute_value(attribute.value)
                faces = 6
            else:
                num_dice = 6
                faces = 6

            if num_dice <= 0:
                raise InvalidDiceCountError(num_dice)

            rolls, sp = dice_module.roll_dice(num_dice, type.value, faces)
            roll_line = dice_module.format_roll_line(type.value, num_dice, rolls, faces)
            await interaction.response.send_message(f"{roll_line}\nSP: {sp}")
        except BotUserError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @app_commands.command(name="attack", description="โจมตีด้วยอาวุธ")
    @app_commands.describe(weapon="เลือกอาวุธ", type="ประเภทการทอย")
    @app_commands.choices(type=ROLL_TYPE_CHOICES)
    async def attack(
        self,
        interaction: discord.Interaction,
        weapon: str,
        type: app_commands.Choice[str],
    ):
        try:
            weapons = self.sheets.fetch_weapons()
            matched = next((w for w in weapons if w.display_name == weapon), None)
            if matched is None:
                raise WeaponNotFoundError(weapon)

            character = self.sheets.find_character_by_discord_username(interaction.user.name)
            if character is None:
                raise CharacterNotFoundError()

            attribute_value = character.attribute_value(matched.attribute)
            skill_value = self.sheets.find_skill_value(character.char_id, matched.skill)
            if skill_value is None:
                raise SkillNotFoundError(matched.skill)

            num_dice = attribute_value + skill_value
            if num_dice <= 0:
                raise InvalidDiceCountError(num_dice)

            rolls, sp = dice_module.roll_dice(num_dice, type.value)
            roll_line = dice_module.format_roll_line(type.value, num_dice, rolls)
            breakdown = (
                f"{matched.skill} {skill_value} + {matched.attribute} {attribute_value} = {num_dice}d6"
            )

            message = (
                f"{character.name} use {matched.display_name}\n"
                f"{breakdown}\n"
                f"{roll_line}\n"
                f"SP: {sp}"
            )
            await interaction.response.send_message(message)
        except BotUserError as e:
            await interaction.response.send_message(str(e), ephemeral=True)
        except ValueError as e:
            await interaction.response.send_message(f"เกิดข้อผิดพลาด: {e}", ephemeral=True)

    @attack.autocomplete("weapon")
    async def weapon_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            weapons = self.sheets.fetch_weapons()
        except Exception:
            return []
        current_lower = current.lower()
        matches = [w for w in weapons if current_lower in w.display_name.lower()]
        return [app_commands.Choice(name=w.display_name, value=w.display_name) for w in matches[:25]]


async def setup_commands(bot: commands.Bot, sheets_client: SheetsClient) -> None:
    await bot.add_cog(DiceCog(bot, sheets_client))
