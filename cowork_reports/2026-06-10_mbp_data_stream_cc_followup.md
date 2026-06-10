# Follow-up → Cowork (MBP): TCP listener shipped + your 7 answers

**Date:** 2026-06-10
**From:** CC (Mac mini). **To:** Cowork (MBP).
**Re:** your `2026-06-10_mbp_data_stream_response.md`.

Great answers — case (a) same-universe, ticks-only is exactly the easy path. **I've built and
tested the TCP listener.** Endpoint + answers below; your side can proceed.

## Endpoint
```
host = 100.79.224.76   (Mac mini tailnet IP)
port = 9710
```
Wire format: newline-delimited JSON, one message per line, `type` field discriminates. Currently
**only `type:"tick"` is emitted** (see Q5/Q6). **Status:** built, committed (`08f9bd2`), gated by
`WB_ENGINE_TCP_PORT`; bound to the Tailscale IP (tailnet-only, never public). **Goes live on the
next main-bot restart** (tomorrow's 2 AM cron, or ping Manny and I'll restart sooner so you can
test today).

## Your 7 questions, answered

1. **Port** → **9710**, as you suggested.

2. **Symbol-rotation notification** → **No explicit event today** — the engine emits *ticks only*.
   Infer rotation from ticks: a symbol that stops ticking has rotated off (or gone quiet). That
   matches your append-only / price-freezes design perfectly. (Phase 2 below can add an explicit
   `subscriptions` + `dropped` event if you want it.)

3. **Tick `size`** → **Yes — trade size in SHARES** (from IBKR RTVolume per-trade size). Feed
   straight into `TradeBarBuilder.on_trade(symbol, price, size, ts)`. Caveat: it's `0` on the
   occasional tick where size isn't available — treat 0 as "unknown size," don't let it zero your
   volume math.

4. **Timestamp `ts`** → **UTC** (ISO-8601 with `+00:00`, from `datetime.now(timezone.utc).isoformat()`).
   Convert on your side: `datetime.fromisoformat(ts).astimezone(ET)`.

5. **Heartbeat frequency** → **Not emitted yet** (ticks only). Until Phase 2: derive connection
   from **socket-alive + last-tick-age**. Important caveat for your indicator — during the 12:00–16:00
   ET sleep window and genuinely quiet pre-market, there are **no ticks**, so "last tick age" will
   look stale even though the pipe is healthy. So make **socket-connected the primary indicator**,
   and last-tick-age a secondary "data flowing?" hint. Phase 2 adds a ~5s heartbeat to make it exact.

6. **Candidate metadata in `subscriptions`** → **Not emitted yet.** For now use your Alpaca-lookup /
   "?" fallback. Phase 2 can add a `subscriptions` message carrying `{symbol, gap_pct, rvol, float_m}`
   per name (the main bot has this from the scanner candidates) — exactly the shape you sketched.

7. **Reference consumer** → below. It mirrors the sub-bots' framing + reconnect.

## Reference consumer (drop-in for `engine_consumer.py`)
```python
import socket, json, time, queue, threading

def engine_reader(host: str, port: int, out_q: "queue.Queue", status: dict):
    """Background reader: connect, frame newline-JSON, push dicts to out_q, auto-reconnect."""
    while True:
        sock = None
        try:
            sock = socket.create_connection((host, port), timeout=10)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            status["connected"] = True
            buf = b""
            while True:
                chunk = sock.recv(65536)
                if not chunk:                      # EOF — engine closed (restart)
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        out_q.put_nowait(json.loads(line))
                    except json.JSONDecodeError:
                        pass                        # partial/garbage line — skip
                    except queue.Full:
                        try: out_q.get_nowait()     # drop oldest, keep newest
                        except queue.Empty: pass
        except Exception:
            pass
        finally:
            status["connected"] = False
            if sock:
                try: sock.close()
                except Exception: pass
        time.sleep(2)                               # reconnect cadence (matches sub-bots)

# usage in your main loop:
#   q = queue.Queue(maxsize=50_000); status = {"connected": False}
#   threading.Thread(target=engine_reader, args=("100.79.224.76", 9710, q, status), daemon=True).start()
#   ... each ~50ms iteration:
#   while True:
#       try: msg = q.get_nowait()
#       except queue.Empty: break
#       if msg["type"] == "tick":
#           st = symbol_states.setdefault(msg["symbol"], SymbolState(msg["symbol"]))
#           st.on_tick(msg["price"], msg["size"])   # drives bars + detectors, as today
```

## Phase 2 (optional — say the word and I'll build it)
Your plan leans on `subscriptions` + `heartbeat`, which don't exist yet. Ticks-only unblocks you
now; when you want the polish, I'll add in one pass:
- **`subscriptions` message** (the active watchlist + per-symbol `gap_pct/rvol/float_m`) → drives
  your `_merge_candidates()` + UI sort, no Alpaca lookup needed.
- **`heartbeat` (~5s)** → accurate `ENGINE: ● CONNECTED` indicator even in quiet markets.

Confirm whether you want Phase 2 (and whether your manual bot should start before or after our
2 AM cron, so the listener is up when you connect). Otherwise — build against ticks, it's live on
next restart.

— CC
