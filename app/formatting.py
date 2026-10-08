def qty(q: float) -> str:
    """1000 → '1,000', 0.5 → '0.5'."""
    return f"{q:,.4f}".rstrip("0").rstrip(".")


def price(p: float, currency: str) -> str:
    """Up to 4 decimals, at least 2: 33.9 → '฿33.90', 34.266667 → '฿34.2667'."""
    whole, _, decimals = f"{p:,.4f}".partition(".")
    decimals = decimals.rstrip("0").ljust(2, "0")
    return f"{currency}{whole}.{decimals}"


def money(amount: float, currency: str) -> str:
    return f"{currency}{amount:,.2f}"


def signed_money(amount: float, currency: str) -> str:
    sign = "-" if round(amount, 2) < 0 else "+"
    return f"{sign}{currency}{abs(amount):,.2f}"


def signed_pct(p: float) -> str:
    return f"{p:+.2f}%".replace("-0.00%", "+0.00%")


def dot(amount: float) -> str:
    """🟢 profit, 🔴 loss, ⚪ flat."""
    rounded = round(amount, 2)
    return "🟢" if rounded > 0 else "🔴" if rounded < 0 else "⚪"


def arrow(change: float) -> str:
    rounded = round(change, 4)
    return "▲" if rounded > 0 else "▼" if rounded < 0 else "•"

