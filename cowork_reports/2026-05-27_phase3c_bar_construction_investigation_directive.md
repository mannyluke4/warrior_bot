# Directive: Phase 3c — Bar-Construction Divergence Investigation

**Date**: 2026-05-27
**Branch**: `v2-ibkr-migration`
**Owner**: CC
**Source**: `cowork_reports/2026-05-27_harness_validation_phase3b.md` (commit `66d6878`). Phase 3b validation showed AMSS regime_shift matches live exactly when both paths have plenty of bar history, but FGL/ASTC entries diverge by 1h+ when one path is starved of bar history. CC's hypothesis: sim's tick-cache replay produces subtly different bars than live's real-time bar-builder, flipping arm/no-arm decisions on borderline bars. Variant B's -205% delta is the proof — bar-construction divergence cascaded into fade-gate evaluating at a different price than live saw.

---

**Pacing rule**: This is the cheap investigation before committing to a bigger fix. Box at ~3 hours. If divergence point is found and fixable, ship the fix. If divergence is the timing-edge-case CC hypothesizes, surface that finding and we decide on bar-stream recording (Path A Option 3) separately.

---

## Why this investigation before any bigger commitment

Two architectural directions exist:
- **Fixable bar-builder bug**: cheap to fix (~1 hour after this investigation finds the bug), restores harness usability for most research.
- **Fundamental timing-edge-case**: requires recording live's bar-stream to disk (~1-2 day commitment), Path A Option 3.

We don't know which yet. The 1-hour investigation tells us. CC explicitly recommended this as the cheapest next experiment in the Phase 3b results report.

---

## What to instrument

Add a bar-stream logger to live's bar callback. The minimal change:

In `bot_v3_hybrid.py` (or wherever the bar-close callback fires — `bars.py:TradeBarBuilder.on_bar_close_1m` is the likely site), emit a single JSONL line per bar close to `logs/bar_stream/<YYYY-MM-DD>.jsonl`:

```json
{"ts": "2026-05-27T08:46:00-04:00", "sym": "ASTC", "o": 6.95, "h": 7.18, "l": 6.92, "c": 7.05, "v": 145000, "tick_count": 487, "first_tick_ts": "2026-05-27T08:45:00.123-04:00", "last_tick_ts": "2026-05-27T08:45:59.876-04:00"}
```

Fields needed:
- `ts`: bar close timestamp (ISO 8601 with ET offset)
- `sym`: symbol
- `o`, `h`, `l`, `c`, `v`: OHLCV (standard)
- `tick_count`: how many ticks aggregated into this bar (signal for borderline-boundary cases)
- `first_tick_ts`, `last_tick_ts`: timestamps of first and last tick included in this bar (the boundary signal — if sim and live disagree on which ticks belong to this bar, these timestamps differ)

Gate behind `WB_BAR_STREAM_LOG_ENABLED` env var, default 0. Flip to 1 for the investigation, off again after.

Live behavior must be byte-identical when env is off (no change to bar-builder logic, only an added log emission when enabled).

---

## What to compare

Once the bar-stream log exists, run live for one trading day with the logger enabled. Then:

1. **Pick one symbol where Phase 3b showed clear divergence** — ASTC and FGL are the obvious candidates (ASTC: 1h 51m entry shift; FGL: phantom arm at 04:27 sim but never armed in live).

2. **Run `simulate_subbot.py` against that day for the same symbol** with bar-stream logging also enabled in sim (CC adds an equivalent log emission to sim's bar-builder code path).

3. **Diff the two bar streams** for that symbol on that day. Specifically:
   - For each bar, compare OHLCV byte-by-byte
   - Where bars differ, compare `first_tick_ts` and `last_tick_ts`
   - Categorize each divergence:
     - **Bar boundary differs** (first_tick_ts or last_tick_ts off by milliseconds): timing-edge-case. Path A Option 3 territory.
     - **OHLCV differs but boundaries match**: bar-builder bug. Fixable.
     - **Sim has a bar live doesn't, or vice versa**: missing/extra ticks. Cache vs live-stream gap.
     - **Sim has zero bars where live has many**: probably a seed-cutoff or subscription-time issue. Already partly addressed in Phase 3b.

---

## Deliverable

`cowork_reports/2026-05-27_phase3c_bar_construction_results.md`:

1. Sample bar-stream entries from live (5-10 representative bars)
2. Sample bar-stream entries from sim (same bars)
3. Diff table classifying divergences by category
4. **Verdict**: fixable bug (and what the fix is) OR timing-edge-case (and what Path A Option 3 would cost)
5. Recommendation: ship the fix if fixable, OR scope Path A Option 3 directive if not.

---

## Time budget

- Bar-stream log instrumentation: ~30 min (live + sim)
- Smoke test that the log fires correctly: ~15 min
- Run live with logging on for one trading day: ~6.5 hours wall-clock if waiting for tomorrow, OR run sim against today's tick cache with the bar-stream output for a controlled comparison: ~15 min (cleaner option — both paths processing the same cache)
- Diff + categorize: ~60 min
- Write up: ~30 min

**Recommended approach**: do the controlled comparison first (both paths against today's tick cache, instrumented). If that reveals the gap, great. If both paths produce identical bars from the same cache, then the divergence is from the cache itself not matching live's real-time stream → confirms Path A Option 3 territory.

Target: full investigation + deliverable within 3 hours of CC time.

---

## What this directive does NOT include

- **No fix code yet**. Investigation deliverable comes first. If fix is straightforward, a follow-up directive scopes it.
- **No live behavior change**. Bar-stream log is purely additive and env-gated off by default.
- **No Phase 4 refactor**. Still blocked on harness validation per CC's recommendation.

---

## Open questions for results review

1. **If the divergence is bar-boundary timing (sub-second)**: is Path A Option 3 (record live bar-stream) the right call, or is there a middle option — e.g., sim could replay ticks WITH explicit tick-arrival simulation that mimics live's bar-builder state machine?
2. **If the divergence is OHLCV-on-matched-boundaries**: cheapest possible fix. Need to identify which path is computing OHLCV wrong.
3. **If sim is missing ticks the cache should have**: separate issue — investigate how tick cache reads in `simulate_subbot.py` may be filtering or deduplicating.
