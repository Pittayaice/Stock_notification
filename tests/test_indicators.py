from app.indicators import crossed, sma


def test_sma():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([1], 2) is None


def test_crossed_up():
    assert crossed([10, 10, 10, 9, 12], 3) == 1


def test_crossed_down():
    assert crossed([10, 10, 10, 11, 8], 3) == -1


def test_stays_above_is_not_a_cross():
    assert crossed([10, 10, 10, 11, 12], 3) == 0


def test_not_enough_data():
    assert crossed([1, 2, 3], 3) == 0
