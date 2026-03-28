# DIRECTIVE: CT Backtest Validation — Prove It Before Enabling Live

**Date:** 2026-03-28  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — Must pass before CT goes live  
**Branch:** `v2-ibkr-migration`

---

## Goal

Validate that the post-squeeze continuation strategy (CT):
1. Does NOT degrade existing squeeze performance (regression tests)
2. Adds incremental P&L on multi-wave stocks (value-add tests)
3. Produces positive CT-only trade P&L with >50% win rate (standalone quality)

---

## Test 1: VERO Regression (SQ cascade stock — CT must defer)

VERO is a cascading squeeze — SQ fires multiple times in sequence. CT must stay deferred the entire time because SQ is never IDLE during the cascade.

```bash
# Baseline (SQ-only)
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 \
python3 simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

# With CT enabled
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 \
python3 simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Pass:** Both produce identical P&L (+$15,692). CT should log `CT DEFERRED: SQ has priority` on every attempt. Zero CT trades.

---

## Test 2: ROLR Regression (another SQ cascade)

```bash
# Baseline
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 \
python3 simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/

# With CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 \
python3 simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Pass:** Both produce identical P&L (+$6,444 or current IBKR baseline). Zero CT trades.

---

## Test 3: EEIQ Validation (THE key test — Ross made $37.8K, we made $1.6K)

EEIQ March 26 is the poster child. One squeeze, then multiple continuation waves. This is where CT should shine.

```bash
# Baseline (SQ-only)
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose

# With CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 \
python3 simulate.py EEIQ 2026-03-26 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

**Pass:** SQ+CT P&L > SQ-only P&L. Look for CT_ARMED and CT_ENTRY in the verbose output. If CT fires at least one re-entry with positive P&L, that's validation.

**If CT doesn't fire:** Check verbose output for CT_REJECT reasons. Common issues:
- `CT_REJECT: MACD negative` — pullback was too deep, MACD crossed below zero
- `CT_REJECT: pullback volume too high` — volume didn't decay enough
- `CT_REJECT: price below VWAP` — pullback went below VWAP
- `CT_RESET: pullback too deep` — retrace exceeded 50% of squeeze move
- `CT DEFERRED: SQ has priority` — SQ was still active (expected on cascading stocks)

If it rejects on every pullback, the gates may be too tight for EEIQ's specific pattern. Note which gate rejected and we'll tune.

**NOTE:** EEIQ tick data may need to be fetched first if not already cached:
```bash
python3 ibkr_tick_fetcher.py EEIQ 2026-03-26 --start 07:00 --end 12:00
```

---

## Test 4: NPT Validation (Feb 3 — $65K squeeze day)

NPT was the biggest single-day P&L in the YTD backtest (+$65,765). Check if CT finds continuation opportunities after the initial squeeze.

```bash
# Baseline
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 \
python3 simulate.py NPT 2026-02-03 07:00 12:00 --ticks --tick-cache tick_cache/

# With CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 \
python3 simulate.py NPT 2026-02-03 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

**Pass:** SQ+CT ≥ SQ-only. CT adds or stays neutral. If NPT was a one-wave stock (no good pullback), CT should stay idle — that's fine.

---

## Test 5: CRE Validation (Mar 6 — $33.7K day)

```bash
# Baseline
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 \
python3 simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/

# With CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 \
python3 simulate.py CRE 2026-03-06 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

**Pass:** SQ+CT ≥ SQ-only.

---

## Test 6: Full YTD A/B (the definitive test)

Run the full Jan 2–Mar 27 YTD backtest in both modes. This is the final gate.

```bash
# Config A: SQ-only (baseline)
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=0 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 run_backtest_v2.py --start 2026-01-02 --end 2026-03-27 \
  --label "ytd_sq_only" --equity 30000

# Config B: SQ + CT
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 WB_MP_ENABLED=0 WB_MP_V2_ENABLED=0 \
python3 run_backtest_v2.py --start 2026-01-02 --end 2026-03-27 \
  --label "ytd_sq_ct" --equity 30000
```

**Pass criteria:**

| Metric | Requirement |
|--------|------------|
| Config B total P&L | > Config A ($264,594 baseline) |
| SQ trades in Config B | Identical to Config A (no regression) |
| CT trades win rate | > 50% |
| CT trades total P&L | > $0 |
| No SQ trade P&L changed | Compare trade-by-trade — every SQ trade must match exactly |

---

## Test 7: Quiet Day Sanity (CT stays dormant)

Pick a day with no squeeze triggers. CT should do absolutely nothing.

```bash
WB_SQUEEZE_ENABLED=1 WB_CT_ENABLED=1 \
python3 simulate.py ONCO 2026-03-27 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose
```

**Pass:** 0 trades. No CT messages (or only CT_COOLDOWN if something weird armed). CT stays IDLE because no squeeze ever fired.

---

## Results Template

After running all tests, fill in this table:

| Test | SQ-Only P&L | SQ+CT P&L | Delta | CT Trades | CT WR | Pass? |
|------|------------|-----------|-------|-----------|-------|-------|
| VERO | | | $0 expected | 0 expected | N/A | |
| ROLR | | | $0 expected | 0 expected | N/A | |
| EEIQ | | | >$0 expected | ≥1 expected | | |
| NPT | | | ≥$0 expected | | | |
| CRE | | | ≥$0 expected | | | |
| YTD | | | >$0 expected | | >50% | |
| ONCO quiet | $0 | $0 | $0 | 0 | N/A | |

**Deployment gate:** Tests 1-2 (regression) MUST pass. Test 6 (YTD) should show positive CT delta. If Test 3 (EEIQ) shows CT doesn't fire, that's diagnostic info — note the reject reasons and we'll tune.

---

## If CT Gates Are Too Tight

If CT rejects every pullback across the YTD, try relaxing one gate at a time:

```bash
# Relax MACD gate (most likely to be too strict)
WB_CT_REQUIRE_MACD=0

# Relax volume decay threshold (allow pullback vol up to 80% of squeeze vol)
WB_CT_MIN_VOL_DECAY=0.80

# Relax retrace depth (allow up to 65% pullback)
WB_CT_MAX_RETRACE_PCT=65

# Allow longer pullbacks (up to 8 bars)
WB_CT_MAX_PULLBACK_BARS=8
```

Test each relaxation individually — don't relax all at once or we're back to MP territory.

---

## If CT Gates Are Too Loose

If CT fires too many losers, tighten:

```bash
# Tighter volume decay (pullback vol must be < 30% of squeeze vol)
WB_CT_MIN_VOL_DECAY=0.30

# Require all gates (default, but verify)
WB_CT_REQUIRE_VWAP=1
WB_CT_REQUIRE_EMA=1
WB_CT_REQUIRE_MACD=1

# Only 1 re-entry per session (more conservative)
WB_CT_MAX_REENTRIES=1
```

---

## Save Results

Save the detailed results to `backtest_status/` and `cowork_reports/` as usual:

```
backtest_status/ct_validation_vero.md
backtest_status/ct_validation_eeiq.md
backtest_status/ytd_sq_ct.md
cowork_reports/2026-03-28_ct_validation_results.md
```
