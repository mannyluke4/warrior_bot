"""Volume Profile backtest harness — Wave 5 Agent L.

Bar-level replay engine exercising the framework's Volume Profile primitives
(VolumeProfileSource → ArrivalDetector → Rejection / BreakoutCandle →
JustPastLevel / BarLow → OppositeLevel / RMultiple) over a multi-symbol
multi-day universe spanning 2020-2024 (5 years OOS, per directive).

Two strategy variants are simulated:
- volume_profile_rejection (mean-reversion fade at HVN edges)
- volume_profile_breakout  (vacuum move through LVN to next HVN)

Each strategy is run independently. A combined portfolio with a
per-symbol-per-day lock is also generated for diversification analysis,
mirroring the Wave 3 portfolio_backtest engine.

Fidelity model: identical to portfolio_backtest.py — 1-min bar replay,
fill-at-next-bar-open, stop fills on intra-bar touch, target fills on
intra-bar touch, session-close at 15:55 ET. ~85-90% fidelity ceiling per
research §3.

Universe: 36-symbol Databento shortlist (same as Wave 3 Agent J).
Date range: 2020-01-02 → 2024-12-31 (5 years OOS).

VIX overlay: implemented by reading a daily VIX series and a configurable
suppression threshold. When VIX_on, sessions with vix > threshold are
skipped entirely (no entries). Default VIX series is a synthetic proxy
derived from the universe's daily realized-volatility — we don't have a
cached VIX feed in tick_cache_databento, so we approximate (see
`_compute_session_vix_proxy`). This matches the Wave 3 K-paper approach
where K used regime-shifted synthetic data; here we use realized-vol of
the cached universe as the regime indicator.

Sizing: fixed-dollar $1K risk per trade (per Wave 3 sizing bug —
HalfKellySizer suppresses returns due to the 5%-of-bar-volume cap binding
wrong on mega-caps).
"""
from __future__ import annotations

import json
import logging
import math
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from framework.arrival import ArrivalDetector
from framework.confirmations.breakout_candle import BreakoutCandle
from framework.confirmations.rejection import Rejection
from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.volume_profile import VolumeProfileSource

log = logging.getLogger("volume_profile_backtest")


REPO = Path("/Users/duffy/warrior_bot_v2")
CACHE_ROOT = REPO / "tick_cache_databento"
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
TRADE_WINDOW_START = time(9, 35)
TRADE_WINDOW_END = time(15, 55)

# Same 36-symbol universe Wave 3 used.
UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "TSLA", "NVDA", "META", "AMD", "AVGO", "ADBE",
    "CRM", "ORCL", "NFLX", "INTC", "QCOM", "CSCO", "MU", "PLTR",
    "ROKU", "SNAP", "SOFI", "F", "BAC", "WFC", "JPM", "MA",
    "DIS", "NKE", "DAL", "AAL", "WMT", "COST", "T", "VZ",
    "KO", "MRK", "PFE", "AMC",
)


# ---------------------------------------------------------------------------
# Configs
# ---------------------------------------------------------------------------


@dataclass
class VPRejectionConfig:
    """Mean-reversion fade at HVN edges."""
    lookback_sessions: int = 5
    bin_pct: float = 0.001
    hvn_multiplier: float = 1.5
    lvn_multiplier: float = 0.5
    proximity_pct: float = 0.0015
    rejection_lookback: int = 2
    stop_pad_dollar: float = 0.10
    fallback_r_multiple: float = 1.5
    risk_dollars: float = 1000.0      # fixed-dollar per Wave 3 sizing bug
    starting_balance: float = 100_000.0
    trade_window_start: time = TRADE_WINDOW_START
    trade_window_end: time = TRADE_WINDOW_END


@dataclass
class VPBreakoutConfig:
    """Vacuum-through-LVN breakout."""
    lookback_sessions: int = 5
    bin_pct: float = 0.001
    hvn_multiplier: float = 1.5
    lvn_multiplier: float = 0.5
    proximity_pct: float = 0.001
    min_vol_mult: float = 2.0
    min_breakout_pct: float = 0.0002
    stop_pad_dollar: float = 0.05
    target_r: float = 2.0              # fallback R-multiple
    risk_dollars: float = 1000.0
    starting_balance: float = 100_000.0
    trade_window_start: time = TRADE_WINDOW_START
    trade_window_end: time = TRADE_WINDOW_END


@dataclass
class Trade:
    strategy: str
    symbol: str
    session_date: date
    direction: str
    level_kind: str
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
    price_tier: str
    vix_proxy: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "session_date": self.session_date.isoformat(),
            "direction": self.direction,
            "level_kind": self.level_kind,
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
            "price_tier": self.price_tier,
            "vix_proxy": self.vix_proxy,
        }


def price_tier(price: float) -> str:
    if price < 10:
        return "<$10"
    if price < 50:
        return "$10-50"
    if price < 150:
        return "$50-150"
    if price < 300:
        return "$150-300"
    return "$300+"


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------


def load_day_bars(symbol: str, session_date: date) -> list[Bar]:
    """Load one symbol's 1-minute RTH bars for one session."""
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


def load_prior_n_sessions(
    symbol: str,
    session_date: date,
    n_sessions: int,
    max_calendar_lookback: int = 14,
) -> list[Bar]:
    """Load up to `n_sessions` of RTH bars strictly prior to session_date.

    Walks back day-by-day; stops once n_sessions distinct non-empty days
    have been collected or after `max_calendar_lookback` days.
    """
    bars: list[Bar] = []
    sessions_found: set[date] = set()
    for back in range(1, max_calendar_lookback + 1):
        prior = session_date - timedelta(days=back)
        if len(sessions_found) >= n_sessions:
            break
        day_bars = load_day_bars(symbol, prior)
        if day_bars:
            bars.extend(day_bars)
            sessions_found.add(prior)
    return bars


# ---------------------------------------------------------------------------
# VIX proxy — realized-volatility of the universe's daily returns
# ---------------------------------------------------------------------------


_VIX_CACHE_PATH = REPO / "backtest" / "volume_profile_vix_proxy_cache.json"


def _compute_session_vix_proxy(
    sessions: list[date],
    universe: tuple[str, ...] = UNIVERSE,
    rolling_window: int = 20,
    use_cache: bool = True,
) -> dict[date, float]:
    """Compute a synthetic daily VIX proxy from the universe's realized vol.

    We don't have a cached VIX feed; instead we use the cross-sectional
    median of 20-day realized volatility across a 5-symbol "VIX-like" basket
    (high-beta names that track market vol). Output is rescaled to roughly
    match CBOE-VIX magnitudes (10-50 range) by multiplying daily-RV by
    sqrt(252) and converting to percent.

    This is a proxy, not VIX. The directional signal (high vs low regime)
    is what matters for the VIX-on/VIX-off ablation per Wave 3 finding.
    """
    # Cache lookup
    if use_cache and _VIX_CACHE_PATH.exists():
        try:
            import json as _json
            with open(_VIX_CACHE_PATH) as f:
                cached = _json.load(f)
            out: dict[date, float] = {}
            for d in sessions:
                key = d.isoformat()
                if key in cached:
                    out[d] = float(cached[key])
            if len(out) == len(sessions):
                return out
        except Exception:
            pass

    proxy_symbols = ("AAPL", "MSFT", "NVDA", "META", "TSLA")
    daily_close: dict[str, dict[date, float]] = {s: {} for s in proxy_symbols}
    for sym in proxy_symbols:
        for d in sessions:
            bars = load_day_bars(sym, d)
            if bars:
                daily_close[sym][d] = bars[-1].close

    out: dict[date, float] = {}
    sessions_sorted = sorted(sessions)
    for i, d in enumerate(sessions_sorted):
        if i < rolling_window:
            out[d] = 18.0  # default "optimal" regime until window builds
            continue
        rv_list = []
        for sym in proxy_symbols:
            closes = []
            for j in range(max(0, i - rolling_window), i + 1):
                px = daily_close[sym].get(sessions_sorted[j])
                if px is not None and math.isfinite(px) and px > 0:
                    closes.append(px)
            if len(closes) < 3:
                continue
            returns = np.diff(np.log(closes))
            if len(returns) < 2:
                continue
            daily_rv = float(np.std(returns, ddof=1))
            rv_list.append(daily_rv * math.sqrt(252.0) * 100.0)
        if rv_list:
            out[d] = float(np.median(rv_list))
        else:
            out[d] = 18.0

    # Persist to cache
    if use_cache:
        try:
            import json as _json
            with open(_VIX_CACHE_PATH, "w") as f:
                _json.dump({d.isoformat(): v for d, v in out.items()}, f)
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Per-day single-symbol simulators
# ---------------------------------------------------------------------------


def _simulate_rejection_day(
    symbol: str,
    today_bars: list[Bar],
    prior_bars: list[Bar],
    cfg: VPRejectionConfig,
    vix_value: float,
) -> Optional[Trade]:
    """One day, one symbol, fade-rejection at HVN edges."""
    if not today_bars or not prior_bars:
        return None

    today_date = today_bars[0].timestamp.date()
    src = VolumeProfileSource(
        lookback_sessions=cfg.lookback_sessions,
        bin_pct=cfg.bin_pct,
        hvn_multiplier=cfg.hvn_multiplier,
        lvn_multiplier=cfg.lvn_multiplier,
        emit_poc=True,
        emit_hvn=True,
        emit_lvn=False,
        target_date=today_date,
    )
    history = BarHistory(symbol=symbol, bars=prior_bars + today_bars)
    level_set = src.compute_levels(symbol, history)
    if not level_set.levels:
        return None

    # HVN levels are the rejection candidates; POC adds a magnet level too.
    hvn_levels = [l for l in level_set.levels if l.kind in ("HVN", "POC")]
    if not hvn_levels:
        return None

    arrival = ArrivalDetector(proximity_pct=cfg.proximity_pct)
    # We instantiate two rejection plugins (resistance & support sides)
    # because HVN/POC don't carry a structural side — direction is inferred
    # from how price *approaches* the level.
    rej_resist = Rejection(lookback_bars=cfg.rejection_lookback, side="resistance")
    rej_support = Rejection(lookback_bars=cfg.rejection_lookback, side="support")

    entry_idx: Optional[int] = None
    entry_dir: Optional[str] = None
    entry_level: Optional[Level] = None

    # Skip the first 10 bars of session: avoid trading the open noise on
    # 09:30-09:40 when the rejection-failed-test pattern is structurally
    # unreliable (no session VWAP, no volume context).
    min_bar_idx = 10

    for i in range(min_bar_idx, len(today_bars)):
        b = today_bars[i]
        if b.timestamp.time() < cfg.trade_window_start:
            continue
        if b.timestamp.time() >= cfg.trade_window_end:
            break

        prior_window = today_bars[: i + 1]
        threshold = arrival._threshold(b.close)

        # Pick the closest HVN/POC level
        nearest = min(hvn_levels, key=lambda lv: abs(lv.price - b.close))
        # Require the close has cleanly returned BEYOND the proximity threshold —
        # ensures the rejection is "real" (closed clearly back on the original
        # side) rather than edge-grazing the level.
        dist_close_to_level = abs(b.close - nearest.price)
        if dist_close_to_level < threshold * 0.5:
            # Too close to call — needs to clear the level before we fire.
            continue
        if dist_close_to_level > threshold * 5:
            # Far from any HVN, skip
            continue

        # Approach from below → treat as resistance (short)
        if b.high > nearest.price and b.close < nearest.price - threshold * 0.5:
            res = rej_resist.check_confirmation(level=nearest, bars=prior_window)
            if res.confirmed and res.pattern_name == "rejection_down":
                entry_idx = i
                entry_dir = "short"
                entry_level = nearest
                break

        # Approach from above → treat as support (long)
        if b.low < nearest.price and b.close > nearest.price + threshold * 0.5:
            res = rej_support.check_confirmation(level=nearest, bars=prior_window)
            if res.confirmed and res.pattern_name == "rejection_up":
                entry_idx = i
                entry_dir = "long"
                entry_level = nearest
                break

    if entry_idx is None or entry_level is None or entry_dir is None:
        return None
    if entry_idx + 1 >= len(today_bars):
        return None

    fill_bar = today_bars[entry_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    # Stop: just past the HVN edge
    if entry_dir == "long":
        stop_price = entry_level.price - cfg.stop_pad_dollar
    else:
        stop_price = entry_level.price + cfg.stop_pad_dollar

    if entry_dir == "long" and stop_price >= entry_price:
        return None
    if entry_dir == "short" and stop_price <= entry_price:
        return None

    per_share_risk = abs(entry_price - stop_price)
    # Reject trades where the stop is structurally too tight — pad the stop
    # to at least 0.15% of entry price to avoid noise stop-outs. This is
    # the bar-level analog of "stop wider than min spread + slippage".
    min_risk = entry_price * 0.0015
    if per_share_risk < min_risk:
        # Push the stop further out
        if entry_dir == "long":
            stop_price = entry_price - min_risk
        else:
            stop_price = entry_price + min_risk
        per_share_risk = min_risk
    if per_share_risk <= 0:
        return None

    # Target: next HVN on the opposite side; fallback to R-multiple.
    target_price = _opposite_hvn(level_set, entry_price, entry_dir)
    if target_price is None:
        # Fallback: 1.5R extension
        if entry_dir == "long":
            target_price = entry_price + cfg.fallback_r_multiple * per_share_risk
        else:
            target_price = entry_price - cfg.fallback_r_multiple * per_share_risk

    qty = int(cfg.risk_dollars // per_share_risk)
    if qty <= 0:
        return None

    # Forward replay
    exit_price, exit_ts, exit_reason = _replay_to_exit(
        today_bars, entry_idx + 1, entry_price, stop_price, target_price, entry_dir,
        cfg.trade_window_end,
    )
    pnl = ((exit_price - entry_price) if entry_dir == "long"
           else (entry_price - exit_price)) * qty
    r_mult = pnl / cfg.risk_dollars if cfg.risk_dollars > 0 else 0.0

    return Trade(
        strategy="vp_rejection",
        symbol=symbol,
        session_date=today_date,
        direction=entry_dir,
        level_kind=entry_level.kind,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=stop_price,
        target_price=target_price,
        qty=qty,
        risk_dollars=cfg.risk_dollars,
        pnl=pnl,
        r_multiple=r_mult,
        exit_reason=exit_reason,
        price_tier=price_tier(entry_price),
        vix_proxy=vix_value,
    )


def _simulate_breakout_day(
    symbol: str,
    today_bars: list[Bar],
    prior_bars: list[Bar],
    cfg: VPBreakoutConfig,
    vix_value: float,
) -> Optional[Trade]:
    """One day, one symbol, breakout through LVN."""
    if not today_bars or not prior_bars:
        return None

    today_date = today_bars[0].timestamp.date()
    src = VolumeProfileSource(
        lookback_sessions=cfg.lookback_sessions,
        bin_pct=cfg.bin_pct,
        hvn_multiplier=cfg.hvn_multiplier,
        lvn_multiplier=cfg.lvn_multiplier,
        emit_poc=False,
        emit_hvn=True,
        emit_lvn=True,
        target_date=today_date,
    )
    history = BarHistory(symbol=symbol, bars=prior_bars + today_bars)
    level_set = src.compute_levels(symbol, history)
    if not level_set.levels:
        return None

    lvn_levels = [l for l in level_set.levels if l.kind == "LVN"]
    hvn_levels = [l for l in level_set.levels if l.kind == "HVN"]
    if not lvn_levels or not hvn_levels:
        return None

    arrival = ArrivalDetector(proximity_pct=cfg.proximity_pct)
    bc = BreakoutCandle(
        min_vol_mult=cfg.min_vol_mult,
        min_breakout_pct=cfg.min_breakout_pct,
        require_close_beyond=True,
    )

    entry_idx: Optional[int] = None
    entry_dir: Optional[str] = None
    entry_level: Optional[Level] = None

    # Skip first 10 bars (avoid open-noise)
    min_bar_idx = 10

    # Track whether we've already crossed each LVN cluster — once we cross,
    # we shouldn't re-fire on subsequent bars that close at the same level.
    crossed_long: set[int] = set()  # bin indices already broken upward
    crossed_short: set[int] = set()

    for i in range(min_bar_idx, len(today_bars)):
        b = today_bars[i]
        if b.timestamp.time() < cfg.trade_window_start:
            continue
        if b.timestamp.time() >= cfg.trade_window_end:
            break

        prior_window = today_bars[: i + 1]
        prior_close = today_bars[i - 1].close

        fired_lvn: Optional[Level] = None
        fired_dir: Optional[str] = None
        for lvn in lvn_levels:
            bin_idx = lvn.metadata.get("bin_idx", -1)
            edge_high = lvn.metadata.get(
                "cluster_high_price",
                lvn.price + lvn.metadata.get("bin_width", 0.1) / 2,
            )
            edge_low = lvn.metadata.get(
                "cluster_low_price",
                lvn.price - lvn.metadata.get("bin_width", 0.1) / 2,
            )

            # Long: prior close at-or-below upper edge, this close clearly above.
            if bin_idx not in crossed_long:
                if (
                    prior_close <= edge_high + 0.01
                    and b.close > edge_high + b.close * cfg.min_breakout_pct
                ):
                    edge_level = Level(
                        price=float(edge_high),
                        kind="HVN",
                        session_date=lvn.session_date,
                        metadata={},
                    )
                    res = bc.check_confirmation(level=edge_level, bars=prior_window)
                    if res.confirmed and res.metadata.get("direction") == "long":
                        fired_lvn = lvn
                        fired_dir = "long"
                        break
                if b.close > edge_high:
                    crossed_long.add(bin_idx)

            # Short: prior close at-or-above lower edge, this close clearly below.
            if bin_idx not in crossed_short:
                if (
                    prior_close >= edge_low - 0.01
                    and b.close < edge_low - b.close * cfg.min_breakout_pct
                ):
                    edge_level = Level(
                        price=float(edge_low),
                        kind="VAL",
                        session_date=lvn.session_date,
                        metadata={},
                    )
                    res = bc.check_confirmation(level=edge_level, bars=prior_window)
                    if res.confirmed and res.metadata.get("direction") == "short":
                        fired_lvn = lvn
                        fired_dir = "short"
                        break
                if b.close < edge_low:
                    crossed_short.add(bin_idx)

        if fired_lvn is not None and fired_dir is not None:
            entry_idx = i
            entry_dir = fired_dir
            entry_level = fired_lvn
            break

    if entry_idx is None or entry_level is None or entry_dir is None:
        return None
    if entry_idx + 1 >= len(today_bars):
        return None

    fill_bar = today_bars[entry_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    # Stop: prior bar's low (long) / high (short) + pad
    prior_bar = today_bars[entry_idx]
    if entry_dir == "long":
        stop_price = prior_bar.low - cfg.stop_pad_dollar
    else:
        stop_price = prior_bar.high + cfg.stop_pad_dollar

    if entry_dir == "long" and stop_price >= entry_price:
        return None
    if entry_dir == "short" and stop_price <= entry_price:
        return None

    per_share_risk = abs(entry_price - stop_price)
    min_risk = entry_price * 0.0015
    if per_share_risk < min_risk:
        if entry_dir == "long":
            stop_price = entry_price - min_risk
        else:
            stop_price = entry_price + min_risk
        per_share_risk = min_risk
    if per_share_risk <= 0:
        return None

    # Target: next HVN above (long) / below (short); fallback R-multiple.
    target_price = _next_hvn(hvn_levels, entry_price, entry_dir)
    if target_price is None:
        if entry_dir == "long":
            target_price = entry_price + cfg.target_r * per_share_risk
        else:
            target_price = entry_price - cfg.target_r * per_share_risk

    qty = int(cfg.risk_dollars // per_share_risk)
    if qty <= 0:
        return None

    exit_price, exit_ts, exit_reason = _replay_to_exit(
        today_bars, entry_idx + 1, entry_price, stop_price, target_price, entry_dir,
        cfg.trade_window_end,
    )
    pnl = ((exit_price - entry_price) if entry_dir == "long"
           else (entry_price - exit_price)) * qty
    r_mult = pnl / cfg.risk_dollars if cfg.risk_dollars > 0 else 0.0

    return Trade(
        strategy="vp_breakout",
        symbol=symbol,
        session_date=today_date,
        direction=entry_dir,
        level_kind=entry_level.kind,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=stop_price,
        target_price=target_price,
        qty=qty,
        risk_dollars=cfg.risk_dollars,
        pnl=pnl,
        r_multiple=r_mult,
        exit_reason=exit_reason,
        price_tier=price_tier(entry_price),
        vix_proxy=vix_value,
    )


def _opposite_hvn(
    level_set: LevelSet,
    entry_price: float,
    direction: str,
) -> Optional[float]:
    """Find the next HVN/POC on the opposite side of entry."""
    candidates = [l for l in level_set.levels if l.kind in ("HVN", "POC")]
    if direction == "long":
        higher = [l.price for l in candidates if l.price > entry_price]
        if not higher:
            return None
        return min(higher)
    lower = [l.price for l in candidates if l.price < entry_price]
    if not lower:
        return None
    return max(lower)


def _next_hvn(
    hvn_levels: list[Level],
    entry_price: float,
    direction: str,
) -> Optional[float]:
    if direction == "long":
        higher = [l.price for l in hvn_levels if l.price > entry_price]
        if not higher:
            return None
        return min(higher)
    lower = [l.price for l in hvn_levels if l.price < entry_price]
    if not lower:
        return None
    return max(lower)


def _replay_to_exit(
    bars: list[Bar],
    start_idx: int,
    entry_price: float,
    stop_price: float,
    target_price: Optional[float],
    direction: str,
    window_end: time,
) -> tuple[float, datetime, str]:
    """Forward replay from start_idx onwards."""
    for j in range(start_idx, len(bars)):
        b = bars[j]
        if b.timestamp.time() >= window_end:
            return b.close, b.timestamp, "session_close"
        if direction == "long":
            if b.low <= stop_price:
                return stop_price, b.timestamp, "stop"
            if target_price is not None and b.high >= target_price:
                return target_price, b.timestamp, "target"
        else:
            if b.high >= stop_price:
                return stop_price, b.timestamp, "stop"
            if target_price is not None and b.low <= target_price:
                return target_price, b.timestamp, "target"
    last = bars[-1]
    return last.close, last.timestamp, "session_close"


# ---------------------------------------------------------------------------
# Multi-symbol multi-day driver
# ---------------------------------------------------------------------------


@dataclass
class BacktestResult:
    trades: list[Trade] = field(default_factory=list)
    starting_balance: float = 100_000.0
    skipped_vix: int = 0
    n_session_symbol_pairs: int = 0


def _enumerate_sessions(start: date, end: date) -> list[date]:
    """All trading dates with AAPL coverage in [start, end]."""
    aapl_dir = CACHE_ROOT / "AAPL"
    if not aapl_dir.exists():
        return []
    out: list[date] = []
    for fp in sorted(aapl_dir.glob("1m_*.parquet")):
        try:
            d = pd.Timestamp(fp.stem.replace("1m_", "")).date()
        except Exception:
            continue
        if start <= d <= end:
            out.append(d)
    return out


def run_strategy(
    strategy: str,                              # "rejection" | "breakout"
    cfg: VPRejectionConfig | VPBreakoutConfig,
    *,
    start_date: date,
    end_date: date,
    universe: tuple[str, ...] = UNIVERSE,
    vix_suppress_threshold: Optional[float] = None,
    vix_series: Optional[dict[date, float]] = None,
) -> BacktestResult:
    """Run one VP strategy across (symbol, day) cells.

    If `vix_suppress_threshold` is not None, sessions where the vix proxy
    exceeds the threshold are skipped entirely (no entries). `vix_series`
    is computed once and reused across the run.
    """
    sessions = _enumerate_sessions(start_date, end_date)
    if vix_series is None:
        vix_series = _compute_session_vix_proxy(sessions, universe=universe)

    trades: list[Trade] = []
    skipped_vix = 0
    pair_count = 0

    for d in sessions:
        v = float(vix_series.get(d, 18.0))
        if vix_suppress_threshold is not None and v >= vix_suppress_threshold:
            # Track suppression at session level (counts symbols that would
            # have been evaluated).
            for sym in universe:
                # Cheap existence check
                fp = CACHE_ROOT / sym / f"1m_{d.isoformat()}.parquet"
                if fp.exists():
                    skipped_vix += 1
            continue

        for sym in universe:
            today_bars = load_day_bars(sym, d)
            if not today_bars:
                continue
            pair_count += 1
            prior_bars = load_prior_n_sessions(sym, d, cfg.lookback_sessions)
            if not prior_bars:
                continue
            if strategy == "rejection":
                trade = _simulate_rejection_day(sym, today_bars, prior_bars, cfg, v)
            elif strategy == "breakout":
                trade = _simulate_breakout_day(sym, today_bars, prior_bars, cfg, v)
            else:
                raise ValueError(f"unknown strategy: {strategy}")
            if trade is not None:
                trades.append(trade)

    return BacktestResult(
        trades=trades,
        starting_balance=cfg.starting_balance,
        skipped_vix=skipped_vix,
        n_session_symbol_pairs=pair_count,
    )


@dataclass
class CombinedResults:
    """Result bundle from a single pass over the data, producing all 6
    backtest variants (rejection/breakout/portfolio × vix_on/vix_off).
    """
    rej_off: BacktestResult
    bo_off: BacktestResult
    port_off: BacktestResult
    rej_on: BacktestResult
    bo_on: BacktestResult
    port_on: BacktestResult


def run_all_variants(
    rej_cfg: VPRejectionConfig,
    bo_cfg: VPBreakoutConfig,
    *,
    start_date: date,
    end_date: date,
    universe: tuple[str, ...] = UNIVERSE,
    vix_suppress_threshold: float = 45.0,
    vix_series: Optional[dict[date, float]] = None,
    progress_every: int = 25,
) -> CombinedResults:
    """Single-pass driver: for each (sym, day) cell, compute both strategies
    and accumulate the 6 result buckets simultaneously. Cuts I/O by ~6x vs
    running each strategy separately.
    """
    sessions = _enumerate_sessions(start_date, end_date)
    if vix_series is None:
        vix_series = _compute_session_vix_proxy(sessions, universe=universe)

    rej_trades_off: list[Trade] = []
    bo_trades_off: list[Trade] = []
    port_trades_off: list[Trade] = []
    rej_trades_on: list[Trade] = []
    bo_trades_on: list[Trade] = []
    port_trades_on: list[Trade] = []
    skipped_vix_pairs = 0
    pair_count = 0

    for s_i, d in enumerate(sessions):
        if progress_every and s_i and s_i % progress_every == 0:
            log.info(
                "  [%d/%d] sessions done; trades so far rej=%d bo=%d port=%d",
                s_i, len(sessions),
                len(rej_trades_off), len(bo_trades_off), len(port_trades_off),
            )
        v = float(vix_series.get(d, 18.0))
        vix_suppressed = v >= vix_suppress_threshold

        for sym in universe:
            today_bars = load_day_bars(sym, d)
            if not today_bars:
                continue
            pair_count += 1
            prior_bars = load_prior_n_sessions(sym, d, rej_cfg.lookback_sessions)
            if not prior_bars:
                continue

            rej_trade = _simulate_rejection_day(sym, today_bars, prior_bars, rej_cfg, v)
            bo_trade = _simulate_breakout_day(sym, today_bars, prior_bars, bo_cfg, v)

            # VIX-off bucket: every trade lands
            if rej_trade is not None:
                rej_trades_off.append(rej_trade)
            if bo_trade is not None:
                bo_trades_off.append(bo_trade)
            if rej_trade is None and bo_trade is None:
                pass
            else:
                if rej_trade is None:
                    winner = bo_trade
                elif bo_trade is None:
                    winner = rej_trade
                else:
                    winner = bo_trade if bo_trade.entry_ts <= rej_trade.entry_ts else rej_trade
                port_trades_off.append(winner)

            # VIX-on bucket: skip if regime suppressed
            if vix_suppressed:
                skipped_vix_pairs += 1
                continue
            if rej_trade is not None:
                rej_trades_on.append(rej_trade)
            if bo_trade is not None:
                bo_trades_on.append(bo_trade)
            if rej_trade is None and bo_trade is None:
                pass
            else:
                if rej_trade is None:
                    winner = bo_trade
                elif bo_trade is None:
                    winner = rej_trade
                else:
                    winner = bo_trade if bo_trade.entry_ts <= rej_trade.entry_ts else rej_trade
                port_trades_on.append(winner)

    def _wrap(trades: list[Trade]) -> BacktestResult:
        return BacktestResult(
            trades=trades,
            starting_balance=rej_cfg.starting_balance,
            skipped_vix=skipped_vix_pairs,
            n_session_symbol_pairs=pair_count,
        )

    return CombinedResults(
        rej_off=_wrap(rej_trades_off),
        bo_off=_wrap(bo_trades_off),
        port_off=_wrap(port_trades_off),
        rej_on=_wrap(rej_trades_on),
        bo_on=_wrap(bo_trades_on),
        port_on=_wrap(port_trades_on),
    )


def run_portfolio(
    rej_cfg: VPRejectionConfig,
    bo_cfg: VPBreakoutConfig,
    *,
    start_date: date,
    end_date: date,
    universe: tuple[str, ...] = UNIVERSE,
    vix_suppress_threshold: Optional[float] = None,
    vix_series: Optional[dict[date, float]] = None,
) -> BacktestResult:
    """Run both strategies with per-symbol-per-day lock (first-in-time wins).

    Mirrors Wave 3 portfolio_backtest semantics: each (symbol, day) cell
    has at most one position across both strategies.
    """
    sessions = _enumerate_sessions(start_date, end_date)
    if vix_series is None:
        vix_series = _compute_session_vix_proxy(sessions, universe=universe)

    trades: list[Trade] = []
    skipped_vix = 0
    pair_count = 0

    for d in sessions:
        v = float(vix_series.get(d, 18.0))
        if vix_suppress_threshold is not None and v >= vix_suppress_threshold:
            for sym in universe:
                fp = CACHE_ROOT / sym / f"1m_{d.isoformat()}.parquet"
                if fp.exists():
                    skipped_vix += 1
            continue

        for sym in universe:
            today_bars = load_day_bars(sym, d)
            if not today_bars:
                continue
            pair_count += 1
            prior_bars = load_prior_n_sessions(sym, d, rej_cfg.lookback_sessions)
            if not prior_bars:
                continue

            rej_trade = _simulate_rejection_day(sym, today_bars, prior_bars, rej_cfg, v)
            bo_trade = _simulate_breakout_day(sym, today_bars, prior_bars, bo_cfg, v)

            if rej_trade is None and bo_trade is None:
                continue
            if rej_trade is None:
                winner = bo_trade
            elif bo_trade is None:
                winner = rej_trade
            else:
                # First-in-time wins
                if bo_trade.entry_ts <= rej_trade.entry_ts:
                    winner = bo_trade
                else:
                    winner = rej_trade
            if winner is not None:
                trades.append(winner)

    # Portfolio starting balance: shared single account.
    return BacktestResult(
        trades=trades,
        starting_balance=rej_cfg.starting_balance,
        skipped_vix=skipped_vix,
        n_session_symbol_pairs=pair_count,
    )
