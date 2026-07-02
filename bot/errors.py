"""Custom exceptions for the dice bot. Messages are user-facing Thai text
meant to be sent as ephemeral Discord replies."""


class BotUserError(Exception):
    """Base class for errors that should be shown to the user as an ephemeral reply."""


class CharacterNotFoundError(BotUserError):
    def __init__(self):
        super().__init__(
            "ไม่พบตัวละครของคุณในระบบ กรุณาติดต่อ GM เพื่อลงทะเบียนตัวละครก่อนใช้คำสั่งนี้"
        )


class WeaponNotFoundError(BotUserError):
    def __init__(self, weapon_input: str):
        super().__init__(
            f"ไม่พบอาวุธ \"{weapon_input}\" กรุณาเลือกอาวุธจากรายการที่ระบบแนะนำ (autocomplete)"
        )


class InvalidDiceCountError(BotUserError):
    def __init__(self, num_dice: int):
        super().__init__(
            f"จำนวนลูกเต๋าที่คำนวณได้ไม่ถูกต้อง ({num_dice}) ไม่สามารถทอยได้ กรุณาตรวจสอบค่าสเตตัส/สกิลของตัวละคร"
        )


class SkillNotFoundError(BotUserError):
    def __init__(self, skill_name: str):
        super().__init__(
            f"ไม่พบค่าสกิล \"{skill_name}\" ของตัวละครคุณในระบบ กรุณาติดต่อ GM"
        )
