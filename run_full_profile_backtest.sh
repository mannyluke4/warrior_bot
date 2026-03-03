#!/bin/bash
# Full 137-Stock Profile System Backtest
# Run from repo root

set -e
cd "$(dirname "$0")"

source venv/bin/activate

RESULTS_FILE="full_profile_backtest_results.csv"
OUTPUT_DIR="full_profile_backtest_outputs"
mkdir -p "$OUTPUT_DIR"

echo "symbol,date,float_m,scanner_time,profile,baseline_pnl,profile_pnl,profile_trades,reason" > "$RESULTS_FILE"

run_profiled() {
    local sym=$1 date=$2 float=$3 scanner=$4 profile=$5 baseline=$6 reason=$7
    local outfile="$OUTPUT_DIR/${sym}_${date}_${profile}.txt"
    echo "=== $sym $date (Profile $profile) ==="

    python simulate.py "$sym" "$date" 07:00 12:00 \
        --profile "$profile" --ticks --feed databento --no-fundamentals \
        > "$outfile" 2>&1 || true

    # Parse P&L and trades with Python for reliability
    result=$(python3 -c "
import re, sys
txt = open('$outfile').read()
pnl_m = re.search(r'Gross P&L: \\\$([+-]?[\d,]+)', txt)
tr_m  = re.search(r'Trades:\s+(\d+)', txt)
pnl   = pnl_m.group(1).replace(',','') if pnl_m else '0'
tr    = tr_m.group(1) if tr_m else '0'
print(f'{pnl},{tr}')
")
    local pnl=$(echo "$result" | cut -d',' -f1)
    local trades=$(echo "$result" | cut -d',' -f2)

    echo "  Profile $profile: \$$pnl ($trades trades) | Baseline: \$$baseline"
    echo "$sym,$date,$float,$scanner,$profile,$baseline,$pnl,$trades,$reason" >> "$RESULTS_FILE"
}

echo "============================================"
echo "  FULL 137-STOCK PROFILE BACKTEST"
echo "  Started: $(date)"
echo "============================================"
echo ""

echo "--- PROFILE A: Micro-Float Pre-Market (57 stocks) ---"
run_profiled ACON 2026-01-06 0.7  "07:00" A 0      "micro-float_7am"
run_profiled ACON 2026-01-08 0.7  "07:00" A -2122  "micro-float_7am"
run_profiled ACON 2026-01-27 0.7  "07:00" A 0      "micro-float_7am"
run_profiled ACON 2026-02-13 0.7  "07:00" A -214   "micro-float_7am"
run_profiled APVO 2026-01-09 0.9  "07:00" A 7622   "micro-float_7am"
run_profiled APVO 2026-02-05 0.9  "07:00" A 0      "micro-float_7am"
run_profiled BCTX 2026-01-16 1.7  "07:00" A 0      "micro-float_7am"
run_profiled BCTX 2026-01-27 1.7  "07:00" A 0      "micro-float_7am"
run_profiled BDSX 2026-01-12 3.7  "07:00" A -45    "micro-float_7am"
run_profiled BNAI 2026-01-16 3.3  "07:00" A -674   "micro-float_7am"
run_profiled BNAI 2026-01-28 3.3  "07:00" A 5610   "micro-float_7am"
run_profiled BNAI 2026-02-05 3.3  "07:00" A 160    "micro-float_7am"
run_profiled ELAB 2026-01-06 0.2  "07:00" A 0      "micro-float_7am"
run_profiled ELAB 2026-01-08 0.2  "07:00" A 0      "micro-float_7am"
run_profiled ELAB 2026-01-09 0.2  "07:00" A 0      "micro-float_7am"
run_profiled ENVB 2026-02-19 0.5  "07:00" A 474    "micro-float_7am"
run_profiled FEED 2026-01-16 0.8  "07:00" A 0      "micro-float_7am"
run_profiled GRI  2026-01-27 1.4  "07:00" A 0      "micro-float_7am"
run_profiled GRI  2026-01-28 1.4  "07:00" A 0      "micro-float_7am"
run_profiled GWAV 2026-01-06 0.8  "07:00" A 0      "micro-float_7am"
run_profiled GWAV 2026-01-16 0.8  "07:00" A 6735   "micro-float_7am"
run_profiled GWAV 2026-02-05 0.8  "07:00" A 0      "micro-float_7am"
run_profiled GWAV 2026-02-13 0.8  "07:00" A 0      "micro-float_7am"
run_profiled HIND 2026-01-16 1.5  "07:00" A 0      "micro-float_7am"
run_profiled HIND 2026-01-27 1.5  "07:00" A 260    "micro-float_7am"
run_profiled HIND 2026-02-05 1.5  "07:00" A 0      "micro-float_7am"
run_profiled LCFY 2026-01-16 1.4  "07:00" A -627   "micro-float_7am"
run_profiled MLEC 2026-01-06 0.7  "07:00" A 0      "micro-float_7am"
run_profiled MLEC 2026-01-28 0.7  "07:00" A 0      "micro-float_7am"
run_profiled MLEC 2026-02-13 0.7  "07:00" A 173    "micro-float_7am"
run_profiled MNTS 2026-02-06 1.3  "07:00" A 862    "micro-float_7am"
run_profiled MOVE 2026-01-23 0.6  "07:00" A -156   "micro-float_7am"
run_profiled MOVE 2026-01-27 0.6  "07:00" A 5502   "micro-float_7am"
run_profiled PAVM 2026-01-16 0.7  "07:00" A 0      "micro-float_7am"
run_profiled PAVM 2026-01-21 0.7  "07:00" A 1586   "micro-float_7am"
run_profiled PAVM 2026-02-05 0.7  "07:00" A 0      "micro-float_7am"
run_profiled PMAX 2026-01-13 1.2  "07:00" A -1098  "micro-float_7am"
run_profiled ROLR 2026-01-06 3.6  "07:00" A -1422  "micro-float_7am"
run_profiled ROLR 2026-01-14 3.6  "07:00" A 1644   "micro-float_7am"
run_profiled ROLR 2026-01-16 3.6  "07:00" A -1228  "micro-float_7am"
run_profiled ROLR 2026-02-13 3.6  "07:00" A 0      "micro-float_7am"
run_profiled RVSN 2026-01-27 1.8  "07:00" A 0      "micro-float_7am"
run_profiled RVSN 2026-02-05 1.8  "07:00" A 0      "micro-float_7am"
run_profiled SHPH 2026-01-16 1.6  "07:00" A -1111  "micro-float_7am"
run_profiled SLE  2026-01-23 0.7  "07:00" A -390   "micro-float_7am"
run_profiled SLE  2026-01-27 0.7  "07:00" A 0      "micro-float_7am"
run_profiled SNSE 2026-01-28 0.7  "07:00" A 0      "micro-float_7am"
run_profiled SNSE 2026-02-05 0.7  "07:00" A 0      "micro-float_7am"
run_profiled SNSE 2026-02-18 0.7  "07:00" A -125   "micro-float_7am"
run_profiled SXTP 2026-01-27 0.9  "07:00" A -2078  "micro-float_7am"
run_profiled SXTP 2026-01-28 0.9  "07:00" A 0      "micro-float_7am"
run_profiled TNMG 2026-01-06 1.2  "07:00" A 0      "micro-float_7am"
run_profiled TNMG 2026-01-16 1.2  "07:00" A -481   "micro-float_7am"
run_profiled TWG  2026-01-20 0.5  "07:00" A 0      "micro-float_7am"
run_profiled VERO 2026-01-06 1.6  "07:00" A 0      "micro-float_7am"
run_profiled VERO 2026-01-16 1.6  "07:00" A 6890   "micro-float_7am"
run_profiled VERO 2026-02-05 1.6  "07:00" A 0      "micro-float_7am"

echo ""
echo "--- PROFILE B: Mid-Float L2-Assisted (16 stocks) ---"
run_profiled ANPA 2026-01-06 12.5 "07:00" B -2730  "mid-float_7am"
run_profiled ANPA 2026-01-09 12.5 "07:00" B 2088   "mid-float_7am"
run_profiled ANPA 2026-02-13 12.5 "07:00" B 0      "mid-float_7am"
run_profiled AZI  2026-01-09 44.5 "07:00" B 0      "mid-float_7am"
run_profiled AZI  2026-01-16 44.5 "07:00" B 0      "mid-float_7am"
run_profiled BATL 2026-02-18 7.2  "07:00" B -499   "mid-float_7am"
run_profiled BEEM 2026-01-14 18.0 "07:00" B -900   "mid-float_7am"
run_profiled FLYX 2026-01-06 5.7  "07:00" B 0      "mid-float_7am"
run_profiled FLYX 2026-01-08 5.7  "07:00" B 473    "mid-float_7am"
run_profiled FLYX 2026-01-27 5.7  "07:00" B 0      "mid-float_7am"
run_profiled FLYX 2026-02-13 5.7  "07:00" B 0      "mid-float_7am"
run_profiled IBIO 2026-01-08 27.1 "07:00" B 0      "mid-float_7am"
run_profiled IBIO 2026-01-09 27.1 "07:00" B -267   "mid-float_7am"
run_profiled OPTX 2026-01-06 6.0  "07:00" B -78    "mid-float_7am"
run_profiled OPTX 2026-01-08 6.0  "07:00" B -223   "mid-float_7am"
run_profiled OPTX 2026-01-09 6.0  "07:00" B -1479  "mid-float_7am"

echo ""
echo "--- PROFILE X: Everything Else (64 stocks) ---"
run_profiled AAOI 2026-02-18 72.0  "07:00" X -415   "large-float"
run_profiled AAOI 2026-02-27 72.0  "09:30" X -1950  "non-7am"
run_profiled ACCL 2026-01-16 2.9   "04:00" X -1072  "non-7am"
run_profiled AEVA 2026-02-27 26.7  "09:30" X 0      "non-7am"
run_profiled AGIG 2026-02-27 8.7   "08:00" X 0      "non-7am"
run_profiled AKAN 2026-01-12 0.1   "09:09" X 0      "non-7am"
run_profiled ALMS 2026-01-06 66.3  "07:00" X 3407   "large-float"
run_profiled ALMS 2026-01-09 66.3  "07:00" X -1154  "large-float"
run_profiled ALMS 2026-01-16 66.3  "07:00" X 0      "large-float"
run_profiled ALMS 2026-02-13 66.3  "07:00" X -236   "large-float"
run_profiled ANNA 2026-02-27 9.4   "08:30" X -1088  "non-7am"
run_profiled ARLO 2026-02-27 103.9 "09:20" X -692   "non-7am"
run_profiled ASBP 2026-02-11 2.3   "07:45" X 0      "non-7am"
run_profiled AUID 2026-01-15 11.8  "08:57" X -1683  "non-7am"
run_profiled AZI  2026-01-06 44.5  "07:27" X 783    "non-7am"
run_profiled AZI  2026-02-10 44.5  "07:15" X 0      "non-7am"
run_profiled BATL 2026-02-27 7.2   "08:00" X 1972   "non-7am"
run_profiled CDIO 2026-02-27 1.7   "09:45" X 791    "non-7am"
run_profiled CNVS 2026-02-13 15.0  "09:04" X -731   "non-7am"
run_profiled CRSR 2026-02-13 46.6  "08:41" X -1939  "non-7am"
run_profiled FEED 2026-01-09 0.8   "07:29" X 0      "non-7am"
run_profiled FIGS 2026-02-27 152.3 "09:00" X -1103  "non-7am"
run_profiled FJET 2026-01-13 18.5  "08:10" X -1263  "non-7am"
run_profiled FSLY 2026-02-12 142.9 "07:26" X 176    "non-7am"
run_profiled HCTI 2026-02-27 0.1   "08:00" X 0      "non-7am"
run_profiled HOVR 2026-01-14 29.4  "09:30" X 0      "non-7am"
run_profiled HSDT 2026-02-13 30.1  "09:01" X 0      "non-7am"
run_profiled IBIO 2026-01-06 27.1  "07:46" X -1444  "non-7am"
run_profiled INDO 2026-02-27 9.5   "08:00" X -487   "non-7am"
run_profiled JDZG 2026-02-12 2.8   "08:34" X 0      "non-7am"
run_profiled JFBR 2026-01-16 0     "07:37" X 0      "unknown_float"
run_profiled KORE 2026-02-27 7.6   "08:00" X 0      "non-7am"
run_profiled LBGJ 2026-02-27 16.7  "09:00" X -110   "non-7am"
run_profiled MCRB 2026-02-13 6.8   "09:30" X 113    "non-7am"
run_profiled MRM  2026-02-27 5.8   "08:00" X -1562  "non-7am"
run_profiled MTVA 2026-01-15 1.0   "09:30" X 0      "non-7am"
run_profiled NAMM 2026-02-27 6.8   "08:00" X 0      "non-7am"
run_profiled NCI  2026-02-13 3.5   "08:43" X 577    "non-7am"
run_profiled NGNE 2026-02-27 5.0   "08:00" X 0      "non-7am"
run_profiled NVCR 2026-02-12 94.3  "09:22" X -507   "non-7am"
run_profiled OCG  2026-01-16 0.1   "09:05" X 0      "non-7am"
run_profiled OCUL 2026-01-15 215.5 "07:00" X 0      "large-float"
run_profiled ONMD 2026-02-27 16.4  "08:30" X -2146  "non-7am"
run_profiled OSCR 2026-02-10 249.5 "07:00" X 0      "large-float"
run_profiled PBYI 2026-02-27 38.9  "09:30" X 21     "non-7am"
run_profiled QMCO 2026-01-15 14.4  "08:31" X -1193  "non-7am"
run_profiled RBNE 2026-02-27 2.2   "08:00" X 0      "non-7am"
run_profiled RELY 2026-02-19 173.5 "07:00" X -1090  "large-float"
run_profiled RPD  2026-02-11 57.9  "09:30" X -186   "non-7am"
run_profiled RUN  2026-02-27 228.3 "09:30" X 0      "non-7am"
run_profiled RVSN 2026-02-11 1.8   "07:34" X -1010  "non-7am"
run_profiled SHPH 2026-01-09 1.6   "08:04" X -1033  "non-7am"
run_profiled SMX  2026-02-09 0     "07:00" X 0      "unknown_float"
run_profiled SND  2026-02-27 27.3  "09:00" X 0      "non-7am"
run_profiled SPRC 2026-01-13 0.4   "07:02" X 0      "non-7am"
run_profiled STKH 2026-01-16 660.0 "07:14" X -697   "non-7am"
run_profiled STRZ 2026-02-27 16.7  "08:00" X 94     "non-7am"
run_profiled STSS 2026-01-16 20.3  "07:01" X 0      "non-7am"
run_profiled TMDE 2026-02-27 3.6   "08:00" X -707   "non-7am"
run_profiled TSSI 2026-02-27 21.8  "08:00" X -1116  "non-7am"
run_profiled UPWK 2026-02-10 121.5 "09:28" X -540   "non-7am"
run_profiled VOR  2026-01-12 7.2   "08:23" X 501    "non-7am"
run_profiled WEN  2026-02-13 145.5 "09:30" X -660   "non-7am"
run_profiled XWEL 2026-02-27 4.3   "08:30" X -2949  "non-7am"

echo ""
echo "=== FULL PROFILE BACKTEST COMPLETE === $(date)"
echo "Results saved to: $RESULTS_FILE"
echo ""
echo "=== SUMMARY ==="

python3 -c "
import csv

rows = []
with open('$RESULTS_FILE') as f:
    for r in csv.DictReader(f):
        rows.append(r)

def total(profile):
    return sum(int(r['profile_pnl']) for r in rows if r['profile'] == profile)

def baseline_total(profile):
    return sum(int(r['baseline_pnl']) for r in rows if r['profile'] == profile)

a_pnl = total('A'); b_pnl = total('B'); x_pnl = total('X')
a_base = baseline_total('A'); b_base = baseline_total('B'); x_base = baseline_total('X')
run1 = a_pnl + b_pnl
run2 = a_pnl + b_pnl + x_pnl

print(f'Profile A ({len([r for r in rows if r[\"profile\"]==\"A\"])} stocks): \${a_pnl:+,}  (baseline: \${a_base:+,}  delta: \${a_pnl-a_base:+,})')
print(f'Profile B ({len([r for r in rows if r[\"profile\"]==\"B\"])} stocks): \${b_pnl:+,}  (baseline: \${b_base:+,}  delta: \${b_pnl-b_base:+,})')
print(f'Profile X ({len([r for r in rows if r[\"profile\"]==\"X\"])} stocks): \${x_pnl:+,}  (baseline: \${x_base:+,}  delta: \${x_pnl-x_base:+,})')
print()
print(f'Run 1 (A+B only, skip X): \${run1:+,}')
print(f'Run 2 (A+B+X):            \${run2:+,}')
print(f'Baseline (all default):   -\$196')
print(f'Delta vs baseline (Run1): \${run1-(-196):+,}')
print(f'Delta vs baseline (Run2): \${run2-(-196):+,}')
"
