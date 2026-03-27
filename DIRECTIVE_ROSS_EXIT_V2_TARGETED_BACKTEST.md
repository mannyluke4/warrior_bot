# Directive: Ross Exit V2 — Targeted Backtest Against Ross Overlap Stocks

## Priority: IMMEDIATE
## Owner: CC
## Created: 2026-03-23
## Context: Exit V2 validation — Phase 1 (exit timing only, NOT scanner)

---

## Objective

Run targeted backtests on every Jan 2025 stock where our scanner overlapped with Ross Cameron's trades. Compare V1 baseline (ross exit OFF) vs V2 (ross exit ON) to validate that exit timing has improved.

**This is NOT a full megatest.** We're testing 9 specific symbol-dates where we have a direct Ross comparison. Once exit timing is confirmed, we run YTD. Scanner improvement is Phase 2.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin main
```

Confirm ross_exit.py has the V2 changes (tiers reordered: candles first, backstops last; topping tail added; CUC requires ≥2 consecutive higher-highs; backstops soften to partial_50 above 5R).

---

## Test Matrix

For each stock below, run TWO tests:
1. **Baseline** (Ross exit OFF): `WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1`
2. **V2** (Ross exit ON): `WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1`

### Priority 1 — THE Case Studies (exit timing is everything here)

These are stocks where bot and Ross had similar entries but wildly different exits.

| # | Date | Symbol | Scanner Rank | Bot Entry | Bot P&L (baseline) | Ross P&L | Gap | Why It Matters |
|---|------|--------|-------------|-----------|-------------------|----------|-----|----------------|
| 1 | 2025-01-24 | ALUR | #1 (0.809) | $7.04/$8.04 | +$1,046 (3 trades) | +$47,000 | 45x | Bot exited sq_target_hit at $8.40; Ross rode to $20. THE case study for exit V2. |
| 2 | 2025-01-14 | AIFF | #1 (0.766) | $2.04/$4.21/$4.61 | +$2,148 (4 trades) | -$2,000 | Bot won | Bot already outperforms via squeeze targets. V2 should hold runners longer. |
| 3 | 2025-01-21 | INM | #1 (1.027) | $7.04 | +$2,405 (1 trade) | +$12,000 | 5x | Bot hit sq_target_hit early; Ross rode full squeeze. |
| 4 | 2025-01-10 | VMAR | #1 (0.891) | $2.04/$3.04/$3.74 | +$826 (3 trades) | +$1,361 | 1.6x | Closest to parity — test V2 doesn't regress. |

### Priority 2 — Exit Pattern Validation

| # | Date | Symbol | Scanner Rank | Bot Entry | Bot P&L (baseline) | Ross P&L | Why It Matters |
|---|------|--------|-------------|-----------|-------------------|----------|----------------|
| 5 | 2025-01-29 | SLXN | #1 (0.587) | $2.04/$2.30/$2.43 | +$243 (3 trades) | ~+$5,000 | Bot: para_trail + TW exits. V2 should replace with candle signals. |
| 6 | 2025-01-28 | YIBO | #1 (0.712) | $3.57/$5.04 | -$296 (2 trades) | +$5,724 | Bot: max_loss + para_trail. Worst outcome — V2 should improve. |
| 7 | 2025-01-16 | WHLR | #2 (0.782) | $4.04 | +$31 (1 trade) | +$3,800 | Bot: para_trail exit same minute. Classic 10s noise exit. |
| 8 | 2025-01-13 | ATPC | #1 (1.026) | $2.69 | -$18 (1 trade) | ~BE | Small trade — V2 should at least not make it worse. |
| 9 | 2025-01-02 | AEI | #1 (0.96) | (traded ORIS) | -$313 (3 ORIS trades) | +$852 (AEI) | Scanner found AEI #1 but bot traded #3 (ORIS). Limited exit test but baseline. |

---

## Commands

**IMPORTANT:** Save tick cache! Add `--tick-cache tick_cache/` to every run. Jan 2025 has ZERO cached ticks. Every fetch from Databento should be cached for future use.

### Run each pair (baseline then V2):

```bash
# --- ALUR 2025-01-24 (THE case study) ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py ALUR 2025-01-24 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/ALUR_2025-01-24_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py ALUR 2025-01-24 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/ALUR_2025-01-24_ross_v2.log

# --- AIFF 2025-01-14 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py AIFF 2025-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/AIFF_2025-01-14_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py AIFF 2025-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/AIFF_2025-01-14_ross_v2.log

# --- INM 2025-01-21 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py INM 2025-01-21 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/INM_2025-01-21_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py INM 2025-01-21 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/INM_2025-01-21_ross_v2.log

# --- VMAR 2025-01-10 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py VMAR 2025-01-10 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/VMAR_2025-01-10_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py VMAR 2025-01-10 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/VMAR_2025-01-10_ross_v2.log

# --- SLXN 2025-01-29 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py SLXN 2025-01-29 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/SLXN_2025-01-29_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py SLXN 2025-01-29 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/SLXN_2025-01-29_ross_v2.log

# --- YIBO 2025-01-28 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py YIBO 2025-01-28 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/YIBO_2025-01-28_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py YIBO 2025-01-28 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/YIBO_2025-01-28_ross_v2.log

# --- WHLR 2025-01-16 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py WHLR 2025-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/WHLR_2025-01-16_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py WHLR 2025-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/WHLR_2025-01-16_ross_v2.log

# --- ATPC 2025-01-13 ---
WB_ROSS_EXIT_ENABLED=0 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py ATPC 2025-01-13 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/ATPC_2025-01-13_baseline.log

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py ATPC 2025-01-13 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/ATPC_2025-01-13_ross_v2.log
```

### Also run standard regression:

```bash
WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/

WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 \
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

Expected: VERO +$18,583, ROLR +$6,444 (V2 should not regress these).

---

## Success Criteria

### Primary (exit timing improved):
- **ALUR V2 P&L >> $1,046 baseline** — This is THE test. Ross made $47K. If V2 holds through the sq_target_hit level and rides candle signals instead, we should see dramatically better numbers.
- **INM V2 P&L >> $2,405 baseline** — Same pattern: sq_target_hit cut the runner early.
- **WHLR V2 P&L >> $31 baseline** — para_trail exit in same minute as entry should be eliminated by 1m candle signals.
- **YIBO V2 P&L > -$296 baseline** — max_loss + para_trail. V2 should at minimum reduce loss.

### Secondary (no regression):
- **AIFF V2 ≥ $2,148 baseline** — Bot already won here. V2 should maintain or improve.
- **VMAR V2 ≥ $826 baseline** — Close to parity already. Don't regress.
- **VERO/ROLR regression passes** — Standard regression targets unchanged.

### What to Look For in Verbose Logs:
1. **Ross exit signals firing**: Look for `ross_doji_partial`, `ross_topping_tail_warning`, `ross_cuc_exit`, `ross_gravestone_doji`, `ross_shooting_star` in exit reasons
2. **Structural stop ratcheting**: `new_structural_stop` values in logs — should trail up with green 1m candles
3. **Backstop timing**: `ross_vwap_break`, `ross_ema20_break`, `ross_macd_negative` should fire AFTER candle signals (not before)
4. **Partial exits**: `partial_50` on warning signals, then `full_100` on confirmation — not all-or-nothing

---

## Recap Format

Write results to `cowork_reports/2026-03-23_ross_v2_targeted_backtest.md`:

```markdown
# CC Report: Ross Exit V2 Targeted Backtest — Jan 2025 Overlap Stocks
## Date: 2026-03-23

### Results Table

| Symbol | Date | Baseline P&L | V2 P&L | Delta | Ross P&L | V2/Ross % | Key Exit Signals |
|--------|------|-------------|--------|-------|----------|-----------|------------------|
| ALUR | 2025-01-24 | +$1,046 | ??? | ??? | +$47,000 | ???% | ??? |
| ... | ... | ... | ... | ... | ... | ... | ... |

### Regression
- VERO: ???
- ROLR: ???

### Key Observations
<What changed between baseline and V2 for each stock>

### Verbose Log Summary
<For each Priority 1 stock: what signals fired, when, and how they compared to baseline exit timing>
```

---

## Post-Flight

```bash
# Cache all the tick data!
git add tick_cache/ verbose_logs/ cowork_reports/
git commit -m "Ross Exit V2 targeted backtest: 9 Jan 2025 overlap stocks + tick cache

Baseline vs V2 comparison on stocks where scanner overlapped with Ross Cameron.
Priority 1: ALUR, AIFF, INM, VMAR (exit timing case studies)
Priority 2: SLXN, YIBO, WHLR, ATPC (pattern validation)
Tick cache saved for all Jan 2025 fetches.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## What Comes Next (DO NOT DO YET)

1. **If V2 passes targeted tests** → Run YTD backtest (2026 Jan-Mar) with V2 enabled
2. **Phase 2: Scanner improvement** — Jan 2025 overlap was only 7.4% (5 of 68 Ross tickers). This is the bigger problem but requires different work (scanner tuning, not exit logic).
3. **Full year backtest** — Only AFTER scanner is fixed. No point caching a year of data if we're missing 92% of the plays.

---

*Directive written by Cowork — 2026-03-23*
*Based on cross-reference of 19 Jan 2025 Ross recap comparisons against megatest V2 state data*
