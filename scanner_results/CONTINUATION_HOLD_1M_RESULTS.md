# Continuation Hold — 1-Minute Exit Resolution Results
## Generated 2026-03-13

---

## Overview

Tests whether switching continuation hold trades to 1-minute bar exit detection (instead of suppressing individual 10-second signals) captures more of the available move.

### Configuration
```
WB_CONTINUATION_HOLD_ENABLED=1
WB_CONT_HOLD_USE_1M_EXITS=1
WB_CONT_HOLD_MIN_VOL_DOM=2.0
WB_CONT_HOLD_MIN_SCORE=8.0
WB_CONT_HOLD_MAX_LOSS_R=0.5
WB_CONT_HOLD_CUTOFF_HOUR=10
WB_CONT_HOLD_CUTOFF_MIN=30
```

### Sizing
- Risk: $750, Max notional: $10,000, Max shares: 3,000

---

## Results: 3-Way Comparison

| Metric | Baseline (no hold) | 10s Hold (max_holds=2) | 1m Exit Resolution |
|--------|-------------------|----------------------|-------------------|
| Total P&L | **-$1,928** | **-$1,131** | **-$1,196** |
| Delta vs baseline | — | +$797 | +$732 |
| Trades changed | — | 4 improved, 0 worsened | 3 improved, 1 worsened |

**10s hold is the better approach overall** (-$1,131 vs -$1,196).

---

## Per-Trade Comparison

| Symbol | Date | Score | Baseline | 10s Hold | 1m Exit | Notes |
|--------|------|-------|----------|----------|---------|-------|
| BNAI | 2026-01-14 | 12.5 | $0 | +$554 | **+$631** | 1m captured more (+$77 vs 10s) |
| NCI | 2026-02-20 | 12.0 | +$101 | +$274 | +$245 | 1m slightly worse (-$29 vs 10s) |
| HIMZ | 2026-02-05 | 9.0 | +$19 | +$75 | **-$38** | 1m held too long, stock reversed |
| GNPX | 2025-11-05 | 12.5 | +$15 | +$29 | +$29 | Same as 10s hold |
| YIBO | 2025-01-27 | 11.0 | -$12 | -$12 | -$12 | After 10:30 cutoff, unchanged |
| IPST | 2025-11-05 | 7.0 | +$331 | +$331 | +$331 | Score < 8, not eligible |
| BOLT | 2026-01-14 | 5.0 | +$38 | +$38 | +$38 | Score < 8, not eligible |
| SPHL | 2026-01-15 | 10.5 | -$183 | -$183 | -$183 | Vol dom < 2.0 |
| CRMX | 2026-02-03 | 12.5 | -$172 | -$172 | -$172 | Vol dom < 2.0 |
| HYPD | 2025-11-05 | 5.5 | -$466 | -$466 | -$466 | Score < 8, vol dom < 2.0 |
| SLMT | 2025-11-05 | 5.5 | -$528 | -$528 | -$528 | Score < 8, vol dom < 2.0 |
| TWAV | 2025-12-08 | 11.5 | -$347 | -$347 | -$347 | Vol dom < 2.0 |
| UONE | 2026-02-12 | 10.0 | -$467 | -$467 | -$467 | Vol dom < 2.0 |
| CGTL | 2026-02-12 | 5.5 | -$257 | -$257 | -$257 | Vol dom < 2.0 |
| INBS | 2026-02-05 | 5.5 | $0 | $0 | $0 | Score < 8 |

---

## Analysis

### Why 1m exits helped BNAI more
BNAI had 4.9x vol dominance — extreme institutional interest. The stock continued to grind higher through minor pullbacks that triggered 10s BE signals. With 1m exits, those micro-pullbacks didn't register as bearish engulfing at the 1-minute level, allowing the trade to hold through to a larger gain.

### Why 1m exits hurt HIMZ
HIMZ had 3.7x vol dom and score 9.0 — right at the qualification thresholds. The stock had a genuine reversal that showed clearly on 10-second bars but took a full minute to confirm on 1m bars. By the time the 1m BE fired, the stock had already given back the profit and was in the red (-$38). The 10s hold approach (max 2 suppressions) exited sooner with +$75.

### Key Insight
**The 1m approach is too aggressive for stocks near the qualification thresholds.** It works well for extreme cases (BNAI at 4.9x vol dom) but over-holds borderline cases (HIMZ at 3.7x). The 10s counter approach provides a gentler buffer — it gives the stock 2 chances to prove itself but doesn't commit to ignoring all micro-level signals.

---

## Recommendation

**Keep the 10s hold (max_holds=2) as the default.** It produces:
- Better overall P&L: -$1,131 vs -$1,196
- No trades turned from winners to losers
- Simpler logic, fewer edge cases

The 1m exit mode (`WB_CONT_HOLD_USE_1M_EXITS=1`) is available as an option but should remain OFF by default. It may be worth revisiting if the vol_dom threshold is raised (e.g., 4.0x instead of 2.0x) to limit it to the highest-conviction cases.

---

*Generated from 15-date continuous scan backtest | Tick mode, Alpaca feed, realistic sizing ($750 risk, $10K max notional)*
