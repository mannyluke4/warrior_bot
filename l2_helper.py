"""L2 Layer 1 helper — synchronous snapshot fetch + gate evaluation.

Cowork directive DIRECTIVE_2026-05-15_L2_LAYER1_TODAY.md. Same-day
observe-only ship: every WB and squeeze ARM that passes the existing
gate stack should ALSO request an L2 snapshot, run it through
L2SignalDetector, and log a verdict. Today: no veto. Monday: thresholds
tune from observe data, then flip OBSERVE_ONLY=0.

Design notes:
- One IBKRFeed per process, attached to the bot's existing IB connection.
  No new clientId (shares the main bot's IB connection).
- request_l2_snapshot() is synchronous with a 2s timeout. Caller blocks
  for up to 2s during ARM evaluation. ARMs are rare; this fits inside
  the 30s entry-retry window comfortably.
- Subscribe → wait for first non-empty depth → process → unsubscribe.
  L2 slot held only momentarily.
- ALL FAILURE PATHS RETURN None → caller treats as PASS. Infra failure
  must NEVER block an entry that would otherwise have fired. Same
  fail-open posture as the BP check.
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Optional

# Module-level env (read once at import)
_MAX_SPREAD_PCT = float(os.environ.get("WB_L2_MAX_SPREAD_PCT", "1.0"))
_MIN_IMBALANCE = float(os.environ.get("WB_L2_MIN_IMBALANCE", "0.40"))
_MIN_BID_DEPTH_TOUCH = float(os.environ.get("WB_L2_MIN_BID_DEPTH_TOUCH", "1000"))
_BLOCK_LARGE_ASK = os.environ.get("WB_L2_BLOCK_LARGE_ASK", "1") == "1"
_BLOCK_FALLING_TREND = os.environ.get("WB_L2_BLOCK_FALLING_TREND", "0") == "1"
_BID_DEPTH_TOUCH_PCT = float(os.environ.get("WB_L2_BID_DEPTH_TOUCH_PCT", "0.5"))


@dataclass
class L2Verdict:
    action: str   # "PASS" or "VETO"
    reason: str


# Per-process singletons (lazy)
_FEED = None
_DETECTOR = None
_FEED_LOCK = threading.Lock()


def _ensure(ib_instance=None) -> Optional[object]:
    """Lazy-init the shared L2 feed + detector. Returns the feed instance,
    or None on failure. If ib_instance is provided, attaches (shares the
    caller's IB connection). If None, dials a NEW IB connection using
    env-driven HOST/PORT/CLIENT_ID (engine bots use this path since they
    don't have their own IB connection — data_engine does)."""
    global _FEED, _DETECTOR
    with _FEED_LOCK:
        if _FEED is None:
            try:
                from ibkr_feed import IBKRFeed
                from l2_signals import L2SignalDetector
                feed = IBKRFeed()
                if ib_instance is not None:
                    feed.attach(ib_instance)
                    if not feed.is_connected:
                        print("[L2] feed attach failed — ib not connected", flush=True)
                        return None
                    mode = "attached"
                else:
                    if not feed.connect():
                        print("[L2] feed connect failed", flush=True)
                        return None
                    mode = "dedicated"
                _FEED = feed
                _DETECTOR = L2SignalDetector()
                print(f"[L2] singleton initialized ({mode} connection)",
                      flush=True)
            except Exception as e:
                print(f"[L2] singleton init failed: {e!r}", flush=True)
                return None
    return _FEED


def request_l2_snapshot(
    symbol: str,
    ib_instance=None,
    timeout_sec: float = 2.0,
) -> Optional[dict]:
    """Synchronous L2 snapshot fetch. Returns state dict or None on any
    failure (None → caller treats as PASS, never blocks the entry).

    If ib_instance is None, the feed dials its own IBKR connection using
    env-driven WB_IBKR_HOST/PORT/CLIENT_ID. Engine bots take this path
    (clientId should be distinct from data_engine's clientId=3)."""
    feed = _ensure(ib_instance)
    if feed is None:
        return None

    received = {"snap": None}
    done = threading.Event()

    def on_snap(sym, snap):
        if received["snap"] is None and snap.bids and snap.asks:
            received["snap"] = snap
            done.set()

    try:
        feed.subscribe_l2(symbol, on_snap, num_rows=10)
        got = done.wait(timeout_sec)
        if not got or received["snap"] is None:
            return None
        _DETECTOR.on_snapshot(received["snap"])
        return _DETECTOR.get_state(symbol)
    except Exception as e:
        print(f"[L2] snapshot {symbol} failed: {e!r}", flush=True)
        return None
    finally:
        try:
            feed.unsubscribe_l2(symbol)
        except Exception:
            pass


def _bid_depth_proxy(state: dict) -> Optional[float]:
    """Coarse proxy for bid depth at touch. Returns:
      - high value (≥ floor) when state evidences bid strength (stacking OR
        imbalance > 0.6 with ask_thinning)
      - None when state can't determine (don't VETO on missing evidence)

    The L2SignalDetector state dict doesn't expose raw bid sizes by level;
    a direct depth computation would require routing the raw snapshot
    through this helper. Deferred to Layer 2.
    """
    if state.get("bid_stacking"):
        levels = state.get("bid_stack_levels", [])
        n = len(levels) if isinstance(levels, list) else int(levels or 0)
        if n > 0:
            return float(n) * 5000.0
        return 15000.0
    imb = state.get("imbalance", 0.5)
    if imb > 0.6 and state.get("ask_thinning"):
        return 10000.0
    return None  # insufficient evidence — don't VETO


def evaluate_l2_filter(state: Optional[dict]) -> L2Verdict:
    """Map an L2 state dict to a verdict. None state → PASS (infra failure
    can't block). Returns L2Verdict for logging."""
    if state is None:
        return L2Verdict("PASS", "no_l2_data")

    if state.get("spread_pct", 0) > _MAX_SPREAD_PCT:
        return L2Verdict(
            "VETO",
            f"spread={state['spread_pct']:.2f}%>{_MAX_SPREAD_PCT}",
        )

    imb = state.get("imbalance", 0.5)
    if imb < _MIN_IMBALANCE:
        return L2Verdict("VETO", f"imbalance={imb:.2f}<{_MIN_IMBALANCE}")

    bid_depth = _bid_depth_proxy(state)
    if bid_depth is not None and bid_depth < _MIN_BID_DEPTH_TOUCH:
        return L2Verdict(
            "VETO",
            f"bid_depth_proxy={bid_depth:.0f}<{_MIN_BID_DEPTH_TOUCH}",
        )

    if state.get("large_ask") and _BLOCK_LARGE_ASK:
        return L2Verdict("VETO", "large_ask_wall_above")

    if state.get("imbalance_trend") == "falling" and _BLOCK_FALLING_TREND:
        return L2Verdict("VETO", "imbalance_falling")

    return L2Verdict(
        "PASS",
        f"imb={imb:.2f}_spread={state.get('spread_pct', 0):.2f}%",
    )


def summarize_l2(state: Optional[dict]) -> str:
    """One-line log summary for telemetry."""
    if not state:
        return "none"
    return (
        f"imb={state.get('imbalance', 0):.2f}"
        f"({state.get('imbalance_trend','?')}) "
        f"spread={state.get('spread_pct', 0):.2f}% "
        f"stack={state.get('bid_stacking', False)} "
        f"lg_bid={state.get('large_bid', False)} "
        f"lg_ask={state.get('large_ask', False)}"
    )
