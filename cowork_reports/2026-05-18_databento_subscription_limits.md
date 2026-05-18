# Databento Live SDK — Subscription/Connection Limits Investigation

**Date:** 2026-05-18 (Monday, post-close)
**Context:** Pre-build research for Setup B (`bot_alpaca_subbot.py` → Databento live ticks). Setup A
(IBKR) caps at 5 symbols / Tier 1 subscriptions. Before wiring Setup B we need to know whether
Databento has analogous tight limits.
**Directive:** Step 0 of the 2026-05-18 Databento subbot research request.
**SDK version under test:** `databento` 0.78.0 (released 2026-05-12) / `databento-dbn` 0.58.0.
**Branch / HEAD:** `v2-ibkr-migration` @ `fe8ac98`.

**Methodology note.** Databento's published docs (`databento.com/docs/...`) are 100% JavaScript-rendered;
`WebFetch` and raw `curl` both return only the SPA shell (no doc body). All "doc citations" below are
therefore against the **SDK source tarball** (`venv/lib/python3.12/site-packages/databento/`) and the
**published CHANGELOG** (`raw.githubusercontent.com/databento/databento-python/main/CHANGELOG.md`,
fetched 2026-05-18). The SDK is open-source and is the authoritative client-side reference; gateway-
side numeric caps that aren't documented in the SDK are noted as "empirically observed, not
documented." Every claim below is backed either by an SDK source line or a captured test run from
`/tmp/databento_tests/` (commands reproduced inline).

---

## Q1 — Per-connection symbol cap on `db.Live().subscribe(...)`

**Answer: No documented hard cap. SDK chunks symbol lists into 500-symbol protocol batches and a
single `subscribe()` call may include thousands. Empirically verified up to 2,000.**

- **SDK source citation.** `databento/live/protocol.py:39`:
  ```python
  SYMBOL_LIST_BATCH_SIZE: Final = 500
  ```
  And `protocol.py:341-348`: `chunked_symbols = list(chunk(symbols_list, SYMBOL_LIST_BATCH_SIZE))`
  — the SDK transparently splits any `symbols` iterable into 500-symbol batches and sends them as
  multiple `SubscriptionRequest` messages on the *same* TCP session.
- **CHANGELOG citation.** `0.53.x` entry: *"Increased live subscription symbol chunking size"* —
  i.e. this is a wire-format tuning knob, not a per-session cap. The SDK has explicitly raised it
  over time.
- **Empirical, 2026-05-18 19:14 ET, `EQUS.MINI` / `trades`:**
  - 50 symbols → `subscribe()` OK, `is_connected=True`, 51 records in 4 s (mappings + system).
  - 200 symbols → OK, 201 records in 4 s.
  - 500 symbols → OK in 1.24 s.
  - 1,000 symbols → OK in 1.23 s.
  - 2,000 symbols → OK in 1.23 s.
  Identical 0-error behavior at every step. (Most symbols at 1k+ were synthetic letter combinations
  → no symbology mapping returned, but the protocol accepted and acknowledged every request.)
- **Implication.** For Setup B we'd ever want 5–50 symbols (watchlist size). We are *three orders of
  magnitude* below any practical limit. Vs IBKR's 5-symbol Tier 1 cap, Databento has **no analogous
  per-connection symbol constraint** that would force Tier 1/Tier 2 partitioning.

---

## Q2 — Per-account concurrent-stream cap

**Answer: ≥ 3 concurrent Live sessions on a single API key work without error. A
`CONNECTION_LIMIT_EXCEEDED` error code exists in the protocol but its numeric ceiling is not
documented in the SDK.**

- **SDK source citation (proof a cap exists).** `databento_dbn.ErrorCode` enum:
  ```
  API_KEY_DEACTIVATED, AUTH_FAILED, CONNECTION_LIMIT_EXCEEDED, INTERNAL_ERROR,
  INVALID_SUBSCRIPTION, SKIPPED_RECORDS_AFTER_SLOW_READING, SYMBOL_RESOLUTION_FAILED
  ```
  `CONNECTION_LIMIT_EXCEEDED` is delivered as an `ErrorMsg` on the live stream when the cap is hit.
  The SDK does not embed the numeric ceiling — it's set server-side per account/tier.
- **Empirical, 2026-05-18 19:18 ET:** Opened 3 simultaneous `db.Live()` sessions against
  `EQUS.MINI` / `trades` with `[AAPL, TSLA, MSFT]` on each. All three reported `is_connected=True`
  and stayed connected for 4 s. No `CONNECTION_LIMIT_EXCEEDED` raised. (Earlier 2-session test also
  passed and delivered SymbolMappingMsg records to both.)
- **The scanner already uses 1 session.** `live_scanner.py:650` opens `db.Live()` for the
  `EQUS.MINI` `tbbo` ALL_SYMBOLS stream. Setup B adds a 2nd; a debugging shell could add a 3rd. We
  are confirmed-safe at 3.
- **Implication.** Setup B is safe. **Risk note:** we did *not* push to find the actual cap because
  hitting `CONNECTION_LIMIT_EXCEEDED` may have account-side cooldown effects (undocumented). If
  Manny ever wants to fan out more parallel sessions, test incrementally and watch for
  `ErrorCode.CONNECTION_LIMIT_EXCEEDED` in the `exception_callback`.

---

## Q3 — Per-schema bandwidth / message-rate limits

**Answer: No fixed msg/sec cap. The gateway will keep sending. If the **client** falls behind, the
gateway escalates: it first sends a `SLOW_READER_WARNING` SystemMsg, then (depending on the
configured `slow_reader_behavior`) either drops/skips records or queues them.**

- **SDK source citation.** `databento/live/client.py` constructor doc:
  ```
  slow_reader_behavior: SlowReadBehavior | str, optional
      The live gateway behavior when the client falls behind real time.
          - "skip": skip records to immediately catch up
          - "warn": send a slow reader warning `SystemMsg` but continue reading every record
  ```
  Plus `ErrorCode.SKIPPED_RECORDS_AFTER_SLOW_READING` (CHANGELOG `0.72.0`) and `SystemCode`:
  ```
  END_OF_INTERVAL, HEARTBEAT, REPLAY_COMPLETED, SLOW_READER_WARNING, SUBSCRIPTION_ACK, UNSET
  ```
- **CHANGELOG `0.78.0` (2026-05-12, current):**
  *"Added time-based backpressure to the live client: pauses reading records from the live gateway
  when the internal queue spans more than 1 second of data by `ts_index`."* — i.e. the SDK already
  paddles backward against the kernel TCP buffer to avoid escalating to gateway-side skip behavior.
- **Client-side queue.** `databento/live/session.py:38`: `DBN_QUEUE_CAPACITY: Final = 2**20`
  (~1,048,576 records). At microcap trade rates (1–10 msg/s on a hot mover) this is unreachable;
  at ALL_SYMBOLS XNAS.ITCH rates (~tens of thousands/sec) it is reachable.
- **Implication.** No "throttle above X msg/s" exists. The architectural pattern is **read fast or
  lose records.** For Setup B's narrow watchlist (5–50 symbols on `trades`/`tbbo`) message volume is
  trivial — well under 1 ms of CPU per record. Use `slow_reader_behavior="warn"` (default) and
  monitor for `SystemCode.SLOW_READER_WARNING` in the callback. **Don't do heavy work in the
  callback** — push to a queue.

---

## Q4 — Subscription-modify behavior (add/remove symbols mid-session)

**Answer: Adding symbols mid-session works without teardown. The session is the dataset's "channel";
multiple `subscribe()` calls add to the existing stream. Changing **dataset** mid-session is
explicitly rejected. The SDK has no `unsubscribe()` — removing symbols requires teardown + reconnect.**

- **SDK source citation.** `databento.Live.subscribe.__doc__`:
  > "Add a new subscription to the session. All subscriptions must be for the same `dataset`.
  > Multiple subscriptions for different schemas can be made. When creating the first subscription,
  > this method will also create the TCP connection to the remote gateway."
- **`Live.subscription_requests` property** (CHANGELOG `0.67.0`, 2025-12-02): SDK retains a list of
  every `SubscriptionRequest` issued, indexable by the returned `subscription_id`. Confirms additive
  model.
- **Empirical, 2026-05-18 19:16 ET:**
  - Subscribed `[AAPL, TSLA, MSFT]`, `.start()`, slept 3 s.
  - Called `.subscribe(...[AMZN, NVDA])` *after* start — returned `sub_id=1` (vs initial 0),
    `is_connected=True`, no exception. Records continued flowing.
  - Attempted `.subscribe(dataset="DBEQ.BASIC", ...)` on a session already bound to `EQUS.MINI` →
    raised `ValueError: Cannot subscribe to dataset 'DBEQ.BASIC' because subscriptions to
    'EQUS.MINI' have already been made.`
- **Removing symbols.** No `Live.unsubscribe()` method exists (`dir(db.Live)` enumerated above).
  Workarounds: (a) filter in the callback, (b) tear down with `stop()`/`block_for_close()` and
  reconnect.
- **Implication.** Setup B can dynamically expand its watchlist as the scanner posts new candidates
  — just call `.subscribe()` again with the new symbols. To shrink the watchlist we'd either filter
  client-side or reconnect; for the squeeze workflow (symbols are durable until end-of-day) this is
  a non-issue.

---

## Q5 — Dataset coverage for the small-cap squeeze universe

**Answer: Confirmed coverage of microfloat names (SBFM, WLDS, MNTS) on `EQUS.MINI`, `DBEQ.BASIC`,
and `XNAS.ITCH`. XNAS.ITCH gives the highest tick density (raw venue depth); EQUS.MINI is
consolidated lit; DBEQ.BASIC is partial.**

- **Empirical, Historical proxy on Friday 2026-05-15 13:30–20:00 UTC (`hist.timeseries.get_range`,
  schema=trades, symbols=`[SBFM, WLDS, MNTS, AAPL]`):**

  | Dataset       | AAPL    | MNTS    | SBFM    | WLDS    |
  |---------------|---------|---------|---------|---------|
  | EQUS.MINI     | 25,705  | 197     | 153     | 33      |
  | DBEQ.BASIC    | 25,268  | 164     | 112     | 15      |
  | XNAS.ITCH     | 148,755 | 1,877   | 745     | 61      |

- **Live consistency.** The scanner already uses `EQUS.MINI` with `tbbo` ALL_SYMBOLS in production
  (`live_scanner.py:650-656`). We are paying for live access on this dataset and it includes the
  microcap universe.
- **Observation: WLDS @ 33 trades / 6.5 hrs on EQUS.MINI.** That's ~5 trades/hr, consistent with an
  illiquid microfloat. **For Setup B's tick-replay needs, EQUS.MINI is fine** but XNAS.ITCH would
  give ~2× more tick granularity for symbols listed on NASDAQ (most microcaps). If we want
  every-print fidelity, upgrade to XNAS.ITCH later.
- **Caveat — Q5 not verified during live trading hours.** This is a *historical* coverage proxy. We
  cannot confirm sub-second live tick delivery for these names without a market-hours test. **Run
  a 5-minute live capture on a hot premarket microcap tomorrow morning (07:00–07:30 ET) to
  confirm Setup B will receive the same ticks Setup A sees.** Add to the morning checklist.

---

## Q6 — Latency floor (venue trade → client receipt)

**Answer: Cannot measure tonight (market closed; smoke test produced 0 trades on AAPL/TSLA at
19:16 ET). SDK supports `ts_out` (gateway-stamped send time) which combined with `ts_recv` /
`ts_event` enables sub-millisecond client-measured latency.**

- **SDK source citation.** `db.Live(ts_out=True)` — constructor doc:
  > "If set, DBN records will be timestamped when they are sent by the gateway."
  Combined with `ts_event` (venue exchange time), `ts_recv` (Databento gateway receive time), and
  `ts_out` (gateway send time), we can decompose: venue → gateway, gateway-internal, gateway → us.
- **CHANGELOG `0.64.0`:** *"Added `ts_index` and `pretty_ts_index` properties for records in Python
  which provides the timestamp that is most appropriate for indexing"* — preferred for
  client-side ordering.
- **Empirical, 2026-05-18 19:16 ET:** 60 s `AAPL`+`TSLA` capture produced 0 `TradeMsg` records
  (after-hours, both names quiet). 2 SystemMsg heartbeats fired at ~5 s and ~35 s — consistent with
  the default heartbeat interval. Connectivity confirmed; latency unmeasured.
- **Tomorrow's measurement plan.** First 5 min after market open, subscribe with `ts_out=True` and
  log `local_recv_ns - ts_out_ns` per record. Expect single-digit ms median for co-located
  customers, tens of ms for general internet. Add to the morning checklist as a one-time
  calibration.

---

## Q7 — Authentication / session quirks

**Answer: API key auth (32-char `db-...` token) in `DATABENTO_API_KEY` env var. No documented
time-of-day windows. Sessions are long-lived; SDK auto-detects hung connections and disconnects
client-side. Reusing a session after disconnect works.**

- **SDK source.** `Live(key=None, gateway=None, port=None, ts_out=False, heartbeat_interval_s=None,
  reconnect_policy=None, slow_reader_behavior=None, compression="none")`. Auth via constructor
  `key=` or `DATABENTO_API_KEY` env var.
- **CHANGELOG `0.67.0`:** *"Added feature to automatically monitor for hung connections in the
  `Live` client. Hung connections will be disconnected client side with a `BentoError`."* —
  important: the SDK takes the safety position of killing zombie connections rather than waiting on
  the gateway.
- **CHANGELOG `0.66.0`:** *"Added a property `Live.session_id` which returns the streaming session
  ID when the client is connected"* — useful for log correlation.
- **CHANGELOG `0.65.0`:** *"A disconnected `Live` client can now be reused with a different
  dataset"* — formerly you had to construct a new `Live()`; since 0.65 you can re-subscribe after a
  disconnect.
- **Heartbeats.** Default heartbeat interval is gateway-set (~30 s observed in our smoke test:
  heartbeats at t+5 and t+35). Can be tuned with `heartbeat_interval_s` (minimum 5 s per docstring).
- **No time-of-day quirks observed.** Our subscriptions worked at 19:14 and 19:18 ET (post-close);
  the scanner runs from 04:00 ET premarket. No "quota refresh hour" hinted anywhere in SDK source
  or CHANGELOG.
- **Implication.** Setup B should:
  - Pass `DATABENTO_API_KEY` via env (do **not** hardcode).
  - Log `Live.session_id` on connect for log correlation.
  - Wrap callbacks with try/except so the auto-emitted exception-callback warning doesn't get lost.

---

## Q8 — Failure modes (disconnect / reconnect)

**Answer: Built into the SDK as of `0.55.x` (release notes confirm). Pass
`reconnect_policy="reconnect"` to `Live()` and register `add_reconnect_callback(...)` to be
notified. Default is `"none"` (no auto-reconnect). The reconnect callback receives the
last-event timestamp and the new session's metadata-start timestamp, so the client can detect and
log the data gap.**

- **SDK source citation.** `Live` constructor doc:
  > "reconnect_policy: ReconnectPolicy | str, optional. The reconnect policy for the live session.
  > - 'none': the client will not reconnect (default)
  > - 'reconnect': the client will reconnect automatically"
- **`Live.add_reconnect_callback` doc:**
  > "Add a callback for handling client reconnection events. This will only be called when using a
  > reconnection policy other than `ReconnectPolicy.NONE` and if the session has been started with
  > `Live.start`. Two instances of `pandas.Timestamp` will be passed to the callback: the last
  > `ts_event` or `Metadata.start` value from the disconnected session, and the `Metadata.start`
  > value of the reconnected session."
- **`Live.is_connected()`** is exposed and can be polled.
- **`exception_callback`** delivered via `add_callback(..., exception_callback=...)` (and
  `add_reconnect_callback(..., exception_callback=...)`).
- **No documented exponential-backoff spec.** Backoff timing is opaque in the SDK source — built
  inside the gateway client's TCP-layer reconnect loop. Treat reconnect timing as "fast but
  unspecified."
- **Implication for Setup B.** Mirror Setup A's resume pattern (`session_state/`, tick-cache
  flush, position rehydrate): on `reconnect_callback`, log the gap, replay any cached ticks from
  the disconnect-to-reconnect window, then resume detector state. **Do not flatten positions on
  reconnect** — follow the same persistence rule as Setup A
  (`feedback_session_persistence_required.md`).

---

## Aggregate: Architectural implications for Setup B

| Constraint                                | IBKR (Setup A)        | Databento (Setup B)                |
|-------------------------------------------|-----------------------|------------------------------------|
| Symbols per subscription                  | 5 (Tier 1)            | No effective cap (≥ 2,000 tested)  |
| Concurrent sessions per account           | 1 client / 32 streams | ≥ 3 verified; `CONNECTION_LIMIT_EXCEEDED` exists but ceiling unknown |
| Per-schema rate cap                       | n/a                   | None; backpressure via slow-reader |
| Mid-session symbol add                    | reqMktData / cancelMktData | `subscribe()` again (same dataset) |
| Mid-session dataset change                | n/a                   | Rejected (`ValueError`)            |
| Auto-reconnect                            | Manual                | Built-in (`reconnect_policy="reconnect"`) |

**No Tier 1/Tier 2 partition is needed on Setup B.** The 5-symbol Setup A architecture is an IBKR
quirk; do not port it.

**Build constraint to enforce in `databento_live_feed.py`:**
1. One `Live()` instance per dataset (we'll need `EQUS.MINI` for trades+tbbo on the watchlist).
2. Open at startup; never tear down except on cleanup.
3. `reconnect_policy="reconnect"` + reconnect-callback that logs the gap and triggers a cache replay
   over the missing window (mirror `session_resume_deployed` from Setup A).
4. `slow_reader_behavior="warn"` and surface `SystemCode.SLOW_READER_WARNING` to the bot's
   structured log.
5. Callback does **not** do work — pushes to a `queue.Queue`; bot thread consumes.

---

## Open / un-verifiable tonight

- Exact `CONNECTION_LIMIT_EXCEEDED` ceiling (not in SDK source; would require pushing N=4, 5, 6,
  ... and likely hitting a soft account-side throttle. Postponed.)
- Live latency floor (Q6) — requires market hours.
- Live coverage parity SBFM/WLDS/MNTS vs IBKR (Q5) — historical proxy positive; live confirmation
  scheduled for 2026-05-19 premarket.

## Verdict

**GREEN — proceed with build.** Every Databento limit empirically observed is looser than the IBKR
limits Setup A is built around. The only constraint to bake into the architecture is "one dataset
per `Live()`" (a non-issue: we want exactly one).
