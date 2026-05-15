"""L2 Layer 1 helper — dedicated-bg-thread refactor (P1.1, 2026-05-15).

Cowork directive DIRECTIVE_2026-05-15_DAILY_RESPONSE.md §3 P1.1: rewrite
request_l2_snapshot to run the IBKR feed on a dedicated background
asyncio loop in its own thread, with its own IB() connection on a
unique clientId. The bot's main asyncio loop is NEVER touched.

Why: the previous `.attach()` design recursed into the bot's event loop
via threading.Event().wait() inside reqMktDepth → ib_insync raised
"This event loop is already running". The bg-thread model isolates the
L2 client entirely.

Per-process clientId: each bot sets WB_L2_CLIENT_ID via env before
importing this module. Map:
  Setup A main          → 42
  Setup A subbot        → 43
  Engine wb_bot         → 44
  Engine squeeze_bot    → 45

Public API (unchanged for callers):
  request_l2_snapshot(symbol, ib_instance=None, timeout_sec=2.0) -> dict | None
  evaluate_l2_filter(state) -> L2Verdict
  summarize_l2(state) -> str

`ib_instance` is now IGNORED (legacy param kept for caller compat).
The bg thread always uses its own IB connection.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import threading
from dataclasses import dataclass
from typing import Optional

# Env (read once at import)
_MAX_SPREAD_PCT = float(os.environ.get("WB_L2_MAX_SPREAD_PCT", "1.0"))
_MIN_IMBALANCE = float(os.environ.get("WB_L2_MIN_IMBALANCE", "0.40"))
_MIN_BID_DEPTH_TOUCH = float(os.environ.get("WB_L2_MIN_BID_DEPTH_TOUCH", "1000"))
_BLOCK_LARGE_ASK = os.environ.get("WB_L2_BLOCK_LARGE_ASK", "1") == "1"
_BLOCK_FALLING_TREND = os.environ.get("WB_L2_BLOCK_FALLING_TREND", "0") == "1"
_BID_DEPTH_TOUCH_PCT = float(os.environ.get("WB_L2_BID_DEPTH_TOUCH_PCT", "0.5"))

_IBKR_HOST = os.environ.get("WB_IBKR_HOST", "127.0.0.1")
_IBKR_PORT = int(os.environ.get("WB_IBKR_PORT", "4002"))
_IBKR_CLIENT_ID = int(os.environ.get("WB_L2_CLIENT_ID", os.environ.get("WB_IBKR_CLIENT_ID", "42")))


@dataclass
class L2Verdict:
    action: str   # "PASS" or "VETO"
    reason: str


# ── Background asyncio loop + IBKR connection (lazy, per-process singleton) ──
_BG_LOCK = threading.Lock()
_BG_LOOP: Optional[asyncio.AbstractEventLoop] = None
_BG_THREAD: Optional[threading.Thread] = None
_BG_IB = None                    # ib_insync IB instance bound to _BG_LOOP
_BG_CONNECT_FAILED = False       # latch — don't keep retrying on persistent failures
_DETECTOR = None                 # L2SignalDetector singleton (thread-safe enough for our use)


def _bg_loop_runner(loop: asyncio.AbstractEventLoop) -> None:
    """Run the dedicated event loop forever (until process exit)."""
    asyncio.set_event_loop(loop)
    try:
        loop.run_forever()
    except Exception as e:
        print(f"[L2] bg loop crashed: {e!r}", flush=True)


async def _bg_connect_ib_async() -> Optional[object]:
    """Async coroutine: dial IBKR on the bg-thread loop."""
    try:
        from ib_insync import IB
        ib = IB()
        await ib.connectAsync(_IBKR_HOST, _IBKR_PORT, clientId=_IBKR_CLIENT_ID,
                              timeout=10)
        print(f"[L2] bg-thread IB connected ({_IBKR_HOST}:{_IBKR_PORT} "
              f"clientId={_IBKR_CLIENT_ID})", flush=True)
        return ib
    except Exception as e:
        print(f"[L2] bg-thread IB connect failed: {e!r}", flush=True)
        return None


def _ensure_bg_ib() -> Optional[object]:
    """Lazy-init the bg loop + thread + IB connection. Returns the IB
    instance (bound to bg loop), or None on failure. Idempotent."""
    global _BG_LOOP, _BG_THREAD, _BG_IB, _BG_CONNECT_FAILED, _DETECTOR
    with _BG_LOCK:
        if _BG_IB is not None:
            return _BG_IB
        if _BG_CONNECT_FAILED:
            return None  # latched — don't keep trying

        # Start the bg loop+thread if not yet running
        if _BG_LOOP is None:
            _BG_LOOP = asyncio.new_event_loop()
            _BG_THREAD = threading.Thread(target=_bg_loop_runner,
                                           args=(_BG_LOOP,),
                                           name="l2-bg-loop",
                                           daemon=True)
            _BG_THREAD.start()

        # Schedule the connect coroutine on the bg loop and wait for result
        future = asyncio.run_coroutine_threadsafe(_bg_connect_ib_async(), _BG_LOOP)
        try:
            ib = future.result(timeout=15)
        except (concurrent.futures.TimeoutError, Exception) as e:
            print(f"[L2] _ensure_bg_ib connect-wait failed: {e!r}", flush=True)
            _BG_CONNECT_FAILED = True
            return None

        if ib is None:
            _BG_CONNECT_FAILED = True
            return None

        _BG_IB = ib

        # Lazy-init the detector while we're under the lock
        if _DETECTOR is None:
            from l2_signals import L2SignalDetector
            _DETECTOR = L2SignalDetector()

        return _BG_IB


async def _bg_fetch_l2_async(ib, symbol: str, num_rows: int,
                              timeout_sec: float):
    """Async coroutine: subscribe to market depth, wait for first non-empty
    snapshot, cancel subscription, return L2Snapshot or None. Runs on the
    bg event loop."""
    from datetime import datetime
    from ib_insync import Stock
    from l2_signals import L2Snapshot

    try:
        contract = Stock(symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
    except Exception as e:
        print(f"[L2] {symbol} qualify failed: {e!r}", flush=True)
        return None

    try:
        try:
            ticker = ib.reqMktDepth(contract, numRows=num_rows, isSmartDepth=True)
        except TypeError:
            ticker = ib.reqMktDepth(contract, numRows=num_rows)
    except Exception as e:
        print(f"[L2] {symbol} reqMktDepth failed: {e!r}", flush=True)
        return None

    # Poll until we see a non-empty book or timeout
    snap = None
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout_sec
    poll_interval = 0.1
    while loop.time() < deadline:
        await asyncio.sleep(poll_interval)
        bids = []
        asks = []
        try:
            if getattr(ticker, "domBids", None):
                for d in ticker.domBids:
                    if d.price > 0 and d.size > 0:
                        bids.append((float(d.price), int(d.size)))
            if getattr(ticker, "domAsks", None):
                for d in ticker.domAsks:
                    if d.price > 0 and d.size > 0:
                        asks.append((float(d.price), int(d.size)))
        except Exception:
            pass
        if bids and asks:
            try:
                from pytz import timezone
                snap = L2Snapshot(
                    timestamp=datetime.now(timezone("US/Eastern")),
                    symbol=symbol, bids=bids, asks=asks,
                )
            except Exception:
                snap = L2Snapshot(timestamp=datetime.now(), symbol=symbol,
                                  bids=bids, asks=asks)
            break

    try:
        ib.cancelMktDepth(contract)
    except Exception:
        pass
    return snap


def request_l2_snapshot(symbol: str, ib_instance=None,
                        timeout_sec: float = 2.0) -> Optional[dict]:
    """Sync wrapper: schedule the L2 fetch on the bg thread, block the
    caller for up to `timeout_sec`, return state dict or None.

    `ib_instance` is IGNORED (legacy param) — the bg thread always uses
    its own connection on WB_L2_CLIENT_ID. The bot's main loop is never
    touched.

    None on any failure (timeout, infra, etc) → caller treats as PASS."""
    ib = _ensure_bg_ib()
    if ib is None:
        return None

    future = asyncio.run_coroutine_threadsafe(
        _bg_fetch_l2_async(ib, symbol, 10, timeout_sec),
        _BG_LOOP,
    )
    try:
        snap = future.result(timeout=timeout_sec + 2.0)
    except (concurrent.futures.TimeoutError, Exception) as e:
        print(f"[L2] {symbol} snapshot future failed: {e!r}", flush=True)
        return None

    if snap is None:
        return None

    try:
        _DETECTOR.on_snapshot(snap)
        return _DETECTOR.get_state(symbol)
    except Exception as e:
        print(f"[L2] {symbol} detector.on_snapshot failed: {e!r}", flush=True)
        return None


# ── Verdict logic (unchanged from prior shipped version) ─────────────

def _bid_depth_proxy(state: dict) -> Optional[float]:
    """Coarse proxy for bid depth at touch. Returns high value when state
    evidences bid strength; None when insufficient evidence (don't VETO)."""
    if state.get("bid_stacking"):
        levels = state.get("bid_stack_levels", [])
        n = len(levels) if isinstance(levels, list) else int(levels or 0)
        if n > 0:
            return float(n) * 5000.0
        return 15000.0
    imb = state.get("imbalance", 0.5)
    if imb > 0.6 and state.get("ask_thinning"):
        return 10000.0
    return None


def evaluate_l2_filter(state: Optional[dict]) -> L2Verdict:
    if state is None:
        return L2Verdict("PASS", "no_l2_data")
    if state.get("spread_pct", 0) > _MAX_SPREAD_PCT:
        return L2Verdict("VETO", f"spread={state['spread_pct']:.2f}%>{_MAX_SPREAD_PCT}")
    imb = state.get("imbalance", 0.5)
    if imb < _MIN_IMBALANCE:
        return L2Verdict("VETO", f"imbalance={imb:.2f}<{_MIN_IMBALANCE}")
    bid_depth = _bid_depth_proxy(state)
    if bid_depth is not None and bid_depth < _MIN_BID_DEPTH_TOUCH:
        return L2Verdict("VETO", f"bid_depth_proxy={bid_depth:.0f}<{_MIN_BID_DEPTH_TOUCH}")
    if state.get("large_ask") and _BLOCK_LARGE_ASK:
        return L2Verdict("VETO", "large_ask_wall_above")
    if state.get("imbalance_trend") == "falling" and _BLOCK_FALLING_TREND:
        return L2Verdict("VETO", "imbalance_falling")
    return L2Verdict("PASS", f"imb={imb:.2f}_spread={state.get('spread_pct', 0):.2f}%")


def summarize_l2(state: Optional[dict]) -> str:
    if not state:
        return "none"
    return (f"imb={state.get('imbalance', 0):.2f}"
            f"({state.get('imbalance_trend','?')}) "
            f"spread={state.get('spread_pct', 0):.2f}% "
            f"stack={state.get('bid_stacking', False)} "
            f"lg_bid={state.get('large_bid', False)} "
            f"lg_ask={state.get('large_ask', False)}")


def env_summary() -> str:
    return (f"l2_helper: client_id={_IBKR_CLIENT_ID} max_spread={_MAX_SPREAD_PCT}% "
            f"min_imb={_MIN_IMBALANCE} min_bid_depth={_MIN_BID_DEPTH_TOUCH}")
