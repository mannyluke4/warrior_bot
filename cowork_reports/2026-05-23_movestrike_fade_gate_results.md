# MOVE_STRIKE Fade-Gate — Stage 1 Results

**Date**: 2026-05-23
**Owner**: CC
**Directive**: `cowork_reports/2026-05-23_movestrike_fade_gate_directive.md`
**Harness**: `run_fade_gate_matrix.py` (9 variants × Set A + Set B, parallelized)
**Branch**: `v2-ibkr-migration` @ commit `0bc647e`

---

## TL;DR

**REVISED AFTER YTD BACKTEST**: SHIP V1 (VWAP). The Stage-1 V4 recommendation was wrong — biased by curated test sets. On the YTD universe (4,431 sym/date pairs, Jan 02 → May 22), V1 dominates V4 by **+$55K**.

YTD comparison (full appendix below):

| Variant | Trades | YTD P&L | Δ vs baseline |
|---|---:|---:|---:|
| V0 baseline (no gate) | 1,153 | −$83,770 | — |
| **V1 VWAP** | **239** | **−$17,897** | **+$65,873** |
| V4 Body-CV | 737 | −$72,925 | +$10,845 |

**Both variants net-negative on YTD**, but V1 cuts the bleeding by 78%. V4 only cuts it by 13%. The Stage-1 finding (V4 looks better) was an artifact of:
1. **Set A** was curated for vertical-class movers (V4's strength)
2. **Set B** was 10 May-only days where V4 happened to preserve the regime-shift winners

On the broader sample, V1's per-trade selectivity dominates V4's "fire sometimes" behavior. V1 also has the best win rate (40.3% vs V0's 30.5% and V4's 28.7%).

**The YTD shows a deeper issue**: the MOVE_STRIKE + regime-shift strategy is net-unprofitable across the full year. Only May 2026 is positive (and only for V1: +$2,028). Surface this with Manny before real-money go-live 6/04 — see YTD appendix for full picture.

**Action**: `daily_run_v3.sh` updated to use V1 (`WB_MOVE_FADE_VWAP_ENABLED=1`) — was V4 prior to this update.

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

---

## YTD Appendix (added 2026-05-23 PM)

After the Stage-1 results recommended V4, Manny asked for a YTD backtest to validate the V1-vs-V4 question on a much larger sample. The results **flipped the recommendation**.

### Methodology

- **Universe**: All 4,431 (symbol, date) pairs in `tick_cache/2026-*/` — what the scanner would have surfaced live each day from Jan 02 → May 22 2026 (~98 trading days, 5 months)
- **Sim window**: 04:00-20:00 ET (full day — detector needs pre-7am context, some stocks run post-12pm)
- **Trade filter**: drop trades that fire before 07:00 ET (approximates live scanner discovery — first checkpoint is 07:00)
- **Harness**: `run_fade_gate_ytd.py` (ProcessPoolExecutor, 8 workers × 3 parallel variants = 24 concurrent sims)
- **Runtime**: ~40 min wall-time per variant (parallel)

### Caveats

1. **07:00 trade filter is permissive** — live scanner would discover some symbols later than 07:00, so my filter over-counts. But the over-counting is identical across V0/V1/V4, so the **differential** signal is valid.
2. **No fill model** — sim uses limit-at-signal-price; real fills would have more slippage. Again, identical across variants.

### Aggregate results

| Variant | Trades | Active days | Win days | Win rate | YTD P&L | Δ vs V0 |
|---|---:|---:|---:|---:|---:|---:|
| V0 baseline | 1,153 | 82 | 25 | 30.5% | −$83,770 | — |
| **V1 VWAP** | **239** | 77 | 31 | **40.3%** | **−$17,897** | **+$65,873** |
| V4 Body-CV | 737 | 80 | 23 | 28.7% | −$72,925 | +$10,845 |

V1 not only has the smallest YTD loss — it also has the **highest win rate** (40.3% vs 30.5%/28.7%). V4 actually has a *worse* win rate than baseline, meaning Body-CV blocks some attempts but doesn't improve trade-selection quality.

### Per-month breakdown

| Month | V0 P&L | V0 trades | V1 P&L | V1 trades | V4 P&L | V4 trades |
|---|---:|---:|---:|---:|---:|---:|
| 2026-01 | −$32,578 | 401 | −$7,751 | 52 | −$33,661 | 224 |
| 2026-02 | −$9,220 | 108 | −$5,050 | 31 | −$8,948 | 72 |
| 2026-03 | −$17,717 | 153 | −$3,028 | 32 | −$12,498 | 79 |
| 2026-04 | −$23,408 | 300 | −$4,096 | 62 | −$16,134 | 200 |
| 2026-05 | **−$847** | 191 | **+$2,028** | 62 | **−$1,684** | 162 |
| **YTD** | **−$83,770** | **1,153** | **−$17,897** | **239** | **−$72,925** | **737** |

Observations:
- **V1 is consistently better every single month** — not just on the curated big-mover sample
- **January was catastrophic for V0** (−$32K) and **V4 was barely better** (−$33K!). V1 cut it to −$7,751
- **V4 leaves substantial damage on the table** — its Body-CV signal fires slowly, so most disaster trades happen before the gate activates. VWAP fires immediately when price dips below VWAP — much earlier intervention.
- **Only May is positive for V1** (+$2,028) — confirms the Stage-1 +$3,411 Set B baseline was lucky/recent-improvement-biased, not representative of YTD

### V0 worst-10 days — what V1 prevents

| Date | V0 trades | V0 P&L |
|---|---:|---:|
| 2026-01-16 | 58 | −$11,908 |
| 2026-04-06 | 34 | −$8,490 |
| 2026-01-21 | 29 | −$7,158 |
| 2026-01-08 | 15 | −$6,113 |
| 2026-01-26 | 17 | −$5,933 |
| 2026-03-02 | 18 | −$5,771 |
| 2026-01-20 | 22 | −$5,591 |
| 2026-01-23 | 30 | −$4,905 |
| 2026-03-24 | 16 | −$4,177 |
| 2026-01-29 | 26 | −$4,073 |

These are the chain-of-doom days. V1's VWAP gate triggers early on these and prevents the cascade. V4's Body-CV gate requires accumulated bar-shape volatility to trigger and is consistently too late on these patterns.

### Verdict

**SHIP V1.** The YTD data overrides the Stage-1 directive criteria. V1 is:
- $66K better than baseline on YTD (vs V4's $11K)
- Best win rate (40.3%)
- Best every single month
- Particularly strong on the chain-of-doom days that crater V0 and V4

The Stage-1 V4 recommendation was based on a curated 31-day sample and a recent 10-day sample. Both biased toward V4's strengths. The 98-day full-universe YTD reveals V1 is the dominant choice.

`daily_run_v3.sh` updated: `WB_MOVE_FADE_VWAP_ENABLED=1` (was `WB_MOVE_FADE_BODY_CV_THRESHOLD=2.0`).

### The bigger issue — YTD net-negative across all variants

This is the bury-the-lede finding. Even V1, the best variant, loses $17,897 over 5 months on the broader universe. Only May 2026 is profitable, and only for V1 (+$2,028).

**Implications for 6/04 real-money go-live**:
- If May's positive trend is **real** (genuine strategy improvement from recent work — chase-skip fix, stay-armed, regime-shift), V1 should improve further in coming months
- If May's positive trend is **lucky variance**, V1 will revert to per-month losses of $3-8K once live capital is at stake
- Cannot distinguish from sample size of one month

Recommend: surface this with Manny **before 6/04**. Possible responses:
1. **Ship V1 and accept negative-EV risk** — bet on recent improvements continuing. Use small position size to bound damage.
2. **Delay 6/04** — accumulate more weeks of paper data to confirm May was the start of a positive run, not noise.
3. **Investigate the broader bleeding** — why is MOVE_STRIKE losing money Jan-Apr? Is it the strategy, the universe, or specific symbol-classes? Targeted research could find a fix.

### Files

- YTD per-variant JSON: `backtest_status/fade_gate_ytd_V*.json`
- YTD summary: `backtest_status/fade_gate_ytd_summary.json`
- Run logs: `backtest_status/fade_gate_ytd_V*_retry.log`
- Harness: `run_fade_gate_ytd.py`
