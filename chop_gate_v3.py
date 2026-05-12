"""chop_gate_v3.py — second-layer chop gate for Wave Breakout entries.

Runs AFTER chop_gate_v2 (`_check_tradability` in bot_alpaca_subbot.py).
Defaults OFF — gated by WB_CHOP_GATE_V3_ENABLED=1.

Three intraday metrics + one cross-session memory check. All four must
clear for entry to fire. The cross-session veto is a hard veto with no
score-bypass override (per directive lines 311-325): even score>=9
"chop_bypass" setups go through v3.

Per directive 2026-05-12 (DIRECTIVE_CHOP_GATE_V3_BUILD.md). Thresholds
all tunable from .env without code changes.
"""

from __future__ import annotations

import os
from typing import Any, Iterable, List, Optional, Tuple


# ══════════════════════════════════════════════════════════════════════
# Tunable thresholds (read once at import; cheap)
# ══════════════════════════════════════════════════════════════════════

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _hod_lookback_minutes() -> int:
    return _env_int("WB_V3_HOD_LOOKBACK_MINUTES", 120)


def _hod_fail_threshold() -> int:
    return _env_int("WB_V3_HOD_FAIL_THRESHOLD", 2)


def _vol_lookback_bars() -> int:
    return _env_int("WB_V3_VOL_LOOKBACK_BARS", 10)


def _vol_followthrough_min_pct() -> float:
    return _env_float("WB_V3_VOL_FOLLOWTHROUGH_MIN_PCT", 0.30)


def _breakout_body_min_pct() -> float:
    return _env_float("WB_V3_BREAKOUT_BODY_MIN_PCT", 0.015)


def _breakout_vol_min_mult() -> float:
    return _env_float("WB_V3_BREAKOUT_VOL_MIN_MULT", 3.0)


# ══════════════════════════════════════════════════════════════════════
# Helpers (bar attribute access — tolerate dict OR Bar object)
# ══════════════════════════════════════════════════════════════════════


def _bar_attr(bar: Any, name: str) -> float:
    """Read open/high/low/close/volume from either a dict-style record
    (as the WB detector keeps internally) or a Bar dataclass instance.
    Returns 0.0 on miss so a malformed bar can't crash the gate."""
    if bar is None:
        return 0.0
    if isinstance(bar, dict):
        v = bar.get(name)
        if v is None:
            return 0.0
        try:
            return float(v)
        except (TypeError, ValueError):
            return 0.0
    v = getattr(bar, name, None)
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════
# Metric 1 — Failed HOD attempts
# ══════════════════════════════════════════════════════════════════════


def failed_hod_attempts(
    bars_1m: List[Any],
    lookback_minutes: Optional[int] = None,
) -> int:
    """Count distinct attempts at session HOD that got rejected.

    An 'attempt' is a bar whose high reached within 1% of session HOD.
    A 'rejection' means all 3 subsequent bars closed >0.5% below the
    attempt's high. Skips the 3-bar window after each attempt so we
    don't double-count the same rejection.
    """
    if not bars_1m or len(bars_1m) < 4:
        return 0

    if lookback_minutes is None:
        lookback_minutes = _hod_lookback_minutes()

    # Session HOD = max high across ALL bars provided (the bot maintains
    # session-scoped bar history per symbol; this is the relevant HOD).
    hod = 0.0
    for b in bars_1m:
        h = _bar_attr(b, "high")
        if h > hod:
            hod = h
    if hod <= 0:
        return 0

    recent: List[Any] = (
        list(bars_1m[-lookback_minutes:])
        if len(bars_1m) > lookback_minutes
        else list(bars_1m)
    )

    attempts = 0
    i = 0
    while i < len(recent) - 3:
        bar = recent[i]
        bar_high = _bar_attr(bar, "high")
        if bar_high >= hod * 0.99:
            next3 = recent[i + 1 : i + 4]
            # Reject if all 3 next bars closed >0.5% below the attempt high.
            if (
                len(next3) == 3
                and all(_bar_attr(b, "close") < bar_high * 0.995 for b in next3)
            ):
                attempts += 1
                i += 4  # skip the rejection window so we don't double-count
                continue
        i += 1

    return attempts


# ══════════════════════════════════════════════════════════════════════
# Metric 2 — MACD curling over
# ══════════════════════════════════════════════════════════════════════


def macd_rolling_over(macd_state: Any) -> bool:
    """True if MACD is in early bearish curl-over phase.

    Two trigger conditions (OR):
      1. MACD line crossed below signal line in the last 2 bars
      2. Histogram has decreased for 3 consecutive bars while starting positive

    Requires macd_state.has_history(3); returns False if not enough history.
    """
    if macd_state is None:
        return False
    has_history = getattr(macd_state, "has_history", None)
    if not callable(has_history) or not has_history(bars=3):
        return False

    line_now = macd_state.line_at(0)
    line_2ago = macd_state.line_at(2)
    sig_now = macd_state.signal_at(0)
    sig_2ago = macd_state.signal_at(2)
    hist_now = macd_state.histogram_at(0)
    hist_1ago = macd_state.histogram_at(1)
    hist_2ago = macd_state.histogram_at(2)

    if (line_now is None or line_2ago is None or sig_now is None
            or sig_2ago is None or hist_now is None or hist_1ago is None
            or hist_2ago is None):
        return False

    # Trigger 1: MACD line crossed BELOW signal in the last 2 bars.
    crossed_down = (line_2ago > sig_2ago) and (line_now < sig_now)

    # Trigger 2: histogram strictly decreasing 3 bars after being positive.
    decreasing_from_positive = (
        hist_2ago > 0
        and hist_2ago > hist_1ago > hist_now
    )

    return crossed_down or decreasing_from_positive


# ══════════════════════════════════════════════════════════════════════
# Metric 3 — Volume follow-through
# ══════════════════════════════════════════════════════════════════════


def has_volume_followthrough(
    bars_1m: List[Any],
    lookback: Optional[int] = None,
) -> bool:
    """True iff the most-recent breakout-sized bar had at least
    `WB_V3_VOL_FOLLOWTHROUGH_MIN_PCT` (default 30%) follow-through
    volume across the next 2 bars.

    Returns True (no warning) when:
      - bar history is too short to evaluate
      - no breakout-sized bar exists in the lookback window
      - average volume in the eval window is zero
    """
    if lookback is None:
        lookback = _vol_lookback_bars()

    if not bars_1m or len(bars_1m) < lookback + 2:
        return True  # not enough history to make a call

    body_min_pct = _breakout_body_min_pct()
    vol_min_mult = _breakout_vol_min_mult()
    followthrough_min_pct = _vol_followthrough_min_pct()

    recent = list(bars_1m[-(lookback + 2):])
    eval_window = recent[:-2]  # leave room for "next 2"
    if not eval_window:
        return True

    avg_vol = sum(_bar_attr(b, "volume") for b in eval_window) / len(eval_window)
    if avg_vol <= 0:
        return True

    # Walk newest → oldest in the eval window; first breakout-sized bar wins.
    for i in range(len(eval_window) - 1, -1, -1):
        bar = eval_window[i]
        op = _bar_attr(bar, "open")
        cl = _bar_attr(bar, "close")
        vol = _bar_attr(bar, "volume")
        body_pct = abs(cl - op) / op if op > 0 else 0.0
        if body_pct >= body_min_pct and vol >= vol_min_mult * avg_vol:
            next2 = recent[i + 1 : i + 3]
            if len(next2) >= 2 and vol > 0:
                # Fail iff BOTH next bars under the threshold (matches
                # directive skeleton: "each had >= 30% of breakout vol").
                if all(
                    _bar_attr(b, "volume") < followthrough_min_pct * vol
                    for b in next2
                ):
                    return False
            return True

    return True  # no breakout-sized bar found in lookback


# ══════════════════════════════════════════════════════════════════════
# Composite gate (cross-session veto + 3 intraday)
# ══════════════════════════════════════════════════════════════════════


# Lazy SessionHistory singleton — built on first use so importing the
# module is side-effect-free (no state/ dir creation). Validation
# scripts can inject their own instance via _set_session_history.
_session_history = None


def _get_session_history():
    global _session_history
    if _session_history is None:
        # Local import to avoid a module-load-time cycle (session_history
        # imports stdlib only, but keeping this lazy mirrors validate
        # script's ability to swap in a per-replay instance).
        from session_history import SessionHistory
        _session_history = SessionHistory()
    return _session_history


def _set_session_history(history) -> None:
    """Test/replay hook — inject a SessionHistory instance. Used by the
    validate_chop_gate_v3 script to replay history chronologically with
    a controlled state file."""
    global _session_history
    _session_history = history


def chop_gate_v3(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    today: str,
) -> Tuple[bool, str]:
    """Returns (passes, reason).

    Runs AFTER chop_gate_v2 has already passed. Second-layer check.
    All four conditions must clear (cross-session veto + 3 intraday
    metrics) for entry to fire. On block, the reason string is the
    failure cause used in the [CHOP_REJECT_V3] log line.
    """
    # 1) Cross-session veto — hard veto, no override.
    history = _get_session_history()
    is_black, reason = history.is_blacklisted(symbol, today)
    if is_black:
        return False, reason

    # 2-4) Intraday gates (AND logic, all must pass).
    fhc = failed_hod_attempts(bars_1m)
    if fhc >= _hod_fail_threshold():
        return False, f"failed_hod_attempts={fhc}>={_hod_fail_threshold()}"

    if macd_rolling_over(macd_state):
        return False, "macd_rolling_over"

    if not has_volume_followthrough(bars_1m):
        return False, "no_volume_followthrough"

    return True, "passed"


__all__ = [
    "chop_gate_v3",
    "failed_hod_attempts",
    "macd_rolling_over",
    "has_volume_followthrough",
    "_set_session_history",
]
