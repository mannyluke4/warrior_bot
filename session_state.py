"""Session-resume persistence (read/write helpers only — no bot wiring).

Approved by Cowork 2026-04-15 (see cowork_reports/2026-04-15_greenlight_session_resume.md).
This module owns durable state so the bot can resume mid-day after a crash
rather than doing a full cold boot (wide scanner scan + per-symbol
reqHistoricalTicks seeding). Detectors are rebuilt by replaying ticks from
tick_cache/, not deserialized — everything here is the minimum durable fact
set needed to drive that replay correctly.

On-disk layout:

    session_state/YYYY-MM-DD/
        marker.json          # exists iff today's session has run
        watchlist.json       # symbols subscribed this session
        risk.json            # daily P&L + counters + last-50 closed trades
        open_trades.json     # active positions with full trade-management state
        epl_state.json       # EPL graduation + registry (best-effort)
    tick_cache/YYYY-MM-DD/
        <SYM>.json.gz        # append-only tick log, written by bot_v3_hybrid

All writes go through atomic_write_json (tmpfile + os.replace). All reads
return a typed default on any failure so the bot can degrade to cold start
cleanly rather than crash on corrupt JSON.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

# Repo root — this module lives at the top level of warrior_bot_v2
_ROOT = os.path.dirname(os.path.abspath(__file__))

# Session/cache directory names. The main bot uses defaults ("session_state"
# / "tick_cache"); a parallel bot (e.g. bot_alpaca_subbot.py) sets these env
# vars at startup to write to isolated directories. Resolved at first call,
# not import (env may not be loaded yet when this module imports).
def _session_dir_name() -> str:
    return os.getenv("WB_SESSION_DIR_NAME", "session_state")

def _tick_cache_dir_name() -> str:
    return os.getenv("WB_TICK_CACHE_DIR_NAME", "tick_cache")

# Cap closed_trades in risk.json to bound the file size over a day
CLOSED_TRADES_CAP = 50

# Required fields for an open_trades.json entry. Schema is strict so a
# downstream bug that drops a field fails fast instead of producing an
# unmanaged position on resume.
#
# Note: the bot uses reactive exits (see 2026-04-15_finding_no_standing_exits.md)
# — no standing stop/target orders exist, so no stop_order_id/target_order_id
# fields. `order_id` is the ENTRY order ID, retained for crash-window
# cross-check against Alpaca position history.
OPEN_TRADE_REQUIRED_FIELDS = {
    "symbol", "setup_type", "entry_price", "entry_time", "qty", "r",
    "stop", "target_r", "target_price", "peak", "trail_mode",
    "partial_filled_at", "partial_filled_qty", "bail_timer_start",
    "exit_mode", "order_id", "fill_confirmed", "score", "is_parabolic",
}


# ══════════════════════════════════════════════════════════════════════
# Paths
# ══════════════════════════════════════════════════════════════════════

def _today_str() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def session_dir(date_str: str | None = None) -> str:
    return os.path.join(_ROOT, _session_dir_name(), date_str or _today_str())


def tick_cache_dir(date_str: str | None = None) -> str:
    return os.path.join(_ROOT, _tick_cache_dir_name(), date_str or _today_str())


def _path(name: str, date_str: str | None = None) -> str:
    return os.path.join(session_dir(date_str), name)


# ══════════════════════════════════════════════════════════════════════
# Atomic IO
# ══════════════════════════════════════════════════════════════════════

def atomic_write_json(path: str, data: Any) -> None:
    """Write JSON atomically: tmpfile in same dir → fsync → os.replace.

    Same-dir tmpfile guarantees the rename is atomic on the same filesystem.
    os.replace is atomic on POSIX and Windows.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        # Best-effort cleanup of tmp file on failure
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def read_json_safe(path: str, default: Any) -> Any:
    """Read JSON, return default on any failure (missing, corrupt, perms)."""
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


# ══════════════════════════════════════════════════════════════════════
# Marker — boot-mode decision rests on this
# ══════════════════════════════════════════════════════════════════════

def write_marker(date_str: str | None = None) -> None:
    atomic_write_json(_path("marker.json", date_str), {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pid": os.getpid(),
    })


def read_marker(date_str: str | None = None) -> dict | None:
    data = read_json_safe(_path("marker.json", date_str), None)
    return data if isinstance(data, dict) else None


def marker_exists(date_str: str | None = None) -> bool:
    return os.path.exists(_path("marker.json", date_str))


def marker_age_seconds(date_str: str | None = None) -> float | None:
    m = read_marker(date_str)
    if not m or "created_at" not in m:
        return None
    try:
        created = datetime.fromisoformat(m["created_at"])
        return (datetime.now(timezone.utc) - created).total_seconds()
    except (ValueError, TypeError):
        return None


# ══════════════════════════════════════════════════════════════════════
# Watchlist
# ══════════════════════════════════════════════════════════════════════

def write_watchlist(symbols: list[dict]) -> None:
    """symbols = [{"symbol": str, "subscribed_at": iso_ts}, ...]"""
    atomic_write_json(_path("watchlist.json"), symbols)


def read_watchlist(date_str: str | None = None) -> list[dict]:
    data = read_json_safe(_path("watchlist.json", date_str), [])
    return data if isinstance(data, list) else []


# ══════════════════════════════════════════════════════════════════════
# Risk (daily counters + capped closed trades)
# ══════════════════════════════════════════════════════════════════════

def write_risk(
    daily_pnl: float,
    daily_trades: int,
    consecutive_losses: int,
    closed_trades: list[dict],
) -> None:
    """Persist daily risk state. closed_trades is capped at CLOSED_TRADES_CAP
    (FIFO — keep the most recent). Counters are the durable state; the list
    is diagnostic.
    """
    trimmed = closed_trades[-CLOSED_TRADES_CAP:] if len(closed_trades) > CLOSED_TRADES_CAP else closed_trades
    atomic_write_json(_path("risk.json"), {
        "daily_pnl": float(daily_pnl),
        "daily_trades": int(daily_trades),
        "consecutive_losses": int(consecutive_losses),
        "closed_trades": trimmed,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


def read_risk(date_str: str | None = None) -> dict:
    data = read_json_safe(_path("risk.json", date_str), None)
    if not isinstance(data, dict):
        return {"daily_pnl": 0.0, "daily_trades": 0, "consecutive_losses": 0, "closed_trades": []}
    return {
        "daily_pnl": float(data.get("daily_pnl", 0.0)),
        "daily_trades": int(data.get("daily_trades", 0)),
        "consecutive_losses": int(data.get("consecutive_losses", 0)),
        "closed_trades": data.get("closed_trades", []) or [],
    }


# ══════════════════════════════════════════════════════════════════════
# Open trades — the Gap 1 payload
# ══════════════════════════════════════════════════════════════════════

def _validate_open_trade(entry: dict) -> None:
    missing = OPEN_TRADE_REQUIRED_FIELDS - set(entry.keys())
    if missing:
        raise ValueError(f"open_trade entry missing required fields: {sorted(missing)}")


def write_open_trades(trades: list[dict]) -> None:
    """Persist active trade-management state. Every state transition
    (fill, stop update, trail update, partial fill, bail-timer) calls this.
    File is small (≤3KB, ≤3 active trades typical) so full rewrite each
    time is fine.
    """
    for t in trades:
        _validate_open_trade(t)
    atomic_write_json(_path("open_trades.json"), trades)


def read_open_trades(date_str: str | None = None) -> list[dict]:
    data = read_json_safe(_path("open_trades.json", date_str), [])
    if not isinstance(data, list):
        return []
    valid = []
    for entry in data:
        if not isinstance(entry, dict):
            print(f"⚠️  read_open_trades: dropped non-dict entry ({type(entry).__name__})", flush=True)
            continue
        try:
            _validate_open_trade(entry)
        except ValueError as e:
            # Skip malformed entries on read — safer than crashing the boot,
            # but log loudly so a real writer bug doesn't hide behind it.
            sym = entry.get("symbol", "?")
            print(f"⚠️  read_open_trades: dropped malformed entry for {sym} ({e})", flush=True)
            continue
        valid.append(entry)
    return valid


# ══════════════════════════════════════════════════════════════════════
# EPL state — best-effort (Cowork q2)
# ══════════════════════════════════════════════════════════════════════

def write_epl_state(state: dict) -> None:
    atomic_write_json(_path("epl_state.json"), state)


def read_epl_state(date_str: str | None = None) -> dict:
    data = read_json_safe(_path("epl_state.json", date_str), {})
    return data if isinstance(data, dict) else {}


# ══════════════════════════════════════════════════════════════════════
# WB / short / WB-pending state — durable plan for non-squeeze strategies.
#
# Per project rule (feedback_session_persistence_required.md): every
# strategy's open positions, pending orders, and exit plan must persist so
# a restart can resume them. The squeeze side uses open_trades.json above;
# this is the equivalent for WB and short. Format is permissive — no strict
# schema validation — because these strategies' state shapes evolve more
# than squeeze's stable trade record.
# ══════════════════════════════════════════════════════════════════════

def write_wb_state(
    *,
    wb_positions: dict,
    wb_pending_orders: dict,
    open_short: dict | None,
) -> None:
    """Persist non-squeeze strategy state. Called on every mutation
    (entry fill, exit fill, pyramid, trail update, order placement) so a
    `kill -9` mid-update loses at most one tick of stop-trail data.

    Datetimes inside the dicts are serialized via the default=str fallback
    in atomic_write_json — they round-trip as ISO strings on read.
    """
    payload = {
        "wb_positions": wb_positions,
        "wb_pending_orders": wb_pending_orders,
        "open_short": open_short,
    }
    atomic_write_json(_path("wb_state.json"), payload)


def read_wb_state(date_str: str | None = None) -> dict:
    """Read non-squeeze strategy state. Returns empty-but-shaped dict on any
    failure so the boot path can call this unconditionally."""
    data = read_json_safe(_path("wb_state.json", date_str),
                          {"wb_positions": {}, "wb_pending_orders": {}, "open_short": None})
    if not isinstance(data, dict):
        return {"wb_positions": {}, "wb_pending_orders": {}, "open_short": None}
    return {
        "wb_positions": data.get("wb_positions") if isinstance(data.get("wb_positions"), dict) else {},
        "wb_pending_orders": data.get("wb_pending_orders") if isinstance(data.get("wb_pending_orders"), dict) else {},
        "open_short": data.get("open_short") if isinstance(data.get("open_short"), dict) else None,
    }


# ══════════════════════════════════════════════════════════════════════
# Scrub
# ══════════════════════════════════════════════════════════════════════

def scrub_today() -> None:
    """Wipe today's session_state/ and tick_cache/. Does NOT touch
    float_cache.json (cross-day with its own TTL per review)."""
    shutil.rmtree(session_dir(), ignore_errors=True)
    shutil.rmtree(tick_cache_dir(), ignore_errors=True)


# ══════════════════════════════════════════════════════════════════════
# Boot-mode decision
# ══════════════════════════════════════════════════════════════════════

def decide_boot_mode(fresh: bool = False, scrub: bool = False) -> tuple[str, str]:
    """Decide cold vs resume. Returns (mode, reason) for logging.

    mode ∈ {"cold", "resume"}
    """
    if scrub:
        scrub_today()
        return "cold", "scrub_flag"
    if fresh:
        return "cold", "fresh_flag"
    if not marker_exists():
        return "cold", "no_marker"

    # Empty-state fallback (Gap 4): marker present but nothing durable to
    # resume from → cold, don't silently phantom-resume.
    td = tick_cache_dir()
    has_ticks = os.path.isdir(td) and any(os.scandir(td))
    risk_path = _path("risk.json")
    wl_path = _path("watchlist.json")
    has_risk = os.path.exists(risk_path) and os.path.getsize(risk_path) > 2
    has_wl = os.path.exists(wl_path) and os.path.getsize(wl_path) > 2

    if not (has_ticks or has_risk or has_wl):
        return "cold", "empty_state"
    return "resume", "marker_present"


# ══════════════════════════════════════════════════════════════════════
# Orphan-position flatten — the Cowork safety-note helper
# ══════════════════════════════════════════════════════════════════════

def flatten_orphan_position(
    broker,
    symbol: str,
    qty: int,
    avg_cost: float,
    current_price: float | None = None,
) -> None:
    """LEGACY name retained for callers; this NO LONGER flattens. Per project
    rule (feedback_session_persistence_required.md), the bot must never
    auto-flatten an orphan position with a market order — that's how the
    2026-05-05 CLNN incident happened. Orphans now halt: this function logs
    loudly and the caller is expected to set an entry-halt flag in bot state
    so new entries are blocked until manual reconciliation.

    `broker` parameter retained for signature compatibility with the old
    flatten path; intentionally unused.
    """
    impact = None
    if current_price is not None:
        impact = (current_price - avg_cost) * qty
    print(
        f"🚧 ORPHAN POSITION DETECTED: {symbol} {qty} shares @ ${avg_cost:.2f} avg_cost "
        f"— no rehydrated state record. Bot will NOT auto-flatten (per project rules). "
        f"Halt new entries; manual reconcile required."
        + (f" Est. impact at ${current_price:.2f}: ${impact:+,.2f}" if impact is not None else ""),
        flush=True,
    )
