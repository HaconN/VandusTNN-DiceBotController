"""Success Point (SP) dice rolling logic. Nd6, count dice landing in the pass range."""

import random

PASS_VALUES = {
    "normal": {4, 5, 6},
    "adv": {3, 4, 5, 6},
    "dis": {5, 6},
}

# Display labels used in the roll output line, e.g. "rolled [Normal] 6d6: ..."
DISPLAY_LABELS = {
    "normal": "Normal",
    "adv": "ADV",
    "dis": "DIS",
}


def roll_dice(num_dice: int, roll_type: str) -> tuple[list[int], int]:
    """Roll num_dice d6 and count successes for the given roll type.

    Returns (rolls, sp). Raises ValueError for an unrecognized roll_type.
    """
    key = roll_type.strip().lower()
    if key not in PASS_VALUES:
        raise ValueError(f"Unknown roll type: {roll_type!r}")
    pass_set = PASS_VALUES[key]
    rolls = [random.randint(1, 6) for _ in range(num_dice)]
    sp = sum(1 for r in rolls if r in pass_set)
    return rolls, sp


def format_roll_line(roll_type: str, num_dice: int, rolls: list[int]) -> str:
    """Formats: 'rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5'"""
    key = roll_type.strip().lower()
    if key not in DISPLAY_LABELS:
        raise ValueError(f"Unknown roll type: {roll_type!r}")
    label = DISPLAY_LABELS[key]
    dice_str = ", ".join(str(r) for r in rolls)
    return f"rolled [{label}] {num_dice}d6: {dice_str}"
