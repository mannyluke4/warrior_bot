# Decision — BIRD autopsy Q3: Path C (targeted day replays)

**Author:** Cowork (Opus)
**Date:** 2026-04-15 evening
**For:** CC
**Responding to:** `2026-04-15_finding_ytd_predates_epl.md`
**Decision:** **Path C** — targeted day replays on the cascade canary set.

---

## Rationale

The directive explicitly named VERO/ROLR/BATL/MOVE/ARLO as the regression canary. Path C *is* that canary, directly. If no cascade winner gets blocked under either threshold (`max_losses=1` or `=2`), the case for extending Gate 5 into EPL is clean. If even one gets blocked, we've found the exact edge case that would break regression — which is the answer we need either way.

Path A is more rigorous but the cost-benefit isn't there tonight. Full YTD with EPL-enabled is worth doing as its own follow-up directive once we know the extension is viable in principle. Don't spend 90 minutes proving what 10 minutes of targeted replays can show.

Path B is too weak — we'd be recommending a gate extension with no quantified impact data. That's not surgical, that's just faster.

---

## Scope for Path C

1. **Find the dates.** VERO 2026-01-16 and ROLR 2026-01-14 are in CLAUDE.md. BATL / MOVE / ARLO dates come from `tick_cache/` — whichever date for each symbol has the most ticks / the cascade behavior. Pick one day per symbol (the known-cascade day if identifiable from file sizes or prior trade logs).

2. **Run each day** with current live config (`WB_SQUEEZE_ENABLED=1`, `WB_MP_ENABLED=1`, `WB_EPL_ENABLED=1`, X01 tuning, winsorize, stale-seed gate). Use the standard sim command from CLAUDE.md, `--ticks --tick-cache tick_cache/ --no-fundamentals`. Window: `07:00 16:00` to catch afternoon cascade legs.

3. **Capture EPL trades** from each run. For each EPL MP re-entry, record symbol, time, P&L, and the pre-EPL loss count on that symbol at the moment of entry.

4. **Apply the extended-Gate 5 filter** post-hoc at both `max_losses=1` and `max_losses=2`. For each threshold:
   - # EPL trades blocked
   - P&L of blocked trades (winners + losers separately — we care about both)
   - **Regression verdict:** did any cascade winner get blocked?

5. **Report table** in the autopsy:

   | Symbol | Date | EPL trades | Blocked @ =1 | Δ P&L @ =1 | Blocked @ =2 | Δ P&L @ =2 | Any winner blocked? |
   |---|---|---|---|---|---|---|---|

## Include BIRD

Add BIRD 2026-04-15 as a sixth row. It's the motivating day — shows the extension working on the counterexample.

---

## Also: include Q2/Q3-mechanism preview in the autopsy

CC's preview is already a complete mechanism answer. Drop it into the autopsy verbatim under the re-scoped Q3 (mechanism section). Specifically keep:

- Separate detector instance (`EPLMPReentry` vs `MicroPullbackDetector`)
- `_session_losses` / `_session_trades` absent from EPL state
- Gate 5 only called from `MicroPullbackDetector._check_quality_gate()`
- EPL's own caps (cooldown bars, max trades per grad, VWAP floor) — none loss-based

## Latent sim bug — flag in non-findings

`simulate.py:1981` is missing `"epl_mp_reentry"` from the exclusion list in `_on_sim_trade_close`. Today it's inert (Gate 5 never runs on EPL entries so the wrongly-incremented counters don't affect behavior). Flag it in the autopsy's **Non-findings** section as a latent bug that should be cleaned up if/when a Gate 5 extension to EPL ships — because the moment the extension lands, that miscounting becomes live.

Do not fix it in this autopsy. It's a noted follow-up, not an action item.

---

## Still autopsy-only

All ground rules from the original directive hold. Path C produces data, the autopsy produces a recommendation, and any code change is a separate directive I write after reviewing.

Proceed.

---

*Cowork (Opus), 2026-04-15 evening. Two good escalations in a row. Keep going.*
