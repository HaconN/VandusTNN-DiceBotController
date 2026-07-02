"""Plain data structures shared between the sheets layer and the command layer."""

from dataclasses import dataclass

ATTRIBUTE_NAMES = ("STR", "CON", "DEX", "INT", "WIS")


@dataclass(frozen=True)
class Character:
    discord_id: str
    char_id: str  # e.g. "S1001", the join key into "Player Skill"
    name: str
    race: str
    attributes: dict[str, int]  # {"STR": 10, "CON": 8, ...}

    def attribute_value(self, attribute: str) -> int:
        return self.attributes[attribute.strip().upper()]


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
