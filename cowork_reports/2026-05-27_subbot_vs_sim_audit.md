# Audit: Sub-bot vs Sim Logic Drift (Phase 1)

**Owner:** CC
**Status:** Research-only audit, no code changes. Output is input for Cowork to build the harness-rebuild directive.
**Source request:** Manny — "do the audit so we can build a sub-bot-aligned backtest harness."
**Date:** 2026-05-27

---

## TL;DR

Sim and live sub-bot are **two parallel implementations of overlapping strategy logic**, with three sources of drift:

1. **Different code paths**. `simulate.py` is fundamentally a *main bot squeeze* backtester with MOVE_STRIKE/REGIME_SHIFT features added on top. `move_strike_subbot.py` is its own decision tree built around MOVE_STRIKE + REGIME_SHIFT + HWM. The two share SOME modules (`movement_strike.py`, `squeeze_detector_v2.py`) but DIVERGE on HWM exit logic, regime detector defaults, and the exit-decision flow ordering.
2. **Different env-var defaults**. One critical case (`WB_REGIME_SHIFT_RATIO_THRESHOLD`: live 4.0, sim 3.0) means the prior YTD backtests have been firing regime_shift on weaker signals than live ever would.
3. **Different exit-decision ordering**. Sim routes MOVE_STRIKE/REGIME_SHIFT trades through `_hwm_exit` first, but **falls through to squeeze-style tick exits** (`topping_wicky_exit_full`, BE/TW patterns) if HWM doesn't fire. Live sub-bot has NO equivalent fall-through. This is the proximate cause of yesterday's ASTC divergence (sim exited at $7.85 via topping-wicky; live rode the regime_shift to $10.00).

The audit recommends extracting a shared `sub_bot_core.py` module that both `move_strike_subbot.py` (live) and a new `simulate_subbot.py` harness import. Eliminate drift architecturally rather than chasing it by hand.

---

## What's already shared (good news)

Three modules are already shared between live sub-bot and sim:

| Module | Used by live | Used by sim | Drift risk |
|---|---|---|---|
| `movement_strike.py` (MovementStrike) | `move_strike_subbot.py:65` import | `simulate.py:2883` import | **None** — same class instance |
| `squeeze_detector_v2.py` (SqueezeDetector) | `move_strike_subbot.py:64` import | (used by sim's squeeze path) | **None** — same class |
| `bars.py` (TradeBarBuilder) | `move_strike_subbot.py:67` import | (used by sim) | **None** |

So the entry-detection layer for MOVE_STRIKE is already common code. This is the cleanest foundation to extend.

---

## What's drifted (problems)

### Drift 1 — RegimeShiftDetector: identical algorithm, divergent default

Both files implement the body-ratio detector with **line-by-line identical logic**:
- Body = `bar.high − bar.low` (range)
- Baseline = median of last `baseline_bars` abs bodies (computed BEFORE appending current bar)
- Fires when `abs_body / baseline ≥ ratio_threshold` AND green bar
- Same warmup gate, same baseline_min/body_min guards

**The divergence is in the default `ratio_threshold` env value:**

| File | `WB_REGIME_SHIFT_RATIO_THRESHOLD` default | Source location |
|---|---|---|
| `move_strike_subbot.py:321` | **4.0** | RegimeShiftDetector constructor + `MoveStrikeSubBot.__init__` |
| `simulate.py:459, 2898` | **3.0** | SimRegimeShiftDetector instantiation |

**Impact:** Today's YTD backtest commands did NOT explicitly set `WB_REGIME_SHIFT_RATIO_THRESHOLD`, so sim defaulted to 3.0 while live runs 4.0. **Sim fires regime_shift on weaker signals than live ever would.** Most of the regime_shift entries in the previous YTD backtest results would have NOT fired in live.

All other regime params match (BASELINE_BARS=5, TARGET_R=1.5, PARTIAL_PCT=0.9, REQUIRE_ARMED=1, REQUIRE_GREEN_BAR=1, RUNNER_STOP_TO_BE=1, MAX_PER_SYMBOL=1). Only ratio_threshold drifted.

**Fix path:** make sim default match live (4.0), OR have sim default to "unset → error" so backtests must explicitly choose. Best: extract the detector to a shared module so there's only one default.

### Drift 2 — HWM exit logic is parallel-implemented

Live sub-bot uses `hwm_exit.py:HWMExitConfig + evaluate()` (`move_strike_subbot.py:66` import). Sim does NOT import `hwm_exit.py` — it has its own parallel HWM implementation inside `simulate.py:_hwm_exit`.

| Feature | hwm_exit.py (live) | simulate.py (sim) | Status |
|---|---|---|---|
| `drawdown_pct` | 0.25 | 0.25 | match |
| `wide_dd_pct` | 0.50 | 0.50 | match |
| `hh_threshold` | 2 | 2 | match |
| `min_gain_pct` | 2.0 | 2.0 | match |
| `noact_minutes` | 30 | 30 | match |
| `stop_prox_pct` | 25 | 25 | match |
| `wide_gain_pct` | 0 | 0 | match |
| `wide_at_r` | (absent) | 0 | sim-only |
| `wide_trail_r` | (absent) | 2.0 | sim-only |
| `fixed_trail_r` | (absent) | 0 | sim-only |
| `vol_suppress` | (absent) | 0 | sim-only |
| `vol_suppress_mult` | (absent) | 2.0 | sim-only |
| `vwap_suppress` | (absent) | 0 | sim-only |
| `macd_suppress` | (absent) | 0 | sim-only |
| `macd_hist_threshold` | (absent) | 0 | sim-only |
| `bar_confirm_bail` | (absent) | 0 | sim-only |

**Currently no behavior divergence** — the sim-only features all default to 0/off, so they don't fire. **But any future change to either side will silently drift.** And anyone running an experimental sim with vol/vwap/macd suppression on gets results that have no live equivalent.

**Fix path:** make simulate.py import HWMExitConfig + evaluate from `hwm_exit.py` and delete its parallel implementation. Live and sim become bit-identical on the shared subset. Sim-only experimental features can move to env-gated extensions of hwm_exit.py.

### Drift 3 — Exit-decision ordering & squeeze-pattern fallthrough

This is the **structural** issue that produced yesterday's ASTC divergence.

In `simulate.py` (lines 835-849), MOVE_STRIKE / REGIME_SHIFT trades route to `_hwm_exit` first:

```python
_is_hwm_owned = (
    "[MOVE_STRIKE]" in (t.score_detail or "")
    or "[REGIME_SHIFT]" in (t.score_detail or "")
    or t.setup_type == "regime_shift"
)
if (self.move_hwm_exit_enabled
        and (t.setup_type == "squeeze" or t.setup_type == "regime_shift")
        and _is_hwm_owned):
    self._hwm_exit(t, price, time_str)
    return
```

If HWM doesn't fire AND `_hwm_exit` returns normally without an exit decision, control falls through to:
1. `bail_timer` (line 851+)
2. Squeeze tick-exit chain (BE, TW, topping-wicky patterns, gravestone, doji, MACD, EMA20, VWAP backstops, etc.)

The squeeze tick-exit chain was designed for the *squeeze main bot*. It contains 10s pattern exits like `topping_wicky_exit_full` that fire on candle-shape signals. **These exits do NOT exist in `move_strike_subbot.py`** — the live sub-bot only has HWM, stop-prox-bail, hard-stop, and target-based exits for REGIME_SHIFT.

**Yesterday's ASTC trade is the proof:**
- Sim ASTC: entry $7.18 @ 08:45, exit $7.85, reason=`topping_wicky_exit_full`, +$262
- Live V_B ASTC: entry $7.06 @ 08:46 (regime_shift), partial out at $9.70, runner at $10.00, +$1,165

Sim's regime_shift detector either didn't fire (because of Drift 1's threshold mismatch — sim's threshold of 3.0 may have fired earlier on an earlier weaker bar, putting the bot in a MOVE_STRIKE-type trade first) OR fired but was then preempted by a squeeze tick exit. Either way, the live behavior (REGIME_SHIFT target + HWM runner) was not reproduced.

**Fix path:**
- The sub-bot's exit logic should be its own self-contained module. When a trade is `setup_type == "regime_shift"` or `"move_strike"`, exits should ONLY consult that module's logic — never fall through to squeeze pattern exits.
- This requires either: (a) refactoring sim's exit flow to early-return for non-squeeze trades, or (b) extracting sub-bot exit logic to a shared module that's the authoritative source for both live and a new sim harness.

### Drift 4 — Position sizing

Both files use the same formula structure: `qty = min(qty_risk, qty_notional, max_shares)` where `qty_risk = risk_dollars / R`. But:

| Field | Live sub-bot | Sim |
|---|---|---|
| risk_dollars source | env `WB_SUBBOT_RISK_DOLLARS=1000` | constructor arg `risk_dollars=1000.0` (default) |
| max_notional | `MAX_NOTIONAL` constant (need to check value) | `max_notional=50000.0` default |
| qty step | `qty = max(1, int(qty * PROBE_SIZE_MULT))` — probe-sized | no probe step |

**Live's `PROBE_SIZE_MULT`** — need to check default value. If it's 0.5 (50% probe), live takes HALF the position sim takes for the same R. That's a meaningful position-size drift that scales every reported P&L number.

**Fix path:** verify PROBE_SIZE_MULT default, ensure sim mirrors it OR explicitly disables probe sizing (PROBE_SIZE_MULT=1.0).

### Drift 5 — Universe source (the elephant)

This is the issue Manny surfaced earlier. The current backtest harness (`replay_live_universe.py`) reads `logs/<date>_daily.log` for the per-day symbol universe. That log captures the **MAIN BOT's ACTIVE tracking** (typically 4-10 symbols at a time, the squeeze main bot's focus list).

The **sub-bot subscribes to a much broader universe** via the engine socket fanout — today saw 112 unique symbols across the session. The sub-bot's universe comes from the engine publisher, which forwards every symbol the engine is tracking (scanner-derived watchlist + in-session adds), not just main bot's narrow focus.

**Where the right data lives:**

- `scanner_results/<date>.json` — list of 156 snapshots/day at 5-min cadence, each with a candidates list (symbol + gap_pct + pm_volume + first_seen + discovery_method + float + RVOL). 81 days of coverage Jan-May.
- This is the canonical record of the live SCANNER's universe (which is the same source the engine publisher uses to decide what to track).

**Fix path:** new harness `replay_subbot_universe.py` that:
- Reads scanner_results/<date>.json for the per-day, per-snapshot symbol universe
- For each symbol, computes its discovery window from the snapshots (`first_seen_et` → last seen as candidate)
- Replays ticks through the sub-bot's logic (NOT simulate.py's squeeze-oriented logic)
- Emits trades that match live sub-bot semantics

### Drift 6 — Tick cache atomic-write race (separate but important)

Backtests against TODAY's date race with the live bot's tick-flush thread. Live writes `tick_cache/<today>/<sym>.json.gz` every 30s (per `WB_SESSION_FLUSH_SEC`). Backtest reads same files. Mid-write reads produce `EOFError: Compressed file ended before the end-of-stream marker was reached`.

Today's gate-ON backtest hit this on ASTC. The replay_live_universe harness silently swallows the error (no `subprocess.run().returncode` check), treating it as "0 trades."

**Fix path:** live's tick-flush should write to `<file>.tmp` then `os.rename()` for atomicity. Then today-date backtests become deterministic.

---

## What the audit DID NOT cover (acknowledged gaps)

1. **MovementStrike (entry detector)** — I verified it's shared via `movement_strike.py`, but did NOT line-audit its internal logic for sub-bot-specific guards (chase cap, fade-gate integration, score formula). The shared-class status makes drift unlikely, but parameters / guards in the calling site could still differ.

2. **REENTRY GREEN logic** — both files have this. I didn't line-compare the implementations. Possible drift in:
   - 30-min watch-window timing
   - Green-bar definition (close > open vs close > prior close vs etc.)
   - Quota / cycle-reset logic
   - Same-bar guard

3. **PROBE_SIZE_MULT value** — needs verification.

4. **Fade-gate (V1 VWAP, V4 BodyCV)** — env-var defaults all match, but I didn't audit the implementation logic itself for drift.

5. **Stop-prox-bail** — present in both, not line-compared.

6. **Engine-socket tick path semantics** — live consumes ticks from the engine socket (which is a published stream from main bot's IBKR subscription). Sim consumes ticks from `tick_cache/<date>/<sym>.json.gz`. Even with identical bot logic, the tick-stream characteristics may differ:
   - Engine socket: every tick the main bot saw + published
   - Tick cache: every tick the main bot's flush thread wrote to disk (subject to flush cadence, partial-write race, the broken `_resubscribe_worker` historical undercount, etc.)
   - **Implication: even a perfect sub-bot sim replay may not match live if the underlying tick stream is materially different.**

---

## Recommended architecture for the new harness (input for Cowork directive)

### Layer 1 — shared decision module

Extract sub-bot strategy logic into `sub_bot_core.py`:
- `SubPosition` (move from `move_strike_subbot.py:165`)
- `RegimeShiftDetector` (move from `move_strike_subbot.py:102`, delete sim's `SimRegimeShiftDetector`)
- Sub-bot's exit decision function: takes (position, tick, time, hwm_cfg) → returns exit_reason or None
- Sub-bot's entry decision function: takes (bar, detectors, fade_cfg) → returns entry_signal or None
- Sub-bot's REENTRY GREEN logic
- Sub-bot's chase-cap, score-formula, position-sizing

Both `move_strike_subbot.py` (live) and the new `simulate_subbot.py` (sim) import from this module.

### Layer 2 — new sim harness

`simulate_subbot.py`:
- Same CLI shape as `simulate.py` (symbol, date, start, end, --ticks --tick-cache, etc.)
- Uses ONLY the shared sub-bot decision module — no fallthrough to squeeze tick exits
- Outputs trade-line format compatible with replay harnesses

### Layer 3 — universe replay harness

`replay_subbot_universe.py`:
- Replaces `replay_live_universe.py` for sub-bot questions
- Reads `scanner_results/<date>.json` for per-snapshot universe
- For each (symbol, discovery_window) tuple, runs `simulate_subbot.py`
- Outputs day-level + trade-level reports compatible with the existing aggregation tools

### Layer 4 — validation

Run the new harness against today (2026-05-27) with each fade-gate variant config (A/B/C). Compare sim output to live broker-truth:
- Variant A (no fade) live: +$322 closed (4 trades)
- Variant B (V1 VWAP) live: +$688 closed (2 trades)
- Variant C (V4 BodyCV) live: +$396 closed (4 trades)

**Acceptance criterion:** sim and live agree within ±15% per variant on closed P&L AND match the trade count exactly. If yes, trust the harness for hypothesis testing. If not, debug before any further hypothesis work.

---

## Open questions for Cowork directive

1. **Phase ordering**: do we extract `sub_bot_core.py` first (medium-blast-radius refactor of live code) and then build `simulate_subbot.py` against it? Or stand up `simulate_subbot.py` as a duplicate of the live logic first, validate it matches live, THEN refactor live to use the shared module? Second order is safer for live code stability but creates a second drift opportunity.

2. **Engine-socket vs tick-cache tick stream**: is the harness's input the live engine socket recordings (if we ever start recording them), or just the tick cache? The latter is what we have today. Either way the audit should note this as a known divergence source separate from logic drift.

3. **Tick cache atomic-write fix**: ship as part of the harness work, or split as a separate fix? It's a 10-LOC change in `bot_v3_hybrid.py`'s tick flush — easy. Recommend bundling.

4. **Reverting the temporary REENTRY HWM gate code** in simulate.py: the gate is ~12 LOC of off-by-default code added today. Keep it for future replays, or remove now that we're building a separate sub-bot harness? Recommend keep — small footprint, low risk, useful for future replays against simulate.py if we want them.

---

## Cross-references

- `cowork_reports/2026-05-27_subbot_trade_deep_dive.md` — Day 1 sub-bot trade analysis that surfaced the hypothesis.
- `cowork_reports/2026-05-27_reentry_green_backtest_directive.md` — the gate-decision directive that ran on the divergent harness.
- `cowork_reports/2026-05-26_sub_bot_orphan_fix_directive.md` — the orphan-handling fixes that landed prior; helps explain why live data quality going forward improves.
- `feedback_sim_live_divergence_inventory_2026-05-22.md` (memory) — earlier sim/live divergence audit; the issues here extend that thread.

---

*Audit complete. Ready for Cowork to scope the directive.*
