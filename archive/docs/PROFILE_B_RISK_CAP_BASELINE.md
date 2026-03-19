# Profile B Risk Cap Baseline — V6.2
**Date:** 2026-03-10
**Branch:** v6-dynamic-sizing

## The Problem
Profile B stocks (float 5-10M) always score float_score=0 in SQS. They can reach SQS>=5 via
PM volume + gap alone, landing in Tier A ($750 risk) — same as micro-float Profile A. Wrong.

## Evidence (V6.1 Oct-Feb backtest)
- Tier A Profile B trades: 2 active, both losers = **-$2,598**
  - CRWG 2025-11-11: -$1,572 at $750 risk
  - IONZ 2025-11-14: -$1,026 at $750 risk
- Tier B Profile B trades: 2 active (1W/1L) = **+$138**

## The Fix
```python
# run_backtest_v4.py (after compute_sqs)
if profile == 'B' and risk > 250:
    risk = 250

# trade_manager.py (in calculate_dynamic_risk)
if profile == 'B' and os.getenv("WB_PROFILE_B_RISK_CAP", "1") == "1":
    risk = min(risk, 250)
```

## Spot Check Results
- CRWG 2025-11-11: $750 → $250 risk | P&L: -$1,572 → **-$262** (saved $1,310)
- Profile B $40K equity: still $250 (cap holds regardless of equity level)
- Profile A $30K: still $750 (unchanged)

## Expected Full Backtest Impact
- Profile B savings: ~+$1,732 (from -$2,598 to ~-$728)
- V6.1 combined: +$5,425 → V6.2 projected: ~+$7,157
- Max drawdown should shrink significantly (CRWG/IONZ drove the Nov drawdown)

## Toggle
WB_PROFILE_B_RISK_CAP=1 (default ON — cap active)
WB_PROFILE_B_RISK_CAP=0 (disable — old V6.1 behavior)
