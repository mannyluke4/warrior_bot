#!/bin/bash
source venv/bin/activate

DATES="2026-03-02 2026-03-03 2026-03-04 2026-03-05"

for DATE in $DATES; do
    echo "=========================================="
    echo "Processing $DATE"
    echo "=========================================="

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
        echo "  RUN $SYM profile=$PROFILE start=$SIM_START"

        if [ "$PROFILE" = "B" ]; then
            timeout 180 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile B --ticks --feed databento --l2 --no-fundamentals > "$OUTFILE" 2>&1
            EXIT_CODE=$?
            if [ $EXIT_CODE -ne 0 ]; then
                echo "  WARN $SYM Databento failed, falling back to Alpaca"
                timeout 120 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile B --ticks --no-fundamentals > "$OUTFILE" 2>&1
            fi
        else
            timeout 120 python simulate.py "$SYM" "$DATE" "$SIM_START" "12:00" --profile A --ticks --no-fundamentals > "$OUTFILE" 2>&1
        fi

        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "  FAIL $SYM (exit=$EXIT_CODE)"
            echo "ERROR: simulate.py exited with code $EXIT_CODE" >> "$OUTFILE"
        fi
    done
done

echo ""
echo "All dates processed."
