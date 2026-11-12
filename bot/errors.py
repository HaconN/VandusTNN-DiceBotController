"""Error types for the dice bot.

Every failure a player can run into has a short, stable code (E101, E203, ...)
so the player's Discord message and the controller's log entry can be matched
up. Each error carries:

  user_message  Thai text for the player (sent as an ephemeral reply): what
                went wrong and who should fix it. Never a stack trace, never a
                credential.
  log_message   One technical English sentence for the controller log.
  details       key=value pairs for the log (tab, column, raw cell value, ...).

Code ranges:
  E1xx  the command's own input
  E2xx  a character's data in the sheet
  E3xx  weapon setup and sheet structure (tabs, columns)
  E4xx  Google access (the number follows the matching HTTP status where one
        exists: E401 auth, E403 permission, E404 not found, E408 timeout,
        E429 rate limit)
  E9xx  the bot itself

Codes are part of the bot's interface (players quote them to the GM): never
renumber one, only add new ones.
"""

from __future__ import annotations

from typing import Any

UNEXPECTED_ERROR_CODE = "E900"
REPLY_FAILED_CODE = "E901"

UNEXPECTED_ERROR_USER_MESSAGE = (
    "เกิดข้อผิดพลาดที่ไม่คาดคิดในบอท\n"
    "กรุณาแจ้ง GM พร้อมรหัสนี้"
)

_ASK_GM_CHECK_CHARACTER_ROW = "กรุณาแจ้ง GM ให้ตรวจสอบแถวของตัวละครนี้"
_ASK_GM_CHECK_STATS = "กรุณาแจ้ง GM ให้ตรวจสอบค่าสเตตัส/สกิลของตัวละคร"
_TRY_AGAIN_OR_ASK_GM = "กรุณาลองใหม่อีกครั้ง ถ้ายังไม่ได้ให้แจ้ง GM"


class BotUserError(Exception):
    """Base class for errors reported to the player with a code.

    str(error) is the Thai user message, so existing callers that send
    str(error) keep working.
    """

    code = UNEXPECTED_ERROR_CODE

    def __init__(self, user_message: str, log_message: str, **details: Any):
        super().__init__(user_message)
        self.user_message = user_message
        self.log_message = log_message
        self.details = {key: value for key, value in details.items() if value is not None}


# ---- E1xx: the command's own input ---------------------------------------


class DiceAndAttributeConflictError(BotUserError):
    code = "E101"

    def __init__(self):
        super().__init__(
            "ใส่ได้อย่างใดอย่างหนึ่งระหว่าง \"dice\" หรือ \"attribute\" เท่านั้น\n"
            "กรุณาลองใหม่โดยใส่แค่ช่องเดียว",
            "both 'dice' and 'attribute' were given",
        )


class InvalidDiceNotationError(BotUserError):
    code = "E102"

    def __init__(self, notation: str):
        super().__init__(
            f"รูปแบบลูกเต๋า \"{notation}\" ไม่ถูกต้อง\n"
            "กรุณาใช้รูปแบบ NdM เช่น 3d6, 2d8, 4d20",
            "dice notation does not match NdM",
            notation=notation,
        )


class InvalidDieSizeError(BotUserError):
    code = "E103"

    def __init__(self, faces: int):
        super().__init__(
            f"ไม่รองรับลูกเต๋า d{faces}\n"
            "ใช้ได้เฉพาะ d4, d6, d8, d10, d12, d20",
            "unsupported die size",
            faces=faces,
        )


class InvalidDiceCountRangeError(BotUserError):
    code = "E104"

    def __init__(self, count: int, min_dice: int = 1, max_dice: int = 100):
        super().__init__(
            f"จำนวนลูกเต๋า {count} ลูกอยู่นอกช่วงที่กำหนด\n"
            f"กรุณาระบุจำนวนระหว่าง {min_dice} ถึง {max_dice} ลูก",
            "dice count in the notation is out of range",
            count=count,
            allowed=f"{min_dice}-{max_dice}",
        )


class WeaponNotFoundError(BotUserError):
    code = "E105"

    def __init__(self, weapon_input: str):
        super().__init__(
            f"ไม่พบอาวุธ \"{weapon_input}\" ในรายการอาวุธ\n"
            "กรุณาเลือกอาวุธจากรายการที่ระบบแนะนำ (autocomplete)",
            "no weapon with this display name in the parsed 'Weapon Info' list",
            weapon=weapon_input,
        )


# ---- E2xx: a character's data --------------------------------------------


class CharacterNotFoundError(BotUserError):
    code = "E201"

    def __init__(self, discord_username: str):
        super().__init__(
            f"ไม่พบตัวละครที่ผูกกับ username \"{discord_username}\" ในแท็บ \"Final Sum\"\n"
            "กรุณาแจ้ง GM เพื่อลงทะเบียนตัวละครก่อนใช้คำสั่งนี้",
            "no row in 'Final Sum' whose 'Discord ID' matches the username",
            username=discord_username,
        )


class CharacterSkillRowNotFoundError(BotUserError):
    code = "E202"

    def __init__(self, char_id: str, char_name: str):
        super().__init__(
            f"ไม่พบแถวของตัวละคร {char_name} (ID {char_id}) ในแท็บ \"Player Skill\"\n"
            "กรุณาแจ้ง GM ให้เพิ่มแถวของตัวละครนี้",
            "no row in 'Player Skill' with this character ID",
            tab="Player Skill",
            id=char_id,
        )


class StatValueError(BotUserError):
    code = "E203"

    def __init__(self, attribute: str, raw: Any, char_name: str, char_id: str):
        if raw is None or str(raw).strip() == "":
            problem = f"ช่องสเตตัส {attribute} ของตัวละคร {char_name} ในชีตว่างอยู่"
        else:
            problem = f"ค่าสเตตัส {attribute} ของตัวละคร {char_name} ในชีตไม่ใช่จำนวนเต็ม"
        super().__init__(
            f"{problem}\n{_ASK_GM_CHECK_CHARACTER_ROW}",
            "stat cell is not a whole number",
            tab="Final Sum",
            column=attribute,
            raw=raw,
        )


class SkillValueError(BotUserError):
    code = "E204"

    def __init__(self, skill_name: str, raw: Any, char_name: str, char_id: str):
        super().__init__(
            f"ค่าสกิล {skill_name} ของตัวละคร {char_name} ในชีตไม่ใช่จำนวนเต็ม\n"
            f"{_ASK_GM_CHECK_CHARACTER_ROW}ในแท็บ \"Player Skill\"",
            "skill cell is not a whole number (a blank cell counts as 0)",
            tab="Player Skill",
            column=skill_name,
            raw=raw,
        )


class InvalidDiceCountError(BotUserError):
    code = "E205"

    def __init__(self, num_dice: int):
        super().__init__(
            f"จำนวนลูกเต๋าที่คำนวณได้คือ {num_dice} ซึ่งทอยไม่ได้\n{_ASK_GM_CHECK_STATS}",
            "computed dice count is zero or negative",
            dice=num_dice,
        )


class TooManyDiceError(BotUserError):
    code = "E206"

    def __init__(self, num_dice: int, max_dice: int):
        super().__init__(
            f"จำนวนลูกเต๋าที่คำนวณได้คือ {num_dice} ลูก เกินขีดจำกัด {max_dice} ลูก\n"
            f"{_ASK_GM_CHECK_STATS}",
            "computed dice count is above the limit",
            dice=num_dice,
            max=max_dice,
        )


# ---- E3xx: weapon setup and sheet structure --------------------------------


class SkillNotFoundError(BotUserError):
    code = "E301"

    def __init__(self, skill_name: str, weapon_name: str = ""):
        weapon_part = f"อาวุธ \"{weapon_name}\" ใช้สกิล" if weapon_name else "สกิล"
        super().__init__(
            f"{weapon_part} \"{skill_name}\" แต่ไม่มีคอลัมน์ชื่อนี้ในแท็บ \"Player Skill\"\n"
            "กรุณาแจ้ง GM ให้ตรวจสอบชื่อสกิลของอาวุธนี้ในแท็บ \"Weapon Info\"",
            "the weapon's skill is not a column in 'Player Skill'",
            tab="Player Skill",
            column=skill_name,
        )


class InvalidWeaponAttributeError(BotUserError):
    code = "E302"

    def __init__(self, weapon_name: str, attribute: str):
        super().__init__(
            f"อาวุธ \"{weapon_name}\" ตั้ง Attribute เป็น \"{attribute}\" "
            "ซึ่งไม่ใช่ STR/CON/DEX/INT/WIS\n"
            "กรุณาแจ้ง GM ให้แก้ช่อง Attribute ในแท็บ \"Weapon Info\"",
            "the weapon's Attribute is not one of STR/CON/DEX/INT/WIS",
            tab="Weapon Info",
            raw=attribute,
        )


class WorksheetMissingError(BotUserError):
    code = "E303"

    def __init__(self, tab: str, available: list[str] | None = None):
        super().__init__(
            f"ไม่พบแท็บ \"{tab}\" ในชีต\n"
            "กรุณาแจ้ง GM ให้ตรวจสอบว่าแท็บนี้ไม่ได้ถูกลบหรือเปลี่ยนชื่อ",
            "a required tab is missing from the spreadsheet",
            tab=tab,
            available=", ".join(available) if available is not None else None,
        )


class ColumnMissingError(BotUserError):
    code = "E304"

    def __init__(self, tab: str, column: str):
        super().__init__(
            f"ไม่พบคอลัมน์ \"{column}\" ในแท็บ \"{tab}\"\n"
            "กรุณาแจ้ง GM ให้ตรวจสอบหัวตาราง (แถวแรก) ของแท็บนี้",
            "a required column is missing from the tab's header row",
            tab=tab,
            column=column,
        )


# ---- E4xx: Google access --------------------------------------------------
# Only the service account file's *path* and its client_email ever go into
# details: never the key, never a token.


class GoogleAuthError(BotUserError):
    code = "E401"

    def __init__(self, json_path: str, client_email: str | None = None, reason: str = ""):
        super().__init__(
            "บอทเข้าสู่ระบบ Google ไม่สำเร็จ\n"
            "กรุณาแจ้ง GM ให้ตรวจสอบไฟล์ Service Account JSON ในโปรแกรม Controller",
            f"could not authenticate with the service account ({reason})"
            if reason
            else "could not authenticate with the service account",
            json_path=json_path,
            client_email=client_email,
        )


class SheetPermissionError(BotUserError):
    code = "E403"

    def __init__(self, client_email: str | None = None):
        super().__init__(
            "บอทไม่มีสิทธิ์เปิดชีตตัวละคร\n"
            "กรุณาแจ้ง GM ให้แชร์ชีตให้อีเมล service account ของบอท",
            "Google returned 403: the sheet is not shared with the service account",
            client_email=client_email,
        )


class SpreadsheetNotFoundError(BotUserError):
    code = "E404"

    def __init__(self, sheet_ref: str, client_email: str | None = None):
        super().__init__(
            "ไม่พบชีตตัวละครตามชื่อหรือ key ที่ตั้งไว้\n"
            "กรุณาแจ้ง GM ให้ตรวจสอบช่อง Google Sheet Name/Key "
            "และการแชร์ชีตให้ service account",
            "spreadsheet not found by name, key or URL "
            "(a sheet that is not shared with the service account is not found by name either)",
            sheet=sheet_ref,
            client_email=client_email,
        )


class SheetsTimeoutError(BotUserError):
    code = "E408"

    def __init__(self, seconds: float):
        super().__init__(
            "Google Sheets ตอบช้าเกินไป\n"
            "กรุณาลองใหม่อีกครั้งในอีกสักครู่",
            f"no answer from Google Sheets within {seconds:g} s",
        )


class SheetsRateLimitError(BotUserError):
    code = "E429"

    def __init__(self):
        super().__init__(
            "มีการเรียกใช้ Google Sheets ถี่เกินไป\n"
            "กรุณารอประมาณ 1 นาทีแล้วลองใหม่",
            "Google returned 429: the Sheets read quota is used up for now",
        )


class GoogleConnectionError(BotUserError):
    code = "E450"

    def __init__(self):
        super().__init__(
            f"บอทเชื่อมต่อ Google ไม่ได้\n{_TRY_AGAIN_OR_ASK_GM}",
            "could not reach Google (network error)",
        )


class SheetsApiError(BotUserError):
    code = "E499"

    def __init__(self, status: int | None):
        super().__init__(
            f"Google Sheets ตอบกลับด้วยข้อผิดพลาด\n{_TRY_AGAIN_OR_ASK_GM}",
            f"Google Sheets API error (HTTP {status})",
            status=status,
        )
