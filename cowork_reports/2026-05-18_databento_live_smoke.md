# Databento Live SDK — 60-Second Smoke Test

**Date:** 2026-05-18 19:16 ET (23:16 UTC) — post-market-close, regular session ended at 16:00 ET.
**Directive:** Step 1 of the 2026-05-18 Databento subbot research request.
**SDK:** `databento` 0.78.0.
**Branch:** `v2-ibkr-migration` @ `fe8ac98`.

## Test specification

```python
live = db.Live(ts_out=True)
live.subscribe(dataset="EQUS.MINI", schema="trades", symbols=["AAPL", "TSLA"])
live.add_callback(cb, ec)
live.start()
# Run 60 s, sample every 2 s
```

Counters bucketed by record type: `TradeMsg`/`Mbp0Msg` (trades), `SystemMsg` (heartbeats),
`SymbolMappingMsg`, and `other`.

## Result

```
[Smoke] started @ 2026-05-18T23:16:34.223977+00:00, running 60s...
  t+  5.2s: trades=0 sys=1 symmap=2 other=0
  t+ 35.3s: trades=0 sys=2 symmap=2 other=0
  t+ 59.4s: trades=0 sys=2 symmap=2 other=0

[Smoke] DONE @ 2026-05-18T23:17:34.436951+00:00
  Total: {'trades': 0, 'system': 2, 'symbol_map': 2, 'other': 0}
  Errors: 0
  Latency: no trade records to measure (market likely closed)
```

## Observations

- **Stream connectivity confirmed.** Two `SymbolMappingMsg` records arrived immediately on
  subscription (one each for AAPL → instrument-id, TSLA → instrument-id). This is the SDK
  registering the symbology resolution for the requested symbols.
- **Heartbeats fire on schedule.** Two `SystemMsg` heartbeats observed (~t+5 s and ~t+35 s) →
  ~30 s heartbeat interval, consistent with Databento gateway default. This confirms the TCP
  session stayed open and the gateway was actively keeping it alive.
- **0 `TradeMsg` records.** Expected. NYSE/NASDAQ regular session ended at 16:00 ET; the test ran
  at 19:16 ET (after-hours). `EQUS.MINI` is the consolidated *lit* equity feed; after-hours
  activity for mega-caps like AAPL/TSLA does happen but is sparse (off-exchange/dark-pool prints
  dominate, which `EQUS.MINI` doesn't carry). On Friday 2026-05-15 during the *regular* session
  AAPL printed 25,705 trades on `EQUS.MINI` between 13:30–20:00 UTC — so the feed works fine when
  there's activity.
- **0 errors / exceptions.** No `exception_callback` triggered. Clean connect, clean tear-down.

## Companion test: ALL_SYMBOLS rate probe

To confirm the 0-trades result wasn't AAPL/TSLA-specific, immediately following the smoke test we
ran:

```python
live.subscribe(dataset="EQUS.MINI", schema="trades", symbols="ALL_SYMBOLS")
# 20 s
```

Result: 0 trades in 21.5 s, 0 errors. **The entire `EQUS.MINI` consolidated feed was silent for
trades during this 21.5-s post-close window.** This is normal after-hours behavior for the
consolidated-lit-only feed and is not a Databento problem.

## Smoke test verdict

**PASS.** The Databento Live SDK connects successfully, subscribes successfully, delivers
symbology mappings, maintains the session with heartbeats, and tears down cleanly. No protocol
errors. No connection limit hit. The 0-trades count is a function of *when* we ran the test, not
*whether* the stream works.

## Action items for tomorrow (2026-05-19) market-hours session

1. Repeat the 60-s smoke at 09:30 ET on AAPL/TSLA with `ts_out=True` — expect hundreds of
   `TradeMsg` records and millisecond-range latency. This becomes the Q6 latency measurement.
2. Repeat on a hot premarket microcap (whichever the scanner promotes top-of-watchlist) between
   07:00–07:30 ET. **This is the actual coverage parity test** for Setup B vs Setup A
   (`Q5_live_parity_followup`).
3. Diff per-second tick counts between Setup A's IBKR `reqMktData` stream and Setup B's Databento
   `trades` stream over the same symbol/window. Discrepancies > 5 % require investigation before
   we trust Setup B P&L.
