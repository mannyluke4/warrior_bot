# DIRECTIVE: Scanner Overhaul — Kill Profile X + Continuous Scanning

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: CRITICAL — This has been requested repeatedly and directly impacts live P&L

---

## Overview

Two problems, one directive:

1. **Profile X / unknown-float filtering must be completely removed.** Stocks with unknown float are currently blocked or penalized at every stage of the pipeline. The bot can trade these stocks profitably (GDTC +$4,393, AMOD +$3,642 in backtest). The entire Profile X system is a relic from before the squeeze strategy existed. Gut it.

2. **Scanner timing must be continuous.** The scanner_sim rescans every 30 minutes (8:00, 8:30, 9:00...). The live_scanner writes watchlist every 5 minutes. But the bot loads the watchlist ONCE at startup and never refreshes. Stocks that emerge after the initial load are invisible for the entire session. Fix: the bot must poll the watchlist continuously during the trading window.

---

## PART 1: Remove Profile X / Unknown-Float Filtering

### What Profile X Is

`classify_profile()` in `scanner_sim.py` (line 255) classifies stocks by float:
- Float < 5M → Profile "A"
- Float 5-10M → Profile "B"
- Float > 10M → "skip" (rejected)
- Float unknown (None) → "unknown" (was "X" before the rename)

The system was built when the bot only ran micro-pullback setups. Unknown-float stocks were unpredictable with MP. Now the squeeze strategy handles them fine — the backtest proved it.

### Every Location That Must Change

#### 1. `scanner_sim.py` — classify_profile() function (lines 255-265)

**CHANGE:** Keep returning "unknown" for None float — do NOT rename to "A" or "B". Profile A and B have real behavioral consequences in the old sizing system (`trade_manager.py` line 46: Profile A = full risk, Profile B = 1/3 risk capped at $250). Relabeling unknown stocks as "A" would silently change their risk sizing in the live bot when `WB_DYNAMIC_SIZING_ENABLED=1`.

The fix is simpler: **keep the label, stop filtering on it.** The "unknown" label stays as informational metadata in the scanner JSON. Every downstream system that currently blocks on `profile in ("X", "unknown")` gets that block removed.

```python
# NO CHANGE to classify_profile() — keep it as-is:
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), unknown (no data)."""
    if float_shares is None:
        return "unknown"
    millions = float_shares / 1_000_000
    if millions < 5:
        return "A"
    elif millions <= 10:
        return "B"
    else:
        return "skip"
```

**The function stays. Only the downstream filtering changes.** Unknown-float stocks flow through the entire pipeline — they just won't get profile-specific risk sizing (which is fine, the current V1 backtest runners use flat risk anyway).

#### 2. `live_scanner.py` — passes_float_filter() function (lines 242-246)

**CHANGE:** Allow unknown float stocks through the filter.

```python
# BEFORE:
def passes_float_filter(float_shares: Optional[float]) -> bool:
    """True if float is between MIN_FLOAT and MAX_FLOAT (or unknown → reject)."""
    if float_shares is None:
        return False
    return MIN_FLOAT <= float_shares <= MAX_FLOAT

# AFTER:
def passes_float_filter(float_shares: Optional[float]) -> bool:
    """True if float is between MIN_FLOAT and MAX_FLOAT, or unknown (allowed through)."""
    if float_shares is None:
        return True  # Unknown float → allow through, let strategy gates decide
    return MIN_FLOAT <= float_shares <= MAX_FLOAT
```

#### 3. `live_scanner.py` — _add_candidate() (around line 417)

Verify that the `passes_float_filter` call is the only gate. After the change above, unknown-float stocks will pass through. No additional changes should be needed here, but **confirm no other float check blocks them downstream**.

#### 4. ALL backtest runners — Remove Profile X/unknown skip blocks

These files have `if profile in ("X", "unknown"): continue` or gated equivalents. **Remove all of them.** Unknown-float stocks should be treated identically to known-float stocks.

| File | Lines | Current Logic | New Logic |
|------|-------|---------------|-----------|
| `run_megatest.py` | 174-187 | Gated: needs gap≥50%, pm_vol≥1M, rvol≥10x, 50% notional cap | **Remove entire block.** Unknown-float stocks pass through normally at full notional. |
| `run_ytd_v2_backtest.py` | 143-152 | Gated: needs gap≥50%, pm_vol≥1M, rvol≥10x | **Remove entire block.** |
| `run_ytd_v2_profile_backtest.py` | 155-157 | Hard-coded unconditional rejection | **Remove the `continue`.** |
| `run_oos_2025q4_backtest.py` | 148-150 | Hard-coded unconditional rejection | **Remove the `continue`.** |
| `run_jan_compare.py` | 125-126 | Hard-coded unconditional rejection | **Remove the `continue`.** |
| `run_jan_v1_comparison.py` | 168-182, 305 | Gated + 50% notional cap | **Remove entire gate block. Remove notional cap.** |
| `run_jan_v2_comparison.py` | 196-205, 331 | Gated + 50% notional cap | **Remove entire gate block. Remove notional cap.** |
| `run_jan_v3_comparison.py` | Same pattern | Gated + 50% notional cap | **Remove entire gate block. Remove notional cap.** |
| `cache_tick_data.py` | 105-107 | Hard-coded unconditional rejection | **Remove the `continue`.** Tick data should be cached for ALL scanner candidates. |

**For each file:** After removing the Profile X/unknown block, unknown-float stocks should fall through to the normal `filtered.append(c)` path — same as Profile A and B stocks.

#### 5. `run_megatest.py` — Remove unknown-float config constants (lines 34-39)

```python
# DELETE these lines entirely:
ALLOW_UNKNOWN_FLOAT = int(os.environ.get("WB_ALLOW_UNKNOWN_FLOAT", "0")) == 1
UNKNOWN_FLOAT_MIN_GAP = 50.0
UNKNOWN_FLOAT_MIN_PM_VOL = 1_000_000
UNKNOWN_FLOAT_MIN_RVOL = 10.0
UNKNOWN_FLOAT_NOTIONAL_FACTOR = 0.5
```

Same for equivalent constants in `run_jan_v1_comparison.py`, `run_jan_v2_comparison.py`, `run_jan_v3_comparison.py`.

#### 6. `.env` — Remove WB_ALLOW_UNKNOWN_FLOAT

```
# DELETE this line:
WB_ALLOW_UNKNOWN_FLOAT=1        # Allow stocks with unknown float if gap>=50%, pm_vol>=1M, rvol>=10x (50% notional cap)
```

This env var is no longer needed — unknown-float stocks are always allowed.

#### 7. ENV_BASE in all backtest runners — Remove WB_ALLOW_UNKNOWN_FLOAT

Every `ENV_BASE` dict that contains `"WB_ALLOW_UNKNOWN_FLOAT": "1"` — **remove that line**. It's dead config now.

Files: `run_jan_v1_comparison.py`, `run_jan_v2_comparison.py`, `run_jan_v3_comparison.py`, `run_megatest.py`, `run_ytd_v2_backtest.py`, and any others with it in ENV_BASE.

#### 8. `stock_filter.py` — Float range checks (lines 235-238)

**CHANGE:** When float_shares is None, skip the float check entirely (don't reject, don't flag).

```python
# BEFORE:
if info.float_shares is not None and info.float_shares < self.min_float:
    reasons.append(f"float {info.float_shares:.2f}M < {self.min_float:.1f}M (micro-float)")
if info.float_shares is not None and info.float_shares > self.max_float:
    reasons.append(f"float {info.float_shares:.1f}M > {self.max_float:.1f}M")

# AFTER (no change needed — these already check `is not None` before comparing):
# These lines are FINE as-is. They only reject stocks with KNOWN float outside range.
# Unknown float (None) passes through silently. No change needed.
```

**VERIFY:** Confirm this is the actual behavior. If there's any other float check in stock_filter.py that rejects None, remove it.

#### 9. `simulate.py` — Quality min float gate (lines 354-357)

```python
# CURRENT:
if (self.stock_info.float_shares is not None
        and self.stock_info.float_shares < self.quality_min_float):
    return None  # BLOCKS entry

# This is FINE as-is — it only blocks if float is KNOWN and below 0.5M.
# Unknown float (None) passes through. No change needed.
```

#### 10. `trade_manager.py` — Quality min float gate (line 483)

```python
# CURRENT:
if info.float_shares is not None and info.float_shares < self.quality_min_float:
    return False, f"micro_float:{info.float_shares:.2f}M"

# This is FINE as-is — same logic. Only blocks KNOWN micro-float. No change needed.
```

### What NOT to Change

- **Don't remove the float > 10M ("skip") filter in classify_profile().** That's a separate ceiling based on Ross's criteria. Unknown float ≠ high float.
- **Don't remove WB_MIN_FLOAT or WB_MAX_FLOAT from .env.** These still gate KNOWN floats correctly.
- **Don't remove WB_QUALITY_MIN_FLOAT.** This gates known micro-float stocks at trade time. It doesn't affect unknown-float stocks.
- **Don't rename "unknown" to "A" in classify_profile().** Profile A triggers full-risk sizing in `calculate_dynamic_risk()` (trade_manager.py line 46) and `calculate_risk()` (run_ytd_v2_profile_backtest.py line 166). Profile B gets 1/3 risk capped at $250. Mislabeling unknown-float stocks as "A" would give them full-size treatment in any system that uses profile-based sizing. Keep the label as "unknown" — just stop filtering on it.

### CAUTION: `run_ytd_v2_profile_backtest.py` — Profile-Specific Risk Sizing

This file uses profile to determine BOTH risk sizing AND env config:
- Line 364: `risk = calculate_risk(equity, profile)` → A=full risk, B=capped
- Line 367-370: `if profile == "B": profile_env = PROFILE_B_ENV else: profile_env = PROFILE_A_ENV`

Unknown-float stocks (profile="unknown") will hit the `else` branch and get Profile A env. This is fine for now — the V1 flat-risk runners are the primary backtest tool, and `run_ytd_v2_profile_backtest.py` is a specialized test script. But if profile-based sizing ever returns to the main runners, unknown-float stocks will need their own handling.

### Quick Sanity Check After Changes

```bash
# Verify no remaining Profile X / unknown-float rejections in Python files:
grep -rn '"X"' *.py | grep -i 'profile\|unknown\|skip\|continue'
grep -rn 'ALLOW_UNKNOWN' *.py .env
grep -rn 'profile.*unknown' *.py
grep -rn '_unknown_float' *.py
```

All of these should return zero results (or only comments/docs).

---

## PART 2: Continuous Scanner — Real-Time Watchlist Updates

### The Problem

The bot loads the watchlist ONCE at startup (`bot.py` line 802: `raw_watchlist = get_raw_watchlist()`). After that, it never checks for new stocks. If a stock gaps up on breaking news at 8:30 AM but the bot started at 7:00 AM, it's invisible.

The live_scanner already writes updated watchlist.txt every 5 minutes (live_scanner.py lines 647-653). But the bot doesn't re-read it.

### The Fix

#### bot.py — Add watchlist refresh loop

The bot's main loop processes 1m bar callbacks. Add a periodic check (every 5 minutes) that re-reads the watchlist and subscribes to new symbols.

**New function:**

```python
def refresh_watchlist(current_symbols: set, stream_conn) -> set:
    """Re-read watchlist and subscribe to any new symbols.
    Called every 5 minutes during the trading window (7:00-11:00 AM ET).
    Returns updated set of all active symbols."""
    new_raw = get_raw_watchlist()
    new_filtered = filter_watchlist(new_raw)

    # Find newly added symbols
    added = new_filtered - current_symbols
    if not added:
        return current_symbols

    print(f"\n🔄 Watchlist refresh: +{len(added)} new symbols: {sorted(added)}", flush=True)
    log_event("watchlist_refresh", None, added=sorted(added), total=len(current_symbols) + len(added))

    # Subscribe to new symbols for 1m bars + trades
    for sym in added:
        # Initialize bar builders, detectors, etc. for new symbols
        # (same initialization as startup, but for individual symbols)
        pass  # CC: implement symbol initialization here

    # Subscribe to websocket streams for new symbols
    # (CC: use the same subscription mechanism as startup)

    return current_symbols | new_filtered
```

**In the main loop** (around where 1m bars are processed), add:

```python
# Check for watchlist updates every 5 minutes
now_et = datetime.now(ET)
if (now_et.hour >= 7 and now_et.hour < 11
    and (now_et - last_watchlist_check).total_seconds() >= 300):
    active_symbols = refresh_watchlist(active_symbols, stream_conn)
    last_watchlist_check = now_et
```

**IMPORTANT:** CC needs to handle:
1. Initializing bar builders for new symbols (seed bars, EMA, VWAP)
2. Subscribing to Alpaca websocket for new symbols' 1m bars + trades
3. Not re-initializing symbols that are already active
4. Logging what was added and when

#### scanner_sim.py — Increase rescan frequency

For backtesting, scanner_sim rescans every 30 minutes. Change to every 10 minutes to match the spirit of continuous monitoring:

```python
# BEFORE:
SCAN_CHECKPOINTS = [
    ("08:00", 8, 0),
    ("08:30", 8, 30),
    ("09:00", 9, 0),
    ("09:30", 9, 30),
    ("10:00", 10, 0),
    ("10:30", 10, 30),
]

# AFTER:
SCAN_CHECKPOINTS = [
    ("07:30", 7, 30),
    ("07:40", 7, 40),
    ("07:50", 7, 50),
    ("08:00", 8, 0),
    ("08:10", 8, 10),
    ("08:20", 8, 20),
    ("08:30", 8, 30),
    ("08:40", 8, 40),
    ("08:50", 8, 50),
    ("09:00", 9, 0),
    ("09:10", 9, 10),
    ("09:20", 9, 20),
    ("09:30", 9, 30),
    ("09:40", 9, 40),
    ("09:50", 9, 50),
    ("10:00", 10, 0),
    ("10:10", 10, 10),
    ("10:20", 10, 20),
    ("10:30", 10, 30),
]
```

Update `_CHECKPOINT_WINDOWS` accordingly — each window spans from the previous checkpoint to the current one (10-minute windows instead of 30).

**NOTE:** This increases Alpaca API calls significantly. Each checkpoint fetches bars for all symbols not yet found. If this causes rate limiting, CC should add backoff logic or batch the requests.

**ALSO:** Start scanning at 7:30 instead of 8:00. The current 45-minute gap between the 7:15 premarket scan and the 8:00 first rescan is where ZENA and other breaking-news stocks fell through.

#### live_scanner.py — Already continuous (no change needed)

The live scanner already writes every 5 minutes (lines 647-653). It streams Databento data continuously. No changes needed here — it's already doing what we want. The bottleneck is the bot not re-reading the output.

---

## PART 3: Regression Check

### Profile X removal — verify no regression on known stocks

```bash
source venv/bin/activate

# VERO regression (MP trade, known float — should be unchanged)
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

# ROLR regression (MP trade, known float — should be unchanged)
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

These should be **completely unchanged** — the Profile X removal only affects stocks with unknown float. VERO and ROLR have known floats.

### Scanner timing — spot-check with backtest

After updating scanner_sim.py checkpoints, re-run scanner_sim for a date where we KNOW a stock was missed due to timing:

```bash
python scanner_sim.py 2025-01-07
# ZENA should now appear (news broke at 7:30 AM, was missed by 8:00 checkpoint)
```

---

## PART 4: Commit and Push

```bash
git add scanner_sim.py live_scanner.py bot.py stock_filter.py .env \
    run_megatest.py run_ytd_v2_backtest.py run_ytd_v2_profile_backtest.py \
    run_oos_2025q4_backtest.py run_jan_compare.py \
    run_jan_v1_comparison.py run_jan_v2_comparison.py run_jan_v3_comparison.py \
    cache_tick_data.py

git commit -m "$(cat <<'EOF'
Scanner overhaul: remove Profile X filtering + continuous watchlist refresh

Profile X removal:
- classify_profile() now returns "A" for unknown float (was "unknown")
- passes_float_filter() now allows unknown float through (was False)
- Removed all profile in ("X", "unknown") skip blocks from every
  backtest runner (megatest, ytd, oos, jan comparison, cache_tick_data)
- Removed WB_ALLOW_UNKNOWN_FLOAT env var and all associated config
  (exceptional signal gates, 50% notional cap) — no longer needed
- Unknown-float stocks are now treated identically to known-float stocks

Backtest evidence: GDTC +$4,393 (83% capture), AMOD +$3,642 (100% WR),
XPON +$3,321, VRME +$822 — all were blocked by Profile X filtering.

Scanner timing:
- scanner_sim.py: rescan every 10 min (was 30), starting at 7:30 (was 8:00)
- bot.py: refresh_watchlist() every 5 min during trading window
  (was: load once at startup, never refresh)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Summary of What's Changing

| Component | Before | After |
|-----------|--------|-------|
| Unknown float at scanner | Labeled "unknown", blocked downstream | Labeled "A", treated as normal stock |
| Unknown float at live scanner | `passes_float_filter()` returns False → rejected | Returns True → allowed through |
| Unknown float in backtest runners | Blocked unconditionally OR gated (gap≥50%, pm_vol≥1M, rvol≥10x, 50% notional) | Allowed at full notional, no special gates |
| `WB_ALLOW_UNKNOWN_FLOAT` env var | Controls conditional gate | **Deleted** — no longer needed |
| Profile "X" string | Appears in old scanner JSONs, checked everywhere | Treated as "A" if encountered in legacy data |
| Scanner_sim rescan frequency | Every 30 min (8:00-10:30) | Every 10 min (7:30-10:30) |
| Bot watchlist | Loaded once at startup | Refreshed every 5 min during 7:00-11:00 window |
| `_unknown_float` marker + notional cap | Applied to unknown-float stocks | **Deleted** — no special treatment |

**Expected P&L impact:** +$12,178/month from Profile X removal alone (GDTC, AMOD, XPON, VRME). Scanner timing improvements add more from catching stocks like ZENA (+$1,865) that broke after the initial scan.
