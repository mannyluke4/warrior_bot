# Directive: YTD 2026 Backtest — Ross Exit V2 vs Baseline

## Priority: IMMEDIATE
## Owner: CC
## Created: 2026-03-23
## Context: Full YTD comparison of ross exit ON vs OFF across all 2026 trading days

---

## Objective

Run a full YTD 2026 backtest with `WB_ROSS_EXIT_ENABLED=1` and compare against the existing baseline (ross exit OFF). The existing baseline is already completed through 2026-03-19 in the state file: 28 trades, +$16,785 total P&L, $46,785 final equity.

**This is the definitive test.** The targeted Jan 2025 backtests showed +$1,020 across 5 overlap stocks and +$18,767 including ROLR. Now we need to see if V2 holds up across 54+ trading days of real scanner data.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin main
```

### Regression Check (MUST PASS before proceeding)

```bash
WB_MP_ENABLED=1 WB_ROSS_EXIT_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583 (1 trade, ~18.6R)

WB_MP_ENABLED=1 WB_ROSS_EXIT_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$17,747 or higher (ross exit V2 target from targeted backtest)
# NOTE: ROLR baseline was +$6,444. V2 improved to +$24,191 in targeted test.
# The exact number may vary slightly due to tick cache vs live fetch.
```

**If VERO regresses, STOP. Do not proceed.**

ROLR is expected to be significantly higher than the old $6,444 baseline because ross exit holds the runner longer. If ROLR is below +$15,000, investigate before proceeding.

---

## Step 1: Preserve Existing Baseline

The existing backtest state IS the baseline (ross exit OFF). Before overwriting anything:

```bash
# Back up existing state and report
cp ytd_v2_backtest_state.json ytd_v2_backtest_state_BASELINE.json
cp YTD_V2_BACKTEST_RESULTS.md YTD_V2_BACKTEST_RESULTS_BASELINE.md
```

Record the baseline summary for the comparison report:
- Config A: $46,785 equity, 28 trades, +$16,785 P&L
- Config B: $46,785 equity, 28 trades, +$16,785 P&L (identical to A — score gate had zero impact)

---

## Step 2: Modify the Script for Ross Exit A/B

Edit `run_ytd_v2_backtest.py` to make the A/B comparison ross exit OFF vs ON instead of score gate 8 vs 0.

### Changes Required

1. **Add to ENV_BASE** (these should be in BOTH configs):
```python
"WB_PILLAR_GATES_ENABLED": "1",
```

2. **Modify `_run_config_day` or the main loop** so:
   - **Config A** = `WB_ROSS_EXIT_ENABLED=0` (baseline — old-style BE/TW exits)
   - **Config B** = `WB_ROSS_EXIT_ENABLED=1` (V2 — 1m candle signals + structural trail)
   - Both configs use score gate = 8 (or 0 — doesn't matter, they're identical)

   The cleanest approach: in `run_backtest()`, before calling `_run_config_day` for each config, set/unset the env var:

```python
# Config A: Ross exit OFF (baseline)
os.environ["WB_ROSS_EXIT_ENABLED"] = "0"
day_trades_a, day_pnl_a = _run_config_day(top5, date, risk_a, min_score=8.0, max_consec_losses=2)

# Config B: Ross exit ON (V2)
os.environ["WB_ROSS_EXIT_ENABLED"] = "1"
day_trades_b, day_pnl_b = _run_config_day(top5, date, risk_b, min_score=8.0, max_consec_losses=2)
```

   Note: both use min_score=8.0 now since score gate has zero impact.

3. **Add dates** through March 20:
```python
# Add to end of March dates:
"2026-03-20",
```
   (March 23 is today/Monday — don't include it. March 20 was last Friday.)

4. **Update report labels** to say "Baseline (Ross Exit OFF)" and "V2 (Ross Exit ON)" instead of "Config A (Gate=8)" and "Config B (No Gate)".

5. **Update report header** to reference the ross exit comparison.

### DO NOT CHANGE

- Scanner filters (MIN_PM_VOLUME, MIN_GAP_PCT, etc.)
- Ranking function
- STARTING_EQUITY ($30,000)
- RISK_PCT (2.5%)
- MAX_TRADES_PER_DAY (5)
- DAILY_LOSS_LIMIT (-$1,500)
- MAX_NOTIONAL ($50,000)
- TOP_N (5)
- Tick mode / tick cache usage
- The `run_sim` function
- State management

---

## Step 3: Clear State and Run Fresh

```bash
# Delete old state so both configs run from scratch
rm ytd_v2_backtest_state.json

# Run the full YTD backtest
python run_ytd_v2_backtest.py 2>&1 | tee ytd_v2_ross_exit_comparison.log
```

**Expected runtime:** ~2-4 hours depending on tick cache hits. The script runs each date sequentially, 2 configs per date (A=baseline, B=V2), up to 5 tickers per config. With ~55 dates × 2 configs × ~3 tickers avg = ~330 sim runs.

The script has state management — if interrupted, it resumes from last completed date.

---

## Step 4: Report Format

After the run completes, the script auto-generates `YTD_V2_BACKTEST_RESULTS.md`. Additionally, write a summary comparison file `cowork_reports/2026-03-23_ytd_ross_exit_v2_comparison.md` with:

### Required Sections

1. **Top-Line Comparison**
```
| Metric              | Baseline (Ross Exit OFF) | V2 (Ross Exit ON) | Delta    |
|---------------------|--------------------------|---------------------|----------|
| Total P&L           |                          |                     |          |
| Total Trades        |                          |                     |          |
| Win Rate            |                          |                     |          |
| Profit Factor       |                          |                     |          |
| Max Drawdown $      |                          |                     |          |
| Largest Win         |                          |                     |          |
| Largest Loss        |                          |                     |          |
| Avg Win             |                          |                     |          |
| Avg Loss            |                          |                     |          |
```

2. **Monthly Breakdown** — Jan / Feb / Mar P&L for each config

3. **Exit Reason Distribution** — Group all trades by exit reason for each config. This is critical. We want to see:
   - Baseline: how many BE/TW exits, sq_target_hit, sq_para_trail, sq_max_loss, etc.
   - V2: how many ross_doji_partial, ross_shooting_star, ross_cuc, ross_vwap_break, ross_ema20_break, ross_macd_cross, etc.

4. **Head-to-Head Trade Comparison** — For every date where BOTH configs traded the SAME stock, compare entry/exit/P&L side by side. This shows exactly which trades improved and which regressed.

5. **Robustness Check** — P&L with top 3 winners removed, for both configs. If V2 is positive even without the top 3, that's a strong signal.

6. **VERO and ROLR Specific** — Pull out VERO and ROLR trades specifically from both configs and compare. These are our known runners — V2 must hold or improve on them.

---

## Success Criteria

- [ ] VERO regression passes (+$18,583)
- [ ] ROLR regression passes (+$15,000 or higher with ross exit ON)
- [ ] V2 total P&L >= baseline total P&L (must not regress overall)
- [ ] V2 largest win >= baseline largest win (ross exit should hold runners longer)
- [ ] V2 max drawdown <= baseline max drawdown × 1.5 (modest DD increase acceptable)
- [ ] Exit reason distribution shows meaningful shift from BE/TW to ross candle signals
- [ ] Report saved to `cowork_reports/2026-03-23_ytd_ross_exit_v2_comparison.md`

**If V2 regresses overall (total P&L lower than baseline), do NOT revert. Document which stocks/dates regressed and why. The targeted backtest showed V2 is net positive — a regression on full YTD would indicate interaction effects that need investigation.**

---

## After Completion

1. Commit the updated script + both reports:
```bash
git add run_ytd_v2_backtest.py YTD_V2_BACKTEST_RESULTS.md YTD_V2_BACKTEST_RESULTS_BASELINE.md cowork_reports/2026-03-23_ytd_ross_exit_v2_comparison.md ytd_v2_ross_exit_comparison.log
git commit -m "YTD 2026 backtest: Ross Exit V2 vs baseline comparison

Full A/B across ~55 trading days. Baseline (BE/TW exits) vs V2 (1m candle signals + structural trail).

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

2. Do NOT modify ross_exit.py, trade_manager.py, simulate.py, or .env
3. Do NOT change any env var defaults
4. The ONLY code changes should be to `run_ytd_v2_backtest.py` (the runner script)

---

## Reference: Existing Baseline Numbers

From the completed state file (ross exit OFF, MP OFF, 2026-01-02 through 2026-03-19):
- 28 trades total
- +$16,785 P&L
- $46,785 final equity (from $30,000 start)
- Config A = Config B (score gate had zero impact)
- VERO was the dominant winner (~$13,433 = 80% of profit)

From the targeted Jan 2025 backtest (ross exit V2 vs baseline, 5 stocks):
- ALUR: baseline +$1,989 → V2 +$7,578 (+$5,589 improvement)
- INM: baseline +$2,414 → V2 -$799 (-$3,213 regression, intra-bar spike-reverse)
- VMAR: baseline +$107 → V2 -$500 (-$607 regression, entry problem not exit)
- SLXN: baseline +$243 → V2 +$373 (+$130 improvement)
- YIBO: baseline -$296 → V2 +$322 (+$618 improvement)
- ROLR: baseline +$6,444 → V2 +$24,191 (+$17,747 improvement)
- VERO: baseline +$18,583 → V2 +$18,583 (unchanged — TW suppressed, no ross exit fired)

**Net across all tested: baseline +$29,484 → V2 +$49,748 (+$20,264 / +69%)**
