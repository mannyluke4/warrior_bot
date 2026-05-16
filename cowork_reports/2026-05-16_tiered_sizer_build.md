# TieredSizer Build Report — Wave 4 Phase C1

**Date:** 2026-05-16
**Branch:** `v2-ibkr-migration`
**Directive:** `DIRECTIVE_2026-05-17_GO_FOR_BUILD.md` §Phase C
**Sub-spec:** `DIRECTIVE_2026-05-17_SIZING_SCHEDULE.md` (9-tier ladder)
**Status:** SHIPPED — all unit + integration tests green

---

## 1. Implementation overview

This delivery completes Phase C1 of the Go-For-Build directive: the
`TieredSizer` class, its YAML config, persistence layer, override flags,
and the wiring into `backtest/portfolio_backtest.py`. Production code
(`bot_v3_hybrid.py`, `squeeze_detector_v2.py`, `wb_persistence.py`, etc.)
is untouched — every change lives under `framework/`, `backtest/`, or
`tests/`.

### Files touched

| File | Type | Purpose |
|---|---|---|
| `framework/sizing_tiers.yaml` | NEW | 9-tier ladder + advancement/retreat config |
| `framework/sizing.py` | EXTEND | `TieredSizer`, `TierState`, `SizerProtocol` added alongside existing `HalfKellySizer` |
| `tests/framework/test_tiered_sizer.py` | NEW | 20 unit tests covering gates, retreats, overrides, persistence |
| `tests/backtest/test_tiered_sizer_integration.py` | NEW | 7 integration tests through `SizingMode.tiered()` |
| `backtest/portfolio_backtest.py` | EXTEND | `SizingMode.tiered()` factory, env-var CLI, per-session `on_session_close` hook |

The existing `HalfKellySizer` was left bit-identical (it still has the
6-7× under-sizing bug noted in `SIZING_SCHEDULE.md` §1 — that fix is
Wave 5 P1 work, explicitly out of scope for Phase C1).

### Design choices worth highlighting

**Tier state is session-boundary, not per-bar.** Tier transitions
happen exactly once per session in `on_session_close`. This means a
single trading day sees one consistent `risk_per_signal` across all of
that day's trades, even if equity surges through a tier floor
mid-session. No tier double-step within one session.

**Retreat triggers fire before advancement.** When both an advancement
and a retreat would technically qualify on the same session close, the
retreat wins. This is the conservative-safety read of `SIZING_SCHEDULE
§3` ("retreat triggers fire regardless of equity") — the bot will pull
back before it pushes forward.

**`tier_lock=True` and `auto_advance=False` are orthogonal.** Both
suppress *automatic* mutation. Difference:
- `tier_lock=True` is the iron lock — even `apply_pending_transition()`
  is a no-op. Used for Wave 4 paper's 60-day Tier-1 freeze (Decision 7).
- `auto_advance=False` is the operator-in-the-loop knob — the sizer
  computes & stages a `pending_transition` but waits for a manual
  `apply_pending_transition()` call. Used as the bridge between
  paper-lock and full automation post-real-money cutover.

If both are set, `tier_lock` wins (it suppresses the manual apply too).

**Tier HWM resets on every transition.** After advancement OR retreat,
the `tier_high_water_mark` resets to 0 and re-anchors on the next
session close. Without this, a retreat would inherit the previous
tier's higher HWM, and the next retreat trigger would need equity to
drop another 15% from *that* peak before firing — meaning each tier
gets one shot at protection per career. With reset, every tier has
fresh DD protection from its own entry equity onwards.

---

## 2. State persistence schema

`framework_state/tier_state.json` is written atomically (tmp + rename)
on every `on_session_close`. The schema:

```json
{
  "current_tier": 2,
  "tier_high_water_mark": 43250.0,
  "days_in_tier": 4,
  "last_advancement_date": "2026-06-08",
  "consecutive_at_next_floor": 0,
  "consecutive_losing_weeks": 0,
  "equity_history": [25000.0, 26120.0, ..., 43250.0],
  "weekly_pnl": [-120.0, 540.0, 1320.0],
  "current_iso_week": "2026-W24",
  "current_week_pnl": 850.0,
  "current_tier_entry_equity": 42000.0
}
```

Field-by-field:

- **current_tier** — integer 1-9, the active tier
- **tier_high_water_mark** — peak equity observed *while in the current tier*
  (resets on every transition)
- **days_in_tier** — session count since the last transition; informational
- **last_advancement_date** — ISO date of the most recent advancement
  (used by Gate 4 — the 14-day window)
- **consecutive_at_next_floor** — session count of consecutive closes at
  or above the next tier's equity floor (Gate 1)
- **consecutive_losing_weeks** — ISO-week count of consecutive losing weeks
  (Retreat trigger C)
- **equity_history** — trailing 120 session-close equities; the
  drawdown-window Gate 3 reads the last 5
- **weekly_pnl** — last 12 closed ISO-week net P&Ls
- **current_iso_week** — bucket key for the in-flight week
- **current_week_pnl** — running P&L for the in-flight week
- **current_tier_entry_equity** — equity at the moment we entered the
  current tier (used for forensic / reporting; HWM reset uses this seed
  on the first close after transition)

Persistence uses tmp-file-then-rename for crash safety. A corrupt or
missing state file falls back to seeding fresh from `initial_tier`
(warning logged). No silent data loss; the worst case is one session of
context evaporating after a disk corruption event.

---

## 3. Advancement/retreat rule edge cases

### Edge case A — Equity straddles a tier threshold mid-session

The sizer evaluates gates at session close, using the **closing
equity** (single-point read of `portfolio_equity` from
`portfolio_backtest.py`'s accounting). Intra-session prints above the
next-tier floor don't count. Gate 1 (consecutive sessions at floor) is
a session-count, not a tick-count.

Justification: a stock spiking through $40K mid-session and dropping
back below $40K by close should not count as "at the floor" — that's
the lottery-ticket-tier-jump anti-pattern called out in `SIZING_SCHEDULE
§3` Gate 4 rationale.

### Edge case B — A trade locks +$10K mid-day at Tier 2, then loses it back

The sizer treats end-of-day equity as canonical. Intra-day P&L
fluctuations are invisible to the sizer. This is fine because tier
transitions are at session boundaries anyway — even if mid-day P&L hit
Tier 3 levels for 90 minutes, the sizer's view of the session is one
single equity mark at close.

### Edge case C — Retreat fires same session as advancement would have

Retreat wins. The flow in `on_session_close`:
1. Update bookkeeping (history, HWM, weekly buckets)
2. Evaluate advancement
3. Evaluate retreat
4. If retreat fired → apply retreat, skip advancement
5. Else if advancement gates passed → apply advancement

So a session where equity is both above next-tier floor AND retreat
triggers fire (e.g. low rolling Sharpe but equity high) retreats. This
matches the conservative safety read.

### Edge case D — Already at top tier (Tier 9)

`_evaluate_advancement` short-circuits: returns
`gates_passed=False` with `reason="already_top_tier"`. The sizer
quietly stays at Tier 9; no error. Retreat triggers still evaluate
normally — Tier 9 can retreat to Tier 8.

### Edge case E — Already at bottom tier (Tier 1) with retreat triggers firing

`_evaluate_retreat` short-circuits: `fired=False`,
`reason="already_bottom_tier"`. State stays at Tier 1. This is the
Wave-4 paper behavior under stress — even if Sharpe craters,
`tier_lock=True` keeps us at Tier 1 *and* the underlying engine
wouldn't have moved us anyway.

### Edge case F — `tier_lock=True` AND `auto_advance=False` AND a gate fires

The transition is staged in `pending_transition` (one slot, last-write-
wins) but `apply_pending_transition()` is a no-op due to `tier_lock`.
This is benign — the staged transition is purely informational; reports
can read `last_gate_eval` to see what would have happened.

### Edge case G — Rolling Sharpe with < 30 sessions of history

Naive Sharpe returns `None` when:
- fewer than 2 returns supplied
- stdev = 0 (degenerate)

For advancement (Gate 2): `None` → gate fails (conservative — don't
advance on insufficient data).

For retreat (Trigger B): `None` → trigger does NOT fire (conservative —
don't punish a young account for thin history). Trigger B explicitly
requires the full 30-session window to be filled.

### Edge case H — ISO-week boundary at a Friday close

The `_update_weekly_pnl` helper buckets P&L by `date.isocalendar()`
year-week. Friday close finishes that ISO week; Monday open starts a
new bucket. If a week's net P&L is < 0 at the moment of bucket-rollover,
`consecutive_losing_weeks` increments. A net-zero week (rare, but
possible with one trade flat) resets the counter — only strictly
negative weeks count as losing.

### Edge case I — Backtest replay vs. live state file

A backtest run that mutates `framework_state/tier_state.json` will
contaminate the live tier state. **Mitigation:** the env var
`WB_TIER_STATE_PATH` allows the engine to redirect persistence to a
per-run path (e.g.
`backtest_archive/wave3_portfolio/tier_state_combined.json`). Live runs
omit the env var and use the default `framework_state/tier_state.json`.
The Wave 4 paper deployment script will need to set this explicitly to
keep paper state segregated from any future real-money state.

### Edge case J — Equity is None / NaN / negative at session close

`on_session_close` accepts the value and rolls it into history without
mutation gates (defensive — the engine should not feed garbage).
`compute_risk` returns `0.0` on bad equity, which the engine treats as
"size 0 shares, skip the trade." No exception; the sizer never crashes.

---

## 4. Test coverage

**Total: 27 new tests, 100% pass on first green run.**

### Unit tests (`tests/framework/test_tiered_sizer.py` — 20 tests)

| Class | Tests | Coverage |
|---|---|---|
| `TestBasic` | 6 | Tier risk lookups, clamping, invalid-equity defenses, `size()` adapter |
| `TestAdvancement` | 6 | All 4 gates verified in isolation + 1→2→3 ladder traversal |
| `TestRetreat` | 4 | All 3 retreat triggers + HWM reset on transition |
| `TestOverrides` | 3 | `tier_lock=True` and `auto_advance=False` semantics |
| `TestPersistence` | 1 | State round-trips through a fresh `TieredSizer` instance |

Specific gates exercised:
- **Gate 1** (consec sessions at floor) — `test_advance_tier1_to_tier2_all_gates`
  and `test_gate1_fires_only_after_three_consecutive`
- **Gate 2** (rolling Sharpe ≥1.0) — `test_gate2_sharpe_blocks_advancement`
  uses a high-variance/low-mean returns series to drive Sharpe below 1
- **Gate 3** (no drawdown vs 5-session avg) — `test_gate3_active_drawdown_blocks`
  builds a recent peak then a dip
- **Gate 4** (14-day window) — `test_gate4_min_14_day_window` verifies
  immediate post-advance equity surge cannot trigger a second advance

Specific retreat triggers exercised:
- **Trigger A** (−15% from tier HWM) — `test_drawdown_15pct_from_hwm_retreats`
- **Trigger B** (Sharpe <0.3) — `test_low_sharpe_retreats` feeds a
  systematically losing returns series
- **Trigger C** (3 losing weeks) — `test_three_losing_weeks_retreats`
  drifts equity down across 4 ISO weeks

Override modes:
- `test_tier_lock_pins_tier_1_through_growth` grows equity through Tier 7
  levels with `tier_lock=True` and confirms the sizer never leaves Tier 1
- `test_tier_lock_apply_pending_is_blocked` confirms manual apply also no-ops
- `test_auto_advance_false_stages_transition` confirms gates fire and stage
  a pending transition; manual apply succeeds

### Integration tests (`tests/backtest/test_tiered_sizer_integration.py` — 7 tests)

| Test | What it proves |
|---|---|
| `test_tiered_factory_binds_sizer` | `SizingMode.tiered(...)` produces a bound TieredSizer |
| `test_size_returns_tier1_risk_dollars` | Engine call path returns $300 risk at Tier 1 |
| `test_size_at_tier7_yields_2500_risk` | Engine call path returns $2,500 at Tier 7 |
| `test_tier_lock_survives_through_sizing_mode` | Equity past Tier 7 floors with `tier_lock=True` → still $300 |
| `test_auto_advance_false_through_sizing_mode` | Gates fire & pending staged through SizingMode wrapper |
| `test_fixed_dollar_unchanged` | Backward compat — fixed_dollar path identical to pre-build |
| `test_half_kelly_unchanged` | Backward compat — half_kelly path identical to pre-build |

### Existing tests preserved

`tests/framework/test_sizing.py` (the 15 HalfKellySizer regression
tests) still passes 100% — the refactor preserved `HalfKellySizer`'s
public API exactly. The only change is that `HalfKellySizer` now
exposes a `compute_risk(equity)` shim to satisfy the new
`SizerProtocol` (additive, no behavioral change).

**Test count delta:** +27 (20 unit + 7 integration). Total sizing-test
count: 42 (15 legacy + 27 new). All green.

---

## 5. Integration with `portfolio_backtest`

### Public surface changes

`backtest/portfolio_backtest.py` gained:

1. **`SizingMode.tiered(initial_tier, tier_lock, auto_advance, state_path)`**
   — classmethod factory that returns a `SizingMode(name="tiered",
   tiered_sizer=<TieredSizer>)`. Use this instead of
   `SizingMode(name="tiered")` to ensure the underlying sizer is bound.

2. **`SizingMode.size(...)` extended** — when `name == "tiered"`, routes
   to `self.tiered_sizer.size(...)`. Bar-volume cap is still applied
   (parity with `fixed_dollar`).

3. **`_build_session_returns_series(...)` helper** — compresses the
   engine's `portfolio_events` into per-session returns suitable for
   the rolling-Sharpe gates.

4. **Per-session hook** — at the bottom of the `for d in sessions:`
   loop in `run_portfolio_backtest`, the engine now calls
   `cfg.sizing_mode.tiered_sizer.on_session_close(...)` when sizing
   mode is `tiered`. No-op for the other two modes.

5. **CLI env-var support** — `_cli()` reads `WB_SIZING_MODE`,
   `WB_TIER_INITIAL`, `WB_TIER_LOCK`, `WB_TIER_AUTO_ADVANCE`, and
   `WB_TIER_STATE_PATH`. The `--mode` flag defaults to whatever
   `WB_SIZING_MODE` says (falling back to `half_kelly` for backward
   compat with the existing Wave 3 portfolio sweep).

### Wave 4 deployment recipe

```bash
export WB_SIZING_MODE=tiered
export WB_TIER_INITIAL=1
export WB_TIER_LOCK=1           # 60-day Tier-1 lock per Decision 7
export WB_TIER_AUTO_ADVANCE=0   # belt-and-suspenders
export WB_TIER_STATE_PATH=framework_state/tier_state_paper.json

python backtest/portfolio_backtest.py \
    --mode tiered \
    --start 2020-01-01 --end 2024-12-31 \
    --out backtest_archive/wave4_combined_5y
```

When real-money cutover happens after the 60-day paper validation:
- Drop `WB_TIER_LOCK` (set to 0)
- Keep `WB_TIER_AUTO_ADVANCE=0` for the first 30 sessions (manual approval)
- After 30 sessions clean, set `WB_TIER_AUTO_ADVANCE=1` for full automation

### Backward compatibility

- `--mode half_kelly` and `--mode fixed_dollar` use the legacy
  `SizingMode(name=...)` constructor unchanged.
- `SizingMode(name="tiered")` with no bound sizer falls back to a
  safe $300 fixed-dollar at Tier-1 baseline (defensive — prevents an
  accidental misconfiguration from blowing up mid-backtest).
- The existing Wave 3 portfolio backtest tests
  (`test_conflict_rules.py`) drive `SizingMode(name="fixed_dollar",
  fixed_dollar_risk=1000.0)` and are unaffected by this build.
  (Note: those 3 tests currently fail on an unrelated Wave 4 Phase B1
  filter wiring — pre-existing, not introduced by this build.)

### What this doesn't do (yet)

- **Squeeze sub-bot is not on TieredSizer.** Production squeeze
  (`bot_v3_hybrid.py`) keeps its existing fixed-$300 sizing per
  Manny's `feedback_no_market_orders.md` constraints. The framework
  strategies (PDH-Fade-filtered, ORB-aligned, PDH-Breakout-F4) get
  TieredSizer; squeeze stays static. Combined-equity tier advancement
  reads the sum, but only framework strategies size off the tier.
- **No per-strategy tier offsets.** The directive intentionally
  rejected variable per-strategy risk; all 3 framework strategies use
  the same tier's `risk_per_signal`.
- **No daily report generation.** The sizer exposes `last_gate_eval`
  and `pending_transition` for daily reports to consume, but the
  report-writing job itself is Phase E1's deliverable.

---

## 6. Open questions / followups

1. **Combined-equity wiring during Phase D3.** The combined-portfolio
   backtest needs to feed *combined* squeeze + framework equity into
   `on_session_close`. Today the engine only tracks framework-side
   equity; squeeze equity needs to be merged before the tier hook fires.
   Tracked as a Phase D3 task.

2. **Sharpe annualization factor.** The rolling Sharpe uses `√252` to
   annualize. If the backtest universe ever drops below daily
   frequency (e.g. weekly resampling), this needs to be re-derived.
   Not an issue for the current daily-bar setup.

3. **Pending-transition staleness.** If the operator runs with
   `auto_advance=False` and never calls `apply_pending_transition()`,
   the staged transition gets overwritten on the next gate fire. This
   is fine for advancement (you'd want the latest gate eval) but means
   a pending retreat could be silently superseded by an advancement
   eval if conditions whipsaw. Not a real-world concern under Wave 4
   paper (where `tier_lock=True` suppresses everything), but flag for
   when `auto_advance=False` becomes the real-money default in Phase 2.

---

## 7. Acceptance check

Per directive §C2 + Acceptance criteria:

- [x] **All unit tests pass.** 20 new + 7 integration + 15 legacy = 42/42 green.
- [x] **TieredSizer integrates without breaking existing `fixed_dollar` /
      `half_kelly` paths.** Both modes regression-tested in
      `TestSizingModeBackwardCompat`.
- [x] **`tier_lock=True` mode is verifiable via a small integration test.**
      `test_tier_lock_survives_through_sizing_mode` drives equity from
      $25K to ~$345K and confirms the sizer never leaves Tier 1 / $300
      risk.

Ready for Phase C2 → Phase D pickup.
