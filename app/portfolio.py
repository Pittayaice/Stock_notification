"""Profit/loss math. Pure functions only, no database or network."""

from dataclasses import dataclass

from app.markets import Market


def merge_buy(qty: float, avg_price: float, buy_qty: float, buy_price: float) -> tuple[float, float]:
    """New (qty, weighted average cost) after buying more of a holding."""
    new_qty = qty + buy_qty
    return new_qty, (qty * avg_price + buy_qty * buy_price) / new_qty


def apply_sell(avg_price: float, sell_qty: float, sell_price: float) -> float:
    """Realized P/L of a sell. Selling never changes the average cost of what is left."""
    return (sell_price - avg_price) * sell_qty


def pct(part: float, whole: float) -> float:
    return part / whole * 100 if whole else 0.0


@dataclass(frozen=True)
class Position:
    symbol: str
    market: Market
    qty: float
    avg_price: float
    price: float
    prev_close: float | None

    @property
    def cost(self) -> float:
        return self.qty * self.avg_price

    @property
    def value(self) -> float:
        return self.qty * self.price

    @property
    def pnl(self) -> float:
        return self.value - self.cost

    @property
    def pnl_pct(self) -> float:
        return pct(self.pnl, self.cost)

    @property
    def day_change(self) -> float:
        """Money gained or lost today: (close − previous close) × qty."""
        if self.prev_close is None:
            return 0.0
        return (self.price - self.prev_close) * self.qty

    @property
    def day_change_pct(self) -> float | None:
        if self.prev_close is None:
            return None
        return pct(self.price - self.prev_close, self.prev_close)


@dataclass(frozen=True)
class Summary:
    """Portfolio totals in THB."""

    cost: float
    value: float
    day_change: float

    @property
    def pnl(self) -> float:
        return self.value - self.cost

    @property
    def pnl_pct(self) -> float:
        return pct(self.pnl, self.cost)

    @property
    def day_change_pct(self) -> float:
        return pct(self.day_change, self.value - self.day_change)


def summarize(positions: list[Position], usd_thb: float) -> Summary:
    """Totals in THB. US positions are converted at today's USD/THB rate."""

    def rate(p: Position) -> float:
        return usd_thb if p.market is Market.US else 1.0

    return Summary(
        cost=sum(p.cost * rate(p) for p in positions),
        value=sum(p.value * rate(p) for p in positions),
        day_change=sum(p.day_change * rate(p) for p in positions),
    )
