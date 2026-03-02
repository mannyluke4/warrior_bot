# Warrior Bot — Project Status Report
## For Claude Code Context Recovery — March 2, 2026

---

## Executive Summary

We've been running a **Stock Behavior Study** to figure out what types of stocks the bot performs best on, and how to adapt its exit strategy per stock type. The study is in **Phase 2.2** across 4 commits over the past week. The bot is now running live with the classifier gate ON and suppression OFF.

---

## What Exists in the Repo (Key Commits)

| Commit | Date | What It Did |
|--------|------|-------------|
| `025182ba` | Feb 27 | Expanded study: 108-stock batch run + analysis improvements |
| `8f64b87` | Feb 27 | Phase 2: Created classifier.py, validate_classifier.py, wired into simulate.py |
| `aa0e12d` | Feb 27 | Phase 2.1: Tuned classifier thresholds (VWAP floors, wider gate) |
| `0b48c24` | Feb 27 | Phase 2.2: Activated exit suppression, ran 3-way comparison |

---

## Current Live Config (.env)

```
WB_EXIT_MODE=signal
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_CLASSIFIER_VWAP_GATE=7
WB_CLASSIFIER_CASC_VWAP_MIN=8
WB_CLASSIFIER_SMOOTH_VWAP_MIN=10
WB_CLASSIFIER_RECLASS_ENABLED=1
```

**Translation**: Classifier is ON (gate filters bad stocks), but exit suppression is OFF (BE/TW exits fire normally). Signal mode cascading is fully preserved.

---

## The Study — What We Found (108 Stocks, Jan + Feb 2026)

### Market Context
- **January 2026** (hot market): +$18,270 total, avg +$554/stock
- **February 2026** (cold market): -$13,678 total, avg -$489/stock
- Combined: +$4,592 across 108 stocks, 133 trades

### Key Findings

**1. VWAP distance is the #1 predictor of success (r = +0.306)**
- VWAP >= 10%: avg +$995/stock
- VWAP < 10%: avg -$477/stock

**2. AVOID gate works** — stocks with VWAP < 7%, range < 10%, NH < 2:
- Gate saves +$2,361 net (blocks $2,834 in losses, misses $473 in profits)
- Only 1 false positive (FLYX +$473)

**3. K-Means clusters identified 5 stock behavior types:**

| Cluster | Label | N | Avg P&L |
|---------|-------|---|---------|
| C0 | Slow Grinder | 18 | -$860 |
| C1 | Choppy Fighter | 13 | -$236 |
| C2 | One Big Move | 8 | +$907 |
| C3 | Cascading Runner | 12 | +$594 |
| C4 | Early Bird | 10 | +$875 |

**4. BE exits leave money on the table**
- 93% of the time, the stock went higher after a BE exit
- Average 80% of the move left on table
- But BE suppression is tricky (see Phase 2.2 results below)

**5. Hold time is destiny**
- Instant exits (0s): -$251 avg, 18% win rate
- Medium (1-5m): +$199 avg, 37% win rate
- Long (5m+): +$1,305 avg, 54% win rate

### Combined Filters That Work in BOTH Markets
- VWAP >= 10% + NH >= 3: Jan avg +$2,248, Feb avg +$234 (profitable in cold!)
- VWAP >= 10% + Vol >= 500K: Jan avg +$1,650, Feb avg -$27 (breakeven in cold)

---

## The Classifier (classifier.py)

### Architecture
- **Pre-entry gate**: VWAP < 7% AND range < 10% AND NH < 2 → AVOID
- **Behavior classification** (decision tree at 5-minute snapshot):
  - CASCADING: NH >= 6, PB >= 3, PB depth >= 2%, VWAP >= 8%
  - ONE_BIG_MOVE: VWAP >= 20%, range >= 50%
  - SMOOTH_TREND: NH >= 3, PB <= 1, green ratio >= 0.6, VWAP >= 10%
  - CHOPPY: PB depth >= 10%, green ratio < 0.50
  - EARLY_BIRD: VWAP >= 8%, vol >= 500K
  - UNCERTAIN: fallback
- **Reclassification** at 10m and 15m with more data
- **Exit profiles** per type (suppress_be_under_r, suppress_tw_under_r, trail_atr_mult)

### Exit Profiles

| Type | BE Suppress | TW Suppress | Trail ATR | Max Re-entries |
|------|------------|------------|-----------|----------------|
| cascading | 0.0 (none) | 0.0 (none) | default | 5 |
| one_big_move | 1.5R | 2.0R | 2.0x | 2 |
| smooth_trend | 1.0R | 1.0R | 1.5x | 3 |
| early_bird | 0.5R | 0.5R | 1.2x | 3 |
| choppy | 0.0 (none) | 0.0 (none) | 0.8x | 1 |
| uncertain | 0.0 (none) | 0.0 (none) | 1.0x | 2 |

### Phase 2.1 Tuning Results (retroactive validation)

| Type | Count | Avg P&L |
|------|-------|---------|
| cascading | 5 | +$1,241 |
| one_big_move | 12 | +$330 |
| smooth_trend | 1 | +$1,413 |
| early_bird | 16 | +$561 |
| uncertain | 49 | -$291 |
| avoid | 25 | -$68 |

### Phase 2.2 Suppression Results (PROBLEM)

When we activated BE suppression (removed the `_exit_mode != "signal"` guard):

| Config | Total P&L | vs Baseline |
|--------|-----------|-------------|
| Baseline (OFF) | +$4,592 | — |
| Gate only | +$6,953 | +$2,361 |
| Gate + Suppress | +$2,970 | -$1,621 |

**Suppression was NET NEGATIVE.** Only 3 stocks affected (all one_big_move):
- ALMS: +$3,407 → +$3,776 (+$369) ✓
- HIND: +$1,621 → -$33 (-$1,654) ✗ — 1.5R threshold too high, peaked at 1.4R
- SNSE: +$88 → -$249 (-$337) ✗

**Root cause**: The 1.5R BE suppress threshold for one_big_move is too aggressive. HIND peaked at ~1.4R (just under the threshold), so BE got suppressed, the stock reversed, and a +$1,621 winner became a -$33 loser.

**Early_bird** (0.5R suppress) produced ZERO suppressions — threshold too narrow.

**Why so few affected**: 5-minute snapshots classify far fewer stocks into specific types than the 30-minute hindsight validation. Most stocks look "uncertain" at 5 minutes.

---

## Known Issues / Open Items

### 1. Exit Suppression Thresholds Need Tuning
- one_big_move BE suppress: lower from 1.5R to 0.8-1.0R
- early_bird BE suppress: raise from 0.5R to 0.8R, or disable
- `WB_CLASSIFIER_SUPPRESS_ENABLED` default should be "0" not "1" in simulate.py (line 995)

### 2. 5-Minute Snapshot Classifies Too Few Stocks
- Many stocks are "uncertain" at 5m but clearly typed at 30m
- The 10m/15m reclassification exists but unclear if it's firing effectively
- Need to check reclassification logs

### 3. Entry Timing Problem (NEW — observed live today, March 2)
**Ticker: TURB** — bot entered twice, both times at the exact HOD/PM_HIGH after a big run-up, immediately reversed, BE exit within 60 seconds for losses.

Second trade details:
- Entry: 08:31:53 ET @ $1.46 (HOD=$1.46, PM_HIGH=$1.46, VWAP=$1.20)
- Exit: ~08:32:35 ET @ $1.38 via bearish_engulfing, P&L: -$346
- The stock had already run 21.7% above VWAP before the bot entered
- Entry signal was a breakout of a level that was also the session high — classic top entry

This is an **entry quality problem**, not a classifier problem. The classifier correctly wouldn't avoid TURB (VWAP distance was strong). The issue is the bot entering breakouts at exhausted resistance levels.

### 4. Interactive Brokers Approval Pending
User is about to get approved for IB, which gives access to **Level 2 order book data**. This could directly address the entry timing problem — seeing sell walls, order flow, and liquidity depth before entering. This will be a major future project.

---

## File Map

| File | Purpose |
|------|---------|
| `classifier.py` | StockClassifier class, EXIT_PROFILES, ClassifierResult dataclass |
| `validate_classifier.py` | Retroactive validation against 108-stock study data |
| `simulate.py` | Main simulation engine — classifier integration at lines 993-995, ~1300-1350 (suppression), ~1390-1420 (classification), snapshot_at() method |
| `compare_results.py` | 3-way comparison: baseline vs gate vs gate+suppress |
| `run_study_classifier.sh` | Batch script for classifier-enabled study runs |
| `analyze_study.py` | Study analysis / reporting |
| `study_data/*.json` | Raw per-stock study data (108 stocks) |
| `study_results/` | Baseline study results + tuned validation |
| `study_results_classifier/` | Gate-only batch results |
| `study_results_suppress/` | Gate+suppress batch results |

---

## Regression Benchmarks (MUST ALWAYS PASS)

| Stock | Date | Expected P&L | Notes |
|-------|------|-------------|-------|
| VERO | 2026-01-16 | +$6,890 | Cascading — must be identical with classifier ON or OFF |
| GWAV | 2026-01-16 | +$6,735 | Early_bird — must be identical |
| ANPA | 2026-01-09 | +$2,088 | One_big_move baseline (changes when suppress ON) |

---

## User Preferences (CRITICAL)

- **Signal mode cascading exits must NEVER be suppressed** — this is the bot's core edge
- "I want 100 $6K winners, not one $90K winner every few weeks"
- Scanner appearance TIME matters — if the bot took profits before the stock appeared on scanner, that P&L doesn't count for live
- "We don't care about the initial run. The initial runner sets off our alert, then we take that 9-12k and move on"
- Two parallel workstreams: (1) Live testing/bug finding, (2) Bot refinement/trade mastery
- For anything needing direct machine access, update the project status document with solid direction
- January was hot, February was cold — sample from both to avoid bias

---

## Active Directives in Repo (Claude Code: Execute These)

### 1. L2_DEEP_DIVE_DIRECTIVE.md (HIGH PRIORITY — March 2, 2026)
Full 3-phase plan to test the dormant L2 subsystem:
- **Phase 1**: Quick wins — add 11 missing .env vars, fix exchange auto-detection, verify Databento API
- **Phase 2**: L2 pilot test on 10 stocks (5 winners, 5 losers from Scanner Study 30) — run with and without `--l2`, compare trade-by-trade
- **Phase 3**: Enhancements (HELD until Phase 2 results reviewed)
- **Reference**: L2_INFRASTRUCTURE_AUDIT.md (547-line audit of full L2 codebase)
- **Key constraint**: DO NOT modify l2_signals.py or l2_entry.py in Phase 1 or 2

### 2. QTTB_INVESTIGATION_DIRECTIVE.md (Sent earlier — results NOT yet in repo)
Investigation into QTTB trade behavior. Awaiting Claude Code execution.

---

## Scanner Study 30 Results (March 2, 2026)

30 randomly sampled stocks from scanner data (15 Jan, 15 Feb), backtested using scanner appearance time as sim-start:
- **Total P&L**: -$10,388 across 41 trades (32% WR)
- **January**: -$3,612 (21 trades, 33% WR) — NOT the blowout winners from Study 1 (selection bias exposed)
- **February**: -$6,776 (20 trades, 30% WR)
- **Key insight**: Market month isn't the variable — stock selection quality is

### Pre-Screening Filters Identified
- Float < 10M + Scanner before 8am: best subset (small sample)
- Strategy type micro_pullback outperforms micro_pullback_l2
- Gap% extremes (>50% or <5%) tend to lose

### Why Two Studies Don't Contradict
Study 1 (Friday, 39 stocks) had selection bias — January included hand-picked big winners (APVO +$7.6k, VERO +$6.9k, GWAV +$6.7k) and February was 8/13 stocks from one bad day (Feb 27). Study 2 (Scanner Study 30, random sample) showed both months lose with random selection.

---

## L2 Infrastructure — What We Know

- L2 subsystem is **COMPLETE but dormant** (`WB_ENABLE_L2=0`)
- Touches 4 decision points: score modifier (±4.5), hard gate, impulse/confirmation acceleration, stop enhancement via bid stacking
- L2 exit logic exists but conservative (only fires at imbalance <0.30)
- `simulate.py` supports `--l2` and `--l2-entry` flags for backtesting with Databento historical data
- Databento: XNAS.ITCH dataset, MBP-10 schema, pay-as-you-go ~$1/GB, $125 free credits on signup
- 20 env vars total (9 documented, 11 hidden with code defaults)
- IBKR L2 approval pending — will provide live L2 when approved

---

## Immediate Priorities

1. **EXECUTE L2_DEEP_DIVE_DIRECTIVE.md** — Phase 1 quick wins, then Phase 2 pilot test on 10 stocks
2. **EXECUTE QTTB_INVESTIGATION_DIRECTIVE.md** — if not already done
3. **Fix `WB_CLASSIFIER_SUPPRESS_ENABLED` default** from "1" to "0" in simulate.py line 995
4. After L2 pilot results: decide whether to build filtration gate WITH or WITHOUT L2 pre-screening
5. After filtration gate: expand to full 93+ stock study with combined filters

---

*Report updated by Perplexity Computer — March 2, 2026 1:23 PM MST*
*For Claude Code context recovery — L2 deep dive is the active workstream*
