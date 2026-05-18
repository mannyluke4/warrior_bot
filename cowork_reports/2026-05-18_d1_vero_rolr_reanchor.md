# Deliverable 1 — VERO + ROLR Re-anchor on HEAD

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Commit:** `cc3e78d`
**Configuration:** X01 (RISK_PCT=0.035, DAILY_LOSS_SCALE=1)
**Replay tool:** `simulate.py --ticks --tick-cache tick_cache/`
**Parent directive:** YTD Honest Re-baseline (2026-05-18)

## TL;DR

| Symbol | Date | Window | Trades | WR | P&L | Historical CLAUDE.md target | Δ vs target |
|---|---|---|---|---|---|---|---|
| VERO | 2026-01-16 | 07:00-12:00 | 5 | 80% | **+$2,268** | +$34,479 (X01 cite, 2026-04-08) | **-$32,211 (-93%)** |
| VERO | 2026-01-16 | 04:00-20:00 | 5 | 80% | **+$2,268** | — | identical to 07-12 (no pre/post-RTH signals) |
| ROLR | 2026-01-14 | 07:00-12:00 | 10 | 60% | **+$49,775** | +$54,654 (X01 cite, 2026-04-08) | -$4,879 (-9%) |
| ROLR | 2026-01-14 | 04:00-20:00 | 11 | 64% | **+$50,602** | — | +$827 over 07-12 (one 17:13 evening trade) |

**Verdict:** VERO has drifted dramatically (-93%) from the CLAUDE.md X01 citation. ROLR has drifted modestly (-9%). VERO's drop is consistent with the X01 baseline number being a sim-fill artifact since reconciled by entry-slippage + retry, seed-staleness, and vol-winsorize work that landed in mid-April (`13d74d3` → `19671c0` window).

These numbers are EXACT matches to Thread 3's A3 control replays today (`cowork_reports/2026-05-18_april_to_may_replay_diff.md` §"Control replays"). Reproducibility confirmed.

## Run details

### Wall clock

| Replay | Duration | Log |
|---|---|---|
| VERO 2026-01-16 07:00-12:00 | ~25 s | `/tmp/d1_replay/vero_07-12.log` |
| VERO 2026-01-16 04:00-20:00 | ~32 s | `/tmp/d1_replay/vero_04-20.log` |
| ROLR 2026-01-14 07:00-12:00 | ~22 s | `/tmp/d1_replay/rolr_07-12.log` |
| ROLR 2026-01-14 04:00-20:00 | ~30 s | `/tmp/d1_replay/rolr_04-20.log` |

Run timestamps: 2026-05-18 15:52-15:54 MDT.

### Invocation

```
WB_BT_RISK_PCT=0.035 WB_BT_DAILY_LOSS_SCALE=1 \
  ./venv/bin/python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
WB_BT_RISK_PCT=0.035 WB_BT_DAILY_LOSS_SCALE=1 \
  ./venv/bin/python simulate.py VERO 2026-01-16 04:00 20:00 --ticks --tick-cache tick_cache/
WB_BT_RISK_PCT=0.035 WB_BT_DAILY_LOSS_SCALE=1 \
  ./venv/bin/python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
WB_BT_RISK_PCT=0.035 WB_BT_DAILY_LOSS_SCALE=1 \
  ./venv/bin/python simulate.py ROLR 2026-01-14 04:00 20:00 --ticks --tick-cache tick_cache/
```

(Note: this does NOT set the `simulate.py`-level env vars from the harness ENV_BASE — `WB_SQ_VOL_MULT`, `WB_SQ_MAX_ATTEMPTS`, etc. — because Manny's directive invocation explicitly omits them. The simulate.py defaults already match X01 for these knobs as of commit `13d74d3`. The directive's spec was to match A3 controls exactly; that is what we did, and the numbers reproduce.)

## VERO 2026-01-16 trade-by-trade

### 07:00-12:00 window

| # | Time | Entry | Stop | R | Score | Exit | Reason | P&L | R-mult |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 07:16 | 4.0400 | 3.9000 | 0.1400 | 8.0 | 4.0600 | sq_para_trail_exit | +$71 | +0.1R |
| 2 | 07:20 | 5.0400 | 4.9000 | 0.1400 | 5.4 | 4.9000 | sq_stop_hit | -$500 | -1.0R |
| 3 | 08:07 | 6.0400 | 5.9000 | 0.1400 | 5.8 | 6.2501 | sq_target_hit_exit_full | +$675 | +1.4R |
| 4 | 09:32 | 6.0400 | 5.9000 | 0.1400 | 10.0 | 6.4590 | sq_target_hit_exit_full | +$1,346 | +2.7R |
| 5 | 09:35 | 6.8500 | 6.7100 | 0.1400 | 11.0 | 7.0600 | sq_target_hit | +$675 | +1.3R |

Totals: 5 trades, 4W/1L, **+$2,268**, avg R +0.5, largest win +$1,346, largest loss -$500.

### 04:00-20:00 window

Identical 5 trades, **+$2,268**. No pre-market or after-hours signals fired — the morning window already captures every legitimate VERO arm.

## ROLR 2026-01-14 trade-by-trade

### 07:00-12:00 window

| # | Time | Entry | Stop | R | Score | Exit | Reason | P&L | R-mult |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 08:19 | 4.0400 | 3.9000 | 0.1400 | 11.0 | 5.2842 | sq_target_hit | +$4,359 | +8.7R |
| 2 | 08:20 | 6.0400 | 5.9000 | 0.1400 | 11.0 | 7.6600 | sq_target_hit | +$5,678 | +11.4R |
| 3 | 08:26 | 9.3300 | 9.3400 | 1.0803 | 8.0 | 13.6000 | epl_mp_time_exit(5bars) | +$22,930 | +4.0R |
| 4 | 08:34 | 14.0400 | 13.9000 | 0.1400 | 10.0 | 17.7600 | sq_target_hit | +$13,540 | +27.2R |
| 5 | 08:54 | 17.8200 | 15.1400 | 2.6600 | 7.0 | 17.3383 | bearish_engulfing_exit_full | -$1,353 | -0.2R |
| 6 | 08:59 | 17.4200 | 16.0000 | 1.4000 | 5.0 | 16.9999 | bearish_engulfing_exit_full | -$1,207 | -0.3R |
| 7 | 09:09 | 16.6200 | 15.4200 | 1.1800 | 7.0 | 16.3800 | bearish_engulfing_exit_full | -$723 | -0.2R |
| 8 | 09:15 | 16.0200 | 15.5000 | 0.5000 | 5.0 | 15.5000 | epl_mp_stop_hit | -$1,625 | -1.0R |
| 9 | 09:22 | 15.9800 | 15.3700 | 0.5900 | 7.0 | 16.2500 | topping_wicky_exit_full | +$846 | +0.5R |
| 10 | 11:27 | 17.0700 | 17.0800 | 1.5600 | 5.0 | 19.5700 | epl_mp_trail_exit(R=1.6) | +$7,330 | +1.6R |

Totals: 10 trades, 6W/4L, **+$49,775**, avg R +5.0, largest win +$22,930, largest loss -$1,625.

### 04:00-20:00 window

Trades 1-10: bit-identical to the 07-12 window above.

| # | Time | Entry | Stop | R | Score | Exit | Reason | P&L | R-mult |
|---|---|---|---|---|---|---|---|---|---|
| 11 | 17:13 | 19.0400 | 18.9000 | 0.1400 | 6.8 | 19.3900 | sq_target_hit_exit_full | +$827 | +2.2R |

Totals: 11 trades, 7W/4L, **+$50,602**.

The 17:13 ET trade is a legitimate evening squeeze entry that the 07:00-12:00 window excludes. The historical X01 +$54,654 citation likely originated from a wider window (or from a different compounding-equity batch run); this 04-20 number is the closest full-day analog and is still -$4,052 below the +$54,654 target. The 9% gap is plausibly accounted for by entry-slippage + retry tightening since X01 (entries now placed at `max($0.05, 0.5% of price)` slippage rather than the original hardcoded $0.02) — which trims the cascade's compounding tail slightly.

## Drift analysis

| Citation source | VERO | ROLR | Provenance |
|---|---|---|---|
| **HEAD (cc3e78d), 07:00-12:00** | **+$2,268** | **+$49,775** | This report |
| **HEAD (cc3e78d), 04:00-20:00** | +$2,268 | +$50,602 | This report |
| CLAUDE.md X01 standing | +$34,479 | +$54,654 | `13d74d3` 2026-04-08 |
| 2026-04-15 autopsy replay | +$35,623 | +$50,602 | `2026-04-15_autopsy_bird_chop_day.md` |
| 2026-04-14 realistic-fill (reverted) | +$18,516 | +$6,444 | `f2bc3a8` → `d82481f` |
| Memory `project_current_state.md` orphan | +$21,024 | +$53,979 | `2026-04-03_box_strategy_session.md` (never reproduced) |

**Headline:** The standing CLAUDE.md +$34,479 / +$54,654 targets are now structurally wrong. The 2026-04-15 autopsy already showed VERO drift to +$35,623; today's number is 16× smaller than that. Something material happened to VERO replay output between mid-April and today, plausibly entry-slippage retry tightening (`WB_ENTRY_SLIPPAGE_PCT=0.005` widened the entry-fill price band but also closed off cascade re-arms whose original entries were optimistic at lower slippage).

ROLR's drop is smaller (-9% from +$54,654 → +$49,775) because ROLR's cascade is dominated by a few large winners that survive any reasonable entry-slippage regime (trade #3 is +$22,930 at +4.0R — fill model has small influence on the largest legs).

## Provenance footer

- Run timestamp: 2026-05-18 15:52-15:54 MDT
- Wall-clock total: ~109 s for all four replays
- Commit SHA: `cc3e78d`
- Branch: `v2-ibkr-migration`
- Python: `./venv/bin/python` (3.12 via /opt/homebrew/Cellar)
- Tick cache: `tick_cache/2026-01-14/ROLR.json.gz`, `tick_cache/2026-01-16/VERO.json.gz` (present, not corrupt)
- Env vars set on each invocation: `WB_BT_RISK_PCT=0.035 WB_BT_DAILY_LOSS_SCALE=1`

## Artifacts

- `/tmp/d1_replay/vero_07-12.log` — full simulate.py stdout
- `/tmp/d1_replay/vero_04-20.log` — full simulate.py stdout
- `/tmp/d1_replay/rolr_07-12.log` — full simulate.py stdout
- `/tmp/d1_replay/rolr_04-20.log` — full simulate.py stdout
- This report at `cowork_reports/2026-05-18_d1_vero_rolr_reanchor.md`
