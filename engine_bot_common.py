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

# ─── wait_for_fill terminal-status enum ─────────────────────────────────
# Returned as the 3rd element of wait_for_fill's tuple so place_with_retry
# (and any other caller) can distinguish "retry-worthy timeout" from
# "broker-side rejection that must NOT be resubmitted".
#
# Background: the 2026-05-11 TRAW incident on the subbot saw a BP-rejection
# (Alpaca returned status=rejected with insufficient buying power) loop the
# retry loop FOUR times, blindly resubmitting the same qty and being rejected
# each time. Same root cause as "exit retry loop on stop-hit might compound
# a position if a partial fill is treated as a timeout".
#
# Semantics:
#   FILL_STATUS_FILLED            — order fully (or "filled enough" — see partial
#                                     rule below) consumed. fill_price + fill_qty
#                                     are valid; caller proceeds.
#   FILL_STATUS_PARTIAL_THEN_TIMEOUT
#                                  — some shares filled, but the rest never did
#                                     before timeout. fill_price/fill_qty reflect
#                                     the partial. **place_with_retry MUST treat
#                                     this as a fill and NOT resubmit** — otherwise
#                                     the next attempt's qty would double-count.
#   FILL_STATUS_REJECTED          — broker rejected the order (BP, HTB, halt,
#                                     duplicate). Terminal. No retry — resubmitting
#                                     the same qty gets rejected again.
#   FILL_STATUS_CANCELLED         — order cancelled (by us or by broker). Terminal.
#                                     No retry — we already gave up on this attempt.
#   FILL_STATUS_EXPIRED           — TIF expired. Terminal. No retry — the limit was
#                                     stale enough that the venue dropped it; the
#                                     caller can decide to start a fresh attempt.
#   FILL_STATUS_REPLACED          — order replaced (rare on Alpaca; possible if a
#                                     pending replace race fires). Terminal — the
#                                     replacement order has its own id we no longer
#                                     track. Caller should treat as unknown state
#                                     and not retry.
#   FILL_STATUS_TIMEOUT           — no terminal state seen within timeout. Eligible
#                                     for retry-with-reprice (this is the ONLY
#                                     status that triggers another attempt).

FILL_STATUS_FILLED = "filled"
FILL_STATUS_PARTIAL_THEN_TIMEOUT = "partial_then_timeout"
FILL_STATUS_REJECTED = "rejected"
FILL_STATUS_CANCELLED = "cancelled"
FILL_STATUS_EXPIRED = "expired"
FILL_STATUS_REPLACED = "replaced"
FILL_STATUS_TIMEOUT = "timeout"

# Statuses that mean "do NOT resubmit". Filled is a success — also no resubmit.
FILL_TERMINAL_NO_RETRY = frozenset({
    FILL_STATUS_FILLED,
    FILL_STATUS_PARTIAL_THEN_TIMEOUT,
    FILL_STATUS_REJECTED,
    FILL_STATUS_CANCELLED,
    FILL_STATUS_EXPIRED,
    FILL_STATUS_REPLACED,
})

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


# Local override (gitignored) wins over committed template.
load_dotenv(os.path.join(_HERE, ".env.engine.local"))
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


def wait_for_fill(
    broker, order_id: str, timeout: float = 10.0,
) -> tuple[Optional[float], int, str]:
    """Poll the broker for fill confirmation. Returns a triple:
        (avg_fill_price, filled_qty, terminal_status)

    `terminal_status` is one of the FILL_STATUS_* constants and is the
    contract the retry loop uses to decide whether resubmit is safe. See
    the comment block on those constants for the full semantics matrix.

    Behavior:
      - status=filled with shares → (price, qty, FILL_STATUS_FILLED).
      - status=partially_filled at the deadline → (price, qty,
        FILL_STATUS_PARTIAL_THEN_TIMEOUT). Caller MUST NOT resubmit.
      - status=rejected → (None, 0, FILL_STATUS_REJECTED). Caller MUST NOT
        resubmit the same qty. Also logs Alpaca's reject_reason for audit.
      - status=cancelled → (None, 0, FILL_STATUS_CANCELLED).
      - status=expired → (None, 0, FILL_STATUS_EXPIRED).
      - status=replaced → (None, 0, FILL_STATUS_REPLACED).
      - deadline reached with no terminal state → cancel + return
        (None, 0, FILL_STATUS_TIMEOUT). Only this status is retry-eligible.

    On rejected, the partial fill (if any — rare but possible: Alpaca can
    fill some shares then reject the remainder) IS returned. The caller
    should treat the partial as a real position update and stop retrying.
    """
    deadline = time.time() + timeout
    last_partial_price: Optional[float] = None
    last_partial_qty: int = 0
    while time.time() < deadline:
        try:
            o = broker.get_order_status(order_id)
        except Exception:
            o = None
        if o is None:
            time.sleep(0.5)
            continue
        # Snapshot any partial-fill progress so we can return it from the
        # final partial_then_timeout / rejected path.
        if o.filled_qty > 0 and o.filled_avg_price > 0:
            last_partial_price = float(o.filled_avg_price)
            last_partial_qty = int(o.filled_qty)

        if o.status == "filled" and o.filled_qty > 0:
            return (
                float(o.filled_avg_price), int(o.filled_qty),
                FILL_STATUS_FILLED,
            )
        if o.status == "rejected":
            reason = getattr(o, "reject_reason", "") or "unspecified"
            print(f"[BOT] {now_iso_et()} order {order_id} REJECTED "
                  f"reason={reason!r} partial={last_partial_qty}/?", flush=True)
            # Return partial fill data too: if Alpaca rejected the remainder
            # after partially filling, the partial is real and the caller
            # must record it (otherwise broker truth diverges from bot state).
            if last_partial_qty > 0 and last_partial_price is not None:
                return (last_partial_price, last_partial_qty, FILL_STATUS_REJECTED)
            return (None, 0, FILL_STATUS_REJECTED)
        if o.status == "cancelled":
            if last_partial_qty > 0 and last_partial_price is not None:
                return (last_partial_price, last_partial_qty, FILL_STATUS_CANCELLED)
            return (None, 0, FILL_STATUS_CANCELLED)
        if o.status == "expired":
            if last_partial_qty > 0 and last_partial_price is not None:
                return (last_partial_price, last_partial_qty, FILL_STATUS_EXPIRED)
            return (None, 0, FILL_STATUS_EXPIRED)
        # Alpaca exposes "replaced" on order replace; treat as terminal
        # because the replacement carries a different id we no longer track.
        if getattr(o, "status", "") == "replaced":
            return (None, 0, FILL_STATUS_REPLACED)
        time.sleep(0.5)

    # Deadline reached without terminal state. If we observed a partial,
    # return PARTIAL_THEN_TIMEOUT so the retry loop records the partial
    # as a fill (and does NOT resubmit — that would compound the position).
    # Otherwise it's a clean timeout: cancel + report.
    if last_partial_qty > 0 and last_partial_price is not None:
        # Best-effort cancel of the remainder so it doesn't surprise-fill later.
        try:
            broker.cancel_order(order_id)
        except Exception:
            pass
        return (last_partial_price, last_partial_qty, FILL_STATUS_PARTIAL_THEN_TIMEOUT)
    try:
        broker.cancel_order(order_id)
    except Exception:
        pass
    return (None, 0, FILL_STATUS_TIMEOUT)


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
# WB_DIVERGENT_QUOTE_MAX_PCT — if Alpaca quote disagrees with IBKR by more
# than this %, the cached Alpaca quote is almost certainly stale or wrong;
# fall back to IBKR-only pricing instead of trusting Alpaca. Applies to
# BOTH BUY (vs alpaca_ask) and SELL (vs alpaca_bid). See 2026-05-12 FATN
# incident where IBKR stop $3.54 vs Alpaca bid $3.09 (12.7% gap).
DIVERGENT_QUOTE_MAX_PCT = float(os.getenv("WB_DIVERGENT_QUOTE_MAX_PCT", "5.0"))


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

    # Divergent-quote guard. If Alpaca's quote disagrees with IBKR by more
    # than DIVERGENT_PCT, the cached Alpaca quote is almost certainly stale
    # or wrong (post-halt one-sided print, missed update, etc). Using it
    # would risk:
    #   BUY  → chase a phantom move above IBKR's view
    #   SELL → sell BELOW where the symbol is actually trading
    # 2026-05-12 FATN: IBKR stop signal $3.54, Alpaca bid $3.09 (12.7% gap).
    # Without this guard, SELL limit priced at $3.07 (Alpaca-bid - buffer).
    # Order luckily filled at $3.52 ($0.45 of price improvement), but if a
    # thin buyer sat at $3.07-3.10 in Alpaca's book we'd have realized
    # a 3R loss instead of a 1R stop. Same shape on BUY: original directive
    # mentioned this fallback for the BUY side but it wasn't wired here.
    relevant = ask if side_upper == "BUY" else bid
    divergence_pct = abs(relevant - ibkr_signal_price) / ibkr_signal_price * 100.0
    if divergence_pct > DIVERGENT_QUOTE_MAX_PCT:
        if side_upper == "BUY":
            limit = ibkr_signal_price * (1.0 + fallback_pct)
        else:
            limit = ibkr_signal_price * (1.0 - fallback_pct)
        limit = round(limit, 2)
        print(f"[ALPACA_QUOTE_DIVERGENT] {symbol} {side_upper} limit={limit:.4f} "
              f"ibkr_signal={ibkr_signal_price:.4f} "
              f"{'alpaca_ask' if side_upper == 'BUY' else 'alpaca_bid'}={relevant:.4f} "
              f"gap_pct={divergence_pct:.2f} "
              f"(>{DIVERGENT_QUOTE_MAX_PCT}%) — using IBKR-only fallback", flush=True)
        return limit

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

        # Wait for fill / terminal state. The triple's third element is
        # the terminal-status enum — see FILL_STATUS_* constants and the
        # comment block above wait_for_fill for the full semantics matrix.
        fill_price, filled_qty, fill_status = wait_for_fill(
            broker, order.order_id, timeout=timeout_sec_per_attempt,
        )

        # FILLED: full success. Stop and return.
        if fill_status == FILL_STATUS_FILLED:
            return RetryResult(float(fill_price), int(filled_qty),
                                order.order_id, cur_limit, attempt)

        # PARTIAL_THEN_TIMEOUT: some shares filled, the rest didn't fill
        # before the per-attempt deadline. Treat the partial as a real
        # fill and STOP — resubmitting would compound the position because
        # the partial qty is already real at the broker.
        #
        # The retry loop carries `qty` (the originally-requested quantity)
        # not the remaining qty, so a naive resubmit would buy `qty` more,
        # not `qty - filled_qty`. Even computing remaining would risk a
        # race vs late-arriving fills. Cleaner contract: partial is final.
        if fill_status == FILL_STATUS_PARTIAL_THEN_TIMEOUT:
            print(f"[{log_prefix}] {now_iso_et()} {symbol} PARTIAL FILL "
                  f"{filled_qty}/{qty} {side_upper} — accepting partial, "
                  f"NOT retrying (would compound the position)", flush=True)
            return RetryResult(float(fill_price), int(filled_qty),
                                order.order_id, cur_limit, attempt)

        # REJECTED: broker refused (BP, HTB, halt, duplicate). Terminal.
        # If shares filled before the reject (rare), record those. Either
        # way: do NOT retry the same qty — it'll get rejected again.
        if fill_status == FILL_STATUS_REJECTED:
            if filled_qty > 0 and fill_price is not None:
                print(f"[{log_prefix}] {now_iso_et()} {symbol} REJECTED "
                      f"after partial fill {filled_qty}/{qty} — recording "
                      f"partial, NOT retrying (broker rejected remainder)",
                      flush=True)
                return RetryResult(float(fill_price), int(filled_qty),
                                    order.order_id, cur_limit, attempt)
            print(f"[{log_prefix}] {now_iso_et()} {symbol} {side_upper} "
                  f"REJECTED by broker — aborting retry loop (resubmitting "
                  f"same qty would re-trigger the same rejection)",
                  flush=True)
            return RetryResult(None, 0, order.order_id, cur_limit, attempt)

        # CANCELLED / EXPIRED / REPLACED: terminal but not a broker NACK.
        # Treat the same as a hard timeout — no retry, since we already
        # gave up on this attempt (cancelled = our cancel, or broker's;
        # expired = TIF; replaced = lost-track-of replacement order).
        if fill_status in (FILL_STATUS_CANCELLED, FILL_STATUS_EXPIRED,
                            FILL_STATUS_REPLACED):
            if filled_qty > 0 and fill_price is not None:
                print(f"[{log_prefix}] {now_iso_et()} {symbol} terminal "
                      f"{fill_status} after partial fill {filled_qty}/{qty} "
                      f"— recording partial, not retrying", flush=True)
                return RetryResult(float(fill_price), int(filled_qty),
                                    order.order_id, cur_limit, attempt)
            print(f"[{log_prefix}] {now_iso_et()} {symbol} order {order.order_id} "
                  f"terminal {fill_status} — not retrying", flush=True)
            return RetryResult(None, 0, order.order_id, cur_limit, attempt)

        # From here down, fill_status must be FILL_STATUS_TIMEOUT — the
        # only retry-eligible status. Decide whether we have budget left.
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


# ══════════════════════════════════════════════════════════════════════
# Session persistence — engine-specific namespace (Phase 3)
# ══════════════════════════════════════════════════════════════════════
#
# Layout (mirrors Setup A but isolated):
#
#   ~/warrior_bot_v2_engine/session_state_engine/<YYYY-MM-DD>/
#       marker.json                 — boot-mode decision token
#       watchlist.json              — symbols this engine subscribed to
#       squeeze_bot/
#           risk.json               — daily_pnl, counters, last-50 closed trades
#           open_trades.json        — active squeeze position state (augmented)
#       wb_bot/
#           risk.json               — same shape, WB side
#           open_trades.json        — active WB position state
#
# Setup A writes to ~/warrior_bot_v2/session_state/<date>/... directly;
# we deliberately namespace under "session_state_engine/" so the A/B
# comparison doesn't risk a cross-bot file-handle race or schema drift.
# The tick cache stays at tick_cache_engine/ where the engine already
# writes — no change to that here.
#
# Write policy:
#   - open_trades.json: synchronously flushed on EVERY position state
#     change (fill confirmed, peak advance, stop update, partial fill,
#     bail-arm transition, close). Same as Setup A's policy.
#   - risk.json: synchronously flushed on close (closes are infrequent
#     enough that per-close is fine). Background flush thread also
#     writes every 60s as a belt-and-suspenders against missed
#     transitions.
#   - watchlist.json: written on subscriptions message from engine.
#   - marker.json: written on cold start; auto-rotates at the date
#     boundary (decide_boot_mode keys on TODAY's directory only).
#
# Reads return typed defaults on any failure so the boot path can call
# them unconditionally and degrade cleanly to cold start on corrupt JSON.

ENGINE_SESSION_ROOT = os.path.join(_HERE, "session_state_engine")

# Schema for an open-trade record. The engine bots are richer than Setup
# A because the Position dataclass is the source of truth — every
# trade-management field the ladder reads must persist or the resumed
# bot won't make identical decisions on subsequent ticks.
OPEN_TRADE_REQUIRED_FIELDS_ENGINE = {
    "symbol", "setup_type", "entry_price", "entry_time", "qty", "r",
    "stop", "score", "peak", "tp_hit", "partial_filled_qty",
    "partial_filled_at", "runner_stop", "is_parabolic", "fill_confirmed",
    "order_id",
}


def _atomic_write_json(path: str, data) -> None:
    """tmpfile → fsync → os.replace. Same-dir tmpfile = atomic rename."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def _read_json_safe(path: str, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


class EngineSession:
    """Per-bot persistence helper. Each bot constructs its own instance with
    a `bot_id` ("squeeze_bot" / "wb_bot") which becomes the subdirectory
    name. All paths derive lazily from today's date so a long-running bot
    that crosses midnight cleanly rolls into a new session directory.
    """

    def __init__(self, bot_id: str, root: Optional[str] = None,
                 flush_sec: Optional[float] = None):
        self.bot_id = bot_id
        self.root = root or ENGINE_SESSION_ROOT
        # WB_SESSION_FLUSH_SEC mirrors Setup A's env var (kept as-is so a
        # single tuning knob applies to both setups).
        self.flush_sec = float(flush_sec if flush_sec is not None
                               else os.getenv("WB_SESSION_FLUSH_SEC", "30"))
        # Lock for read-modify-write under the periodic flush thread.
        self._lock = threading.Lock()

    # ── Path helpers ──────────────────────────────────────────────────
    def _day_dir(self, date_str: Optional[str] = None) -> str:
        return os.path.join(self.root, date_str or today_et_str())

    def _bot_dir(self, date_str: Optional[str] = None) -> str:
        return os.path.join(self._day_dir(date_str), self.bot_id)

    def marker_path(self, date_str: Optional[str] = None) -> str:
        return os.path.join(self._day_dir(date_str), "marker.json")

    def watchlist_path(self, date_str: Optional[str] = None) -> str:
        return os.path.join(self._day_dir(date_str), "watchlist.json")

    def open_trades_path(self, date_str: Optional[str] = None) -> str:
        return os.path.join(self._bot_dir(date_str), "open_trades.json")

    def risk_path(self, date_str: Optional[str] = None) -> str:
        return os.path.join(self._bot_dir(date_str), "risk.json")

    # ── Marker (boot-mode decision) ───────────────────────────────────
    def write_marker(self) -> None:
        _atomic_write_json(self.marker_path(), {
            "created_at": datetime.now(UTC).isoformat(),
            "pid": os.getpid(), "bot_id": self.bot_id,
        })

    def marker_exists(self, date_str: Optional[str] = None) -> bool:
        return os.path.exists(self.marker_path(date_str))

    def marker_age_seconds(self, date_str: Optional[str] = None) -> Optional[float]:
        data = _read_json_safe(self.marker_path(date_str), None)
        if not isinstance(data, dict) or "created_at" not in data:
            return None
        try:
            created = datetime.fromisoformat(data["created_at"])
            return (datetime.now(UTC) - created).total_seconds()
        except (ValueError, TypeError):
            return None

    # ── Watchlist (shared with sibling bot via the date dir) ─────────
    def write_watchlist(self, symbols: list) -> None:
        now_iso = datetime.now(UTC).isoformat()
        entries = [{"symbol": s, "subscribed_at": now_iso} for s in sorted(set(symbols))]
        _atomic_write_json(self.watchlist_path(), entries)

    def read_watchlist(self, date_str: Optional[str] = None) -> list:
        data = _read_json_safe(self.watchlist_path(date_str), [])
        return data if isinstance(data, list) else []

    # ── Open-trades (the trade-management state) ──────────────────────
    def write_open_trades(self, trades: list) -> None:
        # Validate before write — fail fast on missing fields rather than
        # silently writing an unrehydratable record.
        for t in trades:
            missing = OPEN_TRADE_REQUIRED_FIELDS_ENGINE - set(t.keys())
            if missing:
                raise ValueError(
                    f"EngineSession.write_open_trades: entry missing "
                    f"required fields: {sorted(missing)} "
                    f"(symbol={t.get('symbol')!r})"
                )
        with self._lock:
            _atomic_write_json(self.open_trades_path(), trades)

    def read_open_trades(self, date_str: Optional[str] = None) -> list:
        data = _read_json_safe(self.open_trades_path(date_str), [])
        if not isinstance(data, list):
            return []
        valid = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            missing = OPEN_TRADE_REQUIRED_FIELDS_ENGINE - set(entry.keys())
            if missing:
                print(f"[BOT] {now_iso_et()} {self.bot_id} dropping malformed "
                      f"open_trade entry: missing {sorted(missing)} "
                      f"sym={entry.get('symbol', '?')}", flush=True)
                continue
            valid.append(entry)
        return valid

    # ── Risk (daily counters + capped closed_trades) ─────────────────
    def write_risk(self, *, daily_pnl: float, daily_entries: int,
                   consecutive_losses: int, closed_trades: list) -> None:
        # Cap closed_trades at 50 like Setup A — diagnostic, not load-bearing.
        trimmed = closed_trades[-50:] if len(closed_trades) > 50 else closed_trades
        with self._lock:
            _atomic_write_json(self.risk_path(), {
                "daily_pnl": float(daily_pnl),
                "daily_entries": int(daily_entries),
                "consecutive_losses": int(consecutive_losses),
                "closed_trades": trimmed,
                "updated_at": datetime.now(UTC).isoformat(),
            })

    def read_risk(self, date_str: Optional[str] = None) -> dict:
        default = {
            "daily_pnl": 0.0, "daily_entries": 0, "consecutive_losses": 0,
            "closed_trades": [],
        }
        data = _read_json_safe(self.risk_path(date_str), default)
        if not isinstance(data, dict):
            return default
        return {
            "daily_pnl": float(data.get("daily_pnl", 0.0)),
            "daily_entries": int(data.get("daily_entries", 0)),
            "consecutive_losses": int(data.get("consecutive_losses", 0)),
            "closed_trades": data.get("closed_trades", []) or [],
        }

    # ── Scrub (for --fresh / --scrub CLI flags) ───────────────────────
    def scrub_today(self) -> None:
        """Wipe today's session_state_engine/<date>/ subtree. Does NOT
        touch tick_cache_engine — those are needed for backtest replay
        regardless of cold/resume boot."""
        import shutil
        shutil.rmtree(self._day_dir(), ignore_errors=True)


def decide_boot_mode(
    session: "EngineSession",
    fresh: bool = False,
    resume: bool = False,
) -> tuple[str, str]:
    """Decide cold vs resume for a given EngineSession. Returns
    (mode, reason) for logging.

    `mode` ∈ {"cold", "resume"}.

    Precedence (highest first):
      --fresh CLI flag   → always cold (and write a NEW marker)
      --resume CLI flag  → force resume if a marker exists, else cold
                            with reason "resume_no_marker"
      default            → resume if marker exists AND we have something
                            durable to resume from (open_trades/risk);
                            otherwise cold (avoids phantom-resume from an
                            empty marker left by a never-traded session).

    The Setup A pattern. Marker presence alone is not enough — Gap 4 in
    Setup A's resume design: a session that started but produced no
    durable state should cold-start cleanly rather than "phantom-resume".
    """
    if fresh:
        return "cold", "fresh_flag"
    if resume:
        if session.marker_exists():
            return "resume", "resume_flag"
        return "cold", "resume_no_marker"
    if not session.marker_exists():
        return "cold", "no_marker"

    # Auto-decide: only resume if we have something to resume from.
    open_trades_path = session.open_trades_path()
    risk_path = session.risk_path()
    has_open = (os.path.exists(open_trades_path)
                and os.path.getsize(open_trades_path) > 2)
    has_risk = (os.path.exists(risk_path)
                and os.path.getsize(risk_path) > 2)
    if not (has_open or has_risk):
        return "cold", "empty_state"
    return "resume", "marker_present"


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
    # wait_for_fill terminal-status enum
    "FILL_STATUS_FILLED",
    "FILL_STATUS_PARTIAL_THEN_TIMEOUT",
    "FILL_STATUS_REJECTED",
    "FILL_STATUS_CANCELLED",
    "FILL_STATUS_EXPIRED",
    "FILL_STATUS_REPLACED",
    "FILL_STATUS_TIMEOUT",
    "FILL_TERMINAL_NO_RETRY",
    # Session persistence (Phase 3)
    "EngineSession",
    "decide_boot_mode",
    "ENGINE_SESSION_ROOT",
]
