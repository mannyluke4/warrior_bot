# DIRECTIVE: Ross Exit V3 — CUC Fix Phase 1

**Date:** 2026-03-23
**From:** Cowork (Opus)
**For:** CC (Sonnet in terminal)
**Priority:** HIGH — this is the next step for Ross Exit refinement

---

## Context

YTD backtest showed V2 (Ross Exit ON) at +$14,910 vs baseline +$25,709. CUC (Candle Under Candle) is the weakest signal: 9 fires, +$1,163 total (+$129 avg), net ~$1,800 drag vs baseline. Five of the nine CUC exits fire on losing or barely-profitable trades where the old BE/TW exits actually performed better.

**We are NOT re-enabling sq_target_hit.** The fix is to make CUC smarter so it stops firing on noise.

## Objective

Add two new CUC gates to `ross_exit.py`, then run a 3-config YTD comparison to find the best CUC settings.

---

## Step 1: Git Pull

```bash
cd ~/warrior_bot && git pull origin main
```

## Step 2: Code Changes in `ross_exit.py`

### 2A: Add new env vars to `__init__`

After line 115 (`self._cuc_min_r = ...`), add:

```python
self._cuc_floor_r = float(os.getenv("WB_ROSS_CUC_FLOOR_R", "0.0"))
self._cuc_min_trade_bars = int(os.getenv("WB_ROSS_CUC_MIN_TRADE_BARS", "0"))
```

**`WB_ROSS_CUC_FLOOR_R`** = minimum R-multiple profit before CUC can fire. Default 0 = current behavior (no floor). When set to e.g. 2.0, CUC only fires if trade is at ≥2R profit.

**`WB_ROSS_CUC_MIN_TRADE_BARS`** = minimum 1m bars the trade must have been open before CUC can fire. Default 0 = current behavior. When set to 5, CUC is suppressed for the first 5 minutes of every trade.

### 2B: Add gate logic to CUC section

In the CUC block (around line 265, inside `if bullish_context:`), BEFORE the existing deep-runner gate, add:

```python
# CUC floor gate: suppress when not yet profitable enough
if self._cuc_floor_r > 0 and in_trade and unrealized_r < self._cuc_floor_r:
    print(
        f"  ROSS_CUC_FLOOR: unrealized={unrealized_r:.1f}R < floor={self._cuc_floor_r:.1f}R"
        f" — suppressing CUC",
        flush=True,
    )
elif self._cuc_min_trade_bars > 0 and self._bars_since_entry < self._cuc_min_trade_bars:
    print(
        f"  ROSS_CUC_MIN_BARS: bars_in_trade={self._bars_since_entry} < min={self._cuc_min_trade_bars}"
        f" — suppressing CUC",
        flush=True,
    )
```

Wait — the existing code structure needs the gates as early-exits that skip the return. The cleanest way is to wrap the CUC return in additional conditions. Here's the exact replacement for the CUC block (lines ~250-274):

Replace the entire CUC section (from `if self._cuc_enabled and curr["l"] < prev["l"]:` through the `return "full_100", "ross_cuc_exit", new_structural_stop` line) with:

```python
        if self._cuc_enabled and curr["l"] < prev["l"]:
            bullish_context = False
            if len(self._bars) >= 3:
                b_minus2 = self._bars[-3]
                b_minus1 = self._bars[-2]  # == prev
                if b_minus1["h"] > b_minus2["h"]:
                    if len(self._bars) >= 4:
                        b_minus3 = self._bars[-4]
                        bullish_context = b_minus2["h"] > b_minus3["h"]
                    else:
                        bullish_context = (b_minus2["c"] > b_minus2["o"]
                                           and b_minus1["c"] > b_minus1["o"])

            if bullish_context:
                # Deep runner gate: suppress CUC when deep in profit
                if in_trade and unrealized_r >= self._cuc_min_r:
                    print(
                        f"  ROSS_CUC_SUPPRESSED: unrealized={unrealized_r:.1f}R >= threshold={self._cuc_min_r:.1f}R"
                        f" — letting other signals handle exit",
                        flush=True,
                    )
                # Floor gate: suppress CUC when not yet profitable enough
                elif self._cuc_floor_r > 0 and in_trade and unrealized_r < self._cuc_floor_r:
                    print(
                        f"  ROSS_CUC_FLOOR: unrealized={unrealized_r:.1f}R < floor={self._cuc_floor_r:.1f}R"
                        f" — suppressing CUC",
                        flush=True,
                    )
                # Min trade bars gate: suppress CUC in early bars of trade
                elif self._cuc_min_trade_bars > 0 and self._bars_since_entry < self._cuc_min_trade_bars:
                    print(
                        f"  ROSS_CUC_MIN_BARS: bars_in_trade={self._bars_since_entry}"
                        f" < min={self._cuc_min_trade_bars} — suppressing CUC",
                        flush=True,
                    )
                else:
                    return "full_100", "ross_cuc_exit", new_structural_stop
```

### 2C: Update docstring

Add `WB_ROSS_CUC_FLOOR_R` and `WB_ROSS_CUC_MIN_TRADE_BARS` to the docstring at the top of the file so future readers know the gates exist.

### 2D: Add env vars to `.env`

```
WB_ROSS_CUC_FLOOR_R=0.0              # CUC only fires when unrealized >= this R (0=disabled)
WB_ROSS_CUC_MIN_TRADE_BARS=0         # CUC suppressed for first N 1m bars of trade (0=disabled)
```

---

## Step 3: Regression Check

Before anything else, verify no regression on the golden ticker:

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```

Target: +$18,583. The new gates default to 0, so behavior should be identical.

---

## Step 4: Modify YTD Runner for 3-Config Comparison

We already have baseline (Config A) and V2-current (Config B) data from the last run. We need **three new configs**:

- **Config C:** V2 + `WB_ROSS_CUC_MIN_TRADE_BARS=5`
- **Config D:** V2 + `WB_ROSS_CUC_FLOOR_R=2.0`
- **Config E:** V2 + `WB_ROSS_CUC_MIN_TRADE_BARS=5` + `WB_ROSS_CUC_FLOOR_R=2.0`

**Approach:** Rather than refactoring the runner for 5 configs, create a simple wrapper script `run_v3_cuc_comparison.py` that:

1. Imports the same scanning/ranking logic from `run_ytd_v2_backtest.py`
2. Loops through the same 55 dates with the same scanner data
3. Runs 3 configs per day (C, D, E) — Config A & B data already exists in `ytd_v2_backtest_state.json`
4. Tracks equity/trades/drawdown for each
5. Saves state to `ytd_v3_cuc_state.json`
6. Generates a comparison report at the end

**Config environment overrides:**

```python
# Config C: Min trade bars only
os.environ["WB_ROSS_EXIT_ENABLED"] = "1"
os.environ["WB_ROSS_CUC_MIN_TRADE_BARS"] = "5"
os.environ["WB_ROSS_CUC_FLOOR_R"] = "0"

# Config D: Floor R only
os.environ["WB_ROSS_EXIT_ENABLED"] = "1"
os.environ["WB_ROSS_CUC_MIN_TRADE_BARS"] = "0"
os.environ["WB_ROSS_CUC_FLOOR_R"] = "2.0"

# Config E: Both gates
os.environ["WB_ROSS_EXIT_ENABLED"] = "1"
os.environ["WB_ROSS_CUC_MIN_TRADE_BARS"] = "5"
os.environ["WB_ROSS_CUC_FLOOR_R"] = "2.0"
```

**Alternatively** (simpler): Just modify `run_ytd_v2_backtest.py` to add Config C/D/E as additional loops alongside A/B. Add `config_c`, `config_d`, `config_e` to the state dict, toggle the env vars before each `_run_config_day()` call.

**Use whichever approach is cleaner.** The key requirement: same scanner results per day, same starting equity ($30K), same risk parameters.

---

## Step 5: Run the Comparison

```bash
cd ~/warrior_bot
source venv/bin/activate
python run_v3_cuc_comparison.py  # or python run_ytd_v2_backtest.py if you extended it
```

This will take a while (55 days × 3 configs). Use `--tick-cache tick_cache/` if the runner supports it.

---

## Step 6: Generate Report

Save output to `cowork_reports/2026-03-23_v3_cuc_comparison.md` with:

### Required metrics per config (A through E):
- Total P&L
- Trade count
- Win rate
- Profit factor
- Max drawdown $
- Largest win / Largest loss
- Avg win / Avg loss

### CUC-specific analysis:
- How many CUC exits fired in each config (C, D, E)
- Which CUC exits were blocked by the floor-R gate
- Which CUC exits were blocked by the min-trade-bars gate
- Net impact of each gate (P&L difference vs V2)

### Head-to-head on the 9 known CUC trades:
For each of the 9 trades where V2 fired CUC (SLGB, POLA, ROLR, SER, IOTR, MOVE, RUBI, CDIO, ANNA), show what happens in Config C, D, and E.

---

## Step 7: Commit

```bash
git add ross_exit.py .env run_v3_cuc_comparison.py cowork_reports/
git commit -m "V3 CUC gates: add floor-R and min-trade-bars suppression

Add WB_ROSS_CUC_FLOOR_R and WB_ROSS_CUC_MIN_TRADE_BARS gates to
CUC signal in ross_exit.py. Run 3-config YTD comparison (min-bars,
floor-R, both) against existing baseline and V2 data.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin main
```

---

## Success Criteria

1. VERO regression passes (+$18,583) with all new gates at default (0)
2. At least one of Config C/D/E shows improvement over V2 (+$14,910)
3. No config shows worse max drawdown than V2's $1,804
4. Report clearly identifies which gate (or combo) is most effective

## What NOT to Do

- Do NOT re-enable `sq_target_hit` for any config
- Do NOT change any signal other than CUC (doji, shooting star, gravestone, backstops all stay as-is)
- Do NOT change the entry logic or detector
- Do NOT change ENV_BASE settings (risk, equity, notional caps, etc.)
