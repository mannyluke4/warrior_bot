# ⚠️ SUPERSEDED — See DIRECTIVE_UNIFIED_SCANNER_V3.md instead
# This directive is replaced by the unified scanner approach.

# Directive: Wire Databento Live Scanner into bot_ibkr.py (SUPERSEDED)

## Problem
KIDZ gapped +72% today ($2.05→$3.62, 430K float, 36M PM volume) and the bot missed it entirely. IBKR's `reqScannerData` with `STK.US.MAJOR` doesn't include micro-cap stocks ($2M market cap). The Databento `live_scanner.py` streams ALL_SYMBOLS via EQUS.MINI and would have caught KIDZ, but it's not connected to `bot_ibkr.py` at all.

**Three scanners exist, none talking to each other:**
1. `ibkr_scanner.py` — used by `bot_ibkr.py` (live bot). Limited to IBKR's scanner universe. **Misses micro-caps.**
2. `live_scanner.py` — Databento EQUS.MINI streaming. Writes `watchlist.txt`. **Not running. Not read by bot.**
3. `market_scanner.py` — Alpaca API. Used by old `bot.py`. **Not relevant.**

## Solution: Two-part integration

### Part 1: bot_ibkr.py reads watchlist.txt (the "Databento bridge")

Add a `poll_watchlist()` function to `bot_ibkr.py` that:
1. Reads `watchlist.txt` (format: `SYMBOL:gap_pct:rvol:float_m:pm_volume`, one per line, `#` comments)
2. For each symbol NOT already in `state.active_symbols`, call `subscribe_symbol(symbol)`
3. Called from the main loop alongside `run_scanner()`, same 5-minute cadence
4. Gate with env var: `WB_DATABENTO_BRIDGE_ENABLED` (default `1` — ON)
5. Log: `📡 Databento bridge: found N new symbols in watchlist.txt: [SYM1, SYM2]`

**Key design points:**
- This is READ-ONLY — bot never writes to watchlist.txt
- Symbols from watchlist.txt get the same treatment as IBKR scanner picks (seed bars, init detectors, subscribe ticks)
- No double-filtering needed — live_scanner.py already applies the same .env filters (gap%, price, float, RVOL, PM volume)
- append-only semantics: once subscribed, never unsubscribed (same as IBKR scanner behavior, line 361-364)

**Implementation:**

```python
# At top of bot_ibkr.py, near other path constants:
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt")
DATABENTO_BRIDGE = os.getenv("WB_DATABENTO_BRIDGE_ENABLED", "1") == "1"

def poll_watchlist():
    """Read watchlist.txt (written by live_scanner.py) and subscribe to new symbols."""
    if not DATABENTO_BRIDGE:
        return
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
        print(f"\n📡 Databento bridge: {len(new_syms)} new symbols from watchlist.txt: {sorted(new_syms)}", flush=True)
        for sym in new_syms:
            subscribe_symbol(sym)
```

**Call site — in the main loop, right after `run_scanner()`:**

```python
# In the main loop (look for where run_scanner() is called):
run_scanner()
poll_watchlist()  # ← Add this line
```

### Part 2: Launch live_scanner.py automatically (documentation / startup script)

`live_scanner.py` is designed to run as a **separate process** alongside the bot. It:
- Starts streaming at 4:00 AM ET (via Databento historical replay)
- Writes `watchlist.txt` starting at 7:00 AM ET (1-minute updates)
- Self-terminates at 9:30 AM ET

**Add to .env:**
```
WB_DATABENTO_BRIDGE_ENABLED=1    # bot_ibkr reads watchlist.txt from Databento live_scanner
```

**Startup sequence (document in a comment at top of bot_ibkr.py or in README):**
```bash
# Terminal 1: Start Databento scanner (runs 4AM-9:30AM, auto-exits)
cd /Users/duffy/warrior_bot_v2
source venv/bin/activate
python live_scanner.py

# Terminal 2: Start the bot (runs all day)
cd /Users/duffy/warrior_bot_v2
source venv/bin/activate
python bot_ibkr.py
```

## What NOT to change
- Do NOT modify `ibkr_scanner.py` — it still runs normally as the primary scanner
- Do NOT modify `live_scanner.py` — it already works correctly
- Do NOT remove or replace the IBKR scanner — Databento is ADDITIVE coverage
- Do NOT add float re-filtering in the bridge — live_scanner.py already filters

## Testing

### Step 1: Unit test the bridge
Create a test watchlist.txt:
```
# Test watchlist
KIDZ:72.0:9.0:0.43:36000000
POLA:15.0:2.5:1.32:60000
```
Run the bot. Verify it picks up KIDZ and POLA from watchlist.txt and subscribes.

### Step 2: Verify live_scanner.py still works
```bash
python live_scanner.py --dry-run
```
Should stream Databento data, identify candidates, print them (without writing watchlist.txt).

### Step 3: Full integration test
1. Start `live_scanner.py` in one terminal
2. Start `bot_ibkr.py` in another
3. Verify that symbols written to `watchlist.txt` by live_scanner appear in bot_ibkr's subscriptions
4. Check that IBKR scanner symbols ALSO still appear (both sources working)

### Step 4: Regression
Run standard VERO + ROLR regression — this change should have ZERO impact on backtests since simulate.py doesn't use bot_ibkr.py.

## Files Changed
- `bot_ibkr.py` — add `poll_watchlist()` function + call site + env var
- `.env` — add `WB_DATABENTO_BRIDGE_ENABLED=1`

## Risk Assessment
**Very low risk.** This is purely additive — a new function that reads a file and calls the existing `subscribe_symbol()`. No existing behavior is modified. The env var gate provides an instant kill switch.
