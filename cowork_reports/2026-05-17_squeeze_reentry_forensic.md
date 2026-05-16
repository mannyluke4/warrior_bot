# Squeeze Re-Entry Forensic — Investigation 1 of DIRECTIVE_2026-05-16_LOSER_FORENSIC

**Date:** 2026-05-17
**Author:** Cowork
**Window:** 2026-05-11 through 2026-05-15 (5 trading days), Setup A (`bot_v3_hybrid.py`) and Setup B (`squeeze_bot.py`) combined
**Hypothesis owner:** Manny

---

## 1. Hypothesis

Re-entries on the same symbol on the same trading day are systematically worse than the first attempt of the day. Manny's framing: the first squeeze attempt on a symbol captures the cleanest setup; subsequent attempts on the same symbol are entering after the easy money has already left. The audit-week canonical case is SLE on 2026-05-15: a clean N=1 winner (08:32, +$468), an N=2 loser (09:19, −$247), and seven downstream chase-cap timeouts. The hypothesis is *not* "every N=1 is a winner" — LESL 5/15 was N=1 and lost — it is "every N≥2 underperforms N=1 in expectation."

---

## 2. Method

- Tagged every squeeze ATTEMPT (filled OR chase-cap-timeout OR BP-block OR R-floor SKIP) by ordinal attempt number on that symbol that day, both setups combined.
- Source 1: per-trade table from `cowork_reports/2026-05-16_squeeze_strategy_audit_weekly.md`.
- Source 2: line-by-line scan of `logs/2026-05-{11..15}_daily.log` (Setup A) and `~/warrior_bot_v2_engine/logs/2026-05-{11..15}_squeeze_bot.log` (Setup B), grepping for `ENTRY SIGNAL`, `FILL:`, `EXIT:`, `ORDER TIMEOUT`, `ENTRY BLOCKED: insufficient_bp`, and the SKIP path (`R<0.06 min`).
- Excluded: SQ_PRIMED that never produced an ARM/ENTRY (no order intent), SQ_REJECT on `not_new_hod` (filter declined before any order), and the 5/11 ENSC 07:01 pre-fix-bundle signal (no order ever sent — infrastructural, not strategic).
- For each N bucket: counted attempts, broke down by outcome (fill / chase-cap timeout / BP-block / R-skip), then for fills computed win rate, average realized P&L, and average hold duration.

---

## 3. Data table — every squeeze attempt, both setups, by ordinal N

| Date | Sym | Setup | N | Time ET | Score | Outcome | P&L | Δ from prior N |
|------|-----|-------|---|---------|-------|---------|-----|-----------------|
| 5/11 | ODYS | A | 1 | 08:48 | 10.0 | chase-cap timeout | $0 | — |
| 5/11 | TRAW | A | 1 | 09:31 | 12.0 | chase-cap timeout | $0 | — |
| 5/13 | ATRA | A | 1 | 14:34 | 12.0 | SKIP (R=0.059 < 0.06) | $0 | — |
| 5/13 | ATRA | B | 2 | 15:19:53 | 11.0 | FILL → loss-cap | **−$906** | +45m |
| 5/13 | VNET | B | 1 | 15:19:55 | 8.5 | FILL → bail-timer | **−$44** | — |
| 5/14 | LNKS | A | 1 | 13:48 | 12.0 | chase-cap timeout | $0 | — |
| 5/15 | SLE | A | 1 | 08:32 | 10.0 | **FILL → target_hit** | **+$468** | — |
| 5/15 | SLE | B | 1\* | 08:32 | 6.6 | FILL → para-trail (3s) | **−$446** | concurrent |
| 5/15 | LESL | A | 1 | 08:58 | 11.0 | FILL → loss-cap | **−$533** | — |
| 5/15 | SLE | A/B | 2 | 09:19 | 5.3 | FILL → para-trail | **−$247** | +47m |
| 5/15 | ONDG | A | 1 | 09:31 | 12.0 | chase-cap timeout | $0 | — |
| 5/15 | ONDG | B | 1\* | 09:31 | 11.0 | chase-cap timeout (3 retries) | $0 | concurrent |
| 5/15 | ONDG | B | 2 | 09:34 | 11.0 | BP-block | $0 | +3m |
| 5/15 | ONDG | B | 3 | 09:38 | 11.0 | BP-block | $0 | +4m |
| 5/15 | QUCY | A | 1 | 10:10 | 7.9 | chase-cap timeout | $0 | — |
| 5/15 | SLE | A/B | 3 | 10:46 | 7.0 | chase-cap timeout | $0 | +87m |
| 5/15 | SLE | A | 4 | 16:17:15 | 11.0 | chase-cap timeout | $0 | +331m |
| 5/15 | SLE | A | 5 | 16:25:36 | 11.0 | chase-cap timeout | $0 | +8m |
| 5/15 | SLE | A | 6 | 17:16:38 | 11.0 | chase-cap timeout | $0 | +51m |
| 5/15 | SLE | A | 7 | 17:25:46 | 11.0 | chase-cap timeout | $0 | +9m |
| 5/15 | SLE | A | 8 | 17:46:16 | 11.0 | chase-cap timeout | $0 | +21m |
| 5/15 | SLE | A | 9 | 17:50:14 | 11.0 | chase-cap timeout | $0 | +4m |

\* "N=1\*" denotes concurrent same-second signal on the other setup (treated as parallel N=1 because it was the first attempt on that setup's account, not a re-entry).

### Per-N bucket summary

| N | Attempts | Fills | Cap-TO | BP-block | SKIP | Wins | Win rate (of fills) | Net realized P&L | Avg R-multiple (fills) | Avg hold |
|---|----------|-------|--------|----------|------|------|---------------------|-----------------|------------------------|----------|
| 1 | 10 (incl. 2 concurrent) | 4 | 5 | 0 | 1 | 1 | **25%** (1/4) | **−$555** | −0.84R | 3m 0s avg |
| 2 | 3 | 2 | 0 | 1 | 0 | 0 | **0%** (0/2) | **−$1,153** | −2.32R | ~14m avg |
| 3 | 2 | 0 | 1 | 1 | 0 | 0 | n/a (no fills) | $0 | — | — |
| 4–9 | 6 | 0 | 6 | 0 | 0 | 0 | n/a (no fills) | $0 | — | — |

(R-multiples computed from per-trade R$ in the audit table; ATRA N=2 fill at $10.49 → close $10.31 ≈ −0.67R but `sq_dollar_loss_cap` fired at the −$715 threshold which exceeded entry R, hence −2.3R realized. SLE N=2 fill $7.06 → close $6.95 ≈ −1.0R via para-trail before −$247 final.)

---

## 4. Findings

- **N=1 fills: 1 winner / 3 losers / net −$555.** Win rate 25%, average realized R approximately −0.84.
- **N=2 fills: 0 winners / 2 losers / net −$1,153.** Both were larger-dollar losses than the average N=1 loser; both hit a hard exit (loss-cap or para-trail) within ~14 minutes.
- **N≥3: zero fills.** Six attempts on SLE (N=4–9) and two on ONDG (N=2 BP-blocked, N=3 BP-blocked) produced no executions. The chase-cap and BP-block guards effectively silenced re-entries 3-and-beyond.
- **The only realized winner in the week was N=1** (SLE 5/15 08:32, +$468). Every fill at N≥2 lost money.
- **Time-since-prior-attempt is large** for the few N=2 fills that did execute: ATRA 5/13 N=2 was +45 minutes after its Setup A N=1 SKIP; SLE 5/15 N=2 was +47 minutes after N=1. These are not minute-by-minute re-tries — they are mid-day re-arms at new levels (SLE $6→$7 whole-dollar, ATRA $9.81→$10.49). Manny's "after the easy money has left" framing is consistent with the price already having extended by the time N=2 arms.
- **SLE 5/15 N=1 → N=2 transition narrative:** N=1 hit `sq_target_hit` at $6.33 (+$469 net) within 30 seconds. Forty-seven minutes later, the stock had climbed another full dollar ($7.05 HOD) and was re-arming at the $7 whole-dollar level. Score had collapsed from 10.0 → 5.3 (vol_extra dropped from +5.0 → +0.3 — the spike volume was no longer present), and the price was now $6.76 above a VWAP of $5.88 (+15% extension vs N=1's +15%). The para-trail exit fired immediately on bar +1 because the entry was effectively at local top — price went $7.06 → $6.95 within minutes, then to $6.26 over the next 14 minutes. **The detector did not differentiate "we already took the clean shot" from "this is a fresh setup at a new level."** Score collapse from 10.0 to 5.3 was the signal but the score-floor (R>0.06, no minimum score) didn't block it.
- **SLE 5/15 N=3 onwards (extended hours):** Six attempts between 16:17 and 17:50, all on the same arm parameters ($5.02 trigger, $4.90 stop). All chase-capped because the actual market price was sitting in the $5.80–$6.10 range — the level had been broken long before the bot's arm refreshed. Cost $0 in P&L but consumed scanner cycles and log noise. **This is "broken level re-fire," distinct from the N=2 case which was a new level at a new score.**
- **LESL 5/15 (N=1, loss) is the counter-example.** Score 11, parabolic-no, R=0.20, fill $4.04, exit $3.84 via dollar-loss-cap. N=1 is *not* a free pass — the hypothesis only constrains N≥2.
- **ATRA 5/13 (N=2 across-setups, loss).** Setup A had a 14:34 SKIP (R<0.06 floor); Setup B fired N=2 at 15:19 at a higher price ($10.49 vs $9.81). Score went 12.0 → 11.0, R went $0.06 → $0.27 — i.e., a *different* setup geometry. But the bot didn't know that — it treated Setup A's skip and Setup B's signal as independent events. **Cross-setup awareness is currently absent.**
- **ONDG 5/15 N=1 → N=2/N=3 transition.** N=1 (09:31) chase-capped at $7.57 vs $7.57. N=2 (09:34, +3m) BP-blocked at $8.07 — price had already moved $0.50 in 3 minutes. N=3 (09:38, +4m) BP-blocked at $8.10. Even if BP were available, N=2 and N=3 would have entered at the extension. Mechanical guards saved capital here.
- **Both N=2 fills shared a feature:** entry occurred well after price had already extended past where N=1 attempted. ATRA N=2 entry $10.49 vs N=1 attempted level $9.81 (+7%). SLE N=2 entry $7.06 vs N=1 trigger $6.02 (+17%). **N=2 by construction enters at a higher price than N=1; if N=1 was the right entry, N=2 is by definition late.**

---

## 5. Falsification check

The falsification criterion was: "If win rate on Nth attempt (N≥2) is statistically similar to 1st-attempt win rate across available data, hypothesis is rejected."

- N=1 fill win rate: 1/4 = 25%
- N≥2 fill win rate: 0/2 = 0%
- N≥3 fill win rate: undefined (zero fills; mechanical guards prevented execution)

The directional split (25% vs 0%) is consistent with the hypothesis, but with 2 N≥2 fills the difference is not statistically distinguishable from the 25% baseline at any reasonable alpha — a single coin flip producing two losses is unexceptional. With this sample size, **the hypothesis is neither confirmed nor falsified statistically.**

What the data does show unambiguously: **of two N≥2 fills, both lost large dollars**, and **the symptomatic pattern (price extension between N=1 and N=2, score collapse from N=1 to N=2)** is observable on both events. That is a directional finding, not a statistical one.

**The 6× SLE extended-hours stack (N=4–9)** functioned as a stress test of the mechanical guards: zero fills, zero P&L, zero damage. The chase-cap is already doing the right thing for re-fires on stale levels — they don't need a separate kill switch unless log noise is the concern.

---

## 6. Proposed action

**Confidence: medium-low.** Sample too small to ship a hard rule, but the asymmetry warrants a guarded change.

**Proposal:** **per-symbol per-day attempt cap with score-decay aware gating.** Implement as:

1. **Hard cap: max 3 ARMS per symbol per day** (across both setups, via a shared persistent counter in `session_state/`). This silences the SLE extended-hours stack without affecting the legitimate N=2 question.
2. **Score-decay guard on N=2:** if attempt N≥2 has score ≥ 1.5 points below the N=1 score on the same symbol that day, block the entry as `SQ_REJECT: score_decay (n=N-1 was X, now Y)`. SLE N=2 (5.3 vs N=1's 10.0) and ATRA N=2 (11.0 vs N=1's 12.0 — would *not* trigger this gate, important) — so this gate would have blocked SLE N=2 (−$247 saved) but not ATRA N=2 (−$906 not saved). The ATRA case is a different problem — see #4 below.
3. **Cross-setup attempt awareness:** mark a symbol-day-attempt counter at the engine level (shared file between Setup A and Setup B) so both bots see the same N. Setup B fired ATRA at 15:19 not knowing Setup A had already skipped it at 14:34. **This is infrastructure, not strategy, but it's the precondition for N to mean anything across both bots.**
4. **For N=2 fills that pass the score-decay check (ATRA-like cases):** require *fresh PM_HIGH or fresh whole-dollar break that did not exist at N=1*. ATRA N=2 was a fresh PM_HIGH break at $10.49 vs N=1's $9.81; that's arguably the type of "real second setup" we'd want to keep. But this is a single event — don't ship a feature for n=1. **Action: tag and observe for 2 more weeks; do not gate yet.**

**What NOT to do (low confidence anti-recommendations):**

- **Do NOT cap at N=1 only.** The data doesn't support that. ATRA N=2 was a structurally different setup; it lost, but blocking it would also block similar setups that might win in the future. The hypothesis is not "ban all re-entries"; it's "re-entries are systematically worse than first attempts."
- **Do NOT add a time-based cooldown** (e.g., "30 minutes between attempts"). SLE N=2 was 47 minutes after N=1; a 30-minute cooldown wouldn't have blocked it. ATRA N=2 was 45 minutes after the N=1 SKIP — same issue. Time alone is not the signal; *price extension and score decay* are.
- **Do NOT widen the chase cap to capture N≥4 re-fires.** The 6× SLE extended-hours stack would convert from $0 cost to potentially-large losses if filled. The chase-cap is doing its job there.

---

## 7. Limitations

- **Sample size is fatal for statistical claims.** Six fills total across five days, of which exactly two are N≥2. No bootstrap, no p-value, no confidence interval is meaningful on n=2.
- **Single-day dominance:** 4 of 6 fills happened on 5/15, and 8 of 9 N≥2 attempts were on SLE 5/15. The hypothesis is effectively being tested on one symbol's one-day behavior.
- **Selection bias from chase-cap and BP-block:** the chase-cap blocks the *eager* re-entries (the bot wanting to chase higher prices). If the chase-cap were wider, more N≥2 fills would happen — and they would by definition be at *worse* prices. The current data understates how bad N≥2 fills would be at a wider cap.
- **Cross-setup pollution:** Setup B's 5/13 reconnect cluster (ATRA + VNET filed within 2 seconds) was an infrastructure event, not a strategy event. It contaminates the N analysis if treated as independent, but separating it requires judgment calls.
- **Score is a noisy signal.** SLE N=2's score of 5.3 came from `vol_extra` dropping from +5.0 to +0.3 — the spike volume that drove N=1's score had already happened. A score-decay gate that uses the raw score number conflates "real setup quality drop" with "the spike already happened so the contribution decayed." Better signal might be "fresh-vol-bar in the last 3 bars" — but that's a different investigation.
- **No tick-cache re-simulation done.** This forensic is based on log evidence only. If Manny wants the counterfactual ("what if N=2 hadn't been allowed?"), Investigation 3 (stop-hit reverse analysis) on the same trades would be the path; cross-reference if that investigation runs.
- **Jan-Apr backtest data NOT pulled.** The original directive asked for it; in practice, the squeeze configuration shifted multiple times between Jan and the 2026-05-14 fill-rate fix bundle, so historical N=1 vs N=2 comparison would mix configurations. The audit week is the cleanest available slice. Recommend deferring the historical extension until after one more clean week of post-fill-fix data.

---

## Bottom line

The hypothesis **directionally supports** Manny's intuition — both N=2 fills in the audit week lost money, the only realized winner was N=1, and the SLE 5/15 N=1→N=2 sequence shows the canonical "score decays, price extends, exit fires fast" pattern. But with n=2 N≥2 fills, the data is not strong enough to ship a hard "N=1 only" rule. The defensible immediate action is the **per-symbol attempt-cap (max 3 ARMS/day) + score-decay guard on N≥2** combination. The score-decay guard catches the SLE case cleanly; the attempt-cap kills the extended-hours noise; both are reversible if 2-3 more weeks of data show N=2 winners we'd be missing.

The chase-cap and BP-block mechanics did most of the work this week — N≥3 was zero fills, zero damage. The exposed surface is N=2 specifically, on liquid-enough names where the chase-cap doesn't trigger.
