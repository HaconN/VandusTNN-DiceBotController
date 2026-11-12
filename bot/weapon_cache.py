"""Short-lived in-memory copy of the parsed weapon list.

Autocomplete fires on every keystroke, and the weapon list almost never
changes, so autocomplete reads from here instead of the sheet. Character and
skill data are deliberately never cached: a GM's edit must apply at once.
"""

from __future__ import annotations

import time
from typing import Callable

from bot.models import WeaponOption

DEFAULT_TTL_SECONDS = 60.0


class WeaponCache:
    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl
        self._clock = clock
        self._weapons: list[WeaponOption] | None = None
        self._stored_at = 0.0

    def fresh(self) -> list[WeaponOption] | None:
        """The cached list if it is younger than the TTL, else None."""
        if self._weapons is not None and self._clock() - self._stored_at < self._ttl:
            return self._weapons
        return None

    def stale(self) -> list[WeaponOption] | None:
        """The last list stored, however old (a fallback while Sheets fails)."""
        return self._weapons

    def store(self, weapons: list[WeaponOption]) -> None:
        self._weapons = list(weapons)
        self._stored_at = self._clock()
