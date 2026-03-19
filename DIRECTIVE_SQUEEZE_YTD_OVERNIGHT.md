# Directive: Squeeze V2 — Full 55-Day YTD Overnight Backtest

## Priority: HIGH
## Owner: CC
## Created: 2026-03-19

---

## Context

Squeeze V2 is validated on 4 stocks with spectacular results (+58% over MP-only). Now we need
the definitive test: run the full 55-day YTD backtest with squeeze enabled to see how many
opportunities exist, validate the fixes at scale, and surface any new edge cases.

### V2 Validation Results (4-stock)
| Stock | MP-Only | Squeeze V2 | Delta |
|-------|---------|-----------|-------|
| ARTL | +$922 | +$5,275 | +$4,353 |
| VERO | +$18,583 | +$20,922 | +$2,339 |
| ROLR | +$6,444 | +$16,195 | +$9,751 |
| SXTC | +$2,213 | +$2,213 | $0 |
| **Total** | **$28,162** | **$44,605** | **+$16,443** |

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin v6-dynamic-sizing
```

---

## Phase 1: Add Squeeze V2 Env Vars to YTD Runner

In `run_ytd_v2_backtest.py`, add squeeze V2 env vars to `ENV_BASE`:

```python
ENV_BASE = {
    # ... existing vars ...

    # Strategy 2: Squeeze V2 (all gated, conservative defaults)
    "WB_SQUEEZE_ENABLED": "1",
    "WB_SQ_VOL_MULT": "3.0",
    "WB_SQ_MIN_BAR_VOL": "50000",
    "WB_SQ_MIN_BODY_PCT": "1.5",
    "WB_SQ_PRIME_BARS": "3",
    "WB_SQ_MAX_R": "0.80",
    "WB_SQ_LEVEL_PRIORITY": "pm_high,whole_dollar,pdh",
    "WB_SQ_PROBE_SIZE_MULT": "0.5",
    "WB_SQ_MAX_ATTEMPTS": "3",
    "WB_SQ_PARA_ENABLED": "1",
    "WB_SQ_PARA_STOP_OFFSET": "0.10",
    "WB_SQ_PARA_TRAIL_R": "1.0",
    "WB_SQ_NEW_HOD_REQUIRED": "1",
    "WB_SQ_MAX_LOSS_DOLLARS": "500",
    "WB_SQ_TARGET_R": "2.0",
    "WB_SQ_CORE_PCT": "75",
    "WB_SQ_RUNNER_TRAIL_R": "2.5",
    "WB_SQ_TRAIL_R": "1.5",
    "WB_SQ_STALL_BARS": "5",
    "WB_SQ_VWAP_EXIT": "1",
    "WB_SQ_PM_CONFIDENCE": "1",
}
```

---

## Phase 2: Fix setup_type Parsing in Trade Results

The runner currently hardcodes `"setup_type": "micro_pullback"` for all trades (line ~225).
We need to detect squeeze trades from the sim output.

### Option A: Parse from exit reason
Squeeze trades have exit reasons starting with `sq_` (e.g., `sq_target_hit`, `sq_para_trail_exit`,
`sq_dollar_loss_cap`, `sq_hard_stop`, `sq_stall_exit`, `sq_vwap_loss`).

```python
# In run_sim(), when building trade dict:
reason = m.group(8)
setup_type = "squeeze" if reason.startswith("sq_") else "micro_pullback"
trades.append({
    ...
    "setup_type": setup_type,
})
```

### Option B: Parse from verbose output
If sim output includes `setup_type=squeeze` in the ENTRY line, parse that.
Option A is simpler and should work for all cases.

### Why it matters
The summary report should distinguish MP vs squeeze trades so we can see:
- How many squeeze trades fired per day
- Squeeze win rate vs MP win rate
- Squeeze avg R-mult vs MP avg R-mult
- Which stocks had squeeze activity

---

## Phase 3: Add Squeeze Stats to Summary Report

In the final summary, add a breakdown by strategy type:

```
=== Strategy Breakdown ===
MP trades: X  |  Wins: Y  |  Win Rate: Z%  |  Total P&L: $X  |  Avg R: X.XR
SQ trades: X  |  Wins: Y  |  Win Rate: Z%  |  Total P&L: $X  |  Avg R: X.XR
```

---

## Phase 4: Run A/B Comparison

We want to compare squeeze ON vs squeeze OFF to measure the exact delta.

### Run 1: MP-only baseline (if not cached from last run)
The existing `ytd_v2_backtest_state.json` should have the MP-only results. If it does,
skip this and just use the cached data. If the state file doesn't exist or needs refresh:
```bash
# With squeeze OFF (remove WB_SQUEEZE_ENABLED from ENV_BASE or set to "0")
python run_ytd_v2_backtest.py 2>&1 | tee ytd_v2_mp_only.log
cp ytd_v2_backtest_state.json ytd_v2_backtest_state_mp_only.json
```

### Run 2: Squeeze V2 enabled
```bash
# With squeeze ON (all V2 vars in ENV_BASE as shown in Phase 1)
# Clear or rename state file so it runs fresh
mv ytd_v2_backtest_state.json ytd_v2_backtest_state_mp_only_backup.json
python run_ytd_v2_backtest.py 2>&1 | tee ytd_v2_squeeze_v2.log
cp ytd_v2_backtest_state.json ytd_v2_backtest_state_squeeze_v2.json
```

### Important: Don't Delete the MP-only State File
We need both for comparison. Save them with descriptive names.

---

## Phase 5: Regression Check

Before the overnight run, verify regression still passes with squeeze OFF:
```bash
WB_SQUEEZE_ENABLED=0 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_SQUEEZE_ENABLED=0 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

Then verify 4-stock squeeze V2 results match what we validated:
```bash
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$5,275 (2 trades)

WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$20,922 (4 trades)
```

---

## Expected Outcomes

### What we're looking for in the 55-day results:
1. **Squeeze frequency**: How many trading days have squeeze activity? (probably 10-30%)
2. **Win rate**: Should be >50% given probe sizing and HOD gate
3. **Avg R-mult**: Parabolic winners should produce 5-10R+ when they hit
4. **Delta vs MP-only**: Net P&L improvement. The 4-stock test showed +58% — full YTD will normalize this.
5. **New edge cases**: Any stocks where squeeze hurts (bad entries, stop blow-throughs)
6. **Dollar cap effectiveness**: How many times does the $500 cap fire? What would losses be without it?

### What we might need to tune:
- `WB_SQ_VOL_MULT=3.0` — might need 4x or 5x if too many false triggers
- `WB_SQ_MAX_LOSS_DOLLARS=500` — might need higher if it clips too many at breakeven
- `WB_SQ_MAX_ATTEMPTS=3` — might need 2 if attempts 2-3 are net losers

---

## Post-Flight

```bash
git add run_ytd_v2_backtest.py ytd_v2_*.log ytd_v2_backtest_state*.json
git commit -m "Squeeze V2: Full 55-day YTD backtest with squeeze enabled

Added squeeze V2 env vars to run_ytd_v2_backtest.py ENV_BASE.
Fixed setup_type parsing to distinguish squeeze vs MP trades.
Added strategy breakdown to summary report.
Results saved in ytd_v2_backtest_state_squeeze_v2.json.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

## Notes for CC

- Phase 1 is the critical code change — add env vars to ENV_BASE
- Phase 2 is important for analysis — we need to know which trades are squeeze
- The overnight run will take ~2-4 hours depending on tick cache hits
- If a fresh date backtest is still running, let it finish first
- Save BOTH state files (MP-only and squeeze V2) — we need them for the summary
- The `WB_SQUEEZE_ENABLED=1` in ENV_BASE means ALL 55 days will have squeeze active
- This is the big one — the data from this run drives all next decisions
