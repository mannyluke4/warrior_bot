# CC Follow-up to Phase 1 Parity Matrix

**Date**: 2026-05-22
**Branch**: `v2-ibkr-migration`
**Source**: `cowork_reports/2026-05-22_sim_live_parity_matrix.md` (Cowork's Phase 1)
**Status**: Findings from CC's investigation of the matrix's open questions

---

## Answers to Cowork's open questions

### Q1: Dump sim's per-trade list for MTVA 2026-05-22

Done. With current shipped config (`WB_BT_MOVE_STRIKE=1 WB_BT_MOVE_HWM_EXIT=1 WB_BT_MOVE_REENTRY_GREEN=1 WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR=1 WB_BT_MOVE_STAY_ARMED=1 WB_BT_MOVE_MAX_BELOW_ARM_PCT=3.0`, slippage `$0.07`):

| Sim# | Time ET | Type | Entry | Exit | Reason | P&L |
|---|---|---|---|---|---|---|
| 1 | 07:25 | MOVE_STRIKE (s=9.0) | $3.90 | $3.94 | move_hwm_exit | +$186 |
| 2 | 07:42 | REENTRY(GREEN) | $3.89 | $3.81 | move_stop_prox_bail | −$400 |
| 3 | 10:22 | STAY_ARMED (s=50) | $3.93 | $4.01 | move_hwm_exit | +$82 |
| 4 | 10:29 | REENTRY(GREEN) | $4.04 | $4.12 | move_hwm_exit | +$67 |
| 5 | 10:58 | STAY_ARMED (s=50) | $4.21 | $4.26 | move_hwm_exit (dd=50%) | +$58 |
| 6 | 11:08 | REENTRY(GREEN) | $4.19 | $4.26 | move_hwm_exit | +$85 |
| | | | | | **Total** | **+$77** |

### Q2: Why did live miss sim's entries?

Mapped each sim trade to live's behavior:

| Sim# | Sim ET | Live behavior at same moment | Cause |
|---|---|---|---|
| 1 | 07:25 | **No arm. Detector silent since 04:21 CHASE-SKIP** | **Detector arm-state divergence (see §below)** |
| 2 | 07:42 | No arm + no position to re-enter from | Same — no live arm = no live trade |
| 3 | 10:22 | No arm. Live armed at 10:28 (6 min later) | **Detector re-arm 6 min late** |
| 4 | 10:29 | No live trade until 10:39 (10 min later, on the 10:28 arm) | Live arm at 10:28 was new; took 11 min to fire entry. Sim's stay-armed re-fired immediately. |
| 5 | 10:58 | Live armed in stay-armed mode; took entry at 11:04 (6 min later) | Cool-down/continuation gate timing diff |
| 6 | 11:08 | Live entered at 11:09 (1 min later, basically matched) | Closest parity |

**Total P&L delta on the 4 trades the bots both took (sim 3-6 vs live 1-4)**: sim +$292, live tracker −$1,028, live broker −$1,973. The **$945 books-vs-broker gap is the fill bookkeeping issue** — separate from sim/live divergence on trade selection.

### Q3: Confirm MIN_ABSOLUTE_R is wired into sim

**Cowork already verified this** in the matrix (row #15 corrected): sim wires `min_absolute_r=0.10` via `WB_MIN_ABSOLUTE_R`. **Parity confirmed**. No action.

### Q4: Pull MTVA fills from Alpaca — per-trade books-vs-broker gap

Pulled this earlier in conversation. Per-trade:

| Live# | Sub-bot tracker | Alpaca real fills | Per-trade gap |
|---|---|---|---|
| 1 (10:39 MTVA) | −$389 | buy $3.98, sell $3.90 → **−$445** | −$56 |
| 2 (10:43 MTVA re-entry) | −$384 | buy $3.92, sell $3.83 → **−$1,151** | **−$767** |
| 3 (11:04 MTVA stay-armed) | +$154 | buy $4.21, sell $4.23 → **+$77** | −$77 |
| 4 (11:09 MTVA re-entry) | −$409 | buy $4.20, sell $4.10 → **−$455** | −$46 |
| **Total** | **−$1,028** | **−$1,973** | **−$945** |

Trade 2 is the dominant contributor — bot logged sell at "ref $3.88" but Alpaca filled at $3.83. The $0.05/share × 12,787 qty = $640 of the $767 gap. Note also entry: bot logged "anomaly $3.91" but Alpaca filled at $3.92. Both directions of slip.

---

## The single most surprising finding

**Live had a 6-hour MTVA detector silence**: armed at 04:11, chase-skipped at 04:21, then **the squeeze detector did not arm again until 10:28**. Sim's squeeze detector armed within that window (sim's first trade at 07:25 requires a fresh arm).

This isn't trade rejection. It isn't fill optimism. It's the detector itself making different decisions despite (in theory) the same input data.

Hypotheses for why live didn't re-arm during 04:21 → 10:28:

1. **Engine socket dropped ticks** (matrix #13) — sub-bot's bar history is shy of sim's by enough to fail the prime criteria. We have no logged evidence either way because `engine_seq` isn't validated.
2. **Level-tracker locked out** — after the 04:21 break to $4.55, the next available level to break (e.g., whole-dollar $5.00, or PDH) wasn't crossed. Sim might use a different level set or rolling-window HOD.
3. **V1 vs V2 detector behavior** — matrix #14 calls this out. Live uses SqueezeDetector (V1?) per `move_strike_subbot.py:333 (SqueezeDetector()` — let me verify which version sub-bot actually instantiates.

Verification (run after this draft was written):

```
move_strike_subbot.py:64 → from squeeze_detector_v2 import SqueezeDetectorV2 as SqueezeDetector
simulate.py:2486-2489    → conditional via WB_SQUEEZE_VERSION env var; DEFAULTS TO V1
```

**Important config issue found**: `WB_SQUEEZE_VERSION` is **not set anywhere** in `.env`, `daily_run_v3.sh`, `replay_live_universe.py`, or `run_backtest_v2.py`. Every MOVE_STRIKE backtest we've run for the past two days has been using V1 sim against V2 live.

**But — empirical test (re-running MTVA 5/22 with `WB_SQUEEZE_VERSION=2`)**:
Identical 6 trades / +$77 result. V1 vs V2 doesn't change MTVA's outcome today. So the env var IS a config issue worth fixing for hygiene, but **it is NOT the cause of today's MTVA divergence**.

The 6-hour live arm gap (04:21 → 10:28) remains structurally unexplained on this anchor case. Most likely cause:
- **Matrix #13 (engine socket dropped ticks)**: sub-bot's bar history differs from sim's clean cache replay. With no `engine_seq` validation, we have no logged evidence of drops.
- Could also be bar-boundary timing in real-time vs replay (matrix #11 says deterministic, but only "given identical tick streams" — which #13 may not deliver).

Cowork Phase 2 recommendation: build the dropped-tick audit (suggested in matrix #13) as the next investigation. The lack of `engine_seq` validation is suddenly looking like the most important gap to close.

---

## Recommendations for Cowork Phase 2 (baseline recalibration)

In addition to Cowork's existing list (entry-limit overshoot, exit-limit undershoot, R-floor), add:

4. **Detector-version verification**: confirm sub-bot and simulate.py both import SqueezeDetectorV2 (or both import V1). If they differ, the entire 11-day backtest is using a different detector than what shipped.

5. **engine_seq gap audit**: write a small script to scan today's `2026-05-22_move_strike_subbot.log` STATS lines and infer the tick rate. Compare to main bot's `2026-05-22_daily.log` MTVA tick rate over the same window. Quantify dropped-tick magnitude.

6. **Books-vs-broker daily reconciliation**: enable the new real-fill P&L logging (CC just shipped in commit b4b0b73) and produce a daily delta report. Today's $945 should narrow toward $0 once both bots are using actual fills.

---

## Memory writes proposed

Cowork suggested 3 memory notes after this audit. CC will save these following Manny's approval:

1. **Sub-bot internal P&L was anomaly→ref, not fill-based** — pin so we don't lose sight. Fix shipped in b4b0b73 but the gotcha is still important for future readers.
2. **Live entry limit = max(trigger, live_tape) + dynamic_slippage** — 2026-05-19 fix that creates an asymmetric sim/live divergence. Sim doesn't model this.
3. **R-floor parity confirmed** — both sim and live use `max(MIN_R, MIN_ABSOLUTE_R)` with default 0.10. Documented to prevent future re-investigation.

---

## Tasks updates

Re-prioritized based on Cowork's findings:

- **#26 (sim fill model audit)**: still open, now urgent. Phase 2 baseline recalibration depends on a fixed sim fill model.
- **NEW (detector version verification)**: highest priority — if sub-bot is on V1 while sim is on V2, the 11-day +$2,498 number is irrecoverable without re-running with matched detectors.
- **#28 (the broader audit)**: Phase 1 complete via Cowork's matrix. Phase 2 ready to start.

CC will verify detector version next.
