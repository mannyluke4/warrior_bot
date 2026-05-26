# Directive: IBKR Tier-2 Subscription Watchdog (observability + targeted verification)

**Date**: 2026-05-26
**Branch**: `v2-ibkr-migration`
**Owner**: CC
**Source**: `cowork_reports/2026-05-26_ibkr_tier2_subscription_wedge_audit.md` (commit `ce00dd1`). MNTS ran $7.38 → $15.47 today while the bot's `reqMktData` stream delivered ~25 ticks/hour instead of the real ~130K shares/min. Memory note `project_tick_cache_persistence_gap` (2026-04-16 MYSE incident) suggests this is a recurring low-grade bug, today amplified to 99% undercount on the day's hottest setup.

**Important context (added 2026-05-26 PM)**: The Mac mini was restarted yesterday and Manny manually started Gateway last night before the 02:00 MT cron fired. This means today's wedged subscriptions were created against a freshly-started Gateway — NOT a Gateway that had been running for weeks on the normal 20:30 MT auto-restart cycle. This adds H5 to the hypothesis space (see below).
**Real-money go-live**: still ~2026-06-22 (A/B/C test keeps running unchanged).

---

**Pacing rule**: Ship the watchdog Monday. Paper accounts absorb the risk while we learn. No multi-day verification phases.

---

## Why observability before any fix

CC's audit ruled out three root-cause hypotheses (architectural Tier-2 limit, cross-day Gateway reuse, broker-call socket contention) and left four still live (H1 chronic throttling, H2 IBKR rate-limit downgrade, H3 pre-market half-bootstrapped subscription, H4 contract-qualification race). We can't pick a fix without data on which one is real — and the cheapest way to get that data is to instrument what actually happens during a normal trading session.

The watchdog has zero side-effects on trade execution. It just emits structured log lines that:
1. Tell us tomorrow morning whether MNTS-style wedges are routine or rare
2. Feed the A/B/C daily report so we can flag any day where data was suspect
3. Build the dataset to choose between H1/H2/H3/H4 over the next week

**Auto-resubscribe stays OFF for this directive.** That's a separate decision once we have 1-2 days of data.

---

## Detection design (dual-signal)

### Signal 1 — Heuristic (always-on, zero IBKR API cost)

Every 60 seconds, for each symbol in `state.active_symbols`:

- Compute `observed_volume_5m[sym]` = sum of last 5 1-minute bar volumes (we already have this — `state.tier1_volume_buckets[sym]` per `bot_v3_hybrid.py:1407`)
- Compute `median_observed_volume_5m` across all active symbols where `observed_volume_5m > 0`
- Flag `sym` as `HEURISTIC_SUSPECT` if `observed_volume_5m[sym] < median / 10` AND `observed_volume_5m[sym] < 5000`

The dual threshold avoids false positives on genuinely quiet symbols: a stock that's truly dead would have low absolute volume AND match many others at the same level (so it wouldn't be 10× below median). A wedged subscription on a hot symbol would have low absolute volume while peers stream in the hundreds-of-thousands.

This catches MNTS-class extreme misses (200/min vs 50K+ peer median = 250× below) without any IBKR API call.

### Signal 2 — Direct query (precise verification, throttled)

Every 5 minutes, pick up to 5 symbols and run `state.ib.reqHistoricalData(contract, durationStr='300 S', barSizeSetting='1 min', whatToShow='TRADES', useRTH=False, formatDate=2)` to get IBKR's ground-truth 5-minute volume.

Selection priority for the 5 slots:
1. Any symbol with an open position (always verify — money at stake)
2. Any `HEURISTIC_SUSPECT` from Signal 1 (verify the heuristic's alarm)
3. Any symbol in scanner's top-5 by gap % or PM volume (catches symbols the heuristic might be hiding — see "Chicken-and-egg note" below)
4. Round-robin through the rest of `state.active_symbols`

Compute `ratio = observed_volume_5m / truth_volume_5m`. If `ratio < 0.1`, mark `DIRECT_QUERY_WEDGE`.

IBKR historical-data quota is 60 requests per 10 minutes. 5 requests every 5 minutes = 10 per 10 minutes — well under the limit, leaving budget for other uses.

### Chicken-and-egg note (why scanner-top-N matters)

The heuristic uses observed tick rate. A wedged subscription on MNTS produced 200/min observed volume, which on a quiet day could look like "just a quiet stock" — the heuristic might miss it if the universe median is also low. The scanner-top-N path in Signal 2 closes that gap: even if heuristic missed it, the symbol is in the scanner's top-5 by gap or PM-volume rank (data path independent of the wedged subscription), and the direct query reveals truth.

---

## Implementation

### New module: `subscription_watchdog.py`

Self-contained class invoked from the main bot loop:

```python
class SubscriptionWatchdog:
    def __init__(self, state, ib, enabled: bool = False):
        self.state = state
        self.ib = ib
        self.enabled = enabled
        self.last_heuristic_at = None
        self.last_direct_query_at = None
        self.recent_audits = collections.deque(maxlen=500)  # for daily report ingest
        self.client_id_for_truth_query = 99  # match CC's audit query style
        # Optional secondary connection for truth queries to avoid main IB queue contention
        self.truth_ib = None

    def tick(self, now: datetime.datetime):
        if not self.enabled:
            return
        if not self.last_heuristic_at or (now - self.last_heuristic_at).total_seconds() >= 60:
            self._run_heuristic(now)
        if not self.last_direct_query_at or (now - self.last_direct_query_at).total_seconds() >= 300:
            self._run_direct_query(now)

    def _run_heuristic(self, now): ...
    def _run_direct_query(self, now): ...
    def _emit_audit(self, sym, fields): ...  # writes SUBSCRIPTION_AUDIT log line
```

Wire `watchdog.tick(now)` into the main loop at the same cadence as `manage_tier1_subscriptions` (around `bot_v3_hybrid.py:1504`'s caller).

### New env vars (all default OFF for safety)

```
WB_SUB_WATCHDOG_ENABLED=0           # master gate — flip to 1 to enable
WB_SUB_WATCHDOG_HEURISTIC_RATIO=10  # observed must be < median/RATIO to flag
WB_SUB_WATCHDOG_HEURISTIC_ABS_CAP=5000  # AND observed < this to flag (suppresses quiet-stock noise)
WB_SUB_WATCHDOG_DIRECT_QUERY_INTERVAL_SEC=300
WB_SUB_WATCHDOG_DIRECT_QUERY_MAX=5  # symbols per cycle
WB_SUB_WATCHDOG_WEDGE_THRESHOLD=0.1  # ratio below this = WEDGE
```

When enabled in `daily_run_v3.sh`, defaults to `WB_SUB_WATCHDOG_ENABLED=1` for Monday's run.

### Log line format

Every audit emission writes a single `SUBSCRIPTION_AUDIT` line to stdout (captured by the existing log redirection). Format is JSON for clean parsing by the daily report script:

```
SUBSCRIPTION_AUDIT {"ts": "2026-05-26T10:15:23-04:00", "sym": "MNTS", "tier": "snapshot", "obs_v_5m": 850, "median_v_5m": 47000, "ratio_obs_to_median": 0.018, "truth_v_5m": null, "ratio_obs_to_truth": null, "status": "HEURISTIC_SUSPECT", "sub_age_sec": 22100, "contract_exchange": "SMART", "contract_primary": "NASDAQ", "recent_ib_errors": []}
```

`status` is one of: `OK`, `HEURISTIC_SUSPECT`, `DIRECT_QUERY_OK`, `DIRECT_QUERY_WEDGE`.

Lines with `status: OK` are still emitted (once per cycle) so we have ground-truth audit coverage, not just exception logs.

### Daily A/B/C report integration

Extend `scripts/abc_compare_daily.py` to:

1. Grep the main-bot log for `SUBSCRIPTION_AUDIT` lines
2. Count `HEURISTIC_SUSPECT` and `DIRECT_QUERY_WEDGE` events per symbol per day
3. Add a new section to the daily markdown report:

```
## Data Quality Audit

| Symbol | Suspect events | Wedge events | Max obs/truth ratio | Notes |
|---|---|---|---|---|
| MNTS | 47 | 12 | 0.018 | wedged 04:10-12:15 ET, restarted bot to clear |
| CODX | 0 | 0 | n/a | clean |
```

4. If ANY `DIRECT_QUERY_WEDGE` events occurred, add `⚠️ DATA QUALITY DEGRADED` to the report's top-line summary so we know the day's variant comparison numbers are suspect.

---

## What this does NOT include

- **Auto-resubscribe action** — separate decision after 1-2 days of data
- **IBKR error queue parsing** — `recent_ib_errors` field is a placeholder; full implementation requires hooking `ib.errorEvent`. Acceptable to ship with `[]` for v1; add hook in v2.
- **Secondary IB connection (`truth_ib`)** — start with using `self.ib` directly. If we see contention in v1 data, add a dedicated `clientId=99` connection in v2.
- **Cron-driven external sanity check** — Manny chose CC live-monitor over cron for tomorrow. Cron path stays available as future option if live-monitor isn't sustainable.

---

## Tomorrow morning (2026-05-27) — CC live-monitor protocol

Per Manny's call, CC monitors the live engine output during pre-market through the first squeeze window. The watchdog needs to be shipped and running by then so CC has data to monitor *with*; if it's not in place by Monday 04:00 ET, CC monitors anyway using the manual IBKR direct-query technique from yesterday's audit.

CC's live-monitor checklist for tomorrow AM:

1. **Watchdog status check** — after bot launch, confirm `SUBSCRIPTION_AUDIT` lines appear in main bot stdout. If absent, watchdog didn't start — escalate to Manny.
2. **First-hot-symbol check** — when the first scanner-promoted symbol gets a `subscribe_symbol()` call, watch for ticks. If observed/median ratio is < 0.1 within 15 min of subscription, run a manual `clientId=99` direct query to confirm. If confirmed wedge, ping Manny and propose manual restart of `daily_run_v3.sh`.
3. **A/B/C divergence sanity** — if all three sub-bot logs show the *same* symbol going silent, that's the upstream wedge signature (we just learned this in yesterday's failure analysis — sub-bot uniformity = upstream evidence, not health).
4. **Don't restart eagerly** — restart is the heaviest intervention available. Only do it if a confirmed wedge is blocking trades on a stock the scanner has flagged as a top mover.
5. **Log what you saw** — at EOD, write a short note in `cowork_reports/2026-05-27_live_monitor_observations.md` capturing any wedge events, your decisions, and outcomes. This becomes the data point that informs Tuesday's auto-resubscribe decision.

---

## A/B/C interaction

The A/B/C test (`2026-05-23_live_abc_fade_gate_test_directive.md`) keeps running unchanged. The watchdog only adds an audit signal to the daily report — it does NOT modify any variant's behavior.

Important re-framing: **all three variants drink from the same engine-socket fanout, so any upstream wedge affects all three equally.** The variant comparison remains apples-to-apples even with degraded data. What changes is our interpretation of the *absolute* numbers: a day flagged `DATA QUALITY DEGRADED` is a day where the day's P&L (positive or negative) reflects partial data, not the full strategy economics.

This has a hopeful implication for the YTD backtest result that drove us to A/B/C. The YTD's −$17,897 conclusion was drawn against live data we now suspect was systematically undercounted (memory note suggests 30-60% routine undercount). **The strategy might be fine and we've been backtesting against systematically degraded data the whole time.** The A/B/C test gives us the first clean-vs-degraded daily comparison we'll have ever had.

---

## Risk

1. **Watchdog emits noisy `HEURISTIC_SUSPECT` lines on quiet days** — the absolute-volume cap (`HEURISTIC_ABS_CAP=5000`) is the safety. Tune up if Monday's first cycle shows excessive flags on actually-quiet symbols.
2. **Direct queries contend with main IB queue** — 5 requests every 5 min is small, but watch for `Error 100` or similar pacing-related errors. If observed, drop to 3 per cycle or move to dedicated `clientId=99` connection.
3. **Watchdog itself wedges** — if `_run_direct_query` hangs on an `ib.reqHistoricalData` call, the whole loop stalls. Wrap each direct query in a `concurrent.futures.ThreadPoolExecutor` with a 10s timeout (pattern already in repo per the watchdog-freeze fix in commit `a8a95ec`).

---

## Sequencing

This is independent of the A/B/C test scaffolding (separate codepath, separate decision boundaries). Both can ship in parallel.

Order of operations for CC:

1. Implement `subscription_watchdog.py` per spec above
2. Wire `watchdog.tick(now)` into main bot loop
3. Add env vars to `daily_run_v3.sh` (default ON for Monday)
4. Extend `scripts/abc_compare_daily.py` to ingest `SUBSCRIPTION_AUDIT` lines
5. Smoke test: launch bot for 5 minutes, confirm `SUBSCRIPTION_AUDIT` lines appear in stdout with valid JSON
6. Push, commit message: `feat: subscription watchdog (observability for IBKR Tier-2 wedge detection)`
7. Document any quirks in `cowork_reports/2026-05-26_subscription_watchdog_impl_notes.md`

---

## Deliverable

`cowork_reports/2026-05-26_subscription_watchdog_impl_notes.md`:
- Implementation choices CC made (e.g., did you add the secondary IB connection, did you hook error events)
- Smoke test results (sample `SUBSCRIPTION_AUDIT` lines)
- Anything in the spec that didn't translate cleanly to the existing code structure
- A note on whether the heuristic flagged anything during the smoke test (if so, was it real?)

---

## What we learn from this

After Monday + Tuesday with the watchdog running, the audit pattern discriminates between hypotheses:

- **If no wedges fire on either day** → today was a freak event triggered by the Mac-mini-restart-then-manual-Gateway-start sequence (H5 confirmed in absentia). Procedural fix only: post-restart cooldown protocol before cron launch.
- **If wedges fire on every symbol subscribed during the first ~30 min after Gateway start, then clean later** → H5 confirmed live. Fix: add a Gateway-warmup delay in `daily_run_v3.sh` before bot launch when a restart was detected.
- **If wedges fire on hot symbols only** → confirms H1 (chronic Tier-2 throttling correlated with subscription age/contention). Move toward auto-resubscribe action gated separately.
- **If wedges fire uniformly across symbols** → suggests H2 (rate-limit downgrade) or H3 (pre-market half-bootstrap). Different fix path — probably batch-subscribe pacing or post-04:00-ET re-subscribe sweep.
- **If wedges fire on specific exchanges/venues** → H4 (contract qualification race). Fix path is qualify-then-verify-primary-exchange before subscribing.

The watchdog's `sub_age_sec` field in each audit line is what discriminates H5 from H1-H4: if `sub_age_sec < ~1800` correlates strongly with `WEDGE` status while older subscriptions are healthy, H5 is the culprit.

### H5 — Orphaned IBKR server-side session after ungraceful Gateway termination

The Mac mini restarted yesterday and Manny manually started Gateway. The previous Gateway's TCP connection to IBKR terminated without a clean disconnect — IBKR's server-side may have retained ghost market-data subscriptions registered to the account. When today's bot called `reqMktData` against the new Gateway session, IBKR de-duplicated against the orphans and silently downgraded the new subscription to a slower update cadence. No 354/2105/2106 warning generated because IBKR doesn't always emit one for this path.

**Procedural mitigation** (independent of the watchdog, can ship same time):

Add a `--check-orphans` mode to `daily_run_v3.sh` that, when a Mac-mini restart is detected (via boot time vs Gateway start time), waits 15-20 minutes after Gateway launch before firing the bot. Allows IBKR's session timeout to flush orphan subscriptions. Cheap and reactive.

Even cheaper alternative: after any manual Gateway start, Manny should defer launching `daily_run_v3.sh` for 20 minutes. Document in operational runbook.

Two days of audit data → directive choosing the structural fix. By Wednesday-Thursday at the latest.
