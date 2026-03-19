#!/bin/bash
# Run all 10 stocks with their correct dates and extract P&L
# Usage: bash run_backtest_suite.sh [label]

LABEL="${1:-test}"
TOTAL=0

echo "=== $LABEL ==="

run_one() {
  SYM=$1
  DATE=$2
  OUTPUT=$(python simulate.py "$SYM" "$DATE" 07:00 12:00 --ticks 2>&1)
  PNL=$(echo "$OUTPUT" | grep "Gross P&L" | tail -1 | sed 's/.*\$//; s/ .*//' | tr -d ',')
  if [ -z "$PNL" ]; then
    PNL="+0"
  fi
  echo "  $SYM $DATE: \$$PNL"
  # Output just the number for summing
  echo "$PNL" | tr -d '+' >> /tmp/backtest_pnl_$$
}

rm -f /tmp/backtest_pnl_$$

run_one ROLR 2026-01-14
run_one MLEC 2026-02-13
run_one VERO 2026-01-16
run_one TNMG 2026-01-16
run_one GWAV 2026-01-16
run_one LCFY 2026-01-16
run_one PAVM 2026-01-21
run_one ACON 2026-01-08
run_one FLYX 2026-01-08
run_one ANPA 2026-01-09

# Sum up
if [ -f /tmp/backtest_pnl_$$ ]; then
  TOTAL=$(cat /tmp/backtest_pnl_$$ | paste -sd+ | bc)
  rm -f /tmp/backtest_pnl_$$
fi
echo "  TOTAL: \$$TOTAL"
