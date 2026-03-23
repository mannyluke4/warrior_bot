# Ross Exit 2026 YTD Backtest Comparison
**Generated:** 2026-03-23
**Runner:** `run_ytd_v2_backtest.py` (Top-5 ranked, 5 trades/day cap, $30K starting equity)
**Period:** Jan 2 – Mar 19, 2026 (54 trading days)

---

## Summary

| Metric | Baseline | Ross Exit (`WB_ROSS_EXIT_ENABLED=1`) | Delta |
|--------|----------|--------------------------------------|-------|
| **Final Equity** | $64,600 | $46,785 | -$17,815 |
| **Total P&L** | **+$34,600 (+115.3%)** | **+$16,785 (+56.0%)** | **-$17,815** |
| **Trades** | 38 | 28 | -10 |
| **Winners** | 20 | 13 | -7 |
| **Losers** | 18 | 14 | -4 |
| **Win Rate** | 52.6% | 46.4% | -6.2pp |
| **Avg Win** | +$2,105 | +$1,658 | -$447 |
| **Avg Loss** | -$417 | -$341 | +$76 (better) |
| **Profit Factor** | 5.61 | 4.52 | -1.09 |
| **Max Drawdown** | $2,877 | $2,176 | -$701 (better) |
| **Best Trade** | VERO +$16,966 | VERO +$13,433 | -$3,533 |
| **Worst Trade** | FUTG -$1,234 | MOVE -$823 | +$411 (better) |

**Verdict: Baseline outperforms Ross exit by $17,815 over YTD period.**

---

## The Core Problem: Ross Exit Cuts Big Runners Too Early

The signal mode's cascading BE/TW exit system allows massive runners to compound. Ross exit's 1m candle signals (CUC, doji, gravestone, shooting star) fire too early on these stocks and lock in far smaller gains.

### Head-to-Head: Same Stock, Both Runs

| Symbol | Date | Baseline | Ross Exit | Delta | Note |
|--------|------|----------|-----------|-------|------|
| ARTL | 2026-03-18 | +$9,512 | +$1,345 | **-$8,167** | Ross exit fired way early |
| ROLR | 2026-01-14 | +$4,634 | +$238 | **-$4,396** | Near-total runner destruction |
| VERO | 2026-01-16 | +$16,966 | +$13,433 | **-$3,533** | Still big but $3.5K left on table |
| SLGB | 2026-01-21 | +$4,277 | +$1,981 | **-$2,296** | Strong runner cut short |
| SER | 2026-03-19 | +$535 | +$194 | -$341 | |
| ACON | 2026-01-08 | +$553 | +$348 | -$205 | |
| WHLR | 2026-02-06 | +$98 | -$426 | -$524 | Ross exit turned winner into loser |

**Total damage from runner truncation (shared stocks): -$19,462**

### Where Ross Exit Helps

| Symbol | Date | Baseline | Ross Exit | Delta | Note |
|--------|------|----------|-----------|-------|------|
| CJMB | 2026-01-15 | +$65 | +$1,159 | **+$1,094** | Ross exit unlocked re-entry |
| BATL | 2026-01-26 | +$245 | +$963 | +$718 | |
| POLA | 2026-01-20 | +$191 | +$833 | +$642 | |
| BOXL | 2026-02-04 | -$302 | +$164 | **+$466** | Turned loser into winner |
| CYN | 2026-01-27 | -$198 | -$99 | +$99 | Smaller loss |
| RUBI | 2026-02-19 | -$168 | -$109 | +$59 | |

**Total benefit: +$3,078** — not enough to offset the runner damage.

### Trades Only in Baseline (removed by Ross exit)

Net P&L of trades only in baseline: +$507 +$502 +$136 +$59 -$14 -$62 -$267 -$320 -$561 -$625 = **-$645**
(Mostly small losers — Ross exit skipping these is neutral to slightly positive)

### Trades Only in Ross Exit (new trades added)

Net P&L: +$537 +$325 -$34 -$323 -$540 -$590 = **-$625**
(Adds winners but also adds significant new losers, net near-zero)

---

## Interpretation

### Why Ross Exit Underperforms on YTD Basis

1. **Big runners dominate YTD P&L.** Four trades (ARTL, ROLR, VERO, SLGB) account for +$35,389 of baseline's +$34,600 total — they ARE the strategy. Ross exit erases $18,392 of that.

2. **1m candle signals fire during consolidation, not reversal.** On stocks like ARTL (+$9.5K in baseline), the stock likely had doji/CUC patterns mid-run that Ross exit treated as exit signals but baseline's BE/TW system correctly ignored and held.

3. **Structural trailing stop (last green 1m low) is too tight for runners.** High-velocity small-caps have volatile 1m candles; the trailing stop ratchets up aggressively and stops out during normal pullbacks.

4. **Partial 50% doji exit breaks compounding.** Signal mode's power is full-size re-entries that compound. Ross exit's 50% partial reduces position size before the next leg begins.

5. **Ross exit does help on "normal" trades.** The +$3K improvement on CJMB/BATL/POLA/BOXL shows it has value when the stock isn't a massive runner — it locks in gains more reliably on flat/choppy movers.

---

## Recommendations

### Option A: Hybrid — Exempt Cascading Re-Entries
Keep Ross exit OFF for stocks already in a multi-R cascade (>5R open profit), let it fire normally on new entries. This would preserve the runner compounding while still benefiting from Ross exit on smaller moves.

### Option B: Raise Ross Exit Thresholds
The `WB_ROSS_CUC_MIN_R` gate already suppresses CUC exits deep in runners. Consider extending this logic to all Ross exit signals (not just CUC) once the trade reaches e.g. 5R.

### Option C: Live-Test Only
YTD backtest covers Jan–Mar 2026 which had exceptional runners (VERO, ARTL). Ross exit may be the right tool for "normal" market conditions. Leave `WB_ROSS_EXIT_ENABLED=1` in live and monitor rolling 30-day P&L vs baseline.

### Option D: Revert to Baseline
If live bot performance since 2026-03-23 (Ross exit enable date) shows similar degradation on runners, revert to signal-mode BE/TW exits.

---

## Run Commands Used

```bash
# Baseline
WB_MP_ENABLED=1 python run_ytd_v2_backtest.py

# Ross exit
WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 python run_ytd_v2_backtest.py
```

State files: `ytd_v2_backtest_state_baseline.json` (baseline), `ytd_v2_backtest_state.json` (Ross exit, current)
