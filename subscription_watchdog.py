"""Subscription watchdog — observability for IBKR Tier-2 reqMktData wedges.

Per `cowork_reports/2026-05-26_subscription_watchdog_directive.md`.

Background: 2026-05-26 MNTS ran $7.38 → $15.47 while the bot's
`reqMktData` stream delivered ~25 ticks/hr instead of the real
~130K shares/min. Existing drought-only `check_subscription_health`
didn't see it because the wedged subscription wasn't silent — it
trickled occasional updates, just at a deeply degraded rate. This
module adds a tick-rate audit that compares observed per-symbol
volume against (a) the median across active symbols and (b) IBKR's
ground-truth historical bars on a throttled rotation.

DETECTION ONLY for v1. No auto-resubscribe. Emits structured JSON
log lines (`SUBSCRIPTION_AUDIT {...}`) that `scripts/abc_compare_daily.py`
ingests into the daily A/B/C report. The decision to add an
auto-resubscribe action is gated behind a separate directive once
we have 1-2 trading days of audit data.
"""
from __future__ import annotations

import json
import os
import statistics
import time
from collections import deque
from datetime import datetime
from typing import Any


# ── Tunables (env-driven, with safe defaults) ──────────────────────
ENABLED = os.getenv("WB_SUB_WATCHDOG_ENABLED", "0") == "1"
HEURISTIC_INTERVAL_SEC = int(os.getenv("WB_SUB_WATCHDOG_HEURISTIC_INTERVAL_SEC", "60"))
HEURISTIC_RATIO = float(os.getenv("WB_SUB_WATCHDOG_HEURISTIC_RATIO", "10"))  # median / RATIO
HEURISTIC_ABS_CAP = int(os.getenv("WB_SUB_WATCHDOG_HEURISTIC_ABS_CAP", "5000"))  # AND obs < this
DIRECT_QUERY_INTERVAL_SEC = int(os.getenv("WB_SUB_WATCHDOG_DIRECT_QUERY_INTERVAL_SEC", "300"))
DIRECT_QUERY_MAX = int(os.getenv("WB_SUB_WATCHDOG_DIRECT_QUERY_MAX", "5"))
WEDGE_THRESHOLD = float(os.getenv("WB_SUB_WATCHDOG_WEDGE_THRESHOLD", "0.1"))
DIRECT_QUERY_TIMEOUT_SEC = int(os.getenv("WB_SUB_WATCHDOG_DIRECT_QUERY_TIMEOUT_SEC", "10"))


# NOTE on timeout strategy: ib_insync's reqHistoricalData has a built-in
# `timeout=` parameter that returns whatever bars arrived within the
# deadline (empty list if none). We use that instead of a ThreadPoolExecutor
# wrap because ib_insync requires the calling thread to own the asyncio
# event loop; calling reqHistoricalData from a worker thread raises
# RuntimeError("no current event loop"). The watchdog tick() runs on the
# main bot thread (same thread as the loop), so direct sync calls are
# safe. The directive's executor-wrap suggestion (commit a8a95ec) was
# correct for cancelMktData/reqMktData (fire-and-forget) but doesn't
# apply to reqHistoricalData (which awaits on the response).


class SubscriptionWatchdog:
    """Observability watchdog. Call `tick(now)` from the main loop on
    each iteration; internal rate-limiting controls cycle cadence.

    Thread-safety: methods touch `state` (read-only) and IBKR via the
    executor (timeout-guarded). Should only be invoked from the main
    bot thread.
    """

    def __init__(self, state, ib, enabled: bool | None = None):
        self.state = state
        self.ib = ib
        # Allow explicit override (tests) but default to env-driven gate.
        self.enabled = ENABLED if enabled is None else bool(enabled)

        self._last_heuristic_at: datetime | None = None
        self._last_direct_query_at: datetime | None = None

        # Round-robin index into state.active_symbols for direct queries.
        self._round_robin_cursor = 0

        # Symbols flagged HEURISTIC_SUSPECT this cycle — fed into direct
        # query priority for the next direct-query slot.
        self._pending_suspects: set[str] = set()

        # Track last_observed_v_5m per symbol so we can include it in
        # AUDIT lines even on cycles where it wasn't recomputed.
        self._last_obs_v_5m: dict[str, int] = {}
        # Track subscription start times for sub_age_sec field (we don't
        # have authoritative subscribe_at in state; approximate with
        # first-seen time).
        self._first_seen_at: dict[str, datetime] = {}

        # Audit buffer — most-recent N lines for debug introspection.
        self.recent_audits: deque = deque(maxlen=500)

    # ──────────────────────────────────────────────────────────────
    # Entry point
    # ──────────────────────────────────────────────────────────────
    def tick(self, now: datetime) -> None:
        """Called from main bot loop. Cheap when disabled or rate-limited."""
        if not self.enabled:
            return
        if not self.state.active_symbols:
            return  # nothing to audit

        # Track first-seen for sub_age_sec
        for sym in self.state.active_symbols:
            if sym not in self._first_seen_at:
                self._first_seen_at[sym] = now

        try:
            heuristic_due = (
                self._last_heuristic_at is None
                or (now - self._last_heuristic_at).total_seconds() >= HEURISTIC_INTERVAL_SEC
            )
            direct_query_due = (
                self._last_direct_query_at is None
                or (now - self._last_direct_query_at).total_seconds() >= DIRECT_QUERY_INTERVAL_SEC
            )

            if heuristic_due:
                self._run_heuristic(now)
                self._last_heuristic_at = now
            if direct_query_due:
                self._run_direct_query(now)
                self._last_direct_query_at = now
        except Exception as e:
            # Defensive: a watchdog crash must not take down the bot.
            print(f"[SUB_WATCHDOG] tick error: {e!r}", flush=True)

    # ──────────────────────────────────────────────────────────────
    # Signal 1 — heuristic (no IBKR API cost)
    # ──────────────────────────────────────────────────────────────
    def _run_heuristic(self, now: datetime) -> None:
        """Flag HEURISTIC_SUSPECT for symbols whose 5-min observed volume
        is < median/RATIO AND < ABS_CAP. The dual-threshold avoids
        false positives on genuinely quiet symbols."""
        observed: dict[str, int] = {}
        for sym in list(self.state.active_symbols):
            buckets = self.state.tier1_volume_buckets.get(sym, [])
            total = sum(v for _, v in buckets)
            observed[sym] = total
            self._last_obs_v_5m[sym] = total

        nonzero = [v for v in observed.values() if v > 0]
        if not nonzero:
            # Pre-market or quiet across the board — nothing to compare.
            # Still emit OK lines so we have audit coverage.
            for sym in list(self.state.active_symbols):
                self._emit_audit(now, sym, observed[sym], None, None, "OK")
            return

        median_v = statistics.median(nonzero)
        threshold = median_v / HEURISTIC_RATIO

        # Reset suspect set for this cycle.
        self._pending_suspects = set()

        for sym in list(self.state.active_symbols):
            obs = observed[sym]
            ratio_to_median = (obs / median_v) if median_v > 0 else None

            is_suspect = (obs < threshold) and (obs < HEURISTIC_ABS_CAP)
            status = "HEURISTIC_SUSPECT" if is_suspect else "OK"
            if is_suspect:
                self._pending_suspects.add(sym)

            self._emit_audit(
                now, sym, obs, median_v, ratio_to_median, status,
                truth_v_5m=None, ratio_obs_to_truth=None,
            )

    # ──────────────────────────────────────────────────────────────
    # Signal 2 — direct query (precise, throttled)
    # ──────────────────────────────────────────────────────────────
    def _run_direct_query(self, now: datetime) -> None:
        """Pick up to DIRECT_QUERY_MAX symbols and verify against
        IBKR's ground-truth 5-min volume via reqHistoricalData."""
        targets = self._select_direct_query_targets()
        if not targets:
            return

        median_v = self._current_median_v()
        for sym in targets:
            truth_v = self._fetch_truth_volume_5m(sym)
            obs = self._last_obs_v_5m.get(sym, 0)
            if truth_v is None or truth_v <= 0:
                # Could not fetch truth — log without ratio.
                self._emit_audit(
                    now, sym, obs, median_v, None,
                    "DIRECT_QUERY_OK" if obs > 0 else "OK",
                    truth_v_5m=truth_v, ratio_obs_to_truth=None,
                    note="truth_unavailable",
                )
                continue
            ratio = obs / truth_v
            status = "DIRECT_QUERY_WEDGE" if ratio < WEDGE_THRESHOLD else "DIRECT_QUERY_OK"
            ratio_median = (obs / median_v) if median_v and median_v > 0 else None
            self._emit_audit(
                now, sym, obs, median_v, ratio_median, status,
                truth_v_5m=truth_v, ratio_obs_to_truth=ratio,
            )

    def _select_direct_query_targets(self) -> list[str]:
        """Selection priority (directive §Detection design §Signal 2):
          1. Open positions
          2. Heuristic suspects from this cycle
          3. Round-robin remainder
        Caps at DIRECT_QUERY_MAX total.

        Note: v1 omits explicit "scanner top-5" priority (#3 in directive)
        to keep the first ship lean. Round-robin will hit every symbol in
        the universe within (n_active / DIRECT_QUERY_MAX) * 5 min. For 95
        symbols that's a ~95-min worst-case lag. Documented in impl notes
        as a v2 enhancement.
        """
        active = list(self.state.active_symbols)
        if not active:
            return []

        seen: set[str] = set()
        targets: list[str] = []

        # 1. Open positions (squeeze, short, wave-breakout — all surfaces)
        for sym in self._open_position_symbols():
            if sym in self.state.active_symbols and sym not in seen:
                targets.append(sym)
                seen.add(sym)
                if len(targets) >= DIRECT_QUERY_MAX:
                    return targets

        # 2. Heuristic suspects (consume + clear)
        for sym in sorted(self._pending_suspects):
            if sym in self.state.active_symbols and sym not in seen:
                targets.append(sym)
                seen.add(sym)
                if len(targets) >= DIRECT_QUERY_MAX:
                    self._pending_suspects = set()
                    return targets
        self._pending_suspects = set()

        # 3. Round-robin remainder. Advance cursor across cycles so all
        # symbols get checked over time.
        n = len(active)
        for i in range(n):
            idx = (self._round_robin_cursor + i) % n
            sym = active[idx]
            if sym not in seen:
                targets.append(sym)
                seen.add(sym)
                if len(targets) >= DIRECT_QUERY_MAX:
                    # Advance cursor past this batch for next cycle.
                    self._round_robin_cursor = (idx + 1) % n
                    return targets
        # Wrapped fully — advance cursor by batch size to spread coverage.
        self._round_robin_cursor = (self._round_robin_cursor + DIRECT_QUERY_MAX) % max(1, n)
        return targets

    def _fetch_truth_volume_5m(self, symbol: str) -> int | None:
        """reqHistoricalData(300 S, 1 min, TRADES) → sum the bar volumes.
        Uses ib_insync's built-in `timeout=` parameter; called from the
        main bot thread (where the asyncio loop lives) so no executor
        wrap is needed."""
        contract = self.state.contracts.get(symbol)
        if contract is None:
            return None
        try:
            bars = self.ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr="300 S",
                barSizeSetting="1 min",
                whatToShow="TRADES",
                useRTH=False,
                formatDate=2,  # epoch seconds (avoids tz-string parsing)
                timeout=DIRECT_QUERY_TIMEOUT_SEC,
            )
        except Exception as e:
            print(f"[SUB_WATCHDOG] truth query {symbol} failed: {e!r}", flush=True)
            return None
        if not bars:
            # Empty list = either no data in window OR timeout hit. Treat
            # as truth_unavailable rather than zero-volume.
            return None
        try:
            return int(sum((b.volume or 0) for b in bars))
        except Exception:
            return None

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────
    def _open_position_symbols(self) -> set[str]:
        s: set[str] = set()
        op = getattr(self.state, "open_position", None)
        if op and op.get("symbol"):
            s.add(op["symbol"])
        sh = getattr(self.state, "open_short", None)
        if sh and sh.get("symbol"):
            s.add(sh["symbol"])
        wb = getattr(self.state, "wb_positions", None) or {}
        if isinstance(wb, dict):
            s.update(wb.keys())
        return s

    def _current_median_v(self) -> float | None:
        observed = [
            sum(v for _, v in self.state.tier1_volume_buckets.get(sym, []))
            for sym in self.state.active_symbols
        ]
        nonzero = [v for v in observed if v > 0]
        if not nonzero:
            return None
        return statistics.median(nonzero)

    def _emit_audit(
        self,
        now: datetime,
        symbol: str,
        obs_v_5m: int,
        median_v_5m: float | None,
        ratio_obs_to_median: float | None,
        status: str,
        truth_v_5m: int | None = None,
        ratio_obs_to_truth: float | None = None,
        note: str | None = None,
    ) -> None:
        """Emit one SUBSCRIPTION_AUDIT JSON line to stdout."""
        contract = self.state.contracts.get(symbol)
        primary = getattr(contract, "primaryExchange", None) if contract else None
        exchange = getattr(contract, "exchange", None) if contract else None
        tier = self.state.tier.get(symbol, "unknown")
        first_seen = self._first_seen_at.get(symbol)
        sub_age_sec = int((now - first_seen).total_seconds()) if first_seen else None

        payload: dict[str, Any] = {
            "ts": now.isoformat(),
            "sym": symbol,
            "tier": tier,
            "obs_v_5m": int(obs_v_5m or 0),
            "median_v_5m": (None if median_v_5m is None else int(median_v_5m)),
            "ratio_obs_to_median": (
                None if ratio_obs_to_median is None else round(ratio_obs_to_median, 4)
            ),
            "truth_v_5m": (None if truth_v_5m is None else int(truth_v_5m)),
            "ratio_obs_to_truth": (
                None if ratio_obs_to_truth is None else round(ratio_obs_to_truth, 4)
            ),
            "status": status,
            "sub_age_sec": sub_age_sec,
            "contract_exchange": exchange,
            "contract_primary": primary,
        }
        if note:
            payload["note"] = note
        line = "SUBSCRIPTION_AUDIT " + json.dumps(payload, separators=(",", ":"))
        print(line, flush=True)
        self.recent_audits.append(payload)


__all__ = ["SubscriptionWatchdog", "ENABLED"]
