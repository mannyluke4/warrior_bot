# Warrior Bot — Project Status Report
**Date: February 26, 2026**

---

## 1. What Is This Project?

An automated day trading bot that replicates Ross Cameron's (Warrior Trading) micro-pullback strategy on small-cap momentum stocks. The bot trades the morning session (7:00 AM - 12:00 PM ET) on Alpaca's paper trading platform, targeting stocks with low float, high gap%, and strong relative volume.

### Architecture
- **1-minute bars** = primary setup detection (impulse → pullback → ARM → entry)
- **10-second bars** = exit detection (bearish engulfing, topping wicky patterns)
- **Live ticks** = armed trigger execution + stop/TP monitoring
- **State machine** in `micro_pullback.py` drives the core detection logic
- **Trade manager** in `trade_manager.py` handles all order execution, position management, exits

### Key Files
| File | Purpose |
|------|---------|
| `bot.py` | Main live bot — dual bar builders, websocket data ingestion |
| `micro_pullback.py` | Core detector — 1-min state machine, pattern detection, ARM logic |
| `trade_manager.py` | Order execution — entries, exits, chase logic, position tracking |
| `simulate.py` | Backtesting engine — runs historical tick data through detector |
| `bars.py` | Bar builder — VWAP, HOD, PM_HIGH calculations |
| `patterns.py` | Pattern recognition — ASC_TRIANGLE, FLAT_TOP, R2G, VOL_SURGE |
| `.env` | All configuration knobs (~160 settings) |

### Account Settings
- $30K funded, $60K buying power
- $1,000 max risk per trade
- Paper trading only (not live money yet)

---

## 2. Current Project Phase: Trade Profile Study

We are in a **data collection phase**, studying how the bot performs vs Ross Cameron on historically proven trade days. The goal is to identify recurring "trade profiles" — stock behavior patterns where the bot excels or fails — and then tune the bot for each profile.

### Methodology
1. Pick a stock Ross traded profitably from his daily recap videos
2. Run the bot's backtester on that exact stock + date (tick-mode simulation)
3. Document everything: bot's signals, entries, exits, resets, skips
4. Watch Ross's recap video and document his exact trades
5. Compare side-by-side: entry timing, sizing, exit strategy, P&L
6. Identify which "trade profile" the stock fits
7. Log findings in `/warrior_bot/trade_logs/{SYMBOL}_{DATE}.md`

### Progress: 11 of 25-30 target cases complete (~40%)

---

## 3. Completed Trade Studies

| # | Stock | Date | Float | Gap | Bot P&L | Ross P&L | Profile | Key Finding |
|---|-------|------|-------|-----|---------|----------|---------|-------------|
| 1 | ROLR | 01/14 | 4.2M | +16% | -$889 | +$85,000 | A: Early Bird | BE exits killed parabolic runner mid-move |
| 2 | MLEC | 02/13 | 0.3M | +94% | +$178 | +$43,000 | B: Fast PM | Entry 10 min late, 2x the price Ross got |
| 3 | TWG | 01/20 | 1.1M | +155% | $0 | +$20,790 | B: Fast PM | Bot completely shut out — zero trades |
| 4 | VERO | 01/16 | 0.8M | +36% | **+$6,890** | +$3,400 | A: Early Bird | **BOT WON** — 07:03 entry beat Ross |
| 5 | TNMG | 01/16 | 5.5M | +25% | -$481 | +$2,000 | E: Trap | Stale filter saved $1K on late re-entry |
| 6 | GWAV | 01/16 | 0.4M | +22% | **+$6,735** | +$4,000 | D: Flash Spike | **BOT WON** — BE exit captured spike perfectly |
| 7 | LCFY | 01/16 | — | halt | -$1,627 | +$10,000 | C/F: Resistance + Halt | Bot chopped at $6-$6.50 resistance 3 times |
| 8 | PAVM | 01/21 | 0.8M | +80% | -$2,800 | +$43,950 | B: Fast PM | Entered 30x available volume at session low |
| 9 | ACON | 01/08 | 2.2M | +30% | -$2,630 | +$9,293 | C: Resistance | Entry $8.22 vs Ross $7.60 — $0.62 gap = $4K+ edge |
| 10 | FLYX | 01/08 | 3.5M | +15% | -$703 | positive | A: Early Bird | Bot had BETTER entry ($4.91 vs $5.89) but BE exit killed winner |
| 11 | ANPA | 01/09 | 1.8M | +40% | **+$4,368** | -$11,000 | — | **BOT WON** — MACD gate saved from crash, caught 2nd breakout |

**Net: Bot +$5,041 | Ross ~+$265,000**

The massive gap is expected — Ross trades with $500K+ buying power and scales aggressively. The important metrics are win rate, strategy quality, and whether losses were avoidable.

---

## 4. Trade Profiles Identified (6 so far)

### Profile A: "Early Bird Premarket Ramp" — BOT STRENGTH
- Stock starts moving before 7:30 AM with building volume
- Low price ($3-6), micro float, steady green bars
- Bot enters at 07:00-07:15 before Ross even sees it on scanners
- **Bot wins when**: Early detection fires, mechanical entry beats human hesitation
- **Bot loses when**: TW/BE exits cut winners short during parabolic moves
- Cases: VERO (+$6,890 BOT WIN), ROLR (-$889), FLYX (-$703 but had better entry than Ross)

### Profile B: "Fast Premarket Mover" — BOT WEAKNESS
- Stock hits scanner 8:00-8:15, already up big. Ross enters immediately
- Bot's state machine needs bars to build structure — can't enter on first impulse
- By the time patterns confirm, stock is fading. Bot enters hours late at 2x the price
- Cases: MLEC (+$178), TWG ($0), PAVM (-$2,800), MNTS (study only)

### Profile C: "Resistance Chopper" — BOT WEAKNESS
- Clear resistance zone (often at half/whole dollar). Stock tests it 2-3 times
- Bot keeps buying INTO resistance. Ross buys the DIP after rejection, waits for the BREAK
- No resistance tracking — bot treats each setup independently
- Cases: LCFY (-$1,627), TNMG (-$481), ACON (-$2,630)

### Profile D: "Flash Spike Ghost" — BOT STRENGTH (with BE exits)
- Ultra micro float, near-zero premarket volume, sudden 40-60% spike in 2-3 minutes
- Bot enters pre-spike with large position, BE exit catches reversal perfectly
- Cases: GWAV (+$6,735 BOT WIN)

### Profile E: "Morning Spike Trap" — AVOID
- Looks like a runner on scanner but spikes then immediately reverses
- Cannot reclaim premarket high, loses VWAP within 3 minutes
- Cases: TNMG (-$481)

### Profile F: "Post-Halt Crash Recovery" — MISSED OPPORTUNITY
- Halt on open, crash, then real recovery from LOD. Bot can't trade post-halt recoveries
- Cases: LCFY (-$1,627)

---

## 5. Code Fixes Implemented (from studies)

### Fix #1: Bearish Engulfing Parabolic Grace (2026-02-25)
**Problem**: BE exits on 10-second bars were cutting parabolic winners short. ROLR, FLYX, VERO all had winning trades killed by premature BE exits during genuine upward momentum.

**Solution**: 6-bar grace period that suppresses BE exits when the trade is in profit AND the stock is making consecutive new highs on 10s bars. Lives in `trade_manager.py` + `simulate.py`.

**Impact**: Freed re-entries and held winners longer. Net improvement across studies.

### Fix #2: Stale Stock Filter (2026-02-25)
**Problem**: Bot kept re-entering stocks that had gone dead — no new highs, fading volume, sideways/down action. TNMG, LCFY, ACON all had late entries on dead stocks.

**Solution**: Combined rolling window (30 bars no new high) + session HOD (120 bars since last session high). Blocks new ARMs when a stock is stale. Lives in `micro_pullback.py`.

**Impact**: Blocked late re-entries on TNMG ($1K saved), LCFY ($1K saved), ACON ($508 saved). Zero regressions on winners.

**Combined improvement**: +$2,203 (+26%) across all 11 studied stocks.

### Fix #3: Pre-Trade Quote Quality Gate (2026-02-26, today)
**Problem**: Bot entered positions when Alpaca's quote data was garbage — phantom bids (5-9% off last trade), wide spreads. Then couldn't exit because bid data was unreliable.

**Solution**: Two checks before every entry in `on_signal()`:
1. Phantom bid check: skip if bid deviates >5% from last trade
2. Wide spread check: skip if bid-ask spread >5% of mid price

Lives in `trade_manager.py`. Config: `WB_ENTRY_MAX_SPREAD_PCT=5.0`, `WB_ENTRY_MAX_BID_DEV_PCT=5.0`.

### Fix #4: Critical F-String Crash Fix (2026-02-26, today)
**Problem**: Invalid f-string syntax in `_warn_if_stale_trade_and_quote()` caused a ValueError on every 10-second bar close. The exception was caught by a broad try/except in `on_trade()`, which silently killed the entire data pipeline — bar builders, trade manager price updates, and detector tick updates all skipped. The bot went **completely blind** during open positions.

**Solution**: Pre-format float values before interpolation. Also fixed `_stale_age_sec()` in `bot.py` to use `max(qt, tt)` instead of quote-only timestamp.

### Fix #5: Exit Fill Price Tracking (2026-02-26, today)
**Problem**: Bot never read `filled_avg_price` from Alpaca on exit orders. It reported exit prices based on the limit order price (which was always lower than actual fill). P&L was never calculated.

Example: RRGB exit — bot reported $4.67 (limit price, -$3,000 loss), but Alpaca actually filled at $4.90 (-$700 loss). The bot was over-reporting losses by $2,300 on a single trade.

**Solution**: Added exit fill price tracking to `OpenTrade` (accumulates actual exit $ proceeds), reads `filled_avg_price` from Alpaca orders, computes and prints realized P&L on every position close. Now shows: `POSITION CLOSED RRGB reason=max_loss_hit | P&L=$-700 (entry=4.9700 exit_avg=4.9000 qty=10000)`

### Fix #6: Percentage-Based Exit Limit Pricing (2026-02-26, today)
**Problem**: Fixed-cent exit offsets (`sell_limit = ref - 0.04`) were too aggressive on cheap stocks. On a $2 stock, 4 cents = 2% discount. The backtester assumes zero exit slippage, creating a systematic gap between backtest and live P&L.

**Solution**: New percentage-based env vars override fixed-cent values:
- `WB_EXIT_INITIAL_WIGGLE_PCT=0.3` (0.3% of price, ~0.6¢ on $2, ~1.5¢ on $5)
- `WB_LIMIT_OFFSET_SELL_PCT=0.1` (0.1% of price)
- `WB_EXIT_CHASE_STEP_PCT=0.2` (0.2% step when chasing)
- `WB_EXIT_MAX_CHASE_PCT=3.0` (3% max chase, vs old 20% on $2 stock)

Impact: $2 stock initial offset drops from 2.0% to 0.4%. Max chase floor drops from 20% to 3%.

---

## 6. Current Issues (Open)

### Critical: Alpaca Data Feed Quality
**Status**: Unresolved. Waiting on IBKR approval + considering Databento ($200/mo).

The live Alpaca websocket delivers stale/incomplete data compared to the historical API. Today's live session showed:
- **Live P&L: -$6,320** vs **Backtest P&L: -$848** on the same 5 stocks
- $5,472 gap attributable entirely to data feed quality
- Stale prices (5-300+ seconds without updates during open positions)
- Phantom bids (5-9% off last trade)
- Missing tick prints that the historical API provides perfectly

The backtester uses Alpaca's historical trade data (38K-64K ticks per symbol), which is clean and complete. The live websocket misses significant portions, leading to different detection states, different entry prices, and blind exit management.

**Workarounds deployed**: Quote quality gate (Fix #3), f-string crash fix (Fix #4), stale timestamp fix. These are band-aids — the fundamental issue is upstream data quality.

**Planned solutions**: Interactive Brokers (application pending) provides direct market data, L2 depth, and reliable tick streams. Databento ($200/mo) as a backup data source.

### Stale Price Near Stop Correlation
User observed that stale price warnings correlate with the stock price hitting the stop loss area. Alpaca may throttle or drop data on volatile/illiquid names at exactly the moments when accurate data matters most. This needs more investigation.

### Remaining Study Gaps (from ROSS_STUDY.md)
10 identified improvement areas, 4 rated high priority (confidence 3/5):
1. **No scaling in/out** — Bot uses all-or-nothing. Ross scales partials at every dollar level
2. **Exit too passive on parabolic strength** — Topping wicky and BE exits cut winners
3. **Detection too slow for fast PM movers** — State machine needs bars to build; can't act on first impulse
4. **Enters after move is over** — By the time patterns confirm, stock has already made its move

---

## 7. Bot Strengths Confirmed Across Studies

1. **Premarket early detection** — Beat Ross on VERO by entering at 07:03 AM
2. **Mechanical discipline** — No emotional hesitation. Held MLEC 59 min through massive chop
3. **Pattern detection accuracy** — ASC_TRIANGLE, FLAT_TOP, R2G, VOL_SURGE fire correctly on real breakouts
4. **Loss containment** — TW exits limited LCFY damage to -$1,742 vs potential -$3,000
5. **MACD gate as risk manager** — Saved from ANPA first spike (Ross lost -$11K on that spike, bot avoided it, then caught the second breakout for +$4,368)
6. **Flash spike capture** — GWAV +$6,735: BE exit on 10s bars caught the spike reversal faster than human reaction

---

## 8. Bot Weaknesses Confirmed Across Studies

1. **All-or-nothing position sizing** — No scaling. Ross enters 5K shares, adds 10K on confirmation, adds 15K on breakout. Bot enters full size or nothing
2. **No resistance/level awareness** — LCFY entered $6-$6.50 zone 3 times. ACON entered $8.50 resistance 4 times. No memory between attempts
3. **Slow detection on fast movers** — MLEC 10 min late, PAVM 2+ hrs late, TWG complete miss, MNTS 4 hrs late
4. **Breakout chase vs dip buy** — Bot enters AFTER breakout confirms ($8.22). Ross pre-positions BELOW breakout ($7.60). The $0.62 gap = $4K+ edge on ACON alone
5. **Post-halt blindness** — Circuit breakers destroy the state machine. VERO: missed $5.50 → $12.93 (135%) after halt. LCFY: missed entire $3.74 → $5.58 recovery
6. **Extended move guard kills valid setups** — MLEC 8:10 setup (6 green candles), PAVM 09:37 setup blocked. These were legitimate continuation patterns
7. **MACD lag on volatile names** — Bearish cross locked bot out of LCFY breakout 1 bar early. MACD poisoned by extreme bars on GWAV for hours

---

## 9. What's Next

### Immediate (WF2 — Live Testing)
- Deploy fixes #3-#6 in tomorrow's paper trading session
- Monitor real P&L tracking (fix #5) to get accurate live performance data
- Wait for IBKR approval or subscribe to Databento to resolve data quality

### Short-term (WF1 — Trade Studies)
- Complete remaining 14-19 trade studies (targeting 25-30 total)
- Continue identifying and refining trade profiles
- Focus on Ross's January-February 2026 recap videos for stock selection
- Looking for: more Profile A (early bird) and Profile D (flash spike) cases to confirm bot strengths, and more Profile B/C cases to understand bot weaknesses

### Medium-term (Code Improvements)
- Implement findings from completed studies — only after patterns are confirmed across 3+ cases
- Priority improvements (when ready):
  1. Scaling in/out framework
  2. Resistance level tracking
  3. Faster detection for premarket movers
  4. Dip-buy entry type alongside breakout entry
  5. Post-halt state recovery

---

## 10. How to Use This Report with Ross Cameron Video Studies

When watching Ross Cameron's daily recap videos, the most valuable data points to extract for each trade are:

1. **Stock name, date, and which recap video** (for cross-referencing)
2. **Entry price and time** — exact to the minute
3. **Position size** — how many shares, and did he scale in?
4. **Exit price and time** — partial or full exit?
5. **His stated reasoning** — what did he see on the chart? What level was he watching?
6. **Key levels mentioned** — half/whole dollars, VWAP, prior day high, etc.
7. **Whether he used L2/time & sales** to time entry
8. **Catalyst** — what news/headline drove the stock?
9. **Float and gap%** — stated in his scanner results

This data gets compared directly against the bot's backtest output for the same stock and date. The side-by-side comparison reveals exactly where the bot's logic diverges from Ross's decision-making.

### Stocks still needed for study (suggested from identified gaps):
- More **Profile A** (early bird PM ramp) examples to confirm bot strength pattern
- More **Profile C** (resistance chopper) examples to understand how to add level awareness
- Any stocks where Ross **lost money** — these show where the bot's mechanical discipline might win
- Stocks in the **$2-$5 range** — this is where the bot trades most and where pricing improvements (fix #6) matter most
