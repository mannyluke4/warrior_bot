"""hwm_exit.py — High-Water-Mark trailing exit for MOVE_STRIKE positions.

Ported from simulate.py's `_hwm_exit` (2026-05-20). Self-contained so it
can be used by both the simulator and the live sub-bot.

Exit logic (per tick), in order:
  1. Hard stop      — price <= stop  → exit "move_hard_stop"
  2. Stop-proximity — pre-activation, if cum_low has crept within
                      prox_pct of R from the stop, bail. Distinguishes
                      slow consolidations from dying-loser positions.
  3. No-activation  — pre-activation backstop after N minutes without
                      reaching the gain threshold.
  4. HWM trail      — post-activation: peak - dd × (peak - entry).
                      Adaptive: widens to wide_dd once N consecutive
                      higher-high bars confirm sustained momentum.

State requirements on the position object:
  pos.entry          — fill price
  pos.stop           — protective stop (= cons-low at entry)
  pos.peak           — highest price seen since entry (updated by caller)
  pos.cum_low        — lowest price seen since entry (updated by caller)
  pos.entry_time_min — entry time as minutes-since-midnight (int)
  pos.hh_count       — consecutive higher-high bars (caller updates on
                       bar close)

Bar tracking (HH count) lives on the caller because bar-close events
come from a separate channel than ticks.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple


class HWMExitConfig:
    """Reads env-var config once at construction. Pass instance into
    `evaluate()`; one config can manage many positions."""

    def __init__(self):
        self.drawdown_pct = float(os.getenv("WB_BT_MOVE_HWM_DRAWDOWN_PCT", "0.25"))
        self.wide_dd_pct = float(os.getenv("WB_BT_MOVE_HWM_WIDE_DD_PCT", "0.50"))
        self.hh_threshold = int(os.getenv("WB_BT_MOVE_HWM_HH_THRESHOLD", "2"))
        self.min_gain_pct = float(os.getenv("WB_BT_MOVE_HWM_MIN_GAIN_PCT", "2.0"))
        self.noact_minutes = float(os.getenv("WB_BT_MOVE_HWM_NOACT_MIN", "30"))
        self.stop_prox_pct = (
            float(os.getenv("WB_BT_MOVE_HWM_STOP_PROX_PCT", "25")) / 100.0
        )
        self.wide_gain_pct = float(os.getenv("WB_BT_MOVE_HWM_WIDE_GAIN_PCT", "0"))


def evaluate(
    pos,
    price: float,
    now_min: int,
    cfg: HWMExitConfig,
) -> Optional[Tuple[str, float]]:
    """Check this position against the HWM exit rules.

    Returns ``(reason, exit_price)`` if the position should exit, else None.
    Caller is responsible for actually closing the position.

    Args:
      pos:      object with .entry, .stop, .peak, .cum_low, .entry_time_min,
                .hh_count attributes (or dict-like with same keys).
      price:    current tick price.
      now_min:  current ET minute-of-day (hour*60+minute).
      cfg:      HWMExitConfig instance.
    """
    # Compatibility: accept either object attrs or dict keys.
    def _get(attr, default=None):
        if hasattr(pos, attr):
            return getattr(pos, attr)
        if isinstance(pos, dict):
            return pos.get(attr, default)
        return default

    entry = float(_get("entry", 0))
    stop = float(_get("stop", 0))
    peak = float(_get("peak", entry))
    cum_low = float(_get("cum_low", entry))
    entry_time_min = int(_get("entry_time_min", now_min))
    hh_count = int(_get("hh_count", 0))

    # 1) Hard stop
    if price <= stop:
        return ("move_hard_stop", price)

    # Pre-activation gates (steps 2 + 3)
    gain = peak - entry
    r = entry - stop
    gain_pct = (gain / entry * 100.0) if (gain > 0 and entry > 0) else 0.0
    below_threshold = gain_pct < cfg.min_gain_pct

    if below_threshold and r > 0 and cfg.stop_prox_pct > 0:
        buffer_to_stop = cum_low - stop
        prox_threshold = cfg.stop_prox_pct * r
        if buffer_to_stop <= prox_threshold:
            reason = (
                f"move_stop_prox_bail(low={cum_low:.2f},"
                f"stop={stop:.2f},buf={buffer_to_stop:.3f})"
            )
            return (reason, price)

    if below_threshold:
        held_min = now_min - entry_time_min
        if held_min >= cfg.noact_minutes:
            return (f"move_noact_bail({int(held_min)}min)", price)
        return None  # hold

    # 4) Post-activation HWM trail (adaptive)
    widen_by_hh = hh_count >= cfg.hh_threshold
    widen_by_gain = (cfg.wide_gain_pct > 0 and gain_pct >= cfg.wide_gain_pct)
    effective_dd = cfg.wide_dd_pct if (widen_by_hh or widen_by_gain) else cfg.drawdown_pct
    trail_level = peak - effective_dd * gain
    if price <= trail_level:
        reason = (
            f"move_hwm_exit(peak={peak:.2f},"
            f"dd={int(effective_dd*100)}%,hh={hh_count})"
        )
        return (reason, price)

    return None
