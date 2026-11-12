"""Test doubles shared by the command tests: a fake Discord interaction that
records what the bot sent, and a SheetsClient whose single batch request
returns in-memory tables."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from bot.sheets import FINAL_SUM_SHEET, PLAYER_SKILL_SHEET, WEAPON_INFO_SHEET, SheetsClient

FINAL_SUM_HEADERS = ["Discord ID", "ID", "Name", "Race", "STR", "CON", "DEX", "INT", "WIS"]
SKILL_HEADERS = ["ID", "Name", "Knife Fighting", "Swordsmanship", "Archery"]
WEAPON_HEADERS = ["Code", "Weapon Name", "Skill", "Attribute"]

DEFAULT_CHARACTER = ["haconn", "S1001", "Aria Silverleaf", "Human", "4", "1", "1", "1", "1"]
DEFAULT_SKILLS = ["S1001", "Aria Silverleaf", "2", "3", ""]
DEFAULT_WEAPONS = [
    ["W02", "Knife", "Knife Fighting", "STR"],
    ["SWD(G)", "ดาบใหญ่", "Swordsmanship", "STR"],
    ["W03", "Bow", "Archery", "DEX"],
]


def make_sheets(
    characters=None,
    skills=None,
    weapons=None,
    *,
    skill_headers=None,
    final_sum_headers=None,
) -> SheetsClient:
    tabs = {
        FINAL_SUM_SHEET: [final_sum_headers or FINAL_SUM_HEADERS, *(characters if characters is not None else [DEFAULT_CHARACTER])],
        PLAYER_SKILL_SHEET: [skill_headers or SKILL_HEADERS, *(skills if skills is not None else [DEFAULT_SKILLS])],
        WEAPON_INFO_SHEET: [WEAPON_HEADERS, *(weapons if weapons is not None else DEFAULT_WEAPONS)],
    }
    client = SheetsClient("C:/keys/dice-bot.json", "Vandus Characters")
    client.requests = []  # type: ignore[attr-defined]

    def fake_fetch(requested):
        client.requests.append(list(requested))  # type: ignore[attr-defined]
        return {tab: tabs[tab] for tab in requested}

    client._fetch_values = fake_fetch  # type: ignore[method-assign]
    return client


@dataclass
class Sent:
    content: str
    ephemeral: bool
    via: str  # "response" or "followup"


class FakeResponse:
    def __init__(self, interaction: "FakeInteraction"):
        self._interaction = interaction
        self._done = False
        self.deferred = False

    def is_done(self) -> bool:
        return self._done

    async def defer(self, **kwargs) -> None:
        self.deferred = True
        self._done = True

    async def send_message(self, content, *, ephemeral=False, **kwargs) -> None:
        self._done = True
        self._interaction.sent.append(Sent(content, ephemeral, "response"))


class FakeFollowup:
    def __init__(self, interaction: "FakeInteraction"):
        self._interaction = interaction

    async def send(self, content, *, ephemeral=False, **kwargs) -> None:
        if self._interaction.followup_error is not None:
            raise self._interaction.followup_error
        self._interaction.sent.append(Sent(content, ephemeral, "followup"))


class FakeInteraction:
    def __init__(self, username="haconn", display_name="SomeDiscordNick", followup_error=None):
        self.user = SimpleNamespace(name=username, display_name=display_name)
        self.command = None
        self.sent: list[Sent] = []
        self.deleted_original = False
        self.followup_error = followup_error
        self.response = FakeResponse(self)
        self.followup = FakeFollowup(self)

    async def delete_original_response(self) -> None:
        self.deleted_original = True

    @property
    def reply(self) -> Sent:
        assert len(self.sent) == 1, f"expected exactly one message, got {self.sent!r}"
        return self.sent[0]
