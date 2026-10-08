"""LINE Flex Message cards. The portfolio is laid out as a card instead of plain text."""

from dataclasses import dataclass
from datetime import datetime

from app import formatting as fmt
from app.markets import Market
from app.portfolio import Position, Summary

ROWS_PER_BUBBLE = 15  # keeps each bubble well under LINE's 30 KB limit
MAX_BUBBLES = 12  # LINE carousel limit

INK = "#111827"
MUTED = "#6B7280"
RULE = "#E5E7EB"
UP = "#16A34A"
DOWN = "#DC2626"
WARN = "#B45309"
HEADER_BG = "#111827"
HEADER_TEXT = "#FFFFFF"
HEADER_MUTED = "#9CA3AF"
HEADER_UP = "#4ADE80"
HEADER_DOWN = "#F87171"

# Column widths shared by the column titles and every stock row
STOCK_COL, PRICE_COL, PNL_COL = 5, 4, 5


@dataclass(frozen=True)
class PortfolioView:
    positions: list[Position]  # sorted: SET first, then US, A→Z
    summary: Summary | None  # THB totals, None when nothing could be priced
    usd_thb: float | None
    has_us: bool
    missing: list[str]  # holdings with no price, e.g. "🇹🇭 XYZ"
    realized: list[tuple[Market, float]]
    updated: datetime


def tone(amount: float, up: str = UP, down: str = DOWN) -> str:
    rounded = round(amount, 2)
    return up if rounded > 0 else down if rounded < 0 else MUTED


def text(value: str, **style) -> dict:
    return {"type": "text", "text": value, **style}


def vbox(*contents: dict, **style) -> dict:
    return {"type": "box", "layout": "vertical", "contents": list(contents), **style}


def hbox(*contents: dict, **style) -> dict:
    return {"type": "box", "layout": "horizontal", "contents": list(contents), **style}


def label_row(label: str, value: str, value_color: str, label_color: str = MUTED, **style) -> dict:
    return {
        "type": "box",
        "layout": "baseline",
        "contents": [
            text(label, size="xs", color=label_color, flex=0),
            text(value, size="sm", color=value_color, align="end", weight="bold"),
        ],
        **style,
    }


def separator(**style) -> dict:
    return {"type": "separator", "color": RULE, **style}


def in_baht(amount: float, market: Market, usd_thb: float | None) -> tuple[float, str]:
    """(amount, currency) in baht when it can be converted, else in the market's own currency."""
    if market is Market.US and usd_thb:
        return amount * usd_thb, "฿"
    return amount, market.currency


def position_row(p: Position, usd_thb: float | None) -> dict:
    # Prices stay in the stock's own currency (what the user entered); P/L money is in baht
    cur = p.market.currency
    pnl, pnl_cur = in_baht(p.pnl, p.market, usd_thb)
    if p.day_change_pct is None:
        today = text("-", size="xxs", color=MUTED, align="end")
    else:
        today = text(
            f"{fmt.arrow(p.day_change_pct)} {abs(p.day_change_pct):.2f}%",
            size="xxs", color=tone(p.day_change_pct), align="end",
        )
    return hbox(
        vbox(
            text(p.symbol, size="sm", weight="bold", color=INK),
            text(f"{fmt.qty(p.qty)} @ {fmt.price(p.avg_price, cur)}", size="xxs", color=MUTED),
            flex=STOCK_COL,
        ),
        vbox(
            text(fmt.money(p.price, cur), size="sm", color=INK, align="end"),
            today,
            flex=PRICE_COL,
        ),
        vbox(
            text(fmt.signed_money(pnl, pnl_cur), size="sm", weight="bold", color=tone(pnl), align="end"),
            text(fmt.signed_pct(p.pnl_pct), size="xxs", color=tone(pnl), align="end"),
            flex=PNL_COL,
        ),
        margin="lg",
    )


def holdings_rows(positions: list[Position], usd_thb: float | None) -> list[dict]:
    rows = [hbox(
        text("หุ้น · Stock", size="xxs", color=MUTED, flex=STOCK_COL),
        text("ราคา · Price", size="xxs", color=MUTED, align="end", flex=PRICE_COL),
        text("กำไร/ขาดทุน · P/L", size="xxs", color=MUTED, align="end", flex=PNL_COL),
    )]
    for market in Market:
        in_market = [p for p in positions if p.market is market]
        if in_market:
            rows.append(text(f"{market.flag} {market.label}", size="xs", weight="bold", color=INK, margin="xl"))
            rows.append(separator(margin="sm"))
            rows.extend(position_row(p, usd_thb) for p in in_market)
    return rows


def summary_header(view: PortfolioView) -> dict:
    contents = [text("📊 พอร์ตของฉัน · My Portfolio", size="xs", color=HEADER_MUTED)]
    s = view.summary
    if s:
        contents += [
            text(fmt.money(s.value, "฿"), size="xxl", weight="bold", color=HEADER_TEXT, margin="sm"),
            label_row(
                "กำไร/ขาดทุน P/L",
                f"{fmt.signed_money(s.pnl, '฿')} ({fmt.signed_pct(s.pnl_pct)})",
                tone(s.pnl, HEADER_UP, HEADER_DOWN), label_color=HEADER_MUTED, margin="md",
            ),
            label_row(
                "วันนี้ Today",
                f"{fmt.signed_money(s.day_change, '฿')} ({fmt.signed_pct(s.day_change_pct)})",
                tone(s.day_change, HEADER_UP, HEADER_DOWN), label_color=HEADER_MUTED, margin="sm",
            ),
        ]
    return vbox(*contents, paddingAll="20px", backgroundColor=HEADER_BG)


def totals_rows(view: PortfolioView) -> list[dict]:
    rows: list[dict] = [separator(margin="xl")]
    if view.summary:
        rows.append(label_row("ต้นทุน Cost", fmt.money(view.summary.cost, "฿"), INK, margin="lg"))
    realized = [in_baht(total, market, view.usd_thb) for market, total in view.realized]
    if realized and all(cur == "฿" for _, cur in realized):
        realized = [(sum(amount for amount, _ in realized), "฿")]
    for amount, cur in realized:
        rows.append(label_row("ขายแล้ว Realized", fmt.signed_money(amount, cur), tone(amount), margin="sm"))
    if view.has_us and view.usd_thb:
        rows.append(label_row("USD/THB", f"{view.usd_thb:.2f}", INK, margin="sm"))
    warnings = []
    if view.missing:
        warnings.append("⚠️ ดึงราคาไม่ได้ · No price for: " + ", ".join(view.missing))
    if view.has_us and not view.usd_thb:
        warnings.append("⚠️ ไม่มีค่าเงิน USD/THB ยอดรวมไม่รวมหุ้นอเมริกา · Total excludes US")
    rows += [text(w, size="xxs", color=WARN, wrap=True, margin="md") for w in warnings]
    return rows


def footer(updated: datetime) -> dict:
    return vbox(
        text(
            f"อัปเดต {updated.day} {updated:%b %Y %H:%M} · ราคาอาจล่าช้า ~15 นาที",
            size="xxs", color=MUTED, align="center", wrap=True,
        ),
        {
            "type": "button",
            "action": {"type": "message", "label": "🔄 Refresh", "text": "port"},
            "style": "secondary",
            "height": "sm",
            "margin": "md",
        },
    )


def portfolio_card(view: PortfolioView) -> dict:
    """The `port` reply: one card, or a swipeable carousel when there are many holdings."""
    pages = [
        view.positions[i:i + ROWS_PER_BUBBLE]
        for i in range(0, len(view.positions), ROWS_PER_BUBBLE)
    ][:MAX_BUBBLES] or [[]]

    bubbles = []
    for number, page in enumerate(pages, start=1):
        if number == 1:
            header = summary_header(view)
            body = holdings_rows(page, view.usd_thb) + totals_rows(view)
        else:
            header = vbox(
                text(f"📊 พอร์ตของฉัน · My Portfolio ({number}/{len(pages)})", size="xs", color=HEADER_MUTED),
                paddingAll="16px", backgroundColor=HEADER_BG,
            )
            body = holdings_rows(page, view.usd_thb)
        bubbles.append({
            "type": "bubble",
            "size": "giga",
            "header": header,
            "body": vbox(*body, paddingAll="16px"),
            "footer": footer(view.updated),
        })

    if view.summary:
        s = view.summary
        alt = f"📊 พอร์ต {fmt.money(s.value, '฿')} · P/L {fmt.signed_money(s.pnl, '฿')} ({fmt.signed_pct(s.pnl_pct)})"
    else:
        alt = "📊 พอร์ตของฉัน · My Portfolio"
    contents = bubbles[0] if len(bubbles) == 1 else {"type": "carousel", "contents": bubbles}
    return {"type": "flex", "altText": alt, "contents": contents}
