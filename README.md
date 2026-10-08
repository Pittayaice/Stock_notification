# Stock Notification (LINE bot)

A LINE bot that tracks Thai 🇹🇭 (SET) and US 🇺🇸 stocks. Each user types in what they hold
(quantity and average buy price) and the bot shows their profit/loss in ± % and ± money,
plus moving averages (MA20/50/200).

## Commands

| Type | What it does |
|---|---|
| `add PTT 100 33.90` | Add a holding. Adding again re-averages the cost: 100 @ 33.90 + 50 @ 35 → 150 @ 34.2667 |
| `set PTT 150 34.27` | Overwrite quantity and average cost |
| `sell PTT 50 36` | Sell and record realized profit/loss |
| `del PTT` | Remove a holding |
| `port` | Portfolio: each stock's P/L, totals in THB, today's change |
| `PTT` | Price, today's change, MA20/50/200, your P/L on it |
| `deleteall` | Delete all of your data (asks to confirm) |
| `help` | Command list |

If a symbol is listed on both markets (e.g. `BH`), the bot shows **🇹🇭 SET / 🇺🇸 US** buttons.
Users can also type `BH.TH` or `BH.US` directly.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # then paste your LINE Channel secret and access token into .env
```

## Try it without LINE

```bash
.venv/bin/python -m app.cli
```

## Run with LINE

1. Start the server:
   ```bash
   .venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
   ```
2. In a second terminal, open a public tunnel to it:
   ```bash
   ngrok http 8000
   ```
3. In **LINE Developers console → your channel → Messaging API tab**:
   - Webhook URL: `https://<your-ngrok-address>/callback`, then click **Verify**
   - Turn on **Use webhook**
4. Message your bot on LINE: `help`

The free ngrok address changes every time ngrok restarts, so update the webhook URL when it does.

## Tests

```bash
.venv/bin/python -m pytest
```

## Project layout

```
app/
  main.py        Webhook server (FastAPI): checks LINE signature, replies in the background
  bot.py         Commands → reply messages
  portfolio.py   Profit/loss math (average cost, realized, totals in THB)
  indicators.py  Moving averages and cross detection
  prices.py      Yahoo Finance prices, cached 5 minutes, one fetch per symbol for all users
  line_api.py    LINE Messaging API client
  db.py          Tables: users, holdings, realized
  formatting.py  Number formatting (฿/$, ±, %)
  cli.py         Terminal version of the bot
tests/           pytest suite (no network needed)
```

## Notes

- Replies to user messages are free. Pushes (messages the bot sends on its own) use the
  LINE monthly quota, so the daily summary will be one push per user per day.
- Prices come from Yahoo Finance and may be ~15 minutes delayed.
- US holdings are converted to THB at today's USD/THB rate for the totals.

## Next

- Rich menu (button panel) for port / add / alerts / help
- Daily 17:00 summary push (SET close + last night's US close), opt-in per user
- Alerts: big daily moves, MA crosses, target prices
- Deploy: Postgres (Supabase) + Google Cloud Run
