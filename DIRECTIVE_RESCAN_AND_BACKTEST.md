# DIRECTIVE: Rescan All Jan Dates + Re-Run Backtest

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — Previous backtest was zero-delta because scanner JSONs weren't regenerated

---

## Problem

The post-overhaul backtest showed identical results (+$19,832) because `run_jan_v1_comparison.py` reads from `scanner_results/*.json` files, which still contain data from the old 30-minute checkpoint scans. The code changes (5-minute checkpoints, Profile X removal) only take effect when `scanner_sim.py` actually runs and writes new JSONs.

---

## Step 0: Git Pull + Verify

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

---

## Step 1: Back Up Current Scanner Data

```bash
mkdir -p scanner_results/backup_pre_5min_rescan
for f in scanner_results/2025-01-*.json scanner_results/2026-01-*.json; do
    cp "$f" scanner_results/backup_pre_5min_rescan/
done
echo "Backed up $(ls scanner_results/backup_pre_5min_rescan/*.json | wc -l) files"
```

---

## Step 2: Rescan All January Dates

Run `scanner_sim.py` for every trading day in both months. This regenerates the JSONs with:
- 5-minute rescan checkpoints (39 checkpoints per day, was 6)
- No Profile X filtering (unknown-float stocks included)

**Jan 2025 (21 trading days):**
```bash
for d in 2025-01-02 2025-01-03 2025-01-06 2025-01-07 2025-01-08 2025-01-09 2025-01-10 2025-01-13 2025-01-14 2025-01-15 2025-01-16 2025-01-17 2025-01-21 2025-01-22 2025-01-23 2025-01-24 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-01-31; do
    echo "=== Scanning $d ==="
    python scanner_sim.py "$d" 2>&1 | tail -5
    echo ""
done
```

**Jan 2026 (21 trading days):**
```bash
for d in 2026-01-02 2026-01-05 2026-01-06 2026-01-07 2026-01-08 2026-01-09 2026-01-12 2026-01-13 2026-01-14 2026-01-15 2026-01-16 2026-01-20 2026-01-21 2026-01-22 2026-01-23 2026-01-26 2026-01-27 2026-01-28 2026-01-29 2026-01-30; do
    echo "=== Scanning $d ==="
    python scanner_sim.py "$d" 2>&1 | tail -5
    echo ""
done
```

**NOTE:** scanner_sim makes Alpaca API calls for bar data. If rate-limited, add `sleep 2` between runs. The float cache should be warm — most symbols already have cached floats.

---

## Step 3: Diff Old vs New Scanner Data

After all rescans complete, compare:

```bash
python3 -c "
import json, os

backup_dir = 'scanner_results/backup_pre_5min_rescan'
current_dir = 'scanner_results'

for year in ['2025', '2026']:
    old_stocks = set()
    new_stocks = set()
    new_unknown = set()
    new_rescan = set()

    for fname in sorted(os.listdir(backup_dir)):
        if fname.startswith(f'{year}-01') and fname.endswith('.json'):
            with open(f'{backup_dir}/{fname}') as f:
                data = json.load(f)
            for c in (data if isinstance(data, list) else data.get('candidates', [])):
                old_stocks.add(c['symbol'])

    for fname in sorted(os.listdir(current_dir)):
        if fname.startswith(f'{year}-01') and fname.endswith('.json'):
            with open(f'{current_dir}/{fname}') as f:
                data = json.load(f)
            for c in (data if isinstance(data, list) else data.get('candidates', [])):
                new_stocks.add(c['symbol'])
                if c.get('profile') in ('X', 'unknown'):
                    new_unknown.add(c['symbol'])
                if c.get('discovery_method') == 'rescan':
                    new_rescan.add(c['symbol'])

    added = new_stocks - old_stocks
    removed = old_stocks - new_stocks
    print(f'=== JAN {year} ===')
    print(f'  Old: {len(old_stocks)} unique | New: {len(new_stocks)} unique')
    print(f'  Added: {len(added)} — {sorted(added)}')
    print(f'  Removed: {len(removed)} — {sorted(removed)}')
    print(f'  Unknown-float stocks in new data: {sorted(new_unknown)}')
    print(f'  Rescan-discovered stocks: {sorted(new_rescan)}')
    print()
"
```

**This is the key output.** We want to see:
- New stocks discovered by 5-minute checkpoints that 30-minute missed
- Unknown-float stocks now included (previously filtered as Profile X)

---

## Step 4: Fresh Backtest

```bash
# Wipe state file for clean run
rm -f jan_comparison_v1_state.json

# Run
python run_jan_v1_comparison.py 2>&1 | tee jan_comparison_v1_output.txt
```

---

## Step 5: Results + Report

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
    sq = [t for t in d['trades'] if t.get('setup_type') == 'squeeze']
    mp = [t for t in d['trades'] if t.get('setup_type') != 'squeeze']
    sq_pnl = sum(t['pnl'] for t in sq)
    mp_pnl = sum(t['pnl'] for t in mp)
    print(f'{m}: {days}/21 days, {trades} trades, +\${pnl:,}, WR={wr:.0f}%')
    print(f'  SQ: {len(sq)} trades, \${sq_pnl:,}')
    print(f'  MP: {len(mp)} trades, \${mp_pnl:,}')
total = (s['jan2025']['equity'] - 30000) + (s['jan2026']['equity'] - 30000)
print(f'COMBINED: +\${total:,}')
"
```

Save report to `cowork_reports/2026-03-24_post_overhaul_v2_jan_backtest.md` with:
1. Pre-overhaul vs post-overhaul comparison table
2. Scanner diff (new stocks found, unknown-float stocks added)
3. New trades that didn't exist in the pre-overhaul run
4. Net P&L impact of scanner overhaul

---

## Step 6: Commit and Push

```bash
git add scanner_results/2025-01-*.json scanner_results/2026-01-*.json \
    scanner_results/backup_pre_5min_rescan/ \
    jan_comparison_v1_state.json jan_comparison_v1_output.txt \
    cowork_reports/2026-03-24_post_overhaul_v2_jan_backtest.md
git commit -m "$(cat <<'EOF'
Rescan Jan 2025+2026 with 5-min checkpoints + fresh backtest

Regenerated all 42 scanner_results JSONs with:
- 5-minute rescan checkpoints (39 per day, was 6 at 30-min)
- Unknown-float stocks no longer filtered (Profile X removal)

Fresh V1 backtest on new scanner data.
Pre-overhaul backup in scanner_results/backup_pre_5min_rescan/

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```
