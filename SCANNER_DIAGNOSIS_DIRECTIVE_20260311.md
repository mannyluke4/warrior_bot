# SCANNER DIAGNOSIS DIRECTIVE
## Why aren't Ross's stocks on our list?
### For Claude Code — Branch: v6-dynamic-sizing
### March 11, 2026

---

## THE PROBLEM

The backtest ran 5 dates. The bot traded 24 times across 111 scanner candidates. Ross traded 13 times across those same dates. **Almost zero overlap in the stocks traded.**

Ross's winners — the stocks that actually made money — were not on the bot's watchlist at all. Until we fix that, nothing else matters.

---

## THE TASK

For each stock Ross actually traded on the 5 backtest dates, determine **exactly why it did or didn't appear on the scanner's candidate list**, and if it did appear, why the bot didn't trade it.

---

## ROSS'S ACTUAL TRADES BY DATE

### Jan 2, 2025
| Ticker | Ross P&L | Pattern | Entry Time | Price Range | Float |
|--------|----------|---------|------------|-------------|-------|
| AEI | +$852 | Breakout on vol burst | 7:00 AM | $6.50-$8.80 | 700K |
| OST | -$4,000 | Micro pullback + add | 7:30 AM | $4.00-$4.75 | Unknown |
| SPCB | +$2,400 | Micro pullback (multiple entries) | Multiple | $3.70-$4.50 | Unknown |

### Nov 5, 2025
| Ticker | Ross P&L | Pattern | Entry Time | Price Range | Float |
|--------|----------|---------|------------|-------------|-------|
| CCTG | -$900 | Micro pullback (Chinese pump) | Pre-market | $1.00-$1.70 | Unknown |
| LNAI (x3) | -$3,926 net | Micro pullback / breakout | 9:15-9:25 AM | $1.17-$1.60 | 14M |

### Nov 6, 2025
| Ticker | Ross P&L | Pattern | Entry Time | Price Range | Float |
|--------|----------|---------|------------|-------------|-------|
| NUAAI | -$400 | Pullback entry at VWAP | 8:00-8:15 AM | $6.50-$6.83 | 25M |
| FTEEL | +$3,224 | Micro pullbacks on squeeze | 8:45-9:00 AM | $3.16-$5.20 | Low float |

### Jan 6, 2026
| Ticker | Ross P&L | Pattern | Entry Time | Price Range | Float |
|--------|----------|---------|------------|-------------|-------|
| ALM (x2) | +$500 net | Breakout / re-entry | Pre-market | ~$17.00 | Unknown |
| OPTX | +$3,600 | Micro pullback squeeze | ~8:26 AM | Unknown | Unknown |
| ELAB | +$3,500 | Micro pullback + adds | Unknown | $10.50-$12.00 | Unknown |
| CERO | (untested) | Unknown | Unknown | Unknown | Unknown |

### Feb 3, 2026
Ross took **zero trades**. No diagnosis needed — the question here is why the BOT traded, not why Ross didn't.

---

## FOR EACH STOCK ABOVE, ANSWER THESE QUESTIONS

### Step 1: Data Availability
- Does Alpaca have bar/tick data for this ticker on this date?
- If NO → that's the answer. Log it as a data gap and move on.

### Step 2: Scanner Filter Check
Run the stock's actual market data on that date through each scanner filter and report pass/fail:

```
Ticker: ______  Date: ______

1. Price at scan time:     $____  → Pass/Fail ($2-$20 range)
2. Gap % at scan time:     ____%  → Pass/Fail (≥5%)
3. Float:                  ____M  → Pass/Fail (100K-50M)
4. Time first appeared:    ____   → Pass/Fail (within 4AM-11AM window)
5. Made it into watchlist:  Y/N
6. If Y, was it bumped by 8-symbol cap: Y/N
7. If in watchlist, did bot see activity: Y/N
```

### Step 3: If It Passed Scanner But Bot Didn't Trade
- Did the detector arm? How many times?
- Did signals fire?
- What blocked entry? (Stale filter? Exhaustion? Warmup? No pullback pattern?)

### Step 4: If It Failed Scanner
- Which specific filter eliminated it?
- What value would the filter need to be to include it?
- Would loosening that filter also let in garbage stocks?

---

## WHAT TO REPORT BACK

Create a file: `SCANNER_DIAGNOSIS_RESULTS.md` with:

1. **Per-stock diagnosis table** — one row per Ross ticker, showing exactly where it got caught or lost
2. **Filter hit summary** — which filters are responsible for the most misses?
3. **Data gap summary** — which tickers have no Alpaca data at all?
4. **Recommendations** — specific filter changes if any are needed, or whether this is purely a data coverage problem

---

## PRIORITY ORDER

Start with the **winners** — these are the stocks that matter most:

1. **FTEEL** (Nov 6, +$3,224) — This is the #1 priority. Ross's big winner, completely absent from the bot's 26-symbol list.
2. **OPTX** (Jan 6, +$3,600) — Ross's second biggest winner across these dates.
3. **ELAB** (Jan 6, +$3,500) — Appeared on Feb 3 scanner (bot lost on it), but NOT on Jan 6 scanner.
4. **SPCB** (Jan 2, +$2,400) — Ross won, bot never saw it.
5. **CERO** (Jan 6, untested) — We know this is likely a data gap, but confirm.
6. **AEI** (Jan 2) — Was in both lists but Ross won and bot lost. Less about scanner, more about entry timing.
7. **ALM** (Jan 6) — $17 stock, Ross made +$500 net.
8. **LNAI** (Nov 5) — Ross lost on this, but it's still worth knowing if scanner caught it.
9. **CCTG** (Nov 5) — Ross lost on this too. Lower priority.
10. **NUAAI** (Nov 6) — Ross lost. Lower priority.

---

## IMPORTANT NOTES

- Use Alpaca data for everything (unified strategy, no Databento)
- The scanner filters as of the simplification: gap ≥5%, price $2-$20, float 100K-50M, window 4AM-11AM, 8-symbol cap
- If a stock appears after 7:14 AM, it should still be caught by the continuous 5-minute scanner updates through 11AM
- Don't fix anything yet — just diagnose. We need the full picture before making changes.
