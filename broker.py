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

    def get_buying_power(self) -> float:
        """Current buying power for position sizing."""
        try:
            acct = _with_timeout(self._c.get_account, timeout=5)
            return float(acct.buying_power)
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
    is event-driven inside ib_insync (each Trade carries its own orderStatus
    that is updated by the event loop). The BrokerClient contract exposes
    that as a polled `get_order_status` for parity with Alpaca's paradigm.

    Thread-safety: ib_insync is single-event-loop. Methods here run on the
    same loop as the bot's market-data thread; avoid blocking calls that
    would stall ticker updates. `ib.placeOrder` itself is non-blocking
    (returns immediately with a Trade whose status fills in via events).
    """

    # IBKR raw status strings → normalized BrokerClient STATUS_* constants.
    # Reference: ib_insync OrderStatus.Status docstring.
    _STATUS_MAP = {
        "pendingsubmit": STATUS_SUBMITTED,
        "pendingcancel": STATUS_SUBMITTED,  # still live
        "presubmitted": STATUS_SUBMITTED,
        "submitted": STATUS_SUBMITTED,
        "apicancelled": STATUS_CANCELLED,
        "cancelled": STATUS_CANCELLED,
        "filled": STATUS_FILLED,
        "inactive": STATUS_REJECTED,  # IBKR uses Inactive for rejections
    }

    def __init__(self, ib, contracts: dict = None):
        self._ib = ib
        # Trade objects indexed by string orderId. Required because
        # get_order_status / cancel_order need the Trade, not just an id.
        self._trades: dict = {}
        # External contract cache shared with the bot (state.contracts).
        # When callers submit orders from within an ib_insync event loop
        # callback (tick / bar handlers), calling ib.qualifyContracts() is
        # a nested ib.run() and raises "This event loop is already running".
        # We avoid that by reading from the bot's pre-qualified dict first.
        self._contracts_external = contracts
        # Private fallback cache for symbols not pre-qualified externally
        # (e.g. used from the standalone test harness).
        self._contracts: dict = {}
        # Per-symbol shortable cache. False = known non-shortable; True =
        # known shortable; absent = not yet resolved.
        self._shortable_cache: dict = {}

    # ─ Helpers ────────────────────────────────────────────────────
    def _contract_for(self, symbol: str):
        """Return a qualified Stock contract for symbol.

        Prefers the bot's externally-populated contracts dict (safe from
        any call context). Falls back to our own cache and — only as a
        last resort — to ib.qualifyContracts, which is UNSAFE to call
        from an event-loop callback (it performs a nested ib.run()).
        """
        sym = symbol.upper()
        # 1. External dict populated by bot's subscribe_symbol.
        if self._contracts_external is not None:
            c = self._contracts_external.get(sym) or self._contracts_external.get(symbol)
            if c is not None:
                return c
        # 2. Our own cache from prior qualifications (test harness).
        if sym in self._contracts:
            return self._contracts[sym]
        # 3. Fallback — only safe to call from outside a loop callback.
        from ib_insync import Stock
        c = Stock(sym, "SMART", "USD")
        self._ib.qualifyContracts(c)
        self._contracts[sym] = c
        return c

    def _normalize_status(self, raw_status: str, filled: int, total: int) -> str:
        """Map IBKR's OrderStatus string + fill counts into STATUS_* const."""
        if not raw_status:
            return STATUS_UNKNOWN
        base = self._STATUS_MAP.get(raw_status.lower(), STATUS_UNKNOWN)
        # IBKR doesn't emit 'PartiallyFilled' — a partial fill still reads
        # as 'Submitted' with filled>0. Detect by counts.
        if base == STATUS_SUBMITTED and 0 < filled < total:
            return STATUS_PARTIALLY
        return base

    def _order_from_trade(self, trade, *, side: str = "") -> BrokerOrder:
        """Build a BrokerOrder snapshot from an ib_insync Trade object."""
        o = trade.order
        st = trade.orderStatus
        total = int(o.totalQuantity or 0)
        filled = int(st.filled or 0)
        side_ = side or str(o.action or "").upper()
        status = self._normalize_status(st.status, filled, total)
        return BrokerOrder(
            order_id=str(o.orderId),
            symbol=getattr(trade.contract, "symbol", ""),
            qty=total,
            side=side_,
            limit_price=float(o.lmtPrice or 0),
            status=status,
            filled_qty=filled,
            filled_avg_price=float(st.avgFillPrice or 0),
            reject_reason=str(st.whyHeld or ""),
            _handle=trade,
        )

    # ─ Order submission ────────────────────────────────────────────
    def submit_limit(self, symbol: str, qty: int, side: str,
                     limit_price: float, extended_hours: bool = True) -> BrokerOrder:
        """Submit a limit order. ib_insync returns a Trade immediately;
        actual acceptance / rejection arrives asynchronously via orderStatus
        events. Callers should poll get_order_status to observe final state."""
        from ib_insync import LimitOrder
        contract = self._contract_for(symbol)
        action = "BUY" if side.upper() == "BUY" else "SELL"
        order = LimitOrder(action, int(qty), round(float(limit_price), 2))
        # Extended hours: IBKR requires outsideRth=True AND TIF=GTC. DAY TIF
        # won't fill outside RTH even with outsideRth set.
        order.outsideRth = bool(extended_hours)
        order.tif = "GTC" if extended_hours else "DAY"
        trade = self._ib.placeOrder(contract, order)
        # Note: ib.sleep(0) would pump the event loop here, but calling it
        # from inside a callback ("This event loop is already running")
        # raises. ib_insync assigns orderId synchronously before the event
        # round-trip, so reading it immediately is safe.
        order_id = str(trade.order.orderId)
        self._trades[order_id] = trade
        return self._order_from_trade(trade, side=action)

    def submit_market(self, symbol: str, qty: int, side: str) -> BrokerOrder:
        """Submit a market order. Market orders don't fire outside RTH —
        outsideRth is left False."""
        from ib_insync import MarketOrder
        contract = self._contract_for(symbol)
        action = "BUY" if side.upper() == "BUY" else "SELL"
        order = MarketOrder(action, int(qty))
        order.tif = "DAY"
        order.outsideRth = False
        trade = self._ib.placeOrder(contract, order)
        self._ib.sleep(0)
        order_id = str(trade.order.orderId)
        self._trades[order_id] = trade
        return self._order_from_trade(trade, side=action)

    def cancel_order(self, order_id: str) -> None:
        """Best-effort cancel. Unknown order_ids are silently ignored —
        caller confirms terminal state via get_order_status."""
        trade = self._trades.get(str(order_id))
        if trade is None or trade.isDone():
            return
        try:
            self._ib.cancelOrder(trade.order)
        except Exception:
            pass

    def get_order_status(self, order_id: str) -> Optional[BrokerOrder]:
        """Read current Trade.orderStatus snapshot. Returns None for
        unknown order_ids (the bot restarted mid-flight, Trade not in
        our cache)."""
        trade = self._trades.get(str(order_id))
        if trade is None:
            return None
        return self._order_from_trade(trade)

    def get_open_orders(self) -> list[BrokerOrder]:
        """All non-terminal Trades for this session."""
        return [
            self._order_from_trade(t)
            for t in self._ib.trades()
            if not t.isDone()
        ]

    # ─ Position + account ──────────────────────────────────────────
    def get_positions(self) -> list[BrokerPosition]:
        """Return open positions. qty_available is derived from open
        exit orders against the symbol (IBKR has no held_for_orders
        concept). Uses portfolio() when available (includes market data),
        falls back to positions() when it's not."""
        out = []
        # Prefer portfolio() — richer data (marketValue, unrealizedPNL).
        items = []
        try:
            items = self._ib.portfolio()
        except Exception:
            items = []

        if items:
            for it in items:
                qty = int(it.position)
                if qty == 0:
                    continue
                sym = getattr(it.contract, "symbol", "")
                out.append(BrokerPosition(
                    symbol=sym,
                    qty=qty,
                    qty_available=self._qty_available(sym, qty),
                    avg_entry_price=float(it.averageCost or 0),
                    unrealized_pnl=float(it.unrealizedPNL or 0),
                    market_value=float(it.marketValue or 0),
                ))
            return out

        # Fallback: positions() has no market-value data.
        for p in self._ib.positions():
            qty = int(p.position)
            if qty == 0:
                continue
            sym = getattr(p.contract, "symbol", "")
            out.append(BrokerPosition(
                symbol=sym,
                qty=qty,
                qty_available=self._qty_available(sym, qty),
                avg_entry_price=float(p.avgCost or 0),
            ))
        return out

    def _qty_available(self, symbol: str, signed_qty: int) -> int:
        """Mimic Alpaca's qty_available = qty - held_for_orders. For IBKR,
        held_for_orders is the sum of pending close-side orders on symbol."""
        if signed_qty == 0:
            return 0
        # Long → closes are SELL; short → closes are BUY
        close_side = "SELL" if signed_qty > 0 else "BUY"
        held = 0
        for t in self._ib.trades():
            if t.isDone():
                continue
            if getattr(t.contract, "symbol", "") != symbol:
                continue
            if str(t.order.action).upper() != close_side:
                continue
            remaining = int(t.order.totalQuantity or 0) - int(t.orderStatus.filled or 0)
            held += max(0, remaining)
        free = max(0, abs(signed_qty) - held)
        return free

    def get_account_equity(self) -> float:
        """IBKR NetLiquidation for position sizing. accountValues() is
        populated by the connection; no network round-trip here."""
        return self._account_value("NetLiquidation")

    def get_buying_power(self) -> float:
        """IBKR BuyingPower — the broker-reported max notional before
        margin calls. Accounts under $25K get 2× (RegT); over $25K
        get 4× (PDT). Caller multiplies by WB_BUYING_POWER_PCT to
        get the effective position-size cap."""
        return self._account_value("BuyingPower")

    def _account_value(self, tag: str) -> float:
        try:
            for v in self._ib.accountValues():
                if v.tag == tag and v.currency == "USD":
                    try:
                        return float(v.value)
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass
        return 0.0

    def is_shortable(self, symbol: str) -> bool:
        """Phase 2 MVP: optimistic True, with post-submit rejection as the
        filter. IBKR's live shortable universe is broad — we default to
        True and let broker-side rejections (status=Inactive with HTB
        reason) populate the negative cache via the existing short-detector
        `_shorted` gate (one attempt per symbol per session).

        Future enhancement: subscribe generic tick 236 (ShortableShares)
        on first lookup and read ticker.shortableShares directly. Deferred
        to avoid disturbing the main reqMktData('233') subscription path
        during the Phase 2 rollout."""
        sym = symbol.upper()
        if sym in self._shortable_cache:
            return self._shortable_cache[sym]
        self._shortable_cache[sym] = True
        return True


# ════════════════════════════════════════════════════════════════════════
# Factory
# ════════════════════════════════════════════════════════════════════════

def make_broker(backend: str, *, alpaca=None, ib=None, contracts: dict = None):
    """Construct a BrokerClient for the named backend.

    backend:   "alpaca" | "ibkr" (case-insensitive). From WB_BROKER env.
    alpaca:    alpaca.trading.client.TradingClient instance (required if
               backend == "alpaca").
    ib:        ib_insync.IB instance (required if backend == "ibkr").
    contracts: optional symbol→Contract dict the caller already maintains
               (e.g., bot's state.contracts). IBKRBroker uses it to avoid
               calling ib.qualifyContracts() from inside event callbacks
               (which would deadlock on nested event-loop run).
    """
    b = (backend or "alpaca").lower()
    if b == "alpaca":
        if alpaca is None:
            raise ValueError("make_broker(alpaca): alpaca=TradingClient required")
        return AlpacaBroker(alpaca)
    if b == "ibkr":
        if ib is None:
            raise ValueError("make_broker(ibkr): ib=IB required")
        return IBKRBroker(ib, contracts=contracts)
    raise ValueError(f"Unknown broker backend: {backend}")
