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

    def yf_symbol(self, symbol: str) -> str:
        """Symbol as Yahoo Finance knows it: PTT → PTT.BK, BRK.B → BRK-B."""
        if self is Market.SET:
            return f"{symbol}.BK"
        return symbol.replace(".", "-")
