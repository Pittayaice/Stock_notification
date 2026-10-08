from datetime import datetime

import pytest

from app.bot import Bot
from app.config import TZ
from app.db import make_session_factory


def closes(prev: float, last: float, days: int = 250) -> list[float]:
    return [prev] * (days - 1) + [last]


PRICES = {
    "PTT.BK": closes(34.25, 34.75),
    "CPALL.BK": closes(58.50, 58.25),
    "AAPL": closes(226.64, 231.40),
    "BH.BK": closes(150.00, 152.00),  # BH is listed on both SET and US
    "BH": closes(60.00, 61.00),
    "THB=X": closes(33.00, 33.00),
}


class FakePrices:
    def __init__(self, data: dict[str, list[float]]):
        self.data = data
        self.calls: list[list[str]] = []

    def history(self, yf_symbols: list[str]) -> dict[str, list[float]]:
        self.calls.append(list(yf_symbols))
        return {s: self.data[s] for s in yf_symbols if s in self.data}


@pytest.fixture
def prices() -> FakePrices:
    return FakePrices(dict(PRICES))


@pytest.fixture
def sessions():
    return make_session_factory("sqlite://")


@pytest.fixture
def bot(sessions, prices) -> Bot:
    return Bot(sessions, prices, now=lambda: datetime(2026, 10, 9, 17, 5, tzinfo=TZ))
