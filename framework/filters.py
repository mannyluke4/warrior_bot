"""framework.filters — Wave-4 strategy filter helpers (Phase B1).

Centralises the gate logic for the Wave-4 filtered YAML strategies:
  - entry_time_window:  PDH-Fade F1 (09:30-09:44 ET)
  - abandon_rule:       PDH-Fade abandon@10
  - tier_filter:        ORB $300+ tier gate
  - opening_bar_alignment: ORB or5_align ∈ {aligned, doji}
  - skip_mondays:       ORB / framework-wide Monday skip
  - symbol_blacklist:   PDH-Breakout F4 symbol exclusions
  - require_vwap_alignment: PDH-Breakout F4 VWAP alignment
  - pre_entry_consolidation_max_pct: PDH-Breakout F4 5-bar range/price < 1%
  - volume_min_multiple: PDH-Breakout F4 entry-bar vol >= 2x prior-20-bar mean

Each function is a pure predicate: returns True if the signal passes the
filter, False if it must be rejected. The signal evaluator in
backtest/portfolio_backtest.py (and the Wave-4 live filter shim) call
these per signal.

Design source: DIRECTIVE_2026-05-17_GO_FOR_BUILD.md Phase B1.
Forensic references:
  cowork_reports/2026-05-18_pdh_fade_forensic.md
  cowork_reports/2026-05-18_orb_forensic.md
  cowork_reports/2026-05-18_pdh_breakout_forensic.md
"""
from __future__ import annotations

import os
from datetime import datetime, time, timedelta
from typing import Any, Iterable, Optional


# ---------------------------------------------------------------------------
# Time-of-day filter (PDH-Fade F1)
# ---------------------------------------------------------------------------


def _parse_hms(value: str) -> time:
    """Parse 'HH:MM' or 'HH:MM:SS' to a time. Caller has already validated."""
    parts = value.split(":")
    if len(parts) == 2:
        return time(int(parts[0]), int(parts[1]))
    return time(int(parts[0]), int(parts[1]), int(parts[2]))


def passes_entry_time_window(
    entry_ts: datetime, window: Optional[dict[str, Any]]
) -> bool:
    """Return True if entry_ts is within the configured entry-time window.

    Window format: {start: 'HH:MM[:SS]', end: 'HH:MM[:SS]', tz?: str}.
    The tz field is informational for now (timestamps are treated naive ET,
    which matches the backtest convention).

    If window is None or empty, returns True (no gate).
    """
    if not window:
        return True
    start = _parse_hms(window["start"])
    end = _parse_hms(window["end"])
    t = entry_ts.time()
    return start <= t <= end


# ---------------------------------------------------------------------------
# Hold-time abandon rule (PDH-Fade abandon@10)
# ---------------------------------------------------------------------------


def evaluate_abandon_rule(
    entry_ts: datetime,
    entry_price: float,
    direction: str,
    bars_post_entry: list[Any],
    rule: Optional[dict[str, Any]],
) -> Optional[tuple[float, datetime, str]]:
    """Apply the abandon-rule against the post-entry bar stream.

    rule keys (per yaml_schema._validate_filter_extensions):
      - enabled: bool (default True if rule provided)
      - minutes_after_entry: int (required)
      - exit_if_not_profit: bool (default True)
      - exit_cap_dollars: number (informational; capped against per-bar slippage)
      - exit_method: 'limit_aggressive' | ... (informational)

    bars_post_entry is an ordered list of Bar-like objects (must have
    `.timestamp`, `.close`, `.high`, `.low`).

    Returns None if the abandon-rule did NOT fire (caller continues normal
    stop/target replay). Returns (exit_price, exit_ts, 'abandon') if it did.
    """
    if not rule or not rule.get("enabled", True):
        return None
    minutes_after = int(rule["minutes_after_entry"])
    require_profit = bool(rule.get("exit_if_not_profit", True))
    cap_dollars = rule.get("exit_cap_dollars")  # informational

    check_ts = entry_ts + timedelta(minutes=minutes_after)

    # Find the first bar whose timestamp is >= check_ts.
    chosen = None
    for b in bars_post_entry:
        if b.timestamp >= check_ts:
            chosen = b
            break
    if chosen is None:
        return None  # never reached; let session_close logic run

    # Check profitability at minute-N close.
    in_profit = (
        chosen.close > entry_price if direction == "long" else chosen.close < entry_price
    )
    if in_profit:
        return None  # let normal stop/target replay continue
    if not require_profit:
        return None

    # Not in profit — exit at the bar's close with conservative slippage cap.
    exit_px = chosen.close
    if cap_dollars is not None:
        cap = float(cap_dollars)
        # Per-share cap on adverse slippage relative to entry.
        # NOTE: this is a per-trade dollar cap on the loss assumption, NOT a
        # per-share cap. We translate via the position's risk_dollars / qty
        # at the caller. Here we just record the rule's intent on the trade.
        if direction == "long":
            exit_px = max(exit_px, entry_price - cap)
        else:
            exit_px = min(exit_px, entry_price + cap)

    return exit_px, chosen.timestamp, "abandon"


# ---------------------------------------------------------------------------
# Tier filter (ORB tier=$300+)
# ---------------------------------------------------------------------------


def passes_tier_filter(price: float, filt: Optional[dict[str, Any]]) -> bool:
    """Return True if price passes the tier_filter spec.

    filt format: {enabled?: bool, min_price: float, max_price?: float}
    """
    if not filt or not filt.get("enabled", True):
        return True
    min_p = float(filt.get("min_price", 0.0))
    if price < min_p:
        return False
    max_p = filt.get("max_price")
    if max_p is not None and price > float(max_p):
        return False
    return True


# ---------------------------------------------------------------------------
# Opening-bar alignment (ORB or5_align ∈ {aligned, doji})
# ---------------------------------------------------------------------------


def classify_or5_alignment(
    or5_open: float,
    or5_close: float,
    direction: str,
    doji_body_pct: float = 0.0005,
) -> str:
    """Classify the OR5 bar alignment relative to the trade direction.

    Returns one of:
      - 'aligned'    : (direction == 'long' AND green) OR (short AND red)
      - 'misaligned' : opposite of above (long+red or short+green)
      - 'doji'       : abs(close - open)/open < doji_body_pct
    """
    body = abs(or5_close - or5_open)
    if or5_open > 0 and body / or5_open < doji_body_pct:
        return "doji"
    green = or5_close > or5_open
    if (direction == "long" and green) or (direction == "short" and not green):
        return "aligned"
    return "misaligned"


def passes_opening_bar_alignment(
    or5_open: float,
    or5_close: float,
    direction: str,
    config: Optional[dict[str, Any]],
) -> bool:
    """Return True if the OR5 bar passes the opening-bar-alignment gate.

    config format: {required: bool, allow_doji?: bool}
    """
    if not config or not config.get("required", False):
        return True
    allow_doji = bool(config.get("allow_doji", True))
    cls = classify_or5_alignment(or5_open, or5_close, direction)
    if cls == "aligned":
        return True
    if cls == "doji" and allow_doji:
        return True
    return False


# ---------------------------------------------------------------------------
# Monday skip
# ---------------------------------------------------------------------------


def env_skip_mondays_enabled() -> bool:
    """Return True if WB_FRAMEWORK_SKIP_MONDAYS is set (default ON per Decision 3)."""
    return os.environ.get("WB_FRAMEWORK_SKIP_MONDAYS", "1") == "1"


def should_skip_monday(session_date: Any, yaml_flag: bool) -> bool:
    """Return True if this session should be skipped due to Monday rule.

    Either the YAML's `skip_mondays: true` or the env-var
    `WB_FRAMEWORK_SKIP_MONDAYS=1` (default ON) triggers the skip.
    weekday() returns 0=Monday.
    """
    if not (yaml_flag or env_skip_mondays_enabled()):
        return False
    wd = session_date.weekday()
    return wd == 0  # Monday


# ---------------------------------------------------------------------------
# Symbol blacklist (PDH-Breakout F4)
# ---------------------------------------------------------------------------


def passes_symbol_blacklist(symbol: str, blacklist: Iterable[str]) -> bool:
    """Return True if symbol is NOT in the blacklist (i.e. passes the filter)."""
    if not blacklist:
        return True
    return symbol.upper() not in {s.upper() for s in blacklist}


# ---------------------------------------------------------------------------
# VWAP alignment (PDH-Breakout F4)
# ---------------------------------------------------------------------------


def passes_vwap_alignment(
    entry_price: float,
    vwap: Optional[float],
    direction: str,
    require: bool,
) -> bool:
    """Return True if the trade passes the VWAP-alignment gate.

    Long entries require entry_price > vwap; short entries require <.
    If `require` is False, always passes. If vwap is None (insufficient
    history), we ALLOW the trade through to avoid suppressing early-RTH
    entries; caller can override by checking vwap availability first.
    """
    if not require:
        return True
    if vwap is None or vwap <= 0:
        return True
    if direction == "long":
        return entry_price > vwap
    return entry_price < vwap


# ---------------------------------------------------------------------------
# 5-bar pre-entry consolidation (PDH-Breakout F4)
# ---------------------------------------------------------------------------


def compute_5bar_consolidation_pct(
    bars_before_entry: list[Any], entry_price: float, lookback: int = 5
) -> Optional[float]:
    """Return the 5-bar pre-entry high-low range as % of entry_price.

    bars_before_entry is the slice of bars BEFORE the entry bar (NOT including
    the entry bar). If fewer than `lookback` bars are available, returns None
    (filter cannot apply).
    """
    if len(bars_before_entry) < lookback or entry_price <= 0:
        return None
    recent = bars_before_entry[-lookback:]
    hi = max(b.high for b in recent)
    lo = min(b.low for b in recent)
    return (hi - lo) / entry_price * 100.0


def passes_pre_entry_consolidation(
    bars_before_entry: list[Any],
    entry_price: float,
    max_pct: Optional[float],
) -> bool:
    """Return True if the 5-bar pre-entry consolidation passes the gate."""
    if max_pct is None:
        return True
    pct = compute_5bar_consolidation_pct(bars_before_entry, entry_price)
    if pct is None:
        # Not enough bars to apply the filter — pass-through; in practice
        # the entry bar is well into RTH so this rarely fires.
        return True
    return pct < float(max_pct)


# ---------------------------------------------------------------------------
# Volume-multiple filter (PDH-Breakout F4)
# ---------------------------------------------------------------------------


def passes_volume_min_multiple(
    entry_bar_volume: float,
    prior_bars: list[Any],
    min_mult: Optional[float],
    baseline_bars: int = 20,
) -> bool:
    """Return True if entry_bar_volume / prior-N-bar mean >= min_mult.

    If there aren't enough prior bars to compute a baseline, returns True
    (pass-through). The base breakout_candle plugin enforces a similar gate
    on the confirmation bar; this is a redundant but explicit check for
    forensic-audit clarity.
    """
    if min_mult is None:
        return True
    if len(prior_bars) < baseline_bars:
        return True
    baseline = sum(b.volume for b in prior_bars[-baseline_bars:]) / baseline_bars
    if baseline <= 0:
        return True
    return entry_bar_volume / baseline >= float(min_mult)


# ---------------------------------------------------------------------------
# Combined filter dispatch (signal-level)
# ---------------------------------------------------------------------------


def passes_pre_entry_filters(
    *,
    spec: dict[str, Any],
    entry_ts: datetime,
    entry_price: float,
    direction: str,
    symbol: str,
    session_date: Any,
    vwap_at_entry: Optional[float],
    bars_before_entry: list[Any],
    entry_bar_volume: float,
    or5_open: Optional[float] = None,
    or5_close: Optional[float] = None,
) -> tuple[bool, str]:
    """Apply all configured pre-entry filters from `spec`.

    Returns (True, '') if the signal passes everything; (False, reason)
    if any filter rejects it. `reason` is a short string useful for logging.

    `spec` is the raw YAML dict (NOT the StrategySpec dataclass), so this
    function can be used directly from portfolio_backtest's raw-spec flow.
    """
    # entry_time_window
    if not passes_entry_time_window(entry_ts, spec.get("entry_time_window")):
        return False, "entry_time_window"

    # tier_filter
    if not passes_tier_filter(entry_price, spec.get("tier_filter")):
        return False, "tier_filter"

    # opening_bar_alignment (requires OR5 bar)
    oba = spec.get("opening_bar_alignment")
    if oba and oba.get("required", False):
        if or5_open is None or or5_close is None:
            # Missing OR5 — fail closed (the filter is required).
            return False, "opening_bar_alignment_no_data"
        if not passes_opening_bar_alignment(or5_open, or5_close, direction, oba):
            return False, "opening_bar_alignment"

    # skip_mondays
    if should_skip_monday(session_date, bool(spec.get("skip_mondays", False))):
        return False, "skip_mondays"

    # symbol_blacklist
    if not passes_symbol_blacklist(symbol, spec.get("symbol_blacklist") or ()):
        return False, "symbol_blacklist"

    # require_vwap_alignment
    if not passes_vwap_alignment(
        entry_price,
        vwap_at_entry,
        direction,
        bool(spec.get("require_vwap_alignment", False)),
    ):
        return False, "vwap_alignment"

    # pre_entry_consolidation_max_pct
    if not passes_pre_entry_consolidation(
        bars_before_entry,
        entry_price,
        spec.get("pre_entry_consolidation_max_pct"),
    ):
        return False, "pre_entry_consolidation"

    # volume_min_multiple
    if not passes_volume_min_multiple(
        entry_bar_volume,
        bars_before_entry,
        spec.get("volume_min_multiple"),
    ):
        return False, "volume_min_multiple"

    return True, ""
