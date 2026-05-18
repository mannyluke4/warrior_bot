# Framework Live Runner — Build Report (Wave 4 Paper Deployment)

**Date:** 2026-05-18 (build); deploy target Monday 2026-05-18 open
**Branch:** `v2-ibkr-migration`
**Author:** CC (build pass per Manny + Cowork directive)
**Status:** BUILT and DRY-RUN PASSED (11/11 new tests green; full framework
suite 530/532 green — 2 pre-existing failures in `test_universe.py`
unrelated to this work)
**Sources:** `DIRECTIVE_2026-05-18_ENGINE_FRAMEWORK_DEPLOY.md`,
`cowork_reports/2026-05-16_go_for_build_synthesis.md`, `.env.framework`,
`bot_alpaca_subbot.py` (READ-ONLY template), `force_exit.py` (READ-ONLY),
`ibkr_feed.py` (READ-ONLY pattern), `backtest/portfolio_backtest.py`

---

## 1. Architecture (text diagram)

```
┌─────────────────────────────────────────────────────────────────┐
│                       FRAMEWORK PROCESS                          │
│                                                                  │
│  IB Gateway (clientId=51) ──→ LiveDataFeed                       │
│       (5s real-time bars)         │                              │
│                                   │ on_bar_close (1m roll-up)    │
│                                   ▼                              │
│                          FrameworkRunner.handle_bar(sym, bar)    │
│                              │                                    │
│                  ┌───────────┴───────────┐                       │
│                  │                       │                       │
│                  ▼                       ▼                       │
│       _evaluate_open_trade        SignalEvaluator                │
│        (stop/target on bar)        .on_bar_close(...)            │
│              │                          │                        │
│              │                          │ list[StrategySignal]   │
│              │                          ▼                        │
│              │                  _route_signal                    │
│              │                  - per-(sym, day) lock            │
│              │                  - release_on_stop semantics      │
│              │                          │                        │
│              │                          ▼                        │
│              │                  _submit_entry                    │
│              │                  - _compute_stop_and_target       │
│              │                    (REUSED from backtest)         │
│              │                  - TieredSizer.size               │
│              │                  - LiveBroker.submit_entry        │
│              │                                                   │
│              ▼                                                   │
│       _fire_exit ──→ LiveBroker.submit_exit (SELL LIMIT)         │
│                      (releases lock if reason=='stop')           │
│                                                                  │
│  19:55 ET poll ─→ maybe_force_exit ─→ LiveBroker.force_flatten   │
│                                       (force_exit.py chain)      │
│                                                                  │
│  16:01 ET     ─→ write_daily_report                              │
│                  cowork_reports/YYYY-MM-DD_engine_framework_daily.md
│                                                                  │
│  Alpaca paper ◀── LiveBroker (limit-only)                        │
│                                                                  │
│  framework_paper_state/YYYY-MM-DD/                               │
│    marker.json, risk.json, watchlist.json,                       │
│    open_trades.json, closed_trades.json                          │
│  framework_state/tier_state.json (TieredSizer-owned)             │
└─────────────────────────────────────────────────────────────────┘
```

Process isolation:
- **clientId 51** on IB Gateway (Setup A main=1, subbot=2, framework=51)
- **Separate Alpaca paper account** keys via `.env.framework.local`
  (Manny-provisioned; framework reuses Setup B's existing paper keys
  per directive §1 update)
- **Separate state directory** `framework_paper_state/` (does NOT touch
  Setup A's `session_state/`, `session_state_alpaca/`)
- **Separate cron** can wrap `python -m framework.run_live` later

---

## 2. Module breakdown

### 2.1 `framework/run_live.py` (~860 lines)

Main executable. Argparse with `--dry-run` and `--max-iterations` (test
hook). The `FrameworkRunner` class wires:

- **Lifecycle:** `setup()` → connect broker (Alpaca) → load equity →
  connect feed (IBKR) → subscribe 36-symbol universe → seed prior-day
  bars → enter main loop.
- **Per-bar handler:** for each closed 1m bar, evaluate open trade
  (stop/target checks first), then run signal evaluator, route any new
  signal through lock/sizer/broker.
- **Lock semantics:** `lock_holder[(sym, day)]` + `lock_released_at[...]`
  copied bit-for-bit from `portfolio_backtest.py`. `release_on_stop` is
  the default per `.env.framework`.
- **Persistence:** `FrameworkPersistence` writes `marker.json`,
  `risk.json`, `watchlist.json`, `open_trades.json`, and appends
  `closed_trades.json` after every state mutation.
- **Force-exit:** `maybe_force_exit()` polls `force_exit.should_force_exit_now()`
  every loop tick. When it latches, cancels any pending entry orders
  (best-effort) and calls `LiveBroker.force_flatten` for every open
  position. Force-exit fires via SELL LIMIT chain — never MARKET.
- **Daily report:** `write_daily_report()` produces the schema specified
  in the directive (Equity start/end/HWM/LWM, per-strategy P&L, conflict
  events, tier status, force-exit events, anomalies, lock collision
  detail). Fires at 16:01 ET unless main loop has already exited.
- **Verbose logging:** every signal, every filter rejection, every
  conflict event, every tier-lock check is logged with `[FRAMEWORK]`
  prefix. The directive's "soft launch with extra-verbose logging" is
  the default; pass `--quiet` to disable.

### 2.2 `framework/live_broker.py` (~430 lines)

Alpaca exec wrapper. Limit-only.

- **`submit_entry`:** copies the squeeze stack's slippage formula
  (`max($0.05, 0.5% × price)`), 10s timeout per attempt, up to 3
  retries with cancel + reprice, max chase 2% above original ref
  (per `WB_ENTRY_MAX_CHASE_PCT`).
- **`submit_exit`:** single aggressive SELL LIMIT 0.5% below ref price
  (matches force_exit.py first-offset default). Runner re-evaluates
  stop/target on every subsequent bar and resubmits if not filled.
- **`submit_market` raises RuntimeError** — hard guard per directive §1.
- **`submit_stop` raises RuntimeError** — hard guard per directive §1.
- **`force_flatten`** delegates to `force_exit.force_exit_position()`
  which is the same code path Setup A's main bot + subbot use for end-of-
  session flatten. Honors `WB_NO_MARKET_ORDERS=1`.
- **Dry-run path:** `connect()` validates creds via `get_account()` and
  prints `DRY-RUN connect OK`. `submit_entry` / `submit_exit` /
  `force_flatten` return synthetic `OrderResult(status="dry_run")` without
  touching alpaca-py.

### 2.3 `framework/live_data_feed.py` (~310 lines)

IBKR live bar subscription. Patterns derived from `ibkr_feed.py` (READ-
ONLY) and `bot_alpaca_subbot.py`'s `connect()` + `reqHistoricalData`
seeding (READ-ONLY); neither file was modified.

- **`reqRealTimeBars(5s, TRADES)`** is the source. The `_MinuteAggregator`
  inner class rolls 5-second bars into 1-minute closes and fires a
  callback per closed minute. This gives us deterministic 1m boundaries
  that match the backtest's Databento parquet files.
- **`seed_history(symbol)`** fetches the prior trading day's RTH 1m bars
  via `reqHistoricalData(duration="2 D", barSize="1 min", useRTH=True)`.
  Prior-day bars go to `_prior_day_bars[symbol]` (PDH/PDL strategies need
  them); today-so-far bars go to the running `_history[symbol]` deque
  (240-bar cap = 4 hours of RTH).
- **`force_finalize_open_minutes()`** is the hook the runner calls at
  force-exit time so any in-progress 1m bars can be emitted before the
  flatten loop runs.

### 2.4 `framework/live_signal_engine.py` (~210 lines)

Live equivalent of `backtest/portfolio_backtest.py`'s signal-generation
loop. The critical design choice: **`SignalEvaluator` directly imports
and uses `SIGNAL_FUNCS` from `backtest.portfolio_backtest`**. No
re-implementation, no parity-drift risk. The same code path that
produced Sharpe 1.30 / 2.10 / 2.81 OOS in backtest drives live signals.

- **Dedup:** `(arm, sym, day, bar_idx)` tuple suppresses re-emission of
  the same signal across consecutive minute closes while the
  `EntrySignal.bar_idx` doesn't advance.
- **VIX gate** runs FIRST (before any SIGNAL_FUNCS call) — returns `[]`
  whenever `vix_value >= WB_VIX_SUPPRESS_THRESHOLD` (25 by default).
- **Monday skip** runs SECOND — returns `[]` on Mondays when
  `WB_FRAMEWORK_SKIP_MONDAYS=1`.
- **Wave-4 filters** run AFTER signal generation via the shared
  `framework.filters.passes_pre_entry_filters` dispatcher — same code
  path the backtest's `_signal_passes_wave4_filters` calls.

---

## 3. Reuse-vs-build decisions

| Component | Decision | Rationale |
|---|---|---|
| Signal functions (PDH-fade, ORB, PDH-breakout) | **REUSE** from `backtest.portfolio_backtest.SIGNAL_FUNCS` | Bit-identical math; same Sharpe numbers; one code path to maintain |
| Stop/target compute | **REUSE** `_compute_stop_and_target` | Composite/r_multiple/opposite_level/just_past_level/bar_low — all already implemented and tested |
| Wave-4 pre-entry filters | **REUSE** `framework.filters.passes_pre_entry_filters` | 26 unit tests already green on this dispatcher (B1 phase) |
| TieredSizer (Tier 1 lock) | **REUSE** `framework.sizing.TieredSizer` | C1 phase: 42 tests green; persists to `framework_state/tier_state.json` |
| VIX regime | **REUSE** `framework.vix_regime.VIXRegime` | Wave 1 Agent E; default-off but explicitly enabled by `.env.framework` |
| Force-exit ladder | **REUSE** `force_exit.py` (READ-ONLY) | Already shipped 2026-05-15; live in Setup A subbot + main bot; LiveBroker delegates |
| IBKR connect pattern | **BUILD** (`LiveDataFeed`) | `ibkr_feed.py` is for L2 depth, not 1m bars; ib_insync `reqRealTimeBars` patterns copied from `bot_alpaca_subbot.py` READ-ONLY |
| Alpaca exec | **BUILD** (`LiveBroker`) | `bot_alpaca_subbot.py`'s `state.broker = make_broker(...)` reads/writes shared global state we shouldn't touch; cleaner to build a slim limit-only wrapper |
| Per-(sym, day) lock + release_on_stop | **BUILD** (in `run_live.py`) | Copied semantics + variable names verbatim from `portfolio_backtest.run_portfolio_backtest`'s `lock_holder` / `lock_released_at` flow |
| Persistence layer | **BUILD** (`FrameworkPersistence`) | Schema specified by directive — small enough to inline; doesn't fit `session_state.py`'s shape |
| Daily report writer | **BUILD** | Schema specified by directive |

The primary template was **`bot_alpaca_subbot.py`** — its architecture
(IBKR data + Alpaca exec + clientId isolation + force_exit hook +
graceful shutdown) is exactly the shape we needed. Every pattern we
copied was copied as a PATTERN, not as a function call against the
original file. `bot_alpaca_subbot.py` is unmodified.

---

## 4. Test summary

`tests/framework/test_run_live.py` — 11 tests, all passing.

| Test | What it proves |
|---|---|
| `test_dry_run_does_not_submit_orders` | `--dry-run` runs full setup with broker/feed stubs; `submit_entry` and `submit_exit` are never called |
| `test_strategy_load_uses_same_yamls_as_backtest` | All 3 Wave-4 YAMLs load; each is in `SIGNAL_FUNCS` |
| `test_retired_strategies_are_skipped` | Status `retired` YAMLs (vwap_mean_reversion, round_number) are filtered out at load time |
| `test_force_exit_uses_sell_limit_not_market` | `force_flatten` chain submits `LimitOrderRequest`, never `MarketOrderRequest`; `submit_market` raises |
| `test_persistence_round_trip` | `open_trades.json` and `risk.json` round-trip; `OpenTrade.from_dict` matches written values |
| `test_vix_above_25_suppresses` | VIX=30 returns `[]` from `SignalEvaluator.on_bar_close` |
| `test_monday_entries_are_skipped` | Session date 2026-05-18 (Monday) returns `[]` |
| `test_tier_lock_keeps_risk_at_300` | 120 sessions with positive Sharpe + equity at $500K still returns `compute_risk() == 300.0` and `current_tier == 1` |
| `test_filter_dispatcher_reuses_backtest_logic` | `symbol_blacklist=[PLTR,CRM]` rejects PLTR on a non-Monday |
| `test_broker_rejects_market_and_stop_orders` | `submit_market` and `submit_stop` both raise RuntimeError |
| `test_daily_report_writes_to_cowork_reports` | `write_daily_report()` produces a file with all required schema fields |

Full framework test suite: 530/532 passing. The 2 failing tests
(`test_universe.py::TestFloatFilter::test_excludes_too_large_float`,
`test_universe.py::TestIntegration::test_full_pipeline_produces_expected_universe`)
were already failing on `main` before this build pass began — unrelated
to the runner work.

---

## 5. Pre-launch checklist verification

| Step | Status |
|---|---|
| 1. `--dry-run`: loads env, connects (verifies creds), loads YAMLs, prints READY, exits clean | ✅ Verified via smoke test — exit code 0, no orders submitted |
| 2. Normal mode: subscribes 36 symbols, seeds prior-day bars, runs main loop | ✅ Built; cannot smoke-test without IB Gateway + Alpaca live |
| 3. Setup A sacred files untouched | ✅ Zero modifications. `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, `squeeze_detector_v2.py`, `l2_signals.py`, `ibkr_feed.py`, `wb_persistence.py`, `wb_intraday_adder.py` — all unmodified |
| 4. README-level docstring in `run_live.py` | ✅ ~80 line module docstring covering OVERVIEW, ENV VARS, CLI, HARD CONSTRAINTS, ARCHITECTURE, PERSISTENCE |
| 5. Hard constraints enforced | ✅ `submit_market` raises; `submit_stop` raises; `force_flatten` uses `force_exit.py` SELL LIMIT chain; conflict_rule=release_on_stop default |
| 6. Strategy YAMLs load with the three Wave-4 names | ✅ pdh_fade_filtered, orb_aligned_300plus_monskip, pdh_breakout_f4 (vwap_mean_reversion + round_number marked retired and skipped) |
| 7. TieredSizer Tier 1 lock | ✅ `compute_risk()` returns $300 at $25K and at $500K equity |
| 8. VIX overlay enabled | ✅ Verified via dry-run output (`VIX overlay : enabled=True`) and unit test |
| 9. Monday skip enabled | ✅ Verified via dry-run output (`skip_mondays : True`) and unit test |
| 10. clientId 51 | ✅ Verified via dry-run output (`clientId : 51`) |

---

## 6. Daily report schema (what hits cowork_reports/ on Monday evening)

```markdown
# Framework Daily Report — 2026-05-18

**Equity:** start $25,000.00, end $X, HWM $Y, LWM $Z

**Per-strategy P&L:**
- PDH-PDL-Fade-Filtered: $+/-N (entries=k, stops=k, targets=k)
- ORB-Aligned-300Plus-MonSkip: $+/-N (entries=k, stops=k, targets=k)
- PDH-Breakout-F4: $+/-N (entries=k, stops=k, targets=k)

**Conflict events:** N final-blocked collisions, M release_on_stop secondaries

**Tier status:** tier=1, tier_lock=True, pending=None

**Force-exit events:** N

**Anomalies:** ...

## Lock collision detail
- TIMESTAMP SYM: blocked_strategy blocked by winning_strategy (direction=X, intended_price=Y)
```

Note: Monday's `WB_FRAMEWORK_SKIP_MONDAYS=1` means no NEW entries
Monday — so the first real per-strategy numbers will populate Tuesday
2026-05-19's report. Monday's report will likely show zero entries and
zero conflicts (which is the correct behavior; it's not a bug).

---

## 7. Known gaps / Monday-morning attention items

1. **VIX live source.** `VIXRegime.get_vix_value()` returns None
   (placeholder — Wave 4 was expected to wire a Databento source).
   The runner gracefully passes `vix_value=None` to the evaluator,
   which then skips the suppress check entirely. **Effect:** the VIX
   overlay is wired but not active until a live VIX source is
   plumbed. **Monday morning:** if VIX spikes above 25, the runner
   will NOT suppress entries. Manny call: deploy with this gap (low
   probability of an immediate VIX shock; Wave 4 is a calibration
   window anyway) OR hand-set `runner.vix_value` from cron at
   bot start.

2. **Force-exit pending-order cancel.** The maybe_force_exit cancels
   all open orders via `self.broker._client.get_orders()`. If the
   account also has unrelated orders (it shouldn't — directive §1
   says retire the old engine-bot first), they will be cancelled
   too. **Monday morning:** Verify the Alpaca paper account is
   clean before the framework launches.

3. **Reconciliation on cold restart.** Mid-session crash + restart
   will: read `open_trades.json` from disk (via
   `FrameworkPersistence.load_open_trades` — implemented but not
   wired into setup() yet). **Monday morning:** the runner currently
   re-creates `open_trades` as `{}` on every cold boot. If a crash
   happens with positions open, the runner won't auto-rehydrate —
   the operator must restart from cold AFTER calling the existing
   resume reconcile path or manually flatten. **For Monday day-one:
   this is acceptable** because Monday has no new entries; the only
   way to have an open position is if force-exit didn't flatten on
   Friday (which is impossible because the framework wasn't running
   Friday).

4. **Reconcile-on-restart hook unwired.** Same as #3 — `load_open_trades`
   exists and is tested but isn't called from `setup()`. Trivial
   1-line wire-up but I'm leaving it disabled for day-one safety
   (the directive says soft-launch, and the resume path needs its
   own validation pass before going live).

5. **VIX hysteresis (suppress 25 → re-enable 22).** The current
   evaluator only checks the suppress threshold. The "re-enable at
   22" semantics require a state machine across consecutive bars
   that I haven't implemented. **Monday effect:** if VIX crosses
   above 25, signals stop. If it then drops to 24, signals resume.
   The hysteresis exists to prevent oscillation between 24.9 and
   25.1; functionally the live runner will work but may chatter
   around the boundary. Wave 5 cleanup.

6. **Tier state persistence path.** TieredSizer state lives at
   `framework_state/tier_state.json` (the framework-wide tier state,
   NOT under `framework_paper_state/YYYY-MM-DD/`). This is intentional
   — tier state spans sessions. Monday morning: verify the file
   doesn't exist yet (so the sizer cold-starts at Tier 1) or already
   exists with `current_tier: 1` and `tier_lock: True`.

7. **Bar-level fidelity vs tick-level.** The runner consumes 5s
   real-time bars rolled into 1m closes. The backtest consumed
   Databento parquet 1m bars. There may be sub-bar fill differences
   (e.g., a stop that triggers intra-bar in live but on-bar close
   in backtest). This is the SAME fidelity gap the Setup A subbot
   has — acceptable per `feedback_use_standard_backtester` memory.

---

## 8. Files delivered

```
framework/run_live.py              ~860 lines  main runner
framework/live_broker.py           ~430 lines  Alpaca limit-only exec
framework/live_data_feed.py        ~310 lines  IBKR 1m bar feed
framework/live_signal_engine.py    ~210 lines  SignalEvaluator
tests/framework/test_run_live.py    11 tests   all green
cowork_reports/2026-05-18_framework_live_runner_build.md  (this report)
```

**Zero modifications to:**
- `bot_v3_hybrid.py`
- `bot_alpaca_subbot.py`
- engine bots
- `squeeze_detector_v2.py`
- `l2_signals.py`
- `ibkr_feed.py`
- `wb_persistence.py`
- `wb_intraday_adder.py`
- `force_exit.py`
- `backtest/portfolio_backtest.py` (imported FROM, not modified)
- existing framework modules (`registry.py`, `filters.py`, `sizing.py`,
  `vix_regime.py`)

Setup A sacred-list integrity preserved.

---

## 9. Monday-morning verification steps

Before launching the framework Monday:

1. **`git pull`** on whichever box runs the cron (Cowork directive +
   project CLAUDE.md convention).
2. **Confirm `.env.framework.local` exists** at repo root with
   `APCA_API_KEY_ID` + `APCA_API_SECRET_KEY` populated (Manny
   provisions; gitignored).
3. **Confirm `framework_state/tier_state.json`** either doesn't exist
   OR contains `{"current_tier": 1, "tier_lock": true}`.
4. **Confirm IB Gateway is running** on the cron box with port 7497
   open (or whatever `WB_IBKR_PORT` resolves to).
5. **Confirm no orphaned engine-bot processes** on the Alpaca paper
   account (directive §1 coordination note).
6. **Run the dry-run:**

   ```
   cd /Users/duffy/warrior_bot_v2
   source venv/bin/activate
   python -m framework.run_live --dry-run
   ```

   Expected: 30-second exit with `READY` block, no orders, exit code 0.

7. **Launch live** (separate process from Setup A bots):

   ```
   python -m framework.run_live > logs/framework_live_$(date +%Y%m%d).log 2>&1 &
   ```

   Logs go to `logs/`. Daily report lands in
   `cowork_reports/YYYY-MM-DD_engine_framework_daily.md` at 16:01 ET.

8. **Verify on first signal** (or by 10:00 ET if no signals fire):
   - `[FRAMEWORK]` prefix lines in log
   - `[TIER_LOCK_CHECK]` lines show `tier=1 lock=True risk_$=300.00`
   - Any `[CONFLICT]` lines have the expected lock structure

9. **End-of-day:** confirm daily report file exists and force-exit
   block fired at 19:55 ET (if any positions open — Monday has none
   per skip_mondays).

If anything's off, freeze before Tuesday — the directive's "soft launch
with extra-verbose logging" expects exactly this kind of supervision.

---

GO.
