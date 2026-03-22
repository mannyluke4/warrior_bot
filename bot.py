# bot.py

import os
import time
import threading
import traceback
import pytz
from dotenv import load_dotenv
from alpaca.data.historical import StockHistoricalDataClient
from data_feed import DataFeed, create_feed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from datetime import datetime, timedelta, timezone

from logger import log_event
from bars import TradeBarBuilder
from micro_pullback import MicroPullbackDetector
from trade_manager import PaperTradeManager
from stock_filter import StockFilter
from market_scanner import MarketScanner

load_dotenv()

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)

WATCHLIST_FILE = "watchlist.txt"
ET = pytz.timezone("US/Eastern")
POLL_SECONDS = 0.5

trade_manager: PaperTradeManager | None = None
bar_builder: TradeBarBuilder | None = None
bar_builder_1m: TradeBarBuilder | None = None
bar_builder_5m: TradeBarBuilder | None = None
_stock_info_cache: dict = {}  # StockInfo cache for gap_pct injection into detectors
_session_filtered_out: set = set()  # symbols that failed session-start filter; never trade these

if not API_KEY or not API_SECRET:
    raise RuntimeError("Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY in .env")

# -----------------------------
# Strategy gates
# -----------------------------
MP_ENABLED = os.getenv("WB_MP_ENABLED", "0") == "1"  # OFF: 0% win rate Jan 2025, -$3,947

# Console-noise controls
# -----------------------------
# Keep these off for a trade-focused tape.
PRINT_PATTERNS = os.getenv("WB_PRINT_PATTERNS", "0") == "1"
PRINT_BAR_SIGNALS = os.getenv("WB_PRINT_BAR_SIGNALS", "0") == "1"  # impulse/pullback/reset spam
PRINT_ARMED_ONLY = os.getenv("WB_PRINT_ARMED_ONLY", "1") == "1"    # recommended default

# -----------------------------
# Stale price warning controls
# -----------------------------
STALE_PRICE_SEC = float(os.getenv("WB_STALE_PRICE_SEC", "5"))          # warn if no updates for this long
STALE_WARN_COOLDOWN_SEC = float(os.getenv("WB_STALE_WARN_COOLDOWN_SEC", "20"))  # per-symbol throttle

# -----------------------------
# Watchlist
# -----------------------------
def load_watchlist():
    """
    Load watchlist from file (manual mode).
    Reads plain SYMBOL lines (one per line). Returns set of symbols.
    """
    try:
        with open(WATCHLIST_FILE, "r") as f:
            raw = [line.strip().upper() for line in f
                   if line.strip() and not line.strip().startswith("#")]
        result = set()
        for entry in raw:
            # Strip any legacy ":PROFILE" suffix
            sym = entry.split(":")[0].strip()
            if sym.isalpha() and 1 <= len(sym) <= 5:
                result.add(sym)
        return result
    except FileNotFoundError:
        return set()

def get_raw_watchlist():
    """
    Get raw watchlist - either from file (manual) or market scanner (dynamic).
    Returns set of symbols BEFORE filtering.
    """
    enable_dynamic_scanner = os.getenv("WB_ENABLE_DYNAMIC_SCANNER", "0") == "1"

    if enable_dynamic_scanner:
        print("\n🤖 DYNAMIC MARKET SCANNER ENABLED", flush=True)
        print("   Scanning market for active symbols...", flush=True)

        try:
            scanner = MarketScanner(API_KEY, API_SECRET)
            symbols = scanner.scan_market()

            if not symbols:
                print("⚠️ Dynamic scanner returned no symbols. Falling back to manual watchlist.", flush=True)
                return load_watchlist()

            return symbols

        except Exception as e:
            print(f"⚠️ Dynamic scanner failed: {e}", flush=True)
            print("   Falling back to manual watchlist.", flush=True)
            log_event("exception", None, where="get_raw_watchlist_scanner", error=str(e))
            return load_watchlist()

    else:
        # Manual mode: load from watchlist.txt
        return load_watchlist()

def filter_watchlist(symbols):
    """
    Filter watchlist based on Ross Cameron criteria.
    Returns filtered set of symbols.
    """
    if not symbols:
        return set()

    # Check if filtering is enabled
    enable_filtering = os.getenv("WB_ENABLE_STOCK_FILTERING", "1") == "1"
    if not enable_filtering:
        print("📋 Stock filtering disabled, using full watchlist", flush=True)
        return symbols

    try:
        stock_filter = StockFilter(API_KEY, API_SECRET)
        filtered_stocks = stock_filter.filter_watchlist(symbols)

        if not filtered_stocks:
            print("⚠️ No stocks passed filters. Returning empty set (will retry on next rescan).", flush=True)
            return set()

        # Sort by rank (best first)
        ranked = sorted(
            filtered_stocks.items(),
            key=lambda x: stock_filter.rank_stock(x[1]),
            reverse=True
        )

        print(f"\n🎯 Top Candidates (by rank):", flush=True)
        for i, (symbol, info) in enumerate(ranked[:10]):
            rank = stock_filter.rank_stock(info)
            float_str = f"float={info.float_shares:.1f}M" if info.float_shares is not None else "float=N/A"
            print(
                f"   #{i+1} {symbol}: ${info.price:.2f} gap={info.gap_pct:+.1f}% "
                f"vol={info.rel_volume:.1f}x {float_str} rank={rank:.3f}",
                flush=True
            )

        # Attach rank order to the dict so callers can plumb it to trade_manager
        filtered_stocks["__rank_order__"] = [sym for sym, _ in ranked]
        return filtered_stocks  # dict {symbol: StockInfo} — preserves fundamentals

    except Exception as e:
        print(f"⚠️ Stock filtering failed: {e}", flush=True)
        log_event("exception", None, where="filter_watchlist", error=str(e))
        return symbols  # Fallback to unfiltered

def seed_symbol_from_history(symbol: str, minutes: int = 60):
    """
    Pull recent bars from Alpaca REST and seed indicator/pattern memory.
    Does NOT allow arming/trading from seed.

    Always seeds back to at least 4:00 AM ET today so PM_HIGH is correctly
    populated even when the bot is restarted mid-session after market open.
    """
    try:
        det = ensure_detector(symbol)

        end = datetime.now(timezone.utc)

        # Always seed from 4:00 AM ET today to capture full premarket data.
        # This ensures PM_HIGH is populated even if the bot restarts at 11 AM or later.
        now_et = end.astimezone(ET)
        premarket_start_et = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        premarket_start_utc = premarket_start_et.astimezone(timezone.utc)

        # Use whichever start is earlier: 4 AM ET today or the rolling lookback.
        # During market hours, 4 AM ET is always earlier, so we always get premarket bars.
        rolling_start = end - timedelta(minutes=minutes)
        start = min(premarket_start_utc, rolling_start)

        req = StockBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Minute,   # seed from 1-min bars
            start=start,
            end=end,
            feed="sip",                   # safe default; if it errors, remove this line
        )
        bars = hist_client.get_stock_bars(req).data.get(symbol, [])

        if not bars:
            print(f"⚠️ Seed: no bars returned for {symbol}", flush=True)
            return

        for b in bars:
            o = float(b.open)
            h = float(b.high)
            l = float(b.low)
            c = float(b.close)
            v = float(b.volume)

            det.seed_bar_close(o, h, l, c, v)

            # Seed VWAP/HOD/PM_HIGH in bar_builder without triggering on_bar_close
            ts = getattr(b, "timestamp", None) or getattr(b, "t", None) or end
            if bar_builder and hasattr(bar_builder, "seed_bar_close"):
                bar_builder.seed_bar_close(symbol, o, h, l, c, v, ts)
            if bar_builder_1m and hasattr(bar_builder_1m, "seed_bar_close"):
                bar_builder_1m.seed_bar_close(symbol, o, h, l, c, v, ts)
            if bar_builder_5m and hasattr(bar_builder_5m, "seed_bar_close"):
                bar_builder_5m.seed_bar_close(symbol, o, h, l, c, v, ts)

        pm_high = bar_builder.get_premarket_high(symbol) if bar_builder else None
        pm_str = f"{pm_high:.4f}" if pm_high and pm_high > 0 else "N/A"
        print(f"🔥 Seeded {symbol}: {len(bars)} bars (since 4AM ET) EMA9={det.ema:.4f} PM_HIGH={pm_str}", flush=True)

    except Exception as e:
        print(f"⚠️ Seed failed for {symbol}: {e}", flush=True)

# -----------------------------
# Global state
# -----------------------------
pattern_hits = 0
armed_hits = 0
entry_signal_hits = 0

# last update times (UTC epoch seconds)
last_trade_ts: dict[str, float] = {}
last_quote_ts: dict[str, float] = {}
last_stale_warn_ts: dict[str, float] = {}

# Track which symbols have already printed their premarket summary (per trading day)
premarket_reported: set[str] = set()
_premarket_reported_date: str = ""  # ET date string when premarket_reported was last cleared

detectors: dict[str, MicroPullbackDetector] = {}
stop_flag = threading.Event()

# Simple lock for shared counters/maps (keeps races from doing weird things)
state_lock = threading.RLock()

def ensure_detector(symbol: str) -> MicroPullbackDetector:
    if symbol not in detectors:
        det = MicroPullbackDetector(ema_len=9, max_pullback_bars=3)
        det.symbol = symbol
        detectors[symbol] = det
        print(f"Detector created for {symbol}: max_pullback_bars={det.max_pullback_bars}", flush=True)
    return detectors[symbol]

def _now_utc_epoch() -> float:
    return time.time()

def _mark_trade_seen(symbol: str):
    with state_lock:
        last_trade_ts[symbol] = _now_utc_epoch()

def _mark_quote_seen(symbol: str):
    with state_lock:
        last_quote_ts[symbol] = _now_utc_epoch()

def _stale_age_sec(symbol: str) -> float | None:
    """
    Returns age in seconds since the most recent quote OR trade update.
    Uses the freshest of the two (not just quotes).
    """
    now = _now_utc_epoch()
    with state_lock:
        qt = last_quote_ts.get(symbol)
        tt = last_trade_ts.get(symbol)

    # Use the most recent of quote or trade timestamp
    candidates = [ts for ts in (qt, tt) if ts is not None]
    if not candidates:
        return None
    return now - max(candidates)

def _should_warn_stale(symbol: str, age: float) -> bool:
    now = _now_utc_epoch()
    with state_lock:
        last_warn = last_stale_warn_ts.get(symbol, 0.0)
        if (now - last_warn) < STALE_WARN_COOLDOWN_SEC:
            return False
        last_stale_warn_ts[symbol] = now
    return age >= STALE_PRICE_SEC

def _is_symbol_active(symbol: str) -> bool:
    """
    Warn only if symbol matters:
    - open position, pending entry, or pending exit
    """
    if not trade_manager:
        return False
    return (
        (symbol in trade_manager.open)
        or (symbol in trade_manager.pending)
        or (symbol in trade_manager.pending_exits)
    )

def stale_price_monitor():
    """
    Runs in background. If we have open/pending symbols but no recent quote/trade updates,
    warn loudly so "stop didn't trigger" can't happen silently.
    """
    while not stop_flag.is_set():
        try:
            if not trade_manager:
                time.sleep(1.0)
                continue

            # Monitor only relevant symbols
            syms = set()
            syms |= set(trade_manager.open.keys())
            syms |= set(trade_manager.pending.keys())
            syms |= set(trade_manager.pending_exits.keys())

            for sym in syms:
                age = _stale_age_sec(sym)
                if age is None:
                    continue
                if age < STALE_PRICE_SEC:
                    continue
                if not _is_symbol_active(sym):
                    continue
                if not _should_warn_stale(sym, age):
                    continue

                open_qty = trade_manager.open.get(sym).qty_total if sym in trade_manager.open else 0
                pend = 1 if sym in trade_manager.pending else 0
                pexit = 1 if sym in trade_manager.pending_exits else 0

                msg = f"⚠️ STALE PRICE {sym}: no quote/trade updates for {age:.1f}s | open_qty={open_qty} pending={pend} exits={pexit}"
                print(msg, flush=True)
                log_event(
                    "stale_price_warning",
                    sym,
                    age_sec=float(age),
                    open_qty=int(open_qty),
                    has_pending=bool(pend),
                    has_pending_exit=bool(pexit),
                )

        except Exception:
            log_event("exception", None, where="stale_price_monitor", error=traceback.format_exc())

        time.sleep(1.0)

# -----------------------------
# Bar close handlers (dual timeframe)
# -----------------------------
def on_bar_close_10s(bar):
    """10-second bars: exit pattern detection + premarket reporting. No setup detection."""
    global pattern_hits, premarket_reported, _premarket_reported_date

    today_et = datetime.now(ET).strftime("%Y-%m-%d")
    if _premarket_reported_date != today_et:
        _premarket_reported_date = today_et
        premarket_reported.clear()

    symbol = bar.symbol
    det = ensure_detector(symbol)

    pm_high = bar_builder.get_premarket_high(symbol) if bar_builder else None
    pm_bf_high = bar_builder.get_premarket_bull_flag_high(symbol) if bar_builder else None

    # Update detector with premarket levels
    if bar_builder:
        det.update_premarket_levels(pm_high, pm_bf_high)

    # Check if we just entered market hours (report premarket summary)
    if bar_builder and bar_builder.is_market_hours(bar.start_utc):
        if symbol not in premarket_reported and pm_high is not None and pm_high > 0:
            premarket_reported.add(symbol)
            now = datetime.now(ET).strftime("%H:%M:%S")
            pm_high_str = f"{pm_high:.4f}"
            pm_bf_str = f"{pm_bf_high:.4f}" if pm_bf_high else "None"
            print(f"[{now} ET] 📊 {symbol} PREMARKET COMPLETE | PM_HIGH={pm_high_str} PM_BF_HIGH={pm_bf_str}", flush=True)
            log_event("premarket_complete", symbol, premarket_high=pm_high, premarket_bull_flag_high=pm_bf_high)

    # Count patterns (lightweight proxy for heartbeat)
    if getattr(det, "last_patterns", None) and det.last_patterns:
        pattern_hits += 1

    # Feed bar-close candle to trade_manager (for bearish engulfing exit detection)
    if trade_manager:
        trade_manager.on_bar_close(symbol, bar.open, bar.high, bar.low, bar.close, bar.volume)
        # Update R-multiple trailing stop on 10s bar close (WB_TRAILING_STOP_ENABLED gates this)
        trade_manager.update_trailing_stop_on_10s_bar(symbol, bar.close, bar.high)

    # Topping wicky exit: if we're in a trade and the pattern fires, get out
    # Grace period: skip exit within first N minutes of entry (breakout volatility)
    _tw_grace_sec = int(os.getenv("WB_TOPPING_WICKY_GRACE_MIN", "3")) * 60
    _tw_min_profit_r = float(os.getenv("WB_TW_MIN_PROFIT_R", "1.0"))
    if (trade_manager
        and getattr(trade_manager, 'exit_on_topping_wicky', False)
        and symbol in trade_manager.open
        and "TOPPING_WICKY" in (det.last_patterns or [])):
        t = trade_manager.open[symbol]
        age_sec = (datetime.now(timezone.utc) - t.created_at_utc).total_seconds() if t.created_at_utc else 999
        if age_sec >= _tw_grace_sec:
            # Profit gate: suppress TW on confirmed runners (profit >= min R)
            _tw_unreal = bar.close - t.entry
            _tw_r_thresh = _tw_min_profit_r * t.r
            if _tw_min_profit_r > 0 and t.r > 0 and _tw_unreal >= _tw_r_thresh:
                print(f"  TW_SUPPRESSED (profit_gate: ${_tw_unreal:.2f} >= {_tw_min_profit_r}R=${_tw_r_thresh:.2f}) {symbol} @ {bar.close:.4f}", flush=True)
            else:
                trade_manager.on_exit_signal(symbol, "topping_wicky")


def on_bar_close_1m(bar):
    """1-minute bars: PRIMARY setup detection (impulse → pullback → confirmation → ARM)."""
    global armed_hits

    symbol = bar.symbol
    det = ensure_detector(symbol)

    # Always query VWAP/PM from the 10s builder (both track identically, but 10s is canonical)
    vwap = bar_builder.get_vwap(symbol) if bar_builder else None
    pm_high = bar_builder.get_premarket_high(symbol) if bar_builder else None

    # PRIMARY: 1-minute setup detection
    msg = det.on_bar_close_1m(bar, vwap=vwap)

    # Block ARM signals for symbols that failed session-start filter
    if msg and msg.startswith("ARMED") and symbol in _session_filtered_out:
        msg = None

    # Time gate: no ARMs before 7:00 AM ET (premarket too thin for reliable entries)
    arm_earliest_et = int(os.getenv("WB_ARM_EARLIEST_HOUR_ET", "7"))
    if msg and msg.startswith("ARMED"):
        now_et = datetime.now(ET)
        if now_et.hour < arm_earliest_et:
            print(f"  ⏰ ARM blocked (before {arm_earliest_et}:00 ET): {symbol}", flush=True)
            msg = None

    # Count ARMED events
    if msg and msg.startswith("ARMED"):
        armed_hits += 1

    # Log 1m bar snapshot
    log_event(
        "bar_closed_1m",
        symbol,
        start_utc=bar.start_utc.isoformat(),
        open=bar.open,
        high=bar.high,
        low=bar.low,
        close=bar.close,
        volume=bar.volume,
        vwap=vwap,
        ema9=det.ema,
        premarket_high=pm_high,
    )

    # Log detector messages to file
    if msg:
        log_event(
            "signal_1m",
            symbol,
            msg=msg,
            close=bar.close,
            vwap=vwap,
            ema9=det.ema,
            volume=bar.volume,
            premarket_high=pm_high,
        )

    # Continuation hold: 1m bar exit detection for live bot
    if trade_manager:
        trade_manager.on_bar_close_1m_cont_hold(symbol, bar.open, bar.high, bar.low, bar.close, bar.volume)

    if msg:
        # Console printing policy:
        # - Default: print only ARMED lines (trade-relevant)
        # - Optional: print all 1m bar signals (impulse/pullback/reset)
        should_print = False
        if PRINT_BAR_SIGNALS:
            should_print = True
        elif PRINT_ARMED_ONLY and msg.startswith("ARMED"):
            should_print = True

        if should_print:
            ts_et = bar.start_utc.astimezone(ET).strftime("%H:%M:%S")
            ema = det.ema
            ema_str = f"{ema:.4f}" if ema is not None else "None"
            vwap_str = f"{vwap:.4f}" if vwap is not None else "None"
            pm_str = f"{pm_high:.4f}" if pm_high else "None"
            print(
                f"[{ts_et} ET] {symbol} | {msg} | close={bar.close:.4f} EMA9={ema_str} VWAP={vwap_str} PM_HIGH={pm_str} vol={bar.volume}",
                flush=True,
            )

# -----------------------------
# Heartbeats
# -----------------------------
def console_heartbeat():
    while not stop_flag.is_set():
        try:
            open_n = len(trade_manager.open) if trade_manager else 0
            pend_n = len(trade_manager.pending) if trade_manager else 0
            exit_n = len(trade_manager.pending_exits) if trade_manager else 0
            wl_n = len(load_watchlist())
            now = datetime.now(ET).strftime("%H:%M:%S")

            print(
                f"[{now} ET] heartbeat | watch={wl_n} open={open_n} pending={pend_n} exits={exit_n} "
                f"| patt={pattern_hits} armed={armed_hits} signals={entry_signal_hits}",
                flush=True,
            )
        except Exception:
            pass
        time.sleep(10)

def pending_heartbeat():
    while not stop_flag.is_set():
        try:
            if trade_manager:
                trade_manager.check_pending_entries()
                trade_manager.check_pending_exits()
        except Exception:
            log_event("exception", None, where="pending_heartbeat", error=traceback.format_exc())
        time.sleep(0.5)

def on_bar_close_5m(bar):
    """5m bar close: trend guard exit detection for continuation hold trades."""
    if not trade_manager:
        return
    symbol = bar.symbol if hasattr(bar, "symbol") else getattr(bar, "sym", None)
    if not symbol:
        return
    trade_manager.on_bar_close_5m_trend_guard(symbol, bar.open, bar.high, bar.low, bar.close, bar.volume)


# -----------------------------
# Data feed handlers (called by DataFeed with normalized args)
# -----------------------------
def on_trade(symbol: str, price: float, size: int, ts: datetime):
    global entry_signal_hits
    try:
        if not symbol:
            return

        _mark_trade_seen(symbol)

        det = ensure_detector(symbol)

        if bar_builder:
            bar_builder.on_trade(symbol, price, size, ts)

            # Update detector with premarket levels for Gap and Go
            pm_high = bar_builder.get_premarket_high(symbol)
            pm_bf_high = bar_builder.get_premarket_bull_flag_high(symbol)
            det.update_premarket_levels(pm_high, pm_bf_high)

        if bar_builder_1m:
            bar_builder_1m.on_trade(symbol, price, size, ts)
        if bar_builder_5m:
            bar_builder_5m.on_trade(symbol, price, size, ts)

        # Feed live price into trade manager (stop/TP/runner logic)
        if trade_manager:
            trade_manager.on_price(symbol, price, ts)

        # Fast trigger check on prints (includes both micro pullback and Gap and Go)
        # Pass is_premarket so Gap and Go doesn't fire on continuously-updating pm_high during premarket
        in_premarket = bar_builder.is_premarket(ts) if bar_builder else False
        msg = det.on_trade_price(price, is_premarket=in_premarket)
        # Suppress all signal activity for symbols that failed session-start filter
        if msg and symbol in _session_filtered_out:
            msg = None
        if msg:
            now = datetime.now(ET).strftime("%H:%M:%S")
            vwap = bar_builder.get_vwap(symbol) if bar_builder else None
            hod = bar_builder.get_hod(symbol) if bar_builder else None
            pm_high = bar_builder.get_premarket_high(symbol) if bar_builder else None
            vwap_str = f"{vwap:.4f}" if vwap is not None else "None"
            hod_str = f"{hod:.4f}" if hod is not None else "None"
            pm_high_str = f"{pm_high:.4f}" if pm_high is not None else "None"

            # Only log fast signals; only PRINT entry signals
            log_event("signal_fast", symbol, msg=msg, price=price, vwap=vwap, hod=hod, premarket_high=pm_high)

            # Print and send to trade manager for ENTRY SIGNAL
            if msg.startswith("ENTRY SIGNAL"):
                entry_signal_hits += 1
                print(f"[{now} ET] {symbol} | {msg} | VWAP={vwap_str} HOD={hod_str} PM_HIGH={pm_high_str}", flush=True)
                if not MP_ENABLED:
                    print(f"[{now} ET] {symbol} | MP_DISABLED: skipping entry (WB_MP_ENABLED=0)", flush=True)
                elif trade_manager:
                    print(f"🟩 Sending to trade_manager: {symbol} | {msg}", flush=True)
                    trade_manager.on_signal(symbol, msg)

    except Exception:
        log_event("exception", None, where="on_trade", error=traceback.format_exc())
        return

def on_quote(symbol: str, bid, ask, ts: datetime):
    try:
        if not symbol:
            return

        _mark_quote_seen(symbol)

        if trade_manager:
            trade_manager.on_quote(symbol, bid, ask, ts)

    except Exception:
        log_event("exception", None, where="on_quote", error=traceback.format_exc())
        return

# -----------------------------
# Re-scan thread (periodic scanner, matches backtest checkpoints)
# -----------------------------
# Checkpoints in ET hours — scanner re-runs at each to catch emerging movers
RESCAN_CHECKPOINTS_ET = [
    (7, 30), (8, 0), (8, 30), (9, 0), (9, 30), (10, 0), (10, 30),
]

# Shared set that watchlist_thread reads — new symbols appear here after re-scans
rescan_symbols: set = set()
rescan_lock = threading.Lock()

def rescan_thread():
    """
    Periodically re-run the MarketScanner + StockFilter to catch stocks that
    start gapping after the initial 4 AM scan. Mirrors the backtest's 30-minute
    checkpoint approach from scanner_sim.py.

    New symbols are added to rescan_symbols; watchlist_thread picks them up
    automatically on its next poll cycle.
    """
    enable_dynamic = os.getenv("WB_ENABLE_DYNAMIC_SCANNER", "0") == "1"
    if not enable_dynamic:
        return

    fired = set()  # checkpoints already fired

    while not stop_flag.is_set():
        try:
            now_et = datetime.now(ET)
            h, m = now_et.hour, now_et.minute

            # Find the next checkpoint that should fire
            for cp_h, cp_m in RESCAN_CHECKPOINTS_ET:
                cp_key = (cp_h, cp_m)
                if cp_key in fired:
                    continue
                if h > cp_h or (h == cp_h and m >= cp_m):
                    fired.add(cp_key)
                    print(f"\n🔄 RESCAN [{cp_h}:{cp_m:02d} ET] Running market scanner...", flush=True)
                    log_event("rescan_start", None, checkpoint=f"{cp_h}:{cp_m:02d}")

                    try:
                        scanner = MarketScanner(API_KEY, API_SECRET)
                        raw = scanner.scan_market()
                        if not raw:
                            print(f"   Rescan returned 0 symbols", flush=True)
                            continue

                        filtered_result = filter_watchlist(raw)

                        if isinstance(filtered_result, dict):
                            # Extract rank order before updating cache
                            rescan_rank_order = filtered_result.pop("__rank_order__", [])
                            new_syms = set(filtered_result.keys())
                            # Update stock_info_cache for new symbols
                            with state_lock:
                                _stock_info_cache.update(filtered_result)
                                if trade_manager:
                                    trade_manager.set_stock_info_cache(_stock_info_cache)
                                    if rescan_rank_order:
                                        trade_manager.set_symbol_ranks(rescan_rank_order)
                        else:
                            new_syms = filtered_result if isinstance(filtered_result, set) else set()

                        with rescan_lock:
                            added = new_syms - rescan_symbols
                            rescan_symbols.update(new_syms)

                        if added:
                            print(f"   🆕 Rescan found {len(added)} new symbols: {sorted(added)}", flush=True)
                            log_event("rescan_new_symbols", None, count=len(added), symbols=sorted(added))
                        else:
                            print(f"   Rescan: no new symbols (total tracked: {len(rescan_symbols)})", flush=True)

                    except Exception as e:
                        print(f"⚠️ Rescan failed: {e}", flush=True)
                        log_event("exception", None, where="rescan_thread", error=str(e))

            # Past last checkpoint — thread can exit
            last_cp = RESCAN_CHECKPOINTS_ET[-1]
            if h > last_cp[0] or (h == last_cp[0] and m >= last_cp[1]):
                print("🔄 Rescan thread done (past last checkpoint)", flush=True)
                return

        except Exception:
            log_event("exception", None, where="rescan_thread_outer", error=traceback.format_exc())

        time.sleep(30)  # Check every 30 seconds


# -----------------------------
# Watchlist thread
# -----------------------------
def watchlist_thread(feed: DataFeed, initial_filtered: set):
    """
    Monitor watchlist for changes.
    Re-reads watchlist.txt every loop so the user can add/remove tickers live.
    Always keeps initial_filtered (scanner picks) even if the file changes.
    """
    watched = set()
    while not stop_flag.is_set():
        # Re-read the file every iteration so manual edits take effect immediately.
        # Union with initial_filtered + rescan_symbols to keep all discovered symbols.
        with rescan_lock:
            rescan_copy = set(rescan_symbols)
        symbols = load_watchlist() | initial_filtered | rescan_copy

        new_syms = symbols - watched
        removed_syms = watched - symbols

        if new_syms:
            for sym in sorted(new_syms):
                print(f"✅ Subscribing: {sym}", flush=True)
                log_event("watchlist_subscribe", sym)
                feed.subscribe_trades(sym, on_trade)
                feed.subscribe_quotes(sym, on_quote)
                seed_symbol_from_history(sym, minutes=60)
                ensure_detector(sym)
            # Update session file so restart picks up new additions too
            _save_session_symbols(symbols)

        for sym in sorted(removed_syms):
            print(f"🛑 Unsubscribing: {sym}", flush=True)
            log_event("watchlist_unsubscribe", sym)
            feed.unsubscribe_trades(sym)
            feed.unsubscribe_quotes(sym)

        watched = symbols
        time.sleep(POLL_SECONDS)

# -----------------------------
# Session symbol persistence
# -----------------------------
SESSION_SYMBOLS_FILE = "last_session_symbols.txt"

def _save_session_symbols(symbols: set):
    """
    Write the current session's active symbols to last_session_symbols.txt.
    This file is never auto-loaded — it's a human recovery tool.

    If the bot needs to be restarted mid-session:
      cp last_session_symbols.txt watchlist.txt
    then restart. The bot will pick up exactly the same symbols.
    """
    if not symbols:
        return
    try:
        now_et = datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S ET")
        lines = [f"# Warrior Bot session symbols — saved {now_et}"]
        lines += sorted(symbols)
        lines.append("")  # trailing newline

        with open(SESSION_SYMBOLS_FILE, "w") as f:
            f.write("\n".join(lines))

        print(
            f"\n💾 SESSION SYMBOLS SAVED → {SESSION_SYMBOLS_FILE}",
            flush=True,
        )
        print(
            f"   If you restart the bot mid-session, run:\n"
            f"   cp {SESSION_SYMBOLS_FILE} watchlist.txt",
            flush=True,
        )
        log_event("session_symbols_saved", None, count=len(symbols), file=SESSION_SYMBOLS_FILE)

    except Exception as e:
        print(f"⚠️ Could not save session symbols: {e}", flush=True)


# -----------------------------
# Main
# -----------------------------
def main():
    global bar_builder, bar_builder_1m, bar_builder_5m, trade_manager

    print("=== Warrior Bot: 1-Min Primary + 10s Exits + Micro Pullback (PAPER EDITION) ===", flush=True)

    # Load raw watchlist (from file or dynamic scanner)
    raw_watchlist = get_raw_watchlist()
    print(f"\n📋 Raw watchlist: {len(raw_watchlist)} symbols", flush=True)

    # Only print full list if < 50 symbols (otherwise too verbose)
    if len(raw_watchlist) <= 50:
        print(f"   {sorted(raw_watchlist)}", flush=True)
    else:
        print(f"   (too many to display - use dynamic scanner mode)", flush=True)

    # Filter based on Ross Cameron criteria (gap %, float, EMAs, rel volume)
    filtered_result = filter_watchlist(raw_watchlist)

    # Normalize: filter returns dict {symbol: StockInfo} when successful, set when disabled/failed
    global _stock_info_cache
    if isinstance(filtered_result, dict):
        # Extract rank order before storing cache (__rank_order__ is not a StockInfo entry)
        _rank_order = filtered_result.pop("__rank_order__", [])
        stock_info_cache = filtered_result
        _stock_info_cache = stock_info_cache
        filtered_watchlist = set(filtered_result.keys())
    else:
        _rank_order = []
        stock_info_cache = {}
        _stock_info_cache = {}
        filtered_watchlist = filtered_result

    global _session_filtered_out
    _session_filtered_out = raw_watchlist - filtered_watchlist
    if _session_filtered_out:
        print(f"\n🚫 Blocked symbols (failed filter, will not trade): {sorted(_session_filtered_out)}", flush=True)

    print(f"\n✅ Filtered watchlist: {len(filtered_watchlist)} symbols", flush=True)
    print(f"   {sorted(filtered_watchlist)}", flush=True)
    print(f"\nNow (ET): {datetime.now(ET)}", flush=True)

    if not filtered_watchlist:
        print("WARNING: Zero symbols passed filters — bot will run but trade nothing today.", flush=True)
        print("Check scanner pre-filter and stock_filter output above for details.", flush=True)
        log_event("zero_watchlist", None, reason="no symbols passed all filters")

    # Save the session's active symbols so a mid-session restart can restore them quickly.
    # This file is NEVER auto-loaded — it's just a human reference.
    # To restore after a restart: copy last_session_symbols.txt → watchlist.txt
    _save_session_symbols(filtered_watchlist)

    feed = create_feed(api_key=API_KEY, api_secret=API_SECRET)

    bar_builder = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
    bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
    bar_builder_5m = TradeBarBuilder(on_bar_close=on_bar_close_5m, et_tz=ET, interval_seconds=300)

    trade_manager = PaperTradeManager()
    trade_manager.set_stock_info_cache(stock_info_cache)
    if _rank_order:
        trade_manager.set_symbol_ranks(_rank_order)
    trade_manager._micro_detectors = detectors  # Share detector refs for continuation hold vol_dom

    # Wire up quality gate: notify detector of trade results for Gate 5 (no re-entry after loss)
    def _on_trade_close(symbol: str, pnl: float):
        if symbol in detectors:
            detectors[symbol].record_trade_result(pnl)
    trade_manager.on_trade_close_callback = _on_trade_close

    print(f"✅ PaperTradeManager initialized (stock_info cached: {len(stock_info_cache)} symbols)", flush=True)
    log_event("paper_manager_initialized", None, stock_info_cached=len(stock_info_cache))

    # Reconcile a robust universe (filtered watchlist + any active symbols)
    def reconcile_universe():
        syms = set(filtered_watchlist)  # Use filtered list
        if trade_manager:
            syms |= set(trade_manager.open.keys())
            syms |= set(trade_manager.pending.keys())
            syms |= set(trade_manager.pending_exits.keys())
        return list(syms)

    trade_manager.start_reconcile_thread(reconcile_universe)

    # Seed all filtered watchlist symbols so indicators are ready immediately
    for sym in sorted(filtered_watchlist):
        ensure_detector(sym)
        seed_symbol_from_history(sym, minutes=60)

    hb = threading.Thread(target=pending_heartbeat, daemon=True)
    hb.start()

    chb = threading.Thread(target=console_heartbeat, daemon=True)
    chb.start()

    # ✅ stale price monitor
    spm = threading.Thread(target=stale_price_monitor, daemon=True)
    spm.start()

    t = threading.Thread(target=watchlist_thread, args=(feed, filtered_watchlist), daemon=True)
    t.start()

    # Periodic re-scan thread (catches emerging movers after initial scan)
    rst = threading.Thread(target=rescan_thread, daemon=True)
    rst.start()

    feed_name = os.getenv("WB_DATA_FEED", "alpaca").lower()
    print(f"Connecting to {feed_name} data feed... (Ctrl+C to stop)", flush=True)
    try:
        feed.run()
    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
    except Exception:
        print("🔥 Bot crashed with exception:", flush=True)
        traceback.print_exc()
        log_event("exception", None, where="main", error=traceback.format_exc())
    finally:
        stop_flag.set()

if __name__ == "__main__":
    main()

