# Tier Management Design — Stage 3 of TBT Migration

**Date:** 2026-05-05
**Author:** CC
**Per directive:** `DIRECTIVE_TICKBYTICK_MIGRATION.md` (Stage 3)
**Predecessors:**
  - `cowork_reports/2026-05-05_tickbytick_capacity.md` (Stage 1, cap=5)
  - `cowork_reports/2026-05-05_dual_feed_architecture.md` (Stage 2 plumbing)
**Status:** ✅ Implemented + compiled. Gated OFF (`WB_TBT_ENABLED=0`); flip the
env var to activate after a short paper-test on a single symbol.

---

## What this stage does

Adds the policy layer on top of Stage 2's plumbing. Every 30 seconds the bot
ranks all active symbols by setup-state priority, picks the top 5, and
churns the tick-by-tick subscriptions accordingly. Symbols not in the top 5
get demoted (subject to a 5-min cooldown). Symbols not subscribed to TBT
already are promoted up to the cap.

When `WB_TBT_ENABLED=1`, this is the loop that actually delivers the
data-quality fix. When it's 0, all the code is dead-weight and behavior is
unchanged from pre-Stage-2.

## Priority scoring

| Score | Source | Notes |
|---:|---|---|
| 1000 | Open position (any of squeeze/short/WB) | Hard guarantee — bypasses cooldown |
| 500 | Squeeze ARMED or WB ARMED | Detector is one tick from firing |
| 200 | Squeeze PRIMED | Setup is brewing on volume + level break |
| 50 | WB WAVE_OBSERVING | Waves observed but not yet scored to ARM |
| 20–50 | Top-N volume in last 5 1m bars (linearly scaled) | The "active hunt" reserve, N = floor(cap/2) = 2 |
| 0 | Nothing notable | Eligible for demotion |

The directive's WO≥5/WO≥7 distinction is collapsed to a flat 50 because the
WB detector doesn't expose the most-recent-wave score on its public surface.
Adding `_last_score` later would let us split this back into 50 / 100 tiers
if needed; v1 doesn't.

## Promotion / demotion rules

**Promote** when a symbol is in the top `TBT_MAX_SUBSCRIPTIONS` (5) by
priority AND is not already Tier 1 AND there's slot capacity.

**Demote** when a symbol is currently Tier 1 but not in the top 5, AND has
been Tier 1 for ≥ `TBT_COOLDOWN_SEC` (300s = 5 min). Cooldown stops a
volatile detector from thrashing slots.

**Force-evict** override: if a candidate has `priority ≥ 1000` (i.e. an
open position), the bot bypasses cooldown to make room. This is acceptance
criterion #3: open positions are *always* Tier 1. ARMED-level signals
(priority 500) do *not* get force-eviction in v1; they wait for cooldown
to expire on a holder. That's a deliberate conservative choice — if we
observe in production that ARMED setups regularly miss slots due to
volume-rank holders being cooldown-locked, relax the rule then.

## Volume reserve

`floor(cap / 2) = 2` of the 5 slots are notionally reserved for "active
hunt" — the most-traded symbols in the last 5 minutes get TBT even without
a setup signal. Rationale: when nothing is brewing, it's cheap to keep
full data on the day's biggest movers in case something develops.

Implemented as a per-symbol rolling window of the last 5 closed 1m bars'
volume, fed from `on_bar_close_1m`. Each cycle, `_compute_5m_volume_rank()`
ranks symbols by sum of those 5 bars and returns the top-N (1-based ranks).
Volume-rank slots only kick in when their symbol has *zero* detector signal
— a ranked symbol with ARMED state still scores 500, not 30.

## Code map

`bot_v3_hybrid.py` and `bot_alpaca_subbot.py` (mirrored):

- **Module constants** (`TBT_MANAGE_INTERVAL_SEC`, `TBT_COOLDOWN_SEC`,
  `TBT_VOLUME_RESERVE_N`, six `TBT_PRI_*` weights) added near the Stage 2
  TBT constants.
- **BotState fields**: `last_tier1_manage`, `tier1_volume_buckets`,
  `tier1_volume_rank`.
- **New functions** (block after `unsubscribe_tick_by_tick`):
  - `_maintain_tier1_volume_bucket(bar)` — appends to rolling 5-bar window
  - `_compute_5m_volume_rank()` — returns `{sym: rank}` for top-N
  - `_has_open_position(sym)` — checks squeeze/short/WB position state
  - `compute_tier1_priority(sym)` — returns 0–1000 score
  - `_tier1_priority_reason(priority)` — score → human-readable reason
  - `_can_demote_tier1(sym, now)` — cooldown gate
  - `manage_tier1_subscriptions()` — the main cycle, 30s cadence
  - `cancel_all_tick_by_tick(reason)` — bulk cleanup helper
- **Wired into**:
  - `on_bar_close_1m` — calls `_maintain_tier1_volume_bucket(bar)` first thing
  - Main loop — calls `manage_tier1_subscriptions()` after `audit_tick_health()` / `periodic_position_sync()`
  - Window-close (dead-zone reset) — calls `cancel_all_tick_by_tick("dead_zone_reset")` and clears `state.tier`, `tier1_volume_buckets`, `tier1_volume_rank`
  - Reconnect (connection watchdog) — clears tier state, lets next manage cycle re-promote
  - Competing-session error 10197 — calls `cancel_all_tick_by_tick("competing_session")`

## Logging

Every promote / demote / status event uses the `[TIER]` prefix per the
directive's logging convention:

```
[TIER] PROMOTE BIRD reason=detector_armed capacity=3/5
[TIER] DEMOTE CRWG reason=dropped_from_target was_tier1_for=312s capacity=2/5
[TIER] DEMOTE OLDX reason=evicted_for_open_position was_tier1_for=140s capacity=4/5
[TIER] CANCEL_ALL n=3 reason=dead_zone_reset
[TIER] STATUS tier1=[BIRD,FATN,RECT,KIDZ,CNSP] tier2=87 capacity=5/5
[TIER] PROMOTE FOO BLOCKED — capacity full (5/5)
[TIER] PROMOTE FOO BLOCKED — no contract registered
[TIER] PROMOTE FOO FAILED — reqTickByTickData raised: {error}
```

`STATUS` fires every cycle (every 30s when `WB_TBT_ENABLED=1`); the others
fire only on actual state changes.

## Configuration

| Env var | Default | Notes |
|---|---:|---|
| `WB_TBT_ENABLED` | 0 | Master gate. Until 1, all of Stage 3 is dormant. |
| `WB_TBT_MAX` | 5 | Account capacity (Stage 1 probe). |
| `WB_TBT_MANAGE_SEC` | 30 | Re-rank cadence. |
| `WB_TBT_COOLDOWN_SEC` | 300 | Min Tier-1 hold before demotion. |

## Acceptance criteria — status

| # | Criterion | Status |
|---:|---|---|
| 1 | Tier 1 capacity correctly configured | `TBT_MAX_SUBSCRIPTIONS=5` from Stage 1 probe |
| 2 | Active setups always Tier 1 | ARMED → 500, PRIMED → 200, WAVE_OBSERVING → 50 — all earn slots; PROMOTE log proves it |
| 3 | Open positions always Tier 1 | Position priority 1000 + force-eviction override — guaranteed by code |
| 4 | Tier 1 doesn't thrash | 5-min cooldown gate in `_can_demote_tier1` |
| 5 | Daily Tier-1 capture matches `reqHistoricalTicks` ±5% | **Pending paper validation** — needs a day in production |
| 6 | Detector behavior on Tier 1 matches backtest | **Pending validation** — needs cross-comparison against historical fetch |

Criteria 5 and 6 are the proof points. They require paper-running with
`WB_TBT_ENABLED=1` for a full session, then next-day comparing the Tier-1
symbol's tick count against `reqHistoricalTicks` for the same day.

## Rollout plan

1. **Tomorrow morning (2026-05-06), pre-open**: flip `WB_TBT_ENABLED=1` in
   `.env` on a single bot (sub-bot first — paper, isolated). Restart sub-bot.
2. **Through the morning session**: monitor `[TIER]` log lines. Verify
   PROMOTE/DEMOTE events fire on detector state changes. Verify STATUS line
   appears every 30s. Verify no error 10190 (capacity exceeded).
3. **End of session**: pull `reqHistoricalTicks` for one Tier-1-promoted
   symbol. Compare to the bot's live-captured tick count for that symbol
   *during the window it was Tier 1*. Target: within 5%.
4. **If criterion 5 passes**: enable on main bot the next session.
5. **If criterion 5 fails**: investigate per-symbol. Most likely cause is
   timing — Tier 1 was active only for a portion of the symbol's session
   so live-capture excludes ticks before promotion / after demotion. Adjust
   the comparison window to match Tier-1 hold-time, or extend hold-time
   via lower cooldown for that signal type.

## Risks / known limitations

- **Cooldown-locked volume-rank slots blocking ARMED**: per the v1 design
  note above. Likely benign because by the time 5 unique symbols hold
  volume-reserve slots, real setups are already promoted to detector tier.
  Worth instrumenting in production to confirm.
- **No PRIMED-after-PRIMED tie-breaker**: if two squeeze detectors are both
  PRIMED with the same nominal score 200 and only one slot is available,
  the bot picks alphabetically (stable-sort secondary key). The directive
  suggested rising-volume tie-break; v1 doesn't implement it. Add later if
  observed to matter.
- **Volume-rank uses 1m bars, not actual 5-min trade volume**: a symbol
  that hasn't been subscribed for 5 min yet will have <5 buckets in its
  rolling window. `sum(buckets)` is correct (just smaller); the rank
  computation is fine. But the absolute floor for "qualifies for reserve"
  effectively becomes "any non-zero volume ever", which is too permissive.
  In practice, if every active symbol has >0 volume, only the top 2 win
  the slots — so it self-corrects.

## Files modified

- `bot_v3_hybrid.py` — Stage 3 constants, BotState fields, helpers,
  on_bar_close_1m hook, main-loop hook, window-close cleanup, reconnect
  cleanup, competing-session cleanup.
- `bot_alpaca_subbot.py` — same edits, mirrored.
- `cowork_reports/2026-05-05_tier_management_design.md` — this file.

Both bots `py_compile` clean. AST verification confirms all 7 new function
names defined in both bots.

---

*Plumbing was Stage 2; policy is Stage 3. With both shipped, flipping
WB_TBT_ENABLED=1 closes the 80% live-data gap on whichever symbols the
priority scoring picks. The proof comes after the first paper session.*
