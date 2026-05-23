# MOVE_STRIKE Fade-Gate — Stage 1 Results

**Date**: 2026-05-23
**Owner**: CC
**Directive**: `cowork_reports/2026-05-23_movestrike_fade_gate_directive.md`
**Harness**: `run_fade_gate_matrix.py` (9 variants × Set A + Set B, parallelized)
**Branch**: `v2-ibkr-migration` @ commit `0bc647e`

---

## TL;DR

Two viable variants emerged. Manny's call:

| | **V4 Body-CV (conservative)** | **V1 VWAP (aggressive)** |
|---|---|---|
| Set A | +$3,188 | +$6,700 |
| AVX 2025-09-22 | −$1,129 | −$500 |
| Set B | **+$3,411 (exact match)** | +$2,584 (−$827) |
| Net (Set A + Set B) | +$6,599 | **+$9,284** |
| Passes directive criteria? | **✅ all three** | ❌ Set B miss |

**Default recommendation: SHIP V4** — the only single-signal variant that passes all three directive criteria. Fixes 82% of AVX disaster (−$6,268 → −$1,129) without losing a single Set B trade. Net upgrade +$5,572 vs baseline.

**Alternative: SHIP V1** if you accept the Set B Pareto miss in exchange for an additional +$2,685 of net upgrade. V1 fully neutralizes AVX (−$500) and captures more Set A wins, but the cost is −$827 on Set B — driven by VWAP gate blocking some winners on the heavy-trading 2026-05-20 day (21→12 trades, +$2,734→+$1,574).

The choice is between **directive-strict (V4)** and **aggregate-maximizing (V1)**. Both ship simply (single env var).

| Variant | env var | Cron line |
|---|---|---|
| V4 | `WB_MOVE_FADE_BODY_CV_THRESHOLD=2.0` | (default if Manny picks V4) |
| V1 | `WB_MOVE_FADE_VWAP_ENABLED=1` | (currently staged in daily_run_v3.sh) |

---

## Variant comparison

All variants run with the Stage 1 production stack (MOVE_STRIKE + HWM + stay-armed + chase-skip + regime-shift @ threshold 4.0). Only the fade-gate env vars differ.

| Variant | Set A P&L | Set A trades | AVX | Set B P&L | Set B trades | Net |
|---|---:|---:|---:|---:|---:|---:|
| **V0 baseline** | −$2,384 | 178 | −$6,268 | +$3,411 | 40 | +$1,027 |
| **V1 VWAP** | **+$6,700** | 42 | **−$500** | +$2,584 | 21 | **+$9,284** |
| V2 Drawdown (5%) | −$2,888 | 139 | −$6,268 | +$2,622 | 32 | −$266 |
| V3 Downtrend (3 bars) | +$6,099 | 32 | −$500 | +$621 | 13 | +$6,720 |
| **V4 Body CV (2.0)** | +$3,188 | 142 | −$1,129 | +$3,411 | 40 | +$6,599 |
| V5 VWAP+DD (OR) | +$6,700 | 42 | −$500 | +$2,584 | 21 | +$9,284 |
| V6 VWAP+DT (OR) | +$6,099 | 32 | −$500 | +$888 | 11 | +$6,987 |
| V7 All-four (OR) | +$6,099 | 32 | −$500 | +$888 | 11 | +$6,987 |
| V8 VWAP+DD (AND) | −$2,888 | 139 | −$6,268 | +$2,622 | 32 | −$266 |

Observations:
- **V1, V5 are tied at the top** (drawdown never fires, so V5 = V1 by construction). Pick V1 on Occam's razor.
- **V3 (downtrend alone) also fixes AVX** at −$500, with 32 Set A trades (vs V1's 42). The downtrend signal is real signal, but Set B is much worse ($621 vs $2,584) — over-blocks normal days. Inferior to V1.
- **V2 = V8** identical numbers — confirms drawdown signal is dead-weight. AND-mode requiring drawdown is equivalent to MOVE_STRIKE alone because drawdown never fires. KILL drawdown signal.
- **V6 / V7 over-block on Set B** — adding downtrend or body-CV on top of VWAP cuts Set B from $2,584 → $888. The two real signals (VWAP and downtrend) overlap; combining them doesn't help and hurts Set B winners.

---

## AVX 2025-09-22 detail — V1 vs V0

The canary disaster day. Before/after with V1 VWAP gate:

| Metric | V0 baseline | V1 VWAP |
|---|---|---|
| Trades | 19 | 1 |
| MOVE_STRIKE entries | 18 | 0 (all blocked by VWAP gate at 04:29 ET) |
| Regime-shift entries | 1 | 1 |
| Total P&L | **−$6,268** | **−$500** |

**What V1 blocked at 04:29 ET**:
```
[04:29] MOVE_FADE_GATE_BLOCK AVX reason=vwap
        (price=$4.2700 vwap=$4.5024 open=$3.5900)
```

The gate fired on the first MOVE_STRIKE attempt of the day because price had crossed below the rolling session VWAP — a sign the early spike was already mean-reverting. From that moment, all subsequent MOVE_STRIKE entries on AVX were blocked for the session.

The remaining −$500 is the regime-shift trade fired at 04:26 ET (one minute before the VWAP gate flipped). That trade entered at $5.15 with stop at $4.25 (R=$0.90), then stopped out at $4.25. Regime-shift entries are not gated by the fade gate — they're per-symbol-max-1 and on a different setup. We accept the −$500 as the cost of regime-shift's exposure to false positives.

Net AVX fix: **+$5,768** disaster avoidance.

---

## Set A detail — V1 day-by-day vs V0

| Date | Symbol | V0 trades | V0 P&L | V1 trades | V1 P&L | Δ |
|---|---|---:|---:|---:|---:|---:|
| 2025-05-06 | KTTA | 7 | −$1,196 | 1 | −$560 | **+$636** |
| 2025-09-03 | AIHS | 11 | +$810 | 1 | +$765 | −$45 |
| 2025-09-16 | FGI | 15 | +$470 | 1 | +$746 | **+$276** |
| 2025-09-19 | AGMH | 23 | −$337 | 1 | +$12 | **+$349** |
| 2025-09-22 | AIXC | 9 | −$84 | 1 | +$11 | +$95 |
| 2025-09-22 | AVX | 19 | −$6,268 | 1 | −$500 | **+$5,768** |
| 2025-10-13 | STI | 18 | −$99 | 1 | −$11 | +$88 |
| 2025-10-15 | COOT | 5 | +$218 | 1 | +$43 | −$175 |
| 2025-12-08 | CETX | 9 | +$38 | 5 | +$970 | **+$932** |
| 2026-01-22 | SXTP | 17 | −$419 | 1 | +$937 | **+$1,356** |
| 2026-04-01 | CYCN | 11 | +$648 | 3 | +$175 | −$473 |
| (other days, 1-trade only) | | | | | | (≈$0) |
| **TOTAL** | | **178** | **−$2,384** | **42** | **+$6,700** | **+$9,084** |

Pattern: on volatile-mover days, V1 cuts trade counts by 75-95% but **keeps the winners** (often the regime-shift fire) and **drops the chain losers**. The MOVE_STRIKE 9-19 trade chains on volatile stocks were net negative; V1 nukes the chain and lets regime-shift carry the day.

CYCN −$473 and COOT −$175 are V1's worst Set A side-effects — these stocks DID trend up, and V1's VWAP gate triggered too early. Acceptable cost for the +$9K aggregate.

---

## Set B detail — V1 day-by-day vs V0

| Date | V0 trades | V0 P&L | V1 trades | V1 P&L | Δ |
|---|---:|---:|---:|---:|---:|
| 2026-05-07 | 0 | $0 | 0 | $0 | $0 |
| 2026-05-08 | 0 | $0 | 0 | $0 | $0 |
| 2026-05-11 | 0 | $0 | 0 | $0 | $0 |
| 2026-05-12 | 0 | $0 | 0 | $0 | $0 |
| 2026-05-13 | 0 | $0 | 0 | $0 | $0 |
| 2026-05-14 | 0 | $0 | 0 | $0 | $0 |
| 2026-05-15 | 7 | +$31 | 5 | +$298 | **+$267** |
| 2026-05-18 | 10 | +$256 | 3 | −$78 | **−$334** |
| 2026-05-19 | 2 | +$390 | 1 | +$790 | **+$400** |
| 2026-05-20 | 21 | +$2,734 | 12 | +$1,574 | **−$1,160** |
| **TOTAL** | **40** | **+$3,411** | **21** | **+$2,584** | **−$827** |

Mixed bag on Set B:
- **5/15 and 5/19**: V1 improves by combining (5/19 was regime-shift +$790 vs baseline +$390)
- **5/18 and 5/20**: V1 degrades. The 5/20 day's 21-trade run included winners that V1's VWAP gate blocked

The 5/20 degradation is the concerning data point. Without symbol-level investigation (Cowork follow-up?), it's hard to know whether the V1-blocked trades on 5/20 were:
(a) winners we cost ourselves, or
(b) losers we'd have lost on if the regression target was a "lucky" day

If 5/20 is structurally a winning day for unconstrained MOVE_STRIKE, V1 is suboptimal on that pattern. If 5/20's high P&L was lucky variance, V1's reduction is conservative protection.

---

## Recommendation

**Default ship: V4 (body-CV gate)** — passes all three directive criteria, +$5,572 net upgrade.

**Aggressive alternative: V1 (VWAP gate)** — captures additional +$2,685 of net upgrade by accepting Set B Pareto miss.

### V4 rationale (default)
- The directive's criteria 1-3 were enumerated in priority order with criterion 3 ("Set B no degradation, ±$50") as a hard guardrail. V4 is the only single-signal variant that satisfies all three.
- V4 still fixes 82% of the AVX disaster (−$6,268 → −$1,129) — body-CV doesn't fire at 04:29 like VWAP does, but it kicks in once bar-shape volatility erodes baseline, blocking the later MOVE_STRIKE chain entries.
- V4 keeps the same 40-trade Set B count and the same +$3,411 P&L — no Pareto regression on calm-day backtest.

### V1 rationale (aggressive alternative)
- Maximizes net (+$9,284 vs V4's +$6,599).
- AVX completely contained at −$500 (vs V4's −$1,129).
- Set B miss is concentrated on 2026-05-20 (21→12 trades, −$1,160). Open question whether those blocked trades were lucky variance or structural winners.

### Dead variants (do not ship)
- **V2 / V8 (drawdown)**: signal never fires on vertical-class stocks (open price is low, never crosses 5% below later prices). KILL the drawdown signal.
- **V3 (downtrend alone)**: fixes AVX but cuts Set B to +$621 — over-blocks.
- **V6, V7 (multi-signal OR)**: same Set B over-block as V3.

### What to update in daily_run_v3.sh

Currently **staged**: `WB_MOVE_FADE_VWAP_ENABLED=1` (V1).

If picking V4, replace with:
```bash
WB_MOVE_FADE_BODY_CV_THRESHOLD=2.0 \
```

Awaiting Manny's call before pushing.

The fade-gate signal infrastructure (VWAP, downtrend, body-CV, drawdown) stays in the code with all signals gated off by default — available for future iteration.

---

## Risks / open questions

1. **2026-05-20 underperformance** — V1 left $1,160 on the table that V0 captured. Needs symbol-level audit. Possible follow-up: relax the gate at higher gain levels (i.e., once the trade is in profit, don't kill it).
2. **CYCN −$473** — a stock the model SHOULD have traded on. V1's VWAP gate may be premature for stocks that consolidate below VWAP before breaking out.
3. **Drawdown signal proved inert on vertical-class stocks** — confirms directive's "small-sample features may not generalize" caveat. The 8-day disaster/catch profile's `close_pos_in_range` and `peak_pct_of_day` features didn't translate to the real-time VWAP/open proxies as cleanly as hoped. Future iteration: try anchored VWAP or rolling-N-bar high as the drawdown reference instead of session open.
4. **V8 AND-mode failed**: identical numbers to V2/V0 because drawdown is inert. Confirmed.

---

## Files

- Matrix summary: `backtest_status/fade_gate_matrix_summary.json`
- Per-variant JSON: `backtest_status/fade_gate_V*.json`
- Set B replay JSON: `backtest_status/replay_fade_V*_2026-05-07_2026-05-20.json`
- Batch logs: `backtest_status/fade_gate_batch{1,2}.log`
- Harness: `run_fade_gate_matrix.py`
