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
from ib_insync import IB, Stock, LimitOrder, MarketOrder, util

from squeeze_detector import SqueezeDetector
from micro_pullback import MicroPullbackDetector
from ibkr_scanner import scan_premarket_live, rank_score
from bars import TradeBarBuilder, Bar

ET = pytz.timezone("US/Eastern")

# ── Strategy gates ───────────────────────────────────────────────────
SQ_ENABLED = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"
MP_ENABLED = os.getenv("WB_MP_ENABLED", "0") == "1"

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

        # Tick recording for backtest cache
        self.tick_buffer: dict[str, list] = {}  # symbol -> [{p, s, t}, ...]


state = BotState()


# ══════════════════════════════════════════════════════════════════════
# Initialization
# ══════════════════════════════════════════════════════════════════════

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
    """Create squeeze + MP detectors for a symbol."""
    if SQ_ENABLED and symbol not in state.sq_detectors:
        sq = SqueezeDetector()
        sq.symbol = symbol
        state.sq_detectors[symbol] = sq

    if MP_ENABLED and symbol not in state.mp_detectors:
        mp = MicroPullbackDetector()
        mp.symbol = symbol
        state.mp_detectors[symbol] = mp


def subscribe_symbol(symbol: str):
    """Subscribe to market data for a symbol."""
    if symbol in state.active_symbols:
        return

    contract = Stock(symbol, 'SMART', 'USD')
    state.ib.qualifyContracts(contract)
    state.contracts[symbol] = contract

    # Subscribe to market data (~250ms updates)
    ticker = state.ib.reqMktData(contract, '', False, False)
    state.tickers[symbol] = ticker

    # Initialize detectors
    init_detectors(symbol)

    # Seed with historical bars
    seed_symbol(symbol)

    state.active_symbols.add(symbol)
    print(f"✅ Subscribed: {symbol}", flush=True)


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
            if MP_ENABLED and symbol in state.mp_detectors:
                state.mp_detectors[symbol].seed_bar_close(o, h, l, c, v)

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

    # Diagnostic: log bar data every 5 minutes per symbol
    hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else None
    minute = datetime.now(ET).minute
    if minute % 5 == 0:
        sq_state = state.sq_detectors[symbol]._state if symbol in state.sq_detectors else "N/A"
        armed_lvl = f"${state.sq_detectors[symbol].armed.trigger_high:.2f}" if (symbol in state.sq_detectors and state.sq_detectors[symbol].armed) else "none"
        print(f"[{now_str} ET] {symbol} BAR | O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume:,} "
              f"VWAP={vwap:.2f if vwap else 0:.2f} HOD={hod:.2f if hod else 0:.2f} PM_H={pm_high:.2f if pm_high else 0:.2f} "
              f"sq={sq_state} armed={armed_lvl}", flush=True)

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

    # MP detection
    if MP_ENABLED and symbol in state.mp_detectors:
        mp = state.mp_detectors[symbol]
        mp_msg = mp.on_bar_close_1m(bar, vwap=vwap)
        if mp_msg and "ARMED" in mp_msg:
            print(f"[{now_str} ET] {symbol} MP | {mp_msg}", flush=True)


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

    # MP trigger
    if MP_ENABLED and symbol in state.mp_detectors:
        mp = state.mp_detectors[symbol]
        armed_before = mp.armed
        mp_msg = mp.on_trade_price(price, is_premarket=is_premarket)
        if mp_msg and "ENTRY SIGNAL" in mp_msg and armed_before:
            print(f"[{now_str} ET] {symbol} MP | {mp_msg}", flush=True)
            enter_trade(symbol, armed_before, "micro_pullback")
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
    current_equity = STARTING_EQUITY + state.daily_pnl  # Intraday equity
    # TODO: fetch actual account equity from IBKR for multi-day compounding
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
    }


def manage_exit(symbol: str, price: float):
    """Manage exit for open position."""
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
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

    if setup_type == "squeeze":
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
    # Limit slightly below current price to fill fast (marketable limit)
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
    for ticker in tickers:
        _process_ticker(ticker)


def _process_ticker(ticker):
    """Process a single ticker update."""
    contract = ticker.contract
    if not contract:
        return
    symbol = contract.symbol
    price = ticker.last

    if price is None or price <= 0 or math.isnan(price):
        return

    # Get trade size from ticker (lastSize = size of most recent trade print)
    size = int(ticker.lastSize) if ticker.lastSize and not math.isnan(ticker.lastSize) else 0

    ts = datetime.now(ET)

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


def main():
    print("=" * 60)
    print("  WARRIOR BOT V2 — IBKR Edition")
    print(f"  Squeeze: {'ON' if SQ_ENABLED else 'OFF'}")
    print(f"  MP: {'ON' if MP_ENABLED else 'OFF'}")
    print(f"  Port: {IBKR_PORT}")
    print("=" * 60)

    # Connect
    ib = connect()

    # Bar builders
    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)

    # Wire ticker updates
    ib.pendingTickersEvent += on_ticker_update

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
                    # Reset bar builders so evening bars start fresh
                    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
                    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
                    print(f"\n🟢 Evening session started ({now.strftime('%H:%M')} ET). Detectors reset. Resuming trading.", flush=True)

                # Periodic rescan
                run_scanner()

                # Check halts
                check_halts()
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

            # Heartbeat every 30 seconds
            if now.second < 2:
                pos_str = f"open={state.open_position['symbol']}" if state.open_position else "flat"
                zone = "ACTIVE" if active else "SLEEP"
                print(f"[{now.strftime('%H:%M:%S')} ET] {zone} | "
                      f"watch={len(state.active_symbols)} {pos_str} "
                      f"daily=${state.daily_pnl:+,.0f} trades={state.daily_trades}",
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
