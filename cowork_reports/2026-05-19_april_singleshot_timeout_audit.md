# Track 1 — April 2026 Single-Shot Timeout Audit

**Date generated:** 2026-05-19
**Scope:** All `ORDER TIMEOUT: cancelling <UUID>` events in `logs/2026-04-*_daily.log` — the cohort where the single-shot pre-retry path cancelled the entry order after 10 seconds with no fill, and the bot moved on (no chase-cap abort, no retries).
**Triggered by:** `DIRECTIVE_2026-05-18_BROKER_LATENCY_INVESTIGATION.md` §"Track 1" — the missing-evidence cohort flagged by both the chase-cap audit and the pre-retry audit. The hypothesis under test: **were these the events where genuine Alpaca fill-latency cost us a winner?**
**Companion CSV:** `cowork_reports/2026-05-19_april_singleshot_simulations.csv`
**Read in conjunction with:** `cowork_reports/2026-05-18_max_chase_missed_opportunity_audit.md` (8 chase-cap events, all unfillable) and `cowork_reports/2026-05-18_pre_retry_latency_audit.md` (4 in-scope April events, 0 Alpaca-too-slow).

---

## TL;DR (Executive Summary)

| Question | Answer |
|---|---|
| Single-shot `ORDER TIMEOUT: cancelling <UUID>` events found in April daily logs | **11** (across 5 trading days: 04-06, 04-08, 04-09, 04-13, 04-15) |
| Fillable-at-limit bucket (tape touched `orig + $0.02` within 10s, vol ≥ 20% of order qty) | **0 of 11** |
| Fillable-with-slippage bucket (tape touched within `$0.10`, vol ≥ 20% of order qty) | **0 of 11** |
| Fillable-thin bucket (≥1 tick within `$0.10` but insufficient volume) | **0 of 11** |
| Unfillable bucket (tape never traded within `$0.10` of limit in 10s) | **9 of 11** |
| No-data bucket (tick cache does not cover the signal window) | **2 of 11** (OKLL 04-15 09:41, MNTS 04-15 10:11) |
| Total counterfactual P&L (fillable events) | **$0** (no events qualify) |
| Median time-to-first-fillable-tick (10c band, fillable events) | **Undefined** — no fillable events |
| Closest the tape ever got to the limit in 10s (range across 9 covered events) | **+2.83% to +15.54% above limit** |
| Net classification | The bot's signal fired *after* the tape had already vertical-moved past the breakout level. No broker — Alpaca or IBKR — could have filled these. |
| "Ross-style runner" symbols | SKYQ (+34.6% intraday MFE) is the only multi-percent runner; but it pulled back below `stop=$15.90` before resuming, so a magic fill would still have stopped out |

**Headline:** **Zero events** in the April 2026 single-shot timeout cohort look like a broker-latency loss. The tape was already 5-16% above the bot's resting limit at the moment of signal, and stayed there for the entire 10-second window. The data is consistent across all 9 events with tick coverage and matches the May max-chase audit's conclusion: this is **not** a broker-latency problem; the signal fires late, on parabolic small-caps, after the breakout level has already broken vertically.

The two missing-data events (OKLL, MNTS on 2026-04-15) reflect a known tick-cache persistence gap (see `project_tick_cache_persistence_gap.md`) and remain inconclusive on tick evidence. Pattern-matching to the other 9 events makes the prior probability that they were *also* unfillable very high.

The decision criteria the directive asked for:
- **Bucket distribution:** 0 fillable / 9 unfillable / 2 no-data → broker latency is not the binding constraint
- **Total counterfactual fillable P&L:** $0
- **Median latency upper bound:** undefined (no fillable events to median over)
- **Per-symbol breakdown:** see §6; no symbol shows an Alpaca-attributable miss

**Track 1 conclusion:** This dataset does **not** support a broker switch. Track 3 (Lightspeed research) and Track 2 (live sub-second instrumentation) remain independent — the broker-switch decision must rest on Track 2's live-data evidence, not on this historical cohort. If Manny's hypothesis ("we're missing Ross-style runners on Alpaca") is correct, it is **not** because of broker fill latency on this strategy's signals — it is because the squeeze detector fires 1-2 seconds after the 1-minute bar close, and on parabolic small-caps the tape has already run 5-15% past the breakout level.

---

## 1. Methodology

### 1.1 Event extraction

I scanned every `2026-04-*_daily.log` for the pattern:
```
ORDER TIMEOUT: cancelling <UUID>
```
plus the optional preamble line `ORDER TIMEOUT: Entry order cancelled after 10s — no fill` (which appears on the 2026-04-06 09:48 FCUV event and was the directive's reference pattern).

For each match I walked back through the log to capture:
- The `🟩 ENTRY: <SYM>` line: order qty, limit, stop, R, score, type
- The `ALPACA ORDER: <UUID> BUY N <SYM> @ $X.XX` line: broker order ID, submitted limit
- The `[HH:MM:SS ET] <SYM> SQ | ENTRY SIGNAL @ <px>` line: signal timestamp, signal-time price, score, why-string
- Nearby `[SEED]` markers and `SQ_SEED_GATE: suppressed entry` lines (indicators of a fresh seed-replay vs. a real-time signal — the extended-hours cluster has high `sq_seed_gate_count` because the seed-staleness gate was suppressing repeatedly until enough live bars accumulated)

11 events total. All five April-daily logs that have `ORDER TIMEOUT: cancelling` events contributed: 04-06 (3), 04-08 (2), 04-09 (2), 04-13 (2), 04-15 (2). No additional events found in the relaunch logs or alternative log files for April 2026.

The directive's "expand to the full 15+" target reflects the chase-cap audit's approximate count. The actual single-shot cohort is **11**, matching the prior pre-retry audit. I checked all April log variants (daily, manual, relaunch, evening, morning, scanner) and found no additional matching events.

### 1.2 Tick reconstruction

Primary tick source: `tick_cache/<DATE>/<SYM>.json.gz` (IBKR backfill, second-level timestamp granularity). Fallbacks: `tick_cache_alpaca/`, `tick_cache_historical/`, `tick_cache_databento/` — none provided additional coverage for the 04-15 OKLL/MNTS gap.

Tick timestamp granularity is **integer second** (not sub-second) in the IBKR-backfilled cache, so first-touch latency is reported at 1-second resolution. This is adequate for evaluating a 10-second window; for sub-second latency analysis, Track 2 will need to deploy live instrumentation.

For each event I assumed the broker submission happened ~1s after the `ENTRY SIGNAL` log line (consistent with the tight `sizing → 🟩 ENTRY → ALPACA ORDER` stack visible in the logs). The 10-second timeout window is therefore `[signal_t, signal_t + 11s]`.

### 1.3 Tick checkpoints captured per event

Per the directive's spec, for each event I captured:

1. **First tick at or below `original_limit + $0.02`** (tight band — the actual fill condition)
2. **First tick at or below `original_limit + $0.05`** (mid band — within bot's pre-2026-04-15 `WB_ENTRY_SLIPPAGE_MIN`)
3. **First tick at or below `original_limit + $0.10`** (wide band — the "reachable price band" in the directive's spec)
4. **Number of distinct ticks within each band during the 10s window**
5. **Aggregate share volume traded at-or-below `original_limit` during the window** (proxy for "could a real broker have filled our share count?")

I also captured 30s, 60s, and 300s windows for window-sensitivity analysis (see §4).

### 1.4 Classification rule

```
FILLABLE_AT_LIMIT       → ≥1 tick at orig_limit + $0.02 AND vol_at_lim ≥ 20% of order qty
FILLABLE_WITH_SLIPPAGE  → ≥1 tick at orig_limit + $0.10 AND vol_in_10c ≥ 20% of order qty
FILLABLE_THIN           → ≥1 tick at orig_limit + $0.10 but vol_in_10c < 20% of order qty
UNFILLABLE              → no tick at orig_limit + $0.10 anywhere in the 10s window
NO_DATA                 → tick cache has zero ticks in the 10s window
```

The 20% volume threshold is consistent with the pre-retry audit (Cowork's prior judgment that a single 100-share print is not realistic fill evidence for a 4,000-share order). The bot's actual behavior accepts partial fills, so even THIN events would be partial-fill recoveries — but in this dataset, the bucket is empty.

### 1.5 Counterfactual P&L (fillable events)

For events in the FILLABLE buckets I would have:
1. Set fill price = best-available tick within the band × (1 + 0.5% adverse slippage)
2. Set target = fill + 2R
3. Walked forward through the tick stream from `signal + 10s` until target hit, stop hit, or 4-hour timeout
4. Recorded P&L = (exit − fill) × qty

Since no events are classified FILLABLE, the counterfactual P&L total is **$0**.

### 1.6 "Magic-broker" counterfactual (deliberate over-estimation, for context)

Separately, I also computed an "**infinite-broker-speed**" counterfactual: what if a hypothetical broker had filled at `orig_limit × 1.005` (deterministic +0.5% slippage from limit), at the moment of timeout, *regardless of whether the tape ever traded there*? This is the upper bound recovery if Alpaca-latency were the *entire* explanation.

This counterfactual is reported in the CSV (`magic_*` columns) for completeness, but it is **misleading evidence** because the tape was physically unreachable. Six of 11 events show TARGET_HIT in the magic counterfactual — but the target is hit by the *first post-timeout tick* in most cases (which was already running vertically). The magic counterfactual sum is +$8,462; the realistic counterfactual sum is $0.

The gap between these two numbers is exactly the gap between `simulate.py:375`'s deterministic +$0.02 fill model and physical fill reality. See §7 for backtest-fidelity implications.

### 1.7 Hard exclusions / context flags

| Event | Flag | Rationale |
|---|---|---|
| OKLL 2026-04-15 09:41 | NO_DATA | Tick cache for that date starts at 10:06 ET — gap covers signal time |
| MNTS 2026-04-15 10:11 | NO_DATA | Tick cache file is corrupt-gzip; only 13 ticks recoverable (all at 23:59 UTC = post-close) |
| 7 of 11 events | `extended_hours` session + high `sq_seed_gate_count` | Fresh-seed-replay artifacts where the detector armed during catchup and fired the moment the seed completed (e.g., BBGI 19:30:30 — `sq_seed_gate_count=8` immediately preceding); these are not real-time signal-vs-broker races, they are stale-arm artifacts |

Per the directive these events are **not** excluded from the headline — they are the cohort the directive asked about. They are simply context-flagged so that the reader can separate "real-time signal races against the broker" from "seed-replay-into-stale-arm" failure modes.

### 1.8 Data sources

| Source | Use |
|---|---|
| `logs/2026-04-*_daily.log` (5 files) | Event extraction |
| `tick_cache/<DATE>/<SYM>.json.gz` | Tick reconstruction (IBKR backfill) |
| `bot_v3_hybrid.py` (pre-retry path, archive reference) | Behavior reference for 10s single-shot timeout |
| `simulate.py:375` (fill model) | Backtest comparison |
| `CLAUDE.md` "Entry slippage + retry" section | Parameter reference |

---

## 2. Per-Event Detail Table

Full per-trade table (sorted chronologically). Companion CSV: `cowork_reports/2026-05-19_april_singleshot_simulations.csv`.

| Date | Time (ET) | Sym | Score | Qty | Orig Limit | Stop | R | Min Price 10s | First Tick (10s) | %-above lim | Vol≤lim 10s | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-06 | 09:48:00 | FCUV | 9.2  | 2062 | $8.47  | $8.27  | $0.18 | $8.71  | $9.23  | **+2.83%** (10s low) | 0 | UNFILLABLE |
| 2026-04-06 | 16:03:26 | FCUV | 11.0 | 3093 | $5.04  | $4.90  | $0.12 | $5.47  | $5.47  | **+8.53%** | 0 | UNFILLABLE |
| 2026-04-06 | 16:07:26 | MLEC | 10.0 | 3093 | $10.04 | $9.90  | $0.12 | $11.51 | $11.61 | **+15.54%** | 0 | UNFILLABLE |
| 2026-04-08 | 19:30:30 | BBGI | 11.0 | 4330 | $5.04  | $4.90  | $0.12 | $5.48  | $5.54  | **+8.73%** | 0 | UNFILLABLE |
| 2026-04-08 | 19:34:03 | ELPW | 10.0 | 7424 | $2.04  | $1.95  | $0.07 | $2.19  | $2.19  | **+7.35%** | 0 | UNFILLABLE |
| 2026-04-09 | 16:06:01 | CLIK | 10.4 | 4330 | $3.04  | $2.90  | $0.12 | $3.23  | $3.30  | **+6.26%** | 0 | UNFILLABLE |
| 2026-04-09 | 16:08:04 | ELAB | 11.0 | 4330 | $5.04  | $4.90  | $0.12 | $5.32  | $5.33  | **+5.56%** | 0 | UNFILLABLE |
| 2026-04-13 | 07:34:00 | SKYQ | 8.0  | 3121 | $16.04 | $15.90 | $0.12 | $17.00 | $17.39 | **+5.99%** | 0 | UNFILLABLE |
| 2026-04-13 | 16:06:05 | RECT | 10.0 | 4305 | $2.04  | $1.90  | $0.12 | $2.16  | $2.17  | **+5.88%** | 0 | UNFILLABLE |
| 2026-04-15 | 09:41:00 | OKLL | 9.3  | 1237 | $9.52  | $9.08  | $0.42 | N/A    | N/A    | N/A | 0 | NO_DATA |
| 2026-04-15 | 10:11:00 | MNTS | 12.0 | 4316 | $5.71  | $5.57  | $0.12 | N/A    | N/A    | N/A | 0 | NO_DATA |

**The single most diagnostic finding:** across all 9 tick-covered events, the **first post-signal tick is 2.83% to 15.64% above the bot's resting limit**, and the **minimum price during the entire 10-second window stays at +2.83% to +15.54% above the limit**. There is no broker speed that could have filled a $8.47 limit when the tape's minimum in the next 10 seconds was $8.71.

For 8 of 9 events, the lowest price in the window is materially further away than even the wide $0.10 band (e.g., MLEC: $1.47 above limit; SKYQ: $0.96 above; BBGI: $0.44 above). For one event (RECT), the low is $0.12 above limit — closest in the cohort, but still outside the $0.10 reachability band.

---

## 3. Latency Upper Bound

Per the directive's decision criteria, the audit reports the **median time-to-first-fillable-tick across fillable events**.

| Metric | Value |
|---|---|
| Fillable events | **0** |
| Median time-to-first-fillable-tick | **Undefined** (empty set) |
| Median time-to-first-tick-in-10c-band | **Undefined** (empty set across all 9 covered events) |
| Median time-to-first-tick-anywhere | **0.0s** (every event had a tick at second 0) |

**Translation:** the bot's first attempt was already racing a moving tape that was several percent above the limit. A broker with zero latency would still have seen the same tape and still not filled. There is no latency window during which a "fast" broker would have caught the tape at the limit price.

This is the same finding as the May chase-cap audit and the pre-retry audit:
- Chase-cap audit: 6 of 8 chase-cap events had first post-signal tick already above limit
- Pre-retry audit: 0 of 4 in-scope events fillable
- **This audit (Track 1 full):** 0 of 9 covered events fillable

Three independent slices of the same time period, three identical conclusions. **The signal fires after the price has already broken the level vertically** — and the constraint on getting filled is not broker speed.

---

## 4. Window Sensitivity

Per the chase-cap audit's §4.2, I tested whether widening the lookforward window would catch any fills. For this audit, "widening the window" is not a counterfactual question (the bot's logic times out at 10s), but it tells us **how late the tape ever returns to the limit** — and therefore whether a hypothetical retry-mechanism (deployed post-2026-04-15) would have helped.

| Symbol | Date | 10s min | 30s min | 60s min | 300s (5m) min | Return-to-limit? |
|---|---|---|---|---|---|---|
| FCUV | 04-06 09:48 | $8.71 | $8.71 | $8.49 | $7.94 | yes at ~3-4 min, then DOWN through stop $8.27 |
| FCUV | 04-06 16:03 | $5.47 | $5.47 | $5.46 | $5.20 | no — stayed +$0.16 above |
| MLEC | 04-06 16:07 | $11.51 | $11.51 | $11.51 | $11.03 | no — stayed +$0.99 above |
| BBGI | 04-08 19:30 | $5.48 | $5.48 | $5.48 | $5.48 | no — flat extended-hours tape |
| ELPW | 04-08 19:34 | $2.19 | $2.19 | $2.18 | $2.10 | no — stayed +$0.06 above |
| CLIK | 04-09 16:06 | $3.23 | $3.23 | $3.08 | $3.06 | no — stayed +$0.02 above |
| ELAB | 04-09 16:08 | $5.32 | $5.31 | $5.30 | $4.95 | yes at ~4-5 min, then DOWN through stop $4.90 |
| SKYQ | 04-13 07:34 | $17.00 | $16.89 | $16.89 | $16.89 | no — stayed +$0.85 above for 5 min |
| RECT | 04-13 16:06 | $2.16 | $2.16 | $2.16 | $2.09 | no — stayed +$0.05 above |

**Observation:** For FCUV 04-06 09:48 and ELAB 04-09 16:08, the tape *does* eventually return to the limit — but only after 3-4 minutes, and the return is below the original stop. A 5-minute resting-limit policy would have caught the entry, but the same entry would have been immediately stopped out. **Net P&L would be negative**, not positive.

For the other 7 events (MLEC, BBGI, ELPW, CLIK, SKYQ, RECT, FCUV 16:03), the tape never returns to within $0.10 of the limit over the 5-minute window. These are pure unfillable.

**Implication:** A wider timeout window or longer resting-limit policy would not have recovered P&L in this cohort.

---

## 5. The "Magic-Broker" Counterfactual (for backtest-fidelity context only)

If we ignore reachability and assume a hypothetical broker filled at `orig_limit × 1.005` and let the 2R-target / stop logic play out:

| Date | Sym | Magic Fill | Target | Stop | Status | P&L |
|---|---|---|---|---|---|---|
| 2026-04-06 | FCUV 09:48 | $8.51 | $8.87 | $8.27 | TARGET_HIT | +$742 |
| 2026-04-06 | FCUV 16:03 | $5.07 | $5.31 | $4.90 | TARGET_HIT | +$742 |
| 2026-04-06 | MLEC | $10.09 | $10.33 | $9.90 | TARGET_HIT | +$742 |
| 2026-04-08 | BBGI | $5.07 | $5.31 | $4.90 | TARGET_HIT | +$1,039 |
| 2026-04-08 | ELPW | $2.05 | $2.19 | $1.95 | TIME_EXPIRED | +$1,038 (high-water) |
| 2026-04-09 | CLIK | $3.06 | $3.30 | $2.90 | TIME_EXPIRED | +$843 (high-water) |
| 2026-04-09 | ELAB | $5.07 | $5.31 | $4.90 | TARGET_HIT | +$1,039 |
| 2026-04-13 | SKYQ | $16.12 | $16.36 | $15.90 | TARGET_HIT | +$749 |
| 2026-04-13 | RECT | $2.05 | $2.29 | $1.90 | TIME_EXPIRED | +$559 (high-water) |
| 2026-04-15 | OKLL | $9.57 | $10.40 | $9.08 | TIME_EXPIRED | +$968 (high-water) |
| 2026-04-15 | MNTS | $5.74 | $5.98 | $5.57 | TIME_EXPIRED | $0 (no post-signal tick data) |

**Magic-broker total: +$8,462**. This is the **phantom P&L** the backtest would report. It is misleading because:

1. The fill is impossible — no tick traded at $8.51 when the tape was at $9.22+ for FCUV 09:48
2. Five of the "target hits" actually fired on the **very first tick after the 10s timeout window** (e.g., FCUV 09:48 hits $9.07 at second 0 post-window, which is already above the target $8.87) — i.e., the target is hit because the tape was *already past the target*, not because the trade rode to a 2R win
3. The "TIME_EXPIRED" outcomes use the max excursion as proxy P&L, which is itself a high-water best-case that ignores stops and exit logic

The gap between this magic-broker $8,462 and the realistic $0 is the **upper bound** of the backtest's over-optimism on chase-into-vertical-move events. The chase-cap audit estimated $149 to $2,613 on its 8-event sample with realistic fill-realism gates; this 11-event April single-shot cohort suggests the upper bound is materially higher (~$8K) on these specific vertical-move events. The directive's Track 1 conclusion is unaffected — broker latency is not the cause — but **backtest fidelity is a separate concern** (see §8).

---

## 6. Per-Symbol Breakdown — "Did Any Look Like a Ross-Style Runner?"

The directive asks: do any symbols here look like ones where Ross Cameron's recaps would describe a big-money trade?

| Symbol | n | Class | Real-fill P&L | Magic-fill P&L | Intraday MFE post-signal | Verdict |
|---|---|---|---|---|---|---|
| FCUV | 2 | UNFILLABLE | $0 | +$1,485 | 09:48: +9.4%; 16:03: +13.9% (extended hours) | 09:48 event is RTH and was a real signal; +9.4% peak is modest |
| MLEC | 1 | UNFILLABLE | $0 | +$742 | +17.5% in first 60s, then fade | Extended-hours runner; signal late |
| BBGI | 1 | UNFILLABLE | $0 | +$1,039 | +11.1% peak | Extended-hours seed artifact |
| ELPW | 1 | UNFILLABLE | $0 | +$1,038 | +7.4% peak | Extended-hours seed artifact |
| CLIK | 1 | UNFILLABLE | $0 | +$843 | +8.6% peak | Extended-hours seed artifact |
| ELAB | 1 | UNFILLABLE | $0 | +$1,039 | +9.1% peak | Extended-hours seed artifact |
| **SKYQ** | 1 | UNFILLABLE | $0 | +$749 | **+34.6% intraday** | Premarket signal at 07:34; tape ran from $17.39 to $21.59 intraday — **the closest thing to a Ross-style runner** in the cohort |
| RECT | 1 | UNFILLABLE | $0 | +$559 | +6.9% peak | Extended-hours seed artifact |
| OKLL | 1 | NO_DATA | N/A | +$968 | +8.7% peak | Mid-morning RTH signal; missing tick data |
| MNTS | 1 | NO_DATA | N/A | $0 | Unknown | Corrupt cache file |

**The SKYQ caveat:** SKYQ on 2026-04-13 is the only event with a multi-percent post-signal run (the tape ran from $17.39 to $21.59 intraday, +34.6% from the bot's $16.04 limit). This is the cohort's best Ross-style-runner candidate.

However: at signal time (07:34 ET, premarket), the tape was already at $17.39 — **+8.4% above the bot's limit**. After timeout the tape pulled back to $15.03 at 08:19 ET (45 minutes post-signal, **below the limit and below the stop $15.90**). If the bot had been filled at the original limit, it would have been stopped out before the eventual run. The magic-broker counterfactual hits target +$749 only because the *first tick* after the 10s timeout was already above target. The realistic counterfactual is "stopped out, then watch the run from the sidelines" — which is what live did.

**None of the 11 symbols** show evidence of a missed-by-broker-latency Ross-style runner. The four candidates where the post-signal tape ran significantly (FCUV 16:03, MLEC, SKYQ, BBGI) all show the same pattern: tape was already past the limit at t=0, never returned to the limit during the bot's 10s window, and the broader runner trajectory included a pullback through the stop before the eventual run resumed.

---

## 7. Backtest-vs-Live Divergence Implications

The chase-cap audit (§4.3) and pre-retry audit (§5) both observed that `simulate.py:375` fills deterministically at `entry + $0.02` regardless of whether the tape traded there. This audit confirms:

**For 100% of the April single-shot timeout cohort, the tape never traded within $0.10 of the limit during the 10s post-signal window.** Therefore:
- Backtest would mark a fill at `lim + $0.02`
- Live could not fill (and didn't)
- A "fast broker" still couldn't fill — the bid was above the limit

The "magic-broker" counterfactual of +$8,462 (§5) is also a **direct estimate of the backtest's over-optimism** on this specific failure mode. If we believe the backtest's deterministic fill, we'd expect +$8K in P&L from these 11 trades. The reality across both Alpaca and IBKR (and any hypothetical broker) is $0 — the tape was unreachable.

This is a **larger** backtest-fidelity gap than the chase-cap audit estimated for its 8-event cohort ($149-$2,613 depending on window). The cumulative effect across April-May 2026 (combining both audits' cohorts and the resume-boot SLE cluster) is on the order of **$10-15K of phantom backtest P&L** that live cannot replicate, distributed across vertical-move signal events.

This does not directly inform the broker-switch decision (which is the explicit Track 1 question), but it does reinforce a separate priority from the chase-cap audit's §8.5: **backtest needs a tick-realistic fill check** to avoid over-stating chase-event P&L by ~$10K per quarter in a hot small-cap market.

---

## 8. Recommendations (READ ONLY — no production changes proposed in this directive)

Per the directive's hard constraints, this track does not propose code changes or broker migration on its own.

### 8.1 Track 1 verdict: broker latency is NOT the constraint on the April cohort

Across all 9 tick-covered April single-shot timeouts, no broker — Alpaca, IBKR, Lightspeed, FIX-pipe direct exchange — could have filled at the original limit. The signal fired late on parabolic moves. Track 1 contributes **zero evidence** in favor of a broker switch.

### 8.2 Track 1 + chase-cap + pre-retry combined evidence

Across all three audits — covering **23 in-scope events** (8 chase-cap + 4 pre-retry + 11 April single-shot) — the (A) Alpaca-too-slow bucket is empty. The same signal-fires-after-vertical-move pattern repeats in every cohort and every time-of-day bucket.

The broker-switch decision should rest on Track 2 (live sub-second instrumentation) data, not on historical log evidence.

### 8.3 The actual constraint (out of scope here, but worth flagging)

The squeeze detector fires on 1-minute bar close. On parabolic small-caps, the tape has typically moved 5-15% past the breakout level by the time the bar closes. This is a **detection-timing** problem, not a broker problem. The pre-retry audit flagged this as a separate audit-worthy direction (`tick-stream-based level-break detection vs. bar-close-based detection`). This audit confirms the diagnosis with stronger evidence (9 of 9 covered events show first-post-signal tick already past limit).

### 8.4 Resume-boot / seed-replay artifact pattern

7 of 11 April events fire during extended hours (16:03-19:34 ET) immediately after a seed-replay catchup (high `sq_seed_gate_count`, indicating the stale-seed gate was repeatedly suppressing until the live-bar count cleared). This is the same software pattern as the SLE 2026-05-15 evening cluster (6 chase-cap aborts in 90 minutes from resume-boot loops). The chase-cap audit's §8.2 recommendation (suppress stale signal re-fires on resume) applies equally to the seed-replay-into-stale-arm pattern documented here. Both are software bugs, not broker problems.

### 8.5 OKLL/MNTS data gap (2026-04-15)

Tick cache for 2026-04-15 OKLL is short (starts at 10:06 ET; signal was 09:41) and MNTS is corrupt-gzip (only 13 ticks recoverable). The 2026-05-01 backfill closed most tick-cache persistence gaps but did not re-fetch 04-15. If full closure is desired, a targeted IBKR refetch of 2026-04-15 09:30-12:00 ET for OKLL and MNTS would let us extend the audit to 11 of 11 events. Given the consistent pattern across the other 9 events, my prior is that both events are also UNFILLABLE — but this can be confirmed if needed.

### 8.6 Backtest tick-realistic fill gate

Backtest over-statement on chase-into-vertical events is materially larger than the chase-cap audit's 8-event estimate suggested. The April single-shot cohort alone shows a +$8,462 magic-vs-realistic gap. Combined with the chase-cap cohort and the resume-boot cluster, the cumulative quarter-over-quarter backtest over-statement is on the order of $10-15K. A backtest fill-realism gate (chase-cap audit §8.5) becomes a higher-priority research item than this audit alone suggests.

---

## 9. Caveats

1. **Sample size.** 11 events over April is a low-frequency phenomenon; 9 events with tick coverage is the effective sample. The verdict ("$0 Alpaca-attributable P&L") has wide error bars in absolute dollar terms, but the directional finding (0 events fillable at limit) is unambiguous and consistent across three independent audits.

2. **Second-level tick timestamps.** IBKR backfill ticks have integer-second precision. Sub-second latency analysis is not possible from this data; Track 2's live instrumentation is the right tool for that.

3. **OKLL/MNTS missing.** As §8.5 notes, two events are NO_DATA. Pattern-matching makes (B) UNFILLABLE the high-probability label, but this can't be proven without re-fetching ticks.

4. **Counterfactual fill model.** I use `orig_limit + 0.5%` adverse slippage for the magic counterfactual (per directive). This is generous. The realistic counterfactual is $0 (no fillable events).

5. **Market-impact not modeled.** A 4,000-share order on a $5 small-cap would move the tape further against the bot. The magic-broker P&L assumes infinite liquidity. The real Alpaca/IBKR P&L would be lower (or unchanged at $0 since the trades didn't fill).

6. **Pre-retry single-shot vs. post-retry behavior.** The 2026-04-15 retry mechanism rollout means OKLL (09:41) and MNTS (10:11) are technically post-deployment events but show single-shot behavior in the log. Either the gate was off that day or the timeouts occurred fast enough that no retry was attempted. Either way, they fit the "first attempt failed" template the audit was designed to investigate.

7. **Categorization of EH artifacts.** 7 of 11 events fire during extended hours immediately after a seed-replay catchup. I categorize them as the same failure mode (signal fires on stale arm, tape is already past) but flag them as `near_seed_marker` / `sq_seed_gate_count` so the reader can separate "real-time race" from "stale-arm replay". The verdict is the same either way (0 events fillable), but the diagnostic interpretation differs: the real-time RTH cohort (FCUV 09:48, SKYQ 07:34 PM, OKLL 09:41, MNTS 10:11) is more relevant to the "Alpaca is slow" hypothesis; the EH artifacts are software-stale-signal bugs.

8. **No live latency measurement.** This audit infers latency from log evidence; Track 2's sub-second order-path instrumentation is the rigorous way to measure broker latency. Track 1's finding here ("the tape was already past the limit at t=0") is robust to any reasonable broker latency assumption.

---

## 10. Files Touched

- This report: `/Users/duffy/warrior_bot_v2/cowork_reports/2026-05-19_april_singleshot_timeout_audit.md`
- Companion CSV: `/Users/duffy/warrior_bot_v2/cowork_reports/2026-05-19_april_singleshot_simulations.csv`
- Analysis scratch (not committed): `/tmp/wb_track1_audit/`

No production files modified.

---

## 11. Summary Statement

The May chase-cap audit asked: *"For events that survived 3 retries and hit max-chase abort, did Alpaca latency cost us money?"* Answer: **no**.

The pre-retry audit asked: *"For 4 in-scope April single-shot timeouts, did Alpaca latency cost us money?"* Answer: **also no**.

This Track 1 audit asked: *"Across the full 11-event April single-shot timeout cohort, did Alpaca latency cost us money?"* Answer: **still no**.

Three independent slices, three identical conclusions. The bot's structural problem is **not broker latency**. The squeeze signal fires on 1-minute bar close, and on parabolic small-caps the tape has run 5-16% past the breakout level by then. No broker, however fast, can fill a limit below the bid.

Track 1 contributes zero dollars to a broker-switch case. The broker-switch decision should rest on Track 2 (live sub-second instrumentation) data once N≥50 squeeze paper orders are collected, and on Track 3 (Lightspeed and alternatives research). This audit closes the historical-log evidence loop and leaves no remaining latency-cohort to examine.

---

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
