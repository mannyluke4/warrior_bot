"""engine_bot_common.py — shared infrastructure for squeeze_bot.py and wb_bot.py.

Both Setup B strategy bots are thin consumers of the data engine. They
share the same plumbing:
  - Unix-socket client that connects to /tmp/warrior_engine.sock and
    yields decoded engine messages
  - Alpaca client setup from .env.engine (PA-NEW credentials)
  - Daily P&L + max-daily-loss tracking
  - Stream-paused / disconnected fail-CLOSED flag
  - Per-symbol bar builder hookups (the engine sends `bar` messages so
    bots don't build bars themselves — but they DO need to convert the
    engine's BarMessage back into a `bars.Bar` for the detector input)
  - Logging helpers

Only the strategy-specific bits live in the per-bot modules: which
detector class, which entry-message format, which exit logic.
"""

from __future__ import annotations

import json
import math
import os
import socket
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Result tuple for place_with_retry: (fill_price, filled_qty, last_order_id,
# last_limit, attempts). attempts counts retries beyond the initial shot —
# attempts=0 means "filled on the first attempt". last_order_id may be the
# final cancelled order id when no fill — useful for log audits / persistence.
from typing import NamedTuple

# Make sure the worktree root is on sys.path so `from bars import Bar` works
# regardless of how the bot was launched.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from bars import Bar
from engine_ipc import (
    BarMessage,
    HeartbeatMessage,
    HelloMessage,
    QuoteMessage,
    StreamPausedMessage,
    StreamResumedMessage,
    SubscriptionsMessage,
    TickMessage,
    DEFAULT_SOCKET_PATH,
    encode,
    read_frames_blocking,
)


load_dotenv(os.path.join(_HERE, ".env.engine"))
# Inherit non-secret detector config from main .env (Setup A's tuning knobs).
load_dotenv(os.path.join(_HERE, ".env"))

ET = ZoneInfo("America/New_York")
UTC = timezone.utc

SOCKET_PATH = os.getenv("ENGINE_IPC_SOCKET", DEFAULT_SOCKET_PATH)


def now_et() -> datetime:
    return datetime.now(ET)


def now_iso_et() -> str:
    return now_et().isoformat()


def today_et_str() -> str:
    return now_et().strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════════════════
# Alpaca client (paper trading on the third account)
# ══════════════════════════════════════════════════════════════════════


def make_alpaca_broker():
    """Build the AlpacaBroker from Setup B's third paper-account creds.

    Reads APCA_API_KEY_ID / APCA_API_SECRET_KEY from .env.engine. Raises
    RuntimeError with an actionable message if either is unset/template-
    sentinel — the bot should refuse to start rather than silently route
    to the wrong account.
    """
    key = os.getenv("APCA_API_KEY_ID", "").strip()
    secret = os.getenv("APCA_API_SECRET_KEY", "").strip()
    if not key or not secret:
        raise RuntimeError(
            "Setup B requires APCA_API_KEY_ID and APCA_API_SECRET_KEY in .env.engine "
            "(the third paper account credentials). See .env.engine template."
        )
    if "<" in key or "FILL" in key.upper() or "<" in secret:
        raise RuntimeError(
            "APCA creds in .env.engine look like the template placeholder. "
            "Fill in the third paper account's key/secret before starting."
        )
    from alpaca.trading.client import TradingClient
    from broker import AlpacaBroker
    paper = os.getenv("APCA_PAPER", "1") == "1"
    client = TradingClient(key, secret, paper=paper)
    return AlpacaBroker(client)


def wait_for_fill(broker, order_id: str, timeout: float = 10.0) -> tuple[Optional[float], int]:
    """Poll the broker for fill confirmation. Returns (avg_fill_price, qty)
    on fill, (None, 0) on timeout / cancellation. Mirrors Setup A's
    wait_for_fill pattern."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            o = broker.get_order_status(order_id)
        except Exception:
            o = None
        if o is None:
            time.sleep(0.5)
            continue
        if o.filled_qty > 0 and o.filled_avg_price > 0:
            if o.status in ("filled", "partially_filled"):
                return float(o.filled_avg_price), int(o.filled_qty)
        if o.status in ("cancelled", "rejected", "expired"):
            return None, 0
        time.sleep(0.5)
    # Best-effort cancel on timeout so the order isn't left hanging.
    try:
        broker.cancel_order(order_id)
    except Exception:
        pass
    return None, 0


# ══════════════════════════════════════════════════════════════════════
# Engine client — Unix-socket consumer
# ══════════════════════════════════════════════════════════════════════


@dataclass
class EngineState:
    """Live state derived from engine messages. Mutated by the reader
    thread, read by the bot's main thread. Single-flag atomicity is
    enough — the GIL covers the bool/int assignments we care about.

    `latest_alpaca_quote` is the per-symbol cache of the last Alpaca
    bid/ask we received from the engine. Read by get_priced_limit() at
    order-placement time so the limit reflects Alpaca's actual book
    rather than IBKR's possibly-stale last print. Dict shape:
        symbol -> (bid, ask, ts_utc)
    Updated on every QuoteMessage from the engine — no extra API call
    needed at signal time.
    """
    connected: bool = False         # socket open to engine
    ibkr_connected: bool = False    # engine's last reported ibkr state
    stream_paused: bool = True       # fail-CLOSED until first heartbeat
    last_heartbeat_ts: Optional[float] = None
    watchlist: list = None
    # Alpaca-stream health (mirrored from heartbeat).
    alpaca_stream_connected: bool = False
    alpaca_quote_rate_5s: int = 0
    alpaca_quote_oldest_age_ms: int = 0
    # Per-symbol latest Alpaca quote — (bid, ask, ts_utc).
    latest_alpaca_quote: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.watchlist is None:
            self.watchlist = []

    @property
    def can_enter(self) -> bool:
        """Fail-CLOSED policy: refuse new entries when stream is paused,
        socket is down, or engine reports ibkr is offline."""
        return self.connected and self.ibkr_connected and not self.stream_paused


def connect_to_engine(bot_id: str, timeout: float = 30.0) -> socket.socket:
    """Open a Unix-socket connection to the engine. Sends the Hello
    message immediately. Returns the connected socket on success.
    Raises ConnectionError after `timeout` seconds of failure."""
    deadline = time.time() + timeout
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.connect(SOCKET_PATH)
            s.sendall(encode(HelloMessage(bot_id=bot_id)))
            return s
        except OSError as e:
            last_err = e
            time.sleep(1)
    raise ConnectionError(
        f"Could not connect to engine at {SOCKET_PATH} within {timeout}s: {last_err}"
    )


def engine_reader_thread(sock: socket.socket, state: EngineState,
                         on_tick: Callable[[TickMessage], None],
                         on_bar: Callable[[BarMessage], None],
                         on_subscriptions: Callable[[SubscriptionsMessage], None],
                         on_disconnect: Callable[[], None]):
    """Run the message-pump loop. Blocks until the socket closes.

    Should be the target of a `threading.Thread`. on_* callbacks fire on
    THIS thread — keep them quick or hand off to the main bot loop via
    a queue. The detector + broker calls happen on a separate worker
    thread per-symbol (see `BotRunner`).

    QuoteMessage is intentionally handled inline here (no on_quote
    callback) — the bot uses the cached `state.latest_alpaca_quote`
    dict at order-placement time, so there's nothing strategy-specific
    to dispatch per-quote. Keeping the update in the reader thread
    avoids the queue-hop latency that would defeat the purpose.
    """
    try:
        for msg in read_frames_blocking(sock):
            if isinstance(msg, TickMessage):
                on_tick(msg)
            elif isinstance(msg, BarMessage):
                on_bar(msg)
            elif isinstance(msg, QuoteMessage):
                # Cheap dict write. Use a tuple for atomicity — readers
                # get a coherent (bid, ask, ts) snapshot even mid-update
                # since dict[k]=tuple is one slot replacement under the GIL.
                try:
                    ts_utc = datetime.fromisoformat(msg.ts).astimezone(UTC)
                except (ValueError, AttributeError):
                    ts_utc = datetime.now(UTC)
                state.latest_alpaca_quote[msg.symbol] = (
                    float(msg.bid), float(msg.ask), ts_utc,
                )
            elif isinstance(msg, HeartbeatMessage):
                state.last_heartbeat_ts = time.monotonic()
                state.ibkr_connected = msg.ibkr_connected
                state.alpaca_stream_connected = msg.alpaca_stream_connected
                state.alpaca_quote_rate_5s = msg.alpaca_quote_rate_5s
                state.alpaca_quote_oldest_age_ms = msg.alpaca_quote_oldest_age_ms
                # Heartbeat with ibkr_connected=False does NOT clear
                # stream_paused; only StreamResumed does.
            elif isinstance(msg, StreamPausedMessage):
                state.stream_paused = True
                print(f"[BOT] {now_iso_et()} stream_paused reason={msg.reason}",
                      flush=True)
            elif isinstance(msg, StreamResumedMessage):
                state.stream_paused = False
                print(f"[BOT] {now_iso_et()} stream_resumed", flush=True)
            elif isinstance(msg, SubscriptionsMessage):
                state.watchlist = list(msg.watchlist)
                on_subscriptions(msg)
            else:
                # Unknown / dict — log + ignore.
                print(f"[BOT] {now_iso_et()} unhandled engine msg: {msg!r}",
                      flush=True)
    finally:
        state.connected = False
        state.stream_paused = True
        on_disconnect()


def bar_from_message(msg: BarMessage) -> Bar:
    """Convert engine's BarMessage into a `bars.Bar` for detector input."""
    # ts_close is the bucket end (start + interval). Convert back to UTC.
    dt = datetime.fromisoformat(msg.ts_close).astimezone(UTC)
    # The detector cares about start_utc, not close. Reconstruct.
    # BarMessage.interval is "1m" today; engine always uses 60s buckets.
    from datetime import timedelta
    start_utc = dt - timedelta(seconds=60)
    return Bar(
        symbol=msg.symbol,
        start_utc=start_utc,
        open=float(msg.o), high=float(msg.h),
        low=float(msg.l), close=float(msg.c),
        volume=int(msg.v),
    )


# ══════════════════════════════════════════════════════════════════════
# Daily-P&L + risk tracking (mirrors Setup A's risk gate)
# ══════════════════════════════════════════════════════════════════════


class DailyRisk:
    """Track daily P&L and enforce a max-daily-loss kill switch.

    Mirrors Setup A's risk model: dollars-based daily-loss limit, optional
    equity-percent scale (2% of equity if WB_DAILY_LOSS_SCALE=1).
    """

    def __init__(self, starting_equity: float):
        self.starting_equity = float(starting_equity)
        self.daily_pnl: float = 0.0
        self.daily_entries: int = 0
        self.consecutive_losses: int = 0
        self.closed_trades: list = []

        self.max_daily_loss = float(os.getenv("WB_MAX_DAILY_LOSS", "500"))
        self.daily_loss_scale = os.getenv("WB_DAILY_LOSS_SCALE", "1") == "1"
        self.max_consecutive_losses = int(os.getenv("WB_MAX_CONSECUTIVE_LOSSES", "3"))

    @property
    def kill_switch_active(self) -> bool:
        if self.daily_loss_scale:
            effective = max(self.max_daily_loss, self.starting_equity * 0.02)
        else:
            effective = self.max_daily_loss
        if self.daily_pnl <= -effective:
            return True
        if self.consecutive_losses >= self.max_consecutive_losses:
            return True
        return False

    def record_close(self, pnl: float):
        self.daily_pnl += pnl
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        self.closed_trades.append({
            "ts": now_iso_et(), "pnl": pnl,
        })


def starting_equity_from_broker(broker) -> float:
    """Snapshot account equity at bot startup so risk math is anchored
    to the third Alpaca paper account's actual balance."""
    try:
        eq = broker.get_account_equity()
        if eq > 0:
            return float(eq)
    except Exception as e:
        print(f"[BOT] {now_iso_et()} equity lookup failed: {e!r}", flush=True)
    # Fallback so the bot still runs even if Alpaca hiccups at startup.
    return float(os.getenv("WB_FALLBACK_EQUITY", "30000"))


# ══════════════════════════════════════════════════════════════════════
# Cross-feed-aware limit pricing
# ══════════════════════════════════════════════════════════════════════

# Buffer config (read from env at module load — bots reload env via dotenv
# before this is imported, so values are stable for the session).
#
# WB_BASE_BUFFER_PCT       — % above IBKR signal price (BUY) / below (SELL)
# WB_CROSS_FEED_BUFFER_PCT — % above Alpaca ask (BUY) / below bid (SELL)
# WB_QUOTE_STALENESS_MAX_MS — quotes older than this fall back to IBKR-only
# WB_FALLBACK_SAFETY_BUFFER_PCT — wider buffer used when no fresh quote
BASE_BUFFER_PCT_DEFAULT = float(os.getenv("WB_BASE_BUFFER_PCT", "0.5"))
CROSS_FEED_BUFFER_PCT_DEFAULT = float(os.getenv("WB_CROSS_FEED_BUFFER_PCT", "0.5"))
QUOTE_STALENESS_MAX_MS_DEFAULT = int(os.getenv("WB_QUOTE_STALENESS_MAX_MS", "2000"))
FALLBACK_SAFETY_BUFFER_PCT_DEFAULT = float(
    os.getenv("WB_FALLBACK_SAFETY_BUFFER_PCT", "1.0")
)


def get_priced_limit(
    state: EngineState,
    symbol: str,
    side: Literal["BUY", "SELL"],
    ibkr_signal_price: float,
    base_buffer_pct: Optional[float] = None,
    cross_feed_buffer_pct: Optional[float] = None,
    max_quote_age_ms: Optional[int] = None,
    fallback_safety_buffer_pct: Optional[float] = None,
    log_label: str = "QUOTE_AWARE",
) -> float:
    """Compute an entry/exit limit price that's likely to fill on Alpaca.

    BUY:  limit = max(ibkr_signal * (1 + base_buffer_pct/100),
                       alpaca_ask  * (1 + cross_feed_buffer_pct/100))
    SELL: limit = min(ibkr_signal * (1 - base_buffer_pct/100),
                       alpaca_bid  * (1 - cross_feed_buffer_pct/100))

    Fallback (no fresh quote or stream offline): IBKR-only pricing using
    `fallback_safety_buffer_pct` (deliberately wider than base_buffer so a
    stale-quote situation doesn't underprice). Logs a `[FALLBACK]` line
    so the operator can audit how often fallback fires.

    Logs a `[QUOTE_AWARE]` line whenever the Alpaca-side bound is the
    binding constraint — that's the actionable data point for assessing
    whether the cross-feed fix is doing its job.
    """
    if base_buffer_pct is None:
        base_buffer_pct = BASE_BUFFER_PCT_DEFAULT
    if cross_feed_buffer_pct is None:
        cross_feed_buffer_pct = CROSS_FEED_BUFFER_PCT_DEFAULT
    if max_quote_age_ms is None:
        max_quote_age_ms = QUOTE_STALENESS_MAX_MS_DEFAULT
    if fallback_safety_buffer_pct is None:
        fallback_safety_buffer_pct = FALLBACK_SAFETY_BUFFER_PCT_DEFAULT

    side_upper = side.upper()
    if side_upper not in ("BUY", "SELL"):
        raise ValueError(f"get_priced_limit: side must be BUY or SELL, got {side!r}")

    base_pct = base_buffer_pct / 100.0
    cross_pct = cross_feed_buffer_pct / 100.0
    fallback_pct = fallback_safety_buffer_pct / 100.0

    if side_upper == "BUY":
        ibkr_limit = ibkr_signal_price * (1.0 + base_pct)
    else:
        ibkr_limit = ibkr_signal_price * (1.0 - base_pct)

    # Look up the cached Alpaca quote. If we have one and it's fresh,
    # compute the cross-feed-aware bound; otherwise fall back to IBKR-
    # only pricing with the wider safety buffer.
    snap = state.latest_alpaca_quote.get(symbol)
    stream_up = state.alpaca_stream_connected
    fresh_quote: Optional[tuple] = None
    if snap is not None and stream_up:
        bid, ask, ts_utc = snap
        # Quote is meaningful only if both sides are positive (one-sided
        # zero quotes happen at the open + after halts).
        if bid > 0 and ask > 0 and ask >= bid:
            age_ms = (datetime.now(UTC) - ts_utc).total_seconds() * 1000.0
            if age_ms <= max_quote_age_ms:
                fresh_quote = (bid, ask, age_ms)

    if fresh_quote is None:
        # Fallback — use IBKR signal + wider buffer.
        if side_upper == "BUY":
            limit = ibkr_signal_price * (1.0 + fallback_pct)
        else:
            limit = ibkr_signal_price * (1.0 - fallback_pct)
        limit = round(limit, 2)
        reason = "no_quote" if snap is None else (
            "stream_down" if not stream_up else "stale_quote"
        )
        print(f"[FALLBACK] {symbol} {side_upper} limit={limit:.4f} "
              f"reason={reason} ibkr_signal={ibkr_signal_price:.4f} "
              f"buffer_pct={fallback_safety_buffer_pct}", flush=True)
        return limit

    bid, ask, age_ms = fresh_quote
    if side_upper == "BUY":
        alpaca_limit = ask * (1.0 + cross_pct)
        limit = max(ibkr_limit, alpaca_limit)
        binding = "alpaca_ask" if alpaca_limit > ibkr_limit else "ibkr_signal"
    else:
        alpaca_limit = bid * (1.0 - cross_pct)
        limit = min(ibkr_limit, alpaca_limit)
        binding = "alpaca_bid" if alpaca_limit < ibkr_limit else "ibkr_signal"

    limit = round(limit, 2)
    # Log only when Alpaca was the binding constraint — that's the
    # high-signal data we want for evaluating the change. Side noted so
    # squeeze (BUY) and exits (SELL) can be filtered separately.
    if binding.startswith("alpaca_"):
        print(f"[{log_label}] {symbol} {side_upper} limit={limit:.4f} "
              f"from {binding}={ask if side_upper == 'BUY' else bid:.4f} "
              f"(ibkr_signal+buffer={round(ibkr_limit, 4):.4f}) "
              f"quote_age_ms={int(age_ms)}", flush=True)
    return limit


# ══════════════════════════════════════════════════════════════════════
# Retry-with-reprice loop
# ══════════════════════════════════════════════════════════════════════
#
# Why this exists (TRAW 2026-05-11): a single-shot limit picked at signal
# time goes stale fast — Alpaca's ask can jump above the IBKR-derived
# limit between the moment we price and the moment Alpaca routes. The
# 2026-05-11 failure showed 4 sequential limits at $2.36/$2.40/$2.44/$2.45
# all timing out because none of them ever touched Alpaca's actual ask.
#
# The fix: on each retry, repull get_priced_limit() so the new limit is
# anchored to the FRESHEST cached Alpaca quote (the engine reader thread
# updates state.latest_alpaca_quote on every QuoteMessage). The chase cap
# is computed off the ORIGINAL limit so we never buy more than N% above
# what we first committed to — protects against chasing a vertical print.

ENTRY_RETRY_ENABLED_DEFAULT = os.getenv("WB_ENTRY_RETRY_ENABLED", "1") == "1"
ENTRY_MAX_RETRIES_DEFAULT = int(os.getenv("WB_ENTRY_MAX_RETRIES", "3"))
ENTRY_RETRY_TIMEOUT_SEC_DEFAULT = int(os.getenv("WB_ENTRY_RETRY_TIMEOUT_SEC", "10"))
ENTRY_MAX_CHASE_PCT_DEFAULT = float(os.getenv("WB_ENTRY_MAX_CHASE_PCT", "2.0"))


class RetryResult(NamedTuple):
    """Result of place_with_retry. fill_price/filled_qty are None,0 on no-fill.
    last_order_id is the broker id of the FINAL attempted order (filled or
    cancelled) — useful for log correlation. attempts counts retries beyond
    the initial shot (0 = filled on first attempt).
    """
    fill_price: Optional[float]
    filled_qty: int
    last_order_id: Optional[str]
    last_limit: float
    attempts: int


def place_with_retry(
    broker,
    state: EngineState,
    symbol: str,
    side: Literal["BUY", "SELL"],
    qty: int,
    ibkr_signal_price: float,
    *,
    max_retries: Optional[int] = None,
    timeout_sec_per_attempt: Optional[float] = None,
    max_chase_pct: Optional[float] = None,
    base_buffer_pct: Optional[float] = None,
    cross_feed_buffer_pct: Optional[float] = None,
    fallback_safety_buffer_pct: Optional[float] = None,
    extended_hours: bool = True,
    log_prefix: str = "BOT",
    log_label: str = "QUOTE_AWARE",
    retry_enabled: Optional[bool] = None,
) -> RetryResult:
    """Submit a limit order with retry-and-reprice on timeout.

    On timeout, the order is cancelled (wait_for_fill cancels on timeout
    internally — we additionally re-cancel as defense in depth) and the
    next attempt repulls get_priced_limit() to anchor on the freshest
    Alpaca quote. Stops when:
      - Filled (returns RetryResult with fill_price/filled_qty set)
      - max_retries reached (logs ORDER TIMEOUT after N retries)
      - Reprice exceeds chase cap (logs ORDER TIMEOUT: exceeds max chase)

    chase cap direction:
      BUY:  abort if new_limit > original_limit * (1 + max_chase_pct/100)
      SELL: abort if new_limit < original_limit * (1 - max_chase_pct/100)

    Sizing is NOT recomputed between attempts (qty stays fixed) — letting
    risk-based qty drift with price is a design hazard.

    The stop price is NOT a parameter here — that's the caller's
    responsibility; only the entry limit moves between attempts.
    """
    if retry_enabled is None:
        retry_enabled = ENTRY_RETRY_ENABLED_DEFAULT
    if max_retries is None:
        max_retries = ENTRY_MAX_RETRIES_DEFAULT
    if timeout_sec_per_attempt is None:
        timeout_sec_per_attempt = ENTRY_RETRY_TIMEOUT_SEC_DEFAULT
    if max_chase_pct is None:
        max_chase_pct = ENTRY_MAX_CHASE_PCT_DEFAULT

    side_upper = side.upper()
    if side_upper not in ("BUY", "SELL"):
        raise ValueError(f"place_with_retry: side must be BUY or SELL, got {side!r}")

    # Anchor = first limit we computed. Chase cap is measured against it.
    original_limit = get_priced_limit(
        state, symbol, side_upper, ibkr_signal_price,
        base_buffer_pct=base_buffer_pct,
        cross_feed_buffer_pct=cross_feed_buffer_pct,
        fallback_safety_buffer_pct=fallback_safety_buffer_pct,
        log_label=log_label,
    )
    chase_pct = max_chase_pct / 100.0
    if side_upper == "BUY":
        chase_cap = round(original_limit * (1.0 + chase_pct), 4)
    else:
        chase_cap = round(original_limit * (1.0 - chase_pct), 4)

    # If retries are disabled, behave like the old single-shot path.
    effective_max_retries = max_retries if retry_enabled else 0

    cur_limit = original_limit
    last_order_id: Optional[str] = None
    attempt = 0
    while True:
        # On retry, repull the limit so we anchor on freshest Alpaca quote.
        if attempt > 0:
            cur_limit = get_priced_limit(
                state, symbol, side_upper, ibkr_signal_price,
                base_buffer_pct=base_buffer_pct,
                cross_feed_buffer_pct=cross_feed_buffer_pct,
                fallback_safety_buffer_pct=fallback_safety_buffer_pct,
                log_label=log_label,
            )
            # Chase cap: BUY rejects "too high", SELL rejects "too low".
            if side_upper == "BUY" and cur_limit > chase_cap:
                print(f"[{log_prefix}] {now_iso_et()} {symbol} ORDER TIMEOUT: "
                      f"{side_upper} reprice ${cur_limit:.4f} exceeds max chase "
                      f"${chase_cap:.4f} ({max_chase_pct}% above original "
                      f"${original_limit:.4f}) after {attempt} retries — giving up",
                      flush=True)
                return RetryResult(None, 0, last_order_id, cur_limit, attempt)
            if side_upper == "SELL" and cur_limit < chase_cap:
                print(f"[{log_prefix}] {now_iso_et()} {symbol} ORDER TIMEOUT: "
                      f"{side_upper} reprice ${cur_limit:.4f} below max chase "
                      f"${chase_cap:.4f} ({max_chase_pct}% below original "
                      f"${original_limit:.4f}) after {attempt} retries — giving up",
                      flush=True)
                return RetryResult(None, 0, last_order_id, cur_limit, attempt)

        # Submit (or resubmit).
        try:
            order = broker.submit_limit(
                symbol, qty, side_upper, cur_limit, extended_hours=extended_hours,
            )
        except Exception as e:
            print(f"[{log_prefix}] {now_iso_et()} {symbol} "
                  f"{'RETRY ' if attempt > 0 else ''}BROKER REJECT: {e!r}",
                  flush=True)
            return RetryResult(None, 0, last_order_id, cur_limit, attempt)
        last_order_id = order.order_id
        retry_tag = f" [RETRY {attempt}/{effective_max_retries}]" if attempt > 0 else ""
        print(f"[{log_prefix}] {now_iso_et()} BROKER ORDER: {order.order_id} "
              f"{side_upper} {qty} {symbol} @ ${cur_limit:.2f}{retry_tag}",
              flush=True)

        # Wait for fill / terminal state.
        fill_price, filled_qty = wait_for_fill(
            broker, order.order_id, timeout=timeout_sec_per_attempt,
        )
        if filled_qty > 0 and fill_price is not None:
            return RetryResult(float(fill_price), int(filled_qty),
                                order.order_id, cur_limit, attempt)

        # No fill — decide whether to retry.
        if attempt >= effective_max_retries:
            # wait_for_fill already best-effort cancels on timeout; if the
            # state machine raced (filled in-flight), the next iteration
            # would have seen filled_qty>0 already. Defense-in-depth cancel.
            try:
                broker.cancel_order(order.order_id)
            except Exception:
                pass
            print(f"[{log_prefix}] {now_iso_et()} {symbol} ORDER TIMEOUT: "
                  f"{side_upper} cancelling {order.order_id} after "
                  f"{attempt} retries", flush=True)
            return RetryResult(None, 0, order.order_id, cur_limit, attempt)

        # Ensure the prior order is in a terminal state before resubmitting.
        try:
            broker.cancel_order(order.order_id)
        except Exception:
            pass
        # Brief settle so Alpaca's state machine commits CANCELLED before
        # we submit a same-symbol order (avoids spurious "duplicate order").
        time.sleep(0.3)
        attempt += 1


__all__ = [
    "EngineState",
    "DailyRisk",
    "RetryResult",
    "bar_from_message",
    "connect_to_engine",
    "engine_reader_thread",
    "get_priced_limit",
    "make_alpaca_broker",
    "now_et",
    "now_iso_et",
    "place_with_retry",
    "starting_equity_from_broker",
    "today_et_str",
    "wait_for_fill",
    "ET",
    "UTC",
]
