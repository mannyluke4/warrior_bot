# P0 Stack — Implementation Report

**Date**: 2026-05-22
**Branch**: `v2-ibkr-migration`
**Source directive**: `cowork_reports/2026-05-22_p0_go_live_stack_directive.md`

All three P0 items shipped in commit (see below). Will observe in tomorrow's session.

---

## Item 1 — Alpaca-aware limit adapter

**Main bot** (`bot_v3_hybrid.py`):
- **Entry path** (long, around line 3181): replaced `limit_price = round(basis + initial_slip, 2)` with `compute_alpaca_aware_limit(symbol, basis, "BUY")` then `max(aware_limit, base_limit)`. Preserves the existing dynamic slip floor (so cheap stocks don't get tightened below their natural buffer). Recomputes `initial_slip` from the final limit for accurate latency-record logging.
- **Exit path #1** (line ~750, normal exit handler): replaced `_exit_limit_price(ref_price, "SELL")` with `min(aware_limit, base_limit)` — tightens toward Alpaca's bid when sensible, falls back to existing buffer otherwise.
- **Exit path #2** (line ~4651, BOX strategy exit): same pattern.
- **Env**: added `WB_ALPACA_AWARE_LIMITS=1` to `.env`.

**Sub-bot** (`move_strike_subbot.py`):
- Copied the helper as `MoveStrikeSubBot._compute_alpaca_aware_limit()` (sub-bot needs its own data client; no shared module yet).
- Added `StockHistoricalDataClient` initialization alongside the existing `TradingClient` in `_init_alpaca()`. Graceful None-fallback if init fails (helper returns base limit).
- **Entry** (`_open_position_with_tag`, line ~599): widens limit to `max(base, aware)`.
- **Exit** (`_close_position`, line ~640): tightens limit to `min(base, aware)`.

**5% divergence guard preserved** in both copies — falls back to base limit when Alpaca's quote is wildly different from the IBKR-derived signal (likely stale data).

---

## Item 2 — Sub-bot P&L from actual fills

**Problem**: `daily_pnl += (ref_price - p.entry) * p.qty` was the bot lying to itself by $945 today on 4 MTVA trades.

**Fix**:
- New `SubPosition` fields: `fill_entry_price` and `fill_entry_qty` (populated after submit).
- New `_wait_for_fill(order_id, timeout=15)` helper in sub-bot — mirrors main bot's `bot_v3_hybrid.py:1195` pattern. Polls Alpaca every 500ms for filled/canceled/expired/rejected. Cancels on timeout, does one final status check.
- **Entry path**: after `submit_order` returns, calls `_wait_for_fill`. On success, stores actual `filled_avg_price` and `filled_qty` on the position. On failure, abandons the trade (no orphan exit attempt later).
- **Partial fill handling**: if the entry fills less than requested, the position's `qty` is shrunk to the filled amount. The exit will then sell exactly what we own.
- **Exit path**: also calls `_wait_for_fill`. Computes `daily_pnl` as `(exit_fill - entry_fill) × filled_qty` instead of the old anomaly→ref math. Tagged "real" when both fills present, "approx" when falling back (logged for visibility).

Tomorrow's session should show sub-bot's `daily_pnl` matching Alpaca account P&L within rounding error.

---

## Item 3 — Sub-bot tick cache seeding

**Problem**: every sub-bot restart wipes all detector state. On a watchdog crash mid-session (two of them on 5/22 alone), the sub-bot reconnects to a fresh world. Sim with full 04:00→ history sees a completely different setup landscape than live.

**Fix**: new `_seed_symbol_from_cache(symbol)` method on `MoveStrikeSubBot`:
- Triggered from `_ensure_symbol()` on first encounter of any symbol.
- Reads `tick_cache/<today>/<symbol>.json.gz` (the file the main bot writes continuously).
- Replays each tick through `self.bar_builder.on_trade(symbol, price, size, ts)` so bars + VWAP rebuild as they would in a live session.
- Stops at `now_utc` — doesn't replay into the future (live ticks will cover from there).
- Calls `det.begin_seed() / end_seed()` if the detector supports it (squeeze v2; v1 fallback is silent — bar rebuild only).
- Logs `SEED <symbol> replayed N ticks from cache`.
- Gated by `WB_SUBBOT_SEED_FROM_CACHE` (default `1`).

**Edge case**: if the cache file is truncated (the PCLA 2026-05-21 incident is task #25), we replay whatever's there. Partial seed > no seed.

---

## What this should change tomorrow

- Fewer chase-cap timeouts on entries (Alpaca-aware limit catches the bid/ask reality)
- Sub-bot's reported P&L matches Alpaca dashboard within $50 (real-fill accounting)
- After any mid-day restart, sub-bot detector state reflects the full morning's tick history, not zero
- Cleaner sim/live comparison since the live bot now starts with same context the sim has

---

## What's NOT done (deferred to follow-up)

- **Tick-cache EOD truncation fix** (task #25) — orthogonal to today's stack
- **Sim fill model audit** (part of task #26) — the live side is now honest; need to also un-rig the sim side before the +$2,498 baseline number can be trusted
- **Watchdog freeze investigation** (P1 from directive's flag) — two crashes today, needs root cause
- **X01 exits research** (`cowork_reports/2026-05-21_x01_exits_research_directive.md`) — next stack after this one

---

## Tasks closed by this commit

- #29: P0 wire `compute_alpaca_aware_limit()`
- #26 (partial): sub-bot P&L from real fills (sim-side audit still open)
- #27: P0 sub-bot tick_cache seeding

## Tasks still open

- #25: P0 tick-cache truncation
- #26 (sim-side): simulate.py fill model audit
- #28: comprehensive sim/live parity audit (Cowork research, not CC)

---

## Files touched

- `bot_v3_hybrid.py` — entry path, exit path #1, exit path #2 wired through `compute_alpaca_aware_limit()`
- `move_strike_subbot.py` — added helper, data client, `_wait_for_fill`, real-fill P&L, `_seed_symbol_from_cache`
- `.env` — `WB_ALPACA_AWARE_LIMITS=1`

No changes to `simulate.py`, `daily_run_v3.sh`, or any other file. Tomorrow's cron picks all of this up automatically.
