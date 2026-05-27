# Directive: REENTRY-HWM-Gate Live A/B/C Test (Variant C re-purpose)

**Date**: 2026-05-27
**Branch**: `v2-ibkr-migration`
**Owner**: CC
**Source**: `cowork_reports/2026-05-27_subbot_trade_deep_dive.md` (Day 1 A/B/C, n=2 REENTRY-HWM-after-loss pattern). Backtest harness blocked on Phase 3c bar-construction investigation (`cowork_reports/2026-05-27_phase3c_bar_construction_investigation_directive.md`), so backtest evaluation of the gate is unavailable. Manny chose to test the gate live alongside the A/B/C fade-gate comparison.
**Real-money go-live**: still ~2026-06-22.

---

**Pacing rule**: Live IS the test. Ship the gate code, flip ON for one variant, accept that the A/B/C clock effectively resets to Day 1 from change ship date. Paper accounts absorb the risk of being wrong about the gate.

---

## What this directive ships

### Code change 1 — REENTRY-HWM-gate logic in `move_strike_subbot.py`

Add env-gated logic that blocks REENTRY(GREEN) entries when the most recent prior exit on the same symbol was a `move_hwm_exit`. Default OFF.

**Env vars** (default values):

```
WB_MOVE_REENTRY_HWM_GATE_ENABLED=0        # master gate (default OFF)
WB_MOVE_REENTRY_HWM_GATE_WINDOW_MIN=30    # only gate if prior exit was within N minutes
```

**Implementation sketch**:

Add `self._last_exit_reason_by_symbol: dict[str, tuple[str, datetime.datetime]]` to `MoveStrikeSubBot.__init__`. The dict maps symbol → (exit_reason, exit_time_et).

Update on every exit (in `_close_position`, after the exit is confirmed): set `self._last_exit_reason_by_symbol[symbol] = (reason, datetime.now(ET))`.

Check at the REENTRY GREEN entry decision point: if `WB_MOVE_REENTRY_HWM_GATE_ENABLED=1`, look up the symbol's last exit. If reason starts with `move_hwm_exit` AND exit was within `WB_MOVE_REENTRY_HWM_GATE_WINDOW_MIN` minutes, log `REENTRY_HWM_GATE_BLOCK <symbol>` and skip the entry. Otherwise proceed normally.

**Important**: this is REENTRY GREEN only. The same trigger fires REENTRY BREAK on a different code path — that one is NOT gated by this directive. If the data later suggests BREAK has the same pattern, surface it but defer to a separate directive.

### Code change 2 — Variant C config in `daily_run_v3.sh`

Replace Variant C's V4 BodyCV fade-gate with the new REENTRY-HWM-gate. New Variant C config:

```bash
# Sub-bot C (REENTRY-HWM-gate, no fade-gate)
WB_SUBBOT_APCA_API_KEY_ID=$ACCOUNT_C_KEY \
WB_SUBBOT_APCA_API_SECRET_KEY=$ACCOUNT_C_SECRET \
WB_SUBBOT_LOG_SUFFIX=C \
[regime-shift env vars unchanged] \
WB_MOVE_REENTRY_HWM_GATE_ENABLED=1 \
WB_MOVE_REENTRY_HWM_GATE_WINDOW_MIN=30 \
# (V4 BodyCV env vars removed — no longer in Variant C)
python move_strike_subbot.py &
```

Variants A and B unchanged.

### Code change 3 — `scripts/abc_compare_daily.py` log parser

Update the parser to recognize `REENTRY_HWM_GATE_BLOCK <symbol>` log lines and count them per-variant in the daily report's "Fade-gate blocks" column. Rename the column to "Gate blocks" since C no longer has the BodyCV gate.

---

## Why replace Variant C (not add a 4th variant)

We have 3 Alpaca paper accounts. A 4th variant requires either a 4th paper account or sacrificing one of the existing slots. Per today's data:

- **V4 BodyCV (Variant C's current gate) fired exactly once today** (AMSS @ 13:31) and was immediately overridden by regime_shift entering 60 seconds later. **Zero effective contribution to C's behavior.** Sacrificing V4 BodyCV evaluation costs us the least.
- **V1 VWAP (Variant B's gate) had one real save** (AMSS @ 07:32) worth ~$384. Keeping B as the V1 VWAP variant preserves the highest-signal fade-gate test we have running.
- **A (control, no gates) is the baseline** — must stay.

So: A = control, B = V1 VWAP, C = REENTRY-HWM-gate (was V4 BodyCV). Clean experimental design where pairwise comparisons isolate single-gate effects.

If Manny wants to add a 4th paper account later and reintroduce V4 BodyCV as Variant D, that's a separate directive — but today's data suggests V4 BodyCV isn't worth running.

---

## A/B/C clock implication

Changing Variant C's configuration mid-test creates a discontinuity. Pre-change A/B/C data shouldn't be mixed with post-change A/B/C data for the variant comparison.

**Decision**: A/B/C variant clock effectively resets to Day 1 from the day this directive's code ships. Today's data (Day 1, post-orphan-fix) remains useful for absolute strategy-economics analysis (e.g., the regime_shift +$1,100 ASTC trade is real evidence regardless of variant config), but variant-comparison reporting starts fresh.

**Impact on 3-4 week clock**: real-money go-live target ~2026-06-22 was already a 3-4 week window from launch. The 1-2 day cost of resetting the clock is absorbed by the buffer.

---

## Validation criteria (what we want to see)

**Day 1 sanity check**: log shows `REENTRY_HWM_GATE_BLOCK` events firing in Variant C when prior-cycle exit reason was `move_hwm_exit`. If today's data pattern repeats, expect 1-2 block events per active day.

**Cumulative criterion** (over ~10 trading days):
- If Variant C beats Variant A by ≥ $500 cumulative AND most block events would have been losses if taken (verifiable from A's behavior on the same symbol/time): gate is working, ship it across all variants.
- If Variant C trails Variant A: gate is hurting, revert.
- If essentially tied: gate is null on this sample, defer decision until harness is rebuilt and we can backtest properly.

---

## What this directive does NOT include

- **No backtest validation**. Per Manny's call: live IS the test. Phase 3c investigation is happening in parallel; once harness validates, we can re-run REENTRY GREEN backtest as additional evidence.
- **No REENTRY BREAK changes**. Separate trigger, different mechanics. Out of scope.
- **No gate on initial entries**. The REENTRY-HWM-gate fires only on the REENTRY GREEN code path, never on initial setup entries.
- **No regime_shift changes**. Regime_shift entries don't go through the REENTRY pipeline at all, so they're unaffected by this gate.

---

## Sequencing for CC

1. Add `_last_exit_reason_by_symbol` tracking + REENTRY-HWM-gate check in `move_strike_subbot.py` (~20 min)
2. Update `daily_run_v3.sh` Variant C block to remove V4 BodyCV and add REENTRY-HWM-gate (~5 min)
3. Update `scripts/abc_compare_daily.py` to parse the new gate-block log line (~15 min)
4. Smoke test: launch one sub-bot with `WB_MOVE_REENTRY_HWM_GATE_ENABLED=1` for 5 minutes, confirm no crash and that gate-check fires correctly (~15 min)
5. Push with commit message describing the variant re-purpose
6. Document in `cowork_reports/2026-05-27_reentry_hwm_gate_impl_notes.md`

**Target**: full directive shipped within 1-2 hours. Ready for tomorrow's 02:00 MT cron.

---

## Risk

1. **False positives**: gate blocks a legitimate re-entry. Cost: opportunity loss on that trade. Mitigation: 30-min window means the gate only fires shortly after an HWM exit, so the "stale state" risk is bounded. After 30 min, REENTRY proceeds as before.
2. **Gate hides a real edge**: there ARE cases where green continuation after HWM exit is real (e.g., a brief flush followed by genuine continuation). Cost: missed winner. Mitigation: 10 trading days of data + comparison against Variant A reveals whether the gate is net-positive.
3. **Code bug in gate logic**: gate blocks every REENTRY or blocks nothing. Mitigation: smoke test before launch + cumulative log inspection on Day 1.

---

## Deliverable

`cowork_reports/2026-05-27_reentry_hwm_gate_impl_notes.md`:
- Code changes summary
- Smoke test log showing the gate check fires correctly
- New env-var values in `daily_run_v3.sh` Variant C block
- Sample `REENTRY_HWM_GATE_BLOCK` log line

Going forward, the daily A/B/C report shows the gate-block count for Variant C and the cumulative running total for the 10-day evaluation window.
