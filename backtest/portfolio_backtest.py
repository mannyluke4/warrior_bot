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
import os
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
from framework.sizing import HalfKellySizer, TieredSizer


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
    # release_on_stop instrumentation: True when this trade fired only because
    # an earlier (locked) trade's stop released the per-(symbol, day) lock.
    # Lets attribution analysis isolate the $427K recovery cohort.
    secondary_fill: bool = False

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
            "secondary_fill": self.secondary_fill,
        }


# ---------------------------------------------------------------------------
# Sizing modes
# ---------------------------------------------------------------------------


@dataclass
class SizingMode:
    """Sizing mode adapter.

    name: "half_kelly" | "fixed_dollar" | "tiered"
        - half_kelly: per-trade Half-Kelly with bar-volume cap (Wave 1)
        - fixed_dollar: fixed dollar risk per trade (Wave 2)
        - tiered: 9-tier equity ladder (Wave 4 Phase C1).  Instantiate
          via SizingMode.tiered(...) and the engine will route .size()
          calls through the bound TieredSizer.  Tier transitions happen
          on session boundaries — call tiered_sizer.on_session_close(...)
          from the engine's session loop.
    """

    name: str
    fixed_dollar_risk: float = 1000.0
    risk_per_trade_pct: float = 1.0
    max_bar_volume_pct: float = 0.05
    # Bound TieredSizer when name == "tiered"; None otherwise.
    tiered_sizer: Optional[TieredSizer] = None

    @classmethod
    def tiered(
        cls,
        initial_tier: int = 1,
        tier_lock: bool = False,
        auto_advance: bool = True,
        state_path: Optional[Path] = None,
    ) -> "SizingMode":
        """Build a SizingMode wired to a TieredSizer instance."""
        ts = TieredSizer(
            initial_tier=initial_tier,
            tier_lock=tier_lock,
            auto_advance=auto_advance,
            state_path=state_path,
        )
        return cls(name="tiered", tiered_sizer=ts)

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

        if self.name == "tiered":
            if self.tiered_sizer is None:
                # Defensive: tiered mode requested but no sizer bound.
                # Fall back to fixed-dollar at $300 (Tier-1 baseline).
                risk_dollars = 300.0
                qty = int(risk_dollars // per_share)
                return max(qty, 0), risk_dollars
            qty, risk_dollars = self.tiered_sizer.size(
                equity=equity,
                entry_price=entry_price,
                stop_price=stop_price,
                recent_bar_volume=recent_bar_volume,
            )
            # Apply same bar-vol cap as fixed_dollar for parity
            if recent_bar_volume and self.max_bar_volume_pct > 0:
                cap = int(self.max_bar_volume_pct * recent_bar_volume)
                if cap > 0:
                    qty = min(qty, cap)
            return max(qty, 0), risk_dollars

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
    # Wave-4 Phase B1 filtered variants — reuse base signal logic; the
    # Wave-4 filter knobs are evaluated AFTER signal generation in
    # run_portfolio_backtest() via framework.filters.passes_pre_entry_filters.
    "orb_aligned_300plus_monskip.yaml": _opening_range_signal,
    "pdh_fade_filtered.yaml": lambda b, s, prior: _pdh_pdl_signal(b, s, prior, mode="fade"),
    "pdh_breakout_f4.yaml": lambda b, s, prior: _pdh_pdl_signal(b, s, prior, mode="breakout"),
}


# YAML names that need prior-day bars (PDH/PDL family).
_PDH_PDL_YAMLS = {
    "pdh_pdl_fade.yaml",
    "pdh_pdl_breakout.yaml",
    "pdh_fade_filtered.yaml",
    "pdh_breakout_f4.yaml",
}


def _yaml_needs_prior(yname: str) -> bool:
    return yname in _PDH_PDL_YAMLS


# ---------------------------------------------------------------------------
# Wave-4 Phase B1: filter dispatcher
# ---------------------------------------------------------------------------


def _vwap_at_bar(bars: list[Bar], idx: int) -> Optional[float]:
    """Cumulative session VWAP through bar idx (inclusive).

    Uses the typical-price (HLC/3) weighted volume convention shared with
    framework.level_sources.vwap. Returns None if cumulative volume is zero.
    """
    if idx < 0 or idx >= len(bars):
        return None
    cum_pv = 0.0
    cum_v = 0.0
    for j in range(idx + 1):
        b = bars[j]
        typical = (b.high + b.low + b.close) / 3.0
        cum_pv += typical * b.volume
        cum_v += b.volume
    if cum_v <= 0:
        return None
    return cum_pv / cum_v


def _or5_open_close(bars: list[Bar]) -> tuple[Optional[float], Optional[float]]:
    """Return (open, close) of the OR5 (09:30-09:34) bar window.

    The 5-min OR is the OHLC over the first 5 1-min bars of RTH. open is
    the first bar's open; close is the 5th bar's close.
    """
    if not bars:
        return None, None
    session_date = bars[0].timestamp.date()
    or_end_t = (datetime.combine(session_date, RTH_OPEN) + timedelta(minutes=5)).time()
    in_range = [b for b in bars if b.timestamp.time() < or_end_t]
    if not in_range:
        return None, None
    return in_range[0].open, in_range[-1].close


def _signal_passes_wave4_filters(
    *,
    arm: "StrategyArm",
    sig: EntrySignal,
    sym: str,
    bars: list[Bar],
    session_date: date,
) -> bool:
    """Apply the Wave-4 YAML filter knobs to a candidate signal.

    Returns True if the signal passes every configured filter; False otherwise.
    Delegates the per-filter predicates to framework.filters.
    """
    spec = arm.spec
    # Skip the cost if no filter knobs are configured on this YAML.
    if not any(
        k in spec
        for k in (
            "entry_time_window",
            "tier_filter",
            "opening_bar_alignment",
            "skip_mondays",
            "symbol_blacklist",
            "require_vwap_alignment",
            "pre_entry_consolidation_max_pct",
            "volume_min_multiple",
        )
    ):
        return True

    from framework.filters import passes_pre_entry_filters

    # Fill bar = signal.bar_idx + 1 (next bar's open is the entry price).
    if sig.bar_idx + 1 >= len(bars):
        return False
    fill_bar = bars[sig.bar_idx + 1]
    entry_ts = fill_bar.timestamp
    entry_price = fill_bar.open

    bars_before_entry = bars[: sig.bar_idx + 1]  # inclusive of confirm bar; excludes fill bar
    entry_bar_volume = float(fill_bar.volume)

    vwap_at_entry = _vwap_at_bar(bars, sig.bar_idx)
    or5_open, or5_close = (
        _or5_open_close(bars)
        if (spec.get("opening_bar_alignment") or {}).get("required", False)
        else (None, None)
    )

    ok, reason = passes_pre_entry_filters(
        spec=spec,
        entry_ts=entry_ts,
        entry_price=entry_price,
        direction=sig.direction,
        symbol=sym,
        session_date=session_date,
        vwap_at_entry=vwap_at_entry,
        bars_before_entry=bars_before_entry,
        entry_bar_volume=entry_bar_volume,
        or5_open=or5_open,
        or5_close=or5_close,
    )
    if not ok:
        log.debug(
            "[wave4-filter] %s %s %s %s rejected by %s",
            arm.name, sym, session_date, sig.direction, reason,
        )
    return ok


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
    abandon_rule: Optional[dict[str, Any]] = None,
    entry_ts: Optional[datetime] = None,
) -> tuple[float, datetime, str]:
    """Forward replay from entry_idx+1 onwards, return (exit_price, exit_ts, reason).

    If ``abandon_rule`` is provided, evaluates the Wave-4 abandon@N rule
    (PDH-Fade F1+abandon@10): at entry_ts + N minutes, if the trade is NOT
    in profit, exit at that bar's close (adverse slippage capped at
    ``exit_cap_dollars`` per share, per the forensic's $300 assumption).
    """
    abandon_check_ts: Optional[datetime] = None
    abandon_done = False
    if (
        abandon_rule
        and abandon_rule.get("enabled", True)
        and entry_ts is not None
    ):
        mins = int(abandon_rule.get("minutes_after_entry", 0))
        if mins > 0:
            abandon_check_ts = entry_ts + timedelta(minutes=mins)

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

        # Abandon@N rule.
        if (
            not abandon_done
            and abandon_check_ts is not None
            and b.timestamp >= abandon_check_ts
        ):
            abandon_done = True
            require_profit = bool(abandon_rule.get("exit_if_not_profit", True))
            in_profit = (
                b.close > entry_price
                if direction == "long"
                else b.close < entry_price
            )
            if require_profit and not in_profit:
                exit_px = b.close
                cap = abandon_rule.get("exit_cap_dollars")
                if cap is not None:
                    cap_f = float(cap)
                    if direction == "long":
                        exit_px = max(exit_px, entry_price - cap_f)
                    else:
                        exit_px = min(exit_px, entry_price + cap_f)
                return exit_px, b.timestamp, "abandon"
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
        if _yaml_needs_prior(Path(strategy_yaml).name) else [],
        sizing_mode=SizingMode(name="half_kelly"),
        equity=starting_equity,
    )


def _build_trade_from_signal(
    arm: StrategyArm,
    bars: list[Bar],
    signal: EntrySignal,
    sizing_mode: SizingMode,
    equity: float,
    secondary_fill: bool = False,
) -> Optional[dict[str, Any]]:
    """Materialize a Trade dict from a pre-computed EntrySignal.

    Returns None if the signal cannot be executed (no fill bar, bad stop,
    zero qty, etc.). Extracted from _execute_one so the conflict-rule
    machinery can reuse it for re-armed (secondary) signals.
    """
    # Fill at next bar's open (no look-ahead)
    if signal.bar_idx + 1 >= len(bars):
        return None
    fill_bar = bars[signal.bar_idx + 1]
    entry_price = fill_bar.open
    entry_ts = fill_bar.timestamp

    stop_price, target_price = _compute_stop_and_target(signal, bars, arm.spec)
    if stop_price is None:
        return None

    # Recent bar volume for the sizer cap
    recent_vol = float(bars[signal.bar_idx].volume) if bars else 0.0
    qty, risk_dollars = sizing_mode.size(
        equity=equity,
        entry_price=entry_price,
        stop_price=stop_price,
        recent_bar_volume=recent_vol,
    )
    if qty <= 0:
        return None

    exit_price, exit_ts, reason = _replay_to_exit(
        bars=bars,
        entry_idx=signal.bar_idx + 1,
        entry_price=entry_price,
        stop_price=stop_price,
        target_price=target_price,
        direction=signal.direction,
        abandon_rule=arm.spec.get("abandon_rule"),
        entry_ts=entry_ts,
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
        secondary_fill=secondary_fill,
    )
    return trade.to_dict()


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
    if _yaml_needs_prior(yname):
        signal = fn(bars, arm.spec, prior_bars)
    else:
        signal = fn(bars, arm.spec)
    if signal is None:
        return []

    trade = _build_trade_from_signal(
        arm=arm,
        bars=bars,
        signal=signal,
        sizing_mode=sizing_mode,
        equity=equity,
        secondary_fill=False,
    )
    if trade is None:
        return []
    return [trade]


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
    # Conflict resolution rule:
    #   'first_in_time'    — original Wave 3 behavior. The earliest-filling
    #                        strategy claims (symbol, day); all later candidate
    #                        signals are blocked and (optionally) logged.
    #   'release_on_stop'  — NEW DEFAULT (Wave 4). When the locked trade exits
    #                        via stop, the lock releases at exit_ts and any
    #                        queued candidates with fill_ts > exit_ts re-arm
    #                        in fill_ts order. First re-armed candidate wins
    #                        the lock again. Trades from re-armed signals are
    #                        tagged secondary_fill=True. Target / session_close
    #                        exits do NOT release the lock.
    # Per `cowork_reports/2026-05-18_pdh_breakout_forensic.md` §H8 the structural
    # gain from this rule is +$427K on the Wave 3 trade set.
    conflict_rule: str = "release_on_stop"
    # When set, every lock-blocked signal is written to this CSV
    # (columns: fill_ts, symbol, session_date, winning_strategy, blocked_strategy,
    #  blocked_direction, blocked_intended_entry_price). For release_on_stop,
    # only signals that are FINALLY blocked (no successful re-arm) are logged —
    # secondary fills are not collisions, they're recoveries.
    # Set to None to skip logging — see WB_PORTFOLIO_LOG_LOCK_COLLISIONS env var.
    lock_collisions_log_path: Optional[str] = None


def _build_session_returns_series(
    portfolio_events: list[tuple[datetime, float]],
    starting_equity: float,
) -> list[float]:
    """Compress portfolio_events into per-session returns.

    Each `portfolio_events` entry is (exit_ts, post-trade equity). For
    each unique session date we take the LAST equity mark of the day,
    then compute (end_eq / prior_eq - 1). The first session's prior is
    `starting_equity`. Days with no trades are omitted (no equity mark).

    Returns
    -------
    list[float]
        Per-session returns, oldest first. Empty list if no events.
    """
    if not portfolio_events:
        return []
    by_day: dict[date, float] = {}
    for ts, eq in portfolio_events:
        by_day[ts.date()] = eq  # last wins per day (events are ordered)
    days = sorted(by_day.keys())
    out: list[float] = []
    prev = starting_equity
    for d in days:
        end_eq = by_day[d]
        if prev > 0:
            out.append((end_eq / prev) - 1.0)
        prev = end_eq
    return out


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
    lock_collision_events: list[dict[str, Any]] = []

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
                if _yaml_needs_prior(yname):
                    sig = fn(bars, arm.spec, prior_by_sym.get(sym, []))
                else:
                    sig = fn(bars, arm.spec)
                if sig is None:
                    continue
                # entry fill at next bar
                if sig.bar_idx + 1 >= len(bars):
                    continue
                fill_ts = bars[sig.bar_idx + 1].timestamp
                # ---- Wave-4 Phase B1: apply YAML filter knobs at signal-generation time ----
                if not _signal_passes_wave4_filters(
                    arm=arm, sig=sig, sym=sym, bars=bars, session_date=d
                ):
                    continue
                candidates.append((fill_ts, arm, sym, sig))

        # Sort by fill time so first-in-time wins the per-day-per-symbol lock
        candidates.sort(key=lambda x: x[0])

        # Per-(symbol, day) lock state.
        #   lock_holder[key]     — name of strategy currently holding the lock
        #   lock_released_at[key] — exit_ts of the locked trade IF it exited via
        #                           'stop' (so the lock can release). Absent if
        #                           the trade is still notionally open, or if it
        #                           exited via target/session_close (lock stays
        #                           forever for that day).
        lock_holder: dict[tuple[str, date], str] = {}
        lock_released_at: dict[tuple[str, date], datetime] = {}

        def _record_trade(arm_name: str, trade: dict[str, Any]) -> None:
            """Persist a filled trade and update equity accounting."""
            nonlocal portfolio_equity
            trades_by_strategy[arm_name].append(trade)
            equity_per_strategy[arm_name] += trade["pnl"]
            portfolio_equity += trade["pnl"]
            portfolio_events.append(
                (pd.Timestamp(trade["exit_ts"]).to_pydatetime(), portfolio_equity)
            )

        for fill_ts, arm, sym, sig in candidates:
            key = (sym, d)
            if cfg.per_day_per_symbol_lock and key in lock_holder:
                # Determine whether the existing lock has been released by a
                # prior stop. Only release_on_stop ever sets lock_released_at.
                released_ts = lock_released_at.get(key)
                lock_active = (released_ts is None) or (fill_ts <= released_ts)
                if lock_active:
                    # FINAL block: this signal would have fired but the lock
                    # was held at its fill_ts. Count + log it.
                    lock_collisions += 1
                    if cfg.lock_collisions_log_path:
                        lock_collision_events.append({
                            "fill_ts": fill_ts,
                            "symbol": sym,
                            "session_date": d.isoformat(),
                            "winning_strategy": lock_holder[key],
                            "blocked_strategy": arm.name,
                            "blocked_direction": getattr(sig, "direction", ""),
                            "blocked_intended_entry_price": getattr(
                                sig, "entry_price", float("nan")
                            ),
                        })
                    continue
                # Lock has been released — this is a secondary fill candidate.
                # Try to materialize the trade. If the signal can't execute
                # (qty=0, bad stop, etc.) it doesn't claim the lock either.
                bars = bars_by_sym[sym]
                arm_equity = equity_per_strategy[arm.name]
                trade = _build_trade_from_signal(
                    arm=arm,
                    bars=bars,
                    signal=sig,
                    sizing_mode=cfg.sizing_mode,
                    equity=arm_equity,
                    secondary_fill=True,
                )
                if trade is None:
                    continue
                # Lock transfers to this strategy. Determine new release ts.
                lock_holder[key] = arm.name
                if cfg.conflict_rule == "release_on_stop" and trade["exit_reason"] == "stop":
                    lock_released_at[key] = pd.Timestamp(trade["exit_ts"]).to_pydatetime()
                else:
                    lock_released_at.pop(key, None)
                _record_trade(arm.name, trade)
                continue

            # No prior lock holder — first arrival on this (symbol, day).
            bars = bars_by_sym[sym]
            arm_equity = equity_per_strategy[arm.name]
            trade = _build_trade_from_signal(
                arm=arm,
                bars=bars,
                signal=sig,
                sizing_mode=cfg.sizing_mode,
                equity=arm_equity,
                secondary_fill=False,
            )
            if trade is None:
                continue
            lock_holder[key] = arm.name
            if cfg.conflict_rule == "release_on_stop" and trade["exit_reason"] == "stop":
                lock_released_at[key] = pd.Timestamp(trade["exit_ts"]).to_pydatetime()
            _record_trade(arm.name, trade)

        # Wave-4 Phase C1: per-session tiered-sizer transition hook.
        # Called once per session AFTER all trades for the day have settled.
        # The portfolio_returns list is the per-session return relative to
        # prior portfolio equity — used by the rolling-Sharpe gates.
        if cfg.sizing_mode.name == "tiered" and cfg.sizing_mode.tiered_sizer is not None:
            # Build a returns series from portfolio_events seen so far.
            # We use end-of-session marks: the last portfolio_equity for each
            # past session date. This is approximate but matches the rolling-
            # Sharpe-over-session-returns semantics in SIZING_SCHEDULE §3.
            session_returns = _build_session_returns_series(
                portfolio_events, cfg.starting_equity
            )
            cfg.sizing_mode.tiered_sizer.on_session_close(
                session_date=d,
                equity=portfolio_equity,
                portfolio_returns=session_returns,
            )

    # Write lock-collision log if requested (Wave-4 forensic-response §3.2)
    if cfg.lock_collisions_log_path and lock_collision_events:
        out_path = Path(cfg.lock_collisions_log_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(lock_collision_events).to_csv(out_path, index=False)
        log.info("[portfolio] wrote %d lock-collision events → %s",
                 len(lock_collision_events), out_path)

    # Build the equity curve dataframe — per strategy + portfolio
    return {
        "trades_by_strategy": trades_by_strategy,
        "equity_per_strategy": equity_per_strategy,
        "portfolio_events": portfolio_events,
        "lock_collisions": lock_collisions,
        "lock_collision_events": lock_collision_events,
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
    p.add_argument(
        "--mode",
        choices=["half_kelly", "fixed_dollar", "tiered"],
        default=os.environ.get("WB_SIZING_MODE", "half_kelly"),
    )
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

    if args.mode == "tiered":
        # Wave 4 Phase C1: env-var driven knobs
        initial_tier = int(os.environ.get("WB_TIER_INITIAL", "1"))
        tier_lock = os.environ.get("WB_TIER_LOCK", "0") == "1"
        auto_advance = os.environ.get("WB_TIER_AUTO_ADVANCE", "1") == "1"
        state_path_env = os.environ.get("WB_TIER_STATE_PATH")
        state_path = Path(state_path_env) if state_path_env else None
        sizing = SizingMode.tiered(
            initial_tier=initial_tier,
            tier_lock=tier_lock,
            auto_advance=auto_advance,
            state_path=state_path,
        )
        log.info(
            "[portfolio] tiered sizing: initial_tier=%d tier_lock=%s auto_advance=%s",
            initial_tier, tier_lock, auto_advance,
        )
    else:
        sizing = SizingMode(name=args.mode)
    out_dir = REPO / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    # WB_PORTFOLIO_LOG_LOCK_COLLISIONS=1 (default) writes lock_collisions.csv per run
    log_lock = os.environ.get("WB_PORTFOLIO_LOG_LOCK_COLLISIONS", "1") == "1"
    lock_log_path = str(out_dir / "lock_collisions.csv") if log_lock else None
    # WB_PORTFOLIO_CONFLICT_RULE — 'release_on_stop' (default, recovers $427K)
    #                              or 'first_in_time' (Wave 3 baseline behavior).
    conflict_rule = os.environ.get(
        "WB_PORTFOLIO_CONFLICT_RULE", "release_on_stop"
    ).strip().lower()
    if conflict_rule not in ("first_in_time", "release_on_stop"):
        log.warning("[portfolio] unknown WB_PORTFOLIO_CONFLICT_RULE=%r; "
                    "falling back to release_on_stop", conflict_rule)
        conflict_rule = "release_on_stop"
    cfg = PortfolioConfig(
        sizing_mode=sizing,
        strategy_yamls=tuple(yamls),
        start_date=pd.Timestamp(args.start).date(),
        end_date=pd.Timestamp(args.end).date(),
        lock_collisions_log_path=lock_log_path,
        conflict_rule=conflict_rule,
    )
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

    secondary_counts = {
        s: sum(1 for t in trades if t.get("secondary_fill"))
        for s, trades in result["trades_by_strategy"].items()
    }
    summary = {
        "mode": args.mode,
        "start": args.start,
        "end": args.end,
        "conflict_rule": conflict_rule,
        "sessions": len(result["sessions"]),
        "lock_collisions": result["lock_collisions"],
        "trade_counts": {s: len(t) for s, t in result["trades_by_strategy"].items()},
        "secondary_fill_counts": secondary_counts,
        "equity_per_strategy": result["equity_per_strategy"],
    }
    (out_dir / f"summary_{args.mode}.json").write_text(json.dumps(summary, indent=2))
    log.info("wrote summary: %s", summary)


if __name__ == "__main__":
    _cli()
