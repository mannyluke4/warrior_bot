# Framework Build Response — Approvals, Decisions, Wave 4 Hold

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** CC + Manny
**Sources:** All 5 wave synthesis reports + per-strategy backtests + L2 clarification
**Status:** Pre-Wave-4 prep approved. Wave 4 paper deployment awaits Manny's go.

---

## TL;DR

CC shipped the entire framework + 12 strategy variants in one overnight session. **One survivor: PDH-Fade.** Every-year-positive 2020-2024 on real Databento data, Sharpe 1.40-1.47 fixed-dollar, passes all 4 robustness gates, 9,874 trades. Phase 2 strategies all failed acceptance but produced two reusable primitives.

Three critical findings drive Wave 4 readiness:
1. **VIX > 25 universally destroys edge** across all 5 strategies (Wave 3 K synthetic + Wave 5 L real). Lock-in: VIX overlay ON for paper.
2. **HalfKellySizer is buggy** (edge/variance estimate structurally tiny on intraday noise). Ship Wave 4 paper at fixed-dollar $500 risk. Fix HalfKelly in Wave 5.
3. **Bar-level engine missing ATR trailing stop.** Winners clip at 2R when YAML calls for trailing-after-1.5R. PDH-Fade's real edge is *understated*. Subprocess Nautilus re-validation needed before paper to lock baseline.

I'm approving all pre-Wave-4 prep work. Wave 4 paper deployment itself stays on hard hold pending Manny's explicit go — the 18.8% win-rate operator psychology requires his personal sign-off, not mine.

---

## 1. Acknowledgment

CC produced ~50,000 words of report output, 17 framework modules, 12 strategy backtests, two reusable primitives, walk-forward harness, NautilusTrader subprocess runner, and a production L2 capture spec — all overnight. The build velocity validates Manny's "plan rigorously, build in parallel" framing.

More importantly: the data CC produced kills 11 of 12 strategy variants on real data. That's exactly the validation framework we built the infrastructure for. Three weeks ago we had no way to know WB had no edge. Tonight we have a winner backed by 5 years of cross-regime data, with two reusable primitives for future enhancement.

The framework is doing its job.

---

## 2. CC's 5 open questions — decisions

### Q1: Sizing fix priority — ship fixed-dollar for paper, fix Wave 5?

**Decision: Ship Wave 4 paper at fixed-dollar $500 risk. Fix HalfKellySizer in Wave 5.**

CC's recommendation is correct. The HalfKelly fix is multi-day Wave 5 work (rolling 50-trade Kelly + ADV-dollars cap + minimum position floor). Blocking Wave 4 on this delays validation data by a week with no benefit.

Wave 4 paper at fixed-dollar $500 risk gives us:
- Clean P&L signal on the strategy itself
- DD safety margin (half of $1K test value)
- A baseline to compare against Kelly-sized backtest once fixed

Wave 5 sizing fix proceeds in parallel with paper validation.

### Q2: VIX threshold calibration — run the 30-min validation?

**Decision: Yes. Run it before Wave 4 paper.**

The VIX overlay is the single biggest knob in the framework right now. Three independent confirmations (Wave 3 K synthetic, Wave 5 L real VP, Wave 5 M real AVWAP) all point at VIX > 25 being categorically destructive. The 22/25 hysteresis is K's empirical regime boundary on synthetic data — validating on real PDH-Fade data specifically is cheap insurance.

**Specific request:** Run PDH-Fade Wave 3 backtest with `WB_USE_VIX_REGIME=1`, `WB_VIX_SUPPRESS_THRESHOLD=25`, `WB_VIX_REENABLE_THRESHOLD=22`. Compare Sharpe / MaxDD / trade count / per-year P&L against the Wave 3 baseline (1.40-1.47). Save as `cowork_reports/2026-05-XX_pdh_fade_vix_validation.md`.

**Expected:** Sharpe lift to 1.7-2.0 range (per Wave 3 synthesis §3 estimate), trade count drop ~20% (1,974 fewer trades over 5 years), per-year P&L more uniform. If anything other than this pattern appears, pause and report.

### Q3: Watch-list strategies — re-evaluate post-catalyst-filter, or pull?

**Decision: Keep both on watch-list. Re-evaluate post-Wave-5 catalyst filter.**

PDH-Breakout (Sharpe 0.70-0.77) and ORB-5min (0.62-0.82) both have directional edge and pass K's robustness gates. They don't clear the Sharpe ≥ 1.2 gate on real data, but the *Zarattini ORB paper's edge is catalyst-specific* — and our backtest ran without the catalyst filter wired. Pulling them now is premature.

**Action:** Wave 5 P1 work as scheduled (catalyst-day universe filter integration). After it lands, re-run both watch-list strategies. If they clear Sharpe ≥ 1.2 with catalyst filter on, they re-enter the deployable set. If not, retire them.

Catalyst filter spec: premarket gap > 2% AND today's RVOL > 2× (per Wave 1 Agent C infrastructure).

### Q4: Subprocess Nautilus re-validation before Wave 4?

**Decision: Yes. Run before Wave 4 paper. 1.5 hours is nothing.**

Three reasons:
1. **PDH-Fade's edge is currently understated.** Bar-level engine clips winners at 2R when YAML calls for trailing-after-1.5R. Real ATR trailing should add P&L on the upside.
2. **Tick-level fidelity matters for the survivor specifically.** All other strategies failed; the only one we're betting on needs the highest-fidelity validation before paper.
3. **Locks the pre-paper baseline.** When paper data comes in, we need to compare against the most realistic backtest result, not a bar-level approximation.

**Specific request:** Run PDH-Fade through `backtest/nautilus_subprocess_runner.py` on the 36-symbol × 1,307-day Databento universe. Compare Sharpe / MaxDD / per-year P&L against bar-level Wave 3 baseline. Save as `cowork_reports/2026-05-XX_pdh_fade_nautilus_validation.md`.

**Expected:** Tick-level Sharpe should be ≥ bar-level Sharpe (trailing stop adds edge on winners). MaxDD should be similar or tighter. Per-year breakdown should remain every-year-positive.

If tick-level Sharpe falls *below* bar-level by more than 0.2, something's wrong with the trailing stop implementation — pause and investigate before paper.

### Q5: 6/15 deadline — still squeeze-bot-only?

**Decision: Yes. Confirmed. 6/15 is squeeze-bot-only. Framework / PDH-Fade is a separate track.**

The 6/15 cutover is for the existing squeeze bot using its current implementation. PDH-Fade paper validation is 60+ trading days — earliest real-money candidacy is mid-August.

The two tracks run in parallel:
- **Track 1 (existing squeeze bot):** Monday production checklist → Friday 5/22 5-day eval → 6/15 real-money cutover at current configuration
- **Track 2 (framework PDH-Fade):** Pre-Wave-4 prep this week → Wave 4 paper deployment (pending Manny's go) → 60 paper sessions → real-money decision ~August

No interaction between the tracks. No shared resources. No risk to 6/15 from Wave 4.

---

## 3. Wave 4 — held pending Manny's explicit go

This is the only decision I won't make on Manny's behalf. The reason isn't technical:

**PDH-Fade is an 18.8% win-rate strategy.** Profit factor 1.27 says wins are 5-6× larger than losses, so the math is positive. But the live psychology of running an 18.8% WR strategy is brutal. 10+ consecutive losers will happen mathematically. Operator discretionary overrides during streaks will destroy the edge.

Wave 3 synthesis §1.3 names this directly: "Wave 4 paper must measure not just P&L but operator-side discipline. If you start tweaking it after a losing streak, the edge is gone."

This is Manny's call to make. Cowork's recommendation:

**Approve Wave 4 if Manny can commit to:**
1. **Zero discretionary overrides** during the 60-day paper window unless explicitly approved by Cowork. No mid-streak tweaks, no "I think it should sit this one out," no manual closes of paper positions.
2. **Daily review limit of 5 minutes** on the strategy specifically. Look at P&L, log any concerns, move on. Avoid all-day staring at trade results which produces the override pressure.
3. **Hard kill criteria pre-committed:** Sharpe < 0.5 over rolling 30 days → halt. MaxDD > 15% → halt. >5 operator overrides → halt + post-mortem. Numbers are CC's proposal; Manny can adjust before commit.

**Defer Wave 4 if Manny doesn't want to commit to the above.** That's a valid choice. The framework + PDH-Fade survives indefinitely in paper-ready state. We can defer to August, November, or never. The 18.8% WR psychology is real and there's no shame in choosing not to run it.

**Manny: this is the decision. If you go, the deployment plan is locked. If you don't go, nothing breaks and the framework stays paper-ready.**

---

## 4. Pre-Wave-4 prep — approved (CC starts now)

CC can begin all of the following in parallel. None of these touch live production.

### 4.1 VIX validation run

PDH-Fade Wave 3 backtest replay with `WB_USE_VIX_REGIME=1`, threshold 25, hysteresis 22. Report: `cowork_reports/2026-05-XX_pdh_fade_vix_validation.md`. Per §Q2 above.

### 4.2 Subprocess Nautilus survivor validation

PDH-Fade run through `backtest/nautilus_subprocess_runner.py` for tick-level fidelity. Report: `cowork_reports/2026-05-XX_pdh_fade_nautilus_validation.md`. Per §Q4 above.

### 4.3 Wave 5 catalyst-day filter integration

Wire Wave 1 Agent C's catalyst-day filter (premarket gap > 2% AND today's RVOL > 2×) into the universe filter. This is a real Wave 5 task that unblocks watch-list re-evaluation.

After integration, re-run ORB-5min and PDH-Breakout on the catalyst universe. Reports: `cowork_reports/2026-05-XX_orb_catalyst_revalidation.md` and `cowork_reports/2026-05-XX_pdh_breakout_catalyst_revalidation.md`.

### 4.4 HalfKellySizer fix

Replace global `expected_edge / variance` with 50-trade rolling per-strategy estimate. Replace 5% bar-volume cap with 0.1% ADV-in-dollars cap. Add $500 minimum position floor.

Test by re-running PDH-Fade Wave 3 backtest under Kelly mode; expect Sharpe-equivalent to fixed-dollar + tighter DD.

Report: `cowork_reports/2026-05-XX_sizing_fix_validation.md`.

### 4.5 Production L2 capture wiring (Wave 6 prerequisite, can start now)

CC's L2 capture spec at `docs/l2_capture_spec.md` is implementation-ready. Wire into the existing IBKR data engine so we begin accumulating real L2 history immediately. This is a separate workstream that runs while everything else proceeds — by the time we want to validate L2 confirmation on real data (Wave 6), we have 4+ weeks of capture in hand.

**Critical:** L2 capture is *capture only*, not consume. Bots stay env-disabled per Saturday's clarification. The capture is for future backtest, not current decisions.

Report when wired: `cowork_reports/2026-05-XX_l2_capture_wiring.md`.

---

## 5. Production track (separate, untouched)

The existing squeeze bot continues toward 6/15 real-money cutover on its current implementation:

- **Mon 5/18:** Production checklist (dead-tape historical backfill, force-exit validation, dead_bounce enforce, squeeze N-cap, EH/PM block per forensic findings)
- **Fri 5/22:** 5-day squeeze evaluation
- **6/15:** Real-money cutover at current squeeze configuration

The framework build does not affect this track. No code changes to `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, engine bots, or any production file.

**On the L2 state question for the production track:** per CC's L2 state clarification, the architecture is correct (dedicated bg-thread, clientIds 42-45). The isSmartDepth=True bug hit on Saturday afternoon's first deploy. Code hotfix dropped isSmartDepth. Env flags are currently OFF.

**Monday smoke test:** before market open, flip the four `WB_L2_FILTER_*ENABLED` flags to `1`. Watch first ARM. If `[L2] bg-thread IB connected (... clientId=NN)` appears cleanly and verdicts log without IndexError flood, L2 is back live in observe-only mode for production. If problems → revert env to 0 and defer the live-L2 question to Wave 6 backtest framework.

The dead-tape gate stays observe-only regardless of L2 state — per Investigation 2's volume-direction inversion finding.

---

## 6. The strategic situation, named

The framework build delivered exactly what Manny asked for Saturday night: **find healthy fluctuations and capture them with bot capabilities humans can't match.**

The result is sobering:
- 12 strategy variants tested
- 1 survivor (PDH-Fade)
- All Phase 2 strategies failed acceptance
- The survivor has 18.8% win rate — psychologically grueling to run

This is the framework working correctly. **It's better to know after one weekend of backtest that 11 of 12 strategies don't have edge than to discover it in production with real money.**

The framework's value isn't just PDH-Fade. It's:
- A validated harness for testing any future strategy quickly
- Reusable primitives (VP, AVWAP, L2 confirmation) for *enhancing* PDH-Fade
- A walk-forward / robustness battery that catches curve-fitting
- A production-ready paper deployment path with kill criteria
- A documented gap between bar-level (current) and tick-level (Nautilus) backtests

Even if Manny decides not to deploy PDH-Fade to paper, the framework remains a permanent capability for evaluating future strategies — which is exactly what we'd been missing.

---

## 7. Reports CC owes

| When | Report | Status |
|---|---|---|
| Pre-Wave-4 (this week) | `pdh_fade_vix_validation.md` | new |
| Pre-Wave-4 (this week) | `pdh_fade_nautilus_validation.md` | new |
| Wave 5 catalyst filter (this week) | `orb_catalyst_revalidation.md` + `pdh_breakout_catalyst_revalidation.md` | new |
| Wave 5 sizing fix (this week) | `sizing_fix_validation.md` | new |
| L2 capture wiring | `l2_capture_wiring.md` | new |
| Mon EOD 5/18 (production track) | Daily breakdown with production sections | per existing |
| Mon AM 5/18 (production track) | Dead-tape historical backfill | per existing |
| Fri 5/22 (production track) | 5-day squeeze evaluation | per existing |
| Wave 4 paper deployment | **PENDING MANNY GO** | hard-stopped |

---

## 8. Tone

CC did extraordinary work overnight. The data CC produced is honest about both wins (PDH-Fade as real survivor) and limitations (Phase 2 didn't add a strategy, sizing has a bug, ATR trailing missing). That honesty is what makes the framework trustworthy.

The Wave 4 decision is now in Manny's hands. Either path is valid. The framework is paper-ready, the survivor is identified, the bugs are documented, the L2 path is wired. Nothing breaks if Manny chooses to defer.

Pre-Wave-4 prep proceeds in parallel with the existing squeeze production track. CC starts the four work items in §4 now. By the time Manny decides on Wave 4, the prep work is complete and we have higher-fidelity numbers to inform that decision.

---

## 9. Files referenced

- `cowork_reports/2026-05-16_wave3_synthesis.md` — survivor identification
- `cowork_reports/2026-05-16_wave5_synthesis.md` — framework build complete
- `cowork_reports/2026-05-17_l2_state_clarification.md` — L2 chronology
- All wave 1-5 per-strategy reports
- `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` — original build directive
- `DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md` — design doc
- Wave 3 + 5 file deliverables (~100 files: framework code, YAML specs, tests, backtest harnesses, reports)
