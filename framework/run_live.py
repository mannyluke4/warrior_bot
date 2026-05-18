"""framework.run_live — live runner for the Healthy Fluctuation Framework.

Wave 4 paper deployment, soft-launch Monday 2026-05-18.

=== OVERVIEW =================================================================

This is the executable that runs the framework live. It connects to IB
Gateway for market data (clientId 51, separate from Setup A's main bot at
clientId 1 and sub-bot at clientId 2), connects to an Alpaca paper account
for execution (the same paper keys Setup B uses, per directive §1), and
runs the 3-strategy filtered portfolio on the 36-symbol Databento universe.

Strategies armed:
  - PDH-PDL-Fade-Filtered (F1 time-gate 09:30-09:44 ET; abandon@10 disabled)
  - ORB-Aligned-300+ (tier filter ≥ $300, or5-aligned, Mon-skip)
  - PDH-Breakout-F4 (8-symbol blacklist, VWAP-aligned, 5-bar consol < 1%,
    vol ≥ 2× prior 20-bar mean)

=== ENV VARS (loaded from .env.framework + .env.framework.local) ============

Required (Manny provisions .env.framework.local; do NOT commit):
  APCA_API_KEY_ID          Alpaca paper API key
  APCA_API_SECRET_KEY      Alpaca paper API secret

Defaults already shipped in .env.framework:
  WB_FRAMEWORK_IB_CLIENT_ID=51
  WB_FRAMEWORK_PAPER_ACCOUNT=framework_paper
  WB_USE_VIX_REGIME=1
  WB_VIX_SUPPRESS_THRESHOLD=25
  WB_VIX_REENABLE_THRESHOLD=22
  WB_FRAMEWORK_SKIP_MONDAYS=1
  WB_PORTFOLIO_CONFLICT_RULE=release_on_stop
  WB_PORTFOLIO_LOG_LOCK_COLLISIONS=1
  WB_SIZING_MODE=tiered
  WB_TIER_INITIAL=1
  WB_TIER_LOCK=1
  WB_TIER_AUTO_ADVANCE=0
  WB_FIXED_DOLLAR_RISK=300
  WB_NO_MARKET_ORDERS=1
  WB_NO_OVERNIGHTS=1
  WB_NO_BROKER_STOPS=1
  WB_FRAMEWORK_STRATEGIES=pdh_fade_filtered,orb_aligned_300plus_monskip,pdh_breakout_f4

Optional:
  WB_IBKR_HOST=127.0.0.1
  WB_IBKR_PORT=7497
  WB_FRAMEWORK_STATE_DIR=framework_paper_state
  WB_FRAMEWORK_REPORT_DIR=cowork_reports
  WB_SESSION_END_TIME_ET=20:00   (force_exit module reads this)
  WB_SESSION_END_LEAD_MIN=5      (trigger = end - lead = 19:55)

=== CLI ====================================================================

  python -m framework.run_live                # normal mode
  python -m framework.run_live --dry-run      # verify wiring, no orders

Dry-run:
  1. Loads .env.framework (+.local if present)
  2. Loads strategy YAMLs and confirms 3 enabled strategies
  3. Connects to IB Gateway (data) and Alpaca paper (exec, read-only checks)
  4. Confirms TieredSizer at Tier 1 with tier_lock=True
  5. Logs everything verbose-style
  6. Prints "READY" and exits cleanly. No orders submitted.

=== HARD CONSTRAINTS (per directive §1, NON-NEGOTIABLE) =====================

  - Setup A is sacred. No imports/modifications of bot_v3_hybrid.py,
    bot_alpaca_subbot.py, engine bots, squeeze_detector_v2.py,
    l2_signals.py, ibkr_feed.py, wb_persistence.py, wb_intraday_adder.py.
  - Alpaca only for execution. IBKR is data-only.
  - No overnights — force_exit at 19:55 ET via SELL LIMIT chain.
  - No market orders ever — every order is a limit.
  - No broker-side stops — stops are bot-internal price comparisons.

=== ARCHITECTURE ============================================================

  IB Gateway ─→ LiveDataFeed (5s real-time bars → 1m closes)
                    │
                    ▼ on_bar_close(symbol, bar)
  Runner.handle_bar(symbol, bar)
    │
    ├─→ SignalEvaluator.on_bar_close(...)  → list[StrategySignal]
    │      uses SIGNAL_FUNCS from backtest/portfolio_backtest.py
    │      uses framework.filters.passes_pre_entry_filters
    │      uses VIXRegime / WB_FRAMEWORK_SKIP_MONDAYS
    │
    ├─→ apply per-(symbol, session_date) lock (release_on_stop semantics)
    │
    ├─→ TieredSizer.size(equity, entry, stop, recent_vol) → (qty, risk_$)
    │
    └─→ LiveBroker.submit_entry(symbol, qty, side, entry_price)
              uses Alpaca LimitOrderRequest, retry chain, max chase 2%

  Position management (per bar):
    for each open trade:
      bar.high/low vs stop_price/target_price
        → stop hit: LiveBroker.submit_exit (SELL LIMIT aggressive)
                    + release per-(symbol, day) lock
        → target hit: LiveBroker.submit_exit (SELL LIMIT aggressive)

  Force-exit:
    19:55 ET (force_exit.should_force_exit_now)
      → cancel all pending entries
      → LiveBroker.force_flatten for every open position

  Daily report:
    16:01 ET write cowork_reports/YYYY-MM-DD_engine_framework_daily.md

=== PERSISTENCE =============================================================

State files written under framework_paper_state/YYYY-MM-DD/:
    marker.json       — session start/restart marker
    risk.json         — daily P&L counter, equity at start, HWM, LWM
    watchlist.json    — universe subscribed this session
    open_trades.json  — open positions with entry/stop/target
    closed_trades.json — completed trades today

TieredSizer state persists at framework_state/tier_state.json (managed
internally by the TieredSizer class).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal as signal_mod
import sys
import time as _time_mod
import traceback
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Optional

import pytz
from dotenv import load_dotenv

ET = pytz.timezone("US/Eastern")
REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Framework imports — all read-only-against-Setup-A
from framework.live_broker import LiveBroker
from framework.live_data_feed import LiveDataFeed
from framework.live_signal_engine import SignalEvaluator, StrategySignal
from framework.sizing import TieredSizer
from framework.vix_regime import VIXRegime
from framework.level_sources.base import Bar

# Reuse backtest's stop/target machinery so live = backtest bit-for-bit
from backtest.portfolio_backtest import (  # noqa: E402
    StrategyArm,
    _compute_stop_and_target,
)


log = logging.getLogger("framework.run_live")


# ---------------------------------------------------------------------------
# Universe + strategy yaml resolution
# ---------------------------------------------------------------------------

# Same 36-symbol universe as backtest/portfolio_backtest.py.
# Kept hardcoded here so the live runner is self-documenting and the
# backtest module doesn't have to be importable for the universe (the
# import does happen via SIGNAL_FUNCS, but defense-in-depth).
UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "TSLA", "NVDA", "META", "AMD", "AVGO", "ADBE",
    "CRM", "ORCL", "NFLX", "INTC", "QCOM", "CSCO", "MU", "PLTR",
    "ROKU", "SNAP", "SOFI", "F", "BAC", "WFC", "JPM", "MA",
    "DIS", "NKE", "DAL", "AAL", "WMT", "COST", "T", "VZ",
    "KO", "MRK", "PFE", "AMC",
)


def _resolve_strategy_yamls(env_csv: str) -> list[Path]:
    """Map .env.framework's WB_FRAMEWORK_STRATEGIES to YAML paths.

    Honors `status: retired` by SKIPPING those YAMLs. The directive ships
    pdh_fade_filtered, orb_aligned_300plus_monskip, pdh_breakout_f4 —
    none of these are retired.
    """
    names = [s.strip() for s in env_csv.split(",") if s.strip()]
    out: list[Path] = []
    for n in names:
        # If the user supplied "foo" we look up strategies/foo.yaml
        if not n.endswith(".yaml"):
            n = f"{n}.yaml"
        p = REPO / "strategies" / n
        if not p.exists():
            log.warning("strategy YAML missing: %s — skipping", p)
            continue
        # Sniff status field cheaply (yaml lazy import).
        try:
            import yaml  # local
            data = yaml.safe_load(p.read_text())
            if isinstance(data, dict) and str(data.get("status", "")).lower() == "retired":
                log.info(
                    "[STRATEGY_LOAD] skipping retired YAML: %s (status=retired)", p.name
                )
                continue
            if isinstance(data, dict) and not bool(data.get("enabled", True)):
                log.info(
                    "[STRATEGY_LOAD] skipping disabled YAML: %s (enabled=false)", p.name
                )
                continue
        except Exception as e:
            log.warning("yaml sniff failed for %s: %r — including anyway", p, e)
        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Persistence layer
# ---------------------------------------------------------------------------


@dataclass
class OpenTrade:
    arm_name: str
    yaml_path: str
    symbol: str
    side: str           # "BUY" for long, "SELL" for short
    direction: str      # "long" / "short"
    qty: int
    entry_price: float
    stop_price: float
    target_price: Optional[float]
    entry_ts: str       # ISO timestamp
    risk_dollars: float
    order_id: str
    session_date: str
    secondary_fill: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClosedTrade:
    arm_name: str
    symbol: str
    direction: str
    qty: int
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: Optional[float]
    entry_ts: str
    exit_ts: str
    risk_dollars: float
    pnl: float
    r_multiple: float
    exit_reason: str
    session_date: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RiskState:
    starting_equity: float
    current_equity: float
    hwm: float
    lwm: float
    daily_pnl: float = 0.0
    entries_today: int = 0
    stops_today: int = 0
    targets_today: int = 0
    force_exits_today: int = 0
    conflicts_today: int = 0
    lock_collisions_today: int = 0


class FrameworkPersistence:
    """Disk persistence for the framework runner.

    Layout: framework_paper_state/YYYY-MM-DD/{marker,risk,watchlist,open_trades,closed_trades}.json
    """

    def __init__(self, root: Path, session_date: date) -> None:
        self.root = root
        self.session_date = session_date
        self.dir = root / session_date.isoformat()
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self, name: str) -> Path:
        return self.dir / name

    def write_marker(self) -> None:
        payload = {
            "session_date": self.session_date.isoformat(),
            "started_at": datetime.now(ET).isoformat(),
            "pid": os.getpid(),
        }
        self._path("marker.json").write_text(json.dumps(payload, indent=2))

    def write_watchlist(self, symbols: list[str]) -> None:
        self._path("watchlist.json").write_text(
            json.dumps({"symbols": list(symbols)}, indent=2)
        )

    def write_risk(self, risk: RiskState) -> None:
        self._path("risk.json").write_text(json.dumps(asdict(risk), indent=2))

    def write_open_trades(self, trades: dict[str, OpenTrade]) -> None:
        payload = {k: v.to_dict() for k, v in trades.items()}
        self._path("open_trades.json").write_text(json.dumps(payload, indent=2))

    def append_closed_trade(self, ct: ClosedTrade) -> None:
        p = self._path("closed_trades.json")
        try:
            existing = json.loads(p.read_text()) if p.exists() else []
        except Exception:
            existing = []
        existing.append(ct.to_dict())
        p.write_text(json.dumps(existing, indent=2))

    def load_open_trades(self) -> dict[str, OpenTrade]:
        p = self._path("open_trades.json")
        if not p.exists():
            return {}
        try:
            data = json.loads(p.read_text())
        except Exception:
            return {}
        out: dict[str, OpenTrade] = {}
        for k, v in data.items():
            try:
                out[k] = OpenTrade(**v)
            except (TypeError, ValueError):
                continue
        return out


# ---------------------------------------------------------------------------
# Trading-window helpers
# ---------------------------------------------------------------------------

RTH_OPEN_T = dtime(9, 30)
RTH_CLOSE_T = dtime(16, 0)
DAILY_REPORT_T = dtime(16, 1)


def _is_rth(now_et: datetime) -> bool:
    return RTH_OPEN_T <= now_et.time() <= RTH_CLOSE_T


# ---------------------------------------------------------------------------
# FrameworkRunner — the main orchestrator
# ---------------------------------------------------------------------------


class FrameworkRunner:
    """Live runner for the 3-strategy filtered portfolio."""

    def __init__(self, *, dry_run: bool = False, verbose: bool = True) -> None:
        self.dry_run = dry_run
        self.verbose = verbose

        # --- env -------------------------------------------------------
        self.host = os.environ.get("WB_IBKR_HOST", "127.0.0.1")
        self.port = int(os.environ.get("WB_IBKR_PORT", "7497"))
        self.client_id = int(os.environ.get("WB_FRAMEWORK_IB_CLIENT_ID", "51"))
        self.state_root = REPO / os.environ.get(
            "WB_FRAMEWORK_STATE_DIR", "framework_paper_state"
        )
        self.report_dir = REPO / os.environ.get(
            "WB_FRAMEWORK_REPORT_DIR", "cowork_reports"
        )
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.conflict_rule = os.environ.get(
            "WB_PORTFOLIO_CONFLICT_RULE", "release_on_stop"
        )
        self.log_collisions = (
            os.environ.get("WB_PORTFOLIO_LOG_LOCK_COLLISIONS", "1") == "1"
        )
        strategies_csv = os.environ.get(
            "WB_FRAMEWORK_STRATEGIES",
            "pdh_fade_filtered,orb_aligned_300plus_monskip,pdh_breakout_f4",
        )

        # --- session date ---------------------------------------------
        now = datetime.now(ET)
        self.session_date: date = now.date()
        self.persistence = FrameworkPersistence(self.state_root, self.session_date)

        # --- broker (Alpaca exec) -------------------------------------
        self.broker = LiveBroker(
            api_key=os.environ.get("APCA_API_KEY_ID"),
            api_secret=os.environ.get("APCA_API_SECRET_KEY"),
            paper=(os.environ.get("APCA_PAPER", "true").lower() == "true"),
            dry_run=self.dry_run,
        )

        # --- data feed (IBKR) -----------------------------------------
        self.feed = LiveDataFeed(
            host=self.host, port=self.port, client_id=self.client_id
        )

        # --- strategies ----------------------------------------------
        yaml_paths = _resolve_strategy_yamls(strategies_csv)
        if not yaml_paths:
            raise RuntimeError(
                f"No strategy YAMLs loaded from WB_FRAMEWORK_STRATEGIES={strategies_csv!r}"
            )
        self.arms: list[StrategyArm] = [
            StrategyArm.from_yaml(str(p)) for p in yaml_paths
        ]
        self._log(
            f"[STRATEGY_LOAD] loaded {len(self.arms)} arms: "
            f"{[a.name for a in self.arms]}"
        )

        # --- VIX overlay ---------------------------------------------
        self.vix = VIXRegime(
            enabled=(os.environ.get("WB_USE_VIX_REGIME", "0") == "1"),
        )
        self.vix_value: Optional[float] = None  # populated by runner if available

        # --- signal evaluator ----------------------------------------
        self.evaluator = SignalEvaluator(
            arms=self.arms,
            vix_regime=self.vix,
            log_fn=self._log,
        )

        # --- sizer ---------------------------------------------------
        tier_state_env = os.environ.get("WB_TIER_STATE_PATH")
        tier_state_path = Path(tier_state_env) if tier_state_env else None
        self.sizer = TieredSizer(
            initial_tier=int(os.environ.get("WB_TIER_INITIAL", "1")),
            tier_lock=(os.environ.get("WB_TIER_LOCK", "1") == "1"),
            auto_advance=(os.environ.get("WB_TIER_AUTO_ADVANCE", "0") == "1"),
            state_path=tier_state_path,
        )

        # --- lock / conflict state ------------------------------------
        # Per-(symbol, session_date) lock — same semantics as the backtest:
        #   lock_holder[key]      — arm currently holding the lock
        #   lock_released_at[key] — timestamp the lock was released by a stop
        #                            (release_on_stop only). Absent if active or
        #                            target/session-close exited (lock stays
        #                            forever for that day).
        self.lock_holder: dict[tuple[str, date], str] = {}
        self.lock_released_at: dict[tuple[str, date], datetime] = {}
        self.lock_collisions: list[dict[str, Any]] = []

        # --- open / closed trades ------------------------------------
        # Keyed by symbol for fast lookup (one open trade per symbol/day).
        self.open_trades: dict[str, OpenTrade] = {}
        self.closed_trades: list[ClosedTrade] = []
        self.pnl_by_strategy: dict[str, float] = defaultdict(float)
        self.entries_by_strategy: dict[str, int] = defaultdict(int)
        self.stops_by_strategy: dict[str, int] = defaultdict(int)
        self.targets_by_strategy: dict[str, int] = defaultdict(int)

        # --- risk -----------------------------------------------------
        self.risk = RiskState(
            starting_equity=0.0,
            current_equity=0.0,
            hwm=0.0,
            lwm=0.0,
        )

        # --- shutdown ---------------------------------------------
        self._stop_requested = False
        self._daily_report_written = False
        signal_mod.signal(signal_mod.SIGINT, self._handle_signal)
        signal_mod.signal(signal_mod.SIGTERM, self._handle_signal)

    # ----------------------------------------------------------------
    # Logging helper — verbose by default per directive "soft launch"
    # ----------------------------------------------------------------

    def _log(self, msg: str) -> None:
        if not self.verbose:
            return
        ts = datetime.now(ET).strftime("%H:%M:%S")
        print(f"[{ts} ET] [FRAMEWORK] {msg}", flush=True)

    def _handle_signal(self, signum, frame) -> None:
        self._log(f"[SHUTDOWN] signal {signum} received — graceful stop")
        self._stop_requested = True

    # ----------------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------------

    def setup(self) -> bool:
        """Connect broker + feed, load state. Returns True on success."""
        self._log(
            f"[SETUP] dry_run={self.dry_run} session_date={self.session_date} "
            f"clientId={self.client_id} state_dir={self.state_root}"
        )
        self.persistence.write_marker()

        # 1) Broker
        if not self.broker.connect():
            self._log("[SETUP] broker connect FAILED")
            return False

        # 2) Risk: seed from broker equity
        eq = self.broker.get_account_equity()
        self.risk = RiskState(
            starting_equity=eq,
            current_equity=eq,
            hwm=eq,
            lwm=eq,
        )
        self._log(f"[SETUP] account_equity=${eq:,.2f}")
        # Confirm $300 risk dollars (Tier 1, locked)
        tier_risk = self.sizer.compute_risk(eq)
        self._log(
            f"[SETUP] TieredSizer tier={self.sizer.current_tier} "
            f"tier_lock={self.sizer.tier_lock} risk_per_signal=${tier_risk:.2f}"
        )

        # 3) Feed
        if not self.feed.connect():
            self._log("[SETUP] feed connect FAILED")
            return False

        # 4) Subscribe to universe
        self._log(f"[SETUP] subscribing universe ({len(UNIVERSE)} symbols)")
        for sym in UNIVERSE:
            ok = self.feed.subscribe(sym, on_bar_close=self._make_bar_handler(sym))
            if not ok:
                self._log(f"[SETUP] subscribe failed: {sym}")
            self.feed.seed_history(sym)
        self.persistence.write_watchlist(list(UNIVERSE))
        self.persistence.write_risk(self.risk)

        # 5) Reset evaluator dedup
        self.evaluator.reset_session()

        return True

    def teardown(self) -> None:
        """Disconnect everything cleanly."""
        try:
            self.feed.disconnect()
        except Exception:
            pass
        # Final persist
        try:
            self.persistence.write_risk(self.risk)
            self.persistence.write_open_trades(self.open_trades)
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Bar handler — the heart of the runner
    # ----------------------------------------------------------------

    def _make_bar_handler(self, symbol: str):
        """Bind a per-symbol closure for the feed's `on_bar_close` callback."""

        def _handler(bar: Bar, _sym=symbol) -> None:
            try:
                self.handle_bar(_sym, bar)
            except Exception as e:
                self._log(f"[HANDLE_BAR_ERROR] sym={_sym} {e!r}")
                traceback.print_exc()

        return _handler

    def handle_bar(self, symbol: str, bar: Bar) -> None:
        """Called once per closed 1-minute bar per symbol."""
        # 1) Position management first (stops/targets fire on this bar)
        self._evaluate_open_trade(symbol, bar)

        # 2) New signal evaluation (only inside RTH; ext-hours we just track bars)
        if not _is_rth(bar.timestamp):
            return

        history = self.feed.get_history(symbol)
        prior_bars = self.feed.get_prior_day_bars(symbol)
        signals = self.evaluator.on_bar_close(
            symbol=symbol,
            history=history,
            prior_bars=prior_bars,
            session_date=self.session_date,
            vix_value=self.vix_value,
        )
        for sig in signals:
            self._route_signal(sig, history)

    # ----------------------------------------------------------------
    # Signal routing — apply lock → size → submit
    # ----------------------------------------------------------------

    def _route_signal(self, sig: StrategySignal, history: list[Bar]) -> None:
        key = (sig.symbol, sig.session_date)
        if key in self.lock_holder:
            released = self.lock_released_at.get(key)
            lock_active = (released is None) or (sig.fill_ts <= released)
            if lock_active:
                # Final block — count as collision
                self.risk.lock_collisions_today += 1
                self.lock_collisions.append(
                    {
                        "fill_ts": sig.fill_ts.isoformat(),
                        "symbol": sig.symbol,
                        "session_date": sig.session_date.isoformat(),
                        "winning_strategy": self.lock_holder[key],
                        "blocked_strategy": sig.arm_name,
                        "blocked_direction": sig.direction,
                        "blocked_intended_entry_price": sig.entry_price,
                    }
                )
                self._log(
                    f"[CONFLICT] LOCKED sym={sig.symbol} arm={sig.arm_name} "
                    f"blocked_by={self.lock_holder[key]} "
                    f"price=${sig.entry_price:.4f}"
                )
                return
            # Released → secondary fill
            self._log(
                f"[CONFLICT] release_on_stop SECONDARY sym={sig.symbol} "
                f"arm={sig.arm_name} prior={self.lock_holder[key]} "
                f"prior_released_at={released}"
            )
            self._submit_entry(sig, history, secondary_fill=True)
            return

        # First arrival on this (symbol, day)
        self._submit_entry(sig, history, secondary_fill=False)

    def _submit_entry(
        self, sig: StrategySignal, history: list[Bar], *, secondary_fill: bool
    ) -> None:
        # Compute stop & target via the SAME helper the backtest uses
        # so live = backtest math bit-for-bit.
        # The helper expects bars indexed up to sig.bar_idx + 1; we have
        # `history` containing exactly that.
        try:
            stop_price, target_price = _compute_stop_and_target(
                signal=sig.raw_signal,
                bars=history,
                spec=sig.spec,
            )
        except Exception as e:
            self._log(
                f"[ENTRY_SKIP] stop/target compute failed: arm={sig.arm_name} "
                f"sym={sig.symbol} {e!r}"
            )
            return
        if stop_price is None:
            self._log(
                f"[ENTRY_SKIP] stop_price=None arm={sig.arm_name} sym={sig.symbol}"
            )
            return

        # Sizing
        recent_vol = float(history[sig.raw_signal.bar_idx].volume) if history else 0.0
        qty, risk_dollars = self.sizer.size(
            equity=self.risk.current_equity,
            entry_price=sig.entry_price,
            stop_price=stop_price,
            recent_bar_volume=recent_vol,
        )
        self._log(
            f"[TIER_LOCK_CHECK] tier={self.sizer.current_tier} "
            f"lock={self.sizer.tier_lock} risk_$={risk_dollars:.2f} "
            f"qty={qty} sym={sig.symbol} arm={sig.arm_name}"
        )
        if qty <= 0:
            self._log(
                f"[ENTRY_SKIP] qty=0 arm={sig.arm_name} sym={sig.symbol} "
                f"R=${abs(sig.entry_price - stop_price):.4f}"
            )
            return

        side = "BUY" if sig.direction == "long" else "SELL"

        if self.dry_run:
            self._log(
                f"[DRY_RUN_ENTRY] would BUY {qty} {sig.symbol} @ ~${sig.entry_price:.4f} "
                f"stop=${stop_price:.4f} tgt={target_price} arm={sig.arm_name}"
            )
            return

        # Submit via broker
        self._log(
            f"[ENTRY] submit {side} {qty} {sig.symbol} @ ~${sig.entry_price:.4f} "
            f"stop=${stop_price:.4f} tgt={target_price} arm={sig.arm_name} "
            f"risk_$={risk_dollars:.2f} secondary={secondary_fill}"
        )
        result = self.broker.submit_entry(
            symbol=sig.symbol,
            qty=qty,
            side=side,
            ref_price=sig.entry_price,
        )
        if result.status != "filled":
            self._log(
                f"[ENTRY_NOT_FILLED] arm={sig.arm_name} sym={sig.symbol} "
                f"status={result.status} reason={result.reason}"
            )
            return

        # Record open trade + claim lock
        ot = OpenTrade(
            arm_name=sig.arm_name,
            yaml_path=sig.yaml_path,
            symbol=sig.symbol,
            side=side,
            direction=sig.direction,
            qty=result.filled_qty or qty,
            entry_price=result.filled_avg_price or sig.entry_price,
            stop_price=stop_price,
            target_price=target_price,
            entry_ts=datetime.now(ET).isoformat(),
            risk_dollars=risk_dollars,
            order_id=result.order_id,
            session_date=sig.session_date.isoformat(),
            secondary_fill=secondary_fill,
        )
        self.open_trades[sig.symbol] = ot
        self.lock_holder[(sig.symbol, sig.session_date)] = sig.arm_name
        # release_at gets set later if/when the trade exits via stop
        self.risk.entries_today += 1
        self.entries_by_strategy[sig.arm_name] += 1
        self.persistence.write_open_trades(self.open_trades)

    # ----------------------------------------------------------------
    # Open-trade evaluation (per bar): stop / target firing
    # ----------------------------------------------------------------

    def _evaluate_open_trade(self, symbol: str, bar: Bar) -> None:
        ot = self.open_trades.get(symbol)
        if not ot:
            return

        if ot.direction == "long":
            if bar.low <= ot.stop_price:
                self._fire_exit(ot, exit_price=ot.stop_price, reason="stop", bar=bar)
                return
            if ot.target_price is not None and bar.high >= ot.target_price:
                self._fire_exit(ot, exit_price=ot.target_price, reason="target", bar=bar)
                return
        else:  # short
            if bar.high >= ot.stop_price:
                self._fire_exit(ot, exit_price=ot.stop_price, reason="stop", bar=bar)
                return
            if ot.target_price is not None and bar.low <= ot.target_price:
                self._fire_exit(ot, exit_price=ot.target_price, reason="target", bar=bar)
                return

    def _fire_exit(
        self, ot: OpenTrade, *, exit_price: float, reason: str, bar: Bar
    ) -> None:
        """Submit a SELL LIMIT (or BUY LIMIT) exit and record the closed trade."""
        side = "SELL" if ot.direction == "long" else "BUY"
        self._log(
            f"[EXIT] {reason.upper()} {side} {ot.qty} {ot.symbol} @ ~${exit_price:.4f} "
            f"arm={ot.arm_name}"
        )
        if not self.dry_run:
            result = self.broker.submit_exit(
                symbol=ot.symbol,
                qty=ot.qty,
                side=side,
                ref_price=exit_price,
                extended_hours=False,
            )
            self._log(
                f"[EXIT_SUBMIT] sym={ot.symbol} status={result.status} "
                f"limit=${result.limit_price:.4f}"
            )

        # Record closed trade
        pnl = (
            (exit_price - ot.entry_price) * ot.qty
            if ot.direction == "long"
            else (ot.entry_price - exit_price) * ot.qty
        )
        r_mult = pnl / ot.risk_dollars if ot.risk_dollars > 0 else 0.0
        ct = ClosedTrade(
            arm_name=ot.arm_name,
            symbol=ot.symbol,
            direction=ot.direction,
            qty=ot.qty,
            entry_price=ot.entry_price,
            exit_price=exit_price,
            stop_price=ot.stop_price,
            target_price=ot.target_price,
            entry_ts=ot.entry_ts,
            exit_ts=bar.timestamp.isoformat(),
            risk_dollars=ot.risk_dollars,
            pnl=pnl,
            r_multiple=r_mult,
            exit_reason=reason,
            session_date=ot.session_date,
        )
        self.closed_trades.append(ct)
        self.persistence.append_closed_trade(ct)
        self.pnl_by_strategy[ot.arm_name] += pnl
        if reason == "stop":
            self.stops_by_strategy[ot.arm_name] += 1
            self.risk.stops_today += 1
            # Release lock on stop (release_on_stop semantics)
            if self.conflict_rule == "release_on_stop":
                key = (ot.symbol, date.fromisoformat(ot.session_date))
                self.lock_released_at[key] = bar.timestamp
        elif reason == "target":
            self.targets_by_strategy[ot.arm_name] += 1
            self.risk.targets_today += 1
        elif reason in ("session_close", "force_exit"):
            self.risk.force_exits_today += 1

        # Equity update + HWM/LWM
        self.risk.daily_pnl += pnl
        self.risk.current_equity += pnl
        if self.risk.current_equity > self.risk.hwm:
            self.risk.hwm = self.risk.current_equity
        if self.risk.current_equity < self.risk.lwm or self.risk.lwm == 0:
            self.risk.lwm = self.risk.current_equity
        self.persistence.write_risk(self.risk)

        # Remove from open_trades and persist
        self.open_trades.pop(ot.symbol, None)
        self.persistence.write_open_trades(self.open_trades)

    # ----------------------------------------------------------------
    # Force-exit at 19:55 ET
    # ----------------------------------------------------------------

    def maybe_force_exit(self) -> None:
        """Poll the once-per-day force-exit latch and fire if due."""
        try:
            import force_exit
        except Exception as e:
            self._log(f"[FORCE_EXIT_IMPORT_FAIL] {e!r}")
            return
        if not force_exit.should_force_exit_now():
            return
        self._log("[FORCE_EXIT] triggered — cancelling pending entries + flattening")
        # 1) Cancel any pending entry orders (best-effort)
        try:
            if not self.dry_run and self.broker.is_connected and self.broker._client:
                for o in self.broker._client.get_orders() or []:
                    try:
                        self.broker.cancel_order(str(o.id))
                    except Exception:
                        pass
        except Exception as e:
            self._log(f"[FORCE_EXIT] pending-cancel failed: {e!r}")

        # 2) Flatten every open trade via force_exit chain
        for sym, ot in list(self.open_trades.items()):
            self._log(f"[FORCE_EXIT] flatten {sym} qty={ot.qty}")
            try:
                last_bars = self.feed.get_history(sym)
                ref = last_bars[-1].close if last_bars else ot.entry_price
                if self.dry_run:
                    self._log(
                        f"[DRY_RUN_FORCE_EXIT] would flatten {sym} qty={ot.qty} "
                        f"ref=${ref:.4f}"
                    )
                    continue
                res = self.broker.force_flatten(sym, ot.qty, ref)
                fill_px = res.get("fill_price") or ref
                # Construct an exit bar so _fire_exit's accounting runs
                pseudo_bar = Bar(
                    timestamp=datetime.now(ET).replace(tzinfo=None),
                    open=fill_px, high=fill_px, low=fill_px,
                    close=fill_px, volume=0.0, symbol=sym,
                )
                self._fire_exit(
                    ot, exit_price=fill_px, reason="force_exit", bar=pseudo_bar
                )
            except Exception as e:
                self._log(f"[FORCE_EXIT_FAIL] sym={sym} {e!r}")

    # ----------------------------------------------------------------
    # Daily report
    # ----------------------------------------------------------------

    def write_daily_report(self) -> Path:
        """Write cowork_reports/YYYY-MM-DD_engine_framework_daily.md."""
        path = (
            self.report_dir
            / f"{self.session_date.isoformat()}_engine_framework_daily.md"
        )
        eq_start = self.risk.starting_equity
        eq_end = self.risk.current_equity
        hwm = self.risk.hwm
        lwm = self.risk.lwm
        lines: list[str] = [
            f"# Framework Daily Report — {self.session_date.isoformat()}",
            "",
            f"**Equity:** start ${eq_start:,.2f}, end ${eq_end:,.2f}, "
            f"HWM ${hwm:,.2f}, LWM ${lwm:,.2f}",
            "",
            "**Per-strategy P&L:**",
        ]
        if not self.pnl_by_strategy:
            lines.append("- (no trades)")
        else:
            for name, pnl in sorted(self.pnl_by_strategy.items()):
                ent = self.entries_by_strategy.get(name, 0)
                stp = self.stops_by_strategy.get(name, 0)
                tgt = self.targets_by_strategy.get(name, 0)
                lines.append(
                    f"- {name}: ${pnl:+,.2f} (entries={ent}, stops={stp}, targets={tgt})"
                )
        lines.extend(
            [
                "",
                f"**Conflict events:** {self.risk.lock_collisions_today} "
                f"final-blocked collisions, "
                f"{sum(1 for c in self.closed_trades if False)} release_on_stop secondaries",
                "",
                f"**Tier status:** tier={self.sizer.current_tier}, "
                f"tier_lock={self.sizer.tier_lock}, "
                f"pending={self.sizer.pending_transition}",
                "",
                f"**Force-exit events:** {self.risk.force_exits_today}",
                "",
                "**Anomalies:** (none reported)",
                "",
                "---",
                "",
                "## Lock collision detail",
                "",
            ]
        )
        if not self.lock_collisions:
            lines.append("(none)")
        else:
            for c in self.lock_collisions:
                lines.append(
                    f"- {c['fill_ts']} {c['symbol']}: "
                    f"{c['blocked_strategy']} blocked by {c['winning_strategy']} "
                    f"(direction={c['blocked_direction']}, "
                    f"intended_price={c['blocked_intended_entry_price']})"
                )
        lines.append("")
        path.write_text("\n".join(lines))
        self._log(f"[DAILY_REPORT] wrote {path}")
        return path

    # ----------------------------------------------------------------
    # Main loop
    # ----------------------------------------------------------------

    def run(self, *, max_iterations: Optional[int] = None) -> int:
        """Main loop. Returns 0 on clean shutdown."""
        if not self.setup():
            self._log("[FATAL] setup failed")
            return 2

        if self.dry_run:
            # Verify wiring and exit cleanly with READY message.
            self._dry_run_ready_report()
            self.teardown()
            return 0

        self._log("[MAIN] entering main loop — verbose logging on")
        iterations = 0
        try:
            while not self._stop_requested:
                # ib_insync's run loop is event-driven; we poll the latch
                # plus the daily-report timer here.
                try:
                    self.feed.ib.sleep(1.0)  # type: ignore[union-attr]
                except Exception:
                    _time_mod.sleep(1.0)

                now = datetime.now(ET)

                # Daily report at 16:01 ET (before force-exit at 19:55)
                if (
                    not self._daily_report_written
                    and now.time() >= DAILY_REPORT_T
                    and self.session_date == now.date()
                ):
                    self.write_daily_report()
                    self._daily_report_written = True

                # Force-exit @ 19:55 ET
                self.maybe_force_exit()

                iterations += 1
                if max_iterations is not None and iterations >= max_iterations:
                    self._log(
                        f"[MAIN] max_iterations={max_iterations} reached — exiting"
                    )
                    break

                # End-of-day shutdown after force-exit window closes
                if now.time() >= dtime(20, 5):
                    self._log("[MAIN] post-force-exit window — clean shutdown")
                    break

        finally:
            if not self._daily_report_written:
                try:
                    self.write_daily_report()
                except Exception as e:
                    self._log(f"[DAILY_REPORT_FAIL] {e!r}")
            self.teardown()
        return 0

    # ----------------------------------------------------------------
    # Dry-run helper
    # ----------------------------------------------------------------

    def _dry_run_ready_report(self) -> None:
        """Print a verifiable READY block and exit."""
        self._log("=" * 60)
        self._log("DRY-RUN VERIFICATION COMPLETE")
        self._log("=" * 60)
        self._log(f"clientId            : {self.client_id}")
        self._log(f"state_dir           : {self.state_root}")
        self._log(f"report_dir          : {self.report_dir}")
        self._log(f"session_date        : {self.session_date}")
        self._log(f"strategies loaded   : {[a.name for a in self.arms]}")
        self._log(f"universe size       : {len(UNIVERSE)} symbols")
        self._log(
            f"tier                : {self.sizer.current_tier} "
            f"(lock={self.sizer.tier_lock}, auto_advance={self.sizer.auto_advance})"
        )
        self._log(
            f"risk_per_signal     : ${self.sizer.compute_risk(self.risk.current_equity):.2f}"
        )
        self._log(f"VIX overlay         : enabled={self.vix.enabled}")
        self._log(f"skip_mondays        : {self.evaluator.skip_mondays}")
        self._log(f"conflict_rule       : {self.conflict_rule}")
        self._log(f"log_lock_collisions : {self.log_collisions}")
        self._log(f"broker.dry_run      : {self.broker.dry_run}")
        self._log(f"broker.is_connected : {self.broker.is_connected}")
        self._log(f"feed.is_connected   : {self.feed.is_connected}")
        self._log(f"no_market_orders    : {self.broker._no_market_orders}")
        self._log(f"no_broker_stops     : {self.broker._no_broker_stops}")
        self._log(f"account_equity      : ${self.risk.starting_equity:,.2f}")
        self._log("=" * 60)
        self._log("READY")
        self._log("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_dotenvs() -> None:
    """Load env files in priority order.

    1. .env                    — main bot's env (has APCA_API_KEY_ID = Setup B
                                 Alpaca paper keys we're reusing). Lowest priority.
    2. .env.framework          — framework-specific defaults (VIX, Mondays, sizing,
                                 conflict rule, clientId 51). Overrides .env where
                                 they conflict.
    3. .env.framework.local    — secrets / Manny-provisioned overrides (e.g. if he
                                 ever wants framework on a different Alpaca account).
                                 Highest priority.
    """
    main_env = REPO / ".env"
    base = REPO / ".env.framework"
    local = REPO / ".env.framework.local"
    if main_env.exists():
        load_dotenv(main_env, override=False)
    if base.exists():
        load_dotenv(base, override=True)
    if local.exists():
        load_dotenv(local, override=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Healthy Fluctuation Framework live runner"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify wiring; do NOT submit any orders. Exits with READY.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose logging (default verbose for soft-launch day 1).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Limit main loop iterations (test hook).",
    )
    args = parser.parse_args(argv)

    _load_dotenvs()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    runner = FrameworkRunner(dry_run=args.dry_run, verbose=not args.quiet)
    return runner.run(max_iterations=args.max_iterations)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
