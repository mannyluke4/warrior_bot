#!/bin/bash
# Phase 1: Run all 28 sessions to capture VWAP-blocked arms
cd /Users/mannyluke/warrior_bot
source venv/bin/activate

OUTDIR="studies/vwap_override/phase1_output"
mkdir -p "$OUTDIR"

declare -a SESSIONS=(
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

for session in "${SESSIONS[@]}"; do
    SYM=$(echo "$session" | cut -d' ' -f1)
    DATE=$(echo "$session" | cut -d' ' -f2)
    OUTFILE="$OUTDIR/${SYM}_${DATE}.txt"
    echo "Running $SYM $DATE..."
    python simulate.py "$SYM" "$DATE" 07:00 12:00 --profile A --ticks --no-fundamentals -v > "$OUTFILE" 2>&1
    # Extract key info
    BLOCKED=$(grep -c "VWAP_BLOCKED_ARM" "$OUTFILE" 2>/dev/null || echo "0")
    ARMED=$(grep -c "ARMED" "$OUTFILE" 2>/dev/null || echo "0")
    echo "  $SYM $DATE: $ARMED ARMs, $BLOCKED VWAP-blocked"
done

echo ""
echo "=== SUMMARY ==="
echo "Total VWAP-blocked arms across all sessions:"
grep -r "VWAP_BLOCKED_ARM" "$OUTDIR"/ | wc -l
echo ""
echo "All blocked arm details:"
grep -r "BLOCKED:" "$OUTDIR"/
grep -r "post_block:" "$OUTDIR"/
