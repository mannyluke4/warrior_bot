# Directive: Scanner Validation + 49-Day Backtest Re-Run

**TARGET**: 🖥️ Mac Mini CC
**Priority**: CRITICAL — must complete before next live session
**Date**: 2026-03-19

---

## Context

MacBook Pro CC has pushed the scanner alignment changes (commit `e9cbb88`). All three scanner pipelines now use unified Ross Pillar criteria:
- Gap ≥ 10%, RVOL ≥ 2.0x, Float 100K-10M, Price $2-$20, PM Volume ≥ 50K
- Same ranking formula across live_scanner.py, scanner_sim.py, and run_ytd_v2_backtest.py

Now we need to regenerate scanner data, validate it, and re-run the 49-day backtest.

---

## Step 1: Pull Latest Code

```bash
cd ~/warrior_bot
git pull origin v6-dynamic-sizing
```

Verify commit `e9cbb88` (Scanner alignment) is on HEAD.

---

## Step 2: Regenerate Scanner Data for All 49 Dates

Re-run `scanner_sim.py` for every date in the backtest range with the aligned criteria. This overwrites the old `scanner_results/*.json` files.

```bash
source venv/bin/activate

# Regenerate all 49 dates
for date in 2026-01-02 2026-01-03 2026-01-05 2026-01-06 2026-01-07 \
            2026-01-08 2026-01-09 2026-01-12 2026-01-13 2026-01-14 \
            2026-01-15 2026-01-16 2026-01-20 2026-01-21 2026-01-22 \
            2026-01-23 2026-01-26 2026-01-27 2026-01-28 2026-01-29 \
            2026-01-30 2026-02-02 2026-02-03 2026-02-04 2026-02-05 \
            2026-02-06 2026-02-09 2026-02-10 2026-02-11 2026-02-12 \
            2026-02-13 2026-02-17 2026-02-18 2026-02-19 2026-02-20 \
            2026-02-23 2026-02-24 2026-02-25 2026-02-26 2026-02-27 \
            2026-03-02 2026-03-03 2026-03-04 2026-03-05 2026-03-06 \
            2026-03-09 2026-03-10 2026-03-11 2026-03-12; do
    python scanner_sim.py $date
done
```

If scanner_sim.py doesn't accept a date argument, check how it's invoked and adapt. The goal is to regenerate all JSON files in `scanner_results/`.

**Also generate Mar 18 (ARTL day):**
```bash
python scanner_sim.py 2026-03-18
```

---

## Step 3: Validate Key Dates

After regeneration, verify these critical stocks still appear in the top 5:

```bash
python -c "
import json, os

checks = [
    ('2026-01-14', 'ROLR', 'Biggest runner +\$6,444'),
    ('2026-01-16', 'VERO', 'Biggest trade +\$18,583'),
    ('2026-01-08', 'SXTC', 'Cascading winner +\$1,686'),
    ('2026-03-10', 'GITS', 'Weekly best +\$2,748'),
    ('2026-01-02', 'SNSE', 'Config B extra winner +\$784'),
]

for date, symbol, label in checks:
    path = f'scanner_results/{date}.json'
    if not os.path.exists(path):
        print(f'  ❌ {date}: FILE MISSING')
        continue
    with open(path) as f:
        data = json.load(f)
    # Check top 5 by the ranking formula
    match = [c for c in data if c['symbol'] == symbol]
    if match:
        c = match[0]
        print(f'  ✅ {date}: {symbol} FOUND — gap={c.get(\"gap_pct\",0):.1f}% rvol={c.get(\"relative_volume\",0):.1f}x float={c.get(\"float_millions\",\"N/A\")}M — {label}')
    else:
        print(f'  ❌ {date}: {symbol} NOT FOUND — {label}')
"
```

**Also check ARTL on Mar 18:**
```bash
python -c "
import json
with open('scanner_results/2026-03-18.json') as f:
    data = json.load(f)
artl = [c for c in data if c['symbol'] == 'ARTL']
if artl:
    a = artl[0]
    print(f'✅ ARTL FOUND: gap={a.get(\"gap_pct\",0):.1f}% rvol={a.get(\"relative_volume\",0):.1f}x float={a.get(\"float_millions\",\"N/A\")}M')
else:
    print('❌ ARTL NOT FOUND')
    # Show top 5 to see what was selected instead
    for c in data[:5]:
        print(f'  {c[\"symbol\"]}: gap={c.get(\"gap_pct\",0):.1f}% rvol={c.get(\"relative_volume\",0):.1f}x')
"
```

---

## Step 4: Compare Old vs New Candidate Lists

For each of the 49 dates, report how many candidates changed:

```bash
# Quick comparison: count candidates per day, old vs new
python -c "
import json, os

dates = [
    '2026-01-02','2026-01-03','2026-01-05','2026-01-06','2026-01-07',
    '2026-01-08','2026-01-09','2026-01-12','2026-01-13','2026-01-14',
    '2026-01-15','2026-01-16','2026-01-20','2026-01-21','2026-01-22',
    '2026-01-23','2026-01-26','2026-01-27','2026-01-28','2026-01-29',
    '2026-01-30','2026-02-02','2026-02-03','2026-02-04','2026-02-05',
    '2026-02-06','2026-02-09','2026-02-10','2026-02-11','2026-02-12',
    '2026-02-13','2026-02-17','2026-02-18','2026-02-19','2026-02-20',
    '2026-02-23','2026-02-24','2026-02-25','2026-02-26','2026-02-27',
    '2026-03-02','2026-03-03','2026-03-04','2026-03-05','2026-03-06',
    '2026-03-09','2026-03-10','2026-03-11','2026-03-12',
]
for d in dates:
    path = f'scanner_results/{d}.json'
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
        print(f'{d}: {len(data)} candidates')
    else:
        print(f'{d}: NO FILE')
"
```

---

## Step 5: Re-Run 49-Day Backtest

With all 5 strategy fixes enabled AND new scanner data:

```bash
# Ensure .env has all fixes ON:
# WB_CONT_HOLD_DIRECTION_CHECK=1
# WB_MAX_LOSS_R_TIERED=1
# WB_MAX_LOSS_R_ULTRA_LOW_FLOAT=0
# WB_MAX_LOSS_R_LOW_FLOAT=0.85
# WB_MAX_LOSS_TRIGGERS_COOLDOWN=1
# WB_NO_REENTRY_ENABLED=1
# WB_TW_MIN_PROFIT_R=1.5

python run_ytd_v2_backtest.py
```

---

## Step 6: Push Results Report

Push `SCANNER_ALIGNED_BACKTEST_RESULTS.md` with:

1. **Key date validation**: Did VERO, ROLR, SXTC, GITS, SNSE survive the new scanner?
2. **ARTL check**: Is ARTL in the Mar 18 candidates?
3. **Candidate comparison**: How many stocks per day, any major changes?
4. **49-day headline numbers**: P&L, return, profit factor, max drawdown — compare to previous +$19,072
5. **Trade-by-trade detail**: Same format as YTD_V2_BACKTEST_RESULTS.md
6. **Stocks added/removed**: Any new winners or losers that appeared due to different stock selection?

---

## Step 7: Update Repo Files

After results are validated, update these files in the repo:

1. **`COWORK_HANDOFF.md`** — Update with:
   - New workflow: Mac Mini is primary (code + backtest + live). MacBook Pro is mobile/remote access.
   - Current state of all fixes (5 strategy fixes + scanner alignment)
   - New regression targets (VERO +$18,583 or whatever the aligned backtest shows)
   - Updated architecture section (Databento scanner, strategy profiles roadmap)
   - Updated role boundaries: CC MM now does code changes + backtesting + live bot. CC MBP is backup/remote. Cowork is strategy/analysis.

2. **`CLAUDE.md`** — Update with:
   - New regression targets from the aligned backtest
   - Current live config (all fix env vars)
   - Scanner architecture change (Databento live scanner)
   - Note about scanner alignment date

3. **`MASTER_TODO.md`** — Update scanner section status to COMPLETE (or note issues)

---

## What Success Looks Like

| Test | Pass Criteria |
|------|---------------|
| VERO in top 5 on Jan 16 | Must be present |
| ROLR in top 5 on Jan 14 | Must be present |
| SXTC in top 5 on Jan 08 | Must be present |
| ARTL in candidates on Mar 18 | Must be present |
| 49-day P&L | Positive (ideally close to or above +$19,072) |
| Aligned backtest is trustworthy | No known data quality issues remaining |

---

*Directive created: 2026-03-19 | From: Claude Cowork (MacBook Pro) | To: Mac Mini CC*
*Note: After this directive completes, the primary Cowork workspace moves to the Mac Mini.*
