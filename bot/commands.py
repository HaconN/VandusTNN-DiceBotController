"""Slash commands: /roll and /attack.

Every command body runs inside DiceCog._run_command, which turns any
exception into a coded, ephemeral Thai reply for the player plus one
technical entry in the bot log (shown in the controller's log box);
DiceCommandTree.on_error (bot/main.py) does the same for errors raised
before a body starts. Sheet reads run in a worker thread with a timeout,
after the interaction has been deferred, so a slow Google response can
neither block the bot nor run into Discord's 3-second reply limit.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Awaitable, Callable

import discord
from discord import app_commands
from discord.ext import commands

from bot import dice as dice_module
from bot.errors import (
    CharacterNotFoundError,
    DiceAndAttributeConflictError,
    InvalidDiceCountError,
    InvalidDiceCountRangeError,
    InvalidDiceNotationError,
    InvalidDieSizeError,
    InvalidWeaponAttributeError,
    SheetsTimeoutError,
    TooManyDiceError,
    UNEXPECTED_ERROR_CODE,
    WeaponNotFoundError,
)
from bot.models import ATTRIBUTE_NAMES, WeaponOption, normalize_attribute
from bot.reporting import (
    CommandContext,
    format_attack_success,
    format_error_log,
    format_reply_failure,
    format_roll_success,
    format_user_error,
    format_warning,
)
from bot.sheets import SheetsClient, find_character, lookup_skill_value, require_skill_column
from bot.weapon_cache import WeaponCache

logger = logging.getLogger(__name__)

# Overall limit for one command's sheet read (the HTTP layer has its own
# per-request timeout too). After a defer Discord waits up to 15 minutes,
# so this only has to be short enough that a player isn't left waiting.
SHEETS_TIMEOUT_SECONDS = 15.0
# Autocomplete cannot be deferred: it must answer within Discord's 3 s.
AUTOCOMPLETE_TIMEOUT_SECONDS = 2.5
# After a failed autocomplete refresh, serve the cached list for this long
# before trying the sheet again (and logging again).
AUTOCOMPLETE_RETRY_SECONDS = 30.0

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
    if count is outside MIN_DICE-MAX_DICE, and InvalidDieSizeError if faces isn't
    a supported size.
    """
    match = DICE_NOTATION_RE.match(notation.strip())
    if not match:
        raise InvalidDiceNotationError(notation)
    count, faces = int(match.group(1)), int(match.group(2))
    if not (dice_module.MIN_DICE <= count <= dice_module.MAX_DICE):
        raise InvalidDiceCountRangeError(count, dice_module.MIN_DICE, dice_module.MAX_DICE)
    if faces not in dice_module.SUPPORTED_FACES:
        raise InvalidDieSizeError(faces)
    return count, faces


def check_dice_count(num_dice: int) -> None:
    """For dice counts computed from the sheet."""
    if num_dice < dice_module.MIN_DICE:
        raise InvalidDiceCountError(num_dice)
    if num_dice > dice_module.MAX_DICE:
        raise TooManyDiceError(num_dice, dice_module.MAX_DICE)


# ---- error reporting (shared with the command tree's on_error) -------------


async def report_error(interaction: discord.Interaction, ctx: CommandContext, error: BaseException) -> None:
    """Logs one entry for the error and tells the player, ephemerally.
    Never raises."""
    try:
        logger.error(format_error_log(ctx, error))
    except Exception:
        logger.exception("ERROR %s %s: could not format the log entry for an error", UNEXPECTED_ERROR_CODE, ctx.command)
    try:
        text = format_user_error(error)
    except Exception:
        text = f"❌ [{UNEXPECTED_ERROR_CODE}]"
    await send_ephemeral(interaction, ctx, text)


async def send_ephemeral(interaction: discord.Interaction, ctx: CommandContext, text: str) -> None:
    """Sends a message only the player sees, whether or not the interaction
    was deferred. A failure to send is logged (E901), never raised."""
    try:
        if not interaction.response.is_done():
            await interaction.response.send_message(text, ephemeral=True)
            return
        # After defer() Discord shows a public "thinking..." message, and the
        # first followup edits that message in place, keeping it public even
        # with ephemeral=True. Delete it so the error arrives as a new,
        # ephemeral message instead.
        try:
            await interaction.delete_original_response()
        except discord.HTTPException:
            pass
        await interaction.followup.send(text, ephemeral=True)
    except Exception as exc:
        logger.error(format_reply_failure(ctx, exc))


# ---- the cog ---------------------------------------------------------------


class DiceCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        sheets_client: SheetsClient,
        *,
        weapon_cache: WeaponCache | None = None,
        sheets_timeout: float = SHEETS_TIMEOUT_SECONDS,
        autocomplete_timeout: float = AUTOCOMPLETE_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.bot = bot
        self.sheets = sheets_client
        self.weapon_cache = weapon_cache if weapon_cache is not None else WeaponCache(clock=clock)
        self.sheets_timeout = sheets_timeout
        self.autocomplete_timeout = autocomplete_timeout
        self._clock = clock
        self._weapon_refresh_lock = asyncio.Lock()
        self._autocomplete_retry_at = 0.0

    # ---- plumbing --------------------------------------------------------

    async def _call_sheets(self, fn: Callable[..., Any], *args: Any, timeout: float | None = None) -> Any:
        """Runs a blocking SheetsClient call in a worker thread, so the event
        loop keeps serving other players, with an overall timeout."""
        limit = self.sheets_timeout if timeout is None else timeout
        try:
            return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=limit)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            raise SheetsTimeoutError(limit) from exc

    async def _run_command(self, interaction: discord.Interaction, ctx: CommandContext, work: Awaitable[None]) -> None:
        try:
            await work
        except Exception as error:
            await report_error(interaction, ctx, error)

    async def warm_up(self) -> list[WeaponOption]:
        """Reads the weapon list once at startup: proves the sheet is
        reachable and fills the autocomplete cache."""
        weapons = await self._call_sheets(self.sheets.fetch_weapons)
        self.weapon_cache.store(weapons)
        return weapons

    # ---- /roll -------------------------------------------------------------

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
        attribute_name = attribute.value if attribute is not None else None
        ctx = CommandContext("/roll", interaction.user.name)
        ctx.add(attr=attribute_name, type=type.value, notation=dice)
        await self._run_command(interaction, ctx, self._roll(interaction, ctx, type.value, attribute_name, dice))

    async def _roll(
        self,
        interaction: discord.Interaction,
        ctx: CommandContext,
        roll_type: str,
        attribute: str | None,
        notation: str | None,
    ) -> None:
        # Input checks need no sheet, so they answer at once (ephemeral)
        # without a defer.
        if notation is not None and attribute is not None:
            raise DiceAndAttributeConflictError()
        num_dice, faces = 6, 6
        if notation is not None:
            num_dice, faces = parse_dice_notation(notation)

        await interaction.response.defer()

        character = None
        if attribute is not None:
            character = await self._call_sheets(self.sheets.load_character, ctx.user)
            ctx.add(char=character.char_id, name=character.name)
            num_dice = character.attribute_value(attribute)
        ctx.add(dice=f"{num_dice}d{faces}")
        check_dice_count(num_dice)

        rolls, sp = dice_module.roll_dice(num_dice, roll_type, faces)
        roll_line = dice_module.format_roll_line(roll_type, num_dice, rolls, faces)
        await interaction.followup.send(f"{roll_line}\nSP: {sp}")
        logger.info(
            format_roll_success(
                ctx.user,
                char_name=character.name if character is not None else None,
                attribute=attribute,
                num_dice=num_dice,
                faces=faces,
                roll_type=roll_type,
                sp=sp,
            )
        )

    # ---- /attack -----------------------------------------------------------

    @app_commands.command(name="attack", description="โจมตีด้วยอาวุธ")
    @app_commands.describe(weapon="เลือกอาวุธ", type="ประเภทการทอย")
    @app_commands.choices(type=ROLL_TYPE_CHOICES)
    async def attack(
        self,
        interaction: discord.Interaction,
        weapon: str,
        type: app_commands.Choice[str],
    ):
        ctx = CommandContext("/attack", interaction.user.name)
        ctx.add(weapon=weapon, type=type.value)
        await self._run_command(interaction, ctx, self._attack(interaction, ctx, weapon, type.value))

    async def _attack(
        self,
        interaction: discord.Interaction,
        ctx: CommandContext,
        weapon_name: str,
        roll_type: str,
    ) -> None:
        await interaction.response.defer()

        # One request for all three tabs; it also refreshes the weapon cache.
        data = await self._call_sheets(self.sheets.load_attack_data)
        self.weapon_cache.store(data.weapons)

        weapon = next((w for w in data.weapons if w.display_name == weapon_name), None)
        if weapon is None:
            raise WeaponNotFoundError(weapon_name)
        ctx.add(weapon=weapon.display_name, skill=weapon.skill, attr=weapon.attribute)

        # Weapon setup problems first: they fail for every player alike.
        attribute = normalize_attribute(weapon.attribute)
        if attribute is None:
            raise InvalidWeaponAttributeError(weapon.display_name, weapon.attribute)
        require_skill_column(data.player_skill, weapon.skill, weapon.display_name)

        character = find_character(data.final_sum, ctx.user)
        if character is None:
            raise CharacterNotFoundError(ctx.user)
        ctx.add(char=character.char_id, name=character.name)

        attribute_value = character.attribute_value(attribute)
        skill_value = lookup_skill_value(data.player_skill, character, weapon.skill)
        num_dice = attribute_value + skill_value
        ctx.add(dice=f"{num_dice}d6")
        check_dice_count(num_dice)

        rolls, sp = dice_module.roll_dice(num_dice, roll_type)
        roll_line = dice_module.format_roll_line(roll_type, num_dice, rolls)
        breakdown = f"{weapon.skill} {skill_value} + {attribute} {attribute_value} = {num_dice}d6"
        message = (
            f"{character.name} use {weapon.display_name}\n"
            f"{breakdown}\n"
            f"{roll_line}\n"
            f"SP: {sp}"
        )
        await interaction.followup.send(message)
        logger.info(
            format_attack_success(
                ctx.user,
                char_name=character.name,
                weapon=weapon.display_name,
                num_dice=num_dice,
                roll_type=roll_type,
                sp=sp,
            )
        )

    @attack.autocomplete("weapon")
    async def weapon_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        try:
            weapons = await self._weapons_for_autocomplete(interaction.user.name)
            current_lower = current.lower()
            matches = [w for w in weapons if current_lower in w.display_name.lower()]
            return [app_commands.Choice(name=w.display_name, value=w.display_name) for w in matches[:25]]
        except Exception as error:
            ctx = CommandContext("/attack autocomplete", getattr(interaction.user, "name", None))
            logger.warning(format_warning(ctx, error, "returned no suggestions"))
            return []

    async def _weapons_for_autocomplete(self, username: str) -> list[WeaponOption]:
        cached = self.weapon_cache.fresh()
        if cached is not None:
            return cached
        if self._clock() < self._autocomplete_retry_at:
            return self.weapon_cache.stale() or []
        # One refresh at a time; keystrokes that arrive meanwhile wait for it.
        async with self._weapon_refresh_lock:
            cached = self.weapon_cache.fresh()
            if cached is not None:
                return cached
            try:
                weapons = await self._call_sheets(self.sheets.fetch_weapons, timeout=self.autocomplete_timeout)
            except Exception as error:
                self._autocomplete_retry_at = self._clock() + AUTOCOMPLETE_RETRY_SECONDS
                stale = self.weapon_cache.stale() or []
                logger.warning(
                    format_warning(
                        CommandContext("/attack autocomplete", username),
                        error,
                        f"showing {len(stale)} cached weapons; next sheet try in {AUTOCOMPLETE_RETRY_SECONDS:g} s",
                    )
                )
                return stale
            self.weapon_cache.store(weapons)
            return weapons


async def setup_commands(bot: commands.Bot, sheets_client: SheetsClient) -> DiceCog:
    cog = DiceCog(bot, sheets_client)
    await bot.add_cog(cog)
    return cog
