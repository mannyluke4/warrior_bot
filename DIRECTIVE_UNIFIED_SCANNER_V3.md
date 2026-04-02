# Directive: Unified Scanner V3 — Clean Slate

## Why This Exists

We discovered two critical problems:

1. **IBKR scanner misses micro-caps.** KIDZ gapped +72% today ($2.05→$3.62, 430K float, $2M market cap) and the bot never saw it. IBKR's `reqScannerData` with `STK.US.MAJOR` simply doesn't include stocks this small. We're paying for Databento — it streams ALL_SYMBOLS and would have caught KIDZ.

2. **Backtest discovery times are wrong.** 49% of backtest candidates (208 of 428) have `sim_start=04:00` — the IBKR historical scanner uses the first bar's timestamp as discovery time, not the time the scanner would have actually found the stock. V1's `scanner_sim.py` did this correctly with checkpoint-based discovery. Our +$19,832 YTD number is unreliable because backtests see stocks hours before the live bot would.

## The Principle

**One scanner logic. Two modes (live + backtest). Exact same filtering. Exact parity.**

The backtest must answer: "Given the same scanner code, at what EXACT minute would this stock have first passed all filters?" That minute = discovery time. The sim starts there.

## Architecture: `unified_scanner.py` (NEW FILE)

This replaces: `live_scanner.py`, `ibkr_scanner.py`, `scanner_sim.py`, `market_scanner.py`, `stock_filter.py` as the single source of truth for "which stocks to trade and when."

### Core: `ScanEngine` class

```
class ScanEngine:
    """
    Streaming scanner that processes 1-minute bars chronologically.
    Same code path for live (Databento stream) and backtest (Databento historical replay).

    For each 1-min bar:
      1. Update cumulative volume for that symbol
      2. Compute gap% from prev_close
      3. Check all filters (price, gap, volume, RVOL, float)
      4. If ALL filters pass for the first time → record discovery_time

    Discovery time = the timestamp of the 1-min bar where the stock FIRST
    passes all filters simultaneously. This is the exact moment the live
    scanner would have added it to the watchlist.
    """
```

### Filter Pipeline (applied per-bar, per-symbol)

All thresholds read from `.env` (same as today):

```
1. Price:     MIN_PRICE <= bar.close <= MAX_PRICE          ($2-$20)
2. Gap%:      gap >= MIN_GAP_PCT                           (10%+)
3. PM Volume: cumulative_volume >= MIN_PM_VOLUME            (50K+)
4. RVOL:      cumulative_volume / avg_daily_volume >= MIN_RVOL  (2x+)
5. Float:     MIN_FLOAT <= float <= MAX_FLOAT               (0.5M-15M)
```

**Critical detail:** Filters 3 and 4 (volume, RVOL) are CUMULATIVE — they accumulate bar-by-bar from 4 AM. A stock might pass price + gap at 4:00 AM but not pass volume until 7:15 AM when enough shares have traded. The discovery time is 7:15, not 4:00. This is exactly how the live scanner works (it sees quotes accumulate in real-time).

### Two Modes

#### Mode 1: Live (`unified_scanner.py --live`)

```
1. Fetch prev_close + ADV from Databento EQUS.SUMMARY (ohlcv-1d, 21 days)
2. Start Databento Live stream (EQUS.MINI, mbp-1, ALL_SYMBOLS, from 4 AM ET)
3. Build 1-min bars from the stream (or use ohlcv-1m if available)
4. Feed each bar to ScanEngine
5. When ScanEngine discovers a new stock → write to watchlist.txt immediately
6. bot_ibkr.py polls watchlist.txt and subscribes
7. Stream runs 4:00 AM - 10:00 AM ET, then self-terminates
```

**Output:** `watchlist.txt` (same format as today, bot_ibkr.py reads it)

#### Mode 2: Backtest (`unified_scanner.py --backtest --date 2026-01-16`)

```
1. Fetch prev_close + ADV from Databento EQUS.SUMMARY (ohlcv-1d, 21 days before date)
2. Fetch ALL 1-min bars from Databento EQUS.MINI (ohlcv-1m, ALL_SYMBOLS, 04:00-10:00 ET)
3. Sort all bars chronologically across all symbols
4. Feed each bar to ScanEngine in timestamp order
5. ScanEngine records discovery_time for each stock that passes filters
6. Output: scanner_results/{date}.json with per-stock discovery_time
```

**Output:** `scanner_results/{date}.json` — list of candidates with exact `discovery_time` and `sim_start` set to that time.

### Float Lookup

Reuse the existing float lookup chain: `KNOWN_FLOATS → float_cache → FMP → yfinance → EDGAR → AlphaVantage`. This is already proven and shared across all existing scanners.

For backtest mode, float lookups happen once per symbol (cached). The float cache is shared.

### ADV (Average Daily Volume) Computation

For both modes:
- Use Databento `EQUS.SUMMARY` / `ohlcv-1d` for the 20 trading days BEFORE the scan date
- Compute mean daily volume per symbol
- This gives us RVOL denominator

For live mode, this is fetched once at startup (same as today's `live_scanner.py`).
For backtest mode, this is fetched once per date being scanned.

**Cost optimization:** For multi-date backtest runs, the ADV windows overlap heavily. Cache ADV results keyed by (symbol, date_range) to avoid redundant Databento API calls.

### Output Format

`scanner_results/{date}.json`:
```json
[
  {
    "symbol": "KIDZ",
    "prev_close": 2.05,
    "pm_price": 3.58,
    "gap_pct": 74.63,
    "pm_volume": 35981073,
    "cumulative_volume_at_discovery": 125000,
    "avg_daily_volume": 4029394,
    "relative_volume": 31.05,
    "float_shares": 429870,
    "float_millions": 0.43,
    "discovery_time": "06:47",
    "sim_start": "06:47",
    "discovery_method": "unified_v3",
    "rank_score": 0.873
  }
]
```

The key fields: `discovery_time` and `sim_start` are IDENTICAL and represent the exact minute the stock first passed all filters.

## Backtest Runner Changes: `run_backtest_v2.py`

Minimal changes needed. It already reads `scanner_results/{date}.json` and uses `sim_start` per candidate. The only change:

1. Before running sims, call `unified_scanner.py --backtest --date {date}` to regenerate scanner_results with correct discovery times
2. OR: pre-generate all scanner_results files first (`unified_scanner.py --backtest --start 2026-01-02 --end 2026-03-31`), then run the batch

The sim engine (`simulate.py`) already:
- Seeds bars from 4 AM (line 1712: `seed_start_et = ET.localize(date.replace(hour=4, ...))`)
- Splits into seed bars (before sim_start) and sim bars (after sim_start)
- Seeds detectors with pre-sim bars so EMA/VWAP/PM_HIGH are ready

**No changes needed to simulate.py.** It already handles variable sim_start correctly.

## Live Bot Changes: `bot_ibkr.py`

Add a simple watchlist poller (same as DIRECTIVE_DATABENTO_SCANNER_INTEGRATION.md):

```python
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt")

def poll_watchlist():
    """Read watchlist.txt (written by unified_scanner.py) and subscribe to new symbols."""
    if not os.path.exists(WATCHLIST_FILE):
        return
    try:
        with open(WATCHLIST_FILE, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return

    new_syms = []
    for line in lines:
        sym = line.split(":")[0].strip().upper()
        if sym and sym.isalpha() and 1 <= len(sym) <= 5:
            if sym not in state.active_symbols:
                new_syms.append(sym)

    if new_syms:
        print(f"\n📡 Scanner bridge: {len(new_syms)} new symbols from watchlist.txt: {sorted(new_syms)}", flush=True)
        for sym in new_syms:
            subscribe_symbol(sym)
```

Call `poll_watchlist()` right after `run_scanner()` in the main loop.

**NOTE:** CC has already implemented and tested `poll_watchlist()` — KIDZ is subscribed via watchlist.txt in the current live session. This step is DONE. The code above is for reference only.

**Keep the IBKR scanner running too** — it's a secondary source. Databento is primary (catches micro-caps), IBKR is backup (catches anything Databento might miss). Belt and suspenders.

## Bot Start Time: 4 AM + Keep Evening Session

Update `bot_ibkr.py` trading windows:
- Current: `07:00-12:00, 16:00-20:00`
- New: `04:00-10:00, 16:00-20:00`

The 4 AM start aligns with Databento stream start. The 10:00 AM morning end aligns with scanner cutoff and the empirical finding that post-09:30 discoveries are negative EV. Evening session (16:00-20:00) is kept — it's a separate opportunity window.

Update `.env`:
```
WB_TRADING_WINDOWS=04:00-10:00,16:00-20:00
```

## Startup Sequence

```bash
# Terminal 1: Databento scanner (writes watchlist.txt, runs 4AM-10AM, auto-exits)
cd ~/warrior_bot_v2 && source venv/bin/activate
python unified_scanner.py --live

# Terminal 2: Bot (reads watchlist.txt + runs IBKR scanner)
cd ~/warrior_bot_v2 && source venv/bin/activate
python bot_ibkr.py
```

Both start at 4 AM. Scanner writes discoveries to watchlist.txt in real-time. Bot polls watchlist.txt every scan cycle.

## Implementation Steps

### Step 1: Build `unified_scanner.py`

New file. Core `ScanEngine` class + two entry points (`--live` and `--backtest`).

**Backtest mode implementation:**
```python
def run_backtest(date_str: str):
    """Replay Databento historical data to determine exact discovery times."""

    client = db.Historical()

    # 1. Fetch prev_close + ADV (21 trading days before date)
    prev_close, adv = fetch_prev_close_and_adv(client, date_str)

    # 2. Fetch ALL 1-min bars for the date (4AM-10AM ET, ALL_SYMBOLS)
    bars_data = client.timeseries.get_range(
        dataset="EQUS.MINI",
        schema="ohlcv-1m",
        symbols="ALL_SYMBOLS",
        start=f"{date_str}T04:00:00-05:00",  # 4 AM ET
        end=f"{date_str}T10:00:00-05:00",    # 10 AM ET
    )

    # 3. Convert to DataFrame, sort by timestamp
    df = bars_data.to_df(pretty_px=True)
    df = df.sort_values("ts_event")

    # 4. Feed bars to ScanEngine chronologically
    engine = ScanEngine(prev_close=prev_close, adv=adv, float_cache=load_float_cache())

    for _, bar in df.iterrows():
        engine.process_bar(
            symbol=bar["symbol"],
            timestamp=bar["ts_event"],
            close=bar["close"],
            high=bar["high"],
            volume=bar["volume"],
        )

    # 5. Output candidates with exact discovery times
    candidates = engine.get_discoveries()
    save_scanner_results(date_str, candidates)
```

**ScanEngine.process_bar() logic:**
```python
def process_bar(self, symbol, timestamp, close, high, volume):
    # Skip if already discovered
    if symbol in self.discovered:
        return

    # Update cumulative state
    if symbol not in self.cum_volume:
        self.cum_volume[symbol] = 0
    self.cum_volume[symbol] += volume

    # Get prev_close
    pc = self.prev_close.get(symbol)
    if not pc or pc <= 0:
        return

    # Apply filters
    gap_pct = (close - pc) / pc * 100
    cum_vol = self.cum_volume[symbol]
    avg_vol = self.adv.get(symbol, 0)
    rvol = cum_vol / avg_vol if avg_vol > 0 else 0

    # All filters must pass simultaneously
    if close < MIN_PRICE or close > MAX_PRICE:
        return
    if gap_pct < MIN_GAP_PCT:
        return
    if cum_vol < MIN_PM_VOLUME:
        return
    if rvol < MIN_RVOL and avg_vol > 0:
        return

    # Float check (cached, one lookup per symbol)
    if symbol not in self.float_checked:
        self.float_checked[symbol] = get_float(symbol, self.float_cache)
    float_shares = self.float_checked[symbol]
    if float_shares is not None:
        if float_shares < MIN_FLOAT or float_shares > MAX_FLOAT:
            self.rejected.add(symbol)
            return

    # ALL FILTERS PASSED — this is the discovery moment
    ts_et = timestamp.astimezone(ET)
    discovery = f"{ts_et.hour:02d}:{ts_et.minute:02d}"

    self.discovered[symbol] = {
        "symbol": symbol,
        "prev_close": round(pc, 4),
        "pm_price": round(close, 4),
        "gap_pct": round(gap_pct, 2),
        "pm_volume": cum_vol,
        "cumulative_volume_at_discovery": cum_vol,
        "avg_daily_volume": round(avg_vol, 0),
        "relative_volume": round(rvol, 2),
        "float_shares": float_shares,
        "float_millions": round(float_shares / 1e6, 2) if float_shares else None,
        "discovery_time": discovery,
        "sim_start": discovery,
        "discovery_method": "unified_v3",
    }
```

### Step 2: Backfill scanner_results

```bash
# Regenerate ALL scanner_results with correct discovery times
python unified_scanner.py --backtest --start 2026-01-02 --end 2026-03-31
```

This replaces the existing scanner_results files. Back up the old ones first:
```bash
mv scanner_results scanner_results_old_ibkr
mkdir scanner_results
```

### Step 3: Wire into bot_ibkr.py

Add `poll_watchlist()` function + call site (as described above).
Update trading window to start at 4 AM.

### Step 4: Update .env

```
WB_TRADING_WINDOWS=04:00-10:00
# (remove or deprecate old scanner-related vars that are now handled by unified_scanner)
```

### Step 5: Re-run YTD backtest

```bash
python run_backtest_v2.py --start 2026-01-02 --end 2026-03-31 --label "V3 Unified Scanner"
```

This will use the new scanner_results with correct discovery times. The resulting P&L is the REAL number — no look-ahead bias.

### Step 6: Regression

Run VERO and ROLR standalone to establish new regression targets:
```bash
# These will need updated scanner_results too
# The standalone sim uses command-line start time, not scanner_results
# So for regression, manually set the discovery time from the new scanner_results:
python simulate.py VERO 2026-01-16 {VERO_DISCOVERY_TIME} 10:00 --ticks --tick-cache tick_cache/
python simulate.py ROLR 2026-01-14 {ROLR_DISCOVERY_TIME} 10:00 --ticks --tick-cache tick_cache/
```

New regression targets will need to be established after the scanner_results are regenerated.

## What This Replaces

| Old File | Status | Notes |
|----------|--------|-------|
| `live_scanner.py` | DEPRECATED | Replaced by `unified_scanner.py --live` |
| `ibkr_scanner.py` | KEEP (secondary) | Still used by bot_ibkr.py as backup scanner |
| `scanner_sim.py` | DEPRECATED | Replaced by `unified_scanner.py --backtest` |
| `market_scanner.py` | DEPRECATED | Was for old Alpaca bot |
| `stock_filter.py` | DEPRECATED | Filters now inside ScanEngine |

Don't delete old files yet — just stop using them. Mark them with a deprecation comment at the top.

## Databento Cost Considerations

- **Live mode:** Same cost as today's `live_scanner.py` (EQUS.MINI mbp-1 stream)
- **Backtest mode:** Uses `EQUS.MINI ohlcv-1m` — 1-minute bars for ALL_SYMBOLS for one date. This is cheaper than mbp-1 (quotes) but still covers the full universe. If cost is a concern, we can use `EQUS.SUMMARY ohlcv-1m` instead (fewer symbols but major exchanges only).
- **ADV computation:** One `EQUS.SUMMARY ohlcv-1d` call per date range (21 days). Cheap and fast.

Check Databento pricing at https://databento.com/pricing if concerned. The backfill is a one-time cost.

## Risk Assessment

**Medium risk, high reward.** The scanner is a new file (no existing behavior modified). The backtest runner changes are minimal (just reads new scanner_results format — same fields). The bot changes are additive (poll_watchlist). The main risk is Databento API cost for the historical backfill, and ensuring the `ohlcv-1m` schema for `EQUS.MINI` is available in the subscription.

## Files Changed
- `unified_scanner.py` — **NEW** — core scanner with live + backtest modes
- `bot_ibkr.py` — add `poll_watchlist()`, update trading window to 4AM
- `run_backtest_v2.py` — minor: call unified_scanner backtest if scanner_results missing
- `.env` — update `WB_TRADING_WINDOWS`, add any new scanner vars
- `scanner_results/*.json` — regenerated with correct discovery times

## Files NOT Changed
- `simulate.py` — already handles variable sim_start correctly
- `squeeze_detector.py` — unchanged
- `trade_manager.py` / `trade_manager_ibkr.py` — unchanged
- `bars.py` — unchanged
