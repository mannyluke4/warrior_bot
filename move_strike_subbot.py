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

# Load .env BEFORE we read any APCA_API_* env vars. daily_run_v3.sh only
# injects credentials inline for the main bot launch — the sub-bot has
# to source its own (2026-05-21 fix).
from dotenv import load_dotenv
load_dotenv()

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
        "fill_entry_price", "fill_entry_qty",
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
        # Actual fills (populated by _wait_for_fill after order submit).
        self.fill_entry_price: Optional[float] = None
        self.fill_entry_qty: Optional[int] = None


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
        # Same-bar block (2026-05-21): refuse to re-enter on the bar we
        # just exited. Sim-validated, mirrors Manny's day-trading principle.
        self.reentry_block_same_bar = os.getenv("WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR", "1") == "1"
        # Stay-armed (2026-05-21): after a successful MOVE_STRIKE entry,
        # keep movement_strike monitoring continuously even when the
        # squeeze detector hasn't re-armed. With cool-down + continuation
        # gates to filter chop.
        self.move_stay_armed = os.getenv("WB_BT_MOVE_STAY_ARMED", "0") == "1"
        self.move_stay_armed_cooldown_min = float(os.getenv("WB_BT_MOVE_STAY_ARMED_COOLDOWN_MIN", "15"))
        self.move_stay_armed_min_gap_pct = float(os.getenv("WB_BT_MOVE_STAY_ARMED_MIN_GAP_PCT", "2.0"))
        self._move_stay_armed_symbols: set[str] = set()
        self._move_stay_armed_last_exit_min: dict[str, int] = {}
        self._move_stay_armed_last_exit_price: dict[str, float] = {}
        # Max-below-arm filter (2026-05-21): skip MOVE_STRIKE if price
        # has decayed too far below the real arm (PIII 2026-05-21 was
        # -5.6% below arm). Default 0 = off; set to 3.0 to enable.
        self.move_max_below_arm_pct = float(os.getenv("WB_BT_MOVE_MAX_BELOW_ARM_PCT", "0"))
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
        # Alpaca-aware limit pricing (2026-05-22). Mirrors main bot's
        # compute_alpaca_aware_limit() helper. Gated by WB_ALPACA_AWARE_LIMITS.
        self.alpaca_aware_limits = os.getenv("WB_ALPACA_AWARE_LIMITS", "0") == "1"

    def _wait_for_fill(self, order_id: str, timeout: int = 15):
        """Poll Alpaca for the order's fill. Returns (filled_avg_price, filled_qty)
        or (None, 0) on timeout/cancel/reject. Mirrors bot_v3_hybrid.py:1195
        wait_for_fill pattern."""
        if not order_id:
            return None, 0
        try:
            from alpaca.trading.enums import OrderStatus
        except Exception:
            OrderStatus = None
        for _ in range(timeout * 2):
            try:
                o = self.alpaca.get_order_by_id(order_id)
            except Exception:
                o = None
            if o is not None:
                status = getattr(o, "status", None)
                status_val = status.value if hasattr(status, "value") else str(status)
                if status_val == "filled":
                    return float(o.filled_avg_price or 0), int(o.filled_qty or 0)
                if status_val in ("canceled", "cancelled", "expired", "rejected"):
                    return None, 0
            time.sleep(0.5)
        # Timeout — cancel and final check.
        try:
            self.alpaca.cancel_order_by_id(order_id)
        except Exception:
            pass
        try:
            o = self.alpaca.get_order_by_id(order_id)
        except Exception:
            o = None
        if o is not None:
            status = getattr(o, "status", None)
            status_val = status.value if hasattr(status, "value") else str(status)
            if status_val == "filled":
                return float(o.filled_avg_price or 0), int(o.filled_qty or 0)
        return None, 0

    def _compute_alpaca_aware_limit(self, symbol: str, signal_price: float,
                                     side: str, buffer_pct: float = 0.005) -> float:
        """Sub-bot copy of compute_alpaca_aware_limit (see bot_v3_hybrid.py:2775).
        For BUY: max(signal × (1+buffer), alpaca_ask × (1+buffer)).
        For SELL: min(signal × (1-buffer), alpaca_bid × (1-buffer)).
        Falls back to base on >5% divergence or quote failure."""
        side_u = side.upper()
        base_limit = round(signal_price * (1 + buffer_pct), 2) if side_u == "BUY" \
            else round(signal_price * (1 - buffer_pct), 2)
        if not self.alpaca_aware_limits or self.alpaca_data is None:
            return base_limit
        try:
            from alpaca.data.requests import StockLatestQuoteRequest
            q_resp = self.alpaca_data.get_stock_latest_quote(
                StockLatestQuoteRequest(symbol_or_symbols=symbol)
            )
            q = q_resp.get(symbol) if isinstance(q_resp, dict) else None
            if q is None:
                return base_limit
            if side_u == "BUY":
                alpaca_ref = float(q.ask_price) if getattr(q, "ask_price", None) else None
            else:
                alpaca_ref = float(q.bid_price) if getattr(q, "bid_price", None) else None
            if alpaca_ref is None or signal_price <= 0:
                return base_limit
            if abs(alpaca_ref - signal_price) / signal_price > 0.05:
                print(f"{LOG_TAG} ALPACA_QUOTE_DIVERGENT {symbol}: "
                      f"alpaca_ref={alpaca_ref:.4f} signal={signal_price:.4f} "
                      f">5% gap, using base", flush=True)
                return base_limit
            if side_u == "BUY":
                return round(max(base_limit, alpaca_ref * (1 + buffer_pct)), 2)
            return round(min(base_limit, alpaca_ref * (1 - buffer_pct)), 2)
        except Exception as e:
            print(f"{LOG_TAG} ALPACA_AWARE_FAIL {symbol}: {e!r} — using base", flush=True)
            return base_limit

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
        # Separate data client for latest-quote lookups (Alpaca-aware
        # limit pricing). Falls back to None if init fails — helper
        # gracefully returns base limit when data_client is None.
        try:
            from alpaca.data.historical import StockHistoricalDataClient
            self.alpaca_data = StockHistoricalDataClient(key, secret)
        except Exception as e:
            print(f"{LOG_TAG} WARN: Alpaca data client init failed: {e!r}", flush=True)
            self.alpaca_data = None
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
        # Seed from tick cache (2026-05-22 per p0_go_live_stack item 3).
        # If main bot has been running and writing tick_cache for this
        # symbol, replay those ticks through our detector + bar builder
        # so a sub-bot restart mid-session doesn't start blind. Gated by
        # WB_SUBBOT_SEED_FROM_CACHE (default 1).
        if os.getenv("WB_SUBBOT_SEED_FROM_CACHE", "1") == "1":
            self._seed_symbol_from_cache(symbol)

    def _seed_symbol_from_cache(self, symbol: str) -> None:
        """Replay today's tick_cache for `symbol` through the detector +
        bar builder + movement_strike. Mirrors main bot's
        seed_symbol_from_cache (bot_v3_hybrid.py:1823). Idempotent — call
        on first encounter of a symbol after a restart."""
        import gzip
        from datetime import datetime as _dt
        today = _dt.now(ET).strftime("%Y-%m-%d")
        cache_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "tick_cache", today, f"{symbol}.json.gz",
        )
        if not os.path.exists(cache_path):
            return
        try:
            with gzip.open(cache_path, "rt") as f:
                raw_ticks = json.load(f)
        except Exception as e:
            print(f"{LOG_TAG} SEED {symbol} cache read failed: {e!r}", flush=True)
            return
        if not raw_ticks:
            return
        # Cutoff: replay only ticks earlier than NOW (live ticks will
        # cover the rest as they arrive on the engine socket).
        now_utc = _dt.now(timezone.utc)
        replayed = 0
        try:
            det = self.detectors.get(symbol)
            if det is None:
                return
            # Suppress signals during seed if the detector supports it
            # (SqueezeDetector v1 doesn't; v2 has begin_seed/end_seed).
            seed_aware = hasattr(det, "begin_seed") and hasattr(det, "end_seed")
            if seed_aware:
                det.begin_seed()
            for tk in raw_ticks:
                try:
                    price = float(tk["p"])
                    size = int(tk.get("s") or 0)
                    ts_utc = _dt.fromisoformat(tk["t"])
                except (KeyError, ValueError, TypeError):
                    continue
                if ts_utc >= now_utc:
                    break  # don't seed into the future
                try:
                    # TradeBarBuilder.on_trade(symbol, price, size, ts) —
                    # the single shared bar_builder routes by symbol.
                    self.bar_builder.on_trade(symbol, price, size, ts_utc)
                except Exception:
                    pass
                replayed += 1
            if seed_aware:
                det.end_seed()
            print(
                f"{LOG_TAG} SEED {symbol} replayed {replayed:,} ticks from cache",
                flush=True,
            )
        except Exception as e:
            print(f"{LOG_TAG} SEED {symbol} failed: {e!r}", flush=True)

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
            # Same-bar guard: this minute is the exit bar. Block any
            # re-entry attempt that fires before bar_minute advances.
            "exit_bar_minute": now_minute_et(),
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
        cur_min = now_minute_et()
        if cur_min > watch["expires_min"]:
            self._reentry_watches.pop(symbol, None)
            return
        # Same-bar guard — don't re-enter on the bar we just exited.
        if (self.reentry_block_same_bar
                and cur_min <= watch.get("exit_bar_minute", -1)):
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
        if det is None:
            return
        # Real arm OR stay-armed mode (no detector arm, but symbol
        # previously fired MOVE_STRIKE today).
        has_real_arm = det.armed is not None
        stay_armed_active = (
            not has_real_arm
            and self.move_stay_armed
            and symbol in self._move_stay_armed_symbols
        )
        if not (has_real_arm or stay_armed_active):
            return
        ms = self.move_strikes[symbol]
        bar_minute = now_minute_et()
        if not ms.update_and_check(price, bar_minute):
            return
        cons_stop = ms.get_consolidation_stop()
        if cons_stop is None or price <= cons_stop:
            return
        # Real arm: apply chase cap + below-arm filter
        if has_real_arm:
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
                    det.armed = None
                    self.prev_arm_state[symbol] = None
                    return
                # Below-arm filter (PIII 2026-05-21 saved $670 on
                # backtest reconstruction).
                if self.move_max_below_arm_pct > 0:
                    below_arm_pct = (arm_price - price) / arm_price * 100.0
                    if below_arm_pct > self.move_max_below_arm_pct:
                        print(
                            f"{LOG_TAG} [{now_iso_et()}] {symbol} BELOW-ARM-SKIP "
                            f"trigger={price:.3f} arm={arm_price:.3f} "
                            f"below={below_arm_pct:.2f}% (cap={self.move_max_below_arm_pct}%)",
                            flush=True,
                        )
                        det.armed = None
                        self.prev_arm_state[symbol] = None
                        return
        # Stay-armed gates: cool-down + continuation %
        if stay_armed_active:
            last_min = self._move_stay_armed_last_exit_min.get(symbol, -10000)
            last_px = self._move_stay_armed_last_exit_price.get(symbol, 0.0)
            if (bar_minute - last_min) < self.move_stay_armed_cooldown_min:
                return  # within cooldown
            if last_px > 0 and price < last_px * (1.0 + self.move_stay_armed_min_gap_pct / 100.0):
                return  # not a continuation
        r = price - cons_stop
        if r <= 0:
            return
        if stay_armed_active:
            score = 50.0  # synthetic
        else:
            score = det.armed.score
        qty = self._compute_qty(price, r, score)
        if qty <= 0:
            return
        self._open_position(symbol, price, cons_stop, r, qty, score)
        # Mark stay-armed (any MOVE_STRIKE entry flags the symbol)
        if self.move_stay_armed:
            self._move_stay_armed_symbols.add(symbol)
        # Consume the arm (if real)
        if has_real_arm:
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
        base_limit = round(entry + slip, 2)
        # Alpaca-aware limit (2026-05-22): widen to alpaca_ask + buffer
        # when our IBKR-derived limit is below Alpaca's actual ask.
        aware_limit = self._compute_alpaca_aware_limit(symbol, entry, "BUY")
        limit = max(aware_limit, base_limit)
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
        # Wait for fill so we can book real entry price (2026-05-22).
        fill_px, fill_qty = self._wait_for_fill(self.position.order_id_buy, timeout=15)
        if fill_px is not None and fill_qty > 0:
            self.position.fill_entry_price = fill_px
            self.position.fill_entry_qty = fill_qty
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} entry FILLED "
                f"@ ${fill_px:.4f} qty={fill_qty} (limit was ${limit:.2f})",
                flush=True,
            )
            # If partial fill, shrink the position's qty so the exit
            # doesn't try to sell shares we don't own.
            if fill_qty < qty:
                self.position.qty = fill_qty
        else:
            # Order didn't fill (timeout/cancel/reject). Clear position
            # so we don't track ghost shares — and don't manage exits.
            print(
                f"{LOG_TAG} [{now_iso_et()}] {symbol} entry order NOT FILLED "
                f"(timeout/cancel/reject) — abandoning trade",
                flush=True,
            )
            self.position = None
            return
        # Sync HH count from current per-symbol tracker
        self.position.hh_count = self._sym_hh_count.get(symbol, 0)

    def _close_position(self, reason: str, ref_price: float) -> None:
        p = self.position
        if p is None:
            return
        # Exit SELL LIMIT slightly below current price for likely fill
        # (sub-bot mirrors main bot's never-market-order rule).
        slip = max(0.05, ref_price * 0.005)
        base_limit = round(ref_price - slip, 2)
        # Alpaca-aware sell limit (2026-05-22): tighten toward alpaca_bid
        # when our IBKR-derived sell limit is above Alpaca's actual bid.
        aware_limit = self._compute_alpaca_aware_limit(p.symbol, ref_price, "SELL")
        limit = min(aware_limit, base_limit)
        print(
            f"{LOG_TAG} [{now_iso_et()}] 🟥 EXIT {p.symbol} qty={p.qty} "
            f"limit=${limit:.2f} (ref=${ref_price:.2f}) reason={reason}",
            flush=True,
        )
        sell_fill_px = None
        sell_fill_qty = 0
        try:
            req = LimitOrderRequest(
                symbol=p.symbol, qty=p.qty, side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY, limit_price=limit,
                extended_hours=True,
            )
            order = self.alpaca.submit_order(order_data=req)
            p.order_id_sell = str(order.id) if hasattr(order, "id") else None
            sell_fill_px, sell_fill_qty = self._wait_for_fill(p.order_id_sell, timeout=15)
        except Exception as e:
            print(f"{LOG_TAG} EXIT REJECT {p.symbol}: {e!r}", flush=True)
        # Real-fill P&L (2026-05-22): use actual entry + exit fill prices when
        # both are known. Falls back to anomaly→ref approximation if either
        # fill price is missing (order didn't fill cleanly).
        entry_basis = p.fill_entry_price if p.fill_entry_price is not None else p.entry
        exit_basis = sell_fill_px if sell_fill_px is not None else ref_price
        qty_basis = sell_fill_qty if sell_fill_qty > 0 else p.qty
        real_pnl = (exit_basis - entry_basis) * qty_basis
        self.daily_pnl += real_pnl
        self.daily_trades_closed += 1
        if p.fill_entry_price is not None and sell_fill_px is not None:
            tag = "real"
        else:
            tag = "approx"
        print(
            f"{LOG_TAG} {tag} P&L={real_pnl:+,.0f} daily={self.daily_pnl:+,.0f} "
            f"(trade #{self.daily_trades_closed}) "
            f"entry=${entry_basis:.4f} exit=${exit_basis:.4f} qty={qty_basis}",
            flush=True,
        )
        # Set up re-entry watch (cycle reset is inside _register_reentry_watch).
        # Done BEFORE clearing self.position so the position fields are
        # still valid in the snapshot.
        self._register_reentry_watch(p)
        # Record stay-armed close info for cool-down + continuation gate.
        if self.move_stay_armed:
            self._move_stay_armed_last_exit_min[p.symbol] = now_minute_et()
            self._move_stay_armed_last_exit_price[p.symbol] = float(ref_price)
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
