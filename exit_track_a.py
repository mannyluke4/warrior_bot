"""exit_track_a.py — Phase 4 Track A exit framework.

Per cowork_reports/2026-05-28_track_a_exit_framework_spec.md.

Self-contained helpers for an env-gated exit framework that applies to
sub-bot positions (firestorm_trigger and regime_shift). Three components:

  1. R floor on stop placement (sizing)
  2. Phased drawdown floor (philosophy, age-graduated)
  3. Force-flatten before close

When WB_EXIT_TRACK_A_ENABLED=0 (the default), every helper here is a
no-op pass-through. Callers should branch on `track_a_enabled()` before
invoking the helpers; the helpers themselves also short-circuit so that
double-checks are safe.

Env contract (read once via cached module-level helpers):

  WB_EXIT_TRACK_A_ENABLED       — master gate (default "0")
  WB_EXIT_R_FLOOR_ABS           — min absolute R in dollars (default 0.10)
  WB_EXIT_R_FLOOR_PCT           — min R as % of entry price (default 0.05)
  WB_EXIT_DD_PHASE1_MAX_MIN     — phase-1 boundary in minutes (default 15)
  WB_EXIT_DD_PHASE1_PCT         — phase-1 drawdown threshold (default 0.50)
  WB_EXIT_DD_PHASE2_MAX_MIN     — phase-2 boundary (default 45)
  WB_EXIT_DD_PHASE2_PCT         — phase-2 drawdown threshold (default 0.30)
  WB_EXIT_DD_PHASE3_PCT         — phase-3 drawdown threshold (default 0.20)
  WB_EXIT_FORCE_FLATTEN_TIME    — ET HH:MM force-flatten time (default 15:30)

The helpers do not import anything from move_strike_subbot / simulate_subbot.
Callers pass scalar args.
"""

from __future__ import annotations

import os
from typing import Optional


def _getenv_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def _getenv_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def track_a_enabled() -> bool:
    """True iff WB_EXIT_TRACK_A_ENABLED=1. Cheap; safe to call per tick."""
    return os.getenv("WB_EXIT_TRACK_A_ENABLED", "0") == "1"


# ─────────────────────────────────────────────────────────────────────
# Component 1: R floor on stop placement
# ─────────────────────────────────────────────────────────────────────

def compute_stop_with_r_floor(
    entry: float,
    raw_stop: float,
) -> tuple[float, float]:
    """Return (stop, R). When Track A is enabled, widens the stop so that
    R is at least max(WB_EXIT_R_FLOOR_ABS, entry * WB_EXIT_R_FLOOR_PCT).
    Otherwise returns the raw stop unchanged.

    Caller is responsible for downstream qty adjustment (a wider R means
    fewer shares for the same dollar risk budget).
    """
    if not track_a_enabled():
        return raw_stop, entry - raw_stop
    r_floor_abs = _getenv_float("WB_EXIT_R_FLOOR_ABS", 0.10)
    r_floor_pct = _getenv_float("WB_EXIT_R_FLOOR_PCT", 0.05)
    raw_r = entry - raw_stop
    min_r = max(r_floor_abs, entry * r_floor_pct)
    if raw_r >= min_r:
        return raw_stop, raw_r
    # Widen stop to meet R floor.
    widened_stop = entry - min_r
    return widened_stop, min_r


# ─────────────────────────────────────────────────────────────────────
# Component 2: Phased drawdown floor
# ─────────────────────────────────────────────────────────────────────

def phased_drawdown_threshold(age_minutes: float) -> float:
    """Return the drawdown threshold (as decimal fraction) for a position
    of the given age. The three phases default to 50% / 30% / 20% with
    boundaries at 15 / 45 minutes; configurable via env vars.

    Returns 0.0 when Track A is disabled (caller should branch on
    track_a_enabled() before relying on this, but defensive 0 here means
    the caller's `drawdown >= 0.0` check would always fire — caller MUST
    short-circuit when track_a_enabled() is False).
    """
    if not track_a_enabled():
        return 0.0
    p1_max = _getenv_int("WB_EXIT_DD_PHASE1_MAX_MIN", 15)
    p2_max = _getenv_int("WB_EXIT_DD_PHASE2_MAX_MIN", 45)
    p1_pct = _getenv_float("WB_EXIT_DD_PHASE1_PCT", 0.50)
    p2_pct = _getenv_float("WB_EXIT_DD_PHASE2_PCT", 0.30)
    p3_pct = _getenv_float("WB_EXIT_DD_PHASE3_PCT", 0.20)
    if age_minutes < p1_max:
        return p1_pct
    if age_minutes < p2_max:
        return p2_pct
    return p3_pct


def phase_label_for_age(age_minutes: float) -> str:
    """For logging — return 'p1' / 'p2' / 'p3' based on age."""
    p1_max = _getenv_int("WB_EXIT_DD_PHASE1_MAX_MIN", 15)
    p2_max = _getenv_int("WB_EXIT_DD_PHASE2_MAX_MIN", 45)
    if age_minutes < p1_max:
        return "p1"
    if age_minutes < p2_max:
        return "p2"
    return "p3"


# ─────────────────────────────────────────────────────────────────────
# Component 3: Force-flatten time
# ─────────────────────────────────────────────────────────────────────

def force_flatten_minute() -> Optional[int]:
    """Return the ET minute-of-day after which positions should be
    force-flattened. None if Track A is disabled OR the env var is unset/
    invalid."""
    if not track_a_enabled():
        return None
    raw = os.getenv("WB_EXIT_FORCE_FLATTEN_TIME", "15:30").strip()
    if not raw:
        return None
    try:
        h, m = raw.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def should_force_flatten(current_minute_et: int) -> bool:
    """True iff Track A is enabled AND current_minute_et >= force-flatten
    boundary. Caller still must check that the position's setup_type is
    eligible (firestorm_trigger or regime_shift)."""
    f = force_flatten_minute()
    if f is None:
        return False
    return current_minute_et >= f
