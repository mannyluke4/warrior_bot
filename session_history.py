"""session_history.py — per-symbol win/loss history across trading sessions.

Used by chop_gate_v3's xsession_bl sub-gate. Two rule modes are supported,
selected by the active sub-gate:

  v1 (legacy)  — count losses in last N trades; blacklist for ~7 days if
                 >= LOSS_THRESHOLD losses and wins < losses.
  v2 (Cowork modular 2026-05-12, §5) — refined rule:
       blacklist iff over the last LOOKBACK_DAYS *days* of trades on this
       symbol (excluding today):
           r_sum < 0  AND  losses > 2 * wins
           AND  len(trades) >= MIN_TRADES
       — R-multiple sum AND win-rate ratio. Drop recency decay (lookback
       window already bounds recency).

`record_trade` and the v1 blacklist computation are unchanged so the
existing data-collection path (always-on, write-only from both bots)
keeps producing the same trade-history file. The v2 rule is consumed by
chop_gate_v3.sub_gate_xsession_bl via the new `get_trades()` accessor.

Persists to <repo_root>/state/symbol_session_history.json by default;
configurable via WB_V3_SESSION_HISTORY_FILE so the engine bot can write
to its own state dir without colliding with Setup A's.

Schema (per symbol):
    {
        "trades": [
            {"date": "2026-05-08", "pnl": -771.6, "r_multiple": -1.04, "win": false},
            ...
        ],
        "blacklisted_until": "2026-05-15"  // or null  (v1 rule)
    }

Public API:
    SessionHistory(history_file=None)
    record_trade(symbol, date, pnl, r_multiple)
    is_blacklisted(symbol, today) -> (bool, reason)        # v1 rule (legacy)
    get_trades(symbol, lookback_days, exclude_today) -> [TradeRecord]
    manual_unblacklist(symbol)

Thresholds:
    WB_V3_SESSION_HISTORY_LOOKBACK         (default 10)        v1
    WB_V3_SESSION_HISTORY_LOSS_THRESHOLD   (default 3)         v1
    WB_V3_SESSION_HISTORY_BLACKLIST_DAYS   (default 7)         v1
    WB_V3_SESSION_HISTORY_FILE             (default state/symbol_session_history.json)
    WB_CG3_XSESSION_LOOKBACK_DAYS          (default 7)         v2
    WB_CG3_XSESSION_MIN_TRADES             (default 3)         v2
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class TradeRecord:
    """Lightweight record returned by SessionHistory.get_trades().

    The xsession_bl sub-gate reads .pnl + .r_multiple; .win is derived.
    """
    date: str
    pnl: float
    r_multiple: float

    @property
    def win(self) -> bool:
        return self.pnl > 0


# Module-level lock so simultaneous record_trade calls from two threads
# (e.g., WB exit + squeeze exit) can't corrupt the same JSON file. The
# file is tiny so a single lock is fine.
_FILE_LOCK = threading.RLock()

# Resolve the repo root from this module's location so the default path
# works whether the import comes from setup A (warrior_bot_v2/) or from
# the engine worktree (warrior_bot_v2_engine/). The engine duplicates
# this module byte-for-byte so each repo writes to its OWN state dir,
# matching how session_state.py already works.
_ROOT = Path(os.path.dirname(os.path.abspath(__file__)))


def _default_history_file() -> Path:
    override = os.getenv("WB_V3_SESSION_HISTORY_FILE", "")
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = _ROOT / p
        return p
    return _ROOT / "state" / "symbol_session_history.json"


def _parse_iso_date(s: str) -> _date:
    """Accept either 'YYYY-MM-DD' or a full ISO datetime. Returns a date."""
    # Try date first (cheap, common case).
    try:
        return _date.fromisoformat(s)
    except ValueError:
        # Fall back to full datetime parse.
        return datetime.fromisoformat(s).date()


class SessionHistory:
    """Tracks per-symbol win/loss history across sessions.

    Persists to <state_dir>/symbol_session_history.json. Survives bot
    restarts. Updated after every closed trade via record_trade().
    """

    def __init__(self, history_file: Optional[str | Path] = None):
        if history_file is None:
            self.path: Path = _default_history_file()
        else:
            self.path = Path(history_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)

        self.lookback = int(os.getenv("WB_V3_SESSION_HISTORY_LOOKBACK", "10"))
        self.loss_threshold = int(
            os.getenv("WB_V3_SESSION_HISTORY_LOSS_THRESHOLD", "3")
        )
        self.blacklist_days = int(
            os.getenv("WB_V3_SESSION_HISTORY_BLACKLIST_DAYS", "7")
        )
        self._data = self._load()

    # ── IO ──────────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self) -> None:
        # Best-effort atomic write to avoid corruption on crash mid-write.
        tmp = self.path.with_suffix(self.path.suffix + f".tmp.{os.getpid()}")
        try:
            with open(tmp, "w") as f:
                json.dump(self._data, f, indent=2, default=str)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            os.replace(tmp, self.path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

    # ── Public API ─────────────────────────────────────────────────────

    def record_trade(
        self,
        symbol: str,
        date: str,
        pnl: float,
        r_multiple: float,
    ) -> None:
        """Record a closed trade. Call from the exit-handling path AFTER
        pnl is finalized. Updates the blacklist if the pattern triggers."""
        with _FILE_LOCK:
            # Re-read so concurrent records from a sibling bot in the
            # same repo (if any) don't get clobbered. Then merge our
            # change and save.
            self._data = self._load()
            entry = self._data.setdefault(
                symbol, {"trades": [], "blacklisted_until": None}
            )
            entry["trades"].append({
                "date": date,
                "pnl": float(pnl),
                "r_multiple": float(r_multiple),
                "win": float(pnl) > 0,
            })
            # Storage hygiene — only keep the last 30 trades per symbol.
            if len(entry["trades"]) > 30:
                entry["trades"] = entry["trades"][-30:]
            self._maybe_update_blacklist(symbol)
            self._save()

    def is_blacklisted(self, symbol: str, today: str) -> Tuple[bool, str]:
        """Returns (is_blacklisted, reason). Auto-clears expired entries."""
        entry = self._data.get(symbol)
        if not entry:
            return False, ""
        until = entry.get("blacklisted_until")
        if not until:
            return False, ""

        try:
            until_date = _parse_iso_date(str(until))
            today_date = _parse_iso_date(str(today))
        except (ValueError, TypeError):
            # Corrupt entry — treat as not blacklisted and clear it so
            # the next record_trade overwrites cleanly.
            with _FILE_LOCK:
                self._data = self._load()
                e = self._data.get(symbol)
                if e is not None:
                    e["blacklisted_until"] = None
                    self._save()
            return False, ""

        if today_date >= until_date:
            # Expired — clear and persist.
            with _FILE_LOCK:
                self._data = self._load()
                e = self._data.get(symbol)
                if e is not None:
                    e["blacklisted_until"] = None
                    self._save()
            return False, ""

        return (
            True,
            f"recent_loss_pattern (3+ losses in last 10, "
            f"blacklisted until {until_date.isoformat()})",
        )

    def manual_unblacklist(self, symbol: str) -> None:
        """Operator override — e.g., if a stock has clearly changed character."""
        with _FILE_LOCK:
            self._data = self._load()
            if symbol in self._data:
                self._data[symbol]["blacklisted_until"] = None
                self._save()

    def get_trades(
        self,
        symbol: str,
        lookback_days: int = 7,
        exclude_today: Optional[str] = None,
    ) -> List[TradeRecord]:
        """Return closed trades for `symbol` from the last `lookback_days`
        calendar days, excluding any trade dated `exclude_today`.

        Used by chop_gate_v3.sub_gate_xsession_bl (v2 rule per Cowork
        modular directive 2026-05-12, §5). Pure read; does not mutate
        state or trigger v1 blacklist recomputation.
        """
        entry = self._data.get(symbol)
        if not entry:
            return []
        trades = entry.get("trades", [])
        if not trades:
            return []

        try:
            anchor = (
                _parse_iso_date(str(exclude_today))
                if exclude_today is not None
                else datetime.utcnow().date()
            )
        except (ValueError, TypeError):
            anchor = datetime.utcnow().date()
        cutoff = anchor - timedelta(days=int(lookback_days))

        out: List[TradeRecord] = []
        for t in trades:
            try:
                d = _parse_iso_date(str(t.get("date")))
            except (ValueError, TypeError):
                continue
            if exclude_today is not None:
                try:
                    if d == _parse_iso_date(str(exclude_today)):
                        continue
                except (ValueError, TypeError):
                    pass
            if d < cutoff:
                continue
            try:
                pnl = float(t.get("pnl", 0.0))
            except (TypeError, ValueError):
                pnl = 0.0
            try:
                rm = float(t.get("r_multiple", 0.0))
            except (TypeError, ValueError):
                rm = 0.0
            out.append(TradeRecord(date=str(t.get("date")), pnl=pnl, r_multiple=rm))
        return out

    # ── Internals ───────────────────────────────────────────────────────

    def _maybe_update_blacklist(self, symbol: str) -> None:
        """Apply or clear blacklist based on recent N-trade window."""
        entry = self._data.get(symbol)
        if not entry:
            return
        trades = entry.get("trades", [])
        if not trades:
            return

        # Look at the configurable window of most-recent trades.
        recent = trades[-self.lookback:]
        losses = sum(1 for t in recent if not t.get("win", False))
        wins = sum(1 for t in recent if t.get("win", False))

        if losses >= self.loss_threshold and wins < losses:
            # Anchor the blacklist to the LATEST trade date in the window
            # so backfills/replays produce deterministic results.
            try:
                latest_date = _parse_iso_date(str(recent[-1]["date"]))
            except (KeyError, ValueError, TypeError):
                latest_date = datetime.utcnow().date()
            entry["blacklisted_until"] = (
                latest_date + timedelta(days=self.blacklist_days)
            ).isoformat()
        else:
            entry["blacklisted_until"] = None


__all__ = ["SessionHistory", "TradeRecord"]
