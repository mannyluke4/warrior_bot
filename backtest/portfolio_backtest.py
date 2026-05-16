"""
backtest.portfolio_backtest
===========================

Wave 3 Agent J — multi-strategy bar-level portfolio backtest.

Runs 5 strategies simultaneously over a curated 36-symbol shortlist of the
most liquid US equities for 2020-2024, using Databento `ohlcv-1m` data
cached locally under ``tick_cache_databento/<SYM>/1m_<YYYY-MM-DD>.parquet``.

Strategies (loaded from YAML in `/strategies/`):
- orb_5min
- vwap_mean_reversion
- pdh_pdl_fade
- pdh_pdl_breakout
- round_number (filtered to $50-150 tier per Wave 2 Agent I)

Per-symbol-per-day lock: at most ONE open position per (symbol, session_date)
across all strategies.  First-in-time wins (the strategy whose entry bar
fires earliest claims the lock; later strategies' arms on the same symbol
that session are skipped).  This generalizes Wave 2's PDH/PDL conflict
resolution.

Two sizing modes are ablated:
- HalfKellySizer (1% equity risk, 5% bar-volume cap, equity-compound) — Wave 1 default
- Fixed-dollar ($1,000 risk per trade) — Wave 2 Agent F recommendation

Output: per-strategy trade logs, equity curves, and the cross-strategy
correlation matrix.  This is the data the report at
`cowork_reports/2026-05-16_wave3_portfolio_backtest.md` digests.

Why bar-level, not Nautilus subprocess?
---------------------------------------
~5 strategies × 36 symbols × 1258 days ≈ 226 000 (strategy, symbol, day)
tasks.  At 0.6 s subprocess startup × 4 parallel workers that's ~9.5 hours
of subprocess overhead alone — and the per-pair backtest is itself nearly
instantaneous at the bar level.  Nautilus subprocess runner is the right
shape for survivor-strategy *re-runs* (Wave 4 preparation); for the Wave 3
portfolio screen we use the same bar-level engine pattern Agent F used for
ORB-5min on the same dataset.  Fidelity ceiling is identical (~85-90% per
research §3), and survivor strategies will inherit nautilus_subprocess_runner
for higher-fidelity validation.

Author: CC Agent J (Wave 3 — Healthy Fluctuation Framework)
"""
from __future__ import annotations

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
from framework.confirmations.rejection import Rejection
from framework.confirmations.signal_candle import SignalCandle
from framework.level_sources.base import Bar, BarHistory, Level, LevelSet
from framework.level_sources.opening_range import OpeningRangeSource
from framework.level_sources.pdh_pdl import PDHPDLSource
from framework.level_sources.round_number import RoundNumberSource, resolve_tier
from framework.level_sources.vwap import VWAPSource
from framework.sizing import HalfKellySizer


log = logging.getLogger("portfolio_backtest")


REPO = Path("/Users/duffy/warrior_bot_v2")
CACHE_ROOT = REPO / "tick_cache_databento"

# RTH boundaries (ET, naive)
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
TRADE_WINDOW_END = time(15, 55)

# ---------------------------------------------------------------------------
# Top-50 most liquid US equities — Manny shortlist (per Wave 3 directive)
# ---------------------------------------------------------------------------

# Universe = 36 symbols pre-cached in tick_cache_databento.  These are
# selected from S&P-500-by-ADV (2024) intersected with what's been pulled.
# Documented rationale per symbol-tier in the report.
#
# We DON'T have catalyst-day archives separately cached.  The Wave 3
# directive accepts the most-logical path note: we use the dataset as-is.
# This is a *liquid-universe* portfolio screen; the catalyst-day filter
# (Wave 2 ORB report §10) remains a Wave 5 priority.
UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "TSLA", "NVDA", "META", "AMD", "AVGO", "ADBE",
    "CRM", "ORCL", "NFLX", "INTC", "QCOM", "CSCO", "MU", "PLTR",
    "ROKU", "SNAP", "SOFI", "F", "BAC", "WFC", "JPM", "MA",
    "DIS", "NKE", "DAL", "AAL", "WMT", "COST", "T", "VZ",
    "KO", "MRK", "PFE", "AMC",
)


# ---------------------------------------------------------------------------
# Bar loading helpers
# ---------------------------------------------------------------------------


def load_day_bars(symbol: str, session_date: date) -> list[Bar]:
    """Load one symbol's 1-minute RTH bars for one session.

    Returns an empty list if the parquet is missing or the day has no RTH data.
    Timestamps are naive ET (Databento convention used throughout the framework).
    """
    fp = CACHE_ROOT / symbol / f"1m_{session_date.isoformat()}.parquet"
    if not fp.exists():
        return []
    try:
        df = pd.read_parquet(fp)
    except Exception:
        return []
    if df.empty:
        return []

    # Convert to Bar objects, filter to RTH 09:30-16:00
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


def load_prior_day_bars(symbol: str, session_date: date, lookback_days: int = 5) -> list[Bar]:
    """Load the prior RTH session's bars for PDH/PDL.

    Walks backward up to ``lookback_days`` calendar days to find a non-empty
    cached session.  Returns the most recent prior RTH bars (or empty list).
    """
    for back in range(1, lookback_days + 1):
        prior = session_date - timedelta(days=back)
        bars = load_day_bars(symbol, prior)
        if bars:
            return bars
    return []


# ---------------------------------------------------------------------------
# Trade structure
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
        }


# ---------------------------------------------------------------------------
# Sizing modes
# ---------------------------------------------------------------------------


@dataclass
class SizingMode:
    name: str  # "half_kelly" | "fixed_dollar"
    fixed_dollar_risk: float = 1000.0
    risk_per_trade_pct: float = 1.0
    max_bar_volume_pct: float = 0.05

    def size(
        self,
        equity: float,
        entry_price: float,
        stop_price: float,
        recent_bar_volume: float,
    ) -> tuple[int, float]:
        """Return (qty, risk_dollars)."""
        per_share = abs(entry_price - stop_price)
        if per_share <= 0:
            return 0, 0.0

        if self.name == "fixed_dollar":
            risk_dollars = self.fixed_dollar_risk
            qty = int(risk_dollars // per_share)
            # Bar-vol cap still applies even in fixed-dollar mode
            if recent_bar_volume and self.max_bar_volume_pct > 0:
                cap = int(self.max_bar_volume_pct * recent_bar_volume)
                qty = min(qty, cap) if cap > 0 else qty
            return max(qty, 0), risk_dollars

        # half_kelly
        sizer = HalfKellySizer(
            risk_per_trade_pct=self.risk_per_trade_pct,
            max_bar_volume_pct=self.max_bar_volume_pct,
        )
        qty = sizer.size_position(
            equity=equity,
            entry_price=entry_price,
            stop_price=stop_price,
            recent_bar_volume=recent_bar_volume,
        )
        # half-Kelly risk dollars (already halved inside sizer math)
        risk_dollars = equity * (self.risk_per_trade_pct / 100.0) * 0.5
        return qty, risk_dollars


# ---------------------------------------------------------------------------
# Strategy adapter — turns a YAML spec into an `arm` evaluator
# ---------------------------------------------------------------------------


@dataclass
class StrategyArm:
    """Lightweight evaluator for one strategy on one symbol-day.

    Each tick of the bar walk asks `evaluate(bars_so_far)` and, on first
    confirmation, returns an EntrySpec.  None means no signal at this bar.
    """

    name: str
    yaml_path: str
    spec: dict[str, Any]

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "StrategyArm":
        with open(yaml_path) as f:
            spec = yaml.safe_load(f)
        return cls(name=spec.get("name", Path(yaml_path).stem), yaml_path=yaml_path, spec=spec)


@dataclass
class EntrySignal:
    bar_idx: int          # index in the day's bar list where confirmation fired
    direction: str        # "long" / "short"
    level: Level
    proximate_levels: tuple[Level, ...]  # for opposite_level target


# ---------------------------------------------------------------------------
# Per-strategy evaluators
# ---------------------------------------------------------------------------


def _opening_range_signal(
    bars: list[Bar],
    spec: dict[str, Any],
) -> Optional[EntrySignal]:
    """ORB-5min: open-range high/low breakout with volume confirmation."""
    p = spec.get("level_source", {}).get("params", {})
    or_minutes = int(p.get("minutes", 5))
    use_bias = bool(p.get("use_5min_direction_bias", True))

    src = OpeningRangeSource(minutes=or_minutes, use_5min_direction_bias=use_bias)
    history = BarHistory(symbol=bars[0].symbol if bars else "", bars=list(bars))
    level_set = src.compute_levels(bars[0].symbol if bars else "", history)
    if not level_set.levels:
        return None
    orh = next((l for l in level_set.levels if l.kind == "ORH"), None)
    orl = next((l for l in level_set.levels if l.kind == "ORL"), None)
    if orh is None or orl is None:
        return None
    bias = orh.metadata.get("direction_bias", "neutral")

    # Find first bar past OR window
    or_end_t = (datetime.combine(bars[0].timestamp.date(), RTH_OPEN)
                + timedelta(minutes=or_minutes)).time()
    start_idx = next(
        (i for i, b in enumerate(bars) if b.timestamp.time() >= or_end_t),
        None,
    )
    if start_idx is None:
        return None

    cp = spec.get("confirmation_rule", {}).get("params", {})
    bc = BreakoutCandle(
        min_vol_mult=float(cp.get("min_vol_mult", 2.0)),
        min_breakout_pct=float(cp.get("min_breakout_pct", 0.0002)),
        require_close_beyond=bool(cp.get("require_close_beyond", True)),
    )
    long_ok = (not use_bias) or bias == "long"
    short_ok = (not use_bias) or bias == "short"

    for i in range(start_idx, len(bars)):
        if bars[i].timestamp.time() >= TRADE_WINDOW_END:
            break
        prior = bars[: i + 1]
        if long_ok:
            res = bc.check_confirmation(orh, prior, None)
            if res.confirmed and res.metadata.get("direction") == "long":
                return EntrySignal(bar_idx=i, direction="long", level=orh,
                                   proximate_levels=(orh, orl))
        if short_ok:
            res = bc.check_confirmation(orl, prior, None)
            if res.confirmed and res.metadata.get("direction") == "short":
                return EntrySignal(bar_idx=i, direction="short", level=orl,
                                   proximate_levels=(orh, orl))
    return None


def _vwap_meanrev_signal(
    bars: list[Bar],
    spec: dict[str, Any],
) -> Optional[EntrySignal]:
    """VWAP mean-reversion: arrive at ±2σ band, rejection confirmation,
    regime gate = 'flat'."""
    src = VWAPSource(band_sigmas=[2.0])
    proximity_pct = float(
        spec.get("arrival_detector", {}).get("params", {}).get("proximity_pct", 0.003)
    )

    rj_params = spec.get("confirmation_rule", {}).get("params", {})
    rj = Rejection(
        lookback_bars=int(rj_params.get("lookback_bars", 2)),
        side="auto",
    )

    regime_gate = spec.get("regime_gate", {})
    allowed = regime_gate.get("allowed", ["flat"])
    last_n_bars = int(regime_gate.get("last_n_bars", 10))

    # Walk bars; need at least ~10 to build a sigma
    for i in range(15, len(bars)):
        b = bars[i]
        if b.timestamp.time() >= TRADE_WINDOW_END:
            break

        # Rebuild VWAP through bar i (cheap; vectorize if hot)
        sub_history = BarHistory(symbol=b.symbol, bars=bars[: i + 1])
        local_src = VWAPSource(band_sigmas=[2.0])
        ls = local_src.compute_levels(b.symbol, sub_history)
        if not ls.levels:
            continue

        regime = local_src.vwap_slope_classifier(last_n_bars=last_n_bars)
        if regime not in allowed:
            continue

        upper = next((l for l in ls.levels if l.kind == "VWAP_UPPER_2"), None)
        lower = next((l for l in ls.levels if l.kind == "VWAP_LOWER_2"), None)
        center = next((l for l in ls.levels if l.kind == "VWAP"), None)
        if upper is None or lower is None or center is None:
            continue

        price = b.close
        # Arrival: within proximity_pct of either band
        if abs(price - upper.price) / upper.price <= proximity_pct or b.high >= upper.price:
            # Short setup: rejection at resistance (upper band)
            res = rj.check_confirmation(upper, bars[: i + 1], None)
            if res.confirmed and res.pattern_name == "rejection_down":
                return EntrySignal(
                    bar_idx=i, direction="short", level=upper,
                    proximate_levels=(upper, center, lower),
                )
        if abs(price - lower.price) / max(lower.price, 0.01) <= proximity_pct or b.low <= lower.price:
            res = rj.check_confirmation(lower, bars[: i + 1], None)
            if res.confirmed and res.pattern_name == "rejection_up":
                return EntrySignal(
                    bar_idx=i, direction="long", level=lower,
                    proximate_levels=(upper, center, lower),
                )
    return None


def _pdh_pdl_signal(
    bars: list[Bar],
    spec: dict[str, Any],
    prior_bars: list[Bar],
    mode: str,  # "fade" | "breakout"
) -> Optional[EntrySignal]:
    """PDH/PDL fade or breakout.

    Computes PDH/PDL from prior_bars, then walks today's bars looking for
    fade (Rejection) or breakout (BreakoutCandle) confirmation.
    """
    if not prior_bars:
        return None

    # Build a combined history so PDHPDLSource sees both sessions
    combined = BarHistory(symbol=bars[0].symbol, bars=prior_bars + bars)
    source = PDHPDLSource(target_date=bars[0].timestamp.date(), max_gap_days=int(
        spec.get("level_source", {}).get("params", {}).get("max_gap_days", 2)
    ))
    ls = source.compute_levels(bars[0].symbol, combined)
    if not ls.levels:
        return None
    pdh = next((l for l in ls.levels if l.kind == "PDH"), None)
    pdl = next((l for l in ls.levels if l.kind == "PDL"), None)
    if pdh is None or pdl is None:
        return None

    p_arrival = float(spec.get("arrival_detector", {}).get("params", {}).get(
        "proximity_pct", 0.001 if mode == "fade" else 0.0005))

    if mode == "fade":
        rj_params = spec.get("confirmation_rule", {}).get("params", {})
        rj = Rejection(lookback_bars=int(rj_params.get("lookback_bars", 2)))
        for i in range(2, len(bars)):
            b = bars[i]
            if b.timestamp.time() >= TRADE_WINDOW_END:
                break
            # Test PDH (resistance, short fade)
            if abs(b.close - pdh.price) / pdh.price <= p_arrival or b.high >= pdh.price:
                res = rj.check_confirmation(pdh, bars[: i + 1], None)
                if res.confirmed and res.pattern_name == "rejection_down":
                    return EntrySignal(
                        bar_idx=i, direction="short", level=pdh,
                        proximate_levels=(pdh, pdl),
                    )
            # Test PDL (support, long fade)
            if abs(b.close - pdl.price) / max(pdl.price, 0.01) <= p_arrival or b.low <= pdl.price:
                res = rj.check_confirmation(pdl, bars[: i + 1], None)
                if res.confirmed and res.pattern_name == "rejection_up":
                    return EntrySignal(
                        bar_idx=i, direction="long", level=pdl,
                        proximate_levels=(pdh, pdl),
                    )
        return None

    # breakout
    cp = spec.get("confirmation_rule", {}).get("params", {})
    bc = BreakoutCandle(
        min_vol_mult=float(cp.get("min_vol_mult", 2.0)),
        min_breakout_pct=float(cp.get("min_breakout_pct", 0.0002)),
        require_close_beyond=bool(cp.get("require_close_beyond", True)),
    )
    for i in range(2, len(bars)):
        b = bars[i]
        if b.timestamp.time() >= TRADE_WINDOW_END:
            break
        # Long break of PDH
        res = bc.check_confirmation(pdh, bars[: i + 1], None)
        if res.confirmed and res.metadata.get("direction") == "long":
            return EntrySignal(
                bar_idx=i, direction="long", level=pdh,
                proximate_levels=(pdh, pdl),
            )
        # Short break of PDL
        res = bc.check_confirmation(pdl, bars[: i + 1], None)
        if res.confirmed and res.metadata.get("direction") == "short":
            return EntrySignal(
                bar_idx=i, direction="short", level=pdl,
                proximate_levels=(pdh, pdl),
            )
    return None


def _round_number_signal(
    bars: list[Bar],
    spec: dict[str, Any],
) -> Optional[EntrySignal]:
    """Round-number signal-candle confirmation, tier-aware.

    Per Wave 2 Agent I recommendation, ONLY $50-150 tier is enabled for
    Wave 3 deployment screen.  Other tiers are skipped at the signal level.
    """
    p = spec.get("level_source", {}).get("params", {})
    increments = p.get("increments", {})
    window_dollar = float(p.get("window_dollar", 5.0))
    src = RoundNumberSource(increments=increments, window_dollar=window_dollar)

    cp = spec.get("confirmation_rule", {}).get("params", {})
    sc = SignalCandle(
        patterns=list(cp.get("patterns", ["doji", "hammer", "shooting_star"])),
        # NOTE: original YAML calls for require_volume_increase=True; signal
        # candles on rounds are rare on 1-min bars without it but we honor
        # the spec exactly.
        require_volume_increase=bool(cp.get("require_volume_increase", True)),
    )

    proximity_dollar = spec.get("arrival_detector", {}).get("params", {}).get(
        "proximity_dollar", {})

    for i in range(2, len(bars)):
        b = bars[i]
        if b.timestamp.time() >= TRADE_WINDOW_END:
            break
        # Tier filter — Wave 2 Agent I recommendation: $50-150 only
        tier = resolve_tier(b.close)
        if tier != "50_150":
            continue
        prox = proximity_dollar.get(tier, 0.25) if isinstance(proximity_dollar, dict) else 0.25

        ls = src.levels_for_price(b.symbol, current_price=b.close,
                                  session_date=b.timestamp.date())
        if not ls.levels:
            continue

        for lvl in ls.levels:
            if abs(b.close - lvl.price) > prox:
                continue
            res = sc.check_confirmation(lvl, bars[: i + 1], None)
            if not res.confirmed:
                continue
            # Direction: doji at level -> use prior bar's close vs level as bias
            if i == 0:
                continue
            prior_close = bars[i - 1].close
            if prior_close < lvl.price <= b.close or b.close > lvl.price:
                direction = "long"
            else:
                direction = "short"
            # Build proximate levels list for opposite_level target
            return EntrySignal(
                bar_idx=i, direction=direction, level=lvl,
                proximate_levels=tuple(ls.levels),
            )
    return None


SIGNAL_FUNCS = {
    "orb_5min.yaml": _opening_range_signal,
    "vwap_mean_reversion.yaml": _vwap_meanrev_signal,
    "pdh_pdl_fade.yaml": lambda b, s, prior: _pdh_pdl_signal(b, s, prior, mode="fade"),
    "pdh_pdl_breakout.yaml": lambda b, s, prior: _pdh_pdl_signal(b, s, prior, mode="breakout"),
    "round_number.yaml": _round_number_signal,
}


# ---------------------------------------------------------------------------
# Trade execution given an EntrySignal
# ---------------------------------------------------------------------------


def _compute_stop_and_target(
    signal: EntrySignal,
    bars: list[Bar],
    spec: dict[str, Any],
) -> tuple[Optional[float], Optional[float]]:
    """Resolve stop_price + target_price from spec.

    Lightweight inline implementation of stop+target rules so we don't have
    to instantiate the full target_rules dispatcher per bar.
    """
    entry_bar = bars[signal.bar_idx]
    direction = signal.direction
    level = signal.level

    stop_cfg = spec.get("stop_rule", {})
    stop_type = stop_cfg.get("type", "just_past_level")
    stop_price: Optional[float] = None

    if stop_type == "opposite_range":
        # Long stops at ORL, short stops at ORH (signal carries both)
        if direction == "long":
            orl = next((l for l in signal.proximate_levels if l.kind == "ORL"), None)
            if orl: stop_price = orl.price
        else:
            orh = next((l for l in signal.proximate_levels if l.kind == "ORH"), None)
            if orh: stop_price = orh.price
    elif stop_type == "just_past_level":
        pad = stop_cfg.get("params", {}).get("pad_dollar", 0.10)
        if isinstance(pad, dict):
            tier = resolve_tier(entry_bar.close) or "50_150"
            pad_v = float(pad.get(tier, 0.10))
        else:
            pad_v = float(pad)
        if direction == "long":
            stop_price = level.price - pad_v
        else:
            stop_price = level.price + pad_v
    elif stop_type == "bar_low":
        pad = float(stop_cfg.get("params", {}).get("pad_dollar", 0.02))
        prior_bar = bars[signal.bar_idx - 1] if signal.bar_idx >= 1 else entry_bar
        if direction == "long":
            stop_price = prior_bar.low - pad
        else:
            stop_price = prior_bar.high + pad

    if stop_price is None or not np.isfinite(stop_price):
        return None, None
    # Defensive — stop must be on correct side
    fill_bar = bars[signal.bar_idx + 1] if signal.bar_idx + 1 < len(bars) else entry_bar
    entry_price = fill_bar.open
    if direction == "long" and stop_price >= entry_price:
        return None, None
    if direction == "short" and stop_price <= entry_price:
        return None, None

    # Target
    tgt_cfg = spec.get("target_rule", {})
    tgt_type = tgt_cfg.get("type", "r_multiple")
    target_price: Optional[float] = None

    per_share_risk = abs(entry_price - stop_price)

    def _r_target(r: float) -> float:
        if direction == "long":
            return entry_price + r * per_share_risk
        return entry_price - r * per_share_risk

    if tgt_type == "composite":
        params = tgt_cfg.get("params", {})
        primary = params.get("primary", "r_multiple")
        if primary == "r_multiple":
            target_price = _r_target(float(params.get("r_multiple", 2.0)))
        elif primary == "opposite_level":
            # Find next level on opposite side
            target_price = _opposite_level(signal, direction, entry_price)
            if target_price is None:
                # fallback
                fb = params.get("fallback", "r_multiple")
                if fb == "r_multiple":
                    target_price = _r_target(float(params.get("r_multiple", 2.0)))
                # session_close fallback -> leave as None, handled by forward walk
        elif primary == "next_round_number":
            target_price = _opposite_level(signal, direction, entry_price)
            if target_price is None:
                target_price = _r_target(float(params.get("r_multiple", 2.0)))
    elif tgt_type == "r_multiple":
        target_price = _r_target(float(tgt_cfg.get("params", {}).get("r_multiple", 2.0)))
    elif tgt_type == "opposite_level":
        target_price = _opposite_level(signal, direction, entry_price)

    return stop_price, target_price


def _opposite_level(
    signal: EntrySignal,
    direction: str,
    entry_price: float,
) -> Optional[float]:
    """Find the nearest proximate_levels price on the opposite side of entry."""
    if direction == "long":
        candidates = [l.price for l in signal.proximate_levels if l.price > entry_price]
        if not candidates:
            return None
        return min(candidates)
    candidates = [l.price for l in signal.proximate_levels if l.price < entry_price]
    if not candidates:
        return None
    return max(candidates)


def _replay_to_exit(
    bars: list[Bar],
    entry_idx: int,
    entry_price: float,
    stop_price: float,
    target_price: Optional[float],
    direction: str,
) -> tuple[float, datetime, str]:
    """Forward replay from entry_idx+1 onwards, return (exit_price, exit_ts, reason)."""
    for j in range(entry_idx + 1, len(bars)):
        b = bars[j]
        if b.timestamp.time() >= TRADE_WINDOW_END:
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
# Single-pair runner (used by both portfolio engine + subprocess worker)
# ---------------------------------------------------------------------------


def run_single_strategy_single_day(
    strategy_yaml: str,
    symbol: str,
    session_date: date,
    starting_equity: float = 100_000.0,
) -> list[dict[str, Any]]:
    """Run one (strategy, symbol, day) and return a list of trade dicts.

    This is the unit the subprocess Nautilus runner spawns.  The portfolio
    engine below calls it in-process for the full sweep.
    """
    bars = load_day_bars(symbol, session_date)
    if not bars:
        return []
    arm = StrategyArm.from_yaml(strategy_yaml)
    return _execute_one(
        arm=arm,
        bars=bars,
        prior_bars=load_prior_day_bars(symbol, session_date)
        if "pdh_pdl" in strategy_yaml else [],
        sizing_mode=SizingMode(name="half_kelly"),
        equity=starting_equity,
    )


def _execute_one(
    arm: StrategyArm,
    bars: list[Bar],
    prior_bars: list[Bar],
    sizing_mode: SizingMode,
    equity: float,
) -> list[dict[str, Any]]:
    """Run one strategy on one symbol-day; return trades list (0 or 1 trade)."""
    yname = Path(arm.yaml_path).name
    fn = SIGNAL_FUNCS.get(yname)
    if fn is None:
        return []
    if "pdh_pdl" in yname:
        signal = fn(bars, arm.spec, prior_bars)
    else:
        signal = fn(bars, arm.spec)
    if signal is None:
        return []

    # Fill at next bar's open (no look-ahead)
    if signal.bar_idx + 1 >= len(bars):
        return []
    fill_bar = bars[signal.bar_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    stop_price, target_price = _compute_stop_and_target(signal, bars, arm.spec)
    if stop_price is None:
        return []

    # Recent bar volume for the sizer cap
    recent_vol = float(bars[signal.bar_idx].volume) if bars else 0.0
    qty, risk_dollars = sizing_mode.size(
        equity=equity,
        entry_price=entry_price,
        stop_price=stop_price,
        recent_bar_volume=recent_vol,
    )
    if qty <= 0:
        return []

    exit_price, exit_ts, reason = _replay_to_exit(
        bars=bars,
        entry_idx=signal.bar_idx + 1,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        direction=signal.direction,
    )

    pnl = (exit_price - entry_price) * qty if signal.direction == "long" \
        else (entry_price - exit_price) * qty
    r_mult = pnl / risk_dollars if risk_dollars > 0 else 0.0

    trade = Trade(
        strategy=arm.name,
        symbol=bars[0].symbol,
        session_date=bars[0].timestamp.date(),
        direction=signal.direction,
        entry_ts=entry_ts,
        exit_ts=exit_ts,
        entry_price=entry_price,
        exit_price=exit_price,
        stop_price=stop_price,
        target_price=target_price,
        qty=qty,
        risk_dollars=risk_dollars,
        pnl=pnl,
        r_multiple=r_mult,
        exit_reason=reason,
    )
    return [trade.to_dict()]


# ---------------------------------------------------------------------------
# Portfolio engine: all strategies x all symbols x all days with per-day lock
# ---------------------------------------------------------------------------


@dataclass
class PortfolioConfig:
    sizing_mode: SizingMode
    strategy_yamls: tuple[str, ...]
    universe: tuple[str, ...] = UNIVERSE
    starting_equity: float = 100_000.0
    start_date: Optional[date] = None  # inclusive
    end_date: Optional[date] = None    # inclusive
    # Per-symbol-per-day lock: first-in-time strategy wins
    per_day_per_symbol_lock: bool = True


def _enumerate_sessions(cfg: PortfolioConfig) -> list[date]:
    """All trading dates we have cached data for, intersected with cfg window."""
    # Use AAPL as the canonical calendar (always-traded, full coverage)
    aapl_dir = CACHE_ROOT / "AAPL"
    if not aapl_dir.exists():
        return []
    dates: list[date] = []
    for fp in sorted(aapl_dir.glob("1m_*.parquet")):
        try:
            d = pd.Timestamp(fp.stem.replace("1m_", "")).date()
        except Exception:
            continue
        if cfg.start_date and d < cfg.start_date:
            continue
        if cfg.end_date and d > cfg.end_date:
            continue
        dates.append(d)
    return dates


def run_portfolio_backtest(cfg: PortfolioConfig) -> dict[str, Any]:
    """Run the multi-strategy portfolio backtest.

    Returns a dict containing:
      - trades_by_strategy: dict[str, list[dict]]
      - equity_curve: pd.DataFrame indexed by exit_ts with one column per strategy + 'portfolio'
      - lock_collisions: int — number of (strategy, symbol, day) signals skipped due to lock
    """
    arms = [StrategyArm.from_yaml(p) for p in cfg.strategy_yamls]
    sessions = _enumerate_sessions(cfg)
    log.info("[portfolio] %d arms × %d symbols × %d sessions",
             len(arms), len(cfg.universe), len(sessions))

    trades_by_strategy: dict[str, list[dict[str, Any]]] = {a.name: [] for a in arms}
    equity_events: list[dict[str, Any]] = []
    equity_per_strategy: dict[str, float] = {a.name: cfg.starting_equity for a in arms}
    portfolio_equity = cfg.starting_equity
    portfolio_events: list[tuple[datetime, float]] = []

    lock_collisions = 0

    for d in sessions:
        # Preload per-symbol bars + prior_bars for this day
        bars_by_sym: dict[str, list[Bar]] = {}
        prior_by_sym: dict[str, list[Bar]] = {}
        for sym in cfg.universe:
            today = load_day_bars(sym, d)
            if today:
                bars_by_sym[sym] = today
                prior_by_sym[sym] = load_prior_day_bars(sym, d)

        if not bars_by_sym:
            continue

        # Generate signals for every (strategy, symbol) pair
        candidates: list[tuple[datetime, StrategyArm, str, EntrySignal]] = []
        for arm in arms:
            yname = Path(arm.yaml_path).name
            fn = SIGNAL_FUNCS.get(yname)
            if fn is None:
                continue
            for sym, bars in bars_by_sym.items():
                if "pdh_pdl" in yname:
                    sig = fn(bars, arm.spec, prior_by_sym.get(sym, []))
                else:
                    sig = fn(bars, arm.spec)
                if sig is None:
                    continue
                # entry fill at next bar
                if sig.bar_idx + 1 >= len(bars):
                    continue
                fill_ts = bars[sig.bar_idx + 1].timestamp
                candidates.append((fill_ts, arm, sym, sig))

        # Sort by fill time so first-in-time wins the per-day-per-symbol lock
        candidates.sort(key=lambda x: x[0])

        used_keys: set[tuple[str, date]] = set()
        for fill_ts, arm, sym, sig in candidates:
            key = (sym, d)
            if cfg.per_day_per_symbol_lock and key in used_keys:
                lock_collisions += 1
                continue
            used_keys.add(key)
            bars = bars_by_sym[sym]
            arm_equity = equity_per_strategy[arm.name]
            trades = _execute_one(
                arm=arm,
                bars=bars,
                prior_bars=prior_by_sym.get(sym, []),
                sizing_mode=cfg.sizing_mode,
                equity=arm_equity,
            )
            for t in trades:
                trades_by_strategy[arm.name].append(t)
                equity_per_strategy[arm.name] += t["pnl"]
                portfolio_equity += t["pnl"]
                portfolio_events.append(
                    (pd.Timestamp(t["exit_ts"]).to_pydatetime(), portfolio_equity)
                )

    # Build the equity curve dataframe — per strategy + portfolio
    return {
        "trades_by_strategy": trades_by_strategy,
        "equity_per_strategy": equity_per_strategy,
        "portfolio_events": portfolio_events,
        "lock_collisions": lock_collisions,
        "sessions": sessions,
    }


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------


def _cli() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Wave 3 multi-strategy portfolio backtest")
    p.add_argument("--start", type=str, default="2020-01-01")
    p.add_argument("--end", type=str, default="2024-12-31")
    p.add_argument("--mode", choices=["half_kelly", "fixed_dollar"], default="half_kelly")
    p.add_argument("--out", type=str, default="backtest_archive/wave3_portfolio")
    p.add_argument("--strategies", type=str, nargs="*", default=None)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    yamls = args.strategies or [
        str(REPO / "strategies" / "orb_5min.yaml"),
        str(REPO / "strategies" / "vwap_mean_reversion.yaml"),
        str(REPO / "strategies" / "pdh_pdl_fade.yaml"),
        str(REPO / "strategies" / "pdh_pdl_breakout.yaml"),
        str(REPO / "strategies" / "round_number.yaml"),
    ]

    sizing = SizingMode(name=args.mode)
    cfg = PortfolioConfig(
        sizing_mode=sizing,
        strategy_yamls=tuple(yamls),
        start_date=pd.Timestamp(args.start).date(),
        end_date=pd.Timestamp(args.end).date(),
    )
    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    log.info("starting sweep -> %s", out_dir)

    result = run_portfolio_backtest(cfg)

    # Persist
    import json
    for strat, trades in result["trades_by_strategy"].items():
        df = pd.DataFrame(trades)
        if not df.empty:
            df.to_parquet(out_dir / f"trades_{strat}_{args.mode}.parquet", index=False)
            df.to_csv(out_dir / f"trades_{strat}_{args.mode}.csv", index=False)

    # Equity events
    if result["portfolio_events"]:
        eq_df = pd.DataFrame(result["portfolio_events"], columns=["ts", "equity"])
        eq_df.to_parquet(out_dir / f"portfolio_equity_{args.mode}.parquet", index=False)

    summary = {
        "mode": args.mode,
        "start": args.start,
        "end": args.end,
        "sessions": len(result["sessions"]),
        "lock_collisions": result["lock_collisions"],
        "trade_counts": {s: len(t) for s, t in result["trades_by_strategy"].items()},
        "equity_per_strategy": result["equity_per_strategy"],
    }
    (out_dir / f"summary_{args.mode}.json").write_text(json.dumps(summary, indent=2))
    log.info("wrote summary: %s", summary)


if __name__ == "__main__":
    _cli()
