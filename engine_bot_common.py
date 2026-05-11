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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

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
    enough — the GIL covers the bool/int assignments we care about."""
    connected: bool = False         # socket open to engine
    ibkr_connected: bool = False    # engine's last reported ibkr state
    stream_paused: bool = True       # fail-CLOSED until first heartbeat
    last_heartbeat_ts: Optional[float] = None
    watchlist: list = None

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
    """
    try:
        for msg in read_frames_blocking(sock):
            if isinstance(msg, TickMessage):
                on_tick(msg)
            elif isinstance(msg, BarMessage):
                on_bar(msg)
            elif isinstance(msg, HeartbeatMessage):
                state.last_heartbeat_ts = time.monotonic()
                state.ibkr_connected = msg.ibkr_connected
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
