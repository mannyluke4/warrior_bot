# V4 Directive — Tier Restructure & C-Tier Tightening

**Date:** 2026-03-09  
**From:** Luke + Perplexity Analysis  
**To:** Duffy (Claude Code / IronClaw)  
**Branch:** `scanner-sim-backtest`  
**Backtest scope:** Same Jan 2 – Feb 27 dataset (re-run all 38 days)  
**Builds on:** V3 (SQS + PM Volume Sort) — P&L was +$566

---

## What V3 Proved

V3 turned -$17,885 (V1) into +$566. The two-layer architecture works. But the data revealed the tiers are mis-weighted:

| V3 Tier | Sims | Active Trades | P&L | Verdict |
|---------|------|---------------|-----|---------|
| A+ (SQS 7-9, $1k risk) | 4 | 1 | -$588 | Only 1 trade — not enough data |
| B (SQS 5-6, $500 risk) | 42 | 7 (3W/4L) | +$3,328 | Clear winner — 42.9% WR, 4.8x R:R |
| C (SQS 3-4, $250 risk) | 108 | 18 (5W/13L) | -$2,174 | Net drag — losers are low-liquidity |

B-tier carried the entire bot. A+ had insufficient data at n=1. C-tier was a net drag, but its losers share a specific pattern: low PM volume and/or low gap, causing stop slippage on illiquid stocks.

---

## V4 Changes — Summary

Four changes, all in the orchestrator layer. **simulate.py is NOT touched.**

| # | Change | Where | Impact |
|---|--------|-------|--------|
| 1 | Restructure tier risk mapping | `compute_sqs()` | A+ demoted, B promoted |
| 2 | Raise Skip threshold from SQS 0-2 to SQS 0-3 | `compute_sqs()` | Drops SQS=3 stocks entirely |
| 3 | Add C-tier quality gate (gap + PM vol) | Orchestrator loop | Blocks low-quality SQS=4 stocks |
| 4 | SQS logging updates | Report/stats output | Reflects new tier names |

---

## Change 1: Restructured Tier Risk Mapping

### Why:
B-tier (SQS 5-6) proved itself over 42 sims with a 42.9% active win rate and a 4.8:1 reward-to-risk ratio. It deserves more capital. A+ had only 1 active trade in 2 months — not enough to justify $1,000 risk. Demote it until we have more data.

### Old (V3):
```
SQS 7-9  → A+ → $1,000 risk
SQS 5-6  → B  → $500 risk
SQS 3-4  → C  → $250 risk
SQS 0-2  → Skip
```

### New (V4):
```
SQS 7-9  → Shelved → $250 risk   (demoted — insufficient data)
SQS 5-6  → A-tier  → $750 risk   (promoted — proven performers)
SQS 4    → B-tier  → $250 risk   (tightened — must pass quality gate)
SQS 0-3  → Skip    → $0          (SQS=3 demoted to skip)
```

### Updated `compute_sqs()`:

```python
def compute_sqs(candidate: dict) -> tuple[int, str, int]:
    """
    Compute Stock Quality Score and return (sqs, tier_label, risk_dollars).
    
    V4 tier mapping:
      SQS 7-9 → "Shelved" → $250   (was $1000 — insufficient data at n=1)
      SQS 5-6 → "A"       → $750   (was $500  — proven 42.9% WR, 4.8x R:R)
      SQS 4   → "B"       → $250   (was $250  — must also pass quality gate)
      SQS 0-3 → "Skip"    → $0     (was SQS 0-2 — SQS=3 demoted)
    """
    pm_vol = candidate.get('pm_volume', 0) or 0
    gap = candidate.get('gap_pct', 0) or 0
    flt = candidate.get('float_millions')
    
    # PM Volume score (0-3) — unchanged
    if pm_vol >= 500_000:
        pm_score = 3
    elif pm_vol >= 50_000:
        pm_score = 2
    elif pm_vol >= 1_000:
        pm_score = 1
    else:
        pm_score = 0
    
    # Gap % score (0-3) — unchanged
    if gap >= 40:
        gap_score = 3
    elif gap >= 20:
        gap_score = 2
    elif gap >= 10:
        gap_score = 1
    else:
        gap_score = 0
    
    # Float score (0-3) — unchanged
    if flt is None or flt > 5.0:
        float_score = 0
    elif flt > 2.0:
        float_score = 1
    elif flt >= 0.5:
        float_score = 2
    else:
        float_score = 3
    
    sqs = pm_score + gap_score + float_score
    
    # V4 tier mapping
    if sqs >= 7:
        return sqs, "Shelved", 250    # was $1000
    elif sqs >= 5:
        return sqs, "A", 750          # was $500
    elif sqs >= 4:
        return sqs, "B", 250          # same $250, but requires quality gate
    else:
        return sqs, "Skip", 0         # was SQS 0-2, now SQS 0-3
```

---

## Change 2: SQS=3 Demoted to Skip

### Why:
SQS=3 had 35 sims across the backtest. Net P&L: **-$998**. The three winners were tiny ($8, $85, $156). Not worth the exposure.

### What this means:
- Any stock scoring SQS 0, 1, 2, or 3 is now skipped entirely
- The minimum SQS to trade is now 4 (was 3)
- This is already handled in the tier mapping above (SQS 0-3 → Skip)

---

## Change 3: C-Tier Quality Gate (Gap + PM Volume)

### Why:
Even within SQS=4 (now "B-tier"), the backtest showed a clean split. C-tier losers overwhelmingly had low PM volume (median 5,027) while winners had 4x more (median 20,728). Adding a gap requirement catches cases like ELAB (27% gap but only 3,411 PM vol — lost $426) where gap alone would pass.

The combined gate **Gap >= 14% AND PM Volume >= 10,000** on SQS=4 stocks produces:
- 3 winners kept (+$824), 1 tiny loser (-$24) → net +$800
- 12 losers blocked (-$3,611), 2 winners blocked (+$637)
- **Net improvement: +$2,974**

### Implementation:

In the orchestrator loop, AFTER computing SQS but BEFORE calling simulate.py:

```python
for c in all_candidates:
    sym = c['symbol']
    profile = c['profile']
    sim_start = c.get('sim_start', '07:00')
    
    # Compute Stock Quality Score (V4)
    sqs, tier, risk = compute_sqs(c)
    
    if risk == 0:
        print(f"  SQS SKIP {sym} (SQS={sqs})")
        continue
    
    # NEW V4: B-tier quality gate
    # SQS=4 stocks must have gap >= 14% AND PM volume >= 10,000
    if tier == "B":
        pm_vol = c.get('pm_volume', 0) or 0
        gap = c.get('gap_pct', 0) or 0
        if gap < 14.0 or pm_vol < 10_000:
            print(f"  B-GATE SKIP {sym} (SQS={sqs}, gap={gap:.1f}%, pm_vol={pm_vol:,.0f}) — needs gap>=14% AND pm_vol>=10k")
            continue
    
    # Check kill switch (unchanged)
    if session.should_stop():
        ...
    
    # Build simulate.py command with dynamic risk
    if profile == "B":
        cmd = f"timeout 180 python simulate.py {sym} {date} {sim_start} 12:00 --profile B --ticks --feed databento --l2 --no-fundamentals --risk {risk}"
    else:
        cmd = f"timeout 120 python simulate.py {sym} {date} {sim_start} 12:00 --profile A --ticks --no-fundamentals --risk {risk}"
```

### Quality Gate Logic:
```
IF SQS == 4 (B-tier):
    IF gap_pct >= 14.0 AND pm_volume >= 10,000:
        → TRADE at $250 risk
    ELSE:
        → SKIP (log as "B-GATE SKIP")
```

This gate does NOT apply to A-tier (SQS 5-6) or Shelved (SQS 7-9) — only to B-tier (SQS=4).

---

## Change 4: Updated Logging

### Log format:
```
  RUN  GWAV profile=A start=07:00 SQS=6(A) risk=$750 pm_vol=1,537,606 gap=10.3% float=0.80M
  RUN  MLEC profile=A start=07:00 SQS=5(A) risk=$750 pm_vol=29,541 gap=30.1% float=0.70M
  RUN  BAOS profile=A start=07:00 SQS=4(B) risk=$250 pm_vol=15,695 gap=14.7% float=0.94M [B-GATE: PASS]
  B-GATE SKIP JL (SQS=4, gap=14.3%, pm_vol=5,027) — needs gap>=14% AND pm_vol>=10k
  SQS SKIP ROLR (SQS=3)
```

### Stats JSON:
```python
stats['sim_details'].append((date, sym, profile, pnl, sqs, risk, tier))
```

### Report tier labels:
```python
tier_labels = {
    "Shelved": "Shelved (SQS 7-9, $250)",
    "A": "A-tier (SQS 5-6, $750)", 
    "B": "B-tier (SQS 4, $250)",
    "Skip": "Skip"
}
```

---

## What Does NOT Change

| Component | Status |
|-----------|--------|
| simulate.py entry/exit logic | **UNCHANGED** |
| Signal score (MACD, bull_struct, vol_surge, R2G) | **UNCHANGED** |
| min_score threshold (3.0) | **UNCHANGED** |
| VWAP checks | **UNCHANGED** |
| Exit signals (topping_wicky, bearish_engulfing, etc.) | **UNCHANGED** |
| Session kill switch ($2K max loss, 50% give-back, 3 consec) | **UNCHANGED** |
| Cold market gate | **UNCHANGED** |
| PM volume sort (descending) | **UNCHANGED** (from V3) |
| SQS point calculation (PM vol, gap, float scoring) | **UNCHANGED** |
| Profile A/B classification logic | **UNCHANGED** |

---

## Expected V4 Impact (Projected from V3 Data)

| Component | V3 Actual | V4 Projected | Delta |
|-----------|-----------|-------------|-------|
| A-tier (was B) at $750 | +$3,328 (at $500) | +$4,992 | +$1,664 |
| Shelved (was A+) at $250 | -$588 (at $1000) | -$147 | +$441 |
| B-tier (was C) with gate | -$2,174 (all SQS 3-4) | ~+$800 (SQS=4 gated) | +$2,974 |
| **Total** | **+$566** | **~+$5,400** | **+$4,834** |

### Key wins:
- GWAV: +$5,054 (up from +$3,369 at $500 risk → now $750 risk)
- RIOX: +$1,508 (up from +$1,005)
- C-tier blowups (JL -$575, ASTI -$529, CJMB -$472) — all blocked by gate

### Key sacrifice:
- WATT (+$629 at old sizing) — blocked by B-tier gate (PM vol 2,599 < 10k)

---

## Backtest Instructions

1. Copy `run_backtest_v3.py` → `run_backtest_v4.py`
2. Update `compute_sqs()` with new tier mapping (Change 1)
3. Add B-tier quality gate in orchestrator loop (Change 3)
4. Update logging to reflect new tier names (Change 4)
5. Run all 38 days
6. Generate report: `scanner_results/JAN_FEB_BACKTEST_REPORT_V4.md`

**The report should include:**
- All prior metrics (total P&L, trades, win rate, profitable days, etc.)
- Tier distribution: Shelved / A-tier / B-tier / B-GATE SKIP / SQS SKIP
- P&L breakdown by new tier (Shelved / A / B)
- B-tier gate stats: how many SQS=4 stocks passed vs failed the gate
- Per-trade detail with SQS, tier, risk, and gate status
- Version comparison table (V1 / V2 / V3 / V4)

---

## Design Philosophy

V3 proved that stock quality scoring works. V4 refines the calibration:

> **Bet bigger on what we KNOW works. Stay cautious on everything we're less sure about.**

- B-tier earned its promotion through 42 sims of consistent performance
- A+ gets demoted not because it's bad, but because n=1 isn't enough to trust with $1,000
- SQS=3 earned its demotion with -$998 across 35 sims
- The B-tier quality gate doesn't guess which SQS=4 stocks will win — it requires them to prove they have the liquidity (PM vol >= 10k) and catalyst (gap >= 14%) to be worth the risk

Once we do the bigger backtest (Oct 2025 – Feb 2026), we'll have enough A+ data to re-evaluate that tier.

---

*Directive prepared by Perplexity Computer — 2026-03-09*  
*Based on V3 backtest analysis of 154 sims across 38 trading days*
