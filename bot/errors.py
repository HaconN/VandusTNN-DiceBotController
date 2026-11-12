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


class DiceAndAttributeConflictError(BotUserError):
    def __init__(self):
        super().__init__(
            "กรุณาระบุอย่างใดอย่างหนึ่งระหว่าง \"dice\" หรือ \"attribute\" ไม่สามารถใช้พร้อมกันทั้งสองอย่างได้"
        )


class InvalidDiceNotationError(BotUserError):
    def __init__(self, notation: str):
        super().__init__(
            f"รูปแบบลูกเต๋า \"{notation}\" ไม่ถูกต้อง กรุณาใช้รูปแบบ NdM เช่น 3d6, 2d8, 4d20"
        )


class InvalidDieSizeError(BotUserError):
    def __init__(self, faces: int):
        super().__init__(
            f"ขนาดลูกเต๋า d{faces} ไม่ถูกต้อง กรุณาใช้ขนาดที่รองรับเท่านั้น: d4, d6, d8, d10, d12, d20"
        )


class InvalidDiceCountRangeError(BotUserError):
    def __init__(self, count: int):
        super().__init__(
            f"จำนวนลูกเต๋า {count} ไม่ถูกต้อง กรุณาระบุจำนวนระหว่าง 1 ถึง 100"
        )
