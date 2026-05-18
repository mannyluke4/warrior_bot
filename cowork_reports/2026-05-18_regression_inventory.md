# Regression Inventory — Stage A1 (DIRECTIVE_2026-05-18_REAL_REGRESSION_AND_DEPLOY)

**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (read-only inventory; no tests run, no changes applied)
**Source directive:** `DIRECTIVE_2026-05-18_REAL_REGRESSION_AND_DEPLOY.md` §A1
**Time budget:** 30 minutes wall-clock

---

## TL;DR

| Question | Finding |
|---|---|
| Tests covering `bot_v3_hybrid.py:3000-3100` (sizing path) | **none** — zero test imports `bot_v3_hybrid`; zero tests exercise `state.broker.get_buying_power()`, `effective_notional`, the `max(1, …)` floor, or the EPL graduation path. The only sizing-shaped tests (`tests/framework/test_vix_regime.py`) test a different `size_multiplier` (VIX regime), unrelated. |
| Tests covering resume-boot signal rehydration | **none** — zero coverage of `resume_reconcile`, `seed_symbol_from_cache`, `_seed_just_ended` rehydration. `test_squeeze_source.py:198,222` exercises `on_trade_price` in a unit-test toy harness, not the resume path. |
| Tests covering R-floor gate (`WB_MIN_ABSOLUTE_R`) | **none** in `tests/`. Test scaffold proposed inline in `cowork_reports/2026-05-18_r_floor_gate_design.md` but not yet committed under `tests/`. (Gate is new — none expected.) |
| VERO 2026-01-16 canonical P&L drift | Each cited number is traceable to a specific commit. **CLAUDE.md says +$34,479** (commit `13d74d3`, 2026-04-08, X01 tuning). Last actual re-run was 2026-04-15 returning **+$35,623** — a $1.1K drift the autopsy noted but never reconciled. Memory `project_current_state.md` says **+$21,024** — that lineage is from the 2026-04-03 box session report and has *never* been reproduced. There has been **no documented re-run of VERO since 2026-04-15** (33 days). |
| ROLR 2026-01-14 canonical P&L drift | **CLAUDE.md says +$54,654** (same X01 commit). 2026-04-15 re-run produced **+$50,602** — a $4K drift that autopsy explicitly labeled "previously noted as pre-existing baseline shift in `080baf2` commit message." Memory says **+$53,979** (from 2026-04-03 box session, unverified since). **No documented re-run since 2026-04-15.** |
| Origin of VERO+ROLR as the canonical pair | First **joint** appearance with P&L targets: commit `3c456dc` (2026-03-19 09:15 MDT) — Manny's CLAUDE.md regression-targets handoff edit. **No directive ever formally designated them as THE regression battery.** Promoted ad-hoc via CLAUDE.md edit; calcified into ritual by 8+ weeks of paste-forward citation. |

**Headline surprise:** the most recent honest re-run (2026-04-15) was already off-target (+$35,623 vs +$34,479; +$50,602 vs +$54,654). The 2026-04-14 re-baseline that would have corrected the entire regression battery to realistic fills (+$18,516 / +$6,444) was **committed and reverted within 3 minutes** (commits `f2bc3a8` → `d82481f`), and the reasoning is preserved in `cowork_reports/2026-04-14_finding_sim_fill_optimism.md` / `…_decision.md`. The standing CLAUDE.md targets do not represent reality on any axis: not the X01 sim-fill numbers (drifted), not the realistic-fill numbers (rejected), not Manny's memory (orphan +$21,024 / +$53,979). The directive's claim that the regression has "drifted from authoritative to ritual" is empirically correct.

---

## 1. Test coverage of `bot_v3_hybrid.py:3000-3100` (sizing path)

**Specific lines under scrutiny:**
- L3033 — `broker_bp = state.broker.get_buying_power() if state.broker else current_equity * 2`
- L3034 — `effective_notional = broker_bp * BUYING_POWER_PCT`
- L3037-3039 — qty / qty_notional / MAX_SHARES min-cap math
- L3048 — `qty = max(1, int(math.floor(qty * size_mult)))` ← qty=1 floor under SBFM scrutiny
- L3206-3207 — EPL graduation path (separate site, same shape)

**Method:** `grep -rn "bot_v3_hybrid" tests/` and `grep -rn "get_buying_power\|effective_notional\|size_mult" tests/`.

**Result:** Zero hits for `bot_v3_hybrid` in `tests/`. The only `size_mult`-shaped hits are in `tests/framework/test_vix_regime.py:52-91`, which tests `VIXRegime.size_multiplier(vix_value, base_size)` — a different feature entirely (VIX-based size scaler in the framework layer; nothing to do with the squeeze probe `size_mult` on `armed.size_mult` consumed at L3048).

**Evidence:**
```
$ grep -rn "bot_v3_hybrid" /Users/duffy/warrior_bot_v2/tests/
(no output)

$ grep -rn "get_buying_power\|effective_notional" /Users/duffy/warrior_bot_v2/tests/
(no output)
```

The `state.broker.get_buying_power()` path is the very call that returned `$0` in the SBFM 2026-05-18 incident and let a 1-share order through. **It has no automated test coverage.**

**Verdict:** **none.** This is a finding. The sizing path is untested.

---

## 2. Test coverage of the resume-boot signal-rehydration path

**Targets in production code:**
- `bot_v3_hybrid.py:848` — `def resume_reconcile()`
- `bot_v3_hybrid.py:1263, 1787` — `seed_symbol_from_cache(symbol)`
- `bot_v3_hybrid.py:1705, 1868` — `sq.validate_arm_after_seed(latest_price)` calls inside the seed/rehydrate path
- `bot_v3_hybrid.py:4657` — `resume_reconcile()` boot-time invocation
- `squeeze_detector.py:89-119` — `_seeding`, `_seed_just_ended` flags
- `squeeze_detector.py:122` — `validate_arm_after_seed(self, current_price)`
- `squeeze_detector.py:160-163, 295` — `_seed_just_ended` gate logic
- The unit method `on_trade_price` (used in resume rehydrate as the tick→signal advance)

**Method:** `grep -rn "resume_reconcile\|seed_symbol_from_cache\|_seed_just_ended\|validate_arm_after_seed" tests/`.

**Result:** Zero hits. The only `on_trade_price` hit is `tests/framework/test_squeeze_source.py:198,222`:
```
198:    def test_on_trade_price_triggers_entry_when_armed(self, monkeypatch) -> None:
222:            msg = src.on_trade_price(arm.trigger_high + 0.01)
```
This is a **toy unit test** of the framework `SqueezeSource` wrapper — not a replay through the resume-boot path, and not exercising `_seed_just_ended` gating, `validate_arm_after_seed`, or `resume_reconcile` at all.

**Evidence:**
```
$ grep -rn "resume_reconcile\|seed_symbol_from_cache\|_seed_just_ended\|validate_arm_after_seed" /Users/duffy/warrior_bot_v2/tests/
(no output)
```

**Verdict:** **none.** Resume-boot rehydration is the exact code path implicated in the SLE 2026-05-15 16:17 stale-signal re-fire incident. It has no test coverage.

---

## 3. R-floor gate test coverage

**Target:** `WB_MIN_ABSOLUTE_R` env var, `MIN_ABSOLUTE_R` module constant.

**Method:** `grep -rn "WB_MIN_ABSOLUTE_R\|MIN_ABSOLUTE_R" /Users/duffy/warrior_bot_v2/`.

**Result:** The only hits are in directive/design docs:
- `DIRECTIVE_2026-05-18_DEPLOY_AMENDMENT.md:51,77`
- `DIRECTIVE_2026-05-18_BROKER_LATENCY_INVESTIGATION.md:179`
- `DIRECTIVE_2026-05-18_REAL_REGRESSION_AND_DEPLOY.md:81,122`
- `cowork_reports/2026-05-18_r_floor_gate_design.md` (full design + proposed test scaffold inline)

The gate is **not yet applied to production code** — the design doc proposes the patch (`MIN_ABSOLUTE_R = float(os.getenv("WB_MIN_ABSOLUTE_R", "0.10"))`) but `grep` shows no live occurrence in `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, or `simulate.py`. Tests for it are proposed inline in the design doc (lines 318+, `def test_min_absolute_r_floor`…) but **not committed under `tests/`**.

**Verdict:** **none in `tests/`.** Matches directive expectation ("none expected — gate is new"). Proposed scaffold lives at `cowork_reports/2026-05-18_r_floor_gate_design.md:318-385` awaiting Stage B build-out.

---

## 4. VERO 2026-01-16 expected-P&L drift — full lineage

### Timeline of citations and the commits that introduced them

| Number | Date | Commit | Origin |
|---|---|---|---|
| +$9,166 | (pre-Fix 5, baseline) | — | Pre-history, MP-era baseline |
| **+$18,583** | 2026-03-18 16:28 | `1faaf59` "Fix 5: TW profit gate — suppress TW on confirmed runners (>= 1.5R)" | Real code change in `simulate.py` (3 locations) + `bot.py`. CLAUDE.md updated: *"VERO 2026-01-16: +$18,583 ✅ (1 trade, 18.6R — TW suppressed at 9.2R, BE exits at 18.6R)"* |
| (joint VERO+ROLR pair first appears) | 2026-03-19 09:15 | `3c456dc` "Handoff update: scanner alignment directive, updated COWORK_HANDOFF, MASTER_TODO, CLAUDE.md regression targets" | First commit where both VERO +$18,583 AND ROLR +$6,444 appear together in CLAUDE.md "Always run regression before pushing" stanza |
| **+$15,692** | 2026-03-27 11:28 | `360f017` "Update VERO regression baseline: +$18,583 → +$15,692" | Commit message: *"Baseline shifted due to system-wide optimization (bail timer, cont hold guard, scanner parity, etc.) between 3/18 and 3/27. Individual VERO P&L dropped $2.9K but portfolio megatest improved from +$5,543 to +$19,832 across 49 days"* — **real, narration-grounded shift; net portfolio improved** |
| **+$34,479** | 2026-04-08 17:10 | `13d74d3` "Deploy X01 tuning config — VOL_MULT 2.5, RISK 3.5%, MAX_ATTEMPTS 5, CORE 90%, TARGET_R 1.5" | Real config change: `.env`/`bot_v3_hybrid.py`/`run_backtest_v2.py` all modified together. CLAUDE.md diff explicitly: *"VERO 2026-01-16: +$34,479 ✅ (shifted from +$15,692 after X01 tuning…)"* |
| **+$21,024** | 2026-04-03 (memory) / 2026-04-04 commit | `f8daa85` "Add session report: box strategy build + ship (April 3)" → file `cowork_reports/2026-04-03_box_strategy_session.md:63` *"Regression verified: VERO $21,024, ROLR $53,979 (unchanged with box OFF)"* | **This number lives in exactly one commit and one cowork report.** It contradicts the X01 +$34,479 target that was *already* the standing baseline on 2026-04-08. Either the 2026-04-03 box session was run pre-X01 (still on +$15,692 era code) and produced an off-baseline number, or it was a partial/different configuration. **The memory `project_current_state.md` paste-forwards it without re-verification.** No follow-up commit ever confirms +$21,024 against current code. |
| **+$18,516** | 2026-04-14 15:42 → reverted 15:45 | `f2bc3a8` "CLAUDE.md: re-baseline against realistic fill modeling (2026-04-14)" → `d82481f` revert | The honest realistic-fill number. Commit message: *"VERO 2026-01-16: +$18,516 (was +$34,479 sim-fill — -46%)"* with banner *"do not cite as current targets"*. **Reverted 3 minutes later** without revert rationale in commit body. Decision context preserved in `cowork_reports/2026-04-14_finding_sim_fill_optimism_decision.md`. (Per Manny's memory `feedback_fill_optimism_disregard.md`, the entire fill-optimism finding was later proven wrong — so the revert was correct, but the standing +$34,479 was never re-verified after.) |
| **+$35,623** | 2026-04-15 (bird chop autopsy replay) | Inline in `cowork_reports/2026-04-15_autopsy_bird_chop_day.md:143-149` | **The most recent actual replay.** Numbers from `tools/analyze_epl_gate_extension.py` cascade-canary table. Autopsy explicitly flags: *"VERO (+$34,479 in CLAUDE.md vs +$35,623 — drift from earlier winsorize/X01 rounding)"* — drift acknowledged, not reconciled. |

### Was X01 tuning a real config change?

**Yes.** Commit `13d74d3` (2026-04-08) modified three production files:
```
.env                    — squeeze params + risk + daily loss scaling
bot_v3_hybrid.py        — wired DAILY_LOSS_SCALE
run_backtest_v2.py      — ENV_BASE + RISK_PCT defaults match X01
CLAUDE.md               — new regression targets VERO +$34,479, ROLR +$54,654
```
This was a substantive config promotion ("X01 tuning battery winner: $1.12M equity (was $357K baseline) over 64-day YTD"), not narration.

### Has anyone re-run VERO after April 2026?

**Indirectly, once.** The 2026-04-15 bird-chop autopsy replayed VERO and got **+$35,623** with the X01 config. The autopsy filed this as "drift-acceptable" without re-baselining CLAUDE.md.

**Since 2026-04-15, no commit, no cowork report, and no log entry shows VERO 2026-01-16 being replayed.** The framework migration report (`cowork_reports/2026-05-16_squeeze_framework_migration.md:163`) cites +$34,479 as a paste-forward target ("X01-tuning live target") and verifies *signal parity* between the wrapper and raw detector — but does not re-run the simulate.py P&L assertion. That report explicitly says "bit-identical to `squeeze_detector_v2`" and "ARM count, attempts, state all identical" — meaning detector behavior is verified, but the **full simulate.py end-to-end P&L** has not been measured against today's code.

### Predicted current expected P&L if run today

Per directive instruction ("do not run it, just identify what the CLAUDE.md-current-config + current-code would produce based on the most recent run citation"):

**Best estimate: +$35,623 ± drift.** That is the 2026-04-15 autopsy number under X01 config. Since 2026-04-15:
- No squeeze-detector logic changes documented affecting VERO replay specifically (the squeeze-framework migration is bit-identical per `2026-05-16_squeeze_framework_migration.md:347`)
- BUT: chop-gate v2 / dead-bounce / chop-gate-v3 work has landed (per memory `project_chop_gate_v2_validated.md`) — VERO is a parabolic runner so most chop gates won't fire, but if any did, P&L could shift
- The +$34,479 in CLAUDE.md is *already* known-stale by $1.1K as of 2026-04-15

A defensible Stage A2/B Test 6 target is **+$35,623 with ±5% tolerance**, not +$34,479. The "drift-acceptable" handwave from 2026-04-15 should be made explicit.

---

## 5. ROLR 2026-01-14 expected-P&L drift — full lineage

### Timeline

| Number | Date | Commit | Origin |
|---|---|---|---|
| **+$6,444** | 2026-03-19 09:15 (earliest in CLAUDE.md) | `3c456dc` | First appearance: joint with VERO +$18,583 as the regression pair. No "VERO target history" narration ever extended to ROLR (no equivalent ROLR lineage line in CLAUDE.md). Number predates `3c456dc` — likely from MP-era backtest, never re-validated when promoted to regression target. |
| **+$54,654** | 2026-04-08 17:10 | `13d74d3` X01 tuning | CLAUDE.md diff: *"ROLR 2026-01-14: +$54,654 ✅ (shifted from +$6,444 after X01 tuning — compounding equity amplifies gains)"* — **note the hand-wave "compounding equity amplifies gains" with no per-trade breakdown** |
| **+$53,979** | 2026-04-03 | `f8daa85` "Add session report: box strategy build" | Same orphan as VERO +$21,024. One cowork report, one memory citation, never re-verified. |
| **+$6,444 (again)** | 2026-04-14 15:42 → reverted | `f2bc3a8` re-baseline | *"ROLR 2026-01-14: +$6,444 (was +$54,654 sim-fill — -88%)"* — under realistic fill modeling, ROLR collapsed to the original pre-X01 baseline. **88% reduction.** Then reverted 3 min later. |
| **+$50,602** | 2026-04-15 autopsy | `cowork_reports/2026-04-15_autopsy_bird_chop_day.md:144` | Autopsy explicitly: *"ROLR (+$54,654 vs +$50,602 — drift previously noted as pre-existing baseline shift in `080baf2` commit message)"* — refers to a prior winsorize/baseline shift that nobody propagated into CLAUDE.md |
| **+$54,654 (standing)** | CLAUDE.md today | (paste-forward since `13d74d3`) | Current canonical citation |

### Was X01 a real change for ROLR? Why the 8.5× jump?

The X01 commit's narration for ROLR is one line: *"compounding equity amplifies gains."* That is plausible — RISK_PCT went from 2.5% to 3.5%, MAX_ATTEMPTS 3→5, plus DAILY_LOSS_SCALE 2% (compounds with equity). On a multi-trade cascade day like ROLR (11 trades per the 2026-04-15 autopsy), compounding will amplify. But the **per-trade breakdown was never documented** the way VERO's was. The number was *asserted*, not *narrated*.

### Has anyone re-run ROLR after April 2026?

**Same as VERO: once, in the 2026-04-15 autopsy (+$50,602), never since.** The framework-migration report verifies signal parity (216 1-minute bars, bit-identical) but not P&L.

### Predicted current expected P&L

**Best estimate: +$50,602 ± drift.** Drift acknowledged on 2026-04-15 without reconciliation; no documented re-run since. CLAUDE.md +$54,654 has been stale by ~$4K for 33 days.

A defensible Stage A2/B Test 7 target is **+$50,602 with ±10% tolerance** to absorb the EPL re-entry timing variance noted in the autopsy (3 EPL re-entries on ROLR, vs 1 on VERO — more re-entries = more variance per replay).

---

## 6. Origin of VERO/ROLR as canonical

### Search method

```
git log --all --reverse -S "ROLR" -- "DIRECTIVE_*.md" "CLAUDE.md" "cowork_reports/*.md"
grep -rln "VERO.*ROLR\|ROLR.*VERO" DIRECTIVE_*.md cowork_reports/*.md
```

### First joint appearance with target P&Ls

**Commit `3c456dc` (2026-03-19 09:15 MDT, Manny Luke author):** "Handoff update: scanner alignment directive, updated COWORK_HANDOFF, MASTER_TODO, **CLAUDE.md regression targets**"

The CLAUDE.md diff in that commit is the genesis of the pair:
```diff
-- **Always run regression before pushing**: VERO +$6,890, GWAV +$6,735, ANPA +$2,088
+- **Always run regression before pushing**: VERO +$18,583, ROLR +$6,444
```

Prior to this commit, the regression battery was three stocks (VERO, GWAV, ANPA) from MP-era. **In this single edit, Manny:**
1. Replaced GWAV+ANPA (which "no longer produce trades in standalone mode due to detector evolution") with ROLR
2. Promoted ROLR to canonical status without a directive establishing it
3. Updated VERO target to the post-Fix-5 number (+$18,583)
4. Added the `--tick-cache tick_cache/` flag to the standing command

The same-day cowork report `cowork_reports/2026-03-19_squeeze_live_enable.md:15` ratifies the pair: *"Regression: VERO +$18,583, ROLR +$6,444 (pass)"* — this is the **first** explicit cowork-report-level use of the pair as a binary pass/fail gate.

### Was there ever a formal directive?

**No.** Search of all `DIRECTIVE_*.md` files in repo root:
- No directive titled "regression battery," "regression targets," or "canonical regression."
- `DIRECTIVE_SQUEEZE_FIXES_V2.md` (2026-03-19 13:40 — same day, 4 hours after `3c456dc`) discusses VERO and ROLR as *test cases for conflict rules*, not as a regression contract.
- `DIRECTIVE_ENABLE_SQUEEZE_LIVE.md` and `DIRECTIVE_MP_V2_SQ_PRIORITY_GATE.md` both *consume* the pair in regression-bash commands but neither *establishes* it. Both were authored after 2026-03-19.
- `DIRECTIVE_2026-05-18_REAL_REGRESSION_AND_DEPLOY.md` (today's directive) is the first to **formally challenge** the pair's canonical status.

### Why the ritual persisted

Three reinforcement loops kept VERO/ROLR pasted into 15+ reports across 8 weeks:

1. **CLAUDE.md is the project bible.** Once Manny put the pair in the "Always run regression before pushing" stanza on 2026-03-19, every CC iteration reading CLAUDE.md (and that is *every* CC session, by `init` skill protocol) saw it as the contract. Citation begat citation.

2. **The number changes were never re-verified in the same commit.** X01 tuning (`13d74d3`) modified the targets and the config in one commit but did not commit a `simulate.py` output proving +$34,479 / +$54,654. The numbers were trusted because of the X01 battery aggregate ($1.12M equity), not because anyone re-ran the two-stock spot-check after.

3. **The 2026-04-14 honest re-baseline was reverted in 3 minutes.** This was the one moment when CC tried to write *current* numbers — and the revert (without an explicit "why this is wrong" commit body) signaled that the +$34,479 / +$54,654 paste was canonical even when subsequent measurements (autopsy +$35,623 / +$50,602) showed it was drifting.

The "drift" Manny named in today's directive is real. It was empirically visible on 2026-04-15 and ignored.

---

## Appendix — Files referenced

Production code:
- `/Users/duffy/warrior_bot_v2/bot_v3_hybrid.py` (lines 848, 1263, 1705, 1787, 1868, 3000-3100, 3048, 4657)
- `/Users/duffy/warrior_bot_v2/squeeze_detector.py` (lines 89-119, 122, 160-163, 295)

Tests (existing):
- `/Users/duffy/warrior_bot_v2/tests/framework/test_squeeze_parity_e2e.py` (VERO/ROLR signal parity only, not P&L)
- `/Users/duffy/warrior_bot_v2/tests/framework/test_squeeze_source.py:198,222` (`on_trade_price` toy unit test)
- `/Users/duffy/warrior_bot_v2/tests/framework/test_vix_regime.py:52-91` (unrelated `size_multiplier`)

Key commits:
- `1faaf59` 2026-03-18 — Fix 5 TW profit gate, established VERO +$18,583
- `3c456dc` 2026-03-19 — **canonical pair established in CLAUDE.md**
- `360f017` 2026-03-27 — VERO +$18,583 → +$15,692
- `13d74d3` 2026-04-08 — X01 tuning, +$34,479 / +$54,654 established
- `f8daa85` 2026-04-04 — Box session report (orphan +$21,024 / +$53,979)
- `f2bc3a8` 2026-04-14 — realistic fill re-baseline (+$18,516 / +$6,444)
- `d82481f` 2026-04-14 — revert of `f2bc3a8` (3 minutes later)
- `080baf2` — referenced in autopsy as the "pre-existing baseline shift" for ROLR (not investigated here for time-budget)

Recent re-runs:
- `cowork_reports/2026-04-15_autopsy_bird_chop_day.md:143-149` — VERO +$35,623, ROLR +$50,602 (most recent actual data)
- `cowork_reports/2026-05-16_squeeze_framework_migration.md` — signal parity verified, P&L *not* re-measured

Decision context for the 2026-04-14 revert:
- `cowork_reports/2026-04-14_finding_sim_fill_optimism.md`
- `cowork_reports/2026-04-14_finding_sim_fill_optimism_decision.md`
- Memory: `~/.claude/projects/-Users-duffy/memory/feedback_fill_optimism_disregard.md`

---

## Recommendations for Stage A2 (not authoritative — for Manny's call)

Given the findings:

1. **Test 6 (VERO control) target:** propose +$35,623 ± 5% (from 2026-04-15 autopsy), not the CLAUDE.md +$34,479.
2. **Test 7 (ROLR control) target:** propose +$50,602 ± 10% (from 2026-04-15 autopsy), not the CLAUDE.md +$54,654.
3. **Before any Stage B patch lands, re-run both VERO 2026-01-16 and ROLR 2026-01-14 against HEAD** and update CLAUDE.md with `(run YYYY-MM-DD, commit XXXXXXX)` provenance on the target lines. The directive's "every regression citation must include the run date" rule applies to this moment.
4. **Memory `project_current_state.md`'s +$21,024 / +$53,979 should be flagged stale or deleted.** Those numbers have no provenance in main-branch commits beyond a single 2026-04-03 box-session note and have never been reproduced.
