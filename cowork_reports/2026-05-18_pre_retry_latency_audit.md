# Pre-Retry Single-Shot Latency Audit (April 2026)

**Date generated:** 2026-05-18
**Scope:** All single-shot `ORDER TIMEOUT` events in `logs/2026-04-*_daily.log`, the cohort flagged at the end of the 2026-05-18 max-chase audit as "where genuine Alpaca latency evidence lives".
**Triggered by:** Cowork follow-up directive. The max-chase audit examined post-retry events; this audit examines the older single-shot timeouts in April to test whether the **first attempt** failed because of broker latency.
**Read in conjunction with:** `cowork_reports/2026-05-18_max_chase_missed_opportunity_audit.md`.

---

## TL;DR (Executive Summary)

| Question | Answer |
|---|---|
| Events located in April logs with `FILL ... (after K retries)` pattern, K>=1 | **Zero**. The retry mechanism (`WB_ENTRY_RETRY_ENABLED=1`) was deployed 2026-04-15 but no April day produced a successful retry. The April cohort is a *single-shot* cohort: order placed, 10s timeout, cancel. |
| Single-shot `ORDER TIMEOUT` events extracted from April daily logs | **11** (across 6 trading days: 04-06, 04-08, 04-09, 04-13, 04-15, plus UCAR Alpaca reject excluded) |
| In-scope (RTH + premarket signals on tradable assets) | **4** (FCUV 04-06, SKYQ 04-13, OKLL 04-15, MNTS 04-15) |
| Excluded extended-hours / overnight seed-replay artifacts | **7** |
| (A) Alpaca-too-slow events (tape DID touch limit during 10s window) | **0 of 4 in-scope, 0 of 11 total** |
| (B) Genuine chase events (tape never reached limit during 10s) | **2 of 4 in-scope, 9 of 11 total** |
| (C) Inconclusive (tick cache does not cover signal time) | **2 of 4 in-scope** — OKLL 09:41 ET and MNTS 10:11 ET (known cache-persistence gap) |
| (A) cohort total slippage | **$0** (no events qualify) |
| Recovered P&L at 50% IBKR-fills assumption | **$0** |
| Recovered P&L at 80% IBKR-fills assumption | **$0** |
| Recovered P&L at 95% IBKR-fills assumption | **$0** |
| **Broker-switch verdict** | **NO**. The April single-shot timeouts show the same structural pattern as the May chase-cap timeouts: at the moment the bot's signal fired, the tape was already 5-16% above the limit, and stayed there for the entire 10-60s window. Switching brokers will not help — the limit was unreachable by any broker. |
| Threshold dollar number that would flip the verdict | **>$5K recovered P&L** in any 30-session window would justify the broker-switch effort. We're at $0 over April. |

The single most diagnostic finding: across all 9 events with tick coverage, **the very first tick after the signal fired was already +5% to +16% above the bot's limit**. Alpaca cannot fill, IBKR cannot fill, no broker can fill. The bot's signal is firing **after** the price has already vertical-moved past the breakout level, and the resting limit is a stale anchor.

This is the same finding as the May max-chase audit: the limit is unreachable from t=0. The chase / retry / timeout mechanisms are correctly preventing chase-into-vertical entries. **The Alpaca-vs-IBKR latency question is not the binding constraint on this strategy.**

The two outstanding open questions left by this audit:
1. **OKLL/MNTS 2026-04-15 morning data gap** — both signals fired during regular hours but the tick cache for that date is incomplete (OKLL coverage starts at 10:06 ET, signal was 09:41; MNTS is corrupt-gzip with only 13 ticks recovered, all 23:59 UTC). This is the same tick-cache persistence gap documented in `project_tick_cache_persistence_gap.md` and mostly addressed by the 2026-05-01 backfill — but 04-15 specifically appears not to have been re-fetched. Worth a 1-day IBKR refetch if you want to fully close the door.
2. **Why is the bot's signal firing late?** This is *not* a broker-latency question; it's a detection-timing question. The squeeze detector fires on 1-minute bar close — and by that time, on a parabolic small-cap, the tape has run 5-15% past the level. Worth a separate audit into tick-stream-based detection vs. bar-close-based detection.

---

## 1. Methodology

### 1.1 Event extraction (April pre-retry cohort)

Scanned all `2026-04-*_daily.log` files for `ENTRY` followed by `ORDER TIMEOUT` patterns. Two log patterns appear:

```
🟩 ENTRY: <SYM> qty=N limit=$X.XX stop=$S R=$R score=SC type=squeeze
  ALPACA ORDER: <UUID> BUY N <SYM> @ $X.XX
  ORDER TIMEOUT: cancelling <UUID>          ← single-shot (April pattern)
```

vs. the post-2026-04-15 retry pattern (which has additional `RETRY 1/3:`, `BROKER ORDER ... (retry)`, and either `FILL: ... (after K retries)` or `ORDER TIMEOUT: cancelling ... after K retries`):

```
🟩 ENTRY: <SYM> qty=N limit=$X.XX (slip=$0.050) ...
  BROKER ORDER: ID BUY N <SYM> @ $X.XX
  RETRY 1/3: <SYM> market=$X.XX new_limit=$Y.YY (slip=$0.050)
  ...
  FILL: <SYM> @ $Z.ZZZZ qty=N (after K retries)
```

**Key empirical finding from the search:** the mission directive asked for "all April events where `FILL: SYM @ $X.XX qty=N (after K retries)` appears with K>=1". Across **every log in `logs/`**, only **one** such event exists:

```
/Users/duffy/warrior_bot_v2/logs/2026-05-15_daily.log:10406:  FILL: SLE @ $6.1229 qty=2491 (after 1 retries)
```

This is a 2026-05-15 event, not April. The April cohort is therefore the older single-shot pattern, which I treat as the equivalent "first-attempt failed" cohort for the purposes of this audit (and the user's mission spec implicitly anticipated this — see the language about "single-shot timeout where the limit was within reach but the order didn't fill in time" in the max-chase audit's §4.3).

### 1.2 Per-event parsing

For each `ORDER TIMEOUT` I captured:
- ENTRY signal time (`[HH:MM:SS ET]` immediately preceding `ENTRY SIGNAL`)
- Symbol, original signal level, original limit, qty, score, stop, R
- Whether the symbol traded post-event (FILL/EXIT/etc.)
- Was this a fresh seed-replay (`[SEED]` marker within 5 log lines), and what time of day

### 1.3 Tick reconstruction

For each event:
- Primary source: `tick_cache/<DATE>/<SYM>.json.gz` (IBKR tick stream)
- Format: `[{"p": price, "s": size, "t": "YYYY-MM-DDTHH:MM:SS.fffuuu+00:00"}, ...]` (UTC)
- Some files have trailing-garbage gzip corruption; I used `gunzip -c` + truncate-to-last-`}]` recovery

I extracted three windows around each signal:
- **pre60**: 60s before signal — establishes "where was the tape just before signal fired?"
- **post10**: 10s after signal — this is the actual broker timeout window
- **post60**: 60s after signal — establishes "did the tape ever come back?"

### 1.4 Classification rule

```
A_ALPACA_TOO_SLOW       → tape touched orig_limit during 10s window AND
                          fillable size >= 20% of order qty
A_ALPACA_TOO_SLOW_THIN  → tape touched orig_limit during 10s but
                          fillable size < 20% of order qty
B_GENUINE_CHASE         → tape never traded at/below orig_limit during 10s
C_NO_DATA               → tick cache does not cover the signal time
```

The 20% threshold is a soft filter: a single 100-share print at the limit is not realistic
fill-evidence for a 4,000-share order. Any A_THIN tagged event would still be a partial-fill
event for the live bot, which would have hit the broker's partial-fill handling logic (the
bot accepts partials).

### 1.5 Counterfactual P&L

For each event I walked forward through the post-signal tick stream and looked for the first
of: stop hit, 2R target hit, or session close. Fill is modeled at `orig_limit + $0.02`
(the pre-X01 deterministic slippage model). This is the same model as the max-chase
audit §1.2 and aligns with `simulate.py:375`.

### 1.6 Hard exclusions

7 of 11 events are **extended-hours seed-replay artifacts**, flagged by:
- Time of day >16:00 ET or <06:00 ET (FCUV 16:03, MLEC 16:07, CLIK 16:06, ELAB 16:08, RECT 16:06; BBGI 19:30, ELPW 19:34)
- Bot log shows fresh `[SEED] <SYM>: NNNNN ticks so far, jumping to recent 90min for full context` immediately before the ENTRY SIGNAL — i.e., the symbol just appeared in the catchup queue, the detector replayed historical bars, armed at a level that is well below current tape, and fired the moment the seed completed.

These 7 events are documented but excluded from the headline because they're not real-time
Alpaca-vs-tape latency races; they're stale-signal-vs-current-tape mismatches caused by the
seed-staleness path. UCAR 2026-04-08 19:31 is additionally excluded because Alpaca rejected
the order outright (`"asset UCAR is not tradable"`), so there's no broker-side timeout to
analyze.

### 1.7 Data sources

| Source | Use |
|---|---|
| `logs/2026-04-*_daily.log` | Event extraction (11 single-shot timeouts) |
| `tick_cache/<DATE>/<SYM>.json.gz` | Tick reconstruction (IBKR feed) |
| `bot_v3_hybrid.py:2820-3000` | Retry loop reference; pattern emit points |
| `CLAUDE.md` "Entry slippage + retry" section | Parameter reference |
| `simulate.py:375` | Backtest fill model |

---

## 2. Per-Event Classification Table

| Date | Time (ET) | Sym | Cat | Score | Qty | Orig $ | Limit $ | Last pre-tick | First post-tick | % above limit | Classification | Sim PnL 2R |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-06 | 09:48:00 | FCUV | rth | 9.2 | 2062 | $8.45 | $8.47 | $9.245 | $9.226 | **+8.92%** | B_GENUINE_CHASE | +$701 |
| 2026-04-06 | 16:03:26 | FCUV | eh_artifact | 11.0 | 3093 | $5.02 | $5.04 | $5.471 | $5.470 | **+8.53%** | B_GENUINE_CHASE | +$680 |
| 2026-04-06 | 16:07:26 | MLEC | eh_artifact | 10.0 | 3093 | $10.02 | $10.04 | $11.59 | $11.61 | **+15.64%** | B_GENUINE_CHASE | +$680 |
| 2026-04-08 | 19:30:30 | BBGI | eh_artifact | 11.0 | 4330 | $5.02 | $5.04 | $5.54 | $5.54 | **+9.92%** | B_GENUINE_CHASE | +$953 |
| 2026-04-08 | 19:34:03 | ELPW | eh_artifact | 10.0 | 7424 | $2.02 | $2.04 | $2.20 | $2.19 | **+7.35%** | B_GENUINE_CHASE | +$891 |
| 2026-04-09 | 16:06:01 | CLIK | eh_artifact | 10.4 | 4330 | $3.02 | $3.04 | $3.30 | $3.30 | **+8.55%** | B_GENUINE_CHASE | +$953 |
| 2026-04-09 | 16:08:04 | ELAB | eh_artifact | 11.0 | 4330 | $5.02 | $5.04 | $5.34 | $5.33 | **+5.75%** | B_GENUINE_CHASE | +$953 |
| 2026-04-13 | 07:34:00 | SKYQ | pm | 8.0 | 3121 | $16.02 | $16.04 | $17.38 | $17.39 | **+8.42%** | B_GENUINE_CHASE | +$687 |
| 2026-04-13 | 16:06:05 | RECT | eh_artifact | 10.0 | 4305 | $2.02 | $2.04 | $2.17 | $2.17 | **+6.37%** | B_GENUINE_CHASE | -$474 |
| 2026-04-15 | 09:41:00 | OKLL | rth | 9.3 | 1237 | $9.50 | $9.52 | N/A | N/A | N/A | C_NO_DATA | (sim: +$569) |
| 2026-04-15 | 10:11:00 | MNTS | rth | 12.0 | 4316 | $5.69 | $5.71 | N/A | N/A | N/A | C_NO_DATA | (sim: N/A) |

**Headline pattern:** across all 9 events with tick coverage, the *first* post-signal tick is 5.75-15.64% above the bot's limit. There is no Alpaca-latency window in which a faster broker could have caught the tape at the limit price. The signal fired late; the tape was already gone.

---

## 3. The (A) Cohort: Quantification

There are **zero** events in the (A) Alpaca-too-slow cohort across the entire April single-shot timeout dataset.

| Metric | Value |
|---|---|
| Count | 0 |
| Total slippage (final_fill_price - original_limit) x qty | N/A |
| Distribution of latency (time-to-touch vs 10s window) | N/A |
| Mean / median / max touch latency | N/A |

This is the headline finding. Stated in the form Manny's hypothesis predicted: **"If Alpaca latency were the structural problem, this is where it would show up: the first attempt failed because Alpaca was slow, the retry caught the price after Alpaca caught up."** The April cohort produces zero events that match the latency-induced-miss pattern.

What we see instead is the same pattern across all 9 tick-covered events:
- t=0: signal fires (1-minute bar close)
- t=0 first tick: already +5% to +16% above limit
- t=0 to t=10s: tape stays above limit (often higher highs)
- t=10s: broker times out the unfillable resting limit

A broker with zero latency would still see exactly this market data and still not fill, because the *limit was below the bid*. This is not a latency race; it's a stale signal.

---

## 4. The (B) Cohort: Detail

The (B) cohort is the "genuine chase needed" cohort. Brief notes per event:

### 4.1 FCUV 2026-04-06 09:48 ET (in-scope, RTH)
- Tape range pre-signal (last 60s): $8.31-$9.48 — tape was ABOVE limit ($8.47) for most of pre-signal window
- The last tick at-or-below $8.47 was **49 seconds before** the signal fired. The tape was trading at $8.46 around 09:47:11, then ran to $9.48 by 09:48:00, the moment the signal fired.
- Post-10s window: $8.71-$9.27. Never touched $8.47.
- Post-60s window: $8.49-$9.27. Closest was $8.49, $0.02 above limit. Still untouched.
- Outcome had it filled: target $8.83 hit (forward sim), +$701 sim PnL

### 4.2 SKYQ 2026-04-13 07:34 ET (in-scope, premarket)
- Tape range pre-signal: $17.34-$17.52 — tape was 8-9% **above** $16.04 limit for entire pre-60s
- Limit was set at the whole-dollar $16.02 level; tape had broken $16 way before signal
- Post-60s: $16.89-$17.39. Never close to $16.04
- Outcome had it filled: target $16.28 hit, +$687 sim PnL

### 4.3 RECT 2026-04-13 16:06 ET (eh_artifact)
- Post-close (16:06 ET); fresh seed-replay; tape at $2.17 when limit set at $2.04
- Tape continued post-signal at $2.16-$2.18, ended at session close at $2.04-ish but eventually rolled to a session_close sim outcome of -$474
- Note: RECT had a successful FILL at $2.0300 earlier same day at 09:14 ET (real-time signal). The 16:06 fire was a stale-seed artifact.

### 4.4 EH artifacts (FCUV 04-06 16:03, MLEC 04-06 16:07, BBGI 04-08 19:30, ELPW 04-08 19:34, CLIK 04-09 16:06, ELAB 04-09 16:08)
- All fire within seconds of `[SEED] <SYM>: NNNNN ticks so far, jumping to recent 90min for full context`
- All armed at $X.02 level break (whole-dollar) but tape is at +7-16% above that level
- Bot logic: detector replays bars; arms at level break; first post-seed live tick triggers the entry signal; bot submits at +$0.02 over level which is way below current tape
- This is the same failure mode as the SLE 2026-05-15 evening 6-cluster (resume-boot loop) — just a different boot-up path (catchup-during-add vs. resume-from-disk)

### 4.5 (B) cohort sim P&L sum
| Subgroup | Sum sim PnL |
|---|---|
| In-scope B (FCUV 04-06 09:48, SKYQ 04-13 07:34) | +$1,388 |
| EH artifact B (7 events) | +$4,636 |
| Combined | +$6,024 |

But this counterfactual is **moot** because no broker, however fast, would have filled
these orders at the limit. The "sim PnL" column tells us what the bot **would have made if
the chase had worked** — not what a different broker would have given us. The current
chase / retry / cap mechanism captures most of the in-scope upside (FCUV/SKYQ are RTH /
PM events that may have a different outcome under the post-04-15 retry logic — see §6).

---

## 5. Estimated IBKR Recovery Range

Per the directive, three assumptions:

| Assumption | Description | (A) cohort recovery | Total recovered P&L |
|---|---|---|---|
| 50% IBKR-fills | "IBKR would fill half of the latency-misses" | 50% × $0 | **$0** |
| 80% IBKR-fills | "IBKR's lower latency catches most" | 80% × $0 | **$0** |
| 95% IBKR-fills | "Near-perfect broker-side fills" | 95% × $0 | **$0** |

Under any plausible IBKR-fill assumption, recovered P&L from broker latency is **$0** for the April pre-retry single-shot cohort. The signal-time market price was already past the limit; broker speed is irrelevant.

For completeness: even if I expand the universe to include the 7 EH artifacts (which it would
be wrong to do, since those are stale-seed bugs and not real-time order races), the (A)
cohort is still zero events.

---

## 6. Broker-Switch Verdict

**Verdict: NO. Do not switch from Alpaca to IBKR on the basis of fill latency.**

Combined with the May max-chase audit, we now have:

| Audit | Cohort | (A) Alpaca-too-slow events | Recovered P&L at 80% IBKR-fills |
|---|---|---|---|
| 2026-05-18 max-chase | 8 real-signal post-retry chase-cap aborts | 2 of 8 (LNKS, QUCY) but partial-fill-only (single-tick at limit) | <$1,000 net |
| 2026-05-18 pre-retry (this audit) | 4 in-scope April single-shot timeouts | 0 of 4 | $0 |

Across both audits — covering **12 real-signal in-scope events over April-May 2026** — the
total broker-attributable P&L recovery is **<$1,000**.

The **threshold dollar number that would flip the verdict** is roughly **$5,000+** in
recovered P&L per 30-session window — that would justify:
- IBKR live-trading infrastructure debugging time (which already cost weeks during the March migration)
- Real-money risk of running both brokers in parallel during cutover
- The known IBKR routing-cost / market-impact differences for small-cap thin tickers (IBKR's SmartRouting will often quote tighter spreads but route at exchange-pegged orders that get pulled when the tape moves — not necessarily faster fills than Alpaca's smart router on these names)

We're at ~$0 - $1K over 12 events. Far below the threshold.

**The actionable findings remain on detection-timing and execution-software:**
1. Why is the squeeze signal firing 5-16% above the limit?  → 1-minute-bar-close detection latency vs. tick-stream level-break-trigger
2. Resume-boot / catchup seed-replay loops (the 7 EH artifacts here + the 6 SLE evening events in the May audit) — same software bug, two firing paths
3. Tick-cache persistence gap on 2026-04-15 (OKLL/MNTS missing) — already mostly closed by 2026-05-01 backfill, but 04-15 morning specifically is not in the refetched range

**None of these require a broker change.**

---

## 7. Limitations

1. **Sample size.** 4 in-scope events is a low-frequency dataset. The 90% confidence
   interval on "$0 alpaca-attributable P&L" is admittedly wide given that small N — but
   the *direction* of the signal is unambiguous: every event with tick data shows the
   tape +5-16% above the limit at signal time. Even tripling the cohort with the 7 EH
   artifacts doesn't produce a single (A) event.

2. **Tick cache fidelity (OKLL/MNTS gap).** 2026-04-15 morning is the one data hole
   in the in-scope cohort. The previously documented persistence gap was largely closed
   by the 2026-05-01 backfill, but 04-15 was not in the rerun window (which is unfortunate
   because that's the day the retry mechanism shipped). If you want full closure, refetch
   the IBKR tick stream for 04-15 09:30-12:00 ET. Based on the consistent pattern across
   the other 9 events, my prior on OKLL/MNTS would be (B) — but I can't prove it without
   the ticks.

3. **10s window assumption.** I used the documented `WB_ENTRY_RETRY_TIMEOUT_SEC=10` value.
   For April single-shot events, this is the actual broker timeout. The bot does not log
   sub-second order-status polling, so I can't measure the *exact* moment Alpaca first
   acknowledged the order vs. when the tape was above limit. A real Alpaca-latency
   diagnostic would require sub-second `_finalize_latency_record` data (see
   `bot_v3_hybrid.py:2880-2888`) which is gated `WB_LATENCY_DIAGNOSTIC_ENABLED` and was
   not active in April.

4. **Market impact not modeled.** A 4,000-share market order on a $2 small-cap *would*
   move the tape. My counterfactual assumes infinite liquidity at the limit. This is the
   same caveat as §9.1 of the max-chase audit. It cuts against the broker-switch verdict
   even further: a faster broker on a thin tape would mostly produce wider effective slippage.

5. **Counterfactual fill model.** I use `orig_limit + $0.02` (deterministic slippage) for
   the sim P&L column. This matches `simulate.py:375`. For events where the tape was
   far above the limit, this is an extremely optimistic assumption — but since the (A)
   cohort is empty, it doesn't affect the verdict; it only affects the (B) "if the chase
   had worked" column.

6. **Pre-2026-04-15 vs post.** The retry mechanism shipped 2026-04-15. April 6-14 events
   are pre-retry single-shot; April 15 onward had retry enabled but live trading wasn't
   in full swing yet. OKLL/MNTS on 04-15 are technically post-retry-deployment events
   that nonetheless show single-shot behavior in the log (no `RETRY n/3` lines), suggesting
   either the gate was off that day or the timeouts cancelled fast enough that no retry
   was attempted. Either way, they fit the "first attempt failed" template the audit was
   designed to investigate.

7. **Categorization of EH artifacts.** I excluded 7 events as "not real-time latency
   races" because they're seed-replay re-fires. This is a judgment call; a strict reading
   of the directive would include them as pre-retry single-shot timeouts. Including them
   does not change the verdict (still 0 of 11 in (A)).

---

## 8. Files

- This report: `/Users/duffy/warrior_bot_v2/cowork_reports/2026-05-18_pre_retry_latency_audit.md`
- Analysis script (scratch, not committed): `/tmp/wb_pre_retry_audit/full_analyze.py`
- Per-event JSON (scratch): `/tmp/wb_pre_retry_audit/results.json`
- No production files modified

---

## 9. Summary Statement

The May max-chase audit asked: *"For events that survived 3 retries, did Alpaca latency cost us money?"* Answer: **no, the price genuinely ran**.

This April pre-retry audit asked: *"For events where the **first** attempt failed in 10 seconds and never retried, did Alpaca latency cost us money?"* Answer: **also no**.

The bot's structural problem is **not broker latency**. The structural problem is that the
squeeze signal fires on 1-minute bar close, and on parabolic small-caps the tape has
already run 5-16% past the breakout level by the time the bar closes. No broker, however
fast, can fill a limit below the bid. Investing engineering hours in an IBKR-live cutover
will not recover lost P&L — investing them in tick-stream-based level-break detection
might. That's the next directive worth writing.

---

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
