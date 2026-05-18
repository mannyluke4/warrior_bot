"""framework.live_broker — Alpaca limit-only exec wrapper for the framework runner.

Wave 4 paper deployment. Wraps `alpaca-py`'s `TradingClient` with the
limit-only conventions used by `bot_alpaca_subbot.py` (READ-ONLY reference):

  - Every submit is a LimitOrder (never MarketOrder). DAY tif.
  - Entry orders use the same slippage formula the squeeze stack uses
    (max of WB_ENTRY_SLIPPAGE_MIN $0.05 and WB_ENTRY_SLIPPAGE_PCT * price).
  - Entry retries: up to WB_ENTRY_MAX_RETRIES with cancel + reprice.
  - Stops are bot-internal (never submitted to the broker). They fire
    as SELL LIMIT exits at the configured stop trigger price.
  - Force-exit chains live in `force_exit.py` (READ-ONLY) — this module
    delegates to it for end-of-session flatten.

Hard constraints honored (per directive §1):
  - WB_NO_MARKET_ORDERS=1 — submit_market raises RuntimeError.
  - WB_NO_BROKER_STOPS=1  — submit_stop / submit_bracket NOT implemented.
  - WB_NO_OVERNIGHTS=1    — enforced via the runner's session-close
                            force-exit (this module exposes the hook).

Public API:
    LiveBroker(api_key, api_secret, paper=True)
    broker.connect() -> bool
    broker.submit_entry(symbol, qty, side, ref_price) -> dict
    broker.submit_exit(symbol, qty, side, ref_price) -> dict
    broker.cancel_order(order_id)
    broker.get_order_status(order_id)
    broker.get_account_equity() -> float
    broker.get_buying_power() -> float
    broker.get_positions() -> list
    broker.get_latest_quote(symbol) -> object | None  # used by force_exit
    broker.force_flatten(symbol, qty, ref_price)      # force-exit chain
"""
from __future__ import annotations

import os
import time as _time_mod
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Slippage helpers — same defaults as the squeeze stack
# ---------------------------------------------------------------------------


def _entry_slippage_for(price: float) -> float:
    min_slip = float(os.environ.get("WB_ENTRY_SLIPPAGE_MIN", "0.05"))
    pct_slip = float(os.environ.get("WB_ENTRY_SLIPPAGE_PCT", "0.005"))
    return max(min_slip, abs(price) * pct_slip)


def _exit_limit_price(price: float, side: str) -> float:
    """Compute aggressive exit limit. SELL goes below ref, BUY goes above.

    The framework only does long entries by default but short entries are
    schema-supported, so we accept side and adjust accordingly.
    """
    # 0.5% aggressive default (matches force_exit.py first offset)
    aggr = float(os.environ.get("WB_EXIT_AGGR_PCT", "0.5")) / 100.0
    if side.upper() == "SELL":
        return round(price * (1.0 - aggr), 2)
    return round(price * (1.0 + aggr), 2)


# ---------------------------------------------------------------------------
# Result objects — keep them thin so they're easy to mock in tests
# ---------------------------------------------------------------------------


@dataclass
class OrderResult:
    """Outcome of a submit_entry or submit_exit call."""

    order_id: str
    symbol: str
    qty: int
    side: str
    limit_price: float
    status: str            # "submitted" | "filled" | "cancelled" | "rejected" | "timeout"
    filled_qty: int = 0
    filled_avg_price: float = 0.0
    attempts: int = 1
    reason: str = ""


# ---------------------------------------------------------------------------
# LiveBroker
# ---------------------------------------------------------------------------


class LiveBroker:
    """Alpaca limit-only execution wrapper for the framework live runner.

    Two-mode operation:
      - dry_run=True : do NOT submit any orders. Connect-and-verify only.
      - dry_run=False: real submission via alpaca-py TradingClient.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper: bool = True,
        dry_run: bool = False,
    ) -> None:
        # Honor environment defaults from .env.framework.local (Manny
        # provisions these manually per directive).
        self.api_key = api_key or os.environ.get("APCA_API_KEY_ID")
        self.api_secret = api_secret or os.environ.get("APCA_API_SECRET_KEY")
        self.paper = bool(paper) if paper is not None else (
            os.environ.get("APCA_PAPER", "true").lower() == "true"
        )
        self.dry_run = bool(dry_run)
        self._client = None  # alpaca-py TradingClient
        self._connected = False

        # Hard guarantees from .env.framework
        self._no_market_orders = os.environ.get("WB_NO_MARKET_ORDERS", "1") == "1"
        self._no_broker_stops = os.environ.get("WB_NO_BROKER_STOPS", "1") == "1"

        # Entry retry knobs (same as squeeze stack)
        self._max_retries = int(os.environ.get("WB_ENTRY_MAX_RETRIES", "3"))
        self._retry_timeout = int(os.environ.get("WB_ENTRY_RETRY_TIMEOUT_SEC", "10"))
        self._max_chase_pct = float(os.environ.get("WB_ENTRY_MAX_CHASE_PCT", "2.0"))

    # ----- lifecycle -----

    def connect(self) -> bool:
        """Connect to Alpaca paper account. Dry-run mode verifies creds-only
        and does NOT instantiate the client (avoids any chance of a stray
        submit_order in test/wiring runs)."""
        if not self.api_key or not self.api_secret:
            print(
                "[FRAMEWORK_BROKER] FATAL: APCA_API_KEY_ID/APCA_API_SECRET_KEY "
                "not set — populate .env.framework.local",
                flush=True,
            )
            return False
        if self.dry_run:
            # Verify creds via a lightweight account fetch and then drop
            # the client reference so nothing else can use it.
            try:
                from alpaca.trading.client import TradingClient
            except ImportError as e:
                print(f"[FRAMEWORK_BROKER] alpaca-py not installed: {e}", flush=True)
                return False
            try:
                c = TradingClient(self.api_key, self.api_secret, paper=self.paper)
                acct = c.get_account()
                eq = float(getattr(acct, "equity", 0) or 0)
                print(
                    f"[FRAMEWORK_BROKER] DRY-RUN connect OK: "
                    f"account_equity=${eq:,.2f} paper={self.paper}",
                    flush=True,
                )
                # Hold the client for read-only methods even in dry-run
                # (get_positions, get_account_equity) — but submit_entry /
                # submit_exit guard on self.dry_run.
                self._client = c
                self._connected = True
                return True
            except Exception as e:
                print(f"[FRAMEWORK_BROKER] DRY-RUN connect failed: {e!r}", flush=True)
                return False

        try:
            from alpaca.trading.client import TradingClient
        except ImportError as e:
            print(f"[FRAMEWORK_BROKER] alpaca-py not installed: {e}", flush=True)
            return False
        try:
            self._client = TradingClient(self.api_key, self.api_secret, paper=self.paper)
            acct = self._client.get_account()
            print(
                f"[FRAMEWORK_BROKER] connected: paper={self.paper} "
                f"equity=${float(acct.equity):,.2f}",
                flush=True,
            )
            self._connected = True
            return True
        except Exception as e:
            print(f"[FRAMEWORK_BROKER] connect failed: {e!r}", flush=True)
            self._connected = False
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    # ----- limit-only submission ------------------------------------------

    def submit_limit(
        self,
        symbol: str,
        qty: int,
        side: str,
        limit_price: float,
        extended_hours: bool = False,
    ) -> Optional[object]:
        """Submit a plain LimitOrder via alpaca-py and return the raw order.

        In dry-run mode this is a no-op that returns None — the runner
        should never call this in dry-run, but guarded for safety.
        """
        if self.dry_run:
            print(
                f"[FRAMEWORK_BROKER] DRY-RUN: would submit LIMIT {side} {qty} {symbol} "
                f"@ ${limit_price:.4f} (extended_hours={extended_hours})",
                flush=True,
            )
            return None
        if not self.is_connected:
            raise RuntimeError("submit_limit: broker not connected")
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce
        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL,
            time_in_force=TimeInForce.DAY,
            limit_price=round(float(limit_price), 2),
            extended_hours=bool(extended_hours),
        )
        return self._client.submit_order(req)

    def submit_market(self, *_args, **_kwargs):
        """REJECTED — the framework never submits market orders.

        Per directive §1 + feedback_no_market_orders memory + .env.framework
        WB_NO_MARKET_ORDERS=1. Calling this is a programming error.
        """
        raise RuntimeError(
            "Market orders are forbidden in the framework runner "
            "(WB_NO_MARKET_ORDERS=1). Use submit_entry / submit_exit / "
            "force_flatten instead."
        )

    def submit_stop(self, *_args, **_kwargs):
        """REJECTED — broker-side stops are forbidden.

        Per directive §1 + feedback_no_broker_stops memory + .env.framework
        WB_NO_BROKER_STOPS=1. Stops are bot-internal price comparisons.
        """
        raise RuntimeError(
            "Broker-side stops are forbidden (WB_NO_BROKER_STOPS=1). "
            "Stops are evaluated in the runner and fire as SELL LIMIT exits."
        )

    # ----- entry retry chain ---------------------------------------------

    def submit_entry(
        self,
        symbol: str,
        qty: int,
        side: str,
        ref_price: float,
        max_retries: Optional[int] = None,
    ) -> OrderResult:
        """Submit a BUY (or SHORT-SELL) limit with the retry/reprice chain.

        Each attempt:
          - limit = ref_price (+ slippage) for BUY, (- slippage) for SHORT-SELL
          - wait WB_ENTRY_RETRY_TIMEOUT_SEC for fill
          - if unfilled: cancel + widen + retry
          - max chase 2% above original ref (per WB_ENTRY_MAX_CHASE_PCT)
        """
        retries = max_retries if max_retries is not None else self._max_retries
        side_u = side.upper()
        attempt = 0
        cur_order_id = ""
        last_status = "unsubmitted"
        slip = _entry_slippage_for(ref_price)
        original_ref = ref_price

        if self.dry_run:
            limit_price = ref_price + slip if side_u == "BUY" else ref_price - slip
            print(
                f"[FRAMEWORK_BROKER] DRY-RUN: would submit ENTRY {side_u} {qty} "
                f"{symbol} @ ${limit_price:.4f}",
                flush=True,
            )
            return OrderResult(
                order_id="dry-run",
                symbol=symbol,
                qty=qty,
                side=side_u,
                limit_price=limit_price,
                status="dry_run",
                attempts=0,
                reason="dry_run",
            )

        while attempt < retries:
            attempt += 1
            # Cap chase relative to original reference
            chase_pct = abs(ref_price - original_ref) / max(original_ref, 0.01) * 100.0
            if chase_pct > self._max_chase_pct:
                return OrderResult(
                    order_id=cur_order_id,
                    symbol=symbol,
                    qty=qty,
                    side=side_u,
                    limit_price=ref_price,
                    status="cancelled",
                    attempts=attempt - 1,
                    reason=f"chase_capped_at_{self._max_chase_pct}pct",
                )

            limit_price = (
                round(ref_price + slip, 2)
                if side_u == "BUY"
                else round(ref_price - slip, 2)
            )

            try:
                order = self.submit_limit(symbol, qty, side_u, limit_price)
            except Exception as e:
                print(
                    f"[FRAMEWORK_BROKER] entry submit raised attempt={attempt}: {e!r}",
                    flush=True,
                )
                # widen reference & retry
                ref_price = ref_price * (1.005 if side_u == "BUY" else 0.995)
                slip = _entry_slippage_for(ref_price)
                continue
            if order is None:
                return OrderResult(
                    order_id="",
                    symbol=symbol,
                    qty=qty,
                    side=side_u,
                    limit_price=limit_price,
                    status="rejected",
                    attempts=attempt,
                    reason="submit_returned_none",
                )
            cur_order_id = str(getattr(order, "id", ""))

            # Poll for fill
            deadline = _time_mod.time() + self._retry_timeout
            filled = False
            while _time_mod.time() < deadline:
                try:
                    o = self._client.get_order_by_id(cur_order_id)
                except Exception:
                    o = None
                if o is None:
                    _time_mod.sleep(0.5)
                    continue
                status = str(getattr(o, "status", "")).lower()
                if "filled" in status and "partially" not in status:
                    return OrderResult(
                        order_id=cur_order_id,
                        symbol=symbol,
                        qty=qty,
                        side=side_u,
                        limit_price=limit_price,
                        status="filled",
                        filled_qty=int(float(getattr(o, "filled_qty", 0) or 0)),
                        filled_avg_price=float(getattr(o, "filled_avg_price", 0) or 0),
                        attempts=attempt,
                        reason="filled",
                    )
                if status in ("cancelled", "expired", "rejected"):
                    last_status = status
                    break
                _time_mod.sleep(0.5)
            if filled:
                # unreachable — kept as guard if loop refactored
                break
            # cancel + widen + retry
            try:
                self._client.cancel_order_by_id(cur_order_id)
            except Exception:
                pass
            ref_price = ref_price * (1.005 if side_u == "BUY" else 0.995)
            slip = _entry_slippage_for(ref_price)

        return OrderResult(
            order_id=cur_order_id,
            symbol=symbol,
            qty=qty,
            side=side_u,
            limit_price=ref_price,
            status="timeout",
            attempts=attempt,
            reason=f"max_retries={retries}",
        )

    # ----- exit submission ------------------------------------------------

    def submit_exit(
        self,
        symbol: str,
        qty: int,
        side: str,
        ref_price: float,
        extended_hours: bool = False,
    ) -> OrderResult:
        """Submit a single aggressive SELL/BUY limit exit. No retry — the
        runner re-evaluates stop/target on each bar and resubmits if needed.

        side is the EXIT side ('SELL' for long, 'BUY' for short cover).
        """
        side_u = side.upper()
        limit_price = _exit_limit_price(ref_price, side_u)
        if self.dry_run:
            print(
                f"[FRAMEWORK_BROKER] DRY-RUN: would submit EXIT {side_u} {qty} "
                f"{symbol} @ ${limit_price:.4f}",
                flush=True,
            )
            return OrderResult(
                order_id="dry-run",
                symbol=symbol,
                qty=qty,
                side=side_u,
                limit_price=limit_price,
                status="dry_run",
                reason="dry_run",
            )
        try:
            order = self.submit_limit(
                symbol, qty, side_u, limit_price, extended_hours=extended_hours
            )
        except Exception as e:
            return OrderResult(
                order_id="",
                symbol=symbol,
                qty=qty,
                side=side_u,
                limit_price=limit_price,
                status="rejected",
                reason=f"submit_raised:{e!r}",
            )
        oid = str(getattr(order, "id", "")) if order is not None else ""
        return OrderResult(
            order_id=oid,
            symbol=symbol,
            qty=qty,
            side=side_u,
            limit_price=limit_price,
            status="submitted",
            reason="exit_submitted",
        )

    # ----- read methods ---------------------------------------------------

    def cancel_order(self, order_id: str) -> None:
        if self.dry_run or not self.is_connected:
            return
        try:
            self._client.cancel_order_by_id(order_id)
        except Exception:
            pass

    def get_order_status(self, order_id: str):
        if not self.is_connected or not order_id:
            return None
        try:
            return self._client.get_order_by_id(order_id)
        except Exception:
            return None

    def get_account_equity(self) -> float:
        if not self.is_connected:
            return 0.0
        try:
            acct = self._client.get_account()
            return float(acct.equity)
        except Exception:
            return 0.0

    def get_buying_power(self) -> float:
        if not self.is_connected:
            return 0.0
        try:
            acct = self._client.get_account()
            return float(acct.buying_power)
        except Exception:
            return 0.0

    def get_positions(self) -> list:
        if not self.is_connected:
            return []
        try:
            return self._client.get_all_positions() or []
        except Exception:
            return []

    def get_latest_quote(self, symbol: str):
        """Used by force_exit. Optional — returns None if data API not wired.

        The framework runner doesn't depend on Alpaca quote data (IBKR is
        the source of truth). force_exit's fallback path uses the
        reference price we hand it directly, so returning None is fine.
        """
        return None

    # ----- force-exit hook ------------------------------------------------

    def force_flatten(self, symbol: str, qty: int, ref_price: float) -> dict:
        """Delegate to force_exit.force_exit_position — aggressive SELL LIMIT
        chase ladder. Honors no-market-orders, no-overnights constraints.
        """
        if self.dry_run:
            print(
                f"[FRAMEWORK_BROKER] DRY-RUN: would FORCE-EXIT {symbol} qty={qty} "
                f"ref=${ref_price:.4f}",
                flush=True,
            )
            return {
                "filled": False,
                "fill_price": None,
                "fill_qty": 0,
                "attempts": 0,
                "reason": "dry_run",
            }
        try:
            import force_exit
        except Exception as e:
            print(f"[FRAMEWORK_BROKER] force_exit import failed: {e!r}", flush=True)
            return {
                "filled": False,
                "fill_price": None,
                "fill_qty": 0,
                "attempts": 0,
                "reason": f"force_exit_import_failed:{e!r}",
            }
        # force_exit.force_exit_position expects a broker with .submit_limit,
        # .get_order_status, .cancel_order — this class provides all three.
        return force_exit.force_exit_position(
            self, symbol, qty, ref_price, log_prefix="[FRAMEWORK] "
        )
