# Directive: Fix Float Data Propagation for Tiered Max Loss Cap

**TARGET**: 🖥️ MacBook Pro CC (code changes) → 🖥️ Mac Mini CC (backtesting)
**Priority**: HIGH — this is the single biggest remaining improvement (+$1,285 estimated)
**Date**: 2026-03-18

---

## Context

The float-tiered max loss cap (Fix 2 from `DIRECTIVE_STRATEGY_IMPROVEMENTS_V1.md`) is implemented and working — **but it couldn't fire on the two trades that matter most** because the simulator didn't have float data for LUNL (0.17M) and FLYT (0.31M). Both showed `Fundamentals: float=N/A` in the backtest output.

With float data available, LUNL would have been placed in the ultra-low tier (no cap), held through its -0.75R dip, and exited at +$464 via topping wicky instead of -$821 via max_loss_hit. That's a **+$1,285 swing** on a single trade.

---

## Root Cause: Two Separate Float Data Pipelines

The bot has **two different ways** float data reaches the max loss cap logic, and they don't connect:

### Pipeline 1: Batch Runner → simulate.py (BROKEN for float-tiered cap)

```
run_ytd_v2_backtest.py
  → reads scanner_sim JSON (has float_millions from FMP/yfinance)
  → passes to simulate.py via env var: WB_SCANNER_FLOAT_M
  → BUT: simulate.py uses --no-fundamentals flag (line 164)
  → AND: the tiered cap reads from self.stock_info.float_shares (line 303-304)
  → stock_info is None because --no-fundamentals skips the fetch
  → RESULT: tiered cap has no float data → falls back to flat 0.75R
```

The batch runner passes `WB_SCANNER_FLOAT_M` as an env var (line 159), but the SimTradeManager reads float from `self.stock_info.float_shares` (line 303-304), which comes from the Alpaca fundamentals fetch. Since the batch runner uses `--no-fundamentals` for speed, `stock_info` is None, and the tiered cap can't function.

**The float data IS available** — it's sitting in `WB_SCANNER_FLOAT_M` env var — but `SimTradeManager.on_tick()` doesn't look there.

### Pipeline 2: Standalone simulate.py (PARTIALLY BROKEN)

```
simulate.py (standalone, no --no-fundamentals)
  → calls StockFilter.get_stock_info()
  → StockFilter calls Alpaca snapshot API
  → Alpaca sometimes returns null for float on ultra-low float stocks
  → StockFilter tries yfinance as fallback
  → yfinance sometimes also fails for micro-caps
  → RESULT: float=N/A for stocks like LUNL, FLYT
```

Even without `--no-fundamentals`, the Alpaca API doesn't always have float data for ultra-low float stocks. The scanner_sim.py has better fallbacks (FMP API + a known-floats cache from previous scans), but standalone simulate.py only uses the StockFilter path.

### Pipeline 3: Live Bot (WORKS for mid-float, UNTESTED for ultra-low)

```
bot.py
  → StockFilter runs at scan time, caches StockInfo with float
  → trade_manager.py reads from _stock_info_cache
  → float is available at entry time for mid-float cap logic
  → BUT: same Alpaca/yfinance fallback chain — may still miss ultra-low floats
```

---

## The Fix

The simplest fix: **make SimTradeManager read float from the `WB_SCANNER_FLOAT_M` env var as a fallback** when `stock_info.float_shares` is None or missing. The batch runner already passes this value (line 159 of `run_ytd_v2_backtest.py`), and standalone runs can pass it via `--float` CLI arg or env var.

### Implementation (MacBook Pro CC)

**File: `simulate.py` — SimTradeManager constructor (~line 150-160)**

After the existing tiered cap setup, add a fallback:

```python
# Existing code reads tiered thresholds from env...
self._max_loss_r_tiered = os.getenv("WB_MAX_LOSS_R_TIERED", "0") == "1"
self._max_loss_r_ultra_low = float(os.getenv("WB_MAX_LOSS_R_ULTRA_LOW_FLOAT", "0"))
self._max_loss_r_low = float(os.getenv("WB_MAX_LOSS_R_LOW_FLOAT", "0.85"))
self._max_loss_r_thresh_low = float(os.getenv("WB_MAX_LOSS_R_FLOAT_THRESHOLD_LOW", "1.0"))
self._max_loss_r_thresh_high = float(os.getenv("WB_MAX_LOSS_R_FLOAT_THRESHOLD_HIGH", "5.0"))

# NEW: fallback float from scanner env var (batch runner passes this)
self._scanner_float_m = float(os.getenv("WB_SCANNER_FLOAT_M", "0"))
```

**File: `simulate.py` — SimTradeManager.on_tick() (~line 301-310)**

Update the tiered cap logic to use the scanner float as fallback:

```python
# Determine effective cap: flat or float-tiered
if self._max_loss_r_tiered:
    # Try stock_info first, then fall back to scanner env var
    _fm = None
    if self.stock_info and hasattr(self.stock_info, 'float_shares') and self.stock_info.float_shares:
        _fm = self.stock_info.float_shares
    elif self._scanner_float_m > 0:
        _fm = self._scanner_float_m

    if _fm is not None:
        if _fm < self._max_loss_r_thresh_low:
            _eff_mlr = self._max_loss_r_ultra_low  # 0 = OFF for ultra-low float
        elif _fm <= self._max_loss_r_thresh_high:
            _eff_mlr = self._max_loss_r_low  # e.g. 0.85 for 1-5M float
        else:
            _eff_mlr = self.max_loss_r  # e.g. 0.75 for 5M+ float
    else:
        _eff_mlr = self.max_loss_r  # No float data → use flat cap
```

**File: `simulate.py` — also pass float info to the SimTradeManager constructor**

At the point where `SimTradeManager` is created (~line 1179), if `_sim_stock_info` is None but `WB_SCANNER_FLOAT_M` is set, create a minimal stock_info object:

```python
# If batch runner passed float via env var but we skipped fundamentals,
# create a minimal stock_info so the trade manager can use it
if _sim_stock_info is None:
    _scanner_float = float(os.getenv("WB_SCANNER_FLOAT_M", "0"))
    if _scanner_float > 0:
        from stock_filter import StockInfo
        _sim_stock_info = StockInfo(
            symbol=symbol,
            price=0, prev_close=0, gap_pct=float(os.getenv("WB_SCANNER_GAP_PCT", "0")),
            volume=0, avg_volume=0, rel_volume=0,
            float_shares=_scanner_float,
        )
        print(f"  Fundamentals (from scanner): float={_scanner_float:.1f}M", flush=True)
```

This approach is cleaner because it creates a proper StockInfo object that the existing code already knows how to handle, rather than adding a parallel float-reading path.

### Also fix the live bot fallback (bot.py / trade_manager.py)

For the live bot, ensure that if `StockFilter.get_stock_info()` returns `float_shares=None`, the bot tries:
1. The FMP API key (already in `.env` as `FMP_API_KEY`)
2. A local float cache file (scanner_sim already maintains one)

This is lower priority since the live bot has real-time Alpaca data, but ultra-low float stocks may still return null. A one-liner in `stock_filter.py`'s `get_float_estimate()` to add FMP as a fallback before yfinance would help.

---

## Gate

No new env var needed — this is a data plumbing fix, not a strategy change. The tiered cap is already gated behind `WB_MAX_LOSS_R_TIERED=1`.

---

## Test Plan (Mac Mini CC)

After MacBook Pro CC pushes the fix:

1. **LUNL standalone** with tiered cap ON:
   ```bash
   WB_MAX_LOSS_R_TIERED=1 WB_SCANNER_FLOAT_M=0.17 \
   python simulate.py LUNL 2026-03-17 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   **Expected**: Float recognized as 0.17M → ultra-low tier → no cap → TW exit at +$464

2. **FLYT standalone** with tiered cap ON:
   ```bash
   WB_MAX_LOSS_R_TIERED=1 WB_SCANNER_FLOAT_M=0.31 \
   python simulate.py FLYT 2026-03-12 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   **Expected**: Float 0.31M → ultra-low tier → no cap → stop_hit at -$1,200 (the tradeoff — we lose the 0.75R savings on FLYT to save LUNL)

3. **ROLR regression** with tiered cap ON:
   ```bash
   WB_MAX_LOSS_R_TIERED=1 WB_SCANNER_FLOAT_M=3.78 \
   python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   **Expected**: Float 3.78M → low tier → 0.85R cap → survives (min dip -0.60R)

4. **VERO regression**:
   ```bash
   WB_MAX_LOSS_R_TIERED=1 WB_SCANNER_FLOAT_M=1.6 \
   python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   **Expected**: +$9,166 unchanged

5. **Full weekly backtest** (Mar 9-18) with all 4 fixes + float propagation ON
   **Expected**: Previous result +$221 → approximately +$1,506 (LUNL flips from -$821 to +$464)

6. **Full 49-day backtest** with all 4 fixes + float propagation ON → new baseline number

---

## Expected Impact

| Trade | Current (no float data) | With float propagation | Delta |
|-------|------------------------|----------------------|-------|
| LUNL | -$821 (0.75R cap fired) | +$464 (no cap, TW exit) | **+$1,285** |
| FLYT | -$696 (0.75R cap fired) | -$1,200 (no cap, stop_hit) | **-$504** |
| **Net** | | | **+$781** |

The LUNL save (+$1,285) more than offsets the FLYT cost (-$504). This is the expected tradeoff we identified in the original analysis — ultra-low float stocks need their hard stops, not artificial caps.

**Weekly P&L estimate**: +$221 (current) + $781 (float fix net) = **+$1,002**

---

## Critical Rules

- **DO NOT** change the tiered cap thresholds — they were validated against ROLR and VERO
- **DO NOT** add FMP/yfinance calls to the hot path of simulate.py — use env vars only for speed
- The batch runner already passes `WB_SCANNER_FLOAT_M` — this fix just connects the plumbing
- VERO regression must still be +$9,166

---

*Directive created: 2026-03-18 | From: Claude Cowork | To: MacBook Pro CC → Mac Mini CC*
