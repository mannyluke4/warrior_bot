# Realistic Equity Curve Backtest — January 2026

## Configuration
- Starting equity: $30,000
- Risk per trade: $750
- Max notional: $10,000
- Max shares: 3,000
- Entry mode: pullback
- Quality gates: ON
- Window: 07:00 - 12:00 ET
- Buying power: 4x equity (PDT margin)

## A. Daily Equity Table

| Day | Date | Starting Equity | Symbols | Trades | Wins | Losses | Day P&L | Ending Equity |
|-----|------|----------------|---------|--------|------|--------|---------|---------------|
| 1 | 2026-01-05 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |
| 2 | 2026-01-06 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |
| 3 | 2026-01-07 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |
| 4 | 2026-01-08 | $30,000 | 6 | 0 | 0 | 0 | $+0 | $30,000 |
| 5 | 2026-01-09 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |
| 6 | 2026-01-12 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |
| 7 | 2026-01-13 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |
| 8 | 2026-01-16 | $30,000 | 8 | 0 | 0 | 0 | $+0 | $30,000 |

## B. Trade Log

| # | Date | Symbol | Entry | Stop | R | Exit | Reason | P&L | R-Mult |
|---|------|--------|-------|------|---|------|--------|-----|--------|

## C. Gate Activity

### 2026-01-05
```
QUALITY_GATE symbol=QBTZ gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=QBTZ gate=clean_pullback result=SKIP reason=zero_impulse_range
QUALITY_GATE symbol=QBTZ gate=impulse_strength result=FAIL reason=impulse_0.0pct_<_min_2.0pct
QUALITY_GATE symbol=QBTZ gate=volume_dominance result=PASS vol_ratio=0.6x_recent_vs_avg
QUALITY_GATE symbol=QBTZ gate=price_float result=PASS price=7.98
```

### 2026-01-06
```
QUALITY_GATE symbol=ELAB gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=ELAB gate=clean_pullback result=FAIL reason=pb_vol_107pct_>_max_70pct
QUALITY_GATE symbol=ELAB gate=impulse_strength result=FAIL reason=impulse_vol_0.8x_<_min_1.5x
QUALITY_GATE symbol=ELAB gate=volume_dominance result=PASS vol_ratio=1.0x_recent_vs_avg
QUALITY_GATE symbol=ELAB gate=price_float result=PASS price=11.73
```

### 2026-01-07
```
QUALITY_GATE symbol=BENF gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=BENF gate=clean_pullback result=SKIP reason=zero_impulse_range
QUALITY_GATE symbol=BENF gate=impulse_strength result=FAIL reason=impulse_0.0pct_<_min_2.0pct
QUALITY_GATE symbol=BENF gate=volume_dominance result=PASS vol_ratio=1.0x_recent_vs_avg
QUALITY_GATE symbol=BENF gate=price_float result=PASS price=5.86
```

### 2026-01-08
```
QUALITY_GATE symbol=SXTC gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=SXTC gate=clean_pullback result=FAIL reason=retrace_114pct_>_max_65pct
QUALITY_GATE symbol=SXTC gate=impulse_strength result=PASS impulse=10.1pct vol=5.2x_avg
QUALITY_GATE symbol=SXTC gate=volume_dominance result=PASS vol_ratio=3.3x_recent_vs_avg
QUALITY_GATE symbol=SXTC gate=price_float result=PASS price=3.54
QUALITY_GATE symbol=ROLR gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=ROLR gate=clean_pullback result=SKIP reason=zero_impulse_range
QUALITY_GATE symbol=ROLR gate=impulse_strength result=FAIL reason=impulse_0.0pct_<_min_2.0pct
QUALITY_GATE symbol=ROLR gate=volume_dominance result=PASS vol_ratio=0.7x_recent_vs_avg
QUALITY_GATE symbol=ROLR gate=price_float result=REDUCE reason=price_2.67_outside_3.0-15.0_sweet_spot size_mult=0.5
QUALITY_GATE symbol=ROLR gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=ROLR gate=clean_pullback result=FAIL reason=pb_vol_192pct_>_max_70pct
QUALITY_GATE symbol=ROLR gate=impulse_strength result=FAIL reason=impulse_vol_1.1x_<_min_1.5x
QUALITY_GATE symbol=ROLR gate=volume_dominance result=PASS vol_ratio=1.9x_recent_vs_avg
QUALITY_GATE symbol=ROLR gate=price_float result=PASS price=3.03
QUALITY_GATE symbol=MNTS gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=MNTS gate=clean_pullback result=SKIP reason=zero_impulse_range
QUALITY_GATE symbol=MNTS gate=impulse_strength result=FAIL reason=impulse_0.0pct_<_min_2.0pct
QUALITY_GATE symbol=MNTS gate=volume_dominance result=PASS vol_ratio=0.5x_recent_vs_avg
QUALITY_GATE symbol=MNTS gate=price_float result=REDUCE reason=price_15.35_outside_3.0-15.0_sweet_spot size_mult=0.5
```

### 2026-01-09
```
QUALITY_GATE symbol=ATRA gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=ATRA gate=clean_pullback result=FAIL reason=retrace_107pct_>_max_65pct
QUALITY_GATE symbol=ATRA gate=impulse_strength result=FAIL reason=impulse_1.6pct_<_min_2.0pct
QUALITY_GATE symbol=ATRA gate=volume_dominance result=WARN reason=fading_volume_0.4x_recent_vs_avg
QUALITY_GATE symbol=ATRA gate=price_float result=PASS price=14.95
QUALITY_GATE symbol=SOBR gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=SOBR gate=clean_pullback result=SKIP reason=zero_impulse_range
QUALITY_GATE symbol=SOBR gate=impulse_strength result=FAIL reason=impulse_0.0pct_<_min_2.0pct
QUALITY_GATE symbol=SOBR gate=volume_dominance result=PASS vol_ratio=1.0x_recent_vs_avg
QUALITY_GATE symbol=SOBR gate=price_float result=REDUCE reason=price_2.16_outside_3.0-15.0_sweet_spot size_mult=0.5
```

### 2026-01-12
```
QUALITY_GATE symbol=ATRA gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=ATRA gate=clean_pullback result=PASS retrace=44pct vol_ratio=63pct candles=1
QUALITY_GATE symbol=ATRA gate=impulse_strength result=PASS impulse=2.5pct vol=1.9x_avg
QUALITY_GATE symbol=ATRA gate=volume_dominance result=PASS vol_ratio=0.7x_recent_vs_avg
QUALITY_GATE symbol=ATRA gate=price_float result=PASS price=6.43
```

### 2026-01-13
```
QUALITY_GATE symbol=FIGG gate=no_reentry result=PASS losses=0/1 trades=0/10
QUALITY_GATE symbol=FIGG gate=clean_pullback result=SKIP reason=zero_impulse_range
QUALITY_GATE symbol=FIGG gate=impulse_strength result=FAIL reason=impulse_0.0pct_<_min_2.0pct
QUALITY_GATE symbol=FIGG gate=volume_dominance result=PASS vol_ratio=1.2x_recent_vs_avg
QUALITY_GATE symbol=FIGG gate=price_float result=PASS price=4.36
```

## D. Equity Curve Summary

```
Starting equity:  $30,000
Ending equity:    $30,000
Total P&L:        $+0
Total trades:     0
Win rate:         0%
Avg daily P&L:    $+0
Best day:         $+0 (2026-01-05)
Worst day:        $+0 (2026-01-05)
Days with trades: 0/8
Max drawdown:     -$0 (from peak)
```

## E. Position Sizing Verification

See individual trade reports above. Position sizes constrained by:
- Risk: $750/R → qty_risk = 750/R
- Notional cap: $10,000 → qty_notional = 10000/price
- Max shares: 3,000
- Buying power: 4x equity (starts at $120,000)

---
*Generated by run_equity_curve.py | 8 trading days*