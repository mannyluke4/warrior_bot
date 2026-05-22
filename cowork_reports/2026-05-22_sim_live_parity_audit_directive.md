# Cowork Directive: Sim-vs-Live Parity Audit

**Date**: 2026-05-22
**Branch**: `v2-ibkr-migration`
**Priority**: P0 — foundational
**Owner (proposed)**: Cowork deep research; CC will implement fixes

---

## The reckoning

On 2026-05-22, the sub-bot ran with the full validated stack we shipped yesterday (commit `b034a10` — HWM + same-bar block + stay-armed + below-arm 3%). The sub-bot took **4 MTVA trades, real Alpaca P&L = −$1,973**. Sim of the SAME symbol with the SAME config showed **+$77 / 6 trades**.

**$2,050 divergence on a single symbol, single day.**

The 11-day backtest baseline we've been using to validate every change (+$2,498) is almost certainly inflated by the same kind of optimism. Every strategy refinement decision we've made was grounded in numbers that don't match what real money will do. With the **2026-06-04 real-money go-live** approaching, this is the most important thing to fix before we trust any more backtest results.

We need a comprehensive audit of every place sim and live diverge, the dollar impact of each, and a plan to eliminate or honestly account for them.

---

## What we already know (start here)

### Concrete example (use this as your reference case)

**MTVA on 2026-05-22**, sub-bot account `PA3LXGIPGG8B`:

| | Sim | Live |
|---|---|---|
| Trade count | 6 | 4 |
| First entry | 07:25 ET ($3.90) | 10:39 ET ($3.98) |
| Net P&L | **+$77** | **−$1,973** |

Why the difference is **mostly NOT the strategy**: live and sim agree on the strategy logic. The difference is in:
- **What each one saw** (sim had pre-market history; live's sub-bot restarted at 07:57 with no history)
- **When each one acted** (sim's tick replay has zero latency; live had IBKR→main→socket→sub-bot path with 100-300ms delays)
- **How fills resolved** (sim assumes trigger→ref; live filled at limit, $0.05-$0.15 worse per share)

### Known disconnects (preliminary — your job to expand and quantify)

| # | Disconnect | Description | Our guess at $ impact |
|---|---|---|---|
| 1 | Pre-subscription context | Sub-bot starts empty on every restart; sim has 04:00→ history | LARGE — probably the biggest single item |
| 2 | Restart state loss | Watchdog crashes wipe in-memory state | High variance day-to-day |
| 3 | Fill slippage | Sim uses trigger→ref (optimistic); live fills at limit | Measured +$945 on today's 4 MTVA trades |
| 4 | Chase cap rejections | Sim has partial chase-cap (fix #21); live aborts after 3 retries | Live skips fills sim allows |
| 5 | Bot lifecycle interrupts | Two main bot watchdog crashes on 2026-05-22 alone | Lost arms during downtime |
| 6 | Tick stream timing | 0ms sim vs 100-300ms live | Triggers fire on stale prices |
| 7 | Tick cache gaps | Some symbols have multi-minute gaps (incl. 2026-05-21 PCLA truncation incident) | Affects future backtests |
| 8 | Volume baseline calc | Sim uses full cache; live computes from received ticks | Different anomaly thresholds → different fires |
| 9 | Engine socket dropped ticks | Publisher queue might overflow under heavy load | Unknown — needs measurement |

This list is **not exhaustive**. Find the ones we haven't named.

---

## What we need from you

### Phase 1: Inventory (1-2 days of research)

Find **every place** the sim and live behaviors can diverge. Don't just enumerate — quantify. For each disconnect:

- **Where it lives in code**: file:line references in `simulate.py`, `bot_v3_hybrid.py`, `move_strike_subbot.py`, `engine_publisher.py`
- **What sim does**: the literal logic path
- **What live does**: the literal logic path (or, when divergent, prove it via log evidence or a small experiment)
- **How big is the gap**: dollar impact against a known data point (e.g., MTVA 2026-05-22, the 11-day historical, the YTD set)

Deliverable: a **parity matrix** in `cowork_reports/<date>_sim_live_parity_matrix.md` — one row per disconnect, columns for the four bullets above.

### Phase 2: Validation against known data

Take the **11-day historical replay run** (`backtest_status/replay_stay_armed_gated_2026-05-07_2026-05-20.json`, the +$2,498 baseline) and re-cast it with realistic fill assumptions:
- Entry: bot's limit price (anomaly + slippage), not anomaly
- Exit: bot's sell limit price (ref − slippage), not ref

Compare to the original +$2,498. The delta is the fill-only inflation. Document it.

Then identify which of the 19 trades in that sample have an analogous LIVE trade we can compare against. Where lucky enough to have both, document the per-trade gap and attribute it to a disconnect.

Deliverable: `cowork_reports/<date>_baseline_recalibration.md` with the corrected 11-day number and per-trade attribution.

### Phase 3: Fix recommendations

For each disconnect, recommend one of:
- **FIX in code** (e.g., sub-bot seeding from tick cache → task #27 already created)
- **FIX in sim** (e.g., simulate.py uses true limit-to-limit P&L)
- **ACCOUNT for it** (acknowledge as irreducible noise, apply a haircut to backtest expectations)
- **KILL** (some disconnects may not be worth fixing relative to their cost)

Prioritize by impact-per-effort. Highest impact, lowest effort first.

Deliverable: a prioritized fix list with implementation notes that CC can pick up directly.

### Phase 4 (stretch): Continuous parity monitoring

Once disconnects are characterized: design an automated check that runs after EOD and reports the day's sim-vs-live delta per symbol. If the gap exceeds threshold X, flag it. This gives us a daily smoke test that the bots are still in agreement with our simulator, and catches new disconnects as they appear.

---

## Critical context

### File map (where to look)

- `~/warrior_bot_v2/simulate.py` — sim engine, ~5000 lines. MOVE_STRIKE branch starts ~line 3622. HWM exit logic ~line 920. Fill model: `on_signal` method and how it interacts with `--slippage`.
- `~/warrior_bot_v2/run_backtest_v2.py` — wraps simulate.py for multi-day, compounding-equity backtests. We just patched it to use `--slippage 0.07` and accept `WB_BT_STARTING_EQUITY` env var.
- `~/warrior_bot_v2/replay_live_universe.py` — 1:1 backtest tool, bounds simulation to symbols/windows the live bot actually saw (per daily logs).
- `~/warrior_bot_v2/bot_v3_hybrid.py` — main bot, has session resume + tick cache seeding logic.
- `~/warrior_bot_v2/move_strike_subbot.py` — sub-bot consumer. **Has no seeding.** Crashes wipe state.
- `~/warrior_bot_v2/engine_publisher.py` — main bot's tick broadcaster. Single-writer/multi-reader Unix socket at `/tmp/warrior_engine.sock`.
- `~/warrior_bot_v2/engine_ipc.py` — wire protocol (TickMessage, BarMessage, etc.)
- `~/warrior_bot_v2/movement_strike.py` — anomaly detector.
- `~/warrior_bot_v2/hwm_exit.py` — sub-bot's HWM exit module (sim has its own copy in simulate.py).
- `~/warrior_bot_v2/squeeze_detector.py` / `squeeze_detector_v2.py` — squeeze prime/arm logic.
- `~/warrior_bot_v2/bars.py` — `TradeBarBuilder` used by both sim and live.

### Data sources

- Live logs: `~/warrior_bot_v2/logs/<YYYY-MM-DD>_*.log` — daily.log (main bot), move_strike_subbot.log, scanner.log
- Tick cache: `~/warrior_bot_v2/tick_cache/<YYYY-MM-DD>/<SYMBOL>.json.gz`
- Backtest outputs: `~/warrior_bot_v2/backtest_status/`
- Alpaca paper accounts (read-only for analysis):
  - Main bot: `PA3VP0LB4OID`
  - Sub-bot: `PA3LXGIPGG8B`
  - Use `python -c "from alpaca.trading.client import TradingClient; ..."` with creds from `.env`

### Recent memory (read first for context)

- `[[project_alpaca_subbot]]` — sub-bot architecture
- `[[project_dynamic_exit_research_2026-05-21]]` — yesterday's exit refinement research
- `[[project_tick_cache_eod_truncation_2026-05-21]]` — PCLA cache incident
- `[[feedback_fill_optimism_disregard]]` — older note about sim fill optimism (we're rediscovering this now)
- `[[project_broker_latency_investigation]]` — earlier audit into similar fill-divergence patterns
- `[[project_session_resume_deployed]]` — main bot's seeding pattern (template for sub-bot seeding fix)

### Hard constraints (do not violate)

- **No market orders ever** — every order is a limit. (`[[feedback_no_market_orders]]`)
- **No broker-side stops** — stops are bot-internal price comparisons. (`[[feedback_no_broker_stops]]`)
- **Same-bar re-entry block stays on** — Manny's day-trading principle, not negotiable.
- **Real-money deadline: 2026-06-04** — every paper day until then is calibration data. Don't break things to chase elegance.

### Today's open tasks for CC

- #25: P0 — Fix tick-cache truncation at EOD shutdown (separate issue, parallel work)
- #26: Reconcile sub-bot internal P&L vs real Alpaca fills + audit sim fill model (overlaps with this audit)
- #27: P0 — Implement sub-bot pre-subscription tick_cache seeding
- #28: P1 — This audit

### Working agreement

- You research and write reports + recommendations
- CC implements code changes (do not push code changes from this audit)
- All deliverables in `cowork_reports/<YYYY-MM-DD>_*.md` with descriptive names
- Cite specific data points and file:line references; don't speculate when measurement is possible
- If you find anything that contradicts our prior work, surface it loudly — we've been wrong before (e.g., the X01 +$290K YTD baseline was inflated by chase-cap-free sim fills)
- Real-money trading goes live in **13 days**. Time is the binding constraint.

---

## Why this matters

Yesterday I told Manny the sub-bot's shipped config produces **+$2,498 over 10 days** in backtest. Today the same config produced **−$1,973 in a single day live**. Either the strategy got dramatically worse overnight (it didn't), or our backtest framework has been telling us a story that doesn't match reality. The truth is the latter, and we need to know exactly *which* parts are story and which are real before we move another dollar.

Anchor everything to the MTVA example. If we can't explain the $2,050 gap on a single symbol on a single day, we don't yet understand our own system.
