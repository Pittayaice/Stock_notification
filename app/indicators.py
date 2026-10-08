def sma(closes: list[float], period: int) -> float | None:
    """Simple moving average of the last `period` closes, or None if there is not enough data."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def crossed(closes: list[float], period: int) -> int:
    """+1 if the last close crossed above its SMA, -1 if it crossed below, 0 otherwise."""
    if len(closes) < period + 1:
        return 0
    was_above = closes[-2] > sma(closes[:-1], period)
    is_above = closes[-1] > sma(closes, period)
    if is_above and not was_above:
        return 1
    if was_above and not is_above:
        return -1
    return 0
