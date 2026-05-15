"""Session-end force-exit — pairs with the FCHL session-resume fix.

Cowork directive 2026-05-15 §3 P0.2: flatten ALL open positions before the
extended-hours session closes. Prevents the date-boundary orphan class
that produced today's $13K FCHL loss.

User constraint: NEVER market orders (project memory feedback_no_market_
orders.md). Force-exit uses an aggressive SELL LIMIT with chase — initial
limit at last_price × (1 - first_offset_pct), each retry widens by
retry_step_pct, up to max_retries attempts.

Public API:
  should_force_exit_now() -> bool   — caller checks once per main-loop tick
  force_exit_position(...)          — submits the aggressive SELL LIMIT chain
  reset_fired_flag()                — for testing; clears the once-per-day latch

The module-level latch ensures the timer fires AT MOST ONCE per process per
calendar day, so it's safe to call should_force_exit_now() on every loop tick.
"""
from __future__ import annotations

import os
import threading
from datetime import datetime, time as dtime, date
from typing import Optional

import pytz

ET = pytz.timezone("US/Eastern")

# Env — load once at import
_ENABLED = os.environ.get("WB_SESSION_END_FORCE_EXIT", "1") == "1"
_END_TIME_ET = os.environ.get("WB_SESSION_END_TIME_ET", "20:00")
_LEAD_MIN = int(os.environ.get("WB_SESSION_END_LEAD_MIN", "5"))
_FIRST_OFFSET_PCT = float(os.environ.get("WB_SESSION_END_FIRST_OFFSET_PCT", "1.0"))
_RETRY_STEP_PCT = float(os.environ.get("WB_SESSION_END_RETRY_STEP_PCT", "1.0"))
_MAX_RETRIES = int(os.environ.get("WB_SESSION_END_MAX_RETRIES", "3"))
_FILL_TIMEOUT_SEC = int(os.environ.get("WB_SESSION_END_FILL_TIMEOUT_SEC", "10"))

# Once-per-day-per-process latch
_FIRED_LOCK = threading.Lock()
_FIRED_DATE: Optional[date] = None


def _parse_hhmm(s: str) -> dtime:
    try:
        hh, mm = s.strip().split(":")
        return dtime(int(hh), int(mm))
    except Exception:
        print(f"[FORCE_EXIT] bad WB_SESSION_END_TIME_ET={s!r} — defaulting to 20:00",
              flush=True)
        return dtime(20, 0)


def _trigger_time_et() -> dtime:
    end = _parse_hhmm(_END_TIME_ET)
    # Lead = end - LEAD_MIN minutes
    total_min = end.hour * 60 + end.minute - _LEAD_MIN
    if total_min < 0:
        total_min = 0
    return dtime(total_min // 60, total_min % 60)


def should_force_exit_now(now_et: Optional[datetime] = None) -> bool:
    """Returns True at most once per calendar day per process, at or after
    the trigger time. Latches via _FIRED_DATE so callers can poll freely."""
    if not _ENABLED:
        return False
    global _FIRED_DATE
    now = now_et or datetime.now(ET)
    trigger = _trigger_time_et()
    if now.time() < trigger:
        return False
    with _FIRED_LOCK:
        today = now.date()
        if _FIRED_DATE == today:
            return False
        _FIRED_DATE = today
        return True


def reset_fired_flag() -> None:
    """Test hook — clear the latch so should_force_exit_now() returns True
    again on the next call. Production code should never call this."""
    global _FIRED_DATE
    with _FIRED_LOCK:
        _FIRED_DATE = None


def _last_known_price(broker, symbol: str, fallback: float = 0.0) -> float:
    """Best-effort last price from broker. Falls back to caller-supplied
    reference if broker query fails."""
    try:
        q = broker.get_latest_quote(symbol)
        if q and getattr(q, "ask_price", 0) and getattr(q, "bid_price", 0):
            return (float(q.ask_price) + float(q.bid_price)) / 2.0
        if q and getattr(q, "bid_price", 0):
            return float(q.bid_price)
    except Exception:
        pass
    return fallback


def force_exit_position(
    broker,
    symbol: str,
    qty: int,
    reference_price: float,
    log_prefix: str = "",
) -> dict:
    """Submit aggressive SELL LIMIT with chase-down ladder. Returns dict
    {"filled": bool, "fill_price": float|None, "fill_qty": int, "attempts": int,
     "reason": str}.

    Respects user's no-market-orders rule. Each attempt:
      - limit = reference × (1 - offset_pct/100)
      - waits up to _FILL_TIMEOUT_SEC for fill
      - if not filled: cancel, widen offset by _RETRY_STEP_PCT, retry
      - aborts after _MAX_RETRIES attempts
    """
    result = {
        "filled": False, "fill_price": None, "fill_qty": 0,
        "attempts": 0, "reason": "max_retries",
    }
    if qty <= 0 or reference_price <= 0:
        result["reason"] = f"invalid_args qty={qty} ref={reference_price}"
        return result

    # Refresh reference from broker for accuracy
    live_ref = _last_known_price(broker, symbol, fallback=reference_price)
    if live_ref > 0:
        reference_price = live_ref

    offset_pct = _FIRST_OFFSET_PCT
    cur_order_id = None
    for attempt in range(1, _MAX_RETRIES + 1):
        result["attempts"] = attempt
        limit_price = round(reference_price * (1 - offset_pct / 100.0), 2)
        if limit_price <= 0:
            result["reason"] = "limit_non_positive"
            break

        print(f"{log_prefix}FORCE_EXIT {symbol} attempt {attempt}/{_MAX_RETRIES}: "
              f"SELL {qty} @ ${limit_price:.4f} (ref=${reference_price:.4f}, "
              f"offset={offset_pct:.1f}%)", flush=True)

        try:
            order = broker.submit_limit(symbol, qty, "SELL", limit_price,
                                         extended_hours=True)
            cur_order_id = getattr(order, "order_id", None)
        except Exception as e:
            print(f"{log_prefix}FORCE_EXIT {symbol} submit raised: {e!r}",
                  flush=True)
            offset_pct += _RETRY_STEP_PCT
            continue

        # Poll for fill
        from time import sleep, time as _now
        deadline = _now() + _FILL_TIMEOUT_SEC
        fill_price = None
        fill_qty = 0
        while _now() < deadline:
            try:
                o = broker.get_order_status(cur_order_id)
                if o is not None and getattr(o, "status", "") in ("filled", "FILLED"):
                    fill_price = float(o.filled_avg_price)
                    fill_qty = int(o.filled_qty)
                    break
                if o is not None and getattr(o, "status", "") in (
                    "cancelled", "expired", "rejected", "CANCELLED", "EXPIRED", "REJECTED"
                ):
                    break
            except Exception:
                pass
            sleep(0.5)

        if fill_price is not None and fill_qty > 0:
            result.update(filled=True, fill_price=fill_price, fill_qty=fill_qty,
                          reason="filled")
            print(f"{log_prefix}FORCE_EXIT {symbol} FILLED @ ${fill_price:.4f} "
                  f"qty={fill_qty} (attempt {attempt})", flush=True)
            return result

        # Cancel and widen
        try:
            broker.cancel_order(cur_order_id)
        except Exception:
            pass
        offset_pct += _RETRY_STEP_PCT

    print(f"{log_prefix}FORCE_EXIT {symbol} GIVING UP after {_MAX_RETRIES} retries "
          f"(final offset={offset_pct - _RETRY_STEP_PCT:.1f}%)", flush=True)
    return result


def env_summary() -> str:
    """For diagnostic log line at bot boot."""
    return (f"force_exit: enabled={_ENABLED} end={_END_TIME_ET} ET "
            f"trigger={_trigger_time_et().strftime('%H:%M')} ET "
            f"first_offset={_FIRST_OFFSET_PCT}% step={_RETRY_STEP_PCT}% "
            f"retries={_MAX_RETRIES}")
