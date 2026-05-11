"""IPC contract between data_engine.py and the thin strategy bots.

Implements the message types specified in DIRECTIVE_UNIFIED_DATA_ENGINE_BUILD.md
Phase 1 ("IPC Contract"). This module is pure data + serialization helpers —
no socket I/O, no threading, no asyncio. The engine and bots build socket
plumbing on top of these primitives so the wire format is the single source
of truth.

Wire format: newline-delimited JSON over a Unix stream socket
(`/tmp/warrior_engine.sock` by default). Each line is one complete JSON
object as produced by `encode(msg)`. The receiver buffers bytes and yields
parsed messages via `iter_frames(reader)` or `decode(line)`.

Message types (engine → bots):
    TickMessage         — every trade tick
    BarMessage          — 1m bar close (with VWAP)
    SubscriptionsMessage — current watchlist + tier allocation (sent on change)
    HeartbeatMessage    — every 5s
    StreamPausedMessage — engine lost IBKR connection
    StreamResumedMessage — IBKR connection restored

Message types (bots → engine):
    HelloMessage    — sent on connect to identify the bot
    InterestMessage — advisory: which symbols this bot wants Tier 1 priority on
                      (engine ignores during A/B period; reserved for Phase 3)

Versioning: every message dataclass carries an implicit schema. If a
breaking change ships, bump the engine `version` field on Hello /
heartbeat. Adding new optional fields is backwards compatible (older
decoders ignore unknown keys when constructing dataclasses via
`from_dict`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, AsyncIterator, Iterable, Iterator, Optional


# Default socket path. Overridable via ENGINE_IPC_SOCKET env var by callers.
DEFAULT_SOCKET_PATH = "/tmp/warrior_engine.sock"

# Wire-protocol version. Bumped only on breaking schema changes.
IPC_VERSION = 1


# ══════════════════════════════════════════════════════════════════════
# Message dataclasses
# ══════════════════════════════════════════════════════════════════════


@dataclass
class TickMessage:
    """One trade print from the engine. `tier` is always 'snapshot' during
    the A/B period (WB_ENGINE_AB_PERIOD=1); reserved values are 'snapshot'
    and 'tick_by_tick' for the post-A/B Phase 3 upgrade."""
    symbol: str
    ts: str                 # ISO 8601 with timezone
    price: float
    size: int
    engine_seq: int         # monotonic per-symbol sequence number
    exchange: Optional[str] = None
    tier: str = "snapshot"
    type: str = "tick"


@dataclass
class BarMessage:
    """1-minute bar close emitted by the engine's per-symbol bar builder.
    `vwap` is the engine's session-VWAP at bar-close time."""
    symbol: str
    ts_close: str           # ISO 8601 ET
    o: float
    h: float
    l: float
    c: float
    v: int
    vwap: Optional[float]
    engine_seq: int
    interval: str = "1m"
    type: str = "bar"


@dataclass
class SubscriptionsMessage:
    """Engine broadcasts this whenever the watchlist or tier allocation
    changes. During A/B period: tier1 is always empty, tier2 is the full
    watchlist, policy_owner is "engine_ab"."""
    watchlist: list[str]
    tier1: list[str]              # empty during A/B
    tier2: list[str]
    policy_owner: str = "engine_ab"
    type: str = "subscriptions"


@dataclass
class HeartbeatMessage:
    """Engine → bots every 5 seconds. Bots use this to detect engine
    liveness; absence for >2 intervals means socket-level fail-CLOSED."""
    ts: str                       # ISO 8601 ET
    engine_uptime_s: int
    ibkr_connected: bool
    tick_rate_5s: int             # ticks delivered in the trailing 5s
    type: str = "heartbeat"


@dataclass
class StreamPausedMessage:
    """Sent when the engine loses IBKR. Bots fail-CLOSED on receipt:
    no new entries, continue managing open positions."""
    reason: str
    since: str                    # ISO 8601 ET timestamp when pause began
    type: str = "stream_paused"


@dataclass
class StreamResumedMessage:
    """Sent after IBKR reconnect succeeds. Bots may resume new entries."""
    ts: str
    type: str = "stream_resumed"


@dataclass
class HelloMessage:
    """First message a bot sends on connect. Engine uses bot_id for
    diagnostics + (future) interest routing."""
    bot_id: str                   # "squeeze_bot" | "wb_bot"
    version: str = "1.0"
    type: str = "hello"


@dataclass
class InterestMessage:
    """Bot → engine advisory: symbols this strategy wants Tier 1 priority
    on. Engine ignores during A/B period. Wired into the IPC spec now so
    Phase 3 (post-A/B TBT re-enable) doesn't need a protocol bump."""
    bot_id: str
    symbols: list[str] = field(default_factory=list)
    type: str = "interest"


# Registry of all message types we ship. Used by `decode` to route a
# parsed dict to its dataclass.
_MESSAGE_TYPES = {
    "tick": TickMessage,
    "bar": BarMessage,
    "subscriptions": SubscriptionsMessage,
    "heartbeat": HeartbeatMessage,
    "stream_paused": StreamPausedMessage,
    "stream_resumed": StreamResumedMessage,
    "hello": HelloMessage,
    "interest": InterestMessage,
}


# ══════════════════════════════════════════════════════════════════════
# Serialization helpers
# ══════════════════════════════════════════════════════════════════════


def encode(msg: Any) -> bytes:
    """Serialize a message dataclass to newline-terminated JSON bytes.

    Accepts any of the dataclasses above. Always appends a trailing
    newline so the receiver can frame on '\\n' without needing a length
    prefix. Returns bytes ready to write to a socket.
    """
    if hasattr(msg, "__dataclass_fields__"):
        payload = asdict(msg)
    elif isinstance(msg, dict):
        payload = msg
    else:
        raise TypeError(f"encode: expected dataclass or dict, got {type(msg).__name__}")
    # separators=(',', ':') keeps the line compact — at ~5K ticks/min
    # the bytes add up. ensure_ascii=False is fine here, JSON-over-Unix-
    # socket is binary-safe.
    line = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return (line + "\n").encode("utf-8")


def decode(line: str | bytes) -> Any:
    """Parse one newline-delimited JSON message back into its dataclass.

    Returns the appropriate message dataclass (TickMessage, BarMessage, …)
    based on the `type` field. Unknown `type` values return the raw dict
    (forward-compat: receivers see new message kinds as dicts rather
    than crashing).
    """
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    line = line.strip()
    if not line:
        raise ValueError("decode: empty line")
    obj = json.loads(line)
    if not isinstance(obj, dict):
        raise ValueError(f"decode: expected JSON object, got {type(obj).__name__}")
    msg_type = obj.get("type")
    cls = _MESSAGE_TYPES.get(msg_type)
    if cls is None:
        # Forward-compat: unknown message type — return the raw dict.
        return obj
    # Filter unknown keys so the dataclass constructor doesn't choke
    # on a future field added by a newer engine talking to an older bot.
    known_fields = set(cls.__dataclass_fields__.keys())
    kwargs = {k: v for k, v in obj.items() if k in known_fields}
    return cls(**kwargs)


def iter_frames(buf: bytes) -> tuple[Iterable[str], bytes]:
    """Split a byte buffer on '\\n' boundaries.

    Returns (complete_lines, remainder). The remainder is the trailing
    partial frame (if any) that the caller should prepend to the next
    chunk before re-invoking. Lines are returned as utf-8 strings.

    Pure helper — no I/O — so unit tests don't need a socket.
    """
    if not buf:
        return [], b""
    parts = buf.split(b"\n")
    # If the buffer ended on '\n', the last part will be empty and we
    # have nothing left over. Otherwise the last part is a partial line.
    remainder = parts[-1]
    complete = [p.decode("utf-8") for p in parts[:-1] if p]
    return complete, remainder


# ══════════════════════════════════════════════════════════════════════
# Asyncio + blocking-socket frame readers (used by engine and bots)
# ══════════════════════════════════════════════════════════════════════


async def aread_frames(reader) -> AsyncIterator[Any]:
    """Yield decoded messages from an asyncio.StreamReader.

    Generator stops on EOF (engine disconnects → reader closed). Caller
    handles reconnect; this helper is intentionally one-shot. Decoder
    errors on individual frames are logged-and-skipped via printing to
    stderr — a malformed frame should not kill the consumer.
    """
    buf = b""
    while True:
        chunk = await reader.read(65536)
        if not chunk:
            return  # EOF
        buf += chunk
        complete, buf = iter_frames(buf)
        for line in complete:
            try:
                yield decode(line)
            except Exception as e:
                import sys
                print(f"[ipc] decode error (skipped): {e!r} on line={line[:120]!r}",
                      file=sys.stderr, flush=True)


def read_frames_blocking(sock) -> Iterator[Any]:
    """Yield decoded messages from a blocking `socket.socket`.

    Stops cleanly on EOF (peer closed) or on a `socket.error`. Caller
    handles reconnect. Buffer grows unboundedly only if the peer sends
    a single line >65KB and never terminates — that's a peer bug, not
    ours.
    """
    buf = b""
    while True:
        try:
            chunk = sock.recv(65536)
        except OSError:
            return
        if not chunk:
            return
        buf += chunk
        complete, buf = iter_frames(buf)
        for line in complete:
            try:
                yield decode(line)
            except Exception as e:
                import sys
                print(f"[ipc] decode error (skipped): {e!r} on line={line[:120]!r}",
                      file=sys.stderr, flush=True)
