"""SqueezeBreakout — framework wrapper exposing squeeze's volume+body criteria.

This is a thin re-shaping of `SqueezeDetectorV2`'s PRIMED-transition gate as
a `ConfirmationProtocol` so the combined backtest harness can interrogate
"would squeeze prime on this bar" via the same interface it uses for the
other framework confirmations (BreakoutCandle, SignalCandle, Rejection, …).

CRITICAL: this plugin does **not** re-implement squeeze logic. It defers
to the wrapped detector for both the priming gate AND any per-bar state
(rolling HOD, attempt counter, seed gates). The numeric checks below are
informational ONLY — they are exposed for fast-path checks in the combined
backtest's attribution layer, but the *authoritative* signal is whatever
the underlying detector emits via `on_bar_close_1m()`.

Why two layers?

  - The combined backtest needs a yes/no confirmation per bar to feed its
    attribution + conflict-resolution engine. That maps onto the
    framework's `ConfirmationProtocol`.
  - The actual ARM transition is path-dependent (HOD gate, COC, exhaustion
    delay, dynamic attempts) and lives entirely inside `SqueezeDetectorV2`.

The plugin's `check_confirmation()` returns the binary "squeeze priming
criteria met on this bar" answer; the harness then asks the wrapped
detector via `SqueezeSource.is_armed()` / `pull_arm_message()` for the
authoritative state.

Parameters (defaults match X01 tuning per CLAUDE.md / `.env` 2026-04-08):

  - min_vol_mult: WB_SQ_VOL_MULT (default 2.5)
  - prime_bars:   WB_SQ_PRIME_BARS (default 4)  [recorded for attribution; not used in check]
  - min_body_pct: WB_SQ_MIN_BODY_PCT (default 2.0)
  - min_bar_vol:  WB_SQ_MIN_BAR_VOL (default 50_000)

These constants intentionally pin the *framework-side* view to the same
knobs the live detector reads from env. If the env knobs drift, the
detector remains the source of truth — this plugin's verdict is just
fast-path metadata.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any, Optional

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


def _finite(x: float) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


@dataclass
class SqueezeBreakout:
    """ConfirmationProtocol: volume-spike + green-bar + body-pct (squeeze prime gate).

    Detection (informational; the wrapped SqueezeDetectorV2 is authoritative):

      1. `entry.volume >= min_vol_mult * avg(prior bars' volume)`
      2. `entry.volume >= min_bar_vol`
      3. `entry.close >= entry.open` (green bar)
      4. `body / open * 100 >= min_body_pct`

    These four criteria correspond exactly to `SqueezeDetectorV2.on_bar_close_1m()`
    lines 311-330 (IDLE-state volume explosion check + green-body gate).

    Edge cases:
      - Empty bars                       -> confirmed=False, reason="no bars"
      - <3 bars (insufficient baseline)  -> confirmed=False, reason="insufficient baseline"
      - NaN OHLCV                        -> confirmed=False, reason="nan ohlcv"
      - zero baseline volume             -> confirmed=False, reason="zero baseline vol"
    """

    min_vol_mult: float = 2.5
    prime_bars: int = 4
    min_body_pct: float = 2.0
    min_bar_vol: int = 50_000

    @classmethod
    def from_env(cls) -> "SqueezeBreakout":
        """Construct using the same env knobs the live detector reads.

        Matches the X01-tuning defaults from CLAUDE.md (2026-04-08).
        """
        return cls(
            min_vol_mult=float(os.getenv("WB_SQ_VOL_MULT", "2.5")),
            prime_bars=int(os.getenv("WB_SQ_PRIME_BARS", "4")),
            min_body_pct=float(os.getenv("WB_SQ_MIN_BODY_PCT", "2.0")),
            min_bar_vol=int(os.getenv("WB_SQ_MIN_BAR_VOL", "50000")),
        )

    def _avg_prior_vol(self, bars: list[Bar]) -> tuple[float, int]:
        """Average of `bars[:-1]` volume (matches squeeze's `_avg_prior_vol()`)."""
        if len(bars) < 2:
            return 0.0, 0
        prior = [b for b in bars[:-1] if _finite(b.volume)]
        if not prior:
            return 0.0, 0
        return sum(b.volume for b in prior) / len(prior), len(prior)

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        if not bars:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason="no bars",
            )

        # Squeeze requires >=3 bars in the deque to start considering IDLE
        # transitions (per `on_bar_close_1m` line 304). Mirror that.
        if len(bars) < 3:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason=f"insufficient bars ({len(bars)} < 3)",
            )

        entry = bars[-1]
        if not all(
            _finite(x)
            for x in (entry.open, entry.high, entry.low, entry.close, entry.volume)
        ):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason="nan ohlcv",
            )

        # 1. Volume mult check
        baseline, n = self._avg_prior_vol(bars)
        if baseline <= 0:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason=f"zero baseline vol ({n} prior bars)",
            )
        vol_mult = entry.volume / baseline
        if vol_mult < self.min_vol_mult:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason=(
                    f"vol_mult={vol_mult:.2f}x < min={self.min_vol_mult:.2f}x"
                ),
                metadata={"vol_mult": vol_mult, "baseline": baseline, "n": n},
            )

        # 2. Minimum absolute volume
        if entry.volume < self.min_bar_vol:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason=(
                    f"bar_vol={entry.volume:.0f} < min={self.min_bar_vol}"
                ),
                metadata={"bar_vol": entry.volume},
            )

        # 3. Green bar
        if entry.close < entry.open:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason=f"red bar (c={entry.close:.4f} < o={entry.open:.4f})",
            )

        # 4. Body percentage
        body = abs(entry.close - entry.open)
        body_pct = (body / entry.open) * 100 if entry.open > 0 else 0.0
        if body_pct < self.min_body_pct:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="squeeze_breakout",
                strength=0.0,
                reason=(
                    f"body_pct={body_pct:.2f}% < min={self.min_body_pct:.2f}%"
                ),
                metadata={"body_pct": body_pct},
            )

        # Strength: blend vol multiplier (capped at 5x) with body magnitude.
        vol_component = max(0.0, min(1.0, (vol_mult - self.min_vol_mult) / 5.0))
        body_component = max(0.0, min(1.0, body_pct / 10.0))
        strength = round(0.5 * vol_component + 0.5 * body_component, 4)

        return ConfirmationResult(
            confirmed=True,
            pattern_name="squeeze_breakout",
            strength=strength,
            reason=(
                f"prime gate met: vol_mult={vol_mult:.2f}x baseline={baseline:.0f} "
                f"bar_vol={entry.volume:.0f} body_pct={body_pct:.2f}%"
            ),
            metadata={
                "vol_mult": vol_mult,
                "baseline": baseline,
                "bar_vol": entry.volume,
                "body_pct": body_pct,
                "prime_bars": self.prime_bars,
            },
        )


__all__ = ["SqueezeBreakout"]
