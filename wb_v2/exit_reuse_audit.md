# WB v2 — Exit Primitive Reuse Audit

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Status:** Read-only audit. Setup A code is NOT modified by WB v2.
**Directive:** `DIRECTIVE_2026-05-18_WB_V2_STAGE_0.md` deliverable 6.

---

## Scope and framing

Manny's directive is unambiguous: *"the exit strategy we were already using
was working wonderfully. The bot is good at detecting exits."* WB v2 does
not author new exit logic. It calls the squeeze bot's existing exit primitives
from a separate WB v2 entry handler. This document inventories every primitive
WB v2 plans to invoke, with file:line references, parameter shapes, and a
reuse plan that distinguishes direct calls from thin adapters.

There are two parallel implementations of the squeeze exit cascade in the
codebase, both READ-ONLY for WB v2:

1. `bot_v3_hybrid.py::_squeeze_exit` (the live IBKR bot, deployed) — operates
   on a dict-shaped `state.open_position` and calls `exit_trade()` for order
   placement.
2. `trade_manager.py::PaperTradeManager._squeeze_manage_exits` (the Alpaca
   paper / sub-bot path) — operates on the `OpenTrade` dataclass and calls
   `self._exit()` for order placement.

Both implement the same V1 cascade with the same env-var knobs. WB v2 will
target the **live bot path** (`bot_v3_hybrid.py`) because that's the canonical
production path; the Alpaca-paper variant in `trade_manager.py` is the same
logic in a different host shell and can be reached via the same adapter
pattern if/when WB v2 also runs in the Alpaca paper account.

The session-end force-flat (`force_exit.py`) is **shared infrastructure**:
both bot paths import it, and it is broker-agnostic by design.

---

## Primitive 1 — `force_exit.py` (session-end force-flat)

**File:** `force_exit.py:64-79` (`should_force_exit_now`),
`force_exit.py:104-193` (`force_exit_position`).

**Purpose.** At T-minus-`WB_SESSION_END_LEAD_MIN` minutes before
`WB_SESSION_END_TIME_ET` (defaults: 5 min before 20:00 ET, i.e. 19:55 ET),
flatten every open position via aggressive SELL LIMIT with chase-down ladder.
Honors the project-wide no-market-orders rule (memory:
`feedback_no_market_orders.md`).

**Inputs.** `should_force_exit_now()` takes nothing and is a once-per-day
latched poll (safe to call every tick). `force_exit_position()` takes
`(broker, symbol, qty, reference_price, log_prefix="")` where `broker` is
any object exposing `submit_limit(symbol, qty, side, limit_price,
extended_hours=True)`, `get_latest_quote(symbol)`, `get_order_status(order_id)`,
and `cancel_order(order_id)`. The squeeze bot's `state.broker` already
implements this interface; WB v2 will use the same broker handle.

**Outputs.** `force_exit_position` returns a dict:
`{"filled": bool, "fill_price": float|None, "fill_qty": int,
"attempts": int, "reason": str}`. **Side effects:** submits up to
`WB_SESSION_END_MAX_RETRIES` (default 3) SELL LIMIT orders with widening
offsets (`WB_SESSION_END_FIRST_OFFSET_PCT` 1.0%, step
`WB_SESSION_END_RETRY_STEP_PCT` 1.0%), polls each for up to
`WB_SESSION_END_FILL_TIMEOUT_SEC` (default 10s), cancels and retries on
timeout.

**Reusability for WB v2.** **Direct call.** This module is already broker-
generic and position-shape-agnostic — it takes raw `(symbol, qty, ref_price)`
tuples. The existing live-bot integration at
`bot_v3_hybrid.py:1980-2032` already iterates two separate dicts
(`state.open_position` for squeeze, `state.wb_positions` for WB) and
fires the same chain over each. WB v2 inherits the pattern by adding a
third loop over `state.wb_v2_positions` (or whatever dict WB v2 chooses to
maintain) inside `_maybe_session_end_force_exit()`.

**Constraints.** The once-per-day latch is **process-wide**, not
per-strategy. That's correct: a process should fire the flatten chain once
per session, and the strategy loops within that single fire are independent.
WB v2 must NOT call `should_force_exit_now()` separately — it must rely on
the existing live-bot tick loop that already polls it.

---

## Primitive 2 — Squeeze exit cascade (`_squeeze_exit`)

**File:** `bot_v3_hybrid.py:3299-3376` (live path). Mirror implementation:
`trade_manager.py:2907-2974` (`_squeeze_manage_exits`). Detector-internal
version: `squeeze_detector_v2.py:444-526` (`check_exit`) — used by `simulate.py`.

**Purpose.** Self-contained mechanical exit ladder. Six stages in priority
order, all evaluated on every tick:

1. **Dollar loss cap** (`bot_v3_hybrid.py:3306-3311`). If `(entry - price) *
   qty >= SQ_MAX_LOSS_DOLLARS` (default $500), exit full position with
   reason `sq_dollar_loss_cap`. Catches gap-throughs where the per-share
   stop would otherwise blow up at scale.
2. **Hard stop** (`bot_v3_hybrid.py:3313-3316`). If `price <= stop`, exit
   full position with reason `sq_stop_hit`.
3. **Tiered max-loss** (in `trade_manager.py:2924-2936` only — `bot_v3_hybrid`
   does not have this stage; see "Asymmetry" note below). Scales the
   max-loss-R multiplier by float bucket: `_max_loss_r_ultra_low` for
   `float_m < _max_loss_r_float_thresh_low`, `_max_loss_r_low` between the
   two thresholds, base `max_loss_r` above.
4. **Pre-target trail** (`bot_v3_hybrid.py:3319-3327`). If `not tp_hit` and
   `price <= peak - trail_r * r`, exit full position. `trail_r` =
   `SQ_PARA_TRAIL_R` (1.0R, tighter) when `pos["is_parabolic"]` else
   `SQ_TRAIL_R` (1.5R). Reason: `sq_para_trail_exit` or `sq_trail_exit`.
5. **2R target hit** (`bot_v3_hybrid.py:3329-3367`). If `price >= entry +
   SQ_TARGET_R * r` (2.0R default), set `tp_hit = True`, scale partial
   exit by `SQ_CORE_PCT` (75% default — Manny's 2026-04-08 X01 tuning
   raised this to 90%). Submit partial exit with reason `sq_target_hit`,
   leave remainder as runner, shift `runner_stop` to `max(stop, entry +
   0.01)` (BE-plus).
6. **Runner trail** (`bot_v3_hybrid.py:3369-3376`). After `tp_hit`, if
   `price <= max(runner_stop, peak - SQ_RUNNER_TRAIL_R * r)` (2.5R), exit
   remainder with reason `sq_runner_trail`.

**Inputs.** Three pieces of state per position:
- Static: `entry`, `stop`, `r` (= entry − stop), `qty`, `is_parabolic`.
- Dynamic: `peak` (monotonically updated by `manage_exit` at
  `bot_v3_hybrid.py:3274-3275`), `tp_hit`, `runner_stop` (set on target hit).
- Env knobs (all read once at module load): `WB_SQ_TARGET_R`,
  `WB_SQ_TRAIL_R`, `WB_SQ_PARA_TRAIL_R`, `WB_SQ_RUNNER_TRAIL_R`,
  `WB_SQ_MAX_LOSS_DOLLARS`, `WB_SQ_CORE_PCT`. (`bot_v3_hybrid.py:250-255`.)

**Outputs.** No return value. **Side effects:**
- Calls `exit_trade(symbol, price, qty, reason)` (`bot_v3_hybrid.py:3648`),
  which submits the SELL LIMIT via `state.broker.submit_limit(...)` and
  enqueues an async `verify_exit_fill()` thread to book P&L from actual fill
  data, not intended price.
- Mutates `pos["tp_hit"]`, `pos["qty"]` (decrements on partial), and
  `pos["runner_stop"]` (sets to BE-plus on target hit).
- Calls `persist_open_trades()` to flush session state to disk (post-target
  partial state).
- Notifies the EPL watchlist on graduation at 2R (`bot_v3_hybrid.py:3335-3352`)
  — this is **squeeze-specific coupling** that WB v2 must NOT participate
  in; see "Constraints" below.

**Reusability for WB v2.** **Thin adapter required.** The cascade itself is
self-contained — it reads pos dict fields, compares to env-derived
thresholds, calls `exit_trade()`. But it currently routes only when
`setup_type in ("squeeze", "mp_reentry", "continuation")` at
`bot_v3_hybrid.py:3293`. WB v2 has two options:

1. **Preferred: register WB v2 as a routed setup_type.** Add `"wb_v2"` to
   the tuple at `bot_v3_hybrid.py:3293` so the existing `_squeeze_exit`
   function services it without modification. This requires a one-line
   edit, which the directive prohibits ("Setup A is sacred").
2. **Adapter: WB v2 maintains its own position dict
   (`state.wb_v2_positions`) and calls `_squeeze_exit` directly from a WB
   v2 tick handler.** Since `_squeeze_exit` is module-level and takes
   `(symbol, price, pos)`, WB v2 can call it directly **provided** the pos
   dict has the same keys: `entry`, `stop`, `r`, `qty`, `tp_hit`, `peak`,
   `is_parabolic`, `runner_stop` (optional, defaults to `stop`). WB v2
   must construct this dict shape on entry.

   The problem with option 2: `_squeeze_exit` mutates `pos` in place and
   calls `exit_trade()`, which assumes `state.open_position` is the trade
   being exited (`bot_v3_hybrid.py:3684`). It will mis-attribute exits to
   the squeeze trade if a squeeze position is concurrently open. **This
   is the reason a real adapter is required, not just a direct call.**

**Recommended adapter (WB v2 owns):**
`wb_v2/exit_dispatcher.py::wb_v2_manage_exit(symbol, price, wb_v2_pos)`
that re-implements the *control flow* of `_squeeze_exit` (same six stages,
same env knobs, same reason strings) but calls a WB-v2-local
`wb_v2_exit_trade()` that mutates `state.wb_v2_positions[symbol]` and
submits via `state.broker` directly. This duplicates ~70 lines of code
but preserves the "Setup A is sacred" invariant. The duplication is
acceptable because the directive explicitly accepts it.

**Constraints (per-stage).**
- **EPL graduation coupling** (`bot_v3_hybrid.py:3335-3352`): the squeeze
  target-hit branch notifies the EPL watchlist. WB v2 MUST NOT call this
  — WB v2 wave-reversal trades are not squeeze graduates. The adapter
  drops this branch.
- **`is_parabolic` flag**: derived in squeeze entry from
  `"[PARABOLIC]" in armed.score_detail` (`bot_v3_hybrid.py:3170`). WB v2
  has no parabolic concept by default; the adapter sets
  `is_parabolic=False` unless a future WB v2 signal opts in.
- **`r` (risk-per-share)**: squeeze derives this from `entry - stop` where
  stop is `_stop_from_consolidation` (squeeze_detector_v2). WB v2 must
  supply its own stop — typically the bar low / swing low that defined
  the support level. The adapter takes `(entry, stop)` and computes
  `r = entry - stop` the same way.
- **Tiered max-loss (`trade_manager.py:2924-2936`)**: depends on
  `t.float_m`, set at entry from fundamentals fetch. WB v2 can populate
  the same field from the fundamentals cache; the adapter passes it
  through unchanged.

---

## Primitive 3 — `exit_trade` (broker submission + async P&L book)

**File:** `bot_v3_hybrid.py:3648-3850` (approximate end of the function and
its `verify_exit_fill` helper).

**Purpose.** Submit the SELL LIMIT and asynchronously verify the fill from
the broker before booking P&L. Urgent reasons (`sq_stop_hit`,
`sq_dollar_loss_cap`, `sq_max_loss_hit`, `stop_hit`) get an aggressive 3%-
below-bid limit; non-urgent (target / trail) get a 3-cent-below limit. No
market fallback (per project rules at `bot_v3_hybrid.py:3667`).

**Inputs.** `(symbol, price, qty, reason)`. Reads `state.open_position` to
snapshot entry price for P&L. Reads `state.broker` for submission.

**Outputs.** None. **Side effects:**
- Submits limit order via `state.broker.submit_limit(...)`.
- Mutates `state.open_position["qty"]` (partial) or clears
  `state.open_position` (full).
- Spawns `verify_exit_fill()` thread that polls order status for up to
  30s, updates `state.daily_pnl`, increments `state.daily_trades`,
  appends to `state.closed_trades`.

**Reusability for WB v2.** **Adapter required.** This function is tightly
coupled to `state.open_position`, which is the squeeze position slot. WB v2
must NOT use it because:
- It would clobber the squeeze position's P&L books if a squeeze trade is
  also open concurrently.
- It would race on `state.open_position` clear vs WB v2 trade close.

WB v2 must implement a **mirror function** `wb_v2_exit_trade(symbol, price,
qty, reason)` that:
1. Submits via the same broker API (`state.broker.submit_limit`).
2. Mutates `state.wb_v2_positions[symbol]` instead of `state.open_position`.
3. Books P&L into a WB-v2-local counter (`state.wb_v2_daily_pnl` etc.) and
   a separate `closed_trades` list.
4. Uses the **same urgent-reasons logic** (3%-below for stops/caps,
   3-cent-below for targets/trails) to match the squeeze's proven fill
   semantics.

The adapter is ~50 lines and is the core of "the WB v2 entry handler" the
directive refers to. It does not modify `exit_trade` itself.

---

## Primitive 4 — Bail timer

**File:** `bot_v3_hybrid.py:3284-3289` (live), mirrored in `trade_manager.py`.

**Purpose.** If a trade has been open >= `WB_BAIL_TIMER_MINUTES` (default 5)
and `price <= entry`, exit immediately with reason `bail_timer`. Cuts
unprofitable trades that aren't moving.

**Inputs.** `pos["entry_time"]` (datetime, set on entry), `price`, `entry`.

**Outputs.** Calls `exit_trade(symbol, price, qty, "bail_timer")`.

**Reusability for WB v2.** **Direct call in the adapter.** The bail timer
is strategy-agnostic — it's a "did this trade ever go green within N
minutes" check. WB v2 invokes the same five-minute check inside its own
`wb_v2_manage_exit`, using `wb_v2_pos["entry_time"]` and calling
`wb_v2_exit_trade(...)`.

**Constraints.** The bail timer fires BEFORE the squeeze cascade in
`manage_exit` (`bot_v3_hybrid.py:3284-3289`). WB v2's adapter must
preserve this ordering — bail first, then cascade.

---

## Primitive 5 — Peak tracking + `persist_open_trades`

**File:** `bot_v3_hybrid.py:3274-3276` (peak update),
`bot_v3_hybrid.py` (persist function — referenced throughout, writes
`session_state/<date>/open_trades.json`).

**Purpose.** Monotonically update `pos["peak"]` on every new high so the
trailing-stop calculations have the right reference. Flush to disk on every
peak advance so a mid-trade crash + resume preserves trail state.

**Inputs.** `price`, `pos["peak"]`.

**Outputs.** Mutates `pos["peak"]`; writes to disk on advance.

**Reusability for WB v2.** **Adapter required.** Same shape, different
target file. WB v2 maintains `state.wb_v2_positions` and writes to
`session_state/<date>/wb_v2_open_trades.json`. The peak-update logic itself
is two lines of code duplicated into `wb_v2_manage_exit`.

**Constraints.** The disk persistence must use a separate file from
squeeze's `open_trades.json` to avoid mutual clobbering when both
strategies write concurrently. The directive's session-persistence rule
(`memory: feedback_session_persistence_required.md`) applies to WB v2 too.

---

## Asymmetry note: live bot vs Alpaca paper

The live IBKR bot (`bot_v3_hybrid.py::_squeeze_exit`) does **not**
implement tiered max-loss. Only `PaperTradeManager._squeeze_manage_exits`
in `trade_manager.py:2924-2936` does. WB v2 should:

- On the live IBKR path, mirror the live cascade (no tiered max-loss).
- On the Alpaca paper path (if WB v2 ever runs there), mirror the
  `trade_manager` cascade (with tiered max-loss).

This is a deliberate divergence in the production codebase that WB v2
must respect, not "fix."

---

## Reuse plan

### Direct call (no wrapper)

- **`force_exit.py::should_force_exit_now()`** — already polled
  process-wide by `bot_v3_hybrid.py:4787`. WB v2 inherits this for free.
- **`force_exit.py::force_exit_position()`** — WB v2 calls directly from
  inside `_maybe_session_end_force_exit()` once a `state.wb_v2_positions`
  iteration is added (one new for-loop, mirroring the existing WB-positions
  loop at `bot_v3_hybrid.py:2018-2032`).
- **`state.broker.submit_limit(...)`** — direct call from the WB v2
  adapter's `wb_v2_exit_trade` helper.

### Thin adapter required

- **`wb_v2_manage_exit(symbol, price, wb_v2_pos)`** — mirrors the
  control flow of `_squeeze_exit` (dollar cap, hard stop, pre-target
  trail, 2R target, runner trail). Drops the EPL graduation branch.
  Calls `wb_v2_exit_trade` instead of `exit_trade`.
- **`wb_v2_exit_trade(symbol, price, qty, reason)`** — mirrors
  `exit_trade`'s submit-then-async-verify pattern but targets
  `state.wb_v2_positions` and a WB-v2-local P&L bookkeeper.
- **Bail timer block** — copied verbatim into `wb_v2_manage_exit`
  preamble.
- **Peak update + persist** — two lines copied verbatim, but persists
  to `wb_v2_open_trades.json`.

### Net new (WB v2 needs, squeeze doesn't have)

- **Short-side exit cascade.** WB v2 mirrors the long cascade for
  shorts (resistance + MACD red near top), so the adapter needs a
  `side="short"` branch that inverts every price comparison: dollar loss
  cap uses `(price - entry) * qty`, hard stop fires on `price >= stop`,
  trail fires on `price >= trough + trail_r * r`, target fires on
  `price <= entry - target_r * r`. The squeeze bot is long-only;
  this is genuinely new code. **Squeeze exit logic is the structural
  template — the math is mirrored, not reused.**
- **Universe handoff.** WB v2 needs a "what symbols am I watching today"
  feed independent of squeeze's `state.watchlist`. Stage 0 deliverable
  3 (`extracted_universe.csv`) provides the data backbone; the live
  feed will be a new WB v2 scanner. Not an exit-stack concern, but
  noted for completeness.
- **Strategy-tagged P&L.** Daily P&L, position counters, and
  closed-trades log must be tagged by strategy so reports can separate
  WB v2 from squeeze. The squeeze bot stores these on `state` directly;
  WB v2 needs `state.wb_v2_daily_pnl`, `state.wb_v2_daily_trades`,
  `state.wb_v2_closed_trades` (or equivalent on a dedicated WB v2
  state container).

---

## Summary table

| Primitive | File:Lines | Reuse mode |
|---|---|---|
| `should_force_exit_now` | `force_exit.py:64-79` | Direct call |
| `force_exit_position` | `force_exit.py:104-193` | Direct call |
| Dollar loss cap | `bot_v3_hybrid.py:3306-3311` | Adapter (mirror) |
| Hard stop | `bot_v3_hybrid.py:3313-3316` | Adapter (mirror) |
| Tiered max-loss | `trade_manager.py:2924-2936` | Adapter (mirror, paper path only) |
| Pre-target trail | `bot_v3_hybrid.py:3319-3327` | Adapter (mirror) |
| 2R target + partial | `bot_v3_hybrid.py:3329-3367` | Adapter (mirror, drop EPL) |
| Runner trail | `bot_v3_hybrid.py:3369-3376` | Adapter (mirror) |
| Bail timer | `bot_v3_hybrid.py:3284-3289` | Adapter (verbatim copy) |
| Peak update + persist | `bot_v3_hybrid.py:3274-3276` | Adapter (different file) |
| `exit_trade` (broker submit + verify) | `bot_v3_hybrid.py:3648-3850` | Adapter (mirror) |

---

## Closing note

The squeeze bot's exit code stays untouched. WB v2 imports `force_exit`
directly and otherwise re-implements the same control flow in a WB-v2-local
adapter that targets a WB-v2-local position dict. The adapter is ~150 lines
and adds short-side mirroring; everything else is structural duplication of
proven logic. When the squeeze cascade evolves (e.g., Candle Exit V2,
parabolic regime), the WB v2 adapter is updated separately and on its own
review cadence. This is deliberate: shared exit code would couple the two
strategies' release cycles and violate the "Setup A is sacred" invariant.
