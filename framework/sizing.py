"""Position sizing — Half-Kelly and Tiered ladder.

Wave 1, Agent E: ``HalfKellySizer`` (half-Kelly with bar-volume cap).
Wave 4, Phase C1: ``TieredSizer`` (9-tier risk ladder per
``DIRECTIVE_2026-05-17_SIZING_SCHEDULE.md``).

Half-Kelly formula:
    shares = (equity * risk_per_trade_pct / 2) / abs(entry_price - stop_price)

Then capped at:
    max_bar_volume_pct * recent_bar_volume / entry_price

The cap implements the "5% of bar volume" participation rule from
research_backtest_infrastructure.md §3 (realistic fill modeling — queue
position uncertainty discount 20-40%). 5% is the default; configurable.

Defensive contract: any invalid input (zero/negative equity, zero R, zero
or negative entry, non-finite values) returns 0 shares. Never raises —
sizing must not crash the bot.

Public API:
    HalfKellySizer(risk_per_trade_pct=1.0, max_bar_volume_pct=0.05)
    sizer.size_position(equity, entry_price, stop_price, recent_bar_volume)
        -> int  # share count, always >= 0

    TieredSizer(initial_tier=1, tier_lock=False, auto_advance=True,
                state_path=Path("framework_state/tier_state.json"),
                config_path=Path("framework/sizing_tiers.yaml"))
    sizer.compute_risk(equity, signal=None) -> float
    sizer.on_session_close(session_date, portfolio_returns, equity, ...) -> dict
"""
from __future__ import annotations

import json
import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Protocol

try:  # PyYAML is in the project's normal dep set, but we degrade gracefully.
    import yaml  # type: ignore[import-untyped]
except ImportError:  # pragma: no cover - exercised only in stripped envs
    yaml = None  # type: ignore[assignment]

log = logging.getLogger("framework.sizing")


# ---------------------------------------------------------------------------
# Sizer protocol — shared by HalfKellySizer + TieredSizer + fixed_dollar
# ---------------------------------------------------------------------------


class SizerProtocol(Protocol):
    """Common interface used by ``backtest.portfolio_backtest``.

    Both HalfKellySizer (size_position) and TieredSizer (compute_risk) can
    answer "how much dollar risk for this trade?" — different signatures
    but the portfolio engine adapts.
    """

    def compute_risk(self, equity: float, signal: Optional[Any] = None) -> float:
        ...


# ---------------------------------------------------------------------------
# HalfKellySizer — Wave 1 (unchanged below this line; bug fix is Wave 5 P1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HalfKellySizer:
    """Half-Kelly position sizer with bar-volume participation cap.

    Attributes
    ----------
    risk_per_trade_pct: float
        Percent of equity to risk per trade, e.g. 1.0 = 1%.
    max_bar_volume_pct: float
        Cap on shares as fraction of recent_bar_volume. Default 0.05 (5%).
    """

    risk_per_trade_pct: float = 1.0
    max_bar_volume_pct: float = 0.05

    @staticmethod
    def _is_finite_positive(x: float) -> bool:
        try:
            return math.isfinite(x) and x > 0
        except (TypeError, ValueError):
            return False

    def size_position(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        recent_bar_volume: float,
    ) -> int:
        """Compute share count for a trade.

        Returns 0 for any invalid input. Never raises.
        """
        # Validate scalars
        if not self._is_finite_positive(equity):
            return 0
        if not self._is_finite_positive(entry_price):
            return 0
        try:
            if not math.isfinite(stop_price):
                return 0
        except (TypeError, ValueError):
            return 0
        if recent_bar_volume is None:
            return 0
        try:
            if not math.isfinite(float(recent_bar_volume)):
                return 0
        except (TypeError, ValueError):
            return 0
        if recent_bar_volume < 0:
            return 0

        # Validate config
        if self.risk_per_trade_pct <= 0:
            return 0
        if self.max_bar_volume_pct < 0:
            return 0

        # Per-share risk (R)
        r_per_share = abs(entry_price - stop_price)
        if r_per_share <= 0:
            return 0

        # Half-Kelly notional risk
        risk_dollars = equity * (self.risk_per_trade_pct / 100.0) * 0.5
        raw_shares = risk_dollars / r_per_share
        if not math.isfinite(raw_shares) or raw_shares <= 0:
            return 0

        # Bar-volume participation cap.
        # Per directive: shares cap = max_bar_volume_pct * recent_bar_volume
        #                              / entry_price
        # (This treats `recent_bar_volume` as bar dollar-volume when the user
        # supplies dollar volume; or as share volume when shares are supplied.
        # The formula is taken verbatim from the directive — callers pass the
        # measure consistent with how max_bar_volume_pct is calibrated.)
        if recent_bar_volume == 0 or self.max_bar_volume_pct == 0:
            volume_cap_shares = 0.0
        else:
            volume_cap_shares = (
                self.max_bar_volume_pct * recent_bar_volume / entry_price
            )

        shares = min(raw_shares, volume_cap_shares)
        shares_int = int(math.floor(shares))
        return max(shares_int, 0)

    def compute_risk(self, equity: float, signal: Optional[Any] = None) -> float:
        """SizerProtocol shim — returns the half-Kelly dollar risk envelope.

        Mirrors the math inside size_position: equity * pct/100 * 0.5.
        Useful when the portfolio engine wants the risk budget separately
        from share count.
        """
        if not self._is_finite_positive(equity):
            return 0.0
        if self.risk_per_trade_pct <= 0:
            return 0.0
        return float(equity * (self.risk_per_trade_pct / 100.0) * 0.5)


# ---------------------------------------------------------------------------
# TieredSizer — Wave 4 Phase C1
# ---------------------------------------------------------------------------


REPO = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = REPO / "framework" / "sizing_tiers.yaml"
DEFAULT_STATE_PATH = REPO / "framework_state" / "tier_state.json"


@dataclass
class TierRow:
    """One row of the sizing ladder."""

    tier: int
    equity_floor: float
    risk_per_signal: float
    pct_per_trade: float
    combined_session_max: float


@dataclass
class TierState:
    """Persistable state for the TieredSizer.

    Persisted JSON shape::
        {
          "current_tier": 1,
          "tier_high_water_mark": 27500.0,    # peak equity since entering tier
          "days_in_tier": 12,                  # session-day count since tier set
          "last_advancement_date": "2026-06-04",
          "consecutive_at_next_floor": 0,
          "consecutive_losing_weeks": 0,
          "equity_history": [25000, ...],     # last 60 session-close equities
          "weekly_pnl": [12, -5, ...],        # last 12 ISO-week net P&Ls
          "current_iso_week": "2026-W23",     # bucket key for in-flight week
          "current_week_pnl": 0.0,            # running week P&L
          "current_tier_entry_equity": 25000  # equity when tier was entered
        }
    """

    current_tier: int = 1
    tier_high_water_mark: float = 0.0
    days_in_tier: int = 0
    last_advancement_date: Optional[str] = None  # ISO date or None
    consecutive_at_next_floor: int = 0
    consecutive_losing_weeks: int = 0
    equity_history: list[float] = field(default_factory=list)
    weekly_pnl: list[float] = field(default_factory=list)
    current_iso_week: Optional[str] = None
    current_week_pnl: float = 0.0
    current_tier_entry_equity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_tier": self.current_tier,
            "tier_high_water_mark": self.tier_high_water_mark,
            "days_in_tier": self.days_in_tier,
            "last_advancement_date": self.last_advancement_date,
            "consecutive_at_next_floor": self.consecutive_at_next_floor,
            "consecutive_losing_weeks": self.consecutive_losing_weeks,
            "equity_history": list(self.equity_history),
            "weekly_pnl": list(self.weekly_pnl),
            "current_iso_week": self.current_iso_week,
            "current_week_pnl": self.current_week_pnl,
            "current_tier_entry_equity": self.current_tier_entry_equity,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "TierState":
        return cls(
            current_tier=int(payload.get("current_tier", 1)),
            tier_high_water_mark=float(payload.get("tier_high_water_mark", 0.0)),
            days_in_tier=int(payload.get("days_in_tier", 0)),
            last_advancement_date=payload.get("last_advancement_date"),
            consecutive_at_next_floor=int(payload.get("consecutive_at_next_floor", 0)),
            consecutive_losing_weeks=int(payload.get("consecutive_losing_weeks", 0)),
            equity_history=[float(x) for x in payload.get("equity_history", [])],
            weekly_pnl=[float(x) for x in payload.get("weekly_pnl", [])],
            current_iso_week=payload.get("current_iso_week"),
            current_week_pnl=float(payload.get("current_week_pnl", 0.0)),
            current_tier_entry_equity=float(payload.get("current_tier_entry_equity", 0.0)),
        )


class TieredSizer:
    """9-tier risk ladder sizer (Wave 4 Phase C1).

    Returns ``risk_per_signal`` in dollars for the *current* tier. Tier
    transitions (advancement / retreat) happen at session boundaries via
    ``on_session_close`` — not on every signal — so a single backtest
    session sees one consistent risk dollars value across its trades.

    Parameters
    ----------
    initial_tier : int
        Tier to start at (1-9). Clamped into the configured range.
    tier_lock : bool
        If True, the sizer pins the current tier forever — gates are
        evaluated and logged but never applied. Used for Wave 4 paper
        (60-day Tier 1 lock per Decision 7).
    auto_advance : bool
        If False, gates are evaluated and logged but tier mutations
        require manual call to ``apply_pending_transition()``. Used as
        an alternative to tier_lock when ops wants visibility but not
        automation.
    state_path : Path
        Where to persist ``TierState`` JSON. Set to None to disable
        persistence (in-memory only — used by unit tests).
    config_path : Path
        Where to read the ladder YAML. Defaults to the repo's
        ``framework/sizing_tiers.yaml``.
    """

    def __init__(
        self,
        initial_tier: int = 1,
        tier_lock: bool = False,
        auto_advance: bool = True,
        state_path: Optional[Path] = DEFAULT_STATE_PATH,
        config_path: Path = DEFAULT_CONFIG_PATH,
    ) -> None:
        self.tier_lock = bool(tier_lock)
        self.auto_advance = bool(auto_advance)
        self.state_path = Path(state_path) if state_path is not None else None
        self.config_path = Path(config_path)

        self._tiers: list[TierRow] = []
        self._advancement_cfg: dict[str, Any] = {}
        self._retreat_cfg: dict[str, Any] = {}
        self._load_config()

        # Pending transition computed when auto_advance=False
        # Shape: {"action": "advance"|"retreat", "from": int, "to": int,
        #         "reason": str, "session_date": str}
        self.pending_transition: Optional[dict[str, Any]] = None
        # Last gate evaluation result (for diagnostics / reports)
        self.last_gate_eval: Optional[dict[str, Any]] = None

        # Hydrate state from disk, else seed fresh
        loaded = self._load_state()
        if loaded is not None:
            self.state = loaded
        else:
            clamped = max(1, min(int(initial_tier), len(self._tiers)))
            self.state = TierState(current_tier=clamped)

    # ------------------------------------------------------------------
    # Config + state I/O
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        if yaml is None:
            raise RuntimeError(
                "PyYAML is required for TieredSizer.  pip install pyyaml"
            )
        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        rows = data.get("tiers", [])
        if not rows:
            raise ValueError(f"sizing_tiers.yaml has no 'tiers' entries at {self.config_path}")
        self._tiers = sorted(
            (
                TierRow(
                    tier=int(r["tier"]),
                    equity_floor=float(r["equity_floor"]),
                    risk_per_signal=float(r["risk_per_signal"]),
                    pct_per_trade=float(r.get("pct_per_trade", 0.0)),
                    combined_session_max=float(r.get("combined_session_max", 0.0)),
                )
                for r in rows
            ),
            key=lambda x: x.tier,
        )
        self._advancement_cfg = data.get("advancement", {}) or {}
        self._retreat_cfg = data.get("retreat", {}) or {}

    def _load_state(self) -> Optional[TierState]:
        if self.state_path is None or not self.state_path.exists():
            return None
        try:
            payload = json.loads(self.state_path.read_text())
            return TierState.from_dict(payload)
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            log.warning("TieredSizer state load failed (%s); seeding fresh", exc)
            return None

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.state.to_dict(), indent=2, sort_keys=True))
        tmp.replace(self.state_path)

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    @property
    def current_tier(self) -> int:
        return self.state.current_tier

    @property
    def num_tiers(self) -> int:
        return len(self._tiers)

    def tier_row(self, tier: int) -> TierRow:
        idx = max(1, min(tier, len(self._tiers))) - 1
        return self._tiers[idx]

    def compute_risk(self, equity: float, signal: Optional[Any] = None) -> float:
        """Return dollar risk for the current tier.

        ``equity`` is accepted for SizerProtocol parity but the value used
        is the **tier's** risk-per-signal — not a percentage of equity.
        The tier IS the equity-aware abstraction; risk dollars are fixed
        within a tier and step up/down on session boundaries.
        """
        if not math.isfinite(float(equity)) or equity <= 0:
            return 0.0
        return float(self.tier_row(self.state.current_tier).risk_per_signal)

    def size(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        recent_bar_volume: float,
    ) -> tuple[int, float]:
        """Adapter matching ``backtest.portfolio_backtest.SizingMode.size``.

        Returns ``(qty, risk_dollars)`` so the bar-level engine can plug
        TieredSizer in wherever it used SizingMode.
        """
        per_share = abs(entry_price - stop_price)
        if per_share <= 0:
            return 0, 0.0
        risk_dollars = self.compute_risk(equity)
        if risk_dollars <= 0:
            return 0, 0.0
        qty = int(risk_dollars // per_share)
        return max(qty, 0), risk_dollars

    # ------------------------------------------------------------------
    # Tier transition machinery (called from session boundaries)
    # ------------------------------------------------------------------

    def on_session_close(
        self,
        session_date: date,
        equity: float,
        portfolio_returns: Optional[list[float]] = None,
    ) -> dict[str, Any]:
        """Update state at end of session and apply (or stage) a transition.

        Parameters
        ----------
        session_date : date
            The session that just closed.
        equity : float
            Combined portfolio equity at close.
        portfolio_returns : list[float] | None
            Trailing rolling-window per-session portfolio returns
            (most recent last). Caller may pass the full series — only
            the last `rolling_sharpe_window` entries are used.
            Returns are unitless (e.g. 0.01 = +1% on the session).

        Returns
        -------
        dict
            Diagnostic payload with the new tier, applied transition
            (or None), and the gate evaluation. Side-effect: persists
            state to disk.
        """
        # 1. Roll forward bookkeeping
        self.state.days_in_tier += 1
        self.state.equity_history.append(float(equity))
        if len(self.state.equity_history) > 120:
            self.state.equity_history = self.state.equity_history[-120:]
        # Track tier HWM
        if equity > self.state.tier_high_water_mark:
            self.state.tier_high_water_mark = float(equity)
        # If we just entered (HWM was 0), seed entry equity too
        if self.state.current_tier_entry_equity <= 0:
            self.state.current_tier_entry_equity = float(equity)

        # 2. Update weekly P&L bucket (Mon-Fri = ISO week)
        self._update_weekly_pnl(session_date, equity)

        # 3. Evaluate gates
        adv_eval = self._evaluate_advancement(session_date, equity, portfolio_returns)
        ret_eval = self._evaluate_retreat(session_date, equity, portfolio_returns)
        self.last_gate_eval = {
            "session_date": session_date.isoformat(),
            "tier_before": self.state.current_tier,
            "equity": equity,
            "advancement": adv_eval,
            "retreat": ret_eval,
        }

        applied_transition: Optional[dict[str, Any]] = None

        # 4. Retreat triggers fire before advancement (safety first)
        if ret_eval["fired"]:
            transition = {
                "action": "retreat",
                "from": self.state.current_tier,
                "to": max(1, self.state.current_tier - 1),
                "reason": ret_eval["reason"],
                "session_date": session_date.isoformat(),
            }
            applied_transition = self._maybe_apply(transition)
        elif adv_eval["gates_passed"]:
            transition = {
                "action": "advance",
                "from": self.state.current_tier,
                "to": min(len(self._tiers), self.state.current_tier + 1),
                "reason": "all_gates_passed",
                "session_date": session_date.isoformat(),
            }
            applied_transition = self._maybe_apply(transition)

        # 5. Reset per-day rolling counters that only count "consecutive"
        if not adv_eval["at_next_floor"]:
            self.state.consecutive_at_next_floor = 0

        # 6. Persist
        self._save_state()

        return {
            "tier": self.state.current_tier,
            "tier_hwm": self.state.tier_high_water_mark,
            "applied": applied_transition,
            "pending": self.pending_transition,
            "gates": self.last_gate_eval,
        }

    def _maybe_apply(self, transition: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Apply a transition if tier_lock=False AND auto_advance=True.

        If tier_lock=True, do nothing (log only).
        If auto_advance=False, stage as pending_transition.
        Else, mutate state and reset tier-scoped fields.
        """
        if self.tier_lock:
            log.info(
                "TieredSizer[tier_lock]: %s %d->%d suppressed (reason=%s)",
                transition["action"], transition["from"], transition["to"],
                transition["reason"],
            )
            self.pending_transition = transition
            return None
        if not self.auto_advance:
            log.info(
                "TieredSizer[auto_advance=False]: %s %d->%d staged (reason=%s)",
                transition["action"], transition["from"], transition["to"],
                transition["reason"],
            )
            self.pending_transition = transition
            return None
        self._mutate_to_tier(transition["to"], transition)
        self.pending_transition = None
        return transition

    def apply_pending_transition(self) -> Optional[dict[str, Any]]:
        """Manually apply the staged pending_transition.

        Returns the transition that was applied, or None if nothing staged
        or tier_lock=True (which always suppresses).
        """
        if self.tier_lock:
            log.warning("TieredSizer.apply_pending_transition: tier_lock=True; ignoring")
            return None
        if self.pending_transition is None:
            return None
        t = self.pending_transition
        self._mutate_to_tier(t["to"], t)
        self.pending_transition = None
        self._save_state()
        return t

    def _mutate_to_tier(self, new_tier: int, transition: dict[str, Any]) -> None:
        """Apply the actual tier change + reset tier-scoped state."""
        new_tier = max(1, min(int(new_tier), len(self._tiers)))
        if new_tier == self.state.current_tier:
            return
        old = self.state.current_tier
        self.state.current_tier = new_tier
        # Resetting tier HWM on transition is critical: retreat triggers
        # are anchored to the *current* tier's HWM, not all-time peak.
        # Without reset, an advance into tier 5 would inherit tier 4's HWM
        # and never qualify for a tier-5 retreat until equity surged past it.
        self.state.tier_high_water_mark = 0.0
        self.state.consecutive_at_next_floor = 0
        self.state.last_advancement_date = transition["session_date"]
        self.state.days_in_tier = 0
        self.state.current_tier_entry_equity = 0.0  # re-seeded next close
        log.info(
            "TieredSizer: applied %s %d->%d (reason=%s, date=%s)",
            transition["action"], old, new_tier, transition["reason"],
            transition["session_date"],
        )

    # ------------------------------------------------------------------
    # Advancement gate evaluation
    # ------------------------------------------------------------------

    def _evaluate_advancement(
        self,
        session_date: date,
        equity: float,
        portfolio_returns: Optional[list[float]],
    ) -> dict[str, Any]:
        """Run all 4 advancement gates per SIZING_SCHEDULE §3."""
        # If already at top tier, no advancement possible
        if self.state.current_tier >= len(self._tiers):
            return {
                "gates_passed": False, "at_next_floor": False,
                "gate1_consec_at_floor": False, "gate2_sharpe": False,
                "gate3_no_dd": False, "gate4_min_window": False,
                "reason": "already_top_tier",
            }

        next_tier = self.tier_row(self.state.current_tier + 1)
        required_sessions = int(self._advancement_cfg.get("consecutive_sessions_at_floor", 3))

        # Gate 1: equity ≥ next tier floor for ≥ N consecutive sessions
        at_floor = equity >= next_tier.equity_floor
        if at_floor:
            self.state.consecutive_at_next_floor += 1
        gate1 = self.state.consecutive_at_next_floor >= required_sessions

        # Gate 2: rolling 30-session Sharpe ≥ 1.0
        sharpe_window = int(self._advancement_cfg.get("rolling_sharpe_window", 30))
        sharpe_min = float(self._advancement_cfg.get("rolling_sharpe_min", 1.0))
        sharpe_val = self._rolling_sharpe(portfolio_returns or [], sharpe_window)
        gate2 = sharpe_val is not None and sharpe_val >= sharpe_min

        # Gate 3: current equity ≥ trailing 5-session avg (no active drawdown)
        dd_window = int(self._advancement_cfg.get("drawdown_check_window", 5))
        recent = self.state.equity_history[-(dd_window + 1):-1]  # exclude current
        if not recent:
            gate3 = False
            avg5 = None
        else:
            avg5 = sum(recent) / len(recent)
            gate3 = equity >= avg5

        # Gate 4: ≥14 days since last advancement
        min_days = int(self._advancement_cfg.get("min_days_between_advances", 14))
        if self.state.last_advancement_date is None:
            gate4 = True
            days_since = None
        else:
            try:
                last = date.fromisoformat(self.state.last_advancement_date)
                days_since = (session_date - last).days
                gate4 = days_since >= min_days
            except (TypeError, ValueError):
                gate4 = True
                days_since = None

        return {
            "gates_passed": bool(gate1 and gate2 and gate3 and gate4),
            "at_next_floor": at_floor,
            "gate1_consec_at_floor": bool(gate1),
            "gate1_required_sessions": required_sessions,
            "gate1_actual_consecutive": self.state.consecutive_at_next_floor,
            "gate2_sharpe": bool(gate2),
            "gate2_sharpe_value": sharpe_val,
            "gate3_no_dd": bool(gate3),
            "gate3_trailing_avg": avg5,
            "gate4_min_window": bool(gate4),
            "gate4_days_since_last": days_since,
            "next_tier_floor": next_tier.equity_floor,
        }

    # ------------------------------------------------------------------
    # Retreat trigger evaluation
    # ------------------------------------------------------------------

    def _evaluate_retreat(
        self,
        session_date: date,
        equity: float,
        portfolio_returns: Optional[list[float]],
    ) -> dict[str, Any]:
        """Any single retreat trigger fires a one-tier retreat."""
        # If at bottom tier, no further retreat (state stays put)
        if self.state.current_tier <= 1:
            return {
                "fired": False, "trigger_a_dd_from_hwm": False,
                "trigger_b_low_sharpe": False, "trigger_c_3_losing_weeks": False,
                "reason": "already_bottom_tier",
            }

        # Trigger A: equity drops X% from current tier HWM
        dd_pct = float(self._retreat_cfg.get("drawdown_from_hwm_pct", 0.15))
        if self.state.tier_high_water_mark > 0:
            dd_from_hwm = (self.state.tier_high_water_mark - equity) / self.state.tier_high_water_mark
        else:
            dd_from_hwm = 0.0
        trig_a = dd_from_hwm >= dd_pct

        # Trigger B: rolling 30-session Sharpe < 0.3
        sharpe_window = int(self._advancement_cfg.get("rolling_sharpe_window", 30))
        sharpe_floor = float(self._retreat_cfg.get("rolling_sharpe_floor", 0.3))
        sharpe_val = self._rolling_sharpe(portfolio_returns or [], sharpe_window)
        # Only counts as trigger when window is full (enough data)
        ret_len = len(portfolio_returns or [])
        trig_b = (
            sharpe_val is not None
            and ret_len >= sharpe_window
            and sharpe_val < sharpe_floor
        )

        # Trigger C: 3 consecutive losing weeks
        losing_threshold = int(self._retreat_cfg.get("consecutive_losing_weeks", 3))
        trig_c = self.state.consecutive_losing_weeks >= losing_threshold

        fired = trig_a or trig_b or trig_c
        reason = ""
        if trig_a:
            reason = f"dd_{dd_from_hwm:.1%}_from_hwm"
        elif trig_b:
            reason = f"sharpe_{sharpe_val:.2f}_below_{sharpe_floor:.2f}"
        elif trig_c:
            reason = f"{self.state.consecutive_losing_weeks}_losing_weeks"

        return {
            "fired": fired,
            "reason": reason,
            "trigger_a_dd_from_hwm": trig_a,
            "trigger_a_dd_pct": dd_from_hwm,
            "trigger_b_low_sharpe": trig_b,
            "trigger_b_sharpe_value": sharpe_val,
            "trigger_c_3_losing_weeks": trig_c,
            "tier_hwm": self.state.tier_high_water_mark,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _rolling_sharpe(returns: list[float], window: int) -> Optional[float]:
        """Naive Sharpe over the trailing window: mean / stdev * sqrt(252).

        Returns None if the window doesn't have enough samples OR stdev=0
        (degenerate). Caller treats None as "gate fails (insufficient data)"
        for advancement and "trigger does not fire" for retreat — matches
        the conservative interpretation in SIZING_SCHEDULE §3.
        """
        if not returns or len(returns) < 2:
            return None
        sample = returns[-window:] if len(returns) >= window else list(returns)
        if len(sample) < 2:
            return None
        mean = sum(sample) / len(sample)
        var = sum((r - mean) ** 2 for r in sample) / (len(sample) - 1)
        stdev = math.sqrt(var)
        if stdev == 0:
            return None
        # Annualize assuming 252 trading days
        return (mean / stdev) * math.sqrt(252)

    def _update_weekly_pnl(self, session_date: date, equity: float) -> None:
        """Track ISO-week P&L and consecutive_losing_weeks counter.

        We compute the session's P&L as (equity - prior_session_equity)
        from equity_history; on the first session we have no prior, so
        the contribution is zero.
        """
        # Session P&L from history (uses the equity we just appended)
        if len(self.state.equity_history) >= 2:
            session_pnl = (
                self.state.equity_history[-1] - self.state.equity_history[-2]
            )
        else:
            session_pnl = 0.0

        iso_year, iso_week, _ = session_date.isocalendar()
        bucket = f"{iso_year}-W{iso_week:02d}"
        if self.state.current_iso_week is None:
            self.state.current_iso_week = bucket
            self.state.current_week_pnl = session_pnl
            return
        if bucket == self.state.current_iso_week:
            self.state.current_week_pnl += session_pnl
            return
        # Week rolled over — close out the previous week and start new bucket
        closed_pnl = self.state.current_week_pnl
        self.state.weekly_pnl.append(closed_pnl)
        if len(self.state.weekly_pnl) > 12:
            self.state.weekly_pnl = self.state.weekly_pnl[-12:]
        # Update consecutive losing-weeks counter
        if closed_pnl < 0:
            self.state.consecutive_losing_weeks += 1
        else:
            self.state.consecutive_losing_weeks = 0
        self.state.current_iso_week = bucket
        self.state.current_week_pnl = session_pnl


__all__ = ["HalfKellySizer", "TieredSizer", "TierRow", "TierState", "SizerProtocol"]
