# Phase 3b Validation Results

**Owner:** CC
**Source directive:** `cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md` (Phase 3) and CC's recommended Phase 3b in `cowork_reports/2026-05-27_harness_validation_results.md`.
**Date:** 2026-05-27
**Verdict:** **Mixed.** AMSS regime_shift now matches live EXACTLY (entry 13:32, exit price $5.56). Variant C lands in spec (-4.5%, +1 trade). Variant A is borderline (+17.4%, +1 trade — just over the ±15% P&L bound). **Variant B regressed catastrophically** (sim now -$720 vs live +$688, a -205% delta) because Phase 3b's improved entry-time on ASTC interacted with the V1 VWAP fade-gate at a different price than live saw, blocking the trade live took.

The Phase 3b root-cause hypothesis (seed-cutoff) is partially correct — it fixed AMSS — but the underlying bar-construction divergence remains for symbols where pre-window cache was empty (FGL) or sparse (ASTC). Recommend a Phase 3c sub-directive that addresses the deeper bar-construction asymmetry, OR accepts current divergence as the limit of what tick-cache-driven sim can achieve.

---

## Three-variant comparison

### Live broker truth (unchanged baseline)

| Variant | Closed trades | Closed P&L | Notes |
|---|---|---|---|
| A | 4 | +$322 | AMSS chop pair (07:32, 07:34) + ASTC pair (08:46, 11:11) |
| B | 2 | +$688 | Fade blocked AMSS chop cycle; took only ASTC pair |
| C | 4 | +$396 | Similar to A; fade fired once but regime overrode |

### Phase 3b sim

| Variant | Closed trades | Closed P&L | Delta vs live |
|---|---|---|---|
| A | 5 | +$378 | +$56 / +17.4% — **❌ marginal** (±15% threshold) |
| B | 4 | **-$720** | **-$1,408 / -205% — ❌❌ regression** |
| C | 5 | +$378 | -$18 / -4.5% — **✅ P&L within tolerance** |

### Trade-list per variant

**Variant A (5 trades):**
```
04:27 FGL  $3.24 → $3.45 regime_shift_partial            +$429
04:27 FGL  $3.24 → $3.48 move_hwm_exit (runner)          +$54
10:37 ASTC $7.03 → $7.72 regime_shift_partial            +$574
10:37 ASTC $7.03 → $7.69 move_hwm_exit (runner)          +$61
13:32 AMSS $5.93 → $5.56 regime_shift_hard_stop          -$740   ← MATCHES LIVE EXACTLY
```

**Variant B (4 trades — fade-gate blocked ASTC, took an extra FGL re-entry):**
```
04:27 FGL  $3.24 → $3.45 regime_shift_partial            +$429
04:27 FGL  $3.24 → $3.48 move_hwm_exit (runner)          +$54
05:14 FGL  $3.71 → $3.07 move_stop_prox_bail             -$463   ← NEW, blocked in A/C
13:32 AMSS $5.93 → $5.56 regime_shift_hard_stop          -$740
                                            (NO ASTC — VWAP fade blocked at 10:37)
```

**Variant C (5 trades — identical to A; BodyCV fade didn't trigger here):**
```
04:27 FGL  $3.24 → $3.45 regime_shift_partial            +$429
04:27 FGL  $3.24 → $3.48 move_hwm_exit (runner)          +$54
10:37 ASTC $7.03 → $7.72 regime_shift_partial            +$574
10:37 ASTC $7.03 → $7.69 move_hwm_exit (runner)          +$61
13:32 AMSS $5.93 → $5.56 regime_shift_hard_stop          -$740
```

---

## What Phase 3b fixed (positive)

### 1. AMSS regime_shift — exact match with live

| Field | Live | Sim |
|---|---|---|
| Entry time | 13:32 | **13:32** ✓ |
| Entry price | $5.95 | $5.93 (≈ ±0.4%, slippage) |
| Exit reason | regime_shift_hard_stop | regime_shift_hard_stop ✓ |
| Exit price | $5.56 | **$5.56** ✓ exact |

This is the cleanest piece of evidence the harness works correctly when both paths see identical data. AMSS's regime entry happened in the afternoon, by which time both paths had processed enough of the day's tick history that bar construction converged.

### 2. Trade-record entry-time field now historical

Pre-3b: trade row showed wall-clock time (e.g., "18:09" from when the backtest ran).
Post-3b: shows the historical entry time (e.g., "04:27" for FGL, "13:32" for AMSS).
Implementation: `replay_ticks()` detects new-position transitions and overwrites `position.entry_time_et` with `_current_time_str_et`. Covers BOTH the MOVE_STRIKE entry path (via `_open_position_with_tag`) AND the REGIME_SHIFT direct-construction path in `_maybe_fire_regime_shift`.

### 3. Seed-cutoff plumbing landed in live code (zero behavior change)

`move_strike_subbot.py:_seed_symbol_from_cache` now respects `self._seed_cutoff_utc` if set, else falls back to `datetime.now(utc)` (the previous hardcoded behavior). Live behavior is byte-identical to before. Sim sets the attribute before `replay_ticks` to align seed with window start.

---

## What Phase 3b did NOT fix (negative)

### 1. FGL phantom arms persist

Live's sub-bot A logged "new symbol FGL" at 04:05:23 and **never armed FGL** (no ARMED line in the full day's log). Live's MAIN bot armed FGL at 05:02 ET (via SqueezeDetector, a different code path), and traded it 3 times.

Sim's MovementStrike — the SAME class live's sub-bot uses — armed FGL at 04:27 ET. The seed-cutoff change didn't suppress this; FGL had **zero ticks in cache before the window start** (`SEED FGL replayed 0 ticks from cache`), so cutoff had nothing to gate.

**Hypothesis**: tick cache files exist with all session data merged in (the bot accumulates ticks throughout the day). But MoveStrikeSubBot's `_ensure_symbol` runs `_seed_symbol_from_cache` at first-subscription time, when the cache may have been smaller. The cache I'm reading at backtest time has the full day's ticks. The cutoff filter removes future ticks BUT the bar-builder still processes seed ticks IN ORDER, and may construct different bars than live's bar-builder did when it processed those same ticks via live stream.

In short: **even with seed-cutoff, sim and live may build different bars from the same underlying tick set** because the timing of bar-builder state initialization differs. This is hard to fix without recording live's actual bar-stream.

### 2. ASTC entry shifted from 08:46 (live) to 10:37 (sim) — still 1h 51m off

Sim's ASTC regime_shift fired at 10:37 ET (was 10:46 pre-3b — 9 minute improvement). Live fired at 08:46. Both took the same direction (long), but sim's later entry hit a different bar landscape:
- Live caught the parabolic move from $7.06 to $11.27 peak. Live's partial exited at $9.70 → big winner.
- Sim entered at $7.03 but the regime_shift target ($7.03 + 1.5 × $0.22 = $7.36) was hit quickly, partial-exited at $7.72, runner at $7.69. Sim missed the rest of the ride.

The price level was similar; the bar history wasn't.

### 3. Variant B regression caused by entry-time cascade into fade-gate

Pre-3b, sim's Variant B entered ASTC at 10:46 (when sim's VWAP cooperated with the entry) and got +$635 from the ASTC trade. Post-3b's tighter entry timing at 10:37 happened to hit a VWAP-below-price configuration, so the V1 VWAP fade-gate BLOCKED the trade. Result: sim B lost the ASTC winner AND took an extra FGL re-entry loss. Net: -$720.

This is a **cascade**:
- Bar-construction divergence (sim arms FGL/ASTC at different times than live)
- → Entry-time shift (10:37 vs 08:46)
- → Fade-gate evaluation happens at a different bar/price (price above vs below VWAP)
- → Different trade selection
- → Different outcome

Phase 3b reduced the first-layer divergence partially (closer entries for ASTC), but the residual shift was enough to flip the fade-gate decision, which cascades into much worse trade selection on V_B.

---

## Acceptance criteria (revised in 3b)

Per the validation results report's recommendation, I had relaxed acceptance to:
- ±15% P&L per variant
- ±1 trade count

Phase 3b results:

| Variant | ±15% P&L? | ±1 trade count? | Both pass? |
|---|---|---|---|
| A | ❌ (+17.4%) | ✅ (+1) | **NO** |
| B | ❌❌ (-205%) | ❌ (+2) | **NO** |
| C | ✅ (-4.5%) | ✅ (+1) | **YES** |

**1 of 3 variants passes both criteria.** Not enough to call the harness production-ready.

---

## What the remaining divergence tells us

The single cleanest signal is the AMSS afternoon trade matching exactly. The single nosiest signal is FGL's phantom arms. The middle case is ASTC's 1h 51m entry shift.

**The pattern**: when both paths have plenty of bar history (afternoon AMSS), they agree. When one path is starved of bar history (FGL early-morning) or has compressed bar history (ASTC pre-market with sparse early ticks), they disagree.

This points to a deeper structural divergence beyond what seed-cutoff alone can fix:

**Hypothesis**: live's bar-builder processes ticks AS THEY ARRIVE in real-time. Each tick updates the in-progress bar, and bar-close fires when the boundary tick arrives. Bar OHLCV is computed from the exact tick sequence the engine published.

Sim's bar-builder processes ticks FROM THE CACHE, which is a flushed-every-30s snapshot of the bot's tick buffer. The cache may:
- Contain ticks the live bot processed (these are in order with their original timestamps)
- Miss ticks that arrived during the flush window or got deduplicated
- Have ticks aggregated into bars slightly differently because the boundary logic uses tick timestamps that may be ms-different from what live saw

For most ticks, this is invisible. For BORDERLINE bars (where a bar-close decision hangs on whether one tick is INSIDE or OUTSIDE the bar's 1-minute window), it can flip arm/no-arm decisions.

---

## Three paths forward

### Path A — Phase 3c: deeper bar-construction parity work

Concrete options to investigate:

1. **Compare sim's bars to live's bars on a known symbol/day where both are available.** Live's bar-builder fires `on_bar_close_1m` callbacks; if we instrument those to log full OHLCV, we can compare day-by-day for divergence patterns. Could reveal a specific bar-builder edge case (e.g., bar boundary at minute :00 vs :60).

2. **Have sim's seed feed ticks one-by-one (not bar-by-bar)** so the bar-builder reconstructs bars identically to live. Currently `_seed_symbol_from_cache` calls `bar_builder.on_trade(symbol, price, size, ts)` per tick — which is per-tick. So this might already be correct, in which case the divergence is purely about WHICH TICKS exist in cache vs live stream.

3. **Record live's bar-stream** (not just tick cache) into a parallel file, replay that. Larger change. Would close the gap definitively but requires modifying live to write a bar-stream file.

Estimated effort: 3-8 hours depending on which option.

### Path B — accept current divergence as the limit, document it, move on

The harness IS useful even with these limitations:
- Decision-logic parity is proven (AMSS matched exactly)
- 28× universe coverage improvement (113 symbols vs 4 in legacy harness)
- Position sizing now correct (PROBE_SIZE_MULT=0.5)
- Reproduces partial scale-out + HWM runner mechanics
- Catches MAJORITY of live trades within +/-1 trade

For RESEARCH QUESTIONS where directional answers matter more than exact P&L (e.g., "does adding gate X reduce or increase trade count?"), the current harness is adequate. For PRODUCTION-PARITY decisions (e.g., "will this strategy make exactly $X next month?"), we need the deeper fix or accept that live is the source of truth.

### Path C — escalate to Manny/Cowork for decision

Given the regression on Variant B specifically (caused by fade-gate cascade), the harness can produce MISLEADING per-variant comparisons. Continuing to use it for fade-gate research is risky.

CC recommends Path C: pause harness work, surface the cascade finding to Manny + Cowork, and decide whether to invest in Path A vs accept Path B as the operational reality.

---

## Open questions for the next directive

1. **Bar-builder parity**: is it worth a dedicated audit of `bars.py:TradeBarBuilder` to confirm sim and live build IDENTICAL bars from identical tick sequences? If they do, the divergence is purely about WHICH ticks exist in each path (which is harder to fix). If they don't, that's a simpler code fix.

2. **Live bar-stream recording**: would Manny accept ~30 LOC of "write each bar-close to a parallel file" added to live's bar callback? That gives us ground-truth bars to replay against and would close the harness divergence definitively.

3. **Acceptance threshold relaxation**: Variant C passes (-4.5%, +1 trade). If we declare that "good enough" for variant-comparison research, the harness can be used for the REENTRY GREEN gate question and similar — accepting that A/B/C absolute numbers may diverge by ~15-20% from live but DIRECTIONAL outcomes (gate helps vs hurts) should still be correct.

4. **Variant B's regression specifically**: should we add a sanity check in the harness that fails out if any variant differs by > 50% from live? Would catch unstable fade-gate cascade outcomes before they polluted research.

---

## Recommendation

**Do not ship Phase 4 (extract sub_bot_core.py) yet.** Phase 3b improvements are real but the V_B regression shows the harness can produce misleading variant comparisons. Phase 4 refactor would lock in the current sim/live split as the canonical architecture — premature given the divergence findings.

**Recommend Path C**: pause + decide. The harness in its current state has one decisive use (matching the AMSS afternoon regime trade) and one decisive failure (V_B regression). Neither result is conclusive enough to declare done.

If Manny / Cowork wants to continue: Path A's option 1 (bar-builder comparison) is the cheapest next experiment — ~1 hour to instrument live's bar callback with a bar-stream log, then replay one day's bars side-by-side with sim's bars to find the exact divergence point.

---

## Files committed in Phase 3b

- `move_strike_subbot.py`: seed-cutoff via `self._seed_cutoff_utc` attribute (commit `058ea81`)
- `simulate_subbot.py`: re-enabled seed with cutoff, entry-time transition detection, removed redundant monkey-patch (commit `058ea81`)
- `backtest_status/validate_today_variant_{A,B,C}_phase3b.log`: run logs
- `backtest_status/replay_subbot_VALIDATE_VARIANT_{A,B,C}_PHASE3B_*.json`: trade detail

---

## Cross-references

- `cowork_reports/2026-05-27_subbot_vs_sim_audit.md` — Phase 1 audit
- `cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md` — directive
- `cowork_reports/2026-05-27_harness_validation_results.md` — Phase 3 results that motivated 3b
- `cowork_reports/2026-05-27_subbot_trade_deep_dive.md` — today's live broker truth

---

*Phase 3b validation complete. Standing by for Path A/B/C decision.*
