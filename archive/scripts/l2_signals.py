"""
l2_signals.py — Level 2 (order book) signal detector

Processes L2 snapshots (top-of-book bid/ask levels) and detects:
  A. Order book imbalance (bid vs ask dominance)
  B. Bid stacking (large orders accumulating at price levels)
  C. Large order detection (sudden iceberg orders)
  D. Spread + liquidity (ask thinning, wide spread)

Used by both the backtester (Databento historical) and live bot (IBKR feed).
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class L2Snapshot:
    """Single snapshot of the order book (top N levels)."""
    timestamp: datetime
    symbol: str
    bids: list[tuple[float, int]]   # [(price, size), ...] best bid first
    asks: list[tuple[float, int]]   # [(price, size), ...] best ask first


@dataclass
class L2Signal:
    """A detected L2 signal with context."""
    name: str        # e.g. "L2_BID_STACK", "L2_IMBALANCE_BULL"
    detail: str      # human-readable context
    strength: float  # 0.0 to 1.0 normalized confidence


class L2SignalDetector:
    """
    Maintains per-symbol rolling L2 state.
    On each snapshot, computes imbalance, stacking, large orders, spread.
    """

    def __init__(self):
        # Thresholds from env (with sensible defaults from Ross Cameron observations)
        self.imbalance_bull = float(os.getenv("WB_L2_IMBALANCE_BULL", "0.65"))
        self.imbalance_bear = float(os.getenv("WB_L2_IMBALANCE_BEAR", "0.35"))
        self.stack_multiplier = float(os.getenv("WB_L2_STACK_MULTIPLIER", "3.0"))
        self.spread_warn_pct = float(os.getenv("WB_L2_SPREAD_WARN", "1.0"))
        self.large_order_multiplier = 5.0   # sudden 5x jump at a level
        self.large_order_min_size = 10_000  # minimum absolute shares to qualify

        # Per-symbol state: symbol -> _SymbolL2State
        self._states: dict[str, _SymbolL2State] = {}

    def on_snapshot(self, snap: L2Snapshot):
        """Process a new L2 snapshot. Updates internal state + signals."""
        state = self._states.get(snap.symbol)
        if state is None:
            state = _SymbolL2State()
            self._states[snap.symbol] = state
        state.update(snap, self)

    def get_state(self, symbol: str) -> Optional[dict]:
        """
        Return the current L2 state dict for a symbol, or None if no data.
        This is what micro_pullback.py consumes for scoring.
        """
        state = self._states.get(symbol)
        if state is None:
            return None
        return state.to_dict()

    def reset(self, symbol: str):
        """Clear L2 state for a symbol."""
        self._states.pop(symbol, None)


class _SymbolL2State:
    """Internal per-symbol L2 tracking."""

    def __init__(self):
        # Rolling imbalance history (last 10 snapshots)
        self.imbalance_history: deque[float] = deque(maxlen=10)
        self.prev_bids: list[tuple[float, int]] = []
        self.prev_asks: list[tuple[float, int]] = []

        # Current computed values
        self.imbalance: float = 0.5
        self.imbalance_trend: str = "flat"  # "rising", "falling", "flat"
        self.bid_stacking: bool = False
        self.bid_stack_levels: list[tuple[float, int]] = []  # (price, size) of stacked levels
        self.large_bid: bool = False
        self.large_ask: bool = False
        self.spread_pct: float = 0.0
        self.ask_thinning: bool = False
        self.signals: list[L2Signal] = []

        # Bid stack persistence tracking
        self._stack_persist: dict[float, int] = {}  # price -> consecutive snapshot count

    def update(self, snap: L2Snapshot, det: L2SignalDetector):
        """Recompute all signals from a new snapshot."""
        self.signals = []
        bids = snap.bids
        asks = snap.asks

        if not bids or not asks:
            return

        # --- A. Order Book Imbalance ---
        total_bid = sum(size for _, size in bids)
        total_ask = sum(size for _, size in asks)
        total = total_bid + total_ask

        if total > 0:
            self.imbalance = total_bid / total
        else:
            self.imbalance = 0.5

        self.imbalance_history.append(self.imbalance)

        # Trend: compare first half vs second half of history
        if len(self.imbalance_history) >= 4:
            history = list(self.imbalance_history)
            mid = len(history) // 2
            first_avg = sum(history[:mid]) / mid
            second_avg = sum(history[mid:]) / (len(history) - mid)
            diff = second_avg - first_avg
            if diff > 0.05:
                self.imbalance_trend = "rising"
            elif diff < -0.05:
                self.imbalance_trend = "falling"
            else:
                self.imbalance_trend = "flat"
        else:
            self.imbalance_trend = "flat"

        if self.imbalance > det.imbalance_bull:
            self.signals.append(L2Signal(
                "L2_IMBALANCE_BULL",
                f"bid/total={self.imbalance:.2f} trend={self.imbalance_trend}",
                min(1.0, (self.imbalance - 0.5) * 4),  # scale 0.5-0.75 → 0-1
            ))

        if self.imbalance < det.imbalance_bear:
            self.signals.append(L2Signal(
                "L2_IMBALANCE_BEAR",
                f"bid/total={self.imbalance:.2f} trend={self.imbalance_trend}",
                min(1.0, (0.5 - self.imbalance) * 4),
            ))

        # --- B. Bid Stacking ---
        self.bid_stacking = False
        self.bid_stack_levels = []
        new_persist = {}

        if bids and total_bid > 0:
            avg_level_size = total_bid / max(1, len(bids))
            best_bid = bids[0][0]

            for price, size in bids:
                if size > avg_level_size * det.stack_multiplier:
                    # Track persistence
                    prev_count = self._stack_persist.get(price, 0)
                    new_persist[price] = prev_count + 1

                    # Only flag stacking at or near current price (within 0.5%)
                    if best_bid > 0 and price >= best_bid * 0.995:
                        self.bid_stacking = True
                        self.bid_stack_levels.append((price, size))

            if self.bid_stacking:
                # Persistent stacking (5+ snapshots) is stronger
                max_persist = max(
                    (new_persist.get(p, 0) for p, _ in self.bid_stack_levels),
                    default=0,
                )
                strength = min(1.0, max_persist / 10.0)  # ramp to full at 10 snapshots
                self.signals.append(L2Signal(
                    "L2_BID_STACK",
                    f"{len(self.bid_stack_levels)} levels stacked, persist={max_persist}",
                    max(0.3, strength),  # minimum 0.3 if detected at all
                ))

        self._stack_persist = new_persist

        # --- C. Large Order Detection ---
        self.large_bid = False
        self.large_ask = False

        if self.prev_bids:
            prev_bid_map = {p: s for p, s in self.prev_bids}
            for price, size in bids:
                prev_size = prev_bid_map.get(price, 0)
                if (
                    prev_size > 0
                    and size >= prev_size * det.large_order_multiplier
                    and size >= det.large_order_min_size
                ):
                    self.large_bid = True
                    self.signals.append(L2Signal(
                        "L2_LARGE_BID",
                        f"@{price:.2f} size={size:,} (was {prev_size:,})",
                        min(1.0, size / 50_000),
                    ))
                    break  # one is enough

        if self.prev_asks:
            prev_ask_map = {p: s for p, s in self.prev_asks}
            for price, size in asks:
                prev_size = prev_ask_map.get(price, 0)
                if (
                    prev_size > 0
                    and size >= prev_size * det.large_order_multiplier
                    and size >= det.large_order_min_size
                ):
                    self.large_ask = True
                    self.signals.append(L2Signal(
                        "L2_LARGE_ASK",
                        f"@{price:.2f} size={size:,} (was {prev_size:,})",
                        min(1.0, size / 50_000),
                    ))
                    break

        # --- D. Spread + Liquidity ---
        best_bid_price = bids[0][0]
        best_ask_price = asks[0][0]

        if best_bid_price > 0:
            spread = best_ask_price - best_bid_price
            self.spread_pct = (spread / best_bid_price) * 100
        else:
            self.spread_pct = 0.0

        if self.spread_pct > det.spread_warn_pct:
            self.signals.append(L2Signal(
                "L2_WIDE_SPREAD",
                f"spread={self.spread_pct:.2f}%",
                min(1.0, self.spread_pct / 3.0),
            ))

        # Ask thinning: ask depth near price < 50% of bid depth near price
        # "Near price" = within 0.5% of best bid
        self.ask_thinning = False
        if best_bid_price > 0:
            near_threshold = best_bid_price * 1.005
            bid_depth_near = sum(s for p, s in bids if p >= best_bid_price * 0.995)
            ask_depth_near = sum(s for p, s in asks if p <= near_threshold)

            if bid_depth_near > 0 and ask_depth_near < bid_depth_near * 0.5:
                self.ask_thinning = True
                self.signals.append(L2Signal(
                    "L2_THIN_ASK",
                    f"ask_near={ask_depth_near:,} vs bid_near={bid_depth_near:,}",
                    min(1.0, 1.0 - (ask_depth_near / max(1, bid_depth_near))),
                ))

        # Store for next snapshot comparison
        self.prev_bids = list(bids)
        self.prev_asks = list(asks)

    def to_dict(self) -> dict:
        """Export current state as a dict for scoring consumption."""
        return {
            "imbalance": self.imbalance,
            "imbalance_trend": self.imbalance_trend,
            "bid_stacking": self.bid_stacking,
            "bid_stack_levels": self.bid_stack_levels,
            "large_bid": self.large_bid,
            "large_ask": self.large_ask,
            "spread_pct": self.spread_pct,
            "ask_thinning": self.ask_thinning,
            "signals": list(self.signals),
        }


# ─────────────────────────────────────────────
# CLI: quick test with synthetic data
# ─────────────────────────────────────────────
if __name__ == "__main__":
    from datetime import timezone

    det = L2SignalDetector()

    # Simulate a bullish order book (heavy bids, thin asks)
    snap = L2Snapshot(
        timestamp=datetime.now(timezone.utc),
        symbol="TEST",
        bids=[
            (5.00, 50000),
            (4.99, 30000),
            (4.98, 20000),
            (4.97, 15000),
            (4.96, 10000),
        ],
        asks=[
            (5.01, 5000),
            (5.02, 3000),
            (5.03, 2000),
            (5.04, 1000),
            (5.05, 500),
        ],
    )
    det.on_snapshot(snap)
    state = det.get_state("TEST")

    print("=== L2 Signal Detector Test ===")
    print(f"  Imbalance: {state['imbalance']:.2f} (trend: {state['imbalance_trend']})")
    print(f"  Bid stacking: {state['bid_stacking']}")
    print(f"  Large bid: {state['large_bid']}")
    print(f"  Large ask: {state['large_ask']}")
    print(f"  Spread: {state['spread_pct']:.2f}%")
    print(f"  Ask thinning: {state['ask_thinning']}")
    print(f"  Signals: {[s.name for s in state['signals']]}")

    # Feed a second snapshot with a large bid appearing
    snap2 = L2Snapshot(
        timestamp=datetime.now(timezone.utc),
        symbol="TEST",
        bids=[
            (5.00, 250000),   # suddenly 5x at best bid
            (4.99, 30000),
            (4.98, 20000),
            (4.97, 15000),
            (4.96, 10000),
        ],
        asks=[
            (5.01, 3000),     # asks getting even thinner
            (5.02, 2000),
            (5.03, 1000),
            (5.04, 500),
            (5.05, 200),
        ],
    )
    det.on_snapshot(snap2)
    state2 = det.get_state("TEST")

    print("\n=== After Large Bid Snapshot ===")
    print(f"  Imbalance: {state2['imbalance']:.2f} (trend: {state2['imbalance_trend']})")
    print(f"  Bid stacking: {state2['bid_stacking']}")
    print(f"  Large bid: {state2['large_bid']}")
    print(f"  Ask thinning: {state2['ask_thinning']}")
    print(f"  Signals: {[s.name for s in state2['signals']]}")
