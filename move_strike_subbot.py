"""move_strike_subbot.py — Setup B paper sub-bot (2026-05-20).

Runs alongside warrior_bot_v2/bot_v3_hybrid.py to A/B-test the MOVE_STRIKE
entry + HWM exit strategy on the SAME tick stream the main bot processes.

Data flow:
    main bot (IBKR) → engine_publisher Unix socket → THIS BOT → Alpaca exec
                                                     ↓
                                             squeeze_detector → movement_strike
                                                     ↓
                                                position open
                                                     ↓
                                              hwm_exit checks per tick

No IBKR session (no 10197 competing-session risk). No second data feed.
Different Alpaca paper account (sub-bot keys) so the A/B is clean.

Scope deliberately narrow:
  - No resume from disk; fresh start each session.
  - One concurrent position (no portfolio cap juggling).
  - Watchlist inferred from incoming tick symbols (no separate poller).
  - No partials / runners — full position closes on first exit signal.

Strategy logic ports cleanly:
  - Arm: SqueezeDetectorV2 (same as main bot)
  - Strike: MovementStrike (2× avg-body anomaly with arm-reset)
  - Exit: HWM trail (25→50% adaptive HH) + stop-prox bail + hard stop

Env contract:
  ENGINE_IPC_SOCKET             — defaults to /tmp/warrior_engine.sock
  WB_BT_MOVE_STRIKE             — must be 1 to enable arm→strike flow
  WB_BT_MOVE_HWM_EXIT           — must be 1 to enable HWM exit
  WB_BT_MOVE_*                  — full HWM/strike config (see hwm_exit.py
                                  and movement_strike.py)
  WB_SUBBOT_APCA_API_KEY_ID     — sub-bot Alpaca paper account
  WB_SUBBOT_APCA_API_SECRET_KEY
  WB_SUBBOT_RISK_DOLLARS        — default $1000 per trade
"""

from __future__ import annotations

import json
import os
import signal
import socket
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional

# ── Imports of project modules ────────────────────────────────────────
from engine_ipc import (
    DEFAULT_SOCKET_PATH,
    TickMessage,
    decode,
)
from squeeze_detector_v2 import SqueezeDetectorV2 as SqueezeDetector
from movement_strike import MovementStrike
from hwm_exit import HWMExitConfig, evaluate as hwm_evaluate
from bars import TradeBarBuilder

# Alpaca SDK (already in project venv per existing sub-bot)
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


ET = timezone(timedelta(hours=-4))  # EDT; for May 2026


# ══════════════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════════════
SOCKET_PATH = os.getenv("ENGINE_IPC_SOCKET", DEFAULT_SOCKET_PATH)
RISK_DOLLARS = float(os.getenv("WB_SUBBOT_RISK_DOLLARS", "1000"))
PROBE_SIZE_MULT = float(os.getenv("WB_SQ_PROBE_SIZE_MULT", "0.5"))
MAX_NOTIONAL = float(os.getenv("WB_MAX_NOTIONAL", "50000"))
MAX_SHARES = int(os.getenv("WB_MAX_SHARES", "100000"))
LOG_TAG = "[MOVE_SUB]"


def now_iso_et() -> str:
    return datetime.now(ET).strftime("%H:%M:%S")


def now_minute_et() -> int:
    et = datetime.now(ET)
    return et.hour * 60 + et.minute


# ══════════════════════════════════════════════════════════════════════
# Position state
# ══════════════════════════════════════════════════════════════════════
class SubPosition:
    """Single-position-at-a-time state holder for the sub-bot."""

    __slots__ = (
        "symbol", "entry", "stop", "r", "qty", "score",
        "peak", "peak_time", "cum_low", "entry_time_et",
        "entry_time_min", "hh_count", "prev_bar_high",
        "order_id_buy", "order_id_sell", "is_reentry", "reentry_tag",
    )

    def __init__(self, symbol: str, entry: float, stop: float, r: float,
                 qty: int, score: float, time_et: str,
                 is_reentry: bool = False, reentry_tag: str = ""):
        self.symbol = symbol
        self.entry = entry
        self.stop = stop
        self.r = r
        self.qty = qty
        self.score = score
        self.peak = entry
        self.peak_time = time_et
        self.cum_low = entry
        self.entry_time_et = time_et
        et = datetime.now(ET)
        self.entry_time_min = et.hour * 60 + et.minute
        self.hh_count = 0
        self.prev_bar_high = 0.0
        self.order_id_buy: Optional[str] = None
        self.order_id_sell: Optional[str] = None
        self.is_reentry = is_reentry
        self.reentry_tag = reentry_tag


# ══════════════════════════════════════════════════════════════════════
# Sub-bot core
# ══════════════════════════════════════════════════════════════════════
class MoveStrikeSubBot:
    def __init__(self):
        # Per-symbol state
        self.detectors: dict[str, SqueezeDetector] = {}
        self.move_strikes: dict[str, MovementStrike] = {}
        self.prev_arm_state: dict[str, object] = {}
        # Single bar builder driven by all symbols' ticks. Callback wired
        # explicitly per TradeBarBuilder's API.
        self.bar_builder = TradeBarBuilder(
            on_bar_close=self._on_bar_close_internal,
            et_tz=ET,
            interval_seconds=60,
        )
        # Position
        self.position: Optional[SubPosition] = None
        # HWM config (read env once)
        self.hwm_cfg = HWMExitConfig()
        # Movement-strike config
        self.move_lookback = int(os.getenv("WB_BT_MOVE_LOOKBACK", "5"))
        self.move_mult = float(os.getenv("WB_BT_MOVE_MULT", "2.0"))
        self.move_stop_lookback = int(os.getenv("WB_BT_MOVE_STOP_LOOKBACK", "10"))
        self.move_chase_cap_pct = float(os.getenv("WB_BT_MOVE_CHASE_PCT", "2.0"))
        # Alpaca broker
        self.alpaca: Optional[TradingClient] = None
        self._init_alpaca()
        # Daily P&L tracking
        self.daily_pnl = 0.0
        self.daily_trades_closed = 0
        # Stats
        self.ticks_received = 0
        self.symbols_seen: set[str] = set()
        # Per-symbol HH-count state (only matters once a position is open)
        # We pre-track on each bar so HH is correct at any moment.
        self._sym_prev_bar_high: dict[str, float] = {}
        self._sym_hh_count: dict[str, int] = defaultdict(int)
        # Re-entry config (2026-05-20 deploy) — GREEN mode chosen as winner.
        # BREAK kept gated for future flexibility. Cycle-reset semantics:
        # each fresh MOVE_STRIKE cycle gets its own re-entry budget;
        # re-entries don't.
        self.reentry_green = os.getenv("WB_BT_MOVE_REENTRY_GREEN", "0") == "1"
        self.reentry_break = os.getenv("WB_BT_MOVE_REENTRY_BREAK", "0") == "1"
        self.reentry_lookback = int(os.getenv("WB_BT_MOVE_REENTRY_LOOKBACK", "10"))
        self.reentry_window_min = float(os.getenv("WB_BT_MOVE_REENTRY_WINDOW_MIN", "30"))
        self.reentry_max_per_sym = int(os.getenv("WB_BT_MOVE_REENTRY_MAX_PER_SYM", "1"))
        # Per-symbol watch state: {symbol → {"high","stop","expires_min"}}
        self._reentry_watches: dict[str, dict] = {}
        # Persistent per-symbol counter — survives watch pop so the cap
        # is enforced across multiple close→watch cycles within one
        # MOVE_STRIKE cycle.
        self._reentry_count_per_symbol: dict[str, int] = {}
        # Per-symbol bar history for re-entry watch snapshot. Deque so
        # we can take the last N efficiently. Bar dicts mirror sim format.
        from collections import deque
        self._bar_history_per_sym: dict[str, deque] = {}
        self._bar_history_maxlen = max(20, self.reentry_lookback * 2)
        # Shutdown
        self._stop = False
        # Diagnostic — how many bars built per symbol
        self._bars_per_sym: dict[str, int] = defaultdict(int)

    def _init_alpaca(self) -> None:
        key = os.getenv("WB_SUBBOT_APCA_API_KEY_ID") or os.getenv("APCA_API_KEY_ID")
        secret = (
            os.getenv("WB_SUBBOT_APCA_API_SECRET_KEY")
            or os.getenv("APCA_API_SECRET_KEY")
        )
        if not key or not secret:
            print(f"{LOG_TAG} FATAL: no Alpaca credentials in env", flush=True)
            sys.exit(1)
        self.alpaca = TradingClient(key, secret, paper=True)
        try:
            acct = self.alpaca.get_account()
            print(
                f"{LOG_TAG} Alpaca PAPER connected — "
                f"account={acct.account_number} equity=${float(acct.equity):,.0f}",
                flush=True,
            )
        except Exception as e:
            print(f"{LOG_TAG} FATAL: Alpaca auth failed: {e!r}", flush=True)
            sys.exit(1)

    # ──────────────────────────────────────────────────────────────────
    # Setup wiring per symbol (lazy on first tick)
    # ──────────────────────────────────────────────────────────────────
    def _ensure_symbol(self, symbol: str) -> None:
        if symbol in self.detectors:
            return
        det = SqueezeDetector()
        det.symbol = symbol
        self.detectors[symbol] = det
        self.move_strikes[symbol] = MovementStrike(
            lookback_bars=self.move_lookback,
            multiplier=self.move_mult,
            stop_lookback_bars=self.move_stop_lookback,
        )
        self.prev_arm_state[symbol] = None
        self.symbols_seen.add(symbol)
        print(
            f"{LOG_TAG} [{now_iso_et()}] new symbol {symbol} — detector + "
            f"movement_strike instantiated",
            flush=True,
        )

    # ──────────────────────────────────────────────────────────────────
    # Bar-close hook (called by TradeBarBuilder when a 1m bar closes)
    # ──────────────────────────────────────────────────────────────────
    def _on_bar_close_internal(self, bar) -> None:
        """TradeBarBuilder calls this with a Bar dataclass.
        We dispatch to the per-symbol handler."""
        try:
            self.on_bar_close_1m(bar.symbol, bar)
        except Exception as e:
            print(
                f"{LOG_TAG} on_bar_close_1m error {bar.symbol}: {e!r}", flush=True
            )

    def on_bar_close_1m(self, symbol: str, bar) -> None:
        """``bar`` is a Bar dataclass with .open/.high/.low/.close/.volume."""
        self._bars_per_sym[symbol] += 1
        self._ensure_symbol(symbol)
        det = self.detectors[symbol]
        try:
            vwap = self.bar_builder.get_vwap(symbol)
        except Exception:
            vwap = None
        # Feed the detector — this can set det.armed if conditions met.
        # Detector reads bar.open/high/low/close/volume directly.
        try:
            det.on_bar_close_1m(bar, vwap=vwap)
        except Exception as e:
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} det.on_bar_close error: {e!r}",
                flush=True,
            )
        # Detect arm transition (None → armed) to reset movement_strike
        prev = self.prev_arm_state.get(symbol)
        if det.armed is not None and prev is None:
            self.move_strikes[symbol].reset_history()
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} ARMED "
                f"entry={det.armed.trigger_high:.4f} stop={det.armed.stop_low:.4f} "
                f"R={det.armed.r:.4f} score={det.armed.score:.1f} — "
                f"movement_strike history reset",
                flush=True,
            )
        self.prev_arm_state[symbol] = det.armed

        # HH tracking — global per-symbol (for an active position's exit)
        if self._sym_prev_bar_high.get(symbol, 0) > 0:
            if bar.high > self._sym_prev_bar_high[symbol]:
                self._sym_hh_count[symbol] += 1
            else:
                self._sym_hh_count[symbol] = 0
        self._sym_prev_bar_high[symbol] = bar.high

        # Update active position's HH counter if this is the held symbol
        if self.position is not None and self.position.symbol == symbol:
            self.position.hh_count = self._sym_hh_count[symbol]

        # Per-symbol bar history for re-entry watch snapshot.
        from collections import deque
        if symbol not in self._bar_history_per_sym:
            self._bar_history_per_sym[symbol] = deque(maxlen=self._bar_history_maxlen)
        self._bar_history_per_sym[symbol].append({
            "o": bar.open, "h": bar.high, "l": bar.low,
            "c": bar.close, "v": bar.volume,
        })

        # GREEN re-entry trigger: at bar close, if no position AND watch
        # exists for this symbol AND bar is green (close > open) → fire.
        if (self.position is None and self.reentry_green
                and symbol in self._reentry_watches
                and bar.close > bar.open):
            self._try_fire_green_reentry(symbol, bar)

    # ──────────────────────────────────────────────────────────────────
    # Per-tick processing
    # ──────────────────────────────────────────────────────────────────
    def on_tick(self, symbol: str, price: float, ts_iso: str, size: int) -> None:
        self.ticks_received += 1
        self._ensure_symbol(symbol)
        # Bar builder needs a datetime, not the ISO string
        try:
            ts = datetime.fromisoformat(ts_iso)
        except Exception:
            ts = datetime.now(timezone.utc)
        # Feed the bar builder (triggers our on_bar_close_1m via callback)
        try:
            self.bar_builder.on_trade(symbol, price, size, ts)
        except Exception as e:
            print(
                f"{LOG_TAG} bar_builder error on {symbol}: {e!r}", flush=True
            )

        # If we have an open position, run HWM exit checks
        if self.position is not None and self.position.symbol == symbol:
            self._maintain_position(price)
            # If we just closed in _maintain_position, return — don't
            # also evaluate a new entry on the same tick.
            if self.position is None:
                return

        # If no position, check for new entry
        if self.position is None:
            self._maybe_enter(symbol, price)

    # ──────────────────────────────────────────────────────────────────
    # Re-entry helpers (GREEN mode + cycle reset, 2026-05-20)
    # ──────────────────────────────────────────────────────────────────
    def _register_reentry_watch(self, t: SubPosition) -> None:
        """Called after a position closes. Sets up a re-entry watch if
        the cap allows. Cycle semantics: a fresh MOVE_STRIKE exit resets
        the per-symbol count to 0 (new cycle); a re-entry exit does not."""
        if not (self.reentry_green or self.reentry_break):
            return
        # Cycle reset on fresh MOVE_STRIKE (non-reentry) exit
        if not t.is_reentry:
            self._reentry_count_per_symbol[t.symbol] = 0
        # Cap check
        if self._reentry_count_per_symbol.get(t.symbol, 0) >= self.reentry_max_per_sym:
            return
        bars = self._bar_history_per_sym.get(t.symbol)
        if not bars:
            return
        last_n = list(bars)[-self.reentry_lookback:]
        if len(last_n) < 3:
            return
        high = max(b["h"] for b in last_n)
        low = min(b["l"] for b in last_n)
        self._reentry_watches[t.symbol] = {
            "high": high,
            "stop": low,
            "expires_min": now_minute_et() + self.reentry_window_min,
        }
        print(
            f"{LOG_TAG} [{now_iso_et()}] {t.symbol} REENTRY WATCH set: "
            f"high={high:.3f} stop={low:.3f} "
            f"expires_in={int(self.reentry_window_min)}min",
            flush=True,
        )

    def _try_fire_green_reentry(self, symbol: str, bar) -> None:
        """At bar close, if watch exists and bar is green, fire re-entry."""
        watch = self._reentry_watches.get(symbol)
        if watch is None:
            return
        if now_minute_et() > watch["expires_min"]:
            self._reentry_watches.pop(symbol, None)
            return
        # Guard: bar.close must clear the snapshotted stop (otherwise
        # we'd immediately stop out).
        if bar.close <= watch["stop"]:
            return
        entry_price = bar.close
        stop = watch["stop"]
        r = entry_price - stop
        if r <= 0:
            return
        qty = self._compute_qty(entry_price, r, 99.0)
        if qty <= 0:
            return
        # Open re-entry position. Same code path as primary open but
        # tagged so the close handler knows not to reset the count.
        self._open_position_with_tag(
            symbol, entry_price, stop, r, qty, 99.0,
            is_reentry=True, reentry_tag="GREEN",
        )
        self._reentry_count_per_symbol[symbol] = (
            self._reentry_count_per_symbol.get(symbol, 0) + 1
        )
        self._reentry_watches.pop(symbol, None)

    def _maintain_position(self, price: float) -> None:
        p = self.position
        if price > p.peak:
            p.peak = price
            p.peak_time = now_iso_et()
        if price < p.cum_low:
            p.cum_low = price
        # Sync HH count from per-symbol tracker (updated on bar closes)
        p.hh_count = self._sym_hh_count.get(p.symbol, 0)

        decision = hwm_evaluate(p, price, now_minute_et(), self.hwm_cfg)
        if decision is None:
            return
        reason, exit_price = decision
        self._close_position(reason, exit_price)

    def _maybe_enter(self, symbol: str, price: float) -> None:
        det = self.detectors.get(symbol)
        if det is None or det.armed is None:
            return
        ms = self.move_strikes[symbol]
        bar_minute = now_minute_et()
        if not ms.update_and_check(price, bar_minute):
            return
        # Movement anomaly fired. Apply guardrails matching simulate.py
        # MOVE_STRIKE branch:
        #   - stop = consolidation low of last N closed bars
        #   - entry = anomaly tick price
        #   - skip if entry below stop (would immediately stop out)
        #   - skip if trigger > arm × (1 + chase_cap)  (gap too wide)
        cons_stop = ms.get_consolidation_stop()
        if cons_stop is None or price <= cons_stop:
            return
        arm_price = det.armed.entry_price or 0.0
        if arm_price > 0:
            gap_above_arm = (price - arm_price) / arm_price * 100.0
            if gap_above_arm > self.move_chase_cap_pct:
                print(
                    f"{LOG_TAG} [{now_iso_et()}] {symbol} CHASE-SKIP "
                    f"trigger={price:.3f} arm={arm_price:.3f} "
                    f"gap={gap_above_arm:.2f}%",
                    flush=True,
                )
                # Consume the arm so we don't try again on every tick
                det.armed = None
                self.prev_arm_state[symbol] = None
                return
        r = price - cons_stop
        if r <= 0:
            return
        qty = self._compute_qty(price, r, det.armed.score)
        if qty <= 0:
            return
        self._open_position(symbol, price, cons_stop, r, qty, det.armed.score)
        # Consume the arm
        det.armed = None
        self.prev_arm_state[symbol] = None

    def _compute_qty(self, price: float, r: float, score: float) -> int:
        qty_risk = int(RISK_DOLLARS / max(r, 0.01))
        qty_notional = int(MAX_NOTIONAL / max(price, 0.01))
        qty = min(qty_risk, qty_notional, MAX_SHARES)
        # Probe sizing per main bot convention
        qty = max(1, int(qty * PROBE_SIZE_MULT))
        return qty

    # ──────────────────────────────────────────────────────────────────
    # Order submission
    # ──────────────────────────────────────────────────────────────────
    def _open_position(self, symbol: str, entry: float, stop: float,
                       r: float, qty: int, score: float) -> None:
        """Primary entry from MOVE_STRIKE arm + anomaly fire."""
        self._open_position_with_tag(
            symbol, entry, stop, r, qty, score,
            is_reentry=False, reentry_tag="",
        )

    def _open_position_with_tag(
        self, symbol: str, entry: float, stop: float,
        r: float, qty: int, score: float,
        is_reentry: bool, reentry_tag: str,
    ) -> None:
        slip = max(0.07, entry * 0.01)
        limit = round(entry + slip, 2)
        tag_str = f" REENTRY({reentry_tag})" if is_reentry else ""
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🟩 ENTRY{tag_str} {symbol} qty={qty} "
            f"limit=${limit:.2f} (anomaly@${entry:.2f}) stop=${stop:.2f} "
            f"R=${r:.4f} score={score:.1f}",
            flush=True,
        )
        try:
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
        except Exception as e:
            print(f"{LOG_TAG} ENTRY REJECT {symbol}: {e!r}", flush=True)
            return
        self.position = SubPosition(
            symbol=symbol, entry=entry, stop=stop, r=r, qty=qty,
            score=score, time_et=now_iso_et(),
            is_reentry=is_reentry, reentry_tag=reentry_tag,
        )
        self.position.order_id_buy = str(order.id) if hasattr(order, "id") else None
        # Sync HH count from current per-symbol tracker
        self.position.hh_count = self._sym_hh_count.get(symbol, 0)

    def _close_position(self, reason: str, ref_price: float) -> None:
        p = self.position
        if p is None:
            return
        # Exit SELL LIMIT slightly below current price for likely fill
        # (sub-bot mirrors main bot's never-market-order rule).
        slip = max(0.05, ref_price * 0.005)
        limit = round(ref_price - slip, 2)
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🟥 EXIT {p.symbol} qty={p.qty} "
            f"limit=${limit:.2f} (ref=${ref_price:.2f}) reason={reason}",
            flush=True,
        )
        try:
            req = LimitOrderRequest(
                symbol=p.symbol, qty=p.qty, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
            p.order_id_sell = str(order.id) if hasattr(order, "id") else None
        except Exception as e:
            print(f"{LOG_TAG} EXIT REJECT {p.symbol}: {e!r}", flush=True)
        # Book the P&L approximation (entry → ref_price, not actual fills)
        approx_pnl = (ref_price - p.entry) * p.qty
        self.daily_pnl += approx_pnl
        self.daily_trades_closed += 1
        print(
            f"{LOG_TAG} approx P&L={approx_pnl:+,.0f} daily={self.daily_pnl:+,.0f} "
            f"(trade #{self.daily_trades_closed})",
            flush=True,
        )
        # Set up re-entry watch (cycle reset is inside _register_reentry_watch).
        # Done BEFORE clearing self.position so the position fields are
        # still valid in the snapshot.
        self._register_reentry_watch(p)
        self.position = None

    # ──────────────────────────────────────────────────────────────────
    # Socket consumer loop
    # ──────────────────────────────────────────────────────────────────
    def consume(self) -> None:
        sock = self._connect_with_retry()
        if sock is None:
            print(f"{LOG_TAG} could not connect to engine — exiting", flush=True)
            return
        buf = b""
        last_stats = time.time()
        while not self._stop:
            try:
                chunk = sock.recv(65536)
            except (ConnectionResetError, OSError) as e:
                print(f"{LOG_TAG} socket recv error: {e!r} — reconnecting", flush=True)
                try:
                    sock.close()
                except Exception:
                    pass
                sock = self._connect_with_retry()
                if sock is None:
                    return
                buf = b""
                continue
            if not chunk:
                print(f"{LOG_TAG} socket closed by peer — reconnecting", flush=True)
                try:
                    sock.close()
                except Exception:
                    pass
                sock = self._connect_with_retry()
                if sock is None:
                    return
                buf = b""
                continue
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    msg = decode(line)
                except Exception as e:
                    print(f"{LOG_TAG} decode error: {e!r} on {line[:120]!r}", flush=True)
                    continue
                self._dispatch(msg)
            # Periodic stats
            if time.time() - last_stats > 60:
                print(
                    f"{LOG_TAG} [{now_iso_et()}] STATS ticks={self.ticks_received} "
                    f"symbols={len(self.symbols_seen)} pos={'YES' if self.position else 'no'} "
                    f"daily_pnl={self.daily_pnl:+,.0f}",
                    flush=True,
                )
                last_stats = time.time()

    def _connect_with_retry(self) -> Optional[socket.socket]:
        attempt = 0
        while not self._stop:
            attempt += 1
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.connect(SOCKET_PATH)
                print(
                    f"{LOG_TAG} [{now_iso_et()}] connected to engine "
                    f"({SOCKET_PATH}) attempt={attempt}",
                    flush=True,
                )
                return s
            except (FileNotFoundError, ConnectionRefusedError, OSError) as e:
                if attempt == 1:
                    print(
                        f"{LOG_TAG} engine socket not ready yet ({e!r}) — "
                        f"retrying every 2s",
                        flush=True,
                    )
                time.sleep(2)
        return None

    def _dispatch(self, msg) -> None:
        # Hello frames from the publisher come as a plain dict
        if isinstance(msg, dict) and msg.get("type") == "hello":
            print(f"{LOG_TAG} engine hello: {msg}", flush=True)
            return
        if isinstance(msg, TickMessage):
            self.on_tick(msg.symbol, msg.price, msg.ts, msg.size)


def main():
    # Strict gate checks — abort if MOVE_STRIKE/HWM aren't enabled.
    if os.getenv("WB_BT_MOVE_STRIKE", "0") != "1":
        print(f"{LOG_TAG} FATAL: WB_BT_MOVE_STRIKE != 1; refusing to start", flush=True)
        sys.exit(1)
    if os.getenv("WB_BT_MOVE_HWM_EXIT", "0") != "1":
        print(f"{LOG_TAG} FATAL: WB_BT_MOVE_HWM_EXIT != 1; refusing to start", flush=True)
        sys.exit(1)
    bot = MoveStrikeSubBot()

    def _shutdown(signum, frame):
        print(f"{LOG_TAG} signal {signum} received — stopping", flush=True)
        bot._stop = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    print(f"{LOG_TAG} starting consume loop", flush=True)
    bot.consume()
    print(f"{LOG_TAG} consume loop exited", flush=True)


if __name__ == "__main__":
    main()
