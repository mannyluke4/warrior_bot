"""framework.live_signal_engine — live equivalent of portfolio_backtest's signal loop.

Wave 4 paper deployment.

The backtest harness (`backtest/portfolio_backtest.py`) generates signals
by iterating an entire day's bar list with `_pdh_pdl_signal` /
`_opening_range_signal`. For live trading we cannot do that — bars arrive
one-by-one. This module is the live-bar equivalent: each closed 1-minute
bar is fed in, the strategy evaluators run against the accumulated history,
and a fresh `EntrySignal` (or None) is produced.

We REUSE the backtest's `SIGNAL_FUNCS` directly — there is no parity drift
risk because the same code path drives both backtest and live. The trade-off
is that signal evaluators are O(history) per bar; for a 36-symbol universe
with ~390 RTH bars/day this is well under a second per bar on the framework
runner's hardware budget.

Wave-4 filter knobs are evaluated AFTER signal generation here, mirroring
the backtest's `_signal_passes_wave4_filters`.

Public API:
    SignalEvaluator(strategy_specs)
    evaluator.on_bar_close(symbol, history, prior_bars, session_date,
                          vix_value=None, account_equity=None)
        -> list[StrategySignal]

The runner consumes the returned list, applies the per-(symbol, day) lock,
sizes via TieredSizer, and routes to LiveBroker.submit_entry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from framework.level_sources.base import Bar
from framework.filters import (
    env_skip_mondays_enabled,
    passes_pre_entry_filters,
)
from framework.vix_regime import VIXRegime, REGIME_EXTREME


# Import the SAME signal functions the backtest uses. This is intentional
# parity insurance — the backtest's Sharpe 1.30/2.10/2.81 OOS numbers come
# from these functions; the live runner must run them identically.
import sys

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from backtest.portfolio_backtest import (  # noqa: E402
    SIGNAL_FUNCS,
    _yaml_needs_prior,
    _vwap_at_bar,
    _or5_open_close,
    _PDH_PDL_YAMLS,
    EntrySignal,
    StrategyArm,
)


@dataclass
class StrategySignal:
    """One eligible entry signal ready for the runner's risk/lock pipeline."""

    arm_name: str
    yaml_path: str
    yaml_filename: str
    symbol: str
    session_date: date
    fill_ts: datetime
    direction: str
    entry_price: float
    stop_price: Optional[float]
    target_price: Optional[float]
    raw_signal: EntrySignal
    spec: dict[str, Any]
    spec_dict: dict[str, Any] = field(default_factory=dict)


def _passes_filters(
    *,
    spec: dict[str, Any],
    sig: EntrySignal,
    sym: str,
    history: list[Bar],
    session_date: date,
) -> tuple[bool, str]:
    """Live mirror of backtest's `_signal_passes_wave4_filters`.

    The backtest looks at sig.bar_idx + 1 because it has the full day. In
    live mode the SIGNAL_FUNCS work on the in-memory history; sig.bar_idx
    will be the second-to-last index (the just-closed bar is the confirm
    bar, the next bar's open is "the next live bar" — we approximate the
    entry price as the just-closed bar's close).
    """
    if sig.bar_idx + 1 >= len(history):
        # No fill bar yet — caller will retry on next minute close.
        # For live runner we treat the confirm-bar close as the entry ref.
        confirm_bar = history[sig.bar_idx]
        entry_ts = confirm_bar.timestamp
        entry_price = confirm_bar.close
        bars_before_entry = history[: sig.bar_idx]
        entry_bar_volume = float(confirm_bar.volume)
    else:
        fill_bar = history[sig.bar_idx + 1]
        entry_ts = fill_bar.timestamp
        entry_price = fill_bar.open
        bars_before_entry = history[: sig.bar_idx + 1]
        entry_bar_volume = float(fill_bar.volume)

    vwap_at_entry = _vwap_at_bar(history, sig.bar_idx)
    or5_open, or5_close = (
        _or5_open_close(history)
        if (spec.get("opening_bar_alignment") or {}).get("required", False)
        else (None, None)
    )

    return passes_pre_entry_filters(
        spec=spec,
        entry_ts=entry_ts,
        entry_price=entry_price,
        direction=sig.direction,
        symbol=sym,
        session_date=session_date,
        vwap_at_entry=vwap_at_entry,
        bars_before_entry=bars_before_entry,
        entry_bar_volume=entry_bar_volume,
        or5_open=or5_open,
        or5_close=or5_close,
    )


# ---------------------------------------------------------------------------
# SignalEvaluator
# ---------------------------------------------------------------------------


class SignalEvaluator:
    """Evaluate all configured strategy arms on each minute-bar close.

    Designed to be cheap to call repeatedly. State is held externally
    (the runner owns history, prior_bars, locks). This class is a pure
    function wrapper plus a small bit of per-arm caching for fired-signal
    deduplication.
    """

    def __init__(
        self,
        arms: list[StrategyArm],
        vix_regime: Optional[VIXRegime] = None,
        skip_mondays_env: Optional[bool] = None,
        log_fn=None,
    ) -> None:
        self.arms = arms
        self.vix_regime = vix_regime or VIXRegime(enabled=False)
        self.skip_mondays = (
            skip_mondays_env if skip_mondays_env is not None
            else env_skip_mondays_enabled()
        )
        # Track "already-fired" so we don't re-emit the same signal each minute
        # while the strategy's signal func keeps returning the same EntrySignal.
        # Key: (arm_name, symbol, session_date, bar_idx). Cleared on session change.
        self._fired: set[tuple[str, str, str, int]] = set()
        self._log = log_fn or (lambda msg: None)

    def reset_session(self) -> None:
        """Clear per-session dedup state. Runner calls this at session start."""
        self._fired.clear()

    def on_bar_close(
        self,
        symbol: str,
        history: list[Bar],
        prior_bars: list[Bar],
        session_date: date,
        vix_value: Optional[float] = None,
    ) -> list[StrategySignal]:
        """Evaluate all arms against `history`; return new signals only.

        Returns an empty list if no arm fires, or all firing arms have
        already been emitted this session for this symbol.
        """
        if not history:
            return []

        # VIX suppression gate — universal, applies to every arm
        if self.vix_regime.enabled and vix_value is not None:
            regime = self.vix_regime.current_regime(vix_value)
            if regime == REGIME_EXTREME:
                self._log(
                    f"[VIX] suppress at extreme: regime={regime} VIX={vix_value}"
                )
                return []
            # Configurable suppress threshold (.env.framework WB_VIX_SUPPRESS_THRESHOLD=25)
            import os as _os
            suppress = float(_os.environ.get("WB_VIX_SUPPRESS_THRESHOLD", "25"))
            if vix_value >= suppress:
                self._log(
                    f"[VIX] suppress: VIX={vix_value:.1f} >= {suppress:.1f} threshold"
                )
                return []

        # Monday skip (env-wide; per-YAML skip_mondays handled by filter dispatcher)
        if self.skip_mondays and session_date.weekday() == 0:
            self._log(
                f"[MONDAY] skip new entries: {session_date.isoformat()} is Monday"
            )
            return []

        out: list[StrategySignal] = []
        for arm in self.arms:
            spec = arm.spec
            yname = Path(arm.yaml_path).name
            fn = SIGNAL_FUNCS.get(yname)
            if fn is None:
                continue
            try:
                if _yaml_needs_prior(yname):
                    sig = fn(history, spec, prior_bars)
                else:
                    sig = fn(history, spec)
            except Exception as e:
                self._log(
                    f"[SIG_EVAL_ERROR] arm={arm.name} sym={symbol} raised: {e!r}"
                )
                continue
            if sig is None:
                continue

            # Dedup: same (arm, sym, day, bar_idx) emits only once
            key = (arm.name, symbol, session_date.isoformat(), sig.bar_idx)
            if key in self._fired:
                continue

            # Wave-4 filter check
            ok, reason = _passes_filters(
                spec=spec,
                sig=sig,
                sym=symbol,
                history=history,
                session_date=session_date,
            )
            if not ok:
                self._log(
                    f"[FILTER] arm={arm.name} sym={symbol} rejected: reason={reason}"
                )
                self._fired.add(key)  # don't re-evaluate this filter rejection every minute
                continue

            # Build the signal object the runner consumes
            confirm_bar = history[sig.bar_idx]
            if sig.bar_idx + 1 < len(history):
                fill_bar = history[sig.bar_idx + 1]
                fill_ts = fill_bar.timestamp
                entry_price = fill_bar.open
            else:
                fill_ts = confirm_bar.timestamp
                entry_price = confirm_bar.close

            out.append(
                StrategySignal(
                    arm_name=arm.name,
                    yaml_path=arm.yaml_path,
                    yaml_filename=yname,
                    symbol=symbol,
                    session_date=session_date,
                    fill_ts=fill_ts,
                    direction=sig.direction,
                    entry_price=entry_price,
                    stop_price=None,    # caller computes via _compute_stop_and_target
                    target_price=None,
                    raw_signal=sig,
                    spec=spec,
                )
            )
            self._fired.add(key)

        return out
