import pytest

from app.markets import Market
from app.portfolio import Position, apply_sell, merge_buy, summarize

PTT = Position("PTT", Market.SET, 100, 33.90, 34.75, 34.25)
CPALL = Position("CPALL", Market.SET, 200, 59.10, 58.25, 58.50)
AAPL = Position("AAPL", Market.US, 10, 205.00, 231.40, 226.64)


def test_merge_buy_re_averages_cost():
    qty, avg = merge_buy(100, 33.90, 50, 35.00)
    assert qty == 150
    assert avg == pytest.approx(34.266667, abs=1e-6)


def test_sell_profit_uses_average_cost():
    assert apply_sell(34.266667, 50, 36.00) == pytest.approx(86.67, abs=0.01)


def test_sell_at_a_loss_is_negative():
    assert apply_sell(59.10, 100, 58.00) == pytest.approx(-110.00)


@pytest.mark.parametrize(
    ("position", "pnl", "pnl_pct"),
    [(PTT, 85.00, 2.51), (CPALL, -170.00, -1.44), (AAPL, 264.00, 12.88)],
)
def test_position_profit_and_percent(position, pnl, pnl_pct):
    assert position.pnl == pytest.approx(pnl)
    assert position.pnl_pct == pytest.approx(pnl_pct, abs=0.005)


def test_day_change():
    assert PTT.day_change == pytest.approx(50.00)
    assert PTT.day_change_pct == pytest.approx(1.46, abs=0.005)
    assert Position("X", Market.SET, 1, 1, 1, None).day_change == 0


def test_summary_converts_us_to_thb():
    s = summarize([PTT, CPALL, AAPL], usd_thb=33.00)
    assert s.cost == pytest.approx(82_860.00)
    assert s.value == pytest.approx(91_487.00)
    assert s.pnl == pytest.approx(8_627.00)
    assert s.pnl_pct == pytest.approx(10.41, abs=0.005)
    assert s.day_change == pytest.approx(50 - 50 + 4.76 * 10 * 33)
