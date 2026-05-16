"""End-to-end parity tests against real tick caches.

These tests are SLOW (load full tick caches) and are skipped by default
unless the test environment has the cache files at the expected paths.
They run as part of the squeeze migration acceptance check per
DIRECTIVE_2026-05-17_GO_FOR_BUILD §D1.

Acceptance:
  1. Raw SqueezeDetectorV2 vs wrapper produce *identical* state machine
     transitions, primings, arms, and entries across a full session.
  2. Number of ARM messages matches.
  3. Final detector state matches.

The harness builds 1-minute bars from the tick cache (07:00-12:00 ET
backtest window per CLAUDE.md), runs both detectors against the same
sequence, and diffs the output.
"""
from __future__ import annotations

import gzip
import json
import os
from collections import defaultdict
from datetime import datetime, time, timezone, timedelta
from pathlib import Path
from typing import List, Optional

import pytest

from framework.level_sources.base import Bar
from framework.level_sources.squeeze import SqueezeSource


REPO_ROOT = Path(__file__).resolve().parents[2]
TICK_CACHE = REPO_ROOT / "tick_cache"
ET_OFFSET_HOURS = -5  # CC default is EST; DST handled elsewhere


def _load_ticks(symbol: str, session_date: str) -> List[dict]:
    """Load the tick cache for (symbol, date)."""
    path = TICK_CACHE / session_date / f"{symbol}.json.gz"
    if not path.exists():
        return []
    with gzip.open(path, "rt") as f:
        return json.load(f)


def _ts_et(tick_iso: str) -> datetime:
    """Convert tick's UTC ISO timestamp to ET-naive datetime."""
    # Strip timezone, treat as UTC, then add ET offset.
    # Cache stores "2026-01-16T12:00:00.002987+00:00".
    dt = datetime.fromisoformat(tick_iso)
    # Convert to ET (EST -5h; ignore DST — January is EST anyway)
    dt_et = dt.astimezone(timezone(timedelta(hours=-5))).replace(tzinfo=None)
    return dt_et


def _build_minute_bars(
    ticks: List[dict],
    window_start_et: time = time(7, 0),
    window_end_et: time = time(12, 0),
) -> List[Bar]:
    """Aggregate ticks into 1m bars within the backtest window."""
    buckets: dict[datetime, dict] = {}
    for t in ticks:
        ts = _ts_et(t["t"])
        if not (window_start_et <= ts.time() < window_end_et):
            continue
        minute = ts.replace(second=0, microsecond=0)
        p = float(t["p"])
        s = float(t.get("s", 0))
        if minute not in buckets:
            buckets[minute] = {
                "o": p, "h": p, "lo": p, "c": p, "v": s
            }
        else:
            b = buckets[minute]
            b["h"] = max(b["h"], p)
            b["lo"] = min(b["lo"], p)
            b["c"] = p
            b["v"] += s
    bars = [
        Bar(
            timestamp=ts,
            open=b["o"], high=b["h"], low=b["lo"], close=b["c"],
            volume=b["v"], symbol="TEST",
        )
        for ts, b in sorted(buckets.items())
    ]
    return bars


def _run_raw(bars: List[Bar], pm_high: Optional[float], vwap_seed: float):
    """Run raw SqueezeDetectorV2 against a bar sequence."""
    from squeeze_detector_v2 import SqueezeDetectorV2

    det = SqueezeDetectorV2()
    det.symbol = bars[0].symbol if bars else ""
    if pm_high is not None:
        det.update_premarket_levels(pm_high)
    msgs = []

    class _B:
        pass

    # Track running VWAP for parity (simple cumulative typical-price × vol).
    cum_pv, cum_v = 0.0, 0.0
    for bar in bars:
        tp = (bar.high + bar.low + bar.close) / 3.0
        cum_pv += tp * bar.volume
        cum_v += bar.volume
        vwap = (cum_pv / cum_v) if cum_v > 0 else bar.close
        ba = _B()
        ba.open, ba.high, ba.low, ba.close, ba.volume = (
            bar.open, bar.high, bar.low, bar.close, bar.volume
        )
        msgs.append(det.on_bar_close_1m(ba, vwap=vwap))
    return det, msgs


def _run_wrapped(bars: List[Bar], pm_high: Optional[float], vwap_seed: float):
    src = SqueezeSource(symbol=bars[0].symbol if bars else "")
    if pm_high is not None:
        src.set_premarket_levels(pm_high)
    msgs = []
    cum_pv, cum_v = 0.0, 0.0
    for bar in bars:
        tp = (bar.high + bar.low + bar.close) / 3.0
        cum_pv += tp * bar.volume
        cum_v += bar.volume
        vwap = (cum_pv / cum_v) if cum_v > 0 else bar.close
        src.set_vwap(vwap)
        src.update_intraday(bar)
        msgs.append(src.pull_arm_message())
    return src.detector, msgs


@pytest.mark.skipif(
    not (TICK_CACHE / "2026-01-16" / "VERO.json.gz").exists(),
    reason="tick cache not available",
)
@pytest.mark.parametrize("symbol,session_date", [
    ("VERO", "2026-01-16"),
    ("ROLR", "2026-01-14"),
])
def test_wrapper_parity_against_raw_detector(
    symbol: str, session_date: str, monkeypatch
) -> None:
    """Wrapper and raw detector must produce identical signal sequences."""
    monkeypatch.setenv("WB_SQUEEZE_ENABLED", "1")
    monkeypatch.setenv("WB_SQ_VOL_MULT", "2.5")
    monkeypatch.setenv("WB_SQ_PRIME_BARS", "4")
    monkeypatch.setenv("WB_SQ_MIN_BODY_PCT", "2.0")
    monkeypatch.setenv("WB_SQ_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("WB_SEED_GATE_ENABLED", "0")

    ticks = _load_ticks(symbol, session_date)
    if not ticks:
        pytest.skip(f"no tick cache for {symbol} {session_date}")

    bars = _build_minute_bars(ticks)
    if len(bars) < 10:
        pytest.skip(f"too few bars for {symbol} ({len(bars)})")

    # Derive PM high from bars before 09:30
    pm_bars = [b for b in bars if b.timestamp.time() < time(9, 30)]
    pm_high = max((b.high for b in pm_bars), default=None)

    raw_det, raw_msgs = _run_raw(bars, pm_high, vwap_seed=bars[0].close)
    wrap_det, wrap_msgs = _run_wrapped(bars, pm_high, vwap_seed=bars[0].close)

    # State machines must end up identical
    assert raw_det._state == wrap_det._state, (
        f"final state divergence: raw={raw_det._state} wrap={wrap_det._state}"
    )

    # Same attempt count
    assert raw_det._attempts == wrap_det._attempts, (
        f"attempts divergence: raw={raw_det._attempts} wrap={wrap_det._attempts}"
    )

    # Same armed state
    assert (raw_det.armed is None) == (wrap_det.armed is None), (
        f"armed divergence: raw_armed={raw_det.armed is not None}, "
        f"wrap_armed={wrap_det.armed is not None}"
    )

    # Non-empty messages must be identical
    raw_nonempty = [(i, m) for i, m in enumerate(raw_msgs) if m]
    wrap_nonempty = [(i, m) for i, m in enumerate(wrap_msgs) if m]
    assert raw_nonempty == wrap_nonempty, (
        f"message stream divergence:\n"
        f"  raw {len(raw_nonempty)} msgs vs wrap {len(wrap_nonempty)} msgs\n"
        f"  first diff: raw[0]={raw_nonempty[:3]} vs wrap[0]={wrap_nonempty[:3]}"
    )


@pytest.mark.skipif(
    not (TICK_CACHE / "2026-01-16" / "VERO.json.gz").exists(),
    reason="tick cache not available",
)
def test_wrapper_produces_arm_for_vero(monkeypatch) -> None:
    """Sanity check: VERO 2026-01-16 should arm at least once under
    X01 tuning. This is the canonical regression date per CLAUDE.md."""
    monkeypatch.setenv("WB_SQUEEZE_ENABLED", "1")
    monkeypatch.setenv("WB_SQ_VOL_MULT", "2.5")
    monkeypatch.setenv("WB_SQ_PRIME_BARS", "4")
    monkeypatch.setenv("WB_SQ_MIN_BODY_PCT", "2.0")
    monkeypatch.setenv("WB_SQ_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("WB_SEED_GATE_ENABLED", "0")

    ticks = _load_ticks("VERO", "2026-01-16")
    if not ticks:
        pytest.skip("VERO tick cache missing")
    bars = _build_minute_bars(ticks)
    pm_bars = [b for b in bars if b.timestamp.time() < time(9, 30)]
    pm_high = max((b.high for b in pm_bars), default=None)

    _wrap_det, wrap_msgs = _run_wrapped(bars, pm_high, vwap_seed=bars[0].close)
    arm_msgs = [m for m in wrap_msgs if m and "ARMED" in m]
    # At least one ARM somewhere in the session
    assert len(arm_msgs) >= 1, (
        f"expected at least one ARM message for VERO 2026-01-16, got 0. "
        f"All msgs: {[m for m in wrap_msgs if m][:5]}"
    )
