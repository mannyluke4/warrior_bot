"""Discovery-time entry gate — OBSERVE-ONLY logging.

Research (2026-06-05, `cowork_reports`/memory project_discovery_time_entry_research):
over a 55-day pool of 312 bot-subscribe discoveries, a discovery is a "clean rip"
(touches +5% before -5%) 37.2% of the time. A simple negative gate —

    SKIP if  discovery_hour >= 11 ET  AND  pre_discovery 1-min vol < 1.5%   ("G1")

— cuts 41% of discoveries (the dead-tape, afternoon names), lifts the retained
pool to 48.9% clean-rip / +10.7% median MFE, keeps 35/40 big winners, and the
separation holds in BOTH temporal halves (47/22 early, 50/20 late).

This module ONLY LOGS what the gate WOULD do at each subscribe. It never blocks a
subscription or alters trading. Activate with WB_DISCOVERY_GATE_OBSERVE=1; default
off → `observe_discovery()` is a no-op. Mirrors the wb_intraday_adder observe pattern.
Writes one JSONL line per discovery to logs/<date>_discovery_gate_observe.jsonl so the
gate can be validated against live outcomes before it is ever wired into entries.
"""
import os
import json
import statistics
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

OBSERVE = os.getenv("WB_DISCOVERY_GATE_OBSERVE", "0") == "1"
LOG_DIR = os.getenv("WB_LOG_DIR", "logs")

# G1 gate params (overridable for tuning without code change)
GATE_HOUR_MIN = int(os.getenv("WB_DGATE_HOUR_MIN", "11"))        # skip if hour >= this ...
GATE_PREVOL_MAX = float(os.getenv("WB_DGATE_PREVOL_MAX", "1.5"))  # ... AND pre_vol < this
PREVOL_BARS = 30        # window for realized pre-discovery vol
RUNUP_BARS = 15         # window for pre-discovery run-up
MIN_BARS = 16           # below this, features are unreliable → record as insufficient


def _features(bars_1m):
    """Compute discovery-time features from a SqueezeDetector.bars_1m deque
    (ordered dicts with key 'c' = 1-min close). Returns None if too few bars."""
    closes = [b["c"] for b in bars_1m if isinstance(b, dict) and b.get("c", 0) > 0]
    if len(closes) < MIN_BARS:
        return None
    recent = closes[-PREVOL_BARS:]
    rets = [(recent[i] / recent[i - 1] - 1) * 100
            for i in range(1, len(recent)) if recent[i - 1] > 0]
    pre_vol = statistics.pstdev(rets) if len(rets) > 1 else 0.0
    if len(closes) > RUNUP_BARS and closes[-RUNUP_BARS - 1] > 0:
        runup15 = (closes[-1] / closes[-RUNUP_BARS - 1] - 1) * 100
    else:
        runup15 = 0.0
    return {"entry": closes[-1], "pre_vol": pre_vol,
            "runup15": runup15, "n_bars": len(closes)}


def _gate_skip(hour, pre_vol):
    """G1: skip afternoon dead-tape names."""
    return hour >= GATE_HOUR_MIN and pre_vol < GATE_PREVOL_MAX


def _append(now_et, record):
    path = os.path.join(LOG_DIR, f"{now_et.strftime('%Y-%m-%d')}_discovery_gate_observe.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def observe_discovery(symbol, sq_detector, now_et=None):
    """Log what the discovery gate WOULD do for `symbol` at subscribe time.
    OBSERVE-ONLY: returns the would-skip decision but the caller ignores it.
    Wrapped so it can never raise into the bot."""
    if not OBSERVE:
        return None
    try:
        now_et = now_et or datetime.now(ET)
        bars = list(getattr(sq_detector, "bars_1m", []) or [])
        feat = _features(bars)
        hour = now_et.hour
        if feat is None:
            rec = {"ts": now_et.isoformat(), "symbol": symbol,
                   "insufficient_bars": True, "n_bars": len(bars),
                   "would_skip": False, "observe_only": True}
            would_skip = False
        else:
            would_skip = _gate_skip(hour, feat["pre_vol"])
            rec = {"ts": now_et.isoformat(), "symbol": symbol, "hour": hour,
                   "pre_vol": round(feat["pre_vol"], 3),
                   "runup15": round(feat["runup15"], 2),
                   "entry": round(feat["entry"], 4), "n_bars": feat["n_bars"],
                   "gate": "G1", "would_skip": would_skip, "observe_only": True}
        _append(now_et, rec)
        if would_skip:
            print(f"  [DGATE] {symbol} WOULD-SKIP (hour={hour} "
                  f"pre_vol={feat['pre_vol']:.2f}<{GATE_PREVOL_MAX}) — observe only", flush=True)
        return would_skip
    except Exception:
        return None  # never disturb the bot
