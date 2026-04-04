# Session Report: Box Strategy Build + Ship (April 3, 2026)

**Author:** CC (Claude Code)
**Session:** ~4 hours, market holiday
**Branch:** v2-ibkr-migration

---

## What We Built

Took the box strategy from concept to live-ready in one session. Five phases completed:

### Phase 1: Box Scanner V2 (Multi-Day)
- Rewrote `box_scanner.py` — replaced single-morning HOD/LOD with 5-day multi-day range detection
- 30D daily bars from IBKR, split level test counting (resistance via bar.high, support via bar.low)
- Filters: SMA slope < 5%, no gaps > 5%, ADR utilization inverted (want quiet stocks), VWAP proximity
- Stock universe: ~106 liquid tickers (hardcoded fallback, IBKR HOT_BY_VOLUME for live)
- **YTD scan**: 65 dates (Jan 2 - Apr 2), 664 candidates, ~10/day average
- Results in `scanner_results_box/`, review report in `scanner_results_box/YTD_REVIEW_REPORT.md`

### Phase 2: Strategy + Backtest
- Built `box_strategy.py` — BoxStrategyEngine with RSI(14) + reversal confirmation entry, buy zone (bottom 25%), sell zone (top 25%), hard stop, trail, time stop 3:45 PM
- Built `box_backtest.py` — per-candidate backtester, pulls 1m bars from IBKR, caches to `box_backtest_cache/`
- **Baseline results**: 160 trades, +$8,717, 62.5% WR, $54.48 avg/trade
- **Key finding**: 156/160 exits were time stops — stock enters buy zone and drifts toward mid-box but rarely reaches sell zone same-day

### Phase 2B: Exit Optimization + Filter Tightening
Built `box_optimize.py` to test 4 exit variants × 3 filter sets.

**Exit Variant Comparison (all 661 candidates):**

| Variant | Trades | P&L | WR | Avg/Trade | PF |
|---------|--------|-----|----|-----------|----|
| A: Baseline (sell zone) | 160 | $8,717 | 62.5% | $54.48 | 3.19 |
| B: VWAP exit | 179 | $8,363 | 74.9% | $46.72 | 3.63 |
| **C: Mid-Box exit** | **161** | **$9,385** | **64.0%** | **$58.29** | **3.45** |
| D: Tiered (75% VWAP, 25% trail) | 258 | $7,824 | 76.7% | $30.32 | 3.46 |

**Winner: Mid-Box** — highest total P&L and avg P&L/trade.

**Filter Set Comparison (using mid-box exit):**

| Filter | Trades | P&L | WR | Avg/Trade | PF | Consistency |
|--------|--------|-----|----|-----------|----|-------------|
| Baseline (all) | 161 | $9,385 | 64% | $58.29 | 3.45 | 70% |
| Proven Box | 67 | $4,673 | 71.6% | $69.75 | — | — |
| High Conviction | 8 | $1,314 | 87.5% | $164.22 | — | — |
| **Vol Sweet Spot** | **56** | **$4,169** | **75.0%** | **$74.45** | **5.07** | **74%** |

**Winner: Vol Sweet Spot** — best balance of win rate, avg P&L, and consistency.

Vol Sweet Spot filters: range 2-6%, total tests >= 5, price >= $15, ADR util < 0.80, skip Fridays.

### Phase 3: Ship to Live Bot
- Wired box into `bot_v3_hybrid.py` with complete separation from momentum:
  - Own position slot (`state.box_position`), bar builder, scanner, entry/exit functions
  - Box window: 10:00 AM - 3:45 PM ET (momentum is 7:00 AM - 12:00 PM ET)
  - Momentum always has priority — box blocked when momentum has open position
  - `WB_BOX_SIMULTANEOUS=0` prevents both strategies holding positions at once
  - Scanner fires at 10:00 and 11:00 AM with Vol Sweet Spot filter applied
  - Midbox exit, $500 session loss cap, hard close 3:45 PM, skip Fridays
- Gated by `WB_BOX_ENABLED` (now set to `1` in .env)
- Regression verified: VERO $21,024, ROLR $53,979 (unchanged with box OFF)

### Bonus: Scaling Notional
- Added `WB_SCALE_NOTIONAL=1` — MAX_NOTIONAL = max(base $100K, equity × 2)
- Notional grows with the account, like how Ross sizes up as equity increases
- **Backtest impact**: $100K start → $928K (+828%) with scaling vs $395K (+295%) without
- Now enabled in .env for live trading

---

## Key Backtest Scenarios Run

| Scenario | Start | End Equity | Return | Trades | WR |
|----------|-------|-----------|--------|--------|----|
| Phase 2 baseline (box only) | — | +$8,717 | — | 160 | 62.5% |
| Phase 2B best config (box only) | — | +$4,169 | — | 56 | 75.0% |
| PDT $20K → unlock box at $25K | $20K | $132K | +562% | 57 | 66% |
| Ross comp $100K, $200K cap, box | $100K | $395K | +295% | 70 | 69% |
| Ross comp $100K, scaling notional, box | $100K | $928K | +828% | 62 | 72% |
| $30K, scaling notional, no box | $30K | $283K | +843% | 45 | 59% |

---

## What's Live on Mac Mini (.env)

```
WB_BOX_ENABLED=1                   # Box strategy ON
WB_SCALE_NOTIONAL=1                # Notional scales with equity
WB_BOX_MID_EXIT_ENABLED=1          # Midbox exit (Phase 2B winner)
WB_BOX_SKIP_FRIDAY=1               # Skip Fridays (negative EV)
WB_BOX_MAX_LOSS_SESSION=500        # $500 daily box loss cap
WB_BOX_SIMULTANEOUS=0              # No simultaneous positions
```

---

## Files Added/Modified

| File | Status | Purpose |
|------|--------|---------|
| `box_scanner.py` | Modified | V2 multi-day range scanner |
| `box_strategy.py` | New | Mean-reversion entry/exit engine |
| `box_backtest.py` | New | Per-candidate YTD backtester |
| `box_optimize.py` | New | Exit variant + filter comparison runner |
| `run_box_scanner_ytd.py` | Modified | Fixed adr_util key mismatch |
| `run_backtest_v2.py` | Modified | Added --box-after-pdt, --scale-notional |
| `bot_v3_hybrid.py` | Modified | Box integration + WB_SCALE_NOTIONAL |
| `scanner_results_box/` | New | 65 days of scanner results |
| `box_backtest_results/` | New | All variant/filter CSVs + reports |
| `box_backtest_cache/` | New (not committed) | Cached 1m bars from IBKR |

---

## Monday Plan

- Cron fires at 2 AM MT as usual → IBC starts gateway → bot launches
- Box scanner activates at 10:00 AM ET (8:00 AM MT)
- Watch for `[BOX]` log lines — scanner results, engine init, entries/exits
- Scaling notional active — sizing grows with account equity
- Manny will be monitoring from ~4:45 AM MT

---

## Correlation Insights (for future tuning)

From Phase 2 backtest correlation analysis:
- **low_tests** (ρ = +0.28) — strongest predictor of box P&L. More support tests = better.
- **range_pct** (ρ = -0.18) — tighter ranges outperform. 2-4% range = 83% WR, $125/trade.
- **box_score** (ρ = -0.13) — current scoring formula needs reweighting (higher score ≠ better P&L).
- **Fridays** — nearly zero EV ($4 avg). Correctly filtered out.
- **Price $30+** — better performance than sub-$30 stocks.
- **ADR util < 0.5** — quieter stocks produce $77-115/trade avg.

---

*Report by CC (Claude Code). All code pushed to v2-ibkr-migration.*
