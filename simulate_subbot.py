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
from datetime import datetime, timezone
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
# CRITICAL for sim correctness: disable live's seed-from-cache behavior.
# In live, the sub-bot reads today's tick_cache on first subscription to
# warm up detectors. In sim, my replay_ticks() IS the tick stream — if
# seed is on, the bot double-counts: cache replay fires entries on
# historical highs, then the live-replayed ticks immediately stop them out.
# Seen during smoke: AMSS seeded at $10 peak, fired regime_shift entry,
# then first real replayed tick at $7.11 stopped it -$730.
os.environ.setdefault("WB_SUBBOT_SEED_FROM_CACHE", "0")

from move_strike_subbot import MoveStrikeSubBot, SubPosition, LOG_TAG  # noqa: E402


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

    def submit_order(self, order_data):
        self._counter += 1
        order_id = f"sim-{self._counter}"
        # alpaca-py LimitOrderRequest has: symbol, qty, side, limit_price, time_in_force, extended_hours
        self._orders[order_id] = {
            "symbol": order_data.symbol,
            "qty": int(order_data.qty),
            "side": str(order_data.side).split(".")[-1].upper(),  # "BUY" / "SELL"
            "limit_price": float(order_data.limit_price),
            "status": "FILLED",   # assume instant fill in sim
            "filled_qty": int(order_data.qty),
            "filled_avg_price": float(order_data.limit_price),
        }
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
        # Sim never needs broker positions — Lever 3 reconcile would only
        # fire if there was a sync mismatch, which can't happen here
        # because sim is the broker.
        return []


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

    # ─── trade-record emission ───────────────────────────────────────────
    def _record_closed_trade(self, p: SubPosition, exit_px: float, exit_reason: str):
        """Capture a closed trade in simulate.py-compatible format. Called
        from inside our consume/exit overrides; sub-bot's own close logic
        prints its own log lines, but those don't survive into the
        replay harness's TRADE_LINE_RE parser."""
        entry_basis = p.fill_entry_price if p.fill_entry_price is not None else p.entry
        pnl = int(round((exit_px - entry_basis) * p.qty))
        rec = {
            "time": self._current_time_str_et[:5],  # HH:MM
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
        try:
            with gzip.open(cache_path, "rt") as f:
                ticks = json.load(f)
        except (gzip.BadGzipFile, OSError, EOFError) as e:
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
            # Update our notion of "now" for trade-record stamping.
            self._current_minute_et = cur_min
            self._current_time_str_et = ts_et.strftime("%H:%M:%S")
            # Feed the tick through the sub-bot's normal pipeline.
            # NOTE: on_tick takes an ISO string; we re-stringify for safety.
            try:
                self.on_tick(symbol, p, ts.isoformat(), s)
            except Exception as e:
                # Don't crash the whole replay on one tick failure;
                # just log + continue.
                print(f"[SIM] {symbol} on_tick error: {e!r} (tick={tick})", flush=True)
                continue
            replayed += 1
        # NOTE: TradeBarBuilder has no flush API — the last in-flight bar
        # won't fire its on_bar_close callback. Acceptable: a partial
        # last-bar wouldn't trigger valid signals anyway (live bot also
        # only acts on CLOSED bars). Documented as a deliberate gap.
        print(f"[SIM] {symbol} {date_str}: replayed {replayed} ticks "
              f"(skipped {skipped_window} outside window {start_et}-{end_et}); "
              f"emitted {len(self.emitted_trades)} trades", flush=True)


# ════════════════════════════════════════════════════════════════════════
# Trade-line emission monkey-patch — wrap _close_position so we capture
# the trade record at close-time (the base method clears self.position).
# ════════════════════════════════════════════════════════════════════════
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
        # Reconstruct the exit price the bot used: it was the limit
        # passed to MockAlpaca, but we don't have a back-reference here.
        # Approximate as ref_price - slip (matches live's _close_position
        # exit-limit formula at line ~1265: ref_price - max(0.05, ref*0.005)).
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
    "{score:>5.1f}  {exit:>7.4f}  {reason:<30s} {pnl:+d}"
)


def emit_trade_lines(sim: SubBotSim) -> None:
    """Print trades in a TRADE_LINE_RE-compatible format so
    replay_live_universe.py (and a future replay_subbot_universe.py)
    can parse them via existing regex."""
    for t in sim.emitted_trades:
        print(TRADE_LINE_TEMPLATE.format(
            time=t["time"], entry=t["entry"], stop=t["stop"], r=t["r"],
            score=t["score"], exit=t["exit"], reason=t["reason"], pnl=t["pnl"],
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
    args = p.parse_args()

    if not args.ticks:
        print("[SIM] --ticks is required for sub-bot replay", flush=True)
        sys.exit(2)

    cache_root = Path(args.tick_cache).resolve()
    print(f"  Symbols: {args.symbol}  |  Date: {args.date}  "
          f"|  Window: {args.start} -> {args.end} ET", flush=True)
    print("=" * 72, flush=True)
    print()
    print(f"Replaying {args.symbol} via SubBotSim (cache={cache_root})...", flush=True)

    sim = SubBotSim()
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
