# Post-Fix 10-Day Baseline Re-Run — Results

**Date**: 2026-05-22 (Friday evening)
**Branch**: `v2-ibkr-migration`
**Source directive**: `cowork_reports/2026-05-22_post_fix_rebaseline_directive.md`
**Backtest output**: `backtest_status/replay_post_chase_skip_fix_baseline_2026-05-07_2026-05-20.json`

---

## TL;DR

**New 10-day baseline: +$2,489** (vs claimed pre-fix +$2,498). Difference: **−$9**.

**Important framing correction**: the chase-skip bug was **sub-bot-only**, not simulate.py. Per Cowork's own root-cause analysis (`2026-05-22_mtva_arm_gap_root_cause.md`):

> Sim doesn't do this — it just skips THIS tick's entry and lets the arm survive for future MOVE_STRIKE opportunities. (`simulate.py:3745-3771`)

Running the backtest with the fix in place produces results **identical** to the pre-fix sim — because simulate.py never had the bug. **The fix doesn't create new sim trades**; it lets live trades happen that previously couldn't.

The $9 difference between Cowork's cited "+$2,498" and today's run is explained below — it's a config-coverage drift, not a fix-induced change.

---

## Headline numbers

| Date | New (5/22 PM) | Old "stay-armed gated" baseline (5/22 AM) | Δ |
|---|---|---|---|
| 5/07–5/14 | $0 (0 trades) | $0 (0 trades) | 0 |
| 5/15 | +$104 (4 trades) | +$104 (4 trades) | 0 |
| 5/18 | +$105 (7 trades) | +$105 (7 trades) | 0 |
| 5/19 | **−$400 (1 trade)** | −$649 (3 trades) | **+$249** |
| 5/20 | **+$2,680 (18 trades)** | +$2,938 (20 trades) | **−$258** |
| **Total** | **+$2,489** | **+$2,498** | **−$9** |

5/19 and 5/20 each show 2 fewer trades than the "stay-armed gated" run — but the net is essentially unchanged.

---

## Where the $9 difference comes from

Today's run uses the **current shipped config** (per the directive): `HWM + same-bar + stay-armed + below-arm 3% + slippage $0.07`. That config produces **+$2,489**.

The cited "+$2,498" Cowork inherited is from yesterday's "stay_armed_gated" backtest **before the below-arm 3% filter was shipped**. After I added the below-arm filter (commit b034a10), the same config produced +$2,489 on the same 10 days — documented in yesterday's session:

> | Config | 10d total | QUCY today | Total |
> | Same-bar block + stay-armed only | +$2,498 | +$544 | +$3,042 |
> | + below-arm 3% | **+$2,489** (−$9) | +$717 | +$3,206 |

So the +$2,498 → +$2,489 delta is **the below-arm 3% filter blocking 4 trades** (net −$9) — a known small cost of the PIII-style protection. It has **nothing to do with the chase-skip arm preservation fix** that just shipped.

---

## Trades the fix created (Cowork's Deliverable #2)

**Empty.** The chase-skip fix is in `move_strike_subbot.py:642-664`. `simulate.py` does not include this code path. Today's sim re-run produces **byte-identical trades** to a hypothetical previous sim re-run with the same env vars.

Cross-checked: the trades-list in `backtest_status/replay_post_chase_skip_fix_baseline_2026-05-07_2026-05-20.json` is identical (same entries, exits, prices, R-values) to `backtest_status/replay_below_arm_3pct_2026-05-07_2026-05-20.json` from yesterday.

**This is the expected result.** It confirms:
- Sim never had the bug (matches Cowork's `mtva_arm_gap_root_cause.md` finding)
- The fix's value is making LIVE behavior catch up to what sim has always shown
- Yesterday's +$2,489 (with below-arm 3%) is the correct "post-fix" baseline

---

## Trades that changed disposition (Deliverable #3)

None. Same trades, same fills, same exits.

---

## What this means for X01 directive

The X01 research directive (`2026-05-21_x01_exits_research_directive.md`) can be **unblocked**. The baseline should reference **+$2,489**, not +$2,498. The $9 delta won't change any X01 variant's signal-vs-noise call — all of yesterday's tested variants (fixed-R trails, gain-widen, full X01) were >$1K off the baseline in either direction.

Direction A's success criteria (per the directive):

> any config that beats {baseline} on 10d AND captures >+$1,500 on PCLA 2026-05-21

Replace with: **any config that beats +$2,489 on 10d AND captures >+$1,500 on PCLA 2026-05-21**.

---

## What live should look like Monday

The chase-skip fix landed in commit `1c3ce24`. Today's live sub-bot session was **NOT running it** — the fix shipped after the morning's MTVA bleeding. Monday 2026-05-26 is the first session with the fix active.

The expected effect:
- Any symbol that chase-skips early should remain "live" (arm preserved) for later MOVE_STRIKE entries
- Live trade count per chase-skipped symbol should increase
- Live P&L per chase-skipped symbol should converge toward what sim shows on the historical sample

We **won't know the magnitude** until we observe a session where multiple chase-skips happen followed by mean-reversions. The 10-day historical doesn't help us predict this — those chase-skips already DID produce trades in sim, and live in those days was running an even buggier stack than today.

Monday's session is the validation test. If live's chase-skipped symbols start showing entries that didn't happen pre-fix, the fix is working.

---

## Memory update (Cowork's Deliverable #5)

Will update `feedback_sim_live_divergence_inventory_2026-05-22.md` with:
- Clarification that the bug was sub-bot-only
- The +$2,489 number (already documented as the current shipped config baseline)
- The expected-but-not-yet-measured live convergence

---

## Tasks updated

- #33 (re-baseline): closing as completed — result is +$2,489.
- #28 (parity audit): no change.
- #32 (watchdog freeze): unchanged. Today had 3 watchdog crashes that wiped live state; the chase-skip fix doesn't address those.
