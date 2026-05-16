"""Risk manager — per-strategy and portfolio kill switches.

Wave 1, Agent E, deliverable 2 (DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3).

Kill switches per design §5.4:
  - per-strategy daily loss %
  - per-strategy drawdown % (from session-equity peak)
  - per-strategy consecutive losses
  - portfolio daily loss %

State is persisted to disk using the per-PID tmp + atomic rename pattern
from wb_persistence.py — safe under concurrent writers (Setup A + Setup B).

Defensive contract: all methods catch IO errors and continue. A persistence
failure must never break the bot's main loop.
"""
from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import pytz

ET = pytz.timezone("US/Eastern")

_DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent / "framework_state"
_DEFAULT_STATE_PATH = _DEFAULT_STATE_DIR / "risk_state.json"


@dataclass
class StrategyRiskState:
    """Per-strategy mutable risk accounting."""

    daily_pnl: float = 0.0
    session_equity_peak: float = 0.0
    consecutive_losses: int = 0
    last_entry_equity: float = 0.0
    killed: bool = False
    kill_reason: Optional[str] = None
    trade_count: int = 0


@dataclass
class RiskConfig:
    per_strategy_daily_loss_pct: float = 3.0
    per_strategy_drawdown_pct: float = 5.0
    portfolio_daily_loss_pct: float = 5.0
    consecutive_losses_kill: int = 5


class RiskManager:
    """Kill-switch manager. Per-strategy and portfolio-level.

    Construction is cheap. State loads from disk lazily on first access
    and persists after every mutation.
    """

    def __init__(
        self,
        per_strategy_daily_loss_pct: float = 3.0,
        per_strategy_drawdown_pct: float = 5.0,
        portfolio_daily_loss_pct: float = 5.0,
        consecutive_losses_kill: int = 5,
        state_path: Optional[Path | str] = None,
    ) -> None:
        self.config = RiskConfig(
            per_strategy_daily_loss_pct=per_strategy_daily_loss_pct,
            per_strategy_drawdown_pct=per_strategy_drawdown_pct,
            portfolio_daily_loss_pct=portfolio_daily_loss_pct,
            consecutive_losses_kill=consecutive_losses_kill,
        )
        self.state_path = Path(state_path) if state_path else _DEFAULT_STATE_PATH
        self._lock = threading.Lock()
        self._strategies: dict[str, StrategyRiskState] = {}
        self._portfolio_daily_pnl: float = 0.0
        self._portfolio_peak_equity: float = 0.0
        self._session_date: str = self._today_str()
        self._load()

    # ------------------------------------------------------------------ #
    # Disk IO (per-PID tmp + atomic rename — mirrors wb_persistence.py)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _today_str() -> str:
        return datetime.now(ET).strftime("%Y-%m-%d")

    def _load(self) -> None:
        if not self.state_path.exists():
            return
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, json.JSONDecodeError):
            return
        try:
            self._session_date = data.get(
                "session_date", self._today_str()
            )
            self._portfolio_daily_pnl = float(
                data.get("portfolio_daily_pnl", 0.0)
            )
            self._portfolio_peak_equity = float(
                data.get("portfolio_peak_equity", 0.0)
            )
            strategies = data.get("strategies", {})
            for name, s in strategies.items():
                self._strategies[name] = StrategyRiskState(
                    daily_pnl=float(s.get("daily_pnl", 0.0)),
                    session_equity_peak=float(
                        s.get("session_equity_peak", 0.0)
                    ),
                    consecutive_losses=int(
                        s.get("consecutive_losses", 0)
                    ),
                    last_entry_equity=float(
                        s.get("last_entry_equity", 0.0)
                    ),
                    killed=bool(s.get("killed", False)),
                    kill_reason=s.get("kill_reason"),
                    trade_count=int(s.get("trade_count", 0)),
                )
        except (TypeError, ValueError):
            # Corrupt fields — start fresh rather than crash.
            self._strategies = {}
            self._portfolio_daily_pnl = 0.0
            self._portfolio_peak_equity = 0.0

    def _persist(self) -> None:
        """Per-PID tmp + atomic rename. Best-effort — never raises."""
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_date": self._session_date,
                "portfolio_daily_pnl": self._portfolio_daily_pnl,
                "portfolio_peak_equity": self._portfolio_peak_equity,
                "strategies": {
                    name: asdict(s)
                    for name, s in self._strategies.items()
                },
                "updated_at": datetime.now(ET).isoformat(
                    timespec="seconds"
                ),
            }
            tmp = self.state_path.with_name(
                f"{self.state_path.stem}.{os.getpid()}.tmp"
            )
            tmp.write_text(json.dumps(payload, indent=2))
            tmp.replace(self.state_path)
        except OSError as e:
            print(
                f"[RISK] persist failed: {e!r}", flush=True
            )

    # ------------------------------------------------------------------ #
    # State helpers
    # ------------------------------------------------------------------ #
    def _get_or_create(self, strategy_name: str) -> StrategyRiskState:
        if strategy_name not in self._strategies:
            self._strategies[strategy_name] = StrategyRiskState()
        return self._strategies[strategy_name]

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def record_trade(
        self,
        strategy_name: str,
        pnl: float,
        equity_at_entry: float,
    ) -> None:
        """Record a closed-trade P&L for `strategy_name`. Updates all
        relevant counters and persists state."""
        if not strategy_name:
            return
        try:
            pnl_f = float(pnl)
            equity_f = float(equity_at_entry)
        except (TypeError, ValueError):
            return
        if not (math.isfinite(pnl_f) and math.isfinite(equity_f)):
            return

        with self._lock:
            # Daily rollover if calendar day changed since last write
            today = self._today_str()
            if today != self._session_date:
                self._reset_daily_locked()
                self._session_date = today

            s = self._get_or_create(strategy_name)
            s.daily_pnl += pnl_f
            s.trade_count += 1
            s.last_entry_equity = equity_f

            # Peak tracking — per-strategy peak is the peak post-trade
            # cumulative equity (entry equity + cumulative daily pnl).
            post_equity = equity_f + s.daily_pnl
            if post_equity > s.session_equity_peak:
                s.session_equity_peak = post_equity

            # Consecutive losses
            if pnl_f < 0:
                s.consecutive_losses += 1
            elif pnl_f > 0:
                s.consecutive_losses = 0
            # pnl == 0 → unchanged

            # Portfolio aggregation
            self._portfolio_daily_pnl += pnl_f
            portfolio_post = equity_f + self._portfolio_daily_pnl
            if portfolio_post > self._portfolio_peak_equity:
                self._portfolio_peak_equity = portfolio_post

            self._persist()

    def check_strategy_kill(
        self, strategy_name: str, current_equity: float
    ) -> bool:
        """Returns True iff any per-strategy kill switch is tripped."""
        if not strategy_name:
            return False
        try:
            eq = float(current_equity)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(eq) or eq <= 0:
            return False

        with self._lock:
            s = self._strategies.get(strategy_name)
            if s is None:
                return False
            if s.killed:
                return True

            # Daily loss
            if s.daily_pnl < 0:
                loss_pct = -s.daily_pnl / eq * 100.0
                if loss_pct >= self.config.per_strategy_daily_loss_pct:
                    s.killed = True
                    s.kill_reason = (
                        f"daily_loss_{loss_pct:.2f}%>="
                        f"{self.config.per_strategy_daily_loss_pct}%"
                    )
                    self._persist()
                    return True

            # Drawdown from peak
            if s.session_equity_peak > 0:
                current_strat_equity = eq + s.daily_pnl
                dd = (
                    s.session_equity_peak - current_strat_equity
                ) / s.session_equity_peak * 100.0
                if dd >= self.config.per_strategy_drawdown_pct:
                    s.killed = True
                    s.kill_reason = (
                        f"drawdown_{dd:.2f}%>="
                        f"{self.config.per_strategy_drawdown_pct}%"
                    )
                    self._persist()
                    return True

            # Consecutive losses
            if (
                s.consecutive_losses
                >= self.config.consecutive_losses_kill
            ):
                s.killed = True
                s.kill_reason = (
                    f"consecutive_losses_{s.consecutive_losses}>="
                    f"{self.config.consecutive_losses_kill}"
                )
                self._persist()
                return True

            return False

    def check_portfolio_kill(self, current_equity: float) -> bool:
        """Returns True iff the portfolio-wide daily loss limit is hit."""
        try:
            eq = float(current_equity)
        except (TypeError, ValueError):
            return False
        if not math.isfinite(eq) or eq <= 0:
            return False
        with self._lock:
            if self._portfolio_daily_pnl >= 0:
                return False
            loss_pct = -self._portfolio_daily_pnl / eq * 100.0
            return loss_pct >= self.config.portfolio_daily_loss_pct

    def reset_daily(self) -> None:
        """Clear daily counters. Call at session boundary."""
        with self._lock:
            self._reset_daily_locked()
            self._persist()

    def _reset_daily_locked(self) -> None:
        for s in self._strategies.values():
            s.daily_pnl = 0.0
            s.session_equity_peak = 0.0
            s.consecutive_losses = 0
            s.killed = False
            s.kill_reason = None
        self._portfolio_daily_pnl = 0.0
        self._portfolio_peak_equity = 0.0
        self._session_date = self._today_str()

    # ------------------------------------------------------------------ #
    # Introspection
    # ------------------------------------------------------------------ #
    def get_strategy_state(
        self, strategy_name: str
    ) -> Optional[StrategyRiskState]:
        with self._lock:
            s = self._strategies.get(strategy_name)
            if s is None:
                return None
            # Return a copy to keep callers from mutating internals.
            return StrategyRiskState(**asdict(s))

    def debug_state(self) -> dict:
        with self._lock:
            return {
                "session_date": self._session_date,
                "portfolio_daily_pnl": self._portfolio_daily_pnl,
                "portfolio_peak_equity": self._portfolio_peak_equity,
                "strategies": {
                    name: asdict(s)
                    for name, s in self._strategies.items()
                },
                "config": asdict(self.config),
                "state_path": str(self.state_path),
            }


__all__ = ["RiskManager", "RiskConfig", "StrategyRiskState"]
