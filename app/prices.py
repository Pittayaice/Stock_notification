import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

import yfinance as yf

log = logging.getLogger(__name__)


class PriceProvider(Protocol):
    def history(self, yf_symbols: list[str]) -> dict[str, list[float]]:
        """Daily closes (oldest first) for each symbol that has data. Unknown symbols are left out."""
        ...


class YFinanceProvider:
    """Prices from Yahoo Finance (free, no key, ~15 min delayed).

    Each symbol is fetched once and cached for `ttl_seconds`, so many users holding
    the same stock cost a single request.
    """

    def __init__(self, ttl_seconds: int = 300):
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, list[float]]] = {}
        logging.getLogger("yfinance").setLevel(logging.CRITICAL)  # silence "possibly delisted" noise

    def history(self, yf_symbols: list[str]) -> dict[str, list[float]]:
        now = time.monotonic()
        result: dict[str, list[float]] = {}
        missing: list[str] = []
        for symbol in dict.fromkeys(yf_symbols):
            cached = self._cache.get(symbol)
            if cached and now - cached[0] < self._ttl:
                result[symbol] = cached[1]
            else:
                missing.append(symbol)

        if missing:
            with ThreadPoolExecutor(max_workers=8) as pool:
                for symbol, closes in zip(missing, pool.map(self._fetch, missing)):
                    if closes:  # don't cache misses, they may be a temporary network error
                        self._cache[symbol] = (now, closes)
                        result[symbol] = closes
        return result

    @staticmethod
    def _fetch(yf_symbol: str) -> list[float]:
        try:
            # 1 year of daily bars is enough for MA200. auto_adjust=False keeps the real
            # traded close, which is what users compare their average cost against.
            df = yf.Ticker(yf_symbol).history(period="1y", auto_adjust=False)
        except Exception:
            log.warning("Price fetch failed for %s", yf_symbol, exc_info=True)
            return []
        if df is None or df.empty or "Close" not in df:
            return []
        return [float(x) for x in df["Close"].dropna()]
