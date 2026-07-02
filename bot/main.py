"""Bot entrypoint. Builds the discord.py Bot, wires up the sheets layer and
slash commands. Can be run standalone (`python -m bot.main`) for local testing,
or imported by the GUI controller (`gui/bot_runner.py`) which manages its own
event loop/thread and calls `build_bot()` + `bot.start(token)` directly.
"""

from __future__ import annotations

import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bot.commands import setup_commands
from bot.sheets import SheetsClient

logger = logging.getLogger(__name__)

INTENTS = discord.Intents.default()


class DiceBot(commands.Bot):
    """Bot subclass that wires up slash commands exactly once via setup_hook,
    which discord.py guarantees runs a single time before the first connect
    (unlike on_ready, which can fire again on reconnects)."""

    def __init__(self, sheets_client: SheetsClient):
        super().__init__(command_prefix="!", intents=INTENTS)
        self.sheets_client = sheets_client

    async def setup_hook(self) -> None:
        await setup_commands(self, self.sheets_client)
        await self.tree.sync()


def build_bot(sheets_client: SheetsClient) -> DiceBot:
    return DiceBot(sheets_client)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv()

    token = os.environ["DISCORD_BOT_TOKEN"]
    json_path = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    sheet_name = os.environ["GOOGLE_SHEET_NAME"]

    sheets_client = SheetsClient(json_path, sheet_name)
    bot = build_bot(sheets_client)
    bot.run(token)


if __name__ == "__main__":
    main()
