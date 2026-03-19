# V3 Directive — Stock Quality Score & Tiered Risk

**Date:** 2026-03-09  
**From:** Luke + Perplexity Analysis  
**To:** Duffy (Claude Code / IronClaw)  
**Branch:** `scanner-sim-backtest`  
**Backtest scope:** Same Jan 2 – Feb 27 dataset (re-run all 38 days)

---

## Executive Summary

The V2 backtest revealed two critical insights:

1. **The kill switch blocked GWAV (+$6,735) on Jan 16** because candidates were sorted by gap% descending. GWAV had only 10.3% gap but 1.5M PM volume — by far the most liquid stock that day. It was ranked 24th and never got to trade.

2. **The bot's scoring system is inverted.** The current "score" (3–12.5) measures chart patterns (MACD, bull structure, vol surge, R2G) — these are entry/exit signals, not stock quality indicators. Meanwhile, the actual stock quality factors (PM volume, float, liquidity) have zero influence on position sizing. Every trade risks a flat $1,000 regardless of whether the stock is a liquid runner or a ghost town.

This directive introduces a **two-layer architecture** that separates stock selection (how much to risk) from trade execution (when to enter/exit).

---

## The Two-Layer Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: STOCK QUALITY SCORE (SQS)                             │
│  Where: Orchestrator (run_backtest_v3.py / scanner_sim.py)      │
│  When: BEFORE the sim runs                                      │
│  Purpose: Determines HOW MUCH to risk on this stock             │
│  Inputs: PM volume, gap%, float                                 │
│  Output: Risk tier → $1000 / $500 / $250 / $0 (skip)          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 2: SIGNAL SCORE (existing)                               │
│  Where: simulate.py (unchanged)                                 │
│  When: DURING the sim, at each candle                           │
│  Purpose: Determines WHETHER to enter and WHEN to exit          │
│  Inputs: MACD, bull structure, vol surge, R2G, R-value, VWAP   │
│  Output: Entry signals, exit signals (unchanged behavior)       │
└─────────────────────────────────────────────────────────────────┘
```

**Layer 2 (signal score) does NOT change.** All entry/exit logic in simulate.py stays exactly as-is. The min_score gate, MACD gate, VWAP checks, all exit signals — untouched.

**Layer 1 (stock quality score) is NEW.** It runs in the orchestrator before calling simulate.py, and passes the appropriate `--risk` value based on stock quality.

---

## Change 1: Candidate Sort Order — PM Volume Descending

### File: `run_backtest_v3.py` (and live `scanner_sim.py`)

### Current (V2):
```python
profile_a.sort(key=lambda x: x['gap_pct'], reverse=True)
profile_b.sort(key=lambda x: x['gap_pct'], reverse=True)
```

### New (V3):
```python
profile_a.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
profile_b.sort(key=lambda x: x.get('pm_volume', 0), reverse=True)
```

### Why:
- PM volume is the strongest predictor of stock quality in V2 data
- Winners had 10x higher median PM volume than big losers
- GWAV (1.5M PM vol) would have been candidate #1 instead of #24
- Aligns with Ross Cameron: relative volume is his #1 indicator
- Ensures the kill switch protects profits from liquid winners rather than blocking them after ghost-town losers drain the budget

---

## Change 2: Stock Quality Score (SQS) — Tiered Risk Sizing

### File: `run_backtest_v3.py` (new function, called before each sim)

### SQS Calculation

The SQS uses three pre-trade factors, each scored 0–3 points (max 9):

| Factor | 0 pts | 1 pt | 2 pts | 3 pts |
|--------|-------|------|-------|-------|
| **PM Volume** | < 1,000 | 1,000–49,999 | 50,000–499,999 | ≥ 500,000 |
| **Gap %** | < 10% | 10–19.9% | 20–39.9% | ≥ 40% |
| **Float** | > 5M or unknown | 2–5M | 0.5–1.99M | < 0.5M |

### Implementation:

```python
def compute_sqs(candidate: dict) -> tuple[int, int]:
    """
    Compute Stock Quality Score and return (sqs, risk_dollars).
    
    Args:
        candidate: dict with keys pm_volume, gap_pct, float_millions
    
    Returns:
        (sqs_score, risk_dollars) where risk is 1000/500/250/0
    """
    pm_vol = candidate.get('pm_volume', 0) or 0
    gap = candidate.get('gap_pct', 0) or 0
    flt = candidate.get('float_millions')
    
    # PM Volume score (0-3)
    if pm_vol >= 500_000:
        pm_score = 3
    elif pm_vol >= 50_000:
        pm_score = 2
    elif pm_vol >= 1_000:
        pm_score = 1
    else:
        pm_score = 0
    
    # Gap % score (0-3)
    if gap >= 40:
        gap_score = 3
    elif gap >= 20:
        gap_score = 2
    elif gap >= 10:
        gap_score = 1
    else:
        gap_score = 0
    
    # Float score (0-3)
    if flt is None or flt > 5.0:
        float_score = 0
    elif flt > 2.0:
        float_score = 1
    elif flt >= 0.5:
        float_score = 2
    else:
        float_score = 3
    
    sqs = pm_score + gap_score + float_score
    
    # Tier mapping
    if sqs >= 7:
        risk = 1000
    elif sqs >= 5:
        risk = 500
    elif sqs >= 3:
        risk = 250
    else:
        risk = 0  # skip
    
    return sqs, risk
```

### Tier Mapping:

| SQS Range | Tier | Risk | Description |
|-----------|------|------|-------------|
| 7–9 | **A+ (Full)** | $1,000 | High-quality: liquid, gapping, low float |
| 5–6 | **B (Half)** | $500 | Moderate quality: some signals but not all |
| 3–4 | **C (Quarter)** | $250 | Low quality: thin, weak gap, or large float |
| 0–2 | **Skip** | $0 | Ghost town — do not trade |

### Integration with Orchestrator:

In the candidate processing loop, BEFORE calling simulate.py:

```python
for c in all_candidates:
    sym = c['symbol']
    profile = c['profile']
    sim_start = c.get('sim_start', '07:00')
    
    # NEW: Compute Stock Quality Score
    sqs, risk = compute_sqs(c)
    
    if risk == 0:
        print(f"  SQS SKIP {sym} (SQS={sqs}, pm_vol={c.get('pm_volume',0):.0f})")
        continue
    
    # Check kill switch (unchanged)
    if session.should_stop():
        ...
    
    # Build simulate.py command — NOW WITH DYNAMIC RISK
    if profile == "B":
        cmd = f"timeout 180 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --feed databento --l2 --no-fundamentals --risk {risk}"
    else:
        cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile A --ticks --no-fundamentals --risk {risk}"
```

### What This Changes in simulate.py:

**Nothing.** The `--risk` flag already exists and works. When `--risk 500` is passed:
- `risk_dollars` is set to 500
- Position sizing: `qty = floor(500 / R)` instead of `floor(1000 / R)`
- All entry/exit logic, signal scoring, MACD gate, etc. — completely unchanged
- The bot simply takes a smaller position on lower-quality stocks

---

## Change 3: SQS Logging in Output

### File: `run_backtest_v3.py`

Add SQS and risk tier to the orchestrator log for each candidate:

```
  RUN  GWAV profile=A start=07:00 SQS=9(A+) risk=$1000 pm_vol=1,537,606 gap=10.3% float=0.80M
  RUN  MLEC profile=A start=07:00 SQS=5(B)  risk=$500  pm_vol=29,541 gap=30.1% float=0.70M  
  RUN  JL   profile=A start=07:00 SQS=4(C)  risk=$250  pm_vol=5,027 gap=14.3% float=1.24M
```

Also include in the stats JSON:
```python
stats['sim_details'].append((date, sym, profile, pnl, sqs, risk))
```

And in the final report:
```python
# Per-sim detail with SQS
for date, sym, prof, pnl, sqs, risk in stats['sim_details']:
    tier = {1000: "A+", 500: "B", 250: "C", 0: "SKIP"}[risk]
    print(f"  {date} {sym:>6} :{prof} SQS={sqs}({tier}) risk=${risk} P&L=${pnl:+,.0f}")
```

---

## What Does NOT Change

| Component | Status |
|-----------|--------|
| simulate.py entry/exit logic | **UNCHANGED** |
| Signal score (MACD, bull_struct, vol_surge, R2G) | **UNCHANGED** — still gates entries |
| min_score threshold (3.0) | **UNCHANGED** |
| VWAP checks | **UNCHANGED** |
| Exit signals (topping_wicky, bearish_engulfing, etc.) | **UNCHANGED** |
| Session kill switch ($2K max loss, 50% give-back, 3 consec) | **UNCHANGED** |
| Cold market gate | **UNCHANGED** |
| PM volume minimum (1,000) | **UNCHANGED** (now also reflected in SQS = 0 for < 1K) |
| Profile B float ceiling (10M) | **UNCHANGED** |
| Profile A/B classification logic | **UNCHANGED** |

---

## Expected Impact (Estimated from V2 Data)

| Scenario | P&L |
|----------|-----|
| V1 (no filters) | -$17,885 |
| V2 (protective filters) | -$8,938 |
| V3 estimated (SQS + PM vol sort) | **~+$1,800 to +$5,800** |

The range depends on how the kill switch interacts with the new sort order. The PM volume sort alone recovers GWAV (+$6,735). The SQS tiered risk reduces big losers by 50-75% while reducing winners by ~50% on lower-quality stocks.

The key metric to watch: **are we getting more consistent daily results with smaller drawdowns?**

---

## Backtest Instructions

1. Copy `run_backtest_v2.py` → `run_backtest_v3.py`
2. Add `compute_sqs()` function
3. Change sort from gap% to PM volume descending
4. Pass `--risk {risk}` to simulate.py commands
5. Add SQS logging
6. Run all 38 days
7. Generate report: `scanner_results/JAN_FEB_BACKTEST_REPORT_V3.md`

**The report should include:**
- All V2 metrics (total P&L, trades, win rate, etc.)
- NEW: SQS distribution (how many A+/B/C/Skip)
- NEW: P&L breakdown by tier (A+ trades P&L vs B vs C)
- NEW: Per-trade SQS and risk level
- Kill switch analysis (did PM vol sort prevent the GWAV block?)

---

## Design Philosophy

> "Day traders are hunters of volatility, and masters of risk management." — Ross Cameron

The bot hunts volatility through its scanner (gap%, float, PM activity). The SQS makes it a master of risk management by sizing positions according to stock quality — going full size on liquid runners and quarter size on ghost towns.

The signal score (Layer 2) remains the "pull the trigger" system. The SQS (Layer 1) is the "how much ammo to load" system.

---

*Directive prepared by Perplexity Computer — 2026-03-09*  
*Based on V2 backtest analysis of 26 trades across 38 trading days*
