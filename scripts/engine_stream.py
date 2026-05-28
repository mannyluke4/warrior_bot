#!/usr/bin/env python3
"""engine_stream.py — tail the main bot's engine fan-out socket.

The main bot publishes IBKR ticks (and 1m bars, quotes, heartbeats, etc.)
to /tmp/warrior_engine.sock as newline-delimited JSON. Sub-bots A/B/C
consume the same socket. This script is a read-only sniffer that opens
a third concurrent client connection — no impact on the bots.

Usage:
    ./venv/bin/python scripts/engine_stream.py                  # all messages
    ./venv/bin/python scripts/engine_stream.py --symbols NCT,SPRC
    ./venv/bin/python scripts/engine_stream.py --types tick,bar
    ./venv/bin/python scripts/engine_stream.py --raw            # JSON passthrough
    ./venv/bin/python scripts/engine_stream.py --stats          # per-symbol rates

Ctrl-C cleanly disconnects.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import time
from collections import defaultdict

DEFAULT_SOCKET = "/tmp/warrior_engine.sock"


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--socket", default=os.getenv("ENGINE_IPC_SOCKET", DEFAULT_SOCKET))
    ap.add_argument("--symbols", default="",
                    help="comma-separated symbol filter (empty = all)")
    ap.add_argument("--types", default="",
                    help="comma-separated msg-type filter: tick,bar,quote,heartbeat,subscriptions,stream_paused,stream_resumed (empty = all)")
    ap.add_argument("--raw", action="store_true", help="print original JSON lines")
    ap.add_argument("--stats", action="store_true",
                    help="suppress per-msg output, print rolling per-symbol rate every 5s")
    ap.add_argument("--no-heartbeat", action="store_true",
                    help="suppress heartbeat messages (on by default in --stats)")
    return ap.parse_args()


def _fmt_ts(raw: str) -> str:
    """Extract HH:MM:SS.mmm from an ISO timestamp (UTC) and convert to ET."""
    # Quick path — ISO format is YYYY-MM-DDTHH:MM:SS[.fraction][±HH:MM]
    if not raw or "T" not in raw:
        return (raw or "")[-12:]
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        # ET = UTC-4 (EDT) or UTC-5 (EST). Use the dt's actual offset if it
        # already had one local; otherwise hard-code EDT for live use.
        et = dt.astimezone(timezone(timedelta(hours=-4)))
        return et.strftime("%H:%M:%S.") + f"{et.microsecond // 1000:03d}"
    except Exception:
        return raw[-12:]


def fmt_pretty(msg: dict) -> str:
    """Compact one-line render of a decoded message."""
    t = msg.get("type", "?")
    ts = _fmt_ts(msg.get("ts") or msg.get("ts_close") or msg.get("now") or "")
    sym = msg.get("symbol", "")
    if t == "tick":
        price = msg.get("price", 0.0)
        size = msg.get("size", 0)
        tier = msg.get("tier", "?")
        seq = msg.get("engine_seq", 0)
        return f"{ts} TICK   {sym:>6s} ${price:>7.4f} sz={size:<6d} tier={tier:<14s} seq={seq}"
    if t == "bar":
        o, h, l, c = msg.get("o"), msg.get("h"), msg.get("l"), msg.get("c")
        v = msg.get("v", 0)
        return f"{ts} BAR    {sym:>6s} O={o} H={h} L={l} C={c}  V={v:,}"
    if t == "quote":
        bid, ask = msg.get("bid", 0.0), msg.get("ask", 0.0)
        bs, az = msg.get("bid_size", 0), msg.get("ask_size", 0)
        return f"{ts} QUOTE  {sym:>6s} bid=${bid:.4f}x{bs}  ask=${ask:.4f}x{az}"
    if t == "heartbeat":
        return f"{ts} HEART  alpaca={msg.get('alpaca_stream_ok', '?')} ibkr={msg.get('ibkr_ok', '?')}"
    if t == "subscriptions":
        wl = msg.get("watchlist", [])
        return f"{ts} SUBS   watchlist={','.join(wl[:10])}{'…' if len(wl) > 10 else ''}"
    if t == "stream_paused":
        return f"{ts} PAUSED reason={msg.get('reason', '?')}"
    if t == "stream_resumed":
        return f"{ts} RESUME"
    # Unknown — show first 80 chars
    return f"{ts} {t.upper()}  {json.dumps(msg)[:120]}"


def main() -> int:
    args = parse_args()

    sym_filter = {s.strip().upper() for s in args.symbols.split(",") if s.strip()}
    type_filter = {t.strip().lower() for t in args.types.split(",") if t.strip()}
    suppress_heartbeat = args.no_heartbeat or args.stats

    if not os.path.exists(args.socket):
        sys.stderr.write(f"engine_stream: socket not found at {args.socket}\n")
        sys.stderr.write("  → is the main bot running with WB_ENGINE_PUBLISH_ENABLED=1?\n")
        return 1

    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.connect(args.socket)
    except (FileNotFoundError, ConnectionRefusedError) as e:
        sys.stderr.write(f"engine_stream: cannot connect: {e}\n")
        return 1

    sys.stderr.write(f"engine_stream: connected to {args.socket}"
                     + (f" — filter symbols={sorted(sym_filter)}" if sym_filter else "")
                     + (f" types={sorted(type_filter)}" if type_filter else "")
                     + "\n")

    # Ctrl-C → graceful close.
    stop = {"flag": False}
    def _sigint(_signum, _frame):
        stop["flag"] = True
    signal.signal(signal.SIGINT, _sigint)

    stats = defaultdict(lambda: {"ticks": 0, "bars": 0})
    stats_start = time.monotonic()
    STATS_INTERVAL = 5.0

    buf = b""
    sock.settimeout(1.0)
    while not stop["flag"]:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                sys.stderr.write("engine_stream: socket closed by main bot\n")
                break
            buf += chunk
        except socket.timeout:
            chunk = b""
        except OSError as e:
            sys.stderr.write(f"engine_stream: recv error: {e}\n")
            break

        # Frame on newlines.
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError as e:
                sys.stderr.write(f"engine_stream: bad JSON: {e} — {line[:80]!r}\n")
                continue

            t = msg.get("type", "")
            sym = msg.get("symbol", "")

            if sym_filter and sym not in sym_filter:
                continue
            if type_filter and t not in type_filter:
                continue
            if suppress_heartbeat and t == "heartbeat":
                continue

            if args.stats:
                if t == "tick":
                    stats[sym]["ticks"] += 1
                elif t == "bar":
                    stats[sym]["bars"] += 1
            elif args.raw:
                sys.stdout.write(line.decode("utf-8", "replace") + "\n")
                sys.stdout.flush()
            else:
                print(fmt_pretty(msg), flush=True)

        # Periodic stats render.
        if args.stats and (time.monotonic() - stats_start) >= STATS_INTERVAL:
            elapsed = time.monotonic() - stats_start
            rows = sorted(stats.items(), key=lambda x: -x[1]["ticks"])[:20]
            print(f"\n=== last {elapsed:.0f}s — top by tick rate ===", flush=True)
            for sym, c in rows:
                rate = c["ticks"] / elapsed
                print(f"  {sym:>6s}  ticks={c['ticks']:>6d}  ({rate:>6.1f}/s)  bars={c['bars']}", flush=True)
            stats.clear()
            stats_start = time.monotonic()

    sock.close()
    sys.stderr.write("engine_stream: disconnected\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
