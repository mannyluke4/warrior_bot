# trade_manager.py

import os
import math
import re
import threading
import time
from alpaca.trading.requests import GetOrdersRequest
from alpaca.trading.enums import QueryOrderStatus
from dataclasses import dataclass
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from logger import log_event

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from candles import is_bearish_engulfing

load_dotenv()


# -----------------------------
# V6: Dynamic position sizing
# -----------------------------
def calculate_dynamic_risk(account_equity: float, profile: str) -> dict:
    """
    Calculate dynamic position risk based on account equity.

    Args:
        account_equity: Current settled equity from Alpaca
        profile: 'A', 'B', or 'Shelved'

    Returns:
        dict with 'risk', 'scale_factor', 'equity_used'
    """
    RISK_PERCENT = 0.025
    FLOOR = 250
    CEILING = 1500

    base_risk_a = max(FLOOR, min(CEILING, round(account_equity * RISK_PERCENT)))

    if profile == 'A':
        risk = base_risk_a
        baseline = 750
    else:  # B or Shelved
        risk = max(FLOOR, min(CEILING, round(base_risk_a / 3)))
        baseline = 250

    # V6.2: Profile B risk cap — mid-float stocks capped at $250 regardless of SQS/equity
    if profile == 'B' and os.getenv("WB_PROFILE_B_RISK_CAP", "1") == "1":
        risk = min(risk, 250)

    scale_factor = risk / baseline if baseline > 0 else 1.0

    return {
        'risk': risk,
        'scale_factor': round(scale_factor, 4),
        'equity_used': account_equity
    }


# -----------------------------
# V6.1: Toxic entry filters
# -----------------------------
COLD_MONTHS = {2, 10, 11}
HOT_MONTHS = {1}


def check_toxic_filters(
    entry_price: float,
    stop_price: float,
    gap_pct: float,
    pm_volume: float,
    candidates_count: int,
    month: int
) -> dict:
    """
    Check entry against toxic trait filters.

    Returns:
        dict with 'action' ('ALLOW', 'BLOCK', 'HALF_RISK'),
        'filter' (name), 'reason' (human-readable)
    """
    r_pct = abs(entry_price - stop_price) / entry_price * 100

    # Filter 1: Wide R% + Crowded Day → HARD BLOCK
    if os.getenv("WB_TOXIC_FILTER_1_ENABLED", "1") == "1":
        if r_pct >= 5.0 and candidates_count >= 20:
            return {
                'action': 'BLOCK',
                'filter': 'wide_r_crowded_day',
                'reason': f'R%={r_pct:.1f}% + {candidates_count} candidates (toxic combo)',
                'r_pct': r_pct,
                'candidates': candidates_count
            }

    # Filter 2: Cold Market + Low Vol + Small Gap → HALF RISK
    if os.getenv("WB_TOXIC_FILTER_2_ENABLED", "1") == "1":
        market_temp = "cold" if month in COLD_MONTHS else "hot" if month in HOT_MONTHS else "neutral"
        if gap_pct < 30 and pm_volume < 100_000 and market_temp == "cold":
            multiplier = float(os.getenv("WB_TOXIC_FILTER_2_MULTIPLIER", "0.5"))
            return {
                'action': 'HALF_RISK',
                'filter': 'cold_low_vol_small_gap',
                'reason': f'Gap={gap_pct:.1f}% + PMVol={pm_volume:,.0f} + {market_temp} market',
                'multiplier': multiplier,
                'gap_pct': gap_pct,
                'pm_volume': pm_volume,
                'market_temp': market_temp
            }

    return {'action': 'ALLOW', 'filter': None, 'reason': None}


# -----------------------------
# Data models
# -----------------------------
@dataclass
class TradePlan:
    entry: float
    stop: float
    r: float
    take_profit: float


@dataclass
class OpenTrade:
    symbol: str
    qty_total: int
    qty_core: int       # T1 in 3-tranche mode
    qty_runner: int     # T3 in 3-tranche mode
    entry: float
    stop: float
    r: float
    take_profit: float
    tp_hit: bool = False    # T1 hit
    peak: float = 0.0
    runner_stop: float = 0.0
    highest_r: float = 0.0       # Peak R-multiple seen (for WB_TRAILING_STOP)
    created_at_utc: datetime = None
    # T2 (3-tranche only; qty_t2=0 when disabled)
    qty_t2: int = 0
    take_profit_t2: float = 0.0
    t2_hit: bool = False
    # Exit fill tracking for realized P&L
    exit_filled_qty: int = 0
    exit_filled_cost: float = 0.0  # cumulative (price * qty) for weighted avg


@dataclass
class PendingEntry:
    symbol: str
    order_id: str
    qty_total: int
    qty_core: int
    qty_runner: int
    entry: float
    stop: float
    r: float
    take_profit: float
    submitted_at_utc: datetime  # aware UTC

    cancel_requested: bool = False
    last_limit: float = 0.0
    reprice_count: int = 0
    qty_t2: int = 0
    take_profit_t2: float = 0.0

    # ✅ entry fill accounting (filled_qty is cumulative)
    filled_applied: int = 0


@dataclass
class PendingExit:
    symbol: str
    order_id: str
    qty: int
    reason: str
    submitted_at_utc: datetime  # aware UTC
    cancel_requested: bool = False
    last_limit: float = 0.0
    filled_applied: int = 0
    attempts: int = 0
    accounted_cost: float = 0.0  # $ cost of fills we've already tracked for this order


# -----------------------------
# Manager
# -----------------------------
class PaperTradeManager:
    def __init__(self):
        mode = os.getenv("WB_MODE", "PAPER").upper()
        if mode != "PAPER":
            raise RuntimeError(f"WB_MODE must be PAPER for PaperTradeManager, got {mode}")

        # Trading toggles
        self.armed = os.getenv("WB_ARM_TRADING", "0") == "1"

        # Risk / sizing — V6: dynamic equity-based risk (profile-aware)
        self.dynamic_sizing_enabled = os.getenv("WB_DYNAMIC_SIZING_ENABLED", "0") == "1"
        _base_risk = float(os.getenv("WB_RISK_DOLLARS", "10"))
        if self.dynamic_sizing_enabled:
            _equity = float(os.getenv("WB_ACCOUNT_EQUITY", "30000"))
            _profile = os.getenv("WB_DYNAMIC_SIZING_PROFILE", "A")
            result = calculate_dynamic_risk(_equity, _profile)
            self.risk_dollars = result['risk']
            log_event("dynamic_risk_used", equity=result['equity_used'],
                      risk=result['risk'], scale=result['scale_factor'])
        else:
            self.risk_dollars = _base_risk
        self.tp_r_mult = float(os.getenv("WB_TAKE_PROFIT_R", "2.0"))  # NOTE: env mismatch is on Mansion Checklist
        self.scale_core = float(os.getenv("WB_SCALE_CORE", "0.8"))
        self.runner_trail_r = float(os.getenv("WB_RUNNER_TRAIL_R", "1.0"))

        self.min_r = float(os.getenv("WB_MIN_R", "0.03"))
        self.max_notional = float(os.getenv("WB_MAX_NOTIONAL", "5000"))
        self.max_shares = int(os.getenv("WB_MAX_SHARES", "3000"))
        self.round_lot = os.getenv("WB_ROUND_LOT", "1") == "1"

        # Order behavior
        self.limit_offset_buy = float(os.getenv("WB_LIMIT_OFFSET_BUY", "0.00"))
        self.limit_offset_sell = float(os.getenv("WB_LIMIT_OFFSET_SELL", "0.01"))

        # Pending safety
        self.pending_timeout_sec = int(os.getenv("WB_PENDING_TIMEOUT_SEC", "45"))

        # Exit safety
        self.exit_timeout_sec = int(os.getenv("WB_EXIT_TIMEOUT_SEC", "20"))
        self.exit_chase_step = float(os.getenv("WB_EXIT_CHASE_STEP", "0.02"))
        self.exit_on_bear_engulf = os.getenv("WB_EXIT_ON_BEAR_ENGULF", "1") == "1"
        self.exit_on_topping_wicky = os.getenv("WB_EXIT_ON_TOPPING_WICKY", "1") == "1"
        self.exit_mode = os.getenv("WB_EXIT_MODE", "signal")
        self.be_trigger_r = float(os.getenv("WB_BE_TRIGGER_R", "1.0"))
        self.signal_trail_pct = float(os.getenv("WB_SIGNAL_TRAIL_PCT", "0.05"))
        self.max_loss_r = float(os.getenv("WB_MAX_LOSS_R", "2.0"))
        self.last_bar: Dict[str, dict] = {}

        # BE parabolic grace — suppress BE exits during genuine ramps
        self.be_parabolic_grace = os.getenv("WB_BE_PARABOLIC_GRACE", "1") == "1"
        self.be_grace_min_r = float(os.getenv("WB_BE_GRACE_MIN_R", "1.0"))
        self.be_grace_min_new_highs = int(os.getenv("WB_BE_GRACE_MIN_NEW_HIGHS", "3"))
        self.be_grace_lookback = int(os.getenv("WB_BE_GRACE_LOOKBACK_BARS", "6"))
        self._recent_10s_highs: Dict[str, list] = {}
        self.be_grace_sec = int(os.getenv("WB_BE_GRACE_MIN", "0")) * 60  # time-based BE grace

        # Parabolic regime detector (replaces simple grace when enabled)
        self.parabolic_regime_enabled = os.getenv("WB_PARABOLIC_REGIME_ENABLED", "0") == "1"
        self._parabolic_detectors: Dict[str, object] = {}  # symbol -> ParabolicRegimeDetector

        # 3-tranche exit scaling
        self.three_tranche_enabled = os.getenv("WB_3TRANCHE_ENABLED", "0") == "1"
        self.scale_t1 = float(os.getenv("WB_SCALE_T1", "0.40"))
        self.scale_t2 = float(os.getenv("WB_SCALE_T2", "0.35"))
        self.t1_tp_r = float(os.getenv("WB_T1_TP_R", "1.0"))
        self.t2_tp_r = float(os.getenv("WB_T2_TP_R", "2.0"))
        self.t2_stop_lock_r = float(os.getenv("WB_T2_STOP_LOCK_R", "0.5"))
        # Force classic exit mode when 3-tranche is enabled
        if self.three_tranche_enabled and self.exit_mode == "signal":
            self.exit_mode = "classic"

        self.exit_max_attempts = int(os.getenv("WB_EXIT_MAX_ATTEMPTS", "4"))
        self.exit_max_chase = float(os.getenv("WB_EXIT_MAX_CHASE", "0.40"))

        # Entry wiggle / chase
        self.entry_timeout_sec = int(os.getenv("WB_ENTRY_TIMEOUT_SEC", str(self.pending_timeout_sec)))
        self.entry_chase_step = float(os.getenv("WB_ENTRY_CHASE_STEP", "0.03"))
        self.entry_max_chase = float(os.getenv("WB_ENTRY_MAX_CHASE", "0.25"))
        self.entry_max_attempts = int(os.getenv("WB_ENTRY_MAX_ATTEMPTS", "3"))

        # Quote-based execution
        self.use_quotes_for_limits = os.getenv("WB_USE_QUOTES_FOR_LIMITS", "1") == "1"
        self.entry_quote_pad = float(os.getenv("WB_ENTRY_QUOTE_PAD", "0.00"))
        self.exit_quote_pad  = float(os.getenv("WB_EXIT_QUOTE_PAD", "0.00"))
        self.exit_initial_wiggle = float(os.getenv("WB_EXIT_INITIAL_WIGGLE", "0.00"))
        self.entry_initial_wiggle = float(os.getenv("WB_ENTRY_INITIAL_WIGGLE", "0.00"))

        # Pre-trade quote quality gate
        self.entry_max_spread_pct = float(os.getenv("WB_ENTRY_MAX_SPREAD_PCT", "5.0"))
        self.entry_max_bid_dev_pct = float(os.getenv("WB_ENTRY_MAX_BID_DEV_PCT", "5.0"))

        # Percentage-based exit offsets (override fixed-cent if > 0)
        self.exit_wiggle_pct = float(os.getenv("WB_EXIT_INITIAL_WIGGLE_PCT", "0.3"))
        self.exit_offset_sell_pct = float(os.getenv("WB_LIMIT_OFFSET_SELL_PCT", "0.1"))
        self.exit_chase_step_pct = float(os.getenv("WB_EXIT_CHASE_STEP_PCT", "0.2"))
        self.exit_max_chase_pct = float(os.getenv("WB_EXIT_MAX_CHASE_PCT", "3.0"))

        self.last_quote: Dict[str, Dict[str, float]] = {}
        self.last_bid: Dict[str, float] = {}
        self.last_ask: Dict[str, float] = {}

        # Stop-hit re-entry cooldown (bars converted to seconds: N bars * 60s)
        _cooldown_bars = int(os.getenv("WB_REENTRY_COOLDOWN_BARS", "5"))
        self._reentry_cooldown_sec = _cooldown_bars * 60
        self._stop_hit_cooldown_until: Dict[str, datetime] = {}  # symbol -> UTC timestamp

        # -----------------------------
        # ✅ Stale-price guardrails
        # -----------------------------
        # Warn if we haven't received a usable price update for an open symbol.
        # --- Data health (stale detection) ---
        self.stale_trade_sec = float(os.getenv("WB_STALE_TRADE_SEC", "15"))
        self.stale_quote_sec = float(os.getenv("WB_STALE_QUOTE_SEC", "15"))
        self.stale_warn_every_sec = float(os.getenv("WB_STALE_WARN_EVERY_SEC", "10"))

        self.last_trade_ts_utc: Dict[str, datetime] = {}  # symbol -> last trade print timestamp (UTC)
        self.last_quote_ts_utc: Dict[str, datetime] = {}  # symbol -> last quote timestamp (UTC)
        self.last_stale_warn_ts_utc: Dict[str, datetime] = {}  # symbol -> last warning timestamp (UTC)

        # --- Bail Timer: exit if not profitable within N minutes ---
        self.bail_timer_enabled = os.getenv("WB_BAIL_TIMER_ENABLED", "1") == "1"
        self.bail_timer_minutes = float(os.getenv("WB_BAIL_TIMER_MINUTES", "5"))

        # --- Daily risk management ---
        self.daily_goal = float(os.getenv("WB_DAILY_GOAL", "500"))
        self.max_daily_loss = float(os.getenv("WB_MAX_DAILY_LOSS", "500"))
        self.giveback_hard_pct = float(os.getenv("WB_GIVEBACK_HARD_PCT", "50"))
        self.giveback_warn_pct = float(os.getenv("WB_GIVEBACK_WARN_PCT", "20"))
        self.max_consecutive_losses = int(os.getenv("WB_MAX_CONSECUTIVE_LOSSES", "3"))

        # Warmup sizing: start at reduced size until daily P&L crosses threshold
        self.warmup_size_pct = float(os.getenv("WB_WARMUP_SIZE_PCT", "25"))
        self.warmup_size_threshold = float(os.getenv("WB_WARMUP_SIZE_THRESHOLD", "500"))

        # Callback for quality gate trade-close notification (set by caller)
        self.on_trade_close_callback = None  # fn(symbol: str, pnl: float)

        # Daily tracking state (reset each trading day)
        self._daily_pnl: float = 0.0
        self._daily_peak_pnl: float = 0.0
        self._consecutive_losses: int = 0
        self._daily_stopped: bool = False  # hard stop for the day
        self._giveback_warned: bool = False  # risk reduced due to giveback
        self._warmup_graduated: bool = False  # switched to full size
        self._original_risk_dollars: float = self.risk_dollars
        self._daily_date: str = ""  # date string to detect day change

        key = os.getenv("APCA_API_KEY_ID")
        secret = os.getenv("APCA_API_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Missing APCA_API_KEY_ID / APCA_API_SECRET_KEY")

        self.client = TradingClient(key, secret, paper=True)

        acct = self.client.get_account()
        log_event(
            "paper_connected",
            None,
            status=str(acct.status),
            buying_power=float(acct.buying_power),
            equity=float(acct.equity),
            mode="PAPER",
            armed=self.armed,
        )

        self.open: Dict[str, OpenTrade] = {}
        self.pending: Dict[str, PendingEntry] = {}
        self.pending_exits: Dict[str, PendingExit] = {}
        self.last_price: Dict[str, float] = {}
        self._lock = threading.RLock()

        # Per-symbol re-entry cooldown: after N entries, pause for X seconds.
        self.max_entries_per_symbol = int(os.getenv("WB_MAX_ENTRIES_PER_SYMBOL", "2"))
        self.symbol_cooldown_sec = int(os.getenv("WB_SYMBOL_COOLDOWN_SEC", "600"))  # 10 min
        self._symbol_entry_count: Dict[str, int] = {}
        self._symbol_cooldown_until: Dict[str, datetime] = {}

        # Cached fundamental data from startup filtering (for quality gate)
        self._stock_info_cache: dict = {}
        self.quality_min_float = float(os.getenv("WB_QUALITY_MIN_FLOAT", "0.5"))

    def set_stock_info_cache(self, cache: dict):
        """Store fundamental data from startup filtering for trade-time access."""
        self._stock_info_cache = dict(cache)

    def _passes_quality_gate(self, symbol: str) -> tuple:
        """Pre-trade fundamental check using cached StockInfo."""
        info = self._stock_info_cache.get(symbol)
        if info is None:
            return True, ""  # no data = allow (conservative fallback)

        # Min float check
        if info.float_shares is not None and info.float_shares < self.quality_min_float:
            return False, f"micro_float:{info.float_shares:.2f}M"

        return True, ""

    # -----------------------------
    # Funds helpers
    # -----------------------------
    def get_available_funds(self) -> float:
        acct = self.client.get_account()
        return float(acct.buying_power)

    def affordable_qty(self, available_cash: float, limit_price: float, reserve_pct: float = 0.05) -> int:
        usable = available_cash * (1.0 - reserve_pct)
        if limit_price <= 0:
            return 0
        return int(usable // limit_price)

    # -----------------------------
    # ✅ Stale-price helpers
    # -----------------------------
    def _touch_trade_ts(self, symbol: str, ts=None):
        if ts is None:
            now = datetime.now(timezone.utc)
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                now = ts.replace(tzinfo=timezone.utc)
            else:
                now = ts.astimezone(timezone.utc)
        else:
            now = datetime.now(timezone.utc)

        self.last_trade_ts_utc[symbol] = now


    def _touch_quote_ts(self, symbol: str, ts=None):
        if ts is None:
            now = datetime.now(timezone.utc)
        elif isinstance(ts, datetime):
            if ts.tzinfo is None:
                now = ts.replace(tzinfo=timezone.utc)
            else:
                now = ts.astimezone(timezone.utc)
        else:
            now = datetime.now(timezone.utc)

        self.last_quote_ts_utc[symbol] = now


    def _warn_if_stale_trade_and_quote(self, symbol: str):
        with self._lock:
            t = self.open.get(symbol)
            if not t:
                return

            trade_ts = self.last_trade_ts_utc.get(symbol)
            quote_ts = self.last_quote_ts_utc.get(symbol)

            now = datetime.now(timezone.utc)

            trade_age = (now - trade_ts).total_seconds() if trade_ts else None
            quote_age = (now - quote_ts).total_seconds() if quote_ts else None

            trade_stale = trade_age is None or trade_age >= self.stale_trade_sec
            quote_stale = quote_age is None or quote_age >= self.stale_quote_sec

            if not (trade_stale and quote_stale):
                return

            last_warn = self.last_stale_warn_ts_utc.get(symbol)
            if last_warn and (now - last_warn).total_seconds() < self.stale_warn_every_sec:
                return

            self.last_stale_warn_ts_utc[symbol] = now

            bid = self.last_bid.get(symbol)
            last = self.last_price.get(symbol)

            ta_str = f"{trade_age:.1f}" if trade_age is not None else "None"
            qa_str = f"{quote_age:.1f}" if quote_age is not None else "None"
            warn_msg = (
                f"⚠️ STALE FEED {symbol}: "
                f"trade_age={ta_str}s "
                f"quote_age={qa_str}s "
                f"(bid={bid}, last={last}) "
                f"open_qty={t.qty_total} pending_exit={symbol in self.pending_exits}"
            )

        print(warn_msg, flush=True)

        log_event(
            "stale_feed_warning",
            symbol,
            trade_age_sec=trade_age,
            quote_age_sec=quote_age,
            bid=bid,
            last=last,
            open_qty=t.qty_total if t else None,
            pending_exit=(symbol in self.pending_exits),
            stale_trade_sec=self.stale_trade_sec,
            stale_quote_sec=self.stale_quote_sec,
        )


    # -----------------------------
    # Parsing + sizing
    # -----------------------------
    def parse_plan(self, msg: str) -> Optional[TradePlan]:
        # Pattern 1: Generic entry=X stop=Y R=Z format
        m = re.search(
            r"entry=([0-9]*\.?[0-9]+)\s+stop=([0-9]*\.?[0-9]+)\s+R=([0-9]*\.?[0-9]+)",
            msg,
        )
        if m:
            entry = float(m.group(1))
            stop  = float(m.group(2))
            r     = float(m.group(3))
            tp = entry + (self.tp_r_mult * r)
            return TradePlan(entry=entry, stop=stop, r=r, take_profit=tp)

        # Pattern 2: ENTRY SIGNAL @ X ... stop=Y R=Z (micro pullback format)
        m = re.search(
            r"ENTRY SIGNAL\s*@\s*([0-9]*\.?[0-9]+).*?stop=([0-9]*\.?[0-9]+)\s+R=([0-9]*\.?[0-9]+)",
            msg,
        )
        if not m:
            return None

        entry = float(m.group(1))
        stop  = float(m.group(2))
        r     = float(m.group(3))
        tp = entry + (self.tp_r_mult * r)
        return TradePlan(entry=entry, stop=stop, r=r, take_profit=tp)

    def size_qty(self, entry: float, r: float) -> int:
        if r <= 0 or r < self.min_r:
            return 0

        effective_risk = self._get_effective_risk()
        qty_risk = int(math.floor(effective_risk / r))
        if qty_risk <= 0:
            return 0

        qty_notional = int(math.floor(self.max_notional / max(entry, 0.01)))
        qty_cap = min(qty_risk, qty_notional, self.max_shares)
        if qty_cap <= 0:
            return 0

        try:
            acct = self.client.get_account()
            buying_power = float(acct.buying_power)
            qty_bp = int(math.floor(buying_power / max(entry, 0.01)))
            qty_cap = min(qty_cap, qty_bp)
        except Exception:
            pass

        if qty_cap <= 0:
            return 0

        if self.round_lot and qty_cap >= 100:
            qty_cap = (qty_cap // 100) * 100
            qty_cap = max(100, qty_cap)

        return qty_cap

    def _split_core_runner(self, qty_total: int) -> tuple[int, int]:
        if qty_total <= 0:
            return 0, 0
        qty_core = int(math.floor(qty_total * self.scale_core))
        qty_core = max(1, min(qty_core, qty_total))
        qty_runner = max(0, qty_total - qty_core)
        return qty_core, qty_runner

    def _split_tranches(self, qty_total: int) -> tuple[int, int, int]:
        """Split into 3 tranches: T1, T2, T3. Returns (qty_t1, qty_t2, qty_t3)."""
        if qty_total <= 0:
            return 0, 0, 0
        qty_t1 = max(1, int(math.floor(qty_total * self.scale_t1)))
        qty_t2 = max(0, int(math.floor(qty_total * self.scale_t2)))
        qty_t3 = max(0, qty_total - qty_t1 - qty_t2)
        return qty_t1, qty_t2, qty_t3

    # -----------------------------
    # Public heartbeats
    # -----------------------------
    def check_pending_entries(self):
        with self._lock:
            syms = list(self.pending.keys())
        for sym in syms:
            self._check_pending(sym)

    def check_pending_exits(self):
        with self._lock:
            syms = list(self.pending_exits.keys())
        for sym in syms:
            self._check_pending_exit(sym)

    # -----------------------------
    # Reconcile loop
    # -----------------------------
    RECONCILE_EVERY_SEC = 3

    def _ensure_open_trade_from_alpaca(self, symbol: str, alp_qty: int, alp_avg: float):
        qty_core, qty_runner = self._split_core_runner(alp_qty)

        t = self.open.get(symbol)
        if not t:
            p = self.pending.get(symbol)
            entry = float(alp_avg)
            stop = float(p.stop) if p else float(alp_avg)
            r = float(p.r) if p else 0.0
            tp = float(p.take_profit) if p else float(alp_avg)

            self.open[symbol] = OpenTrade(
                symbol=symbol,
                qty_total=alp_qty,
                qty_core=qty_core,
                qty_runner=qty_runner,
                entry=entry,
                stop=stop,
                r=r,
                take_profit=tp,
                tp_hit=False,
                peak=entry,
                runner_stop=stop,
                created_at_utc=datetime.now(timezone.utc),
            )
        else:
            t.qty_total = alp_qty
            if not t.tp_hit:
                t.qty_core, t.qty_runner = qty_core, qty_runner
            else:
                t.qty_core = 0
                t.qty_runner = alp_qty

    def reconcile_symbol(self, symbol: str):
        try:
            pos = self.client.get_open_position(symbol)
            alp_qty = int(float(pos.qty))
            alp_avg = float(pos.avg_entry_price)
            alp_side = str(getattr(pos, "side", "")).lower()
        except Exception:
            alp_qty, alp_avg, alp_side = 0, 0.0, ""

        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            open_orders = self.client.get_orders(req)
            open_order_ids = {str(o.id) for o in open_orders}
        except Exception:
            open_orders = []
            open_order_ids = set()

        with self._lock:
            bot_trade = self.open.get(symbol)
            bot_qty = bot_trade.qty_total if bot_trade else 0
            bot_created_at = bot_trade.created_at_utc if bot_trade else None
            p = self.pending.get(symbol)
            bot_pending_id = p.order_id if p else None
            pending_submitted = p.submitted_at_utc if p else None

        if alp_side == "long" and alp_qty != bot_qty:
            if alp_qty > 0 and bot_qty == 0:
                log_event("reconcile_orphan_adopted", symbol, alp_qty=alp_qty, bot_qty=bot_qty, alp_avg=alp_avg)
                print(f"🔴 CRITICAL: {symbol} bot_qty=0 but Alpaca has {alp_qty} shares — adopting orphan position", flush=True)
            else:
                log_event("reconcile_position", symbol, alp_qty=alp_qty, bot_qty=bot_qty, alp_avg=alp_avg, alp_side=alp_side)
            with self._lock:
                self._ensure_open_trade_from_alpaca(symbol, alp_qty, alp_avg)

        if alp_qty == 0 and bot_qty != 0:
            # Check grace period: Alpaca paper API has 10-30s propagation delay after fills.
            # Don't clear a position that was just entered — trust the fill event.
            entry_grace_sec = int(os.getenv("WB_RECONCILE_ENTRY_GRACE_SEC", "60"))
            if bot_created_at:
                seconds_since_entry = (datetime.now(timezone.utc) - bot_created_at).total_seconds()
                if seconds_since_entry < entry_grace_sec:
                    log_event("reconcile_entry_grace", symbol, alp_qty=0, bot_qty=bot_qty,
                              seconds_since_entry=round(seconds_since_entry, 1),
                              grace_sec=entry_grace_sec)
                    return  # Alpaca propagation delay — keep position, skip reconcile
            log_event("reconcile_position", symbol, alp_qty=0, bot_qty=bot_qty, alp_avg=alp_avg, alp_side=alp_side)
            with self._lock:
                self.open.pop(symbol, None)
                self.pending_exits.pop(symbol, None)

        if bot_pending_id:
            grace_sec = float(os.getenv("WB_RECONCILE_PENDING_GRACE_SEC", "10"))
            age_sec = None
            if pending_submitted:
                age_sec = (datetime.now(timezone.utc) - pending_submitted).total_seconds()

            if bot_pending_id in open_order_ids:
                return

            if age_sec is not None and age_sec < grace_sec:
                log_event("reconcile_pending_entry_grace", symbol, bot_pending=bot_pending_id, age_sec=age_sec, grace_sec=grace_sec, open_order_ids=list(open_order_ids))
                return

            try:
                o = self.client.get_order_by_id(bot_pending_id)
                st = str(getattr(o, "status", "")).lower()
                filled_qty_raw = getattr(o, "filled_qty", 0) or 0
                try:
                    filled_qty = int(math.floor(float(filled_qty_raw)))
                except Exception:
                    filled_qty = 0

                log_event("reconcile_pending_entry_check", symbol, bot_pending=bot_pending_id, status=st, filled_qty=filled_qty, open_order_ids=list(open_order_ids))

                if st in ("new", "accepted", "pending_new", "partially_filled"):
                    return

                if st in ("filled", "canceled", "rejected", "expired"):
                    with self._lock:
                        self.pending.pop(symbol, None)
                    log_event("reconcile_pending_entry_cleared_terminal", symbol, bot_pending=bot_pending_id, status=st)
                    return

            except Exception as e:
                log_event("exception", symbol, where="reconcile_pending_by_id", bot_pending=bot_pending_id, error=str(e))
                return

    def _reconcile_all_positions(self):
        """Safety net: query ALL Alpaca positions and adopt any the bot doesn't know about."""
        try:
            positions = self.client.get_all_positions()
        except Exception as e:
            log_event("exception", None, where="reconcile_all_positions", error=str(e))
            return
        for pos in positions:
            sym = str(pos.symbol)
            side = str(getattr(pos, "side", "")).lower()
            if side != "long":
                continue
            alp_qty = int(float(pos.qty))
            alp_avg = float(pos.avg_entry_price)
            with self._lock:
                bot_trade = self.open.get(sym)
                bot_pending = self.pending.get(sym)
            if bot_trade or bot_pending:
                continue  # bot already knows about this symbol
            log_event("reconcile_orphan_detected", sym, alp_qty=alp_qty, alp_avg=alp_avg)
            print(f"🟧 ORPHAN POSITION DETECTED {sym}: {alp_qty} shares @ ${alp_avg:.4f} — adopting", flush=True)
            with self._lock:
                self._ensure_open_trade_from_alpaca(sym, alp_qty, alp_avg)

    def start_reconcile_thread(self, symbols_provider):
        def loop():
            cycle = 0
            while True:
                try:
                    syms = list(symbols_provider())
                    for sym in syms:
                        self.reconcile_symbol(sym)
                    # Every 10th cycle (~30s), also sweep ALL Alpaca positions
                    cycle += 1
                    if cycle % 10 == 0:
                        self._reconcile_all_positions()
                except Exception as e:
                    log_event("exception", None, where="reconcile_loop", error=str(e))
                time.sleep(self.RECONCILE_EVERY_SEC)

        th = threading.Thread(target=loop, daemon=True)
        th.start()
        return th

    # -----------------------------
    # Entry submission
    # -----------------------------
    # -----------------------------
    # Daily risk management
    # -----------------------------
    def _check_daily_reset(self):
        """Reset daily tracking state at the start of each new trading day."""
        import pytz
        ET = pytz.timezone("US/Eastern")
        today = datetime.now(ET).strftime("%Y-%m-%d")
        if today != self._daily_date:
            self._daily_date = today
            self._daily_pnl = 0.0
            self._daily_peak_pnl = 0.0
            self._consecutive_losses = 0
            self._daily_stopped = False
            self._giveback_warned = False
            self._warmup_graduated = False
            self.risk_dollars = self._original_risk_dollars
            log_event("daily_reset", None, date=today, risk_dollars=self.risk_dollars)

    def _record_trade_pnl(self, pnl: float):
        """Record a closed trade's P&L for daily management."""
        self._daily_pnl += pnl
        self._daily_peak_pnl = max(self._daily_peak_pnl, self._daily_pnl)

        # Track consecutive losses
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        # Check consecutive loser stop
        if self._consecutive_losses >= self.max_consecutive_losses:
            self._daily_stopped = True
            log_event("daily_stopped_consecutive_losses", None,
                      consecutive=self._consecutive_losses,
                      daily_pnl=round(self._daily_pnl, 2))
            print(
                f"DAILY STOP: {self._consecutive_losses} consecutive losses — "
                f"no more entries today (daily P&L: ${self._daily_pnl:.2f})",
                flush=True,
            )

        # Check daily max loss
        if self._daily_pnl <= -self.max_daily_loss:
            self._daily_stopped = True
            log_event("daily_stopped_max_loss", None,
                      daily_pnl=round(self._daily_pnl, 2),
                      max_daily_loss=self.max_daily_loss)
            print(
                f"DAILY STOP: daily loss ${self._daily_pnl:.2f} exceeds "
                f"-${self.max_daily_loss:.2f} — no more entries today",
                flush=True,
            )

        # Check giveback rules (only when peak P&L was positive)
        if self._daily_peak_pnl > 0:
            giveback = self._daily_peak_pnl - self._daily_pnl
            giveback_pct = (giveback / self._daily_peak_pnl) * 100

            # Hard stop: gave back 50%+ of peak
            if giveback_pct >= self.giveback_hard_pct:
                self._daily_stopped = True
                log_event("daily_stopped_giveback_hard", None,
                          daily_pnl=round(self._daily_pnl, 2),
                          peak_pnl=round(self._daily_peak_pnl, 2),
                          giveback_pct=round(giveback_pct, 1))
                print(
                    f"DAILY STOP: gave back {giveback_pct:.0f}% of peak "
                    f"(${self._daily_pnl:.2f} from peak ${self._daily_peak_pnl:.2f}) — done for day",
                    flush=True,
                )

            # Warning: gave back 20%+ — halve risk
            elif giveback_pct >= self.giveback_warn_pct and not self._giveback_warned:
                self._giveback_warned = True
                self.risk_dollars = self._original_risk_dollars * 0.5
                log_event("giveback_warning_risk_halved", None,
                          daily_pnl=round(self._daily_pnl, 2),
                          peak_pnl=round(self._daily_peak_pnl, 2),
                          giveback_pct=round(giveback_pct, 1),
                          new_risk=self.risk_dollars)
                print(
                    f"GIVEBACK WARNING: gave back {giveback_pct:.0f}% of peak "
                    f"— risk reduced to ${self.risk_dollars:.0f} for rest of day",
                    flush=True,
                )

    def _get_effective_risk(self) -> float:
        """Get current risk dollars, accounting for warmup sizing."""
        if not self._warmup_graduated:
            if self._daily_pnl >= self.warmup_size_threshold:
                self._warmup_graduated = True
                log_event("warmup_graduated", None,
                          daily_pnl=round(self._daily_pnl, 2),
                          threshold=self.warmup_size_threshold)
                print(
                    f"WARMUP GRADUATED: daily P&L ${self._daily_pnl:.2f} crossed "
                    f"${self.warmup_size_threshold:.0f} — switching to full size",
                    flush=True,
                )
                return self.risk_dollars
            # Still in warmup — use reduced size
            return self.risk_dollars * (self.warmup_size_pct / 100)
        return self.risk_dollars

    def on_signal(self, symbol: str, msg: str):
        with self._lock:
            # Daily reset check
            self._check_daily_reset()

            # Daily stop check — no new entries
            if self._daily_stopped:
                log_event("skip_entry_daily_stopped", symbol)
                return

            plan = self.parse_plan(msg)
            if not plan:
                return

            # Stop-hit re-entry cooldown
            cooldown_until = self._stop_hit_cooldown_until.get(symbol)
            if cooldown_until and datetime.now(timezone.utc) < cooldown_until:
                log_event("skip_entry_reentry_cooldown", symbol, cooldown_until=cooldown_until.isoformat())
                return
            elif cooldown_until:
                self._stop_hit_cooldown_until.pop(symbol, None)

            # Quality gate: check cached fundamentals before entry
            passes, gate_reason = self._passes_quality_gate(symbol)
            if not passes:
                log_event("skip_entry_quality_gate", symbol, reason=gate_reason)
                print(f"QUALITY GATE {symbol}: {gate_reason}", flush=True)
                return

            qty_total = self.size_qty(plan.entry, plan.r)
            if qty_total <= 0:
                log_event("skip_entry_bad_qty", symbol, entry=plan.entry, r=plan.r)
                return

            # -----------------------------
            # Quote-aware entry limit (optional)
            # -----------------------------
            buy_ref = float(plan.entry)
            bid = None
            ask = None

            if self.use_quotes_for_limits:
                q = self.last_quote.get(symbol) or {}
                bid = float(q.get("bid") or 0) or None
                ask = float(q.get("ask") or 0) or None
                if ask is not None and ask > 0:
                    # Chase guard: if the ask has already moved too far above the signal price,
                    # the move is done — don't chase into it.
                    max_chase_pct = float(os.getenv("WB_MAX_ENTRY_CHASE_PCT", "0.05"))
                    if plan.entry > 0 and ask > plan.entry * (1 + max_chase_pct):
                        log_event(
                            "skip_entry_ask_too_high",
                            symbol,
                            ask=float(ask),
                            signal_entry=float(plan.entry),
                            pct_above=round((ask / plan.entry - 1) * 100, 1),
                            max_pct=max_chase_pct * 100,
                        )
                        print(
                            f"⛔ SKIP {symbol}: ask={ask:.4f} is {(ask/plan.entry-1)*100:.1f}% above signal={plan.entry:.4f} "
                            f"(>{max_chase_pct*100:.0f}% chase limit — stock already ran)",
                            flush=True,
                        )
                        return

                    # --- Pre-trade quote quality gate ---
                    # If quotes are unreliable now, exits will be blind.
                    last_px = float(self.last_price.get(symbol, 0))

                    # Check 1: Phantom bid at entry (same logic as exit guard)
                    if bid is not None and last_px > 0 and self.entry_max_bid_dev_pct > 0:
                        bid_dev = abs(float(bid) - last_px) / last_px * 100
                        if bid_dev > self.entry_max_bid_dev_pct:
                            log_event("skip_entry_phantom_bid", symbol,
                                      bid=float(bid), last_trade=last_px,
                                      deviation_pct=round(bid_dev, 1))
                            print(f"⛔ SKIP {symbol}: bid={bid:.4f} deviates {bid_dev:.1f}% from "
                                  f"last_trade={last_px:.4f} (>{self.entry_max_bid_dev_pct}% — quotes unreliable)",
                                  flush=True)
                            return

                    # Check 2: Wide spread
                    if bid is not None and ask is not None and bid > 0 and ask > 0:
                        mid = (float(bid) + float(ask)) / 2
                        if mid > 0 and self.entry_max_spread_pct > 0:
                            spread_pct = (float(ask) - float(bid)) / mid * 100
                            if spread_pct > self.entry_max_spread_pct:
                                log_event("skip_entry_wide_spread", symbol,
                                          bid=float(bid), ask=float(ask),
                                          spread_pct=round(spread_pct, 1))
                                print(f"⛔ SKIP {symbol}: spread={spread_pct:.1f}% "
                                      f"(bid={bid:.4f} ask={ask:.4f}) exceeds "
                                      f"{self.entry_max_spread_pct}% — too wide",
                                      flush=True)
                                return

                    # buy off ask for more realistic "will I fill" pricing
                    buy_ref = float(ask) + float(self.entry_quote_pad)

            buy_limit = max(0.01, buy_ref + float(self.limit_offset_buy) + float(self.entry_initial_wiggle))
            buy_limit = round(float(buy_limit), 2)

            # -----------------------------
            # Alpaca cash truth gate
            # -----------------------------
            try:
                available = self.get_available_funds()
                max_aff = self.affordable_qty(available, buy_limit, reserve_pct=0.05)
                if qty_total > max_aff:
                    log_event(
                        "skip_entry_bad_qty",
                        symbol,
                        wanted=qty_total,
                        max_affordable=max_aff,
                        cash=available,
                        limit=float(buy_limit),
                    )
                    return
            except Exception as e:
                log_event("exception", symbol, where="affordability_check", error=str(e))
                return

            if self.three_tranche_enabled:
                qty_core, qty_t2, qty_runner = self._split_tranches(qty_total)
                take_profit_t2 = plan.entry + (self.t2_tp_r * plan.r)
            else:
                qty_core, qty_runner = self._split_core_runner(qty_total)
                qty_t2 = 0
                take_profit_t2 = 0.0

            log_event(
                "order_preview",
                symbol,
                side="buy",
                qty=qty_total,
                entry=plan.entry,
                stop=plan.stop,
                take_profit=plan.take_profit,
                r=plan.r,
                armed=self.armed,
                core_qty=qty_core,
                t2_qty=qty_t2,
                runner_qty=qty_runner,
                buy_limit=float(buy_limit),
                ref_bid=float(bid) if bid is not None else None,
                ref_ask=float(ask) if ask is not None else None,
            )

            if not self.armed:
                return

            if symbol in self.open or symbol in self.pending:
                log_event("skip_entry_already_open", symbol)
                return

            # -----------------------------
            # Per-symbol re-entry cooldown
            # -----------------------------
            now_utc = datetime.now(timezone.utc)
            cooldown_until = self._symbol_cooldown_until.get(symbol)

            if cooldown_until and now_utc < cooldown_until:
                remaining = int((cooldown_until - now_utc).total_seconds())
                log_event("skip_entry_cooldown", symbol, remaining_sec=remaining,
                          entry_count=self._symbol_entry_count.get(symbol, 0))
                print(
                    f"⏸️ COOLDOWN {symbol}: {remaining}s remaining "
                    f"({self.max_entries_per_symbol} entries reached, waiting {self.symbol_cooldown_sec}s)",
                    flush=True,
                )
                return

            # If cooldown expired, reset the counter
            if cooldown_until and now_utc >= cooldown_until:
                self._symbol_entry_count[symbol] = 0
                self._symbol_cooldown_until.pop(symbol, None)

            # -----------------------------
            # Submit entry
            # -----------------------------
            try:
                req = LimitOrderRequest(
                    symbol=symbol,
                    qty=qty_total,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.DAY,
                    limit_price=buy_limit,
                    extended_hours=True,
                )
                order = self.client.submit_order(req)
                order_id = str(order.id)

                print(
                    f"🟦 ENTRY SUBMITTED {symbol} id={order_id} qty={qty_total} limit={buy_limit:.2f}",
                    flush=True,
                )

            except Exception as e:
                log_event("order_submit_failed", symbol, where="entry", error=str(e))
                return

            now_utc = datetime.now(timezone.utc)

            self.pending[symbol] = PendingEntry(
                symbol=symbol,
                order_id=order_id,
                qty_total=qty_total,
                qty_core=qty_core,
                qty_runner=qty_runner,
                entry=plan.entry,
                stop=plan.stop,
                r=plan.r,
                take_profit=plan.take_profit,
                submitted_at_utc=now_utc,
                cancel_requested=False,
                last_limit=float(buy_limit),
                reprice_count=0,
                qty_t2=qty_t2,
                take_profit_t2=take_profit_t2,
                filled_applied=0,
            )

            t2_str = f" t2={qty_t2}" if qty_t2 > 0 else ""
            print(
                f"🟨 ENTRY PENDING {symbol} id={order_id} target={qty_total} core={qty_core}{t2_str} runner={qty_runner} stop={plan.stop:.4f}",
                flush=True,
            )

            log_event(
                "entry_pending",
                symbol,
                order_id=order_id,
                qty=qty_total,
                limit_price=float(buy_limit),
                submitted_at_utc=now_utc.isoformat(),
            )

            # Track re-entry count and start cooldown when cap is reached
            entry_count = self._symbol_entry_count.get(symbol, 0) + 1
            self._symbol_entry_count[symbol] = entry_count
            if entry_count >= self.max_entries_per_symbol:
                cd_until = now_utc + timedelta(seconds=self.symbol_cooldown_sec)
                self._symbol_cooldown_until[symbol] = cd_until
                print(
                    f"⏸️ COOLDOWN STARTED {symbol}: {entry_count} entries reached, "
                    f"next entry allowed in {self.symbol_cooldown_sec}s",
                    flush=True,
                )


    # -----------------------------
    # Pending entry -> open promotion (with chase)
    # -----------------------------

    def _check_pending(self, symbol: str):
        # Snapshot pending entry
        with self._lock:
            p = self.pending.get(symbol)
            if not p:
                return

            order_id = p.order_id
            qty_total = int(p.qty_total)
            submitted_at = p.submitted_at_utc
            cancel_requested = bool(p.cancel_requested)
            reprice_count = int(p.reprice_count)
            last_limit = float(p.last_limit)
            entry = float(p.entry)
            stop = float(p.stop)
            r = float(p.r)
            take_profit = float(p.take_profit)
            filled_applied = int(getattr(p, "filled_applied", 0))

        now_utc = datetime.now(timezone.utc)
        age = (now_utc - submitted_at).total_seconds()

        # 1) Poll order status (by id)
        try:
            o = self.client.get_order_by_id(order_id)
        except Exception as e:
            log_event("exception", symbol, where="check_pending_entry", order_id=order_id, error=str(e))
            return

        status = str(getattr(o, "status", "")).lower()
        # Normalize Alpaca enums like "orderstatus.filled" -> "filled"
        if "." in status:
            status = status.split(".")[-1]
        filled_qty_raw = getattr(o, "filled_qty", 0) or 0
        try:
            filled_total = int(math.floor(float(filled_qty_raw)))
        except Exception:
            filled_total = 0

        # Safety cap
        filled_total = min(filled_total, qty_total)

        # 2) Apply fills (filled_qty is cumulative -> apply delta)
        if filled_total > 0:
            with self._lock:
                p = self.pending.get(symbol)
                if not p:
                    return

                already = int(getattr(p, "filled_applied", 0))
                delta = filled_total - already

                if delta > 0:
                    t = self.open.get(symbol)

                    if not t:
                        qty_now = filled_total
                        if self.three_tranche_enabled:
                            qty_core, qty_t2, qty_runner = self._split_tranches(qty_now)
                        else:
                            qty_core, qty_runner = self._split_core_runner(qty_now)
                            qty_t2 = 0
                        self.open[symbol] = OpenTrade(
                            symbol=symbol,
                            qty_total=qty_now,
                            qty_core=qty_core,
                            qty_runner=qty_runner,
                            entry=p.entry,
                            stop=p.stop,
                            r=p.r,
                            take_profit=p.take_profit,
                            tp_hit=False,
                            peak=p.entry,
                            runner_stop=p.stop,
                            created_at_utc=datetime.now(timezone.utc),
                            qty_t2=qty_t2,
                            take_profit_t2=getattr(p, 'take_profit_t2', 0.0),
                        )
                    else:
                        t.qty_total += delta
                        if not t.tp_hit:
                            if self.three_tranche_enabled:
                                t.qty_core, t.qty_t2, t.qty_runner = self._split_tranches(t.qty_total)
                            else:
                                t.qty_core, t.qty_runner = self._split_core_runner(t.qty_total)
                        else:
                            t.qty_runner += delta

                    p.filled_applied = already + delta

                    log_event(
                        "entry_filled" if status == "filled" else "entry_partial",
                        symbol,
                        order_id=p.order_id,
                        status=status,
                        filled_total=filled_total,
                        filled_applied=p.filled_applied,
                        delta_applied=delta,
                        qty_target=p.qty_total,
                        qty_remaining=max(0, p.qty_total - p.filled_applied),
                        entry=p.entry,
                        stop=p.stop,
                        take_profit=p.take_profit,
                        r=p.r,
                    )
                    print(f"✅ ENTRY FILL {symbol} +{delta} (filled={filled_total}/{p.qty_total}) status={status}", flush=True)

        # 3) If fully filled, adjust entry to actual avg fill price, then clear pending
        if status == "filled":
            avg_price = getattr(o, "filled_avg_price", None)
            if avg_price is not None:
                avg_price = float(avg_price)
                with self._lock:
                    t = self.open.get(symbol)
                    if t and avg_price > 0:
                        old_entry = t.entry
                        t.entry = avg_price
                        t.r = t.entry - t.stop
                        t.peak = max(t.peak, t.entry)
                        if t.r > 0:
                            tp_r = float(os.getenv("WB_TAKE_PROFIT_R", "1.0"))
                            t.take_profit = t.entry + (tp_r * t.r)
                        slip = avg_price - old_entry
                        if abs(slip) > 0.001:
                            log_event("entry_price_adjusted", symbol,
                                      old_entry=old_entry, new_entry=avg_price,
                                      slippage=round(slip, 4), new_r=round(t.r, 4))
                            print(
                                f"📐 ENTRY ADJUSTED {symbol}: trigger={old_entry:.4f} → fill={avg_price:.4f} "
                                f"(slip={slip:+.4f}) R={t.r:.4f} TP={t.take_profit:.4f}",
                                flush=True,
                            )
            with self._lock:
                self.pending.pop(symbol, None)
            return

        # 4) Terminal no-fill states
        if status in ("rejected", "expired"):
            log_event("entry_not_filled", symbol, order_id=order_id, status=status)
            print(f"🟥 ENTRY FAILED {symbol} id={order_id} status={status}", flush=True)
            with self._lock:
                self.pending.pop(symbol, None)
            return

        # 5) If we have ANY fills, never chase the rest (just wait)
        with self._lock:
            p = self.pending.get(symbol)
            if not p:
                return
            if int(getattr(p, "filled_applied", 0)) > 0:
                return

        # 6) Timeout -> request cancel once
        if age >= self.entry_timeout_sec:
            with self._lock:
                p = self.pending.get(symbol)
                if not p:
                    return
                if not p.cancel_requested:
                    try:
                        self.client.cancel_order_by_id(p.order_id)
                        p.cancel_requested = True

                        log_event(
                            "entry_timeout_cancel_requested",
                            symbol,
                            order_id=p.order_id,
                            age_sec=age,
                            reprice_count=p.reprice_count,
                            last_limit=p.last_limit,
                        )
                        print(f"🟧 ENTRY TIMEOUT cancel_requested {symbol} id={p.order_id} age={age:.1f}s", flush=True)
                    except Exception as e:
                        log_event("exception", symbol, where="cancel_pending_entry", order_id=p.order_id, error=str(e))
                        return

        # 7) Replace logic:
        #    After we request cancel, don't wait forever for status=="canceled".
        #    If the order is NOT in OPEN orders anymore, treat it as canceled and replace.
        with self._lock:
            p = self.pending.get(symbol)
            if not p:
                return
            if not p.cancel_requested:
                return

            # Guard: max attempts
            if p.reprice_count >= self.entry_max_attempts:
                order_id = p.order_id
                log_event("entry_give_up", symbol, order_id=order_id, reprice_count=p.reprice_count, reason="max_attempts")
                print(f"🟥 ENTRY GIVE UP {symbol} attempts={p.reprice_count}", flush=True)
                self.pending.pop(symbol, None)
                # Cancel the Alpaca order so it doesn't fill after we forget about it
                try:
                    self.client.cancel_order_by_id(order_id)
                    log_event("entry_give_up_cancel_sent", symbol, order_id=order_id)
                except Exception as e:
                    log_event("entry_give_up_cancel_failed", symbol, order_id=order_id, error=str(e))
                return

            current_order_id = p.order_id

        # Check if this order is still OPEN (strong truth)
        try:
            req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol])
            open_orders = self.client.get_orders(req)
            open_ids = {str(x.id) for x in open_orders}
            still_open = current_order_id in open_ids
        except Exception:
            # Fallback to status if OPEN query fails
            still_open = status in ("new", "accepted", "pending_new", "partially_filled")

        # If still open, wait (cancel may still be processing)
        if still_open:
            return

        # At this point, it's effectively canceled/gone → replace
        with self._lock:
            p = self.pending.get(symbol)
            if not p:
                return

            max_pay = max(0.01, round(float(p.entry) + float(self.entry_max_chase), 2))

            # Quote-aware chase reference: ASK > last trade > last_limit
            ref = None
            if self.use_quotes_for_limits:
                q = self.last_quote.get(symbol) or {}
                ask = float(q.get("ask") or 0) or None
                if ask is not None and ask > 0:
                    ref = float(ask) + float(self.entry_quote_pad)

            if ref is None:
                last = self.last_price.get(symbol)
                ref = float(last) if last is not None else float(p.last_limit)

            proposed = float(ref) + float(self.limit_offset_buy) + float(self.entry_chase_step)
            new_limit = max(0.01, round(min(proposed, max_pay), 2))

            # Cap check
            if float(p.last_limit) >= float(max_pay) - 1e-9:
                order_id = p.order_id
                log_event(
                    "entry_give_up",
                    symbol,
                    order_id=order_id,
                    reprice_count=p.reprice_count,
                    reason="at_max_chase_cap",
                    last_limit=float(p.last_limit),
                    max_pay=float(max_pay),
                )
                print(f"🟥 ENTRY GIVE UP {symbol} at_max_chase last_limit={p.last_limit} cap={max_pay}", flush=True)
                self.pending.pop(symbol, None)
                # Cancel the Alpaca order so it doesn't fill after we forget about it
                try:
                    self.client.cancel_order_by_id(order_id)
                    log_event("entry_give_up_cancel_sent", symbol, order_id=order_id)
                except Exception as e:
                    log_event("entry_give_up_cancel_failed", symbol, order_id=order_id, error=str(e))
                return

            old_order_id = p.order_id
            qty_total = int(p.qty_total)

        try:
            req = LimitOrderRequest(
                symbol=symbol,
                qty=qty_total,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.DAY,
                limit_price=new_limit,
                extended_hours=True,
            )
            new_order = self.client.submit_order(req)
            new_id = str(new_order.id)
        except Exception as e:
            log_event("entry_replace_failed", symbol, old_order_id=old_order_id, error=str(e))
            print(f"🟥 ENTRY REPLACE FAILED {symbol} old={old_order_id} err={e}", flush=True)
            with self._lock:
                self.pending.pop(symbol, None)
            return

        with self._lock:
            p = self.pending.get(symbol)
            if not p:
                return

            # Replace pending entry record
            self.pending[symbol] = PendingEntry(
                symbol=symbol,
                order_id=new_id,
                qty_total=p.qty_total,
                qty_core=p.qty_core,
                qty_runner=p.qty_runner,
                entry=p.entry,
                stop=p.stop,
                r=p.r,
                take_profit=p.take_profit,
                submitted_at_utc=datetime.now(timezone.utc),
                cancel_requested=False,
                last_limit=float(new_limit),
                reprice_count=p.reprice_count + 1,
                filled_applied=0,
            )

        log_event(
            "entry_replaced",
            symbol,
            old_order_id=old_order_id,
            new_order_id=new_id,
            new_limit=float(new_limit),
            reprice_count=reprice_count + 1,
            max_pay=float(max_pay),
        )
        print(f"🟦 ENTRY REPLACED {symbol} new_id={new_id} new_limit={new_limit:.2f} attempt={reprice_count + 1}", flush=True)


    def _cancel_pending_entry_if_any(self, symbol: str, why: str):
        with self._lock:
            p = self.pending.get(symbol)
            if not p or p.cancel_requested:
                return
            order_id = p.order_id

        try:
            self.client.cancel_order_by_id(order_id)
            with self._lock:
                p2 = self.pending.get(symbol)
                if p2 and p2.order_id == order_id:
                    p2.cancel_requested = True
            log_event("entry_cancel_requested", symbol, order_id=order_id, why=why)
            print(f"🟧 ENTRY CANCEL REQUESTED {symbol} id={order_id} why={why}", flush=True)
        except Exception as e:
            log_event("exception", symbol, where="cancel_pending_entry_after_tp", order_id=order_id, error=str(e))

    # -----------------------------
    # Exit submission (limit sells) — quote-aware
    # -----------------------------
    def _exit(self, symbol: str, qty: int, reason: str, price: float):
        with self._lock:
            if qty <= 0:
                return

            # Set re-entry cooldown on stop_hit
            if reason == "stop_hit" and self._reentry_cooldown_sec > 0:
                self._stop_hit_cooldown_until[symbol] = datetime.now(timezone.utc) + timedelta(seconds=self._reentry_cooldown_sec)

            if not self.armed:
                log_event("exit_preview", symbol, qty=qty, reason=reason, price=float(price), armed=False)
                print(f"🟫 EXIT PREVIEW {symbol} qty={qty} reason={reason} px={price:.4f} (DISARMED)", flush=True)
                return

            if symbol in self.pending_exits:
                log_event("skip_exit_already_pending", symbol, reason=reason, qty=qty)
                return

            last = float(price)

            bid = None
            ask = None
            if self.use_quotes_for_limits:
                q = self.last_quote.get(symbol) or {}
                bid = float(q.get("bid") or 0) or None
                ask = float(q.get("ask") or 0) or None

            ref = float(bid) if bid is not None else last
            # Sanity: if bid-based ref diverges >5% from last trade, use last trade
            if ref > 0 and last > 0 and abs(ref - last) / last > 0.05:
                ref = last
            # Use percentage-based offsets scaled to price (fall back to fixed-cent if PCT is 0)
            wiggle = ref * (self.exit_wiggle_pct / 100) if self.exit_wiggle_pct > 0 else float(self.exit_initial_wiggle)
            offset = ref * (self.exit_offset_sell_pct / 100) if self.exit_offset_sell_pct > 0 else float(self.limit_offset_sell)
            sell_limit = ref - offset - wiggle - float(self.exit_quote_pad)
            sell_limit = max(0.01, round(sell_limit, 2))

            try:
                req = LimitOrderRequest(
                    symbol=symbol,
                    qty=int(qty),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=sell_limit,
                    extended_hours=True,
                )
                order = self.client.submit_order(req)

                order_id = str(order.id)
                now_utc = datetime.now(timezone.utc)

                self.pending_exits[symbol] = PendingExit(
                    symbol=symbol,
                    order_id=order_id,
                    qty=int(qty),
                    reason=reason,
                    submitted_at_utc=now_utc,
                    cancel_requested=False,
                    last_limit=float(req.limit_price),
                    filled_applied=0,
                    attempts=0,
                )

                log_event("exit_submitted", symbol, order_id=order_id, qty=int(qty), reason=reason, limit_price=float(req.limit_price), ext=True, ref_last=last, ref_bid=float(bid) if bid is not None else None, ref_ask=float(ask) if ask is not None else None)
                print(f"🟥 EXIT SUBMITTED {symbol} id={order_id} qty={qty} reason={reason} limit={sell_limit}", flush=True)

            except Exception as e:
                log_event("exit_submit_failed", symbol, where=reason, error=str(e))
                print(f"🟥 EXIT SUBMIT FAILED {symbol} reason={reason} err={e}", flush=True)
                return

    # -----------------------------
    # Pending exit tracking + chase
    # -----------------------------
    def _check_pending_exit(self, symbol: str):
        # Snapshot pending exit
        with self._lock:
            p = self.pending_exits.get(symbol)
            if not p:
                return

        # Need an open trade to apply fills against
        with self._lock:
            t = self.open.get(symbol)
        if not t:
            with self._lock:
                self.pending_exits.pop(symbol, None)
            return

        now_utc = datetime.now(timezone.utc)
        age = (now_utc - p.submitted_at_utc).total_seconds()

        # 1) Timeout -> request cancel once
        if age >= self.exit_timeout_sec and not p.cancel_requested:
            try:
                self.client.cancel_order_by_id(p.order_id)
                with self._lock:
                    p2 = self.pending_exits.get(symbol)
                    if p2 and p2.order_id == p.order_id:
                        p2.cancel_requested = True

                log_event(
                    "exit_timeout_cancel_requested",
                    symbol,
                    order_id=p.order_id,
                    age_sec=age,
                    reason=p.reason,
                    last_limit=p.last_limit,
                    attempts=getattr(p, "attempts", 0),
                )
                print(f"🟧 EXIT TIMEOUT cancel_requested {symbol} id={p.order_id} age={age:.1f}s reason={p.reason}", flush=True)
            except Exception as e:
                log_event("exception", symbol, where="cancel_exit", order_id=p.order_id, error=str(e))

        # 2) Poll order status
        try:
            o = self.client.get_order_by_id(p.order_id)
        except Exception as e:
            log_event("exception", symbol, where="check_exit", order_id=p.order_id, error=str(e))
            return

        raw_status = getattr(o, "status", "")
        status = str(raw_status).lower()
        # Normalize Alpaca enums like "orderstatus.filled"
        if "." in status:
            status = status.split(".")[-1]

        filled_qty_raw = getattr(o, "filled_qty", 0) or 0
        try:
            filled_total = int(math.floor(float(filled_qty_raw)))
        except Exception:
            filled_total = 0

        # Read actual fill price from Alpaca for P&L tracking
        exit_avg_raw = getattr(o, "filled_avg_price", None)
        exit_avg = float(exit_avg_raw) if exit_avg_raw is not None else None

        # 3) Apply fills (filled_qty is cumulative -> apply delta)
        with self._lock:
            p = self.pending_exits.get(symbol)
            t = self.open.get(symbol)
            if not p or not t:
                return

            already = int(getattr(p, "filled_applied", 0))
            delta = filled_total - already

            if delta > 0:
                remaining_for_order = max(0, int(p.qty) - int(p.filled_applied))
                applied = min(delta, remaining_for_order, int(t.qty_total))

                if applied > 0:
                    p.filled_applied += applied
                    t.qty_total -= applied

                    # Track actual exit fill price for realized P&L
                    if exit_avg is not None and exit_avg > 0 and filled_total > 0:
                        order_total_cost = exit_avg * filled_total
                        delta_cost = order_total_cost - p.accounted_cost
                        t.exit_filled_qty += applied
                        t.exit_filled_cost += delta_cost
                        p.accounted_cost = order_total_cost

                    # Reason-based accounting
                    if p.reason in ("take_profit_core", "take_profit_t1"):
                        t.qty_core = max(0, t.qty_core - applied)

                        # Activate runner on first core/T1 fill
                        if not t.tp_hit:
                            be_offset = float(os.getenv("WB_BE_OFFSET", "0.01"))
                            t.tp_hit = True
                            t.runner_stop = max(t.runner_stop, t.entry + be_offset)
                            t.peak = max(t.peak, float(self.last_bid.get(symbol, t.peak)))

                            log_event(
                                "runner_activated",
                                symbol,
                                runner_qty=t.qty_runner,
                                t2_qty=t.qty_t2,
                                runner_stop=t.runner_stop,
                                peak=t.peak,
                                trail_r=self.runner_trail_r,
                                activated_by="core_fill",
                            )
                            t2_str = f" t2={t.qty_t2}" if t.qty_t2 > 0 else ""
                            print(f"🟪 RUNNER ACTIVATED {symbol}{t2_str} runner_qty={t.qty_runner} runner_stop={t.runner_stop:.4f}", flush=True)

                        self._cancel_pending_entry_if_any(symbol, why="core_tp_filled_runner_activated")

                    elif p.reason == "take_profit_t2":
                        t.qty_t2 = max(0, t.qty_t2 - applied)
                        if not t.t2_hit:
                            t.t2_hit = True
                            # Lock stop at entry + 0.5R
                            lock_stop = t.entry + (self.t2_stop_lock_r * t.r)
                            t.runner_stop = max(t.runner_stop, lock_stop)
                            log_event("t2_hit", symbol, runner_stop=t.runner_stop,
                                      lock_stop=lock_stop, runner_qty=t.qty_runner)
                            print(f"🟪 T2 HIT {symbol} stop locked at {t.runner_stop:.4f} runner_qty={t.qty_runner}", flush=True)

                    elif p.reason == "post_t1_stop":
                        # T2 + T3 exit together after T1 hit
                        t2_take = min(t.qty_t2, applied)
                        t.qty_t2 = max(0, t.qty_t2 - t2_take)
                        runner_take = applied - t2_take
                        if runner_take > 0:
                            t.qty_runner = max(0, t.qty_runner - runner_take)

                    elif p.reason in ("runner_stop_hit", "bearish_engulfing_exit_runner",
                                       "topping_wicky_exit_runner"):
                        t.qty_runner = max(0, t.qty_runner - applied)

                    elif p.reason in ("stop_hit", "bearish_engulfing_exit_full",
                                       "topping_wicky_exit_full", "trail_stop",
                                       "max_loss_hit", "chandelier_stop"):
                        core_take = min(t.qty_core, applied)
                        t.qty_core = max(0, t.qty_core - core_take)
                        remaining = applied - core_take
                        t2_take = min(t.qty_t2, remaining)
                        t.qty_t2 = max(0, t.qty_t2 - t2_take)
                        runner_take = remaining - t2_take
                        if runner_take > 0:
                            t.qty_runner = max(0, t.qty_runner - runner_take)

                    else:
                        core_take = min(t.qty_core, applied)
                        t.qty_core = max(0, t.qty_core - core_take)
                        remaining = applied - core_take
                        t2_take = min(t.qty_t2, remaining)
                        t.qty_t2 = max(0, t.qty_t2 - t2_take)
                        runner_take = remaining - t2_take
                        if runner_take > 0:
                            t.qty_runner = max(0, t.qty_runner - runner_take)

                    exit_px_str = f"{exit_avg:.4f}" if exit_avg else "?"
                    log_event(
                        "exit_filled" if status == "filled" else "exit_partial",
                        symbol,
                        order_id=p.order_id,
                        status=status,
                        filled_total=filled_total,
                        filled_applied=p.filled_applied,
                        delta_applied=applied,
                        reason=p.reason,
                        fill_avg_price=exit_avg,
                        qty_remaining=t.qty_total,
                        core_remaining=t.qty_core,
                        runner_remaining=t.qty_runner,
                    )
                    print(
                        f"✅ EXIT FILL {symbol} -{applied} @{exit_px_str} reason={p.reason} status={status} "
                        f"remaining={t.qty_total} (core={t.qty_core}, runner={t.qty_runner})",
                        flush=True,
                    )

        # 4) If fully filled (or we applied enough), clear pending exit and maybe close position
        with self._lock:
            p = self.pending_exits.get(symbol)
            t = self.open.get(symbol)
            if not p or not t:
                return

            remaining_open = int(t.qty_total)
            done = (status == "filled") or (int(p.filled_applied) >= int(p.qty))

        if done:
            with self._lock:
                self.pending_exits.pop(symbol, None)

            if remaining_open <= 0:
                # Compute realized P&L from actual fill prices
                pnl_str = ""
                with self._lock:
                    t = self.open.get(symbol)
                if t:
                    exit_qty = t.exit_filled_qty
                    if exit_qty > 0 and t.exit_filled_cost > 0:
                        avg_exit = t.exit_filled_cost / exit_qty
                        realized_pnl = t.exit_filled_cost - (t.entry * exit_qty)
                        pnl_str = f" | P&L=${realized_pnl:+,.0f} (entry={t.entry:.4f} exit_avg={avg_exit:.4f} qty={exit_qty})"
                        log_event("position_closed", symbol, reason=p.reason,
                                  entry=t.entry, exit_avg=round(avg_exit, 4),
                                  qty=exit_qty, realized_pnl=round(realized_pnl, 2))
                    else:
                        log_event("position_closed", symbol, reason=p.reason,
                                  entry=t.entry, exit_avg=None, qty=exit_qty)
                else:
                    log_event("position_closed", symbol, reason=p.reason)

                # Record P&L for daily management
                if t and t.exit_filled_qty > 0 and t.exit_filled_cost > 0:
                    realized_pnl = t.exit_filled_cost - (t.entry * t.exit_filled_qty)
                    self._record_trade_pnl(realized_pnl)
                    # Notify quality gate of trade result
                    if self.on_trade_close_callback is not None:
                        try:
                            self.on_trade_close_callback(symbol, realized_pnl)
                        except Exception:
                            pass

                with self._lock:
                    self.open.pop(symbol, None)
                # Reset parabolic regime detector for this symbol
                if self.parabolic_regime_enabled and symbol in self._parabolic_detectors:
                    self._parabolic_detectors[symbol].reset()
                print(f"🏁 POSITION CLOSED {symbol} reason={p.reason}{pnl_str}", flush=True)
            return

        # 5) Terminal states where we may chase/replace (ONLY if we requested cancel)
        terminal = status in ("canceled", "rejected", "expired")
        remaining = max(0, int(p.qty) - int(p.filled_applied))

        if terminal and remaining > 0:
            # If we didn't request cancel, don't replace — just drop it as "not filled".
            if not p.cancel_requested:
                log_event("exit_not_filled", symbol, order_id=p.order_id, status=status, reason=p.reason)
                print(f"🟥 EXIT NOT FILLED {symbol} id={p.order_id} status={status} reason={p.reason}", flush=True)
                with self._lock:
                    self.pending_exits.pop(symbol, None)
                return

            # --- Stale guard: don't chase using stale quotes/prices ---
            last_ts = self.last_quote_ts_utc.get(symbol)
            if last_ts is not None:
                stale_age = (datetime.now(timezone.utc) - last_ts).total_seconds()
                if stale_age >= float(getattr(self, "stale_price_sec", 5.0)):
                    log_event("exit_chase_skipped_stale_price", symbol, reason=p.reason, stale_age_sec=stale_age, order_id=p.order_id)
                    print(f"🟧 EXIT CHASE SKIPPED {symbol} reason={p.reason} stale_age={stale_age:.1f}s", flush=True)
                    with self._lock:
                        self.pending_exits.pop(symbol, None)
                    return

            # Max attempts
            if int(getattr(p, "attempts", 0)) >= int(self.exit_max_attempts):
                log_event("exit_replace_stopped_max_attempts", symbol, order_id=p.order_id, reason=p.reason, attempts=p.attempts)
                print(f"🟥 EXIT GIVE UP {symbol} reason={p.reason} attempts={p.attempts}", flush=True)
                with self._lock:
                    self.pending_exits.pop(symbol, None)
                return

            # Price reference: prefer BID if present, else last trade
            q = self.last_quote.get(symbol) or {}
            bid = q.get("bid")
            ref = float(bid) if (bid is not None and float(bid) > 0) else self.last_price.get(symbol)
            if ref is None:
                log_event("exit_chase_skipped_no_price", symbol, reason=p.reason, order_id=p.order_id)
                with self._lock:
                    self.pending_exits.pop(symbol, None)
                return

            # --- Stop-floor protection (prevents nonsense limits like 4.44) ---
            # For stop-based exits, never submit a limit meaningfully below the stop.
            # Use current trade's stop/runner_stop as the floor anchor.
            with self._lock:
                t = self.open.get(symbol)
            stop_anchor = None
            if t:
                if p.reason in ("runner_stop_hit", "bearish_engulfing_exit_runner"):
                    stop_anchor = float(getattr(t, "runner_stop", 0.0) or 0.0)
                elif p.reason in ("stop_hit", "bearish_engulfing_exit_full", "max_loss_hit"):
                    stop_anchor = float(getattr(t, "stop", 0.0) or 0.0)

            # Allowed slop under stop (cents). Keep tight; this is protection.
            stop_floor_pad = float(os.getenv("WB_EXIT_STOP_FLOOR_PAD", "0.02"))
            stop_floor = (stop_anchor - stop_floor_pad) if (stop_anchor and stop_anchor > 0) else None

            # Chase floor cap (how low we’ll chase relative to reference price)
            max_chase = float(ref) * (self.exit_max_chase_pct / 100) if self.exit_max_chase_pct > 0 else float(self.exit_max_chase)
            floor_limit = max(0.01, float(ref) - max_chase)

            # If stop_floor exists, raise the floor
            if stop_floor is not None:
                floor_limit = max(float(floor_limit), float(stop_floor))

            # Proposed: slightly below ref (sell to get out)
            chase_step = float(ref) * (self.exit_chase_step_pct / 100) if self.exit_chase_step_pct > 0 else float(self.exit_chase_step)
            offset = float(ref) * (self.exit_offset_sell_pct / 100) if self.exit_offset_sell_pct > 0 else float(self.limit_offset_sell)
            proposed = float(ref) - offset - chase_step
            new_limit = max(0.01, round(max(float(floor_limit), float(proposed)), 2))

            # Cap check: if we're already at/under the floor, stop
            if float(p.last_limit) <= float(floor_limit) + 1e-9:
                log_event(
                    "exit_replace_stopped_at_cap",
                    symbol,
                    last_limit=float(p.last_limit),
                    floor_limit=float(floor_limit),
                    stop_anchor=stop_anchor,
                    reason=p.reason,
                    attempts=p.attempts,
                )
                print(
                    f"🟥 EXIT STOPPED AT CAP {symbol} reason={p.reason} last_limit={p.last_limit} floor={floor_limit:.2f}",
                    flush=True,
                )
                with self._lock:
                    self.pending_exits.pop(symbol, None)
                return

            old_order_id = p.order_id

            # Submit replacement order
            try:
                req = LimitOrderRequest(
                    symbol=symbol,
                    qty=int(remaining),
                    side=OrderSide.SELL,
                    time_in_force=TimeInForce.DAY,
                    limit_price=new_limit,
                    extended_hours=True,
                )
                new_order = self.client.submit_order(req)
                new_id = str(new_order.id)

            except Exception as e:
                log_event("exit_replace_failed", symbol, old_order_id=old_order_id, error=str(e), reason=p.reason)
                print(f"🟥 EXIT REPLACE FAILED {symbol} reason={p.reason} err={e}", flush=True)
                with self._lock:
                    self.pending_exits.pop(symbol, None)
                return

            # Update pending exit in-place
            with self._lock:
                p2 = self.pending_exits.get(symbol)
                if not p2:
                    return
                p2.order_id = new_id
                p2.submitted_at_utc = datetime.now(timezone.utc)
                p2.cancel_requested = False
                p2.last_limit = float(new_limit)
                p2.attempts = int(getattr(p2, "attempts", 0)) + 1
                p2.accounted_cost = 0.0  # reset for new order's fills

            log_event(
                "exit_replaced",
                symbol,
                old_order_id=old_order_id,
                new_order_id=new_id,
                new_limit=float(new_limit),
                reason=p.reason,
                filled_applied=p.filled_applied,
                attempts=int(getattr(p, "attempts", 0)) + 1,
                floor_limit=float(floor_limit),
                stop_anchor=stop_anchor,
                ref=float(ref),
            )
            print(f"🟦 EXIT REPLACED {symbol} new_id={new_id} new_limit={new_limit:.2f} attempt={int(getattr(p, 'attempts', 0)) + 1}", flush=True)
            return

        # 6) Safety: if position is already flat, cleanup
        with self._lock:
            t = self.open.get(symbol)
            if t and int(t.qty_total) <= 0:
                pnl_str = ""
                exit_qty = t.exit_filled_qty
                if exit_qty > 0 and t.exit_filled_cost > 0:
                    avg_exit = t.exit_filled_cost / exit_qty
                    realized_pnl = t.exit_filled_cost - (t.entry * exit_qty)
                    pnl_str = f" | P&L=${realized_pnl:+,.0f} (entry={t.entry:.4f} exit_avg={avg_exit:.4f} qty={exit_qty})"
                    log_event("position_closed", symbol, reason=p.reason,
                              entry=t.entry, exit_avg=round(avg_exit, 4),
                              qty=exit_qty, realized_pnl=round(realized_pnl, 2))
                    self._record_trade_pnl(realized_pnl)
                else:
                    log_event("position_closed", symbol, reason=p.reason)
                self.open.pop(symbol, None)
                self.pending_exits.pop(symbol, None)
                print(f"🏁 POSITION CLOSED {symbol} reason={p.reason}{pnl_str}", flush=True)


    # -----------------------------
    # Price updates
    # -----------------------------
    def on_price(self, symbol: str, price: float, ts):
        with self._lock:
            self.last_price[symbol] = float(price)

            # ✅ trade print timestamp
            self._touch_trade_ts(symbol, ts)

            # ✅ Always keep pending entry synced
            if symbol in self.pending:
                self._check_pending(symbol)

        self._manage_exits(symbol)

    def on_quote(self, symbol: str, bid: float | None, ask: float | None, ts=None):
        if bid is None and ask is None:
            return

        with self._lock:
            q = self.last_quote.get(symbol, {"bid": 0.0, "ask": 0.0})
            if bid is not None and bid > 0:
                q["bid"] = float(bid)
                self.last_bid[symbol] = float(bid)
            if ask is not None and ask > 0:
                q["ask"] = float(ask)
                self.last_ask[symbol] = float(ask)
            self.last_quote[symbol] = q

            # ✅ quote timestamp (only if we got any usable leg)
            if (bid is not None and bid > 0) or (ask is not None and ask > 0):
                self._touch_quote_ts(symbol, ts)

        self._manage_exits(symbol)


    def update_trailing_stop_on_10s_bar(self, symbol: str, bar_close: float, bar_peak: float):
        """Update R-multiple trailing stop on each 10-second bar close.

        Called by bot.py on every 10s bar close. Uses bar_close (not tick) to avoid
        spike noise — a single rogue tick won't advance the trailing stop.
        bar_peak is the bar high, used for the trail-below-peak tier.
        """
        if os.getenv("WB_TRAILING_STOP_ENABLED", "0") != "1":
            return
        with self._lock:
            t = self.open.get(symbol)
            # Only activate after signal mode's own tp_hit — avoids premature exits
            # on cascading stocks that pull back before their run.
            # Also skip if R < WB_TRAILING_STOP_MIN_R_PCT% of entry (halt-spike trades
            # with tiny absolute R on high-priced stocks disrupt cascade if trailed).
            if t is None or not t.tp_hit or t.r <= 0:
                return
            _min_r_pct = float(os.getenv("WB_TRAILING_STOP_MIN_R_PCT", "1.0"))
            _r_pct = (t.r / t.entry * 100.0) if t.entry > 0 else 0.0
            if _r_pct < _min_r_pct:
                return
            bar_r = (bar_close - t.entry) / t.r
            t.highest_r = max(t.highest_r, bar_r)
            _be_thr = float(os.getenv("WB_TRAILING_STOP_BE_THRESHOLD_R", "2"))
            _lk_thr = float(os.getenv("WB_TRAILING_STOP_LOCK_THRESHOLD_R", "4"))
            _tr_thr = float(os.getenv("WB_TRAILING_STOP_TRAIL_THRESHOLD_R", "6"))
            _tr_off = float(os.getenv("WB_TRAILING_STOP_TRAIL_OFFSET", "0.15"))
            new_stop = t.stop
            if t.highest_r >= _be_thr:
                new_stop = max(new_stop, t.entry)           # breakeven
            if t.highest_r >= _lk_thr:
                new_stop = max(new_stop, t.entry + t.r)     # lock +1R
            if t.highest_r >= _tr_thr:
                new_stop = max(new_stop, t.peak - _tr_off)  # trail below peak
            if new_stop > t.stop:
                log_event("trailing_stop_raise", symbol,
                          old_stop=round(t.stop, 4), new_stop=round(new_stop, 4),
                          highest_r=round(t.highest_r, 2), peak=round(t.peak, 4))
                t.stop = new_stop

    def _in_parabolic_grace(self, symbol: str) -> bool:
        """Suppress BE exits during genuine parabolic ramps (not flash spikes)."""
        if not self.be_parabolic_grace:
            return False
        t = self.open.get(symbol)
        if not t:
            return False
        # Condition 1: trade is in meaningful profit
        px = float(self.last_price.get(symbol, 0))
        if px < t.entry + (self.be_grace_min_r * t.r):
            return False
        # Condition 2: recent 10s bars show new highs (parabolic, not crash)
        highs = self._recent_10s_highs.get(symbol, [])
        if len(highs) < 2:
            return False
        window = highs[-self.be_grace_lookback:]
        new_high_count = 0
        running_high = window[0]
        for bh in window[1:]:
            if bh > running_high:
                new_high_count += 1
                running_high = bh
        return new_high_count >= self.be_grace_min_new_highs

    def on_bar_close(self, symbol: str, o: float, h: float, l: float, c: float, v: float = 0):
        with self._lock:
            prev = self.last_bar.get(symbol)
            self.last_bar[symbol] = {"o": o, "h": h, "l": l, "c": c}

        # Track 10s bar highs for legacy parabolic grace
        highs = self._recent_10s_highs.setdefault(symbol, [])
        highs.append(h)
        if len(highs) > self.be_grace_lookback + 5:
            self._recent_10s_highs[symbol] = highs[-(self.be_grace_lookback + 5):]

        # Feed parabolic regime detector
        if self.parabolic_regime_enabled:
            t = self.open.get(symbol)
            if t:
                det = self._parabolic_detectors.get(symbol)
                if det is None:
                    from parabolic import ParabolicRegimeDetector
                    det = ParabolicRegimeDetector(
                        enabled=True,
                        min_new_highs=int(os.getenv("WB_PARABOLIC_MIN_NEW_HIGHS", "3")),
                        chandelier_mult=float(os.getenv("WB_PARABOLIC_CHANDELIER_MULT", "2.5")),
                        min_hold_bars_normal=int(os.getenv("WB_PARABOLIC_MIN_HOLD_BARS_NORMAL", "3")),
                        min_hold_bars_parabolic=int(os.getenv("WB_PARABOLIC_MIN_HOLD_BARS", "12")),
                    )
                    self._parabolic_detectors[symbol] = det
                det.on_10s_bar(o, h, l, c, v, t.entry, t.r)

        self._manage_exits(symbol)

        if not self.exit_on_bear_engulf:
            return

        t = self.open.get(symbol)
        if not t or not prev:
            return

        bear = is_bearish_engulfing(o, h, l, c, prev["o"], prev["h"], prev["l"], prev["c"])
        if not bear:
            return

        # Time-based BE grace (like TW grace — suppress BE for first N minutes after entry)
        if self.be_grace_sec > 0 and t.created_at_utc:
            age_sec = (datetime.now(timezone.utc) - t.created_at_utc).total_seconds()
            if age_sec < self.be_grace_sec:
                return

        # Parabolic regime detector (new) or legacy grace
        # In signal mode, do NOT suppress exits — cascading re-entry IS the strategy
        if self.exit_mode != "signal":
            if self.parabolic_regime_enabled:
                det = self._parabolic_detectors.get(symbol)
                if det and det.should_suppress_exit():
                    log_event("be_exit_suppressed_parabolic_regime", symbol,
                              entry=t.entry, r=t.r, price=float(self.last_price.get(symbol, 0)))
                    return
            elif self._in_parabolic_grace(symbol):
                log_event("be_exit_suppressed_parabolic", symbol,
                          entry=t.entry, r=t.r, price=float(self.last_price.get(symbol, 0)))
                return

        # Profit gate: suppress BE only in small positive profit (< min R)
        # Skip in signal mode — BE exits are part of the cascading strategy
        _be_min_profit_r = float(os.getenv("WB_BE_MIN_PROFIT_R", "0.5"))
        if self.exit_mode != "signal" and _be_min_profit_r > 0 and t.r > 0:
            px_now = float(self.last_price.get(symbol, c))
            _be_unreal = px_now - t.entry
            if 0 < _be_unreal < _be_min_profit_r * t.r:
                print(f"  BE_SUPPRESSED (profit_gate: ${_be_unreal:.2f} < {_be_min_profit_r}R=${_be_min_profit_r * t.r:.2f}) {symbol} @ {px_now:.4f}", flush=True)
                return

        if symbol in self.pending_exits:
            log_event("exit_signal_ignored_pending_exit", symbol, signal="bearish_engulfing")
            return

        px = self.last_bid.get(symbol)
        if px is None:
            px = self.last_price.get(symbol, c)
        px = float(px)

        if not t.tp_hit:
            qty_to_exit = t.qty_total
            reason = "bearish_engulfing_exit_full"
        else:
            # Post-T1: exit remaining T2 + T3
            qty_to_exit = t.qty_t2 + t.qty_runner
            reason = "bearish_engulfing_exit_runner"

        if qty_to_exit <= 0:
            return

        log_event("exit_signal", symbol, signal="bearish_engulfing", action="exit", qty=qty_to_exit, price=float(px), tp_hit=t.tp_hit)
        print(f"🟧 EXIT SIGNAL {symbol} bearish_engulfing qty={qty_to_exit} tp_hit={t.tp_hit}", flush=True)

        self._exit(symbol, qty=qty_to_exit, reason=reason, price=px)

    def on_exit_signal(self, symbol: str, signal_name: str):
        """
        Generic exit triggered by external pattern detection
        (topping_wicky, l2_bearish, l2_ask_wall, etc.).
        Same structure as bearish engulfing exit above.
        """
        t = self.open.get(symbol)
        if not t:
            return

        if symbol in self.pending_exits:
            log_event("exit_signal_ignored_pending_exit", symbol, signal=signal_name)
            return

        # Suppress pattern exits (TW, L2) during parabolic regime — hard stops NEVER suppressed
        # In signal mode, do NOT suppress exits — cascading re-entry IS the strategy
        if signal_name in ("topping_wicky", "l2_bearish", "l2_ask_wall"):
            if self.exit_mode != "signal" and self.parabolic_regime_enabled:
                det = self._parabolic_detectors.get(symbol)
                if det and det.should_suppress_exit():
                    log_event("pattern_exit_suppressed_parabolic_regime", symbol,
                              signal=signal_name, entry=t.entry, r=t.r,
                              price=float(self.last_price.get(symbol, 0)))
                    return

        px = self.last_bid.get(symbol)
        if px is None:
            px = self.last_price.get(symbol)
        if px is None:
            return
        px = float(px)

        if not t.tp_hit:
            qty_to_exit = t.qty_total
            reason = f"{signal_name}_exit_full"
        else:
            # Post-T1: exit remaining T2 + T3
            qty_to_exit = t.qty_t2 + t.qty_runner
            reason = f"{signal_name}_exit_runner"

        if qty_to_exit <= 0:
            return

        log_event("exit_signal", symbol, signal=signal_name, action="exit",
                  qty=qty_to_exit, price=px, tp_hit=t.tp_hit)
        print(f"EXIT SIGNAL {symbol} {signal_name} qty={qty_to_exit} tp_hit={t.tp_hit}",
              flush=True)

        self._exit(symbol, qty=qty_to_exit, reason=reason, price=px)

    def _manage_exits(self, symbol: str):
        # ✅ Stale-price warning (rate-limited)
        self._warn_if_stale_trade_and_quote(symbol)

        t = self.open.get(symbol)
        if not t:
            return

        # Don't evaluate stops/TP while the entry order is still filling.
        # Submitting a sell while a buy is open at a higher limit triggers
        # Alpaca's "potential wash trade" rejection.
        if symbol in self.pending:
            return

        # Use bid for exit decisions, but ONLY if the quote is fresh AND sane.
        # Guard 1: stale bid (>10s old) → fall back to last trade price.
        # Guard 2: phantom bid (fresh timestamp but price wildly off from last
        #          trade) → fall back to last trade price. This catches bad NBBO
        #          quotes from thin exchanges or data feed glitches (e.g. bid
        #          shows $14.92 while trades are printing at $17.43).
        bid = self.last_bid.get(symbol)
        last = float(self.last_price.get(symbol, t.entry))
        if bid is not None:
            quote_ts = self.last_quote_ts_utc.get(symbol)
            if quote_ts is not None:
                bid_age = (datetime.now(timezone.utc) - quote_ts).total_seconds()
                if bid_age > 10:
                    bid = last
        if bid is not None and last > 0:
            deviation = abs(float(bid) - last) / last
            if deviation > 0.05:
                log_event("phantom_bid_rejected", symbol,
                          bid=float(bid), last_trade=last,
                          deviation=round(deviation, 4))
                print(
                    f"⚠️ PHANTOM BID REJECTED {symbol}: bid={bid:.4f} vs last_trade={last:.4f} "
                    f"({deviation*100:.1f}% off) → using last trade",
                    flush=True,
                )
                bid = last
        if bid is None:
            bid = last

        t.peak = max(t.peak, float(bid))

        # --- MAX LOSS CAP (hard safety net) ---
        if self.max_loss_r > 0 and t.r > 0:
            loss_per_share = t.entry - float(bid)
            if loss_per_share >= self.max_loss_r * t.r:
                if symbol not in self.pending_exits:
                    log_event("max_loss_cap_triggered", symbol,
                              entry=t.entry, bid=float(bid),
                              loss_r=round(loss_per_share / t.r, 1),
                              max_loss_r=self.max_loss_r)
                    print(
                        f"MAX LOSS CAP {symbol}: {loss_per_share/t.r:.1f}R loss > {self.max_loss_r:.1f}R cap "
                        f"-- FORCED EXIT qty={t.qty_total}",
                        flush=True,
                    )
                    self._exit(symbol, qty=t.qty_total, reason="max_loss_hit", price=bid)
                return

        # --- Bail Timer: exit if not profitable within N minutes ---
        if self.bail_timer_enabled and t.created_at_utc and t.r > 0:
            age_sec = (datetime.now(timezone.utc) - t.created_at_utc).total_seconds()
            bail_sec = self.bail_timer_minutes * 60
            if age_sec >= bail_sec:
                unrealized = float(bid) - t.entry
                if unrealized <= 0:
                    if symbol not in self.pending_exits:
                        log_event("bail_timer_exit", symbol,
                                  entry=t.entry, bid=float(bid),
                                  unrealized=round(unrealized, 4),
                                  age_min=round(age_sec / 60, 1))
                        print(
                            f"BAIL TIMER {symbol}: {age_sec/60:.1f}min elapsed, "
                            f"unrealized=${unrealized:.2f} <= $0 — EXIT qty={t.qty_total}",
                            flush=True,
                        )
                        self._exit(symbol, qty=t.qty_total, reason="bail_timer", price=bid)
                    return

        # --- Chandelier stop (parabolic regime, classic mode ONLY) ---
        # In signal mode, the existing signal trail handles exits;
        # Chandelier is wider and causes worse exits on flash spikes / cascading re-entry stocks
        if self.parabolic_regime_enabled and self.exit_mode == "classic":
            det = self._parabolic_detectors.get(symbol)
            if det:
                chandelier = det.get_chandelier_stop()
                if chandelier > 0 and float(bid) <= chandelier:
                    if symbol not in self.pending_exits:
                        log_event("chandelier_stop_hit", symbol,
                                  entry=t.entry, bid=float(bid),
                                  chandelier=chandelier, peak=t.peak)
                        print(
                            f"CHANDELIER STOP {symbol}: bid={bid:.4f} <= chandelier={chandelier:.4f} "
                            f"-- EXIT qty={t.qty_total}",
                            flush=True,
                        )
                        self._exit(symbol, qty=t.qty_total, reason="chandelier_stop", price=bid)
                    return

                # Exhaustion trim: proactive partial exit on volume divergence + shooting star
                if det.should_trim() and t.qty_runner > 0 and t.tp_hit:
                    if symbol not in self.pending_exits:
                        log_event("parabolic_exhaustion_trim", symbol,
                                  entry=t.entry, bid=float(bid), runner_qty=t.qty_runner)
                        print(
                            f"PARABOLIC EXHAUSTION {symbol}: trimming runner qty={t.qty_runner}",
                            flush=True,
                        )
                        self._exit(symbol, qty=t.qty_runner, reason="parabolic_exhaustion", price=bid)
                    return

        # --- Signal exit mode: no fixed TP, trailing stop on full position ---
        if self.exit_mode == "signal":
            # Activate trailing once price reaches TP level
            if bid >= t.entry + (self.be_trigger_r * t.r):
                t.tp_hit = True
                be_stop = t.entry + float(os.getenv("WB_BE_OFFSET", "0.01"))
                t.stop = max(t.stop, be_stop)

            # Trail only after TP level reached (before that, hard stop provides safety)
            if t.tp_hit:
                trail_stop = t.peak * (1.0 - self.signal_trail_pct)
                t.stop = max(t.stop, trail_stop)

            # NOTE: R-multiple trailing stop is updated on 10s bar closes via
            # update_trailing_stop_on_10s_bar(). The stop level (t.stop) is checked here every tick.

            # Check stop (hard or trailed)
            if bid <= t.stop:
                if symbol not in self.pending_exits:
                    reason = "trail_stop" if t.tp_hit else "stop_hit"
                    self._exit(symbol, qty=t.qty_total, reason=reason, price=bid)
            return  # signal mode done — no TP logic

        # --- Classic exit mode: core TP + runner trail ---

        # 1) HARD STOP (pre-T1) — exit all tranches
        if (not t.tp_hit) and (bid <= t.stop):
            if symbol not in self.pending_exits:
                self._exit(symbol, qty=t.qty_total, reason="stop_hit", price=bid)
            return

        # Post-T1: manage trailing stops and T2/T3 exits
        if t.tp_hit:
            be_stop = t.entry + float(os.getenv("WB_BE_OFFSET", "0.01"))
            t.stop = max(t.stop, be_stop)

            trail_r = float(os.getenv("WB_RUNNER_TRAIL_R", "1.0"))
            trail_stop = t.peak - (trail_r * t.r)
            t.runner_stop = max(t.runner_stop, trail_stop, t.stop)

            # Post-T1, pre-T2 stop: exit remaining T2 + T3
            if self.three_tranche_enabled and not t.t2_hit and bid <= t.runner_stop:
                remaining = t.qty_t2 + t.qty_runner
                if symbol not in self.pending_exits and remaining > 0:
                    self._exit(symbol, qty=remaining, reason="post_t1_stop", price=bid)
                return

            # T2 take profit at 2R
            if self.three_tranche_enabled and not t.t2_hit and t.qty_t2 > 0:
                tp_fuzz = float(os.getenv("WB_TP_FUZZ", "0.02"))
                tp_t2 = t.entry + (self.t2_tp_r * t.r)
                if bid >= (tp_t2 - tp_fuzz):
                    if symbol not in self.pending_exits:
                        self._exit(symbol, qty=t.qty_t2, reason="take_profit_t2", price=bid)
                    return

            # Runner/T3 trailing stop
            if bid <= t.runner_stop:
                if symbol not in self.pending_exits and t.qty_runner > 0:
                    self._exit(symbol, qty=t.qty_runner, reason="runner_stop_hit", price=bid)
                return

        # 2) T1/CORE TAKE PROFIT (+ fuzz)
        if not t.tp_hit and t.qty_core > 0:
            tp_r = self.t1_tp_r if self.three_tranche_enabled else float(os.getenv("WB_CORE_TP_R", "1.0"))
            tp_fuzz = float(os.getenv("WB_TP_FUZZ", "0.02"))
            tp_core = t.entry + (tp_r * t.r)

            if bid >= (tp_core - tp_fuzz):
                if symbol not in self.pending_exits:
                    reason = "take_profit_t1" if self.three_tranche_enabled else "take_profit_core"
                    self._exit(symbol, qty=t.qty_core, reason=reason, price=bid)
                return

