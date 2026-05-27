# Phase 3c Bar-Construction Investigation — Interim Results

**Owner:** CC
**Source directive:** `cowork_reports/2026-05-27_phase3c_bar_construction_investigation_directive.md`
**Status:** Instrumentation shipped. Sim-side bar stream captured today. **Live-side bar stream pending tomorrow's 02:00 MT cron** (env vars now wired into `daily_run_v3.sh`). Surprising preliminary finding documented below — full diff lands tomorrow.

---

## TL;DR

The bar-stream logger is shipped to `bars.py` (shared by all bots). Env-gated `WB_BAR_STREAM_LOG_ENABLED=1` activates it. `daily_run_v3.sh` now sets the flag for main bot (`label=main_bot`) and each sub-bot variant (`label=subbot_A/B/C`) so tomorrow's cron produces 4 parallel bar streams.

**Sim-side bar stream for ASTC 2026-05-27 captured today (282 bars).**

**Surprising preliminary finding** from comparing sim's bar stream to live's logged events:

- **Sim's 12:45 UTC (08:45 ET) ASTC bar has body = $1.77, ratio ≈ 10.4×** — **EXACTLY matches** live sub-bot's `REGIME_SHIFT_TRIGGER ASTC bar_body=$1.7700 baseline=$0.1700 ratio=10.41` at 08:46:00 ET.
- **BUT live MAIN BOT's CHART line at 08:45 ET shows body = $0.17** — completely different OHLCV for what should be the same bar.

This means: sim and live sub-bot AGREE on the bar OHLCV (the body=$1.77 evidence is compelling). But the main bot and sub-bot, running concurrently on the same day with the same `TradeBarBuilder` class, see DIFFERENT bars for the same minute. The divergence is NOT in the bar-builder code; it's in the upstream tick stream — main bot's IBKR subscription delivered different ticks than what got fanned out to the sub-bot via the engine socket.

This re-shapes the Phase 3 story: the harness's bar-builder is fine; **the tick cache (written by main bot's flush) reflects what main bot saw, which differs from what sub-bot saw**. Sim reads the cache → produces sub-bot-like bars (matches sub-bot via regime_shift body match) for SOME bars but produces different bars for others. The "different bars" cases are where sim's MovementStrike makes different arm decisions than live's sub-bot.

---

## What landed (code changes)

### `bars.py` — bar-stream logger (~50 LOC)

- New env-gated emitter `_bar_stream_emit()` writes one JSONL line per bar-close to `logs/bar_stream/<YYYY-MM-DD>_<LABEL>.jsonl`.
- Each line:
  ```json
  {
    "ts": "2026-05-27T12:45:00+00:00",
    "sym": "ASTC",
    "o": 6.04, "h": 7.80, "l": 6.03, "c": 7.18,
    "v": 1261597, "tick_count": 16590,
    "first_tick_ts": "2026-05-27T12:45:00.097-04:00",
    "last_tick_ts": "2026-05-27T12:45:59.984-04:00"
  }
  ```
- Two new instance dicts on `TradeBarBuilder`: `_bar_first_tick_ts` and `_bar_last_tick_ts` track first/last tick timestamps per in-progress bar. Updated in `on_trade()`. Negligible overhead when logger disabled (dict assignments only).
- Gated by `WB_BAR_STREAM_LOG_ENABLED` (default 0). Label via `WB_BAR_STREAM_LABEL` (default `default`).
- Exception-safe emitter — logger failure cannot affect bot behavior.

### `daily_run_v3.sh` — env wiring for tomorrow's cron

- Main bot launch: `WB_BAR_STREAM_LOG_ENABLED=1 WB_BAR_STREAM_LABEL=main_bot`
- Each sub-bot via `launch_subbot()`: `WB_BAR_STREAM_LOG_ENABLED=1 WB_BAR_STREAM_LABEL=subbot_$suffix` (so A/B/C get distinct files)

Tomorrow's bar streams will land at:
```
logs/bar_stream/2026-05-28_main_bot.jsonl
logs/bar_stream/2026-05-28_subbot_A.jsonl
logs/bar_stream/2026-05-28_subbot_B.jsonl
logs/bar_stream/2026-05-28_subbot_C.jsonl
```

---

## Sim-side bar stream captured (2026-05-27, ASTC)

Ran `simulate_subbot.py ASTC 2026-05-27 04:05 12:00` with logger enabled. Result:
- 282 ASTC bars emitted to `logs/bar_stream/2026-05-27_sim_ASTC.jsonl`
- First bar at 09:50 UTC (05:50 ET); last bar at 12:00 ET window cap
- Tick counts per bar range from 1 (sparse pre-market bars) to 16,590 (08:45 ET surge)

### The smoking-gun bar — 08:45 ET (12:45 UTC)

```
SIM:  o=6.040  h=7.800  l=6.030  c=7.180  v=1,261,597  body=1.770  ticks=16,590
                                                      ^^^^^^^^^^^
LIVE sub-bot regime_shift_trigger (08:46:00):  bar_body=$1.7700  baseline=$0.1700  ratio=10.41
                                                       ^^^^^^^^^^
```

**Sim's body = live sub-bot's body to the penny.** This is direct evidence that sim's `TradeBarBuilder` and live sub-bot's `TradeBarBuilder` produce the SAME bar for the same input — assuming they receive the same tick stream.

### The contradiction — live MAIN BOT's CHART at 08:45 ET

From `logs/2026-05-27_daily.log`:
```
[08:45 ET] ASTC CHART | O=6.02 H=6.17 L=6.00 C=6.04 V=255,089
                              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                              body = $0.17 (vs sim/sub-bot's $1.77)
```

Main bot's bar at the same minute shows:
- Volume: **255,089** (sim has 1,261,597 — **4.9× more**)
- High: **$6.17** (sim has $7.80)
- Body (H-L): **$0.17** (sim has $1.77)

**Same minute. Same `TradeBarBuilder` class. Five-fold volume difference.**

---

## What this tells us about the divergence

The bar-builder is NOT the bug. Sim's bar matches sub-bot's bar (the regime_shift trigger body proves it). The divergence is in the TICK STREAM CONTENT:

1. **Main bot's IBKR subscription** delivered ticks during the 08:45-08:46 ET window that yielded V=255,089.
2. **Sub-bot received MORE ticks** from the engine socket (which the main bot publishes) — yielding the $1.77 body the regime_shift triggered on.

That's structurally weird: if main bot publishes what it sees to the engine socket, sub-bot should see ≤ main bot's ticks, not MORE. Possibilities:

- **Engine socket buffer asynchrony**: main bot publishes ticks as they arrive; sub-bot's bar-builder accumulates them into the 08:45-08:46 bucket bucket *after* the bucket already closed on main bot's side. So sub-bot's bucket includes ticks main bot saw later.
- **Main bot's CHART line is logged BEFORE all 08:45 ticks have arrived** — bucket closes at 08:46:00, CHART line fires at that moment, but late ticks from the 08:45-08:46 window may still trickle in afterward. Both main bot's CHART line and sub-bot's regime_shift trigger fire at the same 08:46:00 moment, but they're seeing different snapshots of the bar.
- **Tier 1/Tier 2 subscription difference**: main bot's tick-by-tick stream is throttled per the IBKR API. Sub-bot via engine socket may get a fuller stream with retransmits/aggregations. (See earlier `feedback_quiet_means_broken` for context on Tier 2 sparse-data issues.)

Each of these is plausible. None of them are sim's fault. **The tick cache reflects what main bot saw and flushed**, which may have been a SUBSET of what sub-bot eventually processed via engine socket.

Until tomorrow's parallel bar streams confirm this with the sub-bot's actual bar log, this remains the strongest hypothesis.

---

## What tomorrow's data will tell us

Tomorrow's cron writes 4 bar-stream files. For each symbol that fires interesting events (regime_shift trigger, MOVE_STRIKE arm, REENTRY GREEN, fade-gate block):

1. **Compare `subbot_A.jsonl` to `subbot_B.jsonl` / `subbot_C.jsonl`** — these all consume the same engine-socket tick stream. They should produce IDENTICAL bars. Any divergence here is a bug in TradeBarBuilder state (per-instance racing) or in the engine socket fanout.

2. **Compare `subbot_A.jsonl` to `main_bot.jsonl`** — this is the main vs sub divergence we observed indirectly today. If main bot consistently sees fewer ticks per bar than sub-bot, the engine socket is somehow REPLAYING ticks the main bot missed. Investigate the engine publish + sub-bot tick processing path.

3. **Run `simulate_subbot.py` against tomorrow's tick cache** — produces `sim_subbot_ASTC.jsonl`. Diff against `subbot_A.jsonl`. If they match exactly bar-by-bar, the harness IS reproducible for any tick cache. If they differ, the diff points at the bar-builder-vs-cache-content gap.

These three diffs together exhaust the divergence space and give us a clean answer.

---

## What this means for the harness rebuild

**The Phase 3 acceptance criteria (±15% P&L, exact trade count) may be unachievable** if the tick cache fundamentally doesn't capture what sub-bot saw in real-time. In that case:

- **Path A Option 3** (record live's bar stream and replay against THAT instead of tick cache) becomes the only way to achieve true sim/live parity.
- **Path B** (accept divergence as the limit; use harness for directional research only) is more honest about what the data supports.

Tomorrow's diff is decisive. If `subbot_A.jsonl` and `main_bot.jsonl` agree bar-by-bar (i.e., main bot and sub-bot DO see the same ticks), then the divergence I observed today comes from somewhere else (timing of when CHART logs vs when bars finalize?), and Path A Option 3 might be wrong. If they disagree, Path A Option 3 is confirmed and we have a budget question for Manny.

---

## Today's deliverables (per directive §Deliverable)

1. **Sample bar-stream entries from sim**: ✓ captured (282 ASTC bars in `logs/bar_stream/2026-05-27_sim_ASTC.jsonl`)
2. **Sample bar-stream entries from live**: **pending tomorrow's cron**
3. **Diff table**: **pending tomorrow's data**
4. **Verdict**: **pending — preliminary hypothesis is "tick-stream-content gap (Path A Option 3 territory)"**, but cannot confirm without tomorrow's live data
5. **Recommendation**: **pending verdict**

---

## Open questions (for tomorrow's results review)

1. **If subbot_A and main_bot bars diverge today's-pattern-like**: are we missing a configuration knob in main bot that limits its tick subscription throughput? Tier 1 vs Tier 2 effects?

2. **If subbot_A and main_bot bars match**: then the divergence today was something else (maybe the CHART line timing issue I hypothesized). Phase 3c's bar-stream comparison isn't the right tool; need a different diagnostic.

3. **Even if Path A Option 3 is the answer**: the budget is real (~1-2 days to wire bar-stream recording into live as the persistence layer instead of tick cache). Worth coordinating with Manny before scoping the directive.

---

## Cross-references

- `cowork_reports/2026-05-27_harness_validation_phase3b.md` — the validation that surfaced the bar-construction question
- `cowork_reports/2026-05-27_subbot_vs_sim_audit.md` — Phase 1 audit
- `feedback_quiet_means_broken.md` — earlier context on Tier 2 sparse-data issues (same symptom class)

---

*Interim phase 3c report. Full diff + verdict lands after tomorrow's 02:00 MT cron produces live bar streams.*
