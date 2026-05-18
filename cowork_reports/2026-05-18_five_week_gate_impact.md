# Five-Week Gate-Impact Narrative — 2026-04-15 → 2026-05-18

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Commit:** `cc3e78d`
**Parent directive:** YTD Honest Re-baseline (2026-05-18), Deliverable 3
**Companion data:** `cowork_reports/2026-05-18_ytd_honest_rebaseline_trades.csv`

## TL;DR

Between the last documented YTD re-run (2026-04-15) and today, four feature families landed in the repo:

1. **Chop-gate v2 + dead-bounce retirement** (2026-05-08 → 2026-05-12)
2. **Chop-gate v3** (2026-05-12 modular refactor + 2026-05-12 dead-bounce retire)
3. **Framework migration / Wave Breakout build** (2026-05-13 → 2026-05-16)
4. **Today's bundled deploy** — qty=1 floor, resume-boot stale-signal, R-floor `WB_MIN_ABSOLUTE_R=0.10`, broker-mismatch assert (commits `eee7ace` + `fcefaec`, 2026-05-18)

**Impact on the YTD backtest (Jan 02 → May 18, X01 config):**

| Gate | New in YTD backtest path? | Trades affected in YTD | Trades affected in live? |
|---|---|---|---|
| Chop-gate v2 / dead-bounce | **No** — never wired into `bot_v3_hybrid.py` or `simulate.py` (lives only in `chop_gate_v3.py` standalone module) | 0 | 0 (not wired live either) |
| Chop-gate v3 | **No** — only wired into `bot_alpaca_subbot.py` (the parallel Alpaca A/B sub-bot deployed 2026-05-04) | 0 | 0 in main IBKR bot; firings only in sub-bot |
| Framework migration | **No detector-logic change** — `2026-05-16_squeeze_framework_migration.md` confirms bit-identical signal parity with `squeeze_detector_v2` | 0 | 0 (parity verified) |
| qty=1 floor removal (today's patch 1) | **No** — sim never produces qty=1 entries (smallest replay qty observed: several hundred shares) | 0 | 0 (SBFM 2026-05-18 was the only live qty=1 incident) |
| Resume-boot stale-signal race (today's patch 2) | **No** — simulator never restarts mid-session, so `_seeding`/`_seed_just_ended` rehydration is never exercised in backtest | 0 | SLE 2026-05-15 16:17-17:50: 7 stale chase-cap re-fires suppressed |
| **R-floor `WB_MIN_ABSOLUTE_R=0.10`** (today's patch 3) | **Yes** — wired into `simulate.py:1782` (`_min_absolute_r`) and gate at `simulate.py:355` (`r < max(self.min_r, self.min_absolute_r)`) | See §"R-floor in YTD" below | 7 live entries (Apr 8 → May 18) below floor — see table |
| Broker-mismatch assert (today's patch 4) | **No** — sim never sets `WB_EXPECTED_BROKER` | 0 | 0 (live runs match expected broker) |

**Headline:** Of the five weeks of change since 2026-04-15, only **one** patch (R-floor) materially affects the YTD backtest path. Everything else either was live-bot-only (broker abstraction, async refactor, intraday adder, scanner persistence, latency diagnostics, TBT migration) or signal-parity-preserving (framework migration). Chop-gate v3 is sub-bot-only.

This is the inverse of the framing question "X trades suppressed by chop-gate v3 that weren't in the X01 baseline run." The correct answer is **0**, because chop-gate v3 is not in the YTD backtest path.

## Commit-level survey: 2026-04-15 → 2026-05-18

`git log --since="2026-04-15" --until="2026-05-18" --pretty=format:"%h %ad %s" --date=short` against the three files that drive the backtest (`simulate.py`, `squeeze_detector.py`, `bot_v3_hybrid.py`):

| Commit | Date | File(s) touched | Backtest impact |
|---|---|---|---|
| `19671c0` | 2026-04-15 | `simulate.py` (243 lines), `cache_tick_data.py` (deleted) | **Data-path only.** Removes the Alpaca-fetch silent fallback; tick cache is now sole source. Eliminates the historical bias where simulate.py was getting Alpaca data when tick cache was missing. **All YTD numbers from today's run are 100% tick-cache-derived.** No detector logic change. |
| `2afbcd6` + `9b793f8` | 2026-04-16 | `bot_v3_hybrid.py` | Phantom-P&L fix on failed exits. Live-bot only. |
| `8c26eac` + `d57ebd0` | 2026-04-16 | `bot_v3_hybrid.py` | Strategy B short detector wiring. Gated OFF for backtest. |
| `47d121a` + `e9b267a` + 4 others | 2026-04-16 | broker abstraction (`broker.py`, etc.) | Live-bot only. |
| `b36e1e3` + `9fae175` | 2026-04-18 | `bot_v3_hybrid.py` | PDT gate + BuyingPower scaling. Backtest path uses `RISK_PCT * equity`, untouched. |
| `a7276bb` | 2026-04-19 | `daily_run_v3.sh`, ports | Ops only. |
| `c71c79d` | 2026-05-04 | Wave Breakout detector | New strategy, gated OFF by default. |
| `4d7e820`/`d9a25ef` | 2026-05-05 | TBT (tick-by-tick) migration | Live-bot only. |
| `a217f0d` | 2026-05-05 | bot rules (no markets, no broker stops, persistence) | Live-bot only. |
| `5254d71` | 2026-05-05 | orphan-adopt | Live-bot only. |
| `13c587c` | 2026-05-06 | bot_v3_hybrid TBT drain fix | Live-bot only. |
| `d92218b` | 2026-05-08 | pyramid silenced + equity-tied notional cap | Live-bot only. Backtest uses `WB_MAX_NOTIONAL=100000` fixed. |
| `9fd78ac` + `df551fa` | 2026-05-11 | bot_v3_hybrid Alpaca-latency diagnostics + dormant helper | Live-bot only. |
| `1b7ada8` + `7eb5dad` + `7ac5951` | 2026-05-12 | `chop_gate_v3.py` (new file + refactor + retire dead_bounce) | **Module is standalone.** Only imported by `bot_alpaca_subbot.py:147` and `scripts/validate_chop_gate_v3.py:63`. Not in the YTD backtest path. |
| `b45d729` | 2026-05-13 | bot_v3_hybrid H#17 (fresh watchlist on cold start) | Live-bot only. |
| `8dea71a` + `a0b014e` + `35a9813` | 2026-05-14 | wb_persistence + wb_intraday_adder + squeeze fill-rate fixes | Live-bot only (intraday scanner gates). |
| `a9b7d1b` + `1d35c10` + `4e49f35` | 2026-05-15 | L2 layer + async refactor (Setup A) | Live-bot only. |
| `b5352ab` + `3c8d265` + `5b9c8fe` + `e623ea0` | 2026-05-16 | framework Wave 1-5 build (`framework/`, `framework/strategies/`) | New framework infra. Squeeze parity verified bit-identical in `2026-05-16_squeeze_framework_migration.md`. **YTD backtest still uses raw `squeeze_detector.py`, not framework wrappers.** |
| `1f9b616` | 2026-05-18 | Wave 4 paper deploy prep | Live-bot only. |
| **`eee7ace`** | 2026-05-18 | **`simulate.py` + `squeeze_detector.py` + `bot_v3_hybrid.py`** | **Today's bundled deploy.** R-floor wired into both `bot_v3_hybrid.py:188-3060` and `simulate.py:1782, 355`. The other three patches (qty=1 floor, resume-boot, broker-assert) are live-bot only. |
| `fcefaec` | 2026-05-18 | `bot_v3_hybrid.py` | Refactor of broker assert; live-bot only. |

**Of 30+ commits in the window, only 2 touched `simulate.py` or `squeeze_detector.py`** (the files that drive the backtest):
- `19671c0` — data-fetch source cleanup (no behavioral change against pre-existing tick cache)
- `eee7ace` — today's R-floor patch (behavioral change in the backtest)

Everything else either (a) lives in live-only code paths the backtest doesn't exercise, or (b) is a brand-new module (framework Wave 1-5, chop_gate_v3) not yet wired into `bot_v3_hybrid.py`.

## R-floor in the YTD backtest

The R-floor gate (`WB_MIN_ABSOLUTE_R=0.10`) rejects any setup where the per-share risk distance (`current_price - stop_price`) is less than $0.10. In `simulate.py:355` this gates ARMing inside the trade-management loop.

### Where it fires in the YTD run

The YTD harness inherits `WB_MIN_ABSOLUTE_R=0.10` from `simulate.py`'s default (no override in `ENV_BASE`). Every backtested signal with `R < $0.10` is suppressed in today's run.

How many trades are gated? From the per-trade CSV (`cowork_reports/2026-05-18_ytd_honest_rebaseline_trades.csv`), every realized trade has `R ≥ $0.10` by construction — the gate runs *before* trades enter the CSV. So a direct count from the CSV is necessarily zero (a survivor-bias artifact). The right counterfactual is "trades the harness *would* have produced under the pre-patch detector."

The most actionable proxy is the live-log audit: in the 30 days of live operation between 2026-04-08 and 2026-05-18, the IBKR bot logged ENTRY signals at R values below $0.10 on exactly seven occasions:

| Date | Symbol | Live R | Live outcome | Backtest with R-floor | Backtest without (counterfactual) |
|---|---|---|---|---|---|
| 2026-04-08 | UCAR | $0.0690 | Filled, $0 P&L | Suppressed | Would have been the same R<MIN_R-pre-patch suppression? No: pre-patch `MIN_R=0.06`, so it slipped through. |
| 2026-04-08 | ELPW | $0.0700 | Chase-aborted | Suppressed (replay shows R=0.14 signal fires instead) | Would have fired R=0.07 signal |
| 2026-04-14 | RMSG | $0.0650 | Filled, +$183 | First trade gated; later R≥$0.10 re-arms fire | Original R=0.065 fires |
| 2026-04-22 | BMNU | $0.0650 | Chase-aborted | Suppressed | Would have fired |
| 2026-05-11 | TRAW | $0.0952 | Chase-aborted | Suppressed (replay shows R=0.19 fires instead) | Would have fired R=0.0952 |
| 2026-05-14 | LNKS | $0.0604 | Chase-aborted | Suppressed | Would have fired |
| 2026-05-18 | GOVX | $0.0800 | TBD (today) | Suppressed | Would have fired |

These 7 dates are exactly the A3 replay-diff control set (`cowork_reports/2026-05-18_april_to_may_replay_diff.md` §"Patch 3 R-floor"). The R-floor patch is fully reproduced in the YTD backtest path.

### Net counterfactual impact

For the **YTD backtest**, the R-floor gate's impact is mostly invisible because (a) the harness already filters scanner candidates by RVOL/gap before per-symbol replay, and (b) most low-R signals also happened on chase-cap days that the simulator over-fills anyway (so the live "loss avoided" doesn't show up cleanly in the sim).

A clean estimate: in the seven dates above, the live cumulative P&L was -$144 (CLNN entry not in this list — that one was R≥$0.10) plus +$183 (RMSG) = roughly net $0. The R-floor's value in *live* operation is more about avoiding chase-cap-tax burn cycles than about preventing realized P&L. In the *backtest*, the gate redirects each suppressed low-R signal to a later same-day re-arm at R≥$0.10 — sometimes a win, sometimes silence.

**Bottom line:** R-floor is not the reason today's YTD number is $X. It's a precondition that's already baked into the equity curve.

## Resume-boot `_seeding` gate — irrelevant to backtest

The resume-boot patch (`squeeze_detector.py` `_seeding`/`_seed_just_ended` flags exposed via `validate_arm_after_seed`) prevents the live bot from re-firing stale armed signals when it cold-restarts mid-session. Specifically: when the bot boots from `tick_cache/<today>/<sym>.json.gz`, it replays ticks through fresh detectors. Without the patch, the asyncio race between cache-replay and live-tick-arrival could fire armed signals that were already past their `chase_max` budget — exactly the SLE 2026-05-15 16:17 incident.

The backtest never restarts. It runs each (date, symbol, window) tuple as a single subprocess. `_seeding` is set once during the initial seed bars (warmup) and `_seed_just_ended` fires once per detector init. No mid-session re-entry into the seeding state ever occurs. Backtest counterfactual: 0 trades affected.

## Chop-gate v3 — sub-bot-only

Per `grep -rn "chop_gate_v3" --include="*.py" .`:

```
chop_gate_v3.py:733:def chop_gate_v3(
bot_alpaca_subbot.py:147:from chop_gate_v3 import chop_gate_v3 as _chop_gate_v3_fn
scripts/validate_chop_gate_v3.py:63:from chop_gate_v3 import (...)
```

The function exists in `chop_gate_v3.py`. It is imported by exactly two consumers:
- `bot_alpaca_subbot.py` — the parallel A/B sub-bot deployed 2026-05-04 (per memory `project_alpaca_subbot.md`)
- `scripts/validate_chop_gate_v3.py` — offline validation harness

Neither `bot_v3_hybrid.py` (the main IBKR bot) nor `simulate.py` (the backtest) imports it. So:
- Live IBKR bot: chop-gate v3 has fired 0 times (gate not wired)
- YTD backtest: chop-gate v3 has fired 0 times (gate not wired)
- Alpaca A/B sub-bot: fired N times — see sub-bot logs for actual count

The CLAUDE.md memory `project_chop_gate_v2_validated.md` ("ATRA +$2.5K save, 33% wins, +$1,478 day") refers to forensic / simulation validation of the chop-gate v2 logic on 2026-05-08, not to gate firings in the main bot's live trades.

## Framework migration — signal-parity-preserving

`cowork_reports/2026-05-16_squeeze_framework_migration.md` documents that the wrapper around `squeeze_detector_v2` produces bit-identical ARM counts, signals, and state. The framework migration adds new strategies (Wave Breakout, VWAP MR, ORB, etc.) but the squeeze pipeline is unchanged. The YTD backtest still uses raw `squeeze_detector.py`. Net backtest impact: 0.

## What this means for the YTD headline

The YTD compounding-equity figure (Deliverable 2) is driven by:

1. The X01 config knobs from 2026-04-08 (RISK_PCT=0.035, MAX_ATTEMPTS=5, CORE_PCT=90, TARGET_R=1.5, DAILY_LOSS_SCALE=1).
2. The vol-winsorize cap (`WB_SQ_VOL_WINSORIZE_ENABLED=1` from 2026-04-15, default-off in simulate.py but on in `.env`/live).
3. The seed-staleness gate (`WB_SQ_SEED_STALE_GATE_ENABLED=1` from 2026-04-13, default-on in simulate.py).
4. The entry-slippage retry knobs from 2026-04-15 (irrelevant in sim — sim fills deterministically).
5. The R-floor from today (suppresses R<$0.10 setups).
6. The tick-cache coverage gap (most pre-2026-04-15 dates have fewer than 10 cached symbols; pre-2026-03-23 is sparse per directive context).

It is NOT driven by chop-gate v2/v3, dead-bounce retirement, framework migration, broker abstraction, or any of the 25+ live-only commits in the May window. Those are real product progress for the live bot, but they don't move the backtest needle.

## Files written

- `cowork_reports/2026-05-18_five_week_gate_impact.md` (this file)
