#!/bin/bash
source venv/bin/activate

DATES="2026-01-13 2026-01-15 2026-02-10 2026-02-12 2026-03-04"

for DATE in $DATES; do
    echo "=========================================="
    echo "Processing $DATE"
    echo "=========================================="
    
    # Extract A/B candidates from JSON
    python3 -c "
import json, sys
with open('scanner_results/${DATE}.json') as f:
    candidates = json.load(f)
for c in candidates:
    if c['profile'] in ('A', 'B'):
        print(f\"{c['symbol']} {c['profile']} {c['sim_start']}\")
" | while read SYM PROFILE SIM_START; do
        OUTFILE="scanner_results/${DATE}_${SYM}.txt"
        
        # Skip if already exists and has content
        if [ -s "$OUTFILE" ]; then
            echo "  SKIP $SYM (already exists)"
            continue
        fi
        
        echo "  RUN  $SYM profile=$PROFILE start=$SIM_START"
        timeout 120 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile "$PROFILE" --ticks --no-fundamentals > "$OUTFILE" 2>&1
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "  FAIL $SYM (exit=$EXIT_CODE)"
            echo "ERROR: simulate.py exited with code $EXIT_CODE" >> "$OUTFILE"
        fi
    done
done

echo ""
echo "All dates processed."
