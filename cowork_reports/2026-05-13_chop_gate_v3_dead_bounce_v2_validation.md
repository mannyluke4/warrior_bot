# Chop Gate v3 — `dead_bounce` v2 Sub-Gate Re-Validation Report

**Date generated:** 2026-05-12T13:57:55-04:00
**Source repo:** /Users/duffy/warrior_bot_v2
**Sub-gate under test:** `dead_bounce` v2 patch (Cowork verdict 2026-05-12 §3 — AND→OR + day-range %)
**Patch summary:**
- Step 2 AND→OR exemption: `no_meaningful_drift = (drift_bars < 5) OR (drift_pct_of_range < 0.30)`
- ATR dependency removed; replaced by `cum_drift / day_range` (scale-invariant).
- New env: `WB_CG3_DEAD_BOUNCE_DRIFT_RANGE_MIN_PCT=0.30` (replaces `WB_CG3_DEAD_BOUNCE_ATR_MULT`).

**Sample size:** 22 closed WB trades (other sub-gates = observe-only)

## Acceptance criteria (directive §3 lines 152-159) — BLOCKING

| # | Criterion | Threshold | Result | Detail |
|---|---|---|---|---|
| 1 | All 4 winners preserved | 100% | **PASS** | 4/4 winners preserved |
| 2 | Top-3 winners preserved | 100% | **PASS** | ATRA 2026-05-08 +$2,499.59 (PASS), SST 2026-05-11 +$2,090.40 (PASS), FATN 2026-05-05 +$1,073.59 (PASS) |
| 3 | FATN 5/8 13:58 loser blocked | yes | **FAIL** | FATN 2026-05-08 13:58 -$771.60 PASS (verdict: `dead_bounce_no_drift(bars=0,pct=1.00)`) |
| 4 | Zero new false positives vs MACD+HOD_RECENT combined | yes | **PASS (vacuous)** | dead_bounce blocks 0 trades total under v2; cannot introduce a FP |

**Overall:** **FAIL** — criterion 3 is the deal-breaker per directive line 149.

## Why FATN 5/8 13:58 slips through under v2

At the moment of arm (440 bars into session), the patch measures:
- `drift_streak = 0` (no consecutive lower closes after HOD in post_hod slice) → already < 5 → exemption fires on the OR's first branch alone.
- `drift_pct_of_range = 1.00` is not even consulted — the OR short-circuits.

Because the v2 spec changed the no_meaningful_drift exemption from AND to **OR**, **every trade where `drift_streak < 5` is now exempted at step 2 regardless of its drift-percent**. On this 22-trade dataset, only one trade (FATN 5/5 11:56) has `drift_streak >= 5` (it shows `bars=4`, still <5). All others have `drift_streak ∈ {0,1,3}`. So the gate vetoes nothing on this dataset.

This is the inverse of the v1 failure mode (which fired too often). The v2 spec swings the exemption the other way: the OR is **more permissive** than v1's AND, not less.

The "shouldn't this work?" intuition in the directive (lines 142-147) assumed the OR would only fire on cases where _both_ conditions said no_drift. In practice, with `drift_streak` typically very small (0-3) on these arms, the streak branch alone exempts virtually everything.

## Per-trade decisions (chronological, v2 patch)

| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | Bars | v2 verdict | Reason |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-05 | 10:42 | CLNN | subbot | 7 | LOSS | $-653.04 | -1.03 | 134 | PASS | dead_bounce_no_drift(bars=1,pct=1.00) |
| 2026-05-05 | 11:08 | CLNN | subbot | 7 | LOSS | $-514.64 | -1.89 | 160 | PASS | dead_bounce_no_drift(bars=1,pct=1.00) |
| 2026-05-05 | 11:56 | FATN | subbot | 8 | LOSS | $-955.38 | -1.26 | 174 | PASS | dead_bounce_no_drift(bars=4,pct=0.69) |
| 2026-05-05 | 14:37 | CLNN | subbot | 9 | LOSS | $-673.20 | -1.35 | 365 | PASS | dead_bounce_no_drift(bars=1,pct=1.00) |
| 2026-05-05 | 14:39 | FATN | subbot | 8 | WIN | $+1,073.59 | +1.46 | 324 | PASS | dead_bounce_hod_not_early(age=197m) |
| 2026-05-05 | 14:56 | CLNN | subbot | 7 | LOSS | $-1,051.82 | -1.03 | 384 | PASS | dead_bounce_no_drift(bars=1,pct=1.00) |
| **2026-05-08** | **13:58** | **FATN** | **subbot** | **10** | **LOSS** | **$-771.60** | **-1.04** | **440** | **PASS** | **dead_bounce_no_drift(bars=0,pct=1.00) ← TARGET CASE, MISSED** |
| 2026-05-08 | 15:01 | SST | subbot | 9 | LOSS | $-250.62 | -0.40 | 620 | PASS | dead_bounce_no_drift(bars=0,pct=1.00) |
| 2026-05-08 | 17:09 | ATRA | subbot | 10 | WIN | $+2,499.59 | +2.51 | 772 | PASS | dead_bounce_no_drift(bars=1,pct=1.00) ← v1 FP fixed |
| 2026-05-11 | 10:12 | NVOX | subbot | 9 | LOSS | $-37.09 | -0.47 | 372 | PASS | dead_bounce_no_drift(bars=1,pct=0.93) |
| 2026-05-11 | 13:52 | ATRA | subbot | 10 | LOSS | $-513.24 | -1.16 | 550 | PASS | dead_bounce_hod_not_early(age=230m) |
| 2026-05-11 | 14:18 | SST | subbot | 9 | WIN | $+2,090.40 | +3.28 | 555 | PASS | dead_bounce_no_drift(bars=0,pct=1.00) |
| 2026-05-11 | 18:30 | ATRA | subbot | 10 | LOSS | $-778.36 | -1.43 | 806 | PASS | dead_bounce_hod_not_early(age=503m) |
| 2026-05-12 | 05:31 | TRAW | wb_bot | 10 | LOSS | $-985.20 | -1.14 | 85 | PASS | dead_bounce_no_drift(bars=0,pct=1.00) |
| 2026-05-12 | 05:48 | ODYS | wb_bot | 8 | LOSS | $-856.48 | -1.55 | 109 | PASS | dead_bounce_no_drift(bars=3,pct=0.55) |
| 2026-05-12 | 06:29 | XOS | wb_bot | 10 | LOSS | $-735.27 | -1.20 | 150 | PASS | dead_bounce_no_drift(bars=0,pct=1.00) |
| 2026-05-12 | 08:16 | ENSC | subbot | 9 | LOSS | $-643.54 | -1.03 | 252 | PASS | dead_bounce_no_drift(bars=1,pct=1.00) |
| 2026-05-12 | 11:20 | SST | subbot | 10 | LOSS | $-869.55 | -1.10 | 356 | PASS | dead_bounce_no_drift(bars=0,pct=1.00) |
| 2026-05-12 | 11:41 | FATN | wb_bot | 8 | LOSS | $-1,381.20 | -2.04 | 281 | PASS | dead_bounce_no_drift(bars=0,pct=0.50) |
| 2026-05-12 | 12:20 | ATRA | wb_bot | 8 | WIN | $+41.15 | +0.23 | 393 | PASS | dead_bounce_no_drift(bars=0,pct=0.50) ← v1 FP fixed |
| 2026-05-12 | 12:26 | FATN | wb_bot | 9 | LOSS | $-1,126.72 | -1.36 | 316 | PASS | dead_bounce_no_drift(bars=0,pct=0.67) |
| 2026-05-12 | 13:51 | ATRA | wb_bot | 7 | LOSS | $-1,156.90 | -1.84 | 484 | PASS | dead_bounce_no_drift(bars=0,pct=0.50) |

## Counts (this sub-gate alone, v2 patch)

| Outcome | Count |
|---|---:|
| blocked, was loser (saved) | 0 |
| blocked, was winner (false positive) | 0 |
| passed, was winner (preserved) | 4 |
| passed, was loser (not caught) | 18 |

## v1 → v2 comparison

| Trade | Outcome | v1 verdict | v2 verdict | Δ |
|---|---|---|---|---|
| ATRA 5/8 17:09 | WIN +$2,500 | BLOCK (FP) | PASS | FP fixed ✅ |
| ATRA 5/12 12:20 | WIN +$41 | BLOCK (FP) | PASS | FP fixed ✅ |
| XOS 5/12 06:29 | LOSS -$735 | block (saved) | PASS | save lost |
| ENSC 5/12 08:16 | LOSS -$644 | block (saved) | PASS | save lost |
| FATN 5/12 12:26 | LOSS -$1,127 | block (saved) | PASS | save lost (still caught by same-session BL #11) |
| **FATN 5/8 13:58** | **LOSS -$772 (target)** | PASS (`strong_volume`) | PASS (`no_drift`) | **still missed; CRITERION 3 FAIL** |

Note: even under v1, FATN 5/8 13:58 wasn't being blocked by `dead_bounce` — v1's PASS verdict was `dead_bounce_strong_volume(ratio=7.60>=0.70)`. The original validation report shows it slipped past step 4 (volume), so the design target was never actually caught by step 2 in v1 either.

## Conclusion

The v2 patch fixes both v1 false positives (ATRA winners) but degenerates `dead_bounce` into a no-op on this dataset. **Critically, the target case FATN 5/8 13:58 remains uncaught.** The directive is explicit (line 149): "If the patch lets FATN 5/8 slip through, dead_bounce loses its reason to exist."

Per directive lines 165-167:
> If still failing → return to Cowork with specifics before any further code changes.
> Until then: `WB_CG3_DEAD_BOUNCE_ENABLED=0` (observe-only).

## Status

- Code patch applied verbatim per directive §3 to both `chop_gate_v3.py` copies (byte-identical).
- `.env.example` updated in both repos (new `WB_CG3_DEAD_BOUNCE_DRIFT_RANGE_MIN_PCT=0.30`; `WB_CG3_DEAD_BOUNCE_ATR_MULT` removed).
- Validation re-run with sub-gate observed in isolation; results recorded above.
- **No commits, no pushes.** Awaiting Cowork's response on whether to redesign step 2's drift definition (e.g. bars-below-VWAP, drift via close-vs-HOD percentile) or retire `dead_bounce` from the sub-gate slate.

## Notes

- Per-sub-gate validation runs each sub-gate INDEPENDENTLY (other sub-gates in observe-only). Bars + MACD reconstructed from tick cache up to the exact moment of arm (no future leakage).
- Cross-session blacklist is built incrementally — each trade's decision sees only prior-day trades closed in the dataset.
