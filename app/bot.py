"""Turns a user's chat text into LINE reply messages."""

import math
import re
from collections.abc import Callable
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import formatting as fmt
from app.cards import PortfolioView, portfolio_card
from app.config import TZ
from app.db import Holding, Realized, User
from app.indicators import crossed, sma
from app.line_api import text_message
from app.markets import FX_USD_THB, Market
from app.portfolio import Position, apply_sell, merge_buy, pct, summarize
from app.prices import PriceProvider

SYMBOL_RE = re.compile(r"[A-Z0-9][A-Z0-9.&\-]{0,14}")
MA_PERIODS = (20, 50, 200)
EPSILON = 1e-9

HELP = """📖 วิธีใช้ · How to use

add PTT 100 33.90
เพิ่มหุ้น: จำนวน, ต้นทุนเฉลี่ย (ซื้อเพิ่มจะเฉลี่ยต้นทุนให้)
Add shares: qty, avg price (buying more re-averages)

set PTT 150 34.27
แก้จำนวน/ต้นทุน · Overwrite qty & avg price

sell PTT 50 36
ขายหุ้น · Sell and record realized P/L

del PTT
ลบออกจากพอร์ต · Remove a holding

port
ดูพอร์ต · Show portfolio

PTT
ดูราคา + เส้นค่าเฉลี่ย MA · Price & moving averages

ชื่อซ้ำ 2 ตลาด? ใส่ .TH หรือ .US เช่น BH.TH, AAPL.US
Same symbol in both markets? Add .TH or .US"""

WELCOME = (
    "👋 สวัสดี! บอทสรุปพอร์ตหุ้นไทย 🇹🇭 และอเมริกา 🇺🇸\n"
    "Hi! I track your Thai and US stocks.\n\n"
    f"{HELP}\n\n"
    "⚠️ ใช้ติดตามพอร์ตเท่านั้น ไม่ใช่คำแนะนำการลงทุน ราคาอาจล่าช้า ~15 นาที\n"
    "For tracking only, not investment advice. Prices may be delayed ~15 min."
)

HINT = "พิมพ์ help เพื่อดูวิธีใช้ · Type help to see commands"
UNKNOWN = f"🤔 ไม่เข้าใจคำสั่ง · Unknown command\n{HINT}"
VIEW_PORT = "พิมพ์ port เพื่อดูพอร์ต · Type port to view"

USAGE = {
    "add": ("add SYMBOL QTY PRICE", "add PTT 100 33.90"),
    "set": ("set SYMBOL QTY PRICE", "set PTT 150 34.27"),
    "sell": ("sell SYMBOL QTY PRICE", "sell PTT 50 36"),
    "del": ("del SYMBOL", "del PTT"),
}


def parse_symbol(raw: str) -> tuple[str, list[Market]] | None:
    """'PTT' → ('PTT', [SET, US]), 'BH.TH' → ('BH', [SET]), 'AAPL.US' → ('AAPL', [US])."""
    symbol = raw.upper()
    markets = [Market.SET, Market.US]
    for suffix, market in ((".TH", Market.SET), (".BK", Market.SET), (".US", Market.US)):
        if symbol.endswith(suffix):
            symbol, markets = symbol[: -len(suffix)], [market]
            break
    if not SYMBOL_RE.fullmatch(symbol):
        return None
    return symbol, markets


def parse_number(raw: str) -> float | None:
    """'33.90', '$205', '฿1000' → float. Commas are removed before this is called."""
    try:
        value = float(raw.strip("$฿"))
    except ValueError:
        return None
    return value if value > 0 and math.isfinite(value) else None


def usage_message(cmd: str) -> dict:
    pattern, example = USAGE[cmd]
    return text_message(f"✏️ รูปแบบ · Format\n{pattern}\n\nเช่น · e.g.\n{example}")


class Bot:
    def __init__(
        self,
        sessions: sessionmaker,
        prices: PriceProvider,
        now: Callable[[], datetime] = lambda: datetime.now(TZ),
    ):
        self._sessions = sessions
        self._prices = prices
        self._now = now

    def welcome(self, user_id: str) -> list[dict]:
        with self._sessions() as session:
            self._ensure_user(session, user_id)
            session.commit()
        return [text_message(WELCOME)]

    def deactivate(self, user_id: str) -> None:
        """User blocked the bot. Keep their data in case they come back."""
        with self._sessions() as session:
            user = session.get(User, user_id)
            if user:
                user.active = False
                session.commit()

    def handle_text(self, user_id: str, text: str) -> list[dict]:
        tokens = [t for t in text.replace(",", "").split() if t != "@"]
        if not tokens:
            return [text_message(HINT)]
        cmd, args = tokens[0].lower(), tokens[1:]

        with self._sessions() as session:
            self._ensure_user(session, user_id)
            session.commit()
            if cmd in ("add", "set", "sell"):
                return self._trade(session, user_id, cmd, args)
            if cmd in ("del", "delete", "remove"):
                return self._delete(session, user_id, args)
            if cmd in ("port", "portfolio"):
                return self._portfolio(session, user_id)
            if cmd in ("help", "?"):
                return [text_message(HELP)]
            if cmd == "deleteall":
                return self._delete_all(session, user_id, args)
            if len(tokens) == 1 and parse_symbol(tokens[0]):
                return self._detail(session, user_id, tokens[0])
        return [text_message(UNKNOWN)]

    # --- commands ---

    def _trade(self, session: Session, user_id: str, cmd: str, args: list[str]) -> list[dict]:
        if len(args) != 3:
            return [usage_message(cmd)]
        qty, price = parse_number(args[1]), parse_number(args[2])
        if qty is None or price is None:
            return [usage_message(cmd)]

        resolved = self._resolve(
            session, user_id, args[0],
            retry=lambda s: f"{cmd} {s} {args[1]} {args[2]}",
            held_only=cmd == "sell",
        )
        if isinstance(resolved, list):
            return resolved
        symbol, market = resolved
        holding = self._holding(session, user_id, symbol, market)
        name, cur = f"{market.flag} {symbol}", market.currency

        if cmd == "sell":
            if qty > holding.qty + EPSILON:
                return [text_message(
                    f"❌ คุณมี {name} แค่ {fmt.qty(holding.qty)} หุ้น\n"
                    f"You only hold {fmt.qty(holding.qty)} shares"
                )]
            avg = holding.avg_price
            pnl = apply_sell(avg, qty, price)
            session.add(Realized(
                user_id=user_id, symbol=symbol, market=market.value,
                qty=qty, sell_price=price, avg_price=avg, pnl=pnl,
            ))
            lines = [
                f"✅ ขาย {name} แล้ว · Sold",
                f"{fmt.qty(qty)} @ {fmt.price(price, cur)} (ทุน avg {fmt.price(avg, cur)})",
                f"{fmt.dot(pnl)} กำไรที่ขายแล้ว Realized {fmt.signed_money(pnl, cur)}"
                f" ({fmt.signed_pct(pct(price - avg, avg))})",
            ]
            remaining = holding.qty - qty
            if remaining <= EPSILON:
                session.delete(holding)
                lines.append("ขายหมดแล้ว · Position closed")
            else:
                holding.qty = remaining
                lines.append(f"เหลือ Remaining {fmt.qty(remaining)} @ {fmt.price(avg, cur)}")

        elif cmd == "add" and holding is not None:
            before = f"{fmt.qty(holding.qty)} @ {fmt.price(holding.avg_price, cur)}"
            holding.qty, holding.avg_price = merge_buy(holding.qty, holding.avg_price, qty, price)
            lines = [
                f"✅ ซื้อ {name} เพิ่ม · Bought more",
                f"เดิม Before: {before}",
                f"ซื้อ Buy: {fmt.qty(qty)} @ {fmt.price(price, cur)}",
                f"รวม Now: {fmt.qty(holding.qty)} @ {fmt.price(holding.avg_price, cur)}",
                "(ต้นทุนเฉลี่ยใหม่ · new average cost)",
            ]

        else:  # first add, or set
            if holding is None:
                session.add(Holding(
                    user_id=user_id, symbol=symbol, market=market.value, qty=qty, avg_price=price,
                ))
            else:
                holding.qty, holding.avg_price = qty, price
            verb = "บันทึก {} แล้ว · Saved" if cmd == "set" else "เพิ่ม {} แล้ว · Added"
            lines = [f"✅ {verb.format(name)}", f"{fmt.qty(qty)} @ {fmt.price(price, cur)}"]

        session.commit()
        return [text_message("\n".join([*lines, "", VIEW_PORT]))]

    def _delete(self, session: Session, user_id: str, args: list[str]) -> list[dict]:
        if len(args) != 1:
            return [usage_message("del")]
        resolved = self._resolve(session, user_id, args[0], retry=lambda s: f"del {s}", held_only=True)
        if isinstance(resolved, list):
            return resolved
        symbol, market = resolved
        session.delete(self._holding(session, user_id, symbol, market))
        session.commit()
        return [text_message(f"🗑️ ลบ {market.flag} {symbol} ออกจากพอร์ตแล้ว · Removed")]

    def _delete_all(self, session: Session, user_id: str, args: list[str]) -> list[dict]:
        if [a.lower() for a in args] != ["confirm"]:
            return [text_message(
                "⚠️ ลบข้อมูลพอร์ตทั้งหมดของคุณ? ย้อนกลับไม่ได้\n"
                "Delete ALL your portfolio data? This can't be undone.",
                [("🗑️ ยืนยัน Confirm", "deleteall confirm")],
            )]
        session.execute(delete(Holding).where(Holding.user_id == user_id))
        session.execute(delete(Realized).where(Realized.user_id == user_id))
        session.commit()
        return [text_message("🗑️ ลบข้อมูลทั้งหมดแล้ว · All your data has been deleted")]

    def _portfolio(self, session: Session, user_id: str) -> list[dict]:
        holdings = session.scalars(
            select(Holding).where(Holding.user_id == user_id).order_by(Holding.market, Holding.symbol)
        ).all()
        if not holdings:
            return [text_message("📭 พอร์ตยังว่าง · Your portfolio is empty\nลองพิมพ์ · Try: add PTT 100 33.90")]

        realized = [
            (Market(m), total)
            for m, total in session.execute(
                select(Realized.market, func.sum(Realized.pnl))
                .where(Realized.user_id == user_id)
                .group_by(Realized.market)
                .order_by(Realized.market)
            ).all()
        ]
        # Anything in USD (holdings or past US sells) is shown in baht, so fetch the rate
        has_us = any(h.market == Market.US.value for h in holdings) or any(m is Market.US for m, _ in realized)
        symbols = [Market(h.market).yf_symbol(h.symbol) for h in holdings]
        history = self._prices.history(symbols + [FX_USD_THB] if has_us else symbols)

        positions: list[Position] = []
        missing: list[str] = []
        for h in holdings:
            market = Market(h.market)
            closes = history.get(market.yf_symbol(h.symbol))
            if not closes:
                missing.append(f"{market.flag} {h.symbol}")
                continue
            prev = closes[-2] if len(closes) > 1 else None
            positions.append(Position(h.symbol, market, h.qty, h.avg_price, closes[-1], prev))
        fx = history.get(FX_USD_THB)
        usd_thb = fx[-1] if fx else None

        # Without a USD/THB rate, US holdings can't be added to a THB total
        counted = positions if usd_thb else [p for p in positions if p.market is Market.SET]

        return [portfolio_card(PortfolioView(
            positions=positions,
            summary=summarize(counted, usd_thb or 0.0) if counted else None,
            usd_thb=usd_thb,
            has_us=has_us,
            missing=missing,
            realized=realized,
            updated=self._now(),
        ))]

    def _detail(self, session: Session, user_id: str, raw: str) -> list[dict]:
        resolved = self._resolve(session, user_id, raw, retry=lambda s: s)
        if isinstance(resolved, list):
            return resolved
        symbol, market = resolved
        yf_symbol = market.yf_symbol(symbol)
        closes = self._prices.history([yf_symbol]).get(yf_symbol)
        if not closes:
            return [text_message(f"❌ ดึงราคา {symbol} ไม่ได้ ลองใหม่อีกครั้ง\nCouldn't get a price for {symbol}, please try again")]

        cur, last = market.currency, closes[-1]
        price_line = f"ราคา Price {fmt.money(last, cur)}"
        if len(closes) > 1:
            change = last - closes[-2]
            price_line += (
                f"\n{fmt.arrow(change)} {fmt.signed_money(change, cur)}"
                f" ({fmt.signed_pct(pct(change, closes[-2]))}) วันนี้ today"
            )
        lines = [f"{market.flag} {symbol} ({market.value})", price_line, ""]

        for period in MA_PERIODS:
            ma = sma(closes, period)
            if ma is None:
                lines.append(f"MA{period} - ข้อมูลไม่พอ · not enough data")
                continue
            status = "✅ เหนือเส้น above" if last > ma else "⚠️ ใต้เส้น below"
            cross = crossed(closes, period)
            if cross > 0:
                status += "\n   🔼 ตัดขึ้นวันนี้ · crossed up today"
            elif cross < 0:
                status += "\n   🔽 ตัดลงวันนี้ · crossed down today"
            lines.append(f"MA{period} {fmt.money(ma, cur)} {status}")

        holding = self._holding(session, user_id, symbol, market)
        if holding:
            p = Position(symbol, market, holding.qty, holding.avg_price, last, None)
            lines += [
                "",
                f"ของคุณ Yours: {fmt.qty(p.qty)} @ {fmt.price(p.avg_price, cur)}",
                f"{fmt.dot(p.pnl)} {fmt.signed_money(p.pnl, cur)} ({fmt.signed_pct(p.pnl_pct)})",
            ]
        return [text_message("\n".join(lines))]

    # --- helpers ---

    def _resolve(
        self,
        session: Session,
        user_id: str,
        raw: str,
        retry: Callable[[str], str],
        held_only: bool = False,
    ) -> tuple[str, Market] | list[dict]:
        """Work out which market a symbol is in, or return the messages to send instead.

        `retry` rebuilds the user's command with a market suffix (BH → BH.TH) for the
        quick-reply buttons, so a tap simply re-runs the command and no state is kept.
        """
        parsed = parse_symbol(raw)
        if parsed is None:
            return [text_message(f"❌ ชื่อหุ้นไม่ถูกต้อง · Invalid symbol: {raw}")]
        symbol, markets = parsed
        held = [m for m in markets if self._holding(session, user_id, symbol, m)]

        if held_only:
            if not held:
                return [text_message(f"❌ ไม่มี {symbol} ในพอร์ต · {symbol} is not in your portfolio\n{VIEW_PORT}")]
            candidates = held
        elif len(held) == 1:
            candidates = held  # adding to something they already hold, no need to ask
        else:
            found = self._prices.history([m.yf_symbol(symbol) for m in markets])
            candidates = [m for m in markets if m.yf_symbol(symbol) in found]
            if not candidates:
                hint = "" if len(markets) == 1 else f"\nลองใส่ตลาด · Try {symbol}.TH or {symbol}.US"
                return [text_message(f"❌ ไม่พบหุ้น {symbol} · Symbol not found{hint}")]

        if len(candidates) == 1:
            return symbol, candidates[0]
        return [text_message(
            f"🤔 {symbol} มีทั้งในตลาดไทยและอเมริกา เลือกตลาด\n{symbol} is listed in both markets. Which one?",
            [(f"{m.flag} {m.value}", retry(f"{symbol}.{m.suffix}")) for m in candidates],
        )]

    @staticmethod
    def _holding(session: Session, user_id: str, symbol: str, market: Market) -> Holding | None:
        return session.scalar(select(Holding).where(
            Holding.user_id == user_id, Holding.symbol == symbol, Holding.market == market.value,
        ))

    @staticmethod
    def _ensure_user(session: Session, user_id: str) -> None:
        user = session.get(User, user_id)
        if user is None:
            session.add(User(line_user_id=user_id))
        elif not user.active:
            user.active = True
