# Perplexity Handoff — Pipeline Investigation Update
## 2026-03-16

**Branch**: `v6-dynamic-sizing`
**Status**: V2 backtest re-running from scratch (ETA ~4 hours), early results not promising

---

## What Happened Since Last Session

### 1. Pipeline Fixes Were Applied (from PIPELINE_FIX_DIRECTIVE)

Three fixes were made:

| Fix | What Changed | File |
|-----|-------------|------|
| Scanner OTC filter | Removed `tradable=False` and `fractionable=None` filters — was blocking VERO (OTC stock) | `scanner_sim.py` |
| sim_start override | Always use `sim_start=07:00` instead of scanner discovery time | `run_ytd_v2_backtest.py` |
| PM volume floor | Set `MIN_PM_VOLUME=0` (was 50,000) — let ranking handle it | `run_ytd_v2_backtest.py` |

All 49 dates were re-scanned. VERO now appears in Jan 16 scanner results (ranked #1 with 26.8M PM volume, 181% gap).

### 2. Pipeline Fixes Made Results WORSE (First Run)

| Metric | V2 Pre-Fix | V2 Post-Fix |
|--------|-----------|-------------|
| Config A P&L | -$7,450 | -$13,075 |
| Config B P&L | -$7,450 | -$13,419 |
| Config A Trades | 47 | 79 |

Removing the PM volume floor let more junk candidates through (118 passed filter vs 19 before). More candidates = more bad trades.

### 3. The State File Was Stale — VERO DOES Work

**Critical discovery**: Running VERO directly through simulate.py produces **+$6,875** (risk=$750) or **+$5,930** (risk=$647). The V2 state file showed 0 VERO trades because it was generated from an older code version or scanner data.

Similarly:
- **ROLR Jan 14**: +$1,992 (2 trades, both winners) — works with current code
- **BNAI Jan 14**: -$66 (3 trades, break-even) — was +$4,907 in 2-week test, now break-even
- **GWAV Jan 16**: 0 trades — Arms and signals but entry blocked by notional cap (see below)

### 4. GWAV Mystery Solved

GWAV on Jan 16 arms at 07:05 with entry=$5.41, stop=$5.37, **R=$0.04**. With $750 risk:
- Shares = $750 / $0.04 = 18,750
- Notional = 18,750 × $5.41 = **$101,437**
- MAX_NOTIONAL = $50,000 → **entry blocked**

The stop is too tight ($0.04) — the micro-pullback detector is finding a valid pattern but the R distance is microscopic. In the 2-week backtest, GWAV had a different entry/stop (entry=$5.49 with a wider stop) and produced +$7,713 on trade 1. **The code has changed since the 2-week test was run.**

---

## Fresh V2 Re-Run In Progress

Deleted the stale state file and kicked off a completely fresh V2 run with current code + fixed scanner data. Running in background (PID 12655).

**Early results (9/49 days done) — not good:**
```
Jan 02: A: -$787  eq=$29,213 | B: -$787  eq=$29,213
Jan 05: A: -$365  eq=$28,848 | B: -$365  eq=$28,848
Jan 06: A: -$721  eq=$28,127 | B: -$833  eq=$28,015
Jan 07: A: -$896  eq=$27,231 | B: -$892  eq=$27,123
Jan 08: A: -$694  eq=$26,537 | B: -$692  eq=$26,431
Jan 09: A: $+0    eq=$26,537 | B: -$660  eq=$25,771
Jan 12: A: +$34   eq=$26,571 | B: +$32   eq=$25,803
```

Down -$3,429 (A) in 8 trading days. Jan 14 (ROLR +$1,992) and Jan 16 (VERO +$5,930) are coming up, so we'll see if those winners change the trajectory.

---

## The Core Problem: Every Micro-Pullback Is a "Good Setup"

This is the most important finding. Analysis of the 79 trades from the previous V2 run:

### Trade Quality Distribution (Config A)
```
R-Multiple Distribution:
          <=-1.0R:  20 ████████████████████    (25% — full stop hits)
    -1.0 to -0.5R:  17 █████████████████       (22%)
       -0.5 to 0R:  22 ██████████████████████  (28% — small losers)
               0R:   4 ████                     (5%)
       0 to +0.5R:   7 ███████                 (9%)
    +0.5 to +1.0R:   5 █████                   (6%)
           >+1.0R:   4 ████                     (5% — no big winners)
```

### Key Stats
| Metric | Value |
|--------|-------|
| Win Rate | 22% |
| Best Winner | +$752 (+1.2R) |
| Worst Loser | -$994 (-2.1R) |
| Avg R-Multiple | -0.3R |
| Score Range | 8.0 - 12.5 (avg 11.3) |

### The Asymmetry Problem

The bot's edge is supposed to come from **catching 3R-10R winners** on 30-40% of trades (Ross Cameron's model). Instead:
- **Only 4 of 79 trades (5%) exceeded +1.0R** — and the best was only +1.3R
- **37 of 79 trades (47%) lost -0.5R or worse**
- **The bot exits winners too early** via bearish_engulfing (33 trades) and topping_wicky (24 trades) — these exit signals fire on small moves (+0.2R) before the stock can run

### Why VERO Works But Most Don't

VERO on Jan 16 is the model trade:
- Clean impulse move (gap 181%, 26.8M PM volume)
- Meaningful R distance ($0.12 — not microscopic)
- Entry at $3.58, rides to $4.68 — **+9.2R**
- The continuation hold keeps the position through minor pullbacks

Most other trades:
- Weak impulse (5-20% gap)
- Tiny R distance ($0.08-$0.15)
- Stock doesn't have follow-through momentum
- Bearish engulfing or topping wicky fires at +0.2R → exit with tiny gain or small loss
- If no exit signal fires, rides to stop → -1.0R

### The Scoring System Doesn't Differentiate

The entry score (8.0-12.5) comes primarily from MACD alignment, not from the quality of the momentum. A 12.5-score setup on a stock drifting sideways at +6% gap looks the same to the detector as a 12.5-score setup on VERO ripping +181%.

**The detector finds valid micro-pullback patterns on ALL of these stocks.** The problem is that most small-cap gap-ups don't have the follow-through momentum to produce a multi-R winner. The detector can't tell the difference between a stock that's about to fade back to VWAP and one that's about to 3x.

---

## Exit Analysis

| Exit Reason | Count | Total P&L | Avg P&L |
|------------|-------|-----------|---------|
| bearish_engulfing_exit_full | 33 | -$3,500 | -$106 |
| topping_wicky_exit_full | 24 | +$1,678 | +$70 |
| stop_hit | 18 | -$9,483 | -$527 |
| 5m_trend_guard_exit | 2 | -$232 | -$116 |
| max_loss_hit | 2 | -$1,538 | -$769 |

**Bearish engulfing is the biggest problem** — 33 trades, net -$3,500. It's triggering on normal volatility in small-cap stocks. These stocks ALWAYS have wicky, engulfing candles on the way up. The exit signal is too sensitive for this asset class.

**Stop hits are the most expensive** — 18 trades at -$527 average. These are trades where the setup completely fails (no momentum at all).

---

## Questions for Perplexity

1. **How does Ross Cameron actually filter his watchlist?** He doesn't trade every gap-up with a micro-pullback. What's the qualitative filter he applies that we're missing? Is it relative volume vs average? Is it the quality of the premarket chart pattern? News catalyst type?

2. **Should we be looking at the 1-minute impulse strength as a filter?** If the first impulse bar is weak (small body, low volume), maybe that's not a real setup. VERO's impulse was massive — $3.52 to $5+. Most of these losers probably had tiny impulse bars.

3. **Is the bearish engulfing exit too aggressive for small-caps?** On $50+ stocks, a bearish engulfing candle is meaningful. On a $3 stock with 0.01 tick size, you get engulfing candles constantly. Should the exit require a minimum candle body size relative to the stock's ATR or recent range?

4. **The 2-week backtest used an older code version.** The micro-pullback detector has been modified since then (simplification directive removed profiles, changed classifier behavior). Is it possible the simplification broke something? Specifically, GWAV now finds entry=$5.41/stop=$5.37 (R=$0.04) instead of the 2-week test's entry=$5.49 with a wider stop. What changed in the detector?

5. **Should we add a minimum R-distance filter?** If R < $0.10 (or R < 1% of entry price), the position size becomes enormous and the setup is probably just noise. This would have blocked GWAV's bad entry and likely many other micro-setups on stocks going nowhere.

---

## What's Running / Next Steps

1. **V2 re-run in progress** — 49 dates, fresh from scratch. Will capture VERO (+$5,930) and ROLR (+$1,992). If still deeply negative after including these winners, the problem isn't the pipeline — it's the trade selection quality.

2. **If V2 re-run still fails**: The strategy works on curated stocks (2-week test: +$13,518). It fails on automatically selected stocks. The gap is NOT the scanner (it finds the right stocks) — it's that the detector trades EVERYTHING instead of waiting for the best setups.

3. **Potential filters to investigate**:
   - Minimum R distance (e.g., R > $0.10 or R > 1% of entry)
   - Minimum impulse bar strength (volume and/or body size)
   - Relative volume vs 10-day average (not just absolute PM volume)
   - Gap quality (clean gap-up vs choppy drift-up)

---

## Commits This Session

- `a599b8e` — Pipeline fixes + V2 re-run: remove OTC/fractionable filters, sim_start=07:00, no PM vol floor
- Previous: `d49f2ae` — YTD backtest V1 analysis
- Previous: `ca09a33` — YTD V2 backtest: top-5 ranked + trade cap

---

*Generated from pipeline investigation session | Branch: v6-dynamic-sizing*
