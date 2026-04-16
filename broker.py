"""Broker abstraction layer — routes execution through either Alpaca (legacy)
or IBKR (target), selected at bot startup via WB_BROKER env var.

Purpose: let the Alpaca→IBKR execution migration ship progressively without
touching bot_v3_hybrid.py's strategy logic. Every `state.alpaca.*` call in
the bot becomes `state.broker.*`; `state.broker` is either an AlpacaBroker
or an IBKRBroker, both implementing the same small surface defined below.

Design notes:
  - Normalized shapes: BrokerOrder + BrokerPosition. Callers never see
    alpaca-py or ib_insync types directly.
  - Normalized status strings: STATUS_* constants. Both backends map their
    native status codes to these.
  - Synchronous methods that perform network IO are wrapped in a thread +
    hard timeout (mirrors _alpaca_call pattern in bot_v3_hybrid.py). A hung
    broker call cannot freeze the main bot thread.
  - Order IDs are always str. IBKR's int orderId is stringified at the
    boundary; callers store strings and can use them unchanged across a
    restart / resume.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass, field
from typing import Optional


# ── Normalized status values ─────────────────────────────────────────────
# Callers match against these, not backend-specific status strings.

STATUS_SUBMITTED = "submitted"
STATUS_PARTIALLY = "partially_filled"
STATUS_FILLED = "filled"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"
STATUS_REJECTED = "rejected"
STATUS_UNKNOWN = "unknown"

TERMINAL_STATUSES = frozenset({
    STATUS_FILLED, STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED,
})


# ── Normalized shapes ────────────────────────────────────────────────────

@dataclass
class BrokerOrder:
    """Unified order shape returned by submit_* and get_order_status."""
    order_id: str
    symbol: str
    qty: int
    side: str  # "BUY" or "SELL"
    limit_price: float = 0.0
    status: str = STATUS_SUBMITTED
    filled_qty: int = 0
    filled_avg_price: float = 0.0
    reject_reason: str = ""
    # Backend-specific handle — callers must not rely on shape. Used by
    # IBKRBroker to correlate orderId back to the Trade object for fill
    # polling; AlpacaBroker stores the raw order reference if needed.
    _handle: object = field(default=None, repr=False, compare=False)


@dataclass
class BrokerPosition:
    """Unified position shape returned by get_positions."""
    symbol: str
    qty: int
    # qty_available = qty - held_by_pending_exit_orders. Alpaca's API
    # exposes this directly; IBKR computes it from openOrders ∩ positions.
    # Used for orphan-detection: if qty_available == 0, shares are in
    # flight on a pending order — don't try to flatten.
    qty_available: int
    avg_entry_price: float
    unrealized_pnl: float = 0.0
    market_value: float = 0.0


# ── Hard-timeout wrapper (mirrors _alpaca_call in bot_v3_hybrid.py) ──────
# Broker calls go through the network. A hung SSL read would otherwise
# freeze the main loop. Every sync method runs in a thread with a deadline.

_exec = ThreadPoolExecutor(max_workers=4, thread_name_prefix="broker-call")


def _with_timeout(fn, *args, timeout: float = 10.0, **kwargs):
    """Run fn in a worker thread, raise TimeoutError if it doesn't return
    within `timeout` seconds. We can't cancel a thread blocked on a kernel
    read — the next call gets a fresh worker from the pool."""
    fut = _exec.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout)
    except FuturesTimeoutError:
        raise TimeoutError(f"{fn.__name__} timed out after {timeout}s")


# ════════════════════════════════════════════════════════════════════════
# AlpacaBroker — wraps alpaca-py's TradingClient in the unified interface.
# ════════════════════════════════════════════════════════════════════════

class AlpacaBroker:
    """BrokerClient implementation backed by alpaca-py.

    Preserves today's behavior bit-for-bit — this class IS the current
    bot's Alpaca flow, just wrapped in BrokerClient. Used as the default
    broker (WB_BROKER=alpaca) and as the baseline against which IBKRBroker
    is validated.
    """

    def __init__(self, alpaca_client):
        """alpaca_client: alpaca.trading.client.TradingClient instance.
        Kept as-is; we never hide Alpaca's own models behind the wrapper —
        they're only surfaced through the normalized BrokerOrder /
        BrokerPosition shapes."""
        self._c = alpaca_client

    # ─ Status normalization ────────────────────────────────────────
    @staticmethod
    def _normalize_status(raw: str) -> str:
        """Alpaca status strings → BrokerClient STATUS_* constants."""
        if not raw:
            return STATUS_UNKNOWN
        s = str(raw).lower()
        if "partially_filled" in s:
            return STATUS_PARTIALLY
        if "filled" in s:
            return STATUS_FILLED
        if "cancel" in s:
            return STATUS_CANCELLED
        if "expired" in s:
            return STATUS_EXPIRED
        if "rejected" in s:
            return STATUS_REJECTED
        if "accepted" in s or "new" in s or "pending" in s or "sent" in s:
            return STATUS_SUBMITTED
        return STATUS_UNKNOWN

    @staticmethod
    def _order_from_alpaca(o, *, symbol: str = "", qty: int = 0,
                           side: str = "", limit_price: float = 0.0) -> BrokerOrder:
        """Build a BrokerOrder from an alpaca-py Order object."""
        sym = symbol or getattr(o, "symbol", "")
        q = qty or int(float(getattr(o, "qty", 0) or 0))
        side_ = side or str(getattr(o, "side", "")).upper().replace("ORDERSIDE.", "")
        status = AlpacaBroker._normalize_status(getattr(o, "status", ""))
        filled_qty = int(float(getattr(o, "filled_qty", 0) or 0))
        filled_avg = float(getattr(o, "filled_avg_price", 0) or 0)
        lp = limit_price or float(getattr(o, "limit_price", 0) or 0)
        return BrokerOrder(
            order_id=str(getattr(o, "id", "")),
            symbol=sym,
            qty=q,
            side=side_,
            limit_price=lp,
            status=status,
            filled_qty=filled_qty,
            filled_avg_price=filled_avg,
            _handle=o,
        )

    # ─ Order submission ────────────────────────────────────────────
    def submit_limit(self, symbol: str, qty: int, side: str,
                     limit_price: float, extended_hours: bool = True) -> BrokerOrder:
        """Submit a limit order. Raises on submission failure (preserves
        today's exception-based rejection path)."""
        # Import inside the method so non-Alpaca installs don't fail.
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = LimitOrderRequest(
            symbol=symbol, qty=qty,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=limit_price,
            extended_hours=extended_hours,
        )
        o = self._c.submit_order(req)
        return self._order_from_alpaca(
            o, symbol=symbol, qty=qty, side=side.upper(), limit_price=limit_price,
        )

    def submit_market(self, symbol: str, qty: int, side: str) -> BrokerOrder:
        """Submit a market order (no extended_hours field — Alpaca doesn't
        allow market orders during extended hours)."""
        from alpaca.trading.requests import MarketOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = MarketOrderRequest(
            symbol=symbol, qty=qty,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
        )
        o = self._c.submit_order(req)
        return self._order_from_alpaca(o, symbol=symbol, qty=qty, side=side.upper())

    def cancel_order(self, order_id: str) -> None:
        """Best-effort cancel. Swallows errors — caller uses status poll
        to confirm terminal state."""
        try:
            self._c.cancel_order_by_id(order_id)
        except Exception:
            pass

    def get_order_status(self, order_id: str) -> Optional[BrokerOrder]:
        """Fetch current state of an order. Returns None on lookup failure
        (e.g., order expired out of Alpaca's query window)."""
        try:
            o = _with_timeout(self._c.get_order_by_id, order_id, timeout=5)
            return self._order_from_alpaca(o)
        except Exception:
            return None

    def get_open_orders(self) -> list[BrokerOrder]:
        """Return all currently-open (non-terminal) orders."""
        try:
            orders = _with_timeout(self._c.get_orders, timeout=10) or []
        except Exception:
            return []
        return [self._order_from_alpaca(o) for o in orders]

    # ─ Position + account ──────────────────────────────────────────
    def get_positions(self) -> list[BrokerPosition]:
        """Return all open positions with held_for_orders-aware
        qty_available. The qty_available field is Alpaca-native."""
        try:
            positions = _with_timeout(self._c.get_all_positions, timeout=10) or []
        except Exception:
            return []
        out = []
        for p in positions:
            qty = int(float(getattr(p, "qty", 0) or 0))
            qty_avail = int(getattr(p, "qty_available", qty) or 0)
            avg = float(getattr(p, "avg_entry_price", 0) or 0)
            upnl = float(getattr(p, "unrealized_pl", 0) or 0)
            mval = float(getattr(p, "market_value", 0) or 0)
            out.append(BrokerPosition(
                symbol=getattr(p, "symbol", ""),
                qty=qty, qty_available=qty_avail,
                avg_entry_price=avg, unrealized_pnl=upnl, market_value=mval,
            ))
        return out

    def get_account_equity(self) -> float:
        """Current account equity for dynamic risk sizing."""
        try:
            acct = _with_timeout(self._c.get_account, timeout=5)
            return float(acct.equity)
        except Exception:
            return 0.0

    def is_shortable(self, symbol: str) -> bool:
        """Pre-trade check: can this name be sold short on this account?
        Returns False on lookup failure (conservative — treat as not
        shortable rather than attempt and be rejected)."""
        try:
            a = _with_timeout(self._c.get_asset, symbol, timeout=5)
            return bool(getattr(a, "shortable", False))
        except Exception:
            return False


# ════════════════════════════════════════════════════════════════════════
# IBKRBroker — wraps ib_insync.IB in the unified interface.
# ════════════════════════════════════════════════════════════════════════
# Phase 2 scope — filled in after Phase 1 lands. For now a stub that raises
# NotImplementedError so WB_BROKER=ibkr fails loudly instead of silently.

class IBKRBroker:
    """BrokerClient implementation backed by ib_insync.

    Uses the same IB() instance the bot opened for market data. Order flow
    is event-driven (trade.fillEvent) but exposed through the same poll-
    style get_order_status method Alpaca uses, for caller parity.

    Phase 2 will populate this class. Kept here to pin the import path
    and keep the factory symmetric.
    """
    def __init__(self, ib):
        self._ib = ib
        # trade handles indexed by string orderId — populated on each
        # submit_* call. Required because IBKR's get_order_status needs
        # the Trade object, not just the int orderId.
        self._trades: dict[str, object] = {}
        # Per-symbol shortable cache. Populated from reqShortableShares
        # on first lookup; invalidated never (borrow status can change
        # intraday, but within one session we trust the cached value).
        self._shortable_cache: dict[str, bool] = {}

    def submit_limit(self, symbol, qty, side, limit_price, extended_hours=True):
        raise NotImplementedError("IBKRBroker.submit_limit — Phase 2")

    def submit_market(self, symbol, qty, side):
        raise NotImplementedError("IBKRBroker.submit_market — Phase 2")

    def cancel_order(self, order_id):
        raise NotImplementedError("IBKRBroker.cancel_order — Phase 2")

    def get_order_status(self, order_id):
        raise NotImplementedError("IBKRBroker.get_order_status — Phase 2")

    def get_open_orders(self):
        raise NotImplementedError("IBKRBroker.get_open_orders — Phase 2")

    def get_positions(self):
        raise NotImplementedError("IBKRBroker.get_positions — Phase 2")

    def get_account_equity(self):
        raise NotImplementedError("IBKRBroker.get_account_equity — Phase 2")

    def is_shortable(self, symbol):
        raise NotImplementedError("IBKRBroker.is_shortable — Phase 2")


# ════════════════════════════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════════════════════════════

def make_broker(backend: str, *, alpaca=None, ib=None):
    """Construct a BrokerClient for the named backend.

    backend: "alpaca" | "ibkr" (case-insensitive). From WB_BROKER env.
    alpaca:  alpaca.trading.client.TradingClient instance (required if
             backend == "alpaca").
    ib:      ib_insync.IB instance (required if backend == "ibkr").
    """
    b = (backend or "alpaca").lower()
    if b == "alpaca":
        if alpaca is None:
            raise ValueError("make_broker(alpaca): alpaca=TradingClient required")
        return AlpacaBroker(alpaca)
    if b == "ibkr":
        if ib is None:
            raise ValueError("make_broker(ibkr): ib=IB required")
        return IBKRBroker(ib)
    raise ValueError(f"Unknown broker backend: {backend}")
