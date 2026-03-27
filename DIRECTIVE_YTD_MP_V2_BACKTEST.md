# Directive: YTD A/B Backtest — SQ-Only vs SQ + MP V2
## Priority: HIGH — Run today (Friday evening / overnight)
## Date: 2026-03-27
## Depends On: Commits 7c9d302 (MP V2), a474005 (SQ-priority gate), bf35344 (regression pass)

---

## Context

MP V2 regression passed on individual stocks:
- VERO: +$15,692 (unchanged, SQ-priority gate works)
- ROLR: +$7,974 (+$1,530 improvement over $6,444 baseline)
- EEIQ: neutral (MP V2 unlocked but didn't find a clean pullback)
- ONCO: 0 trades (dormant on quiet days)

**Question this backtest answers:** Does MP V2 add consistent value across 49+ days, or is ROLR a one-off?

---

## Step 1: Modify `run_ytd_v2_backtest.py`

The runner currently A/B tests Ross Exit ON vs OFF. Repurpose for MP V2:

### 1a. Add MP V2 env vars to ENV_BASE

```python
# In ENV_BASE dict, add:
"WB_MP_V2_SQ_PRIORITY": "1",
"WB_MP_REENTRY_COOLDOWN_BARS": "3",
"WB_MP_MAX_REENTRIES": "3",
"WB_MP_REENTRY_MIN_R": "0.06",
"WB_MP_REENTRY_MACD_GATE": "0",
"WB_MP_REENTRY_USE_SQ_EXITS": "1",
"WB_MP_REENTRY_PROBE_SIZE": "0.5",
```

These go in ENV_BASE so both configs get the same base settings. The A/B toggle is `WB_MP_V2_ENABLED`.

### 1b. Change A/B config toggle

Replace the Ross Exit toggle with MP V2:

```python
# Config A: SQ-only baseline (MP V2 OFF)
os.environ["WB_ROSS_EXIT_ENABLED"] = "0"
os.environ["WB_MP_V2_ENABLED"] = "0"
day_trades_a, day_pnl_a = _run_config_day(...)

# Config B: SQ + MP V2 (MP V2 ON)
os.environ["WB_ROSS_EXIT_ENABLED"] = "0"  # Keep Ross OFF for both
os.environ["WB_MP_V2_ENABLED"] = "1"
day_trades_b, day_pnl_b = _run_config_day(...)
```

### 1c. Update setup_type parsing

Line 248 currently only detects "squeeze" vs "micro_pullback":
```python
"setup_type": "squeeze" if m.group(8).startswith("sq_") else "micro_pullback",
```

Update to detect mp_reentry (exit reasons will also start with `sq_` since V2 routes through SQ exits):
```python
# Need a different detection method. mp_reentry trades print "MP_V2_ENTRY" in verbose output.
# Simplest: parse the ENTRY/MP_V2_ENTRY line that precedes the trade summary.
# Or: add setup_type to the trade summary output in simulate.py.
```

**Note:** This is tricky because mp_reentry uses SQ exits (so exit reasons start with `sq_`). The runner currently uses exit reason prefix to determine setup_type. Options:
1. Add `setup_type=` to simulate.py's trade summary line (cleanest)
2. Parse the verbose ENTRY vs MP_V2_ENTRY log lines
3. Just count mp_reentry trades separately by checking if MP V2 was enabled

Option 1 is recommended — add a `[mp_reentry]` or `[squeeze]` tag to the trade summary line in simulate.py's final output table.

### 1d. Add dates through 2026-03-27

Current DATES list ends at 2026-03-20. Add:
```python
"2026-03-23", "2026-03-24", "2026-03-25", "2026-03-26", "2026-03-27",
```

### 1e. Update MAX_FLOAT_MILLIONS

```python
MAX_FLOAT_MILLIONS = 15  # Match .env WB_MAX_FLOAT=15 (was 10)
```

### 1f. Clear old state

Delete `ytd_v2_backtest_state.json` before running — we want a clean A/B from scratch, not a resume from the old Ross Exit comparison.

---

## Step 2: Run the Backtest

```bash
cd ~/warrior_bot_v2
source venv/bin/activate

# Clear old state
rm -f ytd_v2_backtest_state.json

# Run (30-60 min with tick cache)
python run_ytd_v2_backtest.py 2>&1 | tee ytd_mp_v2_backtest_output.log
```

---

## Step 3: Report Key Metrics

After completion, report:

| Metric | Config A (SQ-Only) | Config B (SQ + MP V2) | Delta |
|--------|--------------------|-----------------------|-------|
| Total P&L | | | |
| Final equity | | | |
| Trade count | | | |
| Win rate | | | |
| Max drawdown | | | |
| # of days MP V2 fired | N/A | | |
| MP V2 trade P&L | N/A | | |
| Days where MP V2 added value | N/A | | |
| Days where MP V2 hurt | N/A | | |

**Critical check:** Config A should match or be very close to the previous V1 megatest result (+$19,832). If it diverges significantly, something changed in the runner or env.

---

## Step 4: Commit Results

```bash
git add run_ytd_v2_backtest.py ytd_v2_backtest_state.json ytd_mp_v2_backtest_output.log
git commit -m "YTD A/B backtest: SQ-only vs SQ + MP V2 (49 days)

Config A (SQ-only): $XX,XXX — [X trades, X% WR]
Config B (SQ+V2):   $XX,XXX — [X trades, X% WR, X mp_reentry trades]
Delta: $X,XXX

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin v2-ibkr-migration
```

---

## Success Criteria

| Outcome | Interpretation | Action |
|---------|----------------|--------|
| B > A by $1K+ | MP V2 adds consistent value | Enable for Monday (`WB_MP_V2_ENABLED=1`) |
| B ≈ A (±$500) | MP V2 is neutral — doesn't hurt, doesn't help much | Enable cautiously, monitor live |
| B < A by $500+ | MP V2 is a drag | Keep disabled, investigate which stocks it hurt |

**Regardless of outcome:** Config A must remain within 5% of the +$19,832 baseline. If it doesn't, investigate env var drift before drawing conclusions about MP V2.

---

## Files to Modify

1. `run_ytd_v2_backtest.py` — A/B config, ENV_BASE, setup_type parsing, dates, float
2. `simulate.py` — (optional) Add setup_type to trade summary output for cleaner parsing
3. Delete `ytd_v2_backtest_state.json` before running
