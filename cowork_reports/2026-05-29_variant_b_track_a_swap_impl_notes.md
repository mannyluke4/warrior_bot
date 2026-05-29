# Variant B Swap: V1 VWAP → FIRESTORM-gate + Track A

**Date**: 2026-05-29 (Friday morning)
**Owner**: CC
**Source**: Manny's call to retire V1 VWAP and slot Track A live alongside FIRESTORM-gate, per the in-conversation rationale and `cowork_reports/2026-05-28_track_a_results.md` (Track A passed all 5 acceptance criteria by 1.8-3.5× margins). Cowork's formal Phase 4b directive deferred — Manny accelerated the timeline because Variant B has been bleeding without producing data we don't already have.

---

## TL;DR

Variant B's V1 VWAP fade-gate test is **retired effective today**. Variant B is being re-purposed as the live test slot for **FIRESTORM-gate + Track A combined** (the most aggressive defensive stack). MAIN_APCA paper account is being reset by Manny; new keys will replace the existing `MAIN_APCA_API_KEY_ID/SECRET` env vars on a 1:1 basis. Code already pushed; cron picks up the new config Monday 2 AM MT.

---

## Why retire V1 VWAP now

Cumulative paper P&L for the week (excluding 2026-05-26's orphan-bug-flagged day):

| Variant | Mon-Fri net | Cumulative equity | Trades |
|---|---|---|---|
| A (control → FIRESTORM-gate from 5/28) | **-$230** | $30,180 | 4 entries / 9 orders this week |
| **B (V1 VWAP)** | **-$2,092** | **$25,300** (~-$4.7K from week start) | 6 entries / 13 orders today alone |
| C (V4 BodyCV → REENTRY-loss-gate from 5/27 PM) | -$526 | $27,051 | 3 entries / 7 orders this week |

V1 VWAP has been the worst gate on the bench for the entire test. The hypothesis it was testing ("VWAP fade-gate blocks bad entries") has effectively been falsified: the gate rarely triggers and isn't catching the actual failure modes. We've extracted the learning.

Today alone V1 VWAP took 6 entries that the FIRESTORM-gate (on A) blocked, every one of which lost money:
- STG regime_shift -$488 (entry $6.59, exit $6.23 hard stop on $0.37 R)
- STG REENTRY +$51
- PRFX -$368 (hard stop on $0.19 R)
- PRFX REENTRY $0
- ATPN-class -$100
- (More)

Variant A on the same arms had 0 entries today (gate blocked all sub-firestorm bars) and zero P&L impact. Direct evidence that the FIRESTORM-gate's edge dominates V1 VWAP's at YTD scale.

---

## Why slot Track A in now (not wait for Phase 4b directive)

Track A passed all 5 Phase 4 acceptance criteria yesterday:
- YTD combined delta: +$106,842 (3.5× threshold)
- FT delta: +$73,630 (1.8× threshold)
- REGIME_SHIFT delta: +$29,262
- Worst single trade: -$4,006 (inside the -$5K floor)
- AMSS-class trace: -$740 → -$580

The framework defaults OFF in live and is already shipped in `move_strike_subbot.py` and `exit_track_a.py` (commit `f0dfaee` yesterday). Cowork's Phase 4b directive was queued but the live flip can ship without it because the env-gate ensures bit-identical pre-existing behavior on A and C.

Manny's reasoning for accelerating: "No sense in keeping bleeding accounts alive when we've seen what we set out to learn." B's slot is the obvious target.

---

## What changes today

### `daily_run_v3.sh:376`

**Before**:
```bash
launch_subbot B "$MAIN_APCA_KEY" "$MAIN_APCA_SECRET" "WB_MOVE_FADE_VWAP_ENABLED=1"
```

**After**:
```bash
launch_subbot B "$MAIN_APCA_KEY" "$MAIN_APCA_SECRET" \
  "WB_MOVE_FIRESTORM_GATE_ENABLED=1 WB_MOVE_FIRESTORM_GATE_MIN_TICKS_PER_MIN=6000 WB_EXIT_TRACK_A_ENABLED=1"
```

Track A uses default threshold env vars (`WB_EXIT_R_FLOOR_ABS=0.10`, `WB_EXIT_R_FLOOR_PCT=0.05`, `WB_EXIT_DD_PHASE1_PCT=0.50`, etc.). No need to override.

### `scripts/abc_compare_daily.py:38` VARIANTS list

**Before**: `("B", "V1 VWAP",  "MAIN_APCA_API_KEY_ID", "MAIN_APCA_API_SECRET_KEY")`

**After**: `("B", "FIRESTORM-gate + Track A",  "MAIN_APCA_API_KEY_ID", "MAIN_APCA_API_SECRET_KEY")`

### Today's runtime actions (this morning, pre-Monday-cron)

1. **OLOX position flattened** (was the only open position on B at -$10 unrealized). Sold 1041 shares @ $8.80 LIMIT. Clean exit.
2. **Variant B process killed** (PID 81137 → SIGTERM, then SIGKILL for cleanup).
3. **Main bot, Variant A, Variant C remain up and operating normally** (PIDs 81115, 81136, 81138).
4. Cumulative B realized P&L for the day stops at ~-$1,793 (the -$1,783 from log + -$10 OLOX flatten).

---

## Test design with this swap

| Variant | Entry filter | Exit framework | Comparison signal |
|---|---|---|---|
| A | FIRESTORM-gate | (default hard-stop) | Baseline for FIRESTORM-gate alone |
| **B** | **FIRESTORM-gate** | **Track A** | Track A's marginal contribution = B − A |
| C | (none) | (default hard-stop) | REENTRY-loss-gate (different defense class) |

**A vs B delta** isolates pure Track A effect with FIRESTORM-gate held constant. Specifically:
- On days A blocks everything (today's pattern) → B also blocks everything → no Track A signal that day. Acceptable.
- On days A takes 2-3 firestorm-grade entries → B takes the same entries with Track A's exit framework. Delta reveals whether the phased drawdown floor + R floor improves outcomes vs hard-stop.

This is the **deployment configuration** (max defense stack) — what would ship to real money on 6/22 if the test validates.

---

## Account reset + key rotation

Manny is resetting the MAIN_APCA paper account (wiping the -$4.7K cumulative loss, restoring ~$30K equity). New keys will be provided.

**Whether to repoint env vars depends on what Manny provides:**
- If same MAIN_APCA account with new keys → just replace the existing `.env` values (1:1 swap)
- If a new account entirely → still use `MAIN_APCA_API_KEY_ID/SECRET` env-var names so `daily_run_v3.sh` and the abc_compare config don't need additional edits

Either way, when the keys land, CC will:
1. Update `.env` with new credentials
2. Verify Alpaca connectivity via a quick smoke (account.equity > 0, no positions, no orders)
3. Confirm Variant B is configured and will launch correctly Monday 2 AM MT

Until keys arrive, Variant B stays dark. Main bot, A, and C continue operating normally.

---

## What this swap does NOT change

- **No new entry-side logic.** FIRESTORM-gate is the existing entry filter (shipped 2026-05-28).
- **No code changes to `exit_track_a.py` or `move_strike_subbot.py`.** Track A code already shipped yesterday; today's swap just sets the env var.
- **No live behavior on Variants A or C.** Both unchanged. Track A defaults OFF for them.
- **No real-money go-live decision.** Still 2026-06-22; this is paper validation.
- **No retroactive changes to V1 VWAP results.** Historical Variant B data (5/23-5/29) preserved as the V1 VWAP test record.

---

## Monday cron behavior

`daily_run_v3.sh` already has the new launch line. Monday 2 AM MT cron will:
1. Launch main bot (IBKR, AvailableFunds sizing)
2. Launch Variant A (FIRESTORM-gate)
3. Launch Variant B (**FIRESTORM-gate + Track A — first live day**) — *only if keys are in place in .env*
4. Launch Variant C (REENTRY-loss-gate)
5. If B's keys aren't in `.env`, `launch_subbot()` will print "WARN: variant B has no API keys" and skip — fail-safe.

---

## Tracking + decision criteria

By 2026-06-15 (Manny's evaluation window for 6/22 real-money go-live), Variants A and B will have ~2 weeks of live data each. Compare:

- **B − A**: Track A's marginal contribution at live scale
- **B absolute P&L**: is the FIRESTORM + Track A stack net positive?

Decision tree at 6/15:
- If B > A by ≥$500 → ship FIRESTORM + Track A to real money on 6/22
- If B ≈ A within $500 → ship FIRESTORM-gate alone (simpler, validated effect)
- If B < A by ≥$500 → Track A degrades at live scale despite sim wins; investigate the divergence before deciding

---

## Pending Cowork micro-directive (queued)

Per CC's response yesterday on the bot-vs-broker gap issue (`cowork_reports/2026-05-28_variant_b_accounting_gap_cc_response.md`): the daily_pnl persistence fix is queued for next week. With B now active again, restart accounting on B's first restart day will produce a gap that's expected, not orphan-class. The current `$1,000` threshold (raised yesterday) handles this.

---

## Cross-references

- Track A spec: `cowork_reports/2026-05-28_track_a_exit_framework_spec.md`
- Track A YTD validation: `cowork_reports/2026-05-28_track_a_results.md`
- FIRESTORM-gate impl notes: `cowork_reports/2026-05-28_firestorm_gate_impl_notes.md`
- Original A/B/C test directive: `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`
- Today's bot-vs-broker gap response: `cowork_reports/2026-05-28_variant_b_accounting_gap_cc_response.md`
