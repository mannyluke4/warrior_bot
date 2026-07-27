"""
bot_v3_hybrid.py — Warrior Bot V3: IBKR data + Alpaca execution.

Hybrid architecture:
- IB Gateway: scanner, tick data (reqMktData/RTVolume), VWAP, bar building
- Alpaca: order execution (buy/sell), account equity, position management

Flow:
1. Connect to IB Gateway (data) + Alpaca (execution)
2. Run pre-market scanner (ibkr_scanner.scan_premarket_live)
3. Subscribe to top candidates (IBKR reqMktData)
4. Build 1-min + 10-sec bars from IBKR tick updates
5. Feed bars to squeeze_detector / micro_pullback
6. On signal: place order via ALPACA
7. Manage exits via Alpaca orders, driven by IBKR tick data
8. Scanner runs continuously during all trading windows
9. Two sessions: morning (7:00-12:00 ET) + evening (16:00-20:00 ET)
10. Sleeps during dead zone (12:00-16:00), shuts down after last window
"""

from __future__ import annotations

import os
# L2 Layer 1 P1.1 — per-process L2 clientId so all 4 bots can run L2
# concurrently without collision. Setup A main = 42. Set BEFORE l2_helper
# is imported (lazy import inside the gate, runs after this line).
os.environ.setdefault("WB_L2_CLIENT_ID", "42")
import sys
import time
import math
import json
import gzip
import threading
import queue
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone, time as time_cls
from collections import deque

import pytz
from dotenv import load_dotenv
from ib_insync import IB, Stock, LimitOrder, MarketOrder, util
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

from broker import (
    make_broker, BrokerOrder, BrokerPosition,
    STATUS_SUBMITTED, STATUS_PARTIALLY, STATUS_FILLED,
    STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED, STATUS_UNKNOWN,
    TERMINAL_STATUSES,
)

# Load .env if present (same as simulate.py — ensures env vars are set)
load_dotenv()

if os.getenv("WB_SQUEEZE_VERSION", "1") == "2":
    from squeeze_detector_v2 import SqueezeDetectorV2 as SqueezeDetector
else:
    from squeeze_detector import SqueezeDetector
from micro_pullback import MicroPullbackDetector
from continuation_detector import ContinuationDetector
from ibkr_scanner import scan_premarket_live, scan_catchup, rank_score
from bars import TradeBarBuilder, Bar
from candles import is_bearish_engulfing
from patterns import PatternDetector
from epl_framework import (
    EPL_ENABLED, EPL_MAX_NOTIONAL, EPL_MIN_GRADUATION_R,
    GraduationContext, EPLWatchlist, StrategyRegistry, PositionArbitrator,
)
from epl_mp_reentry import EPLMPReentry, EPL_MP_ENABLED
from subscription_watchdog import SubscriptionWatchdog
import session_state as ss

ET = pytz.timezone("US/Eastern")

# Box strategy (conditional import — gated by WB_BOX_ENABLED)
BOX_ENABLED = os.getenv("WB_BOX_ENABLED", "0") == "1"
BOX_SIMULTANEOUS = os.getenv("WB_BOX_SIMULTANEOUS", "0") == "1"
if BOX_ENABLED:
    from box_scanner import scan_box_candidates
    from box_strategy import BoxStrategyEngine

# ── Databento bridge ────────────────────────────────────────────────
WATCHLIST_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "watchlist.txt")
DATABENTO_BRIDGE = os.getenv("WB_DATABENTO_BRIDGE_ENABLED", "1") == "1"

# Hypothesis #17 — fresh watchlist on cold start (2026-05-13).
# When live_scanner crashes (e.g. Databento 402 on 2026-05-13), the
# un-dated watchlist.txt is never rewritten, so a cold-start bot would
# inherit yesterday's symbols (KBSX, CLNN, FATN, SST, NVOX, ATRA, TRAW,
# ENSC, ODYS) and trade them without scanner validation. Today's ENSC
# at $0.30 was the canonical case. Fix: on cold boot, refuse to read
# watchlist.txt if its mtime is not today's date — wait for the scanner
# to write a fresh one. Resume boots are unchanged (durable session_state
# is rehydrated separately by resume_reconcile).
# Default-ON for safety. Flip to 0 to revert to inheritance behavior.
WB_FRESH_WATCHLIST_ON_COLD_START = os.getenv(
    "WB_FRESH_WATCHLIST_ON_COLD_START", "1") == "1"

# ── Strategy gates ───────────────────────────────────────────────────
SQ_ENABLED = os.getenv("WB_SQUEEZE_ENABLED", "0") == "1"
MP_ENABLED = os.getenv("WB_MP_ENABLED", "0") == "1"
MP_V2_ENABLED = os.getenv("WB_MP_V2_ENABLED", "0") == "1"
CT_ENABLED = os.getenv("WB_CT_ENABLED", "0") == "1"

# Wave Breakout (Stage 3 — DIRECTIVE_WAVE_BREAKOUT_STAGE3_BUILD.md).
# Default OFF; flip to 1 only after Phase 1 paper passes. WaveBreakout fires
# parallel to squeeze, never replacing.
WAVE_BREAKOUT_ENABLED = os.getenv("WB_WAVE_BREAKOUT_ENABLED", "0") == "1"
WB_MAX_CONCURRENT = int(os.getenv("WB_WB_MAX_CONCURRENT", "3"))
if WAVE_BREAKOUT_ENABLED:
    from wave_breakout_detector import WaveBreakoutDetector, WaveBreakoutConfig

# Move-stack (main-bot rebuild R1 — see cowork_reports/2026-06-08_main_bot_rebuild_directive.md).
# Ports the proven sub-bot strategy stack (MovementStrike + RegimeShift + FirestormTrigger)
# into the main bot. Gated OFF by default: when off, the import graph and runtime behavior
# are identical to the current squeeze build, so the squeeze path remains the safe fallback.
MOVE_STACK_ENABLED = os.getenv("WB_MOVE_STACK_ENABLED", "0") == "1"
if MOVE_STACK_ENABLED:
    from movement_strike import MovementStrike
    from firestorm_trigger import FirestormTrigger
    # RegimeShiftDetector currently lives in move_strike_subbot.py (clean __main__
    # guard, no import side effects). TODO(rebuild cleanup): extract to its own module.
    from move_strike_subbot import RegimeShiftDetector
    # Track A entry-side R-floor + exit-side helpers (all self-gated on
    # WB_EXIT_TRACK_A_ENABLED). R3 exit path.
    from exit_track_a import (
        compute_stop_with_r_floor, track_a_enabled,
        phased_drawdown_threshold, should_force_flatten,
    )
    # HWM runner trail (read-only, dict-compatible — pass the position dict directly).
    from hwm_exit import HWMExitConfig, evaluate as hwm_evaluate
    _MOVE_HWM_CFG = HWMExitConfig()
else:
    _MOVE_HWM_CFG = None

# Move-stack entry config (R2, ported from move_strike_subbot). Read unconditionally
# (cheap) but only consulted on the MOVE_STACK_ENABLED entry path.
MOVE_FIRESTORM_GATE_ENABLED = os.getenv("WB_MOVE_FIRESTORM_GATE_ENABLED", "0") == "1"
MOVE_FIRESTORM_MIN_TICKS = int(os.getenv("WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN", "6000"))
MOVE_CHASE_CAP_PCT = float(os.getenv("WB_BT_MOVE_CHASE_PCT", "2.0"))
MOVE_MAX_BELOW_ARM_PCT = float(os.getenv("WB_BT_MOVE_MAX_BELOW_ARM_PCT", "0"))
MOVE_REGIME_REQUIRE_ARMED = os.getenv("WB_REGIME_SHIFT_REQUIRE_ARMED", "1") == "1"
MOVE_REGIME_MAX_PER_SYMBOL = int(os.getenv("WB_REGIME_SHIFT_MAX_PER_SYMBOL", "1"))
MOVE_REGIME_TARGET_R = float(os.getenv("WB_REGIME_SHIFT_TARGET_R", "1.5"))
MOVE_REGIME_PARTIAL_PCT = float(os.getenv("WB_REGIME_SHIFT_PARTIAL_PCT", "0.9"))
# REENTRY-loss gate (R4, Variant C): block re-entry within N min of a loss-class exit.
MOVE_REENTRY_LOSS_GATE_ENABLED = os.getenv("WB_MOVE_REENTRY_LOSS_GATE_ENABLED", "0") == "1"
MOVE_REENTRY_LOSS_GATE_WINDOW_MIN = float(os.getenv("WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN", "30"))
_MOVE_LOSS_EXIT_PREFIXES = ("move_hwm_exit", "move_stop_prox_bail", "move_hard_stop",
                            "regime_shift_hard_stop", "regime_shift_drawdown_floor")
# Halt-count entry gate (R4 addendum, 2026-06-09): block serially-halted names.
# Observe-only by default (logs would-block, doesn't block). See
# cowork_reports/2026-06-09_rebuild_addendum_halt_gate.md.
MOVE_HALT_COUNT_GATE_ENABLED = os.getenv("WB_MOVE_HALT_COUNT_GATE_ENABLED", "0") == "1"
MOVE_HALT_COUNT_GATE_THRESHOLD = int(os.getenv("WB_MOVE_HALT_COUNT_GATE_THRESHOLD", "3"))
MOVE_HALT_COUNT_GATE_OBSERVE_ONLY = os.getenv("WB_MOVE_HALT_COUNT_GATE_OBSERVE_ONLY", "1") == "1"

# Engine publisher (2026-05-20). Optional tick broadcaster — when enabled
# via WB_ENGINE_PUBLISH_ENABLED=1, each processed tick is also sent over
# a Unix socket to subscriber bots (e.g., move_strike_subbot.py running
# an alternate strategy on the same tick stream). When disabled
# (default), this is a no-op — bit-identical to no-publish behavior.
# No strategy logic is affected.
from engine_publisher import get_publisher
_engine_pub = get_publisher()

# Tick-By-Tick migration (DIRECTIVE_TICKBYTICK_MIGRATION.md).
# Stage 1 probe (2026-05-05): account capacity = 5 simultaneous
# reqTickByTickData('AllLast') subscriptions. Override via WB_TBT_MAX if a
# future probe finds a higher cap. WB_TBT_ENABLED master gate is OFF until
# Stage 3 promotion logic ships — Stage 2 alone is dormant infrastructure.
TBT_ENABLED = os.getenv("WB_TBT_ENABLED", "0") == "1"
TBT_MAX_SUBSCRIPTIONS = int(os.getenv("WB_TBT_MAX", "5"))
# Stage 3 — promotion/demotion policy.
TBT_MANAGE_INTERVAL_SEC = int(os.getenv("WB_TBT_MANAGE_SEC", "30"))   # how often to re-rank
# Lever 3 (2026-05-26): periodic broker reconciliation cadence.
RECONCILE_INTERVAL_SEC = int(os.getenv("WB_RECONCILE_INTERVAL_SEC", "60"))
# Orphan-halt ignore-list (P0, 2026-06-10). Symbols here are detected but NOT adopted
# and NOT halted on — the bot keeps trading everything else and leaves the position at
# the broker for manual handling. For stuck/untradeable orphans (e.g. sub-$1 penny names
# whose orders IBKR's price-cap refuses) that would otherwise lock the whole bot out.
# The orphan-halt safety stays fully in force for every OTHER symbol. Comma-separated.
ORPHAN_HALT_IGNORE_SYMBOLS = {
    s.strip().upper() for s in os.getenv("WB_ORPHAN_HALT_IGNORE_SYMBOLS", "").split(",") if s.strip()
}
TBT_COOLDOWN_SEC = int(os.getenv("WB_TBT_COOLDOWN_SEC", "300"))        # min Tier-1 hold time
# How often to republish the subscription frame so the engine's session
# HOD/LOD in the cached snapshot stay fresh for the manual bot (incl. the
# frame re-sent to a reconnecting client). The publisher de-dups, so a
# republish only emits a frame when the rounded HOD/LOD actually moved.
LEVELS_PUBLISH_INTERVAL_SEC = int(os.getenv("WB_ENGINE_LEVELS_PUBLISH_SEC", "20"))
TBT_VOLUME_RESERVE_N = max(1, TBT_MAX_SUBSCRIPTIONS // 2)              # "active hunt" reserve
# Priority weights — see DIRECTIVE_TICKBYTICK_MIGRATION.md.
TBT_PRI_OPEN_POSITION = 1000
TBT_PRI_ARMED = 500
TBT_PRI_PRIMED = 200
TBT_PRI_WB_OBS_MED = 50          # WAVE_OBSERVING (any). The directive distinguishes
                                  # ≥5 vs ≥7 by score, but the WB detector doesn't expose
                                  # last-wave score; flat 50 captures the intent.
TBT_PRI_VOLUME_FLOOR = 20
TBT_PRI_VOLUME_CEIL = 50

# ── Price-momentum Tier-1 promotion (2026-07-22) ───────────────────────
# Fixes the deadlock exposed by LABT 2026-07-22: it ran +301% ($1.74→$6.98)
# in 2m32s and the engine left it in the SNAPSHOT tier for 40 minutes with
# THREE free tier1 slots (tier1=['INM','SXTC'], capacity 2/5), promoting it
# only at 08:45 — long after the move. Root cause: every existing promotion
# signal is derived from RECEIVED TICKS — detector state needs ticks to arm,
# and _compute_5m_volume_rank sums bar.volume which is ~0 for a snapshot
# symbol. So a symbol with no tick-by-tick data can never generate the signal
# that would earn it tick-by-tick data. Deadlock.
#
# Price (HOD/LOD/last) IS delivered at snapshot resolution — LABT's snapshot
# HOD visibly climbed 5.00→6.18→6.47. So promote on price action, which needs
# no prior full-tick stream. LOD is seeded from full-day history on subscribe
# (seed_session_extremes), so gain-from-LOD reflects the true low.
#
# Gated OFF by default per CLAUDE.md. Priority band sits above the volume
# reserve (grabs a free slot, as LABT had) but below PRIMED (won't evict a
# real squeeze setup) — the conservative fix for the actual failure.
TBT_MOMENTUM_ENABLED = os.getenv("WB_TBT_MOMENTUM_ENABLED", "0") == "1"
TBT_MOMENTUM_MIN_PCT = float(os.getenv("WB_TBT_MOMENTUM_MIN_PCT", "30"))       # min gain from LOD to qualify
TBT_MOMENTUM_FULL_PCT = float(os.getenv("WB_TBT_MOMENTUM_FULL_PCT", "100"))    # gain at which priority maxes
TBT_MOMENTUM_MIN_RANGE_POS = float(os.getenv("WB_TBT_MOMENTUM_MIN_RANGE_POS", "0.25"))  # reject a fully round-tripped/crashed spike (2026-07-27: was 0.5, missed VEEE/DFNS that faded to mid-range)
TBT_PRI_MOMENTUM_FLOOR = 60      # just above the volume ceiling (50)
TBT_PRI_MOMENTUM_CEIL = 190      # just below PRIMED (200)

# ── Scanner-wedge self-recovery (2026-07-23) ───────────────────────────
# On 2026-07-23 the IBKR scanner wedged at the 04:00 cron start: the very
# first reqScannerData failed with Error 162 ("API scanner subscription
# cancelled") and EVERY subsequent 5-min scan inherited the stuck state —
# 25 scans, 0 candidates, for 5.5 hours. Empty watchlist → "no symbols" →
# no subscriptions → no ticks → no trading, all morning. Only a full process
# restart (fresh IBKR connection) cleared it.
#
# Recovery: if consecutive scans return 0 candidates AND Error 162 fired this
# scan (the wedge signature — distinct from a genuinely quiet premarket, which
# has 0 candidates but NO 162s), exit(1) so the supervisor's
# WB_MAIN_BOT_AUTORESTART restarts us with a fresh connection. Once ANY symbol
# is subscribed active_symbols stays >0 for the session, so this can only fire
# at startup — it cannot churn a healthy mid-session engine. The supervisor's
# 10-restart cap is the backstop against an IBKR-side outage that a restart
# can't fix.
SCANNER_WEDGE_RECOVERY = os.getenv("WB_SCANNER_WEDGE_RECOVERY", "1") == "1"
SCANNER_WEDGE_MAX = int(os.getenv("WB_SCANNER_WEDGE_MAX", "3"))  # consecutive empty+162 scans before exit

# Short strategy (prototyped 2026-04-16 from DIRECTIVE_SHORT_STRATEGY_RESEARCH).
# Default B — Lower-High Short — won head-to-head against A/C in backtests
# (88% WR, +$3,241, +0.39R avg on the in-universe 8 stocks). A and C are
# selectable for experimentation but B is the shipping variant.
SHORT_ENABLED = os.getenv("WB_SHORT_ENABLED", "0") == "1"
SHORT_STRATEGY = os.getenv("WB_SHORT_STRATEGY", "B").upper()
SHORT_TIME_STOP_MIN = float(os.getenv("WB_SHORT_TIME_STOP_MIN", "60"))
if SHORT_ENABLED:
    from short_detector import make_short_detector

# Broker backend (Phase 1 of Alpaca→IBKR execution migration).
# "alpaca" = legacy path (default), "ibkr" = new event-driven path.
# All order flow in this file goes through state.broker — never state.alpaca.
BROKER_BACKEND = os.getenv("WB_BROKER", "alpaca").lower()


def _assert_broker_matches() -> None:
    """Runtime broker-mismatch assert (2026-05-18 — Patch 4 of bundled deploy).

    Defends against the SBFM-class config drift where .env says one broker
    and daily_run_v3.sh injects another (or vice versa). When
    WB_EXPECTED_BROKER is set and doesn't match the runtime WB_BROKER, fail
    loud at boot rather than silently route orders to the wrong account.
    Unset WB_EXPECTED_BROKER = silently allow (no regression for older
    invocation paths).
    """
    expected = os.getenv("WB_EXPECTED_BROKER", "").lower().strip()
    actual = os.getenv("WB_BROKER", "").lower().strip() or BROKER_BACKEND
    if expected and expected != actual:
        print(
            f"  ❌ BROKER_MISMATCH: WB_BROKER={actual} but "
            f"WB_EXPECTED_BROKER={expected} — refusing to start. "
            f"Check daily_run_v3.sh injection vs .env vs WB_EXPECTED_BROKER.",
            flush=True,
        )
        sys.exit(1)

# ── IBKR connection ──────────────────────────────────────────────────
IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))  # 4002 = Gateway paper
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "1"))

# ── Risk ─────────────────────────────────────────────────────────────
STARTING_EQUITY = float(os.getenv("WB_STARTING_EQUITY", "30000"))
RISK_PCT = float(os.getenv("WB_RISK_PCT", "0.025"))  # 2.5% of equity per trade
MAX_NOTIONAL = float(os.getenv("WB_MAX_NOTIONAL", "100000"))
MAX_SHARES = int(os.getenv("WB_MAX_SHARES", "100000"))
SCALE_NOTIONAL = os.getenv("WB_SCALE_NOTIONAL", "0") == "1"
BUYING_POWER_PCT = float(os.getenv("WB_BUYING_POWER_PCT", "0.50"))
MIN_R = float(os.getenv("WB_MIN_R", "0.06"))
# Absolute R-distance floor (2026-05-18 — Cowork r_floor_gate_design).
# Hard rule: entry → stop must be at least $X. Default 0.10 = a dime,
# comfortably above typical $0.01-0.05 bid-ask noise on $2-20 stocks.
# Combines with MIN_R via max(); set 0.0 to disable.
MIN_ABSOLUTE_R = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))

# PDT protection — limit entries per day to conserve day-trade slots.
# Under $25K equity: 3 day trades per 5 rolling business days. Setting
# MAX_DAILY_ENTRIES=1 keeps us safe. 0 = unlimited (paper mode default).
MAX_DAILY_ENTRIES = int(os.getenv("WB_MAX_DAILY_ENTRIES", "0"))

# Entry slippage + retry (added 2026-04-15 — was hardcoded $0.02 + single-shot)
# Dynamic slippage: max(SLIPPAGE_MIN, price * SLIPPAGE_PCT). If initial limit
# times out, cancel + re-read live price + re-submit at (current + slippage),
# up to MAX_RETRIES times. Gives up if market runs past MAX_CHASE_PCT above
# original limit (stops unbounded chasing on vertical moves).
ENTRY_SLIPPAGE_MIN = float(os.getenv("WB_ENTRY_SLIPPAGE_MIN", "0.05"))
ENTRY_SLIPPAGE_PCT = float(os.getenv("WB_ENTRY_SLIPPAGE_PCT", "0.005"))  # 0.5% of price
ENTRY_MAX_RETRIES = int(os.getenv("WB_ENTRY_MAX_RETRIES", "3"))
ENTRY_RETRY_TIMEOUT_SEC = int(os.getenv("WB_ENTRY_RETRY_TIMEOUT_SEC", "10"))
ENTRY_MAX_CHASE_PCT = float(os.getenv("WB_ENTRY_MAX_CHASE_PCT", "2.0"))  # legacy / fallback cap
# Score-gated chase cap (Cowork directive 2026-05-14_SQUEEZE_FILL_RATE_FIX §2):
# high-conviction signals (score >= threshold) get a wider cap, low-score keep
# the legacy 2.0%. Default thresholds are the directive's recommended values.
ENTRY_SCORE_HIGH_THRESHOLD = float(os.getenv("WB_ENTRY_SCORE_HIGH_THRESHOLD", "11"))
ENTRY_MAX_CHASE_PCT_HIGH = float(os.getenv("WB_ENTRY_MAX_CHASE_PCT_HIGH", "3.5"))
ENTRY_MAX_CHASE_PCT_LOW = float(os.getenv("WB_ENTRY_MAX_CHASE_PCT_LOW", "2.0"))
# Entry time cutoff (user directive 2026-05-14 — FCHL filled 90s before 20:00 ET
# extended-hours close, no time for bot to manage). Format: HH:MM ET.
ENTRY_TIME_CUTOFF_ET = os.getenv("WB_ENTRY_TIME_CUTOFF_ET", "19:30")
# Pre-submit buying-power check (Cowork directive #3): block BUY submits when
# available BP < required init margin. Prevents Reg-T rejection class (ATRA 5/7).
PRESUBMIT_BP_CHECK_ENABLED = os.getenv("WB_PRESUBMIT_BP_CHECK_ENABLED", "1") == "1"
ENTRY_RETRY_ENABLED = os.getenv("WB_ENTRY_RETRY_ENABLED", "1") == "1"
# Partial-fill reconciliation (2026-06-17). The entry-retry loop only reacted to
# STATUS_FILLED / cancel-reject; STATUS_PARTIALLY was ignored, and each retry
# resubmitted the FULL qty (not the remainder). On a fast mover, partial fills
# across retries accumulated at the broker unrecorded → re-detected as orphans
# and adopted at a bad basis (CRVO 2026-06-16: -$1,257). When ON: every retry
# sizes to the REMAINDER (qty - broker_held), and every entry-sequence terminal
# reconciles the bot's position to the broker's actual holding (keep + manage
# whatever filled; clear only if truly flat). See
# memory/project_main_bot_entry_fill_desync_orphan.
ENTRY_RECONCILE_FILLS = os.getenv("WB_ENTRY_RECONCILE_FILLS", "1") == "1"

# Strategy filters ported from the sub-bots (2026-06-17 plan). All OFF by
# default; enabled via the main-bot launch env in daily_run_v3.sh.
#   WB_EQUITY_PCT:  0 = off (existing risk/notional sizing). e.g. 0.70 → each
#                   move-stack entry is 70% of current equity (STARTING_EQUITY +
#                   daily_pnl), no leverage.
#   WB_ENTRY_BLOCK_WINDOWS_ET: comma list of HH:MM-HH:MM ET windows to BLOCK new
#                   entries (e.g. "09:30-11:00,13:00-14:00" — open chop + 1pm dead
#                   hour where losses cluster). "" = off. (Same var the sub-bots use.)
#   WB_SYMBOL_LOSS_LOCKOUT: 1 = once a symbol takes a net LOSS today, block all
#                   further entries on it that day (kills revenge re-entries; keeps
#                   win-continuations). Full-day; in-memory (resets on restart).
EQUITY_PCT_SIZING = float(os.getenv("WB_EQUITY_PCT", "0"))
SYMBOL_LOSS_LOCKOUT = os.getenv("WB_SYMBOL_LOSS_LOCKOUT", "0") == "1"
ENTRY_BLOCK_WINDOWS = []  # [(start_min_et, end_min_et), ...]
for _w in os.getenv("WB_ENTRY_BLOCK_WINDOWS_ET", "").strip().split(","):
    _w = _w.strip()
    if not _w or "-" not in _w:
        continue
    try:
        _a, _b = _w.split("-")
        _ah, _am = (int(x) for x in _a.split(":"))
        _bh, _bm = (int(x) for x in _b.split(":"))
        ENTRY_BLOCK_WINDOWS.append((_ah * 60 + _am, _bh * 60 + _bm))
    except Exception:
        print(f"[FILTERS] bad WB_ENTRY_BLOCK_WINDOWS_ET segment: {_w!r}", flush=True)


def _strategy_filters_block(symbol: str, setup_type: str) -> bool:
    """Time-window block + per-symbol same-day loss-lockout (sub-bot parity).
    Return True to block this move-stack entry. Both gated; no-op unless enabled."""
    if ENTRY_BLOCK_WINDOWS:
        # Gate on ARM time, not entry time (sub-bot parity, Manny 2026-06-22):
        # a setup armed in a valid window may still trigger inside a blocked
        # window; only setups that ARMED in-window are blocked. Fall back to
        # current time if no arm stamp.
        arm_m = getattr(state, "_arm_minute_et", {}).get(symbol)
        if arm_m is not None:
            m = arm_m
            src = "armed_at"
        else:
            now = datetime.now(ET)
            m = now.hour * 60 + now.minute
            src = "now"
        for s, e in ENTRY_BLOCK_WINDOWS:
            if s <= m < e:
                print(f"  TIME_WINDOW_BLOCK: {symbol} {setup_type} ({src}={m} in {s}-{e})",
                      flush=True)
                return True
    if SYMBOL_LOSS_LOCKOUT and symbol in getattr(state, "_lossout_symbols", ()):
        print(f"  LOSS_LOCKOUT_BLOCK: {symbol} {setup_type} (symbol already lost today)",
              flush=True)
        return True
    return False

# Exit-side slippage budget. Exits use SELL LIMITs (per project rule: never
# market orders, never broker-side stops). Limit price = current_price -
# max(EXIT_SLIPPAGE_MIN, current_price * EXIT_SLIPPAGE_PCT). On a BUY-to-
# cover the buffer is added instead of subtracted.
EXIT_SLIPPAGE_MIN = float(os.getenv("WB_EXIT_SLIPPAGE_MIN", "0.05"))
EXIT_SLIPPAGE_PCT = float(os.getenv("WB_EXIT_SLIPPAGE_PCT", "0.005"))

# Alpaca latency diagnostic (deployed 2026-05-11, see DIRECTIVE_ALPACA_LATENCY_DIAGNOSTIC.md)
# Captures per-squeeze-signal Alpaca-vs-IBKR quote/timestamp/price snapshots and
# round-trip submit/ack latency, writes JSONL records to logs/<date>_latency_diagnostic.jsonl.
# Pure read-only logging — failures in diagnostic code MUST NOT block any order from
# being placed (every callsite is wrapped in try/except). Squeeze entries ONLY.
LATENCY_DIAGNOSTIC_ENABLED = os.getenv("WB_LATENCY_DIAGNOSTIC_ENABLED", "1") == "1"

# Alpaca-aware limit pricing (DORMANT — Phase 3 of latency directive, gated OFF).
# When the diagnostic identifies Outcome B (consistent meaningful latency), flip
# WB_ALPACA_AWARE_LIMITS=1 and wire compute_alpaca_aware_limit() into the entry
# path. The helper itself exists in this file so Friday's activation is a single
# env-var flip — it is currently NOT wired into any caller.
ALPACA_AWARE_LIMITS_ENABLED = os.getenv("WB_ALPACA_AWARE_LIMITS", "0") == "1"


def _entry_slippage_for(price: float) -> float:
    """Dynamic slippage: max(MIN, price * PCT). Matches manual bot pattern."""
    return max(ENTRY_SLIPPAGE_MIN, price * ENTRY_SLIPPAGE_PCT)


def _exit_limit_price(price: float, side: str) -> float:
    """Slippage-buffered limit for exits. SELL → below current price, BUY-to-
    cover → above. The bot never submits market orders on exits (per project
    rule); when an internal stop fires we accept up to this slippage to ensure
    fill but never accept a totally unbounded one."""
    buffer = max(EXIT_SLIPPAGE_MIN, price * EXIT_SLIPPAGE_PCT)
    if side.upper() == "SELL":
        return round(price - buffer, 2)
    return round(price + buffer, 2)

# Session resume (2026-04-15 — see cowork_reports/2026-04-15_greenlight_session_resume.md)
# WB_TICK_FLUSH_ENABLED: always-on crash-safety for the tick cache (independent
#   of resume). Flushes state.tick_buffer to tick_cache/ every WB_SESSION_FLUSH_SEC.
# WB_SESSION_RESUME_ENABLED: gates the resume-mode boot path only. When 0, the
#   bot still writes durable state files (so a subsequent enabled run can resume),
#   but always does a cold start itself.
TICK_FLUSH_ENABLED = os.getenv("WB_TICK_FLUSH_ENABLED", "1") == "1"
SESSION_FLUSH_SEC = int(os.getenv("WB_SESSION_FLUSH_SEC", "30"))
SESSION_RESUME_ENABLED = os.getenv("WB_SESSION_RESUME_ENABLED", "0") == "1"

# Lock serializing tick_buffer mutations between the IBKR tick callback
# thread and the periodic flush swap. Acquisition is microseconds; contention
# is negligible (one swap per SESSION_FLUSH_SEC vs thousands of appends).
_tick_buffer_lock = threading.Lock()
MAX_DAILY_LOSS = float(os.getenv("WB_MAX_DAILY_LOSS", "3000"))
DAILY_LOSS_SCALE = os.getenv("WB_DAILY_LOSS_SCALE", "0") == "1"
MAX_CONSECUTIVE_LOSSES = int(os.getenv("WB_MAX_CONSECUTIVE_LOSSES", "3"))
BAIL_TIMER_ENABLED = os.getenv("WB_BAIL_TIMER_ENABLED", "1") == "1"
BAIL_TIMER_MINUTES = float(os.getenv("WB_BAIL_TIMER_MINUTES", "5"))

# ── Squeeze exit params ──────────────────────────────────────────────
SQ_TARGET_R = float(os.getenv("WB_SQ_TARGET_R", "2.0"))
SQ_TRAIL_R = float(os.getenv("WB_SQ_TRAIL_R", "1.5"))
SQ_PARA_TRAIL_R = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
SQ_RUNNER_TRAIL_R = float(os.getenv("WB_SQ_RUNNER_TRAIL_R", "2.5"))
SQ_MAX_LOSS_DOLLARS = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
SQ_CORE_PCT = int(os.getenv("WB_SQ_CORE_PCT", "75"))

# ── Candle-based exit params (parity with simulate.py) ──────────────
SQ_CANDLE_EXITS_ENABLED = os.getenv("WB_SQ_CANDLE_EXITS_ENABLED", "1") == "1"
EXIT_ON_TOPPING_WICKY = os.getenv("WB_EXIT_ON_TOPPING_WICKY", "1") == "1"
EXIT_ON_BEAR_ENGULF = os.getenv("WB_EXIT_ON_BEAR_ENGULF", "1") == "1"
TW_GRACE_MIN = int(os.getenv("WB_TOPPING_WICKY_GRACE_MIN", "3"))
TW_MIN_PROFIT_R = float(os.getenv("WB_TW_MIN_PROFIT_R", "1.5"))
BE_GRACE_MIN = int(os.getenv("WB_BE_GRACE_MIN", "0"))
BE_MIN_PROFIT_R = float(os.getenv("WB_BE_MIN_PROFIT_R", "0.5"))
BE_PARABOLIC_GRACE = os.getenv("WB_BE_PARABOLIC_GRACE", "1") == "1"
BE_GRACE_MIN_R = float(os.getenv("WB_BE_GRACE_MIN_R", "1.0"))
BE_GRACE_MIN_NEW_HIGHS = int(os.getenv("WB_BE_GRACE_MIN_NEW_HIGHS", "3"))
BE_GRACE_LOOKBACK = int(os.getenv("WB_BE_GRACE_LOOKBACK_BARS", "6"))

# ── Trading windows (ET) ─────────────────────────────────────────────
# Two sessions: morning and evening, with a dead zone 12:00-16:00.
# Format: comma-separated "HH:MM-HH:MM" windows.
TRADING_WINDOWS_STR = os.getenv("WB_TRADING_WINDOWS", "07:00-12:00,16:00-20:00")
TRADING_WINDOWS = []
for _w in TRADING_WINDOWS_STR.split(","):
    _parts = _w.strip().split("-")
    if len(_parts) == 2:
        _s = time_cls(int(_parts[0].split(":")[0]), int(_parts[0].split(":")[1]))
        _e = time_cls(int(_parts[1].split(":")[0]), int(_parts[1].split(":")[1]))
        TRADING_WINDOWS.append((_s, _e))

def in_trading_window(now_et: datetime) -> bool:
    """Check if current time falls within any trading window."""
    t = now_et.time()
    return any(start <= t < end for start, end in TRADING_WINDOWS)

def past_all_windows(now_et: datetime) -> bool:
    """Check if we're past the last trading window for the day."""
    t = now_et.time()
    if not TRADING_WINDOWS:
        return True
    last_end = max(end for _, end in TRADING_WINDOWS)
    # If box is enabled, also need to be past box window
    if BOX_ENABLED:
        last_end = max(last_end, BOX_WINDOW_END)
    return t >= last_end

# ── Box trading windows ─────────────────────────────────────────────
BOX_WINDOW_START = time_cls(int(os.getenv("WB_BOX_START_ET", "10:00").split(":")[0]),
                            int(os.getenv("WB_BOX_START_ET", "10:00").split(":")[1]))
BOX_WINDOW_END = time_cls(int(os.getenv("WB_BOX_HARD_CLOSE_ET", "15:45").split(":")[0]),
                          int(os.getenv("WB_BOX_HARD_CLOSE_ET", "15:45").split(":")[1]))
BOX_LAST_ENTRY = time_cls(int(os.getenv("WB_BOX_LAST_ENTRY_ET", "14:30").split(":")[0]),
                          int(os.getenv("WB_BOX_LAST_ENTRY_ET", "14:30").split(":")[1]))
BOX_SKIP_FRIDAY = os.getenv("WB_BOX_SKIP_FRIDAY", "1") == "1"
BOX_MAX_LOSS_SESSION = float(os.getenv("WB_BOX_MAX_LOSS_SESSION", "500"))
BOX_SCAN_CHECKPOINTS = [time_cls(10, 0), time_cls(11, 0)]

# Vol Sweet Spot filter thresholds (from Phase 2B)
BOX_FILTER_MIN_RANGE_PCT = float(os.getenv("WB_BOX_MIN_RANGE_PCT", "2.0"))
BOX_FILTER_MAX_RANGE_PCT = float(os.getenv("WB_BOX_MAX_RANGE_PCT", "6.0"))
BOX_FILTER_MIN_TOTAL_TESTS = int(os.getenv("WB_BOX_MIN_TOTAL_TESTS", "5"))
BOX_FILTER_MIN_PRICE = float(os.getenv("WB_BOX_MIN_PRICE", "15.0"))
BOX_FILTER_MAX_ADR_UTIL = float(os.getenv("WB_BOX_MAX_ADR_UTIL", "0.80"))

def in_box_window(now_et: datetime) -> bool:
    """True if box is enabled and we're in the box window."""
    if not BOX_ENABLED:
        return False
    t = now_et.time()
    return BOX_WINDOW_START <= t <= BOX_WINDOW_END

def in_any_active_window(now_et: datetime) -> bool:
    """True if either momentum or box is active."""
    return in_trading_window(now_et) or in_box_window(now_et)


# ══════════════════════════════════════════════════════════════════════
# State
# ══════════════════════════════════════════════════════════════════════

class BotState:
    """Holds all mutable bot state."""
    def __init__(self):
        self.ib: IB = None
        self.alpaca: TradingClient = None  # raw client, owned by AlpacaBroker; callers use state.broker
        self.broker = None  # BrokerClient — routes all execution. Initialized in main() after connect().
        # Alpaca data REST client — owned by main(). Used for latency diagnostic
        # snapshots (Phase 1) and the dormant compute_alpaca_aware_limit() helper
        # (Phase 3). None until main() initializes it; callers must null-check.
        self.alpaca_data_client = None
        self.active_symbols: set[str] = set()
        self.contracts: dict[str, Stock] = {}
        self.tickers: dict = {}

        # Detectors
        self.sq_detectors: dict[str, SqueezeDetector] = {}
        self.mp_detectors: dict[str, MicroPullbackDetector] = {}
        self.ct_detectors: dict[str, ContinuationDetector] = {}

        # Move-stack detectors (main-bot rebuild R1). Per-symbol, populated only
        # when WB_MOVE_STACK_ENABLED=1. FirestormTrigger stays gated off (entry
        # signal not active live yet — the FIRESTORM *gate* is a separate quiet-bar
        # filter applied in the entry path, not a detector here).
        self.move_strikes: dict = {}             # symbol → MovementStrike
        self.regime_shift_detectors: dict = {}   # symbol → RegimeShiftDetector
        self.firestorm_triggers: dict = {}       # symbol → FirestormTrigger (gated off)
        # Tracks the squeeze arm object per symbol across bars so the move-stack
        # can reset MovementStrike history on a None→armed transition (R2).
        self.move_prev_arm_state: dict = {}      # symbol → armed obj or None
        # Per-symbol ET minute the current arm fired (bar time). Time-window
        # block gates on this, not entry time, so a setup armed in a valid
        # window can still trigger inside a blocked window (sub-bot parity).
        self._arm_minute_et: dict = {}
        # RegimeShift entry bookkeeping (R2b).
        self.regime_shift_armed_today: set = set()      # symbols that armed for MOVE_STRIKE today
        self.regime_shift_entries_per_symbol: dict = {}  # symbol → regime-shift entry count
        # REENTRY-loss gate (R4): symbol → (last_exit_reason, exit_minute_et).
        self.last_exit_reason_by_symbol: dict = {}
        # Halt-count gate (R4 addendum): symbol → halts seen this session (daily-reset
        # naturally via the 2 AM cron restart).
        self.halt_count_today: dict = {}

        # Wave Breakout (parallel strategy; per-symbol detectors + per-symbol
        # positions stored separately from state.open_position so squeeze and
        # WB don't collide). WB enforces ≤ MAX_CONCURRENT positions across
        # symbols at the bot level.
        self.wb_detectors: dict = {}                # symbol → WaveBreakoutDetector
        self.wb_positions: dict = {}                # symbol → {entry, qty, stop, score, ...}
        self.wb_pending_orders: dict = {}           # symbol → order_id (entry order in flight)
        self.wb_closed_trades: list = []
        # Entry-halt safety. Set True when reconcile detects a broker position
        # the bot can't account for (orphan). Per the never-flatten rule, the
        # bot stops opening new positions until the operator clears the halt.
        self.entry_halt_active: bool = False
        self.entry_halt_reason: str = ""

        # Tick-By-Tick Migration (Stage 2 — DIRECTIVE_TICKBYTICK_MIGRATION.md).
        # Two-tier subscription model. Tier 1 = reqTickByTickData('AllLast')
        # delivering every print; capped at 5 simultaneous (probed 2026-05-05).
        # Tier 2 = reqMktData('233') 250ms snapshots — current behavior, kept
        # for all watchlist symbols as awareness layer. Symbols promote to
        # Tier 1 when active in a setup; demote when idle (Stage 3 logic).
        self.tier: dict = {}                        # symbol → "snapshot" | "tick_by_tick"
        self.tbt_tickers: dict = {}                 # symbol → ib_insync Ticker from reqTickByTickData
        self.tbt_last_processed_index: dict = {}    # symbol → last ticker.tickByTicks idx already drained
        self.tbt_subscribed_at: dict = {}           # symbol → datetime promoted (cooldown reference)
        # Stage 3 — promotion/demotion management state.
        self.last_tier1_manage = None                       # datetime of last manage_tier1 cycle
        # Lever 3 (2026-05-26) — periodic broker reconciliation last-run.
        self.last_reconcile_at = None
        self.tier1_volume_buckets: dict = {}                # symbol → list[(ts, vol)] last 5 1m bars
        self.tier1_volume_rank: dict = {}                   # symbol → 1-based rank in top-N volume reserve
        # Short strategy detector (WB_SHORT_ENABLED). Separate from long path.
        self.short_detectors: dict = {}
        self.open_short: dict = None
        self.short_closed_trades: list = []
        # Pre-peak session low per symbol, used for retrace-50 target.
        self.short_pre_peak_low: dict[str, float] = {}
        # Alpaca shortability cache — resolved once per symbol at subscribe time.
        # Only create a short detector for names in short_supported; log-skip the rest.
        self.short_supported: set = set()
        self.short_unsupported: set = set()

        # Bar builders (1m for detection, 10s for exits)
        self.bar_builder_1m: TradeBarBuilder = None
        self.bar_builder_10s: TradeBarBuilder = None

        # Position tracking
        self.open_position: dict = None  # {symbol, qty, entry, stop, r, setup_type, ...}
        self.pending_order: dict = None

        # Daily risk
        self.daily_pnl: float = 0.0
        self.daily_trades: int = 0
        self.daily_entries: int = 0  # PDT guard — counts entries, not round-trips
        self.consecutive_losses: int = 0
        self.closed_trades: list[dict] = []
        # Strategy filters (2026-06-17 plan, sub-bot parity). In-memory per day.
        self._lossout_symbols: set = set()   # symbols that took a net loss today
        self._position_daily_pnl_at_open: float = 0.0  # snapshot for position-net

        # Scanner
        self.candidates: list[dict] = []
        self.last_scan_time: datetime = None
        # Scanner-wedge self-recovery (2026-07-23): count Error 162s and
        # consecutive empty-with-162 scans. See SCANNER_WEDGE_* constants.
        self.scanner_162_count: int = 0
        self.scanner_wedge_streak: int = 0
        self.last_intraday_adder_time: datetime = None
        self.intraday_adder_poll_n: int = 0
        self.in_dead_zone: bool = False  # True while between trading windows

        # Seed completion tracking (suppress stale signals after seeding)
        self.seed_complete_time: dict[str, datetime] = {}  # symbol -> when seed finished
        self.live_tick_count_since_seed: dict[str, int] = {}  # symbol -> live ticks received post-seed

        # Tick health monitoring
        self.tick_counts: dict[str, int] = {}  # symbol -> ticks since last audit
        self.last_tick_time: dict[str, datetime] = {}  # symbol -> last tick timestamp
        self.last_tick_price: dict[str, float] = {}  # symbol -> last tick price
        self.last_nbbo: dict[str, tuple] = {}  # symbol -> (bid, ask), latest top-of-book
        self.last_tick_audit: datetime = None
        self._last_position_sync: datetime = None
        self.sub_retry_counts: dict[str, int] = {}  # symbol -> resubscription attempts
        self.last_on_ticker_fire: datetime = None  # track when on_ticker_update last fired

        # Tick recording for backtest cache
        self.tick_buffer: dict[str, list] = {}  # symbol -> [{p, s, t}, ...]

        # Session-resume (2026-04-15) — "cold" | "resume", set by main()
        # after decide_boot_mode(). Downstream code (seed_symbol, order
        # reconciliation) branches on this to skip expensive cold-start work.
        self.boot_mode: str = "cold"

        # EPL (Extended Play List) — post-2R re-entry system
        self.epl_watchlist: EPLWatchlist = None
        self.epl_registry: StrategyRegistry = None
        self.epl_arbitrator: PositionArbitrator = None

        # Candle exit state (per-symbol)
        self.pattern_dets: dict[str, PatternDetector] = {}  # symbol -> PatternDetector (10s bars)
        self.prev_10s_bar: dict[str, dict] = {}  # symbol -> {o, h, l, c}
        self.recent_10s_highs: dict[str, list] = {}  # symbol -> [highs] for BE parabolic grace

        # Box strategy state
        self.box_position: dict = None        # {symbol, qty, entry, engine, ...}
        self.box_engine: object = None        # active BoxStrategyEngine
        self.box_candidates: list = []        # filtered box scanner candidates
        self.box_active_symbol: str = None    # symbol subscribed for box
        self.box_bar_builder_1m: TradeBarBuilder = None
        self.box_daily_pnl: float = 0.0
        self.box_daily_trades: int = 0
        self.box_closed_trades: list = []
        self.last_box_scan_time: datetime = None


state = BotState()


# ══════════════════════════════════════════════════════════════════════
# Initialization
# ══════════════════════════════════════════════════════════════════════

# ── Hang protection (added 2026-04-10 after Alpaca SDK froze main thread) ──
# Alpaca SDK has no default HTTP timeout. After a network blip, a stale TCP
# socket in the keep-alive pool can cause get_all_positions() to block forever
# on _ssl__SSLSocket_read. We wrap every Alpaca call in a thread with a hard
# timeout so a hung HTTPS call can't freeze the main thread.
_alpaca_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="alpaca-call")


def _alpaca_call(fn, *args, timeout=10, **kwargs):
    """Run an Alpaca SDK call with a hard timeout. Raises TimeoutError if it hangs."""
    future = _alpaca_executor.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout)
    except FuturesTimeoutError:
        # We can't actually cancel a thread blocked on a kernel read, but we
        # don't wait for it — the next call will get a fresh worker.
        raise TimeoutError(f"Alpaca call {fn.__name__} timed out after {timeout}s")


# ── Main-thread watchdog ──
# If the main loop stops updating the heartbeat for >120s, the watchdog kills
# the bot hard. Cron/check_bot.sh will then restart it. This is the safety net
# for any hangs we don't catch with explicit timeouts.
_last_heartbeat = time.time()
_HEARTBEAT_TIMEOUT_SEC = 120


def update_heartbeat():
    global _last_heartbeat
    _last_heartbeat = time.time()


def _watchdog_loop():
    while True:
        time.sleep(15)
        elapsed = time.time() - _last_heartbeat
        if elapsed > _HEARTBEAT_TIMEOUT_SEC:
            print(f"\n💀 WATCHDOG: main thread frozen for {elapsed:.0f}s — exiting hard for restart.",
                  flush=True)
            os._exit(1)


def start_watchdog():
    t = threading.Thread(target=_watchdog_loop, daemon=True, name="watchdog")
    t.start()
    print(f"  Watchdog: armed (kills bot if main thread frozen >{_HEARTBEAT_TIMEOUT_SEC}s)",
          flush=True)


def get_account_equity() -> float:
    """Get current account equity from the broker."""
    try:
        eq = state.broker.get_account_equity()
        if eq > 0:
            return eq
    except Exception as e:
        print(f"  Failed to fetch broker account equity: {e}", flush=True)
    return STARTING_EQUITY  # Fallback


# ──────────────────────────────────────────────────────────────────────
# Wave Breakout helpers (Stage 3)
# ──────────────────────────────────────────────────────────────────────

def _wb_effective_notional_cap(current_equity: float) -> tuple[float, float, float, float]:
    """Compute the effective per-position notional cap.

    Returns (effective_cap, hard_ceiling, equity_cap, floor) so callers can
    log the reasoning. Cap = min(hard_ceiling, max(floor, equity × pct))."""
    hard_ceiling = float(os.getenv("WB_WB_MAX_NOTIONAL", "50000"))
    pct = float(os.getenv("WB_WB_NOTIONAL_PER_POSITION_PCT", "1.0"))
    floor = float(os.getenv("WB_WB_NOTIONAL_FLOOR", "10000"))
    equity_cap = current_equity * pct
    effective = min(hard_ceiling, max(floor, equity_cap))
    return (effective, hard_ceiling, equity_cap, floor)


def compute_wb_position_size(entry_price: float, stop_price: float,
                              current_equity: float) -> tuple[int, float]:
    """Equity-percent sizing with V0 hardening floors + max-notional cap.
    Mirrors squeeze sizing semantics so both strategies scale together as
    equity grows. Returns (shares, risk_dollars). (0, 0) if unsizable.

    Notional cap is min(WB_WB_MAX_NOTIONAL, max(WB_WB_NOTIONAL_FLOOR,
    equity × WB_WB_NOTIONAL_PER_POSITION_PCT))."""
    risk_pct = float(os.getenv("WB_WB_RISK_PCT", "0.025"))
    risk_floor = float(os.getenv("WB_WB_RISK_FLOOR_DOLLARS", "500"))
    risk_ceiling = float(os.getenv("WB_WB_RISK_CEILING_DOLLARS", "5000"))
    risk_dollars = max(risk_floor, min(risk_ceiling, current_equity * risk_pct))

    # V0 hardening — risk-per-share floor catches ~zero-risk edge cases
    min_risk_pct = float(os.getenv("WB_WB_MIN_RISK_PCT", "0.001"))
    min_risk_abs = float(os.getenv("WB_WB_MIN_RISK_PER_SHARE", "0.01"))
    raw_risk_per_share = entry_price - stop_price
    risk_per_share = max(raw_risk_per_share, min_risk_abs, entry_price * min_risk_pct)
    if risk_per_share <= 0 or entry_price <= 0:
        return (0, 0.0)

    shares_by_risk = int(risk_dollars / risk_per_share)
    effective_cap, _hc, _ec, _fl = _wb_effective_notional_cap(current_equity)
    shares_by_notional = int(effective_cap / entry_price)
    return (min(shares_by_risk, shares_by_notional), risk_dollars)


def _wb_active_count() -> int:
    """How many WB positions are currently open (across all symbols)?"""
    return len(state.wb_positions)


def place_wave_breakout_entry(symbol: str, msg: str) -> None:
    """Handle a "WB_ENTER: entry=X stop=Y score=Z" message from the
    detector. Computes size, checks portfolio cap, places the order."""
    if state.entry_halt_active:
        print(f"[WB] {symbol} SKIP: entry halt active ({state.entry_halt_reason})", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed("entry_halt")
        return
    # Parse the detector message
    parts = {}
    for tok in msg.replace("WB_ENTER:", "").strip().split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            parts[k] = v
    try:
        entry_price = float(parts["entry"])
        stop_price = float(parts["stop"])
        score = int(parts.get("score", 7))
    except (KeyError, ValueError) as e:
        print(f"[WB] {symbol} ENTER parse error: {e} ({msg})", flush=True)
        return

    # Symbol-uniqueness: skip if WB already has a position here, or
    # squeeze does (don't pile on top of the squeeze position).
    if symbol in state.wb_positions:
        print(f"[WB] {symbol} DEFER: already in WB position", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed("already_in_wb_position")
        return
    if state.open_position and state.open_position.get("symbol") == symbol:
        print(f"[WB] {symbol} DEFER: squeeze position already open in symbol", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed("squeeze_position_in_symbol")
        return

    # Portfolio concurrency cap
    if _wb_active_count() >= WB_MAX_CONCURRENT:
        print(f"[WB] {symbol} DEFER: portfolio cap "
              f"({_wb_active_count()}/{WB_MAX_CONCURRENT}) reached", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed("portfolio_cap")
        return

    # Size with current account equity
    equity = get_account_equity()
    shares, risk_dollars = compute_wb_position_size(entry_price, stop_price, equity)
    eff_cap, hard_ceiling, equity_cap, floor = _wb_effective_notional_cap(equity)
    print(f"[WB] {symbol} sizing: equity=${equity:,.0f} equity_cap=${equity_cap:,.0f} "
          f"floor=${floor:,.0f} ceiling=${hard_ceiling:,.0f} "
          f"effective_cap=${eff_cap:,.0f}", flush=True)
    if shares <= 0:
        print(f"[WB] {symbol} SKIP: position_size_zero "
              f"(entry={entry_price:.4f} stop={stop_price:.4f})", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed("size_zero")
        return

    notional = shares * entry_price
    print(f"[WB] {symbol} ENTER qty={shares} entry=${entry_price:.4f} "
          f"stop=${stop_price:.4f} risk=${risk_dollars:.0f} notional=${notional:,.0f} "
          f"score={score}", flush=True)

    # Place a limit-buy order with light slippage. Use the same dynamic
    # slippage policy squeeze uses: max($0.05, entry × 0.5%).
    slippage = max(ENTRY_SLIPPAGE_MIN, entry_price * ENTRY_SLIPPAGE_PCT)
    limit_price = round(entry_price + slippage, 2)
    try:
        order = state.broker.submit_limit(
            symbol, shares, "BUY", limit_price, extended_hours=True,
        )
    except Exception as e:
        print(f"[WB] {symbol} ORDER REJECT: {e}", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed(f"submit_failed:{e}")
        return

    # Track pending; on fill confirmation we transition the detector.
    state.wb_pending_orders[symbol] = {
        "order_id": order.order_id,
        "entry_price_target": entry_price,
        "stop_price": stop_price,
        "score": score,
        "shares_requested": shares,
        "placed_at": datetime.now(ET),
    }
    persist_wb_state()

    # Wait briefly for fill (mirrors squeeze pattern)
    fill_price, filled_qty = wait_for_fill(order.order_id, timeout=ENTRY_RETRY_TIMEOUT_SEC)
    if filled_qty > 0 and fill_price is not None:
        # Record position
        state.wb_positions[symbol] = {
            "symbol": symbol,
            "entry": fill_price,
            "qty": filled_qty,
            "stop": stop_price,
            "score": score,
            "risk_dollars": risk_dollars,
            "entry_time": datetime.now(ET),
            "order_id": order.order_id,
            "setup_type": "wave_breakout",
            "peak": fill_price,
            "pyramid_filled": False,
        }
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_filled(fill_price, datetime.now(timezone.utc), score=score)
        print(f"[WB] {symbol} FILL @ ${fill_price:.4f} qty={filled_qty} (R={fill_price-stop_price:.4f})",
              flush=True)
    else:
        print(f"[WB] {symbol} ENTRY TIMEOUT — no fill within "
              f"{ENTRY_RETRY_TIMEOUT_SEC}s, cancelled", flush=True)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_entry_failed("fill_timeout")
    state.wb_pending_orders.pop(symbol, None)
    persist_wb_state()


def place_wave_breakout_exit(symbol: str, msg: str) -> None:
    """Handle a "WB_EXIT: reason=R exit=P r_mult=+X.X" detector message.
    Closes the WB position with a market order."""
    pos = state.wb_positions.get(symbol)
    if pos is None:
        return  # nothing to close

    parts = {}
    for tok in msg.replace("WB_EXIT:", "").strip().split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            parts[k] = v
    reason = parts.get("reason", "unknown")
    try:
        exit_price_signal = float(parts.get("exit", "0"))
    except ValueError:
        exit_price_signal = 0.0

    qty = pos["qty"]
    # Reference price for the limit: prefer the trigger tick, fall back to the
    # position's tracked peak if the message didn't carry one.
    ref_price = exit_price_signal if exit_price_signal > 0 else float(pos.get("peak") or pos["entry"])
    base_limit = _exit_limit_price(ref_price, "SELL")
    # Alpaca-aware sell limit (2026-05-22): tighten to min(base, alpaca_bid × 0.995)
    # when WB_ALPACA_AWARE_LIMITS=1. Helps avoid sells stuck above Alpaca's bid.
    aware_limit = compute_alpaca_aware_limit(symbol, ref_price, "SELL")
    limit_price = min(aware_limit, base_limit)
    print(f"[WB] {symbol} EXIT reason={reason} signal=${exit_price_signal:.4f} "
          f"qty={qty} limit=${limit_price:.4f}", flush=True)
    try:
        sell = state.broker.submit_limit(symbol, qty, "SELL", limit_price, extended_hours=True)
    except Exception as e:
        print(f"[WB] {symbol} EXIT ORDER REJECT: {e}", flush=True)
        return

    fill_price, filled_qty = wait_for_fill(sell.order_id, timeout=15)

    # Lever 1 (2026-05-26, per 2026-05-26_sub_bot_orphan_fix_directive.md):
    # handle full vs partial vs zero fill distinctly so we never pop the
    # position while the broker still holds shares.
    if filled_qty >= qty and fill_price is not None:
        # ── CASE 1: Full fill — flatten. ───────────────────────────────
        pnl = (fill_price - pos["entry"]) * filled_qty
        r = (fill_price - pos["entry"]) / max(pos["entry"] - pos["stop"], 0.0001)
        print(f"[WB] {symbol} EXITED @ ${fill_price:.4f} pnl=${pnl:+,.2f} r_mult={r:+.2f}",
              flush=True)
        state.wb_closed_trades.append({
            "symbol": symbol, "setup_type": "wave_breakout",
            "entry": pos["entry"], "exit": fill_price, "qty": filled_qty,
            "pnl": pnl, "r_mult": r, "reason": reason,
            "entry_time": pos["entry_time"], "exit_time": datetime.now(ET),
        })
        state.wb_positions.pop(symbol, None)
        if symbol in state.wb_detectors:
            state.wb_detectors[symbol].mark_exited()
        persist_wb_state()
        return
    if filled_qty > 0 and fill_price is not None:
        # ── CASE 2: Partial fill — record realized P&L, decrement qty. ─
        pnl = (fill_price - pos["entry"]) * filled_qty
        r = (fill_price - pos["entry"]) / max(pos["entry"] - pos["stop"], 0.0001)
        state.wb_closed_trades.append({
            "symbol": symbol, "setup_type": "wave_breakout",
            "entry": pos["entry"], "exit": fill_price, "qty": filled_qty,
            "pnl": pnl, "r_mult": r, "reason": reason + "_partial",
            "entry_time": pos["entry_time"], "exit_time": datetime.now(ET),
        })
        residual = qty - filled_qty
        pos["qty"] = residual
        print(f"[WB] {symbol} EXIT PARTIAL filled={filled_qty} @ ${fill_price:.4f} "
              f"residual={residual} kept alive (pnl=${pnl:+,.2f} on filled portion)",
              flush=True)
        persist_wb_state()
        return
    # ── CASE 3: Zero fill — position untouched, retry next tick. ───────
    print(f"[WB] {symbol} EXIT NO-FILL — position alive, will retry next tick "
          f"(reason={reason} ref=${ref_price:.4f})", flush=True)
    return


# ══════════════════════════════════════════════════════════════════════
# Position Safety (Fixes 1-5 from DIRECTIVE_V3_POSITION_SYNC.md)
# ══════════════════════════════════════════════════════════════════════

def reconcile_positions_periodic():
    """Lever 3 (2026-05-26): periodic broker reconciliation.

    Compares state.open_position (and state.wb_positions) against the
    broker's truth. Handles the two divergence cases:
      1. Bot tracks position the broker doesn't have → clear local state
         (no broker exposure remains; the bot was holding a phantom).
      2. Broker has position the bot doesn't track → delegate to
         reconcile_positions_on_startup() to adopt or halt.

    Idempotent for periodic invocation: prints only when state diverges,
    not on every clean check. Gated by `state.last_reconcile_at` so it
    only runs every WB_RECONCILE_INTERVAL_SEC.

    Per cowork_reports/2026-05-26_sub_bot_orphan_fix_directive.md
    §Lever 3 main bot.
    """
    try:
        broker_positions = state.broker.get_positions()
    except Exception as e:
        print(f"  RECONCILE FAIL: {e!r}", flush=True)
        return
    broker_syms = {p.symbol for p in broker_positions}

    # Case 1: bot has open_position broker doesn't → flatten locally.
    op = state.open_position
    if op is not None and op.get("symbol") not in broker_syms:
        sym = op.get("symbol")
        print(f"  RECONCILE FLATTEN: {sym} — bot tracked but broker has no shares; "
              f"clearing state.open_position", flush=True)
        state.open_position = None

    # Case 2: bot has wb_positions broker doesn't → flatten locally.
    if state.wb_positions:
        wb_syms = list(state.wb_positions.keys())
        for sym in wb_syms:
            if sym not in broker_syms:
                print(f"  RECONCILE FLATTEN WB: {sym} — bot tracked but broker "
                      f"has no shares; clearing wb_positions", flush=True)
                state.wb_positions.pop(sym, None)
        if any(s for s in wb_syms if s not in broker_syms):
            try:
                persist_wb_state()
            except Exception:
                pass

    # Case 3: broker has positions the bot doesn't track — adopt-or-halt.
    # Reuse the startup function's logic (it already handles WB-vs-squeeze
    # split + adopt + halt). The function prints "Clean start" if there's
    # nothing to do, but that's acceptable noise once per minute.
    reconcile_positions_on_startup()


def reconcile_positions_on_startup():
    """Fix 1: Check broker for positions the bot doesn't know about."""
    try:
        positions = state.broker.get_positions()
    except Exception as e:
        print(f"  Position sync error: {e}", flush=True)
        return

    if not positions:
        print("  Position sync: No open positions at broker. Clean start.", flush=True)
        return

    for pos in positions:
        symbol = pos.symbol
        qty = pos.qty
        qty_available = pos.qty_available
        avg_entry = pos.avg_entry_price
        unrealized_pnl = pos.unrealized_pnl
        market_value = pos.market_value

        # Skip positions fully held by pending orders — they're in-flight, not orphan
        if qty_available == 0:
            print(f"  ⏸ IN-FLIGHT: {symbol} qty={qty} — all shares held_for_orders, "
                  f"skipping adoption/flatten (pending exit will resolve)", flush=True)
            continue

        # Skip Wave Breakout positions — they're owned by WB's own state machine,
        # not orphans. (Patched 2026-05-05 after squeeze adoption stole every WB
        # entry on the sub-bot and force-closed via bail_timer.)
        if symbol in state.wb_positions:
            print(f"  ✅ {symbol} is a WB position (qty={qty}) — skip adoption.", flush=True)
            continue

        print(f"  ⚠️ ORPHAN POSITION FOUND: {symbol} qty={qty} "
              f"(available={qty_available}) entry=${avg_entry:.2f} "
              f"unrealized=${unrealized_pnl:+,.2f} value=${market_value:,.2f}", flush=True)

        if symbol.upper() in ORPHAN_HALT_IGNORE_SYMBOLS:
            print(f"  → ORPHAN IGNORED: {symbol} on WB_ORPHAN_HALT_IGNORE_SYMBOLS — "
                  f"NOT adopting, NOT halting. Bot keeps trading other names; position "
                  f"left at broker for manual handling.", flush=True)
            continue

        if state.open_position is None:
            state.open_position = {
                "symbol": symbol,
                "entry": avg_entry,
                "qty": qty_available,  # only adopt the free qty, not shares held for pending orders
                "r": avg_entry * 0.03,
                "stop": avg_entry * 0.97,
                "score": 0.0,
                "setup_type": "orphan_adopted",
                "peak": avg_entry,
                "tp_hit": False,
                "entry_time": datetime.now(ET),
                "order_id": "adopted",
                "is_parabolic": False,
                "fill_confirmed": True,
            }
            print(f"  → Adopted {symbol} qty={qty_available} into bot state. Exit management active.", flush=True)
        else:
            # Halt-and-log: the broker has a position the bot can't account for.
            # Per project rule (feedback_session_persistence_required.md):
            # never auto-flatten orphans — that's how the 2026-05-05 CLNN
            # SELL-MARKET-after-close incident happened. Halt new entries until
            # the operator manually reconciles. The position keeps any internal
            # stop the bot already had; if state was lost, the operator must
            # decide whether to keep, exit, or hand back to the bot.
            state.entry_halt_active = True
            state.entry_halt_reason = (f"orphan {symbol} qty={qty_available} "
                                       f"avg=${avg_entry:.2f}")
            print(f"  → 🚧 ORPHAN HALT: {symbol} qty={qty_available} avg=${avg_entry:.2f} "
                  f"present in broker, no bot state. Bot will NOT auto-flatten. "
                  f"New entries blocked until manual reconciliation.", flush=True)


def _trade_record_to_open_position(rec: dict) -> dict:
    """Inverse of _open_position_to_trade_record: rehydrate an in-memory
    open_position dict from a persisted open_trades.json entry. Used only
    on resume boot, after qty has been reconciled against Alpaca.
    """
    entry_time_str = rec.get("entry_time", "")
    try:
        entry_time = datetime.fromisoformat(entry_time_str)
        # Normalize to ET for manage_exit's bail-timer math
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=timezone.utc)
        entry_time = entry_time.astimezone(ET)
    except (ValueError, TypeError):
        entry_time = datetime.now(ET)

    return {
        "symbol": rec["symbol"],
        "entry": float(rec["entry_price"]),
        "qty": int(rec["qty"]),
        "r": float(rec["r"]),
        "stop": float(rec["stop"]),
        "score": float(rec.get("score", 0.0)),
        "setup_type": rec.get("setup_type", ""),
        "peak": float(rec.get("peak", rec["entry_price"])),
        "tp_hit": rec.get("trail_mode") == "post_target",
        "entry_time": entry_time,
        "order_id": rec.get("order_id", ""),
        "is_parabolic": bool(rec.get("is_parabolic", False)),
        "fill_confirmed": True,
        "partial_filled_at": rec.get("partial_filled_at"),
        "partial_filled_qty": int(rec.get("partial_filled_qty", 0)),
    }


def resume_reconcile():
    """Resume-mode order + position reconciliation. Called instead of
    reconcile_positions_on_startup() when state.boot_mode == "resume".

    Flow (Cowork-approved, see finding_no_standing_exits.md):
      1. Cancel all pending BUY orders (entry retry state is lost).
      2. Cancel all open SELL orders (invariant: no standing protective
         orders during healthy operation; any found is a crash-mid-exit
         artifact — let manage_exit re-evaluate on the next tick).
      3. For each Alpaca position: match against open_trades.json.
         - Match → rehydrate state.open_position, reconcile qty to Alpaca.
         - No match → flatten_orphan_position() via session_state helper.
      4. Restore risk counters from risk.json.
    """
    print("🔁 RESUME: reconciling orders + positions", flush=True)

    # Step 1-2: cancel all open orders unconditionally.
    cancelled_buy = 0
    cancelled_sell = 0
    try:
        open_orders = state.broker.get_open_orders() or []
    except Exception as e:
        print(f"  RESUME: get_open_orders failed: {e}", flush=True)
        open_orders = []
    for o in open_orders:
        try:
            is_buy = o.side == "BUY"
            state.broker.cancel_order(o.order_id)
            if is_buy:
                cancelled_buy += 1
                print(f"  RESUME: cancelled pending BUY {o.order_id} {o.symbol} "
                      f"@ ${o.limit_price:.2f}", flush=True)
            else:
                cancelled_sell += 1
                print(f"  RESUME: cancelled standing SELL {o.order_id} {o.symbol} "
                      f"(invariant: no standing SELLs during healthy op)", flush=True)
        except Exception as e:
            print(f"  RESUME: cancel {o.order_id} failed: {e}", flush=True)
    if cancelled_buy or cancelled_sell:
        print(f"  RESUME: {cancelled_buy} BUYs + {cancelled_sell} SELLs cancelled", flush=True)

    # Step 3a: rehydrate WB / short state from wb_state.json. Done before the
    # broker-position pass so we recognize WB/short positions as known (not
    # orphans) when reconciling against the broker.
    #
    # JSON serializes datetime as ISO strings; downstream code does datetime
    # arithmetic (e.g. age = now - entry_time) so we must coerce back here.
    def _coerce_dt(d: dict, keys: list) -> None:
        for k in keys:
            v = d.get(k)
            if isinstance(v, str):
                try:
                    parsed = datetime.fromisoformat(v)
                    if parsed.tzinfo is None:
                        parsed = parsed.replace(tzinfo=timezone.utc)
                    d[k] = parsed.astimezone(ET)
                except ValueError:
                    pass

    wb_data = ss.read_wb_state()
    rehydrated_wb = wb_data.get("wb_positions") or {}
    rehydrated_pending = wb_data.get("wb_pending_orders") or {}
    rehydrated_short = wb_data.get("open_short")
    if rehydrated_wb:
        for _sym, _pos in rehydrated_wb.items():
            if isinstance(_pos, dict):
                _coerce_dt(_pos, ["entry_time"])
        state.wb_positions = dict(rehydrated_wb)
        print(f"  RESUME: rehydrated {len(state.wb_positions)} WB positions: "
              f"{sorted(state.wb_positions.keys())}", flush=True)
    if rehydrated_pending:
        for _sym, _po in rehydrated_pending.items():
            if isinstance(_po, dict):
                _coerce_dt(_po, ["placed_at"])
        state.wb_pending_orders = dict(rehydrated_pending)
    if rehydrated_short and isinstance(rehydrated_short, dict):
        _coerce_dt(rehydrated_short, ["entry_time"])
        state.open_short = rehydrated_short
        print(f"  RESUME: rehydrated short on {rehydrated_short.get('symbol')}", flush=True)

    # Step 3b: rehydrate squeeze positions, index persisted trades by symbol.
    persisted = ss.read_open_trades()
    by_symbol = {r["symbol"]: r for r in persisted}
    try:
        positions = state.broker.get_positions() or []
    except Exception as e:
        print(f"  RESUME: get_positions failed: {e}", flush=True)
        positions = []

    rehydrated_symbols: set[str] = set()
    for apos in positions:
        sym = apos.symbol
        broker_qty = apos.qty
        broker_entry = apos.avg_entry_price

        # Skip symbols already accounted for by WB or short rehydrate.
        if sym in state.wb_positions:
            print(f"  RESUME: {sym} qty={broker_qty} matches rehydrated WB position — skip squeeze match", flush=True)
            rehydrated_symbols.add(sym)
            continue
        if state.open_short and state.open_short.get("symbol") == sym:
            print(f"  RESUME: {sym} qty={broker_qty} matches rehydrated short position — skip squeeze match", flush=True)
            rehydrated_symbols.add(sym)
            continue

        rec = by_symbol.get(sym)
        if rec is None:
            if sym.upper() in ORPHAN_HALT_IGNORE_SYMBOLS:
                print(f"  RESUME: orphan {sym} on WB_ORPHAN_HALT_IGNORE_SYMBOLS — "
                      f"NOT halting; bot operates, position left at broker.", flush=True)
                continue
            # No persisted record in any strategy → true orphan. Per project
            # rule (no auto-flatten), set the halt flag and let the operator
            # reconcile manually. flatten_orphan_position now only logs.
            ss.flatten_orphan_position(
                state.broker, sym, broker_qty, broker_entry, current_price=None,
            )
            state.entry_halt_active = True
            state.entry_halt_reason = (f"resume orphan {sym} qty={broker_qty} "
                                       f"avg=${broker_entry:.2f}")
            continue

        # Match: rehydrate with qty drift reconciliation. Broker is truth.
        persisted_qty = int(rec.get("qty", 0))
        if persisted_qty != broker_qty:
            print(f"⚠️  REHYDRATE QTY DRIFT: {sym} persisted={persisted_qty} "
                  f"broker={broker_qty} — trusting broker "
                  f"(likely partial fill during crash)", flush=True)
            rec = dict(rec)
            rec["qty"] = broker_qty
        # (Broker reporting MORE than persisted is also suspicious — we still
        # trust the broker but flag for audit.)
        if broker_qty > persisted_qty:
            print(f"⚠️  REHYDRATE QTY DRIFT UP: {sym} broker={broker_qty} > "
                  f"persisted={persisted_qty} — unexpected. Flagging for audit.",
                  flush=True)

        if state.open_position is None:
            state.open_position = _trade_record_to_open_position(rec)
            rehydrated_symbols.add(sym)
            print(f"  RESUME: rehydrated {sym} qty={broker_qty} "
                  f"entry=${rec['entry_price']:.2f} stop=${rec['stop']:.2f} "
                  f"peak=${rec['peak']:.2f} mode={rec['trail_mode']}", flush=True)
        else:
            # Bot only tracks one momentum position at a time. A second
            # match means the persisted file disagrees with the single-slot
            # invariant — flatten the second one as orphan.
            print(f"  RESUME: {sym} matched but state.open_position already "
                  f"filled by {state.open_position['symbol']} — flattening {sym}",
                  flush=True)
            ss.flatten_orphan_position(
                state.broker, sym, broker_qty, broker_entry, current_price=None,
            )

    # Step 4: restore risk counters.
    risk = ss.read_risk()
    state.daily_pnl = float(risk.get("daily_pnl", 0.0))
    state.daily_trades = int(risk.get("daily_trades", 0))
    state.consecutive_losses = int(risk.get("consecutive_losses", 0))
    state.closed_trades = list(risk.get("closed_trades", []))
    print(f"  RESUME: risk restored — daily_pnl=${state.daily_pnl:+,.2f} "
          f"trades={state.daily_trades} losses={state.consecutive_losses} "
          f"(closed_trades={len(state.closed_trades)} cached)", flush=True)

    # Persist-after-rehydrate: the qty-reconciled records should be written
    # back so the on-disk state matches the live in-memory state.
    persist_open_trades()

    # Sanity: stale persisted records for positions that no longer exist at
    # the broker (closed during crash window) would linger without this sync.
    # persist_open_trades already wrote state.open_position (or []) — if the
    # previous open_trades.json had a symbol the broker no longer reports,
    # that record is now dropped from disk. Log the drop for post-mortem.
    dropped = set(by_symbol.keys()) - rehydrated_symbols
    for sym in dropped:
        print(f"  RESUME: persisted record for {sym} has no live broker position "
              f"— dropping (likely closed during crash window)", flush=True)

    print("🔁 RESUME: reconcile complete", flush=True)


def check_stale_open_short():
    """Clear state.open_short if a short entry's verify daemon timed out
    without seeing a terminal status (happens on 'held while locating'
    when IBKR searches for borrow > 10s). Without this, the bot stays
    gated against new shorts until restart.

    Safe: only clears when (a) > STALE_GRACE_SEC since entry_time AND
    (b) fill_confirmed is still False AND (c) broker reports the order
    is in a terminal state OR broker doesn't know about the order_id.
    """
    STALE_GRACE_SEC = 30
    pos = state.open_short
    if pos is None or pos.get("fill_confirmed", False):
        return
    age = (datetime.now(ET) - pos["entry_time"]).total_seconds()
    if age < STALE_GRACE_SEC:
        return
    order_id = pos.get("order_id", "")
    o = state.broker.get_order_status(order_id) if order_id else None
    should_clear = False
    reason = ""
    if o is None:
        should_clear = True
        reason = "broker unknown"
    elif o.status in TERMINAL_STATUSES:
        # Order is terminal — if anything filled the verify daemon should've
        # booked it. Clearing here only flips state for unfilled terminals.
        if o.filled_qty == 0:
            should_clear = True
            reason = f"terminal {o.status}, 0 filled"
    # Also handle orders that are STILL live after the grace period (e.g.,
    # IBKR "held while locating" that sits in PreSubmitted indefinitely).
    # Cancel the order ourselves and treat it as a non-fill.
    if not should_clear and o is not None and o.status in (STATUS_SUBMITTED, STATUS_PARTIALLY):
        should_clear = True
        reason = f"still {o.status} after {age:.0f}s — force-cancelling"
        state.broker.cancel_order(order_id)

    if should_clear:
        print(f"  ⚠️ STALE SHORT: {pos['symbol']} order {order_id} "
              f"{reason} — clearing stuck slot",
              flush=True)
        # Release cross-detector in_trade locks set at entry time.
        sym = pos["symbol"]
        if SHORT_ENABLED and sym in state.short_detectors:
            try:
                state.short_detectors[sym].notify_trade_closed(0.0)
            except Exception:
                pass
        if SQ_ENABLED and sym in state.sq_detectors:
            state.sq_detectors[sym]._in_trade = False
        if (MP_ENABLED or MP_V2_ENABLED) and sym in state.mp_detectors:
            state.mp_detectors[sym]._in_trade = False
        state.open_short = None
        persist_wb_state()


def periodic_position_sync():
    """Fix 3: Every 60s, verify bot state matches broker reality."""
    now = datetime.now(ET)
    if hasattr(state, '_last_position_sync') and state._last_position_sync and \
       (now - state._last_position_sync).total_seconds() < 60:
        return
    state._last_position_sync = now

    # Piggy-back stale-open_short cleanup on the same cadence.
    check_stale_open_short()

    try:
        positions = state.broker.get_positions()
    except Exception as e:
        print(f"  Position sync error: {e}", flush=True)
        return

    broker_symbols = {pos.symbol: pos for pos in positions}

    # Case 1: Bot thinks it has a position, but the broker doesn't
    if state.open_position and state.open_position.get("fill_confirmed"):
        bot_symbol = state.open_position["symbol"]
        if bot_symbol not in broker_symbols:
            print(f"  ⚠️ POSITION DESYNC: Bot thinks it holds {bot_symbol}, "
                  f"but broker shows no position. Clearing bot state.", flush=True)
            state.open_position = None

    # Case 2: Broker has a position the bot doesn't know about
    # IMPORTANT: skip positions where all shares are held_for_orders (qty_available=0).
    # Those aren't orphans — they're in-flight on a pending exit order.
    # Trying to flatten them produces "insufficient qty available" errors +
    # phantom P&L in exit_trade (see 2026-04-16_morning_report.md).
    if not state.open_position:
        for symbol, pos in broker_symbols.items():
            qty = pos.qty
            qty_available = pos.qty_available
            avg_entry = pos.avg_entry_price
            if qty_available == 0:
                print(f"  ⏸ IN-FLIGHT POSITION: broker holds {symbol} qty={qty} "
                      f"but all shares held_for_orders. Not adopting — waiting "
                      f"for pending exit to resolve.", flush=True)
                continue
            # Skip Wave Breakout positions — owned by WB state machine, not orphans.
            # (Patched 2026-05-05 after squeeze stole every WB entry on the sub-bot.)
            if symbol in state.wb_positions:
                continue
            if symbol.upper() in ORPHAN_HALT_IGNORE_SYMBOLS:
                print(f"  → ORPHAN IGNORED (sync): {symbol} on WB_ORPHAN_HALT_IGNORE_SYMBOLS "
                      f"— NOT adopting; bot keeps trading. Left at broker for manual handling.", flush=True)
                continue
            print(f"  ⚠️ ORPHAN DETECTED: broker holds {symbol} qty={qty} "
                  f"(available={qty_available}) entry=${avg_entry:.2f} — bot unaware. Adopting.", flush=True)
            state.open_position = {
                "symbol": symbol,
                "entry": avg_entry,
                "qty": qty_available,  # adopt only the free qty, not shares held for other orders
                "r": avg_entry * 0.03,
                "stop": avg_entry * 0.97,
                "score": 0.0,
                "setup_type": "orphan_adopted",
                "peak": avg_entry,
                "tp_hit": False,
                "entry_time": datetime.now(ET),
                "order_id": "adopted",
                "is_parabolic": False,
                "fill_confirmed": True,
            }
            break  # Single-position bot

    # Case 3: Quantities mismatch
    if state.open_position and state.open_position.get("fill_confirmed"):
        bot_symbol = state.open_position["symbol"]
        if bot_symbol in broker_symbols:
            brk_qty = broker_symbols[bot_symbol].qty
            bot_qty = state.open_position["qty"]
            if brk_qty != bot_qty:
                print(f"  ⚠️ QTY MISMATCH: Bot thinks {bot_qty} shares, "
                      f"broker shows {brk_qty}. Updating bot.", flush=True)
                state.open_position["qty"] = brk_qty


def wait_for_fill(order_id: str, timeout: int = 15):
    """Fix 2: Wait for broker order fill with timeout. Returns (price, qty) or (None, 0)."""
    for _ in range(timeout * 2):
        o = state.broker.get_order_status(order_id)
        if o is not None:
            if o.status == STATUS_FILLED:
                return o.filled_avg_price, o.filled_qty
            if o.status in (STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED):
                return None, 0
        time.sleep(0.5)
    # Timeout — cancel
    state.broker.cancel_order(order_id)
    # Final check — order may have filled between cancel and check
    o = state.broker.get_order_status(order_id)
    if o is not None and o.status == STATUS_FILLED:
        return o.filled_avg_price, o.filled_qty
    return None, 0


def connect():
    """Connect to IBKR with retry logic."""
    state.ib = IB()
    for attempt in range(1, 4):
        try:
            state.ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
            print(f"Connected: {state.ib.isConnected()}")
            print(f"Account: {state.ib.managedAccounts()}")
            try:
                _engine_pub.set_ibkr_connected(True)
            except Exception:
                pass
            return state.ib
        except Exception as e:
            print(f"Connection attempt {attempt}/3 failed: {e}", flush=True)
            if attempt < 3:
                print(f"Retrying in 10 seconds...", flush=True)
                time.sleep(10)
            else:
                raise


def init_detectors(symbol: str):
    """Create squeeze + MP + CT detectors for a symbol."""
    # SqueezeDetectorV2 is created when squeeze trading is on OR the move-stack is
    # on. R1 correction (2026-06-09): the ported move-stack uses the squeeze
    # detector as its ARMING engine (consumes det.armed only) — MovementStrike is
    # the intra-bar trigger, not an arming detector. So with WB_SQUEEZE_ENABLED=0 +
    # WB_MOVE_STACK_ENABLED=1 (the rebuild config) the arm must still be produced,
    # else move-strike never triggers. The squeeze's own entry/exit stays gated off
    # via SQ_ENABLED in the trade paths; only its arm is consumed by the move-stack.
    if (SQ_ENABLED or MOVE_STACK_ENABLED) and symbol not in state.sq_detectors:
        sq = SqueezeDetector()
        sq.symbol = symbol
        state.sq_detectors[symbol] = sq

    if (MP_ENABLED or MP_V2_ENABLED) and symbol not in state.mp_detectors:
        mp = MicroPullbackDetector()
        mp.symbol = symbol
        state.mp_detectors[symbol] = mp

    if CT_ENABLED and symbol not in state.ct_detectors:
        ct = ContinuationDetector()
        state.ct_detectors[symbol] = ct

    # Move-stack: MovementStrike + RegimeShiftDetector (+ FirestormTrigger, gated
    # off). Main-bot rebuild R1 (2026-06-08 directive). Mirrors the detector
    # instantiation in move_strike_subbot._ensure_symbol so the entry/exit ports
    # in R2/R3 consume identically-configured detectors.
    if MOVE_STACK_ENABLED and symbol not in state.move_strikes:
        state.move_strikes[symbol] = MovementStrike(
            lookback_bars=int(os.getenv("WB_BT_MOVE_LOOKBACK", "5")),
            multiplier=float(os.getenv("WB_BT_MOVE_MULT", "2.0")),
            stop_lookback_bars=int(os.getenv("WB_BT_MOVE_STOP_LOOKBACK", "10")),
        )
        if os.getenv("WB_REGIME_SHIFT_ENABLED", "0") == "1":
            state.regime_shift_detectors[symbol] = RegimeShiftDetector(
                ratio_threshold=float(os.getenv("WB_REGIME_SHIFT_RATIO_THRESHOLD", "4.0")),
                baseline_bars=int(os.getenv("WB_REGIME_SHIFT_BASELINE_BARS", "5")),
                require_green=os.getenv("WB_REGIME_SHIFT_REQUIRE_GREEN_BAR", "1") == "1",
            )
        if os.getenv("WB_MOVE_FIRESTORM_TRIGGER_ENABLED", "0") == "1":
            state.firestorm_triggers[symbol] = FirestormTrigger(
                min_ticks=int(os.getenv("WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN", "6000")),
            )

    # Wave Breakout — parallel strategy, separate detector per symbol.
    if WAVE_BREAKOUT_ENABLED and symbol not in state.wb_detectors:
        state.wb_detectors[symbol] = WaveBreakoutDetector(symbol)

    if SHORT_ENABLED and symbol not in state.short_detectors:
        # Pre-check broker shortability. Paper Alpaca has a narrow shortable
        # universe; IBKR's is much broader. Skip the detector entirely if
        # the broker says this name can't be shorted here.
        if symbol in state.short_unsupported:
            pass  # previously resolved as non-shortable, skip silently
        else:
            if symbol not in state.short_supported:
                try:
                    if state.broker.is_shortable(symbol):
                        state.short_supported.add(symbol)
                    else:
                        state.short_unsupported.add(symbol)
                        print(f"  SHORT_SKIP: {symbol} not shortable at broker — "
                              f"no short detector", flush=True)
                except Exception as e:
                    state.short_unsupported.add(symbol)
                    print(f"  SHORT_SKIP: {symbol} shortability lookup failed ({e}) — "
                          f"no short detector", flush=True)
            if symbol in state.short_supported:
                sd = make_short_detector(SHORT_STRATEGY)
                sd.symbol = symbol
                state.short_detectors[symbol] = sd


def subscribe_symbol(symbol: str):
    """Subscribe to market data for a symbol."""
    if symbol in state.active_symbols:
        return

    contract = Stock(symbol, 'SMART', 'USD')
    state.ib.qualifyContracts(contract)
    state.contracts[symbol] = contract

    # Subscribe to market data with RTVolume (generic tick 233) for Time & Sales
    ticker = state.ib.reqMktData(contract, '233', False, False)
    state.tickers[symbol] = ticker

    # Initialize detectors
    init_detectors(symbol)

    # Seed — resume mode replays from tick_cache/<today>/<sym>.json.gz,
    # cold mode fetches from IBKR. On resume-cache miss (symbol newly
    # subscribed post-crash, or cache read error) we fall back to the cold
    # IBKR path so the detector isn't left under-seeded.
    seeded_from_cache = False
    if state.boot_mode == "resume":
        seeded_from_cache = seed_symbol_from_cache(symbol)
    if not seeded_from_cache:
        seed_symbol(symbol)

    state.active_symbols.add(symbol)
    state.tick_counts[symbol] = 0
    state.sub_retry_counts[symbol] = 0
    # Tick-By-Tick tier: every newly-subscribed symbol starts in Tier 2
    # (snapshot reqMktData). Stage 3 promotion logic decides if/when to
    # add a tick-by-tick subscription on top.
    state.tier.setdefault(symbol, "snapshot")
    print(f"✅ Subscribed: {symbol}", flush=True)
    # Discovery-gate OBSERVE-ONLY logging (WB_DISCOVERY_GATE_OBSERVE=1). No-op when
    # off; never blocks the subscribe or alters trading. See discovery_gate.py.
    try:
        from discovery_gate import observe_discovery
        observe_discovery(symbol, state.sq_detectors.get(symbol))
    except Exception:
        pass
    persist_watchlist()


def subscribe_tick_by_tick(symbol: str, reason: str = "manual") -> bool:
    """Promote `symbol` from Tier 2 (snapshot reqMktData) to Tier 1 (full
    per-print stream via reqTickByTickData('AllLast')). Returns True on
    success, False on failure or no-op.

    The Tier 2 reqMktData subscription is intentionally NOT cancelled —
    snapshot fields keep flowing on the same Ticker, but
    `on_ticker_update` routes the symbol to the per-print drain when
    `state.tier[symbol] == 'tick_by_tick'`, so the snapshot fields are
    ignored. No double-counting.

    Capacity is capped at TBT_MAX_SUBSCRIPTIONS (Stage 1 probe = 5).
    Stage 3's `manage_tier1_subscriptions` is responsible for ensuring the
    cap isn't exceeded; this helper enforces it as a backstop and returns
    False if the cap is already saturated.
    """
    if state.tier.get(symbol) == "tick_by_tick":
        return True  # idempotent
    if len(state.tbt_tickers) >= TBT_MAX_SUBSCRIPTIONS:
        print(f"[TIER] PROMOTE {symbol} BLOCKED — capacity full "
              f"({len(state.tbt_tickers)}/{TBT_MAX_SUBSCRIPTIONS})", flush=True)
        return False
    contract = state.contracts.get(symbol)
    if not contract:
        print(f"[TIER] PROMOTE {symbol} BLOCKED — no contract registered", flush=True)
        return False
    try:
        tbt_ticker = state.ib.reqTickByTickData(contract, "AllLast", 0, False)
    except Exception as e:
        print(f"[TIER] PROMOTE {symbol} FAILED — reqTickByTickData raised: {e}", flush=True)
        return False
    state.tbt_tickers[symbol] = tbt_ticker
    state.tbt_last_processed_index[symbol] = 0
    state.tbt_subscribed_at[symbol] = datetime.now(ET)
    state.tier[symbol] = "tick_by_tick"
    print(f"[TIER] PROMOTE {symbol} reason={reason} "
          f"capacity={len(state.tbt_tickers)}/{TBT_MAX_SUBSCRIPTIONS}", flush=True)
    return True


def unsubscribe_tick_by_tick(symbol: str, reason: str = "manual") -> bool:
    """Demote `symbol` back to Tier 2. Cancels the tick-by-tick stream;
    the snapshot reqMktData subscription remains active so the symbol
    continues on the awareness layer. Returns True if a demotion actually
    occurred (i.e. symbol was in Tier 1)."""
    if state.tier.get(symbol) != "tick_by_tick":
        return False
    contract = state.contracts.get(symbol)
    if contract:
        try:
            state.ib.cancelTickByTickData(contract, "AllLast")
        except Exception as e:
            print(f"[TIER] DEMOTE {symbol} cancelTickByTickData raised: {e}", flush=True)
    sub_at = state.tbt_subscribed_at.get(symbol)
    held = (datetime.now(ET) - sub_at).total_seconds() if sub_at else None
    state.tbt_tickers.pop(symbol, None)
    state.tbt_last_processed_index.pop(symbol, None)
    state.tbt_subscribed_at.pop(symbol, None)
    state.tier[symbol] = "snapshot"
    held_str = f"{held:.0f}s" if held is not None else "?"
    print(f"[TIER] DEMOTE {symbol} reason={reason} was_tier1_for={held_str} "
          f"capacity={len(state.tbt_tickers)}/{TBT_MAX_SUBSCRIPTIONS}", flush=True)
    return True


# ══════════════════════════════════════════════════════════════════════
# Tick-By-Tick Stage 3 — promotion / demotion policy
# ══════════════════════════════════════════════════════════════════════

def _maintain_tier1_volume_bucket(bar) -> None:
    """Called from on_bar_close_1m. Appends this 1m bar's volume to a
    per-symbol rolling window of the last 5 closed bars (≈ 5-min volume).
    The volume-rank Tier-1 reserve picks the top-N by this sum."""
    if not TBT_ENABLED:
        return
    sym = bar.symbol
    buckets = state.tier1_volume_buckets.setdefault(sym, [])
    buckets.append((bar.start_utc, bar.volume))
    if len(buckets) > 5:
        del buckets[: len(buckets) - 5]


def _compute_5m_volume_rank() -> dict:
    """Returns {symbol: 1-based rank} for the top TBT_VOLUME_RESERVE_N
    symbols by sum of the last 5 1m-bar volumes. Symbols outside the
    reserve are not included in the dict."""
    sums = []
    for sym in state.active_symbols:
        buckets = state.tier1_volume_buckets.get(sym, [])
        total = sum(v for _, v in buckets)
        if total > 0:
            sums.append((sym, total))
    sums.sort(key=lambda x: (-x[1], x[0]))
    return {sym: i + 1 for i, (sym, _) in enumerate(sums[:TBT_VOLUME_RESERVE_N])}


def _has_open_position(symbol: str) -> bool:
    if state.open_position and state.open_position.get("symbol") == symbol:
        return True
    if state.open_short and state.open_short.get("symbol") == symbol:
        return True
    if symbol in state.wb_positions:
        return True
    return False


def compute_tier1_priority(symbol: str) -> int:
    """Score `symbol` for Tier 1 desirability. Higher = better candidate.
    Returns 0 if symbol has no signal worth a tick-by-tick slot."""
    # 1000 — open position. Must always be Tier 1 while in a trade.
    if _has_open_position(symbol):
        return TBT_PRI_OPEN_POSITION

    pri = 0
    sq = state.sq_detectors.get(symbol)
    if sq is not None:
        sq_state = getattr(sq, "_state", None)
        if sq_state == "ARMED":
            pri = max(pri, TBT_PRI_ARMED)
        elif sq_state == "PRIMED":
            pri = max(pri, TBT_PRI_PRIMED)

    wb = state.wb_detectors.get(symbol)
    if wb is not None:
        wb_state = getattr(wb, "state", None)
        if wb_state == "ARMED":
            pri = max(pri, TBT_PRI_ARMED)
        elif wb_state == "WAVE_OBSERVING":
            pri = max(pri, TBT_PRI_WB_OBS_MED)

    # Price-momentum: promote a violent mover on price alone, so a symbol
    # with no tick-by-tick data yet can still earn a slot. See the
    # TBT_MOMENTUM_* block for the LABT 2026-07-22 deadlock this fixes.
    pri = max(pri, _momentum_priority(symbol))

    if pri > 0:
        return pri

    # Volume-rank reserve only kicks in when no detector signal is present.
    rank = state.tier1_volume_rank.get(symbol)
    if rank is not None and rank <= TBT_VOLUME_RESERVE_N:
        if TBT_VOLUME_RESERVE_N == 1:
            return TBT_PRI_VOLUME_CEIL
        scale = (TBT_VOLUME_RESERVE_N - rank) / max(1, TBT_VOLUME_RESERVE_N - 1)
        return int(TBT_PRI_VOLUME_FLOOR + (TBT_PRI_VOLUME_CEIL - TBT_PRI_VOLUME_FLOOR) * scale)

    return 0


def _momentum_priority(symbol: str) -> int:
    """Tier-1 priority from price action alone — usable at snapshot resolution.

    Qualifies on the PEAK move: HOD is >= TBT_MOMENTUM_MIN_PCT above LOD (the
    symbol ran hard at some point today), AND current price still sits in the
    upper TBT_MOMENTUM_MIN_RANGE_POS of that range (not a fully round-tripped /
    crashed spike). Reads HOD/LOD/last — all delivered even to snapshot-tier
    symbols, and LOD/HOD are seeded from full-day history on subscribe — so it
    promotes a mover that has no tick-by-tick data yet.

    Peak-based, not current-price-based (fix 2026-07-27): the old rule measured
    current-price-vs-LOD on a 30s poll, so a brief spike that faded before a
    poll (VEEE +53%→mid-range, DFNS +38%) was missed even though it clearly ran.
    Measuring HOD-vs-LOD catches the move regardless of when the poll lands; the
    range-position floor still rejects a spike that fully round-tripped (EDBL,
    which crashed 63% back to the bottom of its range). Priority scales with the
    size of the peak move; a currently-running mover (price near HOD) is further
    de-rated UP vs a faded one so it wins the limited slots. 0 if it does not
    qualify or the gate is off. See the TBT_MOMENTUM_* constants."""
    if not TBT_MOMENTUM_ENABLED:
        return 0
    bb = state.bar_builder_1m
    if bb is None:
        return 0
    price = state.last_tick_price.get(symbol) or 0.0
    lod = bb.get_lod(symbol) or 0.0
    hod = bb.get_hod(symbol) or 0.0
    if price <= 0 or lod <= 0 or hod <= 0:
        return 0
    rng = hod - lod
    if rng <= 0:
        return 0
    peak_gain = rng / lod * 100.0            # how far it ran, high vs low
    if peak_gain < TBT_MOMENTUM_MIN_PCT:
        return 0
    range_pos = (price - lod) / rng          # 1.0 = at the high, 0 = back at the low
    if range_pos < TBT_MOMENTUM_MIN_RANGE_POS:
        return 0
    span = max(1.0, TBT_MOMENTUM_FULL_PCT - TBT_MOMENTUM_MIN_PCT)
    frac = min(1.0, (peak_gain - TBT_MOMENTUM_MIN_PCT) / span)
    base = TBT_PRI_MOMENTUM_FLOOR + (TBT_PRI_MOMENTUM_CEIL - TBT_PRI_MOMENTUM_FLOOR) * frac
    # Tilt priority toward symbols currently near their high so an active runner
    # outranks a faded one for the limited slots (0.7..1.0 of base across the
    # allowed range-position band). Never drops below the floor.
    tilt = 0.7 + 0.3 * min(1.0, range_pos)
    return max(TBT_PRI_MOMENTUM_FLOOR, int(base * tilt))


def _tier1_priority_reason(priority: int) -> str:
    """Map a priority score to the human-readable reason logged with
    [TIER] PROMOTE."""
    if priority >= TBT_PRI_OPEN_POSITION:
        return "open_position"
    if priority >= TBT_PRI_ARMED:
        return "detector_armed"
    if priority >= TBT_PRI_PRIMED:
        return "detector_primed"
    if priority >= TBT_PRI_MOMENTUM_FLOOR:
        return "price_momentum"
    if priority >= TBT_PRI_WB_OBS_MED:
        return "wave_observing"
    if priority >= TBT_PRI_VOLUME_FLOOR:
        return f"volume_top{TBT_VOLUME_RESERVE_N}"
    return "unknown"


def _can_demote_tier1(symbol: str, now) -> bool:
    """Cooldown gate: a symbol can only be demoted after holding its slot
    for at least TBT_COOLDOWN_SEC. Open positions are also a hard hold —
    even if compute_tier1_priority drops, we keep the slot until close."""
    if _has_open_position(symbol):
        return False
    sub_at = state.tbt_subscribed_at.get(symbol)
    if not sub_at:
        return True  # malformed state — let demotion proceed and clean up
    return (now - sub_at).total_seconds() >= TBT_COOLDOWN_SEC


def manage_tier1_subscriptions() -> None:
    """Re-rank all active symbols, promote the top TBT_MAX_SUBSCRIPTIONS
    with priority > 0, demote the rest (subject to cooldown). Called
    every TBT_MANAGE_INTERVAL_SEC from the main loop. No-op when
    TBT_ENABLED is false."""
    if not TBT_ENABLED:
        return
    now = datetime.now(ET)
    if state.last_tier1_manage and (now - state.last_tier1_manage).total_seconds() < TBT_MANAGE_INTERVAL_SEC:
        return
    state.last_tier1_manage = now

    # Refresh volume rank once per cycle.
    state.tier1_volume_rank = _compute_5m_volume_rank()

    # Score every active symbol.
    candidates = [(sym, compute_tier1_priority(sym)) for sym in state.active_symbols]
    candidates.sort(key=lambda x: (-x[1], x[0]))

    # Top N with non-zero priority are the target Tier 1.
    target: list = []
    for sym, pri in candidates:
        if pri <= 0 or len(target) >= TBT_MAX_SUBSCRIPTIONS:
            break
        target.append((sym, pri))
    target_syms = {sym for sym, _ in target}

    current_tier1 = {s for s, t in state.tier.items() if t == "tick_by_tick"}

    # Force-eviction guarantee: an OPEN POSITION must be Tier 1 immediately,
    # even if every slot is locked by cooldown. We only override the cooldown
    # for that case (acceptance criterion #3 in the directive). ARMED-level
    # signals respect cooldown — if observed in production that the policy
    # is too rigid and ARMED setups miss slots, relax then.
    needs_position_slot = any(
        pri >= TBT_PRI_OPEN_POSITION and sym not in current_tier1
        for sym, pri in target
    )

    # 1. Demote symbols that fell off the target list.
    for sym in current_tier1 - target_syms:
        if _can_demote_tier1(sym, now):
            unsubscribe_tick_by_tick(sym, reason="dropped_from_target")
        elif needs_position_slot and not _has_open_position(sym):
            unsubscribe_tick_by_tick(sym, reason="evicted_for_open_position")

    # 2. Promote symbols on the target list not currently in Tier 1.
    for sym, pri in target:
        if state.tier.get(sym) == "tick_by_tick":
            continue
        if len(state.tbt_tickers) >= TBT_MAX_SUBSCRIPTIONS:
            # Capacity full because some held by cooldown — nothing more we can do this cycle.
            break
        subscribe_tick_by_tick(sym, reason=_tier1_priority_reason(pri))

    # 3. Periodic STATUS line — single source of truth for the audit trail.
    tier1_list = sorted(state.tbt_tickers.keys())
    tier2_count = max(0, len(state.active_symbols) - len(tier1_list))
    print(f"[TIER] STATUS tier1={tier1_list} tier2={tier2_count} "
          f"capacity={len(tier1_list)}/{TBT_MAX_SUBSCRIPTIONS}", flush=True)


def cancel_all_tick_by_tick(reason: str = "shutdown") -> None:
    """Cancel every active reqTickByTickData subscription. Used on
    window-close and reconnect to reset Tier 1 state. Safe to call when
    no Tier 1 subs exist."""
    if not state.tbt_tickers:
        return
    for sym in list(state.tbt_tickers.keys()):
        c = state.contracts.get(sym)
        if c:
            try:
                state.ib.cancelTickByTickData(c, "AllLast")
            except Exception:
                pass
    print(f"[TIER] CANCEL_ALL n={len(state.tbt_tickers)} reason={reason}", flush=True)
    state.tbt_tickers.clear()
    state.tbt_last_processed_index.clear()
    state.tbt_subscribed_at.clear()
    for sym in list(state.tier.keys()):
        state.tier[sym] = "snapshot"


# Resubscribe queue + worker (2026-05-22 watchdog freeze fix).
# Three 120s+ main-thread freezes today were all preceded by TICK DROUGHT
# resubscribes that did cancelMktData + state.ib.sleep(2) + reqMktData
# inline. With multiple droughts in one audit cycle the cumulative sync
# work blew past the 120s watchdog limit. Moving the work to a background
# worker keeps the main thread responsive while preserving IBKR's required
# inter-call timing.
_resubscribe_queue: queue.Queue = queue.Queue()
# Background worker + executor removed 2026-05-27 — ib_insync requires the
# calling thread to own an asyncio event loop, which a ThreadPoolExecutor
# worker doesn't have. Drained inline from the main loop now; see
# drain_resubscribe_queue() below.


def drain_resubscribe_queue():
    """Drain ONE queued resubscribe per call. Replaces _resubscribe_worker
    (2026-05-27 fix): the background worker thread was raising
    "There is no current event loop in thread 'ibkr-resub_0'" on every
    invocation, leaving tick droughts unrecovered for the entire day's
    session. Confirmed 2026-05-27: 12 failures across 4 symbols, all
    silent except for the log line.

    ib_insync's sync methods (cancelMktData / reqMktData) require the
    calling thread to own the asyncio event loop. The bot's main thread
    does; ThreadPoolExecutor workers don't. Same root cause as the
    smoke-test bug we hit when shipping subscription_watchdog.py — the
    fix there was identical (drop the executor wrap, call inline).

    Cost: ~2-3 seconds of main-thread blocking per drained entry (mostly
    the IBKR-required cancel-to-req gap). Mitigated by processing only
    ONE entry per call. Multiple droughts in one cycle get spread across
    multiple cycles. Worst-case latency to recover one symbol: ~3 seconds
    after audit detects the drought. Well under the 120s watchdog.
    """
    try:
        symbol, contract = _resubscribe_queue.get_nowait()
    except queue.Empty:
        return
    try:
        try:
            state.ib.cancelMktData(contract)
        except Exception as e:
            print(f"  Resubscribe: cancelMktData({symbol}) failed: {e!r}", flush=True)
            return
        time.sleep(2)  # IBKR-required gap between cancel + req
        try:
            ticker = state.ib.reqMktData(contract, '233', False, False)
            state.tickers[symbol] = ticker
            print(f"  Resubscribed {symbol} (inline)", flush=True)
        except Exception as e:
            print(f"  Resubscribe: reqMktData({symbol}) failed: {e!r}", flush=True)
    except Exception as e:
        print(f"  Resubscription failed for {symbol}: {e}", flush=True)
    finally:
        try:
            _resubscribe_queue.task_done()
        except Exception:
            pass


def check_subscription_health():
    """Detect tick droughts and queue resubscribes for inline drain on
    the next main-loop pass. The drain runs on the main thread (where
    ib_insync's event loop lives) — see drain_resubscribe_queue."""
    for symbol in list(state.active_symbols):
        count = state.tick_counts.get(symbol, 0)
        retries = state.sub_retry_counts.get(symbol, 0)
        if count == 0 and retries < 3:
            contract = state.contracts.get(symbol)
            if not contract:
                continue
            state.sub_retry_counts[symbol] = retries + 1
            print(f"⚠️ TICK DROUGHT: {symbol} — 0 ticks in last audit period. "
                  f"Queued for resubscription (attempt {retries + 1}/3)...",
                  flush=True)
            _resubscribe_queue.put((symbol, contract))
        elif count == 0 and retries >= 3:
            print(f"🔴 CRITICAL: {symbol} — no ticks after 3 resubscription attempts", flush=True)
        else:
            # Getting ticks — reset retry counter
            state.sub_retry_counts[symbol] = 0


def audit_tick_health():
    """Log per-symbol tick counts every 60 seconds and trigger resubscription if needed."""
    now = datetime.now(ET)
    if state.last_tick_audit and (now - state.last_tick_audit).total_seconds() < 60:
        return
    state.last_tick_audit = now

    if not state.active_symbols:
        return

    for symbol in sorted(state.active_symbols):
        count = state.tick_counts.get(symbol, 0)
        last_price = state.last_tick_price.get(symbol, 0)
        last_time = state.last_tick_time.get(symbol)
        last_str = last_time.strftime("%H:%M:%S") if last_time else "never"
        print(f"  TICK AUDIT: {symbol}: {count} ticks in last 60s, "
              f"last_price=${last_price:.2f}, last_tick_time={last_str}", flush=True)

    # Check subscription health and resubscribe if needed
    check_subscription_health()
    # Drain ONE queued resubscribe inline on main thread (2026-05-27 fix).
    drain_resubscribe_queue()

    # Reset counters for next interval
    for symbol in state.active_symbols:
        state.tick_counts[symbol] = 0


def seed_symbol(symbol: str):
    """Seed detectors with historical tick data from today.

    Uses reqHistoricalTicks (tick-level data) replayed through TradeBarBuilder
    to match exactly how simulate.py processes data. This ensures the squeeze
    detector's volume averages and state machine match backtest behavior.
    """
    contract = state.contracts.get(symbol)
    if not contract:
        return

    try:
        # Tell detectors we're about to seed (suppresses entry signals during replay)
        sq = state.sq_detectors.get(symbol)
        if sq:
            sq.begin_seed()

        # Fetch tick-level historical data from today.
        # Strategy: start from 4 AM ET but if too many ticks, restart from
        # 90 minutes before now. This ensures we always get RECENT volume
        # context (what matters for detector baselines) even on high-volume stocks.
        now_et = datetime.now(ET)
        seed_start = now_et.replace(hour=4, minute=0, second=0, microsecond=0)
        start_str = seed_start.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"

        all_ticks = []
        current_start = start_str
        max_pages = 100  # enough for full session
        max_ticks = 50000  # first pass cap
        ticks_per_page = 1000

        for page in range(max_pages):
            # Heartbeat each page — pagination of up to 100 pages with API
            # latency can exceed the 120s watchdog window.
            update_heartbeat()
            ticks = state.ib.reqHistoricalTicks(
                contract, current_start, '', ticks_per_page, 'TRADES', useRth=False
            )
            if not ticks:
                break
            all_ticks.extend(ticks)
            state.ib.sleep(0.3)

            if len(ticks) < ticks_per_page:
                break  # got all ticks

            # If we've hit the cap, restart from 90 min ago to get recent data
            if len(all_ticks) >= max_ticks:
                recent_start = (now_et - timedelta(minutes=90))
                recent_str = recent_start.strftime("%Y%m%d %H:%M:%S") + " US/Eastern"
                # Only restart if we haven't already reached recent data
                last_time = ticks[-1].time
                if last_time < recent_start.astimezone(timezone.utc):
                    print(f"  [SEED] {symbol}: {len(all_ticks)} ticks so far, "
                          f"jumping to recent 90min for full context", flush=True)
                    current_start = recent_str
                    continue
                break

            # Paginate: next page starts after last tick
            last_time = ticks[-1].time
            current_start = last_time.strftime("%Y%m%d %H:%M:%S") + " UTC"

            # Stop if we've caught up to now
            if last_time >= now_et.astimezone(timezone.utc):
                break

        if not all_ticks:
            # Fallback to 1m bars if tick data unavailable
            print(f"⚠️ No tick data for {symbol}, falling back to 1m bars", flush=True)
            _seed_symbol_bars_fallback(symbol)
            return

        # Persist fetched historical ticks to the tick_buffer so that the
        # 30s flush captures them to tick_cache/<today>/<sym>.json.gz.
        # This makes the cache authoritative (04:00 ET onward) so a future
        # resume boot can replay from disk without re-fetching from IBKR.
        # Lock serializes against the flush swap and live tick callback.
        with _tick_buffer_lock:
            buf = state.tick_buffer.setdefault(symbol, [])
            for tick in all_ticks:
                if tick.price <= 0 or not tick.size or int(tick.size) <= 0:
                    continue
                buf.append({
                    "p": float(tick.price),
                    "s": int(tick.size),
                    "t": tick.time.astimezone(timezone.utc).isoformat(),
                })

        # Replay ticks through TradeBarBuilder (same path as live ticks and simulate.py)
        # This builds bars organically with correct volume accumulation
        bars_built = 0
        for tick in all_ticks:
            ts_utc = tick.time
            price = tick.price
            size = int(tick.size) if tick.size else 0
            if price <= 0 or size <= 0:
                continue

            # Feed to the MAIN bar builder — this triggers on_bar_close_1m
            # which feeds the squeeze/MP/CT detectors through the normal pipeline
            if state.bar_builder_1m:
                state.bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            # Feed to box bar builder too — keeps box RSI/VWAP in sync
            if BOX_ENABLED and state.box_bar_builder_1m:
                state.box_bar_builder_1m.on_trade(symbol, price, size, ts_utc)

        # HOD/LOD backstop (2026-07-10): the tick replay above only covers the
        # ticks reqHistoricalTicks returned, which truncates to recent ticks —
        # so a mid-session start leaves bar_builder._hod/_lod missing the earlier
        # session (NVVE showed 14.86 vs the real 20.74, shipped wrong to the
        # manual bot). Seed session extremes from full-day 1-min bars (one cheap
        # request, whatToShow=TRADES, useRTH=False → includes premarket). max/min
        # only, so it's safe on top of the tick replay and never touches VWAP.
        _seed_session_hod_lod(symbol)

        # Count how many bars were built
        sq = state.sq_detectors.get(symbol)
        bar_count = len(sq.bars_1m) if sq else 0
        ema = sq.ema if sq else None
        armed = sq.armed if sq else None

        # Validate armed trigger vs. last replayed price — drops arms that are
        # already stale (trigger_high well below current price) before live
        # ticks can fire them. Complements the seed-gate which only suppresses
        # replayed signals, not stale trigger values. See
        # cowork_reports/2026-04-13_directive_stale_seed_fix.md.
        if sq:
            latest_price = all_ticks[-1].price if all_ticks else 0.0
            stale_msg = sq.validate_arm_after_seed(float(latest_price))
            if stale_msg:
                print(f"  [{symbol}] {stale_msg}", flush=True)
                armed = None  # refresh local summary for the Seeded log line

        # Mark seed complete — detector gate suppresses stale entries until live bars confirm
        if sq:
            sq.end_seed()
        state.seed_complete_time[symbol] = datetime.now(ET)
        state.live_tick_count_since_seed[symbol] = 0

        print(f"🔥 Seeded {symbol}: {len(all_ticks)} ticks → {bar_count} bars"
              + (f", EMA={ema:.4f}" if ema else "")
              + (f", ARMED" if armed else "")
              + f" ({len(all_ticks)//max(1,bar_count)} ticks/bar avg)",
              flush=True)

    except Exception as e:
        print(f"⚠️ Tick seed failed for {symbol}: {e} — falling back to 1m bars", flush=True)
        traceback.print_exc()
        _seed_symbol_bars_fallback(symbol)
        state.seed_complete_time[symbol] = datetime.now(ET)
        state.live_tick_count_since_seed[symbol] = 0


def _bridge_gap_for_symbol(symbol: str, start_utc: datetime, end_utc: datetime) -> int:
    """Fetch ticks from IBKR for [start_utc, end_utc] and feed them through
    the bar builder + persist to the tick buffer (so the flush thread writes
    them to cache). Returns count of ticks fed. On any IBKR error, returns 0
    and lets the caller continue without a bridged window.
    """
    contract = state.contracts.get(symbol)
    if not contract or end_utc <= start_utc:
        return 0
    try:
        # IBKR uses local-formatted strings; convert UTC → "YYYYMMDD HH:MM:SS UTC"
        start_str = start_utc.strftime("%Y%m%d %H:%M:%S") + " UTC"
        bridged_ticks = []
        current_start = start_str
        for _ in range(20):  # 20 pages × 1000 ticks = 20K cap, safety
            update_heartbeat()
            ticks = state.ib.reqHistoricalTicks(
                contract, current_start, '', 1000, 'TRADES', useRth=False
            )
            if not ticks:
                break
            bridged_ticks.extend(ticks)
            state.ib.sleep(0.3)
            if len(ticks) < 1000:
                break
            last_t = ticks[-1].time
            if last_t >= end_utc:
                break
            current_start = last_t.strftime("%Y%m%d %H:%M:%S") + " UTC"

        # Persist to tick buffer for flush + replay through bar builder
        with _tick_buffer_lock:
            buf = state.tick_buffer.setdefault(symbol, [])
            for tick in bridged_ticks:
                if tick.price <= 0 or not tick.size or int(tick.size) <= 0:
                    continue
                buf.append({
                    "p": float(tick.price),
                    "s": int(tick.size),
                    "t": tick.time.astimezone(timezone.utc).isoformat(),
                })
        for tick in bridged_ticks:
            ts_utc = tick.time
            price = tick.price
            size = int(tick.size) if tick.size else 0
            if price <= 0 or size <= 0:
                continue
            if state.bar_builder_1m:
                state.bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            if BOX_ENABLED and state.box_bar_builder_1m:
                state.box_bar_builder_1m.on_trade(symbol, price, size, ts_utc)
        return len(bridged_ticks)
    except Exception as e:
        print(f"  [RESUME] {symbol}: gap bridge failed: {e}", flush=True)
        return 0


def seed_symbol_from_cache(symbol: str) -> bool:
    """Resume-mode seed: replay ticks from tick_cache/<today>/<sym>.json.gz
    into fresh detectors instead of fetching from IBKR. Returns True on
    success, False if no cache or empty (caller falls back to seed_symbol).

    Mirrors seed_symbol exactly below the tick-fetch step:
      - begin_seed on squeeze detector suppresses replayed signals
      - bar_builder_1m.on_trade replays ticks through the normal pipeline;
        MP/CT rebuild their state via on_bar_close_1m
      - validate_arm_after_seed drops stale trigger values
      - end_seed marks replay done; live ticks arriving after re-subscribe
        start feeding signals

    Crucially does NOT run ticks through on_ticker_update's downstream
    (on_trade_price) — that would fire entries retroactively. Same
    architectural guard the cold-path seed relies on.
    """
    today = datetime.now(ET).strftime("%Y-%m-%d")
    cache_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "tick_cache", today, f"{symbol}.json.gz",
    )
    if not os.path.exists(cache_path):
        return False

    try:
        with gzip.open(cache_path, "rt") as f:
            raw_ticks = json.load(f)
    except Exception as e:
        print(f"⚠️ [RESUME] {symbol} cache read failed: {e} — falling back to IBKR seed", flush=True)
        return False

    if not raw_ticks:
        return False

    try:
        sq = state.sq_detectors.get(symbol)
        if sq:
            sq.begin_seed()

        replayed = 0
        last_ts_utc = None
        for t in raw_ticks:
            try:
                price = float(t["p"])
                size = int(t["s"])
                ts_utc = datetime.fromisoformat(t["t"])
            except (KeyError, ValueError, TypeError):
                continue
            if price <= 0 or size <= 0:
                continue

            if state.bar_builder_1m:
                state.bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            if BOX_ENABLED and state.box_bar_builder_1m:
                state.box_bar_builder_1m.on_trade(symbol, price, size, ts_utc)
            replayed += 1
            last_ts_utc = ts_utc

        # Gap-bridge: fetch ticks from IBKR for the window between cache's
        # last tick and now. This makes resume context-complete for symbols
        # the bot was already watching when it died. Capped at 90 min so a
        # bot down for hours doesn't pay an unbounded fetch cost.
        if last_ts_utc is not None:
            now_utc = datetime.now(timezone.utc)
            gap_sec = (now_utc - last_ts_utc).total_seconds()
            if gap_sec > 60:  # only bridge meaningful gaps
                bridge_start_utc = max(last_ts_utc, now_utc - timedelta(minutes=90))
                bridged = _bridge_gap_for_symbol(symbol, bridge_start_utc, now_utc)
                if bridged > 0:
                    print(f"  [RESUME] {symbol}: bridged gap "
                          f"({gap_sec/60:.1f}m, capped 90m) → {bridged:,} ticks",
                          flush=True)

        sq = state.sq_detectors.get(symbol)
        bar_count = len(sq.bars_1m) if sq else 0
        ema = sq.ema if sq else None
        armed = sq.armed if sq else None

        if sq and raw_ticks:
            # Prefer LIVE wall-clock price for staleness comparison
            # (2026-05-18 resume-boot stale-signal fix). raw_ticks[-1] is the
            # last cached tick at the moment of crash — can be minutes/hours
            # stale relative to the current tape. state.last_tick_price[symbol]
            # is refreshed by _process_trade_tick on every live print. Fall
            # back to the cached tick if no live price has arrived yet.
            live_price = state.last_tick_price.get(symbol)
            if live_price and live_price > 0:
                latest_price = float(live_price)
            else:
                latest_price = float(raw_ticks[-1].get("p", 0))
            stale_msg = sq.validate_arm_after_seed(latest_price)
            if stale_msg:
                print(f"  [{symbol}] {stale_msg}", flush=True)
                armed = None

        if sq:
            sq.end_seed()
        state.seed_complete_time[symbol] = datetime.now(ET)
        state.live_tick_count_since_seed[symbol] = 0

        # Clock-drift log per Cowork ask — exposes any detector-time bugs.
        wall_utc = datetime.now(timezone.utc)
        drift_sec = (wall_utc - last_ts_utc).total_seconds() if last_ts_utc else None
        drift_str = f"{drift_sec/60:.1f}m" if drift_sec is not None else "?"
        print(f"🔁 [RESUME] {symbol}: {replayed:,} ticks → {bar_count} bars"
              + (f", EMA={ema:.4f}" if ema else "")
              + (", ARMED" if armed else "")
              + f" | drift={drift_str}",
              flush=True)
        return True
    except Exception as e:
        print(f"⚠️ [RESUME] {symbol} replay failed: {e} — falling back to IBKR seed", flush=True)
        traceback.print_exc()
        # Leave detector state partially built; caller will fall back to
        # seed_symbol which does begin_seed again (idempotent) and re-seeds
        # from IBKR. The worst case is a slightly extended boot.
        return False


def _seed_session_hod_lod(symbol: str):
    """Seed bar_builder session HOD/LOD from today's full-day 1-min bars.
    Restart-proof HOD/LOD for the manual bot's Info panel + level alerts.
    Cheap (one request); max/min only (no VWAP/volume side effects). Never
    raises into the caller."""
    try:
        if state.bar_builder_1m is None:
            return
        contract = state.contracts.get(symbol)
        if contract is None:
            return
        bars = state.ib.reqHistoricalData(
            contract, endDateTime='', durationStr='1 D',
            barSizeSetting='1 min', whatToShow='TRADES',
            useRTH=False, formatDate=1,
        )
        state.ib.sleep(0.3)
        if not bars:
            return
        seeded = 0
        for b in bars:
            ts = getattr(b, 'date', None)
            state.bar_builder_1m.seed_session_extremes(symbol, b.high, b.low, ts)
            seeded += 1
        h = state.bar_builder_1m.get_hod(symbol)
        l = state.bar_builder_1m.get_lod(symbol)
        print(f"  [{symbol}] HOD/LOD seeded from {seeded} bars → "
              f"HOD={h} LOD={l}", flush=True)
    except Exception as e:
        print(f"  [{symbol}] HOD/LOD seed skipped: {e!r}", flush=True)


def _seed_symbol_bars_fallback(symbol: str):
    """Fallback: seed with 1m historical bars (old method). Used when tick data unavailable."""
    contract = state.contracts.get(symbol)
    if not contract:
        return
    try:
        bars = state.ib.reqHistoricalData(
            contract, endDateTime='', durationStr='1 D',
            barSizeSetting='1 min', whatToShow='TRADES',
            useRTH=False, formatDate=1,
        )
        state.ib.sleep(0.5)
        if not bars:
            return
        for b in bars:
            o, h, l, c, v = b.open, b.high, b.low, b.close, b.volume
            # HOD/LOD for the manual bot (max/min, no VWAP side effect).
            if state.bar_builder_1m is not None:
                state.bar_builder_1m.seed_session_extremes(
                    symbol, h, l, getattr(b, 'date', None))
            if SQ_ENABLED and symbol in state.sq_detectors:
                state.sq_detectors[symbol].seed_bar_close(o, h, l, c, v)
            if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
                state.mp_detectors[symbol].seed_bar_close(o, h, l, c, v)
            if CT_ENABLED and symbol in state.ct_detectors:
                state.ct_detectors[symbol].seed_bar_close(o, h, l, c, v)
        print(f"🔥 Seeded {symbol} (fallback): {len(bars)} bars", flush=True)
    except Exception as e:
        print(f"⚠️ Fallback seed also failed for {symbol}: {e}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Scanner
# ══════════════════════════════════════════════════════════════════════

def run_scanner():
    """Run the IBKR scanner and subscribe to top candidates.

    First scan of a session runs a WIDE catchup scan (multiple scanner codes)
    to find everything that moved today, even if we started late.
    Subsequent scans use the normal TOP_PERC_GAIN to catch new arrivals.
    """
    now = datetime.now(ET)

    # Only scan during active trading windows
    if not in_trading_window(now):
        return

    # Don't scan more than every 5 minutes
    if state.last_scan_time and (now - state.last_scan_time).total_seconds() < 300:
        return

    is_first_scan = state.last_scan_time is None

    # Snapshot the Error-162 counter so we can tell whether the scanner
    # subscription got cancelled DURING this scan (the wedge signature).
    _162_before = state.scanner_162_count

    if is_first_scan:
        # First scan of session: wide catchup to find everything that moved today
        print(f"\n🔄 CATCHUP SCAN at {now.strftime('%H:%M:%S')} ET (first scan — casting wide net)...", flush=True)
        state.candidates = scan_catchup(state.ib)
    else:
        # Subsequent scans: just check for new arrivals
        print(f"\n🔄 Running scanner at {now.strftime('%H:%M:%S')} ET...", flush=True)
        state.candidates = scan_premarket_live(state.ib)

    state.last_scan_time = now
    _162_this_scan = state.scanner_162_count - _162_before

    # Subscribe to new candidates (top 5 from catchup, or all new from rescan)
    max_new = 5 if is_first_scan else 5
    new_subs = 0
    for c in state.candidates[:max_new]:
        sym = c["symbol"]
        if sym not in state.active_symbols:
            subscribe_symbol(sym)
            new_subs += 1
            # Heartbeat between subscribes — qualifyContracts + reqMktData +
            # seed_symbol's tick pagination can each take 10-30s; without this,
            # 4-5 sequential subscribes blow past the 120s watchdog.
            update_heartbeat()

    # NOTE: We NEVER unsubscribe symbols during a session. Once subscribed,
    # a stock stays on the watchlist until the trading window closes.
    # This prevents losing coverage when a stock temporarily drops from
    # the scanner (e.g., RVOL dips below threshold between volume spikes).

    print(f"📊 Scanner: {len(state.candidates)} new candidates, "
          f"{new_subs} new subs, {len(state.active_symbols)} total watching", flush=True)

    # Scanner-wedge self-recovery (2026-07-23). Wedge signature: we are watching
    # NOTHING and Error 162 (scanner subscription cancelled) fired this scan.
    # A genuinely quiet premarket also has 0 candidates but produces NO 162s, so
    # it never trips this. Once anything is subscribed active_symbols stays >0
    # for the rest of the session, so this only ever fires at a wedged startup.
    if SCANNER_WEDGE_RECOVERY:
        if len(state.active_symbols) == 0 and _162_this_scan > 0:
            state.scanner_wedge_streak += 1
            print(f"⚠️ SCANNER WEDGE suspected: 0 symbols watching + "
                  f"{_162_this_scan} Error-162 this scan "
                  f"(streak {state.scanner_wedge_streak}/{SCANNER_WEDGE_MAX})",
                  flush=True)
        else:
            state.scanner_wedge_streak = 0
        if state.scanner_wedge_streak >= SCANNER_WEDGE_MAX:
            print(f"🔥 SCANNER WEDGE CONFIRMED — {state.scanner_wedge_streak} "
                  f"consecutive scans with 0 symbols and Error 162. "
                  f"reqScannerData is stuck; only a fresh IBKR connection clears "
                  f"it. Exiting for supervisor auto-restart "
                  f"(2026-07-23 blind-morning fix).", flush=True)
            sys.exit(1)


def _maybe_session_end_force_exit() -> None:
    """Cowork directive 2026-05-15 P0.2 — flatten all open positions before
    extended-hours close. Pairs with the FCHL session-resume fix; together
    they eliminate the date-boundary orphan class.

    NEVER market orders (user constraint). force_exit_position uses an
    aggressive SELL LIMIT with chase-down ladder."""
    try:
        import force_exit
    except Exception as e:
        print(f"⚠️  FORCE_EXIT import failed: {e!r}", flush=True)
        return
    if not force_exit.should_force_exit_now():
        return

    print(f"\n🟧 SESSION_END_FORCE_EXIT triggered at {datetime.now(ET).strftime('%H:%M:%S')} ET",
          flush=True)

    # Squeeze position (state.open_position)
    pos = state.open_position
    if pos and pos.get("fill_confirmed"):
        symbol = pos.get("symbol")
        qty = int(pos.get("qty", 0))
        ref = float(pos.get("peak") or pos.get("entry") or 0.0)
        if symbol and qty > 0 and ref > 0:
            res = force_exit.force_exit_position(state.broker, symbol, qty, ref,
                                                  log_prefix="[SQ] ")
            if res["filled"]:
                pnl = (res["fill_price"] - pos["entry"]) * res["fill_qty"]
                print(f"  🟥 EXIT: {symbol} qty={res['fill_qty']} @ ${res['fill_price']:.4f} "
                      f"reason=session_end_force P&L=${pnl:+,.2f}", flush=True)
                state.open_position = None
                try:
                    persist_open_trades()
                except Exception:
                    pass

    # WB positions (state.wb_positions dict)
    for symbol in list(state.wb_positions.keys()):
        wb_pos = state.wb_positions.get(symbol)
        if not wb_pos:
            continue
        qty = int(wb_pos.get("qty", 0))
        ref = float(wb_pos.get("peak") or wb_pos.get("entry") or 0.0)
        if qty <= 0 or ref <= 0:
            continue
        res = force_exit.force_exit_position(state.broker, symbol, qty, ref,
                                              log_prefix="[WB] ")
        if res["filled"]:
            pnl = (res["fill_price"] - wb_pos["entry"]) * res["fill_qty"]
            print(f"  🟥 EXIT: {symbol} qty={res['fill_qty']} @ ${res['fill_price']:.4f} "
                  f"reason=session_end_force P&L=${pnl:+,.2f}", flush=True)
            state.wb_positions.pop(symbol, None)


def run_intraday_adder() -> None:
    """Stage 0.3 — observe-only intraday WB candidate adder.

    Cowork DIRECTIVE_GO_STAGE_0_3.md: poll the IBKR scanner every
    WB_INTRADAY_ADDER_POLL_MIN minutes during RTH for symbols meeting
    WB-friendly intraday thresholds. Writes one JSONL row per cycle
    to `logs/<today>_wb_intraday_adder_observe.jsonl`. Does NOT inject
    into the live watchlist unless WB_INTRADAY_ADDER_OBSERVE_ONLY=0.

    Lives next to run_scanner() so the existing per-iteration cadence
    in the main loop handles both. Throttling is internal — early
    returns when env-disabled or the poll interval has not elapsed."""
    try:
        import wb_intraday_adder
    except Exception as e:
        print(f"⚠️  WB_INTRADAY_ADDER import failed: {e!r}", flush=True)
        return
    if not wb_intraday_adder.SHOULD_RUN:
        return

    now = datetime.now(ET)
    poll_sec = wb_intraday_adder.POLL_MIN * 60
    if state.last_intraday_adder_time and \
            (now - state.last_intraday_adder_time).total_seconds() < poll_sec:
        return

    state.intraday_adder_poll_n += 1
    state.last_intraday_adder_time = now

    session_losses = getattr(state, "session_losses", None)
    record = wb_intraday_adder.poll(
        state.ib,
        now_et=now,
        poll_n=state.intraday_adder_poll_n,
        session_losses=session_losses,
        active_symbols=state.active_symbols,
    )
    if record is None:
        return

    n_pass = record["candidates_passing"]
    n_eval = record["candidates_evaluated"]
    print(f"🔭 WB_INTRADAY_ADDER poll #{state.intraday_adder_poll_n}: "
          f"{n_eval} evaluated, {n_pass} passing "
          f"(observe_only={record['observe_only']})", flush=True)
    if n_pass:
        syms = wb_intraday_adder.passing_symbols(record)
        print(f"   would-add: {syms}", flush=True)

    # Live mode (Stage 0.3+ only after Mon 5/18 review): subscribe the
    # passing symbols. Guarded behind OBSERVE_ONLY=0 so today's run is
    # pure telemetry.
    if not record["observe_only"]:
        for sym in wb_intraday_adder.passing_symbols(record):
            if sym not in state.active_symbols:
                try:
                    subscribe_symbol(sym)
                except Exception as e:
                    print(f"⚠️  WB_INTRADAY_ADDER subscribe {sym} failed: {e!r}",
                          flush=True)


def poll_watchlist():
    """Read watchlist.txt (written by live_scanner.py / Databento) and subscribe to new symbols.

    Hypothesis #17 (2026-05-13): on COLD START, if watchlist.txt was last
    written before today, ignore it — yesterday's stale list would otherwise
    feed losing trades on symbols that have not been re-validated by today's
    scanner. Today's ENSC at $0.30 was the canonical case (Databento 402 →
    live_scanner crashed → KBSX, CLNN, FATN, SST, NVOX, ATRA, TRAW, ENSC,
    ODYS all carried over from 2026-05-11). Once the scanner writes a fresh
    watchlist.txt later in the session, this check passes naturally. Resume
    boots are unchanged: durable session_state/<today>/watchlist.json is
    rehydrated by resume_reconcile, not by this function. Toggle via
    WB_FRESH_WATCHLIST_ON_COLD_START.
    """
    if not DATABENTO_BRIDGE:
        return
    if not os.path.exists(WATCHLIST_FILE):
        return

    if (WB_FRESH_WATCHLIST_ON_COLD_START
            and getattr(state, "boot_mode", "cold") == "cold"):
        try:
            mtime = os.path.getmtime(WATCHLIST_FILE)
            file_date = datetime.fromtimestamp(mtime, tz=ET).date()
            today_et = datetime.now(ET).date()
            if file_date < today_et:
                # Stale watchlist (scanner has not yet written today's file).
                # Suppress repeat-log spam by stashing the last warning date.
                last_warn = getattr(state, "_h17_stale_warn_date", None)
                if last_warn != today_et:
                    print(f"📡 H#17: skipping stale watchlist.txt "
                          f"(mtime={file_date} < today={today_et}) — "
                          f"waiting for scanner to write a fresh list",
                          flush=True)
                    state._h17_stale_warn_date = today_et
                return
        except Exception as e:
            print(f"⚠️  H#17 mtime check failed: {e!r} — falling through "
                  f"to legacy behavior", flush=True)

    try:
        with open(WATCHLIST_FILE, "r") as f:
            lines = [l.strip() for l in f if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return

    new_syms = []
    for line in lines:
        sym = line.split(":")[0].strip().upper()
        if sym and sym.isalpha() and 1 <= len(sym) <= 5:
            if sym not in state.active_symbols:
                new_syms.append(sym)

    if new_syms:
        print(f"\n📡 Databento bridge: {len(new_syms)} new symbols from watchlist.txt: {sorted(new_syms)}", flush=True)
        for sym in new_syms:
            subscribe_symbol(sym)

    # WB persistence layer (Cowork directive 2026-05-14 §0.2): inject
    # symbols with recent WB_OBSERVE activity even when today's squeeze
    # scanner filtered them out (typically for pm_volume < 30K). These
    # symbols flow downstream to subbot + engine via session_state/
    # watchlist.json.
    try:
        import wb_persistence
        persist_syms = wb_persistence.active_persisted_symbols()
        new_persist = sorted(persist_syms - state.active_symbols)
        if new_persist:
            print(f"\n🧠 WB_PERSIST: {len(new_persist)} symbols carried from "
                  f"prior sessions: {new_persist}", flush=True)
            for sym in new_persist:
                subscribe_symbol(sym)
    except Exception as e:
        print(f"⚠️  WB_PERSIST poll_watchlist injection failed: {e!r}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Bar Building + Detection
# ══════════════════════════════════════════════════════════════════════

def on_bar_close_1m(bar):
    """1-minute bar close: feed to squeeze + MP detectors."""
    symbol = bar.symbol
    now_str = datetime.now(ET).strftime("%H:%M")

    # Tier-1 volume rolling window — fed every closed 1m bar.
    _maintain_tier1_volume_bucket(bar)

    # Get VWAP from bar builder
    vwap = state.bar_builder_1m.get_vwap(symbol) if state.bar_builder_1m else None
    pm_high = state.bar_builder_1m.get_premarket_high(symbol) if state.bar_builder_1m else None

    # Diagnostic: log full chart state every 5 minutes per symbol
    hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else None
    minute = datetime.now(ET).minute
    if minute % 5 == 0:
        try:
            sq = state.sq_detectors.get(symbol)
            sq_state = sq._state if sq else "N/A"
            armed_lvl = f"${sq.armed.trigger_high:.2f}" if (sq and sq.armed) else "none"
            ema = f"{sq.ema:.2f}" if (sq and sq.ema) else "none"
            macd_hist = f"{sq.macd_state.histogram:.3f}" if (sq and hasattr(sq, 'macd_state') and sq.macd_state.histogram is not None) else "N/A"
            bar_count = len(sq.bars_1m) if (sq and hasattr(sq, 'bars_1m')) else 0
            avg_vol = sq._avg_prior_vol() if (sq and hasattr(sq, '_avg_prior_vol')) else 0
            vol_ratio = bar.volume / avg_vol if avg_vol > 0 else 0
            vwap_dist = ((bar.close - vwap) / vwap * 100) if vwap and vwap > 0 else 0
            print(f"[{now_str} ET] {symbol} CHART | "
                  f"O={bar.open:.2f} H={bar.high:.2f} L={bar.low:.2f} C={bar.close:.2f} V={bar.volume:,} | "
                  f"EMA9={ema} VWAP={vwap or 0:.2f} ({vwap_dist:+.1f}%) HOD={hod or 0:.2f} PM_H={pm_high or 0:.2f} | "
                  f"MACD={macd_hist} vol_ratio={vol_ratio:.1f}x avg_vol={avg_vol:,.0f} bars={bar_count} | "
                  f"sq={sq_state} armed={armed_lvl}", flush=True)
        except Exception as e:
            print(f"[{now_str} ET] {symbol} CHART diagnostic error: {e}", flush=True)

    # Squeeze detection — also runs as the ARMING engine for the move-stack
    # (R2). When SQ_ENABLED=0 but MOVE_STACK_ENABLED=1 we still feed the
    # detector so it produces det.armed for MovementStrike to trigger on; the
    # squeeze's own entry/exit stays gated off in check_triggers/exit paths.
    if (SQ_ENABLED or MOVE_STACK_ENABLED) and symbol in state.sq_detectors:
        sq = state.sq_detectors[symbol]
        if pm_high:
            pm_bf = state.bar_builder_1m.get_premarket_bull_flag_high(symbol) if state.bar_builder_1m else None
            sq.update_premarket_levels(pm_high, pm_bf)
        sq_msg = sq.on_bar_close_1m(bar, vwap=vwap)
        if sq_msg:
            if "ARMED" in sq_msg:
                print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            elif "SQ_PRIMED" in sq_msg:
                print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            elif "SQ_REJECT" in sq_msg or "SQ_RESET" in sq_msg:
                print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
        # Move-stack: reset MovementStrike history on a None→armed transition so
        # its rolling average + consolidation low reflect only post-arm bars
        # (mirrors move_strike_subbot:795-801).
        if MOVE_STACK_ENABLED and symbol in state.move_strikes:
            _prev_arm = state.move_prev_arm_state.get(symbol)
            if sq.armed is not None and _prev_arm is None:
                state.move_strikes[symbol].reset_history()
                # Stamp arm time (bar's ET minute) for the time-window block.
                try:
                    _bet = bar.start_utc.astimezone(ET)
                    state._arm_minute_et[symbol] = _bet.hour * 60 + _bet.minute
                except Exception:
                    _n = datetime.now(ET)
                    state._arm_minute_et[symbol] = _n.hour * 60 + _n.minute
            state.move_prev_arm_state[symbol] = sq.armed
            # Track armed-today for the regime-shift require_armed gate.
            if sq.armed is not None:
                state.regime_shift_armed_today.add(symbol)

    # Move-stack: regime-shift entry fires on this 1m bar close (parallel path to
    # the per-tick MOVE_STRIKE trigger). R2b. Runs after the arm feed above so
    # require_armed sees today's arms.
    if MOVE_STACK_ENABLED and symbol in state.regime_shift_detectors:
        maybe_fire_regime_shift(symbol, bar)

    # Wave Breakout detection (parallel to squeeze; the detector returns
    # informational messages on bar close — actual entry triggers happen on
    # the next tick via on_trade_price). All log lines use the [WB] prefix
    # for grep-friendly post-session analysis.
    if WAVE_BREAKOUT_ENABLED and symbol in state.wb_detectors:
        wb_msg = state.wb_detectors[symbol].on_bar_close_1m(bar, vwap=vwap)
        if wb_msg:
            print(f"[WB] [{now_str} ET] {symbol} {wb_msg}", flush=True)

    # MP detection (standalone MP or V2 re-entry)
    if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
        mp = state.mp_detectors[symbol]
        mp_msg = mp.on_bar_close_1m(bar, vwap=vwap)
        if mp_msg and ("ARMED" in mp_msg or "MP_V2" in mp_msg):
            print(f"[{now_str} ET] {symbol} MP | {mp_msg}", flush=True)

    # Continuation detection (post-squeeze — only when SQ is fully idle + lockout clear)
    _ct_sq_idle = not (SQ_ENABLED and symbol in state.sq_detectors and
                       (state.sq_detectors[symbol]._state != "IDLE" or state.sq_detectors[symbol]._in_trade))
    if CT_ENABLED and _ct_sq_idle and symbol in state.ct_detectors:
        ct = state.ct_detectors[symbol]
        # Check for pending activation (deferred from squeeze close)
        _ct_act = ct.check_pending_activation(bar_time=now_str)
        if _ct_act:
            print(f"[{now_str} ET] {symbol} CT | {_ct_act}", flush=True)
        ct_msg = ct.on_bar_close_1m(bar, vwap=vwap, bar_time=now_str)
        if ct_msg:
            if "CT_ARMED" in ct_msg or "CT_REJECT" in ct_msg or "CT_RESET" in ct_msg:
                print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)
            elif "CT_WATCHING" in ct_msg or "CT_PULLBACK" in ct_msg or "CT_PAUSE" in ct_msg:
                print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)

    # Short detector (bar-close feed). Strategy B arms at close, triggers on
    # a later tick. Strategy A arms+triggers on the same bar close.
    if SHORT_ENABLED and symbol in state.short_detectors:
        sd = state.short_detectors[symbol]
        # Track session low while the detector is still hunting (pre-HOD),
        # for the retrace-50 target at exit time.
        if not getattr(sd, "_shorted", False) and getattr(sd, "_state", "IDLE") == "IDLE":
            prev_lo = state.short_pre_peak_low.get(symbol, float("inf"))
            state.short_pre_peak_low[symbol] = min(prev_lo, bar.low)
        sd_msg = sd.on_bar_close_1m(bar, vwap=vwap)
        if sd_msg:
            print(f"[{now_str} ET] {symbol} SHORT | {sd_msg}", flush=True)
        # Strategy A triggers on the bar close itself
        if (sd_msg and sd_msg.startswith("SHORT_A ENTRY") and sd.armed
                and state.open_position is None and state.open_short is None):
            _enter_short_trade(symbol, sd, vwap)

    # ── EPL: 1m bar processing ──
    if EPL_ENABLED and state.epl_registry and state.epl_registry.strategy_count > 0:
        now_et = datetime.now(ET)
        # Expiry check
        expired = state.epl_watchlist.check_expiry(now_et)
        for esym in expired:
            state.epl_registry.notify_expiry(esym)
            state.epl_watchlist.remove(esym)
            print(f"[{now_str} ET] [EPL] {esym} expired from watchlist", flush=True)

        # EPL exit management (1m bar)
        pos = state.open_position
        if pos and pos.get("setup_type", "").startswith("epl_") and pos["symbol"] == symbol:
            epl_strat = state.epl_registry.get_strategy(pos["setup_type"])
            if epl_strat:
                bar_dict = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                            "v": bar.volume, "green": bar.close >= bar.open, "vwap": vwap}
                epl_exit = epl_strat.manage_exit(symbol, bar.close, bar_dict)
                if epl_exit:
                    print(f"[{now_str} ET] [EPL] {epl_exit.strategy} EXIT {symbol} "
                          f"@ ${epl_exit.exit_price:.2f} reason={epl_exit.exit_reason}", flush=True)
                    exit_trade(symbol, epl_exit.exit_price, pos["qty"], epl_exit.exit_reason)
                    if state.epl_arbitrator:
                        epl_pnl = (epl_exit.exit_price - pos["entry"]) * pos["qty"]
                        state.epl_arbitrator.record_epl_trade_result(symbol, epl_pnl)
                    state.epl_registry.reset_all(symbol)

        # EPL entry signals (1m bar)
        if state.open_position is None and state.epl_watchlist.is_graduated(symbol):
            sq_state = state.sq_detectors[symbol]._state if (SQ_ENABLED and symbol in state.sq_detectors) else "IDLE"
            if state.epl_arbitrator.can_epl_enter(symbol, sq_state, False, now_et):
                bar_dict = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close,
                            "v": bar.volume, "green": bar.close >= bar.open, "vwap": vwap}
                signals = state.epl_registry.collect_entry_signals(symbol, bar_dict, None, None)
                best = state.epl_arbitrator.get_best_signal(signals)
                if best:
                    _enter_epl_trade(symbol, best)


def _in_tw_grace() -> bool:
    """True if the open trade is within the topping wicky grace period."""
    pos = state.open_position
    if pos is None or TW_GRACE_MIN <= 0:
        return False
    minutes_in = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
    return minutes_in < TW_GRACE_MIN


def _in_be_grace() -> bool:
    """True if the open trade is within the BE time-based grace period."""
    pos = state.open_position
    if pos is None or BE_GRACE_MIN <= 0:
        return False
    minutes_in = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
    return minutes_in < BE_GRACE_MIN


def _in_parabolic_grace(symbol: str, bar_close: float) -> bool:
    """Suppress BE exits during genuine parabolic ramps (not flash spikes)."""
    if not BE_PARABOLIC_GRACE:
        return False
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return False
    if pos["r"] <= 0 or bar_close < pos["entry"] + (BE_GRACE_MIN_R * pos["r"]):
        return False
    highs = state.recent_10s_highs.get(symbol, [])
    if len(highs) < 2:
        return False
    window = highs[-BE_GRACE_LOOKBACK:]
    new_high_count = 0
    running = window[0]
    for bh in window[1:]:
        if bh > running:
            new_high_count += 1
            running = bh
    return new_high_count >= BE_GRACE_MIN_NEW_HIGHS


def on_bar_close_10s(bar):
    """10-second bar close: candle pattern exit detection (parity with simulate.py)."""
    if not SQ_CANDLE_EXITS_ENABLED:
        return

    symbol = bar.symbol
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return
    if not pos.get("fill_confirmed", False):
        return
    if pos["setup_type"] not in ("squeeze", "mp_reentry", "continuation"):
        return

    now_str = datetime.now(ET).strftime("%H:%M:%S")

    # Ensure PatternDetector exists for this symbol
    if symbol not in state.pattern_dets:
        state.pattern_dets[symbol] = PatternDetector()

    det = state.pattern_dets[symbol]
    signals = det.update(bar.open, bar.high, bar.low, bar.close, bar.volume)
    signal_names = [s.name for s in signals]

    # Track prev 10s bar for bearish engulfing
    prev = state.prev_10s_bar.get(symbol)
    state.prev_10s_bar[symbol] = {"o": bar.open, "h": bar.high, "l": bar.low, "c": bar.close}

    # Track 10s highs for parabolic grace
    highs = state.recent_10s_highs.setdefault(symbol, [])
    highs.append(bar.high)
    if len(highs) > BE_GRACE_LOOKBACK + 5:
        state.recent_10s_highs[symbol] = highs[-(BE_GRACE_LOOKBACK + 5):]

    entry = pos["entry"]
    r = pos["r"]
    qty = pos["qty"]

    # ── Topping Wicky exit ──
    if EXIT_ON_TOPPING_WICKY and "TOPPING_WICKY" in signal_names:
        if not _in_tw_grace():
            # Profit gate: suppress TW on confirmed runners (profit >= min R)
            tw_ok = True
            if TW_MIN_PROFIT_R > 0 and r > 0:
                unrealized = bar.close - entry
                if unrealized >= TW_MIN_PROFIT_R * r:
                    tw_ok = False
                    print(f"[{now_str} ET] {symbol} TW_SUPPRESSED (profit_gate: "
                          f"${unrealized:.2f} >= {TW_MIN_PROFIT_R}R=${TW_MIN_PROFIT_R * r:.2f})", flush=True)
            if tw_ok:
                print(f"[{now_str} ET] {symbol} TOPPING_WICKY_EXIT @ {bar.close:.4f}", flush=True)
                exit_trade(symbol, bar.close, qty, "topping_wicky_exit")
                return
        else:
            print(f"[{now_str} ET] {symbol} TW_SUPPRESSED (grace period)", flush=True)

    # ── Bearish Engulfing exit ──
    if EXIT_ON_BEAR_ENGULF and prev is not None:
        if is_bearish_engulfing(bar.open, bar.high, bar.low, bar.close,
                                prev["o"], prev["h"], prev["l"], prev["c"]):
            if _in_be_grace():
                print(f"[{now_str} ET] {symbol} BE_SUPPRESSED (time grace)", flush=True)
            elif _in_parabolic_grace(symbol, bar.close):
                print(f"[{now_str} ET] {symbol} BE_SUPPRESSED (parabolic grace)", flush=True)
            else:
                # In signal mode (exit_mode=signal), BE exits are part of cascading strategy — no profit gate
                print(f"[{now_str} ET] {symbol} BEARISH_ENGULFING_EXIT @ {bar.close:.4f}", flush=True)
                exit_trade(symbol, bar.close, qty, "bearish_engulfing_exit")
                return


class _MoveArm:
    """Arm-shaped adapter so move-stack entries reuse enter_trade(), which reads
    trigger_high / stop_low / r / score / size_mult. R2 (main-bot rebuild)."""
    __slots__ = ("trigger_high", "stop_low", "r", "score", "size_mult")

    def __init__(self, trigger_high, stop_low, r, score, size_mult=1.0):
        self.trigger_high = trigger_high
        self.stop_low = stop_low
        self.r = r
        self.score = score
        self.size_mult = size_mult


def _move_firestorm_blocks(symbol: str, setup: str) -> bool:
    """FIRESTORM gate (Variant A): block entries when the prior completed 1m bar's
    tick count is below threshold (quiet bars = the bulk of losses). Ported from
    move_strike_subbot._firestorm_gate_blocks."""
    if not MOVE_FIRESTORM_GATE_ENABLED:
        return False
    bb = state.bar_builder_1m
    tc = bb.get_last_completed_bar_tick_count(symbol) if bb else 0
    if tc >= MOVE_FIRESTORM_MIN_TICKS:
        return False
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    print(f"[{now_str} ET] [MOVE] FIRESTORM_GATE_BLOCK {symbol} setup={setup} "
          f"prior_bar_ticks={tc} threshold={MOVE_FIRESTORM_MIN_TICKS}", flush=True)
    return True


def _move_exit_and_record(symbol: str, price: float, qty: int, reason: str):
    """Close a move-stack position via exit_trade and record (reason, minute) for the
    REENTRY-loss gate (R4). Used for full closes only (not the 1.5R partial)."""
    now_et = datetime.now(ET)
    state.last_exit_reason_by_symbol[symbol] = (reason, now_et.hour * 60 + now_et.minute)
    exit_trade(symbol, price, qty, reason)


def _reentry_loss_gate_blocks(symbol: str) -> bool:
    """R4 (Variant C): block a new move-stack entry within
    WB_MOVE_REENTRY_LOSS_GATE_WINDOW_MIN of a loss-class exit on the same symbol.
    Ported from move_strike_subbot (explicit loss-class prefixes only — false
    negatives self-heal next cycle; false positives silently kill winners)."""
    if not MOVE_REENTRY_LOSS_GATE_ENABLED:
        return False
    prev = state.last_exit_reason_by_symbol.get(symbol)
    if prev is None:
        return False
    reason, exit_min = prev
    now_et = datetime.now(ET)
    age = (now_et.hour * 60 + now_et.minute) - exit_min
    if 0 <= age <= MOVE_REENTRY_LOSS_GATE_WINDOW_MIN and reason.startswith(_MOVE_LOSS_EXIT_PREFIXES):
        print(f"[{now_et.strftime('%H:%M:%S')} ET] [MOVE] REENTRY_LOSS_GATE_BLOCK {symbol} "
              f"reason={reason} window_age_min={age}", flush=True)
        return True
    return False


def _halt_count_gate_blocks(symbol: str) -> bool:
    """R4 addendum (2026-06-09): avoid serially-halted names (CCTG halted 34× today).
    Halt count is knowable intraday and halt-prone names keep halting. Observe-only by
    default — logs HALT_COUNT_GATE_WOULD_BLOCK and falls through; flip
    WB_MOVE_HALT_COUNT_GATE_OBSERVE_ONLY=0 to enforce after the validation week."""
    if not MOVE_HALT_COUNT_GATE_ENABLED:
        return False
    halts = state.halt_count_today.get(symbol, 0)
    if halts < MOVE_HALT_COUNT_GATE_THRESHOLD:
        return False
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    if MOVE_HALT_COUNT_GATE_OBSERVE_ONLY:
        print(f"[{now_str} ET] [MOVE] HALT_COUNT_GATE_WOULD_BLOCK {symbol} halts={halts} "
              f"threshold={MOVE_HALT_COUNT_GATE_THRESHOLD} (OBSERVE)", flush=True)
        return False  # observe-only — fall through
    print(f"[{now_str} ET] [MOVE] HALT_COUNT_GATE_BLOCK {symbol} halts={halts} "
          f"threshold={MOVE_HALT_COUNT_GATE_THRESHOLD}", flush=True)
    return True


def maybe_enter_move_strike(symbol: str, price: float):
    """MOVE_STRIKE entry path (R2): squeeze ARM + MovementStrike intra-bar trigger.
    Faithful port of move_strike_subbot._maybe_enter, routed to the main bot's
    enter_trade() (AvailableFunds sizing + _verify_fill_with_retry). Called per tick
    from check_triggers; only acts when MOVE_STACK_ENABLED. The squeeze detector is
    the arming engine — MovementStrike confirms the move and supplies the stop.

    NOTE: REENTRY-loss gate is added in R4; fade-environment gate + stay-armed
    continuation + regime-shift firing are R2b (not yet ported)."""
    if not MOVE_STACK_ENABLED:
        return
    if state.open_position is not None:
        return
    sq = state.sq_detectors.get(symbol)
    ms = state.move_strikes.get(symbol)
    if sq is None or ms is None:
        return

    # Entry-time cutoff (WB_ENTRY_TIME_CUTOFF_ET), mirrors squeeze + sub-bot.
    now_et = datetime.now(ET)
    cutoff = os.getenv("WB_ENTRY_TIME_CUTOFF_ET", "19:30")
    try:
        _ch, _cm = (int(x) for x in cutoff.split(":")[:2])
        if now_et.hour * 60 + now_et.minute >= _ch * 60 + _cm:
            return  # past entry cutoff
    except Exception:
        pass

    # Require a squeeze arm (the move-stack's arming engine).
    if sq.armed is None:
        return

    # Feed MovementStrike this tick; only fires on an upward intra-bar anomaly.
    # ms is reset on the arm transition (on_bar_close_1m), then fed every tick
    # while armed, so its rolling average reflects post-arm bars only.
    bar_minute = now_et.hour * 60 + now_et.minute
    if not ms.update_and_check(price, bar_minute):
        return
    cons_stop = ms.get_consolidation_stop()
    if cons_stop is None or price <= cons_stop:
        return

    # FIRESTORM gate — block on quiet prior bar (Variant A, the winning variant).
    if _move_firestorm_blocks(symbol, "move_strike"):
        return
    # Halt-count gate (R4 addendum) — avoid serially-halted names.
    if _halt_count_gate_blocks(symbol):
        return
    # REENTRY-loss gate (R4) — block re-entry shortly after a loss-class exit.
    if _reentry_loss_gate_blocks(symbol):
        return

    now_str = now_et.strftime("%H:%M:%S")
    # Chase cap + below-arm filter — preserve the arm (don't consume) so price can
    # come back into range. Mirrors sub-bot:1442-1470.
    arm_price = getattr(sq.armed, "entry_price", None) or getattr(sq.armed, "trigger_high", 0.0) or 0.0
    if arm_price > 0:
        gap_above = (price - arm_price) / arm_price * 100.0
        if gap_above > MOVE_CHASE_CAP_PCT:
            print(f"[{now_str} ET] [MOVE] {symbol} CHASE-SKIP (arm preserved) "
                  f"trigger={price:.3f} arm={arm_price:.3f} gap={gap_above:.2f}%", flush=True)
            return
        if MOVE_MAX_BELOW_ARM_PCT > 0:
            below = (arm_price - price) / arm_price * 100.0
            if below > MOVE_MAX_BELOW_ARM_PCT:
                print(f"[{now_str} ET] [MOVE] {symbol} BELOW-ARM-SKIP (arm preserved) "
                      f"trigger={price:.3f} arm={arm_price:.3f} below={below:.2f}% "
                      f"(cap={MOVE_MAX_BELOW_ARM_PCT}%)", flush=True)
                return

    r = price - cons_stop
    if r <= 0:
        return
    score = float(getattr(sq.armed, "score", 0.0) or 0.0)
    print(f"[{now_str} ET] [MOVE] MOVE_STRIKE TRIGGER {symbol} @ ${price:.4f} "
          f"stop=${cons_stop:.4f} R=${r:.4f} score={score:.1f}", flush=True)
    # Route to the main bot's submission path (sizing + fill-verify + open_position).
    move_arm = _MoveArm(trigger_high=price, stop_low=cons_stop, r=r, score=score)
    enter_trade(symbol, move_arm, "move_strike")
    # Consume the arm (mirrors sub-bot:1494-1496); also clear prev-arm tracker so a
    # later re-arm correctly triggers a fresh MovementStrike reset.
    sq.armed = None
    state.move_prev_arm_state[symbol] = None


def _move_risk_guards_block() -> bool:
    """Shared entry guards for the move-stack (mirrors the daily/risk checks at the
    top of check_triggers). Used by the bar-close regime-shift path, which doesn't
    run through check_triggers. Returns True if a new entry should be blocked."""
    if state.open_position is not None:
        return True
    if MAX_DAILY_ENTRIES > 0 and state.daily_entries >= MAX_DAILY_ENTRIES:
        return True
    if BOX_ENABLED and not BOX_SIMULTANEOUS and state.box_position is not None:
        return True
    eff_max_loss = max(MAX_DAILY_LOSS, STARTING_EQUITY * 0.02) if DAILY_LOSS_SCALE else MAX_DAILY_LOSS
    if state.daily_pnl <= -eff_max_loss:
        return True
    if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return True
    return False


def maybe_fire_regime_shift(symbol: str, bar):
    """RegimeShift entry (R2b): fires on a 1m bar-close body anomaly — a parallel
    entry path to MOVE_STRIKE. Faithful port of move_strike_subbot.
    _maybe_fire_regime_shift + _open_regime_shift_position, routed to enter_trade.
    Entry = bar.close, stop = bar.low (widened by Track A's R-floor when enabled)."""
    if not MOVE_STACK_ENABLED:
        return
    if _move_risk_guards_block():
        return
    rs = state.regime_shift_detectors.get(symbol)
    if rs is None:
        return
    rs_result = rs.check_on_bar_close(bar)
    if not rs_result.get("fired"):
        return
    # require_armed — only fire on symbols that armed for MOVE_STRIKE today.
    if MOVE_REGIME_REQUIRE_ARMED and symbol not in state.regime_shift_armed_today:
        return
    # Per-symbol regime-shift entry cap.
    if state.regime_shift_entries_per_symbol.get(symbol, 0) >= MOVE_REGIME_MAX_PER_SYMBOL:
        return
    # FIRESTORM gate (quiet-bar block).
    if _move_firestorm_blocks(symbol, "regime_shift"):
        return
    # Halt-count gate (R4 addendum) — avoid serially-halted names.
    if _halt_count_gate_blocks(symbol):
        return
    # REENTRY-loss gate (R4).
    if _reentry_loss_gate_blocks(symbol):
        return
    # Entry-time cutoff (mirrors MOVE_STRIKE / squeeze).
    now_et = datetime.now(ET)
    cutoff = os.getenv("WB_ENTRY_TIME_CUTOFF_ET", "19:30")
    try:
        _ch, _cm = (int(x) for x in cutoff.split(":")[:2])
        if now_et.hour * 60 + now_et.minute >= _ch * 60 + _cm:
            return
    except Exception:
        pass
    entry = float(bar.close)
    raw_stop = float(bar.low)
    stop, r = compute_stop_with_r_floor(entry, raw_stop)  # Track A R-floor (self-gated)
    if r <= 0.01:
        return
    now_str = now_et.strftime("%H:%M:%S")
    print(f"[{now_str} ET] [MOVE] REGIME_SHIFT_TRIGGER {symbol} "
          f"body=${rs_result['body']:.4f} baseline=${rs_result['baseline']:.4f} "
          f"ratio={rs_result['ratio']:.2f} → entry=${entry:.4f} stop=${stop:.4f} R=${r:.4f}",
          flush=True)
    # Count the entry attempt (mirrors sub-bot's per-symbol cap; bumped on submit
    # rather than fill since enter_trade verifies fills asynchronously).
    state.regime_shift_entries_per_symbol[symbol] = (
        state.regime_shift_entries_per_symbol.get(symbol, 0) + 1)
    move_arm = _MoveArm(trigger_high=entry, stop_low=stop, r=r, score=99.0)
    enter_trade(symbol, move_arm, "regime_shift")


def check_triggers(symbol: str, price: float):
    """Check if any armed detector triggers on this price."""
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    is_premarket = datetime.now(ET).hour < 9 or (datetime.now(ET).hour == 9 and datetime.now(ET).minute < 30)

    # Proactively clear a stuck open_short so a stale unconfirmed slot
    # doesn't block new shorts for the 60s until periodic_position_sync.
    # Cheap (short-circuits when fill_confirmed or recent).
    check_stale_open_short()

    # Already in a position — no new entries
    if state.open_position is not None:
        return

    # PDT guard — max entries per day (conserve day-trade slots under $25K)
    if MAX_DAILY_ENTRIES > 0 and state.daily_entries >= MAX_DAILY_ENTRIES:
        return

    # Box position blocks momentum entry (unless simultaneous allowed)
    if BOX_ENABLED and not BOX_SIMULTANEOUS and state.box_position is not None:
        return

    # Daily risk check
    if DAILY_LOSS_SCALE:
        effective_max_loss = max(MAX_DAILY_LOSS, STARTING_EQUITY * 0.02)
    else:
        effective_max_loss = MAX_DAILY_LOSS
    if state.daily_pnl <= -effective_max_loss:
        return
    if state.consecutive_losses >= MAX_CONSECUTIVE_LOSSES:
        return

    # Move-stack trigger (MOVE_STRIKE entry, R2). Gated; consumes the squeeze arm +
    # MovementStrike. In the rebuild config (WB_SQUEEZE_ENABLED=0) this is the only
    # entry path; the squeeze block below is skipped. Runs after the same daily/risk
    # guards above as squeeze.
    if MOVE_STACK_ENABLED and symbol in state.move_strikes:
        maybe_enter_move_strike(symbol, price)
        if state.open_position is not None:
            return  # entered — don't also evaluate squeeze/WB on the same tick

    # Squeeze trigger (priority)
    if SQ_ENABLED and symbol in state.sq_detectors:
        sq = state.sq_detectors[symbol]

        # --- Tick-level arming (WB_TICK_LEVEL_ARM, 2026-05-19) ---
        # Evaluate prime/arm mid-bar against the in-progress bar BEFORE
        # checking on_trade_price. If the conditions are true on this tick,
        # detector transitions IDLE/PRIMED → ARMED on this tick instead of
        # at bar close. Then on_trade_price below fires ENTRY SIGNAL on the
        # same tick when the price crosses trigger_high. This eliminates the
        # MTVA/RUBI gap-up entry where bar-close arming arrived $0.15-$0.27
        # past the intended arm price.
        if sq.armed is None and not sq._in_trade and state.bar_builder_1m is not None:
            in_progress = state.bar_builder_1m.get_in_progress_bar(symbol)
            if in_progress is not None:
                vwap = state.bar_builder_1m.get_vwap(symbol)
                tick_count = state.bar_builder_1m.get_tick_count_in_bar(symbol)
                # elapsed seconds since bar start; use now() rather than the
                # tick's ts (we don't have ts here, and the call follows the
                # bar builder update by microseconds — close enough).
                try:
                    elapsed_sec = (
                        datetime.now(timezone.utc) - in_progress.start_utc
                    ).total_seconds()
                except Exception:
                    elapsed_sec = 0.0
                tick_arm_msg = sq.try_arm_on_tick(
                    running_open=in_progress.open,
                    running_high=in_progress.high,
                    running_low=in_progress.low,
                    running_close=in_progress.close,
                    running_vol=float(in_progress.volume),
                    tick_count=int(tick_count),
                    elapsed_sec=float(elapsed_sec),
                    vwap=vwap,
                    bar_start_utc=in_progress.start_utc,
                )
                if tick_arm_msg:
                    print(f"[{now_str} ET] {symbol} SQ | {tick_arm_msg}", flush=True)

        armed_before = sq.armed
        sq_msg = sq.on_trade_price(price, is_premarket=is_premarket)
        if sq_msg and "SQ_SEED_GATE" in sq_msg:
            # Detector suppressed a stale entry from seed replay — log it
            print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            return
        if sq_msg and "ENTRY SIGNAL" in sq_msg and armed_before:
            print(f"[{now_str} ET] {symbol} SQ | {sq_msg}", flush=True)
            # Latency diagnostic — create the per-signal record at signal
            # detection moment, before any sizing or order submission. Threaded
            # through enter_trade → _verify_fill_with_retry, finalized at the
            # terminal state. Squeeze is the ONLY strategy this is wired into
            # (per directive scope: "main bot only — squeeze path").
            _lat_record = None
            try:
                if LATENCY_DIAGNOSTIC_ENABLED:
                    _lat_record = _new_squeeze_latency_record(symbol, price, armed_before)
            except Exception:
                _lat_record = None
            enter_trade(symbol, armed_before, "squeeze", latency_record=_lat_record)
            sq.notify_trade_opened()
            return

    # Short trigger (Strategy B + C fire on tick; A fires at bar close).
    # Short is additive — squeeze keeps priority on the same symbol/tick.
    if SHORT_ENABLED and symbol in state.short_detectors and state.open_short is None:
        sd = state.short_detectors[symbol]
        armed_sd = sd.armed
        sd_msg = sd.on_trade_price(price)
        if sd_msg and "ENTRY SIGNAL" in sd_msg and armed_sd:
            print(f"[{now_str} ET] {symbol} SHORT | {sd_msg}", flush=True)
            _vwap = state.bar_builder_1m.get_vwap(symbol) if state.bar_builder_1m else 0
            _enter_short_trade(symbol, sd, _vwap, trigger_price=price)
            return

    # Continuation trigger (after SQ, before MP)
    if CT_ENABLED and symbol in state.ct_detectors:
        ct = state.ct_detectors[symbol]
        ct_armed_before = ct.armed
        if ct_armed_before is not None:
            # SQ-priority gate: defer CT if SQ is actively hunting
            ct_deferred = False
            if SQ_ENABLED and symbol in state.sq_detectors:
                sq = state.sq_detectors[symbol]
                if sq._state != "IDLE" or sq._in_trade:
                    print(f"[{now_str} ET] {symbol} CT | DEFERRED (SQ priority: state={sq._state})", flush=True)
                    ct_deferred = True
            if not ct_deferred:
                ct_msg = ct.on_trade_price(price, is_premarket=is_premarket)
                if ct_msg and "ENTRY SIGNAL" in ct_msg:
                    print(f"[{now_str} ET] {symbol} CT | {ct_msg}", flush=True)
                    enter_trade(symbol, ct_armed_before, "continuation")
                    return

    # MP trigger (standalone or V2 re-entry)
    if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
        mp = state.mp_detectors[symbol]
        armed_before = mp.armed
        mp_msg = mp.on_trade_price(price, is_premarket=is_premarket)
        if mp_msg and "ENTRY SIGNAL" in mp_msg and armed_before:
            _mp_setup_type = getattr(armed_before, 'setup_type', 'micro_pullback')
            # Block standalone MP entries if MP_ENABLED is off (only allow mp_reentry from V2)
            if not MP_ENABLED and _mp_setup_type != "mp_reentry":
                return
            # SQ-priority gate: defer MP V2 if SQ is actively hunting
            if _mp_setup_type == "mp_reentry" and SQ_ENABLED and symbol in state.sq_detectors:
                sq = state.sq_detectors[symbol]
                if sq._state != "IDLE" or sq._in_trade:
                    print(f"[{now_str} ET] {symbol} MP_V2 | DEFERRED (SQ priority: state={sq._state})", flush=True)
                    return
            print(f"[{now_str} ET] {symbol} MP | {mp_msg}", flush=True)
            enter_trade(symbol, armed_before, _mp_setup_type)
            return


# ══════════════════════════════════════════════════════════════════════
# Order Execution
# ══════════════════════════════════════════════════════════════════════

# ─── Alpaca latency diagnostic helpers (Phase 1) ────────────────────────
# Every callsite below is wrapped in try/except. A failure in diagnostic code
# MUST NOT prevent an order from being placed or a retry from running. This
# is the bot's primary directive: capture data without altering behavior.

def _alpaca_snapshot(symbol: str):
    """Fetch Alpaca's current (bid, ask, last) and quote timestamp + the round-
    trip API latency in ms.

    Returns: (bid, ask, last, quote_ts_iso, api_latency_ms)
    On any failure or when diagnostic/data-client is unavailable, every field
    is None. Never raises — callers always get a 5-tuple.
    """
    if not LATENCY_DIAGNOSTIC_ENABLED or state.alpaca_data_client is None:
        return (None, None, None, None, None)
    try:
        # Imports are deferred so a missing alpaca-data install doesn't blow up
        # module import. They're cheap after the first call.
        from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest
        t0 = time.perf_counter()
        q_resp = state.alpaca_data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol)
        )
        t_resp = state.alpaca_data_client.get_stock_latest_trade(
            StockLatestTradeRequest(symbol_or_symbols=symbol)
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)
        q = q_resp.get(symbol) if isinstance(q_resp, dict) else None
        t = t_resp.get(symbol) if isinstance(t_resp, dict) else None
        bid = float(q.bid_price) if q is not None and getattr(q, "bid_price", None) else None
        ask = float(q.ask_price) if q is not None and getattr(q, "ask_price", None) else None
        last = float(t.price) if t is not None and getattr(t, "price", None) else None
        ts = None
        if q is not None and getattr(q, "timestamp", None) is not None:
            try:
                ts = q.timestamp.isoformat()
            except Exception:
                ts = str(q.timestamp)
        return (bid, ask, last, ts, latency_ms)
    except Exception as e:
        # Never block on Alpaca quote-call failure
        try:
            print(f"  [ALPACA_QUOTE_FAIL] {symbol}: {e}", flush=True)
        except Exception:
            pass
        return (None, None, None, None, None)


def _write_latency_record(record: dict) -> None:
    """Append a JSONL record to logs/<today>_latency_diagnostic.jsonl.
    Failures are logged but never raised."""
    if not LATENCY_DIAGNOSTIC_ENABLED:
        return
    try:
        today = datetime.now(ET).strftime("%Y-%m-%d")
        log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        try:
            os.makedirs(log_dir, exist_ok=True)
        except Exception:
            pass
        path = os.path.join(log_dir, f"{today}_latency_diagnostic.jsonl")
        with open(path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except Exception as e:
        try:
            print(f"  [LATENCY_DIAG_WRITE_FAIL] {e}", flush=True)
        except Exception:
            pass


def _new_squeeze_latency_record(symbol: str, signal_price_ibkr: float, armed) -> dict:
    """Create the initial diagnostic record at squeeze ENTRY SIGNAL moment.
    Populates the fields known at signal-detection time; later moments fill in
    the rest. Returns the dict (mutate in place as the order progresses).
    Pure helper — safe to call from inside check_triggers."""
    now = datetime.now(ET)
    try:
        score = float(getattr(armed, "score", 0.0) or 0.0)
    except Exception:
        score = 0.0
    try:
        r_val = float(getattr(armed, "r", 0.0) or 0.0)
    except Exception:
        r_val = 0.0
    return {
        "symbol": symbol,
        "setup_type": "squeeze",
        "signal_time_ibkr_et": now.isoformat(),
        "signal_price_ibkr": signal_price_ibkr,
        "alpaca_bid_at_signal": None,
        "alpaca_ask_at_signal": None,
        "alpaca_last_at_signal": None,
        "alpaca_quote_timestamp": None,
        "alpaca_quote_api_latency_ms": None,
        "limit_price_submitted": None,
        "order_submit_time": None,
        "order_ack_time": None,
        "order_ack_latency_ms": None,
        "ibkr_price_at_signal": signal_price_ibkr,
        "ibkr_price_at_order_submit": None,
        "ibkr_price_at_order_ack": None,
        "ibkr_price_at_terminal": None,
        "terminal_state": None,
        "terminal_time": None,
        "fill_qty": 0,
        "fill_price": None,
        "retries_attempted": 0,
        "armed_score": score,
        "armed_r": r_val,
        "armed_qty": None,        # filled in once sizing computes
        "no_order_reason": None,
    }


def _finalize_latency_record(record: dict, *, terminal_state: str,
                             fill_qty: int = 0, fill_price=None,
                             retries_attempted: int = 0,
                             ibkr_price_at_terminal=None,
                             no_order_reason: str = None) -> None:
    """Stamp terminal fields onto the diagnostic record and write it. Always
    wrapped in try/except by callers; this helper itself never raises."""
    try:
        record["terminal_state"] = terminal_state
        record["terminal_time"] = datetime.now(ET).isoformat()
        if fill_qty:
            record["fill_qty"] = int(fill_qty)
        if fill_price is not None:
            try:
                record["fill_price"] = float(fill_price)
            except Exception:
                record["fill_price"] = fill_price
        record["retries_attempted"] = int(retries_attempted)
        if ibkr_price_at_terminal is not None:
            try:
                record["ibkr_price_at_terminal"] = float(ibkr_price_at_terminal)
            except Exception:
                record["ibkr_price_at_terminal"] = ibkr_price_at_terminal
        if no_order_reason is not None:
            record["no_order_reason"] = no_order_reason
        _write_latency_record(record)
    except Exception as e:
        try:
            print(f"  [LATENCY_DIAG_FINALIZE_FAIL] {e}", flush=True)
        except Exception:
            pass


# ─── Phase 3 (DORMANT) — Alpaca-aware limit price helper ─────────────────
# DORMANT until directive Outcome B activates this. Function exists so the
# Friday post-diagnostic activation is a single env-var flip
# (WB_ALPACA_AWARE_LIMITS=1). NOT wired into any caller yet — flipping the env
# var alone is a no-op until a caller is added in a follow-up commit.

def compute_alpaca_aware_limit(symbol: str, signal_price: float, side: str,
                                buffer_pct: float = 0.005) -> float:
    """Return a limit price calibrated to Alpaca's current view of the market.

    For BUY:  max(signal_price × (1+buffer), alpaca_ask × (1+buffer))
    For SELL: min(signal_price × (1-buffer), alpaca_bid × (1-buffer))

    Falls back to base_limit = signal_price ± buffer when:
      • WB_ALPACA_AWARE_LIMITS is off (default)
      • state.alpaca_data_client is None
      • Alpaca quote call fails / times out
      • Alpaca quote is >5% divergent from signal_price (likely stale/bad data —
        we don't want to chase a phantom move).

    Returns a price rounded to 2 decimal places.

    DORMANT until directive Outcome B activates this — function exists so the
    Friday post-diagnostic activation is a single env-var flip
    (WB_ALPACA_AWARE_LIMITS=1) + a one-line wire-up in enter_trade()."""
    side_u = side.upper()
    if side_u == "BUY":
        base_limit = round(signal_price * (1 + buffer_pct), 2)
    else:
        base_limit = round(signal_price * (1 - buffer_pct), 2)

    if not ALPACA_AWARE_LIMITS_ENABLED or state.alpaca_data_client is None:
        return base_limit

    try:
        from alpaca.data.requests import StockLatestQuoteRequest
        q_resp = state.alpaca_data_client.get_stock_latest_quote(
            StockLatestQuoteRequest(symbol_or_symbols=symbol)
        )
        q = q_resp.get(symbol) if isinstance(q_resp, dict) else None
        if q is None:
            return base_limit
        if side_u == "BUY":
            alpaca_ref = float(q.ask_price) if getattr(q, "ask_price", None) else None
        else:
            alpaca_ref = float(q.bid_price) if getattr(q, "bid_price", None) else None
        if alpaca_ref is None or signal_price <= 0:
            return base_limit
        # Divergence guard: if Alpaca's view is wildly different from IBKR,
        # the Alpaca quote is likely stale or broken — use base_limit.
        if abs(alpaca_ref - signal_price) / signal_price > 0.05:
            try:
                print(f"  [ALPACA_QUOTE_DIVERGENT] {symbol}: alpaca_ref={alpaca_ref:.4f} "
                      f"signal={signal_price:.4f} (>5% gap) — using base limit", flush=True)
            except Exception:
                pass
            return base_limit
        if side_u == "BUY":
            return round(max(base_limit, alpaca_ref * (1 + buffer_pct)), 2)
        return round(min(base_limit, alpaca_ref * (1 - buffer_pct)), 2)
    except Exception as e:
        try:
            print(f"  [ALPACA_AWARE_FAIL] {symbol}: {e} — using base limit", flush=True)
        except Exception:
            pass
        return base_limit


def _entry_time_allowed(now_et: datetime = None) -> tuple[bool, str]:
    """User directive 2026-05-14: no new entries after WB_ENTRY_TIME_CUTOFF_ET.
    Mirrors H#14 pre-11 ET block on the other end. FCHL 2026-05-14 19:58 ET
    filled 90s before extended-hours close — no time for the bot to manage
    the position before scheduled session-end shutdown at 20:05 MT.

    Returns (allowed, reason). On parse failure of the env var, fail-OPEN
    (cutoff disabled) and log a warning, so a typo doesn't silently block."""
    try:
        hh, mm = ENTRY_TIME_CUTOFF_ET.strip().split(":")
        cutoff = (int(hh), int(mm))
    except Exception:
        print(f"⚠️  WB_ENTRY_TIME_CUTOFF_ET bad value={ENTRY_TIME_CUTOFF_ET!r} — "
              f"cutoff disabled (fail-open)", flush=True)
        return True, "cutoff_unparseable"
    now_et = now_et or datetime.now(ET)
    if (now_et.hour, now_et.minute) >= cutoff:
        return False, f"entry_after_cutoff (now={now_et.strftime('%H:%M')} ET >= {ENTRY_TIME_CUTOFF_ET} ET)"
    return True, "ok"


def _presubmit_bp_check(symbol: str, qty: int, limit_price: float,
                        log_prefix: str = "") -> tuple[bool, str]:
    """Pre-submit buying-power check (Cowork directive 2026-05-14_SQUEEZE_FILL_
    RATE_FIX §3). Blocks BUY submits when available BP < notional + 5% safety
    pad. Catches the Reg-T overnight-margin rejection class that bit ATRA 5/7.

    Best-effort: if broker.get_buying_power() raises, returns (True, "bp_
    unknown") to fail-open. Per directive: false positives are detectable
    and recoverable; false negatives are the existing behavior we're trying
    to reduce."""
    if not PRESUBMIT_BP_CHECK_ENABLED:
        return True, "disabled"
    if not state.broker:
        return True, "no_broker"
    try:
        bp = state.broker.get_buying_power()
    except Exception as e:
        print(f"  {log_prefix}BP_CHECK: get_buying_power failed: {e!r} — fail-open",
              flush=True)
        return True, "bp_unknown"
    notional = qty * limit_price
    required = notional * 1.05  # 5% safety pad for slippage between submit/fill
    if bp < required:
        return False, (f"insufficient_bp (bp=${bp:,.2f} < required=${required:,.2f}, "
                       f"notional=${notional:,.2f})")
    return True, f"ok (bp=${bp:,.2f}, notional=${notional:,.2f})"


def _broker_qty_held(symbol: str, settle_sec: float = 0.0) -> tuple:
    """Return (qty, avg_cost) the broker currently holds LONG for `symbol`
    (0, 0.0 if flat/short). Best-effort — returns (0, 0.0) on any broker error
    so a reconcile failure can never crash the entry thread. `settle_sec` lets
    callers wait briefly for a just-cancelled order's partial fill to post."""
    if settle_sec > 0:
        time.sleep(settle_sec)
    try:
        for p in state.broker.get_positions():
            if p.symbol == symbol and int(p.qty) > 0:
                return int(p.qty), float(p.avg_entry_price)
    except Exception as e:
        print(f"  RECONCILE: get_positions({symbol}) failed: {e!r}", flush=True)
    return 0, 0.0


def _reconcile_entry_position(symbol: str, position_attr: str, reason: str,
                              seed: dict = None, settle_sec: float = 1.0) -> bool:
    """Sync the bot's position record to the broker's ACTUAL holding for
    `symbol`. Called at every terminal of the entry-retry sequence so partial
    fills accumulated across retries can never become an unrecorded orphan.

    If the broker holds shares: keep + manage them (qty/entry from broker truth,
    stop re-derived from avg_fill − r, fill_confirmed=True, persisted) so the
    normal exit path protects them. If the broker is flat: clear the record.
    `seed` is the pre-entry position snapshot — used to recover risk params
    (r/stop/score/setup_type) when the core already cleared the live record on a
    terminal. Returns True if shares were kept. Gated by WB_ENTRY_RECONCILE_FILLS."""
    held, avg = _broker_qty_held(symbol, settle_sec=settle_sec)
    # Live record if still present; otherwise fall back to the pre-entry seed so
    # r/stop/setup_type survive the core's terminal clear.
    pos = getattr(state, position_attr) or seed
    if held > 0:
        r = (pos or {}).get("r")
        entry_px = avg if avg > 0 else (pos or {}).get("entry", avg)
        new_stop = (entry_px - r) if (r is not None and entry_px) else (pos or {}).get("stop")
        base = dict(pos) if isinstance(pos, dict) else {}
        base.update({
            "symbol": symbol,
            "qty": held,
            "entry": entry_px,
            "stop": new_stop,
            "peak": max(base.get("peak", entry_px) or entry_px, entry_px),
            "fill_confirmed": True,
        })
        setattr(state, position_attr, base)
        state.pending_order = None
        print(f"  RECONCILE [{reason}]: {symbol} broker holds {held} sh @ "
              f"${entry_px:.4f} — keeping + managing (stop=${(new_stop or 0):.4f})",
              flush=True)
        if position_attr == "open_position":
            try:
                persist_open_trades()
            except Exception as e:
                print(f"  RECONCILE: persist failed for {symbol}: {e!r}", flush=True)
        return True
    # Broker flat — genuinely no fill; clear any stale record.
    setattr(state, position_attr, None)
    state.pending_order = None
    return False


def _verify_fill_with_retry(symbol, qty, r, initial_order_id, initial_limit,
                             original_limit, position_attr, log_prefix="",
                             latency_record: dict = None, score: float = 0.0):
    """Entry fill-verification entry point. Delegates to the retry-loop core,
    then (when WB_ENTRY_RECONCILE_FILLS=1) ALWAYS reconciles the bot's position
    to the broker's actual holding in a finally — so however the loop exits
    (full fill, partial+cancel, reject, timeout, chase-abort), the recorded
    position matches the broker and no partial fill is left as a future orphan.
    """
    # Snapshot risk params before the core runs — the core clears the live
    # record on a terminal, so the finally reconcile needs this to keep a stop.
    seed = dict(getattr(state, position_attr) or {})
    try:
        _verify_fill_with_retry_core(
            symbol, qty, r, initial_order_id, initial_limit, original_limit,
            position_attr, log_prefix=log_prefix, latency_record=latency_record,
            score=score,
        )
    finally:
        if ENTRY_RECONCILE_FILLS:
            try:
                _reconcile_entry_position(symbol, position_attr, "post_entry_sync",
                                          seed=seed)
            except Exception as e:
                print(f"  RECONCILE: post-entry sync failed for {symbol}: {e!r}",
                      flush=True)


def _verify_fill_with_retry_core(symbol, qty, r, initial_order_id, initial_limit,
                             original_limit, position_attr, log_prefix="",
                             latency_record: dict = None, score: float = 0.0):
    """Poll broker for fill. On timeout: cancel + reprice to current market +
    resubmit, up to ENTRY_MAX_RETRIES times. Aborts if market runs above
    original_limit × (1 + effective_chase_pct/100). See directive
    2026-04-15_directive_entry_slippage_retry.md.

    Chase cap is score-gated (Cowork directive 2026-05-14_SQUEEZE_FILL_RATE_FIX
    §2): score >= ENTRY_SCORE_HIGH_THRESHOLD uses ENTRY_MAX_CHASE_PCT_HIGH,
    else ENTRY_MAX_CHASE_PCT_LOW. Default 0 score → low cap (conservative).

    Partial fills (2026-06-17): when WB_ENTRY_RECONCILE_FILLS=1, each retry
    resubmits only the REMAINDER (qty − broker_held) rather than the full qty,
    so fills across retries can't over-accumulate. The caller's finally then
    reconciles the recorded position to the broker holding.
    """
    cur_order_id = initial_order_id
    cur_limit = initial_limit
    attempt = 0
    # Most-recently-known terminal status string from the broker, so the chase-
    # cap / max-retries paths can distinguish a clean cancel from a reject.
    last_terminal_status = None
    while True:
        deadline = time.time() + ENTRY_RETRY_TIMEOUT_SEC
        filled = False
        terminal = False
        while time.time() < deadline:
            o = state.broker.get_order_status(cur_order_id)
            if o is not None:
                if o.status == STATUS_FILLED:
                    actual_price = o.filled_avg_price
                    actual_qty = o.filled_qty
                    pos = getattr(state, position_attr)
                    if pos and pos.get("order_id") == cur_order_id:
                        pos["entry"] = actual_price
                        pos["qty"] = actual_qty
                        if "peak" in pos:
                            pos["peak"] = max(pos["peak"], actual_price)
                        if "stop" in pos and r is not None:
                            pos["stop"] = actual_price - r
                        pos["fill_confirmed"] = True
                        state.pending_order = None
                        print(f"  {log_prefix}FILL: {symbol} @ ${actual_price:.4f} qty={actual_qty}"
                              + (f" (after {attempt} retries)" if attempt > 0 else ""),
                              flush=True)
                        # Persist managed-trade state on fill confirmation.
                        # Reactive-exit architecture: manage_exit() is the
                        # protection layer, so fill-confirmed = protected.
                        # Box positions are not persisted in v1 (deferred).
                        if position_attr == "open_position":
                            persist_open_trades()
                    # Latency diagnostic — fill terminal state.
                    try:
                        if latency_record is not None:
                            _finalize_latency_record(
                                latency_record,
                                terminal_state="fill" if actual_qty == latency_record.get("armed_qty", actual_qty)
                                else "partial_fill",
                                fill_qty=actual_qty, fill_price=actual_price,
                                retries_attempted=attempt,
                                ibkr_price_at_terminal=state.last_tick_price.get(symbol),
                            )
                    except Exception:
                        pass
                    filled = True
                    break
                if o.status in (STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED):
                    print(f"  {log_prefix}ORDER {o.status.upper()}: {symbol} {cur_order_id}", flush=True)
                    last_terminal_status = o.status
                    terminal = True
                    break
            time.sleep(0.5)

        if filled:
            return
        if terminal:
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            # Latency diagnostic — broker-side terminal (cancel/expire/reject).
            try:
                if latency_record is not None:
                    _finalize_latency_record(
                        latency_record,
                        terminal_state=last_terminal_status or "cancelled",
                        retries_attempted=attempt,
                        ibkr_price_at_terminal=state.last_tick_price.get(symbol),
                    )
            except Exception:
                pass
            return

        # Timed out — decide whether to retry
        if not ENTRY_RETRY_ENABLED or attempt >= ENTRY_MAX_RETRIES:
            print(f"  {log_prefix}ORDER TIMEOUT: cancelling {cur_order_id}"
                  + (f" after {attempt} retries" if attempt > 0 else ""),
                  flush=True)
            state.broker.cancel_order(cur_order_id)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            # Latency diagnostic — timeout (no fill within retries budget).
            try:
                if latency_record is not None:
                    _finalize_latency_record(
                        latency_record,
                        terminal_state="timeout",
                        retries_attempted=attempt,
                        ibkr_price_at_terminal=state.last_tick_price.get(symbol),
                    )
            except Exception:
                pass
            return

        # Retry: cancel current, reprice to current market, resubmit
        state.broker.cancel_order(cur_order_id)
        time.sleep(0.3)

        cur_price = state.last_tick_price.get(symbol, cur_limit) or cur_limit
        effective_chase_pct = (
            ENTRY_MAX_CHASE_PCT_HIGH
            if score >= ENTRY_SCORE_HIGH_THRESHOLD
            else ENTRY_MAX_CHASE_PCT_LOW
        )
        max_chase_price = original_limit * (1 + effective_chase_pct / 100.0)
        if cur_price > max_chase_price:
            print(f"  {log_prefix}ORDER TIMEOUT: {symbol} market ${cur_price:.2f} exceeds max chase "
                  f"${max_chase_price:.2f} ({effective_chase_pct}% above original ${original_limit:.2f}, "
                  f"score={score:.1f}) — giving up",
                  flush=True)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            # Latency diagnostic — chase-cap abort.
            try:
                if latency_record is not None:
                    _finalize_latency_record(
                        latency_record,
                        terminal_state="chase_cap_aborted",
                        retries_attempted=attempt,
                        ibkr_price_at_terminal=cur_price,
                    )
            except Exception:
                pass
            return

        slip = _entry_slippage_for(cur_price)
        new_limit = round(cur_price + slip, 2)
        attempt += 1
        # Size the retry to the REMAINDER (qty - already filled at broker) so
        # partial fills from prior attempts don't compound into an oversized
        # position. If prior partials already cover the full qty, stop and let
        # the caller's finally reconcile record them. Gated.
        submit_qty = qty
        if ENTRY_RECONCILE_FILLS:
            held, _avg = _broker_qty_held(symbol)
            remaining = qty - held
            if remaining <= 0:
                print(f"  {log_prefix}RECONCILE: {symbol} already filled {held}/{qty} "
                      f"across retries — not resubmitting, finalizing", flush=True)
                return
            if held > 0:
                print(f"  {log_prefix}RECONCILE: {symbol} {held}/{qty} filled so far "
                      f"— retry sizes remainder {remaining}", flush=True)
            submit_qty = remaining
        print(f"  {log_prefix}RETRY {attempt}/{ENTRY_MAX_RETRIES}: {symbol} market=${cur_price:.2f} "
              f"new_limit=${new_limit:.2f} (slip=${slip:.3f}) qty={submit_qty}", flush=True)

        try:
            new_order = state.broker.submit_limit(symbol, submit_qty, "BUY", new_limit)
            prev_id = cur_order_id
            cur_order_id = new_order.order_id
            cur_limit = new_limit
            print(f"  {log_prefix}BROKER ORDER: {cur_order_id} BUY {qty} {symbol} @ ${new_limit:.2f} (retry)", flush=True)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == prev_id:
                pos["order_id"] = cur_order_id
                pos["entry"] = new_limit
            if state.pending_order:
                state.pending_order["order_id"] = cur_order_id
                state.pending_order["placed_time"] = datetime.now(ET)
        except Exception as e:
            print(f"  {log_prefix}RETRY SUBMIT FAILED: {e}", flush=True)
            pos = getattr(state, position_attr)
            if pos and pos.get("order_id") == cur_order_id:
                setattr(state, position_attr, None)
                state.pending_order = None
            # Latency diagnostic — retry submit failed (treat as no_order tail).
            try:
                if latency_record is not None:
                    _finalize_latency_record(
                        latency_record,
                        terminal_state="rejected",
                        retries_attempted=attempt,
                        ibkr_price_at_terminal=state.last_tick_price.get(symbol),
                        no_order_reason=f"retry_submit_failed: {e}",
                    )
            except Exception:
                pass
            return


def enter_trade(symbol: str, armed, setup_type: str, latency_record: dict = None):
    """Place entry order via IBKR.

    latency_record (Phase 1 diagnostic): if not None, this dict is mutated
    in-place with submit/ack timestamps + Alpaca snapshot, then passed into
    the fill-verify thread which finalizes the terminal state. Squeeze entries
    are the only path that currently threads this in (per directive scope).
    """
    if state.entry_halt_active:
        print(f"  SKIP {symbol}: entry halt active ({state.entry_halt_reason})", flush=True)
        # Latency diagnostic — entry halted by reconcile-orphan safety.
        try:
            if latency_record is not None:
                _finalize_latency_record(
                    latency_record, terminal_state="no_order",
                    no_order_reason=f"entry_halt:{state.entry_halt_reason}",
                )
        except Exception:
            pass
        return
    # Plan filters (sub-bot parity): time-window block + per-symbol loss-lockout.
    if _strategy_filters_block(symbol, setup_type):
        try:
            if latency_record is not None:
                _finalize_latency_record(latency_record, terminal_state="no_order",
                                         no_order_reason="strategy_filter_block")
        except Exception:
            pass
        return
    entry = armed.trigger_high
    stop = armed.stop_low
    r = armed.r
    score = armed.score
    size_mult = getattr(armed, 'size_mult', 1.0)

    effective_min_r = max(MIN_R, MIN_ABSOLUTE_R)
    if r <= 0 or r < effective_min_r:
        floor_source = "abs_floor" if MIN_ABSOLUTE_R > MIN_R and r >= MIN_R else "min_r"
        print(f"  SKIP: R={r:.4f} < floor {effective_min_r:.4f} ({floor_source}) "
              f"reason=R_BELOW_FLOOR", flush=True)
        try:
            if latency_record is not None:
                _finalize_latency_record(
                    latency_record, terminal_state="no_order",
                    no_order_reason=f"R_BELOW_FLOOR: R={r:.4f} < {effective_min_r:.4f}",
                )
        except Exception:
            pass
        return

    # Dynamic equity-based risk: 2.5% of current equity
    current_equity = STARTING_EQUITY + state.daily_pnl  # STARTING_EQUITY is set from IBKR NetLiquidation at startup
    risk_dollars = max(50, current_equity * RISK_PCT)

    # Size calculation. SCALE_NOTIONAL reads actual buying power from the
    # broker and caps at BUYING_POWER_PCT of it. Fixed mode uses MAX_NOTIONAL.
    if SCALE_NOTIONAL:
        broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2
        effective_notional = broker_bp * BUYING_POWER_PCT
    else:
        effective_notional = MAX_NOTIONAL
    qty = int(math.floor(risk_dollars / r))
    qty_notional = int(math.floor(effective_notional / max(entry, 0.01)))
    qty = min(qty, qty_notional, MAX_SHARES)
    # 70%-equity sizing override (sub-bot parity): each entry = EQUITY_PCT of
    # current equity (no leverage). Replaces risk/notional sizing when enabled.
    if EQUITY_PCT_SIZING > 0 and entry > 0 and current_equity > 0:
        qty = min(int((EQUITY_PCT_SIZING * current_equity) / entry), MAX_SHARES)

    notional = qty * entry
    print(f"  Sizing: equity=${current_equity:,.0f} risk=${risk_dollars:,.0f} "
          f"qty={qty} notional=${notional:,.0f}" +
          (f" (BP {BUYING_POWER_PCT*100:.0f}% of ${broker_bp:,.0f} = max ${effective_notional:,.0f})" if SCALE_NOTIONAL else ""),
          flush=True)

    if size_mult < 1.0:
        # qty=1 floor removed 2026-05-18 (SBFM incident, §7+§13 of incident report).
        # Previously max(1, ...) papered over BP=$0/probe-rounding-to-zero by
        # firing a 1-share placebo order. Now zero is honestly reported and
        # caught by the qty<=0 skip below. Visibility comes from broker.py's
        # BP_FETCH_FAIL log (commit 27f54f8).
        qty = int(math.floor(qty * size_mult))

    if qty <= 0:
        print(f"  SKIP: qty={qty} after sizing (size_mult={size_mult:.2f}) — "
              f"likely BP=$0 or probe-rounded-to-zero", flush=True)
        try:
            if latency_record is not None:
                latency_record["armed_qty"] = 0
                _finalize_latency_record(
                    latency_record, terminal_state="no_order",
                    no_order_reason="qty_zero",
                )
        except Exception:
            pass
        return

    # Latency diagnostic — record sized qty + Alpaca snapshot pre-submit.
    # All diagnostic work is in try/except so a failure here cannot block the
    # order. The Alpaca snapshot call adds ~30-100ms of latency to the submit
    # path; that's part of what we're measuring (intentional per directive).
    try:
        if latency_record is not None:
            latency_record["armed_qty"] = int(qty)
            _bid, _ask, _last, _qts, _alat = _alpaca_snapshot(symbol)
            latency_record["alpaca_bid_at_signal"] = _bid
            latency_record["alpaca_ask_at_signal"] = _ask
            latency_record["alpaca_last_at_signal"] = _last
            latency_record["alpaca_quote_timestamp"] = _qts
            latency_record["alpaca_quote_api_latency_ms"] = _alat
    except Exception:
        pass

    # Place limit order with dynamic slippage. Basis is max(arm, live_tape):
    # on a clean trigger (tape ≈ arm), this is the arm price (original
    # behavior). On a gap-up trigger (tape already above arm), use the live
    # tape so the limit lands at a price the stock is actually for sale at
    # rather than $0.08-0.16 below where the trigger-firing tick actually
    # printed. 2026-05-19 fix per MTVA/RUBI missed-fills investigation.
    live_tape = state.last_tick_price.get(symbol)
    if not live_tape or live_tape <= 0:
        live_tape = entry
    basis = max(entry, live_tape)
    initial_slip = _entry_slippage_for(basis)
    base_limit = round(basis + initial_slip, 2)
    # Alpaca-aware limit (activated 2026-05-22 per p0_go_live_stack):
    # widens to max(base, alpaca_ask × 1.005) when WB_ALPACA_AWARE_LIMITS=1.
    # Falls back to base on stale/divergent Alpaca quotes (5% guard).
    # Today's LFS 07:09:41 case: IBKR $4.39 / Alpaca ASK $4.45 (1.4% gap) →
    # base would have been $4.44, Alpaca-aware widens to $4.47.
    aware_limit = compute_alpaca_aware_limit(symbol, basis, "BUY")
    limit_price = max(aware_limit, base_limit)
    initial_slip = round(limit_price - basis, 4)
    original_limit = limit_price  # chase-cap is now relative to the price we
                                   # actually submitted at, not the arm

    gap_pct = (basis - entry) / entry if entry > 0 else 0.0
    gap_note = f" gap={gap_pct:.1%} above arm ${entry:.2f}" if gap_pct >= 0.005 else ""
    print(f"🟩 ENTRY: {symbol} qty={qty} limit=${limit_price:.2f} (slip=${initial_slip:.3f}{gap_note}) "
          f"stop=${stop:.4f} R=${r:.4f} score={score:.1f} "
          f"type={setup_type}", flush=True)

    # Latency diagnostic — capture pre-submit timestamps.
    submit_t_perf = None
    try:
        if latency_record is not None:
            latency_record["limit_price_submitted"] = float(limit_price)
            latency_record["order_submit_time"] = datetime.now(ET).isoformat()
            latency_record["ibkr_price_at_order_submit"] = state.last_tick_price.get(symbol)
            submit_t_perf = time.perf_counter()
    except Exception:
        pass

    # Entry-time cutoff (user directive 2026-05-14 — no new entries after 19:30 ET).
    _et_ok, _et_reason = _entry_time_allowed()
    if not _et_ok:
        print(f"  ENTRY BLOCKED: {symbol} {_et_reason}", flush=True)
        return

    # Pre-submit buying-power check (Cowork directive 2026-05-14 §3).
    _bp_ok, _bp_reason = _presubmit_bp_check(symbol, qty, limit_price)
    if not _bp_ok:
        print(f"  ENTRY BLOCKED: {symbol} {_bp_reason}", flush=True)
        return

    # L2 Layer 1 observe-only gate (Cowork DIRECTIVE_2026-05-15_L2_LAYER1_TODAY).
    if os.environ.get("WB_SQ_L2_FILTER_ENABLED", "0") == "1":
        try:
            import l2_helper
            _l2_state = l2_helper.request_l2_snapshot(symbol, getattr(state, "ib", None), timeout_sec=2.0)
            _l2_verdict = l2_helper.evaluate_l2_filter(_l2_state)
            print(f"[L2] SQ_ARM {symbol} state={l2_helper.summarize_l2(_l2_state)} "
                  f"verdict={_l2_verdict.action} reason={_l2_verdict.reason}", flush=True)
            if os.environ.get("WB_SQ_L2_FILTER_OBSERVE_ONLY", "1") != "1":
                if _l2_verdict.action == "VETO":
                    print(f"  ENTRY BLOCKED by L2: {symbol} {_l2_verdict.reason}", flush=True)
                    return
        except Exception as _e:
            print(f"[L2] SQ_ARM {symbol} eval failed: {_e!r} — proceeding", flush=True)

    try:
        new_order = state.broker.submit_limit(symbol, qty, "BUY", limit_price)
        order_id = new_order.order_id
        print(f"  BROKER ORDER: {order_id} BUY {qty} {symbol} @ ${limit_price:.2f}", flush=True)
    except Exception as e:
        print(f"  BROKER ORDER FAILED: {e}", flush=True)
        # Latency diagnostic — submit raised (rejection at submit time).
        try:
            if latency_record is not None:
                _finalize_latency_record(
                    latency_record, terminal_state="no_order",
                    retries_attempted=0,
                    ibkr_price_at_terminal=state.last_tick_price.get(symbol),
                    no_order_reason=f"submit_exception: {e}",
                )
        except Exception:
            pass
        return

    # Latency diagnostic — capture ack timestamps (the broker.submit_limit
    # synchronous return is treated as the "ack" moment: for AlpacaBroker it's
    # the HTTP POST response from Alpaca's order endpoint; for IBKRBroker it's
    # ib_insync's local Trade construction prior to async exchange ack).
    try:
        if latency_record is not None and submit_t_perf is not None:
            latency_record["order_ack_time"] = datetime.now(ET).isoformat()
            latency_record["order_ack_latency_ms"] = int(
                (time.perf_counter() - submit_t_perf) * 1000
            )
            latency_record["ibkr_price_at_order_ack"] = state.last_tick_price.get(symbol)
    except Exception:
        pass

    state.open_position = {
        "symbol": symbol,
        "qty": qty,
        "entry": limit_price,
        "stop": stop,
        "r": r,
        "score": score,
        "setup_type": setup_type,
        "peak": limit_price,
        "tp_hit": False,
        "entry_time": datetime.now(ET),
        "order_id": order_id,
        "is_parabolic": "[PARABOLIC]" in (armed.score_detail or ""),
        "fill_confirmed": False,
    }
    # Snapshot daily P&L at open so the loss-lockout can judge POSITION-net
    # (final leg + any scaled-out partials) when this position fully closes.
    state._position_daily_pnl_at_open = state.daily_pnl
    state.daily_entries += 1

    # Store pending order for timeout check (latency_record threaded for the
    # retry loop to update terminal fields).
    state.pending_order = {
        "order_id": order_id,
        "placed_time": datetime.now(ET),
        "timeout_seconds": 15,
        "latency_record": latency_record,
    }

    # Verify fill in background — dynamic slippage + retry-on-timeout via
    # _verify_fill_with_retry (see helper docstring + directive).
    def verify_alpaca_fill():
        _verify_fill_with_retry(
            symbol=symbol, qty=qty, r=r,
            initial_order_id=order_id, initial_limit=limit_price,
            original_limit=original_limit, position_attr="open_position",
            latency_record=latency_record, score=score,
        )

    import threading
    threading.Thread(target=verify_alpaca_fill, daemon=True).start()


def _enter_epl_trade(symbol: str, signal):
    """Place EPL entry order via Alpaca."""
    entry = signal.entry_price
    stop = signal.stop_price
    r = entry - stop
    if r <= 0 or r < max(MIN_R, MIN_ABSOLUTE_R):
        print(f"  [EPL] SKIP: {symbol} R={r:.4f} < floor {max(MIN_R, MIN_ABSOLUTE_R):.4f} "
              f"reason=R_BELOW_FLOOR", flush=True)
        return

    qty = int(math.floor(EPL_MAX_NOTIONAL * signal.position_size_pct / max(entry, 0.01)))
    qty = min(qty, MAX_SHARES)
    if qty <= 0:
        return

    initial_slip = _entry_slippage_for(entry)
    limit_price = round(entry + initial_slip, 2)
    original_limit = limit_price
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    print(f"[{now_str} ET] [EPL] 🟩 ENTRY: {symbol} strategy={signal.strategy} "
          f"qty={qty} limit=${limit_price:.2f} (slip=${initial_slip:.3f}) "
          f"stop=${stop:.4f} R=${r:.4f} reason={signal.reason}", flush=True)

    # Entry-time cutoff + BP check (user directive 2026-05-14 + Cowork §3).
    _et_ok, _et_reason = _entry_time_allowed()
    if not _et_ok:
        print(f"  [EPL] ENTRY BLOCKED: {symbol} {_et_reason}", flush=True)
        return
    _bp_ok, _bp_reason = _presubmit_bp_check(symbol, qty, limit_price, log_prefix="[EPL] ")
    if not _bp_ok:
        print(f"  [EPL] ENTRY BLOCKED: {symbol} {_bp_reason}", flush=True)
        return

    try:
        new_order = state.broker.submit_limit(symbol, qty, "BUY", limit_price)
        order_id = new_order.order_id
        print(f"  [EPL] BROKER ORDER: {order_id}", flush=True)
    except Exception as e:
        print(f"  [EPL] ORDER FAILED: {e}", flush=True)
        return

    state.open_position = {
        "symbol": symbol, "qty": qty, "entry": limit_price, "stop": stop,
        "r": r, "score": signal.confidence * 10, "setup_type": signal.strategy,
        "peak": limit_price, "tp_hit": False, "entry_time": datetime.now(ET),
        "order_id": order_id, "is_parabolic": False, "fill_confirmed": False,
    }
    state.daily_entries += 1
    state.pending_order = {"order_id": order_id, "placed_time": datetime.now(ET), "timeout_seconds": 15}

    epl_strat = state.epl_registry.get_strategy(signal.strategy)
    if epl_strat and hasattr(epl_strat, 'mark_in_trade'):
        epl_strat.mark_in_trade(symbol)

    import threading
    def verify_epl_fill():
        _verify_fill_with_retry(
            symbol=symbol, qty=qty, r=r,
            initial_order_id=order_id, initial_limit=limit_price,
            original_limit=original_limit, position_attr="open_position",
            log_prefix="[EPL] ", score=signal.confidence * 10,
        )
    threading.Thread(target=verify_epl_fill, daemon=True).start()


def manage_exit(symbol: str, price: float):
    """Manage exit for open position."""
    pos = state.open_position
    if pos is None or pos["symbol"] != symbol:
        return

    # Don't manage exits until entry fill is confirmed
    if not pos.get('fill_confirmed', False):
        return

    # Lever 1 gate (2026-05-26): if a previous exit submission is still
    # awaiting verification (async fill-poll in progress), don't stack
    # another SELL. The verify thread clears exit_in_flight on terminal
    # status (filled / partial / no-fill).
    if pos.get('exit_in_flight', False):
        return

    # Update peak (persist on advance — see cowork review note on write
    # frequency: peaks advance only on new highs, not every tick, so ~10–50
    # writes per active trade is the realistic upper bound).
    if price > pos["peak"]:
        pos["peak"] = price
        persist_open_trades()

    entry = pos["entry"]
    stop = pos["stop"]
    r = pos["r"]
    qty = pos["qty"]
    setup_type = pos["setup_type"]

    # ── Bail timer ── (skip move-stack: it uses HWM's own noact-bail at 30min,
    # per move_strike_subbot parity — the 5-min bail would cut regime trades
    # before their 1.5R target.)
    if BAIL_TIMER_ENABLED and setup_type not in ("move_strike", "regime_shift"):
        minutes_in = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
        if minutes_in >= BAIL_TIMER_MINUTES and price <= entry:
            exit_trade(symbol, price, qty, "bail_timer")
            return

    if setup_type.startswith("epl_"):
        return  # EPL exits handled via strategy.manage_exit() in tick/bar processing
    elif setup_type in ("move_strike", "regime_shift"):
        _move_stack_exit(symbol, price, pos)
    elif setup_type in ("squeeze", "mp_reentry", "continuation"):
        _squeeze_exit(symbol, price, pos)
    else:
        _mp_exit(symbol, price, pos)


def _squeeze_exit(symbol: str, price: float, pos: dict):
    """Squeeze exit ladder — matches simulate.py exactly."""
    entry = pos["entry"]
    stop = pos["stop"]
    r = pos["r"]
    qty = pos["qty"]

    # 0) Dollar loss cap
    if SQ_MAX_LOSS_DOLLARS > 0:
        unrealized_loss = (entry - price) * qty
        if unrealized_loss >= SQ_MAX_LOSS_DOLLARS:
            exit_trade(symbol, price, qty, f"sq_dollar_loss_cap (${unrealized_loss:,.0f})")
            return

    # 1) Hard stop
    if price <= stop:
        exit_trade(symbol, price, qty, "sq_stop_hit")
        return

    # Pre-target phase
    if not pos["tp_hit"]:
        # 2) Trailing stop
        if r > 0:
            trail_r = SQ_PARA_TRAIL_R if pos.get("is_parabolic") else SQ_TRAIL_R
            trail_price = pos["peak"] - (trail_r * r)
            if price <= trail_price:
                reason = "sq_para_trail_exit" if pos.get("is_parabolic") else "sq_trail_exit"
                exit_trade(symbol, price, qty, reason)
                return

        # 3) Target hit — exit core, keep runner
        if r > 0 and price >= entry + (SQ_TARGET_R * r):
            pos["tp_hit"] = True
            # Stamp partial-fill state for resume rehydrate schema.
            pos["partial_filled_at"] = datetime.now(timezone.utc).isoformat()
            # EPL graduation: stock hit 2R, add to watchlist for re-entry
            if EPL_ENABLED and state.epl_watchlist is not None:
                realized_r = (price - entry) / r if r > 0 else 0
                if realized_r >= EPL_MIN_GRADUATION_R:
                    _vwap = state.bar_builder_1m.get_vwap(symbol) if state.bar_builder_1m else 0
                    _hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else 0
                    _pm_h = state.bar_builder_1m.get_premarket_high(symbol) if state.bar_builder_1m else 0
                    ctx = GraduationContext(
                        symbol=symbol, graduation_time=datetime.now(ET),
                        graduation_price=price, sq_entry_price=entry, sq_stop_price=stop,
                        hod_at_graduation=_hod or 0, vwap_at_graduation=_vwap or 0,
                        pm_high=_pm_h or 0, avg_volume_at_graduation=0,
                        sq_trade_count=1, r_value=r,
                    )
                    state.epl_watchlist.add(ctx)
                    state.epl_registry.notify_graduation(ctx)
                    _now = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{_now} ET] [EPL] {symbol} GRADUATED @ ${price:.2f} "
                          f"(R={realized_r:.1f})", flush=True)
            qty_core = max(1, int(qty * SQ_CORE_PCT / 100))
            qty_runner = qty - qty_core
            pos["partial_filled_qty"] = qty_core
            if qty_runner > 0:
                pos["runner_stop"] = max(stop, entry + 0.01)
                exit_trade(symbol, price, qty_core, "sq_target_hit")
                pos["qty"] = qty_runner  # Set AFTER exit_trade so remaining calc is correct
                # tp_hit + trail_mode change + qty shift all need persisting;
                # exit_trade already persisted (full exit case) or we persist
                # the runner state here.
                if state.open_position:
                    persist_open_trades()
            else:
                exit_trade(symbol, price, qty, "sq_target_hit")
            return

    # Post-target (runner)
    if pos["tp_hit"] and pos["qty"] > 0:
        if r > 0:
            runner_trail = pos["peak"] - (SQ_RUNNER_TRAIL_R * r)
            runner_stop = max(pos.get("runner_stop", stop), runner_trail)
            if price <= runner_stop:
                exit_trade(symbol, price, pos["qty"], "sq_runner_trail")
                return


def _mp_exit(symbol: str, price: float, pos: dict):
    """MP exit — simplified signal mode."""
    if price <= pos["stop"]:
        exit_trade(symbol, price, pos["qty"], "stop_hit")


def _move_stack_exit(symbol: str, price: float, pos: dict):
    """Exit driver for MOVE_STRIKE / regime_shift positions (R3). Faithful port of
    move_strike_subbot._maintain_position:
      • regime_shift pre-partial — Track A phased-drawdown floor (when Track A on)
        else hard stop; force-flatten at WB_EXIT_FORCE_FLATTEN_TIME; fire the 1.5R
        partial. No HWM trail until the partial fires (runway for big runners).
      • move_strike + post-partial runner — HWM trail (hwm_exit.evaluate handles its
        own hard stop, stop-prox/noact bails, and adaptive drawdown trail).
    Closes via the main bot's exit_trade(); manage_exit() already advances pos['peak']."""
    entry = pos["entry"]; stop = pos["stop"]; r = pos["r"]; qty = pos["qty"]
    setup_type = pos["setup_type"]

    # Lazy-init + maintain the fields hwm_evaluate / drawdown logic read off the dict.
    if "cum_low" not in pos:
        pos["cum_low"] = entry
    if price < pos["cum_low"]:
        pos["cum_low"] = price
    if "entry_time_min" not in pos:
        _et = pos.get("entry_time")
        pos["entry_time_min"] = (_et.astimezone(ET).hour * 60 + _et.astimezone(ET).minute) if _et else None
    pos.setdefault("hh_count", 0)
    pos.setdefault("move_partial_fired", False)

    now_et = datetime.now(ET)
    now_min = now_et.hour * 60 + now_et.minute

    # ── regime_shift, pre-partial: loss-cut + 1.5R partial (no trail yet) ──
    if setup_type == "regime_shift" and not pos["move_partial_fired"]:
        if track_a_enabled():
            if should_force_flatten(now_min):
                _move_exit_and_record(symbol, price, qty, "regime_shift_force_flatten")
                return
            entry_min = pos["entry_time_min"] if pos["entry_time_min"] is not None else now_min
            age_min = max(0, now_min - entry_min)
            dd_threshold = phased_drawdown_threshold(age_min)
            drawdown = (entry - price) / entry if entry > 0 else 0.0
            if dd_threshold > 0 and drawdown >= dd_threshold:
                _move_exit_and_record(symbol, price, qty, "regime_shift_drawdown_floor")
                return
        else:
            if price <= stop:
                _move_exit_and_record(symbol, price, qty, "regime_shift_hard_stop")
                return
        if r > 0 and price >= entry + MOVE_REGIME_TARGET_R * r:
            _fire_move_partial(symbol, price, pos)
        return  # no HWM trail pre-partial

    # ── move_strike + post-partial runner: HWM trail (dict passed directly) ──
    decision = hwm_evaluate(pos, price, now_min, _MOVE_HWM_CFG)
    if decision is not None:
        reason, exit_price = decision
        _move_exit_and_record(symbol, exit_price, pos["qty"], reason)


def _fire_move_partial(symbol: str, price: float, pos: dict):
    """Sell MOVE_REGIME_PARTIAL_PCT of a regime_shift position at the 1.5R target,
    raise the stop to break-even, and keep the runner under the HWM trail. Mirrors
    the squeeze core/runner partial: exit_trade with the partial qty, then shrink
    pos['qty'] AFTER the call so the remaining-qty math is correct."""
    qty = pos["qty"]
    qty_partial = max(1, int(round(qty * MOVE_REGIME_PARTIAL_PCT)))
    if qty > 1:
        qty_partial = min(qty_partial, qty - 1)  # always leave >=1 runner share
    qty_runner = qty - qty_partial
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    print(f"[{now_str} ET] [MOVE] {symbol} REGIME_PARTIAL fire qty={qty_partial} @ ${price:.4f} "
          f"({MOVE_REGIME_TARGET_R}R target) — runner={qty_runner} to BE stop", flush=True)
    if qty_runner > 0:
        pos["move_partial_fired"] = True
        pos["stop"] = max(pos["stop"], pos["entry"])  # break-even stop for the runner
        exit_trade(symbol, price, qty_partial, "regime_shift_partial")
        pos["qty"] = qty_runner          # AFTER exit_trade (squeeze pattern)
        if state.open_position:
            persist_open_trades()
    else:
        exit_trade(symbol, price, qty, "regime_shift_partial_full")


# ══════════════════════════════════════════════════════════════════════
# Short strategy — Lower-High Short (+ A/C variants via WB_SHORT_STRATEGY)
# ══════════════════════════════════════════════════════════════════════

def _enter_short_trade(symbol: str, detector, vwap: float, trigger_price: float = 0.0):
    """Open a short position via Alpaca. Mirrors enter_trade's structure but
    submits SELL + tracks the inverse of the long exit ladder.

    For Strategy A, trigger_price is 0 (no tick trigger) — we use
    detector.armed.trigger_low which equals the pattern bar's close.
    For B and C, trigger_price is the tick that crossed below the arm's
    trigger_low — that's the intended entry (short at break).
    """
    arm = detector.armed
    if arm is None:
        return
    entry = trigger_price if trigger_price > 0 else arm.trigger_low
    stop = arm.stop
    r = stop - entry  # for shorts: R = stop (above) minus entry (below)
    if r <= 0 or r < max(MIN_R, MIN_ABSOLUTE_R):
        print(f"  SKIP SHORT: R={r:.4f} < floor {max(MIN_R, MIN_ABSOLUTE_R):.4f} "
              f"reason=R_BELOW_FLOOR", flush=True)
        return

    # Dynamic sizing — same risk % + notional cap as long, mirrors backtest
    current_equity = STARTING_EQUITY + state.daily_pnl
    risk_dollars = max(50, current_equity * RISK_PCT)
    qty = int(math.floor(risk_dollars / r))
    qty_notional = int(math.floor(MAX_NOTIONAL / max(entry, 0.01)))
    qty = min(qty, qty_notional, MAX_SHARES)
    if qty <= 0:
        return

    # Short entries submit as SELL. For a naked short, shares must be
    # easy/hard-to-borrow available at the broker. If HTB is unavailable,
    # the broker returns an error which the submit_limit exception catches.
    initial_slip = _entry_slippage_for(entry)
    limit_price = round(entry - initial_slip, 2)  # sell-side limit BELOW entry
    now_str = datetime.now(ET).strftime("%H:%M:%S")
    print(f"[{now_str} ET] 🟦 SHORT ENTRY: {symbol} qty={qty} SELL @ ${limit_price:.2f} "
          f"(slip=${initial_slip:.3f}) stop=${stop:.4f} R=${r:.4f} HOD=${arm.hod_price:.4f} "
          f"strat={SHORT_STRATEGY}", flush=True)

    try:
        new_order = state.broker.submit_limit(symbol, qty, "SELL", limit_price)
        order_id = new_order.order_id
        print(f"  BROKER ORDER: {order_id} SHORT {qty} {symbol} @ ${limit_price:.2f}", flush=True)
    except Exception as e:
        print(f"  SHORT ORDER FAILED: {e}", flush=True)
        return

    state.open_short = {
        "symbol": symbol, "qty": qty, "entry": limit_price, "stop": stop, "r": r,
        "setup_type": f"short_{SHORT_STRATEGY.lower()}",
        "entry_time": datetime.now(ET), "order_id": order_id,
        "hod_price": arm.hod_price, "armed_vwap": vwap or 0,
        "pre_peak_low": state.short_pre_peak_low.get(symbol, float("inf")),
        "fill_confirmed": False,
    }
    persist_wb_state()

    # Mark per-symbol detectors as in-trade so long-side signals can't fire
    # on the same symbol while the short is open.
    detector.notify_trade_opened()
    if SQ_ENABLED and symbol in state.sq_detectors:
        state.sq_detectors[symbol]._in_trade = True
    if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
        state.mp_detectors[symbol]._in_trade = True
    if CT_ENABLED and symbol in state.ct_detectors:
        try:
            state.ct_detectors[symbol]._in_trade = True
        except Exception:
            pass

    # Background fill verification — on timeout we don't retry (shorts are
    # time-sensitive; a missed fill should be abandoned, not chased).
    def verify_short_fill():
        deadline = time.time() + ENTRY_RETRY_TIMEOUT_SEC
        while time.time() < deadline:
            o = state.broker.get_order_status(order_id)
            if o is not None:
                if o.status == STATUS_FILLED:
                    actual_price = o.filled_avg_price or limit_price
                    actual_qty = o.filled_qty or qty
                    if state.open_short and state.open_short.get("order_id") == order_id:
                        state.open_short["entry"] = actual_price
                        state.open_short["qty"] = actual_qty
                        state.open_short["stop"] = actual_price + r
                        state.open_short["fill_confirmed"] = True
                        print(f"  SHORT FILL: {symbol} @ ${actual_price:.4f} qty={actual_qty}",
                              flush=True)
                    return
                if o.status in (STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED):
                    print(f"  SHORT UNFILLED: {symbol} order {order_id} status={o.status} — clearing slot",
                          flush=True)
                    if state.open_short and state.open_short.get("order_id") == order_id:
                        state.open_short = None
                        persist_wb_state()
                    return
            time.sleep(0.5)
        # Timeout: try one more read; if any shares filled, record the fill.
        o = state.broker.get_order_status(order_id)
        if o is not None and o.filled_qty > 0:
            actual_price = o.filled_avg_price or limit_price
            actual_qty = o.filled_qty
            if state.open_short and state.open_short.get("order_id") == order_id:
                state.open_short["entry"] = actual_price
                state.open_short["qty"] = actual_qty
                state.open_short["stop"] = actual_price + r
                state.open_short["fill_confirmed"] = True
                print(f"  SHORT FILL (late): {symbol} @ ${actual_price:.4f} qty={actual_qty}",
                      flush=True)
    import threading
    threading.Thread(target=verify_short_fill, daemon=True).start()


def manage_short_exit(symbol: str, price: float):
    """Run the short exit ladder on each tick. Mirrors backtest_short.py logic:
      - Stop: price >= stop (cover, taking loss)
      - Target 1: VWAP, if armed_vwap was meaningfully below entry
      - Target 2: 50% retrace, if below entry
      - Time stop: WB_SHORT_TIME_STOP_MIN from entry
    """
    pos = state.open_short
    if pos is None or pos["symbol"] != symbol:
        return
    if not pos.get("fill_confirmed", False):
        return

    entry = pos["entry"]
    stop = pos["stop"]
    armed_vwap = pos.get("armed_vwap", 0)
    hod = pos.get("hod_price", 0)
    pre_peak_low = pos.get("pre_peak_low", float("inf"))
    retrace_50 = (hod + pre_peak_low) / 2.0 if pre_peak_low < float("inf") else entry * 0.90

    # Stop (cover at loss)
    if price >= stop:
        exit_short(symbol, stop, pos["qty"], "short_stop_hit")
        return
    # Target 1 — VWAP. Only take this path if VWAP was meaningfully below entry.
    if armed_vwap > 0 and armed_vwap < entry * 0.99 and price <= armed_vwap:
        exit_short(symbol, price, pos["qty"], "short_target_vwap")
        return
    # Target 2 — 50% retrace of morning move. Only valid if below entry.
    if retrace_50 < entry * 0.99 and price <= retrace_50:
        exit_short(symbol, price, pos["qty"], "short_target_retrace50")
        return
    # Time stop
    held_min = (datetime.now(ET) - pos["entry_time"]).total_seconds() / 60
    if held_min >= SHORT_TIME_STOP_MIN:
        exit_short(symbol, price, pos["qty"], f"short_time_{int(SHORT_TIME_STOP_MIN)}min")


def exit_short(symbol: str, price: float, qty: int, reason: str):
    """Place cover (BUY) order via broker and record the short trade. Mirrors
    exit_trade's phantom-P&L guards: no P&L unless the broker actually fills."""
    # Urgent cover (stop hit): aggressive limit ABOVE current price.
    if reason == "short_stop_hit":
        limit_price = round(price * 1.03, 2)
    else:
        limit_price = round(price + 0.03, 2)

    order_submitted = False
    cover_order = None
    try:
        cover_order = state.broker.submit_limit(symbol, qty, "BUY", limit_price)
        print(f"  BROKER COVER: {cover_order.order_id} BUY {qty} {symbol} @ ${limit_price:.2f}",
              flush=True)
        order_submitted = True
    except Exception as e:
        # Per project rule: no market fallbacks. If the limit didn't take,
        # log and let the next tick re-trigger the exit logic with a fresh price.
        print(f"  BROKER COVER FAILED: {e} — no market fallback (per project rules); "
              f"will retry on next tick with fresh price", flush=True)

    if not order_submitted:
        print(f"  ⚠️ SHORT COVER ABORTED: {symbol} qty={qty} reason={reason} — "
              f"no order accepted, state unchanged, no P&L recorded", flush=True)
        return

    pos = state.open_short
    if pos is None:
        print(f"  ⚠️ SHORT COVER RACE: {symbol} open_short cleared before snapshot", flush=True)
        return
    entry_price = pos["entry"]
    setup_type = pos["setup_type"]
    intended_price = price
    intended_qty = qty

    # Clear slot immediately so repeated ticks don't double-cover.
    remaining = pos["qty"] - qty
    if remaining <= 0:
        state.open_short = None
    else:
        pos["qty"] = remaining
    persist_wb_state()

    def verify_cover_fill():
        actual_qty = 0
        actual_price = 0.0
        status_final = STATUS_UNKNOWN
        for _ in range(60):
            o = state.broker.get_order_status(cover_order.order_id)
            if o is not None:
                if o.status == STATUS_FILLED:
                    actual_qty = o.filled_qty
                    actual_price = o.filled_avg_price
                    status_final = STATUS_FILLED
                    break
                if o.status == STATUS_PARTIALLY:
                    actual_qty = o.filled_qty
                    actual_price = o.filled_avg_price
                    status_final = STATUS_PARTIALLY
                if o.status in (STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED):
                    actual_qty = o.filled_qty
                    actual_price = o.filled_avg_price
                    status_final = o.status
                    break
            time.sleep(0.5)
        if actual_qty == 0:
            print(f"  ⚠️ COVER UNFILLED: {symbol} status={status_final} — no shares, no P&L",
                  flush=True)
            return
        # Short P&L: (entry - exit) × qty.
        pnl = (entry_price - actual_price) * actual_qty
        state.daily_pnl += pnl
        state.daily_trades += 1
        if pnl < 0:
            state.consecutive_losses += 1
        else:
            state.consecutive_losses = 0
        slip_note = ""
        if abs(actual_price - intended_price) > 0.005:
            slip_note = f" (intended ${intended_price:.4f}, slip ${actual_price - intended_price:+.4f})"
        partial_note = ""
        if actual_qty < intended_qty:
            partial_note = f" [PARTIAL {actual_qty}/{intended_qty}]"
        print(f"🟩 SHORT COVER: {symbol} qty={actual_qty} @ ${actual_price:.4f}{slip_note}{partial_note} "
              f"reason={reason} P&L=${pnl:+,.0f} daily=${state.daily_pnl:+,.0f}", flush=True)
        state.short_closed_trades.append({
            "symbol": symbol, "entry": entry_price, "exit": actual_price, "qty": actual_qty,
            "pnl": pnl, "reason": reason, "setup_type": setup_type,
            "time": datetime.now(ET).strftime("%H:%M:%S"),
        })
        # Release the per-symbol cross-detector locks we set on entry.
        if SHORT_ENABLED and symbol in state.short_detectors:
            try:
                state.short_detectors[symbol].notify_trade_closed(pnl)
            except Exception:
                pass
        if SQ_ENABLED and symbol in state.sq_detectors:
            state.sq_detectors[symbol]._in_trade = False
        if (MP_ENABLED or MP_V2_ENABLED) and symbol in state.mp_detectors:
            state.mp_detectors[symbol]._in_trade = False
        if CT_ENABLED and symbol in state.ct_detectors:
            try:
                state.ct_detectors[symbol]._in_trade = False
            except Exception:
                pass
    import threading
    threading.Thread(target=verify_cover_fill, daemon=True).start()


def exit_trade(symbol: str, price: float, qty: int, reason: str):
    """Place exit order via broker and record trade."""
    # For urgent exits (stop hit, dollar loss cap, max loss), use very aggressive limit
    urgent_reasons = ('sq_stop_hit', 'sq_dollar_loss_cap', 'sq_max_loss_hit', 'stop_hit')
    if reason in urgent_reasons:
        limit_price = round(price * 0.97, 2)  # 3% below current price
    else:
        limit_price = round(price - 0.03, 2)

    order_submitted = False
    exit_order = None
    try:
        exit_order = state.broker.submit_limit(symbol, qty, "SELL", limit_price)
        print(f"  BROKER EXIT: {exit_order.order_id} SELL {qty} {symbol} @ ${limit_price:.2f}", flush=True)
        order_submitted = True
    except Exception as e:
        # Per project rule: no market fallbacks. The limit's slippage budget
        # already covers normal exit conditions; if it failed, retrying with a
        # fresh price on the next tick is safer than a market order.
        print(f"  BROKER EXIT FAILED: {e} — no market fallback (per project rules); "
              f"will retry on next tick with fresh price", flush=True)

    # Phantom-P&L guard: if BOTH limit and market submissions were rejected
    # (e.g. "insufficient qty available" when shares are held_for_orders on
    # another open exit order), DO NOT record P&L. Zero shares changed hands,
    # zero P&L. Recording here is what produced today's -$258 phantom-loss
    # divergence from Alpaca truth (see 2026-04-16_morning_report.md).
    if not order_submitted:
        print(f"  ⚠️ EXIT ABORTED: {symbol} qty={qty} reason={reason} — "
              f"no order accepted by broker, state unchanged, no P&L recorded",
              flush=True)
        return

    # Capture pre-exit context BEFORE any mutation, so the async verify
    # thread has a consistent snapshot (even if manage_exit concurrently
    # mutates state.open_position).
    pos = state.open_position
    if pos is None:
        # Race: position already cleared. Submission went through anyway,
        # but we can't compute P&L without an entry price. Rare; log + bail.
        print(f"  ⚠️ EXIT RACE: {symbol} state.open_position cleared before "
              f"P&L snapshot — order {exit_order.order_id} sent, P&L unbookable.",
              flush=True)
        return
    entry_price = pos["entry"]
    setup_type = pos["setup_type"]

    # Lever 1 (2026-05-26, per 2026-05-26_sub_bot_orphan_fix_directive.md):
    # do NOT mutate state.open_position synchronously. Set exit_in_flight
    # to gate manage_exit() against double-exits, then defer the state
    # change to verify_exit_fill where we have authoritative fill info.
    # Old behavior (cleared on `remaining <= 0`) created orphans when the
    # broker only partial-filled or didn't fill at all — bot thought flat,
    # broker still held shares.
    pos["exit_in_flight"] = True

    intended_price = price
    intended_qty = qty

    def verify_exit_fill():
        actual_qty = 0
        actual_price = 0.0
        status_final = STATUS_UNKNOWN
        for _ in range(60):  # up to 30s total (0.5s * 60)
            o = state.broker.get_order_status(exit_order.order_id)
            if o is not None:
                if o.status == STATUS_FILLED:
                    actual_qty = o.filled_qty
                    actual_price = o.filled_avg_price
                    status_final = STATUS_FILLED
                    break
                if o.status == STATUS_PARTIALLY:
                    actual_qty = o.filled_qty
                    actual_price = o.filled_avg_price
                    status_final = STATUS_PARTIALLY
                if o.status in (STATUS_CANCELLED, STATUS_EXPIRED, STATUS_REJECTED):
                    actual_qty = o.filled_qty
                    actual_price = o.filled_avg_price
                    status_final = o.status
                    break
            time.sleep(0.5)

        # Re-fetch the pos reference; state.open_position could have been
        # adopted/changed by reconcile in the interim. Match by symbol.
        cur_pos = state.open_position
        if cur_pos is None or cur_pos.get("symbol") != symbol:
            # Position already gone (reconcile flatten or external close).
            # Just log the fill outcome; nothing to mutate.
            cur_pos = None

        if actual_qty == 0:
            # No fill — clear the in-flight flag so manage_exit can re-attempt.
            # Position itself untouched (the broker still holds the shares).
            if cur_pos is not None:
                cur_pos["exit_in_flight"] = False
            print(f"  ⚠️ EXIT NO-FILL: {symbol} order {exit_order.order_id} "
                  f"status={status_final} — position kept alive at qty={intended_qty}, "
                  f"will retry on next tick (reason={reason})", flush=True)
            return

        # Fill happened (full or partial). Compute P&L on ACTUAL fills.
        pnl = (actual_price - entry_price) * actual_qty
        state.daily_pnl += pnl
        state.daily_trades += 1
        if pnl < 0:
            state.consecutive_losses += 1
        else:
            state.consecutive_losses = 0

        slip_note = ""
        if abs(actual_price - intended_price) > 0.005:
            slip_note = f" (intended ${intended_price:.4f}, slip ${actual_price - intended_price:+.4f})"
        partial_note = ""
        if actual_qty < intended_qty:
            partial_note = f" [PARTIAL {actual_qty}/{intended_qty}]"
        print(f"🟥 EXIT: {symbol} qty={actual_qty} @ ${actual_price:.4f}{slip_note}{partial_note} "
              f"reason={reason} P&L=${pnl:+,.0f} daily=${state.daily_pnl:+,.0f}",
              flush=True)

        # Lever 1: mutate state.open_position HERE based on ACTUAL fill qty
        # (not the intended qty). Full fill → flatten; partial fill →
        # decrement and clear in-flight so manage_exit can chase residual.
        if cur_pos is not None:
            if actual_qty >= cur_pos.get("qty", 0):
                state.open_position = None
                # Loss-lockout: if the POSITION (this leg + any prior scale-outs)
                # netted a loss, block re-entry on this symbol for the rest of today.
                if SYMBOL_LOSS_LOCKOUT:
                    position_net = state.daily_pnl - state._position_daily_pnl_at_open
                    if position_net < 0:
                        state._lossout_symbols.add(symbol)
                        print(f"  {symbol} → LOSS_LOCKOUT armed (position net "
                              f"${position_net:+,.0f}; no re-entry today)", flush=True)
            else:
                cur_pos["qty"] -= actual_qty
                cur_pos["exit_in_flight"] = False

        state.closed_trades.append({
            "symbol": symbol,
            "entry": entry_price,
            "exit": actual_price,
            "qty": actual_qty,
            "pnl": pnl,
            "reason": reason if actual_qty >= intended_qty else reason + "_partial",
            "setup_type": setup_type,
            "time": datetime.now(ET).strftime("%H:%M:%S"),
        })

        # Detector notifications fire with the ACTUAL P&L, not the intended.
        # The cumulative-R / has_winner logic depends on correct sign + magnitude.
        if SQ_ENABLED and symbol in state.sq_detectors:
            state.sq_detectors[symbol].notify_trade_closed(symbol, pnl)

        if setup_type == "squeeze" and symbol in state.mp_detectors:
            state.mp_detectors[symbol].notify_squeeze_closed(symbol, pnl)

        if setup_type == "mp_reentry" and symbol in state.mp_detectors:
            state.mp_detectors[symbol].notify_reentry_closed()

        if setup_type == "squeeze" and CT_ENABLED and symbol in state.ct_detectors:
            hod = state.bar_builder_1m.get_hod(symbol) if state.bar_builder_1m else 0
            avg_vol = 0
            sq = state.sq_detectors.get(symbol)
            if sq and hasattr(sq, 'bars_1m') and sq.bars_1m:
                avg_vol = sum(b.get("v", 0) if isinstance(b, dict) else getattr(b, "volume", 0)
                              for b in sq.bars_1m) / len(sq.bars_1m)
            _ct_now_str = datetime.now(ET).strftime("%H:%M")
            state.ct_detectors[symbol].notify_squeeze_closed(
                symbol, pnl,
                entry=entry_price, exit_price=actual_price,
                hod=hod or 0, avg_squeeze_vol=avg_vol,
                bar_time=_ct_now_str,
            )

        if setup_type == "continuation" and CT_ENABLED and symbol in state.ct_detectors:
            state.ct_detectors[symbol].notify_continuation_closed(pnl)

        # Persist post-exit state after P&L is authoritative.
        persist_open_trades()
        persist_risk()

    threading.Thread(target=verify_exit_fill, daemon=True, name=f"exit-verify-{symbol}").start()


# ══════════════════════════════════════════════════════════════════════
# Halt Detection
# ══════════════════════════════════════════════════════════════════════

_halted_symbols: set = set()  # Track which symbols are currently halted (debounce)

def check_halts():
    """Check for halted stocks via Tick Type 49. Debounced — prints once per halt event."""
    for symbol in state.active_symbols:
        ticker = state.tickers.get(symbol)
        if ticker and hasattr(ticker, 'halted'):
            if ticker.halted == 1 or ticker.halted == 2:
                if symbol not in _halted_symbols:
                    halt_type = "regulatory" if ticker.halted == 1 else "volatility"
                    print(f"⚠️ HALT DETECTED: {symbol} ({halt_type})", flush=True)
                    _halted_symbols.add(symbol)
                    # Halt-count gate bookkeeping (R4 addendum): count halts per
                    # symbol so the entry path can avoid serially-halted names.
                    state.halt_count_today[symbol] = state.halt_count_today.get(symbol, 0) + 1
                    print(f"[HALT_COUNT] {symbol} now {state.halt_count_today[symbol]} "
                          f"halts today", flush=True)
            else:
                if symbol in _halted_symbols:
                    print(f"✅ HALT RESUMED: {symbol}", flush=True)
                    _halted_symbols.discard(symbol)


# ══════════════════════════════════════════════════════════════════════
# Main Loop
# ══════════════════════════════════════════════════════════════════════

def on_ticker_update(tickers):
    """Called on every market data update. Receives a SET of updated tickers
    from ib.pendingTickersEvent — fires for both reqMktData (snapshot) and
    reqTickByTickData updates. Dispatches each ticker by tier.

    Tier 1 (tick_by_tick): drain ticker.tickByTicks list — every print is
        delivered, no 250ms throttle. Snapshot fields on the same Ticker
        are ignored to avoid double-counting (the snapshot fields update
        too, but they're aggregated and we already have the per-print stream).
    Tier 2 (snapshot): the legacy path — read ticker.last / ticker.lastSize
        as before. This is the awareness layer for symbols not actively in
        a setup."""
    state.last_on_ticker_fire = datetime.now(ET)
    for ticker in tickers:
        contract = getattr(ticker, "contract", None)
        sym = contract.symbol if contract else None
        if sym and state.tier.get(sym) == "tick_by_tick":
            _drain_tick_by_tick_ticker(ticker)
        else:
            _process_ticker(ticker)


def _drain_tick_by_tick_ticker(ticker):
    """For Tier 1 symbols: process per-print events in `ticker.tickByTicks`.

    IMPORTANT — `tickByTicks` is per-cycle, NOT accumulating. ib_insync
    populates the list with the ticks that arrived since the last
    `pendingTickersEvent` and clears it before the next cycle. So the
    correct usage is: every event, iterate whatever's currently in the
    list. Do NOT track an index across events — that was the 2026-05-06
    bug that caused Tier 1 symbols to silently go data-blind hours after
    the first tick (verified by scripts/probe_tbt_event_flow.py).

    Same-Ticker note: ib_insync uses ONE Ticker object per contract for
    both reqMktData and reqTickByTickData (probe-confirmed). When the
    snapshot side updates `.last` / `.lastSize`, this same handler fires
    with `tickByTicks` empty — that's fine, we just have nothing to
    process. Health monitoring still updates from the snapshot in that
    case so audit_tick_health doesn't false-alarm on a quiet TBT cycle
    while the snapshot fields are clearly live."""
    contract = ticker.contract
    if not contract:
        return
    symbol = contract.symbol
    _update_nbbo(symbol, ticker)
    tbt_events = list(ticker.tickByTicks or [])

    if tbt_events:
        # Per-print path — the high-fidelity stream we promoted for.
        for tk in tbt_events:
            try:
                price = float(tk.price) if tk.price else 0.0
                size = int(tk.size or 0)
                ts_raw = tk.time
            except (AttributeError, TypeError, ValueError):
                continue
            if ts_raw is None:
                ts_raw = datetime.now(timezone.utc)
            if ts_raw.tzinfo is None:
                ts_raw = ts_raw.replace(tzinfo=timezone.utc)
            ts_et = ts_raw.astimezone(ET)
            state.tick_counts[symbol] = state.tick_counts.get(symbol, 0) + 1
            state.last_tick_time[symbol] = ts_et
            state.last_tick_price[symbol] = price
            if price > 0 and size > 0:
                _process_trade_tick(symbol, price, size, ts_et)
        return

    # No per-print events this cycle — refresh health metrics from the
    # snapshot side (last/lastSize) so audit_tick_health doesn't declare
    # 🔴 CRITICAL drought when the symbol is just briefly quiet on TBT.
    # Don't double-process trades — only the per-print path bumps tick_counts.
    last_attr = getattr(ticker, "last", None)
    if last_attr is not None and not (isinstance(last_attr, float) and math.isnan(last_attr)) and last_attr > 0:
        state.last_tick_time[symbol] = datetime.now(ET)
        state.last_tick_price[symbol] = float(last_attr)


def _update_nbbo(symbol: str, ticker) -> None:
    """Refresh the per-symbol NBBO cache from an ib_insync ticker (one Ticker
    per contract serves both tiers). Keeps the last valid value for a side
    that's momentarily nan/None so a single bad snapshot doesn't blank the
    quote. Read at the publish_tick emit site to attach bid/ask to each tick."""
    def _v(x):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return None
        return x if (x == x and x > 0) else None  # x == x filters NaN
    b = _v(getattr(ticker, "bid", None))
    a = _v(getattr(ticker, "ask", None))
    if b is None and a is None:
        return
    pb, pa = state.last_nbbo.get(symbol, (None, None))
    state.last_nbbo[symbol] = (b if b is not None else pb,
                               a if a is not None else pa)


def _process_ticker(ticker):
    """Tier 2 (snapshot) path. Receives one ticker from reqMktData updates
    delivered every ~250ms. Health-monitoring runs on every ticker update;
    trade-side downstream runs only when ticker.last is a valid trade."""
    contract = ticker.contract
    if not contract:
        return
    symbol = contract.symbol
    _update_nbbo(symbol, ticker)

    # Determine if we have a valid trade price
    trade_price = ticker.last
    is_trade = (trade_price is not None and not math.isnan(trade_price) and trade_price > 0)

    # Fallback price for health monitoring: use bid or ask if no trade price
    health_price = None
    for attr in ('last', 'bid', 'ask'):
        p = getattr(ticker, attr, None)
        if p is not None and not math.isnan(p) and p > 0:
            health_price = p
            break

    if health_price is None:
        return

    ts = datetime.now(ET)

    # Always update health monitoring (even with bid/ask fallback)
    state.tick_counts[symbol] = state.tick_counts.get(symbol, 0) + 1
    state.last_tick_time[symbol] = ts
    state.last_tick_price[symbol] = health_price

    # Only feed trade prices to bar builders, triggers, and exit management
    if not is_trade:
        return

    price = trade_price

    # Get trade size from ticker (lastSize = size of most recent trade print)
    size = int(ticker.lastSize) if ticker.lastSize and not math.isnan(ticker.lastSize) else 0

    _process_trade_tick(symbol, price, size, ts)


def _process_trade_tick(symbol: str, price: float, size: int, ts):
    """Shared trade-tick downstream — bar builders, detectors, EPL, exits, WB.
    Called by both _process_ticker (Tier 2 snapshot path) and
    _drain_tick_by_tick_ticker (Tier 1 per-print path)."""
    # Engine publisher (2026-05-20). Gated; no-op when disabled.
    # Broadcasts the tick over a Unix socket so subscriber bots see the
    # exact same data stream. Non-blocking; never affects strategy.
    if _engine_pub.enabled:
        try:
            ts_iso = ts.astimezone(timezone.utc).isoformat() if ts else None
            bid, ask = state.last_nbbo.get(symbol, (None, None))
            _engine_pub.publish_tick(symbol, price, ts_iso=ts_iso, size=size,
                                     bid=bid, ask=ask)
        except Exception:
            pass  # never let publisher break the tick path

    # Record tick for backtest cache (exact same data the bot sees).
    # Lock serializes against the periodic flush swap — see _tick_flush_loop.
    with _tick_buffer_lock:
        if symbol not in state.tick_buffer:
            state.tick_buffer[symbol] = []
        state.tick_buffer[symbol].append({
            "p": price,
            "s": size,
            "t": ts.astimezone(timezone.utc).isoformat(),
        })

    # Track live ticks since seed (for stale signal suppression)
    if symbol in state.live_tick_count_since_seed:
        state.live_tick_count_since_seed[symbol] += 1

    # Feed to bar builders (price + volume)
    if state.bar_builder_1m:
        state.bar_builder_1m.on_trade(symbol, price, size, ts)
    if state.bar_builder_10s:
        state.bar_builder_10s.on_trade(symbol, price, size, ts)

    # Feed to box bar builder (separate from momentum)
    if BOX_ENABLED and state.box_bar_builder_1m and symbol == state.box_active_symbol:
        state.box_bar_builder_1m.on_trade(symbol, price, size, ts)

    # Check triggers
    check_triggers(symbol, price)

    # ── EPL tick processing ──
    if EPL_ENABLED and state.epl_registry and state.epl_registry.strategy_count > 0:
        pos = state.open_position
        # EPL tick-level exit
        if pos and pos.get("setup_type", "").startswith("epl_") and pos["symbol"] == symbol:
            epl_strat = state.epl_registry.get_strategy(pos["setup_type"])
            if epl_strat:
                epl_exit = epl_strat.manage_exit(symbol, price, None)
                if epl_exit:
                    _now = datetime.now(ET).strftime("%H:%M:%S")
                    print(f"[{_now} ET] [EPL] {epl_exit.strategy} EXIT {symbol} "
                          f"@ ${epl_exit.exit_price:.2f} reason={epl_exit.exit_reason}", flush=True)
                    exit_trade(symbol, epl_exit.exit_price, pos["qty"], epl_exit.exit_reason)
                    if state.epl_arbitrator:
                        epl_pnl = (epl_exit.exit_price - pos["entry"]) * pos["qty"]
                        state.epl_arbitrator.record_epl_trade_result(symbol, epl_pnl)
                    state.epl_registry.reset_all(symbol)
                    return
        # EPL tick-level entry trigger
        if state.open_position is None and state.epl_watchlist and state.epl_watchlist.is_graduated(symbol):
            sq_state = state.sq_detectors[symbol]._state if (SQ_ENABLED and symbol in state.sq_detectors) else "IDLE"
            if state.epl_arbitrator.can_epl_enter(symbol, sq_state, False, datetime.now(ET)):
                signals = state.epl_registry.collect_entry_signals(symbol, None, price, size)
                best = state.epl_arbitrator.get_best_signal(signals)
                if best:
                    _enter_epl_trade(symbol, best)
                    return

    # Manage exits
    if state.open_position and state.open_position["symbol"] == symbol:
        manage_exit(symbol, price)
    if state.open_short and state.open_short["symbol"] == symbol:
        manage_short_exit(symbol, price)

    # Wave Breakout — independent tick path (operates parallel to squeeze).
    # Fires entries when armed AND under the portfolio cap. Manages exits
    # for any active WB position. Runs regardless of state.open_position
    # (the WB position lives in state.wb_positions, separate slot).
    if WAVE_BREAKOUT_ENABLED and symbol in state.wb_detectors:
        det = state.wb_detectors[symbol]
        wb_msg = det.on_trade_price(price, ts=None)
        if wb_msg:
            if wb_msg.startswith("WB_ENTER"):
                place_wave_breakout_entry(symbol, wb_msg)
            elif wb_msg.startswith("WB_EXIT"):
                place_wave_breakout_exit(symbol, wb_msg)
            elif (wb_msg.startswith("WB_TRAIL_ARMED") or
                  wb_msg.startswith("WB_PYRAMID") or
                  wb_msg.startswith("WB_DISARMED")):
                # Informational state-change events — log only.
                now_str = datetime.now(ET).strftime("%H:%M:%S")
                print(f"[WB] [{now_str} ET] {symbol} {wb_msg}", flush=True)


def save_tick_cache(source: dict | None = None):
    """Save recorded ticks to tick_cache/ for future backtesting.
    Uses the exact same format simulate.py --ticks expects.

    If source is provided, saves from that dict instead of state.tick_buffer.
    This lets the periodic flush thread swap-and-save without racing the
    live tick-callback thread that writes into state.tick_buffer.
    """
    if source is None:
        source = state.tick_buffer
    today = datetime.now(ET).strftime("%Y-%m-%d")
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tick_cache", today)
    os.makedirs(cache_dir, exist_ok=True)

    saved = 0
    for symbol, ticks in source.items():
        if not ticks:
            continue
        out_path = os.path.join(cache_dir, f"{symbol}.json.gz")
        # Merge with existing cache (don't overwrite fetched historical data)
        existing = []
        if os.path.exists(out_path):
            try:
                with gzip.open(out_path, "rt") as f:
                    existing = json.load(f)
            except Exception:
                existing = []
        merged = existing + ticks
        # Atomic write (2026-05-27, per orphan-fix & harness directive):
        # write to a temp path first, then os.replace() to swap atomically.
        # Prevents concurrent readers (intraday backtests, sub-bot replays,
        # the subscription_watchdog if it ever reads cache) from seeing a
        # partial gzip stream during the write. Without this, mid-write
        # reads produce EOFError("Compressed file ended before the
        # end-of-stream marker was reached") and silently corrupt
        # backtests on today's date.
        tmp_path = out_path + ".tmp"
        with gzip.open(tmp_path, "wt") as f:
            json.dump(merged, f)
        os.replace(tmp_path, out_path)
        saved += 1
        new_count = len(ticks)
        total_count = len(merged)
        print(f"  Tick cache: {symbol} → +{new_count:,} ticks (total {total_count:,})", flush=True)

    if saved:
        print(f"📦 Tick cache saved: {saved} symbols → tick_cache/{today}/", flush=True)


def _tick_flush_loop():
    """Background loop that flushes state.tick_buffer to tick_cache/ every
    SESSION_FLUSH_SEC. Always-on crash-safety (see
    cowork_reports/2026-04-15_greenlight_session_resume.md).

    Atomically swaps the buffer with a fresh dict so the live tick callback
    thread keeps writing into the fresh buffer while we flush the snapshot.
    Under CPython the GIL makes the `snap, state.tick_buffer = ..., {}`
    assignment atomic across threads (single bytecode store). Ticks that
    arrive during the flush land safely in the new buffer.
    """
    while True:
        time.sleep(SESSION_FLUSH_SEC)
        try:
            with _tick_buffer_lock:
                snap_to_flush = bool(any(state.tick_buffer.values()))
                if snap_to_flush:
                    snap, state.tick_buffer = state.tick_buffer, {}
                else:
                    snap = None
            # Release lock before disk IO — callback thread can resume writing
            # into the fresh state.tick_buffer while we serialize the snapshot.
            if snap is not None:
                save_tick_cache(source=snap)
            # Defense in depth: flush WB state on the same cadence so crash
            # loss is bounded to one tick of trail-stop drift rather than the
            # whole position record. Cheap (small JSON file).
            persist_wb_state()
        except Exception as e:
            print(f"⚠️  TICK FLUSH ERROR: {e}", flush=True)


def _open_position_to_trade_record(pos: dict) -> dict:
    """Map in-memory open_position dict → open_trades.json schema (19 fields).

    Schema fields that aren't first-class on open_position are derived here:
      - target_r / target_price: derived from SQ_TARGET_R + r (squeeze-only;
        for other setup_types we use 0 as a neutral placeholder since their
        exit paths don't use a target-R concept).
      - trail_mode: "pre_target" until pos["tp_hit"] goes True, then "post_target".
      - partial_filled_at / partial_filled_qty: stamped onto pos at the tp_hit
        transition in _squeeze_exit (see write points below). Default None/0.
      - bail_timer_start: identical to entry_time today (bail timer is a
        duration-from-entry check, not a separate countdown we ever restart).
      - exit_mode: env-derived. "signal" is the default today; see CLAUDE.md.
    """
    entry = float(pos["entry"])
    r = float(pos.get("r", 0.0))
    target_r = float(SQ_TARGET_R) if pos.get("setup_type") in ("squeeze", "mp_reentry", "continuation") else 0.0
    target_price = entry + target_r * r if target_r > 0 else 0.0
    trail_mode = "post_target" if pos.get("tp_hit") else "pre_target"
    entry_time = pos.get("entry_time")
    entry_iso = entry_time.isoformat() if hasattr(entry_time, "isoformat") else str(entry_time)
    return {
        "symbol": pos["symbol"],
        "setup_type": pos.get("setup_type", ""),
        "entry_price": entry,
        "entry_time": entry_iso,
        "qty": int(pos.get("qty", 0)),
        "r": r,
        "stop": float(pos.get("stop", 0.0)),
        "target_r": target_r,
        "target_price": target_price,
        "peak": float(pos.get("peak", entry)),
        "trail_mode": trail_mode,
        "partial_filled_at": pos.get("partial_filled_at"),
        "partial_filled_qty": int(pos.get("partial_filled_qty", 0)),
        "bail_timer_start": entry_iso,
        "exit_mode": os.getenv("WB_EXIT_MODE", "signal"),
        "order_id": pos.get("order_id", ""),
        "fill_confirmed": bool(pos.get("fill_confirmed", False)),
        "score": float(pos.get("score", 0.0)),
        "is_parabolic": bool(pos.get("is_parabolic", False)),
    }


def persist_open_trades():
    """Sync state.open_position to open_trades.json. Called on every state
    transition (fill confirmation, peak advance, trail-mode change, partial
    fill, bail arm) and on position close. Box positions are not persisted
    in v1 (see plan — deferred, MASTER_TODO follow-up).

    Only persists fully-confirmed trades per Cowork's write-on-fill rule:
    the moment fill_confirmed=True, manage_exit() is the protection layer,
    so that's the durable state to persist. Pre-fill positions would persist
    as "filled but unmanaged" from a resume perspective, which is worse than
    flattening as orphan.
    """
    try:
        pos = state.open_position
        if pos and pos.get("fill_confirmed"):
            ss.write_open_trades([_open_position_to_trade_record(pos)])
        else:
            ss.write_open_trades([])
    except Exception as e:
        print(f"⚠️  persist_open_trades error: {e}", flush=True)


def persist_wb_state():
    """Sync state.wb_positions / state.wb_pending_orders / state.open_short
    to wb_state.json. Called on every WB mutation (entry fill, exit fill,
    pyramid leg, trail update) plus periodically from the flush thread.

    Datetimes inside dicts serialize via default=str (atomic_write_json) and
    are round-tripped as ISO strings on read; rehydrate parses them back.
    """
    try:
        ss.write_wb_state(
            wb_positions=state.wb_positions,
            wb_pending_orders=state.wb_pending_orders,
            open_short=state.open_short,
        )
    except Exception as e:
        print(f"⚠️  persist_wb_state error: {e}", flush=True)


def persist_risk():
    """Sync daily risk counters to risk.json. Cheap — ≤3KB file, no validation."""
    try:
        ss.write_risk(
            daily_pnl=state.daily_pnl,
            daily_trades=state.daily_trades,
            consecutive_losses=state.consecutive_losses,
            closed_trades=state.closed_trades,
        )
    except Exception as e:
        print(f"⚠️  persist_risk error: {e}", flush=True)


def persist_watchlist():
    """Sync state.active_symbols to watchlist.json with subscription timestamps.
    Called on every subscribe_symbol() success."""
    try:
        now_iso = datetime.now(timezone.utc).isoformat()
        existing = {e["symbol"]: e for e in ss.read_watchlist()}
        entries = []
        for sym in sorted(state.active_symbols):
            if sym in existing:
                entries.append(existing[sym])
            else:
                entries.append({"symbol": sym, "subscribed_at": now_iso})
        ss.write_watchlist(entries)
    except Exception as e:
        print(f"⚠️  persist_watchlist error: {e}", flush=True)
    # Phase 2 (2026-06-10): broadcast the watchlist + scanner metadata to engine
    # consumers (sub-bots + Manny's MBP manual bot). De-duped + no-op when the
    # publisher is disabled, so it's safe to call on every watchlist change.
    _publish_subscriptions()


def _publish_subscriptions():
    """Push the current watchlist + per-symbol scanner metadata to engine
    consumers. Metadata (gap_pct/rvol/float_m) comes from state.candidates;
    symbols without a candidate record (e.g. persisted/databento-bridged) are
    still listed, just with null metadata. Never raises into the caller."""
    try:
        if not _engine_pub.enabled:
            return
        watchlist = sorted(state.active_symbols)
        by_symbol = {}
        for c in (state.candidates or []):
            sym = c.get("symbol")
            if sym:
                by_symbol[sym] = c
        # Float backfill (2026-06-18): scan_catchup/bridged symbols carry no float,
        # so the remote (manual-bot) consumer was falling back to yfinance. Resolve
        # from the shared float_cache (cache-ONLY — no live lookup, never block the
        # publish path) so the engine ships complete float and the MBP can drop its
        # yfinance/Alpaca patch. See warrior_manual CC_TO_COWORK_DATA_WIRING doc.
        try:
            from float_cache import load_float_cache
            _fcache = load_float_cache()
        except Exception:
            _fcache = {}
        # ATH backfill (2026-06-25): all-time high (Databento coverage high) for
        # the manual bot's blue-sky alert + Info panel. Gated WB_ENGINE_ATH_ENABLED
        # so the Databento spend is opt-in. Cache-or-None instantly; the async
        # ath_cache worker fills unknowns over the next few minutes, never
        # blocking the publish path.
        _ath_enabled = os.getenv("WB_ENGINE_ATH_ENABLED", "0") == "1"
        # Session HOD/LOD shipping (2026-06-30). In-memory, no external cost, so
        # default ON — set WB_ENGINE_LEVELS_ENABLED=0 to disable.
        _levels_enabled = os.getenv("WB_ENGINE_LEVELS_ENABLED", "1") == "1"
        _acache = {}
        if _ath_enabled:
            try:
                from ath_cache import load_ath_cache
                _acache = load_ath_cache()
            except Exception:
                _acache = {}
        # Gap/rvol backfill (2026-06-23): symbols subscribed from the Databento
        # watchlist.txt (e.g. GITS/BOLD) aren't in the IBKR scanner's
        # state.candidates, so gap_pct/rvol came through null to the manual bot.
        # watchlist.txt carries them (SYMBOL:gap:rvol:float:pm_volume) — parse it
        # and fill any None. Cache-cheap, never blocks the publish path.
        _wl_meta = {}
        try:
            with open("watchlist.txt") as _wf:
                for _ln in _wf:
                    _ln = _ln.strip()
                    if not _ln or _ln.startswith("#"):
                        continue
                    _p = _ln.split(":")
                    if len(_p) >= 3:
                        def _f(x):
                            try:
                                return float(x)
                            except (TypeError, ValueError):
                                return None
                        _wl_meta[_p[0]] = (_f(_p[1]), _f(_p[2]),
                                           _f(_p[3]) if len(_p) >= 4 else None)
        except Exception:
            pass
        meta = []
        for sym in watchlist:
            c = by_symbol.get(sym)
            _wg, _wr, _wf2 = _wl_meta.get(sym, (None, None, None))
            gap = (c.get("gap_pct") if c else None)
            if gap is None:
                gap = _wg
            rvol = (c.get("relative_volume") if c else None)
            if rvol is None:
                rvol = _wr
            fm = c.get("float_millions") if c else None
            if fm is None:
                _fs = _fcache.get(sym)
                if _fs:
                    fm = round(_fs / 1e6, 2)
            if fm is None:
                fm = _wf2
            _meta_item = {
                "symbol": sym,
                "gap_pct": gap,
                "rvol": rvol,
                "float_m": fm,
            }
            # Session HOD/LOD (2026-06-30): the manual bot used to compute these
            # locally from its since-connect tick stream, so a mid-session
            # restart lost the real high/low (GVH showed 4.23 vs the true 5.31).
            # Ship the engine's authoritative session extremes — bar_builder_1m
            # tracks them from the open (seeded), so they survive a manual-bot
            # restart. Gated WB_ENGINE_LEVELS_ENABLED (default on — in-memory,
            # no external cost unlike ATH). Periodically republished from the
            # main loop so the on-connect snapshot stays fresh.
            if _levels_enabled and state.bar_builder_1m is not None:
                try:
                    _h = state.bar_builder_1m.get_hod(sym)
                    _l = state.bar_builder_1m.get_lod(sym)
                    if isinstance(_h, (int, float)) and _h > 0:
                        _meta_item["hod"] = round(float(_h), 4)
                    if isinstance(_l, (int, float)) and _l > 0:
                        _meta_item["lod"] = round(float(_l), 4)
                except Exception:
                    pass
            if _ath_enabled:
                try:
                    from ath_cache import get_ath
                    _ath = get_ath(sym, _acache)
                    if _ath is not None:
                        _meta_item["ath"] = round(_ath, 4)
                except Exception:
                    pass
            meta.append(_meta_item)
        _engine_pub.publish_subscriptions(watchlist, meta=meta)
    except Exception:
        pass  # never let the publisher break the subscribe/persist path


def _risk_flush_loop():
    """Background loop persisting risk.json every 60s. Writes are cheap but
    this is a belt-and-suspenders in case a transition-point write is missed."""
    while True:
        time.sleep(60)
        try:
            persist_risk()
        except Exception as e:
            print(f"⚠️  RISK FLUSH ERROR: {e}", flush=True)


def start_tick_flush_thread():
    """Start the periodic tick-cache flush thread. Idempotent."""
    if not TICK_FLUSH_ENABLED:
        print("Tick flush thread disabled (WB_TICK_FLUSH_ENABLED=0)", flush=True)
        return
    t = threading.Thread(target=_tick_flush_loop, daemon=True, name="tick-flush")
    t.start()
    print(f"📦 Tick flush thread started (every {SESSION_FLUSH_SEC}s)", flush=True)


def start_risk_flush_thread():
    """Start the periodic risk.json flush thread. Safety net — transition
    writes in exit_trade should keep risk.json fresh, but a background
    flush every 60s protects against a missed write point."""
    t = threading.Thread(target=_risk_flush_loop, daemon=True, name="risk-flush")
    t.start()
    print("📊 Risk flush thread started (every 60s)", flush=True)


def on_ib_error(reqId, errorCode, errorString, contract):
    """Handle IBKR error events — especially market data and competing session errors."""
    # Market data errors that may require resubscription
    MKTDATA_ERRORS = {10197, 354, 2104, 2106, 2158}

    if errorCode in MKTDATA_ERRORS:
        sym = contract.symbol if contract else "?"
        print(f"⚠️ IBKR ERROR {errorCode}: {errorString} (symbol={sym})", flush=True)
        if errorCode == 10197:
            print(f"  >> Competing session detected! Re-subscribing all active symbols...", flush=True)
            # Drop all Tier-1 state — manage_tier1_subscriptions will re-promote next cycle.
            cancel_all_tick_by_tick(reason="competing_session")
            for symbol in list(state.active_symbols):
                c = state.contracts.get(symbol)
                if c:
                    try:
                        state.ib.cancelMktData(c)
                        state.ib.sleep(1)
                        ticker = state.ib.reqMktData(c, '233', False, False)
                        state.tickers[symbol] = ticker
                    except Exception as e:
                        print(f"  Re-sub failed for {symbol}: {e}", flush=True)
            print(f"  >> Re-subscription complete for {len(state.active_symbols)} symbols", flush=True)
    elif errorCode not in {2104, 2106, 2158, 2119}:
        # Log non-informational errors
        sym = contract.symbol if contract else "?"
        print(f"IBKR ERROR {errorCode}: {errorString} (reqId={reqId}, symbol={sym})", flush=True)
        # Error 162 = "API scanner subscription cancelled" — the wedge signature.
        # run_scanner() reads this counter to detect a stuck scanner. See
        # SCANNER_WEDGE_* constants.
        if errorCode == 162:
            state.scanner_162_count += 1


def preflight_port_check():
    """Verify no port conflicts before connecting. Uses IBKR_PORT from .env
    so it works for both paper (4002) and live (4001) configurations."""
    import subprocess
    target_port = IBKR_PORT
    other_port = 7497
    ports = {target_port: False, other_port: False}
    for port in ports:
        try:
            result = subprocess.run(["lsof", "-i", f":{port}"], capture_output=True, text=True)
            if result.stdout.strip():
                ports[port] = True
                print(f"  Port {port}: IN USE", flush=True)
            else:
                print(f"  Port {port}: free", flush=True)
        except FileNotFoundError:
            # lsof not available — try socket connect instead
            import socket
            try:
                s = socket.socket()
                s.settimeout(1)
                s.connect(("127.0.0.1", port))
                s.close()
                ports[port] = True
                print(f"  Port {port}: IN USE", flush=True)
            except Exception:
                print(f"  Port {port}: free", flush=True)

    if ports[target_port] and ports[other_port]:
        print(f"🔴 CRITICAL: Both ports {target_port} AND {other_port} are occupied!", flush=True)
        print("  This can cause IBKR data routing confusion. Kill one.", flush=True)
        sys.exit(1)

    if not ports[target_port]:
        print(f"  WARNING: Port {target_port} not yet open (Gateway may still be starting)", flush=True)


def on_pending_tickers_backup(tickers):
    """Backup listener: alert if pendingTickersEvent fires but on_ticker_update is stale."""
    if not state.last_on_ticker_fire:
        return
    stale_seconds = (datetime.now(ET) - state.last_on_ticker_fire).total_seconds()
    if stale_seconds > 30:
        print(f"⚠️ STALE TICKERS: pendingTickersEvent fired but on_ticker_update "
              f"hasn't fired in {stale_seconds:.0f}s — possible callback issue!", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Box Strategy — Live Integration
# ══════════════════════════════════════════════════════════════════════

def run_box_scanner():
    """Run box scanner at checkpoint times. Applies Vol Sweet Spot filter."""
    if not BOX_ENABLED:
        return
    now = datetime.now(ET)

    # Skip Fridays
    if now.weekday() == 4 and BOX_SKIP_FRIDAY:
        return

    # Don't re-scan within 5 minutes
    if state.last_box_scan_time:
        if (now - state.last_box_scan_time).total_seconds() < 300:
            return

    # Only scan at designated checkpoints (within 2 min window)
    should_scan = False
    for checkpoint in BOX_SCAN_CHECKPOINTS:
        cp_dt = now.replace(hour=checkpoint.hour, minute=checkpoint.minute, second=0, microsecond=0)
        if abs((cp_dt - now).total_seconds()) < 120:
            should_scan = True
            break
    if not should_scan:
        return

    print(f"\n[BOX] Scanner running at {now.strftime('%H:%M')} ET...", flush=True)
    try:
        candidates = scan_box_candidates(state.ib)

        # Apply Vol Sweet Spot filters
        filtered = []
        for c in candidates:
            rp = c.get("range_pct", 0)
            total_tests = c.get("high_tests", 0) + c.get("low_tests", 0)
            price = c.get("price", 0)
            adr_util = c.get("adr_util_today", 999)

            if rp < BOX_FILTER_MIN_RANGE_PCT or rp > BOX_FILTER_MAX_RANGE_PCT:
                continue
            if total_tests < BOX_FILTER_MIN_TOTAL_TESTS:
                continue
            if price < BOX_FILTER_MIN_PRICE:
                continue
            if adr_util > BOX_FILTER_MAX_ADR_UTIL:
                continue
            filtered.append(c)

        state.box_candidates = sorted(filtered, key=lambda x: x.get("box_score", 0), reverse=True)
        state.last_box_scan_time = now

        print(f"  [BOX] {len(state.box_candidates)} candidates passed filter "
              f"(from {len(candidates)} raw)", flush=True)
        for c in state.box_candidates[:5]:
            print(f"    {c['symbol']}: score={c['box_score']:.1f}, range={c['range_pct']:.1f}%, "
                  f"tests={c['high_tests']}H/{c['low_tests']}L, price=${c['price']:.2f}", flush=True)
    except Exception as e:
        print(f"  [BOX] Scanner error: {e}", flush=True)
        traceback.print_exc()


def subscribe_box_symbol(symbol: str):
    """Subscribe to a box candidate for tick/bar data via IBKR."""
    if symbol in state.active_symbols:
        state.box_active_symbol = symbol
        return  # Already subscribed (maybe momentum is watching it)

    contract = Stock(symbol, "SMART", "USD")
    try:
        state.ib.qualifyContracts(contract)
        ticker = state.ib.reqMktData(contract, "233", False, False)
        state.contracts[symbol] = contract
        state.tickers[symbol] = ticker
        state.active_symbols.add(symbol)
        state.box_active_symbol = symbol
        state.tick_counts[symbol] = 0
        state.tick_buffer[symbol] = []
        print(f"  [BOX] Subscribed to {symbol} for box trading", flush=True)
        persist_watchlist()
    except Exception as e:
        print(f"  [BOX] Subscribe error {symbol}: {e}", flush=True)


def on_box_bar_close_1m(bar):
    """Process 1-minute bar for box strategy."""
    if not BOX_ENABLED or not state.box_engine:
        return
    if bar.symbol != state.box_active_symbol:
        return

    result = state.box_engine.on_bar(bar)

    if result is None:
        # Check if engine opened a trade internally
        if state.box_engine.active_trade and not state.box_position:
            _enter_box_trade()
    elif result:
        # Exit signal from engine
        if state.box_position:
            _exit_box_trade(result)


def _enter_box_trade():
    """Enter a box trade via Alpaca."""
    trade = state.box_engine.active_trade
    symbol = trade.symbol

    # Safety: no simultaneous positions (unless gated on)
    if not BOX_SIMULTANEOUS and state.open_position:
        print(f"  [BOX] Entry blocked — momentum position open ({state.open_position['symbol']})", flush=True)
        return
    if state.box_position:
        return
    if state.box_daily_pnl <= -BOX_MAX_LOSS_SESSION:
        print(f"  [BOX] Entry blocked — session loss cap hit (${state.box_daily_pnl:.2f})", flush=True)
        return

    entry_price = trade.entry_price
    shares = trade.shares
    notional = entry_price * shares

    print(f"\n[BOX] ENTRY: {symbol} {shares} shares @ ${entry_price:.2f} "
          f"(notional ${notional:,.0f})", flush=True)
    print(f"  Box: ${state.box_engine.box_bottom:.2f} - ${state.box_engine.box_top:.2f} "
          f"(range ${state.box_engine.box_range:.2f}, mid ${state.box_engine.box_mid:.2f})", flush=True)
    print(f"  Stop: ${state.box_engine.hard_stop_price:.2f}", flush=True)

    initial_slip = _entry_slippage_for(entry_price)
    limit_price = round(entry_price + initial_slip, 2)
    original_limit = limit_price
    try:
        result = state.broker.submit_limit(symbol, shares, "BUY", limit_price)
        order_id = result.order_id

        state.box_position = {
            "symbol": symbol,
            "qty": shares,
            "entry": entry_price,
            "order_id": order_id,
            "fill_confirmed": False,
            "setup_type": "box",
        }
        print(f"  [BOX] Order submitted: {order_id} @ ${limit_price:.2f} "
              f"(slip=${initial_slip:.3f})", flush=True)

        import threading
        def verify_box_fill():
            _verify_fill_with_retry(
                symbol=symbol, qty=shares, r=None,
                initial_order_id=order_id, initial_limit=limit_price,
                original_limit=original_limit, position_attr="box_position",
                log_prefix="[BOX] ",
            )
        threading.Thread(target=verify_box_fill, daemon=True).start()
    except Exception as e:
        print(f"  [BOX] ORDER FAILED: {e}", flush=True)


def _exit_box_trade(reason: str):
    """Exit a box trade via Alpaca."""
    if not state.box_position:
        return

    symbol = state.box_position["symbol"]
    qty = state.box_position["qty"]
    entry = state.box_position["entry"]

    # Get exit price from engine or ticker
    exit_price = 0
    if state.box_engine and state.box_engine.trades:
        last_trade = state.box_engine.trades[-1]
        if last_trade.exit_price:
            exit_price = last_trade.exit_price
    if exit_price <= 0:
        ticker = state.tickers.get(symbol)
        if ticker and ticker.last and not math.isnan(ticker.last):
            exit_price = ticker.last

    pnl = (exit_price - entry) * qty if exit_price > 0 else 0

    print(f"\n[BOX] EXIT: {symbol} {qty} shares @ ${exit_price:.2f} "
          f"reason={reason} P&L=${pnl:+,.2f}", flush=True)

    try:
        base = _exit_limit_price(exit_price, "SELL")
        aware = compute_alpaca_aware_limit(symbol, exit_price, "SELL")
        sell_limit = min(aware, base)
        state.broker.submit_limit(symbol, qty, "SELL", sell_limit,
                                  extended_hours=True)
    except Exception as e:
        # Per project rule: no market fallback. Box exits retry on the next
        # box-loop iteration with fresh price.
        print(f"  [BOX] EXIT ORDER FAILED: {e} — no market fallback (per project rules)",
              flush=True)
        return

    state.box_daily_pnl += pnl
    state.box_daily_trades += 1
    state.box_closed_trades.append({
        "symbol": symbol, "setup_type": "box", "reason": reason,
        "pnl": pnl, "entry": entry, "exit": exit_price,
    })
    state.box_position = None


def main():
    global STARTING_EQUITY  # Must be at top of function before any reference

    # Engine publisher startup (2026-05-20). Idempotent + no-op when
    # disabled. Started before anything else so the socket is up by the
    # time the sub-bot tries to connect (sub-bot has its own retry loop).
    _engine_pub.start()

    # Session-resume CLI flags (see cowork_reports/2026-04-15_greenlight_session_resume.md)
    import argparse
    parser = argparse.ArgumentParser(description="Warrior Bot V3 Hybrid")
    parser.add_argument("--fresh", action="store_true",
                        help="Force cold start, overwriting today's session marker")
    parser.add_argument("--scrub", action="store_true",
                        help="Wipe today's session_state/ and tick_cache/, then cold start")
    args, _ = parser.parse_known_args()

    # Decide boot mode BEFORE any expensive work. Resume requires the feature
    # gate to be explicitly enabled — otherwise we always cold-start but still
    # write durable state so a later enabled run can resume.
    import session_state as ss
    boot_mode, boot_reason = ss.decide_boot_mode(fresh=args.fresh, scrub=args.scrub)
    if boot_mode == "resume" and not SESSION_RESUME_ENABLED:
        print(f"BOOT: would RESUME (reason={boot_reason}) but WB_SESSION_RESUME_ENABLED=0 — forcing COLD", flush=True)
        boot_mode = "cold"
        boot_reason = "resume_gate_off"
    if boot_mode == "resume":
        age = ss.marker_age_seconds()
        age_str = f"{age:.0f}s" if age is not None else "unknown"
        print(f"BOOT: RESUME mode (marker age={age_str}, reason={boot_reason})", flush=True)
    else:
        print(f"BOOT: COLD start (reason={boot_reason})", flush=True)

    print("=" * 60)
    print("  WARRIOR BOT V3 — Hybrid (IBKR data + Alpaca execution)")
    print(f"  Squeeze: {'ON' if SQ_ENABLED else 'OFF'}")
    print(f"  MP: {'ON' if MP_ENABLED else 'OFF'}")
    print(f"  MP V2 (Re-Entry): {'ON' if MP_V2_ENABLED else 'OFF'}")
    print(f"  Short: {'ON (strat=' + SHORT_STRATEGY + ')' if SHORT_ENABLED else 'OFF'}")
    print(f"  Max entries/day: {MAX_DAILY_ENTRIES if MAX_DAILY_ENTRIES > 0 else 'unlimited'}")
    print(f"  Buying power: {BUYING_POWER_PCT*100:.0f}% of 2x margin" if SCALE_NOTIONAL else "  Notional cap: fixed")
    print(f"  Port: {IBKR_PORT}")
    print(f"  Risk: {RISK_PCT*100:.1f}% per trade")
    print(f"  Starting Equity: ${STARTING_EQUITY:,.0f}")
    if DAILY_LOSS_SCALE:
        effective_max_loss = max(MAX_DAILY_LOSS, STARTING_EQUITY * 0.02)
        print(f"  Max Daily Loss: ${effective_max_loss:,.0f} (2% of equity, scaling)")
    else:
        print(f"  Max Daily Loss: ${MAX_DAILY_LOSS:,.0f} (fixed)")
    print(f"  Windows: {TRADING_WINDOWS_STR}")
    print(f"  SQ Target R: {SQ_TARGET_R}")
    if WAVE_BREAKOUT_ENABLED:
        eff, hc, ec, fl = _wb_effective_notional_cap(STARTING_EQUITY)
        print(f"  WB notional cap (at starting equity ${STARTING_EQUITY:,.0f}): "
              f"effective=${eff:,.0f} (equity_cap=${ec:,.0f}, floor=${fl:,.0f}, "
              f"ceiling=${hc:,.0f})")
        print(f"  WB pyramid: {'ON' if os.getenv('WB_WB_PYRAMID_ENABLED', '0') == '1' else 'OFF'}")
    print("=" * 60)
    if not SQ_ENABLED:
        print("⚠️  WARNING: WB_SQUEEZE_ENABLED is OFF — bot will not trade squeezes!")
        print("  Set WB_SQUEEZE_ENABLED=1 in .env or environment to enable.")

    # Pre-flight: check for port conflicts
    print("\nPre-flight port check:")
    preflight_port_check()

    # Start main-thread watchdog (kills bot if frozen >120s)
    start_watchdog()

    # Connect to Alpaca (execution)
    apca_key = os.getenv("APCA_API_KEY_ID")
    apca_secret = os.getenv("APCA_API_SECRET_KEY")
    apca_paper = os.getenv("APCA_PAPER", "true").lower() == "true"
    if not apca_key or not apca_secret:
        print("FATAL: Missing APCA_API_KEY_ID or APCA_API_SECRET_KEY", flush=True)
        sys.exit(1)
    state.alpaca = TradingClient(apca_key, apca_secret, paper=apca_paper)
    print(f"Alpaca connected ({'PAPER' if apca_paper else 'LIVE'})", flush=True)

    # Alpaca data client — used for latency diagnostic snapshots and (when
    # WB_ALPACA_AWARE_LIMITS=1) limit-pricing calibration. Separate from the
    # trading client. Failures here MUST NOT block bot startup — diagnostic
    # will then silently emit None for Alpaca fields.
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        state.alpaca_data_client = StockHistoricalDataClient(apca_key, apca_secret)
        print(f"Alpaca data client connected (for latency diagnostic / aware-limits)", flush=True)
    except Exception as _e:
        print(f"  WARN: Alpaca data client init failed: {_e} — "
              f"latency diagnostic will run without Alpaca snapshots", flush=True)
        state.alpaca_data_client = None

    # Persist boot mode on state for downstream branching (seed_symbol →
    # tick-replay, order reconciliation, etc.). On cold boot we write/refresh
    # the marker so a subsequent crash can resume from this session.
    state.boot_mode = boot_mode
    if boot_mode == "cold":
        ss.write_marker()

    # Start periodic tick-cache flush (crash-safety for backtest data).
    # Always-on, independent of WB_SESSION_RESUME_ENABLED.
    start_tick_flush_thread()
    start_risk_flush_thread()

    # Connect to IBKR BEFORE reconcile — reconcile uses state.broker, and
    # state.broker requires a live state.ib when WB_BROKER=ibkr.
    ib = connect()
    ib.errorEvent += on_ib_error

    # Initialize broker abstraction. All order flow in this file goes
    # through state.broker (never state.alpaca directly). WB_BROKER
    # selects the backend; default "alpaca" preserves legacy behavior.
    state.broker = make_broker(
        BROKER_BACKEND, alpaca=state.alpaca, ib=state.ib, contracts=state.contracts,
    )
    print(f"Broker: {BROKER_BACKEND.upper()}", flush=True)

    # Subscription watchdog (observability for Tier-2 reqMktData wedges).
    # Per cowork_reports/2026-05-26_subscription_watchdog_directive.md.
    # Gated by WB_SUB_WATCHDOG_ENABLED; emits SUBSCRIPTION_AUDIT JSON lines
    # consumed by scripts/abc_compare_daily.py.
    state.subscription_watchdog = SubscriptionWatchdog(state, state.ib)
    print(
        f"SubscriptionWatchdog: "
        f"{'ENABLED' if state.subscription_watchdog.enabled else 'disabled'}",
        flush=True,
    )

    # Runtime broker-mismatch assert (2026-05-18 — Patch 4 of bundled deploy).
    _assert_broker_matches()

    # Startup position reconciliation. Resume mode rehydrates trade state
    # from open_trades.json + reconciles qty/orders against the broker;
    # cold mode adopts any unexpected broker position with conservative defaults.
    if boot_mode == "resume":
        resume_reconcile()
    else:
        reconcile_positions_on_startup()

    # Fix 5: Graceful shutdown — check for orphan positions
    import signal as signal_mod
    def graceful_shutdown(signum, frame):
        print("\n🛑 SHUTDOWN SIGNAL RECEIVED", flush=True)
        try:
            positions = state.broker.get_positions() if state.broker else []
            if positions:
                for pos in positions:
                    print(f"  ⚠️ POSITION OPEN AT SHUTDOWN: {pos.symbol} "
                          f"qty={pos.qty} P&L=${pos.unrealized_pnl:+,.2f}", flush=True)
                print("  *** POSITIONS LEFT OPEN — WILL NEED MANUAL MANAGEMENT ***", flush=True)
            else:
                print("  All positions flat. Clean shutdown.", flush=True)
        except Exception as e:
            print(f"  Could not check positions at shutdown: {e}", flush=True)
        sys.exit(0)
    signal_mod.signal(signal_mod.SIGTERM, graceful_shutdown)
    signal_mod.signal(signal_mod.SIGINT, graceful_shutdown)

    # Fetch actual account equity for position sizing (backend-agnostic)
    actual_equity = get_account_equity()
    print(f"Account equity: ${actual_equity:,.0f}", flush=True)
    STARTING_EQUITY = actual_equity

    # ── EPL Framework ──
    if EPL_ENABLED:
        state.epl_watchlist = EPLWatchlist()
        state.epl_registry = StrategyRegistry()
        state.epl_arbitrator = PositionArbitrator(state.epl_registry, state.epl_watchlist)
        _epl_mp = EPLMPReentry()
        if EPL_MP_ENABLED:
            state.epl_registry.register(_epl_mp)
        print(f"EPL initialized: {state.epl_registry.strategy_count} strategies registered", flush=True)
    else:
        print("EPL disabled (WB_EPL_ENABLED=0)", flush=True)

    # Bar builders
    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
    if BOX_ENABLED:
        state.box_bar_builder_1m = TradeBarBuilder(on_bar_close=on_box_bar_close_1m, et_tz=ET, interval_seconds=60)

    # Wire ticker updates + backup stale-ticker monitor
    ib.pendingTickersEvent += on_ticker_update
    ib.pendingTickersEvent += on_pending_tickers_backup

    # Initial scan
    run_scanner()
    poll_watchlist()

    # Main event loop
    windows_str = ", ".join(f"{s.strftime('%H:%M')}-{e.strftime('%H:%M')}" for s, e in TRADING_WINDOWS)
    print(f"\nBot running. Windows: {windows_str} ET. Ctrl+C to stop.", flush=True)
    try:
        while True:
            now = datetime.now(ET)

            # Past all windows for the day → shut down
            if past_all_windows(now):
                print(f"\n🛑 All trading windows closed. Shutting down.", flush=True)
                break

            # Check if we're in a trading window or the dead zone
            momentum_active = in_trading_window(now)
            box_active = in_box_window(now)
            active = momentum_active or box_active

            if active:
                # Coming back from dead zone — reset for fresh evening session
                if state.in_dead_zone:
                    state.in_dead_zone = False
                    state.last_scan_time = None  # Force immediate rescan
                    # Reset everything for fresh evening session
                    # Cancel morning subscriptions (evening stocks will be different)
                    for sym in list(state.active_symbols):
                        c = state.contracts.get(sym)
                        if c:
                            try:
                                state.ib.cancelMktData(c)
                            except Exception:
                                pass
                    # Drop all Tier-1 tick-by-tick subs — evening session
                    # repromotes from scratch via manage_tier1_subscriptions.
                    cancel_all_tick_by_tick(reason="dead_zone_reset")
                    state.active_symbols.clear()
                    state.contracts.clear()
                    state.tickers.clear()
                    state.tick_counts.clear()
                    state.tier.clear()
                    state.tier1_volume_buckets.clear()
                    state.tier1_volume_rank.clear()
                    state.sq_detectors.clear()
                    state.mp_detectors.clear()
                    state.ct_detectors.clear()
                    state.wb_detectors.clear()  # WaveBreakout detectors per-symbol
                    # Note: state.wb_positions is intentionally NOT cleared on
                    # window-close — open positions persist across the dead
                    # zone (the bot exits them via manage_wb_exits below if
                    # market reopens with a reverse). Position cleanup happens
                    # at session_end_force_exit time.
                    # Reset bar builders so evening bars start fresh
                    state.bar_builder_1m = TradeBarBuilder(on_bar_close=on_bar_close_1m, et_tz=ET, interval_seconds=60)
                    state.bar_builder_10s = TradeBarBuilder(on_bar_close=on_bar_close_10s, et_tz=ET, interval_seconds=10)
                    print(f"\n🟢 Evening session started ({now.strftime('%H:%M')} ET). Full reset. Resuming trading.", flush=True)

                # Periodic rescan (momentum)
                if momentum_active:
                    run_scanner()
                    poll_watchlist()
                    run_intraday_adder()

                    # Check halts
                    check_halts()

                # Tick health audit (every 60s)
                audit_tick_health()

                # Fix 3: Periodic position sync with Alpaca (every 60s)
                periodic_position_sync()

                # Lever 3 (2026-05-26): periodic broker reconciliation.
                # Catches orphan positions that survived past the exit path's
                # Lever 1 keep-alive (e.g., bot restart between exit submit
                # and verify) by comparing bot state vs broker truth.
                if (state.last_reconcile_at is None
                        or (now - state.last_reconcile_at).total_seconds() >= RECONCILE_INTERVAL_SEC):
                    reconcile_positions_periodic()
                    state.last_reconcile_at = now

                # Tick-By-Tick tier rebalance (every 30s when WB_TBT_ENABLED=1).
                manage_tier1_subscriptions()

                # Periodic subscription republish (2026-06-30) so the engine's
                # session HOD/LOD in the cached snapshot stay fresh for the
                # manual bot — including the frame re-sent to a reconnecting
                # client after a manual-bot restart. Throttled; the publisher
                # de-dups, so this only emits when the rounded HOD/LOD moved.
                _last_lvl_pub = getattr(state, "last_levels_publish", None)
                if (_last_lvl_pub is None
                        or (now - _last_lvl_pub).total_seconds() >= LEVELS_PUBLISH_INTERVAL_SEC):
                    _publish_subscriptions()
                    state.last_levels_publish = now

                # Subscription wedge audit (every 60s heuristic, 300s direct
                # query when WB_SUB_WATCHDOG_ENABLED=1). Side-effect-free —
                # emits SUBSCRIPTION_AUDIT JSON for downstream ingest.
                state.subscription_watchdog.tick(now)

                # Session-end force-exit (Cowork directive 2026-05-15 P0.2).
                # Fires once at 19:55 ET. Flattens any open position via
                # aggressive SELL LIMIT with chase-down ladder (no market orders).
                _maybe_session_end_force_exit()

                # ── Box strategy logic ──
                if box_active:
                    run_box_scanner()

                    # Init box engine on top candidate if we don't have one
                    if (state.box_candidates and not state.box_engine
                            and not state.box_position):
                        top = state.box_candidates[0]
                        subscribe_box_symbol(top["symbol"])
                        state.box_engine = BoxStrategyEngine(top, exit_variant="midbox")
                        print(f"  [BOX] Engine initialized: {top['symbol']} "
                              f"(score {top['box_score']:.1f})", flush=True)

                    # Force close box position at 3:45 PM
                    if now.time() >= BOX_WINDOW_END and state.box_position:
                        _exit_box_trade("time_stop")
                        state.box_engine = None
            else:
                # In dead zone between windows
                if not state.in_dead_zone:
                    state.in_dead_zone = True
                    # Close any open position before dead zone
                    if state.open_position:
                        sym = state.open_position["symbol"]
                        ticker = state.tickers.get(sym)
                        # Try last, then bid, then close as fallback price
                        price = None
                        if ticker:
                            for attr in ("last", "bid", "close"):
                                p = getattr(ticker, attr, None)
                                if p and not math.isnan(p) and p > 0:
                                    price = p
                                    break
                        if price:
                            print(f"🛑 Window closing — exiting {sym} at ${price:.2f}", flush=True)
                            exit_trade(sym, price, state.open_position["qty"], "window_close")
                        else:
                            print(f"⚠️ Window closing — NO PRICE for {sym}, position left open!", flush=True)
                    # Close any box position before dead zone
                    if BOX_ENABLED and state.box_position:
                        _exit_box_trade("window_close")
                        state.box_engine = None
                    # Close any Wave Breakout positions before dead zone
                    # (force-exit per WB_WB_SESSION_END_FORCE_EXIT semantics)
                    if WAVE_BREAKOUT_ENABLED and state.wb_positions:
                        for wb_sym in list(state.wb_positions.keys()):
                            ticker = state.tickers.get(wb_sym)
                            wb_price = None
                            if ticker:
                                for attr in ("last", "bid", "close"):
                                    p = getattr(ticker, attr, None)
                                    if p and not math.isnan(p) and p > 0:
                                        wb_price = p
                                        break
                            if wb_price:
                                print(f"[WB] {wb_sym} window_close — force exit at ${wb_price:.2f}", flush=True)
                                place_wave_breakout_exit(
                                    wb_sym,
                                    f"WB_EXIT: reason=window_close exit={wb_price} r_mult=0.0",
                                )
                            else:
                                print(f"[WB] {wb_sym} window_close — NO PRICE, position left open!", flush=True)

                    # Save tick cache from morning session
                    save_tick_cache()
                    print(f"\n💤 Dead zone ({now.strftime('%H:%M')} ET). Sleeping until next window...", flush=True)

            # Issue 5: Pending order timeout check (cancel unfilled entries after 15s)
            if state.pending_order:
                elapsed = (now - state.pending_order['placed_time']).total_seconds()
                if elapsed > state.pending_order['timeout_seconds']:
                    state.broker.cancel_order(state.pending_order['order_id'])
                    if state.open_position and not state.open_position.get('fill_confirmed'):
                        state.open_position = None
                    state.pending_order = None
                    print("  ORDER TIMEOUT: Entry order cancelled after 10s — no fill", flush=True)

            # Issue 9: Connection watchdog — reconnect on disconnect
            if not state.ib.isConnected():
                print("CONNECTION LOST — attempting reconnect...", flush=True)
                try:
                    _engine_pub.set_ibkr_connected(False)
                except Exception:
                    pass
                for attempt in range(1, 6):
                    try:
                        state.ib.disconnect()
                        time.sleep(10)
                        state.ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
                        # Re-wire events
                        state.ib.pendingTickersEvent += on_ticker_update
                        state.ib.pendingTickersEvent += on_pending_tickers_backup
                        state.ib.errorEvent += on_ib_error
                        # Drop Tier-1 state — IB Gateway dropped subscriptions
                        # on disconnect; manage_tier1_subscriptions repromotes
                        # next cycle based on current detector state.
                        state.tbt_tickers.clear()
                        state.tbt_last_processed_index.clear()
                        state.tbt_subscribed_at.clear()
                        for s in list(state.tier.keys()):
                            state.tier[s] = "snapshot"
                        # Re-subscribe all active symbols with RTVolume
                        for sym in list(state.active_symbols):
                            c = state.contracts.get(sym)
                            if c:
                                ticker = state.ib.reqMktData(c, '233', False, False)
                                state.tickers[sym] = ticker
                        try:
                            _engine_pub.set_ibkr_connected(True)
                        except Exception:
                            pass
                        print(f"  Reconnected on attempt {attempt}", flush=True)
                        break
                    except Exception as e:
                        print(f"  Reconnect attempt {attempt}/5 failed: {e}", flush=True)
                        if attempt == 5:
                            print("  FATAL: Could not reconnect after 5 attempts", flush=True)

            # Heartbeat every ~1 minute
            if now.second < 2:
                pos_parts = []
                if state.open_position:
                    pos_parts.append(
                        f"LONG={state.open_position['symbol']} @ "
                        f"${state.open_position['entry']:.2f}"
                    )
                if state.open_short:
                    _conf = "" if state.open_short.get("fill_confirmed") else " (unconfirmed)"
                    pos_parts.append(
                        f"SHORT={state.open_short['symbol']} @ "
                        f"${state.open_short['entry']:.2f}{_conf}"
                    )
                pos_str = " | ".join(pos_parts) if pos_parts else "flat"
                if BOX_ENABLED and state.box_position:
                    pos_str += f" | BOX={state.box_position['symbol']} @ ${state.box_position['entry']:.2f}"
                zone = "ACTIVE" if active else "SLEEP"
                if box_active and not momentum_active:
                    zone = "BOX"

                # Tick flow summary
                total_ticks = sum(state.tick_counts.values())
                tick_syms = []
                for sym in sorted(state.active_symbols):
                    tc = state.tick_counts.get(sym, 0)
                    sq = state.sq_detectors.get(sym)
                    sq_st = sq._state if sq else "?"
                    armed_str = f"${sq.armed.trigger_high:.2f}" if (sq and sq.armed) else ""
                    tick_syms.append(f"{sym}:{tc}t/{sq_st}" + (f"/arm{armed_str}" if armed_str else ""))

                # Connection health
                connected = state.ib.isConnected() if state.ib else False

                print(f"[{now.strftime('%H:%M:%S')} ET] {zone} | "
                      f"{pos_str} | daily=${state.daily_pnl:+,.0f} ({state.daily_trades}t) | "
                      f"conn={'OK' if connected else 'DOWN'} | "
                      f"ticks={total_ticks} | "
                      f"{' '.join(tick_syms) if tick_syms else 'no symbols'}",
                      flush=True)

            # Heartbeat for watchdog — proves main thread is alive
            update_heartbeat()

            # Let ib_insync process events (sleep longer during dead zone)
            ib.sleep(30 if state.in_dead_zone else 1)

    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
    except Exception:
        print("🔥 Bot crashed:")
        traceback.print_exc()
    finally:
        # Close any open momentum position
        if state.open_position:
            sym = state.open_position["symbol"]
            ticker = state.tickers.get(sym)
            if ticker and ticker.last:
                exit_trade(sym, ticker.last, state.open_position["qty"], "shutdown")

        # Close any open box position
        if BOX_ENABLED and state.box_position:
            _exit_box_trade("shutdown")

        # Save tick cache for backtesting (before disconnect)
        save_tick_cache()

        # Disconnect
        ib.disconnect()

        # Print summary
        print(f"\n{'='*60}")
        print(f"  SESSION SUMMARY")
        print(f"  Momentum Trades: {state.daily_trades}")
        print(f"  Momentum P&L: ${state.daily_pnl:+,.0f}")
        for t in state.closed_trades:
            print(f"    {t['symbol']} {t['setup_type']} {t['reason']}: ${t['pnl']:+,.0f}")
        if BOX_ENABLED:
            print(f"  Box Trades: {state.box_daily_trades}")
            print(f"  Box P&L: ${state.box_daily_pnl:+,.2f}")
            for t in state.box_closed_trades:
                print(f"    [BOX] {t['symbol']} {t['reason']}: ${t['pnl']:+,.2f}")
            print(f"  COMBINED P&L: ${state.daily_pnl + state.box_daily_pnl:+,.2f}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
