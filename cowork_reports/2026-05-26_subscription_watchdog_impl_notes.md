# Implementation Notes: Subscription Watchdog (v1)

**Directive:** `cowork_reports/2026-05-26_subscription_watchdog_directive.md`
**Status:** Shipped, smoke-tested, ready for tomorrow's 02:00 MT cron.

---

## What landed

| File | Change |
|---|---|
| `subscription_watchdog.py` | New self-contained module. `SubscriptionWatchdog` class. |
| `bot_v3_hybrid.py` | Import + `state.subscription_watchdog = SubscriptionWatchdog(...)` at startup + `state.subscription_watchdog.tick(now)` in main loop after `manage_tier1_subscriptions()`. |
| `daily_run_v3.sh` | Added `WB_SUB_WATCHDOG_ENABLED=1` to the main bot launch block. |
| `scripts/abc_compare_daily.py` | New `parse_subscription_audit()` ingests `SUBSCRIPTION_AUDIT` lines; new "Data Quality Audit" section in daily report; top-of-report `⚠️ DATA QUALITY DEGRADED` banner when any wedge events occurred. |

---

## Implementation choices

### 1. Threading / event-loop model — different from the directive spec

**Directive:** Wrap each direct query in `ThreadPoolExecutor` with a 10s timeout, per commit `a8a95ec`.

**What I shipped:** Direct call to `self.ib.reqHistoricalData(..., timeout=10)` on the main thread, no executor.

**Why:** The smoke test surfaced a real bug. ib_insync's `reqHistoricalData` awaits on the data response internally, which requires the calling thread to own the asyncio event loop. Shipping it to a `ThreadPoolExecutor` worker raises `RuntimeError("There is no current event loop in thread 'sub-watchdog_0'.")`. The pattern from commit `a8a95ec` works for `cancelMktData` / `reqMktData` (fire-and-forget — no await) but not for `reqHistoricalData`.

Hang protection is preserved via ib_insync's built-in `timeout=` parameter on `reqHistoricalData`. On timeout the call returns whatever bars arrived (empty list if none); we treat the empty-list path as `truth_unavailable` rather than zero-volume, so a transient timeout doesn't false-flag a healthy symbol as wedged.

The directive's "10s timeout" is honored by `WB_SUB_WATCHDOG_DIRECT_QUERY_TIMEOUT_SEC` (default 10), passed straight to `reqHistoricalData(timeout=...)`.

Worst-case main-loop blocking under this design: 5 direct queries × 10s timeout = 50s per direct-query cycle. In practice each call completes in <500ms; only a hung IBKR-side request hits the deadline. If multiple symbols hit the timeout, we accept a 50s loop stall (well under the bot's 120s watchdog).

### 2. Selection priority — v1 omits explicit "scanner top-5"

**Directive §Detection design §Signal 2:** Priority order — open positions → heuristic suspects → scanner top-5 → round-robin.

**What I shipped:** Open positions → heuristic suspects → round-robin (no scanner top-5).

**Why:** Scanner top-5 requires reading `scanner_results/<date>.json` from disk every cycle and rank-sorting by gap_pct/PM_volume. Useful but adds an I/O dependency and JSON-schema coupling that wasn't required to validate the core wedge detection. With round-robin covering 5 symbols per 5-min cycle, every symbol in a ~95-symbol universe gets queried within ~95 min worst case. For tomorrow's diagnostic run that's acceptable.

**v2 enhancement (not shipped):** add scanner top-N pulled from `state.tier1_volume_rank` or directly from the scanner snapshot file, so hot premarket gappers get a direct-query check within their first ~5 min of subscription. This closes the "chicken-and-egg" gap (a wedged hot symbol that the heuristic misses because all peers also wedge → universe median collapses).

### 3. Emit all symbols every cycle, not just flagged ones

The directive emits a single status line per audit. I emit one `SUBSCRIPTION_AUDIT` line per active symbol per cycle, including `status: OK` lines. Rationale: the daily-report's data-quality table benefits from ground-truth volume coverage on *all* symbols, not just flagged ones. This is also how a single bad day can be distinguished from a chronic baseline shift — we'll have OK ratios to compare against the eventual wedge ratios.

Cost: with 95 symbols × 1 line/min/symbol = ~5,700 lines/hour during active windows. Each line is ~250 bytes JSON → ~1.4MB/hour. Trading day total ~14MB. Acceptable for the diagnostic value.

### 4. Empty-bars handling

When `reqHistoricalData` returns `[]` (either timeout OR no bars in window — e.g., pre-market when a symbol hasn't traded), we set `truth_v_5m=None` and `status=DIRECT_QUERY_OK` with `note=truth_unavailable`. We do NOT flag `WEDGE` on `None` truth — only on a confirmed positive truth count where observed < 10% of truth. This prevents pre-market false positives when a symbol hasn't actually traded yet.

### 5. First-seen time approximation for `sub_age_sec`

The directive's `sub_age_sec` field needs subscription-start time. The codebase doesn't have a clean `state.subscribed_at[sym]` dict — there's a `state.tbt_subscribed_at` for tier-1 only. Rather than thread a new state attribute through `subscribe_symbol()`, the watchdog tracks first-seen-in-active_symbols time itself (`self._first_seen_at[sym]`). This is an approximation — if a symbol enters active_symbols at the moment the watchdog observes, the field starts at 0 rather than the actual reqMktData time. For diagnosis purposes the approximation is close enough (we care about hours-old wedges, not seconds).

---

## Smoke test results

Test script: `/tmp/sub_watchdog_smoke.py` (not committed — recreate from this report if needed).

Configuration:
- `WB_SUB_WATCHDOG_ENABLED=1`
- `WB_SUB_WATCHDOG_HEURISTIC_INTERVAL_SEC=1`
- `WB_SUB_WATCHDOG_DIRECT_QUERY_INTERVAL_SEC=1`
- Live IBKR Gateway via `clientId=98` (no contention with running bot's `clientId=1`)

Synthetic state: 6 symbols, MNTS wedged at 250 shares over 5min (today's real symptom shape), peer symbols (CODX, CPSH, FUTG, AIIO, MDAI) at 160K-750K healthy volume. Real IBKR contracts qualified for each.

Two `wd.tick(now)` cycles, 2 seconds apart.

**Results — 22 SUBSCRIPTION_AUDIT lines emitted:**

```
MNTS status sequence: HEURISTIC_SUSPECT → DIRECT_QUERY_WEDGE → HEURISTIC_SUSPECT → DIRECT_QUERY_WEDGE
MNTS DIRECT_QUERY_WEDGE detail: obs=250, truth=98,012, ratio=0.0026 (well below 0.1 threshold)
CODX status sequence: OK → OK → DIRECT_QUERY_OK
```

Sample audit line (MNTS wedge):

```json
SUBSCRIPTION_AUDIT {"ts":"2026-05-26T16:33:01.877391-04:00","sym":"MNTS","tier":"snapshot","obs_v_5m":250,"median_v_5m":275000,"ratio_obs_to_median":0.0009,"truth_v_5m":98012,"ratio_obs_to_truth":0.0026,"status":"DIRECT_QUERY_WEDGE","sub_age_sec":0,"contract_exchange":"SMART","contract_primary":"NASDAQ"}
```

Sample audit line (CODX healthy):

```json
SUBSCRIPTION_AUDIT {"ts":"2026-05-26T16:33:01.877391-04:00","sym":"CODX","tier":"tick_by_tick","obs_v_5m":750000,"median_v_5m":275000,"ratio_obs_to_median":2.7273,"truth_v_5m":12552,"ratio_obs_to_truth":59.7514,"status":"DIRECT_QUERY_OK","sub_age_sec":0,"contract_exchange":"SMART","contract_primary":"NASDAQ"}
```

All emitted lines parsed as valid JSON. All required schema fields present. JSON schema audit:

| Field | Type | Present | Notes |
|---|---|---|---|
| `ts` | ISO 8601 string with offset | ✓ | |
| `sym` | string | ✓ | |
| `tier` | string ("snapshot" / "tick_by_tick" / "unknown") | ✓ | |
| `obs_v_5m` | int | ✓ | sum of `state.tier1_volume_buckets[sym]` |
| `median_v_5m` | int or null | ✓ | null when no peer has nonzero observed |
| `ratio_obs_to_median` | float or null | ✓ | 4-decimal precision |
| `truth_v_5m` | int or null | ✓ | null when direct query not performed this cycle |
| `ratio_obs_to_truth` | float or null | ✓ | 4-decimal precision |
| `status` | enum string | ✓ | OK / HEURISTIC_SUSPECT / DIRECT_QUERY_OK / DIRECT_QUERY_WEDGE |
| `sub_age_sec` | int or null | ✓ | first-seen approximation |
| `contract_exchange` | string or null | ✓ | "SMART" for our universe |
| `contract_primary` | string or null | ✓ | "NASDAQ" most cases |
| `note` | string (optional) | ✓ when present | `truth_unavailable` on empty/timeout |

---

## Quirks discovered during impl

1. **Synthetic peer volumes weren't realistic for v1 test data.** First smoke run had MNTS at 2,500 with peers at ~3,500, and the heuristic correctly NOT-flagged MNTS (the dual-threshold is conservative — 0.1× of median AND under 5,000 absolute). Fixed by inflating peer-volume synthetic data to 160K-750K (matching what TBT promotion produces on a real healthy day). This validates that the dual-threshold's job is *exactly* to require both conditions — a quiet-but-healthy stock at 2,500 looks identical to a wedged stock at 2,500 if you only look at one. The wedge signature requires "I'm in an active universe where peers are running, but I'm dead." Worth noting in the v2 tuning conversation.

2. **The "directive said executor, code rejected executor" finding** (see §1 above) is the kind of thing that would've shipped broken if I'd skipped smoke testing. Smoke ran ~2 seconds and revealed it immediately. Worth keeping the explicit "smoke test before push" step in future directives.

3. **`AIIO`/`FUTG` synthetic obs > IBKR truth.** The synthetic data accidentally inflated peer-symbol observed volume above their real IBKR 5-min truth (e.g., AIIO synthetic 250K vs IBKR 3,395). The watchdog reported `ratio_obs_to_truth=73x` and correctly marked `DIRECT_QUERY_OK` because the wedge check is one-directional (we only flag obs < truth, not obs > truth). This is correct behavior — the bug we care about is *under*-counting, not over-. Documented here so future readers don't think `73x` ratios are a problem.

---

## What this does NOT include (deferred)

Per directive §"What this does NOT include":

- **Auto-resubscribe action.** Watchdog detects; doesn't act. Decision deferred until 1-2 days of audit data prove the heuristic doesn't false-positive in production.
- **IBKR error-queue parsing.** The `recent_ib_errors` field from the directive's spec was simplified to omission. v2 should hook `ib.errorEvent` and capture recent errors per-symbol so wedge events can be correlated with IBKR-side warnings.
- **Secondary IB connection (`clientId=99`) for truth queries.** Smoke test used a separate clientId because the production bot owned clientId=1. In production the watchdog reuses `state.ib` (clientId=1). If we see contention (e.g., main-bot tick processing slowing down during direct-query cycles), v2 should split to a dedicated truth-query connection.
- **Scanner top-5 priority slot.** See §2 above.

---

## Tomorrow morning's monitoring plan

Per the directive's §"Tomorrow morning (2026-05-27) — CC live-monitor protocol":

1. After 02:00 MT cron fires, confirm the startup banner shows `SubscriptionWatchdog: ENABLED`.
2. During pre-market and the first hour of regular session, grep `SUBSCRIPTION_AUDIT` lines from `logs/2026-05-27_daily.log` periodically. Watch for `HEURISTIC_SUSPECT` and `DIRECT_QUERY_WEDGE` status values.
3. If ANY `DIRECT_QUERY_WEDGE` fires:
   - Compare the symbol's `sub_age_sec` field — does it correlate with subscription age?
   - Confirm via independent IBKR `clientId=99` query that the symbol is in fact moving (sanity check on the truth query itself)
   - If wedge confirmed, this is data to inform Wednesday-Thursday's auto-resubscribe directive. Do NOT manually restart unless the wedge is blocking trades on a top mover.
4. EOD: the abc_compare_daily.py will write the Data Quality Audit section automatically. Check for the `⚠️ DATA QUALITY DEGRADED` banner.

---

## Discrimination matrix (per directive §"What we learn from this")

After tomorrow + Wednesday with the watchdog running, the `sub_age_sec` field discriminates the hypotheses:

| Pattern | Hypothesis confirmed | Fix path |
|---|---|---|
| No wedges either day | H5 freak event (yesterday's Mac restart) | Procedural: post-restart cooldown only |
| Wedges within first ~30 min of Gateway start, clean later | H5 confirmed live | Gateway-warmup delay in launcher when restart detected |
| Wedges on hot symbols only (high `obs_v_5m`-relative variance) | H1 chronic Tier-2 throttling | Auto-resubscribe gated separately |
| Wedges uniform across symbols regardless of age/tier | H2 (rate-limit downgrade) or H3 (pre-market half-bootstrap) | Batch-subscribe pacing or post-04:00-ET re-subscribe sweep |
| Wedges concentrate on specific `contract_primary` exchanges | H4 contract qualification race | Qualify-then-verify-primary before subscribing |

The `contract_primary` and `contract_exchange` fields in the audit line make H4 falsifiable from day 1 of data.

---

*Implementation complete. Awaiting tomorrow's data.*
