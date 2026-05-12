"""chop_gate_v3.py — modular second-layer chop gate for Wave Breakout entries.

Architecture (per DIRECTIVE_CHOP_GATE_V3_MODULAR_ROLLOUT.md, 2026-05-12):

    chop_gate_v3 = OR-of-enabled parallel sub-gates
       - sub_gate_macd               (env: WB_CG3_MACD_ENABLED)
       - sub_gate_hod_recent         (env: WB_CG3_HOD_RECENT_ENABLED)
       - sub_gate_dead_bounce        (env: WB_CG3_DEAD_BOUNCE_ENABLED)
       - sub_gate_vol_followthrough  (env: WB_CG3_VOL_FT_ENABLED)
       - sub_gate_xsession_bl        (env: WB_CG3_XSESSION_BL_ENABLED)

    decision: BLOCK iff any ENABLED sub-gate vetoes.

All sub-gates always *compute* and always *log* their metric so we collect
evidence on disabled sub-gates ([CG3_OBSERVE] lines). Only the enabled
sub-gates can veto.

Master kill switch is `WB_CHOP_GATE_V3_ENABLED` (still owned by the caller —
this module assumes the caller has already short-circuited when the master
is off).

Backwards-compat: the older monolithic env knobs (WB_V3_HOD_LOOKBACK_MINUTES,
WB_V3_HOD_FAIL_THRESHOLD, WB_V3_VOL_LOOKBACK_BARS, etc.) are kept as defaults
underneath the new sub-gate-specific knobs, so flipping a sub-gate to
enabled=1 reuses the proven thresholds unless the caller overrides them.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple


# ══════════════════════════════════════════════════════════════════════
# Env helpers
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


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip() not in ("", "0", "false", "False", "no", "NO")


# Enable-flag accessors (read at *call* time so the validate script can
# toggle them inside a single process without re-importing).
def _enabled_macd() -> bool:
    return _env_bool("WB_CG3_MACD_ENABLED", True)


def _enabled_hod_recent() -> bool:
    return _env_bool("WB_CG3_HOD_RECENT_ENABLED", False)


def _enabled_dead_bounce() -> bool:
    return _env_bool("WB_CG3_DEAD_BOUNCE_ENABLED", False)


def _enabled_vol_ft() -> bool:
    return _env_bool("WB_CG3_VOL_FT_ENABLED", False)


def _enabled_xsession_bl() -> bool:
    return _env_bool("WB_CG3_XSESSION_BL_ENABLED", False)


# ══════════════════════════════════════════════════════════════════════
# Bar helpers — tolerate dict OR Bar object
# ══════════════════════════════════════════════════════════════════════


def _bar_attr(bar: Any, name: str) -> float:
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


def _bar_ts(bar: Any) -> Optional[datetime]:
    """Return a tz-aware datetime for the bar start, or None if absent.

    Supports start_utc (engine), start_ts (subbot dicts), and timestamp
    (legacy). All returns are normalised to UTC.
    """
    if bar is None:
        return None
    for attr in ("start_utc", "start_ts", "timestamp", "ts"):
        v = bar.get(attr) if isinstance(bar, dict) else getattr(bar, attr, None)
        if v is None:
            continue
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)):
            try:
                return datetime.fromtimestamp(float(v), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(v, str):
            try:
                dt = datetime.fromisoformat(v)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


# ══════════════════════════════════════════════════════════════════════
# Indicator helpers
# ══════════════════════════════════════════════════════════════════════


def consecutive_lower_closes(bars: List[Any]) -> int:
    """Length of the leading streak of strictly-decreasing closes.

    Walks forward from bars[0]: counts bars whose close is < the previous
    bar's close. Stops at the first non-decreasing bar. (Returns the count
    of *decreasing* bars after bars[0].)
    """
    if not bars or len(bars) < 2:
        return 0
    streak = 0
    prev = _bar_attr(bars[0], "close")
    for b in bars[1:]:
        cl = _bar_attr(b, "close")
        if cl < prev:
            streak += 1
            prev = cl
        else:
            break
    return streak


def compute_atr(bars: List[Any], period: int = 14) -> float:
    """Standard ATR over the trailing `period` bars (Wilder-equivalent
    simple average of true ranges). Returns 0.0 when there isn't enough
    history."""
    if not bars or len(bars) < 2:
        return 0.0
    period = max(1, int(period))
    trs: List[float] = []
    prev_close = _bar_attr(bars[0], "close")
    for b in bars[1:]:
        h = _bar_attr(b, "high")
        l = _bar_attr(b, "low")
        tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = _bar_attr(b, "close")
    if not trs:
        return 0.0
    window = trs[-period:]
    return sum(window) / len(window)


def vwap_slope_positive_15m(bars_1m: List[Any]) -> bool:
    """True iff a linear-regression slope of running VWAP over the last
    15 1m bars is positive.

    VWAP is computed from `vwap` on the bar if present (engine bars carry
    it), else as a session-cumulative typical-price-weighted average from
    the bars supplied. Fail-safe to False (no signal → discriminator not
    met) on too-little history.
    """
    if not bars_1m or len(bars_1m) < 2:
        return False
    recent = bars_1m[-15:] if len(bars_1m) >= 15 else list(bars_1m)
    if len(recent) < 2:
        return False

    # Prefer the bar's own vwap field when populated.
    vw_series: List[float] = []
    have_field = False
    for b in recent:
        v = b.get("vwap") if isinstance(b, dict) else getattr(b, "vwap", None)
        if v is not None:
            try:
                vw_series.append(float(v))
                have_field = True
                continue
            except (TypeError, ValueError):
                pass
        # Fall through to typical price; we'll convert to cumulative VWAP below.
        vw_series.append(0.0)

    if not have_field:
        # Cumulative typical-price VWAP over the WHOLE supplied window
        # (not just the last 15), so the "running VWAP" we slope-fit is
        # the same one the bot would have seen at arm time. Stop when we
        # reach the most-recent bar; emit the trailing 15 values for the
        # regression.
        cum_pv = 0.0
        cum_v = 0.0
        running: List[float] = []
        for b in bars_1m:
            h = _bar_attr(b, "high")
            l = _bar_attr(b, "low")
            cl = _bar_attr(b, "close")
            v = _bar_attr(b, "volume")
            tp = (h + l + cl) / 3.0 if (h or l or cl) else cl
            cum_pv += tp * v
            cum_v += v
            running.append(cum_pv / cum_v if cum_v > 0 else tp)
        vw_series = running[-15:] if len(running) >= 15 else running
        if len(vw_series) < 2:
            return False

    # Linear regression slope, simple.
    n = len(vw_series)
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(vw_series) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, vw_series))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return False
    slope = num / den
    return slope > 0.0


def macd_curling_up(macd_state: Any) -> bool:
    """True iff MACD histogram is negative but RISING for the last 2 bars.

    i.e. hist values [h(2ago), h(1ago), h(now)] satisfy
        h(2ago) < h(1ago) < h(now)  AND  h(now) < 0

    Returns False if MACD history isn't deep enough.
    """
    if macd_state is None:
        return False
    has_history = getattr(macd_state, "has_history", None)
    if not callable(has_history) or not has_history(bars=3):
        return False
    h0 = macd_state.histogram_at(0)
    h1 = macd_state.histogram_at(1)
    h2 = macd_state.histogram_at(2)
    if h0 is None or h1 is None or h2 is None:
        return False
    return h0 < 0 and h2 < h1 < h0


def price_below_midrange(bars_1m: List[Any]) -> bool:
    """True iff current price (= last bar's close) is below the midpoint
    of the session HOD and LOD."""
    if not bars_1m:
        return False
    hod = max(_bar_attr(b, "high") for b in bars_1m)
    lod = min(_bar_attr(b, "low") for b in bars_1m if _bar_attr(b, "low") > 0)
    if hod <= 0 or lod <= 0 or hod <= lod:
        return False
    mid = (hod + lod) / 2.0
    cur = _bar_attr(bars_1m[-1], "close")
    return cur < mid


# ══════════════════════════════════════════════════════════════════════
# Metric primitives kept from v1 (used by sub-gates below)
# ══════════════════════════════════════════════════════════════════════


def _hod_fail_threshold() -> int:
    return _env_int("WB_V3_HOD_FAIL_THRESHOLD", 2)


def _hod_recent_lookback_min() -> int:
    return _env_int("WB_CG3_HOD_RECENT_LOOKBACK_MIN", 60)


def _vol_lookback_bars() -> int:
    return _env_int("WB_V3_VOL_LOOKBACK_BARS", 10)


def _vol_followthrough_min_pct() -> float:
    return _env_float("WB_V3_VOL_FOLLOWTHROUGH_MIN_PCT", 0.30)


def _breakout_body_min_pct() -> float:
    return _env_float("WB_V3_BREAKOUT_BODY_MIN_PCT", 0.015)


def _breakout_vol_min_mult() -> float:
    return _env_float("WB_V3_BREAKOUT_VOL_MIN_MULT", 3.0)


def _count_hod_rejects_in_window(
    bars_1m: List[Any], lookback_minutes: int,
) -> int:
    """Count distinct attempts at session HOD within the trailing
    `lookback_minutes` that got rejected.

    An 'attempt' is a bar within lookback whose high reached within 1%
    of session HOD. A 'rejection' means all 3 subsequent bars closed
    >0.5% below the attempt's high. Skips 3 bars after each attempt so
    one rejection isn't counted twice.
    """
    if not bars_1m or len(bars_1m) < 4:
        return 0

    # Session HOD across all bars (the bot keeps session-scoped bar history).
    hod = max((_bar_attr(b, "high") for b in bars_1m), default=0.0)
    if hod <= 0:
        return 0

    # Slice to the trailing window. We approximate "minutes" by bar count
    # because the bars are 1-minute. When bars carry timestamps, prefer
    # the timestamp filter.
    last_ts = _bar_ts(bars_1m[-1])
    if last_ts is not None:
        cutoff = last_ts.timestamp() - (lookback_minutes * 60)
        recent = [b for b in bars_1m if (_bar_ts(b) or last_ts).timestamp() >= cutoff]
    else:
        recent = (
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
            nxt3 = recent[i + 1 : i + 4]
            if (
                len(nxt3) == 3
                and all(_bar_attr(b, "close") < bar_high * 0.995 for b in nxt3)
            ):
                attempts += 1
                i += 4
                continue
        i += 1
    return attempts


# Legacy public-API surface — kept for the existing validate script
# (which imports these names directly).
def failed_hod_attempts(
    bars_1m: List[Any], lookback_minutes: Optional[int] = None,
) -> int:
    """Legacy whole-session HOD-failure count (lookback default 120min).
    Preserved for backwards compatibility with v1 validation script."""
    if lookback_minutes is None:
        lookback_minutes = _env_int("WB_V3_HOD_LOOKBACK_MINUTES", 120)
    return _count_hod_rejects_in_window(bars_1m, lookback_minutes)


def macd_rolling_over(macd_state: Any) -> bool:
    """MACD curling over (legacy primitive used by sub_gate_macd)."""
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

    if any(v is None for v in (
        line_now, line_2ago, sig_now, sig_2ago,
        hist_now, hist_1ago, hist_2ago,
    )):
        return False

    crossed_down = (line_2ago > sig_2ago) and (line_now < sig_now)
    decreasing_from_positive = (
        hist_2ago > 0 and hist_2ago > hist_1ago > hist_now
    )
    return crossed_down or decreasing_from_positive


def has_volume_followthrough(
    bars_1m: List[Any], lookback: Optional[int] = None,
) -> bool:
    """Legacy primitive — used by sub_gate_vol_followthrough."""
    if lookback is None:
        lookback = _vol_lookback_bars()
    if not bars_1m or len(bars_1m) < lookback + 2:
        return True
    body_min_pct = _breakout_body_min_pct()
    vol_min_mult = _breakout_vol_min_mult()
    followthrough_min_pct = _vol_followthrough_min_pct()

    recent = list(bars_1m[-(lookback + 2):])
    eval_window = recent[:-2]
    if not eval_window:
        return True
    avg_vol = sum(_bar_attr(b, "volume") for b in eval_window) / len(eval_window)
    if avg_vol <= 0:
        return True

    for i in range(len(eval_window) - 1, -1, -1):
        bar = eval_window[i]
        op = _bar_attr(bar, "open")
        cl = _bar_attr(bar, "close")
        vol = _bar_attr(bar, "volume")
        body_pct = abs(cl - op) / op if op > 0 else 0.0
        if body_pct >= body_min_pct and vol >= vol_min_mult * avg_vol:
            next2 = recent[i + 1 : i + 3]
            if len(next2) >= 2 and vol > 0:
                if all(
                    _bar_attr(b, "volume") < followthrough_min_pct * vol
                    for b in next2
                ):
                    return False
            return True
    return True


# ══════════════════════════════════════════════════════════════════════
# SessionHistory singleton wiring (lazy)
# ══════════════════════════════════════════════════════════════════════


_session_history = None


def _get_session_history():
    global _session_history
    if _session_history is None:
        from session_history import SessionHistory
        _session_history = SessionHistory()
    return _session_history


def _set_session_history(history) -> None:
    """Test/replay hook — inject a SessionHistory instance."""
    global _session_history
    _session_history = history


# ══════════════════════════════════════════════════════════════════════
# Sub-gates (pure functions: (passes, reason))
# ══════════════════════════════════════════════════════════════════════


def sub_gate_macd(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    session_history: Any,
    today: str,
) -> Tuple[bool, str]:
    """Veto when MACD is in early bearish curl-over phase."""
    if macd_rolling_over(macd_state):
        return False, "macd_rolling_over"
    return True, "macd_ok"


def sub_gate_hod_recent(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    session_history: Any,
    today: str,
) -> Tuple[bool, str]:
    """Veto on recent HOD failures unless current setup is bottom-fishing.

    Recent = within trailing WB_CG3_HOD_RECENT_LOOKBACK_MIN (default 60 min).
    Discriminators (any 2 of 3 → not a re-attempt, pass):
       - VWAP slope positive over last 15 min
       - MACD histogram curling up (negative-and-rising)
       - Price < (HOD + LOD) / 2 (true bottom-fishing arms from below mid)
    """
    lookback = _hod_recent_lookback_min()
    fail_thresh = _hod_fail_threshold()
    n_recent = _count_hod_rejects_in_window(bars_1m, lookback)
    if n_recent < fail_thresh:
        return True, f"hod_recent_ok({n_recent}<{fail_thresh})"

    disc_vwap = vwap_slope_positive_15m(bars_1m)
    disc_macd = macd_curling_up(macd_state)
    disc_mid = price_below_midrange(bars_1m)
    discriminators_met = int(disc_vwap) + int(disc_macd) + int(disc_mid)

    if discriminators_met >= 2:
        return (
            True,
            f"hod_recent_attempts={n_recent}_but_bottom_fish"
            f"(vwap={'Y' if disc_vwap else 'N'},"
            f"macd_up={'Y' if disc_macd else 'N'},"
            f"below_mid={'Y' if disc_mid else 'N'})",
        )
    return (
        False,
        f"hod_recent_attempts={n_recent}_no_bottom_fish"
        f"(vwap={'Y' if disc_vwap else 'N'},"
        f"macd_up={'Y' if disc_macd else 'N'},"
        f"below_mid={'Y' if disc_mid else 'N'})",
    )


def sub_gate_dead_bounce(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    session_history: Any,
    today: str,
) -> Tuple[bool, str]:
    """Veto when the chart shape is 'stock died slow + weak technical bounce'.

    All 4 conditions must be met for veto:
      1) HOD set in first 90 min of session (configurable)
      2) >= 5 consecutive lower closes after HOD bar OR cum_drift > 1.5 * ATR
      3) Current price hasn't reclaimed midpoint of (HOD, drift_low)
      4) Bounce volume < 0.7 * drift volume
    """
    hod_max_age_min = _env_int("WB_CG3_DEAD_BOUNCE_HOD_MAX_AGE_MIN", 90)
    drift_min_bars = _env_int("WB_CG3_DEAD_BOUNCE_DRIFT_MIN_BARS", 5)
    atr_mult = _env_float("WB_CG3_DEAD_BOUNCE_ATR_MULT", 1.5)
    vol_ratio_max = _env_float("WB_CG3_DEAD_BOUNCE_VOL_RATIO_MAX", 0.7)

    if not bars_1m or len(bars_1m) < drift_min_bars + 2:
        return True, "dead_bounce_no_data"

    # 1) HOD set early?
    hod_idx = max(range(len(bars_1m)), key=lambda i: _bar_attr(bars_1m[i], "high"))
    hod_high = _bar_attr(bars_1m[hod_idx], "high")
    if hod_high <= 0:
        return True, "dead_bounce_no_hod"

    # "Age of HOD" is measured from the session OPEN (09:30 ET), not from
    # the first bar in the cache (which is typically 04:00 ET premarket).
    # Premarket HOD set in the first 90 min of *premarket* would otherwise
    # look "late" by clock time even though the stock just opened heavy.
    hod_ts = _bar_ts(bars_1m[hod_idx])
    first_ts = _bar_ts(bars_1m[0])
    session_start = None
    if hod_ts is not None:
        # Convert to ET to anchor 09:30 RTH-start.
        try:
            from zoneinfo import ZoneInfo
            _ET = ZoneInfo("America/New_York")
            hod_et = hod_ts.astimezone(_ET)
            session_start_et = hod_et.replace(hour=9, minute=30, second=0, microsecond=0)
            # If HOD is in premarket, treat premarket open as session_start so
            # an early-PM HOD still counts as "early".
            if hod_et < session_start_et:
                if first_ts is not None:
                    session_start = first_ts
                else:
                    session_start = hod_ts
            else:
                session_start = session_start_et.astimezone(timezone.utc)
        except Exception:
            session_start = first_ts
    if hod_ts is not None and session_start is not None:
        hod_age_min = (hod_ts - session_start).total_seconds() / 60.0
        if hod_age_min < 0:
            # Earlier than our chosen anchor (shouldn't happen after the
            # branch above, but be defensive).
            hod_age_min = 0.0
    else:
        hod_age_min = float(hod_idx)  # 1 bar ~= 1 minute

    if hod_age_min > hod_max_age_min:
        return True, f"dead_bounce_hod_not_early(age={hod_age_min:.0f}m)"

    # 2) Sustained drift after HOD?
    post_hod = bars_1m[hod_idx + 1:]
    if not post_hod:
        return True, "dead_bounce_no_post_hod"
    drift_streak = consecutive_lower_closes(post_hod)
    drift_low = min(_bar_attr(b, "low") for b in post_hod if _bar_attr(b, "low") > 0) \
        if any(_bar_attr(b, "low") > 0 for b in post_hod) else 0.0
    cum_drift = hod_high - drift_low if drift_low > 0 else 0.0
    atr = compute_atr(bars_1m, period=14)
    if drift_streak < drift_min_bars and (atr <= 0 or cum_drift < atr_mult * atr):
        return True, (
            f"dead_bounce_no_drift(streak={drift_streak}<{drift_min_bars},"
            f"drift=${cum_drift:.2f},atr=${atr:.2f})"
        )

    # 3) Bounce hasn't reclaimed midpoint?
    midpoint = (hod_high + drift_low) / 2.0 if drift_low > 0 else hod_high
    current_price = _bar_attr(bars_1m[-1], "close")
    if current_price >= midpoint:
        return True, f"dead_bounce_reclaimed(price=${current_price:.2f}>=mid=${midpoint:.2f})"

    # 4) Bounce volume vs drift volume?
    bounce_window = bars_1m[-5:]
    bounce_vol = sum(_bar_attr(b, "volume") for b in bounce_window)
    drift_window = post_hod[:max(drift_streak, drift_min_bars)]
    drift_vol = sum(_bar_attr(b, "volume") for b in drift_window)
    if drift_vol <= 0:
        return True, "dead_bounce_no_drift_volume"
    vol_ratio = bounce_vol / drift_vol
    if vol_ratio >= vol_ratio_max:
        return True, f"dead_bounce_strong_volume(ratio={vol_ratio:.2f}>= {vol_ratio_max:.2f})"

    return False, (
        f"dead_bounce_pattern(drift={drift_streak},"
        f"cum=${cum_drift:.2f},vol_ratio={vol_ratio:.2f})"
    )


def sub_gate_vol_followthrough(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    session_history: Any,
    today: str,
) -> Tuple[bool, str]:
    """Veto when the most recent breakout-sized bar lacks follow-through volume."""
    if has_volume_followthrough(bars_1m):
        return True, "vol_ft_ok"
    return False, "no_volume_followthrough"


def sub_gate_xsession_bl(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    session_history: Any,
    today: str,
) -> Tuple[bool, str]:
    """Veto when symbol has bled R-multiple AND lost more than 2x its wins
    across the last WB_CG3_XSESSION_LOOKBACK_DAYS days (excluding today).

    Rule (R-sum AND win-rate-ratio):
        r_sum < 0  AND  losses > 2 * wins
        AND len(trades) >= WB_CG3_XSESSION_MIN_TRADES
    """
    lookback_days = _env_int("WB_CG3_XSESSION_LOOKBACK_DAYS", 7)
    min_trades = _env_int("WB_CG3_XSESSION_MIN_TRADES", 3)

    history = session_history if session_history is not None else _get_session_history()
    if history is None:
        return True, "xbl_no_history"

    # Pull trades. SessionHistory.get_trades is the new contract per the
    # directive; we fall back to its raw store if get_trades isn't present
    # so we degrade gracefully across the two code paths.
    trades = []
    if hasattr(history, "get_trades"):
        try:
            trades = history.get_trades(
                symbol, lookback_days=lookback_days, exclude_today=today,
            )
        except Exception:
            trades = []
    else:
        entry = getattr(history, "_data", {}).get(symbol) if hasattr(history, "_data") else None
        if entry:
            trades = list(entry.get("trades", []))
            # Exclude today's trades.
            trades = [t for t in trades if str(t.get("date")) != str(today)]

    if len(trades) < min_trades:
        return True, f"xbl_insufficient_history({len(trades)}<{min_trades})"

    r_sum = 0.0
    wins = 0
    losses = 0
    for t in trades:
        try:
            r = float(t.get("r_multiple") if isinstance(t, dict) else getattr(t, "r_multiple", 0.0))
        except (TypeError, ValueError):
            r = 0.0
        try:
            p = float(t.get("pnl") if isinstance(t, dict) else getattr(t, "pnl", 0.0))
        except (TypeError, ValueError):
            p = 0.0
        r_sum += r
        if p > 0:
            wins += 1
        else:
            losses += 1

    if r_sum < 0 and losses > 2 * wins:
        return (
            False,
            f"xbl_blacklist(rsum={r_sum:+.2f},w={wins},l={losses})",
        )
    return True, f"xbl_ok(rsum={r_sum:+.2f},w={wins},l={losses})"


# ══════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════


_SUB_GATES = (
    ("macd",              sub_gate_macd,              _enabled_macd),
    ("hod_recent",        sub_gate_hod_recent,        _enabled_hod_recent),
    ("dead_bounce",       sub_gate_dead_bounce,       _enabled_dead_bounce),
    ("vol_followthrough", sub_gate_vol_followthrough, _enabled_vol_ft),
    ("xsession_bl",       sub_gate_xsession_bl,       _enabled_xsession_bl),
)


def chop_gate_v3(
    symbol: str,
    bars_1m: List[Any],
    macd_state: Any,
    today: str,
) -> Tuple[bool, str]:
    """Modular orchestrator. Each sub-gate runs (for telemetry).
    Only enabled sub-gates can veto. Returns (passes, reason); passes=False
    on the FIRST enabled veto.

    Disabled sub-gates emit observe-only [CG3_OBSERVE] log lines so we keep
    collecting evidence on them.
    """
    history = _get_session_history()
    results = []
    for name, fn, enabled_fn in _SUB_GATES:
        enabled = enabled_fn()
        try:
            passes, reason = fn(symbol, bars_1m, macd_state, history, today)
        except Exception as e:
            # A bug in one sub-gate must not block other sub-gates from
            # running and must not block the entry (fail-OPEN).
            passes, reason = True, f"error:{e!r}"
        results.append((name, passes, reason, enabled))
        try:
            print(
                f"[CG3_OBSERVE] symbol={symbol} sub={name} value={reason} "
                f"would_veto={'Y' if not passes else 'N'} "
                f"enabled={'Y' if enabled else 'N'}",
                flush=True,
            )
        except Exception:
            pass

    for name, passes, reason, enabled in results:
        if enabled and not passes:
            return False, f"{name}:{reason}"
    return True, "passed_all_enabled"


__all__ = [
    # Orchestrator
    "chop_gate_v3",
    # Sub-gates
    "sub_gate_macd",
    "sub_gate_hod_recent",
    "sub_gate_dead_bounce",
    "sub_gate_vol_followthrough",
    "sub_gate_xsession_bl",
    # Helpers
    "consecutive_lower_closes",
    "compute_atr",
    "vwap_slope_positive_15m",
    "macd_curling_up",
    "price_below_midrange",
    # Legacy primitives (used by validate_chop_gate_v3 + bot wiring)
    "failed_hod_attempts",
    "macd_rolling_over",
    "has_volume_followthrough",
    "_set_session_history",
]
