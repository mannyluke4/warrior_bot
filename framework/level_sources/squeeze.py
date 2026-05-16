"""SqueezeSource — framework wrapper around `squeeze_detector_v2.SqueezeDetectorV2`.

This is a **wrapper, not a rewrite**. The squeeze production code is sacred
(see DIRECTIVE_2026-05-17_GO_FOR_BUILD §Hard constraints) so this module
*delegates* every detection decision to `SqueezeDetectorV2` — it does not
re-implement any squeeze logic. The wrapper's job is purely structural:

  1. Translate framework `Bar` / `BarHistory` objects into the dict-shaped
     bars `SqueezeDetectorV2.on_bar_close_1m()` expects.
  2. Expose the squeeze detector's *watched levels* as a `LevelSet` so the
     combined portfolio backtest harness can reason about squeeze signals
     alongside the other framework strategies.
  3. Forward tick prices into `SqueezeDetectorV2.on_trade_price()` so the
     state machine's IDLE → PRIMED → ARMED → ENTRY transitions still
     fire exactly as they do in production.

The combined backtest harness consumes:

  - `LevelSet` (from `compute_levels`) so it knows which prices to watch
    on each session (PM_HIGH, PDH, the next whole-dollar above the last
    open). Squeeze does not need an ArrivalDetector in the framework sense
    because the squeeze detector's internal state machine *is* the
    arrival+confirmation gate. The framework runner therefore treats
    squeeze-emitted ARM messages as the confirmation event and consumes
    `entry_price` / `stop_low` / `r` straight off the wrapped detector's
    `ArmedTrade`.

  - `update_intraday(bar)` — forwards 1-minute bars into the detector,
    *exactly* the same call sequence `simulate.py` and `bot_v3_hybrid.py`
    use. Bit-identical output.

  - `on_trade_price(price)` — forwarded to the detector for tick-driven
    ARM transitions (V2's intrabar_arm) and entry-trigger checks.

Squeeze levels surfaced into the LevelSet:

  - `PM_HIGH` — set via `update_premarket_levels(pm_high)` (the caller
    plumbs this from a TradeBarBuilder, mirroring `simulate.py:2098`).
  - `PDH`      — caller sets `prior_day_high` on the wrapped detector;
    the wrapper emits it as a Level.
  - `ROUND`    — the next whole-dollar ceiling above the most recent
    bar's open (matches `_get_level_price("whole_dollar", ...)` exactly).

Notes
-----
Squeeze does *not* fit the framework's clean "level source emits levels +
arrival detector + confirmation rule" decomposition. Its volume/body/HOD
priming gate is structurally inside the detector. We do *not* try to
re-host that logic in confirmation plugins — that would mean
re-implementing it, which violates the wrapper-only rule. Instead the
framework runner treats this source as "self-arming": it polls the
detector for ARM messages via `pull_arm_message()` and uses
`get_armed_trade()` to fetch the entry/stop/R.

This deliberately makes squeeze a *first-class* framework strategy
without modifying any of its internals.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Optional

from framework.level_sources.base import (
    Bar,
    BarHistory,
    Level,
    LevelSet,
    LevelSourceProtocol,
)

# Lazy import keeps this module loadable even if squeeze deps are missing
# in pure-framework test environments (e.g. CI without macd/patterns).
def _load_squeeze_detector():  # pragma: no cover - import indirection
    from squeeze_detector_v2 import SqueezeDetectorV2

    return SqueezeDetectorV2


# Session boundaries we care about for premarket-high extraction.
# Squeeze's TradeBarBuilder uses 04:00-09:29 ET as premarket.
_PM_START = time(4, 0)
_PM_END = time(9, 30)
_RTH_OPEN = time(9, 30)
_RTH_CLOSE = time(16, 0)


def _bar_to_dict(bar: Bar) -> dict:
    """Convert a framework `Bar` into the dict shape the squeeze detector reads.

    SqueezeDetectorV2.on_bar_close_1m() accesses .open/.high/.low/.close/.volume
    (object attributes), so we wrap with a SimpleNamespace-like object.
    """
    return {
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }


class _BarAdapter:
    """Minimal object the squeeze detector can read like a `Bar`.

    SqueezeDetectorV2 reads `bar.open`, `bar.high`, etc. (attribute access).
    A SimpleNamespace would also work; this is a tiny shim that lets us
    pass framework Bars through without copying.
    """

    __slots__ = ("open", "high", "low", "close", "volume")

    def __init__(self, bar: Bar) -> None:
        self.open = bar.open
        self.high = bar.high
        self.low = bar.low
        self.close = bar.close
        self.volume = bar.volume


@dataclass
class SqueezeSource:
    """Framework-compatible wrapper around SqueezeDetectorV2.

    Parameters
    ----------
    target_date:
        Session being traded. If None, inferred from the last bar in history
        on each `compute_levels` call (mirrors PDHPDLSource's convention).
    premarket_high:
        Caller-supplied premarket high. Live/sim plumb this in from
        `TradeBarBuilder.get_premarket_high()`. The wrapper forwards it
        to `SqueezeDetectorV2.update_premarket_levels()` so the detector's
        `_get_level_price("pm_high")` returns the right value.
    prior_day_high:
        PDH for the target session. Forwarded to the detector by setting
        `detector.prior_day_high`.
    gap_pct:
        Premarket gap percent — used by squeeze's `_score_setup()` to
        award a +1.0 score bonus on ≥20% gaps. Optional.

    Detector lifecycle
    ------------------
    The wrapped detector is *constructed lazily* on first use so this
    module imports cleanly even when `squeeze_detector_v2`'s transitive
    deps (macd, candles, patterns) aren't on the path.

    Bit-identity guarantee
    ----------------------
    `update_intraday(bar)` calls `detector.on_bar_close_1m(bar_adapter, vwap)`
    with the same kwargs `simulate.py` does. The detector's reset/prime/arm
    state machine, dynamic-attempts bonus, seed-stale gate, vol winsorize —
    all of it lives inside `SqueezeDetectorV2`. We add nothing.
    """

    target_date: Optional[date] = None
    premarket_high: Optional[float] = None
    prior_day_high: Optional[float] = None
    premarket_bull_flag_high: Optional[float] = None
    gap_pct: Optional[float] = None
    symbol: str = ""

    # Internal — the wrapped detector and last-emitted state.
    _detector: object = field(default=None, init=False, repr=False)
    _last_level_set: Optional[LevelSet] = field(default=None, init=False, repr=False)
    _last_arm_message: Optional[str] = field(default=None, init=False, repr=False)
    _last_bar_open: Optional[float] = field(default=None, init=False, repr=False)
    _last_vwap: Optional[float] = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    # Detector access
    # ------------------------------------------------------------------
    @property
    def detector(self):
        """Lazily-constructed underlying `SqueezeDetectorV2`."""
        if self._detector is None:
            cls = _load_squeeze_detector()
            det = cls()
            det.symbol = self.symbol or ""
            if self.premarket_high is not None or self.premarket_bull_flag_high is not None:
                det.update_premarket_levels(
                    self.premarket_high, self.premarket_bull_flag_high
                )
            if self.prior_day_high is not None:
                det.prior_day_high = self.prior_day_high
            if self.gap_pct is not None:
                det.gap_pct = self.gap_pct
            self._detector = det
        return self._detector

    def set_premarket_levels(
        self, pm_high: Optional[float], pm_bf_high: Optional[float] = None
    ) -> None:
        """Plumb PM_HIGH (and optional bull-flag high) into the detector.

        Mirrors squeeze's `simulate.py:2415` call exactly.
        """
        self.premarket_high = pm_high
        self.premarket_bull_flag_high = pm_bf_high
        if self._detector is not None:
            self.detector.update_premarket_levels(pm_high, pm_bf_high)

    def set_prior_day_high(self, pdh: Optional[float]) -> None:
        """Plumb PDH into the detector."""
        self.prior_day_high = pdh
        if self._detector is not None:
            self.detector.prior_day_high = pdh

    # ------------------------------------------------------------------
    # LevelSourceProtocol
    # ------------------------------------------------------------------
    def compute_levels(self, symbol: str, history: BarHistory) -> LevelSet:
        """Return the squeeze-watched levels for the target session.

        Emits up to three levels:
          - PM_HIGH  (if `premarket_high` is set, else inferred from history)
          - PDH      (if `prior_day_high` is set, else inferred from history)
          - ROUND    (next whole-dollar above the most recent bar's open;
                      this is what squeeze's `whole_dollar` path watches)

        The level kinds use canonical framework names so downstream
        consumers (attribution, conflict resolution) treat them
        consistently with the other strategies' levels.
        """
        if symbol:
            self.symbol = symbol
        target = self._resolve_target_date(history)
        if target is None:
            return LevelSet(symbol=symbol, session_date=date.today(), levels=tuple())

        # Auto-fill PM_HIGH from history when caller hasn't set it.
        pm_high = self.premarket_high
        if pm_high is None:
            pm_high = self._extract_pm_high(history, target)

        # Auto-fill PDH from history when caller hasn't set it.
        pdh = self.prior_day_high
        if pdh is None:
            pdh = self._extract_pdh(history, target)

        # Push into wrapped detector so it sees the same levels at signal time.
        if pm_high is not None:
            self.detector.update_premarket_levels(pm_high, self.premarket_bull_flag_high)
            self.premarket_high = pm_high
        if pdh is not None:
            self.detector.prior_day_high = pdh
            self.prior_day_high = pdh

        levels: list[Level] = []
        if pm_high is not None and pm_high > 0:
            levels.append(
                Level(
                    price=float(pm_high),
                    kind="PM_HIGH",
                    session_date=target,
                    metadata={"source": "squeeze"},
                )
            )
        if pdh is not None and pdh > 0:
            levels.append(
                Level(
                    price=float(pdh),
                    kind="PDH",
                    session_date=target,
                    metadata={"source": "squeeze"},
                )
            )
        # Whole-dollar level — squeeze watches the next $1 ceiling above
        # the most recent 1m open. This mirrors
        # SqueezeDetectorV2._get_level_price("whole_dollar", ...) exactly.
        if self._last_bar_open is not None and self._last_bar_open > 0:
            import math as _math

            whole = float(_math.ceil(self._last_bar_open))
            if whole > 0:
                levels.append(
                    Level(
                        price=whole,
                        kind="ROUND",
                        session_date=target,
                        metadata={"source": "squeeze", "increment": 1.0},
                    )
                )

        ls = LevelSet(
            symbol=symbol, session_date=target, levels=tuple(levels)
        )
        self._last_level_set = ls
        return ls

    def update_intraday(self, bar: Bar) -> None:
        """Forward a 1-minute bar into the wrapped detector.

        Mirrors the call site at `simulate.py:1894-1898` / `bot_v3_hybrid.py`
        — passes the bar to `on_bar_close_1m(bar, vwap=...)`. The caller
        is responsible for tracking the running VWAP and pushing it in
        via `set_vwap()` before calling this method.
        """
        adapter = _BarAdapter(bar)
        self._last_bar_open = bar.open
        msg = self.detector.on_bar_close_1m(adapter, vwap=self._last_vwap)
        if msg is not None:
            # Surface the squeeze detector's free-form ARM / RESET log
            # line for the combined backtest harness to record. We don't
            # parse it — the harness pulls structured state via
            # `get_armed_trade()` and `is_in_trade()`.
            self._last_arm_message = msg

    # ------------------------------------------------------------------
    # Squeeze-specific plumbing the framework runner uses
    # ------------------------------------------------------------------
    def set_vwap(self, vwap: Optional[float]) -> None:
        """Set the VWAP used on the next `update_intraday` call."""
        self._last_vwap = vwap

    def on_trade_price(
        self, price: float, is_premarket: bool = False
    ) -> Optional[str]:
        """Forward a tick price into the squeeze detector.

        Returns the detector's ARM / ENTRY message if one was generated
        on this tick, else None. The combined backtest harness consumes
        the message to drive the entry/exit lifecycle in its trade ledger.
        """
        return self.detector.on_trade_price(price, is_premarket=is_premarket)

    def is_armed(self) -> bool:
        """True when the squeeze detector is in ARMED state with an `ArmedTrade`."""
        det = self._detector
        return det is not None and getattr(det, "armed", None) is not None

    def get_armed_trade(self):
        """Return the underlying `ArmedTrade` namedtuple, or None.

        Combined-backtest consumes `.trigger_high` / `.entry_price` /
        `.stop_low` / `.r` / `.score` / `.size_mult` straight off this
        — there is no framework-side translation needed because we are a
        wrapper, not a re-implementation.
        """
        det = self._detector
        if det is None:
            return None
        return getattr(det, "armed", None)

    def pull_arm_message(self) -> Optional[str]:
        """Pop the most recent detector log message (one-shot)."""
        msg = self._last_arm_message
        self._last_arm_message = None
        return msg

    def begin_seed(self) -> None:
        """Forwarded to detector — switches it into seed-replay mode."""
        self.detector.begin_seed()

    def end_seed(self) -> None:
        """Forwarded to detector — exits seed-replay mode."""
        self.detector.end_seed()

    def seed_bar_close(
        self, o: float, h: float, l: float, c: float, v: float
    ) -> None:
        """Forwarded to detector for premarket warmup bars."""
        self.detector.seed_bar_close(o, h, l, c, v)
        # Keep last_bar_open tracking accurate for the ROUND level even
        # during seed (last bar might be a PM bar at session open).
        self._last_bar_open = o

    def notify_trade_opened(
        self,
        entry: float = 0,
        stop: float = 0,
        r: float = 0,
        qty: int = 0,
        time_str: str = "",
        is_parabolic: bool = False,
    ) -> None:
        """Forwarded — squeeze runs its own exit state, callers must notify it."""
        self.detector.notify_trade_opened(
            entry=entry, stop=stop, r=r, qty=qty,
            time_str=time_str, is_parabolic=is_parabolic,
        )

    def notify_trade_closed(self, symbol: str, pnl: float, r_mult: float = 0.0) -> None:
        """Forwarded — accrues into dynamic-attempts bonus."""
        self.detector.notify_trade_closed(symbol, pnl, r_mult=r_mult)

    def check_exit(
        self,
        price: float,
        qty: int,
        bar_10s=None,
        bar_1m=None,
        time_str: Optional[str] = None,
    ) -> Optional[str]:
        """Forwarded — squeeze owns exit logic per the wrapper contract."""
        return self.detector.check_exit(
            price=price, qty=qty, bar_10s=bar_10s, bar_1m=bar_1m, time_str=time_str
        )

    def reset(self) -> None:
        """Forwarded — squeeze's between-session reset."""
        if self._detector is not None:
            self._detector.reset()
        self._last_arm_message = None
        self._last_bar_open = None

    # ------------------------------------------------------------------
    # Helpers — auto-derive PM_HIGH / PDH from history when caller didn't set
    # ------------------------------------------------------------------
    def _resolve_target_date(self, history: BarHistory) -> Optional[date]:
        if self.target_date is not None:
            return self.target_date
        if len(history) == 0:
            return None
        return max(b.timestamp.date() for b in history.bars)

    def _extract_pm_high(
        self, history: BarHistory, target: date
    ) -> Optional[float]:
        pm_bars = [
            b for b in history.bars
            if b.timestamp.date() == target
            and _PM_START <= b.timestamp.time() < _PM_END
        ]
        if not pm_bars:
            return None
        hi = max(b.high for b in pm_bars)
        return hi if hi > 0 else None

    def _extract_pdh(
        self, history: BarHistory, target: date
    ) -> Optional[float]:
        prior_dates = sorted({
            b.timestamp.date() for b in history.bars
            if b.timestamp.date() < target
            and _RTH_OPEN <= b.timestamp.time() < _RTH_CLOSE
        })
        if not prior_dates:
            return None
        prior = prior_dates[-1]
        prior_rth = [
            b for b in history.bars
            if b.timestamp.date() == prior
            and _RTH_OPEN <= b.timestamp.time() < _RTH_CLOSE
        ]
        if not prior_rth:
            return None
        hi = max(b.high for b in prior_rth)
        return hi if hi > 0 else None


__all__ = ["SqueezeSource"]
