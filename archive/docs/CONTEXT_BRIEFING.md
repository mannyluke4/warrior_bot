# Context Briefing — Paste This When Starting a New Conversation

## What We're Doing
We are building a day trading bot at `/Users/mannyluke/warrior_bot/`. Currently in a **DATA COLLECTION** phase — NO code changes yet.

We are running backtests on proven runner stocks for specific dates (tick mode simulation), analyzing the bot's behavior (what it saw, why it traded or didn't), and comparing side-by-side with Ross Cameron's trades on the exact same stocks/days from his daily recap videos.

Everything is logged in detailed markdown files at `warrior_bot/trade_logs/{SYMBOL}_{DATE}.md`. See `ROLR_2026-01-14.md` as the gold standard format.

## Goal
Collect 25-30 detailed case studies, then review ALL cases side-by-side to identify strengths, weaknesses, and potential improvements for the bot. We are looking for "Trade Profiles" — recurring patterns where the bot excels or fails.

## What We Are NOT Doing
- No code changes. No bot improvements. Data collection only.
- We note potential improvements but do NOT implement them yet.

## Completed Trade Logs (8 of 25-30)
1. `ROLR_2026-01-14.md` — Bot -$889, Ross +$85,000
2. `MLEC_2026-02-13.md` — Bot +$478, Ross +$43,000
3. `TWG_2026-01-20.md` — Bot $0, Ross +$20,790
4. `VERO_2026-01-16.md` — Bot +$6,890, Ross +$3,400 (BOT WON)
5. `TNMG_2026-01-16.md` — Bot -$1,481, Ross +$2,000
6. `GWAV_2026-01-16.md` — Bot +$6,735, Ross +$4,000 (BOT WON)
7. `LCFY_2026-01-16.md` — Bot -$1,627, Ross +$10,000
8. `PAVM_2026-01-21.md` — Bot -$2,800, Ross +$43,950

**Note**: All results updated 2026-02-25 after adding bearish engulfing exit detection to backtester (was previously missing, causing inaccurate results).

Additional older study in `ROSS_STUDY.md` (MNTS — not yet in full trade log format).

## Trade Log Format
Each log includes: Stock Profile, Session Overview, Backtest Results, Key Observations (phase-by-phase), Bot Signal Timeline, Big Move Analysis, Critical Analysis, Pattern Profile, Ross Cameron's Trade Breakdown, Side-by-Side Comparison, Key Takeaways, Full 1-Min Bar Data.

## How to Continue
Ask me which stock/date to do next, or I'll provide the next one from Ross's recaps. The process is:
1. I give you a ticker + date
2. You run the simulation: `cd /Users/mannyluke/warrior_bot && source venv/bin/activate && python simulate.py {TICKER} {YYYY-MM-DD}`
3. Analyze the output and build the trade log
4. I provide Ross's recap from his video
5. You add Ross's section and side-by-side comparison
