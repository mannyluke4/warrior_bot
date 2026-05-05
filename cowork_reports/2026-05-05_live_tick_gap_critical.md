# Live Tick Capture Gap — Critical Finding

**Date:** 2026-05-05
**Author:** CC
**Status:** 🔴 CRITICAL — affects backtest validity AND live trading edge
**Trigger:** Mid-session audit during 2026-05-05 Phase 1 paper test of Wave Breakout

---

## Headline

**The live IBKR tick capture for 2026-05-04 (the first clean full-day session under the post-persistence-fix infrastructure) is missing roughly 80%+ of the ticks the consolidated tape contains.** Historical re-fetch via `ibkr_tick_fetcher.py` for CNSP on 2026-05-04 had already pulled **291,826 ticks for the first 3.5 hours of the session** when this report was started — vs. a live-cached **241,717 ticks for the entire 16-hour session.**

This is not a regression of the previously-known persistence gap (`project_tick_cache_persistence_gap.md`, where pre-2026-05-01 cache was missing ~60%). The 2026-05-01 persistence fixes (resume + IBKR gap-bridge, per `project_session_resume_deployed.md`) addressed *one* leak but **not** the underlying root cause: **the live `reqMktData` feed is materially incomplete vs. what `reqHistoricalTicks` returns for the same period.**

Implication: every backtest built on `tick_cache/` data is built on an inconsistent data set — older dates with backfilled (= complete) ticks for symbols Manny chose to fill, plus newer dates with live-captured (= ~13–20% complete) ticks. The Stage 1 + Stage 2 + Stage 3 wave-breakout research and the squeeze YTD validation are all built on this mixed-quality data.

---

## Evidence

### CNSP, 2026-05-04 — full clean live session

| Source | Coverage | Tick count |
|---|---|---:|
| Live cache (full 16h session, 04:00 → 19:58 ET) | 16h | **241,717** |
| Historical re-fetch (in flight at report time) | first 3.5h (04:00–07:34 ET) | **291,826** (still climbing) |

Linear extrapolation: full-day historical fetch ≈ **1.3M+** ticks. Even if extrapolation overstates by 30%, we're still talking ~5–7× more ticks than the live capture.

### Yesterday's session was NOT a degraded run

- `BOOT: COLD start (reason=no_marker)` at 04:01 ET
- 16-hour session, clean shutdown at 20:00 ET
- 95 symbols cached
- Heartbeats showed `conn=OK` throughout
- No watchdog kills, no IBKR farm disconnections in the log
- Tick flush thread alive entire session (writes every 30s per `WB_SESSION_FLUSH_SEC=30`)

Per top-symbol counts in cache for 5/4:

| Symbol | Live ticks (full day) |
|---|---:|
| CNSP | 241,717 |
| PN | 159,547 |
| CRE | 109,398 |
| NIVF | 106,215 |
| CLNN | 103,978 |
| FATN | 5,904 |
| KBSX | 1,117 |

These look like substantial captures *until* we compare to historical for the same day.

### Before-fix vs after-fix isn't the issue

The previous persistence-gap finding (`project_tick_cache_persistence_gap.md` from 2026-04) documented:
> Tick cache missing ~60% of live's data. MYSE 04-16: 682K → 1.66M ticks after refetch.

That was attributed to a flush-loop bug that lost ticks during write. The 2026-05-01 fix made the flush atomic + added a gap-bridge for crash recovery. **It did not address the live-feed-vs-historical-feed delta.** Yesterday was clean: no flushes lost, no crashes, no resume gaps. And we still missed ~80%.

So this is a different root cause from the original gap, with worse magnitude.

---

## Why this is critical

### 1. Backtest baseline is unreliable

The Stage 1 + Stage 2 wave-breakout research processed `tick_cache/2026-01-02 → 2026-04-30` to identify 15,648 waves and 547 hypothetical trades. Those tick caches are a mix of:

- **Backfilled days** (post-`project_tick_cache_persistence_gap.md`): re-fetched via `ibkr_tick_fetcher.py`. Probably complete.
- **Live-captured days** (pre-fix and post-fix alike): subject to whatever feed gap we've now uncovered.

We cannot tell from the backtest results which days fell into which category. The 547 trades may be derived from selectively-complete data.

The same caveat applies to:
- Squeeze's "honest baseline: $30K → $209,807 (+599.4%)" YTD result
- The V8b candidate's PF 2.01, +$154K projection
- Compounding sim's $30K → $166K projection
- All 14 Stage 2 variant comparisons
- The squeeze's prior optimization studies

**None of these are necessarily wrong**, but they are now suspect until we re-validate against complete data.

### 2. Live trading edge is materially different from backtest

If the live bot only sees ~13–20% of trades, then:

- **Wave detection misses smaller intra-bar oscillations** — the 0.75% magnitude gate may be hitting on very different price points than backtest assumed.
- **Bar OHLC drifts** — bar high/low computed from sparse ticks vs full tape gives different extremes.
- **MACD computed on different bar closes** is not the same MACD the historical sim computed.
- **Trail-stop activation lags** — peak tracking is downsampled.
- **Stop hits are more "gappy"** — between the ticks we see, price can move much further than we think it has.

This is consistent with what we observed today on the WB trades: the −1.35R to −1.89R realized losses (vs intended −1R) have a slippage component, but the *gap* magnitude (price moving past stop by $0.03–$0.07) suggests we're missing intermediate ticks that would have triggered exits earlier.

### 3. Historical fetch is not infinite — IBKR ages out tick history

`reqHistoricalTicks` does retain ticks for a window (typically days for stocks). If we wait too long to backfill, we lose the data permanently. Currently 5/4 is recoverable; older live-captured days may already be partially aged out.

---

## Hypotheses for cause

### H1: IBKR market-data subscription tier limits live update rate

**Most likely.** IBKR's `reqMktData` is documented to deliver tick events subject to:

- **Account-level subscriptions.** The "US Securities Snapshot and Futures Value Bundle" (default for IB paper) provides delayed/sampled data. Real full-tape requires paid subscriptions like:
  - "NASDAQ (Network B/UTP)" — $24.50/mo
  - "NYSE (Network A/CTA)" — $24.50/mo
  - "OPRA" — for options
- **Per-line throttling.** IBKR typically caps reqMktData at "best 250ms updates per line" — meaning even with full subscriptions, the bot sees one snapshot per ~250ms per symbol, NOT every tick. A symbol trading 50 ticks/sec would deliver 4 events/sec to the bot.

**Concrete check needed:** what subscriptions does Manny's IBKR account currently have? Login to IBKR Account Management → Settings → User Settings → Market Data Subscriptions.

If subscriptions are missing/incomplete, that's part of it. Even with full subs, the 250ms throttle would explain a 4–10× gap on liquid names — close to what we observe (5–7× implied gap on CNSP).

### H2: We're using generic tick "233" (RTVolume); other tick types may be richer

`reqMktData(contract, '233', False, False)` requests RTVolume — which streams trades. This is the right product family. But IBKR also offers:

- Generic tick **236** (Shortable / Shortable Shares) — not relevant here
- Generic tick **293** (Trade Count) — gives count but not full ticks
- `reqTickByTickData` — separate API call. Returns "AllLast" or "Last" tick types. **Believed to be uncapped at the same throttle as `reqMktData`.** This may be the answer — we may need to migrate from `reqMktData('233', ...)` to `reqTickByTickData(... 'AllLast' ...)`.

### H3: The bot's tick callback is dropping events under load

Less likely but worth ruling out. The bot's tick callback path:

```
IBKR ws → ib_insync event loop → on_ticker_update(tickers) →
  for each ticker in update batch: _process_ticker(ticker) →
    state.tick_buffer[symbol].append(...) + bar_builder.on_trade(...)
```

If the event loop falls behind during high-volume bursts, `pendingTickersEvent` may merge multiple updates into a single delivery, with the bot only seeing the latest snapshot rather than every individual print. This would explain a 7× gap during peak volume but should be ~1× during quiet periods. Doesn't fully match observations (gap appears uniform across the session).

**Ruling-out check:** instrument the tick callback to count `tickers` per `on_ticker_update` invocation. If we average 1.0 tickers/event, no merging. If 5+ tickers/event, the IB stream is batching and we're potentially losing per-tick granularity.

### H4: `reqHistoricalTicks` returns more than the consolidated tape

Unlikely but worth noting. If `reqHistoricalTicks` includes off-exchange / dark-pool prints that aren't broadcast in real-time, the live feed wouldn't see them. That's a fundamental data delivery difference, not a bot-side bug. If true, **closing this gap may be impossible regardless of subscription tier.**

We can test this by comparing `reqHistoricalTicks` output against a known-good consolidated-tape source (e.g., Polygon, Databento) for the same symbol/period.

---

## Recommended research path

In order of cost/risk:

1. **Verify current IBKR subscriptions.** (Free, 5 min) — Manny logs into Account Management and reads back the active market-data subscriptions. If any of NASDAQ TotalView / NYSE OpenBook / consolidated tape are missing, that's hypothesis H1 confirmed in part.

2. **Complete the in-flight CNSP audit.** (~10 min) — let `ibkr_tick_fetcher.py CNSP 2026-05-04` complete. Report total tick count + ratio vs live capture.

3. **Test `reqTickByTickData` as the live data source.** (~1-2 hours) — write a small standalone script that subscribes to one symbol via `reqTickByTickData('AllLast')` for, say, 30 minutes during market hours. Save ticks to a file. Compare against historical fetch for the same window. If 1:1 match, switch the bot's market-data subscription mechanism.

4. **Instrument the bot's tick callback** for batch sizes / drop counts. (~30 min) — add a counter to `_process_ticker` and `on_ticker_update`. Run for one session. Confirm/rule-out H3.

5. **Cross-check `reqHistoricalTicks` against a consolidated-tape reference.** (~few hours, requires non-IBKR data source) — if Manny doesn't have a Polygon/Databento subscription, this might require signing up for a free Polygon trial. Validates H4.

6. **(If H2 confirmed)** rebuild the bot's market-data subscription path to use `reqTickByTickData`. Re-run regression tests. Deploy.

7. **(Long-term)** consider whether the *backtest* data needs to be re-fetched for all post-2026-05-01 live days too — i.e. once we have complete data delivery, also re-fetch May-2026 onwards via historical fetcher to update `tick_cache/` to a uniform-quality source.

---

## What does NOT change today

- The live bots stay running. Squeeze on main and WB on sub-bot are exposed to the same data feed and have always been. Today's WB winner (FATN +$1,534 / +2.08R) was real — it just used a downsampled-but-correlated tape, which is what live trading on this feed always sees.
- Stage 3 paper validation continues. The point of paper validation is to detect exactly this kind of issue.
- The orphan-adopt fix from earlier today is unrelated and remains valid.

---

## Files & commit reference

- This report: `cowork_reports/2026-05-05_live_tick_gap_critical.md`
- Audit baseline snapshot: `tick_cache_audit_2026-05-04/` (95 .json.gz files copied at 12:19 MT 5/5)
- In-flight fetch log: `logs/audit/cnsp_fetch_20260505_1235.log` (will append to until completion)

When the CNSP fetch completes, this report will be amended with the final ratio.

---

*If the historical 60% gap was a flush-buffer bug, this 80%+ gap is a feed-architecture issue. Different root cause, different fix surface, but same severity for Manny's edge.*
