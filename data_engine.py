"""data_engine.py — Setup B unified data engine.

Phase 2 of DIRECTIVE_UNIFIED_DATA_ENGINE_BUILD.md. One process. Owns the
IBKR connection at clientId=3. Subscribes to reqMktData('233') for every
symbol on Setup A's watchlist. Broadcasts ticks + 1-minute bars + heartbeat
to thin strategy bots over a Unix socket.

Notes per the directive:
  - TBT is NEVER enabled in A/B period (WB_ENGINE_AB_PERIOD=1 enforces).
  - Watchlist is read from Setup A's session_state directory; engine is
    a pure data consumer of the scanner's output.
  - Engine writes a unified tick cache to tick_cache_engine/<date>/<sym>.json
    (separate from Setup A's tick_cache/ and tick_cache_alpaca/ so the
    A/B comparison stays clean).
  - Reconnect on disconnect with exponential backoff; after 5 minutes of
    failed reconnects, broadcast a final stream_paused and exit.

Threading model:
  - Main asyncio event loop runs ib_insync + the Unix socket server
    (asyncio.start_unix_server). ib_insync's pendingTickersEvent fires
    on the same loop, so tick handlers stay non-blocking.
  - One background thread for periodic tick-cache flush (mirrors Setup
    A's `_tick_flush_loop`). Disk I/O on the loop would stall the
    pendingTickersEvent stream during a flush — keep it off-loop.
  - Per-symbol bar builder is the shared `bars.TradeBarBuilder`; its
    on_bar_close callback runs synchronously inside the tick handler
    (cheap — no I/O).

This file is intentionally self-contained: it imports only `bars.py`,
`session_state.py` (read-only watchlist read), and `engine_ipc.py` from
the project tree. No detector code, no broker code.
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import math
import os
import queue
import signal
import sys
import threading
import time
import traceback
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# Make sure the repo root (where bars.py / session_state.py live in this
# worktree) is importable regardless of cwd.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from dotenv import load_dotenv

from bars import Bar, TradeBarBuilder
from engine_ipc import (
    BarMessage,
    HeartbeatMessage,
    HelloMessage,
    InterestMessage,
    QuoteMessage,
    StreamPausedMessage,
    StreamResumedMessage,
    SubscriptionsMessage,
    TickMessage,
    aread_frames,
    encode,
    DEFAULT_SOCKET_PATH,
)

# Load .env.engine.local first (gitignored secrets), then .env.engine
# (committed template), then .env (Setup A's detector knobs for inheritance).
load_dotenv(os.path.join(_HERE, ".env.engine.local"))
load_dotenv(os.path.join(_HERE, ".env.engine"))
load_dotenv(os.path.join(_HERE, ".env"))

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


# ══════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════

IBKR_HOST = os.getenv("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.getenv("IBKR_PORT", "4002"))
IBKR_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", "3"))
SOCKET_PATH = os.getenv("ENGINE_IPC_SOCKET", DEFAULT_SOCKET_PATH)

# A/B safety gate. The directive says TBT must be OFF during A/B. We
# refuse to do anything that would request a tick_by_tick subscription
# when this is 1 (the default). Setting to 0 in Phase 3 unlocks TBT.
AB_PERIOD = os.getenv("WB_ENGINE_AB_PERIOD", "1") == "1"

# Watchlist source: Setup A's session_state/<today>/watchlist.json — the
# directive pinned this exact path (read-only consumption of Setup A's
# scanner output). We re-poll it every WL_POLL_SEC so new scanner pushes
# show up without restarting the engine.
SETUP_A_ROOT = os.path.expanduser("~/warrior_bot_v2")
WL_POLL_SEC = int(os.getenv("ENGINE_WL_POLL_SEC", "10"))

# Tick cache dir — lives inside the engine worktree so we never write
# under ~/warrior_bot_v2/ (Setup A directory is read-only for us per
# directive). Default is <worktree>/tick_cache_engine/.
TICK_CACHE_DIR = os.getenv(
    "ENGINE_TICK_CACHE_DIR",
    os.path.join(_HERE, "tick_cache_engine"),
)
TICK_FLUSH_SEC = int(os.getenv("ENGINE_TICK_FLUSH_SEC", "30"))

# Seed cache dir — READ-ONLY consumption of Setup A's tick_cache so the
# engine can replay today's ticks through bar_builder at boot. This
# populates VWAP/HOD on the engine side AND broadcasts BarMessages to
# all connected bots, which is the load-bearing fix for squeeze_bot
# detector starvation (it needs accumulated avg_vol to compute vol_ratio,
# which lives-only would never have at boot). Setup A's cache is the
# most complete (subscribed since 04:00 ET + morning ibkr_tick_fetcher
# refetches), so we inherit its seed data directly.
SEED_TICK_CACHE_DIR = os.getenv(
    "ENGINE_SEED_TICK_CACHE_DIR",
    os.path.join(SETUP_A_ROOT, "tick_cache"),
)

# Heartbeat cadence.
HEARTBEAT_SEC = 5

# Reconnect policy. Capped at 30s between attempts; total budget 5 min
# (10 attempts roughly) before we give up and exit so cron/manual can
# decide whether to restart the engine.
RECONNECT_BACKOFF = [1, 2, 4, 8, 16, 30, 30, 30, 30, 30]
RECONNECT_TOTAL_BUDGET_SEC = 5 * 60

# Alpaca quote stream — parallel feed for cross-feed-aware limit pricing.
# See QuoteMessage docstring and the 2026-05-11 ODYS/TRAW live losses.
ALPACA_QUOTE_FEED = os.getenv("ENGINE_ALPACA_QUOTE_FEED", "iex").lower()
# Capped per-drain pull from the cross-thread queue so the asyncio loop
# never stalls under a quote-rate burst (premarket runners can fire 1K+
# quotes/sec on hot tickers).
ALPACA_QUOTE_DRAIN_BATCH = 2000


def _alpaca_creds_present() -> tuple[bool, str, str]:
    """Returns (ok, key, secret). ok=False if either is empty or looks like
    the .env.engine template sentinel — engine logs a DISABLED line and
    skips starting the stream in that case."""
    key = (os.getenv("APCA_API_KEY_ID") or "").strip()
    secret = (os.getenv("APCA_API_SECRET_KEY") or "").strip()
    if not key or not secret:
        return False, key, secret
    if "<" in key or "<" in secret or "FILL" in key.upper():
        return False, key, secret
    return True, key, secret


def now_et() -> datetime:
    return datetime.now(ET)


def now_iso_et() -> str:
    return now_et().isoformat()


def today_et_str() -> str:
    return now_et().strftime("%Y-%m-%d")


# ══════════════════════════════════════════════════════════════════════
# Alpaca quote stream — parallel feed
# ══════════════════════════════════════════════════════════════════════


class AlpacaQuoteStream:
    """Subscribes to Alpaca's quote websocket in parallel with IBKR ticks.

    Threading model:
      - alpaca-py's StockDataStream.run() owns its own asyncio loop and
        must run in its own thread (it calls asyncio.run() internally).
        We start it in a daemon thread named "alpaca-quote-stream".
      - The async `_on_quote` callback fires on the stream's loop. It
        is a synchronous-from-asyncio handoff: we push a tuple onto a
        thread-safe `queue.Queue` (NOT asyncio.Queue, since the consumer
        runs on the engine's loop, not the stream's).
      - The engine's asyncio loop runs a `consumer_loop()` coroutine that
        drains the queue in batches and calls back into the engine to
        broadcast QuoteMessage frames + update health counters.

    This mirrors `alpaca_feed.py`'s queue-bridge pattern — the same
    proven plumbing Setup A uses for live trades.

    Reconnect behavior: alpaca-py's StockDataStream auto-reconnects with
    exponential backoff internally. We track liveness via the timestamp
    of the most recent quote we've received. If we go > QUOTE_LIVENESS_S
    without any quote, we flag `connected=False` for heartbeat reporting
    even if the WS object hasn't told us it's dead. This catches the
    "WS hung but never errored" pathology Manny has seen on Alpaca's
    free tier before.
    """

    # Heuristic liveness: if no quote in 30s during market hours, declare
    # the stream stale. Engines run before-open + after-close; we don't
    # use this as a hard fail, just a heartbeat-health signal.
    QUOTE_LIVENESS_S = 30

    def __init__(self, api_key: str, api_secret: str, feed: str,
                 broadcast_fn, get_main_loop_fn,
                 quote_seq_fn, on_quote_received_fn):
        """
        broadcast_fn(QuoteMessage)        — called from engine loop to push
                                             to all IPC clients
        get_main_loop_fn() -> asyncio loop — returns the engine's loop
                                             (used to schedule the consumer
                                             coroutine via call_soon_threadsafe)
        quote_seq_fn(symbol) -> int       — next sequence number for symbol
        on_quote_received_fn(symbol, ts_utc) — health bookkeeping (called
                                             from the engine loop)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.feed = feed
        self.broadcast_fn = broadcast_fn
        self.get_main_loop_fn = get_main_loop_fn
        self.quote_seq_fn = quote_seq_fn
        self.on_quote_received_fn = on_quote_received_fn

        self._stream = None              # alpaca-py StockDataStream
        self._stream_thread: Optional[threading.Thread] = None
        self._subscribed: set[str] = set()
        self._sub_lock = threading.Lock()
        self._stop = threading.Event()
        self._consumer_task: Optional[asyncio.Task] = None

        # Cross-thread bridge — stream callback (background thread) → engine
        # loop (main asyncio loop). Large but bounded; we drop-oldest on
        # full like the IPC slow-consumer policy.
        self._quote_queue: "queue.Queue[tuple]" = queue.Queue(maxsize=50_000)

        # Liveness tracking — last successful quote receipt monotonic ts.
        self._last_quote_mono: float = 0.0
        self._connected: bool = False    # True after stream thread reports ready
        self._dropped: int = 0

    # ── Public surface used by DataEngine ─────────────────────────────

    @property
    def connected(self) -> bool:
        """Heartbeat-grade liveness flag. False if we haven't seen a
        quote in QUOTE_LIVENESS_S and never received one (pre-market)
        is also False — bots interpret False as "fall back to IBKR-only
        pricing"."""
        if not self._connected:
            return False
        # If we've never received a quote, _last_quote_mono == 0 and we
        # report False — bots should not trust an unproven stream.
        if self._last_quote_mono == 0.0:
            return False
        age = time.monotonic() - self._last_quote_mono
        return age <= self.QUOTE_LIVENESS_S

    @property
    def dropped(self) -> int:
        return self._dropped

    def start(self, main_loop: asyncio.AbstractEventLoop):
        """Start the stream thread + the engine-loop consumer task.

        Idempotent: a second call is a no-op."""
        if self._stream_thread is not None and self._stream_thread.is_alive():
            return
        # Build the alpaca-py stream object on the calling (main) thread;
        # actual run() happens in the spawned thread.
        from alpaca.data.live import StockDataStream
        from alpaca.data.enums import DataFeed
        try:
            df = DataFeed(self.feed)
        except ValueError:
            df = DataFeed.IEX
        self._stream = StockDataStream(self.api_key, self.api_secret, feed=df)

        # Start the consumer first so any racing quotes that land during
        # subscribe have somewhere to be drained to.
        self._consumer_task = asyncio.create_task(self._consumer_loop())

        # Spawn the WS thread.
        self._stream_thread = threading.Thread(
            target=self._run_stream, name="alpaca-quote-stream", daemon=True,
        )
        self._stream_thread.start()
        self._connected = True
        print(f"[ENGINE] {now_iso_et()} Alpaca quote stream started "
              f"(feed={self.feed})", flush=True)

    def stop(self):
        """Tear down: stop the WS thread + cancel the consumer."""
        self._stop.set()
        try:
            if self._stream is not None:
                self._stream.stop()
        except Exception:
            pass
        if self._consumer_task is not None:
            try:
                self._consumer_task.cancel()
            except Exception:
                pass
        # Don't join the thread on the loop — alpaca-py's run() may take
        # a moment to unwind. Daemon thread will exit at process end.
        self._connected = False

    def subscribe(self, symbols: list[str]):
        """Add the given symbols to the live subscription set. Safe to
        call from any thread (the alpaca-py call is internally
        thread-safe — same pattern alpaca_feed.py uses)."""
        if not symbols or self._stream is None:
            return
        with self._sub_lock:
            new = [s for s in symbols if s not in self._subscribed]
            if not new:
                return
            try:
                # subscribe_quotes accepts varargs of symbols. Call once per
                # batch so a watchlist push of N symbols is one WS frame.
                self._stream.subscribe_quotes(self._on_quote, *new)
                self._subscribed.update(new)
                print(f"[ENGINE] {now_iso_et()} Alpaca quote sub: "
                      f"{','.join(sorted(new))}", flush=True)
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} Alpaca quote subscribe error: {e!r}",
                      flush=True)

    def unsubscribe(self, symbols: list[str]):
        if not symbols or self._stream is None:
            return
        with self._sub_lock:
            drop = [s for s in symbols if s in self._subscribed]
            if not drop:
                return
            try:
                self._stream.unsubscribe_quotes(*drop)
                self._subscribed.difference_update(drop)
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} Alpaca quote unsub error: {e!r}",
                      flush=True)

    # ── Stream thread entry ───────────────────────────────────────────

    def _run_stream(self):
        """Stream-thread target. alpaca-py's run() blocks until stop()."""
        while not self._stop.is_set():
            try:
                # alpaca-py StockDataStream.run() calls asyncio.run() inside
                # this thread, owning its own event loop. Returns on stop().
                self._stream.run()
                if self._stop.is_set():
                    return
                # If run() returned without a stop() (e.g. WS exited on
                # error), pause briefly and let alpaca-py reconnect on
                # the next iteration.
                print(f"[ENGINE] {now_iso_et()} Alpaca quote stream run() "
                      f"returned unexpectedly — restarting in 2s", flush=True)
                time.sleep(2.0)
            except Exception as e:
                if self._stop.is_set():
                    return
                print(f"[ENGINE] {now_iso_et()} Alpaca quote stream crashed: "
                      f"{e!r} — restarting in 5s", flush=True)
                traceback.print_exc()
                time.sleep(5.0)

    async def _on_quote(self, quote):
        """alpaca-py callback. Runs on the stream's asyncio loop (background
        thread). MUST NOT touch the engine's loop directly — push to the
        cross-thread queue and let the consumer dispatch on the engine
        loop. Keep this fast."""
        try:
            symbol = getattr(quote, "symbol", "") or ""
            bid = float(getattr(quote, "bid_price", 0) or 0)
            ask = float(getattr(quote, "ask_price", 0) or 0)
            bid_sz = int(getattr(quote, "bid_size", 0) or 0)
            ask_sz = int(getattr(quote, "ask_size", 0) or 0)
            ts = getattr(quote, "timestamp", None)
            if not symbol:
                return
            # Skip degenerate or NaN quotes — wide-spread or one-side-only
            # zero quotes happen at the open and right after halts.
            if bid <= 0 and ask <= 0:
                return
            if math.isnan(bid) or math.isnan(ask):
                return
            if ts is None:
                ts = datetime.now(UTC)
            elif getattr(ts, "tzinfo", None) is None:
                ts = ts.replace(tzinfo=UTC)
            try:
                self._quote_queue.put_nowait((symbol, bid, ask, bid_sz, ask_sz, ts))
            except queue.Full:
                # Drop oldest, then enqueue new. We do this on the stream
                # thread (not main loop) so the consumer never blocks.
                try:
                    self._quote_queue.get_nowait()
                except queue.Empty:
                    pass
                self._dropped += 1
                if self._dropped in (1, 100, 1000):
                    print(f"[ENGINE] {now_iso_et()} Alpaca quote queue full — "
                          f"dropped {self._dropped} (consumer falling behind)",
                          flush=True)
                try:
                    self._quote_queue.put_nowait((symbol, bid, ask, bid_sz, ask_sz, ts))
                except queue.Full:
                    pass
        except Exception as e:
            print(f"[ENGINE] {now_iso_et()} Alpaca _on_quote error: {e!r}",
                  flush=True)

    # ── Engine-loop consumer ──────────────────────────────────────────

    async def _consumer_loop(self):
        """Drains _quote_queue on the engine's asyncio loop. Each drained
        quote is converted to a QuoteMessage and broadcast. Sleeps a few
        ms between drains so we don't starve the IBKR tick stream."""
        try:
            while not self._stop.is_set():
                # Drain up to ALPACA_QUOTE_DRAIN_BATCH per cycle to bound
                # one-iteration work. queue.Queue.get_nowait is fine in
                # an asyncio context as long as we yield each cycle.
                drained = 0
                for _ in range(ALPACA_QUOTE_DRAIN_BATCH):
                    try:
                        symbol, bid, ask, bid_sz, ask_sz, ts_utc = \
                            self._quote_queue.get_nowait()
                    except queue.Empty:
                        break
                    drained += 1
                    ts_iso = ts_utc.astimezone(ET).isoformat()
                    seq = self.quote_seq_fn(symbol)
                    msg = QuoteMessage(
                        symbol=symbol, ts=ts_iso, bid=bid, ask=ask,
                        bid_size=bid_sz, ask_size=ask_sz, feed=self.feed,
                        engine_seq=seq,
                    )
                    try:
                        self.broadcast_fn(msg)
                    except Exception as e:
                        print(f"[ENGINE] {now_iso_et()} quote broadcast "
                              f"error: {e!r}", flush=True)
                    try:
                        self.on_quote_received_fn(symbol, ts_utc)
                    except Exception:
                        pass
                    # Stamp liveness here (not in the WS callback) since
                    # the WS thread may have queue-dropped before drain.
                    self._last_quote_mono = time.monotonic()
                # Pace the drain: if nothing pending, sleep longer; if we
                # drained the full batch, yield briefly to let other tasks
                # run before the next drain.
                if drained == 0:
                    await asyncio.sleep(0.05)
                else:
                    await asyncio.sleep(0.002)
        except asyncio.CancelledError:
            return
        except Exception as e:
            print(f"[ENGINE] {now_iso_et()} Alpaca consumer loop crashed: "
                  f"{e!r}", flush=True)


# ══════════════════════════════════════════════════════════════════════
# Per-client connection state
# ══════════════════════════════════════════════════════════════════════


class _Client:
    """One connected strategy bot."""

    def __init__(self, writer: asyncio.StreamWriter):
        self.writer = writer
        self.bot_id: str = "unknown"
        self.connected_at: float = time.monotonic()
        self.dropped_msgs: int = 0
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self.send_task: Optional[asyncio.Task] = None

    def peer_label(self) -> str:
        return f"{self.bot_id}#{id(self) & 0xFFFF:04x}"


# ══════════════════════════════════════════════════════════════════════
# Engine
# ══════════════════════════════════════════════════════════════════════


class DataEngine:
    """The daemon. One instance per process."""

    def __init__(self):
        # Imported lazily so a smoke-test `import data_engine` works
        # without ib_insync being importable on the dev box.
        from ib_insync import IB
        self.ib = IB()

        self.clients: set[_Client] = set()
        self.watchlist: set[str] = set()
        self.contracts: dict = {}
        self.tickers: dict = {}

        # Per-symbol monotonic sequence number (resets on engine restart).
        # `seq` is shared by ticks + bars (interleaved per-symbol ordering).
        # `quote_seq` is separate per the QuoteMessage contract — bots
        # treat tick and quote streams independently.
        self.seq: dict[str, int] = defaultdict(int)
        self.quote_seq: dict[str, int] = defaultdict(int)

        # Per-symbol Alpaca quote bookkeeping for heartbeat staleness.
        # Stamped on every successful quote consume; oldest age is reported
        # by _heartbeat_loop.
        self._last_quote_mono_by_symbol: dict[str, float] = {}
        # Rolling 5s window of quote counts (mirrors _rate_window for ticks).
        self._quote_rate_window: deque = deque()

        # Alpaca quote stream (lazy — only built if creds are present).
        self.alpaca_quote_stream: Optional[AlpacaQuoteStream] = None

        # Bar builder — 1-minute bars from ticks. on_bar_close emits a
        # BarMessage. Same TradeBarBuilder Setup A uses, so our session
        # VWAP / HOD math is byte-identical.
        self.bar_builder = TradeBarBuilder(self._on_bar_close, ET, interval_seconds=60)

        # Tick cache buffer — flushed every TICK_FLUSH_SEC by a worker
        # thread. Same structure as Setup A's tick_buffer for diff-friendly
        # cache reads.
        self._tick_buffer: dict[str, list] = defaultdict(list)
        self._tick_buffer_lock = threading.Lock()
        self._flush_thread: Optional[threading.Thread] = None
        self._flush_stop = threading.Event()

        # Rolling tick-rate window — last 5s of tick counts for heartbeat.
        # deque of (monotonic_ts, count) entries.
        self._rate_window: deque = deque()

        self.ibkr_connected: bool = False
        self.started_at: float = time.monotonic()
        self.shutdown_event: Optional[asyncio.Event] = None
        self._reconnect_in_progress: bool = False
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    # ── lifecycle ─────────────────────────────────────────────────────

    async def run(self):
        """Top-level entry. Returns on shutdown signal."""
        self.shutdown_event = asyncio.Event()
        self._main_loop = asyncio.get_running_loop()

        # Set up the Unix socket server first so a bot connecting before
        # IBKR is up still gets the connection accepted (it'll receive
        # the initial stream_paused if IBKR isn't ready yet).
        try:
            os.unlink(SOCKET_PATH)
        except FileNotFoundError:
            pass
        server = await asyncio.start_unix_server(
            self._handle_client, path=SOCKET_PATH,
        )
        os.chmod(SOCKET_PATH, 0o660)

        self._print_banner()

        # Hook ib_insync events. errorEvent is verbose but the only place
        # we see TBT-quota rejections (10190) if AB safety lets us
        # accidentally request TBT — useful guard rail.
        self.ib.disconnectedEvent += self._on_ibkr_disconnect
        self.ib.errorEvent += self._on_ibkr_error
        self.ib.pendingTickersEvent += self._on_tickers

        # Start the periodic tasks.
        hb_task = asyncio.create_task(self._heartbeat_loop())
        wl_task = asyncio.create_task(self._watchlist_loop())
        self._start_flush_thread()

        # Bring up the Alpaca quote stream (independent of IBKR). If creds
        # are missing or template sentinels, we log DISABLED and continue
        # — the bots fall back to IBKR-only pricing via get_priced_limit().
        self._start_alpaca_quote_stream()

        # Initial IBKR connect.
        await self._ensure_ibkr_connected()

        try:
            await self.shutdown_event.wait()
        finally:
            print(f"[ENGINE] {now_iso_et()} shutdown initiated", flush=True)
            hb_task.cancel()
            wl_task.cancel()
            try:
                await asyncio.gather(hb_task, wl_task, return_exceptions=True)
            except Exception:
                pass
            await self._broadcast(StreamPausedMessage(
                reason="engine_shutdown", since=now_iso_et(),
            ))
            # Close client sockets.
            for c in list(self.clients):
                try:
                    c.writer.close()
                except Exception:
                    pass
            server.close()
            try:
                await server.wait_closed()
            except Exception:
                pass
            # Tear down the Alpaca quote stream before flushing — its
            # consumer task references the broadcast path we're closing.
            if self.alpaca_quote_stream is not None:
                try:
                    self.alpaca_quote_stream.stop()
                except Exception as e:
                    print(f"[ENGINE] {now_iso_et()} Alpaca stream stop "
                          f"error: {e!r}", flush=True)
            self._flush_stop.set()
            if self._flush_thread is not None:
                self._flush_thread.join(timeout=5)
            # Final cache flush so we don't lose the last <30s of ticks.
            self._flush_tick_cache()
            try:
                if self.ib.isConnected():
                    self.ib.disconnect()
            except Exception:
                pass
            try:
                os.unlink(SOCKET_PATH)
            except FileNotFoundError:
                pass
            print(f"[ENGINE] {now_iso_et()} shutdown complete", flush=True)

    def request_shutdown(self):
        """Idempotent shutdown trigger. Safe from signal handlers."""
        if self.shutdown_event and not self.shutdown_event.is_set():
            self.shutdown_event.set()

    def _start_alpaca_quote_stream(self):
        """Bring up the Alpaca quote stream if creds are present. Hooks into
        the engine's broadcast + sequence-numbering + health bookkeeping."""
        ok, key, _ = _alpaca_creds_present()
        if not ok:
            print(f"[ENGINE] {now_iso_et()} Alpaca quote stream DISABLED — "
                  f"credentials not set in .env.engine (APCA_API_KEY_ID / "
                  f"APCA_API_SECRET_KEY missing or template sentinel). "
                  f"Bots will fall back to IBKR-only pricing.", flush=True)
            return
        _, key, secret = _alpaca_creds_present()
        try:
            self.alpaca_quote_stream = AlpacaQuoteStream(
                api_key=key,
                api_secret=secret,
                feed=ALPACA_QUOTE_FEED,
                broadcast_fn=self._broadcast_nowait,
                get_main_loop_fn=lambda: self._main_loop,
                quote_seq_fn=self._next_quote_seq,
                on_quote_received_fn=self._on_quote_received,
            )
            self.alpaca_quote_stream.start(self._main_loop)
            # Pre-subscribe whatever's already in the watchlist (e.g. the
            # engine was restarted mid-session).
            if self.watchlist:
                self.alpaca_quote_stream.subscribe(sorted(self.watchlist))
        except Exception as e:
            print(f"[ENGINE] {now_iso_et()} Alpaca quote stream init failed: "
                  f"{e!r} — continuing without it", flush=True)
            traceback.print_exc()
            self.alpaca_quote_stream = None

    def _next_quote_seq(self, symbol: str) -> int:
        """Allocate next per-symbol quote sequence number. Called from the
        engine loop (consumer coroutine) — safe to mutate dict here."""
        self.quote_seq[symbol] += 1
        return self.quote_seq[symbol]

    def _on_quote_received(self, symbol: str, ts_utc: datetime):
        """Per-quote bookkeeping for heartbeat health. Engine-loop only."""
        self._last_quote_mono_by_symbol[symbol] = time.monotonic()
        self._quote_rate_window.append((time.monotonic(), 1))

    def _print_banner(self):
        print("=" * 72, flush=True)
        print(f"[ENGINE] {now_iso_et()} Setup B Unified Data Engine starting", flush=True)
        print(f"[ENGINE]   IBKR target:    {IBKR_HOST}:{IBKR_PORT} clientId={IBKR_CLIENT_ID}", flush=True)
        print(f"[ENGINE]   IPC socket:     {SOCKET_PATH}", flush=True)
        print(f"[ENGINE]   A/B safety:     WB_ENGINE_AB_PERIOD={'1 (TBT disabled)' if AB_PERIOD else '0 (TBT allowed)'}", flush=True)
        print(f"[ENGINE]   Tick cache:     {TICK_CACHE_DIR}", flush=True)
        print(f"[ENGINE]   Watchlist src:  {self._watchlist_path()}", flush=True)
        print(f"[ENGINE]   Tier 1 (TBT):   0 slots used (A/B period — no TBT)" if AB_PERIOD
              else "[ENGINE]   Tier 1 (TBT):   not implemented yet (Phase 3)", flush=True)
        ok, _, _ = _alpaca_creds_present()
        if ok:
            print(f"[ENGINE]   Alpaca quotes:  ENABLED (feed={ALPACA_QUOTE_FEED})", flush=True)
        else:
            print(f"[ENGINE]   Alpaca quotes:  DISABLED (no creds in .env.engine)",
                  flush=True)
        print("=" * 72, flush=True)

    # ── IBKR ──────────────────────────────────────────────────────────

    async def _ensure_ibkr_connected(self):
        """Connect to IBKR with exponential backoff. Broadcasts
        stream_paused / stream_resumed at the transitions. Returns True
        on success, False after the 5-minute budget is exhausted (in
        which case the engine schedules itself for shutdown)."""
        if self._reconnect_in_progress:
            return self.ibkr_connected
        self._reconnect_in_progress = True
        start = time.monotonic()
        attempts = 0
        was_connected = self.ibkr_connected
        if was_connected:
            await self._broadcast(StreamPausedMessage(
                reason="ibkr_disconnect", since=now_iso_et(),
            ))
            self.ibkr_connected = False
        try:
            while not self.shutdown_event.is_set():
                backoff = RECONNECT_BACKOFF[min(attempts, len(RECONNECT_BACKOFF) - 1)]
                try:
                    print(f"[ENGINE] {now_iso_et()} connecting IBKR "
                          f"(attempt {attempts + 1}, after {time.monotonic() - start:.0f}s)…",
                          flush=True)
                    await self.ib.connectAsync(IBKR_HOST, IBKR_PORT,
                                               clientId=IBKR_CLIENT_ID, timeout=20)
                    self.ibkr_connected = True
                    print(f"[ENGINE] {now_iso_et()} IBKR connected "
                          f"(accounts: {self.ib.managedAccounts()})", flush=True)
                    # Re-subscribe everything currently in watchlist.
                    await self._resubscribe_all()
                    if was_connected:
                        await self._broadcast(StreamResumedMessage(ts=now_iso_et()))
                    return True
                except Exception as e:
                    print(f"[ENGINE] {now_iso_et()} IBKR connect failed: {e!r} — "
                          f"sleeping {backoff}s", flush=True)
                attempts += 1
                if time.monotonic() - start > RECONNECT_TOTAL_BUDGET_SEC:
                    print(f"[ENGINE] {now_iso_et()} IBKR reconnect budget exhausted "
                          f"({RECONNECT_TOTAL_BUDGET_SEC}s) — shutting down engine",
                          flush=True)
                    await self._broadcast(StreamPausedMessage(
                        reason="reconnect_exhausted", since=now_iso_et(),
                    ))
                    self.request_shutdown()
                    return False
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=backoff)
                    # Shutdown won the race.
                    return False
                except asyncio.TimeoutError:
                    pass
        finally:
            self._reconnect_in_progress = False
        return self.ibkr_connected

    def _on_ibkr_disconnect(self):
        if not self.ibkr_connected:
            return
        print(f"[ENGINE] {now_iso_et()} IBKR disconnected (event)", flush=True)
        self.ibkr_connected = False
        if self._main_loop is not None:
            self._main_loop.call_soon_threadsafe(
                asyncio.create_task, self._ensure_ibkr_connected()
            )

    def _on_ibkr_error(self, reqId, errorCode, errorString, contract=None):
        # 10190 = "Max number of tick-by-tick requests" — the TBT cap.
        # Should not happen during A/B (we never request TBT), but if it
        # does we want a loud alert because the safety gate failed.
        if errorCode == 10190 and AB_PERIOD:
            sym = getattr(contract, "symbol", "?") if contract else "?"
            print(f"[ENGINE] {now_iso_et()} !! UNEXPECTED 10190 during A/B "
                  f"(reqId={reqId} sym={sym}) — TBT was requested but AB gate is on. "
                  f"This is a bug.", flush=True)

    async def _resubscribe_all(self):
        """After (re)connect, requalify + reqMktData every watchlist symbol."""
        from ib_insync import Stock
        for sym in sorted(self.watchlist):
            try:
                c = Stock(sym, "SMART", "USD")
                # qualifyContractsAsync avoids the nested ib.run() trap that
                # bites the bot when called from inside a tick handler.
                qualified = await self.ib.qualifyContractsAsync(c)
                if not qualified:
                    print(f"[ENGINE] {now_iso_et()} resub: qualify failed for {sym}",
                          flush=True)
                    continue
                self.contracts[sym] = qualified[0]
                tk = self.ib.reqMktData(qualified[0], "233", False, False)
                self.tickers[sym] = tk
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} resub error {sym}: {e!r}", flush=True)
        # IBKR reconnect doesn't affect the Alpaca stream (independent
        # transport), but the watchlist could have grown while we were
        # disconnected. Re-push the full set; AlpacaQuoteStream dedups
        # against _subscribed internally.
        if self.alpaca_quote_stream is not None and self.watchlist:
            try:
                self.alpaca_quote_stream.subscribe(sorted(self.watchlist))
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} Alpaca quote resub error: {e!r}",
                      flush=True)

    # ── Watchlist ─────────────────────────────────────────────────────

    def _watchlist_path(self) -> str:
        """Setup A's session_state/<today>/watchlist.json."""
        return os.path.join(
            SETUP_A_ROOT, "session_state", today_et_str(), "watchlist.json",
        )

    def _read_watchlist(self) -> list[str]:
        """Return the sorted list of symbols Setup A has subscribed for
        today's session. Returns [] on any failure — caller treats that
        as 'nothing to do yet, scanner hasn't run'."""
        path = self._watchlist_path()
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, list):
            return []
        syms = []
        for entry in data:
            if isinstance(entry, dict):
                s = entry.get("symbol")
            elif isinstance(entry, str):
                s = entry
            else:
                continue
            if isinstance(s, str) and s.isalpha() and 1 <= len(s) <= 5:
                syms.append(s.upper())
        return sorted(set(syms))

    async def _watchlist_loop(self):
        """Poll Setup A's watchlist.json every WL_POLL_SEC; subscribe new
        symbols. Never unsubscribe (Setup A doesn't either; persistence
        across the session is a feature)."""
        while not self.shutdown_event.is_set():
            try:
                if self.ibkr_connected:
                    new = set(self._read_watchlist())
                    added = new - self.watchlist
                    if added:
                        await self._subscribe_new(sorted(added))
                        self.watchlist |= added
                        await self._broadcast_subscriptions()
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} watchlist loop error: {e!r}", flush=True)
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=WL_POLL_SEC)
                return
            except asyncio.TimeoutError:
                pass

    async def _subscribe_new(self, symbols: list[str]):
        from ib_insync import Stock
        for sym in symbols:
            try:
                # SEED FIRST. Replay today's cached ticks through the
                # engine's bar_builder before any live tick arrives so
                # downstream detectors (squeeze_bot in particular) get
                # the full historical bar stream and accumulate avg_vol
                # baselines. Each bar close fires the normal
                # _on_bar_close → BarMessage broadcast path, so connected
                # bots see seed bars indistinguishably from live bars.
                #
                # This MUST run before reqMktData so live ticks layer on
                # top of an already-populated bar_builder for this symbol
                # (and so the first live bar's open/high/low/close/volume
                # flow naturally from where the seed left off).
                try:
                    self._seed_symbol_from_cache(sym)
                except Exception as e:
                    print(f"[ENGINE] {now_iso_et()} seed exception {sym}: "
                          f"{e!r} — continuing to live subscribe", flush=True)
                c = Stock(sym, "SMART", "USD")
                qualified = await self.ib.qualifyContractsAsync(c)
                if not qualified:
                    print(f"[ENGINE] {now_iso_et()} qualify failed: {sym}", flush=True)
                    continue
                self.contracts[sym] = qualified[0]
                # reqMktData('233') = generic ticks for RTVolume / aggregated trade
                # ticks every ~250ms. NO TBT during A/B (per directive).
                tk = self.ib.reqMktData(qualified[0], "233", False, False)
                self.tickers[sym] = tk
                print(f"[ENGINE] {now_iso_et()} subscribed {sym} (snapshot)", flush=True)
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} subscribe {sym} failed: {e!r}", flush=True)
        # Mirror the new symbols into the Alpaca quote stream so bots get
        # bid/ask updates for the same set. Subscribe in one batch (one WS
        # frame) — alpaca-py handles the broadcast internally.
        if self.alpaca_quote_stream is not None:
            try:
                self.alpaca_quote_stream.subscribe(symbols)
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} Alpaca quote sub error: {e!r}",
                      flush=True)

    async def _broadcast_subscriptions(self):
        msg = SubscriptionsMessage(
            watchlist=sorted(self.watchlist),
            tier1=[],                      # always empty during A/B
            tier2=sorted(self.watchlist),
            policy_owner="engine_ab" if AB_PERIOD else "engine",
        )
        await self._broadcast(msg)

    # ── Tick handling ─────────────────────────────────────────────────

    def _on_tickers(self, tickers):
        """ib_insync pendingTickersEvent — fires every ~250ms with the
        set of tickers that changed since the last cycle. We extract the
        trade price/size and broadcast a TickMessage per print.

        During A/B we never call reqTickByTickData, so `ticker.tickByTicks`
        is always empty here — the snapshot path is all we touch.
        """
        import math
        now_utc = datetime.now(UTC)
        now_e = now_utc.astimezone(ET)
        ticks_this_cycle = 0
        for ticker in tickers:
            contract = getattr(ticker, "contract", None)
            if not contract:
                continue
            sym = contract.symbol
            last = getattr(ticker, "last", None)
            if last is None or (isinstance(last, float) and math.isnan(last)) or last <= 0:
                continue
            # Trade size: ib_insync exposes the most recent print size on
            # `lastSize`. Default to 0 if absent (some midpoints arrive
            # without a size — those still count as a price update but
            # we skip them in the bar builder downstream).
            last_size_attr = getattr(ticker, "lastSize", 0)
            try:
                size = int(last_size_attr) if last_size_attr and not (
                    isinstance(last_size_attr, float) and math.isnan(last_size_attr)
                ) else 0
            except (TypeError, ValueError):
                size = 0
            if size <= 0:
                # Setup A's _process_ticker also skips zero-size updates
                # from going into the bar builder (only health-monitor
                # used them). We mirror that behavior so the bar/VWAP
                # series matches Setup A bar-for-bar on the same prints.
                continue

            price = float(last)
            self.seq[sym] += 1

            # Feed the engine's own bar builder. The on_bar_close
            # callback will broadcast BarMessage on bucket close.
            try:
                self.bar_builder.on_trade(sym, price, size, now_utc)
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} bar_builder error {sym}: {e!r}",
                      flush=True)

            # Append to cache buffer (background thread flushes to disk).
            with self._tick_buffer_lock:
                self._tick_buffer[sym].append({
                    "p": price, "s": size, "t": now_utc.isoformat(),
                })

            # Broadcast the tick.
            msg = TickMessage(
                symbol=sym,
                ts=now_e.isoformat(),
                price=price,
                size=size,
                engine_seq=self.seq[sym],
                exchange=getattr(contract, "primaryExchange", None) or None,
                tier="snapshot",
            )
            self._broadcast_nowait(msg)
            ticks_this_cycle += 1

        if ticks_this_cycle:
            self._rate_window.append((time.monotonic(), ticks_this_cycle))

    def _seed_symbol_from_cache(self, symbol: str) -> int:
        """Replay today's cached ticks through bar_builder before live
        subscription starts. The resulting bar closes broadcast as normal
        BarMessages to all connected clients, populating their detectors
        with the accumulated avg_vol / VWAP / HOD baselines they need
        (the squeeze detector's PRIME criterion is vol_ratio against
        rolling avg_vol — without a seed it never primes).

        Cache source: Setup A's tick_cache/<today>/<sym>.json.gz (the
        most complete cache on the box — Setup A has been subscribed
        since 04:00 ET and `ibkr_tick_fetcher` morning refetches feed
        this same directory). Reading is best-effort: missing file =
        skip (live ticks will build a baseline from now), corrupt file
        = log + skip.

        Returns the number of ticks replayed (0 on skip/error). The
        engine's own tick_cache_engine/ is not touched here — that
        directory is the engine's own observation record, kept separate
        from the seed source for A/B comparison cleanliness.
        """
        today = today_et_str()
        cache_path = os.path.join(
            SEED_TICK_CACHE_DIR, today, f"{symbol}.json.gz",
        )
        if not os.path.exists(cache_path):
            print(f"[ENGINE] {now_iso_et()} seed: no cache for {symbol} "
                  f"at {cache_path} — skipping (live ticks will build baseline)",
                  flush=True)
            return 0
        try:
            with gzip.open(cache_path, "rt") as f:
                ticks = json.load(f)
        except (OSError, json.JSONDecodeError, gzip.BadGzipFile) as e:
            print(f"[ENGINE] {now_iso_et()} seed: cache read error for "
                  f"{symbol}: {e!r} — skipping", flush=True)
            return 0
        if not isinstance(ticks, list) or not ticks:
            return 0

        replayed = 0
        skipped = 0
        for t in ticks:
            try:
                price = float(t.get("p") or t.get("price") or 0)
                size = int(t.get("s") or t.get("size") or 0)
                ts_str = t.get("t") or t.get("ts") or t.get("time")
                if price <= 0 or size <= 0 or not ts_str:
                    skipped += 1
                    continue
                # Cache writes UTC ISO with offset (+00:00); fromisoformat
                # in 3.11+ handles 'Z' suffix too, normalize defensively.
                if isinstance(ts_str, str):
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                else:
                    skipped += 1
                    continue
                # bar_builder.on_trade expects tz-aware ts — guarantee UTC.
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                # Allocate seq BEFORE on_trade so BarMessage emissions
                # during seed pull from the per-symbol counter the same
                # way live ticks would. Bars from seed share the symbol's
                # sequence stream (interleaved monotonic) — bots can
                # process them identically to live bars.
                self.bar_builder.on_trade(symbol, price, size, ts)
                replayed += 1
            except (TypeError, ValueError) as e:
                skipped += 1
                if skipped <= 3:
                    print(f"[ENGINE] {now_iso_et()} seed: bad tick {symbol}: "
                          f"{e!r} (t={t!r})", flush=True)

        vwap = self.bar_builder.get_vwap(symbol)
        vwap_s = f"{vwap:.4f}" if vwap is not None else "n/a"
        print(f"[ENGINE] {now_iso_et()} seeded {symbol}: {replayed} ticks "
              f"({skipped} skipped) → bars (vwap={vwap_s})", flush=True)
        return replayed

    def _on_bar_close(self, bar: Bar):
        """TradeBarBuilder callback. Emits BarMessage on every bucket
        close. Engine seq is per-symbol and shared with TickMessage so a
        consumer can interleave the two in order."""
        sym = bar.symbol
        self.seq[sym] += 1
        ts_close = (bar.start_utc.replace(tzinfo=UTC) if bar.start_utc.tzinfo is None
                    else bar.start_utc).astimezone(ET)
        # Bucket close is +interval after the start.
        from datetime import timedelta
        ts_close = ts_close + timedelta(seconds=self.bar_builder.interval_seconds)
        vwap = self.bar_builder.get_vwap(sym)
        msg = BarMessage(
            symbol=sym,
            ts_close=ts_close.isoformat(),
            o=float(bar.open), h=float(bar.high),
            l=float(bar.low), c=float(bar.close), v=int(bar.volume),
            vwap=float(vwap) if vwap is not None else None,
            engine_seq=self.seq[sym],
        )
        self._broadcast_nowait(msg)

    # ── Tick cache flush ──────────────────────────────────────────────

    def _start_flush_thread(self):
        os.makedirs(TICK_CACHE_DIR, exist_ok=True)
        self._flush_thread = threading.Thread(
            target=self._flush_loop, name="engine-flush", daemon=True,
        )
        self._flush_thread.start()

    def _flush_loop(self):
        while not self._flush_stop.is_set():
            if self._flush_stop.wait(timeout=TICK_FLUSH_SEC):
                return
            try:
                self._flush_tick_cache()
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} cache flush error: {e!r}",
                      flush=True)

    def _flush_tick_cache(self):
        """Append today's tick buffer to disk. Per-symbol JSON files in
        tick_cache_engine/<date>/<sym>.json — same structure as Setup A's
        cache (list of {p, s, t}) but in a separate directory so the A/B
        side-by-side comparison stays clean.

        Files are append-merge: read existing, extend, atomic replace.
        Compression intentionally off here (Setup A uses .gz; we keep
        plain JSON during A/B for ease of inspection)."""
        with self._tick_buffer_lock:
            if not any(self._tick_buffer.values()):
                return
            snap, self._tick_buffer = self._tick_buffer, defaultdict(list)
        out_dir = os.path.join(TICK_CACHE_DIR, today_et_str())
        os.makedirs(out_dir, exist_ok=True)
        for sym, ticks in snap.items():
            if not ticks:
                continue
            path = os.path.join(out_dir, f"{sym}.json")
            existing = []
            try:
                if os.path.exists(path):
                    with open(path) as f:
                        existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = []
            except (OSError, json.JSONDecodeError):
                existing = []
            existing.extend(ticks)
            tmp = f"{path}.tmp.{os.getpid()}"
            try:
                with open(tmp, "w") as f:
                    json.dump(existing, f, separators=(",", ":"))
                os.replace(tmp, path)
            except OSError as e:
                print(f"[ENGINE] {now_iso_et()} flush write error {sym}: {e!r}",
                      flush=True)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    # ── Heartbeat ─────────────────────────────────────────────────────

    async def _heartbeat_loop(self):
        while not self.shutdown_event.is_set():
            try:
                # Compute tick rate over the trailing 5s.
                cutoff = time.monotonic() - 5.0
                while self._rate_window and self._rate_window[0][0] < cutoff:
                    self._rate_window.popleft()
                rate = sum(c for _, c in self._rate_window)
                # Same trailing-5s window for Alpaca quote rate.
                while (self._quote_rate_window
                       and self._quote_rate_window[0][0] < cutoff):
                    self._quote_rate_window.popleft()
                quote_rate = sum(c for _, c in self._quote_rate_window)
                # Oldest quote age across the watchlist (ms). Symbols we've
                # never received a quote for don't count (None tracker).
                # If the Alpaca stream is disabled, this is just 0.
                oldest_age_ms = 0
                if (self.alpaca_quote_stream is not None
                        and self._last_quote_mono_by_symbol):
                    now_mono = time.monotonic()
                    ages = [
                        (now_mono - t) * 1000.0
                        for t in self._last_quote_mono_by_symbol.values()
                    ]
                    if ages:
                        oldest_age_ms = int(max(ages))
                alpaca_connected = (self.alpaca_quote_stream is not None
                                    and self.alpaca_quote_stream.connected)
                msg = HeartbeatMessage(
                    ts=now_iso_et(),
                    engine_uptime_s=int(time.monotonic() - self.started_at),
                    ibkr_connected=self.ibkr_connected,
                    tick_rate_5s=int(rate),
                    alpaca_stream_connected=alpaca_connected,
                    alpaca_quote_rate_5s=int(quote_rate),
                    alpaca_quote_oldest_age_ms=int(oldest_age_ms),
                )
                await self._broadcast(msg)
            except Exception as e:
                print(f"[ENGINE] {now_iso_et()} heartbeat error: {e!r}", flush=True)
            try:
                await asyncio.wait_for(self.shutdown_event.wait(), timeout=HEARTBEAT_SEC)
                return
            except asyncio.TimeoutError:
                pass

    # ── IPC server ────────────────────────────────────────────────────

    async def _handle_client(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter):
        client = _Client(writer)
        self.clients.add(client)
        # Start the per-client sender coroutine.
        client.send_task = asyncio.create_task(self._client_sender(client))
        print(f"[ENGINE] {now_iso_et()} IPC client connected ({client.peer_label()})",
              flush=True)
        # Send initial subscriptions immediately so the bot knows the
        # current watchlist without waiting for the next change.
        await self._send_to_client(client, SubscriptionsMessage(
            watchlist=sorted(self.watchlist),
            tier1=[],
            tier2=sorted(self.watchlist),
            policy_owner="engine_ab" if AB_PERIOD else "engine",
        ))
        # If we're not currently connected to IBKR, tell the bot up front.
        if not self.ibkr_connected:
            await self._send_to_client(client, StreamPausedMessage(
                reason="ibkr_not_connected_yet", since=now_iso_et(),
            ))
        try:
            async for msg in aread_frames(reader):
                self._on_client_msg(client, msg)
        except Exception as e:
            print(f"[ENGINE] {now_iso_et()} client {client.peer_label()} "
                  f"reader error: {e!r}", flush=True)
        finally:
            self.clients.discard(client)
            try:
                client.send_task.cancel()
            except Exception:
                pass
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            print(f"[ENGINE] {now_iso_et()} IPC client disconnected "
                  f"({client.peer_label()}, dropped={client.dropped_msgs})",
                  flush=True)

    def _on_client_msg(self, client: _Client, msg):
        if isinstance(msg, HelloMessage):
            client.bot_id = msg.bot_id
            print(f"[ENGINE] {now_iso_et()} hello from {msg.bot_id} v{msg.version}",
                  flush=True)
        elif isinstance(msg, InterestMessage):
            # Advisory only during A/B. Logged so we can replay the Phase 3
            # priority unlock against historical data later.
            print(f"[ENGINE] {now_iso_et()} interest from {msg.bot_id}: {msg.symbols} "
                  f"(advisory — no effect during A/B)", flush=True)
        else:
            print(f"[ENGINE] {now_iso_et()} unhandled client msg: "
                  f"{type(msg).__name__}", flush=True)

    async def _client_sender(self, client: _Client):
        """One coroutine per client. Drains the per-client queue to the
        writer. Slow consumers see their queue fill; we drop *oldest* (FIFO)
        to keep the engine responsive, with a [WARN] log per drop wave."""
        writer = client.writer
        try:
            while True:
                payload = await client.queue.get()
                if payload is None:
                    return
                try:
                    writer.write(payload)
                    await writer.drain()
                except (ConnectionResetError, BrokenPipeError, OSError):
                    return
        except asyncio.CancelledError:
            return

    def _broadcast_nowait(self, msg):
        """Enqueue a message to every connected client. Drops oldest on a
        full queue — the directive's slow-consumer policy."""
        payload = encode(msg)
        for client in list(self.clients):
            try:
                client.queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop oldest (rotate one out), enqueue new.
                try:
                    client.queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                client.dropped_msgs += 1
                if client.dropped_msgs in (1, 10, 100, 1000):
                    print(f"[ENGINE] {now_iso_et()} [WARN] dropped "
                          f"{client.dropped_msgs} messages for "
                          f"{client.peer_label()} (slow consumer)", flush=True)
                try:
                    client.queue.put_nowait(payload)
                except asyncio.QueueFull:
                    pass

    async def _broadcast(self, msg):
        """Async helper — same as _broadcast_nowait but awaits drain on
        each client so backpressure surfaces. Used for slow-cadence
        messages (heartbeat, subscriptions, pause/resume)."""
        self._broadcast_nowait(msg)

    async def _send_to_client(self, client: _Client, msg):
        payload = encode(msg)
        try:
            client.queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass


# ══════════════════════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════════════════════


def _install_signals(engine: DataEngine, loop: asyncio.AbstractEventLoop):
    def _handler():
        print(f"[ENGINE] {now_iso_et()} signal received — requesting shutdown",
              flush=True)
        engine.request_shutdown()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            # add_signal_handler is unix-only; we are unix, this should
            # never fire, but defensive.
            signal.signal(sig, lambda *_: _handler())


def main():
    parser = argparse.ArgumentParser(description="Setup B unified data engine")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate config + open IPC server but don't connect to IBKR. "
                             "Useful for offline smoke-testing the bots.")
    args = parser.parse_args()

    if args.dry_run:
        os.environ["ENGINE_DRY_RUN"] = "1"
        print(f"[ENGINE] {now_iso_et()} DRY-RUN: skipping IBKR connect",
              flush=True)

    async def _runner():
        engine = DataEngine()
        _install_signals(engine, asyncio.get_running_loop())
        if args.dry_run:
            # Skip real IBKR connect; pretend we're connected so bots
            # receive heartbeats with ibkr_connected=False (they'll
            # fail-CLOSED on entries, which is exactly what we want for
            # a paper-safe smoke test).
            engine.ibkr_connected = False
            # Pre-populate watchlist from disk one time so SubscriptionsMessage
            # has something meaningful, but never call reqMktData.
            engine.watchlist = set(engine._read_watchlist())
            async def _noop_watchlist():
                # Replace the real watchlist loop with a no-op so we
                # don't try to subscribe (no IBKR).
                try:
                    while not engine.shutdown_event.is_set():
                        await asyncio.wait_for(engine.shutdown_event.wait(),
                                               timeout=WL_POLL_SEC)
                except asyncio.TimeoutError:
                    pass
                except asyncio.CancelledError:
                    return
            # Monkey-patch: replace _watchlist_loop on this instance.
            engine._watchlist_loop = _noop_watchlist  # type: ignore[assignment]
            # Same for _ensure_ibkr_connected — bypass.
            async def _noop_connect():
                return False
            engine._ensure_ibkr_connected = _noop_connect  # type: ignore[assignment]
        await engine.run()

    try:
        # ib_insync uses asyncio under the hood; asyncio.run is the
        # correct entry point.
        asyncio.run(_runner())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
