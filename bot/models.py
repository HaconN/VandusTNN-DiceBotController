"""Plain data structures shared between the sheets layer and the command layer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from bot.errors import ColumnMissingError, StatValueError

ATTRIBUTE_NAMES = ("STR", "CON", "DEX", "INT", "WIS")

# Tab names in the character spreadsheet.
FINAL_SUM_SHEET = "Final Sum"
PLAYER_SKILL_SHEET = "Player Skill"
WEAPON_INFO_SHEET = "Weapon Info"

_WHOLE_NUMBER_WITH_ZERO_DECIMALS = re.compile(r"[+-]?\d+\.0+")


def parse_whole_number(raw: Any) -> int:
    """Strictly parses a sheet cell as a whole number.

    Accepts ints, integral floats and text such as "5", " 5 " or "5.0".
    Anything else (a blank cell, a word, a real decimal such as "3.5") raises
    ValueError; for text that is int()'s own message, so the log shows the
    exact cell content, e.g. "invalid literal for int() with base 10: '3.5'".
    """
    if isinstance(raw, bool):
        raise ValueError(f"not a whole number: {raw!r}")
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw.is_integer():
            return int(raw)
        raise ValueError(f"not a whole number: {raw!r}")
    text = "" if raw is None else str(raw).strip()
    if _WHOLE_NUMBER_WITH_ZERO_DECIMALS.fullmatch(text):
        text = text.split(".", 1)[0]
    return int(text)


def normalize_attribute(name: Any) -> str | None:
    """Returns the canonical attribute name ("str " -> "STR"), or None if the
    text is not one of ATTRIBUTE_NAMES."""
    key = str(name).strip().upper()
    return key if key in ATTRIBUTE_NAMES else None


@dataclass(frozen=True)
class Character:
    discord_username: str
    char_id: str  # e.g. "S1001", the join key into "Player Skill"
    name: str
    race: str
    # Raw cell values keyed by attribute column ({"STR": "10", ...}), parsed
    # only when used: a bad cell in one stat must not break rolls that use
    # another, and the error should name the stat that was actually rolled.
    attributes: dict[str, Any]

    def attribute_value(self, attribute: str) -> int:
        key = attribute.strip().upper()
        if key not in self.attributes:
            raise ColumnMissingError(FINAL_SUM_SHEET, key)
        raw = self.attributes[key]
        try:
            return parse_whole_number(raw)
        except ValueError as exc:
            raise StatValueError(key, raw, self.name, self.char_id) from exc


@dataclass(frozen=True)
class WeaponOption:
    """A single selectable weapon entry. Weapons whose sheet row encodes two
    usage modes (e.g. a throwable knife) become two separate WeaponOption
    instances, one per (skill, attribute) pair."""

    display_name: str  # what's shown/selected in autocomplete, e.g. "Knife (ขว้าง)"
    base_name: str  # original "Weapon Name" cell value, e.g. "Knife"
    code: str
    skill: str
    attribute: str
