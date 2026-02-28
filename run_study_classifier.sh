#!/bin/bash
# run_study_classifier.sh — Run full study with classifier enabled
# Re-runs the same stocks from study_data/ with classifier ON
# Outputs to study_data_classifier/ to preserve baseline

set -euo pipefail

export WB_CLASSIFIER_ENABLED=1
export WB_CLASSIFIER_VWAP_GATE=7
export WB_CLASSIFIER_CASC_VWAP_MIN=8
export WB_CLASSIFIER_SMOOTH_VWAP_MIN=10

OUT_DIR="study_data_classifier"
mkdir -p "$OUT_DIR"

TOTAL=0
SUCCESS=0
FAIL=0

for json_file in study_data/*.json; do
    filename=$(basename "$json_file" .json)
    # Parse symbol and date (format: SYMBOL_YYYY-MM-DD)
    symbol=$(echo "$filename" | sed 's/_[0-9][0-9][0-9][0-9]-.*$//')
    date=$(echo "$filename" | grep -o '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]')

    if [ -z "$symbol" ] || [ -z "$date" ]; then
        echo "SKIP: could not parse $filename"
        continue
    fi

    # Skip if already done (resume support)
    out_file="$OUT_DIR/${symbol}_${date}.json"
    if [ -f "$out_file" ]; then
        echo "SKIP (exists): $symbol $date"
        TOTAL=$((TOTAL + 1))
        SUCCESS=$((SUCCESS + 1))
        continue
    fi

    TOTAL=$((TOTAL + 1))
    echo -n "[$TOTAL] $symbol $date ... "

    # Read start time from the stock list or default to 07:00
    start_time="07:00"
    if [ -f study_stocks.txt ]; then
        line=$(grep "^${symbol},${date}," study_stocks.txt 2>/dev/null | head -1)
        if [ -n "$line" ]; then
            start_time=$(echo "$line" | cut -d',' -f3)
        fi
    fi

    if python simulate.py "$symbol" "$date" "$start_time" 12:00 --ticks --export-json 2>&1 | tail -1; then
        # Copy the JSON to classifier output dir (preserve baseline in study_data/)
        src="study_data/${symbol}_${date}.json"
        if [ -f "$src" ]; then
            cp "$src" "$out_file"
            SUCCESS=$((SUCCESS + 1))
            echo "OK"
        else
            FAIL=$((FAIL + 1))
            echo "FAIL (no JSON)"
        fi
    else
        FAIL=$((FAIL + 1))
        echo "FAIL"
    fi
done

echo ""
echo "================================"
echo "Classifier batch complete"
echo "Total: $TOTAL  Success: $SUCCESS  Fail: $FAIL"
echo "Output: $OUT_DIR/"
echo "================================"
