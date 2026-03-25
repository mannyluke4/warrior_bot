# Directive: Ross Exit V2 — Signal Hierarchy Fix

## Priority: HIGH
## Owner: CC
## Created: 2026-03-23
## Author: Cowork (Opus)

---

## Context

Ross exit V1 (`ross_exit.py`, commit `b73b2e3`) was modeled after the comprehensive analysis in
`ross_exit_timing_vs_bot_analysis.md`. The implementation addressed 6 of 8 identified gaps
correctly, but introduced 3 bugs that explain the **-$17,815 YTD underperformance** vs baseline
(see `cowork_reports/ross_exit_2026_ytd_backtest.md`).

**The V1 correctly does:**
- Moves exit detection from 10s bars to 1m bars ✅
- Implements CUC (candle-under-candle) ✅
- Implements structural trailing stop (low of last green 1m candle) ✅
- Implements 50% partial on doji warning ✅
- Adds MACD/EMA20/VWAP backstops ✅
- Replaces fixed R-targets for all trade types when enabled ✅

**The V1 gets wrong (3 bugs causing -$17,815):**

1. **Evaluation order is inverted.** Tier 1 backstops (VWAP/EMA20/MACD) fire BEFORE candle
   signals. The source analysis says backstops are the LAST line of defense. On a runner like
   ARTL, MACD flickering negative during consolidation triggers a full exit before CUC or
   doji even gets evaluated. Ross's hierarchy is: candle patterns FIRST, indicators as BACKSTOP.

2. **Shooting star is 100% exit instead of 50% warning.** The source analysis groups topping
   tail / shooting star with doji as Phase 1 WARNING signals (sell 50%). V1 treats shooting
   star as a Tier 2 CONFIRMED signal (sell 100%). A single wick-heavy candle during a run
   dumps the entire position. Ross would lighten by 50% and watch the next candle.

3. **CUC bullish context check is too weak.** V1 requires only 1 prior green bar. The source
   analysis says CUC requires "≥2 consecutive bars making higher highs before." V1 fires CUC
   in choppy zones where one bar happened to be green — not a real trend reversal.

**Additional issue (sim/live divergence):**
- `simulate.py` (line 2278-2282) intentionally does NOT apply structural stop as tick-level
  stop — exits on bar CLOSE only.
- `trade_manager.py` (line 2554-2557) DOES apply structural stop to `t.stop` and
  `t.runner_stop`, causing tick-level stop-outs on intra-bar wicks.
- This means backtesting and live trading behave differently. Fix: align live to match sim
  behavior (structural stop only evaluated on 1m bar close, not tick-by-tick).

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin main
```

---

## Change 1: Reorder Signal Evaluation — Candles First, Backstops Last

### What
Reverse the evaluation order in `ross_exit.py:on_1m_bar_close()`. Candle patterns (CUC,
gravestone, shooting star, doji) evaluate FIRST. Technical backstops (VWAP, EMA20, MACD)
evaluate LAST as the "you must not still be holding" fallback.

### Why
Ross's signal hierarchy from the source video:
1. Level 2 / Time & Sales (earliest warning — N/A for backtest)
2. **Candlestick shapes — the PRIMARY exit trigger**
3. **Technical indicators — lagging backstops**

V1 has this backwards: indicators fire first (Tier 1), candles second (Tier 2/3). On a
runner, MACD going temporarily negative during a healthy consolidation candle triggers a
full exit before the candle pattern even gets evaluated. The candle itself might be a
perfectly fine green bar with a slightly negative MACD histogram.

### Implementation

In `ross_exit.py`, method `on_1m_bar_close()`, restructure the evaluation block
(currently lines 195-258) into this order:

```
# ═══════════════════════════════════════════════════════════════
# TIER 1 — WARNING CANDLES (50% partial exit)
# ═══════════════════════════════════════════════════════════════
# Regular Doji (existing)
# Shooting Star → RECLASSIFIED from full_100 to partial_50 (see Change 2)
# Topping Tail → NEW signal, partial_50 (see Change 2)

# ═══════════════════════════════════════════════════════════════
# TIER 2 — CONFIRMED CANDLE REVERSALS (100% exit of remaining)
# ═══════════════════════════════════════════════════════════════
# Gravestone Doji (existing — stays as full_100)
# CUC — Candle Under Candle (existing — stays as full_100)

# ═══════════════════════════════════════════════════════════════
# TIER 3 — TECHNICAL BACKSTOPS (100% exit — last resort)
# ═══════════════════════════════════════════════════════════════
# VWAP break (existing)
# 20 EMA break (existing)
# MACD histogram negative (existing)
```

**Key change:** Tier 3 backstops now only fire if NO candle signal fired first. On a healthy
green candle where MACD happens to be negative, the candle signals return None (no pattern),
and THEN the MACD backstop catches it. On a doji candle where MACD is also negative, the
doji partial fires first (50% out), leaving the MACD to potentially catch the remainder
on the next bar if conditions worsen.

### Add profit-awareness to backstops

Add a `_backstop_min_r` threshold (env var `WB_ROSS_BACKSTOP_MIN_R`, default `0.0`):

When `unrealized_r >= _backstop_min_r` AND `unrealized_r >= 5.0` (deep in a runner),
backstops should fire as `partial_50` instead of `full_100`. This prevents a single MACD
flicker from dumping a +10R position. The candle signals (CUC, gravestone) handle full
exits on confirmed reversals.

```python
self._backstop_min_r = float(os.getenv("WB_ROSS_BACKSTOP_MIN_R", "0.0"))
```

In each backstop check:
```python
# VWAP break
if self._vwap_enabled and vwap and vwap > 0 and c < vwap:
    if in_trade and unrealized_r >= 5.0 and not self.partial_taken:
        return "partial_50", "ross_vwap_break_warning", new_structural_stop
    return "full_100", "ross_vwap_break", new_structural_stop
```

Same pattern for EMA20 and MACD. Below 5R, backstops fire full (protect small gains / cut
losers). Above 5R, backstops fire as a 50% warning first — CUC or next bar's backstop
handles the rest.

---

## Change 2: Reclassify Shooting Star as 50% Warning + Add Topping Tail

### What
- Move shooting star from Tier 2 (full_100) to Tier 1 (partial_50)
- Add a new "topping tail" pattern as Tier 1 (partial_50)

### Why
The source analysis groups topping tail / shooting star with doji as Phase 1 WARNING signals:

> **Phase 1 — Warning signal: sell 50%**
> - Regular doji after big green run
> - Large topping tail forming

> **Phase 2 — Confirmed signal: sell remaining 50% or 100%**
> - Gravestone doji or shooting star → skip Phase 1, sell 100% directly

Wait — the source actually says gravestone/shooting star skip Phase 1 and sell 100%.
Re-reading carefully: the source distinguishes between "topping tail" (general, any large
upper wick → 50% warning) and "shooting star" (red close + topping tail → 100% confirmed).

**So the correct mapping is:**
- Topping tail (large upper wick, green or flat close) → Phase 1, 50% warning — NEW
- Shooting star (red close + topping tail) → Phase 2, 100% confirmed — KEEP as full_100
- Gravestone doji → Phase 2, 100% confirmed — KEEP as full_100

### Implementation

**Add topping tail to Tier 1 (after doji, before shooting star):**

```python
# Topping Tail: large upper wick after green run, NOT a red close
# (If it closes red, it's a shooting star — handled in Tier 2)
if self._topping_tail_enabled and not self.partial_taken:
    if (not is_red                          # green or flat close (red = shooting star)
            and upper_wick / rng >= 0.50    # wick is >= 50% of bar range
            and upper_wick >= 2.0 * max(body, 1e-9)):  # wick >= 2x body
        prior_was_green = prev["c"] > prev["o"]
        if prior_was_green:
            return "partial_50", "ross_topping_tail_warning", new_structural_stop
```

**Keep shooting star in Tier 2 as full_100** — it's already correct (red candle + long
upper wick is a confirmed reversal per Ross).

**New env var:**
```python
self._topping_tail_enabled = os.getenv("WB_ROSS_TOPPING_TAIL_ENABLED", "1") == "1"
```

Add to `.env`:
```
WB_ROSS_TOPPING_TAIL_ENABLED=1   # Topping tail (green) → 50% warning
```

---

## Change 3: Strengthen CUC Bullish Context Requirement

### What
Require ≥2 consecutive bars making higher highs before CUC fires, instead of just 1 prior
green bar.

### Why
Source analysis:
> CUC requires "≥2 consecutive bars making higher highs before the CUC fires"

V1 only checks that the prior bar (or bar -3) was green. In a choppy consolidation, a single
green bar followed by a lower-low bar would trigger CUC — but there's no uptrend to reverse
from. This creates false exits in sideways zones.

### Implementation

Replace the current bullish context check (lines 229-243 of `ross_exit.py`):

```python
# Candle Under Candle: current low breaks prior low in bullish context
if self._cuc_enabled and curr["l"] < prev["l"]:
    # Require ≥2 consecutive higher-highs before this bar
    # (establishes an uptrend that the CUC is "reversing")
    bullish_context = False
    if len(self._bars) >= 3:
        b_minus2 = self._bars[-3]
        b_minus1 = self._bars[-2]  # == prev
        # Two prior bars made consecutive higher highs
        if b_minus1["h"] > b_minus2["h"]:
            # Check one more bar back if available
            if len(self._bars) >= 4:
                b_minus3 = self._bars[-4]
                bullish_context = b_minus2["h"] > b_minus3["h"]
            else:
                # Only 3 bars available — require the 2 we have to be green
                bullish_context = (b_minus2["c"] > b_minus2["o"]
                                   and b_minus1["c"] > b_minus1["o"])

    if bullish_context:
        # Deep runner gate (unchanged from V1)
        if in_trade and unrealized_r >= self._cuc_min_r:
            print(
                f"  ROSS_CUC_SUPPRESSED: unrealized={unrealized_r:.1f}R"
                f" >= threshold={self._cuc_min_r:.1f}R"
                f" — letting other signals handle exit",
                flush=True,
            )
        else:
            return "full_100", "ross_cuc_exit", new_structural_stop
```

The key difference: instead of "was prior bar green?", we now check "were the prior 2 bars
making consecutive higher highs?" This confirms an actual uptrend before declaring CUC as a
reversal signal.

---

## Change 4: Fix Sim/Live Structural Stop Divergence

### What
In `trade_manager.py`, stop applying the structural stop as a tick-level mechanical stop.
Instead, only evaluate it on 1m bar close (matching simulate.py behavior).

### Why
`simulate.py` (line 2278-2282) explicitly notes:
> Structural stop is NOT applied to t.stop. CUC handles the case when a 1m bar closes below
> the prior bar's low. Applying it as a tick-by-tick mechanical stop would cause premature
> exits on intra-bar noise that Ross explicitly ignores (he exits on bar CLOSE, not on tick).

But `trade_manager.py` (line 2554-2557) DOES ratchet `t.stop` and `t.runner_stop` to the
structural level. Then `_manage_exits` evaluates `t.stop` on every tick, causing stop-outs
on intra-bar wicks that Ross would hold through.

### Implementation

In `trade_manager.py:on_bar_close_1m_ross_exit()`, remove or gate the structural stop
ratchet. Instead, store the structural level separately and only evaluate it in the next
1m bar close callback.

Replace the current block (lines 2552-2563):

```python
# Structural stop ratchet: track the level but do NOT apply to t.stop.
# Ross exits on 1m bar CLOSE, not intra-bar ticks. The CUC signal handles
# the case when a 1m bar closes below prior low. Applying structural stop
# as a tick-level stop causes premature exits on intra-bar noise.
if new_stop is not None and t is not None:
    if not hasattr(t, '_ross_structural_stop'):
        t._ross_structural_stop = 0.0
    if new_stop > t._ross_structural_stop:
        old = t._ross_structural_stop
        t._ross_structural_stop = new_stop
        log_event("ross_structural_stop_update", symbol,
                  old_stop=round(old, 4), new_stop=round(new_stop, 4))
        print(
            f"  ROSS_STRUCT_STOP {symbol}: {old:.4f} → {new_stop:.4f} (tracked, not applied to tick stop)",
            flush=True,
        )
```

This preserves the structural stop tracking for logging/analysis without causing tick-level
stop-outs. The CUC signal naturally handles the bar-close-below-prior-low case.

**Important:** Do NOT remove the hard stop (`t.stop` from entry setup). The original pattern
stop from the micro-pullback or squeeze entry remains active on every tick. We're only
preventing the structural TRAIL from ratcheting `t.stop` upward and creating a too-tight
tick-level stop.

---

## Change 5: Add Tick Cache Write-Back to simulate.py

### What
When `simulate.py` fetches tick data from Databento API (cache miss), write the fetched data
to the tick cache directory before replaying.

### Why
The 297-day megatest fetched ~750 symbol-date tick datasets from Databento for all of 2025
and discarded them. 8+ hours of API calls, zero cache benefit. Any future backtest of 2025
data will re-fetch the same ticks. This is wasteful and costly.

### Implementation

In `simulate.py`, after the Databento fetch block (around lines 2414-2424), add cache write:

```python
elif feed == "databento":
    print(f"  Fetching tick data from Databento...", flush=True)
    from databento_feed import fetch_trades_historical
    _db_trades_raw = fetch_trades_historical(
        symbol, date_str,
        start_et=start_et_str, end_et=end_et_str,
    )
    from collections import namedtuple
    _DbnTick = namedtuple("_DbnTick", ["price", "size", "timestamp"])
    tick_trades = [_DbnTick(t["price"], t["size"], t["timestamp"]) for t in _db_trades_raw]

    # ── NEW: Write to tick cache if tick_cache dir was specified ──
    if tick_cache and _db_trades_raw:
        import gzip as _gzip
        _cache_dir = os.path.join(tick_cache, date_str)
        os.makedirs(_cache_dir, exist_ok=True)
        _cache_out = os.path.join(_cache_dir, f"{symbol}.json.gz")
        _cache_payload = [
            {"p": t["price"], "s": t["size"], "t": t["timestamp"].isoformat()
             if hasattr(t["timestamp"], "isoformat") else str(t["timestamp"])}
            for t in _db_trades_raw
        ]
        with _gzip.open(_cache_out, "wt") as _cf:
            json.dump(_cache_payload, _cf)
        print(f"  Cached {len(_cache_payload)} ticks → {_cache_out}", flush=True)
```

Also add the same write-back for the Alpaca fetch path (lines 2426-2427) using the same
pattern, converting Alpaca tick objects to the `{"p", "s", "t"}` cache format.

**Gate:** No env var needed — this is always-on. If `tick_cache` dir is specified (via
`--tick-cache`), we write. If not specified, no caching. Same as the existing read behavior.

---

## Regression

After implementing all changes, run:

```bash
# Regression — Ross exit OFF (should be unchanged)
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444

# Ross exit V2 — compare vs V1 on key runners
WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v 2>&1 | tee verbose_logs/VERO_ross_v2.log
WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ -v 2>&1 | tee verbose_logs/ROLR_ross_v2.log
WB_ROSS_EXIT_ENABLED=1 WB_MP_ENABLED=1 python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/ -v 2>&1 | tee verbose_logs/ARTL_ross_v2.log

# V1 reference (for delta comparison — re-run V1 to get same-session numbers)
# V1 YTD results: ARTL +$1,345, ROLR +$238, VERO +$13,433
# V2 should be CLOSER to baseline: ARTL +$9,512, ROLR +$4,634, VERO +$16,966
```

**Success criteria:** V2 should hold runners longer than V1. Specifically:
- ARTL V2 > ARTL V1 ($1,345) — target: closer to baseline $9,512
- ROLR V2 > ROLR V1 ($238) — target: closer to baseline $4,634
- VERO V2 > VERO V1 ($13,433) — target: closer to baseline $16,966

If V2 still underperforms baseline significantly, the verbose logs will show which signal
fired the exit. Report this in `cowork_reports/ross_exit_v2_results.md`.

---

## Post-Flight

```bash
# Write results to cowork_reports
# See DIRECTIVE_CC_COWORK_PROTOCOL.md for format

git add ross_exit.py trade_manager.py simulate.py .env verbose_logs/ cowork_reports/
git commit -m "$(cat <<'EOF'
Ross exit V2: fix signal hierarchy, add topping tail, strengthen CUC context

Change 1: Reorder evaluation — candle patterns first, backstops last
Change 2: Add topping tail as 50% warning; keep shooting star as 100%
Change 3: CUC requires ≥2 consecutive higher-highs (not just 1 green bar)
Change 4: Fix sim/live divergence — structural stop tracked, not applied to tick stop
Change 5: Tick cache write-back on Databento/Alpaca fetch (prevent data loss)

V1 underperformed baseline by $17,815 due to inverted signal hierarchy.
V2 corrects evaluation order to match Ross Cameron's actual methodology.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Summary of All Changes

| # | File | Change | Lines |
|---|------|--------|-------|
| 1 | `ross_exit.py` | Reorder: candles first, backstops last; add profit-aware backstop softening | ~195-260 |
| 2 | `ross_exit.py` | Move shooting star to after CUC; add topping tail as partial_50 | ~220-230 |
| 3 | `ross_exit.py` | CUC: require ≥2 consecutive higher-highs for bullish context | ~229-243 |
| 4 | `trade_manager.py` | Structural stop: track but don't apply to tick-level t.stop | ~2552-2563 |
| 5 | `simulate.py` | Write fetched ticks to cache after Databento/Alpaca API calls | ~2414-2427 |
| — | `.env` | Add `WB_ROSS_TOPPING_TAIL_ENABLED=1`, `WB_ROSS_BACKSTOP_MIN_R=0.0` | append |

**New env vars:**
```
WB_ROSS_TOPPING_TAIL_ENABLED=1   # Topping tail (green w/ big wick) → 50% warning
WB_ROSS_BACKSTOP_MIN_R=0.0       # Min R before backstops soften to 50% (0=always full)
```

---

*Directive written by Cowork (Opus) — 2026-03-23. Based on cross-reference of
`ross_exit_timing_vs_bot_analysis.md` against `ross_exit.py` V1 implementation,
`cowork_reports/ross_exit_2026_ytd_backtest.md`, and `cowork_reports/exit_strategy_crossref.md`.*
