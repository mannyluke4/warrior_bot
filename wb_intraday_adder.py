"""WB Intraday Adder — Stage 0.3 (Cowork DIRECTIVE_GO_STAGE_0_3.md)

Polls the IBKR scanner during regular trading hours for WB-shaped
candidates the premarket scanner missed (gap-from-prev-close ≥ 3%,
intraday RVOL ≥ 3×, price 2-30, float ≤ 30M, today's volume ≥ 500K).

DAY 1 IS OBSERVE-ONLY. The poll writes one JSONL line per cycle to
`logs/<today>_wb_intraday_adder_observe.jsonl` describing what WOULD
have been added in live mode. No live watchlist injection unless
`WB_INTRADAY_ADDER_OBSERVE_ONLY=0`.

Public API (the caller — bot_v3_hybrid.py — owns the timing + IO):
  - SHOULD_RUN: read at boot to decide whether to wire the periodic call
  - poll(ib, *, now_et, poll_n, session_losses=None) -> dict
        Returns the telemetry record. Caller writes it to JSONL and,
        if not observe-only, can use `passing_symbols` to subscribe.

The poll is throttled by the caller (every WB_INTRADAY_ADDER_POLL_MIN
minutes), not internally — keeps timing control where the bot's main
loop already lives.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Optional

import pytz
from ib_insync import IB, ScannerSubscription

ET = pytz.timezone("US/Eastern")

# ── Env-driven config ────────────────────────────────────────────────
ENABLED = os.getenv("WB_INTRADAY_ADDER_ENABLED", "0") == "1"
OBSERVE_ONLY = os.getenv("WB_INTRADAY_ADDER_OBSERVE_ONLY", "1") == "1"
POLL_MIN = int(os.getenv("WB_INTRADAY_ADDER_POLL_MIN", "15"))
TIME_START = os.getenv("WB_INTRADAY_ADDER_TIME_START", "09:45")
TIME_END = os.getenv("WB_INTRADAY_ADDER_TIME_END", "15:30")
GAP_MIN = float(os.getenv("WB_INTRADAY_ADDER_GAP_MIN", "3.0"))
RVOL_MIN = float(os.getenv("WB_INTRADAY_ADDER_RVOL_MIN", "3.0"))
PRICE_MIN = float(os.getenv("WB_INTRADAY_ADDER_PRICE_MIN", "2.00"))
PRICE_MAX = float(os.getenv("WB_INTRADAY_ADDER_PRICE_MAX", "30.00"))
FLOAT_MAX_M = float(os.getenv("WB_INTRADAY_ADDER_FLOAT_MAX", "30"))
VOLUME_TODAY_MIN = int(os.getenv("WB_INTRADAY_ADDER_VOLUME_TODAY_MIN", "500000"))
# H#14 — "pre-9 MT block" → block entries before 09:00 MT == 11:00 ET
PRE_THRESHOLD_HOUR_ET = int(os.getenv("WB_PRE_THRESHOLD_HOUR_ET", "11"))

SHOULD_RUN = ENABLED

_LOG_DIR = Path(__file__).resolve().parent / "logs"


def _parse_hhmm(s: str) -> dtime:
    h, m = s.split(":")
    return dtime(int(h), int(m))


def _in_window(now_et: datetime) -> bool:
    start = _parse_hhmm(TIME_START)
    end = _parse_hhmm(TIME_END)
    t = now_et.time()
    return start <= t <= end


def _output_path(now_et: datetime) -> Path:
    today = now_et.strftime("%Y-%m-%d")
    return _LOG_DIR / f"{today}_wb_intraday_adder_observe.jsonl"


def _scan_top_gainers(ib: IB, top_n: int = 30) -> list:
    """Raw IBKR scanner pull — TOP_PERC_GAIN with intraday-friendly bounds."""
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        abovePrice=PRICE_MIN,
        belowPrice=PRICE_MAX,
        aboveVolume=VOLUME_TODAY_MIN,
        marketCapBelow=500_000_000,
        numberOfRows=top_n,
    )
    try:
        return ib.reqScannerData(sub) or []
    except Exception as e:
        print(f"⚠️  WB_INTRADAY_ADDER scanner pull failed: {e!r}", flush=True)
        return []


def _evaluate(ib: IB, contract, float_cache: dict) -> Optional[dict]:
    """Snapshot one symbol → return filtered record or None.

    Best-effort: any per-symbol error is logged and skipped, never raised."""
    try:
        symbol = contract.symbol
        # qualify + snapshot
        ib.qualifyContracts(contract)
        t = ib.reqMktData(contract, "", True, False)
        ib.sleep(2)

        price = t.last or t.close or 0
        prev_close = t.close or 0
        volume = t.volume or 0

        if price <= 0 or prev_close <= 0:
            return None

        gap_pct = (price - prev_close) / prev_close * 100

        # We don't compute ADV/RVOL here — too slow per symbol for a 15-min poll.
        # Use the scanner's volume rank as a proxy; the gap + abs-volume gate
        # already filters out untraded names (VOLUME_TODAY_MIN guard above).
        rvol_proxy = volume / max(1, VOLUME_TODAY_MIN)

        # Float lookup
        from float_cache import get_float
        float_shares = get_float(symbol, float_cache)
        float_m = round(float_shares / 1e6, 2) if float_shares else None

        # WB-specific gates
        if gap_pct < GAP_MIN:
            return None
        if rvol_proxy < (RVOL_MIN * VOLUME_TODAY_MIN / max(1, VOLUME_TODAY_MIN)):
            # Roughly equivalent to volume >= RVOL_MIN * VOLUME_TODAY_MIN
            if volume < RVOL_MIN * VOLUME_TODAY_MIN:
                return None
        if float_m is not None and float_m > FLOAT_MAX_M:
            return None

        return {
            "symbol": symbol,
            "price": round(price, 4),
            "prev_close": round(prev_close, 4),
            "gap_pct": round(gap_pct, 2),
            "volume_today": int(volume),
            "rvol_proxy": round(rvol_proxy, 2),
            "float_m": float_m,
        }
    except Exception as e:
        print(f"⚠️  WB_INTRADAY_ADDER eval failed for "
              f"{getattr(contract, 'symbol', '?')}: {e!r}", flush=True)
        return None


def _gate_stack_check(
    candidate: dict,
    *,
    now_et: datetime,
    session_losses: Optional[dict],
    active_symbols: Optional[set],
) -> dict:
    """Compute would_pass_post_wed_gate_stack for this candidate.

    Day 1: covers H#14 (pre-9 MT / pre-11 ET time gate) and H#11
    (same-session blacklist). Score-based gates (R% floor, MACD,
    divergent quote) require detector state we don't have on a fresh
    candidate — deferred to v2 of this module per directive."""
    h11_blacklisted = bool(session_losses and candidate["symbol"] in session_losses)
    h14_post_threshold = now_et.hour >= PRE_THRESHOLD_HOUR_ET
    already_active = bool(active_symbols and candidate["symbol"] in active_symbols)
    return {
        "h11_same_session_blacklisted": h11_blacklisted,
        "h14_post_pre_threshold_time": h14_post_threshold,
        "already_in_active_symbols": already_active,
        "would_pass_now": (not h11_blacklisted) and h14_post_threshold and (not already_active),
    }


def poll(
    ib: IB,
    *,
    now_et: Optional[datetime] = None,
    poll_n: int = 0,
    session_losses: Optional[dict] = None,
    active_symbols: Optional[set] = None,
) -> Optional[dict]:
    """One poll cycle. Returns the telemetry record (and writes it to
    JSONL). Returns None when out of window or disabled.

    `session_losses` and `active_symbols` are passed by the caller so
    we can compute the gate-stack overlay without coupling to bot state."""
    if not ENABLED:
        return None
    now_et = now_et or datetime.now(ET)
    if not _in_window(now_et):
        return None

    raw = _scan_top_gainers(ib)

    # Lazy float-cache load to avoid touching disk on disabled paths
    from float_cache import load_float_cache
    float_cache = load_float_cache()

    candidates: list[dict] = []
    for r in raw:
        rec = _evaluate(ib, r.contractDetails.contract, float_cache)
        if rec is None:
            continue
        rec["gate_stack"] = _gate_stack_check(
            rec, now_et=now_et,
            session_losses=session_losses,
            active_symbols=active_symbols,
        )
        # score_at_observe_time: deferred to v2. For Day 1 we emit null
        # rather than fake a value. Cowork's spec lets us iterate.
        rec["score_at_observe_time"] = None
        candidates.append(rec)

    record = {
        "ts": now_et.isoformat(timespec="seconds"),
        "poll_n": poll_n,
        "observe_only": OBSERVE_ONLY,
        "candidates_evaluated": len(raw),
        "candidates_passing": len(candidates),
        "candidates": candidates,
        "filter": {
            "gap_min": GAP_MIN, "rvol_min": RVOL_MIN,
            "price_min": PRICE_MIN, "price_max": PRICE_MAX,
            "float_max_m": FLOAT_MAX_M, "volume_today_min": VOLUME_TODAY_MIN,
        },
    }

    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _output_path(now_et).open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as e:
        print(f"⚠️  WB_INTRADAY_ADDER write JSONL failed: {e!r}", flush=True)

    return record


def passing_symbols(record: dict) -> list[str]:
    """Helper: extract symbols the caller would subscribe in live mode."""
    if not record:
        return []
    return [c["symbol"] for c in record.get("candidates", [])
            if c.get("gate_stack", {}).get("would_pass_now")]
