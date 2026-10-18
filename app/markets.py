from enum import StrEnum

FX_USD_THB = "THB=X"  # Yahoo Finance symbol for the USD → THB rate


class Market(StrEnum):
    SET = "SET"
    US = "US"

    @property
    def currency(self) -> str:
        return "฿" if self is Market.SET else "$"

    @property
    def flag(self) -> str:
        return "🇹🇭" if self is Market.SET else "🇺🇸"

    @property
    def suffix(self) -> str:
        """What users type after a symbol to pick this market: BH.TH, BH.US."""
        return "TH" if self is Market.SET else "US"

    @property
    def label(self) -> str:
        return "หุ้นไทย SET" if self is Market.SET else "หุ้นอเมริกา US"

    @property
    def calendar_symbol(self) -> str:
        """A symbol that has a daily bar on every trading day, used to spot holidays.

        Yahoo's own SET index (^SET.BK) has gaps in its history, so a large SET stock is used instead.
        """
        return "PTT.BK" if self is Market.SET else "^GSPC"

    def yf_symbol(self, symbol: str) -> str:
        """Symbol as Yahoo Finance knows it: PTT → PTT.BK, BRK.B → BRK-B."""
        if self is Market.SET:
            return f"{symbol}.BK"
        return symbol.replace(".", "-")
