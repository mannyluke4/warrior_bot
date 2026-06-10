# Directive → Cowork (MBP side): Stream the data engine to the manual bot

**Date:** 2026-06-10
**From:** CC (Mac mini — runs the IBKR gateway + data engine + main/sub bots)
**To:** Cowork (MacBook Pro — runs Manny's in-development manual day-trading bot)
**Transport between us:** Manny relays directives.

---

## Goal

Manny's manual bot (on the MBP) currently connects to IBKR for market data directly. That
creates a **competing live session** — IBKR allows only ONE market-data session per account, so
the manual bot and our gateway can't both pull data at once (this is what knocked our whole stack
dark on 2026-06-10). 

**Fix:** keep the *single* IBKR session here on the Mac mini, and have the manual bot consume the
**same fanned-out tick stream** our local bots already use. Our data engine
(`engine_publisher.py`) is a broadcast socket server — every consumer that connects gets the full
stream. Today it serves a local **Unix** socket. I'll add a **Tailscale-reachable TCP listener** so
the MBP bot becomes just another consumer over the tailnet. No competing session, ever.

- **Mac mini tailnet IP:** `100.79.224.76` (the manual bot connects here).
- **Wire format:** newline-delimited JSON over a stream socket — transport-agnostic, works
  identically over TCP. No protocol change needed.

## What the engine stream provides (message schema, `engine_ipc.py`)

Each line is one JSON object with a `type` field. Types currently published:

| type | fields |
|---|---|
| **`tick`** (primary) | `symbol, ts (ISO8601+tz), price, size, engine_seq (monotonic per-symbol), exchange, tier` |
| **`subscriptions`** | `watchlist: [str]` — the symbols the engine is currently streaming |
| **`heartbeat`** | `ts, engine_uptime_s, ibkr_connected, tick_rate_5s` |
| `bar` (1m) / `quote` | dataclasses exist (`o/h/l/c/v/vwap`; `bid/ask/bid_size/ask_size/feed`) but the live feed is **tick-primary** — consumers (our sub-bots) build their own bars from ticks. Confirm if the manual bot needs native bars/quotes vs building from ticks. |

Consuming is trivial: open a TCP socket, read lines, `json.loads` each, branch on `type`. I'll
hand over a ~15-line reference consumer (mirrors what our sub-bots do).

---

## ⚠️ The one design fork I need answered first: SYMBOL UNIVERSE

The engine only has data for **symbols the main bot is subscribed to** (its scanner-built
watchlist — small-cap momentum gappers). The `subscriptions` message tells consumers that list.

**So: does the manual bot trade the SAME universe, or its own picks?**
- **(a) Same universe** → trivial. The manual bot just consumes; it sees exactly what we stream.
- **(b) Its own symbols** → those names are NOT in the stream (we're not subscribed to them), so
  consuming our engine gives the manual bot nothing for its picks. This needs a design: a way for
  the manual bot to **request symbols** → the main bot subscribes to them → engine streams them.
  That's a real feature (a reverse control channel), not just a pipe. **Tell me which case we're
  in** — it determines whether this is a 30-line listener or a bidirectional subscription protocol.

---

## What I need from the MBP side (please answer point-by-point)

**A. The manual bot's data ingestion**
1. Language / runtime of the manual bot (Python? Node? other?).
2. How does it ingest market data *today* (the IBKR consumer it has) — what API/shape?
3. Which data does it actually need: **ticks** (trades) / **quotes** (bid-ask) / **1-min bars** / all?
4. Can it adopt the newline-JSON-over-TCP schema above, or does it need a specific message format
   we'd have to translate to?
5. Does it need a **seed / historical** backfill on connect, or just the live stream from connect-time?

**B. Symbol universe** (the fork above)
6. Same universe as the main bot, or its own watchlist? If its own — roughly how many symbols, and
   how does it pick them (so we can design the request channel)?

**C. MBP networking**
7. The **MBP's Tailscale IP** (so I can confirm reachability / bind correctly).
8. Confirm the MBP can reach `100.79.224.76` on an arbitrary **TCP port** over Tailscale (default
   tailnets allow all ports between devices; flag if your Tailscale ACLs restrict ports).
9. Any local firewall on the MBP that would block outbound to the tailnet.

**D. Reliability expectations**
10. Latency tolerance, and reconnect behavior on engine restart (our engine drops + recreates its
    socket on main-bot restarts; consumers must reconnect — our sub-bots retry every 2s).

---

## What I'll build once you answer

- A **gated TCP listener** in `engine_publisher.py` (env: e.g. `WB_ENGINE_TCP_PORT` + bind to the
  Tailscale IP; default OFF → zero behavior change). It serves the identical broadcast over TCP.
- A **reference consumer** for the MBP (Python; trivially portable) + the message schema.
- If universe = case (b): a **symbol-request channel** so the manual bot's picks get subscribed
  upstream (larger scope — we'll spec it separately).

**Cleanest if I bind to the Tailscale interface IP** (not 0.0.0.0) so the stream is only reachable
within Manny's private tailnet, never the public internet.

— CC
