#!/usr/bin/env bash
#
# run_scanner_backtest.sh — Run scanner_sim.py for 5 dates, then simulate each candidate
#
# Usage: bash run_scanner_backtest.sh
#

set -euo pipefail
cd "$(dirname "$0")"
source venv/bin/activate

DATES=("2026-01-13" "2026-01-15" "2026-02-10" "2026-02-12" "2026-03-04")
RESULTS_DIR="scanner_results"

mkdir -p "$RESULTS_DIR"

echo "============================================================"
echo "  SCANNER BACKTEST — ${#DATES[@]} dates"
echo "============================================================"
echo ""

for DATE in "${DATES[@]}"; do
    echo "────────────────────────────────────────────────────────────"
    echo "  Scanning: $DATE"
    echo "────────────────────────────────────────────────────────────"

    # Run scanner for this date
    python scanner_sim.py --date "$DATE"

    JSON_FILE="$RESULTS_DIR/$DATE.json"
    if [ ! -f "$JSON_FILE" ]; then
        echo "  ERROR: $JSON_FILE not found, skipping date"
        continue
    fi

    # Parse candidates from JSON and run simulate.py for each
    NUM_CANDIDATES=$(python -c "import json; d=json.load(open('$JSON_FILE')); print(len(d))")
    echo ""
    echo "  Running simulate.py for $NUM_CANDIDATES candidates..."
    echo ""

    python -c "
import json, subprocess, sys

with open('$JSON_FILE') as f:
    candidates = json.load(f)

for i, c in enumerate(candidates, 1):
    sym = c['symbol']
    profile = c['profile']
    sim_start = c['sim_start']
    print(f'  [{i}/{len(candidates)}] {sym} (profile={profile}, start={sim_start})')
    sys.stdout.flush()

    cmd = [
        'python', 'simulate.py',
        sym, '$DATE', sim_start, '12:00',
        '--profile', profile,
        '--ticks',
        '--no-fundamentals',
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Save individual sim output
    out_file = '$RESULTS_DIR/${DATE}_' + sym + '.txt'
    with open(out_file, 'w') as f:
        f.write(result.stdout)
        if result.stderr:
            f.write('\n--- STDERR ---\n')
            f.write(result.stderr)

    # Print summary line from output
    for line in result.stdout.split('\n'):
        if 'Gross P&L' in line:
            print(f'           {line.strip()}')
            break
    else:
        if result.returncode != 0:
            print(f'           ERROR (exit code {result.returncode})')
        else:
            print(f'           No trades')
    sys.stdout.flush()
"

    echo ""
done

echo "============================================================"
echo "  All scanner backtests complete!"
echo "  Running analysis..."
echo "============================================================"
echo ""

python scanner_analysis.py

echo ""
echo "  Report: $RESULTS_DIR/SCANNER_BACKTEST_REPORT.md"
echo "  Done!"
