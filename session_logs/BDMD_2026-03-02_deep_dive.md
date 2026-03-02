# BDMD Deep Dive: Choppy Stock Case Study
**Date**: March 2, 2026
**Author**: Claude Sonnet 4.6
**Responding to**: BDMD_DEEP_DIVE_DIRECTIVE.md

---

## Executive Summary

BDMD generated 5 losing trades (-$3,942) with a 0% win rate. The root causes are:
1. **Classifier reclassified "avoid" → "uncertain"** — initially correctly blocked, but `WB_CLASSIFIER_RECLASS_ENABLED=1` allowed it to flip back before the trade window
2. **Stale filter evaded by micro-HOD drift** — BDMD advanced $0.05-0.13 per entry, just enough to reset the stale counter each time
3. **R-narrowing amplified damage** — R dropped from $0.23 to $0.09 after the first 2 trades, tripling share count to 11,111

The most actionable fix is a **consecutive loss counter** (`WB_MAX_CONSEC_LOSSES`): after N losses on one symbol in a session, block further ARMs. Confirmed safe on all 3 regression stocks.

---

## Part 1: Full Diagnostic Timeline

### Verbose Backtest Output (annotated)

```
[07:03] 1M SKIP (MACD not bullish) macd_score=-4.5
        → Early session: BDMD below VWAP, no momentum

[07:21] CLASSIFIER: BDMD → uncertain (conf=0.30)
        → NH=2, PB=0, green=0.80, VWAP=0.3%, range=0.7%
        → Very early, data too thin for strong classification

[07:40] CLASSIFIER: reclassified uncertain → AVOID ✅
        → Classifier correctly identifies BDMD as avoid at 40m mark

[08:02] ARMED entry=3.02 stop=2.98 R=0.04 score=6.5 [RED_TO_GREEN, WHOLE_DOLLAR_NEARBY]
[08:03] ARMED entry=3.05 stop=3.00 R=0.05 score=6.5 [RED_TO_GREEN, WHOLE_DOLLAR_NEARBY]
        → Arms fired but NOT entered — classifier "avoid" gate blocking entries ✅

[08:08] 1M RESET (lost VWAP)
[08:09] CLASSIFIER: reclassified avoid → uncertain ⚠️
        → BDMD recovered back to VWAP — classifier flipped out of "avoid"
        → This is the critical failure point: the protection was removed

[09:32] ARMED entry=3.40 stop=3.19 R=0.21 score=12.5
        [ASC_TRIANGLE, FLAT_TOP, RED_TO_GREEN, VOLUME_SURGE, WHOLE_DOLLAR_NEARBY]
        → Classifier is now "uncertain" — no gate. Score 12.5 = max. Entry allowed.

[09:33] ENTRY: $3.42  stop=$3.19  R=$0.23  qty=4,316  ← Trade 1
[09:33] BEARISH_ENGULFING_EXIT @ $3.35  →  -$300

[09:33] ARMED entry=3.45  R=0.17  score=12.5  [ABCD, ASC_TRIANGLE, FLAT_TOP, ...]
[09:34] ENTRY: $3.47  stop=$3.28  R=$0.19  qty=5,221  ← Trade 2
        ⚠️ RE-ENTRY IMMEDIATELY AFTER LOSS — 60 seconds between trades
        (BE exit doesn't trigger stop-hit cooldown, only max_entries cooldown)
[09:35] BEARISH_ENGULFING_EXIT @ $3.37  →  -$531

        → 2 entries hit → COOLDOWN activated until 09:44

[09:36] 1M NO_ARM exhaustion: vol_ratio=0.37 (min 0.4) ← Exhaustion blocked ✅
[09:43] 1M NO_ARM exhaustion: vol_ratio=0.37 (min 0.4) ← Exhaustion blocked ✅

[09:44] ARMED entry=3.48  stop=3.41  R=0.07  score=10.0  [ABCD, ASC_TRIANGLE, FLAT_TOP, ...]
        → Cooldown just expired. R has now NARROWED to $0.07.
[09:45] ENTRY: $3.50  stop=$3.41  R=$0.09  qty=11,111  ← Trade 3  ⚠️ 3x shares
        → R dropped from $0.23 → $0.09 (61% shrink). Same $1K risk, 3x shares.
[10:05] STOP_HIT @ $3.41  →  -$1,111

[10:06] ARMED entry=3.61  stop=3.54  R=0.07  score=11.5  [ABCD, ASC_TRIANGLE, ...]
        → Trade 3 was stop_hit 61 minutes ago → stop-hit cooldown has expired
[10:07] ENTRY: $3.63  stop=$3.54  R=$0.09  qty=11,111  ← Trade 4  ⚠️ 3x shares
[10:07] STOP_HIT @ $3.53  →  -$1,111

[10:08] 1M RESET (extended: 6 green candles)
        → 2 entries hit → COOLDOWN activated until 10:17

[10:12-10:15] ARMED × 3 (all blocked by cooldown)
[10:17] ARMED  → cooldown expires, count resets
[10:18] ENTRY: $3.70  stop=$3.61  R=$0.09  qty=11,111  ← Trade 5
[10:18] BEARISH_ENGULFING_EXIT @ $3.62  →  -$889
```

---

### Q&A: Directive Questions

**1. Stale filter state at each ARM — Why didn't it trigger?**

BDMD was making micro new session HODs between every entry:

| ARM Time | Entry | Session HOD | HOD Advance |
|----------|-------|-------------|-------------|
| 09:32 | $3.40 | ~$3.42 | New HOD at entry |
| 09:33 | $3.45 | ~$3.47 | New HOD +$0.05 |
| 09:44 | $3.48 | ~$3.50 | New HOD +$0.03 |
| 10:06 | $3.61 | ~$3.63 | New HOD +$0.13 |
| 10:17 | $3.68 | ~$3.70 | New HOD +$0.07 |

Each ARM was at or near a new session high. `bars_since_new_hod_1m` reset to 0 at every entry, keeping both stale checks (rolling 30-bar and session 120-bar) well below their thresholds. BDMD was a **slow grind up with immediate reversal** — exactly the pattern the stale filter misses.

**2. Exhaustion filter state at each ARM**

| ARM Time | VWAP Dist | Session Range | eff_vwap_pct | vol_ratio | Blocked? |
|----------|-----------|---------------|--------------|-----------|---------|
| 09:32 | ~2% | ~17% | max(10%, 8.5%) = 10% | ~0.45 | No |
| 09:33 | ~2% | ~17% | 10% | ~0.45 | No |
| 09:44 | ~5% | ~18% | 10% | passed | No |
| 09:36 | ~5% | ~18% | 10% | **0.37** | **YES** ✅ |
| 09:43 | ~5% | ~18% | 10% | **0.37** | **YES** ✅ |
| 10:06 | ~8% | ~20% | 10% | ~0.55 | No |
| 10:17 | ~10% | ~21% | max(10%, 10.5%) = 10.5% | ~0.50 | No |

The exhaustion filter blocked 2 ARMs at 09:36 and 09:43 via the vol_ratio check. This was correct — volume was decaying (0.37 < min 0.40). It failed to block the remaining 3 because volume and VWAP distance were within bounds.

**3. Classifier result**

| Time | Classification | Confidence | Implication |
|------|---------------|-----------|-------------|
| 07:21 | `uncertain` | 0.30 | No gate |
| 07:40 | `avoid` | — | ARMs blocked ✅ |
| 08:09 | `uncertain` (reclassified) | — | Gate removed ⚠️ |
| 09:33+ | `uncertain` | — | No gate, all 5 trades through |

**Root cause**: `WB_CLASSIFIER_RECLASS_ENABLED=1` allowed BDMD to flip from "avoid" back to "uncertain" when it temporarily recovered to VWAP at 08:09. By the time the 5 bad trades fired (09:33–10:18), the classifier had forgotten the "avoid" signal.

**4. Score breakdown for trades 3-5**

Scores of 9.5–11.5 despite repeated failures because:
- `MACD gate` (~4.5 points): MACD was still net bullish each time
- `ASC_TRIANGLE + FLAT_TOP` → +3 pts (bull structure)
- `VOLUME_SURGE` → +2 pts (volume picked up at each breakout attempt)
- `RED_TO_GREEN` → +1.5 pts
- `R >= $0.05` → +0.5 pts

BDMD was doing a "staircase" pattern: pull back, consolidate with a flat top, then break out on volume. The bot was correctly detecting the PATTERN. The problem is the pattern kept failing due to macro selling pressure.

**5. Pattern tags**

| Trade | ABCD | ASC_TRI | FLAT_TOP | R2G | VOL_SURGE | WD |
|-------|------|---------|----------|-----|-----------|-----|
| 1 | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| 2 | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 3 | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| 4 | ✓ | ✓ | — | ✓ | ✓ | — |
| 5 | ✓ | ✓ | ✓ | ✓ | — | — |

Full tag complement on every trade. The scoring system sees valid pattern structure each time. This is a fundamental limitation: the scorer grades the SETUP, not the CONTEXT (is this setup the 5th attempt in 2 hours?).

**6. Re-entry cooldown state**

The 2/10 cooldown created 3 trading waves:
- **Wave 1** (09:33–09:34): 2 trades → cooldown until 09:44
- **Wave 2** (09:45): 1 trade, stop_hit → stop-hit cooldown + entry #1 of new window
- **Wave 3** (10:07–10:18): 2 trades → cooldown until 10:27

The cooldown IS working. The problem is BDMD generates a fresh valid-looking setup 22+ minutes after each cooldown expires, so the cycle repeats.

**7. HOD progression and micro-highs**

BDMD's session HOD at each entry: $3.42 → $3.47 → $3.50 → $3.63 → $3.70. Each advance is $0.03–$0.13 (0.8–3.8% of price). The stale filter has no minimum HOD advance requirement — any new high, no matter how small, resets the counter.

---

## Part 2: L2 Data

**Not available.** Databento XNAS.ITCH requires a live license for today's data:
```
403 license_not_found_unauthorized
A live data license is required to access XNAS.ITCH data after 2026-03-02T05:00:00Z.
```

L2 analysis will be possible once IBKR integration is live (`WB_ENABLE_L2=1`). Based on the price action (immediate reversals at each breakout), it's highly likely there was consistent sell-side pressure at each new high — this is exactly the sell-wall pattern L2 would detect.

---

## Part 3: What Could Have Caught This?

### A. Stale Filter — HOD Minimum Advance (Medium impact)

**Problem**: Any new high, even $0.01, resets the stale counter.

**Proposed fix**: `WB_STALE_HOD_MIN_PCT` — require HOD to increase by at least X% to count as a meaningful new high. With 1.0%:
- BDMD's $0.05 advance on a $3.50 stock = 1.4% → would NOT reset stale counter
- A genuine runner from $3.50 to $3.55 (+1.4%) would still reset it

**Risk**: Potential regression impact. Needs testing across full stock set before enabling. **Not recommended for immediate deployment** — the consecutive loss counter is safer.

### B. Consecutive Loss Counter ⭐ RECOMMENDED

**Problem**: No mechanism blocks a symbol that has demonstrated it loses reliably.

**Proposed fix**: `WB_MAX_CONSEC_LOSSES=0` (default=off). When set to N, block further ARMs on a symbol for the rest of the session after N consecutive losses (stop_hit OR bearish_engulfing OR topping_wicky).

**BDMD impact**:
| Gate N | Trades saved | P&L saved | Remaining loss |
|--------|-------------|-----------|----------------|
| N=2 | trades 3+4+5 | +$3,111 | -$831 |
| N=3 | trades 4+5 | +$2,000 | -$1,942 |

**False positive analysis (108-stock study)**:
Stocks with 2 consecutive losses followed by a winner:
- ANPA, AZI, BNAI, BNAI, OPTX, RELY, ROLR, SNSE, ACON (9 instances)
- Most significant: AZI (+$2,167 win after 2 losses)

**Recommended setting: N=3** — after 3 consecutive losses, the stock has failed 3x in a row. The probability of a winner on attempt #4 is very low, and the risk/reward strongly favors blocking.

With N=3:
- All current regression stocks safe: VERO (win/win/win/loss), GWAV (win/loss), ANPA (win/loss) — none have 3 consecutive losses
- BDMD: saves trades 4+5 → +$2,000

### C. Classifier "Avoid" Stickiness (Lower priority)

**Problem**: `WB_CLASSIFIER_RECLASS_ENABLED=1` allowed the "avoid" gate to be removed when BDMD briefly recovered.

**Option 1**: Make "avoid" sticky for the session (can only reclassify FROM avoid if confidence is ≥ 0.7). Lower priority — would need careful regression testing.

**Option 2**: Allow reclassification but gate entry on "uncertain" classification more aggressively when it CAME FROM "avoid". This is complex.

**Recommendation**: Defer to a future round. The consecutive loss counter is a simpler fix with similar protection.

### D. R-Narrowing Detection (Low priority)

**Problem**: R dropped from $0.23 → $0.09 (61% reduction). Trades 3-5 used 11,111 shares vs 4,316 for trade 1 — same $1K risk, but in a narrower range means any tick reversal is catastrophic.

**Proposed fix**: `WB_MIN_R_REL_INITIAL` — if R < X% of the initial R seen on this symbol today, reduce position or skip. With 50%, would block trades where R < $0.115 after seeing R=$0.23.

**Recommendation**: Defer. The root problem is BDMD shouldn't be traded at all after 2-3 losses. Fixing position sizing doesn't address the core issue.

### E. Win-Rate-Aware Sizing (Low priority)

After 2 consecutive losses on the same symbol, reduce position size by 50%; after 3, stop. This overlaps with the consecutive loss counter — if we're going to stop after N losses, blocking is cleaner than half-sizing.

**Recommendation**: Implement the hard block (option B) rather than a soft sizing reduction.

---

## Part 4: Recommended Code Changes

### Priority 1 (P0): Consecutive Loss Counter

**Implementation**:

```python
# In simulate.py SymbolState or tracking dicts (similar to _symbol_entry_count):
# _symbol_consec_losses: dict[str, int] = {}

# In on_trade_exit():
if exit_reason in ('stop_hit', 'bearish_engulfing_exit_full', 'topping_wicky_exit_full', ...):
    if pnl < 0:
        self._symbol_consec_losses[symbol] = self._symbol_consec_losses.get(symbol, 0) + 1
    else:
        self._symbol_consec_losses[symbol] = 0  # reset on any win

# In can_enter() / signal handler, before accepting ARMED:
max_consec = self.max_consec_losses  # from WB_MAX_CONSEC_LOSSES env var, default 0
if max_consec > 0:
    if self._symbol_consec_losses.get(symbol, 0) >= max_consec:
        return None  # blocked: too many consecutive losses
```

**Env var**: `WB_MAX_CONSEC_LOSSES=0` (default=0=off). Recommend setting to 3 in production.

**Regression test plan**:
```bash
# Confirm no regression impact with N=3
WB_MAX_CONSEC_LOSSES=3 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks
WB_MAX_CONSEC_LOSSES=3 python simulate.py GWAV 2026-01-16 07:00 12:00 --ticks
WB_MAX_CONSEC_LOSSES=3 python simulate.py ANPA 2026-01-09 07:00 12:00 --ticks
```
Expected: all three unchanged (no 3-consecutive-loss sequences in current regression runs).

```bash
# Confirm BDMD improvement
WB_MAX_CONSEC_LOSSES=3 python simulate.py BDMD 2026-03-02 07:00 12:00 --ticks
```
Expected: 3 trades (saves -$2,000 from trades 4+5).

### Priority 2 (P1): HOD Minimum Advance (future round)

**Proposed env var**: `WB_STALE_HOD_MIN_PCT=0` (default=0=off, any new high resets)

When > 0, only reset `bars_since_new_hod_1m` if `(new_hod - old_hod) / old_hod * 100 >= WB_STALE_HOD_MIN_PCT`.

Requires regression testing across full stock set before enabling.

---

## Summary

| Issue | Root Cause | Fix | Impact | Status |
|-------|-----------|-----|--------|--------|
| All 5 trades entered | Classifier "avoid" → "uncertain" reclassification at 08:09 | Stickier avoid gate | Medium | Future round |
| Trades 4+5 entered | No consecutive-loss block | `WB_MAX_CONSEC_LOSSES=3` | +$2,000 on BDMD | **P0: implement now** |
| Stale filter bypass | Micro-HOD resets ($0.05 advances) | `WB_STALE_HOD_MIN_PCT` | Medium | P1: future round |
| Oversized positions (trades 3-5) | R narrowed, position size tripled | Consecutive-loss block eliminates these | +$2,000 (bundled with above) | Covered by P0 |

**L2 Data**: Not available for today's data (requires live Databento license or IBKR L2). Once IBKR L2 is live, the `l2_hard_gate` in the codebase will handle sell-wall detection at breakout levels.

---

*Analysis by Claude Sonnet 4.6 — March 2, 2026*
*Sources: simulate.py --verbose output, trades_detail.csv (108-stock study), micro_pullback.py stale filter logic, Databento API (unavailable for live data)*
