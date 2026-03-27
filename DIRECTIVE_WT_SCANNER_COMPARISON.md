# DIRECTIVE: Warrior Trading Scanner vs Our Scanner — Full Comparison Backtest

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — Establishes the bot's true stock selection parameters beyond Ross's five pillars

---

## Context

Manny manually recorded every stock that appeared on the Warrior Trading scanner during 10 trading days (Jan 12-16 and Feb 9-13, 2026). He added them to the watchlist as they appeared, simulating live trading from 7-10 AM Eastern.

**The problem:** Our scanner found only **11 of 91 stocks (12%)** that the WT scanner surfaced. The entire February week was a **0% overlap**. This means we're potentially missing huge amounts of tradeable volume.

**The question:** If the bot had access to the full WT scanner feed, how much more P&L would it generate? And more importantly — which characteristics predict bot profitability? We need to find the bot's own "pillars" independent of Ross's criteria.

### What We Already Know (from our scanner's 11 overlapping stocks)
- ROLR Jan 14: +$1,413 (5 trades)
- GWAV Jan 16: +$6,735 (2 trades)
- LCFY Jan 16: -$627 (2 trades)
- Others: not yet backtested with study-aligned discovery times

### Why Our Scanner Missed 80 Stocks
- 36 stocks (45%): Float > 10M max
- 32 stocks (40%): Float in range but gap/vol/RVOL below thresholds
- 12 stocks (15%): No float data (Profile X)

---

## Step 0: Git Pull + Verify

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

Quick regression:
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

**STOP if regression fails.**

---

## Step 1: Environment Setup

V1 config (SQ mechanical exits, proven strongest):

```bash
export WB_SQUEEZE_ENABLED=1
export WB_SQ_PARA_ENABLED=1
export WB_SQ_NEW_HOD_REQUIRED=1
export WB_SQ_MAX_LOSS_DOLLARS=500
export WB_MP_ENABLED=1
export WB_PILLAR_GATES_ENABLED=0    # OFF — test what the bot CAN do
export WB_ROSS_EXIT_ENABLED=0       # V1 config
export WB_CLASSIFIER_ENABLED=1
export WB_EXHAUSTION_ENABLED=1
export WB_CONTINUATION_HOLD_ENABLED=1
export WB_MAX_NOTIONAL=50000
export WB_RISK_DOLLARS=1000
```

---

## Step 2: Run All 91 Backtests

Each stock uses its WT scanner discovery time as sim_start (the moment the stock appeared on Warrior Trading's scanner). Run until 11:00 AM ET.

**IMPORTANT:** Use `--feed databento --tick-cache tick_cache/` for all runs. 76 of 91 need fresh Databento fetches. This will take time and use API credits. If a stock returns "NO DATA" or errors, log it and move on.

**Capture ALL output to files for analysis:**

```bash
mkdir -p /tmp/wt_study
```

### Day 1: January 12, 2026 (9 stocks)

```bash
echo "=== DAY 1: Jan 12 ===" | tee /tmp/wt_study/day_header_0112.txt

python simulate.py NCEL 2026-01-12 07:04 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NCEL_0112.txt
python simulate.py LYRA 2026-01-12 07:38 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/LYRA_0112.txt
python simulate.py GNPX 2026-01-12 08:11 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/GNPX_0112.txt
python simulate.py VOR 2026-01-12 08:23 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/VOR_0112.txt
python simulate.py OM 2026-01-12 08:34 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/OM_0112.txt
python simulate.py OSS 2026-01-12 08:43 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/OSS_0112.txt
python simulate.py AKAN 2026-01-12 09:09 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/AKAN_0112.txt
python simulate.py SOGP 2026-01-12 09:12 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SOGP_0112.txt
python simulate.py NBY 2026-01-12 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NBY_0112.txt
```

### Day 2: January 13, 2026 (12 stocks)

```bash
echo "=== DAY 2: Jan 13 ===" | tee /tmp/wt_study/day_header_0113.txt

python simulate.py SPRC 2026-01-13 07:02 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SPRC_0113.txt
python simulate.py PDYN 2026-01-13 07:16 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/PDYN_0113.txt
python simulate.py AHMA 2026-01-13 07:20 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/AHMA_0113.txt
python simulate.py OSS 2026-01-13 07:25 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/OSS_0113.txt
python simulate.py BCTX 2026-01-13 07:40 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/BCTX_0113.txt
python simulate.py FJET 2026-01-13 08:10 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/FJET_0113.txt
python simulate.py UMAC 2026-01-13 08:15 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/UMAC_0113.txt
python simulate.py RCAT 2026-01-13 08:24 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/RCAT_0113.txt
python simulate.py NUKK 2026-01-13 08:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NUKK_0113.txt
python simulate.py RZLV 2026-01-13 08:31 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/RZLV_0113.txt
python simulate.py WATT 2026-01-13 08:55 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/WATT_0113.txt
python simulate.py CELZ 2026-01-13 09:15 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CELZ_0113.txt
```

### Day 3: January 14, 2026 (9 stocks)

```bash
echo "=== DAY 3: Jan 14 ===" | tee /tmp/wt_study/day_header_0114.txt

python simulate.py NRXP 2026-01-14 07:10 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NRXP_0114.txt
python simulate.py AZI 2026-01-14 07:28 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/AZI_0114.txt
python simulate.py GSIT 2026-01-14 08:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/GSIT_0114.txt
python simulate.py FEED 2026-01-14 08:01 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/FEED_0114.txt
python simulate.py ROLR 2026-01-14 08:06 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ROLR_0114.txt
python simulate.py XAIR 2026-01-14 08:32 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/XAIR_0114.txt
python simulate.py KULR 2026-01-14 08:37 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/KULR_0114.txt
python simulate.py CMND 2026-01-14 08:56 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CMND_0114.txt
python simulate.py HOVR 2026-01-14 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/HOVR_0114.txt
```

### Day 4: January 15, 2026 (10 stocks)

```bash
echo "=== DAY 4: Jan 15 ===" | tee /tmp/wt_study/day_header_0115.txt

python simulate.py SPHL 2026-01-15 07:01 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SPHL_0115.txt
python simulate.py ARAI 2026-01-15 07:33 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ARAI_0115.txt
python simulate.py CGTL 2026-01-15 07:38 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CGTL_0115.txt
python simulate.py BNKK 2026-01-15 08:01 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/BNKK_0115.txt
python simulate.py QMCO 2026-01-15 08:31 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/QMCO_0115.txt
python simulate.py NITO 2026-01-15 08:33 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NITO_0115.txt
python simulate.py CJMB 2026-01-15 08:45 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CJMB_0115.txt
python simulate.py AUID 2026-01-15 08:57 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/AUID_0115.txt
python simulate.py IPW 2026-01-15 09:23 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/IPW_0115.txt
python simulate.py MTVA 2026-01-15 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/MTVA_0115.txt
```

### Day 5: January 16, 2026 (9 stocks)

```bash
echo "=== DAY 5: Jan 16 ===" | tee /tmp/wt_study/day_header_0116.txt

python simulate.py STSS 2026-01-16 07:01 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/STSS_0116.txt
python simulate.py GWAV 2026-01-16 07:10 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/GWAV_0116.txt
python simulate.py STKH 2026-01-16 07:14 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/STKH_0116.txt
python simulate.py BDRX 2026-01-16 07:27 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/BDRX_0116.txt
python simulate.py JFBR 2026-01-16 07:37 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/JFBR_0116.txt
python simulate.py LCFY 2026-01-16 08:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/LCFY_0116.txt
python simulate.py DXF 2026-01-16 08:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/DXF_0116.txt
python simulate.py NUKK 2026-01-16 08:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NUKK_0116.txt
python simulate.py OCG 2026-01-16 09:05 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/OCG_0116.txt
```

### Day 6: February 9, 2026 (6 stocks)

```bash
echo "=== DAY 6: Feb 9 ===" | tee /tmp/wt_study/day_header_0209.txt

python simulate.py LIMN 2026-02-09 07:33 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/LIMN_0209.txt
python simulate.py MNTS 2026-02-09 08:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/MNTS_0209.txt
python simulate.py NRXP 2026-02-09 08:04 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NRXP_0209.txt
python simulate.py ICU 2026-02-09 08:20 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ICU_0209.txt
python simulate.py SXTC 2026-02-09 09:05 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SXTC_0209.txt
python simulate.py HIMS 2026-02-09 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/HIMS_0209.txt
```

### Day 7: February 10, 2026 (7 stocks)

```bash
echo "=== DAY 7: Feb 10 ===" | tee /tmp/wt_study/day_header_0210.txt

python simulate.py SMX 2026-02-10 07:14 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SMX_0210.txt
python simulate.py AZI 2026-02-10 07:15 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/AZI_0210.txt
python simulate.py CCCX 2026-02-10 09:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CCCX_0210.txt
python simulate.py VELO 2026-02-10 09:02 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/VELO_0210.txt
python simulate.py UPWK 2026-02-10 09:28 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/UPWK_0210.txt
python simulate.py ESOA 2026-02-10 09:28 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ESOA_0210.txt
python simulate.py TECX 2026-02-10 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/TECX_0210.txt
```

### Day 8: February 11, 2026 (8 stocks)

```bash
echo "=== DAY 8: Feb 11 ===" | tee /tmp/wt_study/day_header_0211.txt

python simulate.py RVSN 2026-02-11 07:34 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/RVSN_0211.txt
python simulate.py ASBP 2026-02-11 07:45 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ASBP_0211.txt
python simulate.py PRFX 2026-02-11 08:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/PRFX_0211.txt
python simulate.py VELO 2026-02-11 08:34 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/VELO_0211.txt
python simulate.py OMDA 2026-02-11 09:02 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/OMDA_0211.txt
python simulate.py PLYX 2026-02-11 09:24 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/PLYX_0211.txt
python simulate.py ROLR 2026-02-11 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ROLR_0211.txt
python simulate.py RPD 2026-02-11 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/RPD_0211.txt
```

### Day 9: February 12, 2026 (10 stocks)

```bash
echo "=== DAY 9: Feb 12 ===" | tee /tmp/wt_study/day_header_0212.txt

python simulate.py JZXN 2026-02-12 07:26 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/JZXN_0212.txt
python simulate.py FSLY 2026-02-12 07:26 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/FSLY_0212.txt
python simulate.py PODC 2026-02-12 08:01 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/PODC_0212.txt
python simulate.py PTRN 2026-02-12 08:20 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/PTRN_0212.txt
python simulate.py SMR 2026-02-12 08:27 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SMR_0212.txt
python simulate.py ONCO 2026-02-12 08:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ONCO_0212.txt
python simulate.py JDZG 2026-02-12 08:34 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/JDZG_0212.txt
python simulate.py NVCR 2026-02-12 09:22 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NVCR_0212.txt
python simulate.py PMI 2026-02-12 09:22 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/PMI_0212.txt
python simulate.py QVCGP 2026-02-12 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/QVCGP_0212.txt
```

### Day 10: February 13, 2026 (11 stocks)

```bash
echo "=== DAY 10: Feb 13 ===" | tee /tmp/wt_study/day_header_0213.txt

python simulate.py MGRT 2026-02-13 07:54 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/MGRT_0213.txt
python simulate.py MLEC 2026-02-13 08:03 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/MLEC_0213.txt
python simulate.py DBGI 2026-02-13 08:39 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/DBGI_0213.txt
python simulate.py CRSR 2026-02-13 08:41 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CRSR_0213.txt
python simulate.py NCI 2026-02-13 08:43 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/NCI_0213.txt
python simulate.py HSDT 2026-02-13 09:01 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/HSDT_0213.txt
python simulate.py CNVS 2026-02-13 09:04 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/CNVS_0213.txt
python simulate.py WEN 2026-02-13 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/WEN_0213.txt
python simulate.py MCRB 2026-02-13 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/MCRB_0213.txt
python simulate.py SRTS 2026-02-13 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/SRTS_0213.txt
python simulate.py ELVA 2026-02-13 09:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/wt_study/ELVA_0213.txt
```

---

## Step 3: Parse Results and Build Analysis

After all 91 backtests, run this script to extract results from the output files:

```bash
python3 << 'PYEOF'
import re, os, json

results_dir = "/tmp/wt_study"
float_cache_file = os.path.expanduser("~/warrior_bot/scanner_results/float_cache.json")

with open(float_cache_file) as f:
    float_cache = json.load(f)

# Stock metadata from the study
stocks = [
    # (ticker, date, sim_start, wt_discovery_time)
    # Day 1: Jan 12
    ("NCEL", "2026-01-12", "07:04", "07:04"),
    ("LYRA", "2026-01-12", "07:38", "07:38"),
    ("GNPX", "2026-01-12", "08:11", "08:11"),
    ("VOR", "2026-01-12", "08:23", "08:23"),
    ("OM", "2026-01-12", "08:34", "08:34"),
    ("OSS", "2026-01-12", "08:43", "08:43"),
    ("AKAN", "2026-01-12", "09:09", "09:09"),
    ("SOGP", "2026-01-12", "09:12", "09:12"),
    ("NBY", "2026-01-12", "09:30", "09:30"),
    # Day 2: Jan 13
    ("SPRC", "2026-01-13", "07:02", "07:02"),
    ("PDYN", "2026-01-13", "07:16", "07:16"),
    ("AHMA", "2026-01-13", "07:20", "07:20"),
    ("OSS", "2026-01-13", "07:25", "07:25"),
    ("BCTX", "2026-01-13", "07:40", "07:40"),
    ("FJET", "2026-01-13", "08:10", "08:10"),
    ("UMAC", "2026-01-13", "08:15", "08:15"),
    ("RCAT", "2026-01-13", "08:24", "08:24"),
    ("NUKK", "2026-01-13", "08:30", "08:30"),
    ("RZLV", "2026-01-13", "08:31", "08:31"),
    ("WATT", "2026-01-13", "08:55", "08:55"),
    ("CELZ", "2026-01-13", "09:15", "09:15"),
    # Day 3: Jan 14
    ("NRXP", "2026-01-14", "07:10", "07:10"),
    ("AZI", "2026-01-14", "07:28", "07:28"),
    ("GSIT", "2026-01-14", "08:00", "08:00"),
    ("FEED", "2026-01-14", "08:01", "08:01"),
    ("ROLR", "2026-01-14", "08:06", "08:06"),
    ("XAIR", "2026-01-14", "08:32", "08:32"),
    ("KULR", "2026-01-14", "08:37", "08:37"),
    ("CMND", "2026-01-14", "08:56", "08:56"),
    ("HOVR", "2026-01-14", "09:30", "09:30"),
    # Day 4: Jan 15
    ("SPHL", "2026-01-15", "07:01", "07:01"),
    ("ARAI", "2026-01-15", "07:33", "07:33"),
    ("CGTL", "2026-01-15", "07:38", "07:38"),
    ("BNKK", "2026-01-15", "08:01", "08:01"),
    ("QMCO", "2026-01-15", "08:31", "08:31"),
    ("NITO", "2026-01-15", "08:33", "08:33"),
    ("CJMB", "2026-01-15", "08:45", "08:45"),
    ("AUID", "2026-01-15", "08:57", "08:57"),
    ("IPW", "2026-01-15", "09:23", "09:23"),
    ("MTVA", "2026-01-15", "09:30", "09:30"),
    # Day 5: Jan 16
    ("STSS", "2026-01-16", "07:01", "07:01"),
    ("GWAV", "2026-01-16", "07:10", "07:10"),
    ("STKH", "2026-01-16", "07:14", "07:14"),
    ("BDRX", "2026-01-16", "07:27", "07:27"),
    ("JFBR", "2026-01-16", "07:37", "07:37"),
    ("LCFY", "2026-01-16", "08:00", "08:00"),
    ("DXF", "2026-01-16", "08:30", "08:30"),
    ("NUKK", "2026-01-16", "08:30", "08:30"),
    ("OCG", "2026-01-16", "09:05", "09:05"),
    # Day 6: Feb 9
    ("LIMN", "2026-02-09", "07:33", "07:33"),
    ("MNTS", "2026-02-09", "08:00", "08:00"),
    ("NRXP", "2026-02-09", "08:04", "08:04"),
    ("ICU", "2026-02-09", "08:20", "08:20"),
    ("SXTC", "2026-02-09", "09:05", "09:05"),
    ("HIMS", "2026-02-09", "09:30", "09:30"),
    # Day 7: Feb 10
    ("SMX", "2026-02-10", "07:14", "07:14"),
    ("AZI", "2026-02-10", "07:15", "07:15"),
    ("CCCX", "2026-02-10", "09:00", "09:00"),
    ("VELO", "2026-02-10", "09:02", "09:02"),
    ("UPWK", "2026-02-10", "09:28", "09:28"),
    ("ESOA", "2026-02-10", "09:28", "09:28"),
    ("TECX", "2026-02-10", "09:30", "09:30"),
    # Day 8: Feb 11
    ("RVSN", "2026-02-11", "07:34", "07:34"),
    ("ASBP", "2026-02-11", "07:45", "07:45"),
    ("PRFX", "2026-02-11", "08:30", "08:30"),
    ("VELO", "2026-02-11", "08:34", "08:34"),
    ("OMDA", "2026-02-11", "09:02", "09:02"),
    ("PLYX", "2026-02-11", "09:24", "09:24"),
    ("ROLR", "2026-02-11", "09:30", "09:30"),
    ("RPD", "2026-02-11", "09:30", "09:30"),
    # Day 9: Feb 12
    ("JZXN", "2026-02-12", "07:26", "07:26"),
    ("FSLY", "2026-02-12", "07:26", "07:26"),
    ("PODC", "2026-02-12", "08:01", "08:01"),
    ("PTRN", "2026-02-12", "08:20", "08:20"),
    ("SMR", "2026-02-12", "08:27", "08:27"),
    ("ONCO", "2026-02-12", "08:30", "08:30"),
    ("JDZG", "2026-02-12", "08:34", "08:34"),
    ("NVCR", "2026-02-12", "09:22", "09:22"),
    ("PMI", "2026-02-12", "09:22", "09:22"),
    ("QVCGP", "2026-02-12", "09:30", "09:30"),
    # Day 10: Feb 13
    ("MGRT", "2026-02-13", "07:54", "07:54"),
    ("MLEC", "2026-02-13", "08:03", "08:03"),
    ("DBGI", "2026-02-13", "08:39", "08:39"),
    ("CRSR", "2026-02-13", "08:41", "08:41"),
    ("NCI", "2026-02-13", "08:43", "08:43"),
    ("HSDT", "2026-02-13", "09:01", "09:01"),
    ("CNVS", "2026-02-13", "09:04", "09:04"),
    ("WEN", "2026-02-13", "09:30", "09:30"),
    ("MCRB", "2026-02-13", "09:30", "09:30"),
    ("SRTS", "2026-02-13", "09:30", "09:30"),
    ("ELVA", "2026-02-13", "09:30", "09:30"),
]

# Which stocks our scanner also found
our_scanner_found = {
    ("NCEL", "2026-01-12"), ("GNPX", "2026-01-12"),
    ("SPRC", "2026-01-13"), ("AHMA", "2026-01-13"), ("BCTX", "2026-01-13"),
    ("ROLR", "2026-01-14"), ("CMND", "2026-01-14"),
    ("SPHL", "2026-01-15"), ("CJMB", "2026-01-15"),
    ("GWAV", "2026-01-16"), ("LCFY", "2026-01-16"),
}

results = []
for ticker, date, sim_start, wt_time in stocks:
    mmdd = date[5:7] + date[8:10]
    fname = f"{results_dir}/{ticker}_{mmdd}.txt"

    flt = float_cache.get(ticker)
    float_m = f"{flt/1e6:.1f}" if flt else "?"
    float_bucket = "?"
    if flt:
        if flt < 1e6: float_bucket = "<1M"
        elif flt < 5e6: float_bucket = "1-5M"
        elif flt < 10e6: float_bucket = "5-10M"
        elif flt < 20e6: float_bucket = "10-20M"
        elif flt < 50e6: float_bucket = "20-50M"
        elif flt < 100e6: float_bucket = "50-100M"
        else: float_bucket = ">100M"

    in_our_scanner = "YES" if (ticker, date) in our_scanner_found else "no"

    if not os.path.exists(fname):
        results.append({
            "ticker": ticker, "date": date, "sim_start": sim_start,
            "trades": "?", "pnl": "?", "float_m": float_m, "float_bucket": float_bucket,
            "in_our_scanner": in_our_scanner, "status": "FILE MISSING"
        })
        continue

    with open(fname) as f:
        content = f.read()

    if "NO DATA" in content.upper() or "Error" in content or "error" in content.lower():
        results.append({
            "ticker": ticker, "date": date, "sim_start": sim_start,
            "trades": "—", "pnl": "N/A", "float_m": float_m, "float_bucket": float_bucket,
            "in_our_scanner": in_our_scanner, "status": "NO DATA"
        })
        continue

    # Parse trade count and P&L from output
    # Look for "No trades taken" or trade summary lines
    if "No trades taken" in content:
        results.append({
            "ticker": ticker, "date": date, "sim_start": sim_start,
            "trades": 0, "pnl": 0, "float_m": float_m, "float_bucket": float_bucket,
            "in_our_scanner": in_our_scanner, "status": "0 trades"
        })
        continue

    # Try to find P&L total
    pnl_match = re.search(r'Net P&L:\s*\$?([\-\d,\.]+)', content)
    if not pnl_match:
        pnl_match = re.search(r'TOTAL.*?P&L.*?\$?([\-\d,\.]+)', content, re.IGNORECASE)

    trade_count_match = re.search(r'Trades:\s*(\d+)', content)
    if not trade_count_match:
        trade_count_match = re.search(r'(\d+)\s+trade', content, re.IGNORECASE)

    pnl = pnl_match.group(1).replace(',', '') if pnl_match else "PARSE"
    trades = trade_count_match.group(1) if trade_count_match else "PARSE"

    results.append({
        "ticker": ticker, "date": date, "sim_start": sim_start,
        "trades": trades, "pnl": pnl, "float_m": float_m, "float_bucket": float_bucket,
        "in_our_scanner": in_our_scanner, "status": "OK"
    })

# Output results as JSON for further analysis
with open("/tmp/wt_study_results.json", "w") as f:
    json.dump(results, f, indent=2)

# Print summary table
print("| Date | Ticker | Start | Trades | P&L | Float(M) | Bucket | Our Scanner | Status |")
print("|---|---|---|---|---|---|---|---|---|")
for r in results:
    pnl_str = f"${r['pnl']}" if r['pnl'] not in ('?', 'N/A', 'PARSE') else r['pnl']
    print(f"| {r['date']} | {r['ticker']} | {r['sim_start']} | {r['trades']} | {pnl_str} | {r['float_m']} | {r['float_bucket']} | {r['in_our_scanner']} | {r['status']} |")

print(f"\nTotal stocks: {len(results)}")
PYEOF
```

---

## Step 4: Build the Analysis Report

Save to `cowork_reports/2026-03-24_wt_scanner_comparison.md`. The report MUST include these sections — this is the data Manny needs to define the bot's own stock selection pillars:

### Section A: Overall Results
- Total P&L across all 91 stocks
- Win rate, avg R-multiple
- Stocks with trades vs 0-trade stocks vs NO DATA

### Section B: Our Scanner vs WT Scanner
Compare side-by-side:
- **Our scanner stocks (11):** How did they do when entered at WT discovery times?
- **WT-only stocks (80):** What P&L are we leaving on the table?
- Net delta: How much MORE would the bot make with WT scanner feed?

### Section C: Performance by Float Bucket (THE KEY ANALYSIS)
Break down P&L by float range. This tells us whether expanding beyond 10M is profitable:
```
Float < 1M:      XX stocks, $XXX P&L, XX% win rate
Float 1-5M:      XX stocks, $XXX P&L, XX% win rate  (current sweet spot)
Float 5-10M:     XX stocks, $XXX P&L, XX% win rate  (current max)
Float 10-20M:    XX stocks, $XXX P&L, XX% win rate  ← expand here?
Float 20-50M:    XX stocks, $XXX P&L, XX% win rate  ← too far?
Float 50-100M:   XX stocks, $XXX P&L, XX% win rate
Float > 100M:    XX stocks, $XXX P&L, XX% win rate
Unknown float:   XX stocks, $XXX P&L, XX% win rate
```

### Section D: Performance by Discovery Time
When does the bot perform best?
```
7:00-7:30 AM:    XX stocks, $XXX P&L, XX% win rate
7:30-8:00 AM:    XX stocks, $XXX P&L, XX% win rate
8:00-8:30 AM:    XX stocks, $XXX P&L, XX% win rate
8:30-9:00 AM:    XX stocks, $XXX P&L, XX% win rate
9:00-9:30 AM:    XX stocks, $XXX P&L, XX% win rate
9:30-10:00 AM:   XX stocks, $XXX P&L, XX% win rate
```

### Section E: Performance by Strategy
- SQ trades: count, P&L, win rate, avg R
- MP trades: count, P&L, win rate, avg R
- Which strategy works better on WT-only stocks vs overlap stocks?

### Section F: The Bot's Pillars (Recommendations)
Based on the data, what are the optimal stock selection criteria for THE BOT (not Ross)?
- Optimal float range
- Minimum/maximum gap%
- Discovery time sweet spot
- Volume/RVOL thresholds
- Which WT scanner alert types produce the most bot profit?

---

## Step 5: Commit and Push

```bash
git add tick_cache/ cowork_reports/2026-03-24_wt_scanner_comparison.md
git commit -m "$(cat <<'EOF'
WT scanner comparison: 91 stocks from Manny's Feb study

Backtested every stock from 10 days of manual Warrior Trading
scanner tracking (Jan 12-16, Feb 9-13, 2026). Used WT discovery
times as sim_start to simulate manual watchlist entry.

Comparison: our scanner found 11/91 (12%). This tests the P&L
delta and identifies optimal stock selection criteria for the bot.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Important Notes

- **Databento costs:** 76 fresh fetches needed. Monitor API usage. Each fetch is one symbol-day of trade-level ticks.
- **Run time estimate:** ~60-90 seconds per stock in tick mode = ~90-135 minutes total for all 91.
- **Some tickers may fail:** QVCGP (preferred shares), SOGP, STKH, DXF, etc. may not be in Databento. Log and move on.
- **Float data from float_cache.json.** 17 stocks have no float data — they'll be in the "Unknown" bucket. CC should try to resolve floats for any that trade successfully.
- **The Feb week is critical.** Our scanner found ZERO of those stocks. If the bot is profitable on them, that's pure found money.

## What We're Looking For

The goal is NOT to match Ross's five pillars. The goal is to discover the BOT's pillars:

1. **Where does SQ dominate?** Low float squeezes are obvious. But does SQ also work on 15M float stocks? 30M? Where does it break down?
2. **Where does MP shine?** Do micro-pullbacks fire on the larger-float WT stocks? Or only on sub-10M?
3. **Is there a "Goldilocks zone"?** Maybe 5-20M float is the sweet spot where we get enough volume for clean entries but enough float scarcity for squeezes.
4. **Time-of-day edge:** Does the bot do better on early birds (7:00-8:00) or mid-morning runners (8:30-9:30)?
5. **What should we AVOID?** If stocks above 50M float consistently produce losses, that's a hard filter to keep.

This data will directly inform the next scanner configuration.
