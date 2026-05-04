"""wave_census.py — Wave research driver, variant-aware.

Stage 1 (DIRECTIVE_WAVE_SCALP_STAGE1_RESEARCH.md): emits census + waves +
hypothetical trades for the baseline rule set.
Stage 2 (DIRECTIVE_WAVE_BREAKOUT_STAGE2.md): same pipeline, but exit/sizing
rules are now driven by a `VariantConfig` so all 8 variants reuse the
detection + scoring code.

Mandatory V0 hardening (applies to ALL variants):
  - MIN_RISK_PER_SHARE = max($0.01, entry × 0.1%)  — eliminates FIGG-style
    degenerate positions when stop ≈ entry due to float precision.
  - MAX_NOTIONAL = $50,000  — caps absolute capital per trade (matches the
    main bot's WB_MAX_NOTIONAL). Pyramid (V5) caps the COMBINED position.

Outputs (variant-specific) into `wave_research/<prefix>/`:
  - <prefix>_wave_census.csv       — per (symbol, date) summary
  - <prefix>_waves_detail.csv      — every detected wave + score
  - <prefix>_hypothetical_trades.csv — every simulated trade

This is RESEARCH only. No live strategy / order code is invoked.
`bot_v3_hybrid.py` is never modified or imported.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterator, List, Optional, Tuple

import pytz

# Add repo root to path so we can import the bot's modules.
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from bars import TradeBarBuilder, Bar  # noqa: E402
from macd import MACDState  # noqa: E402
from wave_detector import WaveDetector  # noqa: E402

ET = pytz.timezone("US/Eastern")
TICK_CACHE = os.path.join(REPO, "tick_cache")
OUT_DIR = os.path.join(REPO, "wave_research")
os.makedirs(OUT_DIR, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────
# Tick file loading
# ─────────────────────────────────────────────────────────────────────

def load_ticks(path: str) -> Iterator[Tuple[float, int, datetime]]:
    """Yield (price, size, ts_utc) tuples from a gzipped tick log."""
    try:
        with gzip.open(path, "rt") as f:
            data = json.load(f)
    except Exception as e:
        print(f"  ⚠️  failed to read {path}: {e}", flush=True)
        return
    for t in data:
        try:
            price = float(t["p"])
            size = int(t["s"])
            ts = datetime.fromisoformat(t["t"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (KeyError, ValueError, TypeError):
            continue
        if price <= 0 or size <= 0:
            continue
        yield price, size, ts


# ─────────────────────────────────────────────────────────────────────
# Wave scoring per the directive's 7 criteria
# ─────────────────────────────────────────────────────────────────────

@dataclass
class WaveScore:
    """Detailed score breakdown for downstream analysis."""
    total: int
    has_prior_waves: bool       # +1
    near_recent_low: bool       # +2
    macd_rising: bool           # +2
    higher_low: bool            # +2
    volume_confirm: bool        # +1
    green_bounce: bool          # +1
    minimal_upper_wick: bool    # +1


def score_wave_setup(
    *,
    just_emitted_wave: dict,
    prior_waves: List[dict],
    bounce_bar: dict,
    avg_5_bar_volume: float,
    macd_state: MACDState,
) -> WaveScore:
    """Score a freshly-emitted DOWN wave as a long-entry setup.

    The bounce_bar is the bar that *confirmed* the down-wave reversal —
    it's the candidate entry bar (next bar's open will be entry price in
    the simulator).

    Per directive Deliverable 3:
      1. (+1) Prior waves observed (≥ 2)
      2. (+2) Bounce bar low is within 1% of the recent wave low cluster
      3. (+2) MACD histogram rising (positive and increasing)
      4. (+2) Higher low forming (current low > previous down-wave's low)
      5. (+1) Volume confirmation (bounce bar > avg of last 5 bars)
      6. (+1) Bounce candle is green (close > open)
      7. (+1) Minimal upper wick (upper_wick / body < 0.5)

    Total range: 0–10.
    """
    score = 0

    # (1) prior waves ≥ 2
    has_prior = len(prior_waves) >= 2
    if has_prior:
        score += 1

    # Reference points from the most recent down-waves (those whose end is
    # a low) for criteria 2 & 4.
    recent_down_endings = [
        w["end_price"] for w in prior_waves[-3:] if w["direction"] == "down"
    ]
    prev_down_endings = [
        w["end_price"] for w in prior_waves[-2:] if w["direction"] == "down"
    ]

    # (2) bounce bar low within 1% of the *cluster* of recent down-wave lows
    near_recent_low = False
    if recent_down_endings:
        recent_low = min(recent_down_endings)
        if recent_low > 0 and abs(bounce_bar["low"] - recent_low) / recent_low <= 0.01:
            near_recent_low = True
            score += 2

    # (3) MACD histogram rising — hist is positive (or non-negative) AND
    #     hist is greater than prev_hist by some small amount (rising).
    macd_rising = False
    if (macd_state.hist is not None and macd_state.prev_hist is not None
            and macd_state.hist > macd_state.prev_hist):
        # Loosely "positive and rising" — directive language is "histogram
        # positive and increasing for 2 bars". We approximate with: hist
        # not negative AND rising vs prev. Strict "positive" can disqualify
        # bottoms where hist is just turning; the directive's example
        # implies the catch is the *flip*, not deep-positive territory.
        if macd_state.hist >= -1e-9:
            macd_rising = True
            score += 2

    # (4) higher low — current bounce low > previous down-wave's low
    higher_low = False
    if prev_down_endings:
        prev_down_low = min(prev_down_endings)
        if bounce_bar["low"] > prev_down_low:
            higher_low = True
            score += 2

    # (5) volume confirmation
    volume_confirm = False
    if avg_5_bar_volume > 0 and bounce_bar["volume"] > avg_5_bar_volume:
        volume_confirm = True
        score += 1

    # (6) green candle
    green_bounce = bounce_bar["close"] > bounce_bar["open"]
    if green_bounce:
        score += 1

    # (7) minimal upper wick
    body = abs(bounce_bar["close"] - bounce_bar["open"])
    upper_wick = bounce_bar["high"] - max(bounce_bar["open"], bounce_bar["close"])
    minimal_upper_wick = body > 0 and (upper_wick / body) < 0.5
    if minimal_upper_wick:
        score += 1

    return WaveScore(
        total=score,
        has_prior_waves=has_prior,
        near_recent_low=near_recent_low,
        macd_rising=macd_rising,
        higher_low=higher_low,
        volume_confirm=volume_confirm,
        green_bounce=green_bounce,
        minimal_upper_wick=minimal_upper_wick,
    )


# ─────────────────────────────────────────────────────────────────────
# Hypothetical trade simulator (long entries on score-≥7 down waves)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class HypotheticalTrade:
    symbol: str
    date: str
    wave_id: int
    score: int
    entry_time_et: str
    entry_price: float
    target: float
    stop: float
    exit_time_et: str
    exit_price: float
    exit_reason: str  # "target_hit" | "stop_hit" | "time_stop"
    pnl_per_share: float
    shares: int
    pnl: float
    risk_per_share: float
    duration_minutes: float


# ─────────────────────────────────────────────────────────────────────
# Variant configuration (Stage 2 — DIRECTIVE_WAVE_BREAKOUT_STAGE2.md)
# ─────────────────────────────────────────────────────────────────────

@dataclass
class VariantConfig:
    """All exit/sizing knobs the simulator honors. V0-V8 are concrete
    presets defined below; new variants just add a preset."""
    name: str = "v0_baseline"

    # ── Sizing (V0 hardening — always on)
    risk_dollars: float = 1000.0          # base risk per trade
    score_weighted_risk: bool = False     # V6 → 7:$500, 8:$1k, 9:$1.5k, 10:$2k
    max_notional: float = 50_000.0        # absolute cap (V0 mandatory)

    # ── Target
    # "recent_up_high" — highest end-price of recent up-wave (with floor)
    # "fixed_pct"      — entry × (1 + target_pct)
    # "none"           — no fixed target (use trailing or session_end only)
    target_mode: str = "recent_up_high"
    target_pct: float = 0.0
    # Optional minimum-target floor: target = max(candidate, entry × (1+floor))
    # V0 keeps this at 0 to match Stage 1 baseline exit rules exactly; some
    # later variants (e.g. v8 combined) may set it.
    target_floor_pct: float = 0.0

    # ── Stop
    stop_buffer_pct: float = 0.25         # below bounce low

    # ── Trailing stop
    # Activates after price reaches +activate_r·R; trails offset_r·R below
    # the running peak. When active and price ≤ trail_stop, exit.
    trailing_enabled: bool = False
    trailing_activate_r: float = 1.0
    trailing_offset_r: float = 0.5

    # ── Time stop
    # None means no time cap (V4)
    time_stop_minutes: Optional[int] = 10

    # ── Pyramid
    # If set, on hitting +pyramid_at_r·R add a second leg sized identically
    # (subject to combined-position MAX_NOTIONAL cap).
    pyramid_at_r: Optional[float] = None

    # ── Score gate (V0 baseline = 7; tightening filters to higher-quality)
    min_score: int = 7

    def risk_for_score(self, score: int) -> float:
        if not self.score_weighted_risk:
            return self.risk_dollars
        return {7: 500.0, 8: 1000.0, 9: 1500.0, 10: 2000.0}.get(int(score), self.risk_dollars)


# Preset registry. New variants: add a constructor here; the orchestrator
# in wave_variants.py iterates over PRESETS by name.
def preset_v0() -> VariantConfig:  # baseline (Stage 1 rules + sizer hardening)
    return VariantConfig(name="v0_baseline")

def preset_v1() -> VariantConfig:  # wide target
    return VariantConfig(name="v1_wide_target", target_mode="fixed_pct", target_pct=0.05)

def preset_v2() -> VariantConfig:  # trailing stop only, no fixed target, no time cap
    return VariantConfig(name="v2_trailing_only", target_mode="none",
                          trailing_enabled=True, time_stop_minutes=None)

def preset_v3() -> VariantConfig:  # 30-min time stop
    return VariantConfig(name="v3_time30", time_stop_minutes=30)

def preset_v4() -> VariantConfig:  # no time stop
    return VariantConfig(name="v4_no_time_stop", time_stop_minutes=None)

def preset_v5() -> VariantConfig:  # pyramid on +1R
    return VariantConfig(name="v5_pyramid", pyramid_at_r=1.0)

def preset_v6() -> VariantConfig:  # score-weighted sizing
    return VariantConfig(name="v6_score_sized", score_weighted_risk=True)

def preset_v8(combined_cfg: Optional[VariantConfig] = None) -> VariantConfig:
    """V8 combined config — built data-driven from V1-V7 results.

    Inclusions:
      - V0 sizer hardening (mandatory; built in)
      - V2 mechanics: target_mode="none", trailing stop only — confirmed
        winner (PF 2.01, +443% over V0)
      - V3 mechanics: 30-min time stop as a failsafe in case trailing
        never arms (a wave that drifts sideways at +0.5R for 30 min is
        capital better used elsewhere)
      - V6 mechanics: score-weighted sizing — concentrates capital on
        cleaner setups (modest help alone, but compounds with trailing)
      - Pyramid intentionally OFF — flat alone, untested with V2 longer
        holds; revisit only if V8 misses Stage 3 PF gate
      - V7 (concurrent positions) is enforced at the portfolio driver,
        not in this single-position config — passed via wave_portfolio_sim.
    """
    return combined_cfg or VariantConfig(
        name="v8_combined",
        target_mode="none",
        trailing_enabled=True,
        trailing_activate_r=1.0,
        trailing_offset_r=0.5,
        time_stop_minutes=30,        # V3 failsafe
        score_weighted_risk=True,    # V6
    )

# V8 candidate variants (all built on V2 trailing-only). Run + compare.
def preset_v8a_v2_only() -> VariantConfig:
    return VariantConfig(name="v8a_v2_only", target_mode="none",
                          trailing_enabled=True, time_stop_minutes=None)

def preset_v8b_v2_pyramid() -> VariantConfig:
    return VariantConfig(name="v8b_v2_pyramid", target_mode="none",
                          trailing_enabled=True, time_stop_minutes=None,
                          pyramid_at_r=1.0)

def preset_v8c_v2_score8() -> VariantConfig:
    return VariantConfig(name="v8c_v2_score8", target_mode="none",
                          trailing_enabled=True, time_stop_minutes=None,
                          min_score=8)

def preset_v8d_v2_score9() -> VariantConfig:
    return VariantConfig(name="v8d_v2_score9", target_mode="none",
                          trailing_enabled=True, time_stop_minutes=None,
                          min_score=9)

def preset_v8e_v2_pyramid_score8() -> VariantConfig:
    return VariantConfig(name="v8e_v2_pyramid_score8", target_mode="none",
                          trailing_enabled=True, time_stop_minutes=None,
                          pyramid_at_r=1.0, min_score=8)


PRESETS = {
    "v0_baseline": preset_v0,
    "v1_wide_target": preset_v1,
    "v2_trailing_only": preset_v2,
    "v3_time30": preset_v3,
    "v4_no_time_stop": preset_v4,
    "v5_pyramid": preset_v5,
    "v6_score_sized": preset_v6,
    # v7 has its own driver (wave_portfolio_sim.py); no preset here.
    "v8_combined": preset_v8,
    "v8a_v2_only": preset_v8a_v2_only,
    "v8b_v2_pyramid": preset_v8b_v2_pyramid,
    "v8c_v2_score8": preset_v8c_v2_score8,
    "v8d_v2_score9": preset_v8d_v2_score9,
    "v8e_v2_pyramid_score8": preset_v8e_v2_pyramid_score8,
}


def _size_position(entry_price: float, stop: float, risk_dollars: float,
                   max_notional: float) -> Tuple[int, float]:
    """V0 sizer: returns (shares, effective_risk_per_share). Returns (0, 0)
    if the trade should be skipped."""
    if entry_price <= 0 or stop >= entry_price:
        return 0, 0.0
    raw_risk = entry_price - stop
    # V0 hardening — clamp risk to a sane floor before dividing.
    min_risk = max(0.01, entry_price * 0.001)
    risk_per_share = max(raw_risk, min_risk)
    shares_by_risk = int(risk_dollars / risk_per_share) if risk_per_share > 0 else 0
    shares_by_notional = int(max_notional / entry_price) if entry_price > 0 else 0
    shares = min(shares_by_risk, shares_by_notional)
    if shares <= 0:
        return 0, 0.0
    return shares, risk_per_share


def simulate_trade(
    *,
    symbol: str,
    date_str: str,
    wave: dict,
    score: int,
    bounce_bar: dict,
    next_bar: dict,
    forward_bars: List[dict],
    prior_waves: List[dict],
    config: Optional[VariantConfig] = None,
) -> Optional[HypotheticalTrade]:
    """Simulate a long trade entered on the bar after the bounce bar.

    Single-position variant (V0-V6, V8). Variant-specific exit rules come
    from `config`; sizing always honors V0 hardening (min risk-per-share
    floor + max-notional cap).

    Returns None if the trade is skipped (no upside room, sizing-zero,
    etc.). Otherwise returns a HypotheticalTrade row.
    """
    cfg = config or VariantConfig()

    entry_price = float(next_bar["open"])
    if entry_price <= 0:
        return None

    # ── Target (variant-controlled) ────────────────────────────────────
    if cfg.target_mode == "fixed_pct":
        target = entry_price * (1.0 + cfg.target_pct)
    elif cfg.target_mode == "none":
        target = float("inf")  # never hit → trailing/time/session control exit
    else:  # "recent_up_high"
        recent_up = [w for w in prior_waves[-5:] if w["direction"] == "up"]
        if not recent_up:
            return None
        candidate = max(w["end_price"] for w in recent_up)
        floor = entry_price * (1.0 + cfg.target_floor_pct)
        target = max(candidate, floor)
        if target <= entry_price:
            return None

    # ── Stop ───────────────────────────────────────────────────────────
    wave_low = float(bounce_bar["low"])
    stop = wave_low * (1.0 - cfg.stop_buffer_pct / 100.0)
    if stop >= entry_price:
        return None

    # ── Sizing (V0 hardening, variant-overridable risk_dollars) ────────
    risk_dollars = cfg.risk_for_score(score)
    shares, risk_per_share = _size_position(
        entry_price, stop, risk_dollars, cfg.max_notional,
    )
    if shares <= 0:
        return None

    R = entry_price - stop  # 1R = stop distance (use raw, not floored)

    # Pyramid bookkeeping
    pyramid_active = False
    pyramid_entry_price = 0.0
    pyramid_shares = 0

    # Trailing stop bookkeeping
    peak = entry_price
    trail_armed = False
    trail_stop_level = stop

    # ── Walk forward bars ──────────────────────────────────────────────
    entry_time_utc = datetime.fromisoformat(next_bar["start_utc"])
    if entry_time_utc.tzinfo is None:
        entry_time_utc = entry_time_utc.replace(tzinfo=timezone.utc)
    deadline = (entry_time_utc + timedelta(minutes=cfg.time_stop_minutes)
                if cfg.time_stop_minutes is not None else None)

    exit_price = None
    exit_reason = None
    exit_time_utc = entry_time_utc

    for fb in forward_bars:
        ts = (datetime.fromisoformat(fb["start_utc"])
              if isinstance(fb["start_utc"], str) else fb["start_utc"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        # Time stop check (variant-controlled)
        if deadline is not None and ts > deadline:
            exit_price = float(fb["open"])
            exit_reason = "time_stop"
            exit_time_utc = ts
            break

        bar_high = float(fb["high"])
        bar_low = float(fb["low"])

        # Update running peak — bar high is the best the trade saw this bar.
        if bar_high > peak:
            peak = bar_high

        # ── Trailing-stop activation + check ──
        if cfg.trailing_enabled:
            if not trail_armed and (peak - entry_price) >= cfg.trailing_activate_r * R:
                trail_armed = True
            if trail_armed:
                # Trail under the running peak by offset_r·R, but never
                # tighter than the original hard stop (don't widen risk).
                trail_stop_level = max(stop, peak - cfg.trailing_offset_r * R)

        # ── Pyramid second-leg activation ──
        if (cfg.pyramid_at_r is not None and not pyramid_active
                and (peak - entry_price) >= cfg.pyramid_at_r * R):
            # Add second leg at current price (use bar.close as proxy for
            # mid-bar fill — could also use peak; close is conservative).
            second_entry = float(fb["close"])
            # Combined-notional cap: how many extra shares can we add?
            current_notional = shares * entry_price
            remaining_notional = max(0.0, cfg.max_notional - current_notional)
            extra_by_notional = int(remaining_notional / second_entry) if second_entry > 0 else 0
            extra_by_risk = int(cfg.risk_dollars / risk_per_share) if risk_per_share > 0 else 0
            extra = min(extra_by_risk, extra_by_notional)
            if extra > 0:
                pyramid_active = True
                pyramid_entry_price = second_entry
                pyramid_shares = extra

        # ── Exit checks (in priority order: stop → trailing → target) ──
        # Conservative bar-resolution rule: when both stop and target/trail
        # are hit in the same bar, assume stop fires first.
        if cfg.trailing_enabled and trail_armed:
            effective_stop = trail_stop_level
        else:
            effective_stop = stop

        if bar_low <= effective_stop:
            exit_price = effective_stop
            exit_reason = ("trailing_stop" if (cfg.trailing_enabled and trail_armed
                                                and effective_stop > stop)
                           else "stop_hit")
            exit_time_utc = ts
            break
        if bar_high >= target:
            exit_price = target
            exit_reason = "target_hit"
            exit_time_utc = ts
            break

    if exit_price is None:
        # Ran out of forward bars (session_end). Mark with closing price.
        if forward_bars:
            last = forward_bars[-1]
            exit_price = float(last["close"])
            ts = (datetime.fromisoformat(last["start_utc"])
                  if isinstance(last["start_utc"], str) else last["start_utc"])
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            exit_time_utc = ts
        else:
            exit_price = entry_price
        exit_reason = "session_end"

    # P&L: leg-1 + leg-2 (pyramid)
    pnl_leg1 = (exit_price - entry_price) * shares
    pnl_leg2 = ((exit_price - pyramid_entry_price) * pyramid_shares
                if pyramid_active else 0.0)
    pnl = pnl_leg1 + pnl_leg2
    pnl_per_share = (exit_price - entry_price)  # leg-1 ps, for reference
    duration_minutes = (exit_time_utc - entry_time_utc).total_seconds() / 60.0

    return HypotheticalTrade(
        symbol=symbol,
        date=date_str,
        wave_id=int(wave["wave_id"]),
        score=score,
        entry_time_et=entry_time_utc.astimezone(ET).strftime("%H:%M:%S"),
        entry_price=round(entry_price, 4),
        target=round(target if target != float("inf") else 0.0, 4),
        stop=round(stop, 4),
        exit_time_et=exit_time_utc.astimezone(ET).strftime("%H:%M:%S"),
        exit_price=round(exit_price, 4),
        exit_reason=exit_reason,
        pnl_per_share=round(pnl_per_share, 4),
        shares=shares + pyramid_shares,  # combined position size (for reporting)
        pnl=round(pnl, 2),
        risk_per_share=round(risk_per_share, 4),
        duration_minutes=round(duration_minutes, 2),
    )


# ─────────────────────────────────────────────────────────────────────
# Per (symbol, date) processor
# ─────────────────────────────────────────────────────────────────────

@dataclass
class CensusRow:
    symbol: str
    date: str
    session_start_et: str
    session_end_et: str
    total_ticks: int
    total_bars: int
    total_waves: int
    waves_per_hour: float
    avg_wave_magnitude_pct: float
    median_wave_magnitude_pct: float
    max_wave_magnitude_pct: float
    avg_wave_duration_min: float
    up_waves: int
    down_waves: int
    setups_score_ge_7: int
    trades_simulated: int
    trades_pnl_total: float
    waves_premarket: int      # 4-9:30 ET
    waves_morning: int        # 9:30-12:00 ET
    waves_midday: int         # 12:00-15:00 ET
    waves_close: int          # 15:00-16:00 ET
    waves_afterhours: int     # 16:00-20:00 ET


def process_symbol_date(
    symbol: str, date_str: str, tick_path: str,
    config: Optional[VariantConfig] = None,
) -> Tuple[Optional[CensusRow], List[dict], List[HypotheticalTrade]]:
    """Process one (symbol, date) cell. Returns the census row, all detected
    wave dicts (each augmented with score fields), and any hypothetical
    trades simulated."""
    waves_emitted: List[dict] = []  # waves with score fields appended
    trades: List[HypotheticalTrade] = []

    bars: List[dict] = []  # parallel to detector's _bars but kept here for
                           # forward-walk simulation use.

    # Wave detector + MACD per symbol-date.
    det = WaveDetector(symbol)
    macd = MACDState()
    macd_history: List[Tuple[Optional[float], Optional[float]]] = []  # (hist, prev_hist) per bar

    def on_bar(bar: Bar) -> None:
        # Update MACD with bar close.
        macd.update(bar.close)
        macd_history.append((macd.hist, macd.prev_hist))

        # Mirror the bar into our local list (so simulate_trade can walk
        # forward bars without poking detector internals).
        bars.append({
            "start_utc": bar.start_utc.isoformat(),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": int(bar.volume),
        })

        # Feed bar to wave detector. May emit a wave.
        wave = det.on_bar_close(bar)
        if wave is None:
            return

        # The bar that just closed — call it the "bounce bar" for scoring.
        # When direction == 'down' (down-wave just ended), this bar is the
        # one whose low confirmed the wave; that's the long-entry candidate.
        bounce_bar = bars[-1]
        prior_waves = list(waves_emitted)  # everything emitted before this one

        if wave["direction"] == "down":
            # Score for long-entry setup.
            macd_snapshot = MACDState(
                ema12=macd.ema12, ema26=macd.ema26,
                macd=macd.macd, signal=macd.signal, hist=macd.hist,
                prev_macd=macd.prev_macd, prev_signal=macd.prev_signal,
                prev_hist=macd.prev_hist,
            )
            avg5 = det.avg_volume_last_n(5, end_bar_index=len(bars) - 2)  # avg of bars BEFORE bounce
            ws = score_wave_setup(
                just_emitted_wave=wave,
                prior_waves=prior_waves,
                bounce_bar=bounce_bar,
                avg_5_bar_volume=avg5,
                macd_state=macd_snapshot,
            )
            wave["score"] = ws.total
            wave["score_has_prior_waves"] = int(ws.has_prior_waves)
            wave["score_near_recent_low"] = int(ws.near_recent_low)
            wave["score_macd_rising"] = int(ws.macd_rising)
            wave["score_higher_low"] = int(ws.higher_low)
            wave["score_volume_confirm"] = int(ws.volume_confirm)
            wave["score_green_bounce"] = int(ws.green_bounce)
            wave["score_minimal_upper_wick"] = int(ws.minimal_upper_wick)

            # Simulate trade if score ≥ 7. Forward bars are everything
            # after the bounce bar. We build them lazily by stashing the
            # current bar index; the actual simulation runs when this
            # function returns and we know we have enough forward bars.
            wave["bounce_bar_index"] = len(bars) - 1
        else:
            # Up wave — not a long setup; record without scoring.
            wave["score"] = None
            for k in ("score_has_prior_waves", "score_near_recent_low", "score_macd_rising",
                      "score_higher_low", "score_volume_confirm", "score_green_bounce",
                      "score_minimal_upper_wick"):
                wave[k] = None
            wave["bounce_bar_index"] = None

        waves_emitted.append(wave)

    # Build bars from ticks.
    bar_builder = TradeBarBuilder(on_bar_close=on_bar, et_tz=ET, interval_seconds=60)
    n_ticks = 0
    first_ts = None
    last_ts = None
    for price, size, ts in load_ticks(tick_path):
        if first_ts is None:
            first_ts = ts
        last_ts = ts
        bar_builder.on_trade(symbol, price, size, ts)
        n_ticks += 1

    # Flush any pending bar by feeding a far-future tick? The TradeBarBuilder
    # only emits a bar on bucket transition. To flush the very last bucket
    # we'd need a sentinel — for the wave census, missing the very last
    # 1m bar is acceptable.

    # Now simulate trades for any down-waves clearing the variant's score
    # gate (default 7). Walk forward bars from each wave's bounce_bar_index.
    cfg_min_score = (config.min_score if config is not None else 7)
    for w in waves_emitted:
        if w["direction"] != "down" or w.get("score") is None:
            continue
        if w["score"] < cfg_min_score:
            continue
        bbi = w["bounce_bar_index"]
        if bbi is None or bbi + 1 >= len(bars):
            continue  # need at least the bar after bounce for entry
        bounce_bar = bars[bbi]
        next_bar = bars[bbi + 1]
        forward = bars[bbi + 2:]
        prior = [pw for pw in waves_emitted if pw["wave_id"] < w["wave_id"]]
        trade = simulate_trade(
            symbol=symbol,
            date_str=date_str,
            wave=w,
            score=int(w["score"]),
            bounce_bar=bounce_bar,
            next_bar=next_bar,
            forward_bars=forward,
            prior_waves=prior,
            config=config,
        )
        if trade is not None:
            trades.append(trade)

    if n_ticks == 0:
        return None, waves_emitted, trades

    # Census aggregates.
    mags = [w["magnitude_pct"] for w in waves_emitted]
    durs = [w["duration_minutes"] for w in waves_emitted]
    up_count = sum(1 for w in waves_emitted if w["direction"] == "up")
    down_count = sum(1 for w in waves_emitted if w["direction"] == "down")
    setups7 = sum(1 for w in waves_emitted
                  if w["direction"] == "down" and (w.get("score") or 0) >= 7)

    # Time-of-day bucket counts (use end_time_utc converted to ET).
    pm = morn = mid = close_b = ah = 0
    for w in waves_emitted:
        ts = datetime.fromisoformat(w["end_time_utc"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        et = ts.astimezone(ET).time()
        if et < datetime.strptime("09:30", "%H:%M").time():
            pm += 1
        elif et < datetime.strptime("12:00", "%H:%M").time():
            morn += 1
        elif et < datetime.strptime("15:00", "%H:%M").time():
            mid += 1
        elif et < datetime.strptime("16:00", "%H:%M").time():
            close_b += 1
        else:
            ah += 1

    session_seconds = (last_ts - first_ts).total_seconds() if first_ts and last_ts else 0
    session_hours = max(session_seconds / 3600.0, 0.001)

    if mags:
        sorted_mags = sorted(mags)
        median_mag = sorted_mags[len(sorted_mags) // 2]
        avg_mag = sum(mags) / len(mags)
        max_mag = max(mags)
        avg_dur = sum(durs) / len(durs)
    else:
        median_mag = avg_mag = max_mag = avg_dur = 0.0

    row = CensusRow(
        symbol=symbol,
        date=date_str,
        session_start_et=first_ts.astimezone(ET).strftime("%H:%M:%S") if first_ts else "",
        session_end_et=last_ts.astimezone(ET).strftime("%H:%M:%S") if last_ts else "",
        total_ticks=n_ticks,
        total_bars=len(bars),
        total_waves=len(waves_emitted),
        waves_per_hour=round(len(waves_emitted) / session_hours, 2),
        avg_wave_magnitude_pct=round(avg_mag, 3),
        median_wave_magnitude_pct=round(median_mag, 3),
        max_wave_magnitude_pct=round(max_mag, 3),
        avg_wave_duration_min=round(avg_dur, 2),
        up_waves=up_count,
        down_waves=down_count,
        setups_score_ge_7=setups7,
        trades_simulated=len(trades),
        trades_pnl_total=round(sum(t.pnl for t in trades), 2),
        waves_premarket=pm,
        waves_morning=morn,
        waves_midday=mid,
        waves_close=close_b,
        waves_afterhours=ah,
    )
    return row, waves_emitted, trades


# ─────────────────────────────────────────────────────────────────────
# Driver
# ─────────────────────────────────────────────────────────────────────

import re
_DATE_RE = re.compile(r"^2026-\d{2}-\d{2}$")  # strict YYYY-MM-DD; skip ".BROKEN_*" dirs


def discover_2026_files() -> List[Tuple[str, str, str]]:
    """Walk tick_cache/, return (symbol, date_str, full_path) for 2026-only."""
    out = []
    for name in sorted(os.listdir(TICK_CACHE)):
        if not _DATE_RE.match(name):
            continue
        date_dir = os.path.join(TICK_CACHE, name)
        if not os.path.isdir(date_dir):
            continue
        for fn in sorted(os.listdir(date_dir)):
            if not fn.endswith(".json.gz"):
                continue
            sym = fn[: -len(".json.gz")]
            out.append((sym, name, os.path.join(date_dir, fn)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Wave research census (variant-driven)")
    ap.add_argument("--variant", default="v0_baseline",
                    help=f"Variant preset name. Available: {', '.join(PRESETS.keys())}")
    ap.add_argument("--limit", type=int, default=0,
                    help="If >0, stop after this many (sym, date) cells (for testing)")
    ap.add_argument("--symbols", default="",
                    help="Comma-separated symbol filter (e.g. CNSP,PN). Empty = all.")
    ap.add_argument("--out-prefix", default="",
                    help="Output prefix override. Default = variant name.")
    ap.add_argument("--out-dir", default="",
                    help="Output dir override. Default = wave_research/<variant>/.")
    args = ap.parse_args()

    if args.variant not in PRESETS:
        print(f"Unknown variant: {args.variant}", file=sys.stderr)
        print(f"Available: {', '.join(PRESETS.keys())}", file=sys.stderr)
        return 2
    config = PRESETS[args.variant]()
    print(f"Variant: {config.name}", flush=True)

    files = discover_2026_files()
    if args.symbols:
        wanted = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
        files = [f for f in files if f[0].upper() in wanted]
    if args.limit:
        files = files[: args.limit]

    print(f"Census scope: {len(files)} (symbol, date) cells", flush=True)

    prefix = args.out_prefix or args.variant
    out_dir = args.out_dir or os.path.join(OUT_DIR, args.variant)
    os.makedirs(out_dir, exist_ok=True)
    census_path = os.path.join(out_dir, f"{prefix}_wave_census.csv")
    waves_path  = os.path.join(out_dir, f"{prefix}_waves_detail.csv")
    trades_path = os.path.join(out_dir, f"{prefix}_hypothetical_trades.csv")

    census_rows: List[CensusRow] = []
    all_waves: List[dict] = []
    all_trades: List[HypotheticalTrade] = []

    t0 = time.time()
    for i, (sym, date_str, path) in enumerate(files, 1):
        try:
            row, waves, trades = process_symbol_date(sym, date_str, path, config=config)
        except Exception as e:
            print(f"  [{i}/{len(files)}] {sym} {date_str}: ERROR {e}", flush=True)
            continue
        if row is not None:
            census_rows.append(row)
        for w in waves:
            w_out = dict(w)
            w_out["symbol"] = sym
            w_out["date"] = date_str
            all_waves.append(w_out)
        all_trades.extend(trades)
        if i % 50 == 0 or i == len(files):
            elapsed = time.time() - t0
            rate = i / max(elapsed, 0.001)
            print(f"  [{i}/{len(files)}] {sym} {date_str}: "
                  f"{row.total_waves if row else 0} waves, "
                  f"{row.setups_score_ge_7 if row else 0} setups≥7, "
                  f"{row.trades_simulated if row else 0} trades  "
                  f"[{rate:.1f}/s, eta {(len(files)-i)/max(rate,0.001):.0f}s]",
                  flush=True)

    # Write census CSV.
    with open(census_path, "w", newline="") as f:
        if census_rows:
            w = csv.DictWriter(f, fieldnames=list(vars(census_rows[0]).keys()))
            w.writeheader()
            for r in census_rows:
                w.writerow(vars(r))
    # Wave detail CSV.
    with open(waves_path, "w", newline="") as f:
        if all_waves:
            fieldnames = sorted({k for w in all_waves for k in w.keys()})
            # Move common keys to the front for readability.
            front = ["symbol", "date", "wave_id", "direction", "start_time_utc",
                     "end_time_utc", "start_price", "end_price",
                     "duration_minutes", "magnitude_pct", "magnitude_dollars",
                     "score"]
            ordered = [k for k in front if k in fieldnames] + \
                      [k for k in fieldnames if k not in front]
            w = csv.DictWriter(f, fieldnames=ordered)
            w.writeheader()
            for wave in all_waves:
                w.writerow(wave)
    # Trades CSV.
    with open(trades_path, "w", newline="") as f:
        if all_trades:
            fieldnames = list(vars(all_trades[0]).keys())
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for t in all_trades:
                w.writerow(vars(t))

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s", flush=True)
    print(f"  census   → {census_path}  ({len(census_rows)} rows)")
    print(f"  waves    → {waves_path}  ({len(all_waves)} rows)")
    print(f"  trades   → {trades_path}  ({len(all_trades)} rows)")

    if all_trades:
        wins = [t for t in all_trades if t.pnl > 0]
        losses = [t for t in all_trades if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in all_trades)
        gross_w = sum(t.pnl for t in wins)
        gross_l = abs(sum(t.pnl for t in losses))
        wr = len(wins) / len(all_trades) * 100.0
        pf = gross_w / gross_l if gross_l > 0 else float("inf")
        print(f"\nQuick read: {len(all_trades)} trades, {wr:.1f}% WR, "
              f"PF={pf:.2f}, total=${total_pnl:+,.0f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
