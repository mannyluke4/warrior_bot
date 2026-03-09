"""
Session Manager — Intraday Kill Switch

Tracks session-level P&L across multiple stock simulations within a single
trading day. Implements three protective rules:

1. DAILY MAX LOSS: Hard cap at -$2,000. Stop all trading for the day.
2. GIVE-BACK RULE: If session peak P&L was >= +$1,000 and current P&L
   drops to <= 50% of peak, stop for the day. Protects winning days.
3. CONSECUTIVE LOSS RULE: After 3 consecutive losing sims (net P&L < 0
   on the sim), stop for the day.

Usage:
    session = SessionManager()

    for stock in today_candidates:
        if session.should_stop():
            print(f"KILL SWITCH: {session.stop_reason}")
            break

        # Run simulation...
        sim_pnl = run_sim(stock)
        session.record_sim(stock.symbol, sim_pnl)

    session.summary()
"""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass
class SessionManager:
    """Track session-level P&L and enforce kill switch rules."""

    # Configurable thresholds
    max_daily_loss: float = -2000.0          # Rule 1: hard floor
    giveback_threshold: float = 1000.0       # Rule 2: only activates above this peak
    giveback_pct: float = 0.50               # Rule 2: stop if P&L drops to this % of peak
    max_consecutive_losses: int = 3          # Rule 3: consecutive losing sims

    # State
    session_pnl: float = 0.0
    peak_pnl: float = 0.0
    consecutive_losses: int = 0
    sim_results: List[Tuple[str, float]] = field(default_factory=list)
    stopped: bool = False
    stop_reason: str = ""

    def record_sim(self, symbol: str, pnl: float):
        """Record a completed simulation's P&L."""
        self.sim_results.append((symbol, pnl))
        self.session_pnl += pnl

        # Update peak
        if self.session_pnl > self.peak_pnl:
            self.peak_pnl = self.session_pnl

        # Track consecutive losses (sim-level, not trade-level)
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # Check rules after recording
        self._check_rules()

    def _check_rules(self):
        """Evaluate all three kill switch rules."""
        if self.stopped:
            return

        # Rule 1: Daily max loss
        if self.session_pnl <= self.max_daily_loss:
            self.stopped = True
            self.stop_reason = (
                f"DAILY MAX LOSS: session P&L ${self.session_pnl:+,.0f} "
                f"hit floor of ${self.max_daily_loss:+,.0f}"
            )
            return

        # Rule 2: Give-back rule (only if we were meaningfully green)
        if self.peak_pnl >= self.giveback_threshold:
            giveback_floor = self.peak_pnl * self.giveback_pct
            if self.session_pnl <= giveback_floor:
                self.stopped = True
                self.stop_reason = (
                    f"GIVE-BACK: peak was ${self.peak_pnl:+,.0f}, "
                    f"current ${self.session_pnl:+,.0f} "
                    f"(<= {self.giveback_pct:.0%} of peak)"
                )
                return

        # Rule 3: Consecutive losses
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.stopped = True
            self.stop_reason = (
                f"CONSECUTIVE LOSSES: {self.consecutive_losses} losing sims in a row"
            )
            return

    def should_stop(self) -> bool:
        """Check if the kill switch has fired."""
        return self.stopped

    def summary(self) -> str:
        """Return a summary string for the session."""
        n_sims = len(self.sim_results)
        n_winners = sum(1 for _, p in self.sim_results if p > 0)
        n_losers = sum(1 for _, p in self.sim_results if p < 0)
        n_flat = sum(1 for _, p in self.sim_results if p == 0)

        lines = [
            f"Session P&L: ${self.session_pnl:+,.0f} "
            f"(peak: ${self.peak_pnl:+,.0f})",
            f"Sims: {n_sims} ({n_winners}W / {n_losers}L / {n_flat}F)",
        ]
        if self.stopped:
            lines.append(f"KILL SWITCH FIRED: {self.stop_reason}")

        return " | ".join(lines)
