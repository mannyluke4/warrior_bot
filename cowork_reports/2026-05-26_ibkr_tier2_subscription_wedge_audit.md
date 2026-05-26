# Cowork Audit: IBKR Tier-2 reqMktData Subscription Wedge (2026-05-26)

**Owner:** CC (this session)
**Status:** Diagnosis complete to the extent the live evidence supports. Three hypotheses ruled out. Root cause not yet proven. No code change recommended without further data.
**Branch:** `v2-ibkr-migration` HEAD `2be7efe`

---

## TL;DR

- Main bot ran ~10 hours after the 02:00 MT cron (PID 12300). Subscribed ~95 symbols including MNTS, which gapped from prior close $7.38 to a $15.47 HOD (+110%).
- For the entire morning session, the bot's `reqMktData(symbol, '233', False, False)` stream for MNTS delivered roughly **25 ticks/hour**. Per-minute bar volume printed `V=200–1,100` shares.
- A side `clientId=99` query to the **same Gateway, same symbol, same timeframe** returned real volume: **624,859 shares total, 60K–190K shares/minute** during the morning ramp. IBKR had the data; the bot's subscription was wedged.
- The bot's drought-based subscription health check missed it because the wedged subscription wasn't *silent* — it delivered ~1 tick every ~3 minutes, never a true zero-tick drought.
- Restart of `bot_v3_hybrid.py` via `daily_run_v3.sh` (Gateway reused, fresh TWS API session) restored full streaming. Next 5-min chart line on MNTS post-restart: `V=27,230, vol_ratio=56.2x, bars=50`.
- **Cost of the incident:** today's pre-market and morning squeeze opportunities. MNTS specifically: missed the entire run from $7.38 → $15.47.

---

## Timeline (all times ET unless noted)

| Time | Event |
|---|---|
| 2026-05-25 22:13 MT | CC launched `gatewaystartmacos.sh` directly; failed with "Error: process is already running" (lock from prior IBC instance). |
| 2026-05-25 22:13–22:15 MT | Pre-existing IBC instance crash-looping every 60s on "login dialog not displayed within 60s" — display asleep. |
| 2026-05-25 22:15 MT | CC killed IBC restart loop. |
| 2026-05-25 22:18 MT | CC fired `daily_run_v3.sh` (which runs `caffeinate -u` first to wake display). Gateway came up on port 4002 in 10s. Bot dress rehearsal launched, ran ~1 minute, exited cleanly at 22:19 MT (past trading windows). |
| 2026-05-26 02:00 MT | Cron fired today's `daily_run_v3.sh`. Reused existing Gateway (port 4002 in use). Bot started PID 12300, sub-bots 12321/22/23. |
| 04:05 ET | First scanner symbology mapping for MNTS — bot's `subscribe_symbol()` called. |
| 04:10 ET | First MNTS chart print: `V=800, avg_vol=0, bars=0`. **Already in degraded state.** |
| 04:00–10:15 ET | MNTS chart prints stay sparse: V=200–1,100 per minute throughout the morning ramp. Underlying tape ran $9.82 → $15.47. |
| 12:03 ET | CC asked "how long has the bot been watching MNTS" — answered "8 hours, but it isn't moving" based on a single 04:10 ET chart line. **This was wrong.** |
| 12:05 ET | Manny: "Several squeeze events should have triggered. Price well above 9.88 all day. Made $7k swinging TV paper." |
| 12:10 ET | CC ran IBKR direct query with `clientId=99`. Confirmed real volume: 624K shares total, 130K/min average during run. **Bot's subscription wedged, not the IBKR data feed.** |
| 12:15 ET | CC killed `daily_run_v3.sh` PID 12234. Cleanup trap fired, all bots terminated, logs committed/pushed. |
| 12:16 ET | CC re-launched `daily_run_v3.sh`. New bot PID 16582, sub-bots 16606/07/08. Gateway reused (java 10962). |
| 13:10 ET | First post-restart MNTS chart: `V=27,230, vol_ratio=56.2x, avg_vol=485, bars=50`. **Subscription delivering full streaming data.** |

---

## Evidence

### Side-by-side: bot's pre-restart vs post-restart view of MNTS

| Field | Pre-restart (10:15 ET) | Post-restart (13:10 ET) | IBKR direct (12:10 ET) |
|---|---|---|---|
| Last price | $14.43 | $13.26 | $13.25 |
| Today's HOD seen | $14.78 | $14.78 (from history) | $15.47 |
| Per-minute V | 200–1,100 shares | 27,230 shares | 60K–190K shares |
| avg_vol | 0 | 485 | (n/a) |
| vol_ratio | 0.0x | 56.2x | (n/a) |
| bars built | 0 | 50 | (n/a) |
| EMA9 | none | 13.38 | (n/a) |
| Squeeze state | N/A (no indicators) | IDLE | (n/a) |

The bot was getting **real prices** (the chart did print $14.43 etc.), but at sparse update rate. So the failure mode is *not* "data path completely dead" — it's "streaming subscription delivers occasional snapshots instead of full tick stream."

### IBKR direct query results (12:10 ET via `clientId=99`)

```
MNTS  bid=13.22  ask=13.28  last=13.25  lastSize=800
       high=15.47  low=11.86  close=7.38  volume=624,859

Last 10 1-min bars (TRADES, 12:55–13:04 ET):
  12:55  O=13.86  H=13.92  L=13.6   C=13.63  V=167,061
  12:56  O=13.63  H=13.66  L=13.4   C=13.5   V=192,814
  12:57  O=13.48  H=13.54  L=13.28  C=13.36  V=143,384
  12:58  O=13.36  H=13.4   L=13.17  C=13.25  V=189,949
  12:59  O=13.24  H=13.39  L=13.18  C=13.39  V=80,275
  13:00  O=13.35  H=13.6   L=13.32  C=13.58  V=158,726
  13:01  O=13.6   H=13.66  L=13.41  C=13.48  V=119,233
  13:02  O=13.49  H=13.5   L=13.32  C=13.36  V=79,088
  13:03  O=13.34  H=13.37  L=13.21  C=13.21  V=62,093
  13:04  O=13.21  H=13.28  L=13.1   C=13.22  V=119,391
```

Bot's chart prints during that exact 10-minute window showed `V=200–1,100`. Ratio of IBKR-real to bot-observed: ~100–1000×.

### Tier-1 promotion did run; MNTS just wasn't promoted

```
[TIER] PROMOTE CODX reason=volume_top2 capacity=2/5
[TIER] PROMOTE VCIG reason=wave_observing capacity=1/5
[TIER] STATUS tier1=['CODX', 'VCIG'] tier2=3 capacity=2/5
```

Tier-1 promotion logic (`manage_tier1_subscriptions`, `bot_v3_hybrid.py:1491`) executed correctly. It promoted 2 of 5 available slots. MNTS had `compute_tier1_priority() == 0` because:
- No detector signals reached ARMED/PRIMED/WAVE_OBSERVING (no volume baseline)
- Not in top-2 of 5-min volume rank (volume buckets fed by the wedged subscription = tiny)

But this is a **symptom**, not the cause. After restart MNTS was *still* in Tier 2 (not promoted to Tier 1) yet received full streaming data. So Tier-2 `reqMktData` is not architecturally limited to sparse data — it can and does deliver full streams when working.

---

## What I (CC) got wrong, and why it matters

### Failure 1: "Genuinely quiet morning" (12:03 ET)

I looked at one chart line on MNTS (04:10 ET, $9.82, low PM volume) and concluded the stock wasn't moving. The bot had printed dozens of later chart lines showing $13–14+ prices that I didn't grep for. Worse, memory `feedback_quiet_means_broken` is explicit: *100% of the time, "quiet" has been wrong.* I cited the rule and walked it back anyway, because three sub-bots all reported identical "healthy" tick counts.

**The uniformity itself was the bug.** Three sub-bots consuming the same engine-socket fanout will always report identical counts whether the upstream is real or broken. Uniformity across them is evidence they're reading the same stream, *not* evidence the stream is healthy.

I've updated `feedback_quiet_means_broken.md` with this trap explicitly called out (rule #6) and the IBKR direct-query diagnostic (rule #7).

### Failure 2: First root-cause hypothesis — architectural circular dependency

I (and an Explore agent) initially theorized:
> "Tier 2 = snapshot-mode at 250ms minimum interval. Squeeze detector can't arm without volume baseline. Without arming, never promoted to Tier 1. Therefore stays sparse forever."

**Disproved by post-restart evidence.** MNTS in Tier 2 post-restart delivers V=27,230/min. Tier-2 `reqMktData(c, '233', False, False)` is a *streaming* subscription (not snapshot), and when working delivers full tick rates. The hypothesis confused the IBKR API semantic of `snapshot=False` with the bot's "snapshot tier" naming.

### Failure 3: Second root-cause hypothesis — cross-day Gateway session reuse

I theorized that yesterday's dress rehearsal left orphan state on the Gateway that today's bot inherited.

**Manny invalidated this directly:** the Gateway auto-restarts nightly at 20:30 MT and has been doing so for a month under the same operational pattern, with no prior wedges. Cross-day session reuse is the daily norm, not the anomaly.

### Failure 4: Third root-cause hypothesis — broker-call socket contention

After the WB_BROKER=alpaca→ibkr flip in `2be7efe`, all `state.broker.*` calls now hit `state.ib` instead of Alpaca's HTTPS endpoints. I theorized this added enough socket traffic to starve `reqMktData` deliveries.

**Disproved by inspection of `broker.py:553-575`.** Every getter (`get_account_equity`, `get_buying_power`, `get_positions`, `is_shortable`) reads from in-memory state already populated by ib_insync's connection; no fresh network calls. The only API-call broker methods (`submit_limit`, `cancel_order`) didn't fire today because no positions opened.

---

## Hypotheses still on the table

### H1 — Pre-existing low-grade Tier-2 reqMktData throttling, MNTS-class miss was just the first visible one

Memory `project_tick_cache_persistence_gap.md` documents an analogous incident on 2026-04-16: MYSE refetch showed 682K → 1.66M ticks (~60% missing in live). Was attributed to "tick cache persistence" but the actual symptom — live-vs-true volume gap — is identical to today.

If this hypothesis is correct: the bug has been present for at least 6 weeks. Most days it produces a 30–60% volume undercount that erodes arm-detection sensitivity but doesn't kill any single trade. Today happened to produce a 99% undercount on the day's best squeeze candidate.

**Test:** add observational watchdog (see "Proposed instrumentation" below). One trading day of data tells us whether wedged subscriptions are routine or rare.

### H2 — IBKR per-subscription rate limit hit early, never reset

IBKR enforces market-data subscription quotas per account. If the bot's `reqMktData` calls during pre-market exceeded some internal soft-limit, IBKR may have downgraded the stream to a slower update cadence without surfacing an error. ib_insync would receive whatever IBKR sent, with no API-level signal.

**Test:** the watchdog should log the IB error queue concurrently. If IBKR ever sent a 354/2105/2106/anything-similar warning, that's the smoking gun.

### H3 — Subscription created during pre-market half-bootstrapped state

The bot subscribes via `subscribe_symbol()` (`bot_v3_hybrid.py:1282–1316`). Sequence:
1. `reqMktData()` placed (line 1292)
2. Detector instantiated (line 1296)
3. `seed_symbol_from_cache()` runs — can take 5–30 seconds (lines 1303–1306)
4. `state.active_symbols.add(symbol)` (line 1308)

If `reqMktData` was placed during a window when IBKR's data farms were in their nightly maintenance cycle (typical ~04:00–05:00 ET when our pre-market starts), the subscription might land in a degraded state and IBKR never auto-upgrades it once the data farms come back. The post-restart subscription at 13:06 ET would naturally land in a clean state.

**Test:** watchdog comparing subscription timestamps to known IBKR data-farm maintenance windows + tick-rate observation by subscription-age bucket.

### H4 — Race between `reqMktData` and `qualifyContracts` resulting in stale contract reference

`subscribe_symbol()` qualifies the contract before `reqMktData`. If contract qualification returned a non-primary exchange variant (e.g., ARCA instead of NASDAQ for a NASDAQ-listed name), IBKR would route updates from a thin venue while the real tape prints on the primary.

**Test:** watchdog logs the `Contract.primaryExchange` and `Contract.exchange` resolved for each subscription, and compare to expected for hot movers.

---

## Proposed instrumentation (observability, not fix)

A tick-rate watchdog that runs every 60 seconds and emits a `SUBSCRIPTION_AUDIT` log line per active symbol. For each symbol, log:

| Field | Source |
|---|---|
| `symbol` | from `state.active_symbols` |
| `tier` | `state.tier[symbol]` (snapshot / tick_by_tick) |
| `observed_ticks_5m` | rolling count from `state.tickers[symbol]` callback fires |
| `observed_volume_5m` | sum of `volume` ticks over the same window |
| `ibkr_truth_volume_5m` | side `reqHistoricalData('300 S', '1 min', 'TRADES')` via `clientId=99` |
| `ratio` | observed / ibkr_truth |
| `subscription_age_sec` | `now - state.subscribed_at[symbol]` |
| `contract_primary_exchange` | `state.contracts[symbol].primaryExchange` |
| `contract_exchange` | `state.contracts[symbol].exchange` |
| `recent_ib_errors` | tail of `state.recent_errors` log |

Side-effect-free for first 1–2 trading days. Just emits the data so we can:
- Distinguish a one-off (today only) from a daily occurrence
- Correlate wedge events with subscription age, time of day, scanner batch, IBKR error queue
- Build the dataset to choose between H1–H4

After 1–2 clean days of diagnostic data, optionally turn on **auto-resubscribe action**: if a symbol's observed/truth ratio is < 0.1 for >3 consecutive cycles, automatically `cancelMktData` + `reqMktData` to refresh. Action gate behind a separate env var so we can roll observability and action separately.

**Cost:** ~150–200 lines of code in `bot_v3_hybrid.py`. ~5 IBKR API calls per minute (1 historical-data request per active symbol, but throttled to 5–10 per minute to stay well under IBKR's 60/10min historical-data limit). Storage: ~2 MB/day of audit log.

**Risk:** the historical-data API has its own rate limit (60 requests per 10 minutes). With 95+ symbols we'd need to round-robin the audit, not query every symbol every minute. Implementation needs care.

---

## Suggested directive scaffolding (for Cowork/Manny review)

Three independent decisions:

1. **Ship observability-only first?** (Yes/No)
   - Yes = the watchdog logs but takes no action. 1–2 days, then revisit.
   - No = wait until we have a stronger root-cause hypothesis before adding any code.

2. **What is the manual mitigation in the meantime?**
   - Option A: CC monitors live during morning session and triggers manual restart on first sign of wedge (high vol_ratio with low absolute V on a known hot symbol).
   - Option B: nothing — accept the risk that today repeats — until we have evidence.
   - Option C: add a cron-driven sanity-check that runs IBKR direct queries on the top-3 watchlist symbols every 15 minutes during 07:00–12:00 ET and pages Manny if rate ratio < 0.1.

3. **Auto-resubscribe on detection?** (gated separately)
   - Default to OFF until we have one clean day of diagnostic data.
   - When ON, mid-session resubscription will cause a 1–2 second tick gap on the affected symbol. Acceptable if it gets us back into a real squeeze in time to fire.

---

## Open questions for Cowork / Manny

1. **Has anything resembling today's miss happened in the past 30 days that we wouldn't have noticed?** A morning where the bot was flat but the universe had a clear technical squeeze setup? Even one named instance from memory would validate H1.

2. **Is the 8:30 PM nightly Gateway restart actually clean every night?** The dress rehearsal yesterday at 22:18 MT was after that 20:30 MT auto-restart. Was the Gateway *also* restarted today's pre-market that I'd be aware of, or is the current Gateway (java 10962, up since 22:18 yesterday) running on yesterday's 20:30 auto-restart cycle?

3. **For the watchdog, is the per-minute `reqHistoricalData` polling cost acceptable?** This is a non-trivial increase in IBKR API traffic. Alternative is a less precise heuristic (compare observed tick rate to the rolling average across all active symbols at the same time — anomalous if 10× below median, no historical-data API needed).

4. **Are there other Tier-2 sparse incidents to look up?** The 04-16 MYSE case (in memory `project_tick_cache_persistence_gap`) — is there an audit report from that incident I should read before designing the watchdog? It might already have ground-truth observations from a similar event.

---

## Cross-references

- `feedback_quiet_means_broken.md` — updated 2026-05-26 with sub-bot uniformity trap (rule #6) and IBKR direct-query diagnostic (rule #7)
- `project_tick_cache_persistence_gap.md` — likely the same underlying bug, surfaced 2026-04-16
- `project_broker_latency_investigation.md` — 2026-05-18 — closed conclusion was "stay on Alpaca through 6/15" which is now superseded by today's IBKR flip; see entry update on 2026-05-26
- `project_live_abc_fade_gate.md` — the reason WB_BROKER flipped to ibkr (free MAIN_APCA for Variant B)
- `feedback_sim_live_divergence_inventory_2026-05-22.md` — §"Engine socket dropped ticks suspected cause of remaining arm divergences" — may be the same root cause family

---

*End of audit. CC standing by for directive.*
