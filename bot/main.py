"""Bot entrypoint. Builds the discord.py Bot, wires up the sheets layer and
slash commands. Can be run standalone (`python -m bot.main`) for local testing,
or imported by the GUI controller (`gui/bot_runner.py`) which manages its own
event loop/thread and calls `build_bot()` + `bot.start(token)` directly.

Log output goes to the "bot" logger (and its children); the GUI forwards it
to the controller's log box, standalone mode prints it to the console.
"""

from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from bot.commands import DiceCog, report_error, setup_commands
from bot.models import WeaponOption
from bot.reporting import CommandContext
from bot.sheets import SheetsClient

logger = logging.getLogger(__name__)

INTENTS = discord.Intents.default()


class DiceCommandTree(app_commands.CommandTree):
    """Last line of defence: errors raised outside a command body (argument
    conversion, checks, a command Discord still lists but the bot no longer
    has) get the same coded reply and log entry as errors inside one. The
    default handler would only print them to a console nobody sees."""

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        original = getattr(error, "original", None) or error
        command = interaction.command
        name = f"/{command.qualified_name}" if command is not None else "/(unknown command)"
        ctx = CommandContext(name, getattr(interaction.user, "name", None))
        await report_error(interaction, ctx, original)


class DiceBot(commands.Bot):
    """Bot subclass that wires up slash commands exactly once via setup_hook,
    which discord.py guarantees runs a single time before the first connect
    (unlike on_ready, which can fire again on reconnects)."""

    def __init__(self, sheets_client: SheetsClient):
        super().__init__(command_prefix="!", intents=INTENTS, tree_cls=DiceCommandTree)
        self.sheets_client = sheets_client
        self.dice_cog: DiceCog | None = None

    async def setup_hook(self) -> None:
        self.dice_cog = await setup_commands(self, self.sheets_client)
        await self.tree.sync()

    async def warm_up_sheets(self) -> list[WeaponOption]:
        """Startup check: reads the weapon list once (and caches it). Raises
        a coded BotUserError if the sheet can't be read."""
        if self.dice_cog is None:
            raise RuntimeError("slash commands are not set up yet")
        return await self.dice_cog.warm_up()


def build_bot(sheets_client: SheetsClient) -> DiceBot:
    return DiceBot(sheets_client)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
    load_dotenv()

    token = os.environ["DISCORD_BOT_TOKEN"]
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    sheet_name = os.environ["GOOGLE_SHEET_NAME"]

    sheets_client = SheetsClient(json_path, sheet_name)
    bot = build_bot(sheets_client)
    bot.run(token, log_handler=None)


if __name__ == "__main__":
    main()
