# Overnight Session — Flag Battery + Alpaca Sub-Bot Build

**Date:** 2026-05-04 (work done 2026-05-03 evening through 2026-05-04 ~00:40 MT)
**Author:** CC
**Status:** SHIPPED — sub-bot wired into 02:00 MT cron, monitoring armed
**Branch:** v2-ibkr-migration

---

## Headline

Three things happened tonight:

1. **YTD post-backfill backtest** completed cleanly: $30K → $209,807 (+599.4%) on the refilled IBKR-tick cache. This is the new honest baseline, replacing the Apr-14 $917K Alpaca-bar artifact (already debunked in commit `19671c0`).

2. **Stage-2 flag battery** of 10 unused-but-reachable Class-A env flags: only `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED` cleared the 5% Stage-3 threshold (+7.2%, +$15,153). Several flags were materially negative (3tranche −16.3%, partial_exit −12.3%, runner_detect −6.1%). Stage 3 combo testing pivoted to deferred — only one strong winner makes the combo battery uninteresting.

3. **Alpaca sub-bot built end-to-end** for live A/B testing of the data-feed hypothesis. `bot_alpaca_subbot.py` runs alongside `bot_v3_hybrid.py` from the 02:00 MT cron, mirrors the main bot's watchlist, executes through `AlpacaBroker`, and writes isolated state. Main bot is untouched.

The Apr-14 $917K controversy — does Alpaca data inflate backtests? — instead of being settled by argument, will now be settled empirically by running both feeds in production tomorrow.

---

## YTD Post-Backfill Backtest

**Trigger:** Yesterday's full-year tick refetch via `ibkr_tick_fetcher.py` finished at 11:17 MT today (47 symbol-dates fetched, 41 cache files improved). Per Manny's directive, kicked off the YTD backtest immediately against the refilled cache to validate the new baseline.

**Run:**
```
python3 run_ytd_backtest.py \
  --start 2026-01-02 --end 2026-04-30 \
  --squeeze-only --start-equity 30000
```

Log: `logs/ytd_backtest_post_backfill_20260503_1117.log`

**Result:**
- 84 trading days
- 179 trades, 31W/24L (17% WR)
- $+179,807 squeeze-only
- $30K → **$209,807 (+599.4%)**

Trajectory matches the honest baseline (`project_ytd_baseline_truth.md`: $10K → $150K, scaled). Good.

---

## Stage 2 Flag Battery — Single-Variable YTD Sweep

**Hypothesis:** Many `WB_*_ENABLED` flags are off by default (defensive). Now that the cache is honest, are any of these gates costing PnL? Test each one solo on full YTD against the $209,807 baseline.

### Stage 1 triage (Explore agent)

Triaged ~70 unused flags into reachable+meaningful (Class A), reachable+minor (Class B), or orphan (Class C). Class-C drops included whole feature families that aren't wired into the squeeze-only sim path: `WB_VR_*` (Volume Reclaim — separate strategy module), `WB_SHORT_*` (live-only), `WB_BOX_*` (deferred to v2), `WB_L2_*` (no L2 in squeeze detector), `WB_EPL_VR_*` (gated by parent EPL_ENABLED that simulate doesn't honor for sims), `WB_SQV2_*` (only fires under WB_SQUEEZE_VERSION=2).

**Class A shortlist (10 flags):** `LEVEL_MAP`, `SQ_RUNNER_DETECT`, `SQ_DYNAMIC_ATTEMPTS`, `SQ_PARTIAL_EXIT`, `SEED_GATE` (currently ON, flipped OFF), `SQ_SEED_STALE_GATE` (currently ON, flipped OFF), `SQ_WIDE_TRAIL`, `3TRANCHE`, `VOL_FLOOR`, `PARABOLIC_REGIME`.

### Stage 2 execution

Wrote `run_flag_battery.sh` (sequential to avoid `ytd_backtest_state.json` write races; concurrent runs would clobber each other's resume state file). Each run: 84 trading days, ~15 min wall clock. Total battery: ~2.5 hrs.

### Results

| Flag | Setting | Final Equity | Δ vs Baseline | Trades | Read |
|------|---------|-------------:|--------------:|-------:|------|
| `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED` | 1 | $224,960 | **+$15,153 (+7.2%)** | 188 | ✓ Bonus attempts on profitable days unlock 9 additional trades for ~$15K |
| `WB_PARABOLIC_REGIME_ENABLED` | 1 | $213,538 | +$3,731 (+1.8%) | 179 | Marginal positive — multi-signal parabolic detection helps slightly on existing trades |
| `WB_LEVEL_MAP_ENABLED` | 1 | $209,807 | $0 | 179 | Inert — no resistance zones triggered any blocks on this YTD |
| `WB_SEED_GATE_ENABLED=0` | 0 | $209,807 | $0 | 179 | Inert — no entries were being suppressed by stale-seed gate |
| `WB_SQ_SEED_STALE_GATE_ENABLED=0` | 0 | $209,807 | $0 | 179 | Inert — no arms had stale triggers when seed completed |
| `WB_VOL_FLOOR_ENABLED` | 1 | $209,807 | $0 | 179 | Inert — vol floor never tripped |
| `WB_SQ_WIDE_TRAIL_ENABLED` | 1 | $202,986 | −$6,821 (−3.3%) | 180 | Wider trail → more give-back on winners |
| `WB_SQ_RUNNER_DETECT_ENABLED` | 1 | $197,062 | −$12,745 (−6.1%) | 179 | 3× wider trail for fast runners is net-negative on this YTD |
| `WB_SQ_PARTIAL_EXIT_ENABLED` | 1 | $183,951 | **−$25,856 (−12.3%)** | 179 | 50/50 partial-at-2R caps runner upside vs current 90% core |
| `WB_3TRANCHE_ENABLED` | 1 | $175,556 | **−$34,251 (−16.3%)** | 179 | T1+T2+T3 + forced classic exits chops up runners |

**Mechanism summary:** `dynamic_attempts` *adds* trades (179→188, +9 entries on profitable days), the rest with same trade count change *exit quality only*. Anything that loosens exits hurts — current squeeze exits are tight on purpose.

### Stage 3 disposition

**Decision: deferred.** With only `dynamic_attempts` clearing the 5% threshold, the only meaningful combo would be `dynamic_attempts + parabolic_regime` (+9% combined-if-additive, but probably non-additive). The combo battery's information value is low and Manny prioritized the sub-bot build over Stage 3.

**Recommended deployment** (when ready, low risk): set `WB_SQ_DYNAMIC_ATTEMPTS_ENABLED=1` in `.env`. Single env flip, +7.2% expected. Adds re-arm headroom on profitable days, doesn't change losing-day behavior.

---

## The $917K Discussion

Manny pushed back on the framing that the Apr-14 $917K YTD figure was "fake," asking: if Alpaca data is real market data, why is using it invalid? This was the right question, and the answer led to the sub-bot build.

### The conceptual answer

Both Alpaca and IBKR ticks are real. But:

- **Layer 1 (the headline):** simulate.py had a silent fallback to Alpaca's pre-aggregated 1-minute bars when `tick_cache` was missing. Pre-aggregated 1m bars have *no intra-minute order* — bot reacts tick-by-tick within a minute, but a 1m bar is just OHLC+V. Different seed context (PM_HIGH, EMA, VWAP) → different SQ arm prices → different entries.

- **Layer 2 (subtler):** Even cache-hit days were dirty because `cache_tick_data.py` (deleted in `19671c0`) was literally titled "Cache **Alpaca** tick data." Cached ticks were Alpaca's, not IBKR's. Different exchanges, different consolidation rules, different filtering — for the same setup on the same date, the BIRD trade *sign-flipped* from −$1,909 (Alpaca data) to +$4,206 (IBKR-bars-from-IBKR-ticks).

- **The validity test isn't "is the data real"** — it's "does the backtest data path match what the live bot consumes." Live bot reads IBKR ticks, so backtests need IBKR ticks. Alpaca-fed backtests describe an Alpaca-fed bot, which is not the bot we run.

- **Empirical proof already on file:** Manny's 2026-04-20 live day on WLDS (−$85) didn't reproduce the inflated backtest forecast. Live runs on IBKR. The honest IBKR-tick backtest (today's $209,807) matches what live can plausibly produce.

### The empirical answer (in flight)

Manny's instinct: instead of arguing this conceptually, run *both* feeds in production on the same setups and measure divergence in real time. → motivated the sub-bot build below.

---

## Alpaca Sub-Bot Build

### Goal

A parallel `bot_alpaca_subbot.py` that:
1. Mirrors `bot_v3_hybrid.py` exactly except for **data feed** (Alpaca instead of IBKR) and **execution** (Alpaca paper account instead of IBKR paper account).
2. Reads the same watchlist (no separate scanner — consumes main bot's `session_state/<today>/watchlist.json`).
3. Mirrors the main bot's symbol-seeding behavior (4 AM ET → now historical seed, replayed through identical `TradeBarBuilder` + `SqueezeDetector.begin_seed/end_seed`).
4. Writes isolated state (own session_state, own tick_cache, own logs).
5. Auto-starts from `daily_run_v3.sh` alongside the main bot.
6. Doesn't touch `bot_v3_hybrid.py`.

### Key architectural decision: drop-in shim, not rebuild

Considered three approaches:

- **A.** Resurrect V1 `bot.py` from `archive/v1_chain/`. Rejected — different strategy (V1 MP-primary), confounds the comparison.
- **B.** Build a slim sub-bot from scratch importing strategy modules. Rejected — `bot_v3_hybrid.py` is 3,465 lines with ~30 IBKR touchpoints; replicating manually is error-prone and slow.
- **C.** Copy `bot_v3_hybrid.py` → `bot_alpaca_subbot.py`, build `alpaca_feed.py` as a drop-in `ib_insync.IB` replacement, and surgically swap two imports + a few hardcoded paths. **Chose C.**

The drop-in shim approach reduces the bot-side diff to ~10 lines. Every `state.ib.reqMktData(...)`, `state.ib.reqHistoricalTicks(...)`, `state.ib.sleep(...)`, `pendingTickersEvent`, `errorEvent`, `qualifyContracts(...)` call works unchanged because `AlpacaFeed` exposes the same surface backed by Alpaca's `StockDataStream` + `StockHistoricalDataClient`.

### What was built

**`alpaca_feed.py` (new, ~24KB)** — `ib_insync.IB`-shaped wrapper:
- `StockContract` (drop-in for `ib_insync.Stock`)
- `HistoricalTickStub` / `HistoricalBarStub` (drop-ins for IB's tick/bar shapes)
- `AlpacaTicker` (`.last`, `.lastSize`, `.contract`, `marketPrice()` — what `_process_ticker` reads)
- `_Event` (for `pendingTickersEvent += handler` syntax)
- `AlpacaFeed.connect/disconnect/isConnected/sleep/qualifyContracts/reqMktData/cancelMktData/reqHistoricalTicks/reqHistoricalData`
- Threading: stream thread runs `StockDataStream.run()` (its own asyncio loop). Trade events are coroutine-handled, enqueued to a thread-safe queue, drained on the main thread by `sleep()` which fires `pendingTickersEvent` with the set of updated tickers — same shape `ib_insync` delivers.

**`bot_alpaca_subbot.py` (copy of `bot_v3_hybrid.py` with surgical edits)** — diff vs. main:
1. Header docstring rewritten.
2. Top of file (BEFORE module imports that read env): `os.environ["WB_BROKER"] = "alpaca"`, `os.environ.setdefault("WB_SESSION_DIR_NAME", "session_state_alpaca")`, `os.environ.setdefault("WB_TICK_CACHE_DIR_NAME", "tick_cache_alpaca")`.
3. `from ib_insync import IB, Stock, ...` → `from alpaca_feed import AlpacaFeed as IB, Stock`.
4. `LimitOrder`/`MarketOrder`/`util` stubbed to `None` (unused; order flow goes through `state.broker = AlpacaBroker`).
5. Two hardcoded `tick_cache/` paths in `seed_symbol_from_cache` and `save_tick_cache` rewritten to `ss.tick_cache_dir(today)` (env-aware).
6. `run_scanner()` rewritten as no-op — sub-bot doesn't run its own scanner.
7. `poll_watchlist()` rewritten — instead of reading `watchlist.txt` (Databento bridge), reads `session_state/<today>/watchlist.json` from the **main bot's** path (hardcoded "session_state", not the env-controlled one) and mirrors those symbols. Per-call resolved so date rollover works.
8. Banner header updated to identify itself as the Alpaca sub-bot.

**`session_state.py` (modified, additive)** — added `WB_SESSION_DIR_NAME` and `WB_TICK_CACHE_DIR_NAME` env vars with defaults preserving current behavior. Resolved per-call (not at import) so the sub-bot's env override at module top works. Main bot is unaffected (unset env → same defaults).

**`daily_run_v3.sh` (modified)** — additive changes only:
- New `SUBBOT_PID` variable + cleanup line.
- Pre-flight imports both modules.
- Added `pkill -f "bot_alpaca_subbot.py"` to stale-cleanup.
- After main bot's 15s health check passes, launches sub-bot in parallel: `python3 bot_alpaca_subbot.py >> "$SUBBOT_LOG" 2>&1 &`. **Non-fatal** — if sub-bot crashes within 15s, log a WARN and continue without it. Main bot must keep running.
- Watchdog loop monitors both PIDs; if sub-bot dies main bot continues (sub-bot is non-critical).
- Shutdown signal kills both.
- File hashes for `bot_alpaca_subbot.py` and `alpaca_feed.py` logged for traceability alongside `bot_v3_hybrid.py`.

### What was NOT touched (per directive)

- `bot_v3_hybrid.py` (md5: `1725f394e141ae220cc507da3b92fc02`)
- IBC config
- Cron entry (`0 2 * * 1-5 ...`)
- `.env` (Alpaca keys + `WB_BROKER=ibkr` for main bot stay as-is)

### Verification

**`alpaca_feed.py` smoke tests (after-hours, AAPL):**
- `connect()` — clean, stream thread armed.
- `reqHistoricalTicks` — 50 ticks fetched from a 5-min window. Time/price/size all parsed correctly.
- `reqHistoricalData` — 396 1-min bars over 1 day. OHLCV all correct.
- `reqMktData` + `sleep(12)` — websocket subscribed, no ticks delivered (markets closed, expected). No errors.

**`AlpacaBroker` (broker.py, already-existing class):**
- Account equity: $30,194.74 (matches Manny's baseline)
- Buying power: $120,778.96 (4× PDT — account >$25K)
- `is_shortable("AAPL")` → True
- Clean state — no open positions, no open orders.

**`bot_alpaca_subbot.py` end-to-end boot (mocked watchlist):**
1. Created `session_state/2026-05-04/watchlist.json` with AAPL.
2. Launched sub-bot (`WB_TRADING_WINDOWS="00:00-23:59"` env override to bypass dead-zone gating for the test).
3. Verified flow: BOOT COLD → banner → preflight port check → watchdog armed → Alpaca TradingClient connect → AlpacaFeed connect → tick-flush + risk-flush threads → broker init → position sync (clean) → EPL init → main loop → `📡 Sub-bot: 1 new symbols from main bot's watchlist: ['AAPL']` → `subscribe_symbol(AAPL)` → seed (no data — pre-04-AM-ET) → fallback to bars (also empty) → `✅ Subscribed: AAPL` → tick audit (no live ticks, expected after-hours) → resubscribe attempt → graceful SIGINT shutdown → session summary.
4. Cleaned up test artifacts (`session_state/2026-05-04/` + `session_state_alpaca/2026-05-04/` removed).

### What expects to happen tomorrow morning

Per `daily_run_v3.sh` flow:

1. **02:00 MT (04:00 ET)** — cron fires. Wakes display via `caffeinate -u`. Pulls latest code, runs preflight. IBC reused (port 4002 already up from yesterday's manual restart at 22:55 MDT — won't be killed because `daily_run_v3.sh` checks port-listening first). Live scanner starts. Main bot launches.
2. **02:01-02:05 MT** — main bot's 15s health check passes. Sub-bot launches. Sub-bot's 15s health check.
3. **04:00-12:00 ET** — both bots active. Same watchlist (sub-bot polls main's), same seeding window, same detector code. Trades on independent paper accounts.
4. **12:00 ET** — morning window closes. (Bot's `WB_TRADING_WINDOWS="04:00-20:00"` is single-window, so technically it stays active until 20:00 ET, but Manny's task here ends at the morning-session boundary.)
5. **20:05 ET** — both bots shut down by daily_run watchdog. Logs commit-and-pushed.

### Comparison artifacts available tomorrow

| | Main bot (IBKR) | Sub-bot (Alpaca) |
|---|---|---|
| Session state | `session_state/2026-05-04/` | `session_state_alpaca/2026-05-04/` |
| Tick cache | `tick_cache/2026-05-04/<sym>.json.gz` | `tick_cache_alpaca/2026-05-04/<sym>.json.gz` |
| Daily log | `logs/2026-05-04_daily.log` | `logs/2026-05-04_subbot_alpaca.log` |
| Risk file | `session_state/2026-05-04/risk.json` | `session_state_alpaca/2026-05-04/risk.json` |
| Closed trades | last 50 in `risk.json` `closed_trades` | same shape, sub-bot's |

**Diffing tick caches** for the same symbol on the same minute reveals exactly how the two feeds saw the same tape: print count, price differences, timing skew, missing/added trades. That answers the bars-from-IBKR-ticks vs bars-from-Alpaca-ticks question with primary data.

### Known limitations / deferred hardening

- **Alpaca data feed:** defaults to `iex` (free). Most low-float small-caps Manny trades have decent IEX coverage but it's *not* the consolidated tape (SIP). If the sub-bot consistently sees less volume than the main bot, that's a known feed-tier difference, not a bug. Override via `WB_ALPACA_DATA_FEED=sip` (paid).
- **AlpacaFeed.connect on reconnect:** the bot's reconnect loop calls `state.ib.disconnect()` then `state.ib.connect()`. Current `AlpacaFeed.disconnect` doesn't wait for the stream thread to die; rapid disconnect→connect could leave dueling stream threads. Mitigation: this path is only taken on actual connection loss, which is rare. If it becomes a problem, harden `AlpacaFeed._start_stream_thread` to teardown previous thread first.
- **Log noise:** sub-bot will log "TICK DROUGHT" on subscribed symbols if Alpaca's IEX feed has gaps the IBKR feed doesn't. Expected, not actionable.
- **EPL parity:** main bot has `WB_EPL_ENABLED=1`; sub-bot inherits same `.env` so EPL is also on. EPL re-entries fire on graduation criteria — if sub-bot's data feed produces different graduation timing, EPL trades may diverge. For a clean A/B of squeeze trades only, filter EPL out post-hoc when comparing.

---

## Files Inventory

### Created
- `alpaca_feed.py` — 24KB, drop-in `ib_insync.IB` replacement.
- `bot_alpaca_subbot.py` — 160KB, copy of `bot_v3_hybrid.py` with surgical edits.
- `run_flag_battery.sh` — 2KB, executes the Stage-2 single-variable battery sequentially.
- `logs/flag_battery_20260503_2058/` — battery results: 10 per-flag logs + SUMMARY.md.
- `logs/ytd_backtest_post_backfill_20260503_1117.log` — refilled-cache YTD baseline.

### Modified
- `session_state.py` — added env-controlled directory names. Backwards compatible.
- `daily_run_v3.sh` — parallel sub-bot launch + non-fatal failure handling. Backwards compatible.

### Untouched
- `bot_v3_hybrid.py`
- IBC config (`~/ibc/config.ini`)
- Cron (`crontab -l`)
- `.env`

---

## Open Questions / Future Work

1. **Stage 3 combos** — deferred. Only meaningful one is `dynamic_attempts + parabolic_regime`. Run if/when there's free compute time.

2. **Deploy `dynamic_attempts`** — the +7.2% Stage-2 winner is safe to deploy (additive, doesn't change losing-day behavior). One-line `.env` change. Awaiting Manny's call on timing.

3. **Sub-bot v2 features** (deferred from tonight's "full ship"):
   - Resume on intra-day restart (sub-bot is currently cold-start each day; main bot supports resume via `WB_SESSION_RESUME_ENABLED`).
   - `AlpacaFeed.disconnect` thread-teardown hardening.
   - Possibly: separate sub-bot `.env` for parameter-divergence experiments (currently shares main bot's `.env`).

4. **A/B fairness question** — for clean comparison, decide whether to:
   - (a) leave both bots fully on, filter to squeeze-only trades when comparing (post-hoc cleanup)
   - (b) temporarily flip main bot's `WB_EPL_ENABLED=0` for one trading day so both bots run pure squeeze (cleaner direct comparison)
   - Currently doing (a). Manny TBD.

5. **Tick-cache diff tooling** — once a few days of paired tick caches accumulate, write a small script that diffs `tick_cache/<date>/<sym>.json.gz` vs `tick_cache_alpaca/<date>/<sym>.json.gz` and reports: tick count delta, price delta on shared timestamps, timing skew distribution. That's the primary-data answer to the data-feed-divergence question.

---

## Monitoring (active during this report)

`/loop` self-paced, currently armed:
- **Monitor (persistent)** — tailing `cron_2026-05-04.log` + `2026-05-04_daily.log` + `2026-05-04_subbot_alpaca.log` for boot events, crashes, watchdog kills, ENTRY SIGNAL, ORPHAN, connection loss, exit_trade.
- **Fallback heartbeat** — 60min (~01:39 MT) so I'm awake near 02:00 MT cron fire even if the Monitor somehow misses the boot logs.
- After boot is confirmed healthy, will check every 15-30 min through the morning window (until 10:00 MT / 12:00 ET) and report a final session summary.

---

## Memory updates

Two new entries written to `~/.claude/projects/-Users-duffy/memory/`:

- `feedback_daily_run_v3.md` — V2 cron uses `daily_run_v3.sh` not `daily_run.sh` (with reuse-existing-gateway logic). Captured because I cited the wrong script earlier in the session.
- `project_alpaca_subbot.md` — sub-bot architecture summary so a future session knows where the parallel bot lives without rediscovering it.

---

**End of report.**
