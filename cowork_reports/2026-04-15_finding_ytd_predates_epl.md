# Finding — YTD state files predate EPL framework

**Author:** CC (Opus)
**Date:** 2026-04-15 evening
**For:** Cowork (Q3 YTD analysis — scope decision needed)
**Status:** Escalation — second finding before Q3 YTD runs.

---

## What I found

The existing YTD state files on disk are dated **March 25, 2026** — before the EPL framework was added. Inspection of every `ytd_v2_backtest_state*.json` confirms:

| File | Trades | Date span | `setup_type` distribution |
|---|---|---|---|
| `ytd_v2_backtest_state_BIASED.json`::config_a | 38 | 2026-01-02 → 2026-03-19 | `micro_pullback:21, squeeze:17` |
| `ytd_v2_backtest_state_baseline.json`::config_a | 28 | 2026-01-08 → 2026-03-19 | `micro_pullback:26, squeeze:2` |
| `ytd_v2_backtest_state_mp_only.json`::config_a | 27 | 2026-01-07 → 2026-03-12 | `?:27` (schema missing setup_type) |
| `ytd_v3_cuc_state.json`::config_c/d/e | 24–27 | 2026-01-08 → 2026-03-20 | no EPL |

Zero EPL trades across any file. No trade reason contains `epl_mp_*` or setup_type `epl_mp_reentry`.

## Implication for Q3 (re-scoped)

The re-scoped Q3 asks me to "isolate EPL re-entry trades across 49 days" and compute the delta from extending Gate 5 to EPL. That is impossible with the existing data — there are no EPL trades in the YTD state to isolate. The files predate the framework.

To produce the table Cowork wants, I would need to **re-run the YTD batch** with current EPL-enabled config to generate fresh data. Cached Alpaca tick data exists for ~28 days (per `cache_tick_data.py` output: "240 pairs, 34M ticks"), so the inputs are available. The run itself is the cost.

## Three paths forward

**A. Re-run the YTD batch.** Use `run_ytd_v2_profile_backtest.py` (or a focused equivalent) across the 28 cached dates with today's live config (`WB_SQUEEZE_ENABLED=1`, `WB_MP_ENABLED=1`, `WB_EPL_ENABLED=1`, X01 tuning, winsorize). Wall time probably 30–90 minutes depending on day density. Produces an authoritative dataset for Q3 parts 2–4 and for future analyses.

**B. Scope-limited Q3.** Skip the YTD extension. Deliver a three-part autopsy:
- Q1 — why BIRD didn't re-arm post-T10 (unchanged)
- Q2/Q3-mechanism — the EPL Gate 5 bypass trace (complete, report draft already drafted below)
- Q3-YTD — state that the data doesn't exist yet; propose (A) as a follow-up directive

Weakest of the three but fastest.

**C. Targeted day replays.** Re-run only the days most likely to generate EPL trades (the cascading stocks CLAUDE.md names: VERO 2026-01-16, ROLR 2026-01-14, BATL, MOVE, ARLO — find dates). Faster than full YTD (~5 dates, ~10 minutes). Gives a directional answer without the full batch. Regression canary (VERO/ROLR) is directly covered.

## CC's recommendation

**C** is the best fit for the directive's intent. The directive specifically names VERO/ROLR/BATL/MOVE/ARLO as the regression canary, and those are a small, high-signal subset. Under C I can:
1. Replay each day with current config, capture EPL trades
2. Apply the extended-Gate 5 filter at `max_losses=1` and `max_losses=2`
3. Report the delta per symbol and whether any cascade winner would be blocked

If no cascade winner is blocked under either threshold, the case for extension is clean. If one is blocked, we've found the exact edge case that would break regression.

C produces a table; it just has 5 symbols instead of 49 days. Qualitatively sufficient to support the recommendation at the end of the autopsy.

**A** is more rigorous but expensive. I'd do it if Cowork wants the full YTD number; otherwise C.

**B** is the escape hatch if you want the autopsy shipped tonight and the YTD question deferred to a follow-up directive.

---

## Q2 / Q3-mechanism finding (preview, complete)

The Explore agent's trace answered the mechanism question in full. Short summary:

- EPL MP re-entry uses a **separate detector instance** (`EPLMPReentry` in `epl_mp_reentry.py:60–77`), not `MicroPullbackDetector`.
- `EPLMPReentry._states` has no `_session_losses` / `_session_trades` (epl_mp_reentry.py:36–55).
- Gate 5 is checked **only inside** `MicroPullbackDetector._check_quality_gate()` at `micro_pullback.py:921–939`. EPL paths do not call it.
- EPL has its own caps: `EPL_MP_COOLDOWN_BARS=3`, `EPL_MAX_TRADES_PER_GRAD=3`, `EPL_MP_MAX_PULLBACK_BARS=3`, `EPL_MP_VWAP_FLOOR=1`. None of these are loss-based.
- There is also a **latent bug** at `simulate.py:1981`: `setup_type="epl_mp_reentry"` is missing from the exclusion list in `_on_sim_trade_close`, so EPL trade closes would wrongly increment standalone MP's `_session_losses` / `_session_trades`. It's inert today (the gate check never runs on EPL entries) but worth flagging for future cleanup.

Full trace (6 questions) ready to drop into the autopsy report.

---

## Ask

Pick A / B / C. I'll proceed immediately with whichever you choose. If picking A or C, I'll keep the running bot's env untouched — YTD runs are launched via simulate.py with explicit env-var prefixes, not by flipping `.env`.

---

*CC, 2026-04-15 evening. Second finding, same principle — measure twice, cut once.*
