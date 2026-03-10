# PROFILE B DEEP DIVE — Architecture Analysis & Roadmap

**Date:** 2026-03-10
**Branch:** v6-dynamic-sizing
**Scope:** Complete code review of Profile B vs Profile A — every file, every gate, every difference

---

## EXECUTIVE SUMMARY

Profile B has a **fundamentally different challenge** than Profile A. After reviewing every line of code, the backtest data, and the validation results, here's the core diagnosis:

**Profile B's L2 system works.** The validation proved it — L2 improves mid-float stocks by +$3,157 (Alpaca) / +$18,128 (Databento) vs NoL2 baseline. The problem isn't the L2 system. The problem is that **Profile B operates inside Profile A's framework** with only 5 config overrides, when mid-float stocks behave fundamentally differently.

---

## 1. ARCHITECTURE COMPARISON — Profile A vs Profile B

### What Profile A Gets (profiles/A.json)
```json
{
  "WB_ENABLE_L2": "0",
  "WB_EXIT_MODE": "signal",
  "WB_CLASSIFIER_ENABLED": "1",
  "WB_CLASSIFIER_SUPPRESS_ENABLED": "0",
  "WB_FAST_MODE": "0"
}
```

### What Profile B Gets (profiles/B.json)
```json
{
  "WB_ENABLE_L2": "1",
  "WB_L2_HARD_GATE_WARMUP_BARS": "30",
  "WB_L2_STOP_TIGHTEN_MIN_IMBALANCE": "0.65",
  "WB_EXIT_MODE": "signal",
  "WB_CLASSIFIER_ENABLED": "1",
  "WB_CLASSIFIER_SUPPRESS_ENABLED": "0",
  "WB_FAST_MODE": "0",
  "WB_MAX_ENTRIES_PER_SYMBOL": "3"
}
```

### STRUCTURAL DIFFERENCES (only 3 actual differences)
| Setting | Profile A | Profile B | Impact |
|---------|----------|----------|--------|
| WB_ENABLE_L2 | 0 (OFF) | 1 (ON) | L2 order book signals active |
| WB_L2_HARD_GATE_WARMUP_BARS | default (30) | 30 | Same — no difference |
| WB_MAX_ENTRIES_PER_SYMBOL | 2 (default) | 3 | B gets one extra re-entry attempt |

**Everything else is identical.** Same classifier thresholds, same exhaustion filters, same exit mode, same scoring, same stop logic, same MACD gates, same VWAP gates.

---

## 2. THE SQS SCORING PROBLEM

The Stock Quality Score (SQS) is **profile-blind**. It scores all stocks the same way:

```
SQS = pm_vol_score + gap_score + float_score

Float scoring:
  < 0.5M  → 3 points
  0.5-2M  → 2 points
  2-5M    → 1 point
  > 5M    → 0 points  ← ALL Profile B stocks get 0 here

Tier mapping:
  SQS >= 7 → Shelved ($250 risk)
  SQS >= 5 → Tier A  ($750 risk)  ← Profile B can reach this
  SQS >= 4 → Tier B  ($250 risk)
  SQS <  4 → Skip
```

**Profile B stocks (float 5-10M) always get float_score = 0.** To reach Tier A ($750 risk), they only need:
- pm_vol >= 500K (3pts) + gap >= 20% (2pts) = SQS 5 → **$750 risk**
- pm_vol >= 50K (2pts) + gap >= 40% (3pts) = SQS 5 → **$750 risk**

### Actual V6.1 Data: Profile B Tier Distribution
| Tier | Sims | Active | P&L | Risk Level |
|------|------|--------|-----|------------|
| Tier A (SQS>=5) | 5 | 2 trades | **-$2,598** | $750/trade |
| Tier B (SQS=4) | 11 | 2 trades | **+$138** | $250/trade |

**Tier A Profile B trades are catastrophic.** Both active Tier A trades were monster losers (CRWG -$1,572, IONZ -$1,026). Meanwhile, Tier B Profile B trades are slightly positive.

---

## 3. PROFILE B CANDIDATE FILTERING

From `run_backtest_v4_extended.py` (lines 171-180):

```python
# Profile A filter:
if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
    profile_a.append(c)

# Profile B filter:
elif p == 'B' and 5.0 <= flt <= 10.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
    profile_b.append(c)

# Profile B max 2 per day:
profile_b = profile_b[:2]
```

**Key differences in candidate selection:**
| Parameter | Profile A | Profile B | Implication |
|-----------|----------|----------|-------------|
| Float | 0.5-5.0M | 5.0-10.0M | B is mid-float (less explosive moves) |
| Gap | 10-40% | 10-25% | B has tighter gap cap |
| Price | $3-$10 | $3-$10 | Same |
| Max per day | Unlimited | 2 | B is capped |

---

## 4. PROFILE B ENTRY SYSTEM — HOW L2 ACTUALLY WORKS

Profile B uses the **same MicroPullbackDetector** as Profile A, with L2 overlaid:

### L2 Acceleration (helps entries)
- If bullish L2 (>=3 bullish signals): waives impulse requirement
- If bullish L2 (>=3 bullish signals): waives weak trigger candle at confirmation
- Score boost: imbalance > 0.65 → +2 to score; bid stacking → +2; ask thinning → +1.5

### L2 Hard Gate (blocks entries)
- If L2 is bearish (imbalance < 0.30, or large ask + imb < 0.45): **blocks ARM**
- Only activates after 30 bars warmup (prevents false blocks at open)
- Also blocks during pullback phase and at confirmation

### L2 Exit Signals
- Imbalance < 0.30 → "l2_bearish" exit
- Large ask wall + imbalance < 0.45 → "l2_ask_wall" exit

### L2 Stop Tightening
- If bid stacking detected AND imbalance >= 0.65: tighten stop to bid stack level
- Only active when L2 confirms genuine support

### Standalone L2 Entry (l2_entry.py)
Completely separate L2EntryDetector that can arm trades purely from order book signals — no impulse/pullback needed. Fires when:
- 2+ consecutive bars of bullish L2 (imbalance > 0.58, bid stacking, ask thinning)
- Above VWAP + above EMA + green bar + MACD not bearish
- Score >= 4.0
- Not exhausted (< 15% above VWAP, < 60% from session low)

---

## 5. IB GATEWAY CONNECTION — WHAT'S READY

The IBKR integration is **fully wired** in bot.py (lines 784-805):

```python
if os.getenv("WB_ENABLE_L2", "0") == "1":
    l2_detector = L2SignalDetector()
    from ibkr_feed import IBKRFeed
    ibkr_feed = IBKRFeed()
    if ibkr_feed.connect():
        for sym in sorted(filtered_watchlist):
            ibkr_feed.subscribe_l2(sym, _on_l2_update)
```

**To activate live L2 via IBKR, you need:**
1. IB Gateway or TWS running locally
2. `.env` settings:
   - `WB_ENABLE_L2=1`
   - `WB_IBKR_HOST=127.0.0.1`
   - `WB_IBKR_PORT=7497` (paper) or `4002` (live)
   - `WB_IBKR_CLIENT_ID=1`
3. IBKR market data subscriptions:
   - US Securities Snapshot and Futures Value Bundle
   - NASDAQ TotalView + EDS
   - NYSE Open Book
4. `pip install ib_insync`

**The ibkr_feed.py has a built-in smoke test:**
```bash
python ibkr_feed.py AAPL 10  # Test L2 for AAPL for 10 seconds
```

---

## 6. WHAT NEEDS TO CHANGE — PROFILE B ROADMAP

### Phase 1: Risk Architecture Fix (Critical)
**Problem:** Profile B stocks with SQS >= 5 get $750 risk (same as Profile A). Mid-float stocks don't deserve the same conviction sizing as micro-floats.

**Fix options:**
A. **Profile-aware SQS**: Add profile multiplier to float_score — Profile B gets max 1pt float bonus instead of 0, keeping them in Tier B
B. **Profile risk cap**: Override risk to min(sqs_risk, profile_max_risk) — cap Profile B at $250 regardless of SQS
C. **Separate tier table**: Profile B gets its own tier mapping entirely

### Phase 2: Profile B Classifier Tuning
**Problem:** Same classifier thresholds for 5-10M float stocks as 0.5-5M stocks. Mid-float stocks have different VWAP distances, range%, and pullback patterns.

**What to investigate:**
- Do mid-float stocks hit the VWAP gate (7%) and range gate (10%) at the same rates?
- Do they cascade the same way? (6+ new highs + 3+ pullbacks seems high for mid-float)
- Should B have different exhaustion thresholds? (mid-float may extend less before fading)

### Phase 3: L2 Signal Calibration for Live IB
**Problem:** L2 thresholds were tuned on the initial 27-stock study with Databento historical data. Live IB data may behave differently.

**Key questions:**
- Is the 30-bar warmup right for live IB data? (IB updates faster than Databento historical)
- Is imbalance 0.65 the right bull threshold for live L2? (IB book depth may differ from Databento MBP-10)
- Should the L2 hard gate be more aggressive? (it already blocks losing entries well)

### Phase 4: B-Gate Refinement
**Problem:** B-Gate (gap >= 14% AND pm_vol >= 10K) only applies to Tier B stocks. Tier A Profile B stocks bypass it entirely.

**Fix:** Apply the B-gate to ALL Profile B stocks regardless of tier.

### Phase 5: Databento vs IB Tick Fidelity
The validation showed Databento ticks dramatically outperform Alpaca (+$18K vs +$3K).
Live IB data should be closer to Databento fidelity. This is a natural advantage for Profile B once IB is connected.

---

## 7. IMMEDIATE IBKR HOOKUP STEPS

Since the code is ready, here's what Claude Code needs to do:

1. **Install ib_insync**: `pip install ib_insync`
2. **Update .env**: Set `WB_ENABLE_L2=1` and IB connection params
3. **Start IB Gateway** (or TWS) in paper trading mode
4. **Run smoke test**: `python ibkr_feed.py AAPL 10`
5. **Test with a single Profile B stock**: Add a known B stock to watchlist with `:B` tag, run bot
6. **Watch for**: L2 signal output in console, hard gate blocks, score boosts, L2 exits

---

## 8. V6.1 PROFILE B DATA — FULL INVENTORY

### All 16 Profile B Simulations
| Date | Symbol | SQS | Tier | Risk | P&L |
|------|--------|-----|------|------|-----|
| 2025-10-06 | IONZ | 5 | A | $750 | $0 |
| 2025-10-14 | CYN | 4 | B | $250 | +$263 |
| 2025-10-15 | SOAR | 4 | B | $250 | $0 |
| 2025-11-03 | SDST | 4 | B | $250 | $0 |
| 2025-11-06 | CRWG | 4 | B | $250 | -$125 |
| 2025-11-11 | CRWG | 5 | A | $750 | **-$1,572** |
| 2025-11-14 | IONZ | 5 | A | $750 | **-$1,026** |
| 2025-11-24 | OLOX | 4 | B | $250 | $0 |
| 2025-12-12 | CRWG | 4 | B | $250 | $0 |
| 2025-12-15 | CRWG | 4 | B | $250 | $0 |
| 2026-01-29 | NAMM | 5 | A | $750 | $0 |
| 2026-02-02 | BATL | 4 | B | $250 | $0 |
| 2026-02-05 | CRWG | 4 | B | $250 | $0 |
| 2026-02-20 | CRWG | 4 | B | $250 | $0 |
| 2026-02-20 | AGIG | 4 | B | $250 | $0 |
| 2026-02-27 | CRWG | 5 | A | $750 | $0 |

### Profile B Net Impact
- Total P&L: **-$2,460**
- Tier A trades (SQS>=5): 2 active, both losers = **-$2,598**
- Tier B trades (SQS=4): 2 active (1W/1L) = **+$138**
- If all B trades were capped at $250: **-$728** (improvement of +$1,732)

### CRWG — The Repeat Offender
CRWG appears **7 times** across the backtest period on Profile B. It scored SQS=4 five times ($250 risk) and SQS=5 twice ($750 risk). The only time it had a real trade at $750, it lost $1,572. This stock alone accounts for 64% of Profile B's total losses.
