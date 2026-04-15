"""
bot_v3_hybrid.py — Warrior Bot V3: IBKR data + Alpaca execution.

Hybrid architecture:
- IB Gateway: scanner, tick data (reqMktData/RTVolume), VWAP, bar building
- Alpaca: order execution (buy/sell), account equity, position management

Flow:
1. Connect to IB Gateway (data) + Alpaca (execution)
2. Run pre-market scanner (ibkr_scanner.scan_premarket_live)
3. Subscribe to top candidates (IBKR reqMktData)
4. Build 1-min + 10-sec bars from IBKR tick updates
5. Feed bars to squeeze_detector / micro_pullback
6. On signal: place order via ALPACA
7. Manage exits via Alpaca orders, driven by IBKR tick data
8. Scanner runs continuously during all trading windows
9. Two sessions: morning (7:00-12:00 ET) + evening (16:00-20:00 ET)
10. Sleeps during dead zone (12:00-16:00), shuts down after last window
"""

from __future__ import annotations

import os
import sys
import time
import math
import json
import gzip
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone, time as time_cls
from collections import deque

import pytz
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder, MarketOrder, util
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Load .env if present (same as simulate.py — ensures env vars are set)
load_dotenv()

if os.getenv("WB_SQUEEZE_VERSION", "1") == "2":
    from squeeze_detector_v2 import SqueezeDetectorV2 as SqueezeDetector
else:
    from squeeze_detector import SqueezeDetector
from micro_pullback import MicroPullbackDetector
from continuation_detector import ContinuationDetector
from ibkr_scanner import scan_premarket_live, scan_catchup, rank_score
from bars import TradeBarBuilder, Bar
from candles import is_bearish_engulfing
from patterns import PatternDetector
from epl_framework import (
    EPL_ENABLED, EPL_MAX_NOTIONAL, EPL_MIN_GRADUATION_R,
    GraduationContext, EPLWatchlist, StrategyRegistry, PositionArbitrator,
)
from epl_mp_reentry import EPLMPReentry, EPL_MP_ENABLED
import session_state as ss

ET = pytz.timezone("US/Eastern")

# Box strategy (conditional import — gated by WB_BOX_ENABLED)
BOX_ENABLED = os.getenv("WB_BOX_ENABLED", "0") == "1"
BOX_SIMULTANEOUS = os.getenv("WB_BOX_SIMULTANEOUS", "0") == "1"
if BOX_ENABLED:
    from box_scanner import scan_box_candidates
    from box_strategy import BoxStrategyEngine

# ── Databento bridge ────────────────────────────────────────────────
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt")
DATABENTO_BRIDGE = os.getenv("WB_DATABENTO_BRIDGE_ENABLED", "1") == "1"

# ── Strategy gates ───────────────────────────────────────────────────
SQ_ENABLED = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"
MP_ENABLED = os.getenv("WB_MP_ENABLED", "0") == "1"
MP_V2_ENABLED = os.getenv("WB_MP_V2_ENABLED", "0") == "1"
CT_ENABLED = os.getenv("WB_CT_ENABLED", "0") == "1"

# ── IBKR connection ──────────────────────────────────────────────────
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))  # 4002 = Gateway paper
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))

# ── Risk ─────────────────────────────────────────────────────────────
STARTING_EQUITY = float(os.getenv("WB_STARTING_EQUITY", "30000"))
RISK_PCT = float(os.getenv("WB_RISK_PCT", "0.025"))  # 2.5% of equity per trade
MAX_NOTIONAL = float(os.getenv("WB_MAX_NOTIONAL", "100000"))
MAX_SHARES = int(os.getenv("WB_MAX_SHARES", "100000"))
SCALE_NOTIONAL = os.getenv("WB_SCALE_NOTIONAL", "0") == "1"  # 50% buying power (2x equity)
MIN_R = float(os.getenv("WB_MIN_R", "0.06"))

# Entry slippage + retry (added 2026-04-15 — was hardcoded $0.02 + single-shot)
# Dynamic slippage: max(SLIPPAGE_MIN, price * SLIPPAGE_PCT). If initial limit
# times out, cancel + re-read live price + re-submit at (current + slippage),
# up to MAX_RETRIES times. Gives up if market runs past MAX_CHASE_PCT above
# original limit (stops unbounded chasing on vertical moves).
ENTRY_SLIPPAGE_MIN = float(os.getenv("WB_ENTRY_SLIPPAGE_MIN", "0.05"))
ENTRY_SLIPPAGE_PCT = float(os.getenv("WB_ENTRY_SLIPPAGE_PCT", "0.005"))  # 0.5% of price
ENTRY_MAX_RETRIES = int(os.getenv("WB_ENTRY_MAX_RETRIES", "3"))
ENTRY_RETRY_TIMEOUT_SEC = int(os.getenv("WB_ENTRY_RETRY_TIMEOUT_SEC", "10"))
ENTRY_MAX_CHASE_PCT = float(os.getenv("WB_ENTRY_MAX_CHASE_PCT", "2.0"))  # max % above original limit
ENTRY_RETRY_ENABLED = os.getenv("WB_ENTRY_RETRY_ENABLED", "1") == "1"


def _entry_slippage_for(price: float) -> float:
    """Dynamic slippage: max(MIN, price * PCT). Matches manual bot pattern."""
    return max(ENTRY_SLIPPAGE_MIN, price * ENTRY_SLIPPAGE_PCT)

# Session resume (2026-04-15 — see cowork_reports/2026-04-15_greenlight_session_resume.md)
# WB_TICK_FLUSH_ENABLED: always-on crash-safety for the tick cache (independent
#   of resume). Flushes state.tick_buffer to tick_cache/ every WB_SESSION_FLUSH_SEC.
# WB_SESSION_RESUME_ENABLED: gates the resume-mode boot path only. When 0, the
#   bot still writes durable state files (so a subsequent enabled run can resume),
#   but always does a cold start itself.
TICK_FLUSH_ENABLED = os.getenv("WB_TICK_FLUSH_ENABLED", "1") == "1"
SESSION_FLUSH_SEC = int(os.getenv("WB_SESSION_FLUSH_SEC", "30"))
SESSION_RESUME_ENABLED = os.getenv("WB_SESSION_RESUME_ENABLED", "0") == "1"

# Lock serializing tick_buffer mutations between the IBKR tick callback
# thread and the periodic flush swap. Acquisition is microseconds; contention
# is negligible (one swap per SESSION_FLUSH_SEC vs thousands of appends).
_tick_buffer_lock = threading.Lock()
MAX_DAILY_LOSS = float(os.getenv("WB_MAX_DAILY_LOSS", "3000"))
DAILY_LOSS_SCALE = os.getenv("WB_DAILY_LOSS_SCALE", "0") == "1"
MAX_CONSECUTIVE_LOSSES = int(os.getenv("WB_MAX_CONSECUTIVE_LOSSES", "3"))
BAIL_TIMER_ENABLED = os.getenv("WB_BAIL_TIMER_ENABLED", "1") == "1"
BAIL_TIMER_MINUTES = float(os.getenv("WB_BAIL_TIMER_MINUTES", "5"))

# ── Squeeze exit params ──────────────────────────────────────────────
SQ_TARGET_R = float(os.getenv("WB_SQ_TARGET_R", "2.0"))
SQ_TRAIL_R = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
SQ_PARA_TRAIL_R = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
SQ_RUNNER_TRAIL_R = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
SQ_MAX_LOSS_DOLLARS = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
SQ_CORE_PCT = int(os.getenv("WB_SQ_CORE_PCT", "75"))

# ── Candle-based exit params (parity with simulate.py) ──────────────
SQ_CANDLE_EXITS_ENABLED = os.getenv("WB_SQ_CANDLE_EXITS_ENABLED", "1") == "1"
EXIT_ON_TOPPING_WICKY = os.getenv("WB_EXIT_ON_TOPPING_WICKY", "1") == "1"
EXIT_ON_BEAR_ENGULF = os.getenv("WB_EXIT_ON_BEAR_ENGULF", "1") == "1"
TW_GRACE_MIN = int(os.getenv("WB_TOPPING_WICKY_GRACE_MIN", "3"))
TW_MIN_PROFIT_R = float(os.getenv("WB_TW_MIN_PROFIT_R", "1.5"))
BE_GRACE_MIN = int(os.getenv("WB_BE_GRACE_MIN", "0"))
BE_MIN_PROFIT_R = float(os.getenv("WB_BE_MIN_PROFIT_R", "0.5"))
BE_PARABOLIC_GRACE = os.getenv("WB_BE_PARABOLIC_GRACE", "1") == "1"
BE_GRACE_MIN_R = float(os.getenv("WB_BE_GRACE_MIN_R", "1.0"))
BE_GRACE_MIN_NEW_HIGHS = int(os.getenv("WB_BE_GRACE_MIN_NEW_HIGHS", "3"))
BE_GRACE_LOOKBACK = int(os.getenv("WB_BE_GRACE_LOOKBACK_BARS", "6"))

# ── Trading windows (ET) ─────────────────────────────────────────────
# Two sessions: morning and evening, with a dead zone 12:00-16:00.
# Format: comma-separated "HH:MM-HH:MM" windows.
TRADING_WINDOWS_STR = os.getenv("WB_TRADING_WINDOWS", "07:00-12:00,16:00-20:00")
TRADING_WINDOWS = []
for _w in TRADING_WINDOWS_STR.split(","):
    _parts = _w.strip().split("-")
    if len(_parts) == 2:
        _s = time_cls(int(_parts[0].split(":")[0]), int(_parts[0].split(":")[1]))
        _e = time_cls(int(_parts[1].split(":")[0]), int(_parts[1].split(":")[1]))
        TRADING_WINDOWS.append((_s, _e))

def in_trading_window(now_et: datetime) -> bool:
    """Check if current time falls within any trading window."""
    t = now_et.time()
    return any(start <= t < end for start, end in TRADING_WINDOWS)

def past_all_windows(now_et: datetime) -> bool:
    """Check if we're past the last trading window for the day."""
    t = now_et.time()
    if not TRADING_WINDOWS:
        return True
    last_end = max(end for _, end in TRADING_WINDOWS)
    # If box is enabled, also need to be past box window
    if BOX_ENABLED:
        last_end = max(last_end, BOX_WINDOW_END)
    return t >= last_end

# ── Box trading windows ─────────────────────────────────────────────
BOX_WINDOW_START = time_cls(int(os.getenv("WB_BOX_START_ET", "10:00").split(":")[0]),
                            int(os.getenv("WB_BOX_START_ET", "10:00").split(":")[1]))
BOX_WINDOW_END = time_cls(int(os.getenv("WB_BOX_HARD_CLOSE_ET", "15:45").split(":")[0]),
                          int(os.getenv("WB_BOX_HARD_CLOSE_ET", "15:45").split(":")[1]))
BOX_LAST_ENTRY = time_cls(int(os.getenv("WB_BOX_LAST_ENTRY_ET", "14:30").split(":")[0]),
                          int(os.getenv("WB_BOX_LAST_ENTRY_ET", "14:30").split(":")[1]))
BOX_SKIP_FRIDAY = os.getenv("WB_BOX_SKIP_FRIDAY", "1") == "1"
BOX_MAX_LOSS_SESSION = float(os.getenv("WB_BOX_MAX_LOSS_SESSION", "500"))
BOX_SCAN_CHECKPOINTS = [time_cls(10, 0), time_cls(11, 0)]

# Vol Sweet Spot filter thresholds (from Phase 2B)
BOX_FILTER_MIN_RANGE_PCT = float(os.getenv("WB_BOX_MIN_RANGE_PCT", "2.0"))
BOX_FILTER_MAX_RANGE_PCT = float(os.getenv("WB_BOX_MAX_RANGE_PCT", "6.0"))
BOX_FILTER_MIN_TOTAL_TESTS = int(os.getenv("WB_BOX_MIN_TOTAL_TESTS", "5"))
BOX_FILTER_MIN_PRICE = float(os.getenv("WB_BOX_MIN_PRICE", "15.0"))
BOX_FILTER_MAX_ADR_UTIL = float(os.getenv("WB_BOX_MAX_ADR_UTIL", "0.80"))

def in_box_window(now_et: datetime) -> bool:
    """True if box is enabled and we're in the box window."""
    if not BOX_ENABLED:
        return False
    t = now_et.time()
    return BOX_WINDOW_START <= t <= BOX_WINDOW_END

def in_any_active_window(now_et: datetime) -> bool:
    """True if either momentum or box is active."""
    return in_trading_window(now_et) or in_box_window(now_et)


# ══════════════════════════════════════════════════════════════════════
# State
# ══════════════════════════════════════════════════════════════════════

class BotState:
    """Holds all mutable bot state."""
    def __init__(self):
        self.ib: IB = None
        self.alpaca: TradingClient = None  # V3: Alpaca for execution
        self.active_symbols: set[str] = set()
        self.contracts: dict[str, Stock] = {}
        self.tickers: dict = {}

        # Detectors
        self.sq_detectors: dict[str, SqueezeDetector] = {}
        self.mp_detectors: dict[str, MicroPullbackDetector] = {}
        self.ct_detectors: dict[str, ContinuationDetector] = {}

        # Bar builders (1m for detection, 10s for exits)
        self.bar_builder_1m: TradeBarBuilder = None
        self.bar_builder_10s: TradeBarBuilder = None

        # Position tracking
        self.open_position: dict = None  # {symbol, qty, entry, stop, r, setup_type, ...}
        self.pending_order: dict = None

        # Daily risk
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.consecutive_losses: int = 0
        self.closed_trades: list[dict] = []

        # Scanner
        self.candidates: list[dict] = []
        self.last_scan_time: datetime = None
        self.in_dead_zone: bool = False  # True while between trading windows

        # Seed completion tracking (suppress stale signals after seeding)
        self.seed_complete_time: dict[str, datetime] = {}  # symbol -> when seed finished
        self.live_tick_count_since_seed: dict[str, int] = {}  # symbol -> live ticks received post-seed

        # Tick health monitoring
        self.tick_counts: dict[str, int] = {}  # symbol -> ticks since last audit
        self.last_tick_time: dict[str, datetime] = {}  # symbol -> last tick timestamp
        self.last_tick_price: dict[str, float] = {}  # symbol -> last tick price
        self.last_tick_audit: datetime = None
        self._last_position_sync: datetime = None
        self.sub_retry_counts: dict[str, int] = {}  # symbol -> resubscription attempts
        self.last_on_ticker_fire: datetime = None  # track when on_ticker_update last fired

        # Tick recording for backtest cache
        self.tick_buffer: dict[str, list] = {}  # symbol -> [{p, s, t}, ...]

        # Session-resume (2026-04-15) — "cold" | "resume", set by main()
        # after decide_boot_mode(). Downstream code (seed_symbol, order
        # reconciliation) branches on this to skip expensive cold-start work.
        self.boot_mode: str = "cold"

        # EPL (Extended Play List) — post-2R re-entry system
        self.epl_watchlist: EPLWatchlist = None
        self.epl_registry: StrategyRegistry = None
        self.epl_arbitrator: PositionArbitrator = None

        # Candle exit state (per-symbol)
        self.pattern_dets: dict[str, PatternDetector] = {}  # symbol -> PatternDetector (10s bars)
        self.prev_10s_bar: dict[str, dict] = {}  # symbol -> {o, h, l, c}
        self.recent_10s_highs: dict[str, list] = {}  # symbol -> [highs] for BE parabolic grace

        # Box strategy state
        self.box_position: dict = None        # {symbol, qty, entry, engine, ...}
        self.box_engine: object = None        # active BoxStrategyEngine
        self.box_candidates: list = []        # filtered box scanner candidates
        self.box_active_symbol: str = None    # symbol subscribed for box
        self.box_bar_builder_1m: TradeBarBuilder = None
        self.box_daily_pnl: float = 0.0
        self.box_daily_trades: int = 0
        self.box_closed_trades: list = []
        self.last_box_scan_time: datetime = None


state = BotState()


# ══════════════════════════════════════════════════════════════════════
# Initialization
# ══════════════════════════════════════════════════════════════════════

# ── Hang protection (added 2026-04-10 after Alpaca SDK froze main thread) ──
# Alpaca SDK has no default HTTP timeout. After a network blip, a stale TCP
# socket in the keep-alive pool can cause get_all_positions() to block forever
# on _ssl__SSLSocket_read. We wrap every Alpaca call in a thread with a hard
# timeout so a hung HTTPS call can't freeze the main thread.
_alpaca_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alpaca-call")


def _alpaca_call(fn, *args, timeout=10, **kwargs):
    """Run an Alpaca SDK call with a hard timeout. Raises TimeoutError if it hangs."""
    future = _alpaca_executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        # We can't actually cancel a thread blocked on a kernel read, but we
        # don't wait for it — the next call will get a fresh worker.
        raise TimeoutError(f"Alpaca call {fn.__name__} timed out after {timeout}s")


# ── Main-thread watchdog ──
# If the main loop stops updating the heartbeat for >120s, the watchdog kills
# the bot hard. Cron/check_bot.sh will then restart it. This is the safety net
# for any hangs we don't catch with explicit timeouts.
_last_heartbeat = time.time()
_HEARTBEAT_TIMEOUT_SEC = 120


def update_heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()


def _watchdog_loop():
    while True:
        time.sleep(15)
        elapsed = time.time() - _last_heartbeat
        if elapsed > _HEARTBEAT_TIMEOUT_SEC:
            print(f"\n💀 WATCHDOG: main thread frozen for {elapsed:.0f}s — exiting hard for restart.",
                  flush=True)
            os._exit(1)


def start_watchdog():
    t = threading.Thread(target=_watchdog_loop, daemon=True, name="watchdog")
    t.start()
    print(f"  Watchdog: armed (kills bot if main thread frozen >{_HEARTBEAT_TIMEOUT_SEC}s)",
          flush=True)


def get_account_equity() -> float:
    """Get current account equity from Alpaca."""
    try:
        account = _alpaca_call(state.alpaca.get_account)
        return float(account.equity)
    except Exception as e:
        print(f"  Failed to fetch Alpaca account equity: {e}", flush=True)
    return STARTING_EQUITY  # Fallback


# ══════════════════════════════════════════════════════════════════════
# Position Safety (Fixes 1-5 from DIRECTIVE_V3_POSITION_SYNC.md)
# ══════════════════════════════════════════════════════════════════════

def reconcile_positions_on_startup():
    """Fix 1: Check Alpaca for positions the bot doesn't know about."""
    try:
        positions = _alpaca_call(state.alpaca.get_all_positions)
    except Exception as e:
        print(f"  Position sync error: {e}", flush=True)
        return

    if not positions:
        print("  Position sync: No open positions on Alpaca. Clean start.", flush=True)
        return

    for pos in positions:
        symbol = pos.symbol
        qty = int(pos.qty)
        avg_entry = float(pos.avg_entry_price)
        unrealized_pnl = float(pos.unrealized_pl)
        market_value = float(pos.market_value)

        print(f"  ⚠️ ORPHAN POSITION FOUND: {symbol} qty={qty} "
              f"entry=${avg_entry:.2f} unrealized=${unrealized_pnl:+,.2f} "
              f"value=${market_value:,.2f}", flush=True)

        if state.open_position is None:
            state.open_position = {
                "symbol": symbol,
                "entry": avg_entry,
                "qty": qty,
                "r": avg_entry * 0.03,
                "stop": avg_entry * 0.97,
                "score": 0.0,
                "setup_type": "orphan_adopted",
                "peak": avg_entry,
                "tp_hit": False,
                "entry_time": datetime.now(ET),
                "order_id": "adopted",
                "is_parabolic": False,
                "fill_confirmed": True,
            }
            print(f"  → Adopted {symbol} into bot state. Exit management active.", flush=True)
        else:
            print(f"  → Bot already has position in {state.open_position['symbol']}. "
                  f"CLOSING orphan {symbol}.", flush=True)
            try:
                from alpaca.trading.requests import MarketOrderRequest
                req = MarketOrderRequest(
                    symbol=symbol, qty=qty,
                    side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
                )
                state.alpaca.submit_order(req)
                print(f"  → Orphan {symbol} close order submitted.", flush=True)
            except Exception as e:
                print(f"  → FAILED to close orphan {symbol}: {e}", flush=True)


def _trade_record_to_open_position(rec: dict) -> dict:
    """Inverse of _open_position_to_trade_record: rehydrate an in-memory
    open_position dict from a persisted open_trades.json entry. Used only
    on resume boot, after qty has been reconciled against Alpaca.
    """
    entry_time_str = rec.get("entry_time", "")
    try:
        entry_time = datetime.fromisoformat(entry_time_str)
        # Normalize to ET for manage_exit's bail-timer math
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        entry_time = entry_time.astimezone(ET)
    except (ValueError, TypeError):
        entry_time = datetime.now(ET)

    return {
        "symbol": rec["symbol"],
        "entry": float(rec["entry_price"]),
        "qty": int(rec["qty"]),
        "r": float(rec["r"]),
        "stop": float(rec["stop"]),
        "score": float(rec.get("score", 0.0)),
        "setup_type": rec.get("setup_type", ""),
        "peak": float(rec.get("peak", rec["entry_price"])),
        "tp_hit": rec.get("trail_mode") == "post_target",
        "entry_time": entry_time,
        "order_id": rec.get("order_id", ""),
        "is_parabolic": bool(rec.get("is_parabolic", False)),
        "fill_confirmed": True,
        "partial_filled_at": rec.get("partial_filled_at"),
        "partial_filled_qty": int(rec.get("partial_filled_qty", 0)),
    }


def resume_reconcile():
    """Resume-mode order + position reconciliation. Called instead of
    reconcile_positions_on_startup() when state.boot_mode == "resume".

    Flow (Cowork-approved, see finding_no_standing_exits.md):
      1. Cancel all pending BUY orders (entry retry state is lost).
      2. Cancel all open SELL orders (invariant: no standing protective
         orders during healthy operation; any found is a crash-mid-exit
         artifact — let manage_exit re-evaluate on the next tick).
      3. For each Alpaca position: match against open_trades.json.
         - Match → rehydrate state.open_position, reconcile qty to Alpaca.
         - No match → flatten_orphan_position() via session_state helper.
      4. Restore risk counters from risk.json.
    """
    print("🔁 RESUME: reconciling orders + positions", flush=True)

    # Step 1-2: cancel all open orders unconditionally.
    cancelled_buy = 0
    cancelled_sell = 0
    try:
        open_orders = _alpaca_call(state.alpaca.get_orders) or []
    except Exception as e:
        print(f"  RESUME: get_orders failed: {e}", flush=True)
        open_orders = []
    for o in open_orders:
        try:
            side = str(getattr(o, "side", "")).lower()
            is_buy = "buy" in side
            state.alpaca.cancel_order_by_id(o.id)
            if is_buy:
                cancelled_buy += 1
                print(f"  RESUME: cancelled pending BUY {o.id} {o.symbol} "
                      f"@ ${float(getattr(o, 'limit_price', 0) or 0):.2f}", flush=True)
            else:
                cancelled_sell += 1
                print(f"  RESUME: cancelled standing SELL {o.id} {o.symbol} "
                      f"(invariant: no standing SELLs during healthy op)", flush=True)
        except Exception as e:
            print(f"  RESUME: cancel {o.id} failed: {e}", flush=True)
    if cancelled_buy or cancelled_sell:
        print(f"  RESUME: {cancelled_buy} BUYs + {cancelled_sell} SELLs cancelled", flush=True)

    # Step 3: rehydrate positions, index persisted trades by symbol.
    persisted = ss.read_open_trades()
    by_symbol = {r["symbol"]: r for r in persisted}
    try:
        positions = _alpaca_call(state.alpaca.get_all_positions) or []
    except Exception as e:
        print(f"  RESUME: get_all_positions failed: {e}", flush=True)
        positions = []

    rehydrated_symbols: set[str] = set()
    for apos in positions:
        sym = apos.symbol
        alpaca_qty = int(apos.qty)
        alpaca_entry = float(apos.avg_entry_price)

        rec = by_symbol.get(sym)
        if rec is None:
            # No persisted record → orphan. Loud flatten (gated by
            # WB_RESUME_FLATTEN_ORPHANS). No current-price estimate available
            # pre-live-ticks; helper omits impact line when None.
            ss.flatten_orphan_position(
                state.alpaca, sym, alpaca_qty, alpaca_entry, current_price=None,
            )
            continue

        # Match: rehydrate with qty drift reconciliation. Alpaca is truth.
        persisted_qty = int(rec.get("qty", 0))
        if persisted_qty != alpaca_qty:
            print(f"⚠️  REHYDRATE QTY DRIFT: {sym} persisted={persisted_qty} "
                  f"alpaca={alpaca_qty} — trusting Alpaca "
                  f"(likely partial fill during crash)", flush=True)
            rec = dict(rec)
            rec["qty"] = alpaca_qty
        # (Alpaca reporting MORE than persisted is also suspicious — we still
        # trust Alpaca but flag for audit.)
        if alpaca_qty > persisted_qty:
            print(f"⚠️  REHYDRATE QTY DRIFT UP: {sym} alpaca={alpaca_qty} > "
                  f"persisted={persisted_qty} — unexpected. Flagging for audit.",
                  flush=True)

        if state.open_position is None:
            state.open_position = _trade_record_to_open_position(rec)
            rehydrated_symbols.add(sym)
            print(f"  RESUME: rehydrated {sym} qty={alpaca_qty} "
                  f"entry=${rec['entry_price']:.2f} stop=${rec['stop']:.2f} "
                  f"peak=${rec['peak']:.2f} mode={rec['trail_mode']}", flush=True)
        else:
            # Bot only tracks one momentum position at a time. A second
            # match means the persisted file disagrees with the single-slot
            # invariant — flatten the second one as orphan.
            print(f"  RESUME: {sym} matched but state.open_position already "
                  f"filled by {state.open_position['symbol']} — flattening {sym}",
                  flush=True)
            ss.flatten_orphan_position(
                state.alpaca, sym, alpaca_qty, alpaca_entry, current_price=None,
            )

    # Step 4: restore risk counters.
    risk = ss.read_risk()
    state.daily_pnl = float(risk.get("daily_pnl", 0.0))
    state.daily_trades = int(risk.get("daily_trades", 0))
    state.consecutive_losses = int(risk.get("consecutive_losses", 0))
    state.closed_trades = list(risk.get("closed_trades", []))
    print(f"  RESUME: risk restored — daily_pnl=${state.daily_pnl:+,.2f} "
          f"trades={state.daily_trades} losses={state.consecutive_losses} "
          f"(closed_trades={len(state.closed_trades)} cached)", flush=True)

    # Persist-after-rehydrate: the qty-reconciled records should be written
    # back so the on-disk state matches the live in-memory state.
    persist_open_trades()

    # Sanity: stale persisted records for positions that no longer exist on
    # Alpaca (closed during crash window) would linger without this sync.
    # persist_open_trades already wrote state.open_position (or []) — if the
    # previous open_trades.json had a symbol that Alpaca no longer reports,
    # that record is now dropped from disk. Log the drop for post-mortem.
    dropped = set(by_symbol.keys()) - rehydrated_symbols
    for sym in dropped:
        print(f"  RESUME: persisted record for {sym} has no live Alpaca position "
              f"— dropping (likely closed during crash window)", flush=True)

    print("🔁 RESUME: reconcile complete", flush=True)


def periodic_position_sync():
    """Fix 3: Every 60s, verify bot state matches Alpaca reality."""
    now = datetime.now(ET)
    if hasattr(state, '_last_position_sync') and state._last_position_sync and \
       (now - state._last_position_sync).total_seconds() < 60:
        return
    state._last_position_sync = now

    try:
        positions = _alpaca_call(state.alpaca.get_all_positions)
    except Exception as e:
        print(f"  Position sync error: {e}", flush=True)
        return

    alpaca_symbols = {pos.symbol: pos for pos in positions}

    # Case 1: Bot thinks it has a position, but Alpaca doesn't
    if state.open_position and state.open_position.get("fill_confirmed"):
        bot_symbol = state.open_position["symbol"]
        if bot_symbol not in alpaca_symbols:
            print(f"  ⚠️ POSITION DESYNC: Bot thinks it holds {bot_symbol}, "
                  f"but Alpaca shows no position. Clearing bot state.", flush=True)
            state.open_position = None

    # Case 2: Alpaca has a position the bot doesn't know about
    if not state.open_position:
        for symbol, pos in alpaca_symbols.items():
            qty = int(pos.qty)
            avg_entry = float(pos.avg_entry_price)
            print(f"  ⚠️ ORPHAN DETECTED: Alpaca holds {symbol} qty={qty} "
                  f"entry=${avg_entry:.2f} — bot unaware. Adopting.", flush=True)
            state.open_position = {
                "symbol": symbol,
                "entry": avg_entry,
                "qty": qty,
                "r": avg_entry * 0.03,
                "stop": avg_entry * 0.97,
                "score": 0.0,
                "setup_type": "orphan_adopted",
                "peak": avg_entry,
                "tp_hit": False,
                "entry_time": datetime.now(ET),
                "order_id": "adopted",
                "is_parabolic": False,
                "fill_confirmed": True,
            }
            break  # Single-position bot

    # Case 3: Quantities mismatch
    if state.open_position and state.open_position.get("fill_confirmed"):
        bot_symbol = state.open_position["symbol"]
        if bot_symbol in alpaca_symbols:
            alp_qty = int(alpaca_symbols[bot_symbol].qty)
            bot_qty = state.open_position["qty"]
            if alp_qty != bot_qty:
                print(f"  ⚠️ QTY MISMATCH: Bot thinks {bot_qty} shares, "
                      f"Alpaca shows {alp_qty}. Updating bot.", flush=True)
                state.open_position["qty"] = alp_qty


def wait_for_fill(order_id: str, timeout: int = 15):
    """Fix 2: Wait for Alpaca order fill with timeout. Returns (price, qty) or (None, 0)."""
    for _ in range(timeout * 2):
        try:
            o = state.alpaca.get_order_by_id(order_id)
            if o.status == 'filled':
                return float(o.filled_avg_price), int(float(o.filled_qty))
            if o.status in ('cancelled', 'expired', 'rejected'):
                return None, 0
        except Exception:
            pass
        time.sleep(0.5)
    # Timeout — cancel
    try:
        state.alpaca.cancel_order_by_id(order_id)
    except Exception:
        pass
    # Final check — order may have filled between cancel and check
    try:
        o = state.alpaca.get_order_by_id(order_id)
        if o.status == 'filled':
            return float(o.filled_avg_price), int(float(o.filled_qty))
    except Exception:
        pass
    return None, 0


def connect():
    """Connect to IBKR with retry logic."""
    state.ib = IB()
    for attempt in range(1, 4):
        try:
            state.ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
            print(f"Connected: {state.ib.isConnected()}")
            print(f"Account: {state.ib.managedAccounts()}")
            return state.ib
        except Exception as e:
            print(f"Connection attempt {attempt}/3 failed: {e}", flush=True)
            if attempt < 3:
                print(f"Retrying in 10 seconds...", flush=True)
                time.sleep(10)
            else:
                raise


def init_detectors(symbol: str):
    """Create squeeze + MP + CT detectors for a symbol."""
    if SQ_ENABLED and symbol not in state.sq_detectors:
        sq = SqueezeDetector()
        sq.symbol = symbol
        state.sq_detectors[symbol] = sq

    if (MP_ENABLED or MP_V2_ENABLED) and symbol not in state.mp_detectors:
        mp = MicroPullbackDetector()
        mp.symbol = symbol
        state.mp_detectors[symbol] = mp

    if CT_ENABLED and symbol not in state.ct_detectors:
        ct = ContinuationDetector()
        state.ct_detectors[symbol] = ct


def subscribe_symbol(symbol: str):
    """Subscribe to market data for a symbol."""
    if symbol in state.active_symbols:
        return

    contract = Stock(symbol, 'SMART', 'USD')
    state.ib.qualifyContracts(contract)
    state.contracts[symbol] = contract

    # Subscribe to market data with RTVolume (generic tick 233) for Time & Sales
    ticker = state.ib.reqMktData(contract, '233', False, False)
    state.tickers[symbol] = ticker

    # Initialize detectors
    init_detectors(symbol)

    # Seed — resume mode replays from tick_cache/<today>/<sym>.json.gz,
    # cold mode fetches from IBKR. On resume-cache miss (symbol newly
    # subscribed post-crash, or cache read error) we fall back to the cold
    # IBKR path so the detector isn't left under-seeded.
    seeded_from_cache = False
    if state.boot_mode == "resume":
        seeded_from_cache = seed_symbol_from_cache(symbol)
    if not seeded_from_cache:
        seed_symbol(symbol)

    state.active_symbols.add(symbol)
    state.tick_counts[symbol] = 0
    state.sub_retry_counts[symbol] = 0
    print(f"✅ Subscribed: {symbol}", flush=True)
    persist_watchlist()


def check_subscription_health():
    """Check that all subscribed symbols are receiving ticks. Resubscribe if not."""
    for symbol in list(state.active_symbols):
        count = state.tick_counts.get(symbol, 0)
        retries = state.sub_retry_counts.get(symbol, 0)
        if count == 0 and retries < 3:
            contract = state.contracts.get(symbol)
            if not contract:
                continue
            state.sub_retry_counts[symbol] = retries + 1
            print(f"⚠️ TICK DROUGHT: {symbol} — 0 ticks in last audit period. "
                  f"Resubscribing (attempt {retries + 1}/3)...", flush=True)
            try:
                state.ib.cancelMktData(contract)
                state.ib.sleep(2)
                ticker = state.ib.reqMktData(contract, '233', False, False)
                state.tickers[symbol] = ticker
            except Exception as e:
                print(f"  Resubscription failed for {symbol}: {e}", flush=True)
        elif count == 0 and retries >= 3:
            print(f"🔴 CRITICAL: {symbol} — no ticks after 3 resubscription attempts", flush=True)
        else:
            # Getting ticks — reset retry counter
            state.sub_retry_counts[symbol] = 0


def audit_tick_health():
    """Log per-symbol tick counts every 60 seconds and trigger resubscription if needed."""
    now = datetime.now(ET)
    if state.last_tick_audit and (now - state.last_tick_audit).total_seconds() < 60:
        return
    state.last_tick_audit = now

    if not state.active_symbols:
        return

    for symbol in sorted(state.active_symbols):
        count = state.tick_counts.get(symbol, 0)
        last_price = state.last_tick_price.get(symbol, 0)
        last_time = state.last_tick_time.get(symbol)
        last_str = last_time.strftime("%H:%M:%S") if last_time else "never"
        print(f"  TICK AUDIT: {symbol}: {count} ticks in last 60s, "
              f"last_price=${last_price:.2f}, last_tick_time={last_str}", flush=True)

    # Check subscription health and resubscribe if needed
    check_subscription_health()

    # Reset counters for next interval
    for symbol in state.active_symbols:
        state.tick_counts[symbol] = 0


def seed_symbol(symbol: str):
    """Seed detectors with historical tick data from today.

    Uses reqHistoricalTicks (tick-level data) replayed through TradeBarBuilder
    to match exactly how simulate.py processes data. This ensures the squeeze
    detector's volume averages and state machine match backtest behavior.
    """
    contract = state.contracts.get(symbol)
    if not contract:
        return

    try:
        # Tell detectors we're about to seed (suppresses entry signals during replay)
        sq = state.sq_detectors.get(symbol)
        if sq:
            sq.begin_seed()

        # Fetch tick-level historical data from today.
        # Strategy: start from 4 AM ET but if too many ticks, restart from
        # 90 minutes before now. This ensures we always get RECENT volume
        # context (what matters for detector baselines) even on high-volume stocks.
        now_et = datetime.now(ET)
        seed_start = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        start_str = seed_start.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"

        all_ticks = []
        current_start = start_str
        max_pages = 100  # enough for full session
        max_ticks = 50000  # first pass cap
        ticks_per_page = 1000

        for page in range(max_pages):
            # Heartbeat each page — pagination of up to 100 pages with API
            # latency can exceed the 120s watchdog window.
            update_heartbeat()
            ticks = state.ib.reqHistoricalTicks(
                contract, current_start, '', ticks_per_page, 'TRADES', useRth=False
            )
            if not ticks:
                break
            all_ticks.extend(ticks)
            state.ib.sleep(0.3)

            if len(ticks) < ticks_per_page:
                break  # got all ticks

            # If we've hit the cap, restart from 90 min ago to get recent data
            if len(all_ticks) >= max_ticks:
                recent_start = (now_et - timedelta(minutes=90))
                recent_str = recent_start.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"
                # Only restart if we haven't already reached recent data
                last_time = ticks[-1].time
                if last_time < recent_start.astimezone(timezone.utc):
                    print(f"  [SEED] {symbol}: {len(all_ticks)} ticks so far, "
                          f"jumping to recent 90min for full context", flush=True)
                    current_start = recent_str
                    continue
                break

            # Paginate: next page starts after last tick
            last_time = ticks[-1].time
            current_start = last_time.strftime("%Y%m%d %H:%M:%S") + " UTC"

            # Stop if we've caught up to now
            if last_time >= now_et.astimezone(timezone.utc):
                break

        if not all_ticks:
            # Fallback to 1m bars if tick data unavailable
            print(f"⚠️ No tick data for {symbol}, falling back to 1m bars", flush=True)
            _seed_symbol_bars_fallback(symbol)
            return

        # Persist fetched historical ticks to the tick_buffer so that the
        # 30s flush captures them to tick_cache/<today>/<sym>.json.gz.
        # This makes the cache authoritative (04:00 ET onward) so a future
        # resume boot can replay from disk without re-fetching from IBKR.
        # Lock serializes against the flush swap and live tick callback.
        with _tick_buffer_lock:
            buf = state.tick_buffer.setdefault(symbol, [])
            for tick in all_ticks:
                if tick.price <= 0 or not tick.size or int(tick.size) <= 0:
                    continue
                buf.append({
                    "p": float(tick.price),
                    "s": int(tick.size),
                    "t": tick.time.astimezone(timezone.utc).isoformat(),
                })

        # Replay ticks through TradeBarBuilder (same path as live ticks and simulate.py)
        # This builds bars organically with correct volume accumulation
        bars_built = 0
        for tick in all_ticks:
            ts_utc = tick.time
            price = tick.price
            size = int(tick.size) if tick.size else 0
            if price <= 0 or size <= 0:
                continue

            # Feed to the MAIN bar builder — this triggers on_bar_close_1m
            # which feeds the squeeze/MP/CT detectors through the normal pipeline
            if state.bar_builder_1m:
                state.bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            # Feed to box bar builder too — keeps box RSI/VWAP in sync
            if BOX_ENABLED and state.box_bar_builder_1m:
                state.box_bar_builder_1m.on_trade(symbol, price, size, ts_utc)

        # Count how many bars were built
        sq = state.sq_detectors.get(symbol)
        bar_count = len(sq.bars_1m) if sq else 0
        ema = sq.ema if sq else None
        armed = sq.armed if sq else None

        # Validate armed trigger vs. last replayed price — drops arms that are
        # already stale (trigger_high well below current price) before live
        # ticks can fire them. Complements the seed-gate which only suppresses
        # replayed signals, not stale trigger values. See
        # cowork_reports/2026-04-13_directive_stale_seed_fix.md.
        if sq:
            latest_price = all_ticks[-1].price if all_ticks else 0.0
            stale_msg = sq.validate_arm_after_seed(float(latest_price))
            if stale_msg:
                print(f"  [{symbol}] {stale_msg}", flush=True)
                armed = None  # refresh local summary for the Seeded log line

        # Mark seed complete — detector gate suppresses stale entries until live bars confirm
        if sq:
            sq.end_seed()
        state.seed_complete_time[symbol] = datetime.now(ET)
        state.live_tick_count_since_seed[symbol] = 0

        print(f"🔥 Seeded {symbol}: {len(all_ticks)} ticks → {bar_count} bars"
              + (f", EMA={ema:.4f}" if ema else "")
              + (f", ARMED" if armed else "")
              + f" ({len(all_ticks)//max(1,bar_count)} ticks/bar avg)",
              flush=True)

    except Exception as e:
        print(f"⚠️ Tick seed failed for {symbol}: {e} — falling back to 1m bars", flush=True)
        traceback.print_exc()
        _seed_symbol_bars_fallback(symbol)
        state.seed_complete_time[symbol] = datetime.now(ET)
        state.live_tick_count_since_seed[symbol] = 0


def seed_symbol_from_cache(symbol: str) -> bool:
    """Resume-mode seed: replay ticks from tick_cache/<today>/<sym>.json.gz
    into fresh detectors instead of fetching from IBKR. Returns True on
    success, False if no cache or empty (caller falls back to seed_symbol).

    Mirrors seed_symbol exactly below the tick-fetch step:
      - begin_seed on squeeze detector suppresses replayed signals
      - bar_builder_1m.on_trade replays ticks through the normal pipeline;
        MP/CT rebuild their state via on_bar_close_1m
      - validate_arm_after_seed drops stale trigger values
      - end_seed marks replay done; live ticks arriving after re-subscribe
        start feeding signals

    Crucially does NOT run ticks through on_ticker_update's downstream
    (on_trade_price) — that would fire entries retroactively. Same
    architectural guard the cold-path seed relies on.
    """
    today = datetime.now(ET).strftime("%Y-%m-%d")
    cache_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "tick_cache", today, f"{symbol}.json.gz",
    )
    if not os.path.exists(cache_path):
        return False

    try:
        with gzip.open(cache_path, "rt") as f:
            raw_ticks = json.load(f)
    except Exception as e:
        print(f"⚠️ [RESUME] {symbol} cache read failed: {e} — falling back to IBKR seed", flush=True)
        return False

    if not raw_ticks:
        return False

    try:
        sq = state.sq_detectors.get(symbol)
        if sq:
            sq.begin_seed()

        replayed = 0
        last_ts_utc = None
        for t in raw_ticks:
            try:
                price = float(t["p"])
                size = int(t["s"])
                ts_utc = datetime.fromisoformat(t["t"])
            except (KeyError, ValueError, TypeError):
                continue
            if price <= 0 or size <= 0:
                continue

            if state.bar_builder_1m:
                state.bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            if BOX_ENABLED and state.box_bar_builder_1m:
                state.box_bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            replayed += 1
            last_ts_utc = ts_utc

        sq = state.sq_detectors.get(symbol)
        bar_count = len(sq.bars_1m) if sq else 0
        ema = sq.ema if sq else None
        armed = sq.armed if sq else None

        if sq and raw_ticks:
            latest_price = float(raw_ticks[-1].get("p", 0))
            stale_msg = sq.validate_arm_after_seed(latest_price)
            if stale_msg:
                print(f"  [{symbol}] {stale_msg}", flush=True)
                armed = None

        if sq:
            sq.end_seed()
        state.seed_complete_time[symbol] = datetime.now(ET)
        state.live_tick_count_since_seed[symbol] = 0

        # Clock-drift log per Cowork ask — exposes any detector-time bugs.
        wall_utc = datetime.now(timezone.utc)
        drift_sec = (wall_utc - last_ts_utc).total_seconds() if last_ts_utc else None
        drift_str = f"{drift_sec/60:.1f}m" if drift_sec is not None else "?"
        print(f"🔁 [RESUME] {symbol}: {replayed:,} ticks → {bar_count} bars"
              + (f", EMA={ema:.4f}" if ema else "")
              + (", ARMED" if armed else "")
              + f" | drift={drift_str}",
              flush=True)
        return True
    except Exception as e:
        print(f"⚠️ [RESUME] {symbol} replay failed: {e} — falling back to IBKR seed", flush=True)
        traceback.print_exc()
        # Leave detector state partially built; caller will fall back to
        # seed_symbol which does begin_seed again (idempotent) and re-seeds
        # from IBKR. The worst case is a slightly extended boot.
        return False


def _seed_symbol_bars_fallback(symbol: str):
    """Fallback: seed with 1m historical bars (old method). Used when tick data unavailable."""
    contract = state.contracts.get(symbol)
    if not contract:
        return
    try:
        bars = state.ib.reqHistoricalData(
            contract, endDateTime='', durationStr='1 D',
            barSizeSetting='1 min', whatToShow='TRADES',
            useRTH=False, formatDate=1,
        )
        state.ib.sleep(0.5)
        if not bars:
            return
        for b in bars:
            o, h, l, c, v = b.open, b.high, b.low, b.close, b.volume
            if SQ_ENABLED and symbol in state.sq_detectors:
                state.sq_detectors[symbol].seed_bar_close(o, h, l, c, v)
            if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
                state.mp_detectors[symbol].seed_bar_close(o, h, l, c, v)
            if CT_ENABLED and symbol in state.ct_detectors:
                state.ct_detectors[symbol].seed_bar_close(o, h, l, c, v)
        print(f"🔥 Seeded {symbol} (fallback): {len(bars)} bars", flush=True)
    except Exception as e:
        print(f"⚠️ Fallback seed also failed for {symbol}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════════════════════════════════

def run_scanner():
    """Run the IBKR scanner and subscribe to top candidates.

    First scan of a session runs a WIDE catchup scan (multiple scanner codes)
    to find everything that moved today, even if we started late.
    Subsequent scans use the normal TOP_PERC_GAIN to catch new arrivals.
    """
    now = datetime.now(ET)

    # Only scan during active trading windows
    if not in_trading_window(now):
        return

    # Don't scan more than every 5 minutes
    if state.last_scan_time and (now - state.last_scan_time).total_seconds() < 300:
        return

    is_first_scan = state.last_scan_time is None

    if is_first_scan:
        # First scan of session: wide catchup to find everything that moved today
        print(f"\n🔄 CATCHUP SCAN at {now.strftime('%H:%M:%S')} ET (first scan — casting wide net)...", flush=True)
        state.candidates = scan_catchup(state.ib)
    else:
        # Subsequent scans: just check for new arrivals
        print(f"\n🔄 Running scanner at {now.strftime('%H:%M:%S')} ET...", flush=True)
        state.candidates = scan_premarket_live(state.ib)

    state.last_scan_time = now

    # Subscribe to new candidates (top 5 from catchup, or all new from rescan)
    max_new = 5 if is_first_scan else 5
    new_subs = 0
    for c in state.candidates[:max_new]:
        sym = c["symbol"]
        if sym not in state.active_symbols:
            subscribe_symbol(sym)
            new_subs += 1
            # Heartbeat between subscribes — qualifyContracts + reqMktData +
            # seed_symbol's tick pagination can each take 10-30s; without this,
            # 4-5 sequential subscribes blow past the 120s watchdog.
            update_heartbeat()

    # NOTE: We NEVER unsubscribe symbols during a session. Once subscribed,
    # a stock stays on the watchlist until the trading window closes.
    # This prevents losing coverage when a stock temporarily drops from
    # the scanner (e.g., RVOL dips below threshold between volume spikes).

    print(f"📊 Scanner: {len(state.candidates)} new candidates, "
          f"{new_subs} new subs, {len(state.active_symbols)} total watching", flush=True)


def poll_watchlist():
    """Read watchlist.txt (written by live_scanner.py / Databento) and subscribe to new symbols."""
    if not DATABENTO_BRIDGE:
        return
    if not os.path.exists(WATCHLIST_FILE):
        return

    try:
        with open(WATCHLIST_FILE, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return

    new_syms = []
    for line in lines:
        sym = line.split(":")[0].strip().upper()
        if sym and sym.isalpha() and 1 <= len(sym) <= 5:
            if sym not in state.active_symbols:
                new_syms.append(sym)

    if new_syms:
        print(f"\n📡 Databento bridge: {len(new_syms)} new symbols from watchlist.txt: {sorted(new_syms)}", flush=True)
        for sym in new_syms:
            subscribe_symbol(sym)


# ══════════════════════════════════════════════════════════════════════
# Bar Building + Detection
# ══════════════════════════════════════════════════════════════════════

def on_bar_close_1m(bar):
    """1-minute bar close: feed to squeeze + MP detectors."""
    symbol = bar.symbol
    now_str = datetime.now(ET).strftime("%H:%M")

    # Get VWAP from bar builder
    vwap = state.bar_builder_1m.get_vwap(symbol) if state.bar_builder_1m else None
    pm_high = state.bar_builder_1m.get_premarket_high(symbol) if state.bar_builder_1m else None

    # Diagnostic: log full chart state every 5 minutes per symbol
    hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else None
    minute = datetime.now(ET).minute
    if minute % 5 == 0:
        try:
            sq = state.sq_detectors.get(symbol)
            sq_state = sq._state if sq else "N/A"
            armed_lvl = f"${sq.armed.trigger_high:.2f}" if (sq and sq.armed) else "none"
            ema = f"{sq.ema:.2f}" if (sq and sq.ema) else "none"
            macd_hist = f"{sq.macd_state.histogram:.3f}" if (sq and hasattr(sq, 'macd_state') and sq.macd_state.histogram is not None) else "N/A"
            bar_count = len(sq.bars_1m) if (sq and hasattr(sq, 'bars_1m')) else 0
            avg_vol = sq._avg_prior_vol() if (sq and hasattr(sq, '_avg_prior_vol')) else 0
            vol_ratio = bar.volume / avg_vol if avg_vol > 0 else 0
            vwap_dist = ((bar.close - vwap) / vwap * 100) if vwap and vwap > 0 else 0
            print(f"[{now_str} ET] {symbol} CHART | "
                  f"O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume:,} | "
                  f"EMA9={ema} VWAP={vwap or 0:.2f} ({vwap_dist:+.1f}%) HOD={hod or 0:.2f} PM_H={pm_high or 0:.2f} | "
                  f"MACD={macd_hist} vol_ratio={vol_ratio:.1f}x avg_vol={avg_vol:,.0f} bars={bar_count} | "
                  f"sq={sq_state} armed={armed_lvl}", flush=True)
        except Exception as e:
            print(f"[{now_str} ET] {symbol} CHART diagnostic error: {e}", flush=True)

    # Squeeze detection
    if SQ_ENABLED and symbol in state.sq_detectors:
        sq = state.sq_detectors[symbol]
        if pm_high:
            pm_bf = state.bar_builder_1m.get_premarket_bull_flag_high(symbol) if state.bar_builder_1m else None
            sq.update_premarket_levels(pm_high, pm_bf)
        sq_msg = sq.on_bar_close_1m(bar, vwap=vwap)
        if sq_msg:
            if "ARMED" in sq_msg:
                print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            elif "SQ_PRIMED" in sq_msg:
                print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            elif "SQ_REJECT" in sq_msg or "SQ_RESET" in sq_msg:
                print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)

    # MP detection (standalone MP or V2 re-entry)
    if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
        mp = state.mp_detectors[symbol]
        mp_msg = mp.on_bar_close_1m(bar, vwap=vwap)
        if mp_msg and ("ARMED" in mp_msg or "MP_V2" in mp_msg):
            print(f"[{now_str} ET] {symbol} MP | {mp_msg}", flush=True)

    # Continuation detection (post-squeeze — only when SQ is fully idle + lockout clear)
    _ct_sq_idle = not (SQ_ENABLED and symbol in state.sq_detectors and
                       (state.sq_detectors[symbol]._state != "IDLE" or state.sq_detectors[symbol]._in_trade))
    if CT_ENABLED and _ct_sq_idle and symbol in state.ct_detectors:
        ct = state.ct_detectors[symbol]
        # Check for pending activation (deferred from squeeze close)
        _ct_act = ct.check_pending_activation(bar_time=now_str)
        if _ct_act:
            print(f"[{now_str} ET] {symbol} CT | {_ct_act}", flush=True)
        ct_msg = ct.on_bar_close_1m(bar, vwap=vwap, bar_time=now_str)
        if ct_msg:
            if "CT_ARMED" in ct_msg or "CT_REJECT" in ct_msg or "CT_RESET" in ct_msg:
                print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)
            elif "CT_WATCHING" in ct_msg or "CT_PULLBACK" in ct_msg or "CT_PAUSE" in ct_msg:
                print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)

    # ── EPL: 1m bar processing ──
    if EPL_ENABLED and state.epl_registry and state.epl_registry.strategy_count > 0:
        now_et = datetime.now(ET)
        # Expiry check
        expired = state.epl_watchlist.check_expiry(now_et)
        for esym in expired:
            state.epl_registry.notify_expiry(esym)
            state.epl_watchlist.remove(esym)
            print(f"[{now_str} ET] [EPL] {esym} expired from watchlist", flush=True)

        # EPL exit management (1m bar)
        pos = state.open_position
        if pos and pos.get("setup_type", "").startswith("epl_") and pos["symbol"] == symbol:
            epl_strat = state.epl_registry.get_strategy(pos["setup_type"])
            if epl_strat:
                bar_dict = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                            "v": bar.volume, "green": bar.close >= bar.open, "vwap": vwap}
                epl_exit = epl_strat.manage_exit(symbol, bar.close, bar_dict)
                if epl_exit:
                    print(f"[{now_str} ET] [EPL] {epl_exit.strategy} EXIT {symbol} "
                          f"@ ${epl_exit.exit_price:.2f} reason={epl_exit.exit_reason}", flush=True)
                    exit_trade(symbol, epl_exit.exit_price, pos["qty"], epl_exit.exit_reason)
                    if state.epl_arbitrator:
                        epl_pnl = (epl_exit.exit_price - pos["entry"]) * pos["qty"]
                        state.epl_arbitrator.record_epl_trade_result(symbol, epl_pnl)
                    state.epl_registry.reset_all(symbol)

        # EPL entry signals (1m bar)
        if state.open_position is None and state.epl_watchlist.is_graduated(symbol):
            sq_state = state.sq_detectors[symbol]._state if (SQ_ENABLED and symbol in state.sq_detectors) else "IDLE"
            if state.epl_arbitrator.can_epl_enter(symbol, sq_state, False, now_et):
                bar_dict = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                            "v": bar.volume, "green": bar.close >= bar.open, "vwap": vwap}
                signals = state.epl_registry.collect_entry_signals(symbol, bar_dict, None, None)
                best = state.epl_arbitrator.get_best_signal(signals)
                if best:
                    _enter_epl_trade(symbol, best)


def _in_tw_grace() -> bool:
    """True if the open trade is within the topping wicky grace period."""
    pos = state.open_position
    if pos is None or TW_GRACE_MIN <= 0:
        return False
    minutes_in = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
    return minutes_in < TW_GRACE_MIN


def _in_be_grace() -> bool:
    """True if the open trade is within the BE time-based grace period."""
    pos = state.open_position
    if pos is None or BE_GRACE_MIN <= 0:
        return False
    minutes_in = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
    return minutes_in < BE_GRACE_MIN


def _in_parabolic_grace(symbol: str, bar_close: float) -> bool:
    """Suppress BE exits during genuine parabolic ramps (not flash spikes)."""
    if not BE_PARABOLIC_GRACE:
        return False
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return False
    if pos["r"] <= 0 or bar_close < pos["entry"] + (BE_GRACE_MIN_R * pos["r"]):
        return False
    highs = state.recent_10s_highs.get(symbol, [])
    if len(highs) < 2:
        return False
    window = highs[-BE_GRACE_LOOKBACK:]
    new_high_count = 0
    running = window[0]
    for bh in window[1:]:
        if bh > running:
            new_high_count += 1
            running = bh
    return new_high_count >= BE_GRACE_MIN_NEW_HIGHS


def on_bar_close_10s(bar):
    """10-second bar close: candle pattern exit detection (parity with simulate.py)."""
    if not SQ_CANDLE_EXITS_ENABLED:
        return

    symbol = bar.symbol
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return
    if not pos.get("fill_confirmed", False):
        return
    if pos["setup_type"] not in ("squeeze", "mp_reentry", "continuation"):
        return

    now_str = datetime.now(ET).strftime("%H:%M:%S")

    # Ensure PatternDetector exists for this symbol
    if symbol not in state.pattern_dets:
        state.pattern_dets[symbol] = PatternDetector()

    det = state.pattern_dets[symbol]
    signals = det.update(bar.open, bar.high, bar.low, bar.close, bar.volume)
    signal_names = [s.name for s in signals]

    # Track prev 10s bar for bearish engulfing
    prev = state.prev_10s_bar.get(symbol)
    state.prev_10s_bar[symbol] = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close}

    # Track 10s highs for parabolic grace
    highs = state.recent_10s_highs.setdefault(symbol, [])
    highs.append(bar.high)
    if len(highs) > BE_GRACE_LOOKBACK + 5:
        state.recent_10s_highs[symbol] = highs[-(BE_GRACE_LOOKBACK + 5):]

    entry = pos["entry"]
    r = pos["r"]
    qty = pos["qty"]

    # ── Topping Wicky exit ──
    if EXIT_ON_TOPPING_WICKY and "TOPPING_WICKY" in signal_names:
        if not _in_tw_grace():
            # Profit gate: suppress TW on confirmed runners (profit >= min R)
            tw_ok = True
            if TW_MIN_PROFIT_R > 0 and r > 0:
                unrealized = bar.close - entry
                if unrealized >= TW_MIN_PROFIT_R * r:
                    tw_ok = False
                    print(f"[{now_str} ET] {symbol} TW_SUPPRESSED (profit_gate: "
                          f"${unrealized:.2f} >= {TW_MIN_PROFIT_R}R=${TW_MIN_PROFIT_R * r:.2f})", flush=True)
            if tw_ok:
                print(f"[{now_str} ET] {symbol} TOPPING_WICKY_EXIT @ {bar.close:.4f}", flush=True)
                exit_trade(symbol, bar.close, qty, "topping_wicky_exit")
                return
        else:
            print(f"[{now_str} ET] {symbol} TW_SUPPRESSED (grace period)", flush=True)

    # ── Bearish Engulfing exit ──
    if EXIT_ON_BEAR_ENGULF and prev is not None:
        if is_bearish_engulfing(bar.open, bar.high, bar.low, bar.close,
                                prev["o"], prev["h"], prev["l"], prev["c"]):
            if _in_be_grace():
                print(f"[{now_str} ET] {symbol} BE_SUPPRESSED (time grace)", flush=True)
            elif _in_parabolic_grace(symbol, bar.close):
                print(f"[{now_str} ET] {symbol} BE_SUPPRESSED (parabolic grace)", flush=True)
            else:
                # In signal mode (exit_mode=signal), BE exits are part of cascading strategy — no profit gate
                print(f"[{now_str} ET] {symbol} BEARISH_ENGULFING_EXIT @ {bar.close:.4f}", flush=True)
                exit_trade(symbol, bar.close, qty, "bearish_engulfing_exit")
                return


def check_triggers(symbol: str, price: float):
    """Check if any armed detector triggers on this price."""
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    is_premarket = datetime.now(ET).hour < 9 or (datetime.now(ET).hour == 9 and datetime.now(ET).minute < 30)

    # Already in a position — no new entries
    if state.open_position is not None:
        return

    # Box position blocks momentum entry (unless simultaneous allowed)
    if BOX_ENABLED and not BOX_SIMULTANEOUS and state.box_position is not None:
        return

    # Daily risk check
    if DAILY_LOSS_SCALE:
        effective_max_loss = max(MAX_DAILY_LOSS, STARTING_EQUITY * 0.02)
    else:
        effective_max_loss = MAX_DAILY_LOSS
    if state.daily_pnl <= -effective_max_loss:
        return
    if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return

    # Squeeze trigger (priority)
    if SQ_ENABLED and symbol in state.sq_detectors:
        sq = state.sq_detectors[symbol]
        armed_before = sq.armed
        sq_msg = sq.on_trade_price(price, is_premarket=is_premarket)
        if sq_msg and "SQ_SEED_GATE" in sq_msg:
            # Detector suppressed a stale entry from seed replay — log it
            print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            return
        if sq_msg and "ENTRY SIGNAL" in sq_msg and armed_before:
            print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            enter_trade(symbol, armed_before, "squeeze")
            sq.notify_trade_opened()
            return

    # Continuation trigger (after SQ, before MP)
    if CT_ENABLED and symbol in state.ct_detectors:
        ct = state.ct_detectors[symbol]
        ct_armed_before = ct.armed
        if ct_armed_before is not None:
            # SQ-priority gate: defer CT if SQ is actively hunting
            ct_deferred = False
            if SQ_ENABLED and symbol in state.sq_detectors:
                sq = state.sq_detectors[symbol]
                if sq._state != "IDLE" or sq._in_trade:
                    print(f"[{now_str} ET] {symbol} CT | DEFERRED (SQ priority: state={sq._state})", flush=True)
                    ct_deferred = True
            if not ct_deferred:
                ct_msg = ct.on_trade_price(price, is_premarket=is_premarket)
                if ct_msg and "ENTRY SIGNAL" in ct_msg:
                    print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)
                    enter_trade(symbol, ct_armed_before, "continuation")
                    return

    # MP trigger (standalone or V2 re-entry)
    if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
        mp = state.mp_detectors[symbol]
        armed_before = mp.armed
        mp_msg = mp.on_trade_price(price, is_premarket=is_premarket)
        if mp_msg and "ENTRY SIGNAL" in mp_msg and armed_before:
            _mp_setup_type = getattr(armed_before, 'setup_type', 'micro_pullback')
            # Block standalone MP entries if MP_ENABLED is off (only allow mp_reentry from V2)
            if not MP_ENABLED and _mp_setup_type != "mp_reentry":
                return
            # SQ-priority gate: defer MP V2 if SQ is actively hunting
            if _mp_setup_type == "mp_reentry" and SQ_ENABLED and symbol in state.sq_detectors:
                sq = state.sq_detectors[symbol]
                if sq._state != "IDLE" or sq._in_trade:
                    print(f"[{now_str} ET] {symbol} MP_V2 | DEFERRED (SQ priority: state={sq._state})", flush=True)
                    return
            print(f"[{now_str} ET] {symbol} MP | {mp_msg}", flush=True)
            enter_trade(symbol, armed_before, _mp_setup_type)
            return


# ══════════════════════════════════════════════════════════════════════
# Order Execution
# ══════════════════════════════════════════════════════════════════════

def _verify_fill_with_retry(symbol, qty, r, initial_order_id, initial_limit,
                             original_limit, position_attr, log_prefix=""):
    """Poll Alpaca for fill. On timeout: cancel + reprice to current market +
    resubmit, up to ENTRY_MAX_RETRIES times. Aborts if market runs above
    original_limit × (1 + ENTRY_MAX_CHASE_PCT/100). See directive
    2026-04-15_directive_entry_slippage_retry.md.
    """
    cur_order_id = initial_order_id
    cur_limit = initial_limit
    attempt = 0
    while True:
        deadline = time.time() + ENTRY_RETRY_TIMEOUT_SEC
        filled = False
        terminal = False
        while time.time() < deadline:
            try:
                o = state.alpaca.get_order_by_id(cur_order_id)
                if o.status == 'filled':
                    actual_price = float(o.filled_avg_price)
                    actual_qty = int(float(o.filled_qty))
                    pos = getattr(state, position_attr)
                    if pos and pos.get("order_id") == cur_order_id:
                        pos["entry"] = actual_price
                        pos["qty"] = actual_qty
                        if "peak" in pos:
                            pos["peak"] = max(pos["peak"], actual_price)
                        if "stop" in pos and r is not None:
                            pos["stop"] = actual_price - r
                        pos["fill_confirmed"] = True
                        state.pending_order = None
                        print(f"  {log_prefix}FILL: {symbol} @ ${actual_price:.4f} qty={actual_qty}"
                              + (f" (after {attempt} retries)" if attempt > 0 else ""),
                              flush=True)
                        # Persist managed-trade state on fill confirmation.
                        # Reactive-exit architecture: manage_exit() is the
                        # protection layer, so fill-confirmed = protected.
                        # Box positions are not persisted in v1 (deferred).
                        if position_attr == "open_position":
                            persist_open_trades()
                    filled = True
                    break
                if o.status in ('cancelled', 'expired', 'rejected'):
                    print(f"  {log_prefix}ORDER {o.status.upper()}: {symbol} {cur_order_id}", flush=True)
                    terminal = True
                    break
            except Exception as e:
                print(f"  {log_prefix}FILL CHECK ERROR: {e}", flush=True)
            time.sleep(0.5)

        if filled:
            return
        if terminal:
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            return

        # Timed out — decide whether to retry
        if not ENTRY_RETRY_ENABLED or attempt >= ENTRY_MAX_RETRIES:
            print(f"  {log_prefix}ORDER TIMEOUT: cancelling {cur_order_id}"
                  + (f" after {attempt} retries" if attempt > 0 else ""),
                  flush=True)
            try: state.alpaca.cancel_order_by_id(cur_order_id)
            except Exception: pass
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            return

        # Retry: cancel current, reprice to current market, resubmit
        try: state.alpaca.cancel_order_by_id(cur_order_id)
        except Exception: pass
        time.sleep(0.3)

        cur_price = state.last_tick_price.get(symbol, cur_limit) or cur_limit
        max_chase_price = original_limit * (1 + ENTRY_MAX_CHASE_PCT / 100.0)
        if cur_price > max_chase_price:
            print(f"  {log_prefix}ORDER TIMEOUT: {symbol} market ${cur_price:.2f} exceeds max chase "
                  f"${max_chase_price:.2f} ({ENTRY_MAX_CHASE_PCT}% above original ${original_limit:.2f}) — giving up",
                  flush=True)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            return

        slip = _entry_slippage_for(cur_price)
        new_limit = round(cur_price + slip, 2)
        attempt += 1
        print(f"  {log_prefix}RETRY {attempt}/{ENTRY_MAX_RETRIES}: {symbol} market=${cur_price:.2f} "
              f"new_limit=${new_limit:.2f} (slip=${slip:.3f})", flush=True)

        try:
            req = LimitOrderRequest(
                symbol=symbol, qty=qty, side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY, limit_price=new_limit, extended_hours=True,
            )
            new_alpaca_order = state.alpaca.submit_order(req)
            prev_id = cur_order_id
            cur_order_id = str(new_alpaca_order.id)
            cur_limit = new_limit
            print(f"  {log_prefix}ALPACA ORDER: {cur_order_id} BUY {qty} {symbol} @ ${new_limit:.2f} (retry)", flush=True)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == prev_id:
                pos["order_id"] = cur_order_id
                pos["entry"] = new_limit
            if state.pending_order:
                state.pending_order["order_id"] = cur_order_id
                state.pending_order["placed_time"] = datetime.now(ET)
        except Exception as e:
            print(f"  {log_prefix}RETRY SUBMIT FAILED: {e}", flush=True)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            return


def enter_trade(symbol: str, armed, setup_type: str):
    """Place entry order via IBKR."""
    entry = armed.trigger_high
    stop = armed.stop_low
    r = armed.r
    score = armed.score
    size_mult = getattr(armed, 'size_mult', 1.0)

    if r <= 0 or r < MIN_R:
        print(f"  SKIP: R={r:.4f} < min {MIN_R}", flush=True)
        return

    # Dynamic equity-based risk: 2.5% of current equity
    current_equity = STARTING_EQUITY + state.daily_pnl  # STARTING_EQUITY is set from IBKR NetLiquidation at startup
    risk_dollars = max(50, current_equity * RISK_PCT)

    # Size calculation — scale notional with equity if enabled
    effective_notional = MAX_NOTIONAL
    if SCALE_NOTIONAL:
        effective_notional = max(MAX_NOTIONAL, current_equity * 2)  # 50% buying power (2x equity)
    qty = int(math.floor(risk_dollars / r))
    qty_notional = int(math.floor(effective_notional / max(entry, 0.01)))
    qty = min(qty, qty_notional, MAX_SHARES)

    notional = qty * entry
    print(f"  Sizing: equity=${current_equity:,.0f} risk=${risk_dollars:,.0f} "
          f"qty={qty} notional=${notional:,.0f}" +
          (f" (scaled max=${effective_notional:,.0f})" if SCALE_NOTIONAL else ""),
          flush=True)

    if size_mult < 1.0:
        qty = max(1, int(math.floor(qty * size_mult)))

    if qty <= 0:
        return

    # Place limit order with dynamic slippage (trigger + max(MIN, price × PCT))
    initial_slip = _entry_slippage_for(entry)
    limit_price = round(entry + initial_slip, 2)
    original_limit = limit_price  # preserved for MAX_CHASE_PCT cap during retries

    print(f"🟩 ENTRY: {symbol} qty={qty} limit=${limit_price:.2f} (slip=${initial_slip:.3f}) "
          f"stop=${stop:.4f} R=${r:.4f} score={score:.1f} "
          f"type={setup_type}", flush=True)

    try:
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True,
        )
        alpaca_order = state.alpaca.submit_order(req)
        order_id = str(alpaca_order.id)
        print(f"  ALPACA ORDER: {order_id} BUY {qty} {symbol} @ ${limit_price:.2f}", flush=True)
    except Exception as e:
        print(f"  ALPACA ORDER FAILED: {e}", flush=True)
        return

    state.open_position = {
        "symbol": symbol,
        "qty": qty,
        "entry": limit_price,
        "stop": stop,
        "r": r,
        "score": score,
        "setup_type": setup_type,
        "peak": limit_price,
        "tp_hit": False,
        "entry_time": datetime.now(ET),
        "order_id": order_id,
        "is_parabolic": "[PARABOLIC]" in (armed.score_detail or ""),
        "fill_confirmed": False,
    }

    # Store pending order for timeout check
    state.pending_order = {
        "order_id": order_id,
        "placed_time": datetime.now(ET),
        "timeout_seconds": 15,
    }

    # Verify fill in background — dynamic slippage + retry-on-timeout via
    # _verify_fill_with_retry (see helper docstring + directive).
    def verify_alpaca_fill():
        _verify_fill_with_retry(
            symbol=symbol, qty=qty, r=r,
            initial_order_id=order_id, initial_limit=limit_price,
            original_limit=original_limit, position_attr="open_position",
        )

    import threading
    threading.Thread(target=verify_alpaca_fill, daemon=True).start()


def _enter_epl_trade(symbol: str, signal):
    """Place EPL entry order via Alpaca."""
    entry = signal.entry_price
    stop = signal.stop_price
    r = entry - stop
    if r <= 0 or r < MIN_R:
        return

    qty = int(math.floor(EPL_MAX_NOTIONAL * signal.position_size_pct / max(entry, 0.01)))
    qty = min(qty, MAX_SHARES)
    if qty <= 0:
        return

    initial_slip = _entry_slippage_for(entry)
    limit_price = round(entry + initial_slip, 2)
    original_limit = limit_price
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    print(f"[{now_str} ET] [EPL] 🟩 ENTRY: {symbol} strategy={signal.strategy} "
          f"qty={qty} limit=${limit_price:.2f} (slip=${initial_slip:.3f}) "
          f"stop=${stop:.4f} R=${r:.4f} reason={signal.reason}", flush=True)

    try:
        req = LimitOrderRequest(
            symbol=symbol, qty=qty, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY, limit_price=limit_price, extended_hours=True,
        )
        alpaca_order = state.alpaca.submit_order(req)
        order_id = str(alpaca_order.id)
        print(f"  [EPL] ALPACA ORDER: {order_id}", flush=True)
    except Exception as e:
        print(f"  [EPL] ORDER FAILED: {e}", flush=True)
        return

    state.open_position = {
        "symbol": symbol, "qty": qty, "entry": limit_price, "stop": stop,
        "r": r, "score": signal.confidence * 10, "setup_type": signal.strategy,
        "peak": limit_price, "tp_hit": False, "entry_time": datetime.now(ET),
        "order_id": order_id, "is_parabolic": False, "fill_confirmed": False,
    }
    state.pending_order = {"order_id": order_id, "placed_time": datetime.now(ET), "timeout_seconds": 15}

    epl_strat = state.epl_registry.get_strategy(signal.strategy)
    if epl_strat and hasattr(epl_strat, 'mark_in_trade'):
        epl_strat.mark_in_trade(symbol)

    import threading
    def verify_epl_fill():
        _verify_fill_with_retry(
            symbol=symbol, qty=qty, r=r,
            initial_order_id=order_id, initial_limit=limit_price,
            original_limit=original_limit, position_attr="open_position",
            log_prefix="[EPL] ",
        )
    threading.Thread(target=verify_epl_fill, daemon=True).start()


def manage_exit(symbol: str, price: float):
    """Manage exit for open position."""
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return

    # Don't manage exits until entry fill is confirmed
    if not pos.get('fill_confirmed', False):
        return

    # Update peak (persist on advance — see cowork review note on write
    # frequency: peaks advance only on new highs, not every tick, so ~10–50
    # writes per active trade is the realistic upper bound).
    if price > pos["peak"]:
        pos["peak"] = price
        persist_open_trades()

    entry = pos["entry"]
    stop = pos["stop"]
    r = pos["r"]
    qty = pos["qty"]
    setup_type = pos["setup_type"]

    # ── Bail timer ──
    if BAIL_TIMER_ENABLED:
        minutes_in = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
        if minutes_in >= BAIL_TIMER_MINUTES and price <= entry:
            exit_trade(symbol, price, qty, "bail_timer")
            return

    if setup_type.startswith("epl_"):
        return  # EPL exits handled via strategy.manage_exit() in tick/bar processing
    elif setup_type in ("squeeze", "mp_reentry", "continuation"):
        _squeeze_exit(symbol, price, pos)
    else:
        _mp_exit(symbol, price, pos)


def _squeeze_exit(symbol: str, price: float, pos: dict):
    """Squeeze exit ladder — matches simulate.py exactly."""
    entry = pos["entry"]
    stop = pos["stop"]
    r = pos["r"]
    qty = pos["qty"]

    # 0) Dollar loss cap
    if SQ_MAX_LOSS_DOLLARS > 0:
        unrealized_loss = (entry - price) * qty
        if unrealized_loss >= SQ_MAX_LOSS_DOLLARS:
            exit_trade(symbol, price, qty, f"sq_dollar_loss_cap (${unrealized_loss:,.0f})")
            return

    # 1) Hard stop
    if price <= stop:
        exit_trade(symbol, price, qty, "sq_stop_hit")
        return

    # Pre-target phase
    if not pos["tp_hit"]:
        # 2) Trailing stop
        if r > 0:
            trail_r = SQ_PARA_TRAIL_R if pos.get("is_parabolic") else SQ_TRAIL_R
            trail_price = pos["peak"] - (trail_r * r)
            if price <= trail_price:
                reason = "sq_para_trail_exit" if pos.get("is_parabolic") else "sq_trail_exit"
                exit_trade(symbol, price, qty, reason)
                return

        # 3) Target hit — exit core, keep runner
        if r > 0 and price >= entry + (SQ_TARGET_R * r):
            pos["tp_hit"] = True
            # Stamp partial-fill state for resume rehydrate schema.
            pos["partial_filled_at"] = datetime.now(timezone.utc).isoformat()
            # EPL graduation: stock hit 2R, add to watchlist for re-entry
            if EPL_ENABLED and state.epl_watchlist is not None:
                realized_r = (price - entry) / r if r > 0 else 0
                if realized_r >= EPL_MIN_GRADUATION_R:
                    _vwap = state.bar_builder_1m.get_vwap(symbol) if state.bar_builder_1m else 0
                    _hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else 0
                    _pm_h = state.bar_builder_1m.get_premarket_high(symbol) if state.bar_builder_1m else 0
                    ctx = GraduationContext(
                        symbol=symbol, graduation_time=datetime.now(ET),
                        graduation_price=price, sq_entry_price=entry, sq_stop_price=stop,
                        hod_at_graduation=_hod or 0, vwap_at_graduation=_vwap or 0,
                        pm_high=_pm_h or 0, avg_volume_at_graduation=0,
                        sq_trade_count=1, r_value=r,
                    )
                    state.epl_watchlist.add(ctx)
                    state.epl_registry.notify_graduation(ctx)
                    _now = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{_now} ET] [EPL] {symbol} GRADUATED @ ${price:.2f} "
                          f"(R={realized_r:.1f})", flush=True)
            qty_core = max(1, int(qty * SQ_CORE_PCT / 100))
            qty_runner = qty - qty_core
            pos["partial_filled_qty"] = qty_core
            if qty_runner > 0:
                pos["runner_stop"] = max(stop, entry + 0.01)
                exit_trade(symbol, price, qty_core, "sq_target_hit")
                pos["qty"] = qty_runner  # Set AFTER exit_trade so remaining calc is correct
                # tp_hit + trail_mode change + qty shift all need persisting;
                # exit_trade already persisted (full exit case) or we persist
                # the runner state here.
                if state.open_position:
                    persist_open_trades()
            else:
                exit_trade(symbol, price, qty, "sq_target_hit")
            return

    # Post-target (runner)
    if pos["tp_hit"] and pos["qty"] > 0:
        if r > 0:
            runner_trail = pos["peak"] - (SQ_RUNNER_TRAIL_R * r)
            runner_stop = max(pos.get("runner_stop", stop), runner_trail)
            if price <= runner_stop:
                exit_trade(symbol, price, pos["qty"], "sq_runner_trail")
                return


def _mp_exit(symbol: str, price: float, pos: dict):
    """MP exit — simplified signal mode."""
    if price <= pos["stop"]:
        exit_trade(symbol, price, pos["qty"], "stop_hit")


def exit_trade(symbol: str, price: float, qty: int, reason: str):
    """Place exit order via ALPACA and record trade."""
    # For urgent exits (stop hit, dollar loss cap, max loss), use very aggressive limit
    urgent_reasons = ('sq_stop_hit', 'sq_dollar_loss_cap', 'sq_max_loss_hit', 'stop_hit')
    if reason in urgent_reasons:
        limit_price = round(price * 0.97, 2)  # 3% below current price
    else:
        limit_price = round(price - 0.03, 2)

    try:
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True,
        )
        alpaca_order = state.alpaca.submit_order(req)
        print(f"  ALPACA EXIT: {alpaca_order.id} SELL {qty} {symbol} @ ${limit_price:.2f}", flush=True)
    except Exception as e:
        print(f"  ALPACA EXIT FAILED: {e} — trying market order", flush=True)
        try:
            from alpaca.trading.requests import MarketOrderRequest
            req = MarketOrderRequest(
                symbol=symbol,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.DAY,
            )
            alpaca_order = state.alpaca.submit_order(req)
            print(f"  ALPACA MARKET EXIT: {alpaca_order.id} SELL {qty} {symbol}", flush=True)
        except Exception as e2:
            print(f"  ALPACA MARKET EXIT ALSO FAILED: {e2}", flush=True)

    pos = state.open_position
    pnl = (price - pos["entry"]) * qty
    state.daily_pnl += pnl
    state.daily_trades += 1

    if pnl < 0:
        state.consecutive_losses += 1
    else:
        state.consecutive_losses = 0

    print(f"🟥 EXIT: {symbol} qty={qty} @ ${price:.4f} reason={reason} "
          f"P&L=${pnl:+,.0f} daily=${state.daily_pnl:+,.0f}", flush=True)

    state.closed_trades.append({
        "symbol": symbol,
        "entry": pos["entry"],
        "exit": price,
        "qty": qty,
        "pnl": pnl,
        "reason": reason,
        "setup_type": pos["setup_type"],
        "time": datetime.now(ET).strftime("%H:%M:%S"),
    })

    # Notify squeeze detector
    if SQ_ENABLED and symbol in state.sq_detectors:
        state.sq_detectors[symbol].notify_trade_closed(symbol, pnl)

    # MP V2: unlock re-entry detection when squeeze trade closes
    if pos["setup_type"] == "squeeze" and symbol in state.mp_detectors:
        state.mp_detectors[symbol].notify_squeeze_closed(symbol, pnl)

    # MP V2: track re-entry count when mp_reentry trade closes
    if pos["setup_type"] == "mp_reentry" and symbol in state.mp_detectors:
        state.mp_detectors[symbol].notify_reentry_closed()

    # CT: unlock continuation detection when squeeze trade closes
    if pos["setup_type"] == "squeeze" and CT_ENABLED and symbol in state.ct_detectors:
        hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else 0
        avg_vol = 0
        sq = state.sq_detectors.get(symbol)
        if sq and hasattr(sq, 'bars_1m') and sq.bars_1m:
            avg_vol = sum(b.get("v", 0) if isinstance(b, dict) else getattr(b, "volume", 0)
                          for b in sq.bars_1m) / len(sq.bars_1m)
        _ct_now_str = datetime.now(ET).strftime("%H:%M")
        state.ct_detectors[symbol].notify_squeeze_closed(
            symbol, pnl,
            entry=pos["entry"], exit_price=price,
            hod=hod or 0, avg_squeeze_vol=avg_vol,
            bar_time=_ct_now_str,
        )

    # CT: track re-entry count when continuation trade closes
    if pos["setup_type"] == "continuation" and CT_ENABLED and symbol in state.ct_detectors:
        state.ct_detectors[symbol].notify_continuation_closed(pnl)

    # Clear position if fully exited
    remaining = pos["qty"] - qty
    if remaining <= 0:
        state.open_position = None
    else:
        pos["qty"] = remaining

    # Persist post-exit state: open_trades shrinks (empty on full exit, or
    # updated with new qty on partial), risk picks up the closed trade.
    persist_open_trades()
    persist_risk()


# ══════════════════════════════════════════════════════════════════════
# Halt Detection
# ══════════════════════════════════════════════════════════════════════

_halted_symbols: set = set()  # Track which symbols are currently halted (debounce)

def check_halts():
    """Check for halted stocks via Tick Type 49. Debounced — prints once per halt event."""
    for symbol in state.active_symbols:
        ticker = state.tickers.get(symbol)
        if ticker and hasattr(ticker, 'halted'):
            if ticker.halted == 1 or ticker.halted == 2:
                if symbol not in _halted_symbols:
                    halt_type = "regulatory" if ticker.halted == 1 else "volatility"
                    print(f"⚠️ HALT DETECTED: {symbol} ({halt_type})", flush=True)
                    _halted_symbols.add(symbol)
            else:
                if symbol in _halted_symbols:
                    print(f"✅ HALT RESUMED: {symbol}", flush=True)
                    _halted_symbols.discard(symbol)


# ══════════════════════════════════════════════════════════════════════
# Main Loop
# ══════════════════════════════════════════════════════════════════════

def on_ticker_update(tickers):
    """Called on every market data update (~250ms). Receives a SET of updated tickers."""
    state.last_on_ticker_fire = datetime.now(ET)
    for ticker in tickers:
        _process_ticker(ticker)


def _process_ticker(ticker):
    """Process a single ticker update."""
    contract = ticker.contract
    if not contract:
        return
    symbol = contract.symbol

    # Determine if we have a valid trade price
    trade_price = ticker.last
    is_trade = (trade_price is not None and not math.isnan(trade_price) and trade_price > 0)

    # Fallback price for health monitoring: use bid or ask if no trade price
    health_price = None
    for attr in ('last', 'bid', 'ask'):
        p = getattr(ticker, attr, None)
        if p is not None and not math.isnan(p) and p > 0:
            health_price = p
            break

    if health_price is None:
        return

    ts = datetime.now(ET)

    # Always update health monitoring (even with bid/ask fallback)
    state.tick_counts[symbol] = state.tick_counts.get(symbol, 0) + 1
    state.last_tick_time[symbol] = ts
    state.last_tick_price[symbol] = health_price

    # Only feed trade prices to bar builders, triggers, and exit management
    if not is_trade:
        return

    price = trade_price

    # Get trade size from ticker (lastSize = size of most recent trade print)
    size = int(ticker.lastSize) if ticker.lastSize and not math.isnan(ticker.lastSize) else 0

    # Record tick for backtest cache (exact same data the bot sees).
    # Lock serializes against the periodic flush swap — see _tick_flush_loop.
    with _tick_buffer_lock:
        if symbol not in state.tick_buffer:
            state.tick_buffer[symbol] = []
        state.tick_buffer[symbol].append({
            "p": price,
            "s": size,
            "t": ts.astimezone(timezone.utc).isoformat(),
        })

    # Track live ticks since seed (for stale signal suppression)
    if symbol in state.live_tick_count_since_seed:
        state.live_tick_count_since_seed[symbol] += 1

    # Feed to bar builders (price + volume)
    if state.bar_builder_1m:
        state.bar_builder_1m.on_trade(symbol, price, size, ts)
    if state.bar_builder_10s:
        state.bar_builder_10s.on_trade(symbol, price, size, ts)

    # Feed to box bar builder (separate from momentum)
    if BOX_ENABLED and state.box_bar_builder_1m and symbol == state.box_active_symbol:
        state.box_bar_builder_1m.on_trade(symbol, price, size, ts)

    # Check triggers
    check_triggers(symbol, price)

    # ── EPL tick processing ──
    if EPL_ENABLED and state.epl_registry and state.epl_registry.strategy_count > 0:
        pos = state.open_position
        # EPL tick-level exit
        if pos and pos.get("setup_type", "").startswith("epl_") and pos["symbol"] == symbol:
            epl_strat = state.epl_registry.get_strategy(pos["setup_type"])
            if epl_strat:
                epl_exit = epl_strat.manage_exit(symbol, price, None)
                if epl_exit:
                    _now = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{_now} ET] [EPL] {epl_exit.strategy} EXIT {symbol} "
                          f"@ ${epl_exit.exit_price:.2f} reason={epl_exit.exit_reason}", flush=True)
                    exit_trade(symbol, epl_exit.exit_price, pos["qty"], epl_exit.exit_reason)
                    if state.epl_arbitrator:
                        epl_pnl = (epl_exit.exit_price - pos["entry"]) * pos["qty"]
                        state.epl_arbitrator.record_epl_trade_result(symbol, epl_pnl)
                    state.epl_registry.reset_all(symbol)
                    return
        # EPL tick-level entry trigger
        if state.open_position is None and state.epl_watchlist and state.epl_watchlist.is_graduated(symbol):
            sq_state = state.sq_detectors[symbol]._state if (SQ_ENABLED and symbol in state.sq_detectors) else "IDLE"
            if state.epl_arbitrator.can_epl_enter(symbol, sq_state, False, datetime.now(ET)):
                signals = state.epl_registry.collect_entry_signals(symbol, None, price, size)
                best = state.epl_arbitrator.get_best_signal(signals)
                if best:
                    _enter_epl_trade(symbol, best)
                    return

    # Manage exits
    if state.open_position and state.open_position["symbol"] == symbol:
        manage_exit(symbol, price)


def save_tick_cache(source: dict | None = None):
    """Save recorded ticks to tick_cache/ for future backtesting.
    Uses the exact same format simulate.py --ticks expects.

    If source is provided, saves from that dict instead of state.tick_buffer.
    This lets the periodic flush thread swap-and-save without racing the
    live tick-callback thread that writes into state.tick_buffer.
    """
    if source is None:
        source = state.tick_buffer
    today = datetime.now(ET).strftime("%Y-%m-%d")
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_cache", today)
    os.makedirs(cache_dir, exist_ok=True)

    saved = 0
    for symbol, ticks in source.items():
        if not ticks:
            continue
        out_path = os.path.join(cache_dir, f"{symbol}.json.gz")
        # Merge with existing cache (don't overwrite fetched historical data)
        existing = []
        if os.path.exists(out_path):
            try:
                with gzip.open(out_path, "rt") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        merged = existing + ticks
        with gzip.open(out_path, "wt") as f:
            json.dump(merged, f)
        saved += 1
        new_count = len(ticks)
        total_count = len(merged)
        print(f"  Tick cache: {symbol} → +{new_count:,} ticks (total {total_count:,})", flush=True)

    if saved:
        print(f"📦 Tick cache saved: {saved} symbols → tick_cache/{today}/", flush=True)


def _tick_flush_loop():
    """Background loop that flushes state.tick_buffer to tick_cache/ every
    SESSION_FLUSH_SEC. Always-on crash-safety (see
    cowork_reports/2026-04-15_greenlight_session_resume.md).

    Atomically swaps the buffer with a fresh dict so the live tick callback
    thread keeps writing into the fresh buffer while we flush the snapshot.
    Under CPython the GIL makes the `snap, state.tick_buffer = ..., {}`
    assignment atomic across threads (single bytecode store). Ticks that
    arrive during the flush land safely in the new buffer.
    """
    while True:
        time.sleep(SESSION_FLUSH_SEC)
        try:
            with _tick_buffer_lock:
                if not any(state.tick_buffer.values()):
                    continue
                snap, state.tick_buffer = state.tick_buffer, {}
            # Release lock before disk IO — callback thread can resume writing
            # into the fresh state.tick_buffer while we serialize the snapshot.
            save_tick_cache(source=snap)
        except Exception as e:
            print(f"⚠️  TICK FLUSH ERROR: {e}", flush=True)


def _open_position_to_trade_record(pos: dict) -> dict:
    """Map in-memory open_position dict → open_trades.json schema (19 fields).

    Schema fields that aren't first-class on open_position are derived here:
      - target_r / target_price: derived from SQ_TARGET_R + r (squeeze-only;
        for other setup_types we use 0 as a neutral placeholder since their
        exit paths don't use a target-R concept).
      - trail_mode: "pre_target" until pos["tp_hit"] goes True, then "post_target".
      - partial_filled_at / partial_filled_qty: stamped onto pos at the tp_hit
        transition in _squeeze_exit (see write points below). Default None/0.
      - bail_timer_start: identical to entry_time today (bail timer is a
        duration-from-entry check, not a separate countdown we ever restart).
      - exit_mode: env-derived. "signal" is the default today; see CLAUDE.md.
    """
    entry = float(pos["entry"])
    r = float(pos.get("r", 0.0))
    target_r = float(SQ_TARGET_R) if pos.get("setup_type") in ("squeeze", "mp_reentry", "continuation") else 0.0
    target_price = entry + target_r * r if target_r > 0 else 0.0
    trail_mode = "post_target" if pos.get("tp_hit") else "pre_target"
    entry_time = pos.get("entry_time")
    entry_iso = entry_time.isoformat() if hasattr(entry_time, "isoformat") else str(entry_time)
    return {
        "symbol": pos["symbol"],
        "setup_type": pos.get("setup_type", ""),
        "entry_price": entry,
        "entry_time": entry_iso,
        "qty": int(pos.get("qty", 0)),
        "r": r,
        "stop": float(pos.get("stop", 0.0)),
        "target_r": target_r,
        "target_price": target_price,
        "peak": float(pos.get("peak", entry)),
        "trail_mode": trail_mode,
        "partial_filled_at": pos.get("partial_filled_at"),
        "partial_filled_qty": int(pos.get("partial_filled_qty", 0)),
        "bail_timer_start": entry_iso,
        "exit_mode": os.getenv("WB_EXIT_MODE", "signal"),
        "order_id": pos.get("order_id", ""),
        "fill_confirmed": bool(pos.get("fill_confirmed", False)),
        "score": float(pos.get("score", 0.0)),
        "is_parabolic": bool(pos.get("is_parabolic", False)),
    }


def persist_open_trades():
    """Sync state.open_position to open_trades.json. Called on every state
    transition (fill confirmation, peak advance, trail-mode change, partial
    fill, bail arm) and on position close. Box positions are not persisted
    in v1 (see plan — deferred, MASTER_TODO follow-up).

    Only persists fully-confirmed trades per Cowork's write-on-fill rule:
    the moment fill_confirmed=True, manage_exit() is the protection layer,
    so that's the durable state to persist. Pre-fill positions would persist
    as "filled but unmanaged" from a resume perspective, which is worse than
    flattening as orphan.
    """
    try:
        pos = state.open_position
        if pos and pos.get("fill_confirmed"):
            ss.write_open_trades([_open_position_to_trade_record(pos)])
        else:
            ss.write_open_trades([])
    except Exception as e:
        print(f"⚠️  persist_open_trades error: {e}", flush=True)


def persist_risk():
    """Sync daily risk counters to risk.json. Cheap — ≤3KB file, no validation."""
    try:
        ss.write_risk(
            daily_pnl=state.daily_pnl,
            daily_trades=state.daily_trades,
            consecutive_losses=state.consecutive_losses,
            closed_trades=state.closed_trades,
        )
    except Exception as e:
        print(f"⚠️  persist_risk error: {e}", flush=True)


def persist_watchlist():
    """Sync state.active_symbols to watchlist.json with subscription timestamps.
    Called on every subscribe_symbol() success."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = {e["symbol"]: e for e in ss.read_watchlist()}
        entries = []
        for sym in sorted(state.active_symbols):
            if sym in existing:
                entries.append(existing[sym])
            else:
                entries.append({"symbol": sym, "subscribed_at": now_iso})
        ss.write_watchlist(entries)
    except Exception as e:
        print(f"⚠️  persist_watchlist error: {e}", flush=True)


def _risk_flush_loop():
    """Background loop persisting risk.json every 60s. Writes are cheap but
    this is a belt-and-suspenders in case a transition-point write is missed."""
    while True:
        time.sleep(60)
        try:
            persist_risk()
        except Exception as e:
            print(f"⚠️  RISK FLUSH ERROR: {e}", flush=True)


def start_tick_flush_thread():
    """Start the periodic tick-cache flush thread. Idempotent."""
    if not TICK_FLUSH_ENABLED:
        print("Tick flush thread disabled (WB_TICK_FLUSH_ENABLED=0)", flush=True)
        return
    t = threading.Thread(target=_tick_flush_loop, daemon=True, name="tick-flush")
    t.start()
    print(f"📦 Tick flush thread started (every {SESSION_FLUSH_SEC}s)", flush=True)


def start_risk_flush_thread():
    """Start the periodic risk.json flush thread. Safety net — transition
    writes in exit_trade should keep risk.json fresh, but a background
    flush every 60s protects against a missed write point."""
    t = threading.Thread(target=_risk_flush_loop, daemon=True, name="risk-flush")
    t.start()
    print("📊 Risk flush thread started (every 60s)", flush=True)


def on_ib_error(reqId, errorCode, errorString, contract):
    """Handle IBKR error events — especially market data and competing session errors."""
    # Market data errors that may require resubscription
    MKTDATA_ERRORS = {10197, 354, 2104, 2106, 2158}

    if errorCode in MKTDATA_ERRORS:
        sym = contract.symbol if contract else "?"
        print(f"⚠️ IBKR ERROR {errorCode}: {errorString} (symbol={sym})", flush=True)
        if errorCode == 10197:
            print(f"  >> Competing session detected! Re-subscribing all active symbols...", flush=True)
            for symbol in list(state.active_symbols):
                c = state.contracts.get(symbol)
                if c:
                    try:
                        state.ib.cancelMktData(c)
                        state.ib.sleep(1)
                        ticker = state.ib.reqMktData(c, '233', False, False)
                        state.tickers[symbol] = ticker
                    except Exception as e:
                        print(f"  Re-sub failed for {symbol}: {e}", flush=True)
            print(f"  >> Re-subscription complete for {len(state.active_symbols)} symbols", flush=True)
    elif errorCode not in {2104, 2106, 2158, 2119}:
        # Log non-informational errors
        sym = contract.symbol if contract else "?"
        print(f"IBKR ERROR {errorCode}: {errorString} (reqId={reqId}, symbol={sym})", flush=True)


def preflight_port_check():
    """Verify no port conflicts before connecting."""
    import subprocess
    ports = {4002: False, 7497: False}
    for port in ports:
        result = subprocess.run(["lsof", "-i", f":{port}"], capture_output=True, text=True)
        if result.stdout.strip():
            ports[port] = True
            print(f"  Port {port}: IN USE", flush=True)
        else:
            print(f"  Port {port}: free", flush=True)

    if ports[4002] and ports[7497]:
        print("🔴 CRITICAL: Both ports 4002 AND 7497 are occupied!", flush=True)
        print("  This can cause IBKR data routing confusion. Kill one.", flush=True)
        sys.exit(1)

    if not ports[4002]:
        print(f"  WARNING: Port 4002 not yet open (Gateway may still be starting)", flush=True)


def on_pending_tickers_backup(tickers):
    """Backup listener: alert if pendingTickersEvent fires but on_ticker_update is stale."""
    if not state.last_on_ticker_fire:
        return
    stale_seconds = (datetime.now(ET) - state.last_on_ticker_fire).total_seconds()
    if stale_seconds > 30:
        print(f"⚠️ STALE TICKERS: pendingTickersEvent fired but on_ticker_update "
              f"hasn't fired in {stale_seconds:.0f}s — possible callback issue!", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Box Strategy — Live Integration
# ══════════════════════════════════════════════════════════════════════

def run_box_scanner():
    """Run box scanner at checkpoint times. Applies Vol Sweet Spot filter."""
    if not BOX_ENABLED:
        return
    now = datetime.now(ET)

    # Skip Fridays
    if now.weekday() == 4 and BOX_SKIP_FRIDAY:
        return

    # Don't re-scan within 5 minutes
    if state.last_box_scan_time:
        if (now - state.last_box_scan_time).total_seconds() < 300:
            return

    # Only scan at designated checkpoints (within 2 min window)
    should_scan = False
    for checkpoint in BOX_SCAN_CHECKPOINTS:
        cp_dt = now.replace(hour=checkpoint.hour, minute=checkpoint.minute, second=0, microsecond=0)
        if abs((cp_dt - now).total_seconds()) < 120:
            should_scan = True
            break
    if not should_scan:
        return

    print(f"\n[BOX] Scanner running at {now.strftime('%H:%M')} ET...", flush=True)
    try:
        candidates = scan_box_candidates(state.ib)

        # Apply Vol Sweet Spot filters
        filtered = []
        for c in candidates:
            rp = c.get("range_pct", 0)
            total_tests = c.get("high_tests", 0) + c.get("low_tests", 0)
            price = c.get("price", 0)
            adr_util = c.get("adr_util_today", 999)

            if rp < BOX_FILTER_MIN_RANGE_PCT or rp > BOX_FILTER_MAX_RANGE_PCT:
                continue
            if total_tests < BOX_FILTER_MIN_TOTAL_TESTS:
                continue
            if price < BOX_FILTER_MIN_PRICE:
                continue
            if adr_util > BOX_FILTER_MAX_ADR_UTIL:
                continue
            filtered.append(c)

        state.box_candidates = sorted(filtered, key=lambda x: x.get("box_score", 0), reverse=True)
        state.last_box_scan_time = now

        print(f"  [BOX] {len(state.box_candidates)} candidates passed filter "
              f"(from {len(candidates)} raw)", flush=True)
        for c in state.box_candidates[:5]:
            print(f"    {c['symbol']}: score={c['box_score']:.1f}, range={c['range_pct']:.1f}%, "
                  f"tests={c['high_tests']}H/{c['low_tests']}L, price=${c['price']:.2f}", flush=True)
    except Exception as e:
        print(f"  [BOX] Scanner error: {e}", flush=True)
        traceback.print_exc()


def subscribe_box_symbol(symbol: str):
    """Subscribe to a box candidate for tick/bar data via IBKR."""
    if symbol in state.active_symbols:
        state.box_active_symbol = symbol
        return  # Already subscribed (maybe momentum is watching it)

    contract = Stock(symbol, "SMART", "USD")
    try:
        state.ib.qualifyContracts(contract)
        ticker = state.ib.reqMktData(contract, "233", False, False)
        state.contracts[symbol] = contract
        state.tickers[symbol] = ticker
        state.active_symbols.add(symbol)
        state.box_active_symbol = symbol
        state.tick_counts[symbol] = 0
        state.tick_buffer[symbol] = []
        print(f"  [BOX] Subscribed to {symbol} for box trading", flush=True)
        persist_watchlist()
    except Exception as e:
        print(f"  [BOX] Subscribe error {symbol}: {e}", flush=True)


def on_box_bar_close_1m(bar):
    """Process 1-minute bar for box strategy."""
    if not BOX_ENABLED or not state.box_engine:
        return
    if bar.symbol != state.box_active_symbol:
        return

    result = state.box_engine.on_bar(bar)

    if result is None:
        # Check if engine opened a trade internally
        if state.box_engine.active_trade and not state.box_position:
            _enter_box_trade()
    elif result:
        # Exit signal from engine
        if state.box_position:
            _exit_box_trade(result)


def _enter_box_trade():
    """Enter a box trade via Alpaca."""
    trade = state.box_engine.active_trade
    symbol = trade.symbol

    # Safety: no simultaneous positions (unless gated on)
    if not BOX_SIMULTANEOUS and state.open_position:
        print(f"  [BOX] Entry blocked — momentum position open ({state.open_position['symbol']})", flush=True)
        return
    if state.box_position:
        return
    if state.box_daily_pnl <= -BOX_MAX_LOSS_SESSION:
        print(f"  [BOX] Entry blocked — session loss cap hit (${state.box_daily_pnl:.2f})", flush=True)
        return

    entry_price = trade.entry_price
    shares = trade.shares
    notional = entry_price * shares

    print(f"\n[BOX] ENTRY: {symbol} {shares} shares @ ${entry_price:.2f} "
          f"(notional ${notional:,.0f})", flush=True)
    print(f"  Box: ${state.box_engine.box_bottom:.2f} - ${state.box_engine.box_top:.2f} "
          f"(range ${state.box_engine.box_range:.2f}, mid ${state.box_engine.box_mid:.2f})", flush=True)
    print(f"  Stop: ${state.box_engine.hard_stop_price:.2f}", flush=True)

    initial_slip = _entry_slippage_for(entry_price)
    limit_price = round(entry_price + initial_slip, 2)
    original_limit = limit_price
    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=shares,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=True,
        )
        result = state.alpaca.submit_order(order)
        order_id = str(result.id)

        state.box_position = {
            "symbol": symbol,
            "qty": shares,
            "entry": entry_price,
            "order_id": order_id,
            "fill_confirmed": False,
            "setup_type": "box",
        }
        print(f"  [BOX] Order submitted: {order_id} @ ${limit_price:.2f} "
              f"(slip=${initial_slip:.3f})", flush=True)

        import threading
        def verify_box_fill():
            _verify_fill_with_retry(
                symbol=symbol, qty=shares, r=None,
                initial_order_id=order_id, initial_limit=limit_price,
                original_limit=original_limit, position_attr="box_position",
                log_prefix="[BOX] ",
            )
        threading.Thread(target=verify_box_fill, daemon=True).start()
    except Exception as e:
        print(f"  [BOX] ORDER FAILED: {e}", flush=True)


def _exit_box_trade(reason: str):
    """Exit a box trade via Alpaca."""
    if not state.box_position:
        return

    symbol = state.box_position["symbol"]
    qty = state.box_position["qty"]
    entry = state.box_position["entry"]

    # Get exit price from engine or ticker
    exit_price = 0
    if state.box_engine and state.box_engine.trades:
        last_trade = state.box_engine.trades[-1]
        if last_trade.exit_price:
            exit_price = last_trade.exit_price
    if exit_price <= 0:
        ticker = state.tickers.get(symbol)
        if ticker and ticker.last and not math.isnan(ticker.last):
            exit_price = ticker.last

    pnl = (exit_price - entry) * qty if exit_price > 0 else 0

    print(f"\n[BOX] EXIT: {symbol} {qty} shares @ ${exit_price:.2f} "
          f"reason={reason} P&L=${pnl:+,.2f}", flush=True)

    try:
        order = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=round(exit_price - 0.02, 2),
        )
        state.alpaca.submit_order(order)
    except Exception as e:
        print(f"  [BOX] EXIT ORDER FAILED: {e} — attempting market order", flush=True)
        try:
            from alpaca.trading.requests import MarketOrderRequest
            order = MarketOrderRequest(
                symbol=symbol, qty=qty,
                side=OrderSide.SELL, time_in_force=TimeInForce.DAY,
            )
            state.alpaca.submit_order(order)
        except Exception as e2:
            print(f"  [BOX] MARKET ORDER ALSO FAILED: {e2}", flush=True)
            return

    state.box_daily_pnl += pnl
    state.box_daily_trades += 1
    state.box_closed_trades.append({
        "symbol": symbol, "setup_type": "box", "reason": reason,
        "pnl": pnl, "entry": entry, "exit": exit_price,
    })
    state.box_position = None


def main():
    global STARTING_EQUITY  # Must be at top of function before any reference

    # Session-resume CLI flags (see cowork_reports/2026-04-15_greenlight_session_resume.md)
    import argparse
    parser = argparse.ArgumentParser(description="Warrior Bot V3 Hybrid")
    parser.add_argument("--fresh", action="store_true",
                        help="Force cold start, overwriting today's session marker")
    parser.add_argument("--scrub", action="store_true",
                        help="Wipe today's session_state/ and tick_cache/, then cold start")
    args, _ = parser.parse_known_args()

    # Decide boot mode BEFORE any expensive work. Resume requires the feature
    # gate to be explicitly enabled — otherwise we always cold-start but still
    # write durable state so a later enabled run can resume.
    import session_state as ss
    boot_mode, boot_reason = ss.decide_boot_mode(fresh=args.fresh, scrub=args.scrub)
    if boot_mode == "resume" and not SESSION_RESUME_ENABLED:
        print(f"BOOT: would RESUME (reason={boot_reason}) but WB_SESSION_RESUME_ENABLED=0 — forcing COLD", flush=True)
        boot_mode = "cold"
        boot_reason = "resume_gate_off"
    if boot_mode == "resume":
        age = ss.marker_age_seconds()
        age_str = f"{age:.0f}s" if age is not None else "unknown"
        print(f"BOOT: RESUME mode (marker age={age_str}, reason={boot_reason})", flush=True)
    else:
        print(f"BOOT: COLD start (reason={boot_reason})", flush=True)

    print("=" * 60)
    print("  WARRIOR BOT V3 — Hybrid (IBKR data + Alpaca execution)")
    print(f"  Squeeze: {'ON' if SQ_ENABLED else 'OFF'}")
    print(f"  MP: {'ON' if MP_ENABLED else 'OFF'}")
    print(f"  MP V2 (Re-Entry): {'ON' if MP_V2_ENABLED else 'OFF'}")
    print(f"  Port: {IBKR_PORT}")
    print(f"  Risk: {RISK_PCT*100:.1f}% per trade")
    print(f"  Starting Equity: ${STARTING_EQUITY:,.0f}")
    if DAILY_LOSS_SCALE:
        effective_max_loss = max(MAX_DAILY_LOSS, STARTING_EQUITY * 0.02)
        print(f"  Max Daily Loss: ${effective_max_loss:,.0f} (2% of equity, scaling)")
    else:
        print(f"  Max Daily Loss: ${MAX_DAILY_LOSS:,.0f} (fixed)")
    print(f"  Windows: {TRADING_WINDOWS_STR}")
    print(f"  SQ Target R: {SQ_TARGET_R}")
    print("=" * 60)
    if not SQ_ENABLED:
        print("⚠️  WARNING: WB_SQUEEZE_ENABLED is OFF — bot will not trade squeezes!")
        print("  Set WB_SQUEEZE_ENABLED=1 in .env or environment to enable.")

    # Pre-flight: check for port conflicts
    print("\nPre-flight port check:")
    preflight_port_check()

    # Start main-thread watchdog (kills bot if frozen >120s)
    start_watchdog()

    # Connect to Alpaca (execution)
    apca_key = os.getenv("APCA_API_KEY_ID")
    apca_secret = os.getenv("APCA_API_SECRET_KEY")
    apca_paper = os.getenv("APCA_PAPER", "true").lower() == "true"
    if not apca_key or not apca_secret:
        print("FATAL: Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY", flush=True)
        sys.exit(1)
    state.alpaca = TradingClient(apca_key, apca_secret, paper=apca_paper)
    print(f"Alpaca connected ({'PAPER' if apca_paper else 'LIVE'})", flush=True)

    # Persist boot mode on state for downstream branching (seed_symbol →
    # tick-replay, order reconciliation, etc.). On cold boot we write/refresh
    # the marker so a subsequent crash can resume from this session.
    state.boot_mode = boot_mode
    if boot_mode == "cold":
        ss.write_marker()

    # Start periodic tick-cache flush (crash-safety for backtest data).
    # Always-on, independent of WB_SESSION_RESUME_ENABLED.
    start_tick_flush_thread()
    start_risk_flush_thread()

    # Startup position reconciliation. Resume mode rehydrates trade state
    # from open_trades.json + reconciles qty/orders against Alpaca; cold
    # mode adopts any unexpected Alpaca position with conservative defaults.
    if boot_mode == "resume":
        resume_reconcile()
    else:
        reconcile_positions_on_startup()

    # Fix 5: Graceful shutdown — check for orphan positions
    import signal as signal_mod
    def graceful_shutdown(signum, frame):
        print("\n🛑 SHUTDOWN SIGNAL RECEIVED", flush=True)
        try:
            positions = _alpaca_call(state.alpaca.get_all_positions)
            if positions:
                for pos in positions:
                    print(f"  ⚠️ POSITION OPEN AT SHUTDOWN: {pos.symbol} "
                          f"qty={pos.qty} P&L=${float(pos.unrealized_pl):+,.2f}", flush=True)
                print("  *** POSITIONS LEFT OPEN — WILL NEED MANUAL MANAGEMENT ***", flush=True)
            else:
                print("  All positions flat. Clean shutdown.", flush=True)
        except Exception as e:
            print(f"  Could not check positions at shutdown: {e}", flush=True)
        sys.exit(0)
    signal_mod.signal(signal_mod.SIGTERM, graceful_shutdown)
    signal_mod.signal(signal_mod.SIGINT, graceful_shutdown)

    # Connect to IBKR (data only)
    ib = connect()

    # Wire error handler (competing sessions, market data errors)
    ib.errorEvent += on_ib_error

    # Fetch actual account equity from Alpaca for position sizing
    actual_equity = get_account_equity()
    print(f"Account equity: ${actual_equity:,.0f}", flush=True)
    STARTING_EQUITY = actual_equity

    # ── EPL Framework ──
    if EPL_ENABLED:
        state.epl_watchlist = EPLWatchlist()
        state.epl_registry = StrategyRegistry()
        state.epl_arbitrator = PositionArbitrator(state.epl_registry, state.epl_watchlist)
        _epl_mp = EPLMPReentry()
        if EPL_MP_ENABLED:
            state.epl_registry.register(_epl_mp)
        print(f"EPL initialized: {state.epl_registry.strategy_count} strategies registered", flush=True)
    else:
        print("EPL disabled (WB_EPL_ENABLED=0)", flush=True)

    # Bar builders
    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
    if BOX_ENABLED:
        state.box_bar_builder_1m = TradeBarBuilder(on_bar_close=on_box_bar_close_1m, et_tz=ET, interval_seconds=60)

    # Wire ticker updates + backup stale-ticker monitor
    ib.pendingTickersEvent += on_ticker_update
    ib.pendingTickersEvent += on_pending_tickers_backup

    # Initial scan
    run_scanner()
    poll_watchlist()

    # Main event loop
    windows_str = ", ".join(f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in TRADING_WINDOWS)
    print(f"\nBot running. Windows: {windows_str} ET. Ctrl+C to stop.", flush=True)
    try:
        while True:
            now = datetime.now(ET)

            # Past all windows for the day → shut down
            if past_all_windows(now):
                print(f"\n🛑 All trading windows closed. Shutting down.", flush=True)
                break

            # Check if we're in a trading window or the dead zone
            momentum_active = in_trading_window(now)
            box_active = in_box_window(now)
            active = momentum_active or box_active

            if active:
                # Coming back from dead zone — reset for fresh evening session
                if state.in_dead_zone:
                    state.in_dead_zone = False
                    state.last_scan_time = None  # Force immediate rescan
                    # Reset everything for fresh evening session
                    # Cancel morning subscriptions (evening stocks will be different)
                    for sym in list(state.active_symbols):
                        c = state.contracts.get(sym)
                        if c:
                            try:
                                state.ib.cancelMktData(c)
                            except Exception:
                                pass
                    state.active_symbols.clear()
                    state.contracts.clear()
                    state.tickers.clear()
                    state.tick_counts.clear()
                    state.sq_detectors.clear()
                    state.mp_detectors.clear()
                    state.ct_detectors.clear()
                    # Reset bar builders so evening bars start fresh
                    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
                    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
                    print(f"\n🟢 Evening session started ({now.strftime('%H:%M')} ET). Full reset. Resuming trading.", flush=True)

                # Periodic rescan (momentum)
                if momentum_active:
                    run_scanner()
                    poll_watchlist()

                    # Check halts
                    check_halts()

                # Tick health audit (every 60s)
                audit_tick_health()

                # Fix 3: Periodic position sync with Alpaca (every 60s)
                periodic_position_sync()

                # ── Box strategy logic ──
                if box_active:
                    run_box_scanner()

                    # Init box engine on top candidate if we don't have one
                    if (state.box_candidates and not state.box_engine
                            and not state.box_position):
                        top = state.box_candidates[0]
                        subscribe_box_symbol(top["symbol"])
                        state.box_engine = BoxStrategyEngine(top, exit_variant="midbox")
                        print(f"  [BOX] Engine initialized: {top['symbol']} "
                              f"(score {top['box_score']:.1f})", flush=True)

                    # Force close box position at 3:45 PM
                    if now.time() >= BOX_WINDOW_END and state.box_position:
                        _exit_box_trade("time_stop")
                        state.box_engine = None
            else:
                # In dead zone between windows
                if not state.in_dead_zone:
                    state.in_dead_zone = True
                    # Close any open position before dead zone
                    if state.open_position:
                        sym = state.open_position["symbol"]
                        ticker = state.tickers.get(sym)
                        # Try last, then bid, then close as fallback price
                        price = None
                        if ticker:
                            for attr in ("last", "bid", "close"):
                                p = getattr(ticker, attr, None)
                                if p and not math.isnan(p) and p > 0:
                                    price = p
                                    break
                        if price:
                            print(f"🛑 Window closing — exiting {sym} at ${price:.2f}", flush=True)
                            exit_trade(sym, price, state.open_position["qty"], "window_close")
                        else:
                            print(f"⚠️ Window closing — NO PRICE for {sym}, position left open!", flush=True)
                    # Close any box position before dead zone
                    if BOX_ENABLED and state.box_position:
                        _exit_box_trade("window_close")
                        state.box_engine = None

                    # Save tick cache from morning session
                    save_tick_cache()
                    print(f"\n💤 Dead zone ({now.strftime('%H:%M')} ET). Sleeping until next window...", flush=True)

            # Issue 5: Pending order timeout check (cancel unfilled entries after 15s)
            if state.pending_order:
                elapsed = (now - state.pending_order['placed_time']).total_seconds()
                if elapsed > state.pending_order['timeout_seconds']:
                    try:
                        state.alpaca.cancel_order_by_id(state.pending_order['order_id'])
                    except Exception as e:
                        print(f"  ORDER CANCEL ERROR: {e}", flush=True)
                    if state.open_position and not state.open_position.get('fill_confirmed'):
                        state.open_position = None
                    state.pending_order = None
                    print("  ORDER TIMEOUT: Entry order cancelled after 10s — no fill", flush=True)

            # Issue 9: Connection watchdog — reconnect on disconnect
            if not state.ib.isConnected():
                print("CONNECTION LOST — attempting reconnect...", flush=True)
                for attempt in range(1, 6):
                    try:
                        state.ib.disconnect()
                        time.sleep(10)
                        state.ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
                        # Re-wire events
                        state.ib.pendingTickersEvent += on_ticker_update
                        state.ib.pendingTickersEvent += on_pending_tickers_backup
                        state.ib.errorEvent += on_ib_error
                        # Re-subscribe all active symbols with RTVolume
                        for sym in list(state.active_symbols):
                            c = state.contracts.get(sym)
                            if c:
                                ticker = state.ib.reqMktData(c, '233', False, False)
                                state.tickers[sym] = ticker
                        print(f"  Reconnected on attempt {attempt}", flush=True)
                        break
                    except Exception as e:
                        print(f"  Reconnect attempt {attempt}/5 failed: {e}", flush=True)
                        if attempt == 5:
                            print("  FATAL: Could not reconnect after 5 attempts", flush=True)

            # Heartbeat every ~1 minute
            if now.second < 2:
                pos_str = f"OPEN={state.open_position['symbol']} @ ${state.open_position['entry']:.2f}" if state.open_position else "flat"
                if BOX_ENABLED and state.box_position:
                    pos_str += f" | BOX={state.box_position['symbol']} @ ${state.box_position['entry']:.2f}"
                zone = "ACTIVE" if active else "SLEEP"
                if box_active and not momentum_active:
                    zone = "BOX"

                # Tick flow summary
                total_ticks = sum(state.tick_counts.values())
                tick_syms = []
                for sym in sorted(state.active_symbols):
                    tc = state.tick_counts.get(sym, 0)
                    sq = state.sq_detectors.get(sym)
                    sq_st = sq._state if sq else "?"
                    armed_str = f"${sq.armed.trigger_high:.2f}" if (sq and sq.armed) else ""
                    tick_syms.append(f"{sym}:{tc}t/{sq_st}" + (f"/arm{armed_str}" if armed_str else ""))

                # Connection health
                connected = state.ib.isConnected() if state.ib else False

                print(f"[{now.strftime('%H:%M:%S')} ET] {zone} | "
                      f"{pos_str} | daily=${state.daily_pnl:+,.0f} ({state.daily_trades}t) | "
                      f"conn={'OK' if connected else 'DOWN'} | "
                      f"ticks={total_ticks} | "
                      f"{' '.join(tick_syms) if tick_syms else 'no symbols'}",
                      flush=True)

            # Heartbeat for watchdog — proves main thread is alive
            update_heartbeat()

            # Let ib_insync process events (sleep longer during dead zone)
            ib.sleep(30 if state.in_dead_zone else 1)

    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
    except Exception:
        print("🔥 Bot crashed:")
        traceback.print_exc()
    finally:
        # Close any open momentum position
        if state.open_position:
            sym = state.open_position["symbol"]
            ticker = state.tickers.get(sym)
            if ticker and ticker.last:
                exit_trade(sym, ticker.last, state.open_position["qty"], "shutdown")

        # Close any open box position
        if BOX_ENABLED and state.box_position:
            _exit_box_trade("shutdown")

        # Save tick cache for backtesting (before disconnect)
        save_tick_cache()

        # Disconnect
        ib.disconnect()

        # Print summary
        print(f"\n{'='*60}")
        print(f"  SESSION SUMMARY")
        print(f"  Momentum Trades: {state.daily_trades}")
        print(f"  Momentum P&L: ${state.daily_pnl:+,.0f}")
        for t in state.closed_trades:
            print(f"    {t['symbol']} {t['setup_type']} {t['reason']}: ${t['pnl']:+,.0f}")
        if BOX_ENABLED:
            print(f"  Box Trades: {state.box_daily_trades}")
            print(f"  Box P&L: ${state.box_daily_pnl:+,.2f}")
            for t in state.box_closed_trades:
                print(f"    [BOX] {t['symbol']} {t['reason']}: ${t['pnl']:+,.2f}")
            print(f"  COMBINED P&L: ${state.daily_pnl + state.box_daily_pnl:+,.2f}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
