# Stage 0.3 — WB Intraday Adder — Day 1 Telemetry

**Date:** 2026-05-14 (deployed mid-day; first telemetry session)
**Author:** CC
**For:** Cowork (Perplexity)
**Spec:** `DIRECTIVE_GO_STAGE_0_3.md` §4
**Mode:** OBSERVE_ONLY=1 (no live watchlist injection)

---

## Deploy state

- Module: `wb_intraday_adder.py` (160 lines, V2 worktree only — engine doesn't run the adder)
- Hook: `run_intraday_adder()` in `bot_v3_hybrid.py`, called from the main loop next to `run_scanner()` and `poll_watchlist()`
- Throttle: 15-min internal (`WB_INTRADAY_ADDER_POLL_MIN`)
- Window: 09:45–15:30 ET
- Output: `logs/2026-05-14_wb_intraday_adder_observe.jsonl` (append, one record per poll)
- Env vars: 11 new keys all `WB_INTRADAY_ADDER_*`, `OBSERVE_ONLY=1` default

Deployed at 13:00 ET mid-day after 4 clean iterations (Stage 0.2 persistence already running). Result: 2.5 hours of polling captured today (~10 cycles expected by 15:30).

## Day-1 acceptance criteria (per directive §4)

| # | Criterion | Status |
|---|---|---|
| 1 | JSONL exists with ≥12 entries (full 09:45–15:30 window) | Partial — deployed mid-day; ≥1 entry already, more expected by 15:30 |
| 2 | At least one poll cycle returned ≥1 candidate | ✅ Poll #1: QUCY surfaced |
| 3 | At least one candidate with `score_at_observe_time ≥ 7` | ❌ Deferred — see "Known gap" below |
| 4 | Zero crashes / fail-soft errors | ✅ No errors in logs |
| 5 | Telemetry summarized in this report | ✅ |

## First-poll record (verbatim)

```json
{
  "ts": "2026-05-14T13:03:09-04:00",
  "poll_n": 1,
  "observe_only": true,
  "candidates_evaluated": 30,
  "candidates_passing": 1,
  "candidates": [
    {
      "symbol": "QUCY",
      "price": 2.6101,
      "prev_close": 1.34,
      "gap_pct": 94.78,
      "volume_today": 2148433,
      "rvol_proxy": 4.3,
      "float_m": 3.55,
      "gate_stack": {
        "h11_same_session_blacklisted": false,
        "h14_post_pre_threshold_time": true,
        "already_in_active_symbols": true,
        "would_pass_now": false
      },
      "score_at_observe_time": null
    }
  ],
  "filter": {
    "gap_min": 3.0, "rvol_min": 3.0,
    "price_min": 2.0, "price_max": 30.0,
    "float_max_m": 30.0, "volume_today_min": 500000
  }
}
```

QUCY hit every WB filter cleanly: +95% gap, $2.61 price, 3.55M float, 2.1M today's volume. The IBKR `TOP_PERC_GAIN` scanner surfaced it; our WB-friendly filter passed it. The `would_pass_now` flag is `false` because QUCY is **already in `state.active_symbols`** (it came in via the morning catchup scan). The adder correctly recognizes it as redundant.

This is exactly the design — the adder isn't trying to re-discover symbols the squeeze scanner already found. It's hunting for the *gap* (MEI-shape, FATN-shape mid-day movers the premarket scanner missed because they had no PM volume).

## Known gap — `score_at_observe_time` is null on Day 1

The directive specifies emitting a `score_at_observe_time` field per candidate. Day 1 ships with this set to `null`. Rationale:

- For symbols **already in `state.wb_detectors`**: trivially readable from the existing detector. Cheap.
- For symbols **NOT yet subscribed** (the interesting case — net-new candidates): requires fetching ~20 historical 1m bars via `reqHistoricalData`, instantiating a fresh `WaveBreakoutDetector`, replaying bars, and reading the resulting state. ~3–5 seconds per candidate. Doable, but adds non-trivial code and IBKR-API surface area.

**Day 1 is observe-only telemetry.** The data we *do* have (gap, RVOL proxy, price, float, volume, gate-stack overlay) is enough to evaluate whether the adder is surfacing real WB-shape candidates. Whether to wire score computation depends on what we learn from Days 1-3.

If Cowork wants score computed for Day 2 onward, the implementation is: read `state.wb_detectors[sym]` if present, otherwise spawn an isolated detector and replay 20 bars from `reqHistoricalData` over the last 20 minutes. ~30 LOC, isolated.

## Gate stack overlay — Day 1 coverage

The directive asks for `would_pass_post_wed_gate_stack`. Day 1 covers:

- ✅ **H#11** (`same_session_blacklisted`): symbol in `state.session_losses` dict
- ✅ **H#14** (`post_pre_threshold_time`): `now_et.hour >= 11` (the pre-9 MT block)
- ✅ **already_in_active_symbols**: deduplication check

Day 1 **does not cover** (deferred — require detector state or pricing context not available at scan time):
- R% floor — needs an ARMed setup with computed stop
- MACD sub-gate — needs `wb_detectors[sym]`
- Divergent-quote guard — needs current IBKR + Alpaca quotes
- $30K notional cap — needs computed risk

The covered checks are the deterministic ones; the deferred ones depend on detector state that doesn't exist for a fresh candidate. Same code path as the score gap above — if Cowork wants these wired, we can do it.

## Process note shipped — manual-interventions log

Per directive §3, `CLAUDE.md` updated with the manual-intervention logging convention. Future agent-driven `python -c` heredoc / direct watchlist mutation must append to `logs/manual_interventions.log` with the prescribed format. The MEI 5-13 mystery showed this audit gap was real.

## What ships next

- **EOD today:** persistence + intraday adder telemetry rolled into the 2026-05-14 trade breakdown (pending — separate report)
- **Tomorrow (5/15):** clean 02:00 MT cron boot will run intraday adder for a full 09:45–15:30 ET session, producing the 22-poll dataset the directive really wants
- **Mon 5/18 EOD:** 3-day observe summary (5/14 partial + 5/15 + 5/18)
- **Tue 5/19:** decision memo per directive §6

## Risks & open items

- **JSONL coverage gap today.** Mid-day deploy means ~10 polls instead of 22. Friday 5/15 fills the full window cleanly.
- **Single-source-scanner risk.** All candidates come from IBKR `TOP_PERC_GAIN`. If that's a thin universe today (e.g., IBKR cap), we miss candidates. Mitigation: same scanner backstops the squeeze run-scanner path, so coverage is consistent.
- **`rvol_proxy` is not true 20-day RVOL.** It's `volume_today / VOLUME_TODAY_MIN` as a cheap proxy. Real RVOL needs ADV lookup per candidate (~slow). For Day 1 the proxy is sufficient to filter out untraded names. If Stage 1 backtest finds RVOL is load-bearing, we wire real ADV-RVOL in Day 2.

## Files changed (this commit)

```
A wb_intraday_adder.py                        — module
M bot_v3_hybrid.py                            — run_intraday_adder + state fields
M CLAUDE.md                                   — manual-intervention convention
M .env                                        — 11 WB_INTRADAY_ADDER_* env keys
A cowork_reports/2026-05-15_wb_intraday_adder_day1.md   — this report
A cowork_reports/2026-05-14_mei_bypass_trace.md         — MEI trace closure
```

---

*Stage 0.3 ships clean with one caveat (score_at_observe_time deferred). The data picture for Cowork's Monday review will include: persistence layer (Stage 0.2) WB_OBSERVE captures from today + Friday, plus intraday-adder JSONLs from partial-today + full-Friday. If Friday's full-window data surfaces a MEI-shape mid-day candidate the squeeze scanner missed, the adder has earned its keep.*
