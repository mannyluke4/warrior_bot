# Directive: Scanner Alignment — Unified Ross Pillar Scanning

**TARGET**: 🖥️ MacBook Pro CC (code changes) → 🖥️ Mac Mini CC (regenerate data + backtest)
**Priority**: CRITICAL — blocks all live trading AND backtest trustworthiness
**Date**: 2026-03-19

---

## Context

The bot has two completely different scanning pipelines that produce different stock selections:

**Live scanner (`market_scanner.py` + `stock_filter.py`)**: Broken. Uses Alpaca snapshots (stale data, null prev closes), yfinance for float (slow/unreliable), computes RVOL from single trade size instead of session volume. Has found ZERO usable stocks in 3 days of live trading.

**Backtest scanner (`scanner_sim.py`)**: Better data quality but uses different filter thresholds, different ranking formula, and pre-generated static JSON files in `scanner_results/`. These files were generated with possibly different criteria at different times.

**Databento live scanner (`live_scanner.py`)**: Already built and uses the best data sources (Databento for prev close + streaming quotes, FMP for float). But it has NO RVOL computation and uses looser filter thresholds than our current Ross Pillar standards.

**The result**: We're backtesting against one stock universe, the live bot sees a different (empty) universe, and the Databento scanner that would actually work uses a third set of criteria. Nothing matches.

---

## Objective

**One set of Ross Pillar criteria, applied identically everywhere.**

After this directive is complete:
1. `live_scanner.py` finds stocks using the same criteria as the backtest
2. `scanner_sim.py` produces data with the same criteria
3. `run_ytd_v2_backtest.py` filters with the same criteria
4. All three produce the same top-N stocks for any given day

---

## The Unified Ross Pillar Filter Criteria

These are the canonical thresholds. All scanners must use these exact values:

```
Pillar 1 (Catalyst/Gap):    gap_pct >= 10%
Pillar 2 (Relative Volume): rvol >= 2.0x (vs 20-day avg daily volume)
Pillar 3 (Low Float):       float <= 10M shares, float >= 100K shares
Pillar 4 (Price Range):     $2.00 <= price <= $20.00
Pillar 5 (Volume):          pm_volume >= 50,000 shares (premarket, sane floor)
```

**Ranking formula** (for selecting top N when more candidates pass than needed):
```
score = (0.40 * rvol_score) + (0.30 * vol_score) + (0.20 * gap_score) + (0.10 * float_score)

where:
  rvol_score  = log10(min(rvol, 50) + 1) / log10(51)     # 0-1, capped at 50x
  vol_score   = log10(max(pm_volume, 1)) / 8               # 0-1, normalized
  gap_score   = min(gap_pct, 100) / 100                    # 0-1, capped at 100%
  float_score = 1 - (min(float_millions, 10) / 10)         # 0-1, lower float = higher score
```

**Top N**: 5 candidates per day (backtest) / 8 candidates per session (live)

---

## Phase 1: Fix `live_scanner.py` (MacBook Pro CC)

### 1A: Update filter thresholds

```python
# Current (too loose):
MIN_GAP_PCT = 5.0
MAX_FLOAT = 50_000_000
# No RVOL filter
# No min volume filter

# New (Ross Pillar aligned):
MIN_GAP_PCT = 10.0
MAX_FLOAT = 10_000_000    # 10M
MIN_FLOAT = 100_000       # 100K (already set)
MIN_PM_VOLUME = 50_000    # 50K shares premarket floor
```

### 1B: Add RVOL computation

`live_scanner.py` currently has NO RVOL. Add it:

1. After loading prev close via Databento Historical (`load_prev_close()`), also fetch 20-day average daily volume for each symbol in the same bulk request
2. Store as `self.avg_daily_volume: dict[str, float]`
3. In the `on_event()` callback, compute cumulative session volume per symbol by tracking a running sum
4. RVOL = cumulative_session_volume / avg_daily_volume
5. Only add to candidates if RVOL >= 2.0x

**Implementation note**: Databento's `ohlcv-1d` schema already includes volume. When fetching prev close, also compute 20-day average volume from the last 20 daily bars:

```python
# In load_prev_close(), extend to fetch 20 days:
start = (today_ts - pd.offsets.BusinessDay(21)).date()
# ...
# Compute avg daily volume per symbol from the 20-day window
avg_vol = df.groupby("symbol")["volume"].mean().to_dict()
self.avg_daily_volume = avg_vol
```

For tracking cumulative session volume in real-time:
```python
# In __init__:
self.session_volume: dict[str, float] = {}  # symbol -> cumulative shares

# In on_event():
trade_size = event.size  # or event.levels[0].ask_sz + bid_sz as proxy
self.session_volume[symbol] = self.session_volume.get(symbol, 0) + trade_size
avg_vol = self.avg_daily_volume.get(symbol, 0)
if avg_vol > 0:
    rvol = self.session_volume[symbol] / avg_vol
else:
    rvol = 0
```

Note: The MBP1 schema may not have trade size directly. Check what fields are available. If trade size isn't in MBP1, consider using `trades` schema alongside, or compute a volume proxy from quote changes. CC MBP should investigate the best approach given the Databento schema.

### 1C: Add ranking formula

When writing to `watchlist.txt`, rank candidates using the same formula as the batch runner (see "Unified Ranking Formula" above) instead of simple gap% descending.

### 1D: Include RVOL and volume in watchlist output

Currently `watchlist.txt` just has symbol names. Extend it to include metadata the bot can use:
```
# Format: SYMBOL:gap_pct:rvol:float_m:pm_volume
VERO:181.5:14.13:1.6:26831003
ROLR:42.3:8.5:3.78:10669416
```

This allows `bot.py` to pass scanner data (gap%, RVOL, float) to the detector and trade manager via env vars, which is needed for pillar gates, mid-float cap, and tiered max loss.

---

## Phase 2: Align `scanner_sim.py` (MacBook Pro CC)

### 2A: Ensure same filter thresholds

Verify `scanner_sim.py` uses:
- `gap_pct >= 10%` (not 5%)
- `rvol >= 2.0x`
- `float 100K - 10M`
- `price $2 - $20`
- `pm_volume >= 50,000`

### 2B: Ensure same ranking formula

Verify it matches the unified formula above.

### 2C: Ensure RVOL computation is correct

`scanner_sim.py` already computes RVOL from 20-day avg daily volume. Verify the computation matches what `live_scanner.py` will use. Specifically:
- Is it using the same 20-day window?
- Is pm_volume computed the same way (total premarket shares traded)?

---

## Phase 3: Regenerate Scanner Data (Mac Mini CC)

### 3A: Re-run `scanner_sim.py` for all 49 backtest dates

After Phase 1-2 code changes are pushed:

```bash
# Regenerate all scanner_results/*.json with aligned criteria
python scanner_sim.py --regenerate-all
```

Or if scanner_sim.py doesn't have a bulk regenerate mode, run it for each date:
```bash
for date in 2026-01-02 2026-01-03 2026-01-05 ... 2026-03-12; do
    python scanner_sim.py $date
done
```

### 3B: Compare old vs new candidate lists

For each date, report:
- How many candidates changed
- Which stocks were added (previously filtered out)
- Which stocks were removed (no longer pass tighter filters)
- Were VERO, ROLR, SXTC, GITS still in the top 5 on their respective days?

### 3C: Re-run the 49-day backtest with new scanner data

```bash
python run_ytd_v2_backtest.py
```

**Compare to previous result (+$19,072)**. The number may change significantly if different stocks are selected on key days.

---

## Phase 4: Align `run_ytd_v2_backtest.py` filters (MacBook Pro CC)

The batch runner has its own filter in `load_and_rank()`:
```python
MIN_PM_VOLUME = 0        # Should be 50,000
MIN_GAP_PCT = 5           # Should be 10
MAX_GAP_PCT = 500         # OK
MAX_FLOAT_MILLIONS = 10   # OK
```

Update to match the unified criteria:
```python
MIN_PM_VOLUME = 50_000
MIN_GAP_PCT = 10
MAX_GAP_PCT = 500
MAX_FLOAT_MILLIONS = 10
MIN_RVOL = 2.0  # ADD THIS — currently no RVOL filter in load_and_rank()
```

Also add RVOL check to the filter:
```python
rvol = c.get("relative_volume", 0) or 0
if rvol < MIN_RVOL:
    continue
```

---

## Phase 5: Validate Alignment (Mac Mini CC)

### Test 1: Key date verification

For these critical dates, verify both scanners produce the same top 5:

| Date | Must-have stock | Why |
|------|----------------|-----|
| 2026-01-14 | ROLR | Biggest runner (+$6,444) |
| 2026-01-16 | VERO | Biggest trade (+$18,583) |
| 2026-01-08 | SXTC | Cascading winner (+$1,686) |
| 2026-03-10 | GITS | Weekly best trade (+$2,748) |

Run `live_scanner.py` in historical/backtest mode (if possible) or compare `scanner_sim.py` output against what `live_scanner.py` WOULD produce given the same data.

### Test 2: ARTL verification

Generate scanner data for 2026-03-18. Verify ARTL appears in the candidate list.

### Test 3: Full 49-day backtest

Run with regenerated scanner data. Push results as `YTD_V2_BACKTEST_RESULTS_ALIGNED.md`.

---

## What NOT to Change

- **Do NOT change the detection engine** (`micro_pullback.py`) — that's separate work
- **Do NOT change exit logic** — the 5 fixes from yesterday stay as-is
- **Do NOT change execution logic** (`trade_manager.py`) — stays the same
- **Do NOT touch tick cache data** — only scanner candidate selection changes

---

## Expected Outcome

After this directive:
1. `live_scanner.py` finds the same stocks that made money in backtests
2. The 49-day backtest uses the same stock selection the live bot would use
3. We can trust the backtest results because they reflect real-world scanning
4. The live bot will actually find stocks tomorrow morning

**Risk**: Tightening the backtest scanner filters (adding RVOL≥2x gate, raising min PM volume) may remove some stocks that previously traded in the 49-day test. If a losing stock gets removed, P&L improves. If a winning stock gets removed, P&L drops. We need the full re-run to see the net effect.

---

## Handoff Notes

### MacBook Pro CC:
1. Update `live_scanner.py` (Phase 1: thresholds, RVOL, ranking, watchlist format)
2. Verify/update `scanner_sim.py` (Phase 2: alignment)
3. Update `run_ytd_v2_backtest.py` (Phase 4: filter alignment)
4. Push all changes

### Mac Mini CC:
1. Pull latest
2. Regenerate all `scanner_results/*.json` (Phase 3A)
3. Compare old vs new candidates (Phase 3B)
4. Run 49-day backtest (Phase 3C)
5. Run validation tests (Phase 5)
6. Push results report

---

*Directive created: 2026-03-19 | From: Claude Cowork | To: MacBook Pro CC → Mac Mini CC*
