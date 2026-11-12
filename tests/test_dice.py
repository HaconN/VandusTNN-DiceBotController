import pytest

from bot import dice


def test_pass_ranges():
    assert dice.PASS_VALUES["normal"] == {4, 5, 6}
    assert dice.PASS_VALUES["adv"] == {3, 4, 5, 6}
    assert dice.PASS_VALUES["dis"] == {5, 6}


def test_roll_dice_length_and_sp(monkeypatch):
    sequence = iter([3, 4, 4, 1, 6, 5])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    rolls, sp = dice.roll_dice(6, "normal")

    assert rolls == [3, 4, 4, 1, 6, 5]
    assert sp == 4  # 4, 4, 6, 5 pass


def test_roll_dice_adv(monkeypatch):
    sequence = iter([3, 4, 4, 1, 6, 5])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    rolls, sp = dice.roll_dice(6, "ADV")

    assert sp == 5  # everything except the 1


def test_roll_dice_dis(monkeypatch):
    sequence = iter([3, 4, 4, 1, 6, 5])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    rolls, sp = dice.roll_dice(6, "dis")

    assert sp == 2  # 6 and 5 only


def test_roll_dice_invalid_type():
    with pytest.raises(ValueError):
        dice.roll_dice(6, "bogus")


def test_format_roll_line():
    line = dice.format_roll_line("normal", 6, [3, 4, 4, 1, 6, 5])
    assert line == "rolled [Normal] 6d6: 3, 4, 4, 1, 6, 5"


def test_format_roll_line_labels():
    assert dice.format_roll_line("adv", 1, [3]).startswith("rolled [ADV]")
    assert dice.format_roll_line("dis", 1, [3]).startswith("rolled [DIS]")


def test_format_roll_line_shows_die_size():
    line = dice.format_roll_line("adv", 2, [5, 3], faces=8)
    assert line == "rolled [ADV] 2d8: 5, 3"


# faces -> roll_type -> expected pass values (min, max inclusive range)
EXPECTED_PASS_RANGES = {
    4: {"normal": (3, 4), "adv": (2, 4), "dis": (4, 4)},
    6: {"normal": (4, 6), "adv": (3, 6), "dis": (5, 6)},
    8: {"normal": (5, 8), "adv": (4, 8), "dis": (6, 8)},
    10: {"normal": (6, 10), "adv": (4, 10), "dis": (8, 10)},
    12: {"normal": (7, 12), "adv": (5, 12), "dis": (9, 12)},
    20: {"normal": (11, 20), "adv": (8, 20), "dis": (14, 20)},
}


@pytest.mark.parametrize("faces", dice.SUPPORTED_FACES)
@pytest.mark.parametrize("roll_type", ["normal", "adv", "dis"])
def test_pass_values_thresholds(faces, roll_type):
    low, high = EXPECTED_PASS_RANGES[faces][roll_type]
    assert dice.pass_values(faces, roll_type) == set(range(low, high + 1))


def test_pass_values_d6_matches_original_hardcoded_ranges():
    assert dice.pass_values(6, "normal") == {4, 5, 6}
    assert dice.pass_values(6, "adv") == {3, 4, 5, 6}
    assert dice.pass_values(6, "dis") == {5, 6}


def test_roll_dice_with_custom_faces(monkeypatch):
    sequence = iter([5, 3])
    monkeypatch.setattr(dice.random, "randint", lambda a, b: next(sequence))

    rolls, sp = dice.roll_dice(2, "adv", faces=8)

    assert rolls == [5, 3]
    assert sp == 1  # only 5 passes ADV on d8 (4-8)
