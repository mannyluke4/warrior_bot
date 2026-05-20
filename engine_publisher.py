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

from engine_ipc import TickMessage, encode, DEFAULT_SOCKET_PATH


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

        self._server_thread = threading.Thread(
            target=self._accept_loop, daemon=True, name="engine-pub-accept"
        )
        self._broadcast_thread = threading.Thread(
            target=self._broadcast_loop, daemon=True, name="engine-pub-broadcast"
        )
        self._server_thread.start()
        self._broadcast_thread.start()
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
            print(
                f"[ENGINE_PUB] client connected "
                f"(total clients: {len(self._clients)})",
                flush=True,
            )

    def _broadcast_loop(self) -> None:
        while not self._stop_event.is_set():
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
