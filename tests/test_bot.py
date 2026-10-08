import json

import pytest
from sqlalchemy import select

from app.cards import DOWN, UP
from app.db import Holding, Realized
from app.line_api import message_text
from tests.conftest import closes


def say(bot, text: str, user: str = "U1") -> str:
    return "\n".join(message_text(m) for m in bot.handle_text(user, text))


def text_nodes(node, found=None) -> list[dict]:
    """Every text component in a Flex message, in order."""
    found = [] if found is None else found
    if isinstance(node, dict):
        if node.get("type") == "text":
            found.append(node)
        for value in node.values():
            text_nodes(value, found)
    elif isinstance(node, list):
        for value in node:
            text_nodes(value, found)
    return found


def color_of(message: dict, text: str) -> str:
    return next(n for n in text_nodes(message) if n["text"] == text)["color"]


def holdings(sessions, user: str = "U1") -> dict[tuple[str, str], tuple[float, float]]:
    with sessions() as s:
        rows = s.scalars(select(Holding).where(Holding.user_id == user)).all()
        return {(h.symbol, h.market): (h.qty, h.avg_price) for h in rows}


def test_add_new_holding(bot, sessions):
    reply = say(bot, "add PTT 100 33.90")
    assert "PTT" in reply and "100 @ ฿33.90" in reply
    assert holdings(sessions) == {("PTT", "SET"): (100, 33.90)}


def test_add_again_re_averages(bot, sessions):
    say(bot, "add PTT 100 33.90")
    reply = say(bot, "add PTT 50 35")
    assert "150 @ ฿34.2667" in reply
    qty, avg = holdings(sessions)[("PTT", "SET")]
    assert qty == 150 and avg == pytest.approx(34.266667, abs=1e-6)


def test_accepts_commas_at_sign_and_currency(bot, sessions):
    say(bot, "add PTT 1,000 @ ฿33.90")
    assert holdings(sessions) == {("PTT", "SET"): (1000, 33.90)}


def test_set_overwrites(bot, sessions):
    say(bot, "add PTT 100 33.90")
    say(bot, "set PTT 300 32")
    assert holdings(sessions) == {("PTT", "SET"): (300, 32.0)}


def test_sell_records_realized_profit(bot, sessions):
    say(bot, "add PTT 100 33.90")
    reply = say(bot, "sell PTT 40 36")
    assert "+฿84.00" in reply
    assert holdings(sessions) == {("PTT", "SET"): (60, 33.90)}
    with sessions() as s:
        assert s.scalar(select(Realized.pnl)) == pytest.approx(84.00)


def test_sell_everything_closes_position(bot, sessions):
    say(bot, "add PTT 100 33.90")
    assert "Position closed" in say(bot, "sell PTT 100 36")
    assert holdings(sessions) == {}


def test_cannot_sell_more_than_held(bot, sessions):
    say(bot, "add PTT 100 33.90")
    assert "only hold 100" in say(bot, "sell PTT 101 36")
    assert holdings(sessions) == {("PTT", "SET"): (100, 33.90)}


def test_cannot_sell_what_you_dont_hold(bot):
    assert "not in your portfolio" in say(bot, "sell PTT 1 36")


def test_delete(bot, sessions):
    say(bot, "add PTT 100 33.90")
    assert "Removed" in say(bot, "del PTT")
    assert holdings(sessions) == {}


def test_bad_format_shows_usage(bot):
    assert "add SYMBOL QTY PRICE" in say(bot, "add PTT 100")
    assert "add SYMBOL QTY PRICE" in say(bot, "add PTT abc 33")
    assert "add SYMBOL QTY PRICE" in say(bot, "add PTT -5 33")


def test_unknown_symbol(bot, sessions):
    assert "Symbol not found" in say(bot, "add NOPE 1 1")
    assert holdings(sessions) == {}


def test_symbol_in_both_markets_asks_which(bot, sessions):
    [message] = bot.handle_text("U1", "add BH 100 150")
    buttons = [item["action"]["text"] for item in message["quickReply"]["items"]]
    assert buttons == ["add BH.TH 100 150", "add BH.US 100 150"]
    assert holdings(sessions) == {}


def test_market_suffix_skips_question(bot, sessions):
    say(bot, "add BH.US 10 55")
    assert holdings(sessions) == {("BH", "US"): (10, 55.0)}


def test_held_symbol_skips_question(bot, sessions):
    say(bot, "add BH.TH 100 150")
    say(bot, "add BH 100 160")
    assert holdings(sessions) == {("BH", "SET"): (200, 155.0)}


def test_portfolio_card(bot):
    say(bot, "add PTT 100 33.90")
    say(bot, "add CPALL 200 59.10")
    say(bot, "add AAPL 10 205")
    say(bot, "add BH.TH 100 150")
    say(bot, "sell BH 100 152")  # +฿200 realized
    say(bot, "add BH.US 10 55")
    say(bot, "sell BH.US 10 61")  # +$60 realized = ฿1,980 at 33.00
    [message] = bot.handle_text("U1", "port")

    assert message["type"] == "flex"
    assert message["contents"]["type"] == "bubble"
    assert message["altText"] == "📊 พอร์ต ฿91,487.00 · P/L +฿8,627.00 (+10.41%)"

    card = message_text(message)
    assert "฿91,487.00" in card  # value, big in the header
    assert "กำไร/ขาดทุน P/L  +฿8,627.00 (+10.41%)" in card
    assert "วันนี้ Today  +฿1,570.80 (+1.75%)" in card
    assert "PTT 100 @ ฿33.90  ฿34.75 ▲ 1.46%  +฿85.00 +2.51%" in card
    assert "CPALL 200 @ ฿59.10  ฿58.25 ▼ 0.43%  -฿170.00 -1.44%" in card
    # US: price and average stay in $, P/L money is converted to ฿ ($264 × 33.00)
    assert "AAPL 10 @ $205.00  $231.40 ▲ 2.10%  +฿8,712.00 +12.88%" in card
    assert "ต้นทุน Cost  ฿82,860.00" in card
    assert "ขายแล้ว Realized  +฿2,180.00" in card  # ฿200 + $60 × 33.00
    assert "USD/THB  33.00" in card
    assert "9 Oct 2026 17:05" in card
    assert "[🔄 Refresh]" in card
    assert card.index("CPALL") < card.index("PTT") < card.index("AAPL")  # SET first, A→Z

    assert color_of(message, "+฿85.00") == UP
    assert color_of(message, "-฿170.00") == DOWN


def test_many_holdings_become_a_carousel(bot, prices):
    for i in range(20):
        prices.data[f"S{i:02}.BK"] = closes(10.0, 11.0)
        say(bot, f"add S{i:02}.TH 100 10")
    [message] = bot.handle_text("U1", "port")
    bubbles = message["contents"]["contents"]
    assert message["contents"]["type"] == "carousel"
    assert len(bubbles) == 2
    assert "(2/2)" in message_text(message)
    assert all(len(json.dumps(b, ensure_ascii=False).encode()) < 30_000 for b in bubbles)


def test_portfolio_fetches_each_symbol_once(bot, prices):
    say(bot, "add PTT 100 33.90")
    say(bot, "add AAPL 10 205")
    prices.calls.clear()
    say(bot, "port")
    assert prices.calls == [["PTT.BK", "AAPL", "THB=X"]]


def test_portfolio_without_fx_rate_excludes_us(bot, prices):
    say(bot, "add PTT 100 33.90")
    say(bot, "add AAPL 10 205")
    del prices.data["THB=X"]
    reply = say(bot, "port")
    assert "ต้นทุน Cost  ฿3,390.00" in reply
    assert "+$264.00" in reply  # can't convert, so stays in $
    assert "Total excludes US" in reply


def test_empty_portfolio(bot):
    assert "empty" in say(bot, "port")


def test_users_are_separate(bot):
    say(bot, "add PTT 100 33.90", user="U1")
    assert "empty" in say(bot, "port", user="U2")


def test_stock_detail_with_moving_averages(bot):
    say(bot, "add PTT 100 33.90")
    reply = say(bot, "ptt")
    assert "🇹🇭 PTT (SET)" in reply
    assert "ราคา Price ฿34.75" in reply
    assert "+฿0.50 (+1.46%)" in reply
    assert "MA50 ฿34.26" in reply  # (49 × 34.25 + 34.75) / 50
    assert "crossed up today" in reply
    assert "MA200" in reply
    assert "+฿85.00 (+2.51%)" in reply


def test_detail_with_short_history(bot, prices):
    prices.data["NEW.BK"] = [10.0, 11.0]
    assert "not enough data" in say(bot, "NEW")


def test_delete_all_needs_confirmation(bot, sessions):
    say(bot, "add PTT 100 33.90")
    [message] = bot.handle_text("U1", "deleteall")
    assert message["quickReply"]["items"][0]["action"]["text"] == "deleteall confirm"
    assert holdings(sessions)
    say(bot, "deleteall confirm")
    assert holdings(sessions) == {}


def test_help_and_unknown(bot):
    assert "How to use" in say(bot, "help")
    assert "Unknown command" in say(bot, "สวัสดี")
    assert "Unknown command" in say(bot, "what is my port")
