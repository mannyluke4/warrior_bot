"""
epl_framework.py — Extended Play List (EPL) Framework.

When SQ hits 2R target, the stock "graduates" to the EPL watchlist.
Independent strategies (registered via StrategyRegistry) then watch
graduated stocks for re-entry setups with their own entries/stops/exits.

Framework only — no actual strategies. Strategies plug in via EPLStrategy ABC.
Gated: WB_EPL_ENABLED=0 by default.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional


# ── Env vars ─────────────────────────────────────────────────────────

EPL_ENABLED = os.getenv("WB_EPL_ENABLED", "0") == "1"
EPL_MAX_STOCKS = int(os.getenv("WB_EPL_MAX_STOCKS", "5"))
EPL_EXPIRY_MINUTES = int(os.getenv("WB_EPL_EXPIRY_MINUTES", "60"))
EPL_MIN_GRADUATION_R = float(os.getenv("WB_EPL_MIN_GRADUATION_R", "2.0"))
EPL_SQ_PRIORITY = os.getenv("WB_EPL_SQ_PRIORITY", "1") == "1"
EPL_COOLDOWN_BARS = int(os.getenv("WB_EPL_COOLDOWN_BARS", "3"))
EPL_MAX_TRADES_PER_GRAD = int(os.getenv("WB_EPL_MAX_TRADES_PER_GRAD", "3"))
EPL_MAX_NOTIONAL = float(os.getenv("WB_EPL_MAX_NOTIONAL",
                                    os.getenv("WB_MAX_NOTIONAL", "50000")))
EPL_MAX_LOSS_SESSION = float(os.getenv("WB_EPL_MAX_LOSS_SESSION", "1000"))


# ── Data classes ─────────────────────────────────────────────────────

@dataclass
class GraduationContext:
    symbol: str
    graduation_time: datetime
    graduation_price: float
    sq_entry_price: float
    sq_stop_price: float
    hod_at_graduation: float
    vwap_at_graduation: float
    pm_high: float
    avg_volume_at_graduation: float
    sq_trade_count: int
    r_value: float


@dataclass
class EntrySignal:
    symbol: str
    strategy: str
    entry_price: float
    stop_price: float
    target_price: Optional[float]
    position_size_pct: float
    reason: str
    confidence: float


@dataclass
class ExitSignal:
    symbol: str
    strategy: str
    exit_price: float
    exit_reason: str
    exit_pct: float = 1.0


# ── Strategy ABC ─────────────────────────────────────────────────────

class EPLStrategy(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def priority(self) -> int: ...

    @abstractmethod
    def on_graduation(self, ctx: GraduationContext) -> None: ...

    @abstractmethod
    def on_expiry(self, symbol: str) -> None: ...

    @abstractmethod
    def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]: ...

    @abstractmethod
    def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]: ...

    @abstractmethod
    def manage_exit(self, symbol: str, price: float, bar: Optional[dict]) -> Optional[ExitSignal]: ...

    @abstractmethod
    def reset(self, symbol: str) -> None: ...


# ── EPL Watchlist ────────────────────────────────────────────────────

class EPLWatchlist:
    def __init__(self, max_stocks: int = EPL_MAX_STOCKS,
                 expiry_minutes: int = EPL_EXPIRY_MINUTES):
        self._graduated: Dict[str, GraduationContext] = {}
        self._graduation_times: Dict[str, datetime] = {}
        self.max_stocks = max_stocks
        self.expiry_minutes = expiry_minutes

    def add(self, ctx: GraduationContext) -> None:
        if ctx.symbol in self._graduated:
            # Re-graduation: update context
            self._graduated[ctx.symbol] = ctx
            self._graduation_times[ctx.symbol] = ctx.graduation_time
            return
        # Evict oldest if at capacity
        if len(self._graduated) >= self.max_stocks:
            oldest_sym = min(self._graduation_times, key=self._graduation_times.get)
            self.remove(oldest_sym)
        self._graduated[ctx.symbol] = ctx
        self._graduation_times[ctx.symbol] = ctx.graduation_time

    def remove(self, symbol: str) -> None:
        self._graduated.pop(symbol, None)
        self._graduation_times.pop(symbol, None)

    def is_graduated(self, symbol: str) -> bool:
        return symbol in self._graduated

    def get_context(self, symbol: str) -> Optional[GraduationContext]:
        return self._graduated.get(symbol)

    def check_expiry(self, current_time: datetime) -> List[str]:
        expired = []
        cutoff = current_time - timedelta(minutes=self.expiry_minutes)
        for sym, grad_time in list(self._graduation_times.items()):
            if grad_time <= cutoff:
                expired.append(sym)
        return expired

    @property
    def symbols(self) -> List[str]:
        return list(self._graduated.keys())

    def clear(self) -> None:
        self._graduated.clear()
        self._graduation_times.clear()


# ── Strategy Registry ────────────────────────────────────────────────

class StrategyRegistry:
    def __init__(self):
        self._strategies: List[EPLStrategy] = []

    def register(self, strategy: EPLStrategy) -> None:
        self._strategies.append(strategy)
        self._strategies.sort(key=lambda s: s.priority, reverse=True)

    def notify_graduation(self, ctx: GraduationContext) -> None:
        for s in self._strategies:
            s.on_graduation(ctx)

    def notify_expiry(self, symbol: str) -> None:
        for s in self._strategies:
            s.on_expiry(symbol)

    def collect_entry_signals(self, symbol: str, bar: Optional[dict] = None,
                              tick_price: Optional[float] = None,
                              tick_size: Optional[int] = None) -> List[EntrySignal]:
        signals = []
        for s in self._strategies:
            sig = None
            if bar is not None:
                sig = s.on_bar(symbol, bar)
            if sig is None and tick_price is not None:
                sig = s.on_tick(symbol, tick_price, tick_size or 0)
            if sig is not None:
                signals.append(sig)
        signals.sort(key=lambda s: s.confidence, reverse=True)
        return signals

    def get_strategy(self, name: str) -> Optional[EPLStrategy]:
        for s in self._strategies:
            if s.name == name:
                return s
        return None

    def reset_all(self, symbol: str) -> None:
        for s in self._strategies:
            s.reset(symbol)

    @property
    def strategy_count(self) -> int:
        return len(self._strategies)


# ── Position Arbitrator ──────────────────────────────────────────────

class PositionArbitrator:
    def __init__(self, registry: StrategyRegistry, watchlist: EPLWatchlist):
        self._registry = registry
        self._watchlist = watchlist
        self._epl_session_pnl: float = 0.0
        self._epl_trade_count: Dict[str, int] = {}
        self._cooldown_until: Dict[str, datetime] = {}

    def can_epl_enter(self, symbol: str, sq_state: str,
                      has_open_position: bool, current_time: datetime) -> bool:
        if not EPL_ENABLED:
            return False
        if not self._watchlist.is_graduated(symbol):
            return False
        if has_open_position:
            return False
        if EPL_SQ_PRIORITY and sq_state in ("PRIMED", "ARMED"):
            return False
        if symbol in self._cooldown_until and current_time < self._cooldown_until[symbol]:
            return False
        if self.session_loss_cap_hit:
            return False
        if self._epl_trade_count.get(symbol, 0) >= EPL_MAX_TRADES_PER_GRAD:
            return False
        return True

    def get_best_signal(self, signals: List[EntrySignal]) -> Optional[EntrySignal]:
        if not signals:
            return None
        return signals[0]  # Already sorted by confidence

    def record_epl_trade_result(self, symbol: str, pnl: float) -> None:
        self._epl_session_pnl += pnl
        self._epl_trade_count[symbol] = self._epl_trade_count.get(symbol, 0) + 1

    def set_cooldown(self, symbol: str, current_time: datetime,
                     cooldown_seconds: int = EPL_COOLDOWN_BARS * 60) -> None:
        self._cooldown_until[symbol] = current_time + timedelta(seconds=cooldown_seconds)

    @property
    def session_loss_cap_hit(self) -> bool:
        return self._epl_session_pnl <= -EPL_MAX_LOSS_SESSION

    @property
    def session_pnl(self) -> float:
        return self._epl_session_pnl

    def reset_session(self) -> None:
        self._epl_session_pnl = 0.0
        self._epl_trade_count.clear()
        self._cooldown_until.clear()
