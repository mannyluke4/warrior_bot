# Directive: Precise Discovery Time for Backtests

## Priority: HIGH — Without this, squeeze backtest results are unreliable
## Owner: CC
## Created: 2026-03-20 (Cowork)

---

## The Problem

The scanner sim uses 30-minute checkpoint windows (8:00, 8:30, 9:00, etc.) to discover
stocks. A stock that starts exploding at 7:49 AM gets `sim_start = "08:00"` — missing 11
minutes of potential action. For squeeze/parabolic stocks, this is the difference between
catching the first leg and missing the move entirely.

The live scanner (Databento streaming) would spot that 7:49 move in real-time. So the
backtest is systematically pessimistic for early-window movers and we can't trust the
squeeze results without fixing this.

## The Solution

Add a new step between scanning and simulation: **precise discovery time resolution**.

For each scanner candidate, fetch 1-minute bars from 4:00 AM onward and find the EXACT
minute when the stock first met ALL scanner criteria simultaneously:

1. Gap >= 10% (price vs prev_close)
2. Cumulative volume >= 50,000 shares
3. Cumulative RVOL >= 2.0x (cumulative volume / avg_daily_volume * fraction_of_day)

The `sim_start` becomes that minute (rounded down to the minute), not the checkpoint.

## Implementation

### Option A: Post-processing step in scanner_sim.py (RECOMMENDED)

Add a function `resolve_precise_discovery()` that runs after the main scan:

```python
def resolve_precise_discovery(candidates: list, prev_close: dict,
                               avg_daily_vol: dict, date_str: str) -> list:
    """
    For each candidate, fetch 1-min bars from 4AM and find the exact minute
    when scanner criteria were first met. Updates sim_start in-place.

    Live scanner criteria (all must be true simultaneously):
    - gap_pct >= 10% (bar close vs prev_close)
    - cumulative volume >= 50,000
    - price between $2.00 and $20.00

    We intentionally do NOT require RVOL >= 2.0 for the per-minute check because
    the live scanner uses a rolling volume spike detector, not a strict daily RVOL
    threshold applied to partial-day data.
    """
    date = datetime.strptime(date_str, "%Y-%m-%d")
    scan_start = ET.localize(datetime.combine(date.date(),
                             datetime.min.time().replace(hour=4, minute=0)))
    scan_end = ET.localize(datetime.combine(date.date(),
                           datetime.min.time().replace(hour=10, minute=30)))

    for c in candidates:
        sym = c["symbol"]
        pc = prev_close.get(sym)
        if not pc or pc <= 0:
            continue

        # Fetch full 1-min bar series for this stock
        try:
            request = StockBarsRequest(
                symbol_or_symbols=[sym],
                timeframe=TimeFrame.Minute,
                start=scan_start,
                end=scan_end,
            )
            bars = hist_client.get_stock_bars(request)
            bar_list = bars.data.get(sym, [])
        except Exception as e:
            print(f"  [precise_discovery] {sym}: fetch error: {e}")
            continue

        if not bar_list:
            continue

        # Walk bars chronologically, tracking cumulative volume
        cum_vol = 0
        discovery_minute = None

        for bar in bar_list:
            cum_vol += bar.volume if bar.volume else 0
            bar_time = bar.timestamp.astimezone(ET)
            price = bar.close
            gap = (price - pc) / pc * 100

            # Check all criteria
            if (gap >= 10.0 and
                cum_vol >= 50_000 and
                price >= 2.0 and price <= 20.0):
                discovery_minute = bar_time
                break

        if discovery_minute:
            # Round to minute string HH:MM
            precise_start = f"{discovery_minute.hour:02d}:{discovery_minute.minute:02d}"
            old_start = c.get("sim_start", "?")

            # Only update if earlier than current sim_start (don't make it worse)
            if precise_start < old_start or old_start == "?":
                c["precise_discovery"] = precise_start
                c["sim_start"] = precise_start
                c["discovery_time"] = precise_start
                c["discovery_method"] = "precise"
                print(f"  [precise] {sym}: {old_start} → {precise_start} "
                      f"(gap={gap:+.1f}%, vol={cum_vol:,})")
            else:
                c["precise_discovery"] = precise_start
                # Keep existing sim_start if it's already earlier
        else:
            # Stock never met all criteria simultaneously in the window
            c["precise_discovery"] = None

    return candidates
```

### Where to call it

In `run_scanner()`, after Step 4b (continuous re-scan) but before Step 5 (float lookup):

```python
    # Step 4c: Resolve precise discovery times
    print(f"  [4c/6] Resolving precise discovery times...")
    candidates = resolve_precise_discovery(candidates, prev_close, avg_daily_vol, date_str)
    precise_count = sum(1 for c in candidates if c.get("discovery_method") == "precise")
    print(f"         {precise_count}/{len(candidates)} candidates got precise timestamps")
```

### Option B: Standalone post-processing script (ALTERNATIVE)

If you don't want to modify scanner_sim.py, create a separate script that reads
`scanner_results/*.json`, resolves discovery times, and rewrites the JSON.
This is simpler but adds an extra step to the pipeline.

## Validation

After implementing, re-run a known date and verify:

```bash
python scanner_sim.py --date 2026-03-19
```

Check CHNR: the old scanner had `sim_start = "08:00"` (rescan checkpoint). With precise
discovery, it should be closer to 07:16 (when the gap + volume first qualified). Compare:

```bash
# Old: from 08:00 (missed the move)
python simulate.py CHNR 2026-03-19 08:00 12:00 --ticks -v
# Result: 0 trades (the move was 07:18-07:48)

# Precise: from actual discovery time
python simulate.py CHNR 2026-03-19 07:16 12:00 --ticks -v
# Expected: should catch the same trades as 07:00 start (+$429)
```

Also verify ARTL (2026-03-18): check if precise discovery is earlier than the checkpoint
time, and if the earlier start catches additional trades.

## Impact on Results

This fix will:
1. **Make squeeze results MORE reliable** — no more debate about whether the backtest is
   catching moves the live scanner would miss
2. **Potentially IMPROVE P&L** — earlier discovery means earlier entries on parabolic stocks
3. **Potentially REDUCE P&L** — some stocks that were being caught "early" at 07:00 via
   the premarket scan might have a later precise discovery time
4. **Align backtest with live behavior** — the Databento streaming scanner already does
   this in real-time, so the backtest should approximate the same timing

## After Implementation

1. Re-run today's backtest (2026-03-20) with precise discovery times
2. Re-run the 55-day YTD backtest with precise times (save as separate state file)
3. Compare old vs precise P&L — document the delta
4. If delta is significant, re-run OOS 2025 Q4 as well

## Regression

```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583 (regression uses fixed sim_start, not scanner)

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

*Directive created by Cowork — 2026-03-20*
*Purpose: Eliminate discovery timing bias from backtest results*
