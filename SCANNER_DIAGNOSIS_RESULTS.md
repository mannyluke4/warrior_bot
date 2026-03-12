# SCANNER DIAGNOSIS RESULTS
## Why Ross's Stocks Weren't on the Bot's Scanner
### March 12, 2026

---

## IMPORTANT FINDING: scanner_sim.py uses 10% gap minimum, not 5%

The directive states the scanner filters include "gap ≥5%", but `scanner_sim.py:265` actually uses `gap_pct < 10` as the cutoff. The live scanner (`live_scanner.py:52`) uses 5%. This discrepancy means the backtest scanner was MORE restrictive than intended. However, this didn't affect the outcome for any of Ross's stocks — the failures were all due to other filters or data gaps.

---

## PER-STOCK DIAGNOSIS

### 1. FTEEL — Nov 6, 2025 | Ross: +$3,224 | Ross price: $3.16-$5.20

```
Step 1: Data Availability
  Prev close:        NO DATA (Alpaca has zero bars for FTEEL)
  Premarket bars:    NO DATA
  Regular hours:     NO DATA

Step 2: Scanner Filter Check
  1. Price at scan:  N/A        → CANNOT EVALUATE
  2. Gap %:          N/A        → CANNOT EVALUATE
  3. Float:          UNKNOWN    → FAIL (no FMP/yfinance data either)
  4. First appeared:  N/A
  5. In watchlist:    NO
  6. Bumped by cap:   N/A
  7. Bot saw activity: N/A

VERDICT: COMPLETE DATA GAP — Alpaca has zero data for FTEEL on this date.
This was Ross's #1 winner (+$3,224). The bot could never have seen it.
```

---

### 2. OPTX — Jan 6, 2026 | Ross: +$3,600 | Pattern: Micro pullback squeeze ~8:26 AM

```
Step 1: Data Availability
  Prev close:        $3.28 ✓ (from Jan 6 daily bar)
  Premarket bars:    74 bars (4:00-9:30 AM) ✓
  Regular hours:     149 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $3.04      → PASS ($2-$20)
  2. Gap %:          -7.32%     → FAIL (gapping DOWN, need ≥5%)
  3. Float:          5.98M      → PASS (100K-50M)
  4. First appeared: 04:00 ET
  5. In watchlist:   NO
  6. Bumped by cap:  N/A
  7. Bot saw activity: N/A

  PM high (by 7:15): $3.05
  Reg hours: Open $3.42, High $3.50, Vol 1.86M

VERDICT: NOT A GAP-UP. OPTX was gapping DOWN -7.3% premarket.
Ross traded it as an intraday squeeze, not a gap-up. The stock was $3.04 PM
and opened at $3.42 — it rallied into the open but never showed a premarket gap.
The scanner only finds gap-ups ≥5%, so OPTX was invisible.
This stock is fundamentally outside the scanner's design — Ross caught intraday
momentum, not a premarket gap pattern.
```

---

### 3. ELAB — Jan 6, 2026 | Ross: +$3,500 | Ross price: $10.50-$12.00

```
Step 1: Data Availability
  Prev close:        $5.62 ✓
  Premarket bars:    26 bars — BUT first bar at 09:05 AM (none before 9:05)
  Regular hours:     145 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $8.46 (at 9:30 open) → PASS ($2-$20)
  2. Gap %:          +50.53%    → PASS (huge gap)
  3. Float:          2.1M (KNOWN_FLOATS) → PASS (100K-50M), Profile A
  4. First appeared: 09:05 ET   → FAIL for scanner_sim (only checks 4:00-7:15)
  5. In watchlist:   NO (on Jan 6) — YES on Feb 3 (different date)
  6. Bumped by cap:  N/A
  7. Bot saw activity: N/A

  PM high: $12.50 (between 9:05-9:30)
  Reg hours: Open $9.50, High $9.59, Vol 2.44M

VERDICT: LATE-MOVER PROBLEM. ELAB had +50% gap and passed all filters
EXCEPT timing: zero Alpaca premarket bars before 9:05 AM. The scanner_sim
only checks 4:00-7:15 AM, and the live_scanner continuous updates would
still need premarket quote data to compute the gap. No data = no detection.

This is ELAB's second appearance in the study — it DID appear on the Feb 3
scanner (gap +66.7%, same KNOWN_FLOATS entry). The difference: Feb 3 had
PM bars starting at 05:17. On Jan 6, the first bar was 09:05.

WHY NO PM DATA? Likely the stock halted or had no premarket liquidity on
this date. The gap happened overnight/at open, with no premarket trading.
Scanner_sim would need to check the opening bar (9:30) to catch this.
```

---

### 4. SPCB — Jan 2, 2025 | Ross: +$2,400 | Ross price: $3.70-$4.50

```
Step 1: Data Availability
  Prev close:        $7.68 ✓
  Premarket bars:    41 bars (first at 04:21) ✓
  Regular hours:     138 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $5.12      → PASS ($2-$20)
  2. Gap %:          -33.33%    → FAIL (gapping DOWN massively)
  3. Float:          4.44M      → PASS (100K-50M), Profile A
  4. First appeared: 04:21 ET
  5. In watchlist:   NO
  6. Bumped by cap:  N/A
  7. Bot saw activity: N/A

  PM high (by 7:15): $5.34
  Reg hours: Open $5.55, High $10.80, Vol 28.5M (!)

VERDICT: GAP-DOWN REVERSAL — NOT A GAP-UP. SPCB closed at $7.68 the
prior day, gapped DOWN to $5.12 premarket (-33%), then rallied intraday
from $5.55 to $10.80. Ross caught the bounce from $3.70 to $4.50.

This is a completely different pattern from what the scanner looks for.
The scanner finds gap-UPs; SPCB was a gap-DOWN reversal play. This is
outside the bot's strategy design.

NOTE: Ross's price range ($3.70-$4.50) doesn't match Alpaca's data
(Open $5.55, Low $5.11). Possible that Ross was looking at a different
timeframe or Alpaca has a data quality issue on this specific bar.
```

---

### 5. CERO — Jan 6, 2026 | Ross: untested

```
Step 1: Data Availability
  Prev close:        $0.0951 (sub-penny — likely delisted/restructured)
  Premarket bars:    NO DATA
  Regular hours:     NO DATA

VERDICT: DATA GAP + PENNY STOCK. Prev close was $0.095 (under $0.10).
Even if Alpaca had PM data, the $2 minimum price filter would block it.
Confirmed data gap — no premarket or regular hours bars in Alpaca.
```

---

### 6. AEI — Jan 2, 2025 | Ross: +$852 | Ross price: $6.50-$8.80

```
Step 1: Data Availability
  Prev close:        $1.38 ✓
  Premarket bars:    331 bars (first at 04:00) ✓
  Regular hours:     151 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $2.19      → PASS ($2-$20)
  2. Gap %:          +58.70%    → PASS
  3. Float:          3.86M      → PASS (100K-50M), Profile A
  4. First appeared: 04:00 ET
  5. In watchlist:   YES ✓ (top candidate on Jan 2 list)
  6. Bumped by cap:  NO
  7. Bot saw activity: YES

  PM high (by 7:15): $2.90, PM volume: 14.9M
  Reg hours: Open $2.06, High $2.61, Vol 16.7M

VERDICT: ON THE LIST — passed all filters and was the #1 candidate.
Ross made +$852, bot result depends on the trade execution not the scanner.

NOTE: Ross's price range ($6.50-$8.80) doesn't match Alpaca data at all
(PM high $2.90, reg high $2.61). This suggests either a stock split/reverse
split between Jan 2025 and now affecting historical data, or a data mismatch
in Ross's reported prices. The scanner correctly identified AEI as a 58.7%
gap-up candidate.
```

---

### 7. ALM — Jan 6, 2026 | Ross: +$500 | Ross price: ~$17.00

```
Step 1: Data Availability
  Prev close:        $9.74 ✓
  Premarket bars:    54 bars (first at 04:00) ✓
  Regular hours:     151 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $9.60      → PASS ($2-$20)
  2. Gap %:          -1.44%     → FAIL (flat/slightly down)
  3. Float:          167.11M    → FAIL (way over 50M cap)
  4. First appeared: 04:00 ET
  5. In watchlist:   NO
  6. Bumped by cap:  N/A
  7. Bot saw activity: N/A

  PM high (by 7:15): $9.69
  Reg hours: Open $9.60, High $9.97, Vol 1.09M

VERDICT: DOUBLE FAIL — no gap + massive float.
ALM had zero gap (-1.4%) and 167M float. This stock was never going to
appear on a small-cap gap scanner. Ross's reported price (~$17) doesn't
match Alpaca data ($9.60-$9.97), suggesting either a different ALM ticker
or a data issue.
```

---

### 8. LNAI — Nov 5, 2025 | Ross: -$3,926 | Ross price: $1.17-$1.60

```
Step 1: Data Availability
  Prev close:        $1.17 ✓
  Premarket bars:    10 bars — first bar at 08:00 AM (none before 8:00)
  Regular hours:     151 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $1.19 (at 9:30) → FAIL (under $2 minimum)
  2. Gap %:          +1.71%     → FAIL (need ≥5%)
  3. Float:          UNKNOWN    → FAIL (rejected)
  4. First appeared: 08:00 ET   → Late (no PM bars before 7:15)
  5. In watchlist:   NO
  6. Bumped by cap:  N/A
  7. Bot saw activity: N/A

  Reg hours: Open $1.10, High $1.53, Vol 85.8M

VERDICT: TRIPLE FAIL — price under $2, no gap, unknown float.
This is a sub-$2 stock with no meaningful premarket gap. It ran intraday
from $1.10 to $1.53 (+39%) on 86M volume, but the scanner would never
see it due to the price floor and gap requirements. Ross lost -$3,926
on this one anyway.
```

---

### 9. CCTG — Nov 5, 2025 | Ross: -$900 | Ross price: $1.00-$1.70

```
Step 1: Data Availability
  Prev close:        $0.6191 ✓
  Premarket bars:    59 bars (first at 04:01) ✓
  Regular hours:     149 bars ✓

Step 2: Scanner Filter Check
  1. Price at scan:  $0.84      → FAIL (under $2 minimum)
  2. Gap %:          +35.70%    → PASS
  3. Float:          0.23M      → PASS (100K-50M), Profile A
  4. First appeared: 04:01 ET
  5. In watchlist:   NO
  6. Bumped by cap:  N/A
  7. Bot saw activity: N/A

  Reg hours: Open $1.69, High $1.69, Vol 9.94M

VERDICT: PRICE FILTER KILLED IT. CCTG had a great gap (+35.7%) and
good float (230K), but at $0.84 PM it was under the $2 minimum.
It spiked to $1.69 at open, but even that's under $2.

To catch CCTG, the scanner would need to lower MIN_PRICE to $0.50 or
$1.00, but that would also let in a flood of penny stocks.
Ross lost -$900 on this trade, so missing it was actually beneficial.
```

---

### 10. NUAAI — Nov 6, 2025 | Ross: -$400 | Ross price: $6.50-$6.83

```
Step 1: Data Availability
  Prev close:        NO DATA
  Premarket bars:    NO DATA
  Regular hours:     NO DATA

VERDICT: COMPLETE DATA GAP — Alpaca has zero data for NUAAI.
Not in the Alpaca universe at all. Ross lost -$400 on it, so
missing this stock was actually beneficial.
```

---

## FILTER HIT SUMMARY

| Filter | Stocks Blocked | Tickers |
|--------|---------------|---------|
| **No Alpaca data** | 3 | FTEEL, CERO, NUAAI |
| **No gap-up (flat or gapping down)** | 3 | OPTX (-7.3%), SPCB (-33.3%), ALM (-1.4%) |
| **Price under $2** | 2 | LNAI ($1.19), CCTG ($0.84) |
| **No PM bars before 7:15** | 1 | ELAB (first bar 9:05 AM) |
| **Float over 50M** | 1 | ALM (167M) |
| **Passed all filters** | 1 | AEI ✓ (on scanner list) |

*Note: Some stocks fail multiple filters. LNAI failed 3 (price + gap + float). ALM failed 2 (gap + float).*

### By impact on P&L missed:

| Root Cause | Ross P&L Affected | Stocks |
|------------|-------------------|--------|
| **Data gap** | +$3,224 (FTEEL) | FTEEL is the only winner in this category |
| **Not a gap-up** | +$6,500 (OPTX +$3,600, SPCB +$2,400, ALM +$500) | These are intraday plays, not gap-ups |
| **Late mover** | +$3,500 (ELAB) | Genuine gap-up but no PM data before 9:05 |
| **Under $2** | -$4,826 (LNAI -$3,926, CCTG -$900) | Both losers — filtering helped |
| **Already caught** | +$852 (AEI) | On scanner list, entry execution issue |

---

## DATA GAP SUMMARY

| Ticker | Date | What's Missing | Impact |
|--------|------|----------------|--------|
| **FTEEL** | Nov 6, 2025 | Zero Alpaca data (prev close, PM, regular hours) | Ross's #1 winner (+$3,224) |
| **NUAAI** | Nov 6, 2025 | Zero Alpaca data (prev close, PM, regular hours) | Ross lost -$400 |
| **CERO** | Jan 6, 2026 | No PM or regular hours bars; prev close $0.095 (penny) | Untested |

These tickers are simply not in Alpaca's data universe. No filter changes will fix this.

---

## RECOMMENDATIONS

### 1. The scanner is NOT the primary problem

Of the 10 Ross tickers:
- **3 are data gaps** (Alpaca doesn't have them) — nothing the scanner can do
- **3 were not gap-ups** (OPTX, SPCB, ALM) — Ross traded intraday momentum/reversal patterns that are fundamentally outside the gap-up scanner's design
- **2 were sub-$2 penny stocks** (LNAI, CCTG) — both were losers for Ross
- **1 was a genuine miss** (ELAB — late mover with no PM data)
- **1 was correctly identified** (AEI)

### 2. The one actionable fix: late-mover detection

**ELAB on Jan 6** is the only stock where a scanner change could have helped. It had a +50% gap, good float, good price — but zero Alpaca bars before 9:05 AM. The scanner_sim only looks at 4:00-7:15 AM bars.

**Possible fix**: Add a post-open gap check at 9:30-9:35 AM. Any stock that opens significantly above its prev close (gap ≥5%) that wasn't in the premarket candidate list should be added as a late candidate. The live_scanner already runs updates until 11 AM, but it relies on premarket quote data to compute the gap. A "gap at open" supplemental check would catch ELABs.

**Risk**: Low. This would only add stocks that meet all other filters (price, float) and gap ≥5% at open. The 8-symbol cap would still apply.

### 3. Do NOT lower the $2 minimum price

CCTG ($0.84) and LNAI ($1.19) were both sub-$2 and both were Ross losers. Lowering the price floor would add noise without adding edge.

### 4. Do NOT add intraday momentum scanning

OPTX, SPCB, and ALM were not gap-ups. They were intraday breakout/reversal plays. Adding a non-gap scanner would be a completely different strategy and is out of scope for the current architecture.

### 5. Data provider gap is real but limited

FTEEL was Ross's biggest winner (+$3,224) and Alpaca has zero data for it. This is the kind of stock Databento or a different data source might catch. However, this is 1 stock out of 10. The scanner's bigger issue is structural (it only finds gap-ups, while Ross trades multiple patterns).

### 6. Gap threshold discrepancy: scanner_sim uses 10%, live_scanner uses 5%

`scanner_sim.py:265` uses `if gap_pct < 10: continue` while `live_scanner.py:52` uses `MIN_GAP_PCT = 5.0`. The backtest was run with the 10% threshold. None of Ross's stocks would have been affected (the ones with gaps had gaps well above 10%, and the ones without gaps had negative or near-zero gaps), but this should be aligned.

---

## BOTTOM LINE

The scanner overlap problem is primarily caused by:

1. **Strategy mismatch** (3 of 10): Ross doesn't only trade gap-ups. He also trades intraday momentum, reversals, and breakouts. The scanner is designed for one specific pattern.
2. **Data gaps** (3 of 10): Alpaca simply doesn't have some tickers.
3. **Late movers** (1 of 10): ELAB is the single actionable miss — a genuine gap-up with no premarket data.

The scanner filters themselves are correctly configured for their intended purpose. The real question is whether the bot should expand beyond gap-up scanning to capture the broader set of patterns Ross trades.
