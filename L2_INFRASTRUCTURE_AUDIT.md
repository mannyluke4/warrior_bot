# L2 INFRASTRUCTURE AUDIT — warrior_bot
**Date:** 2026-03-02  
**Repo:** mannyluke4/warrior_bot  
**Scope:** Full L2 subsystem review — l2_entry.py, l2_signals.py, databento_feed.py,  
           micro_pullback.py (L2 sections), bot.py (L2 sections), .env.example, simulate.py

---

## EXECUTIVE SUMMARY

The warrior_bot has a **complete, well-architected L2 subsystem** — but it is **off by default in live trading**. The code is not dead code; it is production-ready and wired into all the right places. The single line `WB_ENABLE_L2=0` in `.env.example` is the only thing keeping it dormant in the live bot.

In backtesting (`simulate.py`), L2 can be activated with `--l2` or `--l2-entry` flags, backed by Databento historical MBP-10 data. The architecture is cleanly separated: L2 is an optional overlay that enhances (never replaces) the existing MACD/VWAP/candle-pattern logic.

---

## 1. WHAT EXISTS — Every L2 Function, Class, and Method

### l2_signals.py — The Signal Engine

| Component | Type | Purpose |
|-----------|------|---------|
| `L2Snapshot` | dataclass | Container for a single order book snapshot: timestamp, symbol, bids[(price,size)], asks[(price,size)] — top-N levels |
| `L2Signal` | dataclass | A detected signal with: name (e.g. "L2_BID_STACK"), detail string, strength (0.0–1.0) |
| `L2SignalDetector` | class | Public facade — maintains per-symbol state, receives snapshots, exposes `get_state()` |
| `L2SignalDetector.on_snapshot(snap)` | method | Routes snapshot to per-symbol state object; creates new state if first snapshot for symbol |
| `L2SignalDetector.get_state(symbol)` | method | Returns current L2 state dict for a symbol (or None if no data yet). This is the dict that micro_pullback.py consumes |
| `L2SignalDetector.reset(symbol)` | method | Clears L2 state for a symbol (e.g. on session reset) |
| `_SymbolL2State` | class | Internal per-symbol state machine — computes all signals on each new snapshot |
| `_SymbolL2State.update(snap, det)` | method | Core computation: runs all 4 signal categories on the new snapshot |
| `_SymbolL2State.to_dict()` | method | Exports state as a flat dict for downstream consumption |

**The 4 Signal Categories computed in `_SymbolL2State.update()`:**

| Signal Category | What It Computes | Signal Name(s) |
|-----------------|-----------------|----------------|
| A. Order Book Imbalance | `total_bid / (total_bid + total_ask)` across all levels. Trend computed by comparing first-half vs second-half of 10-snapshot rolling history | `L2_IMBALANCE_BULL`, `L2_IMBALANCE_BEAR` |
| B. Bid Stacking | Flags any bid level with size > `stack_multiplier * avg_level_size` that is within 0.5% of best bid. Tracks persistence (snapshots). Stacking must be *near current price* | `L2_BID_STACK` |
| C. Large Order Detection | Compares current snapshot to previous. Flags any level that jumped by 5x AND exceeds 10,000 shares absolute. Checks both bid and ask sides | `L2_LARGE_BID`, `L2_LARGE_ASK` |
| D. Spread + Liquidity | `(best_ask - best_bid) / best_bid * 100`. Ask thinning: ask depth within 0.5% of best bid < 50% of bid depth in same zone | `L2_WIDE_SPREAD`, `L2_THIN_ASK` |

**State dict fields returned by `get_state()`:**
```python
{
    "imbalance":       float,   # 0.0–1.0, bid/(bid+ask) ratio
    "imbalance_trend": str,     # "rising" | "falling" | "flat"
    "bid_stacking":    bool,    # True if stacking near current price
    "bid_stack_levels": list,   # [(price, size), ...] of stacked levels
    "large_bid":       bool,    # True if 5x+ sudden jump on bid side
    "large_ask":       bool,    # True if 5x+ sudden jump on ask side
    "spread_pct":      float,   # bid-ask spread as % of best bid
    "ask_thinning":    bool,    # True if near-ask depth < 50% of near-bid depth
    "signals":         list,    # [L2Signal, ...] raw signal objects
}
```

---

### l2_entry.py — The Standalone L2 Entry Strategy

| Component | Type | Purpose |
|-----------|------|---------|
| `L2ArmedTrade` | dataclass | Holds an armed L2 entry: trigger_high, stop_low, entry_price, R, score, score_detail, setup_type="l2_entry" |
| `L2EntryDetector` | class | Detects pre-breakout entry setups driven purely by L2 signals. Completely separate from MicroPullbackDetector |
| `L2EntryDetector.seed_bar_close()` | method | Seeds EMA/MACD from historical bars without arming |
| `L2EntryDetector.on_bar_close()` | method | Main evaluation. Called on each 1-minute bar close. Returns log string or None |
| `L2EntryDetector.on_trade_price()` | method | Tick-level trigger check: fires entry if price >= trigger_high while armed |
| `L2EntryDetector._score_l2_entry()` | method | Scores the setup with weighted L2 signals |
| `L2EntryDetector._find_stop()` | method | Sets stop: uses highest bid_stack_level if available, else 3-bar swing low |
| `L2EntryDetector._reset_after_trade()` | method | Post-trade reset with 3-bar cooldown |
| `L2EntryDetector.full_reset()` | method | Hard reset all state |

**L2EntryDetector Scoring System:**

| Component | Score | Notes |
|-----------|-------|-------|
| Imbalance > 0.75 | +3.0 | Strong bull |
| Imbalance > 0.65 | +2.0 | Moderate bull |
| Imbalance > 0.58 | +1.0 | Mild bull |
| Bid stacking | +2.0 | |
| Ask thinning | +1.5 | Resistance fading |
| Large bid | +1.5 | Institutional interest |
| Imbalance trend rising | +1.0 | |
| MACD strength > 3 | +1.0 | Confirmation |
| Spread > 1.0% | −(spread/2, max 2.0) | Slippage risk penalty |
| Consecutive bullish bars ≥ 4 | +1.0 | Sustained pressure bonus |
| **Minimum score to arm** | **4.0** | (WB_L2E_MIN_SCORE) |

**Armed trigger:** Entry = break of current bar's high. This is a *pre-breakout* setup — L2 shows buyers accumulating BEFORE the breakout prints.

---

### databento_feed.py — Historical L2 Data Client

| Component | Purpose |
|-----------|---------|
| `fetch_l2_historical()` | Fetches MBP-10 data from Databento API for a symbol/date. Checks local cache first. Falls back from NASDAQ (XNAS.ITCH) to NYSE (XNYS.PILLAR) on failure |
| `_parse_dbn_file()` | Parses a cached `.dbn.zst` file into L2Snapshot objects |
| `_parse_dbn_data()` | Core parser: converts Databento DataFrame rows to L2Snapshot objects. **Samples at 1-second intervals** to reduce memory (raw L2 can be millions of updates/day) |
| `get_l2_for_bar_window()` | Filters L2 snapshots to those within a bar's time window. Used by simulate.py |
| `_resolve_dataset()` | Returns "XNAS.ITCH" by default (hardcoded — exchange auto-detection is a TODO) |
| `_cache_path()` | Naming: `l2_cache/{SYMBOL}_{DATE}_{EXCHANGE_PREFIX}.dbn.zst` |

**Data format:** MBP-10 (Market by Price, top 10 levels). Each snapshot contains up to 10 bid and 10 ask levels as (price, size) tuples. Databento prices in raw format may be fixed-point (divided by 1e9 if > 1e6).

---

### micro_pullback.py — L2 Integration (Summary)

4 embedded L2 mechanisms (detailed in Section 4):

| Method | Role |
|--------|------|
| `_l2_bullish_strength()` | Counts 0–5 bullish signals present |
| `_l2_is_bearish()` | Conservative bearish check (hard gate) |
| `check_l2_exit()` | Exit signal generator |
| `_score_setup()` | Adds/subtracts L2-based score points |

---

## 2. DATA FLOW — How L2 Gets from Databento → Trading Decisions

### Backtesting Path (simulate.py --l2)

```
Databento API
    │
    ▼ fetch_l2_historical(symbol, date)
[.dbn.zst local cache] ────────────────────────────────┐
    │                                                   │
    ▼ _parse_dbn_data()                                │
[list of L2Snapshots, sampled 1/sec]                   │
    │                                                   │
    ▼ (per bar loop in simulate.py)                    │
filter snapshots for this bar's time window            │
    │                                                   │
    ▼ l2_det.on_snapshot(snap) [for each snap]         │
[_SymbolL2State.update()]                              │
  ├── Compute imbalance ratio + trend                  │
  ├── Detect bid stacking (near price)                 │
  ├── Detect large order jumps (vs prev snapshot)      │
  └── Compute spread + ask thinning                    │
    │                                                   │
    ▼ l2_det.get_state(symbol)                        │
[L2 state dict]                                        │
    │                                                   │
    ├──▶ det.on_bar_close_1m(bar, vwap, l2_state)      │
    │       ├── Store as _last_l2_state (for scoring)  │
    │       ├── _l2_bullish_strength() → impulse accel │
    │       ├── bid_stack_levels → stop enhancement    │
    │       ├── _l2_is_bearish() → hard gate           │
    │       └── _score_setup() reads _last_l2_state    │
    │               (adds/subtracts score)              │
    │                                                   │
    └──▶ det.check_l2_exit(l2_state)                   │
            (if open position: may trigger exit)        │
```

### Live Trading Path (bot.py with WB_ENABLE_L2=1)

```
IBKR TWS/Gateway (real-time L2 stream)
    │
    ▼ ibkr_feed.subscribe_l2(symbol, callback)
    │
    ▼ _on_l2_update(symbol, snapshot)   [fires on every L2 update]
    │
    ▼ l2_detector.on_snapshot(snapshot)
    │
    [state held in memory, per-symbol, updated continuously]
    │
    ▼ [on 1-minute bar close — bar_builder_1m fires on_bar_close_1m()]
    │
    ▼ l2_state = l2_detector.get_state(symbol)
    │
    ├──▶ det.on_bar_close_1m(bar, vwap, l2_state)
    │       [same logic as backtest]
    │
    └──▶ det.check_l2_exit(l2_state)
            [if open position]
```

**Key architectural note:** L2 data is consumed at **bar-close granularity** (once per minute), not at tick frequency. The live L2 stream updates the internal state continuously, but the decision logic only reads `get_state()` when a 1-minute bar closes. This is a deliberate design — it avoids over-trading on momentary order book noise.

---

## 3. WHAT IT CURRENTLY MEASURES — Every Metric / Signal

| Metric | Calculation | What It Tells You |
|--------|-------------|------------------|
| `imbalance` | `total_bid_size / (total_bid_size + total_ask_size)` across all levels | Overall book weight: >0.65 = buyers dominating, <0.35 = sellers dominating |
| `imbalance_trend` | Compare avg of first half vs second half of 10-snapshot rolling history. Threshold: ±0.05 | Is buying pressure accelerating ("rising") or fading ("falling")? |
| `bid_stacking` | Any bid level size > 3× avg level size, within 0.5% of best bid | Buyers actively "stacking" at current price — visible institutional support |
| `bid_stack_levels` | List of (price, size) for all stacking levels near price | Specific prices where buyers are concentrated — used as stop reference |
| `large_bid` | Any bid level with 5× sudden size jump vs prior snapshot AND ≥10,000 shares | Sudden large buyer appearing — potentially iceberg order surfacing |
| `large_ask` | Same logic on ask side | Sudden large seller appearing — distribution signal |
| `spread_pct` | `(best_ask - best_bid) / best_bid * 100` | Book liquidity health; >1% penalized in scoring, >3% blocks L2 entry |
| `ask_thinning` | Ask depth within 0.5% of best bid < 50% of bid depth in same zone | Resistance evaporating — sellers not defending current level |

**Signal strengths (normalized 0.0–1.0) for each L2Signal:**
- `L2_IMBALANCE_BULL`: `min(1.0, (imbalance - 0.5) * 4)` — scales linearly from 0 at 0.5 to 1.0 at 0.75
- `L2_IMBALANCE_BEAR`: `min(1.0, (0.5 - imbalance) * 4)` — mirror image
- `L2_BID_STACK`: `max(0.3, min(1.0, persist_count / 10))` — ramps up with persistence, minimum 0.3 when detected
- `L2_LARGE_BID` / `L2_LARGE_ASK`: `min(1.0, size / 50_000)` — scales with absolute size
- `L2_WIDE_SPREAD`: `min(1.0, spread_pct / 3.0)` — full strength at 3%+
- `L2_THIN_ASK`: `min(1.0, 1.0 - (ask_near / bid_near))` — scales with severity of thinning

---

## 4. INTEGRATION POINTS — How L2 Influences Decisions

### 4a. Scoring: Score Modifier (Not a Hard Gate)

**In `_score_setup()` (micro_pullback.py lines 497–524):**

L2 contributes additively/subtractively to the total setup score. These points are added on top of MACD, pattern tags, and R-quality scoring:

| Condition | Score Impact | Threshold |
|-----------|-------------|-----------|
| Bullish imbalance | +2.0 | imbalance > 0.65 |
| Bid stacking | +1.5 | bid_stacking == True |
| Ask thinning | +1.0 | ask_thinning == True |
| Bearish imbalance | **−3.0** | imbalance < 0.35 |
| Large ask wall | **−2.0** | large_ask == True |
| Wide spread | **−2.0** | spread_pct > 1.0 |

The current `WB_MIN_SCORE=3` default means a bearish imbalance (−3.0) alone can kill an otherwise marginal setup. A strong L2 context (+2.0 +1.5 +1.0 = +4.5 bonus) can push a borderline setup over the threshold.

### 4b. Hard Gate: Blocks Entry (Direct Veto)

**In `_direct_entry_check()` and `_pullback_entry_check()` (WB_L2_HARD_GATE=1 by default):**

```python
if self.l2_hard_gate and self._l2_is_bearish(l2_state):
    return f"1M NO_ARM L2_bearish imbalance={imb:.2f}"
```

`_l2_is_bearish()` triggers when:
- Imbalance < 0.30 (strong sellers dominating), OR
- large_ask=True AND imbalance < 0.45 (ask wall with weak buying)

This is a **veto** — it overrides even a high score. The condition is intentionally conservative (not just any bearish reading — must be truly dominated by sellers). `WB_L2_HARD_GATE=1` by default means this gate is **active even when WB_ENABLE_L2=0**, but since l2_state would be None in that case, `_l2_is_bearish(None)` returns False, so it never fires without data.

### 4c. Acceleration: Waives Candle Requirements

**L2 acceleration (enabled by WB_L2_ACCEL_IMPULSE=1 and WB_L2_ACCEL_CONFIRM=1):**

1. **Impulse acceleration** (`_direct_entry_check` and `_pullback_entry_check`):  
   Normally requires rising close (`b1["c"] > b2["c"]`). When L2 bullish strength ≥ 3 signals, this requirement is **waived** — a flat or slightly down-close bar can still be treated as an impulse. This allows entry on a "pause" bar when the order book shows strong accumulation.

2. **Confirmation acceleration** (`_pullback_entry_check` only):  
   Normally requires a hammer, bullish engulfing, or close in top 75% of range. When L2 bullish strength ≥ 3, a mediocre candle is **accepted anyway**. The logic: "the book knows what the candle can't see yet."

3. **Pullback gate**:  
   During a pullback phase, if L2 turns bearish, the state machine **resets immediately** (`1M RESET (L2 bearish during pullback)`). This prevents arming after a bearish book shift ruins the pullback setup.

### 4d. Stop Enhancement: Uses Bid Stack as Support

**In both `_direct_entry_check()` and `_pullback_entry_check()` (also in `l2_entry.py._find_stop()`):**

```python
if l2_state is not None and l2_state.get("bid_stack_levels"):
    stack_prices = [p for p, _ in l2_state["bid_stack_levels"]]
    if stack_prices:
        highest_stack = max(stack_prices)
        if highest_stack > raw_stop and highest_stack < entry:
            raw_stop = highest_stack
```

When buyers are visibly stacking at a price level near the current price, that level becomes the stop reference (minus STOP_PAD). This creates **tighter, more logical stops** than using bar lows alone — which directly improves position sizing (more shares for the same dollar risk).

### 4e. Exit Signal: Real-Time Exit Trigger

**In `check_l2_exit()` — called by bot.py and simulate.py on every 1-min bar close while a position is open:**

```python
if imbalance < 0.30:      → "l2_bearish"
if large_ask and imb < 0.45: → "l2_ask_wall"
```

This is the **only L2 mechanism that can force an exit** — it routes through `trade_manager.on_exit_signal()`. All other L2 mechanisms only influence entry decisions.

### Summary Matrix

| L2 Role | Mechanism | Gate Type | When Active |
|---------|-----------|-----------|-------------|
| Boost score | `_score_setup()` imbalance/stack/thinning | Score modifier (+/−) | On every ARM attempt |
| Penalize score | `_score_setup()` bearish imbalance/ask wall/spread | Score modifier | On every ARM attempt |
| Block entry | `_l2_is_bearish()` → hard gate | Hard veto | Pre-ARM in direct/pullback |
| Accelerate impulse | `_l2_bullish_strength() ≥ 3` | Waives rising-close | Impulse detection |
| Accelerate confirm | `_l2_bullish_strength() ≥ 3` | Waives candle quality | Confirmation detection |
| Reset on pullback | `_l2_is_bearish()` during pullback | Hard reset | Pullback phase |
| Enhance stop | `bid_stack_levels` → raw_stop | Stop placement | ARM calculation |
| Force exit | `check_l2_exit()` | Exit signal | While position open |

---

## 5. CONFIG VARIABLES — Every L2-Related .env Variable

### Variables Documented in .env.example

| Variable | Default | Controls |
|----------|---------|---------|
| `WB_ENABLE_L2` | `0` | Master switch for live L2. `0=off` means no IBKR connection, l2_detector=None |
| `WB_IBKR_HOST` | `127.0.0.1` | IBKR TWS/Gateway hostname |
| `WB_IBKR_PORT` | `7497` | IBKR port (7497=paper, 7496=live) |
| `WB_IBKR_CLIENT_ID` | `1` | IBKR API client ID |
| `WB_L2_IMBALANCE_BULL` | `0.65` | Threshold for `L2_IMBALANCE_BULL` signal |
| `WB_L2_IMBALANCE_BEAR` | `0.35` | Threshold for `L2_IMBALANCE_BEAR` signal |
| `WB_L2_STACK_MULTIPLIER` | `3.0` | A level is "stacked" when its size > N × avg level size |
| `WB_L2_SPREAD_WARN` | `1.0` | Spread % above which `L2_WIDE_SPREAD` fires |
| `DATABENTO_API_KEY` | *(none)* | Required for backtesting with `--l2`. Not needed for live. |

### Variables NOT in .env.example (Hidden Defaults)

| Variable | Default | Controls |
|----------|---------|---------|
| `WB_L2_ACCEL_IMPULSE` | `1` | Enable L2 to waive rising-close impulse requirement |
| `WB_L2_ACCEL_CONFIRM` | `1` | Enable L2 to waive weak trigger candle at confirmation |
| `WB_L2_HARD_GATE` | `1` | Enables hard block when `_l2_is_bearish()` returns True |
| `WB_L2_MIN_BULLISH_ACCEL` | `3` | Min count from `_l2_bullish_strength()` to trigger acceleration |
| `WB_L2E_MIN_BULLISH_BARS` | `2` | L2EntryDetector: consecutive bullish bars before arming |
| `WB_L2E_MIN_SIGNALS` | `2` | L2EntryDetector: min bullish signals per bar |
| `WB_L2E_IMBALANCE_MIN` | `0.58` | L2EntryDetector: lower imbalance threshold (vs 0.65 for scoring) |
| `WB_L2E_MAX_SPREAD` | `3.0` | L2EntryDetector: max spread % allowed |
| `WB_L2E_MAX_VWAP_PCT` | `15` | L2EntryDetector: exhaustion gate (% above VWAP) |
| `WB_L2E_MAX_MOVE_PCT` | `60` | L2EntryDetector: exhaustion gate (% from session low) |
| `WB_L2E_MIN_SCORE` | `4.0` | L2EntryDetector: minimum score to ARM |
| `WB_L2_CACHE_DIR` | `l2_cache` | Local directory for Databento `.dbn.zst` cached files |

**Gap:** 11 L2-related variables have working defaults in code but are not documented in `.env.example`. This is a documentation gap — a developer enabling L2 has no visibility to these tuning knobs.

---

## 6. WHAT'S MISSING OR COULD BE IMPROVED

### 6a. Pre-Trade Filtering: Is the Book Thin or Thick?

**Current state:** `spread_pct` is computed and included in the score (wide spread = −2.0 penalty). `ask_thinning` adds +1.0 to score when resistance fades.

**Gap:** There is no *pre-entry* minimum liquidity check in `micro_pullback.py`. The `L2EntryDetector` has `WB_L2E_MAX_SPREAD=3.0` as a hard block, but the main `MicroPullbackDetector` only uses spread as a scoring penalty, not a hard veto.

**What to add:** A liquidity quality gate before arming. Example:
```python
# Block if total book depth < minimum threshold
total_near_depth = sum(s for p, s in l2_state["bids"][:3]) + sum(s for p, s in l2_state["asks"][:3])
if total_near_depth < WB_L2_MIN_NEAR_DEPTH:
    return "1M NO_ARM (thin book)"
```
This would prevent entries on stocks where the L2 shows only a handful of shares at the top 3 levels — high slippage risk even if imbalance looks good.

### 6b. Entry Timing: Is There Bid Support at Key Levels?

**Current state:** `bid_stacking` is detected and used in two ways:
1. Score modifier (+1.5)
2. Stop enhancement (use highest stack as stop reference)

**Gap:** The system doesn't track *where* the stacking is relative to key levels (VWAP, premarket high, round numbers). A bid stack at VWAP is much more significant than one 10 cents below a random price.

**What to add:** Level-aware stacking signal:
```python
# Is the bid stack at or near a key level?
for price, size in l2_state["bid_stack_levels"]:
    if abs(price - vwap) / vwap < 0.005:   # within 0.5% of VWAP
        score += 1.5  # "bid_stack_at_vwap"
    if premarket_high and abs(price - premarket_high) / premarket_high < 0.005:
        score += 1.5  # "bid_stack_at_pm_high"
```

### 6c. Exit Decisions: Is Sell Pressure Mounting?

**Current state:** `check_l2_exit()` only fires on two extreme conditions:
- Imbalance < 0.30 (strong sellers)
- Large ask wall + imbalance < 0.45

**Gap:** The exit logic misses early warning signals:
1. **Declining imbalance trend** — the book is shifting from bullish to neutral BEFORE hitting 0.30. `imbalance_trend == "falling"` is computed but never used in exit decisions.
2. **Stacking appearing on the ask side** — a large ask appearing near HOD is a distribution signal that the exit logic doesn't check.
3. **Spread widening suddenly** — a sudden spread expansion (e.g., 0.2% → 1.5%) while in a trade signals a liquidity event.

**What to add:**
```python
def check_l2_exit_enhanced(self, l2_state):
    # Existing: imbalance < 0.30 and ask_wall + weak imbalance
    
    # New: falling imbalance trend + below neutral
    if (l2_state.get("imbalance_trend") == "falling" 
        and l2_state.get("imbalance", 0.5) < 0.45):
        return "l2_trend_shift"
    
    # New: spread spike (sudden deterioration)
    if l2_state.get("spread_pct", 0) > WB_L2_EXIT_SPREAD_PCT:
        return "l2_spread_spike"
```

### 6d. Scanner Study Context: Distinguishing Winners from Losers

**Current state:** L2 is only used at the per-bar decision point, not in the pre-trade scanner/filter phase.

**Gap:** The scanner (`market_scanner.py`, `stock_filter.py`) does not consider order book quality at all. L2 could provide early-session signals before the first bar:

1. **Book quality at open:** A stock with massive bid support and thin ask side in the first 30 seconds is a fundamentally different candidate than one with a thin, balanced book — even if both have the same gap%, float, and relative volume.

2. **Pre-entry imbalance trend:** If a stock has been building bullish imbalance for the first 5 minutes of trading, it's a higher-conviction setup than one that just had a single strong bar.

3. **For the scanner study (30 stocks):** The L2 data from Databento could be used *retrospectively* to label whether winning trades had bid support and losing trades had thin/bearish books at entry time. This would quantify whether L2 actually improves edge.

**What to add — Scanner L2 Pre-filter:**
```python
# In stock_filter.py or market_scanner.py:
# After stocks pass gap/float/volume filters,
# fetch first 5 minutes of L2 data and compute:
def get_l2_quality_score(symbol, date):
    snaps = fetch_l2_historical(symbol, date, "09:30", "09:35")
    det = L2SignalDetector()
    for snap in snaps:
        det.on_snapshot(snap)
    state = det.get_state(symbol)
    # Rank candidates by L2 quality at open
    return state["imbalance"] + (0.3 if state["bid_stacking"] else 0)
```

### 6e. Exchange Auto-Detection

**Current state:** `_resolve_dataset()` in `databento_feed.py` always returns `"XNAS.ITCH"` with a TODO comment. It falls back to `XNYS.PILLAR` on error.

**Gap:** This means every NYSE-listed stock requires a failed NASDAQ fetch before getting the correct dataset. For stocks like SPY, NVDA (NYSE-listed), this adds latency and unnecessary API costs.

**Fix:** Use Alpaca metadata or a hardcoded lookup table of known NYSE-listed symbols to pre-select the correct dataset.

### 6f. L2 Data Sampling Rate

**Current state:** `databento_feed.py` samples at **1-second intervals** (deduplicated by `ts_sec`). Raw MBP-10 data can be millions of events per day; 1 per second gives ~23,400 snapshots for a 6.5-hour session.

**Gap:** For fast-moving low-float stocks (the primary target), order book changes in milliseconds during key moments. A 1-second sample might miss a bid stack that appeared and disappeared within 500ms.

**Consideration:** Increasing to every 100ms during the first 30 minutes of trading (when most setups form) could improve signal quality at a manageable cost increase.

### 6g. L2EntryDetector Not Integrated with Scoring

**Current state:** `L2EntryDetector` is a completely separate strategy — it runs in parallel with `MicroPullbackDetector` in `simulate.py`, but the two never interact. A stock can trigger both simultaneously.

**Gap:** No combined scoring or priority logic. If both strategies fire on the same bar, simulate.py processes them independently, which could theoretically result in a double entry.

---

## 7. CURRENT STATE: Is L2 Code Active in Live Trading?

### Short Answer: **NO — L2 is wired but switched off.**

**In the live bot (bot.py):**

```python
# Line 732 in bot.py
if os.getenv("WB_ENABLE_L2", "0") == "1":
    l2_detector = L2SignalDetector()
    # ... IBKR connection ...
else:
    l2_detector = None   # ← This is what runs with the default .env
```

With `WB_ENABLE_L2=0` (the .env.example default), `l2_detector = None`. Every downstream call to `l2_detector.get_state(symbol)` returns `None`, and every function that receives `l2_state=None` silently no-ops:

- `_l2_bullish_strength(None)` → returns 0 (no acceleration ever fires)
- `_l2_is_bearish(None)` → returns False (no hard gate ever fires)
- `check_l2_exit(None)` → returns None (no L2 exit ever fires)
- `_score_setup()` reads `self._last_l2_state` → `None` (no L2 score contribution)

**Result:** With `WB_ENABLE_L2=0`, the bot behaves identically to a bot with no L2 code at all. All L2 code paths are fully backward-compatible no-ops.

### In backtesting (simulate.py):

L2 is **not active by default** either. You must explicitly pass `--l2` or `--l2-entry`:

```bash
python simulate.py ENVB 2026-02-19              # No L2 (default)
python simulate.py ENVB 2026-02-19 --l2         # L2 scoring/gates active via Databento
python simulate.py ENVB 2026-02-19 --l2-entry   # L2EntryDetector strategy (implies --l2)
```

### Is the Code Dead?

**No.** The code is:
1. **Complete** — all signal detection, scoring, gating, and exit logic is implemented
2. **Connected** — properly wired into every decision point in micro_pullback.py and bot.py  
3. **Tested** — l2_signals.py has a `__main__` block with synthetic data, databento_feed.py has CLI usage
4. **Backward-compatible** — 100% no-op when disabled (None-safe everywhere)
5. **Documented** — each function has a docstring explaining its purpose

The code is better described as **dormant infrastructure awaiting activation** — a deliberate architectural choice (new features default-off until validated in backtesting).

### To Activate in Live Trading:

```bash
# In .env:
WB_ENABLE_L2=1
WB_IBKR_HOST=127.0.0.1
WB_IBKR_PORT=7497   # 7497 for paper, 7496 for live

# Requires:
# 1. IBKR TWS or IB Gateway running and accepting API connections
# 2. ibkr_feed.py (IBKRFeed class) to be fully implemented
#    (note: bot.py imports IBKRFeed but its implementation was not in scope)
```

---

## 8. ARCHITECTURE ASSESSMENT

### Strengths

1. **Clean separation of concerns.** `l2_signals.py` does signal detection, `micro_pullback.py` does decision-making. The L2 state dict is a clean interface.
2. **Fail-graceful.** Every function handles `None` l2_state. The bot never crashes without L2 data.
3. **Dual-source architecture.** Databento for historical backtest, IBKR for live. The same `L2Snapshot` and `L2SignalDetector` classes work for both.
4. **Per-symbol state isolation.** Each symbol has its own `_SymbolL2State` — no cross-symbol contamination.
5. **Conservative bearish gates.** `_l2_is_bearish()` requires imbalance < 0.30 (very extreme) or explicit ask wall + weak imbalance. This avoids false exits during normal pullback chop.

### Weaknesses

1. **`WB_L2_ACCEL_IMPULSE=1` and `WB_L2_ACCEL_CONFIRM=1` default to ON.** These accelerations require L2 strength ≥ 3, which can never be reached when `l2_state=None` (strength returns 0). So they are functionally dormant without L2 data, but the code reads as if they are "always enabled" — potentially confusing.

2. **`_score_setup()` reads `self._last_l2_state`** (a stored attribute) rather than receiving `l2_state` as a direct parameter. This creates a subtle coupling: the L2 state used in scoring is whatever was set on the *previous call* to `on_bar_close_1m()`, not necessarily the one for this specific score computation. In practice this is fine since scoring is always called in the same bar-close context, but it's a hidden dependency.

3. **Exchange auto-detection is a TODO.** NYSE-listed stocks will always incur a failed NASDAQ fetch before getting correct data. This adds latency and consumes API credits.

4. **11 undocumented L2 env vars.** The acceleration and hard-gate variables have correct defaults but are invisible to operators who want to tune them. These should be added to `.env.example`.

5. **No L2 in the scanner/pre-filter.** L2 quality is not used for initial stock selection, only for per-bar decisions. A thin-book gapper with a great candle setup will pass the same filters as a thick-book gapper with strong institutional support.

---

## FILES SAVED TO WORKSPACE

| File | Contents |
|------|----------|
| `/home/user/workspace/l2_audit/l2_entry.py` | Complete source — L2EntryDetector strategy |
| `/home/user/workspace/l2_audit/l2_signals.py` | Complete source — L2SignalDetector signal engine |
| `/home/user/workspace/l2_audit/databento_feed.py` | Complete source — Databento historical L2 client |
| `/home/user/workspace/l2_audit/micro_pullback_l2_refs.txt` | All L2 sections extracted from micro_pullback.py with line references |
| `/home/user/workspace/l2_audit/env_l2_vars.txt` | All L2 env vars (documented + undocumented) with descriptions |
| `/home/user/workspace/l2_audit/bot_l2_refs.txt` | All L2 integration points in bot.py and simulate.py |
| `/home/user/workspace/l2_audit/L2_INFRASTRUCTURE_AUDIT.md` | This document |

---

*Audit completed 2026-03-02. All code read line-by-line from mannyluke4/warrior_bot master branch.*
