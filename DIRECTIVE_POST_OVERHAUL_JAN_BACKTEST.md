# DIRECTIVE: Post-Scanner-Overhaul January Backtest

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — Validates scanner overhaul changes

---

## Context

CC just completed the scanner overhaul (commit `5fcf05f`):
- Removed all Profile X / unknown-float filtering from every backtest runner
- Updated scanner_sim to 10-minute rescan checkpoints (was 30-minute)
- Rescanned all Jan 2025 + Jan 2026 scanner_results with the new checkpoints
- Removed `WB_ALLOW_UNKNOWN_FLOAT` env var and all associated gates/notional caps

We need a clean backtest on the fresh scanner data to see the impact. This is V1 config (SQ mechanical exits, no Ross exit) — our proven best performer.

---

## Step 0: Git Pull + Regression Check

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate

# Regression — must still pass
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

**STOP if regression fails.** The scanner overhaul should not have touched simulate.py's core logic. If regression fails, something went wrong.

---

## Step 1: Fresh State Files

Delete old state files and create fresh ones. The old results are from pre-overhaul scanner data — mixing them would invalidate the comparison.

```bash
# Back up old state files
mkdir -p backtest_archive/pre_overhaul
cp jan_comparison_v1_state.json backtest_archive/pre_overhaul/
cp jan_comparison_v1_output.txt backtest_archive/pre_overhaul/ 2>/dev/null

# Delete state files to force fresh run
rm jan_comparison_v1_state.json
```

---

## Step 2: Run V1 Comparison (Fresh)

```bash
python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_v1_output.txt
```

This runs Jan 2025 (21 days) + Jan 2026 (21 days) with V1 config:
- SQ mechanical exits (no Ross exit)
- All scanner overhaul changes active (no Profile X filtering, 10-min checkpoints)
- Flat risk model ($30K equity, 2.5% risk, $50K max notional)

---

## Step 3: Verify Completion

```bash
python3 -c "
import json
with open('jan_comparison_v1_state.json') as f:
    s = json.load(f)
for m in ['jan2025', 'jan2026']:
    d = s[m]
    days = len(d['daily'])
    trades = len(d['trades'])
    eq = d['equity']
    pnl = eq - 30000
    wins = sum(1 for t in d['trades'] if t['pnl'] > 0)
    wr = (wins/trades*100) if trades else 0
    # Count unknown-float trades
    uf_trades = [t for t in d['trades'] if t.get('_unknown_float')]
    print(f'{m}: {days}/21 days, {trades} trades, +\${pnl:,}, WR={wr:.0f}%')
    if uf_trades:
        uf_pnl = sum(t['pnl'] for t in uf_trades)
        print(f'  Unknown-float trades: {len(uf_trades)}, P&L: \${uf_pnl:,}')
"
```

Both months must show 21/21 days.

---

## Step 4: Comparison Report

Save to `cowork_reports/2026-03-24_post_overhaul_jan_backtest.md`.

### Key comparison: Pre-overhaul V1 vs Post-overhaul V1

Pre-overhaul baseline (from backed-up state file):
```
Jan 2025: 32 trades, +$3,423, WR=41%
Jan 2026: 17 trades, +$16,409, WR=41%
Combined: +$19,832
```

Report should include:

1. **Side-by-side P&L comparison** (pre-overhaul vs post-overhaul)
2. **New stocks found** by 10-minute scanning that weren't in old 30-minute results
3. **New unknown-float stocks** that now trade (previously blocked by Profile X filter)
4. **Per-stock trade table** for any NEW trades that didn't exist in the pre-overhaul run
5. **Any trades that disappeared** (scanner changes could also remove candidates if checkpoint timing differs)

---

## Step 5: Commit and Push

```bash
git add jan_comparison_v1_state.json jan_comparison_v1_output.txt \
    cowork_reports/2026-03-24_post_overhaul_jan_backtest.md \
    backtest_archive/pre_overhaul/
git commit -m "$(cat <<'EOF'
Post-scanner-overhaul Jan backtest: V1 config on fresh scanner data

Clean re-run of Jan 2025 + Jan 2026 with scanner overhaul changes:
- Profile X / unknown-float filtering removed
- 10-minute rescan checkpoints (was 30-minute)
- Validates that scanner improvements capture more profitable trades

Pre-overhaul baseline archived to backtest_archive/pre_overhaul/

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## What We're Looking For

1. **More trades from unknown-float stocks** — GDTC, AMOD, XPON, VRME were all blocked before. Do they trade now?
2. **More trades from 10-minute scanning** — ZENA and other news-break stocks that fell in the 30-minute gaps. Do the shorter checkpoint windows catch them?
3. **Net P&L impact** — Does the scanner overhaul improve the combined P&L above the +$19,832 baseline?
4. **No regressions** — Stocks that traded before should still trade with similar or better results.
