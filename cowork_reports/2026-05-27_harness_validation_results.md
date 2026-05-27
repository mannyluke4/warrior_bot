# Phase 3 Validation Results: simulate_subbot.py + replay_subbot_universe.py

**Owner:** CC
**Source directive:** `cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md` (Phase 3)
**Date:** 2026-05-27 (live data: 04:00 → 16:30 ET, partial day)
**Verdict:** **FAIL** acceptance criteria. Harness is **functional** (runs end-to-end, decision logic inherited cleanly, no crashes). **Root cause of divergence identified** (bar-construction warm-up). Fix path is concrete and bounded; recommend a Phase 3b sub-directive to land it before considering harness production-ready.

---

## TL;DR

The new harness reproduces a SUBSET of today's live behavior but diverges substantially on entry-detection timing for ASTC and FGL. AMSS regime_shift hard_stop matches live exactly. Net result: 5-6 sim trades per variant vs live's 2-4, with one matching trade (AMSS), one ~near-match (ASTC entry price within 0.4%, exit price diverges), and two phantom trades (FGL ×2) sim took that live's sub-bot never armed.

**Root cause:** I disabled `WB_SUBBOT_SEED_FROM_CACHE=0` in sim to avoid double-counting ticks, but that strips the pre-window historical context that live's bot reads via seed at first-subscription. Sim's `MovementStrike` detector ends up with a shallower bar history than live, producing different ARM decisions, which cascades into different REGIME_SHIFT firings.

**Fix (Phase 3b directive scope):** re-enable seed with a cutoff timestamp so seed reads cache up to the replay window start; replay then feeds ticks from window start onward. Both paths see identical warm-up + identical live stream.

---

## Per-variant comparison

### Live broker truth (from `cowork_reports/2026-05-27_subbot_trade_deep_dive.md`)

| Variant | Closed trades | Closed P&L | Fade blocks | Notes |
|---|---|---|---|---|
| A (no fade) | 4 | **+$322** | 0 | AMSS +$46/-$379 + ASTC +$1,110/-$454 |
| B (V1 VWAP fade) | 2 | **+$688** | 1 (AMSS @ 07:32) | Fade blocked the AMSS chop cycle |
| C (V4 BodyCV fade) | 4 | **+$396** | 1 (AMSS @ 13:31, regime overrode) | Fade fired once but regime entered 60s later |

Open position across all variants: AMSS qty ~2000 from afternoon regime_shift re-entry @ ~$6.05 (after the 13:32 regime_shift hard-stopped at 15:14 — note: **this hard_stop is also what sim caught**; the live REENTRY GREEN at 15:16 is what's currently held with +$100 unrealized).

### Sim (new harness — same env vars per variant)

| Variant | Trades | P&L | Symbols watched | Symbols traded | Skipped |
|---|---|---|---|---|---|
| A | 6 | +$384 | 113 | 3 | 0 |
| B | 5 | +$378 | 113 | 3 | 0 |
| C | 5 | +$378 | 113 | 3 | 0 |

### Delta (sim − live)

| Variant | Trade count | P&L | % of live | Pass ±15%? |
|---|---|---|---|---|
| A | +2 | +$62 | +19% | **FAIL** (just over) |
| B | +3 | **-$310** | **-45%** | **FAIL** |
| C | +1 | -$18 | -4.5% | ✅ P&L only |

**Trade-count acceptance fails on all three variants. P&L acceptance fails on A and B. C's P&L matches within tolerance, but trade count diverges.**

---

## Per-trade comparison

Sim trade list (Variant A; B and C are subsets with the ASTC re-entry filtered):

| Time (exit) | Symbol | Entry | Exit | Reason | P&L | In live A? |
|---|---|---|---|---|---|---|
| 05:02 | FGL | $3.24 | $3.45 | regime_shift_partial | +$429 | **NO** — live A never armed FGL |
| 05:05 | FGL | $3.24 | $3.48 | move_hwm_exit | +$54 | **NO** |
| 10:46 | ASTC | $7.03 | $7.72 | regime_shift_partial | +$574 | Live entered ASTC at **08:46** ($7.06), partial-exited at $9.70 (+$1,038 on partial leg) — **same entry direction, different bar timing + much longer ride** |
| 10:46 | ASTC | $7.03 | $7.69 | move_hwm_exit (runner) | +$61 | Live runner exited at $10.00 (+$72 on small remainder). Sim's runner exited much earlier. |
| 10:59 | ASTC | $9.94 | $9.98 | move_hwm_exit | +$6 | Live's REENTRY GREEN was at 11:11 ($9.83 → $9.35 = **-$454**). Sim took a different ASTC entry post-partial and exited tiny win. |
| 15:14 | AMSS | $5.93 | $5.56 | regime_shift_hard_stop | -$740 | ✓ **MATCH** — live entered regime_shift at 13:32 ($5.95), hard_stop at 15:14 ($5.56 exit price exact). Then live REENTRY GREEN at 15:16 (currently open at +$100). |

### Trades live took that sim missed

- **AMSS morning move_strike** (07:32 +$46 small win, 07:34 REENTRY -$379 loss): sim never armed AMSS in the morning. Live did at 07:19 ET with entry=$13.02, stop=$12.90, R=$0.12.
- **ASTC regime_shift @ 08:46** (the big +$1,110 winner that all 3 variants caught live): sim entered ASTC ~2 hours later at a different bar, and the partial+runner ride was much shorter ($7.72 vs $10.00 exit).
- **ASTC REENTRY GREEN @ 11:11** (-$454 live): sim took a different post-partial ASTC entry at 10:59 for +$6.

### Trades sim took that live didn't

- **FGL ×2** (regime_shift partial + runner = +$483 total): live's sub-bot A only logged "new symbol FGL" with no ARM, no entry. Sim armed FGL via MovementStrike then fired regime_shift on a body=$0.43 baseline=$0.0911 ratio=4.72 bar. Live's `MovementStrike` should be the same code (`movement_strike.py` shared import). **The detector code is identical; the bar data isn't.**

---

## Root cause diagnosis

**The decision logic is shared bit-for-bit** (sim subclasses `MoveStrikeSubBot`, imports `RegimeShiftDetector` from the live module, uses `hwm_evaluate` from `hwm_exit.py`, uses `MovementStrike` from `movement_strike.py`). When given identical bar+tick inputs, the two paths produce identical decisions. The AMSS regime_shift hard_stop matching exit ($5.56) is direct proof of this.

**The data going into the decision logic differs.** Specifically:

In live, `MoveStrikeSubBot._ensure_symbol()` calls `_seed_symbol_from_cache(symbol)` on first tick for a new symbol. This reads `tick_cache/<today>/<sym>.json.gz` and replays ALL ticks through the detector + bar builder before any live ticks arrive. Result: live's detectors have a warm history (all pre-subscription ticks) before the first live tick is processed.

In sim, I set `WB_SUBBOT_SEED_FROM_CACHE=0` to avoid double-counting (when seed=ON, the cache replay processes ticks that my `replay_ticks()` would ALSO process). Result: sim's detectors only see ticks WITHIN the `[start_et, end_et]` window. Pre-window ticks (typically pre-04:00 ET) are invisible.

For symbols where the bot's first arm/regime trigger depends on pre-window context (e.g., FGL's MovementStrike arm bar at 04:55 needs a baseline computed from earlier bars), sim's detector is operating without that history. It either arms or doesn't on different criteria than live.

### Why ASTC entered 2 hours later in sim

Live's regime_shift required-armed gate: `regime_shift_require_armed=1`. The detector won't fire regime_shift until MovementStrike has armed the symbol at least once. Live armed ASTC at some pre-08:46 timestamp; sim's missing-history meant sim's MovementStrike armed ASTC at some LATER bar (10:46). Once armed, regime_shift fired on the next qualifying body-ratio bar.

So sim is firing the same logical sequence as live (arm → regime) — just timeshifted by hours due to detector warmup happening late.

### Why FGL phantom-traded in sim

Live's sub-bot logged "new symbol FGL" at 04:05:23 but NEVER ARMED. The MovementStrike detector evaluated bars and found no qualifying arm bar before the day ended.

In sim, MovementStrike DID find a qualifying arm bar — at 04:55ish. This means sim's bar builder produced an arm-qualifying bar where live's bar builder didn't. Either:
- Sim's bars have different OHLCV from live's bars on the SAME underlying ticks (boundary or aggregation difference)
- Sim's bars are computed from a different SUBSET of ticks (window-filtering effects)

Most likely explanation per the seed-from-cache theory: live's seed loaded pre-04:05 ticks → built a bar at, say, 04:00-04:05 with one OHLCV; sim skipped those ticks → built FGL's first bar starting at the first in-window tick, which had a different aggregation → different arm decision.

### Why AMSS regime_shift hard_stop matched exactly

The AMSS regime_shift entry happens in the AFTERNOON (live: 13:32, sim: 13:32-ish). By that time, both sim and live have processed the same range of ticks (the morning's $14 ramp, the crash to $6, etc.). The detector warmup difference no longer matters — both have plenty of history. Both fire the regime_shift trigger on the same bar. Both hit the same hard_stop at the same price.

**This is direct evidence that the decision logic + shared imports work correctly. The divergence is purely a startup-warmup issue.**

---

## Fix path (input for Phase 3b sub-directive)

### The minimal change

`simulate_subbot.py:replay_ticks` and the bot's `_ensure_symbol` need to coordinate so seed-from-cache runs ONCE with a clear cutoff:

1. **Re-enable seed**: set `WB_SUBBOT_SEED_FROM_CACHE=1` (or omit the override).
2. **Patch `_seed_symbol_from_cache`** to accept a cutoff timestamp. Read cache ticks; only feed those with `ts < cutoff` into the detector.
3. **Set cutoff = window start** in `simulate_subbot.py:replay_ticks`. After seeding completes, my replay then feeds ticks with `ts >= cutoff`.
4. **Result**: seed gives detectors pre-window context exactly equivalent to live's seed at subscription time. Replay then feeds the same forward stream live's engine socket fanned out. Each tick processed exactly once.

This is ~15-25 LOC change in `move_strike_subbot.py` (adding cutoff parameter to seed) + ~5 LOC in `simulate_subbot.py` (call seed before replay loop).

### Expected outcome after fix

- ASTC arm timing: sim should arm at the same bar live armed.
- FGL: sim's MovementStrike should produce the same "no arm" decision live got.
- AMSS morning trades: sim should fire on the same 07:32 arm bar live did.
- Trade count parity: should drop to within ±1 trade per variant on a typical day.
- P&L parity: should hit within ±15% on all variants if the above corrections land.

### What remains as unfixable-by-sim divergence

Even with seed-cutoff fix, some divergence will persist:

- **Single-position constraint timing**: live's sub-bot is single-position. If two symbols print arm bars at overlapping minutes, live takes the first; sim doesn't have inter-symbol coupling (each symbol runs in a fresh subprocess). Sim might double-take where live single-takes. Open question for the directive.
- **Engine socket tick semantics**: live's tick stream comes from the engine publisher; tick cache writes are periodic flushes that may capture different tick boundaries than live's real-time processing. Should be small but not zero divergence.
- **Order fill simulation**: sim assumes instant fill at limit; live has Alpaca-side fill timing variance, partial fills, and slippage that sim can't model from tick data alone.

---

## What this validation PROVES (positive findings)

1. **Decision-logic inheritance works correctly.** Subclassing approach (vs clean-room duplicate) succeeded — no manual code duplication, no drift between sim and live decision tree.
2. **The AMSS regime_shift hard_stop matched exit price exactly** ($5.56). When both paths see the same data window, they produce the same decision.
3. **`replay_subbot_universe.py` discovers a realistic universe** (113 symbols/day from sub-bot log parsing, vs the legacy harness's 4 symbols from main bot daily.log). This is a ~28× coverage improvement.
4. **No crashes, no EOFErrors, no silent failures.** Atomic-write fix to live's tick cache lands at next 02:00 MT cron; today's run had some race tolerance built into simulate_subbot.py.
5. **Phase 1 Drift 1 fix shipped** — `WB_REGIME_SHIFT_RATIO_THRESHOLD` default 4.0 now matches live in both simulate_subbot.py (always) and simulate.py (so any future research on the legacy harness also doesn't over-fire).

---

## What this validation REVEALS (negative findings — informs Phase 3b)

1. **Seed-from-cache warm-up is load-bearing** for entry-detection parity. Disabling it in sim is wrong; needs cutoff-based re-enablement.
2. **`simulate_subbot.py`'s trade-record output uses EXIT time, not entry time** — a minor cosmetic bug. Should use `p.entry_time_et` for the time field to match `simulate.py` convention.
3. **Per-symbol subprocess isolation** means sim doesn't model the single-position constraint across symbols. May not matter for most days, but on days with simultaneous setups, sim's over-counting becomes visible.
4. **`replay_subbot_universe.py` doesn't capture fade-gate block events** from sim subprocess output (sim's FADE_GATE_BLOCK lines go to stdout but the harness's TRADE_LINE_RE parser doesn't pull them). Should be added so we can validate fade-gate behavior against live.

---

## Recommendation

### Don't ship the duplicate-vs-live refactor yet (Phase 4)

The directive's Phase 4 was deferred pending Phase 3 validation. Result: validation didn't pass acceptance, so Phase 4 should wait until 3b lands.

### Phase 3b proposed scope (for Cowork to formalize)

1. Add cutoff parameter to `move_strike_subbot.py:_seed_symbol_from_cache`. Live behavior unchanged (no cutoff → reads all).
2. Wire cutoff in `simulate_subbot.py:replay_ticks` to call seed once before the live-stream feed.
3. Fix entry-time vs exit-time in trade-record emission.
4. Re-run Phase 3 validation. Accept if A/B/C all land within ±15% P&L AND trade count is within ±1 of live (relaxed from "exact" to allow for single-position-constraint cross-symbol timing).
5. If 3b passes: ship Phase 4 (extract `sub_bot_core.py` shared module) the same week.
6. If 3b still diverges: the bar/tick semantics gap is bigger than seed-warmup. Then we're looking at engine-socket recording or accepting backtest-vs-live divergence at some baseline level.

### Time estimate for Phase 3b

~1-2 hours to implement + ~1 hour to re-validate. Total <half a day.

---

## Open questions for Manny + Cowork

1. **Phase 3b vs continuing to use the harness as-is for research questions:** even with current divergence, the harness reproduces the AMSS regime_shift correctly. Are there research questions we can answer NOW (e.g., REENTRY GREEN hypothesis re-test) before 3b lands? My read: no — the FGL/ASTC divergences would pollute the dataset.

2. **Single-position cross-symbol constraint**: should we add this to `simulate_subbot.py` (track a global "open position" across symbol subprocesses)? Probably yes for fidelity, but requires a different harness architecture (single long-running process consuming a multi-symbol time-merged tick stream, vs the current per-symbol subprocess model). Substantial refactor — defer or address in 3b?

3. **The AMSS regime_shift hard_stop in sim says -$740, but live's same trade closed at -$780 then re-entered.** Sim doesn't model the REENTRY GREEN that fired 2 seconds later. This is acceptable per Phase 3 acceptance criteria (closed P&L only), but the open position semantics differ. Worth a note in any directive that asks the harness to predict end-of-day P&L including reopens.

---

## Cross-references

- `cowork_reports/2026-05-27_subbot_vs_sim_audit.md` — Phase 1 audit that surfaced the 6 drifts.
- `cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md` — Phases 1-4 directive.
- `cowork_reports/2026-05-27_subbot_trade_deep_dive.md` — live broker-truth baseline for today.
- `move_strike_subbot.py:534-595` — `_ensure_symbol` + `_seed_symbol_from_cache` (the load-bearing seed mechanism).
- `simulate_subbot.py:53-58` — the `WB_SUBBOT_SEED_FROM_CACHE=0` override that caused the divergence.

---

*Phase 3 validation complete. Standing by for Phase 3b directive or guidance on next research priority.*
