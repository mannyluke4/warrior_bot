#!/bin/bash
# Usage: ./run_study.sh stocks.txt
# stocks.txt format: SYMBOL,DATE,START,END (one per line)
# Example: VERO,2026-01-16,07:00,12:00

INPUT_FILE="$1"
RESULTS_DIR="study_data"
mkdir -p "$RESULTS_DIR"

TOTAL=0
SUCCESS=0
FAILED=0
SKIPPED=0

while IFS=',' read -r SYMBOL DATE START END; do
    # Skip empty lines and comments
    [[ -z "$SYMBOL" || "$SYMBOL" == \#* ]] && continue

    TOTAL=$((TOTAL + 1))
    OUTFILE="$RESULTS_DIR/${SYMBOL}_${DATE}.json"

    # Skip if already exists (allows resuming)
    if [ -f "$OUTFILE" ]; then
        echo "[$TOTAL] SKIP $SYMBOL $DATE (already exists)"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    echo "[$TOTAL] Running $SYMBOL $DATE $START-$END..."
    if python simulate.py "$SYMBOL" "$DATE" "$START" "$END" --ticks --export-json 2>&1 | tail -5; then
        if [ -f "$OUTFILE" ]; then
            SUCCESS=$((SUCCESS + 1))
            echo "  -> OK: $OUTFILE"
        else
            FAILED=$((FAILED + 1))
            echo "  -> FAIL: no JSON output"
        fi
    else
        FAILED=$((FAILED + 1))
        echo "  -> FAIL: simulate.py error"
    fi
    echo ""
done < "$INPUT_FILE"

echo "========================================"
echo "STUDY BATCH COMPLETE"
echo "Total: $TOTAL | Success: $SUCCESS | Failed: $FAILED | Skipped: $SKIPPED"
echo "========================================"
