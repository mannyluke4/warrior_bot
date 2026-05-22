# X01 Direction A — Results & Recommendation

**Date**: 2026-05-22
**Branch**: `v2-ibkr-migration`
**Source directive**: `cowork_reports/2026-05-22_x01_direction_a_kickoff.md`
**Baseline to beat**: +$2,489 on 5/07–5/20, +$622 on PCLA 5/21 (current shipped HWM config)

---

## TL;DR

**Direction A fails.** All three bail_timer variants of X01 exits captured PCLA's vertical move (+$1,772 each, ✅ >$1,500), but **lost massively on the 10-day broader sample** (−$215 to −$496 vs the +$2,489 HWM baseline).

The hypothesis was that bail_timer was the killer. **Disproved**: even with bail_timer fully OFF, X01 lost −$215 on the 10d (a $2,704 gap vs HWM). The killer is X01's exit framework itself on small/choppy moves — target_hit at 1.5R rarely fires, leaving trades sitting until time_exit or stop, while stay-armed cascades multiply the losers.

**Recommendation**: kill Direction A. Move to **Direction B (scale-out partial at 1.5R + HWM runner)** — that's the cleanest remaining angle to capture PCLA-style verticals while keeping HWM's edge on small moves.

---

## Three-variant comparison

| Variant | Config | 10d Total | PCLA 5/21 | vs HWM 10d | vs HWM PCLA |
|---|---|---|---|---|---|
| **HWM baseline** *(current shipped)* | HWM 25% | **+$2,489** | **+$622** | — | — |
| V1 | X01 exits, bail_timer OFF | −$215 | +$1,772 | **−$2,704** | +$1,150 |
| V2 | X01 exits, bail_timer 15min | −$215 | +$1,772 | **−$2,704** | +$1,150 |
| V3 | X01 exits, bail_timer 10min | −$496 | +$1,772 | **−$2,985** | +$1,150 |

V1 and V2 are byte-identical — the 15-min bail never fires on any trade in the 10d sample. V3 (10min) costs an additional −$281 by firing on 5/20's slow-warming trades.

**Combined 11-day** (10d + PCLA):
- HWM baseline: +$2,489 + $622 = **+$3,111**
- X01 V1/V2 best: −$215 + $1,772 = **+$1,557** (−$1,554 vs HWM)
- X01 V3 worst: −$496 + $1,772 = **+$1,276** (−$1,835 vs HWM)

X01 trades the certain +$2,489 for a ~$1,150 PCLA upside. Bad trade — the PCLA pattern is rare.

---

## Per-day breakdown of best variant (V1/V2)

| Date | HWM baseline | X01 V1/V2 | Δ | Notes |
|---|---|---|---|---|
| 5/15 | +$104 (4 trades) | **−$713 (8 trades)** | **−$817** | Stay-armed cascade fires X01 re-entries that target-miss and time-exit at losses |
| 5/18 | +$105 (7 trades) | **−$898 (9 trades)** | **−$1,003** | Same pattern. 11 trades on 5/18 from full-X01 yesterday; bail_timer change didn't reduce count |
| 5/19 | −$400 (1 trade) | −$46 (1 trade) | +$354 | Below-arm filter blocked the original 2 RUBI losers; remaining MTVA was small loss |
| 5/20 | +$2,680 (18 trades) | +$1,442 (22 trades) | **−$1,238** | X01 took 4 more trades. Target_hit fired on some winners (+) but most extra trades were small losers (−) |

The pattern: X01 cascades more re-entries (via stay-armed + sq target/runner framework) than HWM. On a chop day, those extra re-entries lose. On a ripper day, they catch the move (PCLA +$1,772 vs HWM +$622).

---

## Trade-level inspection — the bail_timer non-effect

V1 (bail OFF) vs V2 (bail 15min) produced **byte-identical** outcomes across all 19 sim trades. That tells us: on the 10-day sample, **no trade sat unprofitable for 15+ minutes before resolving via another exit**. The bail_timer wasn't firing.

This contradicts the original hypothesis (`2026-05-21_x01_exits_research_directive.md`: "the bail_timer (5-min unprofitable exit) over-traded on chop days"). The 15-min timeout is too permissive; the trades that lost in yesterday's full-X01 test (with default 5-min bail) lost because target_hit didn't fire fast enough, not because bail_timer was clipping winners.

V3 (10-min bail) does fire on some trades (per the 5/20 −$281 delta), but cuts winners as much as losers. There's no sweet spot for bail_timer that recovers the 10d gap.

---

## PCLA 5/21 — the only place X01 shines

All three X01 variants captured PCLA identically: **4 trades, 100% WR, +$1,772**:

| # | Time | Entry | Exit | Reason | P&L |
|---|---|---|---|---|---|
| 1 | 16:23 | $2.95 | $3.18 | sq_target_hit (1.5R) | +$726 |
| 2 | 16:31 | $2.95 | $3.01 | sq_time_exit(5bars) | +$89 |
| 3 | 16:56 | $3.33 | $3.41 | sq_time_exit(5bars) | +$83 |
| 4 | 17:02 | $3.52 | $4.56 | sq_target_hit (1.7R) | **+$874** |

Trade 4 is what HWM misses — it caught the 17:02-17:07 ripper to $4.56 via sq_target_hit at 1.7R. HWM's 25% trail fires at the first pullback well before that level. This is exactly the PCLA-class catch we wanted.

**But it costs $2,704 of certain 10d edge to enable.**

---

## Why X01 loses on small/choppy days

On HWM's 5/15 +$104 vs X01's −$713: same 4 vs 8 trade count differential. X01's extra trades are mostly stay-armed re-entries that the squeeze framework allows but HWM doesn't.

Looking at X01's 5/15 trades:
- Multiple LESL/ONDG re-entries that target-miss (gain doesn't hit 1.5R)
- Time-exit at 5 bars closes them flat-to-small-loss
- HWM's tight 25% trail closes them at the first +0.5R-ish move

So HWM's "exit at small profit" beats X01's "wait for target_hit or time out" on bars that don't develop into runs. On a sample where 90%+ of trades don't develop into PCLA-scale moves, HWM wins decisively.

---

## Recommendation: kill Direction A, move to Direction B

X01 + stay-armed produces too many small losers. The exit framework is the wrong shape for non-vertical moves. Tuning bail_timer doesn't fix the underlying issue.

**Direction B is the clean next experiment**: layer scale-out on top of HWM rather than swapping framework:
- Partial exit at 1.5R (try 50%, 75%, 90%)
- Remaining runner keeps HWM 25% trail
- Hard stop + prox bail unchanged
- Captures the PCLA-class catch via the runner without re-introducing X01's loose-on-chop exits

Per the X01 directive Direction B uses the SAME success criteria. If it hits both (>+$2,489 10d AND >+$1,500 PCLA), ship it gated off for review.

---

## Closing this task

Task #35 (X01 Direction A) closes as completed with verdict **KILL**. No commit needed — none of the variants pass the criterion and no code changes were made beyond the existing gated env vars.

Direction B should be the next investigation. Spec is in `2026-05-21_x01_exits_research_directive.md` § "Direction B".
