# Directive: VWAP Reclaim Tuning V2 — Better Test Stocks + Wider Thresholds

## Priority: HIGH
## Created: 2026-03-20 by Cowork (Opus)
## Depends on: VR validation report (Phase 1 regression PASSED, 0 trades on CHNR/ARTL)

---

## Problem

VR detector works mechanically but produced 0 trades on CHNR and ARTL. Root causes:
1. **Wrong test stocks** — Both were first-leg momentum plays (squeeze territory), not dip → reclaim patterns
2. **R-cap too tight** ($0.50) — CHNR's best reclaim had R=$1.04 with 5.1x volume
3. **Reclaim window too short** (3 bars) — CHNR's first reclaim needed >3 minutes

## Solution: Test on actual VWAP reclaim stocks with widened thresholds

---

## Phase 1: Threshold Adjustments

Update these env vars before running ANY VR tests:

```bash
WB_VR_MAX_R=0.80             # Was 0.50. Match squeeze cap. CHNR reclaim at $1.04 still blocked but closer.
WB_VR_MAX_R_PCT=5.0           # Was 3.0%. Small-caps with $5 price can have $0.25 R = 5%.
WB_VR_RECLAIM_WINDOW=5        # Was 3. Give 5 bars (5 min) for new-high confirmation after reclaim.
WB_VR_MAX_BELOW_BARS=20       # Was 10. Real VWAP dips can last 10-20 minutes before reclaim.
WB_VR_MAX_ATTEMPTS=3          # Was 2. Match squeeze. Some stocks need 3 attempts.
```

Leave these unchanged (reasonable as-is):
- `WB_VR_VOL_MULT=1.5` — reclaims are lower-volume than squeezes by definition
- `WB_VR_MIN_BODY_PCT=0.5` — thin wicks should still be rejected
- `WB_VR_MAX_LOSS_DOLLARS=300` — tighter than squeeze is correct for VR
- All exit params — validate before changing

---

## Phase 2: Test Stocks (ALL in tick cache)

Ranked by VWAP reclaim potential (from study data analysis):

### Tier 1: High Confidence VR Candidates

**GRI 2026-01-28** — VR Score: 35.7 (BEST candidate)
- 9 VWAP crosses in 30 min, only 23% of bars above VWAP
- Spent most of session oscillating around VWAP — textbook reclaim territory
- Float: 1.45M, Cache: 428K
- 0 bot trades (MP/squeeze didn't catch it — this is VR's niche)
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py GRI 2026-01-28 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

**APVO 2026-01-09** — VR Score: 24.3
- 5 VWAP crosses, only 27% above VWAP, huge 58% range
- 1 existing trade at 08:05 (entry near $9.45) → +$7,622 winner
- Float: 0.94M, Cache: 204K
- VR could catch additional entries during VWAP oscillation cycles
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py APVO 2026-01-09 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

**CDIO 2026-02-27** — VR Score: 20.7
- 3 VWAP crosses, only 33% above, 1 pullback, 2 existing trades
- 24% gap (Profile A), 1.7M float — classic small-cap gapper
- Trade 1: +$1,042, Trade 2: -$250 — net positive day
- Price at 30m ($6.54) was BELOW price at 10m ($6.97) — dip pattern
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py CDIO 2026-02-27 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

### Tier 2: Medium Confidence

**ACCL 2026-01-16** — VR Score: 18.0
- 2 VWAP crosses, 40% above, 2 pullbacks (avg 19.4% deep!), 80% range
- 2 existing trades both losers — but deep pullbacks = reclaim opportunities
- Float: 2.93M, Cache: 1.1M
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py ACCL 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

**TWG 2026-01-20** — VR Score: 14.3
- 3 VWAP crosses, 87% above, 4 pullbacks (avg 17% deep), 104% range
- Trade log explicitly documents Ross's "VWAP break + inverted H&S" entry
- 0 bot trades (MACD gate blocked) — VR could catch what MP missed
- Float: 0.54M (ultra micro), Cache: 4.0M (lots of tick data)
```bash
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py TWG 2026-01-20 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

### Tier 3: Control / Regression

**ROLR 2026-01-14** — VR Score: 17.7 (REGRESSION stock)
- 2 VWAP crosses, 93% above, 174% range, 5 existing trades
- TARGET: +$6,444 with VR OFF. With VR ON, P&L should be >= $6,444
- Any VR trades are BONUS — must not interfere with MP trades
```bash
# Run TWICE — once VR OFF (regression), once VR ON (additive check)
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/

WB_VR_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ -v
```

**VERO 2026-01-16** — REGRESSION
- TARGET: +$18,583 with VR OFF. With VR ON, must be unchanged.
- VERO stayed above VWAP the entire session (pct_above=1.0) → VR should NEVER trigger
```bash
WB_VR_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

---

## Phase 3: Re-test Original Stocks (with wider thresholds)

Now that thresholds are wider, re-run CHNR and ARTL to see if the 07:44 reclaim (R=$1.04, previously blocked by $0.50 cap) now arms:

```bash
# CHNR — the $1.04 R reclaim at 07:44 should now pass with MAX_R=0.80... wait, $1.04 > $0.80.
# If still blocked, note it — may need parabolic mode for VR (like squeeze has).
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py CHNR 2026-03-19 07:16 12:00 --ticks --tick-cache tick_cache/ -v

# ARTL — wider MAX_BELOW_BARS (20 vs 10) should keep BELOW_VWAP state alive longer
WB_VR_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_VR_MAX_R=0.80 WB_VR_MAX_R_PCT=5.0 WB_VR_RECLAIM_WINDOW=5 WB_VR_MAX_BELOW_BARS=20 WB_VR_MAX_ATTEMPTS=3 \
python simulate.py ARTL 2026-03-18 08:00 12:00 --ticks --tick-cache tick_cache/ -v
```

**Note**: CHNR's best reclaim had R=$1.04. Even with MAX_R=0.80, this is still blocked. If the Tier 1 tests show VR working on other stocks, we may want to add parabolic mode to VR (level-based stop, like squeeze has) as a follow-up.

---

## Phase 4: Report

Write report to `cowork_reports/2026-03-20_vr_tuning_v2.md` with:

1. Regression status (VERO +$18,583, ROLR +$6,444 — must pass)
2. Per-stock results table:

| Stock | Date | VR OFF P&L | VR ON P&L | Delta | VR Trades | VR Events |
|-------|------|-----------|----------|-------|-----------|-----------|
| GRI | 2026-01-28 | ? | ? | ? | ? | ? |
| APVO | 2026-01-09 | ? | ? | ? | ? | ? |
| CDIO | 2026-02-27 | ? | ? | ? | ? | ? |
| ACCL | 2026-01-16 | ? | ? | ? | ? | ? |
| TWG | 2026-01-20 | ? | ? | ? | ? | ? |
| ROLR | 2026-01-14 | ? | ? | ? | ? | ? |
| VERO | 2026-01-16 | ? | ? | ? | ? | ? |
| CHNR | 2026-03-19 | ? | ? | ? | ? | ? |
| ARTL | 2026-03-18 | ? | ? | ? | ? | ? |

3. VR detector log snippets for each stock showing state transitions
4. Whether parabolic mode is needed for VR (if R-cap blocks legitimate entries)
5. Recommended final threshold values

**STOP after Phase 4.** Do NOT run full YTD until Manny reviews.

---

## Why These Stocks Are Better Test Candidates

The original CHNR/ARTL tests failed because both were **first-leg momentum stocks** — they ran straight up with little VWAP oscillation. VR is designed for a different pattern: stocks that run, dip below VWAP, then recover.

The new test stocks were selected by scoring historical data for:
- **VWAP cross count** (how many times price crossed VWAP — higher = more reclaim cycles)
- **% bars above VWAP** (lower = more time below VWAP = more reclaim opportunities)
- **Pullback count and depth** (real dips, not just wicks)
- **Multiple trades** (bot re-entered = stock had recurring setup opportunities)

GRI is the #1 candidate: 9 VWAP crosses, only 23% above VWAP, and the existing bot produced 0 trades. If VR can't find entries on a stock that oscillated around VWAP 9 times, something fundamental needs to change.

---

*Directive by Cowork (Opus) — 2026-03-20*
