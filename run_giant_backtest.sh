#!/bin/bash
source venv/bin/activate

ALL_DATES="2026-01-02 2026-01-03 2026-01-05 2026-01-06 2026-01-07 2026-01-08 2026-01-09 2026-01-12 2026-01-13 2026-01-14 2026-01-15 2026-01-16 2026-01-21 2026-01-22 2026-01-23 2026-01-26 2026-01-27 2026-01-28 2026-01-29 2026-02-02 2026-02-03 2026-02-04 2026-02-05 2026-02-06 2026-02-09 2026-02-10 2026-02-11 2026-02-12 2026-02-13 2026-02-17 2026-02-18 2026-02-19 2026-02-20 2026-02-23 2026-02-24 2026-02-25 2026-02-26 2026-02-27"

for DATE in $ALL_DATES; do
    echo "=========================================="
    echo "Processing $DATE"
    echo "=========================================="

    if [ ! -f "scanner_results/${DATE}.json" ]; then
        echo "  SKIP — no scanner results"
        continue
    fi

    python3 -c "
import json
with open('scanner_results/${DATE}.json') as f:
    candidates = json.load(f)

profile_a = []
profile_b = []

for c in candidates:
    p = c.get('profile', 'X')
    flt = c.get('float_millions')
    gap = c['gap_pct']
    price = c['pm_price']
    if flt is None or p == 'X':
        continue
    if p == 'A' and 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
        profile_a.append(c)
    elif p == 'B' and 5.0 <= flt <= 50.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
        profile_b.append(c)

profile_b.sort(key=lambda x: x['gap_pct'], reverse=True)
profile_b = profile_b[:2]

for c in profile_a:
    print(f\"{c['symbol']} A {c['sim_start']}\")
for c in profile_b:
    print(f\"{c['symbol']} B {c['sim_start']}\")
" | while read SYM PROFILE SIM_START; do
        OUTFILE="scanner_results/${DATE}_${SYM}.txt"

        if [ -s "$OUTFILE" ]; then
            echo "  SKIP $SYM (already exists)"
            continue
        fi

        echo "  RUN $SYM profile=$PROFILE start=$SIM_START"

        if [ "$PROFILE" = "B" ]; then
            timeout 180 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile B --ticks --feed databento --l2 --no-fundamentals > "$OUTFILE" 2>&1
            EXIT_CODE=$?
            if [ $EXIT_CODE -ne 0 ] || grep -q "license_not_found\|403\|Error" "$OUTFILE"; then
                echo "  WARN $SYM Databento failed, falling back to Alpaca"
                timeout 120 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile B --ticks --no-fundamentals > "$OUTFILE" 2>&1
            fi
        else
            timeout 120 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile A --ticks --no-fundamentals > "$OUTFILE" 2>&1
        fi

        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "  FAIL $SYM (exit=$EXIT_CODE)"
        fi
    done
done
echo "Phase 2 complete."
