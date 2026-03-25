# DIRECTIVE: Backtest Corrected Tickers from Data Gap Investigation

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — These are the 9 "NO DATA" stocks from the March 23 megatest (now with corrected ticker names) + GLTO Oct 7

---

## Context

On March 23, we backtested 37 of Ross Cameron's January 2025 tickers. **10 returned "NO DATA — not in Databento."** We now know why: most of those tickers were **transcription errors** from Ross's video recaps. The AI transcript misread tickers like BLBX→BBX, RNAZ→ARNAZ, ZEO→ZO, etc.

The Perplexity investigation + Manny's manual verification produced corrected tickers. These are ALL NASDAQ-listed stocks that Databento should cover. This directive backtests each one individually to see what the bot would have done.

**JG (was AURL)** is excluded — it was a duplicate already in our data and WAS backtested on March 23 (made +$1,327).

---

## Step 0: Git Pull + Verify

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

Quick regression (should take ~60 seconds):
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

**STOP if regression fails.**

---

## Step 1: Environment Setup

Match the megatest V1 config exactly:

```bash
export WB_SQUEEZE_ENABLED=1
export WB_SQ_PARA_ENABLED=1
export WB_SQ_NEW_HOD_REQUIRED=1
export WB_SQ_MAX_LOSS_DOLLARS=500
export WB_MP_ENABLED=1
export WB_PILLAR_GATES_ENABLED=0    # OFF — test what the bot CAN do
export WB_ROSS_EXIT_ENABLED=0       # V1 config — SQ mechanical exits only
export WB_CLASSIFIER_ENABLED=1
export WB_EXHAUSTION_ENABLED=1
export WB_CONTINUATION_HOLD_ENABLED=1
export WB_MAX_NOTIONAL=50000
export WB_RISK_DOLLARS=1000
```

---

## Step 2: Run Each Corrected Ticker

For each stock, use the discovery time from Ross's recap as `sim_start` (this approximates when the scanner would have surfaced it). Run until 11:00 AM ET (Ross's active window, per Manny's request).

### 2A. BLBX — Jan 22, 2025 (was "BBX" in transcript)

- **Company:** Blackboxstocks Inc (NASDAQ)
- **Ross P&L:** +$13,036
- **Ross setup:** Premarket news squeeze — $2M financing + merger news, 2M float
- **Ross entry:** ~$3.10-$3.15, ran to $3.80, multiple trades
- **Discovery time:** Premarket — use 07:00

```bash
echo "=== BLBX Jan 22 ==="
python simulate.py BLBX 2025-01-22 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/blbx_jan22.txt
echo ""
```

### 2B. RNAZ — Jan 28, 2025 (was "ARNAZ" in transcript)

- **Company:** TransCode Therapeutics Inc (NASDAQ)
- **Ross P&L:** +$12,234
- **Ross setup:** Daily breakout — "first candle to make new high", halt resumption dip-and-rip, $7.50→$14.00
- **Discovery time:** During session — use 07:00
- **NOTE:** Ross traded this at $7.50-$14.00. Our max price filter is $20. If the price was above $20 when the scanner would have found it, this trade was outside our parameters. The backtest will tell us.

```bash
echo "=== RNAZ Jan 28 ==="
python simulate.py RNAZ 2025-01-28 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/rnaz_jan28.txt
echo ""
```

### 2C. ZEO — Jan 17, 2025 (was "ZO" in transcript)

- **Company:** Zeo Energy Corp (NASDAQ)
- **Ross P&L:** ~$4,864 (bulk of daily P&L, best trade of the day)
- **Ross setup:** VWAP reclaim range trading, 4-5 re-entries in $3.82-$4.20 range
- **Discovery time:** Morning session — use 07:00
- **Float:** 27.56M (above our 10M max — scanner would have filtered this out, but we're testing the strategy)

```bash
echo "=== ZEO Jan 17 ==="
python simulate.py ZEO 2025-01-17 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/zeo_jan17.txt
echo ""
```

### 2D. AMIX — Jan 17, 2025 (was "AIMX" in transcript)

- **Company:** Autonomix Medical Inc (NASDAQ)
- **Ross P&L:** +$1,200 (net — first trade stopped out -$500, second trade 5K shares dip buy $3.50→$4.00 = +$1,600)
- **Ross setup:** News breakout, 8 AM catalyst
- **Discovery time:** 8:00 AM per recap
- **Float:** 11.06M (slightly above 10M max)

```bash
echo "=== AMIX Jan 17 ==="
python simulate.py AMIX 2025-01-17 08:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/amix_jan17.txt
echo ""
```

### 2E. NIXX — Jan 21, 2025 (was "NXX" in transcript)

- **Company:** NiSun International Enterprise Management Inc (NASDAQ)
- **Ross P&L:** +$1,800 (entry $5.45→$6.30, then dip trade at $4.59→$4.90)
- **Ross setup:** News breakout + dip buy, two trades
- **Discovery time:** 7:30 AM per recap
- **Float:** 22.37M (above 10M max)

```bash
echo "=== NIXX Jan 21 ==="
python simulate.py NIXX 2025-01-21 07:30 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/nixx_jan21.txt
echo ""
```

### 2F. EVAX — Jan 24, 2025 (was "EVAC" in transcript)

- **Company:** EVAX (exact company TBD — biotech)
- **Ross P&L:** +$5K-$10K (estimated)
- **Ross setup:** Biotech sympathy play off ALRN/ALUR GLP-1 momentum, $8→$11
- **Discovery time:** Shortly after ALUR started running (~7:01 AM), sympathy play — use 07:00
- **Float:** Unknown (not cached — was Profile X)

```bash
echo "=== EVAX Jan 24 ==="
python simulate.py EVAX 2025-01-24 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/evax_jan24.txt
echo ""
```

### 2G. NVNI — Jan 29, 2025 (was "MVNI" in transcript)

- **Company:** Nvni Group Limited (NASDAQ)
- **Ross P&L:** +$3,920
- **Ross setup:** Multi-trade pattern — first trade at ~$6.00 lost $500, re-entry broke even, third trade at 9:47 AM from ~$4.75 ran to $7.50 (58% move)
- **Discovery time:** Morning session — use 07:00 (to catch all three of Ross's attempts)
- **Float:** 7.03M

```bash
echo "=== NVNI Jan 29 ==="
python simulate.py NVNI 2025-01-29 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/nvni_jan29.txt
echo ""
```

### 2H. ESHA — Jan 9, 2025

- **Company:** ESH Acquisition Corp (NASDAQ, SPAC)
- **Ross P&L:** +$15,556
- **Ross setup:** Unknown (no Jan 9 recap file available)
- **Discovery time:** Unknown — use 07:00
- **Float:** 1.04M
- **NOTE:** Previously returned "NO DATA" under the same ticker. If it still returns no data, this confirms a Databento SPAC coverage gap.

```bash
echo "=== ESHA Jan 9 ==="
python simulate.py ESHA 2025-01-09 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/esha_jan09.txt
echo ""
```

### 2I. INBS — Jan 9, 2025

- **Company:** Intelligent Bio Solutions Inc (NASDAQ)
- **Ross P&L:** +$18,444
- **Ross setup:** Unknown (no Jan 9 recap file available)
- **Discovery time:** Unknown — use 07:00
- **Float:** 0.64M (post-split figure; actual Jan 2025 float was ~4-5M pre-split)
- **NOTE:** Previously returned "NO DATA" under the same ticker. Same test as ESHA.

```bash
echo "=== INBS Jan 9 ==="
python simulate.py INBS 2025-01-09 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/inbs_jan09.txt
echo ""
```

### 2J. GLTO — Oct 7, 2025

- **Company:** GLTO (NASDAQ)
- **Ross P&L:** TBD
- **Discovery time:** 7:00 AM

```bash
echo "=== GLTO Oct 7 ==="
python simulate.py GLTO 2025-10-07 07:00 11:00 --ticks --feed databento --tick-cache tick_cache/ 2>&1 | tee /tmp/glto_oct07.txt
echo ""
```

---

## Step 3: Collect Results

After all 10 backtests complete, compile results:

```bash
python3 -c "
import re, os

results = []
tickers = [
    ('BLBX', '2025-01-22', 'BBX', '+\$13,036'),
    ('RNAZ', '2025-01-28', 'ARNAZ', '+\$12,234'),
    ('ZEO', '2025-01-17', 'ZO', '~\$4,864'),
    ('AMIX', '2025-01-17', 'AIMX', '+\$1,200'),
    ('NIXX', '2025-01-21', 'NXX', '+\$1,800'),
    ('EVAX', '2025-01-24', 'EVAC', '+\$5-10K'),
    ('NVNI', '2025-01-29', 'MVNI', '+\$3,920'),
    ('ESHA', '2025-01-09', 'ESHA', '+\$15,556'),
    ('INBS', '2025-01-09', 'INBS', '+\$18,444'),
    ('GLTO', '2025-10-07', 'GLTO', 'TBD'),
]

print('| Correct Ticker | Date | Was | Ross P&L | Bot Trades | Bot P&L | Strategy | Notes |')
print('|---|---|---|---|---|---|---|---|')

total_bot_pnl = 0
total_trades = 0
no_data_count = 0
zero_trade_count = 0

for ticker, date, was, ross_pnl in tickers:
    fname = f'/tmp/{ticker.lower()}_{date[5:7]}{date[8:10]}.txt'
    if not os.path.exists(fname):
        # Try alternate naming
        month_day = 'jan' + date[8:10]
        fname = f'/tmp/{ticker.lower()}_{month_day}.txt'

    if not os.path.exists(fname):
        print(f'| {ticker} | {date} | {was} | {ross_pnl} | ? | ? | ? | Output file not found |')
        continue

    with open(fname) as f:
        content = f.read()

    if 'NO DATA' in content.upper() or 'no trades' in content.lower() or 'Error' in content:
        if 'NO DATA' in content.upper() or 'Error' in content:
            no_data_count += 1
            print(f'| {ticker} | {date} | {was} | {ross_pnl} | — | N/A | — | NO DATA in Databento |')
        else:
            zero_trade_count += 1
            print(f'| {ticker} | {date} | {was} | {ross_pnl} | 0 | \$0 | — | No setup triggered |')
    else:
        # Parse trade count and P&L from output
        trade_lines = [l for l in content.split('\n') if 'P&L' in l or 'pnl' in l.lower() or 'TOTAL' in l]
        print(f'| {ticker} | {date} | {was} | {ross_pnl} | CHECK | CHECK | CHECK | See /tmp/{ticker.lower()}_*.txt |')

print()
print(f'NO DATA: {no_data_count} stocks')
print(f'Zero trades: {zero_trade_count} stocks')
"
```

**Then manually review each output file** and fill in the actual results table.

---

## Step 4: Write Report

Save to `cowork_reports/2026-03-24_corrected_tickers_backtest.md` with:

1. **Per-stock results table** — ticker, date, Ross P&L, bot trades, bot P&L, strategy, exit reasons
2. **Comparison with March 23 megatest** — these 9 stocks were previously "NO DATA", now we know the actual results
3. **Updated grand total** — add these results to the March 23 megatest total (+$42,818 from 25 stocks). What's the new combined number?
4. **Scanner implications:**
   - Which of these would our scanner find WITH the overhaul changes (Profile X removed, 5-min checkpoints)?
   - Which are still blocked by float > 10M? (ZEO 27.5M, AMIX 11M, NIXX 22.4M)
   - Which are genuine Databento coverage gaps? (ESHA, INBS if still NO DATA)
5. **Recommendation:** Is it worth raising the float cap above 10M? What's the P&L impact?

---

## Step 5: Commit and Push

```bash
git add tick_cache/ cowork_reports/2026-03-24_corrected_tickers_backtest.md
git commit -m "$(cat <<'EOF'
Backtest corrected tickers from data gap investigation

9 stocks previously showed "NO DATA" because of transcription errors
from Ross's video recaps. Corrected tickers:
BBX→BLBX, ARNAZ→RNAZ, ZO→ZEO, AIMX→AMIX, NXX→NIXX,
EVAC→EVAX, MVNI→NVNI, ESHA/INBS re-tested.

Individual backtests from discovery time to 11:00 AM ET.
Results update the March 23 megatest totals.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## What We're Looking For

1. **How much P&L is recoverable?** Ross made ~$76,800 on these 9 stocks (plus JG). If the bot captures even 10-20%, that's $7-15K/month additional profit.
2. **ESHA/INBS data availability** — These are the true test. If Databento has them now, the scanner overhaul solves the problem. If not, we have a genuine SPAC coverage gap to escalate.
3. **Float filter impact** — ZEO (27.5M), AMIX (11M), NIXX (22.4M) are all above our 10M max float. If the bot is profitable on them, we have evidence to raise the float cap.
4. **Strategy effectiveness on corrected tickers** — Do SQ and MP fire on these stocks? Or do they produce 0 trades like some of the March 23 stocks?
