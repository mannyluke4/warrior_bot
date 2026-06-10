"""engine_publisher.py — main-bot-side socket publisher (2026-05-20).

Main bot exposes its IBKR tick stream over a Unix socket so a sub-bot
running an alternate strategy (MOVE_STRIKE + HWM exit) can consume the
SAME tick stream — no second IBKR session, no 10197 competing-session
errors, no data-feed divergence.

Wire protocol reuses engine_ipc.py (TickMessage). Each tick the main bot
processes gets encoded and broadcast to all connected client sockets.

Design:
  - Single Unix-domain socket server. Listens for client connections.
  - Per-symbol monotonic `engine_seq` counter, matching engine_ipc schema.
  - Non-blocking publish: `publish_tick()` enqueues; a background thread
    drains the queue and broadcasts. Slow/dead clients are dropped without
    blocking the main bot's tick handler.
  - Queue has a max size; overflow drops the OLDEST tick (FIFO) so latest
    market data wins. Backpressure logged.
  - Gated by WB_ENGINE_PUBLISH_ENABLED; default off. When off, the bot's
    `publish_tick()` call is a no-op — bit-identical to no-publish behavior.

Threading model:
  - Server-accept loop in a daemon thread.
  - Broadcast loop in a daemon thread (drains queue → writes to clients).
  - Both daemons exit on process shutdown; no explicit cleanup needed.

Usage from bot_v3_hybrid.py:
  ```python
  from engine_publisher import get_publisher

  pub = get_publisher()
  if pub.enabled:
      pub.start()

  # ...in on_ticker_update / _process_trade_tick:
  if pub.enabled:
      pub.publish_tick(symbol, price, ts_iso)
  ```
"""

from __future__ import annotations

import json
import os
import queue
import socket
import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from engine_ipc import (
    TickMessage,
    SubscriptionsMessage,
    HeartbeatMessage,
    encode,
    DEFAULT_SOCKET_PATH,
)


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


class EnginePublisher:
    """Singleton socket server that broadcasts ticks to subscriber bots."""

    def __init__(
        self,
        socket_path: Optional[str] = None,
        queue_max: int = 10_000,
    ):
        self.socket_path = (
            socket_path or os.getenv("ENGINE_IPC_SOCKET", DEFAULT_SOCKET_PATH)
        )
        self.enabled = os.getenv("WB_ENGINE_PUBLISH_ENABLED", "0") == "1"
        self._queue: queue.Queue = queue.Queue(maxsize=queue_max)
        self._clients: list = []
        self._clients_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._server_sock: Optional[socket.socket] = None
        self._server_thread: Optional[threading.Thread] = None
        self._broadcast_thread: Optional[threading.Thread] = None
        self._seq_per_symbol: dict[str, int] = defaultdict(int)
        self._started = False
        # Counters for diagnostics
        self._stats_published = 0
        self._stats_dropped = 0
        self._stats_lock = threading.Lock()
        # Optional TCP listener (2026-06-10) so a REMOTE consumer (Manny's MBP
        # manual bot) gets the identical broadcast over Tailscale — keeping the
        # single IBKR session here and avoiding the competing-session conflict.
        # 0 = disabled. Bind to the Tailscale interface IP so it's tailnet-only,
        # never exposed to the public internet. Same newline-JSON wire format.
        self.tcp_port = int(os.getenv("WB_ENGINE_TCP_PORT", "0") or "0")
        self.tcp_bind = os.getenv("WB_ENGINE_TCP_BIND", "127.0.0.1")
        self._tcp_server_sock: Optional[socket.socket] = None
        self._tcp_accept_thread: Optional[threading.Thread] = None
        # --- Phase 2 (2026-06-10): subscriptions + heartbeat -----------------
        # Engine uptime is measured from start() with a monotonic clock (wall
        # clock not needed and avoids DST/skew). Heartbeat thread emits a
        # HeartbeatMessage every ~5s so remote consumers get an exact liveness
        # signal even when the market is quiet (no ticks ≠ dead pipe).
        self._start_monotonic: Optional[float] = None
        self._hb_interval_s = float(os.getenv("WB_ENGINE_HEARTBEAT_SEC", "5") or "5")
        self._heartbeat_thread: Optional[threading.Thread] = None
        # ibkr_connected defaults True: the publisher only runs inside a live,
        # IBKR-connected main bot. The bot flips it via set_ibkr_connected() on
        # an IBKR disconnect/reconnect so the consumer's indicator stays honest.
        self._ibkr_connected = True
        # Total ticks published (monotonic). The heartbeat thread snapshots the
        # delta over each interval to derive tick_rate_5s.
        self._tick_count_total = 0
        self._hb_last_tick_count = 0
        self._hb_last_monotonic: Optional[float] = None
        # Last subscriptions frame (encoded). Re-sent to each newly-connected
        # client so a (re)connecting consumer learns the current watchlist
        # immediately instead of waiting for the next watchlist change.
        self._last_subscriptions_encoded: Optional[bytes] = None
        self._last_subscriptions_sig: Optional[tuple] = None

    def start(self) -> None:
        """Open the server socket + spin up background threads. Idempotent."""
        if self._started:
            return
        if not self.enabled:
            print(f"[ENGINE_PUB] disabled (WB_ENGINE_PUBLISH_ENABLED=0)", flush=True)
            return

        # Best-effort cleanup of stale socket
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_sock.bind(self.socket_path)
        self._server_sock.listen(8)
        try:
            os.chmod(self.socket_path, 0o660)
        except OSError:
            pass

        import time as _time
        self._start_monotonic = _time.monotonic()
        self._hb_last_monotonic = self._start_monotonic

        self._server_thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="engine-pub-accept"
        )
        self._broadcast_thread = threading.Thread(
            target=self._broadcast_loop, daemon=True, name="engine-pub-broadcast"
        )
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, daemon=True, name="engine-pub-heartbeat"
        )
        self._server_thread.start()
        self._broadcast_thread.start()
        self._heartbeat_thread.start()

        # Optional TCP listener for remote (tailnet) consumers. The accepted TCP
        # sockets join the SAME self._clients set, so the existing broadcast loop
        # fans ticks to them automatically — no broadcast changes needed.
        if self.tcp_port > 0:
            try:
                self._tcp_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._tcp_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._tcp_server_sock.bind((self.tcp_bind, self.tcp_port))
                self._tcp_server_sock.listen(8)
                self._tcp_accept_thread = threading.Thread(
                    target=self._tcp_accept_loop, daemon=True, name="engine-pub-tcp-accept"
                )
                self._tcp_accept_thread.start()
                print(
                    f"[ENGINE_PUB] TCP listener on {self.tcp_bind}:{self.tcp_port} "
                    f"(tailnet fan-out — newline-JSON, same stream as the Unix socket)",
                    flush=True,
                )
            except Exception as e:
                print(f"[ENGINE_PUB] TCP listener failed to start "
                      f"({self.tcp_bind}:{self.tcp_port}): {e!r} — Unix socket unaffected",
                      flush=True)
                self._tcp_server_sock = None

        self._started = True
        print(
            f"[ENGINE_PUB] listening on {self.socket_path} "
            f"(queue_max={self._queue.maxsize})",
            flush=True,
        )

    def stop(self) -> None:
        """Signal background threads to exit + close server socket."""
        if not self._started:
            return
        self._stop_event.set()
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except Exception:
                pass
        if self._tcp_server_sock is not None:
            try:
                self._tcp_server_sock.close()
            except Exception:
                pass
        with self._clients_lock:
            for c in self._clients:
                try:
                    c.close()
                except Exception:
                    pass
            self._clients.clear()
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

    def publish_tick(
        self,
        symbol: str,
        price: float,
        ts_iso: Optional[str] = None,
        size: int = 0,
    ) -> None:
        """Enqueue a tick for broadcast. Non-blocking; drops on overflow."""
        if not self.enabled or not self._started:
            return
        self._tick_count_total += 1
        self._seq_per_symbol[symbol] += 1
        msg = TickMessage(
            symbol=symbol,
            ts=ts_iso or _now_iso_utc(),
            price=float(price),
            size=int(size or 0),
            engine_seq=self._seq_per_symbol[symbol],
        )
        try:
            self._queue.put_nowait(encode(msg))
            with self._stats_lock:
                self._stats_published += 1
        except queue.Full:
            # Drop oldest to make room for newest tick
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(encode(msg))
            except (queue.Empty, queue.Full):
                pass
            with self._stats_lock:
                self._stats_dropped += 1

    def set_ibkr_connected(self, connected: bool) -> None:
        """Main bot calls this on IBKR connect/disconnect so the heartbeat's
        ibkr_connected flag is honest. No-op effect on tick flow."""
        self._ibkr_connected = bool(connected)

    def publish_subscriptions(
        self,
        watchlist: list,
        meta: Optional[list] = None,
    ) -> None:
        """Broadcast the current watchlist (+ optional per-symbol scanner
        metadata) to all consumers. De-duplicated: a frame is only emitted when
        the watchlist or metadata actually changes, so calling this on every
        scan loop is cheap. The latest frame is cached and re-sent to each
        newly-connected client.

        `watchlist` — list of symbol strings.
        `meta` — optional list of dicts [{"symbol","gap_pct","rvol","float_m"}].
        """
        if not self.enabled or not self._started:
            return
        wl = [str(s) for s in (watchlist or [])]
        meta = list(meta or [])
        # Signature for de-dup: watchlist + a stable view of the metadata.
        try:
            meta_sig = tuple(
                (
                    m.get("symbol"),
                    m.get("gap_pct"),
                    m.get("rvol"),
                    m.get("float_m"),
                )
                for m in meta
            )
        except AttributeError:
            meta_sig = tuple()
        sig = (tuple(wl), meta_sig)
        if sig == self._last_subscriptions_sig:
            return
        # During the A/B period the engine policy puts everything in tier2
        # (tier1 stays empty) — matches the SubscriptionsMessage docstring.
        msg = SubscriptionsMessage(
            watchlist=wl,
            tier1=[],
            tier2=wl,
            meta=meta,
        )
        data = encode(msg)
        self._last_subscriptions_encoded = data
        self._last_subscriptions_sig = sig
        try:
            self._queue.put_nowait(data)
        except queue.Full:
            # Subscriptions are low-frequency + important — force room.
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(data)
            except (queue.Empty, queue.Full):
                pass

    def stats(self) -> dict:
        """Diagnostic snapshot."""
        with self._stats_lock:
            return {
                "enabled": self.enabled,
                "started": self._started,
                "clients": len(self._clients),
                "queue_size": self._queue.qsize(),
                "published": self._stats_published,
                "dropped": self._stats_dropped,
            }

    # ------------------------------------------------------------------
    # Background-thread loops
    # ------------------------------------------------------------------
    def _accept_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                client_sock, _ = self._server_sock.accept()
            except OSError:
                break
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[ENGINE_PUB] accept error: {e!r}", flush=True)
                continue
            # No greeting frame — the engine_ipc.decode() expects strictly
            # typed messages; a hello here would need to match the
            # HelloMessage schema. Just accept the connection and start
            # broadcasting ticks. The client knows it's connected when
            # the first frame arrives.
            try:
                client_sock.settimeout(None)
            except Exception:
                pass
            with self._clients_lock:
                self._clients.append(client_sock)
            self._send_subscriptions_snapshot(client_sock)
            print(
                f"[ENGINE_PUB] client connected "
                f"(total clients: {len(self._clients)})",
                flush=True,
            )

    def _tcp_accept_loop(self) -> None:
        """Accept remote (tailnet) TCP consumers. Accepted sockets join the same
        self._clients set the Unix consumers use, so the broadcast loop serves them
        identically. Mirrors _accept_loop."""
        while not self._stop_event.is_set():
            try:
                client_sock, addr = self._tcp_server_sock.accept()
            except OSError:
                break
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[ENGINE_PUB] tcp accept error: {e!r}", flush=True)
                continue
            try:
                client_sock.settimeout(None)
                client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            except Exception:
                pass
            with self._clients_lock:
                self._clients.append(client_sock)
            self._send_subscriptions_snapshot(client_sock)
            print(
                f"[ENGINE_PUB] TCP client connected from {addr} "
                f"(total clients: {len(self._clients)})",
                flush=True,
            )

    def _send_subscriptions_snapshot(self, client_sock) -> None:
        """Best-effort: push the cached subscriptions frame to one freshly
        connected client so it learns the current watchlist immediately rather
        than waiting for the next watchlist change. Failures are swallowed —
        the broadcast loop reaps the socket if it's actually dead."""
        data = self._last_subscriptions_encoded
        if not data:
            return
        try:
            client_sock.sendall(data)
        except Exception:
            pass

    def _heartbeat_loop(self) -> None:
        """Emit a HeartbeatMessage every ~5s onto the broadcast queue so all
        consumers get an exact liveness signal (socket-alive + IBKR-up +
        tick-rate) independent of whether the market is currently ticking."""
        import time as _time
        from datetime import datetime, timezone
        while not self._stop_event.is_set():
            # Wait the interval, but wake early on shutdown.
            if self._stop_event.wait(self._hb_interval_s):
                break
            now_mono = _time.monotonic()
            start_mono = self._start_monotonic or now_mono
            uptime_s = int(max(0.0, now_mono - start_mono))
            # tick_rate over the trailing interval, normalized to a 5s window so
            # the field name (tick_rate_5s) stays meaningful regardless of the
            # configured interval.
            prev_count = self._hb_last_tick_count
            cur_count = self._tick_count_total
            prev_mono = self._hb_last_monotonic or now_mono
            elapsed = max(1e-3, now_mono - prev_mono)
            ticks_delta = max(0, cur_count - prev_count)
            tick_rate_5s = int(round((ticks_delta / elapsed) * 5.0))
            self._hb_last_tick_count = cur_count
            self._hb_last_monotonic = now_mono
            msg = HeartbeatMessage(
                ts=datetime.now(timezone.utc).isoformat(),
                engine_uptime_s=uptime_s,
                ibkr_connected=bool(self._ibkr_connected),
                tick_rate_5s=tick_rate_5s,
            )
            try:
                self._queue.put_nowait(encode(msg))
            except queue.Full:
                # Heartbeat is important for the consumer's liveness indicator —
                # force room by dropping the oldest queued frame.
                try:
                    self._queue.get_nowait()
                    self._queue.put_nowait(encode(msg))
                except (queue.Empty, queue.Full):
                    pass

    def _broadcast_loop(self) -> None:
        import time as _time
        last_stats_log = _time.time()
        while not self._stop_event.is_set():
            # Periodic publisher STATS — exposes drop count for the
            # engine_seq audit (2026-05-22). Default ON via env.
            if _time.time() - last_stats_log > 60:
                if os.getenv("WB_SUBBOT_SEQ_AUDIT", "1") == "1":
                    with self._stats_lock:
                        pub = self._stats_published
                        drp = self._stats_dropped
                    print(
                        f"[ENGINE_PUB] STATS published={pub:,} dropped={drp:,} "
                        f"clients={len(self._clients)}",
                        flush=True,
                    )
                last_stats_log = _time.time()
            try:
                data = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            dead: list = []
            with self._clients_lock:
                clients_snapshot = list(self._clients)
            for client_sock in clients_snapshot:
                try:
                    client_sock.sendall(data)
                except (BrokenPipeError, ConnectionError, OSError):
                    dead.append(client_sock)
                except Exception as e:
                    print(
                        f"[ENGINE_PUB] broadcast error: {e!r}", flush=True
                    )
                    dead.append(client_sock)
            if dead:
                with self._clients_lock:
                    for d in dead:
                        try:
                            d.close()
                        except Exception:
                            pass
                        if d in self._clients:
                            self._clients.remove(d)
                print(
                    f"[ENGINE_PUB] dropped {len(dead)} disconnected client(s)",
                    flush=True,
                )


# Module-level singleton accessor
_instance: Optional[EnginePublisher] = None


def get_publisher() -> EnginePublisher:
    global _instance
    if _instance is None:
        _instance = EnginePublisher()
    return _instance
