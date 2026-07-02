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
