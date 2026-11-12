"""Success Point (SP) dice rolling logic. NdM, count dice landing in the pass range."""

import random

# Fraction of the die's faces that count as a pass, keeping success
# probability constant across die sizes.
PASS_RATIOS = {
    "normal": 0.5,
    "adv": 2 / 3,
    "dis": 1 / 3,
}

# Die sizes the bot supports for the "dice" notation parameter.
SUPPORTED_FACES = (4, 6, 8, 10, 12, 20)

# Display labels used in the roll output line, e.g. "rolled [Normal] 6d6: ..."
DISPLAY_LABELS = {
    "normal": "Normal",
    "adv": "ADV",
    "dis": "DIS",
}


def pass_values(faces: int, roll_type: str) -> set[int]:
    """Computes the set of face values that count as a pass for a die with
    the given number of faces.

    min_pass = faces - round(faces * ratio) + 1, where ratio is the target
    pass-probability for the roll type. Reproduces the original hardcoded
    d6 ranges exactly (Normal 4-6, ADV 3-6, DIS 5-6).
    """
    key = roll_type.strip().lower()
    if key not in PASS_RATIOS:
        raise ValueError(f"Unknown roll type: {roll_type!r}")
    ratio = PASS_RATIOS[key]
    min_pass = faces - round(faces * ratio) + 1
    return set(range(min_pass, faces + 1))


# Backward-compatible d6 pass sets.
PASS_VALUES = {key: pass_values(6, key) for key in PASS_RATIOS}


def roll_dice(num_dice: int, roll_type: str, faces: int = 6) -> tuple[list[int], int]:
    """Roll num_dice dice with the given number of faces and count successes
    for the given roll type.

    Returns (rolls, sp). Raises ValueError for an unrecognized roll_type.
    """
    key = roll_type.strip().lower()
    pass_set = pass_values(faces, key)
    rolls = [random.randint(1, faces) for _ in range(num_dice)]
    sp = sum(1 for r in rolls if r in pass_set)
    return rolls, sp


def format_roll_line(roll_type: str, num_dice: int, rolls: list[int], faces: int = 6) -> str:
    """Formats: 'rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5'"""
    key = roll_type.strip().lower()
    if key not in DISPLAY_LABELS:
        raise ValueError(f"Unknown roll type: {roll_type!r}")
    label = DISPLAY_LABELS[key]
    dice_str = ", ".join(str(r) for r in rolls)
    return f"rolled [{label}] {num_dice}d{faces}: {dice_str}"
