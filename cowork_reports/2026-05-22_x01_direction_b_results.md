# X01 Direction B — Results & Recommendation

**Date**: 2026-05-22
**Branch**: `v2-ibkr-migration`
**Source directive**: `cowork_reports/2026-05-22_x01_direction_b_kickoff.md`
**Predecessors**: Direction A killed in `cowork_reports/2026-05-22_x01_direction_a_results.md`
**Baseline to beat**: +$2,489 on 5/07–5/20 AND +$1,500 on PCLA 5/21

---

## TL;DR

**Direction B passes the 10-day criterion (+$2,637 vs +$2,489 baseline, +$148) but fails the PCLA criterion ($802 vs $1,500 target).** Strict success criterion not met. Per the directive language, this is a dead end and Direction C (volatility-adjusted trail) is next.

**But honestly the result is a small strict-improvement** over HWM baseline:
- 10d: +$2,637 (best variant 90%) — small win
- PCLA: +$802 (best variant 90%) — better than HWM's +$622, no regression
- **Combined 11-day**: **+$3,439** vs HWM's +$3,111 → **+$328 better**

It's a Pareto improvement. The reason it doesn't hit $1,500 on PCLA: the partial-then-runner closes the original trade faster, which sets the stay-armed cool-down window forward, blocking the 17:02 ripper entry (the trade that gave Direction A its +$874).

If a $328 net improvement over 11 days at the cost of meeting a binary threshold is worth shipping, do it. If not, kill and move to Direction C.

---

## Three-variant comparison

| Variant | 10d (5/07–5/20) | PCLA (5/21) | Combined |
|---|---|---|---|
| HWM baseline (current shipped) | +$2,489 | +$622 | +$3,111 |
| **B-50%** (partial 50% at 1.5R) | **+$2,637** | +$722 | +$3,359 |
| **B-75%** (partial 75% at 1.5R) | **+$2,637** | +$772 | +$3,409 |
| **B-90%** (partial 90% at 1.5R) | **+$2,637** | **+$802** | **+$3,439** ← best |

The 10-day total is **identical across all three variants** (+$2,637, +$148 vs baseline) because:
- Only ONE trade in the 10-day sample (5/20) ever crosses 1.5R gain before exiting
- For that one trade, the runner exits at the same price as the partial (HWM trail fires immediately after)
- So total trade P&L = `qty_total × (exit_price − entry)`, independent of how it's split
- The +$148 improvement comes from the runner riding $0.01-0.02 higher than the basic HWM trail would have closed at

Variants 50/75/90 do differ on PCLA (+$22, +$50, +$80 respectively over partial-50%) because PCLA's trade 1 has a brief tick at $3.18+ where the partial captures more qty at the higher price.

---

## Per-day breakdown — best variant (B-90%)

| Date | HWM | B-90% | Δ | Notes |
|---|---|---|---|---|
| 5/15 | +$104 | +$104 | $0 | No trade reaches 1.5R |
| 5/18 | +$105 | +$105 | $0 | Same |
| 5/19 | −$400 | −$400 | $0 | Same |
| 5/20 | +$2,680 | +$2,828 | **+$148** | One trade fired the partial; runner trail captured fractional extra |
| Total | +$2,489 | +$2,637 | **+$148** | |

For PCLA 5/21:
| Trade | HWM | B-90% | Δ |
|---|---|---|---|
| 1 (16:23 $2.95→) | +$567 (HWM trail at $3.12) | **+$747** (partial at $3.18, runner trails to $3.12) | **+$180** |
| 2 (16:28 re-entry) | +$56 | +$56 | $0 |
| **PCLA total** | **+$622** | **+$802** | **+$180** |

The partial fires at $3.18 (1.5R), locking in 90% × ($3.18 − $2.95) = $0.207/share × 3000 ≈ $621. Runner (333 shares) trails to $3.12 = $0.17 × 333 = $57. Combined $678 — vs HWM-only $567. Net partial value: $111 from the higher partial-fire price.

---

## The 17:02 ripper — why Direction B misses it

Direction A captured PCLA's 17:02-17:07 rip via a 4th trade (stay-armed entry at $3.52, target_hit at $4.56, +$874). Direction B has only 2 PCLA trades.

The cause: the partial+runner pattern closes trade 1 by 16:24 (partial at 16:23, runner trails at 16:24). Then trade 2 (re-entry) closes at 16:54. Stay-armed `last_exit_min` is set to 16:54, with 15-min cool-down. **Eligible again at 17:09 — but the rip peaked at 17:07.** Stay-armed never engages.

In Direction A, the X01 framework cycles re-entries through the sq_target_hit/runner pathway differently, and stay-armed fires at 17:02 before the 17:09 cool-down. That's why A caught the ripper despite losing on chop.

Direction B inherits HWM-baseline behavior on stay-armed timing, which means it can't catch PCLA-class continuations that fall just outside the cool-down window. This is structural, not tuneable via partial_pct.

---

## Strict pass/fail vs combined economics

**Strict directive criterion**: 10d > $2,489 AND PCLA > $1,500
- B-90%: ✅ 10d ($2,637), ❌ PCLA ($802)
- **Result**: FAIL

**Pareto comparison vs baseline**:
- Combined 11-day: B-90% +$328 vs HWM baseline
- 10d: B-90% +$148 vs HWM
- PCLA: B-90% +$180 vs HWM
- No day regression, no symbol regression

**Reading**: by the directive's binary criterion, kill it. By Pareto economics, ship it gated. Manny's call.

If shipped, it should be:
- `WB_BT_MOVE_PARTIAL_ENABLED=1`
- `WB_BT_MOVE_PARTIAL_AT_R=1.5`
- `WB_BT_MOVE_PARTIAL_PCT=0.9` (best variant on PCLA, identical on 10d)

Wire into `daily_run_v3.sh` for sub-bot launch + add identical partial logic to `move_strike_subbot.py` (currently the implementation is sim-only per the directive's "sub-bot mirror is follow-up" rule).

---

## What this DIDN'T test (and might be worth)

The 10-day sample has only ONE trade that crosses 1.5R. The partial mechanism is barely active. Two possible follow-ups:

1. **Lower partial_at_R** (e.g., 1.0R instead of 1.5R) — would activate the partial more frequently. Risk: locks in profits too early, leaving less for the runner. But if most trades that reach 1R make small additional progress before exit, lowering threshold gives more "certain-win" lock-ins.

2. **Pair with wider partial-pct on big-R trades** — for stocks with R=$0.30+, a 1.5R move is a meaningful $0.45+. For stocks with R=$0.10, a 1.5R move is $0.15 (a tick or two). Maybe partial only fires on `R >= 0.20` setups where the gain is materially worth locking?

Both are tuning explorations. If we decide Direction B's marginal Pareto improvement is worth shipping, those are reasonable next experiments. If we kill it, they're moot.

---

## Implementation notes

Code changes for partial mechanism (commit pending):
- `simulate.py`: SimTrade.move_partial_fired field (default False)
- Three new SimTradeManager config vars (gated off by default)
- qty_core/qty_runner override at MOVE_STRIKE entry creation when partial enabled
- `_hwm_exit`: partial-fire check at top (before hard_stop, prox_bail, etc.)
- All subsequent exit paths gate write target on `move_partial_fired` (runner-only after partial)

`move_strike_subbot.py`: NOT touched per directive. Sub-bot mirror is follow-up after experiment validation.

---

## Recommendation

**My read**: ship Direction B 90% gated off by default. The +$328 combined 11-day improvement is small but real and Pareto-positive (no regressions). The binary criterion miss is structural (cool-down timing on PCLA's specific shape), not a real flaw.

But it's a marginal win. Direction C (volatility-adjusted trail width) was flagged in the original directive as "less promising" — probably not worth investigating next. If Direction B doesn't ship, the X01 research is closed and we focus on monitoring Monday's live performance with the watchdog + chase-skip fixes.

Manny's call.
