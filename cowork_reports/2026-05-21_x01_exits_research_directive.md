# Research Directive: Capturing Vertical Moves with X01-Style Exits

**Date**: 2026-05-21
**Branch**: `v2-ibkr-migration`
**Reporting context**: Sub-bot (MOVE_STRIKE) paper session 2026-05-21. PCLA went **$2.95 → $6.45 (~119% / ~23R)** in 13 minutes (16:54–17:07 ET). Bot captured only **+$540 live / +$622 sim** out of a possible **$5,000+** because HWM 25% trail exited on the first intra-bar pullback.

**Goal of this directive**: figure out how to make the sub-bot capture vertical PCLA-class moves *without* destroying its performance on the broader sample (10-day historical +$2,498 with the current HWM + same-bar + stay-armed + below-arm config).

---

## What's already validated (do not re-test)

These results are confirmed and shipped (commit `b034a10`). Read [[project_alpaca_subbot]] and [[project_dynamic_exit_research_2026-05-21]] before starting.

| Config | 10-day total | PCLA 2026-05-21 |
|---|---|---|
| **HWM 25% + same-bar block + stay-armed + below-arm 3%** *(current)* | **+$2,498** | +$622 |
| Legacy (no fixes) | +$1,759 | −$122 |

### What I tested today and ruled out

1. **Fixed R-distance trail** (`WB_BT_MOVE_HWM_FIXED_TRAIL_R`): tested at 1.0R, 2.0R, 3.0R. All produced negative net on 10d sample (−$5 to −$1,299). Captures PCLA-style winners but bleeds on choppy days.

2. **Dynamic widening via `WB_BT_MOVE_HWM_WIDE_AT_R`** (switch trail mode when gain crosses N R): code is shipped but gated off. Tested with `WIDE_AT_R=1.5, WIDE_TRAIL_R=2.0` → PCLA trade 1 lost $233 because peak barely crossed 1.5R then collapsed back, and the wider 2R trail let it ride down. Higher thresholds (2R, 3R, 4R) didn't trigger because HWM 25% fires *before* the position can reach those levels — the chicken-and-egg problem.

3. **Bar-close-only trail**: tested manually against PCLA data. PCLA's first bar closed at $2.96 with peak $2.99 — already below the $2.98 trail level. Bar-close evaluation doesn't save it.

4. **Volume / VWAP / MACD-bullish suppressors** (`WB_BT_MOVE_HWM_VOL_SUPPRESS`, `_VWAP_SUPPRESS`, `_MACD_SUPPRESS`): all tested today, all proved net-flat or net-negative on the 10d sample. The MACD/signal cross had already turned bearish at the trail-fire moment (mathematically correct — momentum had turned). VWAP suppressor held losses too long. Vol suppressor (even with in-progress bar tracking) didn't change the exit price.

5. **Full X01 exits** (`WB_BT_MOVE_HWM_EXIT=0`, letting the squeeze framework's `sq_target_hit` + runner trail take over): captured PCLA +$1,819 today (vs HWM's $622) BUT lost on the 10d sample (−$577 vs HWM +$2,498). The bail_timer (5-min unprofitable exit) over-traded on chop days (5/18 had 11 trades vs 2 with HWM, mostly losers).

### Discriminator analysis (at-entry-time signals)

Captured features for every 10d+today trade (see body_ratio, vol_ratio, pre_pct features in research session). Conclusion: **at-entry-time signals do not cleanly separate big winners from chop losers**. Body × ratios of 3-5× appear in both winners AND losers. PCLA's eventual 23R move came 40+ minutes after entry — no entry-time signal could predict it.

**Mid-trade signal `gain > 1.5R`** *would* cleanly separate (losers never reach 1.5R; winners cross 2R+), but the HWM 25% trail fires before the position can build to that level.

---

## Research directions worth pursuing

### Direction A (highest priority): X01 exits minus bail_timer

The full X01 exit framework captured PCLA +$1,819 cleanly but lost $3,075 vs HWM on 10d. The biggest 10d killer was **bail_timer (`WB_BAIL_TIMER_ENABLED=1`, 5-min unprofitable exit)** firing too aggressively after MOVE_STRIKE entries. The MOVE_STRIKE entry timing differs from the original squeeze level-break entries the bail_timer was tuned for.

**Hypothesis**: Disabling bail_timer specifically for MOVE_STRIKE positions (or extending its timeout to 15+ min) recovers most of the 10d gap while keeping the X01 target_hit + runner trail advantage on vertical moves.

**Experiment**:
1. Run `replay_live_universe.py --start 2026-05-07 --end 2026-05-20` with:
   - `WB_BT_MOVE_STRIKE=1 WB_BT_MOVE_HWM_EXIT=0` (X01 exits)
   - `WB_BAIL_TIMER_ENABLED=0`
   - All other current fixes (same-bar block, stay-armed, below-arm)
2. Then with `WB_BAIL_TIMER_MINUTES=15` (still on but more permissive)
3. Then with `WB_BAIL_TIMER_MINUTES=10`
4. Compare to baseline HWM +$2,498 and full-X01 −$577

**Success criteria**: any config that beats +$2,498 on 10d AND captures >+$1,500 on PCLA 2026-05-21. If found, ship it.

### Direction B: Scale-out partial at 1.5R + HWM runner

Instead of swapping the entire exit framework, **layer scale-out on top of HWM**:
- At gain = 1.5R (target hit), exit 50-90% of position
- Remaining 10-50% (the "runner") keeps HWM 25% trail but from a higher peak
- Hard stop + prox bail unchanged

**Hypothesis**: this captures the certain-win at 1.5R (most winners), and gives the runner free option on the rare vertical move. Avoids the bail_timer over-trading that killed full X01.

**Experiment**:
1. Add a partial-exit mechanism to `simulate.py`'s MOVE_STRIKE branch:
   - When position's gain crosses 1.5R, exit `core_pct%` (try 50%, 75%, 90%)
   - Remaining position runs with current HWM trail
2. Backtest on the 10-day + PCLA 2026-05-21
3. Tune `core_pct` and target threshold

**Success criteria**: same as Direction A.

### Direction C: Volatility-adjusted trail width

Currently every trade uses the same 25% trail regardless of stock characteristics. PCLA is volatile ($3 stock with multi-cent swings); QUCY is also volatile; ATPC is smoother. **A trail proportional to recent volatility** might naturally widen for vertical movers.

**Hypothesis**: trail width = `max(25% × gain, K × ATR)` where K is a tuning constant. On high-volatility bars, the ATR-based component dominates, giving naturally wider trails.

**Experiment**:
1. Add bar-by-bar ATR tracking to SimTradeManager (already have bar history)
2. Modify trail level to use `max(default_trail, k * atr)`
3. Tune k

**Less certain than A and B** because ATR is a lagging indicator and might widen too late.

### Direction D: Pattern-based widening

When the last N bars show "vertical pattern" (large green bodies, growing volume, consecutive HH), widen the trail. We tested vol suppressor briefly but it was scoped too narrowly.

**Hypothesis**: a multi-bar pattern check (e.g., "last 3 bars: all green, body > 1.5× avg, vol > 1.5× avg") flags vertical trades. Switch to wider trail when flagged.

**Less promising** — adds complexity, may have same chicken-and-egg problem as `WIDE_AT_R`.

---

## What to deliver

For each direction explored:
1. A backtest table with the **same 11-day window** (5/07–5/20 + 5/21 PCLA) so results are directly comparable.
2. Per-day P&L breakdown showing where the variant wins/loses vs current HWM baseline.
3. Trade-level inspection of any 2-3 trades where the variant changes behavior — confirm the change is doing what we expect.
4. A recommendation: ship, defer, or kill.

If a variant beats current config: stage it in a commit, push, but **do not enable it in `daily_run_v3.sh`** without Manny's explicit approval — keep all new flags defaulted off and gate the wiring change for review.

If no variant beats current config: write up the dead ends in a follow-up memory note so we don't repeat them.

---

## Reference points

- **Current shipped config**: `/Users/duffy/warrior_bot_v2/daily_run_v3.sh` lines 266-276 (the sub-bot launch block).
- **Sim entry point**: `simulate.py` MOVE_STRIKE branch starts around line 3622. HWM exit at `_hwm_exit()` method.
- **Backtest harness**: `replay_live_universe.py` (1:1 to live coverage; uses `--slippage 0.07` for realistic fills).
- **PCLA tick cache**: `tick_cache/2026-05-21/PCLA.json.gz` (restored from snapshot — see [[project_tick_cache_eod_truncation_2026-05-21]] for the corruption incident).
- **Per-trade data**: `backtest_status/replay_stay_armed_gated_2026-05-07_2026-05-20.json` for the 10d trade-level features.

---

## Constraints

- Same-bar re-entry block (`WB_BT_MOVE_REENTRY_BLOCK_SAME_BAR=1`) **must stay on** — it's a day-trading principle, not negotiable.
- Below-arm 3% filter (`WB_BT_MOVE_MAX_BELOW_ARM_PCT=3.0`) **must stay on** — saved PIII $670 on 2026-05-21.
- Stay-armed (`WB_BT_MOVE_STAY_ARMED=1`) **must stay on** — captured QUCY 9:30 ripper for +$173 swing today; +$1,248 over 10d sample.
- No market orders ever. No broker-side stops ever. (See [[feedback_no_market_orders]], [[feedback_no_broker_stops]].)
- Real-money deadline: 2026-06-04. Time-box this research to ~2-3 days; if no clean win by then, lock current config and move on.
