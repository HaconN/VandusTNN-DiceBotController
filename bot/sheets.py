"""Google Sheets access layer.

Sheet *data* is fetched fresh on every command (no caching) so GM edits show
up immediately. The gspread client and spreadsheet handle are cached, since
authorising and opening are comparatively slow.

Every SheetsClient method blocks (gspread is synchronous); the command layer
runs them in a worker thread with a timeout. Every gspread, google-auth and
network exception is translated into a coded BotUserError (bot/errors.py) on
the way out, so callers only ever see those.
"""

from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import zip_longest
from typing import Any, Iterator, Sequence

import google.auth.exceptions
import gspread
import requests
from google.oauth2.service_account import Credentials

from bot.errors import (
    BotUserError,
    CharacterNotFoundError,
    CharacterSkillRowNotFoundError,
    ColumnMissingError,
    GoogleAuthError,
    GoogleConnectionError,
    SheetPermissionError,
    SheetsApiError,
    SheetsRateLimitError,
    SheetsTimeoutError,
    SkillNotFoundError,
    SkillValueError,
    SpreadsheetNotFoundError,
    WorksheetMissingError,
)
from bot.models import (
    ATTRIBUTE_NAMES,
    FINAL_SUM_SHEET,
    PLAYER_SKILL_SHEET,
    WEAPON_INFO_SHEET,
    Character,
    WeaponOption,
    parse_whole_number,
)

__all__ = [
    "FINAL_SUM_SHEET",
    "PLAYER_SKILL_SHEET",
    "WEAPON_INFO_SHEET",
    "AttackData",
    "SheetTable",
    "SheetsClient",
    "find_character",
    "lookup_skill_value",
    "parse_weapons",
    "require_skill_column",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Per HTTP request to Google. The command layer adds an overall timeout on
# top; this one makes sure a hung request also frees its worker thread.
HTTP_TIMEOUT_SECONDS = 10.0

# Columns each tab must have. Stat columns (STR, ...) and skill columns are
# checked when a command actually needs them.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    FINAL_SUM_SHEET: ("Discord ID", "ID", "Name"),
    PLAYER_SKILL_SHEET: ("ID",),
    WEAPON_INFO_SHEET: ("Weapon Name", "Skill", "Attribute"),
}

# Columns in "Player Skill" that are never skill columns.
PLAYER_SKILL_NON_SKILL_COLUMNS = {"ID", "Name"}


@dataclass(frozen=True)
class SheetTable:
    """One tab: its header row and its data rows as {header: cell value}."""

    tab: str
    headers: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]

    @classmethod
    def from_values(cls, tab: str, values: Sequence[Sequence[Any]]) -> "SheetTable":
        """Builds a table from the API's 2-D values (first row = headers).

        Header text is trimmed, blank header cells are ignored, and for a
        repeated header the first column wins. Short rows (the API drops
        trailing blank cells) are padded with "". Raises ColumnMissingError
        if a column in REQUIRED_COLUMNS is missing.
        """
        headers = tuple(str(cell).strip() for cell in values[0]) if values else ()
        for column in REQUIRED_COLUMNS.get(tab, ()):
            if column not in headers:
                raise ColumnMissingError(tab, column)
        rows = []
        for raw_row in values[1:]:
            row: dict[str, Any] = {}
            for header, cell in zip_longest(headers, raw_row, fillvalue=""):
                if header and header not in row:
                    row[header] = cell
            rows.append(row)
        return cls(tab, headers, tuple(rows))


@dataclass(frozen=True)
class AttackData:
    """Everything /attack needs, read in a single request."""

    final_sum: SheetTable
    player_skill: SheetTable
    weapons: list[WeaponOption]


# ---- parsing (pure functions, no network) ----------------------------------


def find_character(table: SheetTable, discord_username: str) -> Character | None:
    """The 'Final Sum' row whose 'Discord ID' matches the username,
    ignoring case and surrounding spaces."""
    target = str(discord_username).strip().casefold()
    if not target:
        return None
    for row in table.rows:
        if str(row.get("Discord ID", "")).strip().casefold() == target:
            return Character(
                discord_username=str(row.get("Discord ID", "")).strip(),
                char_id=str(row.get("ID", "")).strip(),
                name=str(row.get("Name", "")).strip(),
                race=str(row.get("Race", "")).strip(),
                attributes={attr: row[attr] for attr in ATTRIBUTE_NAMES if attr in row},
            )
    return None


def require_skill_column(table: SheetTable, skill_name: str, weapon_name: str = "") -> None:
    if skill_name not in table.headers:
        raise SkillNotFoundError(skill_name, weapon_name)


def lookup_skill_value(table: SheetTable, character: Character, skill_name: str) -> int:
    """The character's value in a 'Player Skill' column. A blank cell means
    the character never trained the skill and counts as 0; any other
    non-whole-number content is an error."""
    require_skill_column(table, skill_name)
    for row in table.rows:
        if str(row.get("ID", "")).strip() == character.char_id:
            raw = row.get(skill_name, "")
            if raw is None or str(raw).strip() == "":
                return 0
            try:
                return parse_whole_number(raw)
            except ValueError as exc:
                raise SkillValueError(skill_name, raw, character.name, character.char_id) from exc
    raise CharacterSkillRowNotFoundError(character.char_id, character.name)


def parse_weapons(table: SheetTable) -> list[WeaponOption]:
    weapons: list[WeaponOption] = []
    for row in table.rows:
        code = str(row.get("Code", "")).strip()
        name = str(row.get("Weapon Name", "")).strip()
        skills = [s.strip() for s in str(row.get("Skill", "")).split("\n") if s.strip()]
        attrs = [a.strip() for a in str(row.get("Attribute", "")).split("\n") if a.strip()]

        if not skills or not name:
            continue

        if len(skills) == 1:
            weapons.append(
                WeaponOption(
                    display_name=name,
                    base_name=name,
                    code=code,
                    skill=skills[0],
                    attribute=attrs[0] if attrs else "",
                )
            )
            continue

        # Multi-mode weapon: pair skills with attributes positionally.
        # A shorter attrs list (e.g. one shared attribute for both modes)
        # repeats its last value instead of truncating the pairing.
        fill = attrs[-1] if attrs else ""
        for skill, attribute in zip_longest(skills, attrs, fillvalue=fill):
            if "thrown" in skill.lower():
                display_name = f"{name} (ขว้าง)"
            else:
                display_name = name
            weapons.append(
                WeaponOption(
                    display_name=display_name,
                    base_name=name,
                    code=code,
                    skill=skill,
                    attribute=attribute,
                )
            )
    return weapons


# ---- the client ------------------------------------------------------------


class SheetsClient:
    def __init__(
        self,
        service_account_json_path: str,
        sheet_name_or_key: str,
        *,
        http_timeout: float = HTTP_TIMEOUT_SECONDS,
    ):
        self._json_path = service_account_json_path
        self._sheet_ref = sheet_name_or_key
        self._http_timeout = http_timeout
        self._lock = threading.Lock()
        self._gc: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None
        self._client_email: str | None = None
        self._client_email_read = False

    @property
    def json_path(self) -> str:
        return self._json_path

    def service_account_email(self) -> str | None:
        """The service account file's client_email, or None if unreadable.
        This is the only field ever read out of the file for display."""
        if not self._client_email_read:
            self._client_email_read = True
            try:
                with open(self._json_path, encoding="utf-8") as f:
                    data = json.load(f)
                email = data.get("client_email") if isinstance(data, dict) else None
                self._client_email = email if isinstance(email, str) else None
            except (OSError, ValueError):
                self._client_email = None
        return self._client_email

    # ---- reads: one HTTP request each (after the first open) -------------

    def load_character(self, discord_username: str) -> Character:
        table = self.fetch_tables([FINAL_SUM_SHEET])[FINAL_SUM_SHEET]
        character = find_character(table, discord_username)
        if character is None:
            raise CharacterNotFoundError(discord_username)
        return character

    def fetch_weapons(self) -> list[WeaponOption]:
        return parse_weapons(self.fetch_tables([WEAPON_INFO_SHEET])[WEAPON_INFO_SHEET])

    def load_attack_data(self) -> AttackData:
        tables = self.fetch_tables([FINAL_SUM_SHEET, PLAYER_SKILL_SHEET, WEAPON_INFO_SHEET])
        return AttackData(
            final_sum=tables[FINAL_SUM_SHEET],
            player_skill=tables[PLAYER_SKILL_SHEET],
            weapons=parse_weapons(tables[WEAPON_INFO_SHEET]),
        )

    def fetch_tables(self, tabs: Sequence[str]) -> dict[str, SheetTable]:
        """The given tabs, read together in one values:batchGet request."""
        with self._translate_errors():
            values = self._fetch_values(list(tabs))
        return {tab: SheetTable.from_values(tab, values.get(tab, [])) for tab in tabs}

    # ---- internals ---------------------------------------------------------

    def _fetch_values(self, tabs: list[str]) -> dict[str, list[list[Any]]]:
        spreadsheet = self._spreadsheet_handle()
        ranges = [_whole_tab_range(tab) for tab in tabs]
        try:
            response = spreadsheet.values_batch_get(ranges)
        except gspread.exceptions.APIError as exc:
            # A missing (or renamed) tab makes the whole batch fail with 400
            # "Unable to parse range"; name the tab instead of reporting a
            # generic API error.
            if _http_status(exc) == 400 and "Unable to parse range" in str(exc):
                titles = self._worksheet_titles(spreadsheet)
                missing = [tab for tab in tabs if tab not in titles]
                if missing:
                    raise WorksheetMissingError(missing[0], available=titles) from exc
            raise
        value_ranges = response.get("valueRanges", [])
        return {tab: value_range.get("values", []) for tab, value_range in zip(tabs, value_ranges)}

    def _worksheet_titles(self, spreadsheet: gspread.Spreadsheet) -> list[str]:
        return [worksheet.title for worksheet in spreadsheet.worksheets()]

    def _spreadsheet_handle(self) -> gspread.Spreadsheet:
        # Locked: commands run in parallel worker threads, and only one of
        # them should authorise and open the spreadsheet.
        with self._lock:
            if self._spreadsheet is None:
                self._spreadsheet = self._open_spreadsheet(self._client())
            return self._spreadsheet

    def _client(self) -> gspread.Client:
        if self._gc is None:
            try:
                creds = Credentials.from_service_account_file(self._json_path, scopes=SCOPES)
            except FileNotFoundError as exc:
                raise GoogleAuthError(self._json_path, None, "file not found") from exc
            except (OSError, ValueError, KeyError) as exc:
                # Malformed JSON, missing fields or an unparsable key. The
                # exception text never contains the key itself.
                raise GoogleAuthError(
                    self._json_path,
                    self.service_account_email(),
                    "the file is not a valid service account key",
                ) from exc
            gc = gspread.authorize(creds)
            gc.set_timeout(self._http_timeout)
            self._gc = gc
        return self._gc

    def _open_spreadsheet(self, gc: gspread.Client) -> gspread.Spreadsheet:
        ref = self._sheet_ref.strip()
        if ref.startswith(("http://", "https://")):
            return gc.open_by_url(ref)
        # Accept either a full name or a sheet key.
        try:
            return gc.open(ref)
        except gspread.SpreadsheetNotFound:
            pass
        try:
            return gc.open_by_key(ref)
        except gspread.exceptions.APIError as exc:
            if _http_status(exc) == 400:  # a name with spaces is not a valid key
                raise SpreadsheetNotFoundError(self._sheet_ref, self.service_account_email()) from exc
            raise

    @contextmanager
    def _translate_errors(self) -> Iterator[None]:
        try:
            yield
        except BotUserError:
            raise
        except google.auth.exceptions.RefreshError as exc:
            raise GoogleAuthError(
                self._json_path, self.service_account_email(), "Google rejected the service account key"
            ) from exc
        except google.auth.exceptions.TransportError as exc:
            raise GoogleConnectionError() from exc
        except (gspread.SpreadsheetNotFound, gspread.exceptions.NoValidUrlKeyFound) as exc:
            raise SpreadsheetNotFoundError(self._sheet_ref, self.service_account_email()) from exc
        except gspread.WorksheetNotFound as exc:
            raise WorksheetMissingError(str(exc)) from exc
        except gspread.exceptions.APIError as exc:
            raise self._api_error(exc) from exc
        except PermissionError as exc:
            # gspread's open_by_key turns HTTP 403 into the builtin PermissionError.
            raise SheetPermissionError(self.service_account_email()) from exc
        except requests.exceptions.ConnectionError as exc:
            # Before Timeout: ConnectTimeout is both, and "cannot connect" is
            # a network problem rather than a slow Google.
            raise GoogleConnectionError() from exc
        except requests.exceptions.Timeout as exc:
            raise SheetsTimeoutError(self._http_timeout) from exc
        except requests.exceptions.RequestException as exc:
            raise GoogleConnectionError() from exc

    def _api_error(self, exc: gspread.exceptions.APIError) -> BotUserError:
        status = _http_status(exc)
        email = self.service_account_email()
        if status == 401:
            return GoogleAuthError(self._json_path, email, "Google returned 401")
        if status == 403:
            return SheetPermissionError(email)
        if status == 404:
            return SpreadsheetNotFoundError(self._sheet_ref, email)
        if status == 429:
            return SheetsRateLimitError()
        if status in (408, 504):
            return SheetsTimeoutError(self._http_timeout)
        return SheetsApiError(status)


def _whole_tab_range(tab: str) -> str:
    """A1 range for a whole tab; quoted because tab names contain spaces."""
    return "'" + tab.replace("'", "''") + "'"


def _http_status(exc: gspread.exceptions.APIError) -> int | None:
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int):
        return status
    code = getattr(exc, "code", None)
    return code if isinstance(code, int) and code > 0 else None
