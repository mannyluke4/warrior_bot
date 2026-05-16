"""Anchored VWAP backtest — Wave 5, Agent M.

Backtests the two Anchored-VWAP strategies (pullback + breakout) across the
36-symbol Databento shortlist for 2020-2024, using the same bar-level engine
pattern as ``backtest/portfolio_backtest.py``.

Per the Wave 3 synthesis (cowork_reports/2026-05-16_wave3_synthesis.md):
- Sizing: fixed-dollar $1,000 risk (Wave 4 paper recommendation).
- VIX gate: VIX > 25 suppression enabled (regime gate from spec).
- Universe: 36 symbols pre-cached in ``tick_cache_databento/``.

Outputs:
- ``backtest_archive/anchored_vwap/trades_AVWAP-Pullback.parquet``
- ``backtest_archive/anchored_vwap/trades_AVWAP-Breakout.parquet``
- ``backtest_archive/anchored_vwap/summary.json``
- Anchor-type breakdown CSV.

This runs against real Databento data; no synthetic.

Per directive §9: BACKTEST ONLY — no paper deployment.
Per directive §7: existing live code untouched.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.confirmations.breakout_candle import BreakoutCandle
from framework.confirmations.signal_candle import SignalCandle
from framework.level_sources.anchored_vwap import AnchoredVWAPSource
from framework.level_sources.base import Bar, BarHistory, Level

log = logging.getLogger("anchored_vwap_backtest")


REPO = Path("/Users/duffy/warrior_bot_v2")
CACHE_ROOT = REPO / "tick_cache_databento"

RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
TRADE_WINDOW_START = time(9, 35)
TRADE_WINDOW_END = time(15, 55)


# Wave 3 Databento shortlist (36 symbols)
UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "TSLA", "NVDA", "META", "AMD", "AVGO", "ADBE",
    "CRM", "ORCL", "NFLX", "INTC", "QCOM", "CSCO", "MU", "PLTR",
    "ROKU", "SNAP", "SOFI", "F", "BAC", "WFC", "JPM", "MA",
    "DIS", "NKE", "DAL", "AAL", "WMT", "COST", "T", "VZ",
    "KO", "MRK", "PFE", "AMC",
)


# ---------------------------------------------------------------------------
# VIX series loader — for regime gate (Wave 3 synthesis: VIX > 25 suppression)
# ---------------------------------------------------------------------------


def load_vix_series() -> dict[date, float]:
    """Load a per-day VIX value series.

    We don't have a cached VIX feed in tick_cache_databento.  As an
    approximation, we read VIX values from a hardcoded daily series saved
    in ``backtest/vix_daily.csv`` if it exists; otherwise we fall back to
    a coarse 2020-2024 regime map derived from public history.
    """
    fp = REPO / "backtest" / "vix_daily.csv"
    series: dict[date, float] = {}
    if fp.exists():
        try:
            df = pd.read_csv(fp)
            for row in df.itertuples(index=False):
                d = pd.Timestamp(row.date).date()
                series[d] = float(row.vix)
            return series
        except Exception:
            pass
    # Fallback: very coarse VIX > 25 windows from public data 2020-2024.
    # Format: (start, end_inclusive) → flag is_high (vix > 25). Used to
    # suppress entries on known stress days without exact daily VIX.
    high_windows = [
        # COVID crash + aftershock
        (date(2020, 2, 24), date(2020, 5, 29)),
        (date(2020, 6, 11), date(2020, 6, 30)),
        (date(2020, 9, 3), date(2020, 11, 5)),
        # GameStop / Jan 2021
        (date(2021, 1, 27), date(2021, 2, 1)),
        # 2022 bear market
        (date(2022, 1, 24), date(2022, 11, 10)),
        # SVB crisis 2023
        (date(2023, 3, 13), date(2023, 3, 24)),
        # Yen carry / Aug 2024 vol spike
        (date(2024, 8, 5), date(2024, 8, 9)),
    ]

    def is_high(d: date) -> bool:
        for s, e in high_windows:
            if s <= d <= e:
                return True
        return False

    # Materialize coarse series — for any date encountered set to 30 if
    # high window, else 18. Callers cache results.
    # Return empty dict; callers must use ``vix_value_for``.
    return series


_VIX_SERIES: Optional[dict[date, float]] = None
_VIX_HIGH_WINDOWS: list[tuple[date, date]] = [
    (date(2020, 2, 24), date(2020, 5, 29)),
    (date(2020, 6, 11), date(2020, 6, 30)),
    (date(2020, 9, 3), date(2020, 11, 5)),
    (date(2021, 1, 27), date(2021, 2, 1)),
    (date(2022, 1, 24), date(2022, 11, 10)),
    (date(2023, 3, 13), date(2023, 3, 24)),
    (date(2024, 8, 5), date(2024, 8, 9)),
]


def vix_value_for(d: date) -> float:
    """Best-effort VIX value lookup for a date.

    Uses the daily series file if present; otherwise the coarse regime map
    returns 30 for high-window dates, 18 otherwise. Wave 3 synthesis flagged
    a Wave 5 calibration of 22/25 hysteresis; we use a hard 25 cutoff with
    the coarse map.
    """
    global _VIX_SERIES
    if _VIX_SERIES is None:
        _VIX_SERIES = load_vix_series()
    if d in _VIX_SERIES:
        return _VIX_SERIES[d]
    for s, e in _VIX_HIGH_WINDOWS:
        if s <= d <= e:
            return 30.0
    return 18.0


# ---------------------------------------------------------------------------
# Bar loaders (same pattern as portfolio_backtest)
# ---------------------------------------------------------------------------


def load_day_bars(symbol: str, session_date: date) -> list[Bar]:
    fp = CACHE_ROOT / symbol / f"1m_{session_date.isoformat()}.parquet"
    if not fp.exists():
        return []
    try:
        df = pd.read_parquet(fp)
    except Exception:
        return []
    if df.empty:
        return []
    bars: list[Bar] = []
    for row in df.itertuples(index=False):
        ts = pd.Timestamp(row.ts_event).to_pydatetime()
        t = ts.time()
        if t < RTH_OPEN or t >= RTH_CLOSE:
            continue
        try:
            bars.append(Bar(
                timestamp=ts,
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume),
                symbol=symbol,
            ))
        except (ValueError, TypeError):
            continue
    return bars


def load_history_for_anchor_window(
    symbol: str,
    target_date: date,
    lookback_days: int,
) -> list[Bar]:
    """Load all session bars for a symbol from ``target_date - lookback_days``
    (calendar days) up to and including ``target_date``. Returns RTH-only
    bars, chronologically ordered.

    To keep memory and IO sane we load only the FIRST and LAST RTH bar of
    each prior session (sufficient for gap detection + anchor selection),
    then the full bar list for the target session itself.
    """
    bars: list[Bar] = []
    start = target_date - timedelta(days=lookback_days)
    cur = start
    while cur <= target_date:
        if cur == target_date:
            day = load_day_bars(symbol, cur)
            bars.extend(day)
        else:
            day = load_day_bars(symbol, cur)
            if day:
                # First + last bar suffice for gap detection
                bars.append(day[0])
                bars.append(day[-1])
        cur += timedelta(days=1)
    return bars


# ---------------------------------------------------------------------------
# Trade dataclass
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    strategy: str
    symbol: str
    session_date: date
    direction: str
    entry_ts: datetime
    exit_ts: datetime
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: Optional[float]
    qty: int
    risk_dollars: float
    pnl: float
    r_multiple: float
    exit_reason: str
    anchor_type: str
    anchor_date: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "direction": self.direction,
            "entry_ts": self.entry_ts.isoformat(),
            "exit_ts": self.exit_ts.isoformat(),
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "stop_price": self.stop_price,
            "target_price": self.target_price,
            "qty": self.qty,
            "risk_dollars": self.risk_dollars,
            "pnl": self.pnl,
            "r_multiple": self.r_multiple,
            "exit_reason": self.exit_reason,
            "anchor_type": self.anchor_type,
            "anchor_date": self.anchor_date,
        }


# ---------------------------------------------------------------------------
# Signal generators
# ---------------------------------------------------------------------------


@dataclass
class AVWAPSignal:
    bar_idx: int
    direction: str          # 'long' | 'short'
    level: Level            # the AVWAP level reacted to
    anchor_type: str
    anchor_date: str


def _build_history_around_target(
    symbol: str,
    target_date: date,
    lookback_days: int,
) -> tuple[list[Bar], list[Bar]]:
    """Return (prior_summary_bars, today_bars).

    ``prior_summary_bars`` contains first+last bar of each prior session
    within the lookback window — sufficient for anchor detection (gap day
    uses prior_close + open; earnings/FOMC use first RTH bar).
    """
    today_bars = load_day_bars(symbol, target_date)
    prior_bars: list[Bar] = []
    cur = target_date - timedelta(days=lookback_days)
    while cur < target_date:
        day = load_day_bars(symbol, cur)
        if day:
            prior_bars.append(day[0])
            prior_bars.append(day[-1])
        cur += timedelta(days=1)
    return prior_bars, today_bars


def _avwap_pullback_signal(
    today_bars: list[Bar],
    prior_summary_bars: list[Bar],
    spec: dict[str, Any],
    symbol: str,
    target_date: date,
) -> Optional[AVWAPSignal]:
    """Pullback signal: AVWAP as support (long) or resistance (short) with
    signal-candle reaction.

    Performance: ``AnchoredVWAPSource`` is built once at the start of the
    session (selecting anchors against the pre-target history), then
    intraday bars are fed via ``update_intraday`` for O(1) running-AVWAP
    updates instead of O(N²) rebuilds.
    """
    ls_params = spec.get("level_source", {}).get("params", {})
    src = AnchoredVWAPSource(
        anchor_type=ls_params.get("anchor_type", "gap_day"),
        lookback_days=int(ls_params.get("lookback_days", 30)),
        multi_anchor_count=int(ls_params.get("multi_anchor_count", 1)),
        gap_threshold_pct=float(ls_params.get("gap_threshold_pct", 0.02)),
    )

    # Build initial state from PRIOR summary bars only — pre-session anchor
    # selection. Then intraday bars accumulate via update_intraday.
    history = BarHistory(symbol=symbol, bars=list(prior_summary_bars))
    ls = src.compute_levels(symbol, history, target_date=target_date)
    if not ls.levels:
        return None
    avwap_level0 = ls.levels[0]
    anchor_type = avwap_level0.metadata.get("anchor_type", "unknown")
    anchor_date = avwap_level0.metadata.get("anchor_date", "")

    # Arrival proximity
    proximity_pct = float(
        spec.get("arrival_detector", {}).get("params", {}).get("proximity_pct", 0.002)
    )
    cp = spec.get("confirmation_rule", {}).get("params", {})
    sc = SignalCandle(
        patterns=list(cp.get("patterns", ["hammer", "doji", "shooting_star"])),
        require_volume_increase=bool(cp.get("require_volume_increase", True)),
    )

    # Walk today's bars; feed each via update_intraday to advance the AVWAP.
    for i in range(0, len(today_bars)):
        src.update_intraday(today_bars[i])
        if i < 2:
            continue
        b = today_bars[i]
        if b.timestamp.time() < TRADE_WINDOW_START:
            continue
        if b.timestamp.time() >= TRADE_WINDOW_END:
            break

        sub_ls = src.current_levelset(symbol=symbol)
        if not sub_ls.levels:
            continue
        avwap_price = sub_ls.levels[0].price

        price = b.close
        prior_close = today_bars[i - 1].close

        # Pullback from above (long bias): prior bar was above AVWAP,
        # current bar touched AVWAP from above.
        from_above = prior_close > avwap_price and b.low <= avwap_price * (1 + proximity_pct)
        # Pullback from below (short bias): prior bar was below AVWAP,
        # current bar touched AVWAP from below.
        from_below = prior_close < avwap_price and b.high >= avwap_price * (1 - proximity_pct)

        if not (from_above or from_below):
            continue

        # Signal candle confirmation
        # Build a fake Level at AVWAP for the SignalCandle.check (which
        # only uses the bar shape, not the level).
        avwap_lvl_now = Level(
            price=avwap_price,
            kind="AVWAP",
            session_date=target_date,
            metadata=sub_ls.levels[0].metadata,
        )
        res = sc.check_confirmation(avwap_lvl_now, today_bars[: i + 1], None)
        if not res.confirmed:
            continue

        # Long bias from_above + hammer (or doji), short from_below + shooting_star (or doji)
        if from_above and res.pattern_name in ("hammer", "doji"):
            return AVWAPSignal(
                bar_idx=i, direction="long", level=avwap_lvl_now,
                anchor_type=anchor_type, anchor_date=anchor_date,
            )
        if from_below and res.pattern_name in ("shooting_star", "doji"):
            return AVWAPSignal(
                bar_idx=i, direction="short", level=avwap_lvl_now,
                anchor_type=anchor_type, anchor_date=anchor_date,
            )
    return None


def _avwap_breakout_signal(
    today_bars: list[Bar],
    prior_summary_bars: list[Bar],
    spec: dict[str, Any],
    symbol: str,
    target_date: date,
) -> Optional[AVWAPSignal]:
    """Breakout signal: any of the multi-anchor AVWAPs reclaimed from below
    with a breakout candle.
    """
    ls_params = spec.get("level_source", {}).get("params", {})
    src = AnchoredVWAPSource(
        anchor_type=ls_params.get("anchor_type", "earnings_or_gap"),
        lookback_days=int(ls_params.get("lookback_days", 30)),
        multi_anchor_count=int(ls_params.get("multi_anchor_count", 3)),
        gap_threshold_pct=float(ls_params.get("gap_threshold_pct", 0.02)),
    )

    # Initial anchor selection on prior history only.
    history = BarHistory(symbol=symbol, bars=list(prior_summary_bars))
    initial_ls = src.compute_levels(symbol, history, target_date=target_date)
    if not initial_ls.levels:
        return None

    proximity_pct = float(
        spec.get("arrival_detector", {}).get("params", {}).get("proximity_pct", 0.001)
    )
    cp = spec.get("confirmation_rule", {}).get("params", {})
    bc = BreakoutCandle(
        min_vol_mult=float(cp.get("min_vol_mult", 1.5)),
        min_breakout_pct=float(cp.get("min_breakout_pct", 0.0002)),
        require_close_beyond=bool(cp.get("require_close_beyond", True)),
        direction="long",
    )

    for i in range(0, len(today_bars)):
        # O(1) incremental update — all active anchors refreshed in place.
        src.update_intraday(today_bars[i])
        if i < 20:
            continue
        b = today_bars[i]
        if b.timestamp.time() < TRADE_WINDOW_START:
            continue
        if b.timestamp.time() >= TRADE_WINDOW_END:
            break

        sub_ls = src.current_levelset(symbol=symbol)
        if not sub_ls.levels:
            continue

        prior_close = today_bars[i - 1].close
        for avwap_level in sub_ls.levels:
            avwap_price = avwap_level.price
            if avwap_price <= 0:
                continue
            # Retesting from below: prior bar close < AVWAP price
            if prior_close >= avwap_price:
                continue
            # Bar low must be near AVWAP (proximity)
            if b.low > avwap_price * (1 + proximity_pct):
                continue
            # Breakout: close above AVWAP + vol mult
            res = bc.check_confirmation(avwap_level, today_bars[: i + 1], None)
            if not res.confirmed:
                continue
            if res.metadata.get("direction") != "long":
                continue
            return AVWAPSignal(
                bar_idx=i,
                direction="long",
                level=avwap_level,
                anchor_type=avwap_level.metadata.get("anchor_type", "unknown"),
                anchor_date=avwap_level.metadata.get("anchor_date", ""),
            )
    return None


# ---------------------------------------------------------------------------
# Stop + target + exit replay
# ---------------------------------------------------------------------------


def _compute_stop_target(
    signal: AVWAPSignal,
    today_bars: list[Bar],
    spec: dict[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    if signal.bar_idx + 1 >= len(today_bars):
        return None, None
    fill_bar = today_bars[signal.bar_idx + 1]
    entry_price = fill_bar.open
    direction = signal.direction

    stop_cfg = spec.get("stop_rule", {})
    stop_type = stop_cfg.get("type", "just_past_level")
    stop_price: Optional[float] = None

    if stop_type == "just_past_level":
        pad = float(stop_cfg.get("params", {}).get("pad_dollar", 0.15))
        if direction == "long":
            stop_price = signal.level.price - pad
        else:
            stop_price = signal.level.price + pad
    elif stop_type == "bar_low":
        pad = float(stop_cfg.get("params", {}).get("pad_dollar", 0.05))
        prior_bar = today_bars[signal.bar_idx] if signal.bar_idx >= 0 else fill_bar
        if direction == "long":
            stop_price = prior_bar.low - pad
        else:
            stop_price = prior_bar.high + pad

    if stop_price is None or not np.isfinite(stop_price):
        return None, None
    if direction == "long" and stop_price >= entry_price:
        return None, None
    if direction == "short" and stop_price <= entry_price:
        return None, None

    per_share_risk = abs(entry_price - stop_price)

    tgt_cfg = spec.get("target_rule", {})
    params = tgt_cfg.get("params", {})
    r_target_mult = float(params.get("r_multiple", 2.0))
    if direction == "long":
        target_price = entry_price + r_target_mult * per_share_risk
    else:
        target_price = entry_price - r_target_mult * per_share_risk
    return stop_price, target_price


def _replay_to_exit(
    today_bars: list[Bar],
    entry_idx: int,
    entry_price: float,
    stop_price: float,
    target_price: Optional[float],
    direction: str,
    trail_activate_r: Optional[float] = None,
    trail_atr_mult: Optional[float] = None,
) -> tuple[float, datetime, str]:
    """Forward replay with optional ATR trailing-after-R activation.

    We approximate ATR per bar with (bar.range_size) — for 1m bars this is
    a reasonable proxy. After ``trail_activate_r`` R achieved, the stop
    trails to ``high - trail_atr_mult * atr`` (long) or ``low + ...`` (short).
    """
    per_share_risk = abs(entry_price - stop_price)
    cur_stop = stop_price
    extreme = entry_price  # high water mark (long) or low water mark (short)
    trailing = False

    for j in range(entry_idx + 1, len(today_bars)):
        b = today_bars[j]
        if b.timestamp.time() >= TRADE_WINDOW_END:
            return b.close, b.timestamp, "session_close"

        # Trail activation check (using bar.high / bar.low to capture intra-bar)
        if direction == "long":
            extreme = max(extreme, b.high)
            r_unrealized = (extreme - entry_price) / per_share_risk if per_share_risk > 0 else 0
            if (
                trail_activate_r is not None
                and trail_atr_mult is not None
                and r_unrealized >= trail_activate_r
            ):
                trailing = True
            if trailing and trail_atr_mult is not None:
                # ATR-proxy = bar range; pull stop to extreme - mult*atr
                atr = max(b.range_size, 0.01)
                new_stop = extreme - trail_atr_mult * atr
                if new_stop > cur_stop:
                    cur_stop = new_stop
            if b.low <= cur_stop:
                return cur_stop, b.timestamp, "stop" if cur_stop == stop_price else "trail_stop"
            if target_price is not None and b.high >= target_price:
                return target_price, b.timestamp, "target"
        else:
            extreme = min(extreme, b.low)
            r_unrealized = (entry_price - extreme) / per_share_risk if per_share_risk > 0 else 0
            if (
                trail_activate_r is not None
                and trail_atr_mult is not None
                and r_unrealized >= trail_activate_r
            ):
                trailing = True
            if trailing and trail_atr_mult is not None:
                atr = max(b.range_size, 0.01)
                new_stop = extreme + trail_atr_mult * atr
                if new_stop < cur_stop:
                    cur_stop = new_stop
            if b.high >= cur_stop:
                return cur_stop, b.timestamp, "stop" if cur_stop == stop_price else "trail_stop"
            if target_price is not None and b.low <= target_price:
                return target_price, b.timestamp, "target"
    last = today_bars[-1]
    return last.close, last.timestamp, "session_close"


# ---------------------------------------------------------------------------
# One-day-one-strategy execution
# ---------------------------------------------------------------------------


def _execute_one(
    strategy_name: str,
    spec: dict[str, Any],
    today_bars: list[Bar],
    prior_summary_bars: list[Bar],
    symbol: str,
    target_date: date,
    fixed_risk: float,
    vix_max: float,
) -> Optional[Trade]:
    # VIX gate
    vix_now = vix_value_for(target_date)
    if vix_now > vix_max:
        return None

    if "pullback" in strategy_name.lower():
        signal = _avwap_pullback_signal(today_bars, prior_summary_bars, spec, symbol, target_date)
    else:
        signal = _avwap_breakout_signal(today_bars, prior_summary_bars, spec, symbol, target_date)

    if signal is None:
        return None
    if signal.bar_idx + 1 >= len(today_bars):
        return None
    fill_bar = today_bars[signal.bar_idx + 1]
    entry_price = fill_bar.open
    stop_price, target_price = _compute_stop_target(signal, today_bars, spec)
    if stop_price is None:
        return None
    per_share_risk = abs(entry_price - stop_price)
    if per_share_risk <= 0:
        return None
    qty = int(fixed_risk // per_share_risk)
    if qty <= 0:
        return None
    # 5% of bar volume cap (defensive)
    recent_vol = float(today_bars[signal.bar_idx].volume) if today_bars else 0.0
    if recent_vol > 0:
        qty = min(qty, int(0.05 * recent_vol))
    if qty <= 0:
        return None

    tgt_params = spec.get("target_rule", {}).get("params", {})
    trail_at = tgt_params.get("activate_trailing_at_r", None)
    trail_mult = tgt_params.get("trailing_atr_mult", None)
    trail_at_f = float(trail_at) if trail_at is not None else None
    trail_mult_f = float(trail_mult) if trail_mult is not None else None

    exit_price, exit_ts, reason = _replay_to_exit(
        today_bars=today_bars,
        entry_idx=signal.bar_idx + 1,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        direction=signal.direction,
        trail_activate_r=trail_at_f,
        trail_atr_mult=trail_mult_f,
    )
    pnl = (exit_price - entry_price) * qty if signal.direction == "long" \
        else (entry_price - exit_price) * qty
    r_mult = pnl / fixed_risk if fixed_risk > 0 else 0.0

    return Trade(
        strategy=strategy_name,
        symbol=symbol,
        session_date=target_date,
        direction=signal.direction,
        entry_ts=fill_bar.timestamp,
        exit_ts=exit_ts,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=stop_price,
        target_price=target_price,
        qty=qty,
        risk_dollars=fixed_risk,
        pnl=pnl,
        r_multiple=r_mult,
        exit_reason=reason,
        anchor_type=signal.anchor_type,
        anchor_date=signal.anchor_date,
    )


# ---------------------------------------------------------------------------
# Top-level sweep
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    strategy_yaml: str
    universe: tuple[str, ...] = UNIVERSE
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    fixed_risk: float = 1000.0
    vix_max: float = 25.0


def _enumerate_sessions(start: date, end: date) -> list[date]:
    """All weekdays in [start, end] that AAPL has bars for."""
    aapl_dir = CACHE_ROOT / "AAPL"
    if not aapl_dir.exists():
        return []
    dates: list[date] = []
    for fp in sorted(aapl_dir.glob("1m_*.parquet")):
        try:
            d = pd.Timestamp(fp.stem.replace("1m_", "")).date()
        except Exception:
            continue
        if d < start or d > end:
            continue
        dates.append(d)
    return dates


def run_backtest(cfg: BacktestConfig) -> list[dict[str, Any]]:
    """Execute the backtest sweep, return list of trade dicts."""
    with open(cfg.strategy_yaml) as f:
        spec = yaml.safe_load(f)
    strategy_name = spec.get("name", Path(cfg.strategy_yaml).stem)
    lookback_days = int(spec.get("level_source", {}).get("params", {}).get("lookback_days", 30))

    start = cfg.start_date or date(2020, 1, 1)
    end = cfg.end_date or date(2024, 12, 31)
    sessions = _enumerate_sessions(start, end)

    log.info(
        "[%s] %d sessions × %d symbols, lookback %d days, VIX max %.1f",
        strategy_name, len(sessions), len(cfg.universe), lookback_days, cfg.vix_max,
    )

    # Preload a per-symbol session map of (date -> first+last bar) so we
    # don't reload prior days every iteration.
    summary_cache: dict[str, dict[date, list[Bar]]] = {sym: {} for sym in cfg.universe}

    trades: list[dict[str, Any]] = []
    progress_every = max(1, len(sessions) // 20)

    for i, d in enumerate(sessions):
        if i % progress_every == 0:
            log.info("  session %d/%d (%s) — trades_so_far=%d",
                     i, len(sessions), d.isoformat(), len(trades))
        for sym in cfg.universe:
            today = load_day_bars(sym, d)
            if not today:
                continue
            # Build prior summary bars from cache
            prior: list[Bar] = []
            cur = d - timedelta(days=lookback_days)
            while cur < d:
                if cur in summary_cache[sym]:
                    prior.extend(summary_cache[sym][cur])
                else:
                    day_bars = load_day_bars(sym, cur)
                    if day_bars:
                        summary_cache[sym][cur] = [day_bars[0], day_bars[-1]]
                        prior.extend(summary_cache[sym][cur])
                    else:
                        summary_cache[sym][cur] = []
                cur += timedelta(days=1)
            # Prune old cache entries (>2× lookback)
            cutoff = d - timedelta(days=lookback_days * 2)
            for k in list(summary_cache[sym].keys()):
                if k < cutoff:
                    del summary_cache[sym][k]

            t = _execute_one(
                strategy_name=strategy_name,
                spec=spec,
                today_bars=today,
                prior_summary_bars=prior,
                symbol=sym,
                target_date=d,
                fixed_risk=cfg.fixed_risk,
                vix_max=cfg.vix_max,
            )
            if t:
                trades.append(t.to_dict())
    return trades


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def summarize(trades: list[dict[str, Any]], starting_equity: float = 100_000.0) -> dict:
    if not trades:
        return {
            "n_trades": 0, "win_rate": float("nan"), "profit_factor": float("nan"),
            "sharpe": float("nan"), "max_drawdown_pct": 0.0, "total_pnl": 0.0,
        }
    df = pd.DataFrame(trades)
    df["session_date"] = pd.to_datetime(df["session_date"])
    df = df.sort_values("entry_ts").reset_index(drop=True)

    # Equity curve (per trade)
    df["equity"] = starting_equity + df["pnl"].cumsum()

    # Daily aggregation for Sharpe
    daily = df.groupby(df["session_date"].dt.date)["pnl"].sum()
    daily_returns = daily / starting_equity
    if len(daily_returns) > 1:
        sharpe = (daily_returns.mean() / daily_returns.std(ddof=1)) * (252 ** 0.5)
    else:
        sharpe = float("nan")

    wins = (df["pnl"] > 0).sum()
    losses = (df["pnl"] < 0).sum()
    gross_win = df.loc[df["pnl"] > 0, "pnl"].sum()
    gross_loss = df.loc[df["pnl"] < 0, "pnl"].sum()
    pf = float(gross_win / abs(gross_loss)) if gross_loss != 0 else float("inf")

    # Drawdown
    eq = df["equity"]
    peak = eq.cummax()
    dd = (eq - peak) / peak
    max_dd_pct = float(dd.min()) if len(dd) else 0.0

    return {
        "n_trades": int(len(df)),
        "n_wins": int(wins),
        "n_losses": int(losses),
        "win_rate": float(wins / len(df)) if len(df) else float("nan"),
        "profit_factor": float(pf) if pf != float("inf") else 99.0,
        "sharpe": float(sharpe) if pd.notna(sharpe) else float("nan"),
        "avg_r": float(df["r_multiple"].mean()),
        "total_pnl": float(df["pnl"].sum()),
        "max_drawdown_pct": max_dd_pct,
        "starting_equity": starting_equity,
        "ending_equity": float(starting_equity + df["pnl"].sum()),
    }


def per_anchor_breakdown(trades: list[dict[str, Any]]) -> dict[str, dict]:
    """Aggregate metrics per anchor_type."""
    if not trades:
        return {}
    df = pd.DataFrame(trades)
    out: dict[str, dict] = {}
    for at in sorted(df["anchor_type"].unique()):
        sub = df[df["anchor_type"] == at].to_dict("records")
        out[at] = summarize(sub)
    return out


def per_year_breakdown(trades: list[dict[str, Any]]) -> dict[str, dict]:
    if not trades:
        return {}
    df = pd.DataFrame(trades)
    df["session_date"] = pd.to_datetime(df["session_date"])
    out: dict[str, dict] = {}
    for y in sorted(df["session_date"].dt.year.unique()):
        sub = df[df["session_date"].dt.year == y].to_dict("records")
        out[str(int(y))] = summarize(sub)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Anchored VWAP backtest (Wave 5, Agent M)")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default="2024-12-31")
    ap.add_argument("--out", default="backtest_archive/anchored_vwap")
    ap.add_argument("--symbols", nargs="*", default=None)
    ap.add_argument("--strategies", nargs="*", default=None,
                    help="YAML paths; default = both AVWAP specs")
    ap.add_argument("--fixed-risk", type=float, default=1000.0)
    ap.add_argument("--vix-max", type=float, default=25.0,
                    help="VIX gate ceiling; set to 999 to disable")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    yamls = args.strategies or [
        str(REPO / "strategies" / "anchored_vwap_pullback.yaml"),
        str(REPO / "strategies" / "anchored_vwap_breakout.yaml"),
    ]
    universe = tuple(args.symbols) if args.symbols else UNIVERSE

    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_all: dict[str, Any] = {
        "config": {
            "start": args.start, "end": args.end,
            "fixed_risk": args.fixed_risk, "vix_max": args.vix_max,
            "universe_n": len(universe),
        },
        "strategies": {},
    }
    for ypath in yamls:
        cfg = BacktestConfig(
            strategy_yaml=ypath,
            universe=universe,
            start_date=pd.Timestamp(args.start).date(),
            end_date=pd.Timestamp(args.end).date(),
            fixed_risk=args.fixed_risk,
            vix_max=args.vix_max,
        )
        log.info("starting %s", ypath)
        trades = run_backtest(cfg)
        sname = Path(ypath).stem
        if trades:
            df = pd.DataFrame(trades)
            df.to_parquet(out_dir / f"trades_{sname}.parquet", index=False)
            df.to_csv(out_dir / f"trades_{sname}.csv", index=False)
        summary = summarize(trades)
        summary["per_anchor"] = per_anchor_breakdown(trades)
        summary["per_year"] = per_year_breakdown(trades)
        summary_all["strategies"][sname] = summary
        log.info("%s: %s", sname, {k: v for k, v in summary.items()
                                    if k not in ("per_anchor", "per_year")})

    (out_dir / "summary.json").write_text(json.dumps(summary_all, indent=2, default=str))
    log.info("done -> %s", out_dir)


if __name__ == "__main__":
    _cli()
