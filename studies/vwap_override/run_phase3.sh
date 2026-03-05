#!/bin/bash
# Phase 3: Run all sessions at three VWAP override thresholds
cd /Users/mannyluke/warrior_bot
source venv/bin/activate

OUTDIR="studies/vwap_override/phase3_output"
mkdir -p "$OUTDIR"

# 28 study sessions
declare -a STUDY_SESSIONS=(
    "ROLR 2026-01-06"
    "ACON 2026-01-08"
    "APVO 2026-01-09"
    "BDSX 2026-01-12"
    "PMAX 2026-01-13"
    "ROLR 2026-01-14"
    "BNAI 2026-01-16"
    "GWAV 2026-01-16"
    "LCFY 2026-01-16"
    "ROLR 2026-01-16"
    "SHPH 2026-01-16"
    "TNMG 2026-01-16"
    "VERO 2026-01-16"
    "PAVM 2026-01-21"
    "MOVE 2026-01-23"
    "SLE 2026-01-23"
    "BCTX 2026-01-27"
    "HIND 2026-01-27"
    "MOVE 2026-01-27"
    "SXTP 2026-01-27"
    "BNAI 2026-01-28"
    "BNAI 2026-02-05"
    "MNTS 2026-02-06"
    "ACON 2026-02-13"
    "MLEC 2026-02-13"
    "SNSE 2026-02-18"
    "ENVB 2026-02-19"
    "JZXN 2026-03-04"
)

# 6 regression benchmarks (some overlap with study sessions)
declare -a REGRESSION=(
    "VERO 2026-01-16"
    "GWAV 2026-01-16"
    "APVO 2026-01-09"
    "BNAI 2026-01-28"
    "MOVE 2026-01-27"
    "ANPA 2026-01-09"
)

for THRESHOLD in 10.0 11.0 12.0; do
    echo ""
    echo "=========================================="
    echo "  THRESHOLD: WB_VWAP_OVERRIDE_MIN_SCORE=$THRESHOLD"
    echo "=========================================="

    TDIR="$OUTDIR/threshold_${THRESHOLD}"
    mkdir -p "$TDIR"

    # Run all 28 study sessions
    for session in "${STUDY_SESSIONS[@]}"; do
        SYM=$(echo "$session" | cut -d' ' -f1)
        DATE=$(echo "$session" | cut -d' ' -f2)
        OUTFILE="$TDIR/${SYM}_${DATE}.txt"
        echo "  Running $SYM $DATE (threshold=$THRESHOLD)..."
        WB_VWAP_OVERRIDE_MIN_SCORE=$THRESHOLD python simulate.py "$SYM" "$DATE" 07:00 12:00 --profile A --ticks --no-fundamentals -v > "$OUTFILE" 2>&1
    done

    # Run regression benchmarks (only ones not already in study sessions)
    for session in "${REGRESSION[@]}"; do
        SYM=$(echo "$session" | cut -d' ' -f1)
        DATE=$(echo "$session" | cut -d' ' -f2)
        OUTFILE="$TDIR/${SYM}_${DATE}.txt"
        if [ ! -f "$OUTFILE" ]; then
            echo "  Running regression $SYM $DATE (threshold=$THRESHOLD)..."
            WB_VWAP_OVERRIDE_MIN_SCORE=$THRESHOLD python simulate.py "$SYM" "$DATE" 07:00 12:00 --profile A --ticks --no-fundamentals -v > "$OUTFILE" 2>&1
        fi
    done

    # Summary for this threshold
    echo ""
    echo "  --- Results for threshold $THRESHOLD ---"
    TOTAL_PNL=0
    for f in "$TDIR"/*.txt; do
        sym=$(basename "$f" .txt)
        pnl=$(grep -oP 'Gross P&L: \$([+\-]?[\d,]+)' "$f" | grep -oP '[+\-]?[\d,]+' | tr -d ',')
        overrides=$(grep -c "VWAP_OVERRIDE" "$f" 2>/dev/null || echo "0")
        if [ -n "$pnl" ]; then
            TOTAL_PNL=$((TOTAL_PNL + pnl))
            if [ "$overrides" -gt 0 ]; then
                echo "  $sym: \$$pnl (${overrides} overrides)"
            fi
        fi
    done
    echo "  TOTAL P&L: \$$TOTAL_PNL"

    # Regression check
    echo ""
    echo "  --- Regression Check (threshold=$THRESHOLD) ---"
    for session in "${REGRESSION[@]}"; do
        SYM=$(echo "$session" | cut -d' ' -f1)
        DATE=$(echo "$session" | cut -d' ' -f2)
        OUTFILE="$TDIR/${SYM}_${DATE}.txt"
        pnl=$(grep -oP 'Gross P&L: \$([+\-]?[\d,]+)' "$OUTFILE" | grep -oP '[+\-]?[\d,]+' | tr -d ',')
        echo "  $SYM $DATE: \$$pnl"
    done
done
