"""L2Confirm — three-mode L2 confirmation wrapper.

Wave-5 Agent N extension of the Wave-1 stub.

This module exposes three explicit, composable L2-confirmation modes (per
`DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §5 Agent N + design §5.3):

1. ``depth_imbalance``  — ratio of bid_size to ask_size at top N levels.
   Long-side requires imbalance > min_imbalance (default 1.5);
   short-side requires < (1 / min_imbalance) (default 0.67).
2. ``stacked_bids`` / ``stacked_asks`` — 3+ consecutive top levels with
   size > stack_size_threshold (default 1000).  Models "iceberg"
   institutional support/resistance.
3. ``momentum_vacuum`` — opposite-side aggregate size drops by
   > vacuum_drop_pct (default 0.50) within ``vacuum_window_secs``
   (default 5s).  Signals institutional withdrawal from one side,
   suggesting momentum continuation.

The plugin also retains the legacy single-shot wrapper around
``l2_signals.L2SignalDetector`` state dicts (imbalance + spread + stacking
combined) used by Wave-1 callers; the legacy mode is selected when
``mode=="legacy"`` (the historical default).

Input format
------------

``L2Confirm.check_confirmation()`` accepts ``l2_state`` in two shapes,
auto-detected:

* **Raw book snapshot** — has ``bids`` and ``asks`` keys, each a list of
  ``(price, size)`` tuples sorted best-first.  Optionally ``timestamp``
  (datetime) and ``history`` (a list of prior raw snapshots, oldest
  first) for ``momentum_vacuum`` mode.
* **Aggregated state dict** — the dict returned by
  ``l2_signals.L2SignalDetector.get_state()`` (imbalance / bid_stacking /
  spread_pct / etc.).  Used by the legacy mode and the synthetic-L2 path.

Backwards compatibility
-----------------------

The Wave-1 stub's call signature, defaults, and result schema are
preserved when ``mode == "legacy"`` (the unset default).  Existing tests
in ``tests/framework/test_confirmations.py::TestL2Confirm`` continue to
pass against this file unchanged.

Synthetic L2 (Wave 5 — see ``backtest/synthetic_l2.py``)
-------------------------------------------------------

L2 historical data is NOT in our Databento Standard subscription.  The
companion synthetic-L2 generator in ``backtest/synthetic_l2.py``
produces an aggregated state dict from 1m bar candles using:

* candle wick length → depth imbalance proxy
* trade volume → top-of-book size proxy
* bar-over-bar volume delta → momentum vacuum proxy

The synthetic state is shaped to satisfy this plugin's input contract,
so the same plugin runs in both backtest (synthetic) and live (real L2)
without changes.

Production capture spec (Wave 6)
--------------------------------

See ``docs/l2_capture_spec.md``.  Once live L2 events are persisted to
``l2_cache/<symbol>/<date>.parquet``, the backtest can feed real
snapshots into this plugin via ``RawSnapshot`` mode and the synthetic
generator becomes a fallback rather than the primary input.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, Optional, Sequence

from framework.confirmations.base import ConfirmationResult
from framework.level_sources.base import Bar, Level


# ---------------------------------------------------------------------------
# Direction inference (shared with breakout/rejection plugins).
# ---------------------------------------------------------------------------

Direction = Literal["long", "short", "auto"]
Mode = Literal[
    "legacy",
    "depth_imbalance",
    "stacked_bids",
    "stacked_asks",
    "momentum_vacuum",
]


_LONG_KINDS = frozenset(
    {"PDH", "ORH", "ROUND", "PM_HIGH", "BOX_TOP", "VAH", "POC", "ANCHORED_VWAP",
     "VWAP", "SWING_HIGH"}
)
_SHORT_KINDS = frozenset({"PDL", "ORL", "PM_LOW", "BOX_BOTTOM", "VAL", "SWING_LOW"})


def _infer_direction(level: Level) -> Literal["long", "short"]:
    if level.kind in _SHORT_KINDS:
        return "short"
    return "long"


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# State helpers — figure out which shape we got.
# ---------------------------------------------------------------------------


def _is_raw_snapshot(state: dict[str, Any]) -> bool:
    """A raw snapshot has bids/asks as sequences of (price, size)."""
    return (
        isinstance(state.get("bids"), (list, tuple))
        and isinstance(state.get("asks"), (list, tuple))
    )


def _level_sum(levels: Sequence[Sequence[float]] | None, n: int) -> float:
    """Sum size of the first ``n`` levels in a (price, size) sequence."""
    if not levels:
        return 0.0
    total = 0.0
    for level in levels[:n]:
        try:
            size = float(level[1])
        except (TypeError, ValueError, IndexError):
            continue
        if _finite(size):
            total += size
    return total


def _consecutive_above(levels: Sequence[Sequence[float]] | None, threshold: float) -> int:
    """Count consecutive top-of-book levels whose size > threshold."""
    if not levels:
        return 0
    count = 0
    for lvl in levels:
        try:
            size = float(lvl[1])
        except (TypeError, ValueError, IndexError):
            break
        if not _finite(size) or size <= threshold:
            break
        count += 1
    return count


# ---------------------------------------------------------------------------
# L2Confirm — Wave 5 extension.
# ---------------------------------------------------------------------------


@dataclass
class L2Confirm:
    """L2-state confirmation plugin with explicit mode selection.

    Modes:
        ``legacy``           — Wave-1 behavior (imbalance + spread + stacking).
                               This is the unset default for backwards compat.
        ``depth_imbalance``  — bid/ask size ratio at top ``top_n`` levels.
        ``stacked_bids``     — N+ consecutive top bid levels above size threshold.
        ``stacked_asks``     — N+ consecutive top ask levels above size threshold.
        ``momentum_vacuum``  — opposite-side size drop > X% within window.

    Args:
        mode: Which check to run.  Default ``"legacy"`` for backwards compat.
        min_imbalance: For ``depth_imbalance`` mode, the bid/ask ratio
            threshold favoring our direction.  Default 1.5 (long requires
            bids > 1.5 x asks; short requires asks > 1.5 x bids, i.e.
            bid/ask < 0.67).  For ``legacy``, this is the bid-share
            threshold (0.55) on (bid_total / (bid+ask)).
        top_n: Number of top-of-book levels to inspect.  Default 5.
        stack_size_threshold: Min size per level to count toward stacking.
            Default 1000.
        stack_levels_required: Min number of consecutive levels meeting
            threshold to confirm stacking.  Default 3.
        vacuum_drop_pct: Opposite-side relative drop required for vacuum.
            Default 0.50 (i.e. 50% drop).
        vacuum_window_secs: Window over which the drop must occur.
            Default 5.0.
        max_spread_pct: Spread veto.  Set very large to disable.  Default 1.0.
        require_bid_stacking: (legacy only) for long, bid_stacking must
            be True.
        require_ask_stacking: (legacy only) for short, see Wave-1 docstring.
        direction: ``"long"`` / ``"short"`` / ``"auto"``.
        pass_through_on_missing: If True and ``l2_state`` is None or empty,
            return confirmed=True with strength 0.  Default False.
    """

    mode: Mode = "legacy"
    min_imbalance: float = 0.55
    top_n: int = 5
    stack_size_threshold: float = 1000.0
    stack_levels_required: int = 3
    vacuum_drop_pct: float = 0.50
    vacuum_window_secs: float = 5.0
    max_spread_pct: float = 1.0
    require_bid_stacking: bool = False
    require_ask_stacking: bool = False
    direction: Direction = "auto"
    pass_through_on_missing: bool = False

    # ----- public API -----

    def check_confirmation(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: Optional[dict[str, Any]] = None,
    ) -> ConfirmationResult:
        # Direction resolution.
        if self.direction in ("long", "short"):
            direction = self.direction
        elif level is not None:
            direction = _infer_direction(level)
        else:
            direction = "long"

        if l2_state is None:
            return self._missing(direction, "no L2 state")

        if self.mode == "legacy":
            return self._check_legacy(level, bars, l2_state, direction)
        if self.mode == "depth_imbalance":
            return self._check_depth_imbalance(l2_state, direction)
        if self.mode == "stacked_bids":
            return self._check_stacked(l2_state, direction, side="bids")
        if self.mode == "stacked_asks":
            return self._check_stacked(l2_state, direction, side="asks")
        if self.mode == "momentum_vacuum":
            return self._check_momentum_vacuum(l2_state, direction)
        raise ValueError(f"unknown L2Confirm.mode={self.mode!r}")

    # ----- helpers -----

    def _missing(self, direction: str, reason: str) -> ConfirmationResult:
        if self.pass_through_on_missing:
            return ConfirmationResult(
                confirmed=True,
                pattern_name="l2_confirm",
                strength=0.0,
                reason=f"{reason} (pass-through)",
                metadata={"direction": direction, "pass_through": True, "mode": self.mode},
            )
        return ConfirmationResult(
            confirmed=False,
            pattern_name="l2_confirm",
            strength=0.0,
            reason=reason,
            metadata={"direction": direction, "mode": self.mode},
        )

    # =====================================================================
    # Mode: depth_imbalance
    # =====================================================================

    def _check_depth_imbalance(
        self, l2_state: dict[str, Any], direction: str
    ) -> ConfirmationResult:
        """Long: bid_size_top_n / ask_size_top_n >= min_imbalance.
        Short: ask_size_top_n / bid_size_top_n >= min_imbalance."""
        bids = l2_state.get("bids")
        asks = l2_state.get("asks")
        if bids is not None and asks is not None:
            # Raw snapshot mode
            bid_size = _level_sum(bids, self.top_n)
            ask_size = _level_sum(asks, self.top_n)
            if bid_size <= 0 and ask_size <= 0:
                return self._missing(direction, "empty book")
            if direction == "long":
                if ask_size <= 0:
                    ratio = float("inf")
                else:
                    ratio = bid_size / ask_size
                ok = ratio >= self.min_imbalance
            else:
                if bid_size <= 0:
                    ratio = float("inf")
                else:
                    ratio = ask_size / bid_size
                ok = ratio >= self.min_imbalance
            strength = self._imbalance_strength(ratio)
            if not ok:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason=(
                        f"depth_imbalance {direction} fail: "
                        f"ratio={ratio:.2f}, need >= {self.min_imbalance:.2f} "
                        f"(top_n={self.top_n}, bid_size={bid_size:.0f}, "
                        f"ask_size={ask_size:.0f})"
                    ),
                    metadata={
                        "direction": direction,
                        "mode": "depth_imbalance",
                        "ratio": ratio,
                        "bid_size": bid_size,
                        "ask_size": ask_size,
                        "top_n": self.top_n,
                    },
                )
            return ConfirmationResult(
                confirmed=True,
                pattern_name="l2_confirm_depth_imbalance",
                strength=strength,
                reason=(
                    f"depth_imbalance {direction} ok: ratio={ratio:.2f} "
                    f">= {self.min_imbalance:.2f} "
                    f"(bid_size={bid_size:.0f}, ask_size={ask_size:.0f})"
                ),
                metadata={
                    "direction": direction,
                    "mode": "depth_imbalance",
                    "ratio": ratio,
                    "bid_size": bid_size,
                    "ask_size": ask_size,
                    "top_n": self.top_n,
                },
            )

        # Aggregated state: fall back to imbalance (bid-share) re-interpreted
        # as a ratio.  bid-share s → ratio b/a = s / (1-s).
        imb = l2_state.get("imbalance")
        if not _finite(imb):
            return self._missing(direction, "missing imbalance / book")
        imb = float(imb)
        # Avoid divide-by-zero with a small epsilon.
        if imb <= 0:
            ratio_long = 0.0
        elif imb >= 1.0:
            ratio_long = float("inf")
        else:
            ratio_long = imb / (1.0 - imb)
        ratio = ratio_long if direction == "long" else (
            float("inf") if ratio_long == 0 else 1.0 / ratio_long
        )
        ok = ratio >= self.min_imbalance
        strength = self._imbalance_strength(ratio)
        if not ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason=(
                    f"depth_imbalance {direction} fail (aggregated): "
                    f"ratio={ratio:.2f}, need >= {self.min_imbalance:.2f}"
                ),
                metadata={
                    "direction": direction,
                    "mode": "depth_imbalance",
                    "ratio": ratio,
                    "imbalance": imb,
                },
            )
        return ConfirmationResult(
            confirmed=True,
            pattern_name="l2_confirm_depth_imbalance",
            strength=strength,
            reason=(
                f"depth_imbalance {direction} ok (aggregated): ratio={ratio:.2f}"
            ),
            metadata={
                "direction": direction,
                "mode": "depth_imbalance",
                "ratio": ratio,
                "imbalance": imb,
            },
        )

    def _imbalance_strength(self, ratio: float) -> float:
        """Map ratio to [0, 1] strength.  At threshold -> ~0.5; at 3x -> ~1.0."""
        if not _finite(ratio):
            return 1.0
        if ratio <= 1.0:
            return 0.0
        # Linear ramp from min_imbalance to 3x for [0.5, 1.0].
        span = max(1e-6, 3.0 - self.min_imbalance)
        s = 0.5 + 0.5 * (ratio - self.min_imbalance) / span
        return max(0.0, min(1.0, round(s, 4)))

    # =====================================================================
    # Mode: stacked_bids / stacked_asks
    # =====================================================================

    def _check_stacked(
        self, l2_state: dict[str, Any], direction: str, side: Literal["bids", "asks"]
    ) -> ConfirmationResult:
        """Detect N+ consecutive top levels above the size threshold."""
        levels = l2_state.get(side)
        if levels is None:
            # Fall back to aggregated bid_stack_levels (bids only).
            agg = l2_state.get("bid_stack_levels")
            if side == "bids" and agg:
                count = sum(1 for _, size in agg if size > self.stack_size_threshold)
                if count >= self.stack_levels_required:
                    return ConfirmationResult(
                        confirmed=True,
                        pattern_name=f"l2_confirm_stacked_{side}",
                        strength=min(1.0, count / max(self.stack_levels_required + 2, 1)),
                        reason=(
                            f"aggregated stacked_{side}: {count} levels "
                            f">= {self.stack_size_threshold:.0f}"
                        ),
                        metadata={
                            "direction": direction,
                            "mode": f"stacked_{side}",
                            "count": count,
                            "threshold": self.stack_size_threshold,
                        },
                    )
            return self._missing(direction, f"no {side} levels available")

        count = _consecutive_above(levels, self.stack_size_threshold)
        ok = count >= self.stack_levels_required
        # Sum of stacked sizes contributes to strength.
        stacked_size = sum(
            float(lvl[1]) for lvl in levels[:count] if _finite(lvl[1])
        )

        if not ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason=(
                    f"stacked_{side} fail: {count} consecutive levels "
                    f"> {self.stack_size_threshold:.0f}, need "
                    f">= {self.stack_levels_required}"
                ),
                metadata={
                    "direction": direction,
                    "mode": f"stacked_{side}",
                    "count": count,
                    "threshold": self.stack_size_threshold,
                    "required": self.stack_levels_required,
                },
            )

        strength = min(1.0, count / max(self.stack_levels_required + 2, 1))
        return ConfirmationResult(
            confirmed=True,
            pattern_name=f"l2_confirm_stacked_{side}",
            strength=round(strength, 4),
            reason=(
                f"stacked_{side} ok: {count} consecutive levels "
                f"> {self.stack_size_threshold:.0f} (total={stacked_size:.0f})"
            ),
            metadata={
                "direction": direction,
                "mode": f"stacked_{side}",
                "count": count,
                "stacked_size": stacked_size,
                "threshold": self.stack_size_threshold,
                "required": self.stack_levels_required,
            },
        )

    # =====================================================================
    # Mode: momentum_vacuum
    # =====================================================================

    def _check_momentum_vacuum(
        self, l2_state: dict[str, Any], direction: str
    ) -> ConfirmationResult:
        """Opposite-side total size dropped by > vacuum_drop_pct within window.

        Requires either:
            (a) ``history`` key with prior raw snapshots (each having
                bids/asks/timestamp); OR
            (b) ``opposite_side_drop_pct`` key (aggregated state from the
                synthetic-L2 generator or future live L2 capture).
        """
        agg_drop = l2_state.get("opposite_side_drop_pct")
        if _finite(agg_drop):
            agg_drop = float(agg_drop)
            ok = agg_drop >= self.vacuum_drop_pct
            strength = min(1.0, max(0.0, agg_drop)) if ok else 0.0
            if not ok:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason=(
                        f"momentum_vacuum fail (aggregated): "
                        f"drop={agg_drop:.2%} < {self.vacuum_drop_pct:.2%}"
                    ),
                    metadata={
                        "direction": direction,
                        "mode": "momentum_vacuum",
                        "drop_pct": agg_drop,
                        "required": self.vacuum_drop_pct,
                    },
                )
            return ConfirmationResult(
                confirmed=True,
                pattern_name="l2_confirm_momentum_vacuum",
                strength=round(strength, 4),
                reason=(
                    f"momentum_vacuum ok (aggregated): drop={agg_drop:.2%} "
                    f">= {self.vacuum_drop_pct:.2%}"
                ),
                metadata={
                    "direction": direction,
                    "mode": "momentum_vacuum",
                    "drop_pct": agg_drop,
                    "required": self.vacuum_drop_pct,
                },
            )

        history = l2_state.get("history")
        if not history:
            return self._missing(direction, "no L2 history for momentum_vacuum")

        # Pick reference snapshot at start of window.
        try:
            now_ts = l2_state.get("timestamp")
            if isinstance(now_ts, str):
                now_ts = datetime.fromisoformat(now_ts)
            if now_ts is None and history:
                # use first/last in history if no current ts
                last = history[-1]
                now_ts = last.get("timestamp")
                if isinstance(now_ts, str):
                    now_ts = datetime.fromisoformat(now_ts)
        except (TypeError, ValueError):
            now_ts = None
        if now_ts is None:
            return self._missing(direction, "missing timestamp for vacuum window")

        window_start = now_ts - timedelta(seconds=self.vacuum_window_secs)
        ref_snap = None
        for snap in history:
            try:
                ts = snap.get("timestamp")
                if isinstance(ts, str):
                    ts = datetime.fromisoformat(ts)
            except (AttributeError, TypeError, ValueError):
                continue
            if ts is None:
                continue
            if ts <= window_start:
                ref_snap = snap
                continue
            # The first snapshot inside the window is also acceptable if
            # we never see one strictly before the start; we keep going to
            # find the latest snapshot <= window_start.
        # If we never found one before window_start, fall back to oldest.
        if ref_snap is None:
            ref_snap = history[0]

        # Opposite side: for long, vacuum on ask side; for short, on bid side.
        opp_side = "asks" if direction == "long" else "bids"
        cur_size = _level_sum(l2_state.get(opp_side), self.top_n)
        ref_size = _level_sum(ref_snap.get(opp_side), self.top_n)
        if ref_size <= 0:
            return self._missing(direction, f"reference {opp_side} size = 0")

        drop_pct = (ref_size - cur_size) / ref_size
        ok = drop_pct >= self.vacuum_drop_pct
        if not ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason=(
                    f"momentum_vacuum fail: opposite-side ({opp_side}) "
                    f"drop={drop_pct:.2%} < {self.vacuum_drop_pct:.2%} "
                    f"(ref={ref_size:.0f} -> cur={cur_size:.0f})"
                ),
                metadata={
                    "direction": direction,
                    "mode": "momentum_vacuum",
                    "opp_side": opp_side,
                    "drop_pct": drop_pct,
                    "ref_size": ref_size,
                    "cur_size": cur_size,
                },
            )
        strength = min(1.0, drop_pct)
        return ConfirmationResult(
            confirmed=True,
            pattern_name="l2_confirm_momentum_vacuum",
            strength=round(strength, 4),
            reason=(
                f"momentum_vacuum ok: {opp_side} drop={drop_pct:.2%} "
                f"in last {self.vacuum_window_secs:.0f}s "
                f"({ref_size:.0f} -> {cur_size:.0f})"
            ),
            metadata={
                "direction": direction,
                "mode": "momentum_vacuum",
                "opp_side": opp_side,
                "drop_pct": drop_pct,
                "ref_size": ref_size,
                "cur_size": cur_size,
            },
        )

    # =====================================================================
    # Mode: legacy (Wave-1 behavior, preserved for backwards compatibility)
    # =====================================================================

    def _check_legacy(
        self,
        level: Optional[Level],
        bars: list[Bar],
        l2_state: dict[str, Any],
        direction: str,
    ) -> ConfirmationResult:
        imbalance = l2_state.get("imbalance")
        spread_pct = l2_state.get("spread_pct")
        bid_stacking = bool(l2_state.get("bid_stacking", False))
        ask_thinning = bool(l2_state.get("ask_thinning", False))
        large_bid = bool(l2_state.get("large_bid", False))
        large_ask = bool(l2_state.get("large_ask", False))

        # 1. Spread veto
        if spread_pct is not None and _finite(spread_pct):
            if float(spread_pct) > self.max_spread_pct:
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason=(
                        f"spread_pct={float(spread_pct):.2f}% > "
                        f"max={self.max_spread_pct:.2f}%"
                    ),
                    metadata={
                        "direction": direction,
                        "spread_pct": float(spread_pct),
                        "mode": "legacy",
                    },
                )

        # 2. Imbalance check
        if imbalance is None or not _finite(imbalance):
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason="missing imbalance",
                metadata={"direction": direction, "mode": "legacy"},
            )
        imbalance = float(imbalance)
        if direction == "long":
            imbalance_ok = imbalance >= self.min_imbalance
            imb_strength = min(1.0, max(0.0, (imbalance - 0.5) * 4.0))
        else:
            short_threshold = 1.0 - self.min_imbalance
            imbalance_ok = imbalance <= short_threshold
            imb_strength = min(1.0, max(0.0, (0.5 - imbalance) * 4.0))

        if not imbalance_ok:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason=(
                    f"{direction} imbalance fail: bid_share={imbalance:.2f}, "
                    f"need {'>=' if direction == 'long' else '<='} "
                    f"{self.min_imbalance if direction == 'long' else 1.0 - self.min_imbalance:.2f}"
                ),
                metadata={
                    "direction": direction,
                    "imbalance": imbalance,
                    "mode": "legacy",
                },
            )

        # 3. Stacking requirements
        if direction == "long" and self.require_bid_stacking and not bid_stacking:
            return ConfirmationResult(
                confirmed=False,
                pattern_name="l2_confirm",
                strength=0.0,
                reason="long requires bid_stacking but absent",
                metadata={
                    "direction": direction,
                    "imbalance": imbalance,
                    "mode": "legacy",
                },
            )
        if direction == "short" and self.require_ask_stacking:
            if bid_stacking and not (large_ask or ask_thinning):
                return ConfirmationResult(
                    confirmed=False,
                    pattern_name="l2_confirm",
                    strength=0.0,
                    reason="short requires ask_stacking; bid_stacking present, no ask signal",
                    metadata={
                        "direction": direction,
                        "bid_stacking": bid_stacking,
                        "large_ask": large_ask,
                        "ask_thinning": ask_thinning,
                        "mode": "legacy",
                    },
                )

        stack_bonus = 0.0
        if direction == "long":
            if bid_stacking:
                stack_bonus += 0.5
            if large_bid:
                stack_bonus += 0.25
            if large_ask:
                stack_bonus -= 0.25
        else:
            if not bid_stacking:
                stack_bonus += 0.25
            if large_ask:
                stack_bonus += 0.5
            if ask_thinning:
                stack_bonus += 0.25
            if large_bid:
                stack_bonus -= 0.25
        stack_bonus = max(0.0, min(1.0, stack_bonus))
        strength = round(0.6 * imb_strength + 0.4 * stack_bonus, 4)

        return ConfirmationResult(
            confirmed=True,
            pattern_name="l2_confirm",
            strength=strength,
            reason=(
                f"{direction} L2 ok: imbalance={imbalance:.2f}, "
                f"spread_pct={spread_pct if spread_pct is not None else 'n/a'}, "
                f"bid_stacking={bid_stacking}, large_bid={large_bid}, "
                f"large_ask={large_ask}"
            ),
            metadata={
                "direction": direction,
                "imbalance": imbalance,
                "spread_pct": spread_pct,
                "bid_stacking": bid_stacking,
                "large_bid": large_bid,
                "large_ask": large_ask,
                "ask_thinning": ask_thinning,
                "mode": "legacy",
            },
        )
