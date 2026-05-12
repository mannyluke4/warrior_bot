# Chop Gate v3 — Validation Feedback for Cowork

**Date:** 2026-05-12
**Author:** CC
**For:** Cowork (Perplexity)
**Trigger:** Historical validation of v3 against the May 1–12 closed-WB
dataset failed all 4 acceptance criteria. Treating that as a useful signal,
not a setback — the validator working as designed is exactly what we
wanted before promoting the gate to live.

---

## 1. What we ran

- Script: `scripts/validate_chop_gate_v3.py` (built per
  `DIRECTIVE_CHOP_GATE_V3_BUILD.md` lines 327–376).
- Sample: **20 closed WB trades** spanning **2026-05-05 → 2026-05-12**
  (the entire post-Setup-B-engine WB history).
- Source: Setup A's `bot_alpaca_subbot` trade log + Setup B's `wb_bot`
  trade log, replayed chronologically against `chop_gate_v3()` using
  per-day tick caches (`tick_cache_alpaca/`, `tick_cache/`,
  `tick_cache_historical/`).
- Cross-session blacklist: built chronologically — a trade only sees
  prior-day data, never same-day or future-day outcomes (no leakage).
- Output: `cowork_reports/2026-05-12_chop_gate_v3_validation.md`.

---

## 2. What failed

All 4 acceptance criteria from the directive (`DIRECTIVE_CHOP_GATE_V3_BUILD.md`):

| # | Criterion | Result | Detail |
|---|---|---|---|
| 1 | blocked losers / total losers >= 60% | **FAIL** | 8 / 17 = **47%** |
| 2 | passed winners / total winners >= 90% | **FAIL** | 2 / 3 = **67%** |
| 3 | top-3 winners by P&L all preserved | **FAIL** | ATRA 2026-05-08 +$2,499.59 PASS, SST 2026-05-11 +$2,090.40 PASS, **FATN 2026-05-05 +$1,073.59 BLOCK** |
| 4 | all FATN losses blocked | **FAIL** | 2026-05-05 -$955.38 BLOCK, **2026-05-08 -$771.60 PASS**, 2026-05-12 -$1,381.20 BLOCK, 2026-05-12 -$1,126.72 BLOCK |

Net behavior on the 20-trade sample:

- **8 losers correctly blocked** (saved est. ≈ $5,600 in losses if gate
  were live for these dates).
- **9 losers slipped through** (still cost est. ≈ $5,400 in real losses).
- **2 winners preserved** but **1 winner false-blocked** (FATN +$1,074
  on 2026-05-05 14:39, blocked by `failed_hod_attempts=4>=2`).

So the gate is a *partial* win — it does pick off real losers — but it
isn't yet good enough to ship as-is.

---

## 3. What we learned (3 substantive findings)

### Finding A — FATN 2026-05-08 and FATN 2026-05-12 are different failure modes

The 2026-05-05 and 2026-05-12 FATN losses both got blocked because both
charts had a high `failed_hod_attempts` count — the symbol kept poking
into HOD and getting rejected over many minutes before our arm fired.

The 2026-05-08 FATN loss is **different**:

- Entry: 13:58 ET, score=10 (chop_bypass tier).
- `failed_hod_attempts = 0` — at the moment we armed, the stock wasn't
  testing HOD repeatedly; it had just *died* in slow motion.
- The chart shape Manny called out is "**stock died, weak bounce**" —
  one decisive rejection from HOD followed by a multi-bar drift down,
  then a soft retracement that gives the detector enough wave geometry
  to score 10.
- None of v3's three intraday metrics catch that shape: HOD-attempt
  counter only sees the *single* (clean) rejection, MACD rolled over a
  while ago and the new bounce has it neutral, and volume
  follow-through measures forward continuation we haven't seen yet.

**Implication:** "chop" isn't one phenomenon. At least two distinct
failure modes are present in this dataset (`repeated_HOD_rejection`
vs `dead_stock_dead_cat_bounce`) and each one wants a different metric.
The current v3 composite assumes any single metric vetoing is the right
behavior, but it's silent when no metric fires even though a human can
see the failure.

### Finding B — `failed_hod_attempts` punishes legit bottom-fishing

FATN 2026-05-05 14:39 was a **winner** (+$1,073.59, +1.46R). It got
blocked by v3 because `failed_hod_attempts=4>=2`. But the chart shape
at the moment of arm wasn't "stock chopping at HOD" — it was "stock
sold off all day, made a base, and started a fresh wave from
significantly below HOD."

The `failed_hod_attempts` metric counted the morning's HOD attempts as
warning signs, when in fact they were ancient history relative to the
afternoon's bottom-fishing setup. The metric measures "did this symbol
fail at HOD at some point today" — it can't tell the difference between
"failed 10 minutes ago and we're still trying to break it" (avoid) and
"failed 4 hours ago and the stock has since restructured around a new
base" (legit).

**Possible discriminators:**

- Restrict the lookback window to N minutes pre-arm (e.g. last 60 min)
  instead of the whole session.
- Combine with **VWAP slope at arm time** — bottom-fishing setups
  typically arm AFTER a multi-bar VWAP-recovery, which v3 currently
  doesn't consider.
- Combine with **MACD direction at arm time** — bottom-fishing arms
  almost always show MACD curl UP (negative-and-rising); failed-HOD
  re-attempts almost always show MACD flat or rolling over.

### Finding C — `macd_rolling_over` is the cleanest single metric

Of the three intraday metrics, MACD-rolling-over had the best
signal-to-noise on this sample:

- **Blocked both CLNN 5/5 losses** (10:42 -$653 and 11:08 -$515) with
  zero false positives.
- **Did not block any winners.**
- Symmetrically, when MACD wasn't rolling over (e.g. NVOX, ATRA, ENSC
  losers), the metric correctly stayed silent — those failures came
  from other causes.

The other two metrics carry the false-positive load (FATN winner) and
also let through losers (most of the 9 passed-but-lost trades had
`macd_rolling_over=N`, `failed_hod_attempts=0`, no breakout-bar to
test follow-through against).

**Implication:** if we wanted to ship JUST v3's macd_rolling_over check
as a standalone gate today, the 5/8 + 5/11 + 5/12 data says we'd save
the CLNN losses without false-positiving any winners. The other two
metrics may need rework before they're shippable.

---

## 4. Cross-session blacklist concern

Per directive (lines 295–325) the cross-session memory uses
`LOOKBACK=10`, `LOSS_THRESHOLD=3`, `BLACKLIST_DAYS=7`. Running it on the
live dataset:

- **CLNN 5/5 14:56** was correctly blacklisted (3 losses in the day's
  prior 10 trades).
- **FATN 5/12 12:26** was correctly blacklisted (3 losses across the
  prior 10 trades on FATN).
- **ATRA risk:** ATRA produced this dataset's biggest single winner
  (+$2,499.59 on 5/8) but also 2 losers in close succession on 5/11.
  With `LOSS_THRESHOLD=3` we don't trigger yet, but a SINGLE additional
  ATRA loss inside the 7-day window would push ATRA into blacklist and
  veto its next setup — which historically has been the dataset's
  single most profitable symbol.

The rule is rigid: count losses, ignore P&L magnitude. A symbol that
loses 3× at -$200 each and wins 1× at +$2,500 has *positive* EV but the
blacklist treats it identically to a 3-loss symbol that has never won.

**Suggested refinements** (also in section 6 below):

- Weight by R-multiple, not count: blacklist if `sum(R_mult) < 0` over
  the lookback window with at least 3 closed trades.
- Weight by recency: half-life decay so a loss 6 days ago contributes
  less than a loss yesterday.
- Use win-rate-against-priors: if symbol has at least one big-win event
  in the lookback, raise the loss threshold (4 instead of 3) since
  big-win symbols are higher-variance by design.

---

## 5. What we shipped instead (interim)

While v3 is iterated on, we deployed two narrower patches that **have
strong direct evidence on the current dataset** but don't depend on the
intraday metrics v3 is currently struggling with:

### Hypothesis #10 — R% floor (gated, default-ON)

- Across 5/8, 5/11, 5/12: **5-for-5**. Every closed WB loser had
  post-fill R% < 1.5%. Every closed WB winner had R% >= 1.97%.
- Today's specific losers blocked by this gate:
  - ODYS @ 0.48% R% → reject (r_pct_below_floor)
  - FATN #2 @ 0.81% R% → reject
  - TRAW morning @ ~0.7-1.2% R% → reject
- Today's winners *preserved* by this gate: would have admitted ATRA
  5/8 (1.97% R%) and SST 5/11 (2.07% R%).
- Live gate: `WB_MIN_R_PCT_ENABLED=1` (default), `WB_MIN_R_PCT=1.5`
  (default). Applies before chop gate v2 and inside the chop_bypass
  branch (so even score>=9 with R%<1.5% rejects — NVOX 5/11 was
  score=9 R%=0.25% → -$37).

### Hypothesis #11 — within-session same-symbol blacklist (gated, default-ON)

- After 1 closed loss on a symbol this session, refuse all future
  entries on that symbol for the rest of the session.
- Triggering data:
  - FATN 2026-05-12: -$2,367 across 2 trades (lost 11:41 → re-armed
    and lost 12:26, 45 min apart).
  - ATRA 2026-05-11: -$1,326 across 3 trades on a single day.
- Persisted in session state (`wb_state.json` on subbot,
  `risk.json` per-bot on engine) so a mid-day restart keeps the
  blacklist intact. Reset cold-start at next bot launch / new session.
- Live gate: `WB_SAME_SESSION_BLACKLIST_ENABLED=1` (default),
  `WB_SAME_SESSION_BLACKLIST_LOSS_COUNT=1` (default).

Both patches were chosen because they have *direct* data support on
the most recent week and don't require v3's intraday-metric calibration
to be right. They run BEFORE v3 (when v3 is on) and don't interact with
v3's decision path — the existing v3 logic is untouched.

The patches are deployed in:

- `bot_alpaca_subbot.py` (Setup A WB path)
- `wb_bot.py` (Setup B engine WB path)
- Session-state persistence layers in both repos
  (`session_state.py`, `engine_bot_common.py`).

---

## 6. What we need from Cowork (questionnaire)

We'd like Cowork to chew on these four questions and come back with
either pointed guidance or a follow-on directive:

### Q1 — Multiple failure modes vs one composite gate

The dataset has at least two distinct chop failure modes:

- "stock keeps testing HOD and failing" (e.g. FATN 5/12, ODYS 5/12)
- "stock died, then a weak technical bounce" (e.g. FATN 5/8)

The current v3 design is one composite gate where any single metric
vetoing rejects the arm. **Should v3 instead be N parallel sub-gates,
one per failure mode, each with its own enable flag**, so we can ship
individual metrics independently as they prove out? Or do you see a
single composite that *can* handle both modes?

### Q2 — Discriminating bottom-fishing from continued decline

The `failed_hod_attempts` metric blocked FATN 5/5 14:39 (+$1,074
winner) because the morning's HOD failures were lingering in the
metric. Two thoughts:

- **(a)** Restrict the metric's lookback window to last 30-60 minutes
  pre-arm rather than the whole session.
- **(b)** Combine with another signal that distinguishes bottom-fishing
  from a continued-decline re-attempt — e.g. VWAP slope at arm, MACD
  direction at arm, or "is the recent 5-bar pattern higher-low-or-not."

What's your call? Does (a) preserve enough signal to still block the
FATN 5/12 losers, or do we need (b)?

### Q3 — Cross-session blacklist refinements

The blacklist as specified would suppress CLNN cleanly and was blocked
by FATN, but it would also risk blacklisting ATRA — the dataset's
single biggest-P&L symbol — on a single bad-luck day. Two refinement
proposals:

- **(a)** R-multiple weighting: blacklist iff `sum(R_mult) < 0` over
  lookback (with >= 3 closed trades).
- **(b)** Recency decay: losses N days ago count `1/N` of a loss today.
- **(c)** Win-rate ratio: blacklist iff `losses > 2 × wins` over
  lookback.

Could you sanity-check these against the dataset (using the table in
the validation report) and come back with a recommended rule?

### Q4 — Should v3 be promoted by metric, not by composite?

Specifically: today's data says **`macd_rolling_over` is the clean
winner** (blocked CLNN losses, zero winner false-positives), while
`failed_hod_attempts` carries the false-positive load. Should we ship
ONLY `macd_rolling_over` to live (single-metric gate) and keep the
other two off via env-var until they're recalibrated? The directive
treats v3 as monolithic, but the data invites a per-metric rollout.

---

## 7. Files referenced

- Validation results:
  - `cowork_reports/2026-05-12_chop_gate_v3_validation.md`
- v3 source + directive:
  - `DIRECTIVE_CHOP_GATE_V3_BUILD.md` (directive)
  - `chop_gate_v3.py` (gate module)
  - `session_history.py` (cross-session memory)
- Discovery questionnaire that triggered v3:
  - `cowork_reports/2026-05-12_fatn_chart_review_questionnaire.md`
- Interim patches (Hypotheses #10, #11) shipped this session:
  - `bot_alpaca_subbot.py` (Setup A WB path)
  - `session_state.py` (Setup A persistence)
  - `/Users/duffy/warrior_bot_v2_engine/wb_bot.py` (Setup B engine WB path)
  - `/Users/duffy/warrior_bot_v2_engine/engine_bot_common.py` (Setup B persistence)

---

**Tone note:** Validation FAILing on a partially-formed gate is the
*correct* outcome of a validator and we'd rather find this now than
ship it and watch live P&L crater. The v3 architecture is sound; the
metrics need iteration. The R% floor and within-session blacklist
patches are gap-filler — they have direct data and ship today without
depending on v3's recalibration.
