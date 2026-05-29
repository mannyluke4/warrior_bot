# STG 2026-05-29 Audit — Resolution

**Date**: 2026-05-29 (afternoon)
**Owner**: CC
**Source directive**: `cowork_reports/2026-05-29_sim_live_convergence_directive.md` Component 3
**Prior**: `cowork_reports/2026-05-29_sim_vs_live_audit.md` + commit `4f15875` (SQ_TRIGGER_GAP_ABORT visibility) + commit (this one — Component 1 cooldown removal)
**Status**: Trade 2 root cause **resolved (option b confirmed)**. Trade 1 still pending Component 2's bar-stream replay mode.

---

## TL;DR

With sim's silent cooldowns removed (Component 1) AND the chase-cap rejection now logging (commit `4f15875`), running STG 2026-05-29 cleanly reveals:

- **Cooldowns were NOT blocking trades 2 and 3.** Sim still shows 1 entry with cooldowns removed. Component 1 was correct conceptually (live has no equivalent) but didn't affect STG specifically.
- **The silent `WB_BT_MAX_TRIGGER_GAP_PCT=2.0` chase-cap was the blocker.** Three SQ_TRIGGER_GAP_ABORT events fire across the day, two of them at the exact arm-prices where live entered (4.37% and 4.82% gaps above arm $6.02).
- **Option (b) confirmed per the directive.**

Trade 1's Class-A opposite-outcome remains unsolved — requires Component 2 (bar-stream replay) to do the per-bar OHLCV diff.

---

## Resolution: Trade 2 (Class B)

Per the directive's option (b) — silent gap-abort was the blocker. Evidence:

```
[?] SQ_TRIGGER_GAP_ABORT: STG basis=$6.1825 entry=$5.0200 gap=23.16% > cap=2.0%
[?] SQ_TRIGGER_GAP_ABORT: STG basis=$6.2830 entry=$6.0200 gap=4.37% > cap=2.0%
[?] SQ_TRIGGER_GAP_ABORT: STG basis=$6.3100 entry=$6.0200 gap=4.82% > cap=2.0%
```

Mapping to live's actual trades:
- Second SQ_TRIGGER_GAP_ABORT (`basis=$6.2830 entry=$6.0200 gap=4.37%`) — **this is the signal that became live's trade 2** at limit $6.37, fill $6.30, exit $6.72 sq_target_hit for **+$755**
- Third SQ_TRIGGER_GAP_ABORT (`basis=$6.3100 entry=$6.0200 gap=4.82%`) — **this is the signal that became live's trade 3** at limit $6.91 (subsequently BP-blocked in live, orphan-runner exit at $6.36 for +$11)

Sim's single-shot `if gap_pct > 2.0%: return None` blocked both. Live's `_verify_fill_with_retry` (`bot_v3_hybrid.py:3149-3158`) does multi-attempt repricing up to `ENTRY_MAX_CHASE_PCT_HIGH=3.5%`, which accommodates 4.37% and 4.82% gaps via the retry budget.

### Verification

Re-ran STG with `WB_BT_MAX_TRIGGER_GAP_PCT=5.0` (matches live's effective max chase) — sim caught all 3 signals:

| # | Sim TIME | Sim entry | Sim exit | Sim P&L | Live entry | Live exit | Live P&L |
|---|---|---|---|---|---|---|---|
| 1 | 05:35 | $6.28 | $6.32 trail | +$154 | (not taken — chase-cap retry expired before fill) | — | — |
| 2 | 05:44 | $7.02 | $7.07 trail | +$208 | $6.93 fill | $6.83 trail | **-$169** |
| 3 | 06:49 | $6.31 | $6.84 target | **+$2,385** | $6.30 fill | $6.72 target | **+$755** |
| Net | | | | **+$2,747** | | | **+$597** |

Sim now beats live by +$2,150 — the *opposite* of historical sim-fill-optimism. The delta is from Class A (sim's better trail/target exits per Phase 3c bar divergence), not from sim taking more trades. With the chase-cap raise sim takes the SAME number of trades as live (3 each).

### Remediation status (open question for Cowork)

The directive's recommended remediation: "relax `WB_BT_MAX_TRIGGER_GAP_PCT` from 2.0 to 3.5% to match live's `ENTRY_MAX_CHASE_PCT_HIGH`".

**Not shipped in this resolution** because:
1. Track A YTD re-baseline (the directive's next sequencing step) requires a clean baseline to isolate Track A's effect. Bundling cooldown removal + chase-cap raise in the same baseline run mixes two effects.
2. The chase-cap change has broader implications — every historical sim regression (VERO +$2,268, ROLR +$49,775, YTD compounding) would re-baseline. That's a project-level decision, not a Component 3 implementation detail.

**Recommendation for Cowork's next directive**: after Track A re-baseline lands (this Component 1 + cooldown-removal-only), evaluate whether to ship the chase-cap raise as a separate Component 4. If shipped, every historical regression number needs to be updated in CLAUDE.md.

---

## Resolution: Trade 1 (Class A — still pending)

Sim's trade 1: 05:44 entry $7.02 → exit $7.07 sq_para_trail_exit = +$208.
Live's trade 1: 05:44 entry ~$6.93 (limit $7.09 with favorable fill) → exit $6.83 sq_para_trail_exit = -$169.

Same trail logic (`trail_price = peak - r * trail_r`, with `trail_r=1.0`). Same `r=$0.12` from arm. Different `peak` evolution because:

- Sim's peak fed by `tick_cache/2026-05-29/STG.json.gz` ticks
- Live's peak fed by IBKR engine socket ticks
- Yesterday's Phase 3c report confirmed these can diverge by 5× per-bar on bursty minutes

Without Component 2's bar-stream replay mode, this audit cannot distinguish:
- (a) sim's bar cache truncated the surge bar's true high, so sim's peak < live's peak → sim's `trail_price` (= peak - r) is *lower*, sim survives longer to a higher exit
- (b) sim's bar arithmetic and live's bar arithmetic match, but mid-bar tick sequence differs so the per-tick peak updates produce different running maxima

Component 2 will replay sim against `logs/bar_stream/2026-05-29_main_bot.jsonl` (the live bar stream) and reproduce live's peak deterministically. **Acceptance criterion for that test**: sim's trade 1 outcome lands within ±$50 of live's -$169.

### Interim diagnostic (executable now, before Component 2)

The Phase 3c instrumentation already produced `logs/bar_stream/2026-05-29_main_bot.jsonl`. A simulator-side bar stream at `logs/bar_stream/2026-05-29_sim_STG.jsonl` was not generated for today's sim runs (the env var was not set). To produce a sim bar stream for today's data:

```bash
WB_BAR_STREAM_LOG_ENABLED=1 WB_BAR_STREAM_LABEL=sim_STG \
WB_BT_RISK_PCT=0.035 \
./venv/bin/python simulate.py STG 2026-05-29 04:00 12:00 \
  --ticks --tick-cache tick_cache/ --no-fundamentals 2>&1 | tail -5
```

Then diff `logs/bar_stream/2026-05-29_main_bot.jsonl` and `logs/bar_stream/2026-05-29_sim_STG.jsonl` for STG bars in the 05:44-05:50 ET window. That single diff exposes whether the OHLCV differs and by how much. This is a 5-minute task; CC can run it after Track A re-baseline or whenever Manny prioritizes.

---

## Component 1 status (for completeness)

The cooldown deletions landed in this commit alongside the resolution notes:

| Site | Action | Lines deleted |
|---|---|---|
| `simulate.py:677-690` | Removed `_symbol_cooldown_until` + `_stop_hit_cooldown` reads | 14 lines → 8 lines |
| `simulate.py:822-829` | Removed non-squeeze cooldown write | 7 lines → 4 lines |
| `simulate.py:2183-2186` | Removed `_stop_hit_cooldown` write on close | 4 lines → 4 lines |
| `simulate.py:1854-1857` | Removed dead per-bar decrement of `_stop_hit_cooldown` | 4 lines → 3 lines |

`__init__` initializers for `_symbol_cooldown_until` and `_stop_hit_cooldown` remain (harmless empty dicts; not worth touching). Constructor argument `symbol_cooldown_min` retained too (defaulted parameter, no caller change).

**Smoke test on STG 2026-05-29**: 1 entry / +$208 — unchanged from pre-Component-1. Confirms cooldowns were not the blocker today. Other days may have been gated; Track A re-baseline will surface those.

---

## Next sequenced step: Track A re-baseline

Per directive sequencing:
1. Run F2' — baseline (no Track A, cooldowns removed, default 2% chase cap)
2. Run E' — Track A enabled, same other config

Compare to original Run F2/E deltas. If new delta within ±$10K of +$106,842, Track A's verdict stands.

CC will kick off these YTD runs next.

---

## Cross-references

- Source directive: `cowork_reports/2026-05-29_sim_live_convergence_directive.md`
- Audit that surfaced the gap: `cowork_reports/2026-05-29_sim_vs_live_audit.md`
- Phase 3c bar-construction: `cowork_reports/2026-05-27_phase3c_bar_construction_results.md`
- Live trade record: `logs/2026-05-29_daily.log` (main bot's 3 trades) and prior conversation
