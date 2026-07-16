"""simulate_subbot.py — sub-bot tick-replay backtest harness.

Per cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md.

Replays a single symbol on a single date through the EXACT live sub-bot
decision logic (MOVE_STRIKE + REGIME_SHIFT + HWM + REENTRY GREEN + fade-gates).
Subclasses MoveStrikeSubBot from move_strike_subbot.py so the decision
tree is shared bit-for-bit with live — no clean-room duplication, no
drift opportunity for the decision logic itself.

What this file overrides vs. live:
  - Alpaca init: replaced with MockAlpaca (no live HTTP)
  - Order fills: assumed instant fill at limit price (synthetic +slippage on buys,
    -slippage on sells), no broker round-trip
  - Tick stream: read from tick_cache/<date>/<sym>.json.gz instead of engine socket
  - Logging: trade lines emitted in simulate.py's TRADE_LINE_RE format so the
    replay harness can parse them

What this file does NOT change vs. live:
  - Entry triggers (MovementStrike, RegimeShiftDetector, both via inherited methods)
  - Exit logic (hwm_evaluate, regime_shift partial+target, hard-stop, stop-prox-bail)
  - Fade-gate decisions (VWAP, open-drawdown, downtrend, BodyCV)
  - Re-entry mechanics (REENTRY GREEN with same-bar guard, close>stop guard,
    cycle-reset, per-symbol cap)
  - Position sizing (incl. PROBE_SIZE_MULT, MAX_NOTIONAL, MAX_SHARES)
  - Stay-armed cooldown, max-below-arm filter, chase-cap

CLI (matches simulate.py for tool compatibility):
    ./venv/bin/python simulate_subbot.py SYMBOL DATE START END \\
        --ticks --tick-cache tick_cache/ \\
        [--slippage 0.07] [--no-fundamentals]

Env vars consumed (all read by inherited MoveStrikeSubBot.__init__):
    See move_strike_subbot.py and hwm_exit.py for the full env contract.
    The most load-bearing for sub-bot behavior:
      WB_BT_MOVE_STRIKE, WB_BT_MOVE_HWM_EXIT, WB_BT_MOVE_REENTRY_GREEN,
      WB_REGIME_SHIFT_ENABLED, WB_REGIME_SHIFT_RATIO_THRESHOLD,
      WB_MOVE_FADE_VWAP_ENABLED, WB_MOVE_FADE_BODY_CV_THRESHOLD,
      WB_SUBBOT_RISK_DOLLARS, WB_SQ_PROBE_SIZE_MULT.
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# Fake Alpaca credentials BEFORE importing the live module — its
# _init_alpaca() would sys.exit(1) on missing creds. TradingClient
# constructs lazily; no API call happens until we actually use it,
# and we never use it because MockAlpaca replaces self.alpaca below.
os.environ.setdefault("WB_SUBBOT_APCA_API_KEY_ID", "sim")
os.environ.setdefault("WB_SUBBOT_APCA_API_SECRET_KEY", "sim")
# Disable Alpaca-aware-limit features in sim (no real quote feed available).
os.environ.setdefault("WB_ALPACA_AWARE_LIMITS", "0")
# Seed-from-cache IS enabled in sim (default), but with a cutoff. The
# subclass installs self._seed_cutoff_utc = replay_window_start_utc, and
# the patched _seed_symbol_from_cache uses it instead of "now()" for the
# cutoff. Result: cache replay loads ticks up to (but not including)
# the replay window start, then my replay_ticks() feeds ticks from the
# window onward. No double-counting, full historical warm-up — matches
# live behavior at first-subscription.
os.environ.setdefault("WB_SUBBOT_SEED_FROM_CACHE", "1")

import move_strike_subbot as _mod  # noqa: E402  (for set_sim_now sim-time override)
from move_strike_subbot import MoveStrikeSubBot, SubPosition, LOG_TAG, now_iso_et  # noqa: E402
from firestorm_trigger import FirestormTrigger  # noqa: E402


# Patch _init_alpaca BEFORE any SubBotSim instance is created. The base
# class's _init_alpaca() makes a real account-validation call against
# Alpaca and sys.exit(1)s if it fails — which it does in sim with fake
# creds. We replace it with a no-op stub; SubBotSim.__init__ then
# installs MockAlpaca after super().__init__().
def _init_alpaca_sim_stub(self):
    self.alpaca = None
    self.alpaca_data = None
MoveStrikeSubBot._init_alpaca = _init_alpaca_sim_stub


# ════════════════════════════════════════════════════════════════════════
# MockAlpaca — replaces TradingClient for in-process fill simulation.
# ════════════════════════════════════════════════════════════════════════
class _MockOrder:
    """Mimics the parts of alpaca-py Order the sub-bot uses."""
    def __init__(self, order_id: str):
        self.id = order_id


class _MockPosition:
    """Mimics the alpaca-py Position fields the sub-bot reads."""
    def __init__(self, symbol: str, qty: int, avg: float):
        self.symbol = symbol
        self.qty = str(qty)
        self.qty_available = str(qty)   # sim has no held_for_orders
        self.avg_entry_price = str(avg)


class MockAlpaca:
    """In-process replacement for alpaca-py TradingClient.

    The sub-bot uses TradingClient only for:
      - submit_order(order_data=req) → returns Order with .id
      - get_order_by_id(order_id) → returns Order with .status, .filled_avg_price, .filled_qty
      - cancel_order_by_id(order_id) → no-op (Lever 2 retries)
      - get_all_positions() → returns list (Lever 3 reconcile)

    All four are stubbed here. Fills are assumed instant at the submitted
    limit price (no slippage realism beyond what the sub-bot itself
    applies on top of the trigger price).
    """
    def __init__(self):
        self._counter = 0
        self._orders: dict[str, dict] = {}  # order_id → {sym, side, qty, limit, status}
        # Latest market (tick) price, fed by SubBotSim.replay_ticks before
        # each on_tick. Used for the realistic fill model below.
        self._market_price: Optional[float] = None
        # Realistic-fill model (2026-06-30): a marketable limit fills at the
        # PREVAILING MARKET PRICE when it arrives (≈ the decision-time tick),
        # capped by the limit — NOT at the limit itself. Filling at the limit
        # (entry+slip on buys, ref-slip on sells) systematically over-states
        # slippage, making the sim ~$50-300/trade more pessimistic than the
        # real fills (UPC 6/29: sim $14.63 vs live $14.19). Default ON; set
        # WB_SUBBOT_SIM_REALISTIC_FILL=0 to revert to fill-at-limit.
        self._realistic_fill = os.getenv("WB_SUBBOT_SIM_REALISTIC_FILL", "1") == "1"
        # Position tracking (2026-06-30): the regime_shift PARTIAL scale-out
        # checks get_open_position()/get_all_positions() to confirm sellable
        # shares before scaling. Without real position state the mock returned
        # "flat", so the partial SKIPPED and a winning runner never closed
        # (0 trades emitted). This only surfaces on WINNERS that reach the 1.5R
        # partial — which the bleeding anomaly-close entry never produced.
        self._positions: dict[str, dict] = {}  # symbol -> {qty, avg}

    def set_market_price(self, px: float) -> None:
        self._market_price = float(px)

    def submit_order(self, order_data):
        self._counter += 1
        order_id = f"sim-{self._counter}"
        # alpaca-py LimitOrderRequest has: symbol, qty, side, limit_price, time_in_force, extended_hours
        side = str(order_data.side).split(".")[-1].upper()  # "BUY" / "SELL"
        limit = float(order_data.limit_price)
        fill = limit
        if self._realistic_fill and self._market_price is not None:
            mkt = self._market_price
            if side == "BUY":
                # Marketable buy: fills at the ask ≈ market, never ABOVE limit.
                fill = min(mkt, limit)
            else:
                # Marketable sell: fills at the bid ≈ market, never BELOW limit.
                fill = max(mkt, limit)
        qty = int(order_data.qty)
        self._orders[order_id] = {
            "symbol": order_data.symbol,
            "qty": qty,
            "side": side,
            "limit_price": limit,
            "status": "FILLED",   # assume instant fill in sim
            "filled_qty": qty,
            "filled_avg_price": round(fill, 4),
        }
        # Track the resulting position (instant fill) so get_open_position /
        # get_all_positions report broker truth for the partial scale-out.
        sym = order_data.symbol
        pos = self._positions.get(sym, {"qty": 0, "avg": 0.0})
        if side == "BUY":
            new_qty = pos["qty"] + qty
            pos["avg"] = ((pos["avg"] * pos["qty"]) + fill * qty) / new_qty if new_qty else fill
            pos["qty"] = new_qty
        else:  # SELL
            pos["qty"] = max(0, pos["qty"] - qty)
        if pos["qty"] <= 0:
            self._positions.pop(sym, None)
        else:
            self._positions[sym] = pos
        return _MockOrder(order_id)

    def get_order_by_id(self, order_id):
        rec = self._orders.get(order_id)
        if rec is None:
            return None
        # Build a tiny duck-typed Order
        class _O:
            pass
        o = _O()
        o.id = order_id
        # alpaca-py's OrderStatus enum has .value; sub-bot's _wait_for_fill
        # compares to OrderStatus.FILLED, .PARTIALLY_FILLED, etc.
        from alpaca.trading.enums import OrderStatus
        o.status = OrderStatus.FILLED
        o.filled_avg_price = rec["filled_avg_price"]
        o.filled_qty = rec["filled_qty"]
        return o

    def cancel_order_by_id(self, order_id):
        if order_id in self._orders:
            self._orders[order_id]["status"] = "CANCELED"

    def get_all_positions(self):
        return [_MockPosition(s, p["qty"], p["avg"])
                for s, p in self._positions.items() if p["qty"] > 0]

    def get_open_position(self, symbol):
        # alpaca-py raises (404) when flat; the sub-bot's _broker_available_qty
        # catches that and treats it as 0. Mirror that contract.
        p = self._positions.get(symbol)
        if not p or p["qty"] <= 0:
            raise ValueError(f"no open position for {symbol}")
        return _MockPosition(symbol, p["qty"], p["avg"])

    def get_orders(self, *args, **kwargs):
        # Exit path cancels any resting open orders before submitting the
        # SELL. In sim all orders fill instantly, so there are never open
        # orders — return empty. (Missing method otherwise raises mid-exit:
        # "PARTIAL CANCEL-OPEN FAIL ... no attribute 'get_orders'".)
        return []

    def get_account(self):
        # Equity-% sizing (WB_SUBBOT_EQUITY_PCT) calls this to seed
        # _starting_equity. Without it the live config sizes every entry to
        # qty=0 and the sim emits ZERO trades — a parity break vs live, which
        # sizes off the broker's real equity. Return a configurable equity
        # (WB_SUBBOT_SIM_EQUITY) so sim qty/P&L matches live for the day under
        # test. Default $3000 = the 2026-06-17 fresh-paper reset base.
        class _Acct:
            pass
        a = _Acct()
        a.equity = float(os.getenv("WB_SUBBOT_SIM_EQUITY", "3000"))
        a.account_number = "SIM"
        a.cash = a.equity
        a.buying_power = a.equity
        return a


# ════════════════════════════════════════════════════════════════════════
# SubBotSim — the actual sim driver.
# ════════════════════════════════════════════════════════════════════════
class SubBotSim(MoveStrikeSubBot):
    """Sub-bot subclass that runs against a tick cache instead of the
    engine socket. Inherits ALL decision logic; overrides only the
    boundaries (Alpaca, socket, fill-wait)."""

    def __init__(self):
        super().__init__()
        # Replace whatever _init_alpaca constructed with our mock.
        self.alpaca = MockAlpaca()
        self.alpaca_data = None
        # Sim-mode flag (informational; no behavior gates today).
        self._sim_mode = True
        # Trades emitted during this run (one record per close).
        self.emitted_trades: list[dict] = []
        # Track current bar-time for trade timestamping.
        self._current_minute_et: int = 0
        self._current_time_str_et: str = "00:00:00"

        # FIRESTORM_TRIGGER prototype (Phase 3 Stage 1). Per-symbol
        # detector instances + state. Independent of MovementStrike /
        # RegimeShift — adds a third arming path that fires on quiet→
        # firestorm tick-rate transitions. NOT wired into live in this
        # iteration; sim-only.
        self.firestorm_trigger_enabled = (
            os.getenv("WB_FIRESTORM_TRIGGER_ENABLED", "0") == "1"
        )
        self.firestorm_trigger_min_ticks = int(
            os.getenv("WB_FIRESTORM_TRIGGER_MIN_TICKS", "6000")
        )
        self.firestorm_trigger_min_gap_pct = float(
            os.getenv("WB_FIRESTORM_TRIGGER_MIN_GAP_PCT", "5.0")
        )
        self.firestorm_trigger_max_per_sym = int(
            os.getenv("WB_FIRESTORM_TRIGGER_MAX_PER_SYM", "3")
        )
        # Time cutoff HH:MM ET — no FT arms after this time.
        cutoff_str = os.getenv("WB_FIRESTORM_TRIGGER_TIME_CUTOFF", "12:00")
        try:
            ch, cm = cutoff_str.split(":")
            self.firestorm_trigger_time_cutoff_min = int(ch) * 60 + int(cm)
        except Exception:
            self.firestorm_trigger_time_cutoff_min = 12 * 60  # 12:00 ET
        self._firestorm_triggers: dict[str, FirestormTrigger] = {}
        self._firestorm_entries_per_symbol: dict[str, int] = {}
        # (symbol, current_date_str) → prior-day-close cache
        self._firestorm_prior_close: dict[tuple[str, str], Optional[float]] = {}

        # FT exit sweep knobs (Phase 3 Stage 1.5). All default to
        # Stage 1 behavior (zero = use bar_low * 0.99 stop, no force flatten).
        # Run B: WB_FT_STOP_FLOOR_ABS=0.10 WB_FT_STOP_FLOOR_PCT=0.05
        # Run C: WB_FT_DRAWDOWN_FLOOR_PCT=0.25 WB_FT_FORCE_FLATTEN_TIME=15:30
        # Run D: union of B + C
        self.ft_stop_floor_abs = float(os.getenv("WB_FT_STOP_FLOOR_ABS", "0"))
        self.ft_stop_floor_pct = float(os.getenv("WB_FT_STOP_FLOOR_PCT", "0"))
        # Force-flatten ET time HH:MM. Empty/0 = disabled.
        ft_ff_str = os.getenv("WB_FT_FORCE_FLATTEN_TIME", "")
        try:
            fh, fm = ft_ff_str.split(":")
            self.ft_force_flatten_min = int(fh) * 60 + int(fm)
        except Exception:
            self.ft_force_flatten_min = 0  # disabled

    def _current_min_for_age(self) -> int:
        """Override: return the simulator's tracked historical minute
        (set per-tick from the tick timestamp) instead of wall clock.
        Needed for Track A's phased drawdown floor: age = current_minute
        - entry_minute, both must be historical for sim correctness."""
        return self._current_minute_et

    def _wait_for_fill(self, order_id: str, timeout: int = 15):
        """Override: read from MockAlpaca's deterministic fill record."""
        if not order_id:
            return None, 0
        rec = self.alpaca._orders.get(order_id)
        if rec is None:
            return None, 0
        if rec.get("status") == "FILLED":
            return float(rec["filled_avg_price"]), int(rec["filled_qty"])
        return None, 0

    def _compute_alpaca_aware_limit(self, symbol: str, signal_price: float,
                                     side: str, buffer_pct: float = 0.005) -> float:
        """Override: no live quote feed in sim. Return base limit per the
        same formula live uses when alpaca_aware_limits is disabled."""
        side_u = side.upper()
        base_limit = round(signal_price * (1 + buffer_pct), 2) if side_u == "BUY" \
            else round(signal_price * (1 - buffer_pct), 2)
        return base_limit

    # ─── FIRESTORM_TRIGGER helpers ───────────────────────────────────────
    def _firestorm_prior_close_for(self, symbol: str, date_str: str,
                                    tick_cache_root: Path) -> Optional[float]:
        """Return the last tick price from the most recent prior trading
        day's tick cache for `symbol`. None if no prior cache exists
        within the look-back window. Cached per (symbol, date)."""
        key = (symbol, date_str)
        if key in self._firestorm_prior_close:
            return self._firestorm_prior_close[key]
        # Look back up to 7 calendar days for a prior cache (skips weekends/holidays).
        try:
            y, m, d = (int(x) for x in date_str.split("-"))
            cur = datetime(y, m, d)
        except Exception:
            self._firestorm_prior_close[key] = None
            return None
        for delta_days in range(1, 8):
            prev = cur - timedelta(days=delta_days)
            prev_str = prev.strftime("%Y-%m-%d")
            prev_path = tick_cache_root / prev_str / f"{symbol}.json.gz"
            if not prev_path.exists():
                continue
            try:
                with gzip.open(prev_path, "rt") as f:
                    prev_ticks = json.load(f)
                if not prev_ticks:
                    continue
                last_tick = prev_ticks[-1]
                if isinstance(last_tick, dict):
                    px = float(last_tick.get("p") or last_tick.get("price") or 0)
                elif isinstance(last_tick, (list, tuple)) and len(last_tick) > 1:
                    px = float(last_tick[1])
                else:
                    continue
                if px > 0:
                    self._firestorm_prior_close[key] = px
                    return px
            except Exception:
                continue
        # No prior cache found.
        self._firestorm_prior_close[key] = None
        return None

    def _maybe_fire_firestorm_trigger(self, symbol: str, price: float,
                                       cur_min_et: int) -> None:
        """Per-tick FT check. Called from on_tick when no position is open.
        Opens a firestorm-trigger position if the detector fires and all
        gates pass."""
        if not self.firestorm_trigger_enabled:
            return
        # Time cutoff
        if cur_min_et > self.firestorm_trigger_time_cutoff_min:
            return
        # Per-symbol entry cap
        cur = self._firestorm_entries_per_symbol.get(symbol, 0)
        if cur >= self.firestorm_trigger_max_per_sym:
            return
        ft = self._firestorm_triggers.get(symbol)
        if ft is None:
            ft = FirestormTrigger(
                min_ticks=self.firestorm_trigger_min_ticks,
                min_gap_pct=self.firestorm_trigger_min_gap_pct,
            )
            self._firestorm_triggers[symbol] = ft
        # Look up prior close lazily (only on tick-feed; tick_cache_root
        # set by replay_ticks before this method is called).
        prior_close = self._firestorm_prior_close.get(
            (symbol, getattr(self, "_current_date_str", "")), None
        )
        fire = ft.update_and_check(
            price=price, bar_minute=cur_min_et, prior_close=prior_close,
        )
        if fire is None:
            return
        # Trigger fired — open position.
        self._open_firestorm_trigger_position(symbol, fire)

    def _open_firestorm_trigger_position(self, symbol: str,
                                          fire) -> None:
        """Open a firestorm-trigger position. Entry = trigger_price + 20bps
        slippage, stop = bar_low * 0.99. Reuses regime_shift exit framework
        via setup_type='firestorm_trigger' (dispatched in the patched
        _maintain_position below)."""
        entry = float(fire.trigger_price)
        # Stop at 1% below the firestorm bar's low — Stage 1 default.
        baseline_stop = fire.bar_low * 0.99
        # Track A (Phase 4) supersedes the Stage 1.5 FT-specific floor.
        # When Track A is enabled, the helper enforces the unified
        # framework's R floor across both setups. When Track A is OFF,
        # fall through to the Stage 1.5 FT-specific floor (kept for
        # sweep-reproducibility) or the Stage 1 raw stop.
        from exit_track_a import track_a_enabled, compute_stop_with_r_floor
        if track_a_enabled():
            stop, r = compute_stop_with_r_floor(entry, baseline_stop)
            stop = round(stop, 4)
        elif self.ft_stop_floor_abs > 0 or self.ft_stop_floor_pct > 0:
            stop_floor_abs = self.ft_stop_floor_abs
            stop_floor_pct_abs = entry * self.ft_stop_floor_pct
            min_r = max(stop_floor_abs, stop_floor_pct_abs)
            widened_stop = entry - min_r
            stop = round(min(baseline_stop, widened_stop), 4)
            r = entry - stop
        else:
            stop = round(baseline_stop, 4)
            r = entry - stop
        if r <= 0.01:
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} firestorm_trigger skip — "
                f"r={r:.4f} too small (entry=${entry:.2f} stop=${stop:.2f})",
                flush=True,
            )
            return
        qty = self._compute_qty(entry, r, 60.0)  # score=60 per directive
        if qty <= 0:
            return
        # Entry limit = trigger_price * 1.002 (20bps slippage allowance)
        limit = round(entry * 1.002, 2)
        gap_str = (f" gap={fire.gap_pct_vs_prior_close:.1f}%"
                   if fire.gap_pct_vs_prior_close is not None else "")
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🚀 ENTRY FIRESTORM_TRIGGER {symbol} "
            f"qty={qty} limit=${limit:.2f} (trigger@${entry:.2f}{gap_str}) "
            f"stop=${stop:.2f} R=${r:.4f} ticks={fire.tick_count}",
            flush=True,
        )
        try:
            from alpaca.trading.requests import LimitOrderRequest
            from alpaca.trading.enums import OrderSide, TimeInForce
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
        except Exception as e:
            print(f"{LOG_TAG} FIRESTORM_TRIGGER ENTRY REJECT {symbol}: {e!r}",
                  flush=True)
            return
        self.position = SubPosition(
            symbol=symbol, entry=entry, stop=stop, r=r, qty=qty,
            score=60.0, time_et=now_iso_et(),
            is_reentry=False, reentry_tag="",
            setup_type="firestorm_trigger",
        )
        self.position.order_id_buy = str(order.id) if hasattr(order, "id") else None
        fill_px, fill_qty = self._wait_for_fill(self.position.order_id_buy, timeout=15)
        if fill_px is not None and fill_qty > 0:
            self.position.fill_entry_price = fill_px
            self.position.fill_entry_qty = fill_qty
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} firestorm_trigger entry "
                f"FILLED @ ${fill_px:.4f} qty={fill_qty} (limit was ${limit:.2f})",
                flush=True,
            )
            if fill_qty < qty:
                self.position.qty = fill_qty
            self._firestorm_entries_per_symbol[symbol] = (
                self._firestorm_entries_per_symbol.get(symbol, 0) + 1
            )
        else:
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} firestorm_trigger entry "
                f"NOT FILLED — abandoning",
                flush=True,
            )
            self.position = None
            return
        self.position.hh_count = self._sym_hh_count.get(symbol, 0)

    def on_tick(self, symbol: str, price: float, ts_iso: str, size: int) -> None:
        """Override to add FIRESTORM_TRIGGER check AFTER the base on_tick
        finishes. The base call handles bar building, MovementStrike,
        RegimeShiftDetector, _maintain_position, and _maybe_enter. If
        none of those opened a position, FT gets a chance to arm.

        Stage 1.5: also check FT force-flatten time. If an FT position is
        open and current ET minute >= ft_force_flatten_min, close it.
        """
        # Parse ET minute once — used by both force-flatten and FT arm.
        try:
            from zoneinfo import ZoneInfo
            ts = datetime.fromisoformat(ts_iso)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            ts_et = ts.astimezone(ZoneInfo("America/New_York"))
            cur_min = ts_et.hour * 60 + ts_et.minute
        except Exception:
            cur_min = None

        # FT force-flatten check BEFORE base on_tick — guarantees we don't
        # let an FT position survive past the cutoff even if the base
        # path's _maintain_position would have held it.
        if (cur_min is not None
                and self.ft_force_flatten_min > 0
                and self.position is not None
                and self.position.setup_type == "firestorm_trigger"
                and self.position.symbol == symbol
                and cur_min >= self.ft_force_flatten_min):
            self._close_position("firestorm_trigger_force_flatten", price)

        super().on_tick(symbol, price, ts_iso, size)
        if not self.firestorm_trigger_enabled:
            return
        if self.position is not None:
            # Either an existing position is being managed, or one of the
            # base entry paths just opened. Either way, FT does not arm.
            return
        if cur_min is None:
            return
        self._maybe_fire_firestorm_trigger(symbol, price, cur_min)

    # ─── trade-record emission ───────────────────────────────────────────
    def _record_closed_trade(self, p: SubPosition, exit_px: float, exit_reason: str):
        """Capture a closed trade in simulate.py-compatible format. Called
        from inside our consume/exit overrides; sub-bot's own close logic
        prints its own log lines, but those don't survive into the
        replay harness's TRADE_LINE_RE parser.

        Phase 3b fix: `time` field is now the ENTRY time, matching
        simulate.py's convention (replay_live_universe.py's TRADE_LINE_RE
        expects entry time). Live's _open_position_with_tag stores
        entry_time_et via now_iso_et() which is WALL CLOCK in sim;
        the _open_with_tag_capture_time monkey-patch overwrites it
        with our historical _current_time_str_et at position-open time."""
        entry_basis = p.fill_entry_price if p.fill_entry_price is not None else p.entry
        pnl = int(round((exit_px - entry_basis) * p.qty))
        # Use entry time, not exit time. Fall back to current time if
        # the entry-time-capture monkey-patch didn't fire (defensive).
        entry_time = (p.entry_time_et or self._current_time_str_et)[:5]
        rec = {
            "time": entry_time,  # HH:MM (entry time)
            "entry": round(entry_basis, 4),
            "stop": round(p.stop, 4),
            "r": round(p.r, 4),
            "score": round(p.score, 1) if p.score is not None else 0.0,
            "exit": round(exit_px, 4),
            "reason": exit_reason,
            "pnl": pnl,
            "symbol": p.symbol,
            "setup": p.setup_type,
            "reentry_tag": p.reentry_tag if p.is_reentry else None,
        }
        self.emitted_trades.append(rec)

    # ─── consume() replacement: drive ticks from the cache ───────────────
    def replay_ticks(
        self,
        symbol: str,
        date_str: str,
        start_et: str,
        end_et: str,
        tick_cache_root: Path,
    ) -> None:
        """Walk the symbol's tick cache file and feed each tick into the
        bot's on_tick() in chronological order. Bars + bar-close callbacks
        are driven by the existing TradeBarBuilder.

        Window filter: ticks outside [start_et, end_et] are skipped. The
        sub-bot itself has no end-time logic; this filter only narrows
        the input stream to match a specific live discovery window.
        """
        cache_path = tick_cache_root / date_str / f"{symbol}.json.gz"
        if not cache_path.exists():
            print(f"[SIM] {symbol} {date_str}: no tick cache at {cache_path}", flush=True)
            return
        # Stash current date for FIRESTORM_TRIGGER prior-close lookup.
        self._current_date_str = date_str
        # Pre-warm prior-close cache for FT (no-op if FT disabled).
        if self.firestorm_trigger_enabled:
            self._firestorm_prior_close[(symbol, date_str)] = (
                self._firestorm_prior_close_for(symbol, date_str, tick_cache_root)
            )
        try:
            with gzip.open(cache_path, "rt") as f:
                ticks = json.load(f)
        except (gzip.BadGzipFile, OSError, EOFError) as e:
            # Tick cache files are multi-member gzip (atomic-flush writes append
            # members); a trailing partial member makes gzip.open raise BadGzipFile
            # AFTER decoding the first member. zlib wbits=31 reads the first
            # complete member (the full tick array) and ignores trailing bytes.
            try:
                import zlib
                ticks = json.loads(zlib.decompress(cache_path.read_bytes(), 31))
            except Exception:
                print(f"[SIM] {symbol} {date_str}: cache read failed: {e!r}", flush=True)
                return

        # Convert HH:MM strings to total-minutes-from-midnight ET
        sh, sm = (int(x) for x in start_et.split(":")[:2])
        eh, em = (int(x) for x in end_et.split(":")[:2])
        start_min = sh * 60 + sm
        end_min = eh * 60 + em

        # ET timezone for tick-time conversion
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")

        # Phase 3b: set the seed-from-cache cutoff to the replay window
        # start (in UTC). Live's _seed_symbol_from_cache will read cache
        # ticks earlier than this cutoff during _ensure_symbol's first
        # call for each symbol; my replay loop below feeds ticks at or
        # after the cutoff. Pre-window context is loaded the same way
        # live's bot loads it at first-subscription, but without
        # double-counting our forward stream.
        try:
            y, m, d = (int(x) for x in date_str.split("-"))
            window_start_local = datetime(y, m, d, sh, sm, tzinfo=ET)
            self._seed_cutoff_utc = window_start_local.astimezone(timezone.utc)
        except Exception:
            self._seed_cutoff_utc = None

        # Track previous tick capture to compute existing _wait_for_fill
        # synchronously (each on_tick may trigger an entry/exit that calls
        # _wait_for_fill, which in sim returns instantly from MockAlpaca).
        replayed = 0
        skipped_window = 0
        for tick in ticks:
            try:
                p = float(tick["p"])
                s = int(tick.get("s") or 0)
                t_iso = tick["t"]
            except (KeyError, ValueError, TypeError):
                continue
            # Parse timestamp → ET minutes
            try:
                ts = datetime.fromisoformat(t_iso)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ts_et = ts.astimezone(ET)
            except Exception:
                continue
            cur_min = ts_et.hour * 60 + ts_et.minute
            if cur_min < start_min or cur_min > end_min:
                skipped_window += 1
                continue
            # Update our notion of "now" for trade-record stamping AND for the
            # bot's time-of-day gates (set_sim_now → now_minute_et/now_iso_et
            # return the historical bar time, not wall-clock).
            self._current_minute_et = cur_min
            self._current_time_str_et = ts_et.strftime("%H:%M:%S")
            _mod.set_sim_now(cur_min, self._current_time_str_et)
            # Feed the tick through the sub-bot's normal pipeline.
            # NOTE: on_tick takes an ISO string; we re-stringify for safety.
            #
            # Detect new-position transitions to stamp historical entry
            # time on the SubPosition (live uses now_iso_et() which is
            # wall-clock — meaningless in sim). Both MOVE_STRIKE entry
            # paths (via _open_position_with_tag) AND regime_shift
            # (direct SubPosition construction in _maybe_fire_regime_shift)
            # go through here.
            had_pos = self.position is not None
            # Feed the realistic-fill model: an order submitted during this
            # on_tick fills at ≈ this tick's market price (capped by limit),
            # not at the limit. See MockAlpaca.submit_order.
            self.alpaca.set_market_price(p)
            try:
                self.on_tick(symbol, p, ts.isoformat(), s)
            except Exception as e:
                # Don't crash the whole replay on one tick failure;
                # just log + continue.
                print(f"[SIM] {symbol} on_tick error: {e!r} (tick={tick})", flush=True)
                continue
            if (not had_pos and self.position is not None
                    and self._current_time_str_et):
                # Phase 3b: overwrite wall-clock entry_time_et with the
                # historical sim time captured at this tick.
                self.position.entry_time_et = self._current_time_str_et
                # Track A: stash historical entry minute on the
                # sim-only field; do NOT touch entry_time_min (other
                # code paths use it as wall-clock and depend on
                # wall-clock-vs-wall-clock consistency).
                self.position.entry_minute_sim = self._current_minute_et
            replayed += 1
        # NOTE: TradeBarBuilder has no flush API — the last in-flight bar
        # won't fire its on_bar_close callback. Acceptable: a partial
        # last-bar wouldn't trigger valid signals anyway (live bot also
        # only acts on CLOSED bars). Documented as a deliberate gap.
        print(f"[SIM] {symbol} {date_str}: replayed {replayed} ticks "
              f"(skipped {skipped_window} outside window {start_et}-{end_et}); "
              f"emitted {len(self.emitted_trades)} trades", flush=True)

    # ─── BAR replay: drive from the live bar_stream (trade-for-trade parity) ──
    def replay_bars(
        self,
        symbol: str,
        date_str: str,
        start_et: str,
        end_et: str,
        variant: str = "A",
        bar_stream_root: Path = Path("logs/bar_stream"),
    ) -> None:
        """Replay the EXACT bars the live sub-bot recorded to bar_stream,
        instead of rebuilding bars from the full tick cache. This is the only
        faithful way to reproduce live trade-for-trade: live ran on a
        Tier-gated engine feed (sparse snapshot ticks until a symbol is
        promoted to Tier-1), so cache-derived bars diverge from what live
        actually saw during early discovery — which shifts arm timing and
        which bar the regime_shift fires on. bar_stream is the ground truth
        of live's bars.

        Each recorded bar (o,h,l,c,v,tick_count) is turned into a short
        synthetic tick sequence that rebuilds the identical bar: first=open,
        then high, then low, then close, padded with the close price up to
        the recorded tick_count (capped at _BAR_TICK_CAP — only matters for
        the FIRESTORM tick-count gate, whose 6000/min threshold is preserved
        because any bar above the cap is still above the threshold). Volume
        is split evenly across the synthetic ticks.
        """
        _BAR_TICK_CAP = 8000
        path = Path(bar_stream_root) / f"{date_str}_subbot_{variant}.jsonl"
        if not path.exists():
            print(f"[SIM] {symbol} {date_str}: no bar_stream at {path}", flush=True)
            return
        sh, sm = (int(x) for x in start_et.split(":")[:2])
        eh, em = (int(x) for x in end_et.split(":")[:2])
        start_min, end_min = sh * 60 + sm, eh * 60 + em
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        # Bar replay is self-contained: do NOT also seed from the tick cache
        # (that would double-feed full ticks and reintroduce the divergence —
        # and with _seed_cutoff_utc=None the seeder would use wall-clock now
        # and pull the ENTIRE day). Force the seed gate off for this run.
        self._seed_cutoff_utc = None
        os.environ["WB_SUBBOT_SEED_FROM_CACHE"] = "0"

        bars = []
        for ln in open(path):
            try:
                b = json.loads(ln)
            except Exception:
                continue
            if b.get("sym") != symbol:
                continue
            bars.append(b)
        bars.sort(key=lambda b: b["ts"])

        replayed_bars = 0
        for b in bars:
            try:
                o, h, l, c = float(b["o"]), float(b["h"]), float(b["l"]), float(b["c"])
                vol = int(b.get("v") or 0)
                tcount = int(b.get("tick_count") or 1)
                ts0 = datetime.fromisoformat(b["ts"])
            except Exception:
                continue
            if ts0.tzinfo is None:
                ts0 = ts0.replace(tzinfo=timezone.utc)
            ts_et = ts0.astimezone(ET)
            cur_min = ts_et.hour * 60 + ts_et.minute
            if cur_min < start_min or cur_min > end_min:
                continue
            # Build a DENSE piecewise-linear intra-bar path open->high->low->
            # close. Density matters: with a coarse [o,h,l,c] jump, a
            # threshold exit (partial target, drawdown floor, stop, trail)
            # triggers at the bar EXTREME instead of near its level — which
            # over-states winners (partial fires at the high) AND losers
            # (floor fires at the low), a directional bias. Stepping through
            # the range makes each crossing fire within ~one step of its
            # actual level, so the realistic-fill + trade-record logic stay
            # accurate. The o->h->l->c ORDER is the standard bar-replay
            # assumption (true intra-bar path is unknowable) — documented.
            n = max(1, min(tcount, _BAR_TICK_CAP))
            legs = [(o, h), (h, l), (l, c)]
            seglens = [abs(b - a) for a, b in legs]
            total = sum(seglens)
            prices = []
            if total <= 0:
                prices = [c] * n            # flat bar
            else:
                for (a, b), sl in zip(legs, seglens):
                    k = max(1, int(round(n * sl / total)))
                    for i in range(k):
                        prices.append(a + (b - a) * (i / k))
                prices.append(c)            # guarantee last tick = close
            n = len(prices)
            size_each = max(1, vol // n) if vol > 0 else 1
            step = 60.0 / n
            for i, px in enumerate(prices):
                ts = ts0 + timedelta(seconds=min(59.0, i * step))
                tk_et = ts.astimezone(ET)
                self._current_minute_et = tk_et.hour * 60 + tk_et.minute
                self._current_time_str_et = tk_et.strftime("%H:%M:%S")
                _mod.set_sim_now(self._current_minute_et, self._current_time_str_et)
                self.alpaca.set_market_price(px)
                had_pos = self.position is not None
                try:
                    self.on_tick(symbol, px, ts.isoformat(), size_each)
                except Exception as e:
                    print(f"[SIM] {symbol} on_tick error: {e!r}", flush=True)
                    continue
                if (not had_pos and self.position is not None
                        and self._current_time_str_et):
                    self.position.entry_time_et = self._current_time_str_et
                    self.position.entry_minute_sim = self._current_minute_et
            replayed_bars += 1
        print(f"[SIM] {symbol} {date_str}: replayed {replayed_bars} bars from "
              f"{path.name} (window {start_et}-{end_et}); "
              f"emitted {len(self.emitted_trades)} trades", flush=True)


# ════════════════════════════════════════════════════════════════════════
# Trade-line emission monkey-patch — wrap _close_position so we capture
# the trade record at close-time (the base method clears self.position).
# ════════════════════════════════════════════════════════════════════════
# Entry-time stamping: handled in SubBotSim.replay_ticks itself
# (had_pos transition detection covers both MOVE_STRIKE and REGIME_SHIFT
# entry paths). No monkey-patch needed.

_original_close_position = MoveStrikeSubBot._close_position

def _close_position_with_capture(self, reason: str, ref_price: float) -> None:
    """Wrap _close_position to record the closed trade before the
    position dict is wiped. Only active for SubBotSim instances."""
    p = self.position
    if not isinstance(self, SubBotSim) or p is None or p.exit_pending:
        return _original_close_position(self, reason, ref_price)
    qty_before = p.qty  # for partial-fill accounting later
    # Call the live close logic. In sim, _wait_for_fill always returns
    # the limit price + ordered qty, so we get a "FULL" path execution.
    _original_close_position(self, reason, ref_price)
    # After the close: self.position is None for FULL fills (sim path).
    # Use limit ≈ ref_price minus slip for trade record. The actual exit
    # price the bot used in P&L is reconstructable from the position's
    # fields BEFORE close, but those are gone now. Use ref_price as
    # exit_px — same convention simulate.py uses in its trade lines.
    if self.position is None:  # full close
        # Realistic-fill model (2026-06-30): a marketable SELL fills at the
        # prevailing bid ≈ ref_price (the price that triggered the exit), NOT
        # at the ref-minus-slip limit. Filling at ref-slip over-states exit
        # slippage symmetrically with the old entry pessimism. Keep the
        # slip model only when realistic fill is disabled.
        if os.getenv("WB_SUBBOT_SIM_REALISTIC_FILL", "1") == "1":
            exit_px = round(ref_price, 4)
        else:
            slip = max(0.05, ref_price * 0.005)
            exit_px = round(ref_price - slip, 2)
        self._record_closed_trade(p, exit_px, reason)

MoveStrikeSubBot._close_position = _close_position_with_capture


# ════════════════════════════════════════════════════════════════════════
# Regime-shift partial capture — at partial fire, record a trade record
# for the partial leg too, so the harness sees the full close history.
# ════════════════════════════════════════════════════════════════════════
_original_fire_partial = MoveStrikeSubBot._fire_regime_shift_partial

def _fire_partial_with_capture(self, p: SubPosition, ref_price: float) -> None:
    """Wrap partial scale-out fire — record the partial-leg trade."""
    if not isinstance(self, SubBotSim) or p is None:
        return _original_fire_partial(self, p, ref_price)
    qty_before = p.qty
    _original_fire_partial(self, p, ref_price)
    qty_partial = qty_before - (p.qty if self.position else 0)
    if qty_partial > 0 and self.position is not None:
        # Emit the partial leg as its own trade record. exit_px reconstructed.
        slip = max(0.05, ref_price * 0.005)
        exit_px = round(ref_price - slip, 2)
        # Build a "snapshot" SubPosition for the recorder — same fields
        # but with qty=qty_partial.
        snap = SubPosition(
            symbol=p.symbol, entry=p.entry, stop=p.stop, r=p.r,
            qty=qty_partial, score=p.score, time_et=p.entry_time_et,
            is_reentry=p.is_reentry, reentry_tag=p.reentry_tag,
            setup_type=p.setup_type,
        )
        snap.fill_entry_price = p.fill_entry_price
        self._record_closed_trade(snap, exit_px, "regime_shift_partial")

MoveStrikeSubBot._fire_regime_shift_partial = _fire_partial_with_capture


# ════════════════════════════════════════════════════════════════════════
# CLI main()
# ════════════════════════════════════════════════════════════════════════
TRADE_LINE_TEMPLATE = (
    "    1  {time:>5s}  {entry:>7.4f}  {stop:>7.4f}  {r:>6.4f}  "
    "{score:>5.1f}  {exit:>7.4f}  {reason:<30s} {pnl:+d}  setup={setup}"
)


def emit_trade_lines(sim: SubBotSim) -> None:
    """Print trades in a TRADE_LINE_RE-compatible format so
    replay_live_universe.py (and a future replay_subbot_universe.py)
    can parse them via existing regex. The `setup=` suffix (added
    2026-05-28 for Phase 3 FT attribution) is parsed by the updated
    TRADE_LINE_RE; absence is tolerated (backwards-compatible)."""
    for t in sim.emitted_trades:
        print(TRADE_LINE_TEMPLATE.format(
            time=t["time"], entry=t["entry"], stop=t["stop"], r=t["r"],
            score=t["score"], exit=t["exit"], reason=t["reason"], pnl=t["pnl"],
            setup=t.get("setup") or "move_strike",
        ), flush=True)


def main():
    p = argparse.ArgumentParser(description="Sub-bot tick-replay backtest harness.")
    p.add_argument("symbol", help="Ticker symbol (e.g. AMSS)")
    p.add_argument("date", help="YYYY-MM-DD")
    p.add_argument("start", help="HH:MM ET")
    p.add_argument("end", help="HH:MM ET")
    p.add_argument("--ticks", action="store_true",
                   help="Tick mode (the only mode for sub-bot replay)")
    p.add_argument("--tick-cache", default="tick_cache/",
                   help="Root directory for the tick cache")
    p.add_argument("--slippage", type=float, default=0.07,
                   help="Slippage in dollars (entry-only; exits use ref-price-minus-slip).")
    p.add_argument("--no-fundamentals", action="store_true",
                   help="Skip Alpaca fundamentals lookup (always-on in sub-bot sim).")
    p.add_argument("--bars", action="store_true",
                   help="Replay from the recorded live bar_stream (trade-for-trade "
                        "parity) instead of rebuilding bars from the full tick cache.")
    p.add_argument("--variant", default="A",
                   help="bar_stream variant suffix to replay (A or C). --bars only.")
    args = p.parse_args()

    if not args.ticks:
        print("[SIM] --ticks is required for sub-bot replay", flush=True)
        sys.exit(2)

    cache_root = Path(args.tick_cache).resolve()
    print(f"  Symbols: {args.symbol}  |  Date: {args.date}  "
          f"|  Window: {args.start} -> {args.end} ET"
          f"{'  [BARS]' if args.bars else ''}", flush=True)
    print("=" * 72, flush=True)
    print()

    sim = SubBotSim()
    if args.bars:
        print(f"Replaying {args.symbol} via SubBotSim from bar_stream "
              f"(variant {args.variant})...", flush=True)
        sim.replay_bars(args.symbol, args.date, args.start, args.end, args.variant)
    else:
        print(f"Replaying {args.symbol} via SubBotSim (cache={cache_root})...", flush=True)
        sim.replay_ticks(args.symbol, args.date, args.start, args.end, cache_root)

    print()
    print("=" * 72, flush=True)
    print(f"  TRADES")
    print("=" * 72, flush=True)
    emit_trade_lines(sim)
    print()
    print(f"  Trades: {len(sim.emitted_trades)}", flush=True)
    total_pnl = sum(t["pnl"] for t in sim.emitted_trades)
    wins = [t for t in sim.emitted_trades if t["pnl"] > 0]
    print(f"  Total P&L: ${total_pnl:+,}  |  Wins: {len(wins)} / {len(sim.emitted_trades)}", flush=True)


if __name__ == "__main__":
    main()
