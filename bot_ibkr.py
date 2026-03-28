"""
bot_ibkr.py — Warrior Bot V2 using Interactive Brokers via ib_insync.

Simplified flow:
1. Connect to IB Gateway/TWS
2. Run pre-market scanner (ibkr_scanner.scan_premarket_live)
3. Subscribe to top candidates (reqMktData)
4. Build 1-min + 10-sec bars from tick updates
5. Feed bars to squeeze_detector / micro_pullback
6. On signal: place order via IBKR
7. Manage exits via trade_manager_ibkr
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
import traceback
from datetime import datetime, timedelta, timezone, time as time_cls
from collections import deque

import pytz
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder, MarketOrder, util

# Load .env if present (same as simulate.py — ensures env vars are set)
load_dotenv()

from squeeze_detector import SqueezeDetector
from micro_pullback import MicroPullbackDetector
from continuation_detector import ContinuationDetector
from ibkr_scanner import scan_premarket_live, rank_score
from bars import TradeBarBuilder, Bar

ET = pytz.timezone("US/Eastern")

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
MIN_R = float(os.getenv("WB_MIN_R", "0.06"))
MAX_DAILY_LOSS = float(os.getenv("WB_MAX_DAILY_LOSS", "3000"))
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
    return t >= last_end


# ══════════════════════════════════════════════════════════════════════
# State
# ══════════════════════════════════════════════════════════════════════

class BotState:
    """Holds all mutable bot state."""
    def __init__(self):
        self.ib: IB = None
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

        # Tick health monitoring
        self.tick_counts: dict[str, int] = {}  # symbol -> ticks since last audit
        self.last_tick_time: dict[str, datetime] = {}  # symbol -> last tick timestamp
        self.last_tick_price: dict[str, float] = {}  # symbol -> last tick price
        self.last_tick_audit: datetime = None
        self.sub_retry_counts: dict[str, int] = {}  # symbol -> resubscription attempts
        self.last_on_ticker_fire: datetime = None  # track when on_ticker_update last fired

        # Tick recording for backtest cache
        self.tick_buffer: dict[str, list] = {}  # symbol -> [{p, s, t}, ...]


state = BotState()


# ══════════════════════════════════════════════════════════════════════
# Initialization
# ══════════════════════════════════════════════════════════════════════

def get_account_equity() -> float:
    """Get current account equity from IBKR (NetLiquidation)."""
    try:
        account_values = state.ib.accountValues()
        for av in account_values:
            if av.tag == 'NetLiquidation' and av.currency == 'USD':
                return float(av.value)
    except Exception as e:
        print(f"  Failed to fetch account equity: {e}", flush=True)
    return STARTING_EQUITY  # Fallback


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

    # Seed with historical bars
    seed_symbol(symbol)

    state.active_symbols.add(symbol)
    state.tick_counts[symbol] = 0
    state.sub_retry_counts[symbol] = 0
    print(f"✅ Subscribed: {symbol}", flush=True)


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
    """Seed detectors with historical bars from today."""
    contract = state.contracts.get(symbol)
    if not contract:
        return

    try:
        bars = state.ib.reqHistoricalData(
            contract,
            endDateTime='',
            durationStr='1 D',
            barSizeSetting='1 min',
            whatToShow='TRADES',
            useRTH=False,
            formatDate=1,
        )
        state.ib.sleep(0.5)

        if not bars:
            print(f"⚠️ No seed bars for {symbol}", flush=True)
            return

        for b in bars:
            o, h, l, c, v = b.open, b.high, b.low, b.close, b.volume
            if SQ_ENABLED and symbol in state.sq_detectors:
                state.sq_detectors[symbol].seed_bar_close(o, h, l, c, v)
            if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
                state.mp_detectors[symbol].seed_bar_close(o, h, l, c, v)
            if CT_ENABLED and symbol in state.ct_detectors:
                state.ct_detectors[symbol].seed_bar_close(o, h, l, c, v)

        ema = state.sq_detectors[symbol].ema if SQ_ENABLED and symbol in state.sq_detectors else None
        print(f"🔥 Seeded {symbol}: {len(bars)} bars, EMA={ema:.4f}" if ema else
              f"🔥 Seeded {symbol}: {len(bars)} bars", flush=True)

    except Exception as e:
        print(f"⚠️ Seed failed for {symbol}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════════════════════════════════

def run_scanner():
    """Run the IBKR scanner and subscribe to top candidates."""
    now = datetime.now(ET)

    # Only scan during active trading windows
    if not in_trading_window(now):
        return

    # Don't scan more than every 5 minutes
    if state.last_scan_time and (now - state.last_scan_time).total_seconds() < 300:
        return

    print(f"\n🔄 Running scanner at {now.strftime('%H:%M:%S')} ET...", flush=True)
    state.candidates = scan_premarket_live(state.ib)
    state.last_scan_time = now

    # Subscribe to top 5 (or all if fewer)
    for c in state.candidates[:5]:
        subscribe_symbol(c["symbol"])

    print(f"📊 Scanner: {len(state.candidates)} candidates, "
          f"{len(state.active_symbols)} subscribed", flush=True)


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
            avg_vol = sq._avg_vol if (sq and hasattr(sq, '_avg_vol') and sq._avg_vol) else 0
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

    # Continuation detection (post-squeeze — only when SQ is fully idle)
    _ct_sq_idle = not (SQ_ENABLED and symbol in state.sq_detectors and
                       (state.sq_detectors[symbol]._state != "IDLE" or state.sq_detectors[symbol]._in_trade))
    if CT_ENABLED and _ct_sq_idle and symbol in state.ct_detectors:
        ct = state.ct_detectors[symbol]
        # Check for pending activation (deferred from squeeze close)
        _ct_act = ct.check_pending_activation()
        if _ct_act:
            print(f"[{now_str} ET] {symbol} CT | {_ct_act}", flush=True)
        ct_msg = ct.on_bar_close_1m(bar, vwap=vwap)
        if ct_msg:
            if "CT_ARMED" in ct_msg or "CT_REJECT" in ct_msg or "CT_RESET" in ct_msg:
                print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)
            elif "CT_WATCHING" in ct_msg or "CT_PULLBACK" in ct_msg:
                print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)


def on_bar_close_10s(bar):
    """10-second bar close: exit detection (for MP trades only)."""
    # Squeeze trades use _squeeze_manage_exits on every tick, not 10s patterns
    pass


def check_triggers(symbol: str, price: float):
    """Check if any armed detector triggers on this price."""
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    is_premarket = datetime.now(ET).hour < 9 or (datetime.now(ET).hour == 9 and datetime.now(ET).minute < 30)

    # Already in a position — no new entries
    if state.open_position is not None:
        return

    # Daily risk check
    if state.daily_pnl <= -MAX_DAILY_LOSS:
        return
    if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return

    # Squeeze trigger (priority)
    if SQ_ENABLED and symbol in state.sq_detectors:
        sq = state.sq_detectors[symbol]
        armed_before = sq.armed
        sq_msg = sq.on_trade_price(price, is_premarket=is_premarket)
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

    # Size calculation
    qty = int(math.floor(risk_dollars / r))
    qty_notional = int(math.floor(MAX_NOTIONAL / max(entry, 0.01)))
    qty = min(qty, qty_notional, MAX_SHARES)

    notional = qty * entry
    print(f"  Sizing: equity=${current_equity:,.0f} risk=${risk_dollars:,.0f} "
          f"qty={qty} notional=${notional:,.0f}", flush=True)

    if size_mult < 1.0:
        qty = max(1, int(math.floor(qty * size_mult)))

    if qty <= 0:
        return

    # Place limit order slightly above trigger
    limit_price = round(entry + 0.02, 2)
    contract = state.contracts[symbol]
    order = LimitOrder('BUY', qty, limit_price)
    order.tif = 'GTC'
    order.outsideRth = True  # Allow fill in extended hours

    print(f"🟩 ENTRY: {symbol} qty={qty} limit=${limit_price:.2f} "
          f"stop=${stop:.4f} R=${r:.4f} score={score:.1f} "
          f"type={setup_type}", flush=True)

    trade = state.ib.placeOrder(contract, order)

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
        "order_id": trade.order.orderId,
        "is_parabolic": "[PARABOLIC]" in (armed.score_detail or ""),
        "fill_confirmed": False,
    }

    # Store pending order for timeout check
    state.pending_order = {
        "trade": trade,
        "placed_time": datetime.now(ET),
        "timeout_seconds": 10,
    }

    # Register fill callback to update position with actual fill price
    def on_entry_fill(trade_obj, fill):
        if state.open_position and state.open_position.get("order_id") == trade_obj.order.orderId:
            actual_price = fill.execution.price
            actual_qty = int(fill.execution.shares)
            state.open_position["entry"] = actual_price
            state.open_position["qty"] = actual_qty
            state.open_position["peak"] = max(state.open_position["peak"], actual_price)
            state.open_position["stop"] = actual_price - r
            state.open_position["fill_confirmed"] = True
            state.pending_order = None
            print(f"  FILL: {symbol} @ ${actual_price:.4f} qty={actual_qty}", flush=True)

    trade.fillEvent += on_entry_fill


def manage_exit(symbol: str, price: float):
    """Manage exit for open position."""
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return

    # Don't manage exits until entry fill is confirmed
    if not pos.get('fill_confirmed', False):
        return

    # Update peak
    if price > pos["peak"]:
        pos["peak"] = price

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

    if setup_type in ("squeeze", "mp_reentry", "continuation"):
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
            qty_core = max(1, int(qty * SQ_CORE_PCT / 100))
            qty_runner = qty - qty_core
            if qty_runner > 0:
                pos["runner_stop"] = max(stop, entry + 0.01)
                exit_trade(symbol, price, qty_core, "sq_target_hit")
                pos["qty"] = qty_runner  # Set AFTER exit_trade so remaining calc is correct
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
    """Place exit order and record trade. Uses aggressive limit order (required for extended hours)."""
    contract = state.contracts[symbol]
    # For urgent exits (stop hit, dollar loss cap, max loss), use very aggressive limit
    urgent_reasons = ('sq_stop_hit', 'sq_dollar_loss_cap', 'sq_max_loss_hit', 'stop_hit')
    if reason in urgent_reasons:
        limit_price = round(price * 0.97, 2)  # 3% below current price
    else:
        limit_price = round(price - 0.03, 2)
    order = LimitOrder('SELL', qty, limit_price)
    order.tif = 'GTC'
    order.outsideRth = True  # Allow fill in extended hours
    state.ib.placeOrder(contract, order)

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
        state.ct_detectors[symbol].notify_squeeze_closed(
            symbol, pnl,
            entry=pos["entry"], exit_price=price,
            hod=hod or 0, avg_squeeze_vol=avg_vol,
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

    # Record tick for backtest cache (exact same data the bot sees)
    if symbol not in state.tick_buffer:
        state.tick_buffer[symbol] = []
    state.tick_buffer[symbol].append({
        "p": price,
        "s": size,
        "t": ts.astimezone(timezone.utc).isoformat(),
    })

    # Feed to bar builders (price + volume)
    if state.bar_builder_1m:
        state.bar_builder_1m.on_trade(symbol, price, size, ts)
    if state.bar_builder_10s:
        state.bar_builder_10s.on_trade(symbol, price, size, ts)

    # Check triggers
    check_triggers(symbol, price)

    # Manage exits
    if state.open_position and state.open_position["symbol"] == symbol:
        manage_exit(symbol, price)


def save_tick_cache():
    """Save recorded ticks to tick_cache/ for future backtesting.
    Uses the exact same format simulate.py --ticks expects."""
    today = datetime.now(ET).strftime("%Y-%m-%d")
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_cache", today)
    os.makedirs(cache_dir, exist_ok=True)

    saved = 0
    for symbol, ticks in state.tick_buffer.items():
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


def main():
    global STARTING_EQUITY  # Must be at top of function before any reference

    print("=" * 60)
    print("  WARRIOR BOT V2 — IBKR Edition")
    print(f"  Squeeze: {'ON' if SQ_ENABLED else 'OFF'}")
    print(f"  MP: {'ON' if MP_ENABLED else 'OFF'}")
    print(f"  MP V2 (Re-Entry): {'ON' if MP_V2_ENABLED else 'OFF'}")
    print(f"  Port: {IBKR_PORT}")
    print(f"  Risk: {RISK_PCT*100:.1f}% per trade")
    print(f"  Starting Equity: ${STARTING_EQUITY:,.0f}")
    print(f"  Max Daily Loss: ${MAX_DAILY_LOSS:,.0f}")
    print(f"  Windows: {TRADING_WINDOWS_STR}")
    print(f"  SQ Target R: {SQ_TARGET_R}")
    print("=" * 60)
    if not SQ_ENABLED:
        print("⚠️  WARNING: WB_SQUEEZE_ENABLED is OFF — bot will not trade squeezes!")
        print("  Set WB_SQUEEZE_ENABLED=1 in .env or environment to enable.")

    # Pre-flight: check for port conflicts
    print("\nPre-flight port check:")
    preflight_port_check()

    # Connect
    ib = connect()

    # Wire error handler (competing sessions, market data errors)
    ib.errorEvent += on_ib_error

    # Fetch actual account equity for position sizing (multi-day compounding)
    actual_equity = get_account_equity()
    print(f"Account equity: ${actual_equity:,.0f}", flush=True)
    STARTING_EQUITY = actual_equity

    # Bar builders
    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)

    # Wire ticker updates + backup stale-ticker monitor
    ib.pendingTickersEvent += on_ticker_update
    ib.pendingTickersEvent += on_pending_tickers_backup

    # Initial scan
    run_scanner()

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
            active = in_trading_window(now)

            if active:
                # Coming back from dead zone — reset for fresh evening session
                if state.in_dead_zone:
                    state.in_dead_zone = False
                    state.last_scan_time = None  # Force immediate rescan
                    # Reset detectors — morning PM highs and EMAs are stale for evening
                    state.sq_detectors.clear()
                    state.mp_detectors.clear()
                    state.ct_detectors.clear()
                    # Reset bar builders so evening bars start fresh
                    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
                    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
                    print(f"\n🟢 Evening session started ({now.strftime('%H:%M')} ET). Detectors reset. Resuming trading.", flush=True)

                # Periodic rescan
                run_scanner()

                # Check halts
                check_halts()

                # Tick health audit (every 60s)
                audit_tick_health()
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
                    # Save tick cache from morning session
                    save_tick_cache()
                    print(f"\n💤 Dead zone ({now.strftime('%H:%M')} ET). Sleeping until next window...", flush=True)

            # Issue 5: Pending order timeout check (cancel unfilled entries after 10s)
            if state.pending_order:
                elapsed = (now - state.pending_order['placed_time']).total_seconds()
                if elapsed > state.pending_order['timeout_seconds']:
                    try:
                        state.ib.cancelOrder(state.pending_order['trade'].order)
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
                zone = "ACTIVE" if active else "SLEEP"

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

            # Let ib_insync process events (sleep longer during dead zone)
            ib.sleep(30 if state.in_dead_zone else 1)

    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
    except Exception:
        print("🔥 Bot crashed:")
        traceback.print_exc()
    finally:
        # Close any open position
        if state.open_position:
            sym = state.open_position["symbol"]
            ticker = state.tickers.get(sym)
            if ticker and ticker.last:
                exit_trade(sym, ticker.last, state.open_position["qty"], "shutdown")

        # Save tick cache for backtesting (before disconnect)
        save_tick_cache()

        # Disconnect
        ib.disconnect()

        # Print summary
        print(f"\n{'='*60}")
        print(f"  SESSION SUMMARY")
        print(f"  Trades: {state.daily_trades}")
        print(f"  Daily P&L: ${state.daily_pnl:+,.0f}")
        for t in state.closed_trades:
            print(f"    {t['symbol']} {t['setup_type']} {t['reason']}: ${t['pnl']:+,.0f}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
