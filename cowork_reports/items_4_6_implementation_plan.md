# Implementation Plan: Items 4–6 from January 2025 Strategy Audit

**Generated:** 2026-03-22
**Scope:** Item 4 (Fix Selection Logic), Item 5 (Conviction Sizing), Item 6 (Halt-Through Logic)
**Source audit:** `cowork_reports/jan_2025_strategy_audit.md`
**Branch target:** Create feature branch per item; merge sequentially after megatest validation.

---

## Item 4: Fix Selection Logic

### The INM Problem

On January 21, the scanner ranked INM #1 with a score of 1.027 — the highest-ranked candidate by a wide margin (68K float, massive gap). The bot never traded it. Instead it traded VATE (#5, -$163), PTHS (#3, -$679), and LEDS (#4, -$281) — a combined -$1,082. Ross made +$12,000 on INM.

The root cause: the bot's entry criteria (impulse → pullback → confirmation → ARM in `MicroPullbackDetector`, and squeeze priming in `squeeze_detector.py`) didn't fire on INM's specific price action pattern. Lower-ranked stocks that did produce entry signals were traded instead. The ranking system correctly identified the opportunity but the entry logic couldn't capitalize on it.

### 4.1 Current Behavior

**Signal generation pipeline (live bot):**

1. `bot.py:filter_watchlist()` → calls `StockFilter.filter_watchlist()` → ranks candidates via `StockFilter.rank_stock()` → returns dict of `{symbol: StockInfo}` for the top candidates.
2. `bot.py:watchlist_thread()` → subscribes all filtered symbols to the data feed. **All symbols are treated equally** — there is no concept of "wait for #1 before trading #3."
3. `micro_pullback.py:on_bar_close_1m()` → runs the impulse/pullback/confirmation state machine on 1-minute bars. If the 3-bar cycle completes, it creates an `ArmedTrade` object.
4. `micro_pullback.py:on_trade_price()` → if price crosses `armed.trigger_high`, emits `ENTRY SIGNAL`.
5. `bot.py:on_trade()` → forwards `ENTRY SIGNAL` to `trade_manager.on_signal()`.
6. `trade_manager.on_signal()` → validates (daily stop, score gate, cooldown, quality gate, pillar gates, toxic filters) → sizes position via `size_qty()` → submits limit order.

**Backtesting pipeline (run_megatest.py):**

1. `load_and_rank()` → loads scanner JSON → filters (PM vol, gap, float, profile, rvol) → ranks via `rank_score()` → takes `TOP_N=5`.
2. `_run_config_day()` → runs `simulate.py` for each of the top 5 sequentially → collects all trades → sorts by entry time → enforces single-position gate (a trade can only start after the previous trade's exit time).
3. The single-position gate in `_run_config_day()` at line 477: `if t["time"] < position_end: continue` — this means whichever stock's FIRST trade fires earliest wins the slot. If #3's entry fires at 07:05 and #1's entry fires at 07:12, #3 gets the slot.

**The fundamental problem:** Neither the live bot nor the backtester has a mechanism to say "wait for the #1 ranked stock to generate a signal before committing capital to #3, #4, or #5." Every stock that passes the filter competes in a race to fire first, and rank is irrelevant.

### 4.2 Desired Behavior

The #1 ranked stock should have a grace period — a window of time during which only the top-N ranked stocks (e.g., top 1 or top 2) are eligible to generate entry signals. After the grace period expires without a signal from the top stocks, all stocks become eligible.

Additionally, entry criteria should be slightly relaxed for top-ranked stocks. If the #1 ranked stock has a score of 1.027 and a 68K float, it's very likely a good trade even if the pullback pattern isn't textbook-perfect. The quality gates should acknowledge rank.

### 4.3 Specific Files and Functions to Modify

**Live bot (`bot.py`):**

- `filter_watchlist()` (line 109): Already returns a dict `{symbol: StockInfo}`. The `rank_stock()` score is computed but only used for display (line 141). Need to: (a) store each symbol's rank and rank position in `_stock_info_cache`, and (b) pass rank data to `trade_manager`.
- `on_trade()` (line 533): Currently sends all `ENTRY SIGNAL` messages to `trade_manager.on_signal()` without rank awareness. Need to: either filter here based on rank + time window, or pass rank through so `trade_manager` can filter.

**Trade manager (`trade_manager.py`):**

- `on_signal()` (line 940): This is where the grace period check should live. Add logic: if current time is within `WB_RANK_GRACE_MINUTES` of market open (or session start), only accept signals from symbols with rank position <= `WB_RANK_GRACE_TOP_N`. After the grace window, accept all.
- `set_stock_info_cache()`: Already exists. Enhance to also store rank position for each symbol.
- Need a new field `_symbol_rank: Dict[str, int]` mapping symbol → rank position (1-indexed).

**Backtester (`run_megatest.py`):**

- `_run_config_day()` (line 417): Currently runs all 5 stocks in sequence, then sorts by time. Modify to: (a) add a configurable grace window, (b) during the grace window, only allow trades from the top-ranked stocks.
- Simplest approach: after sorting `all_trades_flat` by time, annotate each trade with its stock's rank position. In the selection loop, check `if time < grace_end and rank > WB_RANK_GRACE_TOP_N: continue`.

**Detector relaxation (`micro_pullback.py`):**

- `on_bar_close_1m()`: The impulse/pullback/confirmation cycle requires specific bar patterns. For top-ranked stocks, consider: reducing `max_pullback_bars` threshold, lowering `WB_WARMUP_BARS`, or reducing the MACD hard gate requirement.
- Best approach: pass a `rank_tier` flag into the detector. If `rank_tier == 1`, relax the pullback requirement (allow 1-bar direct entry after impulse, bypassing the 3-bar pullback cycle).
- The `entry_mode` env var already supports `"direct"` vs `"pullback"` — could make this per-symbol based on rank.

### 4.4 Env Var Gates

| Env Var | Default | Description |
|---------|---------|-------------|
| `WB_RANK_GRACE_ENABLED` | `0` | Master switch for rank-based grace period |
| `WB_RANK_GRACE_MINUTES` | `10` | Minutes after session start where only top-N stocks can trade |
| `WB_RANK_GRACE_TOP_N` | `2` | How many top-ranked stocks are eligible during grace period |
| `WB_RANK_RELAX_ENTRY_TOP_N` | `1` | Top-N stocks get relaxed entry criteria (direct entry mode) |
| `WB_RANK_RELAX_WARMUP_BARS` | `3` | Reduced warmup bars for top-ranked stocks (vs default 5) |

### 4.5 Risks and Edge Cases

- **Grace period too long:** If set to 30 minutes, the bot could miss early entries on #3/#4 that would have been profitable. INM was an exceptional case; most days the best trade could come from any rank position.
- **Relaxed entry = worse entries:** Lowering the bar for #1 could produce more false entries. The Jan 14 AIFF example shows the standard entry criteria working well — relaxing them on that day would have been unnecessary. Mitigation: only relax for stocks with rank score > 1.0 (very high conviction).
- **Stale rank after rescan:** If the 07:30 rescan changes the ranking, the grace period logic must update. Need to refresh `_symbol_rank` on each rescan.
- **Single stock monopolizes entries:** If #1 fires repeatedly during the grace period, it could consume all daily trade slots. Mitigation: the existing `WB_MAX_ENTRIES_PER_SYMBOL=2` and `WB_SYMBOL_COOLDOWN_MIN=10` still apply.

### 4.6 How to Test/Validate

1. **Backtest Jan 21 specifically:** Run `simulate.py INM 2025-01-21 07:00 12:00 --ticks` with relaxed entry criteria. Does INM produce an entry? If yes, what's the P&L? Compare to the -$1,082 the bot lost trading VATE/PTHS/LEDS.
2. **Full megatest with grace period ON vs OFF:** Run `run_megatest.py all_three` twice — once with `WB_RANK_GRACE_ENABLED=1` and once without. Compare net P&L, win rate, and specifically check whether the grace period blocks profitable trades on lower-ranked stocks.
3. **Scan the selection_log in megatest state:** For each day, identify the #1 ranked stock and check if it generated any trades. This gives the "INM problem frequency" — how often the top stock is missed.
4. **Live paper test:** Run for 1 week with grace period enabled at conservative settings (5 minutes, top 1 only). Compare to the baseline.

### 4.7 Estimated Complexity

**Medium.** The grace period logic is straightforward (time check + rank lookup). The entry relaxation is trickier because it touches the detector's state machine and needs to be parameterized per-symbol. Backtester changes require plumbing rank position through `run_sim()` and into `simulate.py`.

---

## Item 5: Conviction Sizing

### The Problem

The bot uses flat notional sizing regardless of setup quality. `WB_RISK_DOLLARS=1000` and `WB_MAX_NOTIONAL=50000` are constants. On YIBO (Jan 28), the 46x P&L gap between Ross (+$5,724) and the bot (+$125) was approximately 19x from sizing and the rest from exit management. Ross sized ALUR at approximately $138K notional — 7x the bot's max.

Even with perfect exits, flat sizing means the bot treats a 1.027-ranked stock identically to a 0.597-ranked stock. This is fundamentally anti-Ross — he sizes aggressively on A+ setups and modestly on B setups.

### 5.1 Current Behavior

**Position sizing code path (live bot):**

1. `trade_manager.on_signal()` calls `size_qty(plan.entry, plan.r)` at line 1006.
2. `size_qty()` (line 581) computes:
   - `effective_risk = _get_effective_risk()` — returns `self.risk_dollars` (from `WB_RISK_DOLLARS`, default 1000), potentially reduced by warmup sizing.
   - `qty_risk = floor(effective_risk / r)` — shares based on risk per share.
   - `qty_notional = floor(max_notional / entry)` — shares capped by `WB_MAX_NOTIONAL` (50000).
   - `qty_cap = min(qty_risk, qty_notional, max_shares)` — take the most restrictive.
   - Then checks Alpaca buying power for a further cap.
3. Additional modifiers applied in `on_signal()`:
   - **Mid-float cap** (line 1002): if `float > 5.0M`, qty is capped to `floor(250 / r)`. This is a risk reduction for mid-float stocks.
   - **Toxic half-risk** (line 1015): if toxic filter fires, qty halved.
   - **Warmup sizing** (line 922): pre-graduation, risk is `risk_dollars * (warmup_size_pct / 100)` = 25% of base.

**Backtester sizing (`run_megatest.py`):**

1. `risk_a = max(int(eq_a * RISK_PCT), 50)` — 2.5% of equity, floor $50 (line 365).
2. Per-stock risk: `stock_risk = min(risk, 250) if float_m > 5.0 else risk` (line 436) — mid-float stocks capped at $250 risk.
3. This `stock_risk` is passed to `run_sim()` → `simulate.py` → used as the `--risk` argument.

**Key insight:** The `ArmedTrade` dataclass already has a `size_mult` field (line 36 in `micro_pullback.py`), but it's never set to anything other than 1.0 and is never read by `trade_manager.py`. This is an unused hook that was designed for exactly this purpose.

### 5.2 Desired Behavior

Position size should scale with the scanner rank score. A stock ranked 1.027 (INM) should get 2–3x the risk dollars of a stock ranked 0.5 (bottom of the list). The scaling should be smooth and bounded.

Proposed formula:
```
conviction_mult = clamp(rank_score / WB_CONVICTION_BASE_SCORE, WB_CONVICTION_MIN_MULT, WB_CONVICTION_MAX_MULT)
effective_risk = risk_dollars * conviction_mult
```

With defaults: base_score=0.6, min_mult=0.5, max_mult=2.5.

A 1.027-ranked stock would get: `clamp(1.027 / 0.6, 0.5, 2.5) = clamp(1.71, 0.5, 2.5) = 1.71x` risk.
A 0.5-ranked stock would get: `clamp(0.5 / 0.6, 0.5, 2.5) = clamp(0.83, 0.5, 2.5) = 0.83x` risk.

Additionally, consider extra factors that compound with rank:
- **Gap%:** Stocks with gap > 100% (like ALUR at 181%) could get a gap bonus.
- **Float:** Ultra-low float (< 1M) could get a float bonus — these are the stocks that move the most.
- **PM volume:** High PM volume (> 500K) signals institutional interest.

### 5.3 Specific Files and Functions to Modify

**Trade manager (`trade_manager.py`):**

- `on_signal()` (line 940): After retrieving `plan` and `info`, compute `conviction_mult` from the symbol's rank score. Apply it to `effective_risk` before calling `size_qty()`.
- `size_qty()` (line 581): Either accept an override `effective_risk` parameter, or set `self._current_conviction_mult` before the call and read it in `_get_effective_risk()`.
- **Preferred approach:** Add `conviction_mult` parameter to `size_qty()`. Cleaner than state mutation.
- `_get_effective_risk()` (line 922): Stays as-is for warmup logic. Conviction mult is applied on top.
- **MAX_NOTIONAL interaction:** `WB_MAX_NOTIONAL=50000` is currently a hard cap. For conviction sizing to work on A+ setups, this cap needs to scale too: `effective_max_notional = max_notional * conviction_mult`. Otherwise a 2x risk multiplier hits the notional ceiling on a $10 stock (50K / $10 = 5000 shares is the same regardless of conviction).
- New method: `_compute_conviction_mult(symbol: str) -> float` that reads rank score from `_stock_info_cache` and applies the formula.

**Backtester (`run_megatest.py`):**

- `_run_config_day()` (line 417): Before calling `run_sim()` for each candidate, compute the conviction multiplier from `rank_score(c)`. Pass it as a scaled `stock_risk`.
- `run_sim()` (line 210): Already accepts `risk` parameter. Pass `int(stock_risk * conviction_mult)`.
- Also pass a scaled `max_notional` via env var override: `env["WB_MAX_NOTIONAL"] = str(int(MAX_NOTIONAL * conviction_mult))`.

**Detector (`micro_pullback.py`):**

- The `ArmedTrade.size_mult` field (line 36) is already there. It could be set by the arming logic based on externally provided rank data, and then read by `trade_manager.on_signal()`. However, this requires the detector to know about rank, which is a layering violation. Better to keep sizing in `trade_manager` and use the `_stock_info_cache`.

### 5.4 Env Var Gates

| Env Var | Default | Description |
|---------|---------|-------------|
| `WB_CONVICTION_SIZING_ENABLED` | `0` | Master switch |
| `WB_CONVICTION_BASE_SCORE` | `0.6` | Rank score that gets 1.0x sizing |
| `WB_CONVICTION_MIN_MULT` | `0.5` | Floor multiplier (worst-ranked stocks) |
| `WB_CONVICTION_MAX_MULT` | `2.5` | Ceiling multiplier (best-ranked stocks) |
| `WB_CONVICTION_SCALE_NOTIONAL` | `1` | Also scale MAX_NOTIONAL with conviction (0=cap stays flat) |
| `WB_CONVICTION_GAP_BONUS_PCT` | `100` | Gap% above this adds +0.25x (0=disabled) |
| `WB_CONVICTION_FLOAT_BONUS_M` | `1.0` | Float below this adds +0.25x (0=disabled) |

### 5.5 Risks and Edge Cases

- **Oversizing on losers:** If the #1 ranked stock is 2.5x sized and hits `max_loss_hit`, the loss is 2.5x larger too. The PTHS example from Jan 21 (-$679 at normal sizing) would have been -$1,698 at 2.5x. Mitigation: conviction sizing only applies to stocks meeting a minimum rank score threshold (e.g., > 0.7). Below that, use 1.0x.
- **MAX_NOTIONAL interaction:** At 2.5x conviction, `max_notional` becomes $125K. On a $3 stock, that's 41,666 shares. Alpaca may reject orders this large on thin stocks due to buying power limits. Mitigation: buying power check in `size_qty()` already exists (line 596). Also add a hard share cap at `WB_MAX_SHARES`.
- **Daily loss amplification:** If conviction sizing leads to a larger first trade and it loses, the daily loss limit ($3K) is hit faster. This could prevent the bot from taking the recovery trade. Mitigation: the existing warmup sizing (`WB_WARMUP_SIZE_PCT=25`) already gates the first trade at 25% risk. Conviction mult applies on top, so the first trade would be `25% * 2.5x = 62.5%` of base risk — still below full size.
- **Backtester divergence:** Must ensure live bot and backtester use identical conviction math to avoid train/test skew. Extract into a shared function in a utils module.

### 5.6 How to Test/Validate

1. **Replay ALUR Jan 24:** With conviction sizing, ALUR (rank ~1.0+) would get ~1.7x risk. At $1000 base risk and R=$0.36, that's `floor(1700 / 0.36) = 4722 shares` vs current `floor(1000 / 0.36) = 2777`. Even with the early exit at $8.40, P&L goes from +$506 to ~$860. Still tiny vs Ross's $85K, but the direction is correct.
2. **Full megatest with conviction ON vs OFF:** The critical metric is **risk-adjusted return** — not just total P&L. If conviction sizing increases average win AND average loss proportionally, net improvement is zero. Need to see a disproportionate increase in wins (because high-ranked stocks win more often).
3. **Backtest the conviction multiplier distribution:** For each megatest day, compute what the conviction_mult would have been for each traded stock. Histogram: how many trades get > 1.5x? How many get < 0.8x? If most trades cluster around 1.0x, the feature has low impact.
4. **Max daily drawdown analysis:** With conviction sizing, does any single day exceed -$5K? -$10K? The daily loss limit ($3K) should still protect, but verify.

### 5.7 Estimated Complexity

**Low-Medium.** The formula is trivial. The main work is plumbing the rank score through to `size_qty()` in both the live bot and backtester, and ensuring the `MAX_NOTIONAL` scaling interacts correctly with buying power and share limits. No state machine changes needed.

---

## Item 6: Halt-Through Logic

### The Problem

On January 24, ALUR halted up multiple times on the way from $8 to $20. Ross held through every halt and captured the full $12/share move. The bot's first trade exited at $8.40 via `sq_target_hit` (before halts were relevant), but the re-entry trades at $10.04 were clipped by `sq_para_trail_exit` — likely because the violent price action around halt resumptions triggered the trailing stop.

More broadly: during a trading halt, no price updates arrive. When the stock resumes, the first prints can be significantly above or below the halt price. The bot's exit logic — which evaluates stops/trails on every tick via `_manage_exits()` — is not halt-aware. It doesn't know the difference between "price dropped because of a selloff" and "price gapped on halt resumption."

### 6.1 Current Behavior

**What happens during a halt (live bot):**

1. **Data feed goes silent:** No trade prints arrive for the symbol. `on_trade()` stops being called. The `stale_price_monitor()` in `bot.py` (line 296) will fire warnings after `WB_STALE_PRICE_SEC=5` seconds.
2. **Exit logic freezes:** `_manage_exits()` is only called from `on_price()` and `on_quote()`. With no new data, no exit evaluation happens. **The stop doesn't fire during the halt** — but it doesn't protect either.
3. **Halt resumption:** When trading resumes, the first tick arrives. If the stock resumes above the entry, great — `_manage_exits()` updates peak and trail. If it resumes below the stop, the stop fires immediately on the first tick. If it resumes with volatile prints, the parabolic trail can fire on the first dip.
4. **Bail timer ticks:** The bail timer (`WB_BAIL_TIMER_ENABLED=1`, 5 minutes) uses wall-clock time. During a halt, the bail timer keeps counting. A 5-minute halt could cause the bot to bail immediately on resumption if the trade was already 3 minutes old. **This is a concrete bug.**
5. **Bar builders:** The `TradeBarBuilder` accumulates bars based on trade prints. During a halt, the current bar stays open indefinitely. On resumption, the first bar will have an anomalously long duration, which could produce false signals.

**Existing halt-related code:**

The `MicroPullbackDetector` already has a post-halt sizing override system:
- `halt_sizing_enabled` (line 129): reads `WB_HALT_SIZING_OVERRIDE=1`.
- `_halt_adjusted_stop()` (line 225): If a halt is detected (bar range > `halt_range_multiplier * avg_range`), tightens the stop for new entries to `entry - (halt_stop_atr_mult * avg_range)`.
- `_halt_active_bars` (line 134): Tracks how many bars the halt flag persists.
- This code handles **entries after halts** — it does NOT handle **positions held through halts**.

In `simulate.py`:
- `_squeeze_tick_exits()` (line 483): Trail stop at line 544-556 fires on every tick. No halt awareness. On halt resumption, if the first tick is below `peak - (trail_r * r)`, the trail fires.
- `_manage_exits()` in `trade_manager.py` (line 2526): Same issue in live bot. Hard stop and trail evaluated on every tick.

### 6.2 Desired Behavior

When a stock halts UP while the bot holds a **winning** position:

1. **Detect the halt:** When no price updates arrive for > N seconds (configurable, e.g., 30s), and the last known price was above entry + 1R, flag the position as "in halt."
2. **Suspend exit logic:** While the halt flag is active, do NOT evaluate trailing stops, parabolic trails, bail timer, or pattern exits (TW, BE). Only the hard stop should remain active as a disaster safety net.
3. **Freeze the bail timer:** Pause the bail timer during halt. Resume counting after trade resumes.
4. **Grace period on resumption:** When the first tick arrives after a halt, do NOT immediately evaluate exit logic. Allow a `WB_HALT_RESUME_GRACE_SEC` window (e.g., 10 seconds) for the price to stabilize before resuming normal exit evaluation. Update `peak` from the resumption price if it's a new high.
5. **Only apply to winning positions halted UP:** If the stock halts while the bot is underwater, normal exit logic should resume immediately on the halt-resumption tick. Holding through a halt on a losing position is not the desired behavior.
6. **Log everything:** Halt detection, suspension, resumption, grace period — all must be logged for post-trade analysis.

### 6.3 Specific Files and Functions to Modify

**Trade manager (`trade_manager.py`):**

- New fields on `OpenTrade` dataclass (line 131):
  - `halt_detected: bool = False` — is this position currently in a detected halt?
  - `halt_detected_at: datetime = None` — when was the halt detected?
  - `halt_resume_grace_until: datetime = None` — when does the post-resume grace period end?
  - `last_price_update_at: datetime = None` — timestamp of the last price update for this symbol.

- `on_price()` (line 2082): Before calling `_manage_exits()`:
  1. Update `t.last_price_update_at = now`.
  2. If `t.halt_detected` is True and a new price arrives: clear the halt flag, set `halt_resume_grace_until = now + WB_HALT_RESUME_GRACE_SEC`. Log "halt resumed."
  3. If the first post-halt tick is above entry, update `t.peak` from this price.

- `_manage_exits()` (line 2526): At the top, add halt checks:
  1. If `t.halt_detected`: skip all exit logic (return early). Only keep the max_loss_hit safety net active.
  2. If `t.halt_resume_grace_until` is set and `now < halt_resume_grace_until`: skip trail/pattern exits but allow hard stop. This prevents the first volatile tick from triggering a trail exit.

- New method `_check_halt_detection()`: Called periodically (from the `pending_heartbeat` loop or a new halt monitor thread). For each open position:
  1. If `now - t.last_price_update_at > WB_HALT_DETECT_SEC` (e.g., 30s),
  2. AND the position is in profit (last price > entry + `WB_HALT_MIN_PROFIT_R` * R),
  3. THEN set `t.halt_detected = True`, `t.halt_detected_at = now`.
  4. Log "halt detected for {symbol}, position is profitable, suspending exits."

- **Bail timer interaction** (line 2599): Add check: if `t.halt_detected` or `t.halt_resume_grace_until > now`, skip the bail timer evaluation.

**Bot.py:**

- `stale_price_monitor()` (line 296): When a halt is detected by `trade_manager`, suppress the stale price warnings for that symbol (they're noise during a known halt). Add a check: `if trade_manager.is_halt_detected(symbol): continue`.

- `pending_heartbeat()` (line 510): Add a call to `trade_manager.check_halt_detection()` on each cycle. Since this runs every 0.5 seconds, it will detect halts within ~1 second of the data going silent.

**Simulate.py (backtester):**

- `_squeeze_tick_exits()` (line 483): Add halt simulation. In the tick replay loop, track the time gap between consecutive ticks. If the gap exceeds `WB_HALT_DETECT_SEC` AND the position is profitable:
  1. Skip trail exit evaluation for the first `WB_HALT_RESUME_GRACE_SEC` worth of ticks after the gap.
  2. Update peak from the resumption price.
  3. Log "simulated halt through" for analysis.

- The tick replay in `simulate.py` already has timestamps. Add: `if (current_tick_time - prev_tick_time).total_seconds() > halt_detect_sec and position_profitable: set halt_grace_until = current_tick_time + grace_sec`.

**Micro pullback detector (`micro_pullback.py`):**

- The existing `_halt_active_bars` / `_halt_adjusted_stop()` logic (lines 128-166, 225-237) is for **post-halt entries** and should be left intact. The new halt-through logic is for **positions already held** and lives in `trade_manager.py`.
- No changes needed here, but ensure the halt detection in the detector doesn't interfere with the halt-through logic in the trade manager. They serve different purposes and should be independent.

### 6.4 Env Var Gates

| Env Var | Default | Description |
|---------|---------|-------------|
| `WB_HALT_THROUGH_ENABLED` | `0` | Master switch for halt-through logic |
| `WB_HALT_DETECT_SEC` | `30` | Seconds of silence before declaring a halt |
| `WB_HALT_MIN_PROFIT_R` | `1.0` | Minimum R-multiple of profit to hold through halt (only hold winning positions) |
| `WB_HALT_RESUME_GRACE_SEC` | `10` | Seconds after resumption before trail exits re-engage |
| `WB_HALT_MAX_DURATION_SEC` | `600` | Safety: if halt lasts > 10 minutes, re-enable exits (prevents infinite hold on a pause that isn't a circuit breaker) |
| `WB_HALT_FREEZE_BAIL_TIMER` | `1` | Freeze bail timer during halt (1=yes, 0=no) |

### 6.5 Risks and Edge Cases

- **False halt detection:** If the data feed drops trades for 30 seconds due to a network glitch (not a real halt), the bot could suspend exits during a genuine selloff. Mitigation: (a) check quote feed too — during a real halt, both trades AND quotes go silent; (b) require the position to be in profit before suspending exits; (c) set a max halt duration after which exits re-engage.
- **Halt DOWN:** A stock can halt on a circuit breaker down too. If the bot is long and the stock halts down, the position is underwater and the halt-through logic should NOT suspend exits. The `WB_HALT_MIN_PROFIT_R` gate handles this — it only suspends exits when the position is in meaningful profit.
- **Halt resume with a gap down:** The stock halts at $15 (bot is in profit at entry $10), then resumes at $9 (massive gap down). If exits are suspended during the grace period, the bot holds a now-losing position for `WB_HALT_RESUME_GRACE_SEC` seconds. Mitigation: the hard stop and max_loss_hit safety net remain active even during the grace period. Only trail/pattern exits are suspended.
- **Multiple halts:** A stock like ALUR halts multiple times. Each halt detection/resumption cycle must be independent. The logic should handle: halt → resume → halt again → resume. State resets cleanly on each resumption.
- **Alpaca order behavior during halts:** If the bot submitted a limit sell order before the halt, Alpaca will hold the order and attempt to fill on resumption. This could cause an unintended exit. Mitigation: when a halt is detected, cancel any pending exit orders for the symbol. Re-evaluate after resumption.
- **Backtester accuracy:** Simulating halts from tick data requires detecting large time gaps. The tick replay in `simulate.py` has timestamps, but the time resolution depends on the data source. Databento tick data preserves halt gaps; Alpaca historical bars may not. Need to verify that halt gaps are present in the tick cache.

### 6.6 How to Test/Validate

1. **Replay ALUR Jan 24 with halt-through ON:** The tick data for ALUR should show clear gaps where halts occurred (no prints for 5+ minutes). With halt-through enabled, the bot should hold through each halt and capture more of the move. Compare P&L: current (+$586 across 3 trades) vs halt-through (potentially +$2,000–5,000 depending on how many halts are held).
2. **Identify all halt situations in the megatest period:** Scan the tick cache for symbols where price gaps > 30 seconds exist during market hours. For each, check if the bot had a position. This gives the "halt frequency" — how often the feature would activate.
3. **Worst-case scenario test:** Find instances where a stock halted UP and then gapped down on resumption. With halt-through logic, would the bot have taken a larger loss than without it? If yes, ensure the hard stop safety net limits the damage.
4. **Live paper test with intentional monitoring:** Run the live bot during a session where halts are likely (earnings season, high-volatility mornings). Monitor the halt detection logs in real time. Verify that: (a) halts are detected within 30 seconds, (b) exits are suspended, (c) resumption is handled cleanly.
5. **Stale price interaction test:** Verify that `stale_price_monitor()` doesn't spam warnings during a detected halt. The log should show one "halt detected" event followed by silence until "halt resumed."

### 6.7 Estimated Complexity

**Medium-High.** The core logic (detect halt, suspend exits, resume with grace) is conceptually simple but touches multiple systems: `trade_manager._manage_exits()`, `on_price()`, bail timer, stale monitor, and the backtester's tick replay. The edge cases (false detection, halt-down, cancel pending exits) add significant testing surface. The backtester simulation of halts from tick gaps requires careful timestamp handling.

---

## Implementation Sequence

| Order | Item | Depends On | Rationale |
|-------|------|-----------|-----------|
| 1 | Item 4: Fix Selection Logic | None | Highest signal-to-noise: the INM problem is the clearest "bot did the wrong thing" case. Low risk, high diagnostic value. |
| 2 | Item 5: Conviction Sizing | Item 4 (rank data plumbing) | Conviction sizing needs rank scores flowing into `trade_manager`. Item 4 builds the plumbing for rank-awareness. |
| 3 | Item 6: Halt-Through Logic | None (independent) | Highest complexity, but also highest potential payoff for A+ runner trades. Should be developed and backtested in parallel with items 4–5 but merged last. |

### Megatest Validation Protocol

For each item, before merging:

1. Run `run_megatest.py all_three` with the feature ON and OFF.
2. Compare: total P&L, win rate, max drawdown, profit factor.
3. Generate a diff report showing which specific trades changed.
4. Specifically check January 2025 for: (a) INM being traded on Jan 21, (b) ALUR capturing more on Jan 24, (c) No new catastrophic losses introduced.
5. Run `run_megatest.py sq_only` as a secondary validation (squeeze trades are the highest-value target).

### Shared Infrastructure Needed

Before implementing any item, create:

1. **`_symbol_rank` dict in `trade_manager`:** Maps `symbol → (rank_position, rank_score)`. Populated from `_stock_info_cache` whenever `set_stock_info_cache()` is called. Both Item 4 and Item 5 need this.
2. **`rank_score()` utility function:** Currently defined in `run_megatest.py` (line 130) and separately in `stock_filter.py`. Extract to a shared `utils.py` so both live bot and backtester use identical ranking math. This prevents train/test divergence.
3. **Feature flag pattern:** All three items use the same pattern: master switch env var (default OFF) + tuning knobs. Ensure the env var naming is consistent (`WB_RANK_*`, `WB_CONVICTION_*`, `WB_HALT_THROUGH_*`).

---

*This plan is a blueprint for implementation. No code changes should be made without first backtesting each item independently and validating against the January 2025 data.*
