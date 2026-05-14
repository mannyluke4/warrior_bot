"""WB persistence layer — carry forward WB-observed symbols across sessions.

Cowork directive 2026-05-14 (DIRECTIVE_WB_SCANNER_STRATEGY.md §0.2):
  Track every symbol with WB_OBSERVE activity for N sessions. At boot,
  inject these symbols into the watchlist so wb_bot still has them even
  when the squeeze scanner filters them out for pm_volume < 30K (which
  was the channel keeping FATN/SST winners alive via stale-watchlist
  carryover — see cowork_reports/2026-05-14_wb_filter_gap_feedback.md).

File:   ~/warrior_bot_v2/wb_persistence.txt (override via WB_PERSIST_FILE)
Format: one CSV line per symbol — `SYMBOL,YYYY-MM-DD`
        date is the most recent WB_OBSERVE for that symbol

Public API:
  record_wb_observe(symbol)        — call from bot WB_OBSERVE log handler
  active_persisted_symbols() -> set — call from watchlist-poll for injection
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import pytz

ET = pytz.timezone("US/Eastern")

_DEFAULT_FILE = Path(__file__).resolve().parent / "wb_persistence.txt"
_FILE = Path(os.environ.get("WB_PERSIST_FILE", str(_DEFAULT_FILE)))
_ENABLED = os.environ.get("WB_PERSIST_ENABLED", "1") == "1"
_SESSIONS = max(1, int(os.environ.get("WB_PERSIST_SESSIONS", "3")))
_LOCK = Lock()


def _load_raw() -> dict[str, str]:
    if not _FILE.exists():
        return {}
    out: dict[str, str] = {}
    for line in _FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(",", 1)
        if len(parts) != 2:
            continue
        sym = parts[0].strip().upper()
        date_str = parts[1].strip()
        if not (sym and sym.isalpha() and 1 <= len(sym) <= 5):
            continue
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            continue
        out[sym] = date_str
    return out


def _atomic_write(data: dict[str, str]) -> None:
    lines = [
        "# wb_persistence.txt — WB-observed symbols within last N sessions",
        "# Format: SYMBOL,YYYY-MM-DD (last WB_OBSERVE date)",
        f"# Updated: {datetime.now(ET).isoformat(timespec='seconds')}",
    ]
    for sym in sorted(data):
        lines.append(f"{sym},{data[sym]}")
    tmp = _FILE.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    tmp.replace(_FILE)


def _prune(data: dict[str, str], today) -> dict[str, str]:
    cutoff = today - timedelta(days=_SESSIONS)
    out: dict[str, str] = {}
    for sym, d in data.items():
        try:
            obs = datetime.strptime(d, "%Y-%m-%d").date()
        except ValueError:
            continue
        if obs >= cutoff:
            out[sym] = d
    return out


def record_wb_observe(symbol: str) -> None:
    """Record a WB_OBSERVE event for `symbol` (no-op when disabled or
    already recorded today). Safe to call frequently — file write is
    skipped when the entry already matches today's date.

    Best-effort: any IO error is logged but never raised, because a
    persistence failure must not break the bot's main loop."""
    if not _ENABLED or not symbol:
        return
    symbol = symbol.upper().strip()
    if not (symbol.isalpha() and 1 <= len(symbol) <= 5):
        return
    today_et = datetime.now(ET).strftime("%Y-%m-%d")
    with _LOCK:
        try:
            data = _load_raw()
            if data.get(symbol) == today_et:
                return
            data[symbol] = today_et
            data = _prune(data, datetime.now(ET).date())
            _atomic_write(data)
        except Exception as e:
            print(f"[WB_PERSIST] record_wb_observe({symbol}) failed: {e!r}",
                  flush=True)


def active_persisted_symbols() -> set[str]:
    """Return the set of symbols with a WB_OBSERVE within the last
    WB_PERSIST_SESSIONS calendar days (inclusive of today). Returns
    empty set when disabled or on read error."""
    if not _ENABLED:
        return set()
    try:
        return set(_prune(_load_raw(), datetime.now(ET).date()).keys())
    except Exception as e:
        print(f"[WB_PERSIST] active_persisted_symbols read failed: {e!r}",
              flush=True)
        return set()


def debug_state() -> dict:
    """Return state snapshot for diagnostics — used by the validation
    script and by ad-hoc inspection. Not called from the hot path."""
    return {
        "enabled": _ENABLED,
        "sessions": _SESSIONS,
        "file": str(_FILE),
        "file_exists": _FILE.exists(),
        "entries": _load_raw(),
        "active_today": sorted(active_persisted_symbols()),
    }
