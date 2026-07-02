"""Google Sheets access layer.

Wraps gspread. Worksheet *data* is re-fetched on every call (no caching / TTL)
so GM edits show up immediately, per spec. The gspread client + spreadsheet
handle themselves are cached lazily since opening/authorizing is comparatively
expensive and doesn't need to happen on every single lookup.
"""

from __future__ import annotations

from google.oauth2.service_account import Credentials
import gspread

from bot.models import ATTRIBUTE_NAMES, Character, WeaponOption

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

FINAL_SUM_SHEET = "Final Sum"
PLAYER_SKILL_SHEET = "Player Skill"
WEAPON_INFO_SHEET = "Weapon Info"

# Columns in "Player Skill" that are never skill columns.
PLAYER_SKILL_NON_SKILL_COLUMNS = {"ID", "Name"}


class SheetsClient:
    def __init__(self, service_account_json_path: str, sheet_name_or_key: str):
        self._json_path = service_account_json_path
        self._sheet_ref = sheet_name_or_key
        self._gc: gspread.Client | None = None
        self._spreadsheet: gspread.Spreadsheet | None = None

    def _client(self) -> gspread.Client:
        if self._gc is None:
            creds = Credentials.from_service_account_file(self._json_path, scopes=SCOPES)
            self._gc = gspread.authorize(creds)
        return self._gc

    def _spreadsheet_handle(self) -> gspread.Spreadsheet:
        if self._spreadsheet is None:
            gc = self._client()
            # Accept either a full name or a sheet key/URL.
            try:
                self._spreadsheet = gc.open(self._sheet_ref)
            except gspread.SpreadsheetNotFound:
                self._spreadsheet = gc.open_by_key(self._sheet_ref)
        return self._spreadsheet

    def _worksheet_records(self, worksheet_name: str) -> list[dict]:
        ws = self._spreadsheet_handle().worksheet(worksheet_name)
        return ws.get_all_records()

    # ---- Final Sum -------------------------------------------------

    def find_character_by_discord_id(self, discord_id: str) -> Character | None:
        records = self._worksheet_records(FINAL_SUM_SHEET)
        for row in records:
            if str(row.get("Discord ID", "")).strip() == str(discord_id).strip():
                attributes = {attr: int(row.get(attr, 0) or 0) for attr in ATTRIBUTE_NAMES}
                return Character(
                    discord_id=str(row.get("Discord ID", "")).strip(),
                    char_id=str(row.get("ID", "")).strip(),
                    name=str(row.get("Name", "")).strip(),
                    race=str(row.get("Race", "")).strip(),
                    attributes=attributes,
                )
        return None

    # ---- Player Skill ------------------------------------------------

    def find_skill_value(self, char_id: str, skill_name: str) -> int | None:
        records = self._worksheet_records(PLAYER_SKILL_SHEET)
        for row in records:
            if str(row.get("ID", "")).strip() == str(char_id).strip():
                if skill_name not in row:
                    return None
                value = row.get(skill_name, 0)
                if value in ("", None):
                    return 0
                return int(value)
        return None

    # ---- Weapon Info ------------------------------------------------

    def fetch_weapons(self) -> list[WeaponOption]:
        records = self._worksheet_records(WEAPON_INFO_SHEET)
        weapons: list[WeaponOption] = []
        for row in records:
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
            for skill, attribute in zip(skills, attrs):
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
