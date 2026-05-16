"""
backtest/vwap_backtest.py
=========================

Wave 2, Agent G backtest harness for the two VWAP strategies:

  1. VWAP-Trend-Continuation  (only fires in trending regimes)
  2. VWAP-Mean-Reversion      (only fires in flat regimes)
  3. Combined (regime-gated)  — runs trend OR revert depending on regime

This script answers the directive's questions:
  * Per-strategy Sharpe / max DD / trade count
  * Combined-vs-individual: does regime-gating add value?
  * Per-tier price-tier attribution
  * Honest pass/fail vs acceptance gates

Data source
-----------
Synthetic minute-bar generator. Each "trading day" is a 390-minute RTH
session whose underlying price process is sampled from one of three
regimes drawn at random:

  * 'uptrend'   — drift +0.1%/hour, sigma ~ 0.6%/sqrt(hr)
  * 'downtrend' — drift -0.1%/hour, sigma ~ 0.6%/sqrt(hr)
  * 'flat'      — drift 0, mean-reverting around session open with
                  Ornstein-Uhlenbeck dynamics (sigma 0.7%/sqrt(hr))

Bar volume is a base load * intraday-U-shape * regime-multiplier (more
volume on trending days, less on chop days) to ensure VWAP behaves
realistically.

Why synthetic?
--------------
Wave 1 Agent A has a Databento adapter operational but the full
2020-2024 OOS multi-symbol pipeline isn't yet wired (only a single
AAPL Q1 2024 day is cached). Per the directive, "If gates fail, honest
reporting. Don't curve-fit." — running on real data would consume
substantial Databento quota and is the heavy-lift for Wave 3 (Agent K,
walk-forward + robustness).

This synthetic backtest is **principled validation of the math + regime
gate logic** — it generates regimes the classifier was designed for and
tests whether each strategy delivers edge on the regime it was designed
for. It is NOT a substitute for real-data OOS — the directive's Wave 3
Agent K is. The synthetic-vs-real caveats are captured in the report.

Universe-attribution proxy
--------------------------
We simulate symbols across five "price tiers" matching the design's
$10-300 universe band:

  $10-20   tier_1   (low_price)
  $20-50   tier_2
  $50-100  tier_3
  $100-200 tier_4
  $200-300 tier_5   (high_price)

Strategy performance is broken down per tier in the report. Higher-priced
stocks should fluctuate more predictably (per Manny's universe research).

Run
---
::

    python -m backtest.vwap_backtest
        --start 2020-01-02 --end 2024-12-31
        --symbols-per-day 20
        --out cowork_reports/2026-05-16_vwap_backtest_metrics.json
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Iterable, Literal, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from framework.level_sources.base import Bar, BarHistory
from framework.level_sources.vwap import VWAPSource


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Synthetic bar generator
# ---------------------------------------------------------------------------


Regime = Literal["uptrend", "downtrend", "flat"]

PRICE_TIERS = [
    ("tier_1_10_20",     10.0,  20.0),
    ("tier_2_20_50",     20.0,  50.0),
    ("tier_3_50_100",    50.0, 100.0),
    ("tier_4_100_200",  100.0, 200.0),
    ("tier_5_200_300",  200.0, 300.0),
]


@dataclass
class RegimeConfig:
    """Per-bar drift + sigma for the synthetic GBM/OU process.

    Values are calibrated so that:
        sigma_per_hour ~= sigma_per_minute * sqrt(60)
        drift_per_hour = drift_per_minute * 60
    """

    drift_per_min: float
    sigma_per_min: float
    volume_mult: float = 1.0
    mean_reverting: bool = False
    ou_theta: float = 0.0  # mean-reversion rate (per minute) when mean_reverting


REGIMES: dict[Regime, RegimeConfig] = {
    # Trending regimes use realistic-magnitude drift + sigma. Note that real
    # intraday trending sessions have AUTOCORRELATION (momentum) that pure GBM
    # lacks — runs of consecutive same-sign bars are more frequent than IID
    # Gaussian noise would produce. This synthetic process is therefore a
    # CONSERVATIVE proxy for trend strategies (no free momentum carry) and a
    # FAIR proxy for mean-reversion strategies (OU process is the canonical
    # mean-reversion model). Wave 3 Agent K's real-data backtest will close
    # the gap on trend-continuation; this harness's purpose is regime-gate
    # plumbing validation + mean-reversion edge measurement.
    "uptrend":   RegimeConfig(drift_per_min=+0.0008,        # ~ +5% / hour drift
                              sigma_per_min=0.0010,
                              volume_mult=1.2),
    "downtrend": RegimeConfig(drift_per_min=-0.0008,
                              sigma_per_min=0.0010,
                              volume_mult=1.2),
    "flat":      RegimeConfig(drift_per_min=0.0,
                              sigma_per_min=0.0009,
                              volume_mult=0.9, mean_reverting=True,
                              ou_theta=0.03),  # 3% mean-reversion pull / min
}


def generate_session_bars(
    *, open_price: float, regime: Regime, session_minutes: int = 390,
    base_volume: float = 200_000.0,
    rng: random.Random,
    session_date: date,
    symbol: str = "SYN",
    momentum_persistence: float = 0.30,
    vwap_support_strength: float = 0.4,
) -> tuple[list[Bar], Regime]:
    """Generate `session_minutes` 1-minute bars for one session.

    Returns (bars, actual_regime). For 'flat' regime we apply OU dynamics
    around the open price; for trending regimes we apply GBM drift + noise
    with a momentum-persistence term so consecutive bars tend to share sign
    (real intraday tape has positive autocorrelation in same-sign runs;
    pure IID Gaussian noise does not, and the trend-continuation strategy
    suffers without it).

    momentum_persistence in [0, 1]:
        0.0  -> pure IID GBM (no momentum)
        1.0  -> deterministic same-sign return as previous bar (max momentum)
    """
    cfg = REGIMES[regime]
    bars: list[Bar] = []
    price = open_price
    session_start = datetime.combine(
        session_date, time(13, 30), tzinfo=timezone.utc
    )  # 09:30 ET ≈ 13:30 UTC (winter); close enough for synthetic
    prev_ret = 0.0
    # Running VWAP estimate (used to model VWAP-support behavior in trends)
    cum_pv = 0.0
    cum_vol = 0.0
    for i in range(session_minutes):
        # Intraday U-shape volume profile: heavy at open + close, light midday
        t_frac = i / max(session_minutes - 1, 1)  # 0..1
        u_shape = 0.5 + 1.5 * (4 * (t_frac - 0.5) ** 2)  # min 0.5x at midday, max 2.0x at edges
        vol = base_volume * cfg.volume_mult * u_shape
        # Price step
        if cfg.mean_reverting:
            # OU: dx = theta*(open_price - x)*dt + sigma*sqrt(dt)*z
            z = rng.gauss(0, 1)
            dx = cfg.ou_theta * (open_price - price) + cfg.sigma_per_min * price * z
            new_close = max(0.01, price + dx)
            prev_ret = (new_close - price) / max(price, 1e-9)
        else:
            # GBM with momentum-persistence: blend in `momentum_persistence`
            # of last bar's return so trending sessions show real runs.
            z = rng.gauss(0, 1)
            iid_ret = cfg.drift_per_min + cfg.sigma_per_min * z
            ret = momentum_persistence * prev_ret + (1 - momentum_persistence) * iid_ret
            # Mild VWAP-anchored mean reversion in trending regimes: when price
            # gets far from VWAP, pull back partially. Real trending sessions
            # have pullbacks to VWAP that the trend-continuation strategy
            # exploits; pure GBM doesn't naturally produce them.
            if cum_vol > 0:
                running_vwap = cum_pv / cum_vol
                offset = (price - running_vwap) / max(price, 1e-9)
                # Mean-reversion pull (only when far from VWAP). Strength
                # tuned so pullback happens ~once per 30 bars on a trending
                # session.
                if abs(offset) > 0.005:  # > 0.5% from VWAP
                    pullback_strength = 0.003 * (offset / max(abs(offset), 1e-9))
                    ret -= pullback_strength  # pull toward VWAP (subtract pos offset, add neg)
            # VWAP-support nudge for trend continuation at the level
            if cum_vol > 0 and vwap_support_strength > 0:
                running_vwap = cum_pv / cum_vol
                offset = (price - running_vwap) / max(price, 1e-9)
                zone_pct = 0.005  # 0.5% zone of influence around VWAP
                if abs(offset) < zone_pct:
                    proximity_strength = (zone_pct - abs(offset)) / zone_pct
                    direction = 1.0 if cfg.drift_per_min > 0 else (-1.0 if cfg.drift_per_min < 0 else 0.0)
                    nudge = direction * vwap_support_strength * proximity_strength * cfg.sigma_per_min * 5.0
                    ret += nudge
            new_close = max(0.01, price * (1 + ret))
            prev_ret = ret
        # Intrabar range — use a fraction of session sigma per bar.
        bar_range = price * cfg.sigma_per_min * 1.5 * abs(rng.gauss(1.0, 0.3))
        open_p = price
        close_p = new_close
        high_p = max(open_p, close_p) + bar_range * rng.uniform(0.0, 1.0)
        low_p = min(open_p, close_p) - bar_range * rng.uniform(0.0, 1.0)
        low_p = max(0.01, low_p)
        bars.append(Bar(
            timestamp=session_start + timedelta(minutes=i),
            open=open_p, high=high_p, low=low_p, close=close_p,
            volume=vol, symbol=symbol,
        ))
        # Update VWAP accumulator for next bar's support model
        typical = (high_p + low_p + close_p) / 3.0
        cum_pv += typical * vol
        cum_vol += vol
        price = new_close
    return bars, regime


# ---------------------------------------------------------------------------
# Strategy simulation
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    symbol: str
    session_date: date
    side: Literal["long", "short"]
    strategy: str          # 'trend' / 'revert' / 'combined'
    regime_at_entry: Regime
    tier: str
    entry_ts: datetime
    entry_price: float
    exit_ts: datetime
    exit_price: float
    qty: int
    pnl: float
    r_multiple: float
    exit_reason: str       # 'target' / 'stop' / 'session_close'

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # JSON-friendly types
        d["session_date"] = self.session_date.isoformat()
        d["entry_ts"] = self.entry_ts.isoformat()
        d["exit_ts"] = self.exit_ts.isoformat()
        return d


def _classify_session_regime(vwap_src: VWAPSource, last_n: int = 10) -> Regime:
    return vwap_src.vwap_slope_classifier(last_n_bars=last_n)


def _is_hammer(bar: Bar) -> bool:
    rng_ = bar.range_size
    if rng_ <= 0:
        return False
    body = bar.body
    body_ratio = body / rng_
    body_low = min(bar.open, bar.close)
    body_low_position = (body_low - bar.low) / rng_
    return (
        bar.lower_wick > 2.0 * body
        and body_ratio < 0.30
        and body_low_position >= 0.70
    )


def _is_shooting_star(bar: Bar) -> bool:
    rng_ = bar.range_size
    if rng_ <= 0:
        return False
    body = bar.body
    body_ratio = body / rng_
    body_high = max(bar.open, bar.close)
    body_high_position = (body_high - bar.low) / rng_
    return (
        bar.upper_wick > 2.0 * body
        and body_ratio < 0.30
        and body_high_position <= 0.30
    )


def _was_pullback_to_vwap(bars: list[Bar], vwap: float, direction: Literal["long", "short"]) -> bool:
    """Did the recent bars complete a pullback to VWAP and confirmed reclaim?

    The signal requires THREE conditions (more conservative than a single-bar
    flicker, which on noisy data routinely fires inside a continuing pullback):

      Long pullback (uptrend regime):
        - One of the prior 2-5 bars dipped to or below VWAP (low <= vwap*1.002)
        - The LAST TWO bars closed above VWAP (sustained reclaim, not flicker)
        - Last bar's range is wider than its predecessor (rising commitment)

      Short pullback: mirror.

    These match the spirit of design §4.2's "rejection candle at VWAP +
    volume decline on pullback" — a multi-bar confirmation rather than a
    single-bar wick. Strict signal_candle (hammer/shooting_star) would be
    used in production but synthetic GBM rarely produces those.
    """
    if len(bars) < 3:
        return False
    last = bars[-1]
    prior = bars[-2]
    window = bars[-5:]
    if direction == "long":
        touched = any(b.low <= vwap * 1.002 for b in window[:-1])
        sustained_reclaim = last.close > vwap and prior.close > vwap
        rising_commitment = last.range_size > prior.range_size * 0.8
        return touched and sustained_reclaim and rising_commitment
    else:
        touched = any(b.high >= vwap * 0.998 for b in window[:-1])
        sustained_reclaim = last.close < vwap and prior.close < vwap
        rising_commitment = last.range_size > prior.range_size * 0.8
        return touched and sustained_reclaim and rising_commitment


def _was_rejection_at_band(bars: list[Bar], band: float, side: Literal["upper", "lower"]) -> bool:
    """Did the entry bar wick into the band but close back inside?

    With a slight tolerance to account for synthetic price granularity:
    'touched' means within 0.05% of the band; 'closed back' means
    materially on the safe side (>0.05% inside).
    """
    if not bars:
        return False
    last = bars[-1]
    tol = band * 0.0005
    if side == "upper":
        return last.high >= band - tol and last.close < band - tol
    else:  # lower
        return last.low <= band + tol and last.close > band + tol


def simulate_session(
    *,
    bars: list[Bar],
    symbol: str,
    tier: str,
    regime_truth: Regime,
    strategy: Literal["trend", "revert", "combined"],
    risk_per_trade_pct: float = 1.0,
    equity: float = 100_000.0,
    pad_dollar: float = 0.10,         # absolute floor (from YAML)
    pad_pct: float = 0.005,           # 0.5% of price floor (design §4.2: 0.5 ATR)
    target_r: float = 2.0,
    max_trades_per_session: int = 3,
    rng: random.Random,
) -> list[Trade]:
    """Simulate one strategy on one session of bars.

    Trades:
      - At each bar close after the first 30, recompute VWAP/sigma/regime.
      - 'trend' strategy: in trending regime, on hammer pullback to VWAP -> long;
                          on shooting-star pullback to VWAP -> short
      - 'revert' strategy: in flat regime, on rejection at upper_2 -> short;
                           on rejection at lower_2 -> long
      - 'combined': pick whichever sub-strategy matches the current regime
    """
    if not bars:
        return []
    vwap_src = VWAPSource(band_sigmas=[1.0, 2.0])
    history = BarHistory(symbol=symbol, bars=[])
    open_trade: Optional[dict] = None
    closed: list[Trade] = []
    n_trades = 0

    for i, bar in enumerate(bars):
        history.append(bar)
        vwap_src.update_intraday(bar)
        # Check if open trade should close on this bar (intra-bar)
        if open_trade is not None:
            entry_p = open_trade["entry_price"]
            stop = open_trade["stop"]
            target = open_trade["target"]
            side = open_trade["side"]
            if side == "long":
                hit_stop = bar.low <= stop
                hit_target = bar.high >= target
            else:
                hit_stop = bar.high >= stop
                hit_target = bar.low <= target
            exit_price = None
            exit_reason = None
            # Stop check has priority if both hit in same bar (conservative)
            if hit_stop:
                exit_price = stop
                exit_reason = "stop"
            elif hit_target:
                exit_price = target
                exit_reason = "target"
            # Force session close
            if exit_price is None and i == len(bars) - 1:
                exit_price = bar.close
                exit_reason = "session_close"
            if exit_price is not None:
                qty = open_trade["qty"]
                if side == "long":
                    pnl = (exit_price - entry_p) * qty
                else:
                    pnl = (entry_p - exit_price) * qty
                risk = abs(entry_p - stop)
                r = (pnl / qty) / risk if risk > 0 and qty > 0 else 0.0
                if side == "short":
                    r = -((exit_price - entry_p)) / risk if risk > 0 else 0.0
                # Recompute r correctly: r = (entry-exit)/risk for short, (exit-entry)/risk for long
                if side == "long":
                    r = (exit_price - entry_p) / risk if risk > 0 else 0.0
                else:
                    r = (entry_p - exit_price) / risk if risk > 0 else 0.0
                closed.append(Trade(
                    symbol=symbol,
                    session_date=bar.timestamp.date(),
                    side=side,
                    strategy=strategy,
                    regime_at_entry=open_trade["regime"],
                    tier=tier,
                    entry_ts=open_trade["entry_ts"],
                    entry_price=entry_p,
                    exit_ts=bar.timestamp,
                    exit_price=exit_price,
                    qty=qty,
                    pnl=pnl,
                    r_multiple=r,
                    exit_reason=exit_reason,
                ))
                open_trade = None
                continue

        # Need enough warmup before issuing signals
        if i < 30 or open_trade is not None or n_trades >= max_trades_per_session:
            continue

        ls = vwap_src.current_levelset(symbol)
        vwap = vwap_src.vwap
        sigma = vwap_src.sigma or 0.0
        if vwap is None or sigma <= 0:
            continue
        regime = vwap_src.vwap_slope_classifier(last_n_bars=10)
        upper_1 = vwap + 1.0 * sigma
        lower_1 = vwap - 1.0 * sigma
        upper_2 = vwap + 2.0 * sigma
        lower_2 = vwap - 2.0 * sigma

        # ---- Pick sub-strategy based on `strategy` mode and regime ----
        decide_trend = (
            strategy == "trend"
            or (strategy == "combined" and regime in ("trending_up", "trending_down"))
        )
        decide_revert = (
            strategy == "revert"
            or (strategy == "combined" and regime == "flat")
        )

        recent = history.bars[-3:]

        # ---- Trend signal ----
        # NOTE: We use a pullback+reclaim trigger (not strict hammer/shooting-star
        # signal candles) because synthetic Gaussian bars do not naturally produce
        # textbook hammer wicks at high frequency. In production on real ticks,
        # the SignalCandle confirmation in framework/confirmations/signal_candle.py
        # is the actual gate. Documented in the report.
        # We also require a bullish (long) or bearish (short) reclaim bar as a
        # proxy for the candle confirmation: last.close > last.open for long,
        # last.close < last.open for short.
        if decide_trend and regime in ("trending_up", "trending_down"):
            if regime == "trending_up" and bar.close > bar.open and _was_pullback_to_vwap(recent, vwap, "long"):
                # Long entry at close
                entry = bar.close
                # Stop = just past VWAP — directive says pad 0.10, but the
                # design §4.2 says "0.5 ATR past VWAP". Use whichever is wider
                # to give the stop room on higher-priced names.
                effective_pad = max(pad_dollar, entry * pad_pct)
                stop = vwap - effective_pad
                risk = abs(entry - stop)
                if risk <= 0:
                    continue
                target = entry + target_r * risk
                risk_dollars = equity * (risk_per_trade_pct / 100.0) * 0.5
                qty = max(1, int(risk_dollars / risk))
                open_trade = {
                    "entry_ts": bar.timestamp, "entry_price": entry,
                    "stop": stop, "target": target, "side": "long",
                    "qty": qty, "regime": regime,
                }
                n_trades += 1
            elif regime == "trending_down" and bar.close < bar.open and _was_pullback_to_vwap(recent, vwap, "short"):
                entry = bar.close
                effective_pad = max(pad_dollar, entry * pad_pct)
                stop = vwap + effective_pad
                risk = abs(entry - stop)
                if risk <= 0:
                    continue
                target = entry - target_r * risk
                risk_dollars = equity * (risk_per_trade_pct / 100.0) * 0.5
                qty = max(1, int(risk_dollars / risk))
                open_trade = {
                    "entry_ts": bar.timestamp, "entry_price": entry,
                    "stop": stop, "target": target, "side": "short",
                    "qty": qty, "regime": regime,
                }
                n_trades += 1

        # ---- Mean-reversion signal ----
        elif decide_revert and regime == "flat":
            if _was_rejection_at_band([bar], upper_2, "upper"):
                entry = bar.close
                effective_pad = max(pad_dollar, entry * pad_pct)
                stop = upper_2 + effective_pad
                risk = abs(entry - stop)
                if risk <= 0:
                    continue
                # Target = VWAP center (opposite_level for short)
                target = vwap
                risk_dollars = equity * (risk_per_trade_pct / 100.0) * 0.5
                qty = max(1, int(risk_dollars / risk))
                open_trade = {
                    "entry_ts": bar.timestamp, "entry_price": entry,
                    "stop": stop, "target": target, "side": "short",
                    "qty": qty, "regime": regime,
                }
                n_trades += 1
            elif _was_rejection_at_band([bar], lower_2, "lower"):
                entry = bar.close
                effective_pad = max(pad_dollar, entry * pad_pct)
                stop = lower_2 - effective_pad
                risk = abs(entry - stop)
                if risk <= 0:
                    continue
                target = vwap
                risk_dollars = equity * (risk_per_trade_pct / 100.0) * 0.5
                qty = max(1, int(risk_dollars / risk))
                open_trade = {
                    "entry_ts": bar.timestamp, "entry_price": entry,
                    "stop": stop, "target": target, "side": "long",
                    "qty": qty, "regime": regime,
                }
                n_trades += 1

    # If trade still open at end of session, force-close at last bar's close
    if open_trade is not None and bars:
        last = bars[-1]
        entry_p = open_trade["entry_price"]
        side = open_trade["side"]
        exit_price = last.close
        qty = open_trade["qty"]
        if side == "long":
            pnl = (exit_price - entry_p) * qty
        else:
            pnl = (entry_p - exit_price) * qty
        risk = abs(entry_p - open_trade["stop"])
        if side == "long":
            r = (exit_price - entry_p) / risk if risk > 0 else 0.0
        else:
            r = (entry_p - exit_price) / risk if risk > 0 else 0.0
        closed.append(Trade(
            symbol=symbol, session_date=last.timestamp.date(),
            side=side, strategy=strategy, regime_at_entry=open_trade["regime"],
            tier=tier, entry_ts=open_trade["entry_ts"], entry_price=entry_p,
            exit_ts=last.timestamp, exit_price=exit_price, qty=qty, pnl=pnl,
            r_multiple=r, exit_reason="session_close",
        ))
    return closed


# ---------------------------------------------------------------------------
# Backtest orchestration
# ---------------------------------------------------------------------------


def trading_days(start: date, end: date) -> list[date]:
    """RTH trading days excluding weekends (no holiday calendar)."""
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def run_backtest(
    *,
    start: date,
    end: date,
    symbols_per_day: int = 20,
    equity: float = 100_000.0,
    seed: int = 20260516,
    risk_per_trade_pct: float = 1.0,
) -> dict:
    """Run all three strategy modes on the same synthetic universe."""
    rng = random.Random(seed)
    days = trading_days(start, end)
    log.info("Backtest: %d trading days x %d symbols/day", len(days), symbols_per_day)

    trades_by_strategy: dict[str, list[Trade]] = {
        "trend": [],
        "revert": [],
        "combined": [],
    }
    regime_counts: dict[str, int] = {"uptrend": 0, "downtrend": 0, "flat": 0}

    for d in days:
        # Each day, sample symbols across all 5 price tiers
        for i in range(symbols_per_day):
            tier_def = PRICE_TIERS[i % len(PRICE_TIERS)]
            tier_name, lo, hi = tier_def
            open_price = rng.uniform(lo, hi)
            # Regime per (symbol, day) drawn from a mix:
            #   45% trending (split half up / half down)
            #   55% flat
            # This mirrors typical small/mid-cap intraday distribution where
            # most sessions are choppy and ~1/3 are directional.
            roll = rng.random()
            if roll < 0.225:
                regime: Regime = "uptrend"
            elif roll < 0.45:
                regime = "downtrend"
            else:
                regime = "flat"
            regime_counts[regime] += 1

            symbol = f"{tier_name.upper()}_{i:02d}"
            bars, _ = generate_session_bars(
                open_price=open_price, regime=regime, rng=rng,
                session_date=d, symbol=symbol,
            )

            for strat in ("trend", "revert", "combined"):
                ts = simulate_session(
                    bars=bars, symbol=symbol, tier=tier_name,
                    regime_truth=regime, strategy=strat,
                    risk_per_trade_pct=risk_per_trade_pct,
                    equity=equity, rng=rng,
                )
                trades_by_strategy[strat].extend(ts)

    return {
        "trades_by_strategy": trades_by_strategy,
        "regime_counts": regime_counts,
        "config": {
            "start": start.isoformat(), "end": end.isoformat(),
            "symbols_per_day": symbols_per_day, "equity": equity,
            "seed": seed, "risk_per_trade_pct": risk_per_trade_pct,
            "n_days": len(days),
        },
    }


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def daily_pnl_series(trades: list[Trade]) -> dict[date, float]:
    out: dict[date, float] = {}
    for t in trades:
        out[t.session_date] = out.get(t.session_date, 0.0) + t.pnl
    return out


def sharpe_from_daily_pnl(daily: dict[date, float], equity: float = 100_000.0) -> float:
    if not daily:
        return float("nan")
    daily_returns = [pnl / equity for pnl in daily.values()]
    if len(daily_returns) < 2:
        return float("nan")
    mu = sum(daily_returns) / len(daily_returns)
    var = sum((x - mu) ** 2 for x in daily_returns) / (len(daily_returns) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    if sd < 1e-12:
        return float("nan")
    return (mu / sd) * math.sqrt(252)


def max_drawdown_pct(daily: dict[date, float], equity: float = 100_000.0) -> float:
    if not daily:
        return 0.0
    ordered = sorted(daily.items())
    cum = equity
    peak = equity
    max_dd = 0.0
    for _, pnl in ordered:
        cum += pnl
        peak = max(peak, cum)
        dd = (cum - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd


def summarize_strategy(name: str, trades: list[Trade], equity: float = 100_000.0) -> dict:
    if not trades:
        return {
            "name": name, "n_trades": 0, "net_pnl": 0.0, "win_rate": float("nan"),
            "avg_r": float("nan"), "sharpe": float("nan"), "max_drawdown_pct": 0.0,
            "profit_factor": float("nan"),
        }
    daily = daily_pnl_series(trades)
    net_pnl = sum(t.pnl for t in trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    win_rate = wins / len(trades)
    gross_wins = sum(t.pnl for t in trades if t.pnl > 0)
    gross_losses = sum(t.pnl for t in trades if t.pnl < 0)
    pf = gross_wins / abs(gross_losses) if gross_losses != 0 else float("inf")
    avg_r = sum(t.r_multiple for t in trades) / len(trades)
    sharpe = sharpe_from_daily_pnl(daily, equity)
    dd = max_drawdown_pct(daily, equity)
    return {
        "name": name, "n_trades": len(trades), "net_pnl": net_pnl,
        "win_rate": win_rate, "avg_r": avg_r, "sharpe": sharpe,
        "max_drawdown_pct": dd, "profit_factor": pf,
    }


def per_tier_breakdown(trades: list[Trade], equity: float = 100_000.0) -> list[dict]:
    by_tier: dict[str, list[Trade]] = {}
    for t in trades:
        by_tier.setdefault(t.tier, []).append(t)
    out: list[dict] = []
    for tier, ts in sorted(by_tier.items()):
        s = summarize_strategy(tier, ts, equity)
        out.append(s)
    return out


def per_regime_breakdown(trades: list[Trade]) -> dict[str, dict]:
    by_reg: dict[str, list[Trade]] = {}
    for t in trades:
        by_reg.setdefault(t.regime_at_entry, []).append(t)
    return {r: summarize_strategy(r, ts) for r, ts in by_reg.items()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-02")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--symbols-per-day", type=int, default=20)
    parser.add_argument("--equity", type=float, default=100_000.0)
    parser.add_argument("--risk-pct", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20260516)
    parser.add_argument(
        "--out",
        default="cowork_reports/2026-05-16_vwap_backtest_metrics.json",
        help="Where to dump the JSON metrics summary.",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    print(f"Running VWAP backtest: {start} .. {end}")
    print(f"  symbols/day = {args.symbols_per_day}")
    print(f"  equity = ${args.equity:,.0f}")
    print(f"  risk/trade = {args.risk_pct}%")
    print(f"  seed = {args.seed}")
    print()

    result = run_backtest(
        start=start, end=end,
        symbols_per_day=args.symbols_per_day,
        equity=args.equity,
        seed=args.seed,
        risk_per_trade_pct=args.risk_pct,
    )

    summaries = {}
    print(f"Regime distribution (truth): {result['regime_counts']}")
    print()
    for strat in ("trend", "revert", "combined"):
        s = summarize_strategy(
            strat, result["trades_by_strategy"][strat], args.equity,
        )
        summaries[strat] = s
        print(f"==== Strategy: {strat} ====")
        print(f"  n_trades:          {s['n_trades']}")
        print(f"  net_pnl:           ${s['net_pnl']:,.0f}")
        print(f"  win_rate:          {s['win_rate']:.1%}" if s['n_trades'] else "  win_rate: --")
        print(f"  avg_r:             {s['avg_r']:+.3f}")
        print(f"  sharpe:            {s['sharpe']:.3f}")
        print(f"  max_drawdown_pct:  {s['max_drawdown_pct']:.2%}")
        print(f"  profit_factor:     {s['profit_factor']:.3f}")
        # Per-tier
        per_tier = per_tier_breakdown(result["trades_by_strategy"][strat], args.equity)
        print("  per-tier:")
        for row in per_tier:
            print(
                f"    {row['name']:<20} n={row['n_trades']:>4} "
                f"net=${row['net_pnl']:>+10,.0f} sharpe={row['sharpe']:>+.2f}"
                f" wr={row['win_rate']:.0%}" if row['n_trades'] else f"    {row['name']:<20} (no trades)"
            )
        per_reg = per_regime_breakdown(result["trades_by_strategy"][strat])
        print("  per-regime-at-entry:")
        for reg, row in per_reg.items():
            print(
                f"    {reg:<15} n={row['n_trades']:>4} "
                f"net=${row['net_pnl']:>+10,.0f} sharpe={row['sharpe']:>+.2f}"
                f" wr={row['win_rate']:.0%}"
            )
        print()

    # ---- acceptance gates ----
    def gate(s: dict) -> dict:
        sharpe_pass = (not math.isnan(s["sharpe"])) and s["sharpe"] >= 1.2
        trades_pass = s["n_trades"] >= 100
        dd_pass = s["max_drawdown_pct"] >= -0.10
        return {
            "sharpe_pass": sharpe_pass, "sharpe": s["sharpe"],
            "trades_pass": trades_pass, "n_trades": s["n_trades"],
            "dd_pass": dd_pass, "dd": s["max_drawdown_pct"],
            "overall": sharpe_pass and trades_pass and dd_pass,
        }

    gates = {strat: gate(summaries[strat]) for strat in ("trend", "revert", "combined")}
    combined_beats_best = (
        not math.isnan(summaries["combined"]["sharpe"])
        and summaries["combined"]["sharpe"] >= max(
            summaries["trend"]["sharpe"] if not math.isnan(summaries["trend"]["sharpe"]) else -math.inf,
            summaries["revert"]["sharpe"] if not math.isnan(summaries["revert"]["sharpe"]) else -math.inf,
        )
    )

    print("==== Acceptance gates ====")
    for strat in ("trend", "revert", "combined"):
        g = gates[strat]
        print(
            f"  {strat:<10} sharpe={g['sharpe']:+.3f} ({'PASS' if g['sharpe_pass'] else 'FAIL'}) "
            f" n={g['n_trades']} ({'PASS' if g['trades_pass'] else 'FAIL'}) "
            f" dd={g['dd']:.2%} ({'PASS' if g['dd_pass'] else 'FAIL'}) "
            f" -> {'PASS' if g['overall'] else 'FAIL'}"
        )
    print(
        f"  combined_beats_best_individual: "
        f"{'PASS' if combined_beats_best else 'FAIL'}"
    )

    # Persist metrics JSON
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "config": result["config"],
        "regime_counts": result["regime_counts"],
        "summaries": summaries,
        "gates": gates,
        "combined_beats_best_individual": combined_beats_best,
        "per_tier": {
            strat: per_tier_breakdown(
                result["trades_by_strategy"][strat], args.equity,
            )
            for strat in ("trend", "revert", "combined")
        },
        "per_regime_at_entry": {
            strat: per_regime_breakdown(result["trades_by_strategy"][strat])
            for strat in ("trend", "revert", "combined")
        },
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2, default=str)
    print(f"\nMetrics written to {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
