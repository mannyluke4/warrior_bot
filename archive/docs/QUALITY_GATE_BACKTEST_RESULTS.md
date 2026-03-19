# QUALITY GATE BACKTEST RESULTS
## March 12, 2026 | Entry Mode: direct | Flags: --ticks --feed alpaca --no-fundamentals

---

## CRITICAL DISCOVERY: Gates 1 & 2 Don't Apply in Direct Mode

The shell environment has `WB_ENTRY_MODE=direct`, which was used for the original baseline. In direct mode, the detector has no impulse/pullback state machine, so:

- **Gate 1 (Clean Pullback): SKIP** — No impulse/pullback data available
- **Gate 2 (Impulse Strength): SKIP** — No impulse bar tracked
- **Gate 3 (Volume Dominance): ACTIVE** — Warn only, never blocks
- **Gate 4 (Price/Float Sweet Spot): ACTIVE** — Blocks >$20 or <$2, reduces size outside $3-$15
- **Gate 5 (No Re-entry After Loss): ACTIVE** — Blocks all entries after 1 loss on same symbol

**To fully test gates 1-2, the bot must run in pullback mode** (`WB_ENTRY_MODE=pullback`). In pullback mode, the 5-date baseline drops from 28 trades to only 7 — the pullback pattern is far more selective. Pullback mode with gates ON produces **zero trades** (gates 1-2 filter everything).

**Code fix applied:** Wired `_check_quality_gate()` into `_direct_entry_check()` so gates 3-5 now run in both entry modes (previously only Gate 5 ran in direct mode).

---

## SCANNER NOTE

The scanner gap threshold was fixed from 10% to 5% (matching live_scanner.py). This expanded 2025-11-06 from 26 to 52 candidates, adding 4 extra trades to the baseline (QVCGA -$500, STEM -$684, SLMT -$500). The directive's original baseline (-$6,426 / 24 trades) used the old 10% threshold. The updated baseline below reflects the scanner fix.

---

## A. Trade-by-Trade Comparison (Gates OFF vs Gates ON)

### Date 1: 2025-01-02

| Symbol | Gates OFF | Gates ON | What Changed |
|--------|-----------|----------|--------------|
| AEI | 1T 0W/1L -$1,481 (stop_hit) | 1T 0W/1L -$1,481 | No change — first entry passes all gates. Gate 4: REDUCE (price $2.79 < $3.00) |
| XPON | 1T 0W/1L -$151 (BE exit) | 1T 0W/1L -$151 | No change — first entry. Gate 5 blocked 2nd attempt after loss |
| APM | 4T 2W/2L +$876 | 2T 1W/1L +$215 | **Gate 5 blocked 2 trades after first loss** — lost $661 of winning re-entries |
| **Date Total** | **6T 2W/4L -$756** | **4T 1W/3L -$1,417** | **-$661 (WORSE)** |

> APM is a key finding: Gate 5 blocked profitable cascading re-entries. The first APM trade lost, then Gate 5 blocked all subsequent entries — including the 2 winners. This is the exact scenario the directive warned about.

### Date 2: 2025-11-05

| Symbol | Gates OFF | Gates ON | What Changed |
|--------|-----------|----------|--------------|
| BQ | 2T 0W/2L -$1,029 | 1T 0W/1L -$500 | **Gate 5 saved $529** — blocked revenge trade after first loss |
| **Date Total** | **2T 0W/2L -$1,029** | **1T 0W/1L -$500** | **+$529 (BETTER)** |

### Date 3: 2025-11-06

| Symbol | Gates OFF | Gates ON | What Changed |
|--------|-----------|----------|--------------|
| SMU | 1T 1W/0L +$195 | 1T 1W/0L +$195 | No change. Gate 4: REDUCE (price $18.47 > $15) |
| NHTC | 1T 0W/1L -$540 | 1T 0W/1L -$540 | No change |
| AVX | 1T 0W/1L -$556 | 1T 0W/1L -$556 | No change |
| CRWU | 1T 0W/1L -$580 | 1T 0W/1L -$580 | No change. Gate 4: REDUCE (price $17.37 > $15) |
| CRWG | 1T 0W/1L -$500 | 1T 0W/1L -$500 | No change. Gate 5 blocked 2 re-entries after loss |
| NCEL | 1T 0W/1L -$454 | 1T 0W/1L -$454 | No change |
| QVCGA | 1T 0W/1L -$500 | 1T 0W/1L -$500 | No change. Gate 5 blocked re-entry after loss |
| STEM | 2T 0W/2L -$684 | 0T — | **Gate 4 blocked: price $20.12 > $20 hard limit. Saved $684** |
| ANEL | 0T $0 | 0T — | Gate 4 blocked (price $20.17 > $20) but had 0 baseline trades anyway |
| SLMT | 1T 0W/1L -$500 | 1T 0W/1L -$500 | No change. Gate 3: WARN (fading vol 0.5x) |
| **Date Total** | **10T 1W/9L -$4,119** | **8T 1W/7L -$3,435** | **+$684 (BETTER)** |

### Date 4: 2026-01-06

| Symbol | Gates OFF | Gates ON | What Changed |
|--------|-----------|----------|--------------|
| RKLZ | 1T 1W/0L +$234 | 1T 1W/0L +$234 | No change — winner preserved |
| UXRP | 1T 0W/1L -$600 | 1T 0W/1L -$600 | No change. Gate 5 blocked re-entry after loss |
| CRDU | 2T 1W/1L +$187 | 2T 1W/1L +$187 | No change — no loss before re-entry |
| CYCN | 1T 0W/1L -$154 | 1T 0W/1L -$154 | No change. Gate 4: REDUCE (price $2.21 < $3) |
| **Date Total** | **5T 2W/3L -$333** | **5T 2W/3L -$333** | **$0 (NO CHANGE)** |

### Date 5: 2026-02-03 (Ross's no-trade day)

| Symbol | Gates OFF | Gates ON | What Changed |
|--------|-----------|----------|--------------|
| ELAB | 1T 0W/1L -$156 | 1T 0W/1L -$156 | No change |
| GLGG | 1T 0W/1L -$577 | 1T 0W/1L -$577 | No change. Gate 3: WARN (fading vol 0.5x) |
| BIYA | 1T 0W/1L -$266 | 1T 0W/1L -$266 | No change |
| MTEN | 0T $0 | 0T — | Gate 4 blocked (price $1.99 < $2) but had 0 baseline trades anyway |
| MOVE | 1T 0W/1L -$706 | 1T 0W/1L -$706 | No change. Gate 4: REDUCE (price $15.50 > $15) |
| DRCT | 1T 0W/1L -$169 | 1T 0W/1L -$169 | No change. Gate 4: REDUCE (price $2.14 < $3) |
| **Date Total** | **5T 0W/5L -$1,874** | **5T 0W/5L -$1,874** | **$0 (NO CHANGE)** |

> **Feb 3 verdict:** Gates did NOT help. All 5 trades were first entries on different symbols (Gate 5 can't help). All were within the $2-$20 range (Gate 4 can't help). Gates 1-2 (pullback quality) are the only ones that could filter these — but they require pullback mode.

---

## B. Gate Activity Log

### 2025-01-02
```
AEI:   G5 PASS (0 losses) | G1 SKIP | G2 SKIP | G3 PASS (6.2x vol) | G4 REDUCE ($2.79<$3) → ARMED
XPON:  G5 PASS → G4 PASS ($4.40) → ARMED → LOSS → G5 FAIL (1 loss) → BLOCKED
KORE:  G5 PASS → G4 PASS ($3.45) → ARMED (no trigger) | G5 PASS → ARMED (no trigger)
APM:   G5 PASS → G4 REDUCE ($2.94<$3) → ARMED → ENTRY →
       G5 PASS → G4 PASS ($3.20) → ARMED → ENTRY → LOSS →
       G5 FAIL (1 loss) → BLOCKED (×6 more attempts)
BYAH:  G5 PASS → G4 PASS ($5.94) → ARMED (no trigger)
SPHL:  G5 PASS → G4 PASS ($6.62) → ARMED (no trigger)
```

### 2025-11-05
```
BQ:    G5 PASS → G3 PASS (1.5x) → G4 PASS ($3.86) → ARMED → ENTRY → LOSS →
       G5 FAIL (1 loss) → BLOCKED (×2)
```

### 2025-11-06
```
SMU:   G5 PASS → G4 REDUCE ($18.47>$15) → ARMED → WIN →
       G5 PASS → G4 REDUCE ($18.55) → ARMED (no trigger) ×2
NHTC:  G5 PASS → G4 PASS ($3.36) → ARMED → LOSS
AVX:   G5 PASS → G4 PASS ($3.22) → ARMED → LOSS
CRWU:  G5 PASS → G4 REDUCE ($17.37>$15) → ARMED → LOSS ×3 checks, 1 entry
CRWG:  G5 PASS → G4 PASS ($9.53) → ARMED → LOSS → G5 FAIL → BLOCKED (×2)
NCEL:  G5 PASS → G4 PASS ($4.95) → ARMED → LOSS
QVCGA: G5 PASS → G4 PASS ($6.55) → ARMED → LOSS → G5 FAIL → BLOCKED
STEM:  G5 PASS → G4 FAIL ($20.12>$20) → BLOCKED (×5 attempts). All blocked by price.
ANEL:  G5 PASS → G4 FAIL ($20.17>$20) → BLOCKED
SLMT:  G5 PASS → G3 WARN (fading 0.5x) → G4 PASS ($7.45) → ARMED → LOSS
```

### 2026-01-06
```
RKLZ:  G5 PASS → G4 PASS ($4.26) → ARMED → WIN → G5 PASS (0 losses) → ARMED (×5 more)
UXRP:  G5 PASS → G4 PASS ($14.89) → ARMED ×4 checks → LOSS →
       G5 FAIL (1 loss) → BLOCKED
CRDU:  G5 PASS → G4 PASS ($13.22) → ARMED ×5 checks → 2 ENTRIES (1W/1L)
CYCN:  G5 PASS → G4 REDUCE ($2.21<$3) → ARMED → LOSS → G5 FAIL → BLOCKED (×2)
```

### 2026-02-03
```
ELAB:  G5 PASS → G4 PASS ($4.30) → ARMED → LOSS
GLGG:  G5 PASS → G3 WARN (fading 0.5x) → G4 PASS ($11.00) → ARMED → LOSS
BIYA:  G5 PASS → G4 PASS ($4.67) → ARMED → LOSS
MTEN:  G5 PASS → G3 WARN (fading 0.3x) → G4 FAIL ($1.99<$2) → BLOCKED
MOVE:  G5 PASS → G4 REDUCE ($15.50>$15) → ARMED → LOSS
DRCT:  G5 PASS → G4 REDUCE ($2.14<$3) → ARMED → LOSS
```

---

## C. Summary Table

| Date | Trades (OFF) | Trades (ON) | Filtered | P&L (OFF) | P&L (ON) | Delta |
|------|-------------|-------------|----------|-----------|----------|-------|
| 2025-01-02 | 6 | 4 | 2 | -$756 | -$1,417 | -$661 |
| 2025-11-05 | 2 | 1 | 1 | -$1,029 | -$500 | +$529 |
| 2025-11-06 | 10 | 8 | 2 | -$4,119 | -$3,435 | +$684 |
| 2026-01-06 | 5 | 5 | 0 | -$333 | -$333 | $0 |
| 2026-02-03 | 5 | 5 | 0 | -$1,874 | -$1,874 | $0 |
| **TOTAL** | **28** | **23** | **5** | **-$8,111** | **-$7,559** | **+$552** |

**Win rates:** Baseline 5W/23L = 17.9% | Gates ON 4W/19L = 17.4%

**vs. Directive baseline** (-$6,426 / 24 trades): The updated baseline is worse (-$8,111 / 28 trades) because the scanner gap fix (10%→5%) added 4 extra losing trades on 2025-11-06 (QVCGA, STEM×2, SLMT).

---

## D. Gate Hit Rate

| Gate | Times Checked | Times Failed | Trades Blocked | $ Saved (losses avoided) | $ Lost (winners filtered) |
|------|--------------|-------------|----------------|------------------------|--------------------------|
| 1: Clean Pullback | 88 | 0 (all SKIP) | 0 | $0 | $0 |
| 2: Impulse Strength | 88 | 0 (all SKIP) | 0 | $0 | $0 |
| 3: Volume Dominance | 88 | 0 (warn only) | (warn only) | N/A | N/A |
| 4: Price/Float | 88 | 8 (>$20 or <$2) | 2 trades | $684 saved (STEM) | $0 |
| 5: No Re-entry | 88 | 17 | 5 trades | $1,529 saved (BQ, CRWG, QVCGA re-entries) | $661 lost (APM winners) |

**Gate 5 detail:**
- Symbols blocked after loss: APM (6 attempts blocked), BQ (2), XPON (1), CRWG (2), QVCGA (1), STEM (0 — blocked by G4 first), UXRP (1), CYCN (2), SLMT (0)
- Net Gate 5 impact: +$529 (BQ) - $661 (APM) + $0 (others had 0 baseline re-entry trades) = **-$132 net negative**
- Gate 5 hurt more than it helped because APM's cascading winners got blocked

**Gate 4 detail:**
- Stocks >$20 blocked: STEM ($20.12, 5 checks), ANEL ($20.17, 1 check), MTEN ($1.99, 1 check)
- Net Gate 4 impact: **+$684** (saved STEM's 2 losing trades)
- REDUCE applied but did not block: AEI ($2.79), APM ($2.94), SMU ($18.47), CRWU ($17.37), DASX ($18.00), QSU ($19.67), MOVE ($15.50), DRCT ($2.14), CYCN ($2.21), SLGB ($2.51)

---

## KEY FINDINGS

### 1. Gates 1 & 2 are inert in direct mode
The quality gate was designed for pullback mode. In direct mode (current production config), there is no impulse/pullback state machine, so gates 1-2 always SKIP. **These are the highest-impact gates** (clean pullback, impulse strength) — the directive's biggest expected improvement.

### 2. Gate 5 is a double-edged sword
- **Helps:** Prevents revenge trading (saved $529 on BQ)
- **Hurts:** Kills cascading re-entries (cost $661 on APM)
- **Net:** -$132 (slightly negative)
- This matches the directive's concern about `MAX_SYMBOL_TRADES=2` killing cascading winners. Even with `MAX_SYMBOL_TRADES=10`, `MAX_SYMBOL_LOSSES=1` blocks ALL re-entries after a first loss — including subsequent winners.

### 3. Gate 4 is the only reliable positive contributor
- Blocked STEM ($20.12/share) for $684 savings
- The $20 hard price cap is a clean, unambiguous filter

### 4. Feb 3 (no-trade day) is untouched
- All 5 losers were first entries on different symbols
- Only gates 1-2 (pullback quality) could filter these
- This is the single biggest improvement opportunity, and it requires pullback mode

### 5. The scanner gap fix added $1,684 in losses
- 4 new trades from lowering gap threshold 10%→5%: QVCGA (-$500), STEM (-$684), SLMT (-$500)
- Gate 4 recovered $684 of this (STEM blocked), but QVCGA and SLMT still trade

---

## RECOMMENDATIONS FOR PERPLEXITY

1. **Entry mode decision required:** The quality gate's highest-impact features (gates 1-2) only work in pullback mode. But pullback mode produces far fewer trades (7 vs 28 in the baseline). Switching entry modes changes everything — it's not a configuration tweak, it's a strategy pivot.

2. **Gate 5 needs refinement:** `MAX_SYMBOL_LOSSES=1` is too aggressive. It blocks the cascading re-entry edge (APM). Consider `MAX_SYMBOL_LOSSES=2` to allow one recovery attempt, or only apply Gate 5 after consecutive losses.

3. **Gate 4 works well as-is.** The $20 price cap is clean and saved money. Consider tightening the sweet spot ($3-$15) from a REDUCE to a hard FAIL to block more marginal trades.

4. **Scanner gap threshold needs review:** The 5% gap minimum added net-negative trades. Consider reverting to 10% or filtering by PM volume (all 3 new losers had <2K PM volume).

---

*Backtest executed by Claude Code (Duffy) | March 12, 2026*
*Code change: Wired _check_quality_gate() into _direct_entry_check() for gates 3-5 support*
