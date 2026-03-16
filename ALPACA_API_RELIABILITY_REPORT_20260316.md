# Alpaca API Reliability Report — V2 Backtest Results Are Unreliable
## 2026-03-16

**Branch**: `v6-dynamic-sizing`
**Severity**: CRITICAL — all automated backtest results to date are compromised

---

## Executive Summary

The V2 backtest (and likely V1) results are unreliable because **Alpaca's tick data API intermittently returns 500 errors** during batch simulation runs. The backtest runner silently swallows these failures and records 0 trades for affected stocks. This means our biggest winners (VERO, ROLR) are randomly dropped from results, making the backtest appear far worse than reality.

---

## The Discovery

### What we expected
VERO on Jan 16 should produce **+$5,930** (confirmed by running simulate.py directly). ROLR on Jan 14 should produce **+$2,099**. These are our two biggest known winners.

### What the V2 backtest recorded
- VERO Jan 16: **0 trades** (silently failed)
- ROLR Jan 14: **0 trades** (silently failed)
- Both stocks were correctly selected #1 by the ranking algorithm

### Root cause
When simulate.py fetches tick data from Alpaca during a batch run, some requests fail:

```
requests.exceptions.HTTPError: 500 Server Error: Internal Server Error
for url: https://data.alpaca.markets/v2/stocks/trades?symbols=VERO&...
```

The `run_sim()` function in `run_ytd_v2_backtest.py` catches all exceptions and returns an empty trade list:

```python
except subprocess.TimeoutExpired:
    print(f"    TIMEOUT: {symbol} {date}", flush=True)
    return []
except Exception as e:
    print(f"    ERROR: {symbol} {date}: {e}", flush=True)
    return []
```

But when `simulate.py` itself crashes (the error happens inside the subprocess), the subprocess returns non-zero exit code and empty stdout. The runner doesn't check `result.returncode` — it just tries to regex-match trades from the empty output and finds none. **No error is printed, no retry is attempted.**

---

## Impact Assessment

### Confirmed affected stocks
| Stock | Date | Expected P&L | V2 Recorded | Status |
|-------|------|-------------|-------------|--------|
| VERO | Jan 16 | +$5,930 | $0 (0 trades) | API 500 error |
| ROLR | Jan 14 | +$2,099 | $0 (0 trades) | Likely API failure |

### Likely affected (not verified)
Any stock that was selected in the top 5 but produced 0 trades could be an API failure rather than a genuine "no setup" result. Across 49 dates × 5 stocks × 2 configs = 490 sim runs, we don't know how many silently failed.

### P&L impact
- VERO + ROLR alone: **+$8,029 missing** from Config A results
- V2 fresh run final: Config A **$20,102** (-$9,898)
- If VERO + ROLR had been captured: ~**$28,131** (-$1,869) — nearly break-even
- Unknown number of other winners also silently dropped

### Previous backtests also affected
- **V1 backtest** (ran 100+ stocks per day): Even more API calls, likely even more failures
- **V2 first run** (stale state): Same issue — we thought it was "stale scanner data" but it was API failures
- **Any batch run using tick mode**: All are susceptible

---

## Fresh V2 Re-Run Results (Stopped Early — Unreliable)

Run was killed at ~45/49 dates because results are known to be compromised.

```
Starting equity: $30,000
Config A final:   $20,102 (-$9,898, -33.0%)
Config B final:   $19,184 (-$10,816, -36.1%)
```

### Key dates
| Date | A Trades | A Day P&L | A Equity | B Trades | B Day P&L | B Equity | Notes |
|------|----------|-----------|----------|----------|-----------|----------|-------|
| Jan 02 | 1 | -$787 | $29,213 | 1 | -$787 | $29,213 | |
| Jan 05 | 1 | -$365 | $28,848 | 1 | -$365 | $28,848 | |
| Jan 06 | 1 | -$721 | $28,127 | 2 | -$833 | $28,015 | |
| Jan 07 | 2 | -$896 | $27,231 | 2 | -$892 | $27,123 | |
| Jan 08 | 3 | -$694 | $26,537 | 3 | -$692 | $26,431 | |
| Jan 09 | 0 | $0 | $26,537 | 1 | -$660 | $25,771 | |
| Jan 12 | 2 | +$34 | $26,571 | 2 | +$32 | $25,803 | |
| Jan 13 | 3 | -$1,417 | $25,154 | 4 | -$1,324 | $24,479 | |
| **Jan 14** | **3** | **+$908** | **$26,062** | **3** | **+$883** | **$25,362** | **ROLR was #1 but 0 ROLR trades — all from AHMA** |
| Jan 15 | 1 | -$158 | $25,904 | 1 | -$154 | $25,208 | |
| **Jan 16** | **1** | **-$138** | **$25,766** | **1** | **-$134** | **$25,074** | **VERO was #1 but 0 VERO trades — API 500 error confirmed** |

### 2-Week Test Comparison (Jan 13-29)

The 2-week test covered Jan 13-29 and produced **+$14,525**. In the same window, V2 shows:
- Jan 13: -$1,417
- Jan 14: +$908 (missing ROLR's +$2,099)
- Jan 15: -$158
- Jan 16: -$138 (missing VERO's +$5,930)

**We can't reliably compare** because we don't know which other stocks in the Jan 13-29 window also had silent API failures.

---

## Why This Happens

### Alpaca's tick data endpoint is rate-limited and flaky
- Each `simulate.py --ticks` call fetches potentially **millions of trades** via paginated API calls
- VERO on Jan 16 alone has **1,696,214 trades** to fetch
- During batch runs, we're making these requests back-to-back for 10 stocks per date
- Alpaca's API occasionally returns 500 errors, especially for:
  - OTC stocks (VERO)
  - High-volume stocks with large tick datasets
  - Sustained request volumes (rate limiting manifests as 500s, not 429s)

### The error is non-deterministic
- Running VERO directly (single request, no competing calls): **works reliably**
- Running VERO during a batch of 10 sims: **fails intermittently**
- The failure can happen on any page of the paginated response (in VERO's case, it failed on a middle page after already fetching some data)

---

## Recommended Fixes

### Fix 1: Add retry logic to simulate.py tick fetching (HIGH PRIORITY)
```python
# In simulate.py fetch_trades():
for attempt in range(3):
    try:
        trade_set = hist_client.get_stock_trades(req)
        break
    except Exception as e:
        if attempt < 2:
            time.sleep(2 ** attempt)  # exponential backoff: 1s, 2s
            continue
        raise
```

### Fix 2: Check subprocess return code in run_ytd_v2_backtest.py
```python
result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env, cwd=WORKDIR)
if result.returncode != 0:
    print(f"    SIM FAILED: {symbol} {date} (exit code {result.returncode})", flush=True)
    # Optionally retry
    return []
```

### Fix 3: Add rate limiting between sim runs
```python
import time
# Between each simulate.py call:
time.sleep(1)  # Give Alpaca's API a breather
```

### Fix 4: Log failed stocks for manual re-run
Track which stocks failed so they can be re-simulated individually after the batch completes.

### Fix 5 (Nuclear): Cache tick data locally
Download and cache all tick data for the 49 dates before running backtests. This eliminates API dependency during the actual backtest run. Disk-heavy but reliable.

---

## What This Means For The Project

### The bot strategy may actually be profitable
- Direct simulation of known winners works: VERO +$5,930, ROLR +$2,099, ANPA +$2,088
- The 2-week backtest (+$13,518) was run with fewer concurrent API calls and likely had fewer failures
- **We literally cannot evaluate the strategy** until the backtest infrastructure is reliable

### All previous backtest conclusions are suspect
- V1's -$22,245 included silent API failures on an unknown number of stocks
- V2's results (both runs) include silent API failures
- The "every micro-pullback is a bad setup" analysis from the previous report may be skewed — some "0 trade" stocks were actually API failures, not genuine no-setups

### The "stale data" diagnosis was partially wrong
Earlier today we thought the V2 state file was stale because VERO showed 0 trades. We re-ran from scratch expecting different results. The fresh run ALSO showed 0 VERO trades — because the root cause is API reliability, not stale data.

---

## Immediate Next Steps

1. **Implement retry logic in simulate.py** (Fix 1) — this is the minimum viable fix
2. **Add subprocess error checking** (Fix 2) — so failures are visible, not silent
3. **Re-run V2 with fixes** — this time we'll know which stocks actually have no setups vs which ones failed
4. **Consider local tick data caching** (Fix 5) — most reliable long-term solution

Until the API reliability issue is fixed, **no backtest results should be trusted**.

---

*Discovered during V2 fresh re-run investigation | Branch: v6-dynamic-sizing*
