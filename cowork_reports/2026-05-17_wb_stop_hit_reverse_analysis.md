# WB Stop-Hit Reverse-Time Analysis — Investigation 3

**Author:** CC (forensic per `DIRECTIVE_2026-05-16_LOSER_FORENSIC.md` Investigation 3 + amendment + `NO_OVERNIGHTS_CLARIFICATION`)
**Window:** 2026-05-11 → 2026-05-15
**Universe:** All WB stop-hit losers (18 fills) plus full WB fill set for 3.2 EH bucketing
**Data:** `tick_cache/2026-05-DD/<SYM>.json.gz` walked tick-by-tick from entry → stop-hit
**Exclusions:** FCHL 5/14 (infra), MEI 5/13 (manual injection), ODYS 5/13 ×2 (overnight, now obsolete under force-exit)

---

## 1. Hypotheses

**Hypothesis 3.1.** Many WB stop-hit losers had a positive-unrealized-P&L window before reversing. If most hit +0.3R or higher at some point, a faster exit trigger (move-to-BE at +0.5R, or partial-out at +0.5R) would convert losses to scratches or partial scratches. **Falsification:** if most losers go from entry directly to stop without ever tagging +0.3R, the exit-side has no salvage; entries themselves are the defect.

**Hypothesis 3.2.** Force-exit at 19:55 ET now bounds the EH downside structurally. If WB fills in the extended-hours window (16:00–19:55 ET) win at within 10% of the RTH win rate, the recently-clarified `WB_DISABLE_EXTENDED_HOURS_ENTRY=0` (allow EH) is the correct posture. If EH win rate is materially worse than RTH, the EH-specific block should be kept on. **Falsification:** EH WR within 10pp of RTH WR.

---

## 2. Method

### 3.1 — Stop-hit reverse walk

- For each of the 18 stop-hit fills, load the day's tick file.
- Walk tick-by-tick from the entry timestamp forward until either (a) price ≤ stop level (true stop-hit moment) or (b) declared exit time + 2 min buffer.
- Track `max_price`, `min_price`, `t_max`, `t_first_breach`.
- Compute unrealized R-multiple at peak and trough using `(price − fill) / (fill − stop)`.
- Bucket by max-R: **direct-to-stop** (< +0.3R), **bounce-then-fail** (+0.3R to < +1.0R), **near-win-then-fail** (≥ +1.0R).
- For named directive cases (ATRA 5/11 13:52, LESL 5/15 16:53, ATRA 5/11 18:30), explicitly check whether intraday tag of +0.3R/+0.5R/+1.0R ever occurred.

### 3.2 — Time-of-day buckets

- Bucket every WB P&L fill (5/11–5/15, 22 fills) into PM (pre-09:30 ET), RTH (09:30–16:00), EH (16:00–19:55).
- Per bucket: count, wins, win rate, net P&L, average $/fill.
- Sub-bucket EH into early-EH (16:00–17:29) and late-EH (17:30–19:55).
- Flag fills bounded by force-exit at 19:55 vs. fills stopped out before 19:55.

---

## 3. Per-trade unrealized-R table (Hypothesis 3.1)

Tick-walk results, all 18 stop-hit WB losers, 5/11–5/15. `R$` = entry−stop (long). `max_R` = unrealized R at peak. `min_R` = unrealized R at trough. `sec→max` = seconds from entry to peak. `sec→stop` = seconds from entry to first stop breach (`None` = stop never breached on ticks before scheduled exit / force-exit hit instead).

| Date | Sym | Time ET | Setup | Fill | Stop | R$ | Peak | max_R | Trough | min_R | sec→max | sec→stop | Bucket |
|------|-----|---------|-------|------|------|------|--------|-------|--------|-------|---------|----------|--------|
| 5/11 | ATRA | 13:52 | A | 8.4700 | 8.3491 | 0.121 | 8.4700 | **+0.00** | 8.3600 | −0.91 | 0 | — | direct |
| 5/11 | ATRA | 18:30 | A | 9.4900 | 9.2867 | 0.203 | 9.5900 | **+0.49** | 9.3700 | −0.59 | 28 | — | bounce |
| 5/12 | ENSC | 08:16 | A | 0.3291 | 0.3215 | 0.0076 | 0.3291 | **+0.00** | 0.3210 | −1.07 | 0 | 198 | direct |
| 5/12 | SST  | 11:20 | A | 3.9400 | 3.8420 | 0.098 | 3.9400 | **+0.00** | 3.8400 | −1.02 | 0 | 81 | direct |
| 5/12 | ENSC | 14:54 | A | 0.3354 | 0.3311 | 0.0043 | 0.3372 | **+0.42** | 0.3301 | −1.23 | 73 | 197 | bounce |
| 5/12 | TRAW | 15:17 | A | 1.8200 | 1.8000 | 0.020 | 1.8200 | **+0.00** | 1.8000 | −1.00 | 0 | 41 | direct |
| 5/13 | ENSC | 11:53 | A | 0.3011 | 0.2948 | 0.0063 | 0.3011 | **+0.00** | 0.2944 | −1.06 | 0 | 414 | direct |
| 5/15 | LESL | 16:53 | A | 3.0900 | 3.0130 | 0.077 | 3.0900 | **+0.00** | 3.0100 | −1.04 | 0 | 200 | direct |
| 5/12 | TRAW | 05:31 | B | 2.0400 | 2.0150 | 0.025 | 2.0400 | **+0.00** | 2.0100 | −1.20 | 0 | 757 | direct |
| 5/12 | ODYS | 05:48 | B | 4.7000 | 4.6780 | 0.022 | 4.7000 | **+0.00** | 4.6700 | −1.36 | 0 | 9 | direct |
| 5/12 | XOS  | 06:29 | B | 2.0500 | 2.0350 | 0.015 | 2.0500 | **+0.00** | 2.0300 | −1.33 | 0 | 49 | direct |
| 5/12 | FATN | 11:41 | B | 3.6200 | 3.5710 | 0.049 | 3.6300 | **+0.20** | 3.5400 | −1.63 | 580 | 1157 | direct |
| 5/12 | FATN | 12:26 | B | 3.5800 | 3.5510 | 0.029 | 3.5800 | **+0.00** | 3.5500 | −1.03 | 0 | 37 | direct |
| 5/12 | ATRA | 13:51 | B | 10.0300 | 9.9950 | 0.035 | 10.0300 | **+0.00** | 9.9400 | −2.57 | 0 | 19 | direct |
| 5/15 | ONDG | 14:07 | B | 6.7300 | 6.6230 | 0.107 | 6.8700 | **+1.31** | 6.6100 | −1.12 | 365 | 1450 | **near-win** |
| 5/15 | PIII | 16:18 | B | 11.4000 | 11.0720 | 0.328 | 11.4000 | **+0.00** | 11.0700 | −1.01 | 0 | 117 | direct |
| 5/15 | LESL | 16:53 | B | 3.0900 | 3.0225 | 0.0675 | 3.0900 | **+0.00** | 3.0200 | −1.04 | 0 | 12 | direct |
| 5/15 | SLE  | 19:17 | B | 5.6100 | 5.5160 | 0.094 | 5.6100 | **+0.00** | 5.5300 | −0.85 | 0 | — (force-exit) | direct |

**Bucket distribution:**

| Bucket | Count | % of 18 |
|--------|-------|---------|
| Direct-to-stop (< +0.3R) | **15** | **83%** |
| Bounce-then-fail (+0.3R → +1.0R) | 2 | 11% |
| Near-win-then-fail (≥ +1.0R) | 1 | 6% |

### Per-named-case findings

- **ATRA 5/11 13:52 −$513:** filled $8.47, max tick = $8.47 flat. Peak R = 0.00. Direct.
- **LESL 5/15 16:53 −$735 (A):** filled $3.09, max tick = $3.09 flat. Peak R = 0.00. Direct.
- **ATRA 5/11 18:30 −$778 (EH):** filled $9.49, peak $9.59 at +28s (+0.49R), missed +0.5R trigger by $0.0017. +0.3R BE-stop would have armed and exited near BE; +0.5R BE-stop would not have armed.

### BE-rescue counterfactual

For the 3 non-direct-to-stop trades, simulating "arm BE at +0.3R, exit at fill":

| Trade | Actual | +0.3R BE outcome | $-Saved |
|-------|--------|------------------|---------|
| ATRA 5/11 18:30 | −$778 | exit ~$9.49 | ~$770 |
| ENSC 5/12 14:54 | −$519 | exit ~$0.3342 | ~$385 |
| ONDG 5/15 14:07 | −$1,198 | exit ~$6.72 | ~$1,140 |
| **Subtotal** | **−$2,495** | **~−$200** | **~$2,295** |

For the 15 direct-to-stop trades a tighter exit saves $0. A **+0.5R** rule rescues only ONDG (~$1,140). Across all 18 stop-hits (~−$15,693), a +0.3R BE-stop recovers 15% concentrated in 3 trades.

---

## 4. EH vs RTH bucket table (Hypothesis 3.2)

All 22 P&L fills 5/11–5/15 (excluding FCHL, MEI manual, ODYS overnights), bucketed by entry time:

| Bucket | n | Wins | WR% | Net P&L | Avg $/fill |
|--------|---|------|-----|---------|------------|
| PM (pre-09:30) | 4 | 0 | **0.0%** | −$3,220 | −$805 |
| RTH (09:30–16:00) | 13 | 3 | **23.1%** | −$4,681 | −$360 |
| EH (16:00–19:55) | 5 | 0 | **0.0%** | −$5,153 | −$1,031 |

**EH detail:**

| Date | Sym | Time | Setup | Outcome | P&L | Force-exit bounded? |
|------|-----|------|-------|---------|------|---------------------|
| 5/11 | ATRA | 18:30 | A | L (stop) | −$778 | No (stopped 13m in) |
| 5/15 | PIII | 16:18 | B | L (stop) | −$1,628 | No (stopped 3m in) |
| 5/15 | LESL | 16:53 | A | L (stop) | −$735 | No (stopped 7m in) |
| 5/15 | LESL | 16:53 | B | L (stop) | −$1,299 | No (stopped 13m in) |
| 5/15 | SLE  | 19:17 | B | L (force-exit) | −$713 | **Yes** — slippage-bounded at 19:55 |

**EH sub-buckets:**

| Sub-bucket | n | Wins | WR% | Net P&L |
|------------|---|------|-----|---------|
| Early-EH (16:00–17:29) | 3 | 0 | 0.0% | −$3,662 |
| Late-EH (17:30–19:55) | 2 | 0 | 0.0% | −$1,491 |

---

## 5. Findings — Hypothesis 3.1

- **15 of 18 stop-hit losers (83%) never tagged +0.3R — they went from entry tick straight to stop.** 5 of those reached stop in under 1 minute (ODYS 5/12 05:48: 9s; ATRA 5/12 13:51: 19s; FATN 12:26: 37s; TRAW 15:17: 41s; XOS 06:29: 49s).
- **13 of 18 had max_R = exactly 0.00** — price literally never exceeded the fill tick.
- **Only ONDG 5/15 14:07 qualifies as "near-win-then-fail" (+1.31R, peak at +6min).** A +0.5R BE-stop would have saved ~$1,140 here. N=1.
- The two bounce trades (ATRA 5/11 18:30 +0.49R; ENSC 5/12 14:54 +0.42R) **miss a +0.5R trigger by a hair**. A +0.3R BE-stop catches both, saving ~$1,155 combined.
- **Aggregate +0.3R BE-stop rescue: ~$2,295 of ~$15,693 stop-hit losses (15%), entirely concentrated in 3 of 18 trades.** The other 15 save $0.
- The 15 direct-to-stop trades share a clean signature: the entry tick was at or near the local high — these are entries placed into immediate sellers, not trades that went bad.

### Falsification check — 3.1

Hypothesis 3.1 required "most losers" to bounce ≥ +0.3R. Observed: 17% do; 83% don't. **Rejected.** This restates the WB audit's structural finding: **entries are the defect, not exits.** Tightening exits recovers a small backward-looking tail and risks chopping legitimate winners that dip below BE-arm in normal noise. Faster exits are not the lever.

---

## 6. Findings — Hypothesis 3.2

- **EH WR = 0/5 = 0.0%; RTH WR = 3/13 = 23.1%.** Delta = −23.1pp, 13pp outside the directive's 10pp tolerance.
- **PM WR also 0/4.** PM + EH = 9 fills, 0 wins, −$8,373.
- **Force-exit bounded exactly 1 of 5 EH fills** (SLE 5/15 19:17, exited −0.85R = −$713). The other 4 stopped pre-19:55 — force-exit was irrelevant. Force-exit caps the FCHL-class tail; it does not rehabilitate EH P&L distribution.
- LESL 5/15 16:53 lost on **both** setups simultaneously — EH variance is correlated across setups, not diversifying.
- Audit's already-stripped −$1,804 EH-excl-FCHL figure is the post-force-exit steady-state. EH is structurally negative under the production gate stack.

### Falsification check — 3.2

EH WR (0%) is 23pp below RTH WR (23%) — well outside the 10pp tolerance. **Rejected.** Force-exit bounds the catastrophic tail but not the median EH entry.

### Direct answer — should `WB_DISABLE_EXTENDED_HOURS_ENTRY` be reverted to `=0`?

**No.** Keep the block on. The clarification's premise ("force-exit makes EH safe") is unsupported: force-exit mattered on 1/5 EH fills and EH WR is still 0%. Force-exit is a tail-cap, not an edge-restorer. Recommend `WB_DISABLE_EXTENDED_HOURS_ENTRY=1` through at least 5/29; re-evaluate only after 2+ weeks of clean paper data show EH > 20% WR.

Caveat: n=5 is small. The directive set the 10pp bar with that in mind; EH misses by 13pp.

---

## 7. Falsification checks — summary

| Hypothesis | Predicted | Observed | Verdict |
|------------|-----------|----------|---------|
| 3.1 — losers had positive windows; faster exits convert losses to scratches | majority bounce ≥ +0.3R before stop | 17% bounce ≥ +0.3R; 83% direct-to-stop | **Rejected** — exits don't help, entries are the problem |
| 3.2 — EH wins at within 10pp of RTH under force-exit | |WR_EH − WR_RTH| ≤ 10pp | WR_EH = 0%, WR_RTH = 23%, delta = 23pp | **Rejected** — keep EH block |

---

## 8. Proposed actions

1. **Do not add a +0.5R or +0.3R BE-stop rule.** (**High confidence.**) +0.5R saves only ONDG (~$1,140, 1 trade). +0.3R saves ~$2,295 (3 trades, $1,140 of which is ONDG) but is dangerously close to normal small-cap noise and would chop winners that dip below BE-arm. Both rules optimize for a backward-looking 1-trade outlier.

2. **Keep `WB_DISABLE_EXTENDED_HOURS_ENTRY=1`.** (**High confidence on dataset; medium overall given n=5.**) EH is 0/5 WR, force-exit only mattered on 1/5, dollar-loss-per-fill is 2.9× RTH. Block stays through at least 5/29.

3. **Reinforce WB audit's structural finding: entries are the problem, not exits.** (**High confidence.**) Prioritize Investigation 2 (loser behavioral profile) and Investigation 4 (winner template) over any further exit-side mechanic.

4. **Consider a parallel PM block (pre-09:30 ET).** (**Medium confidence.**) PM is also 0/4, −$3,220. Combining EH + PM blocks eliminates 9 of 22 fills (~$8,373 of losses) with zero winners forfeited. Tighten WB to an RTH-only gate, or push the ≥12 ET floor recommended in the audit.

5. **Investigation 3's headline answer to "do losers rescue by tighter exits?": NO.** (**High confidence.**) WB needs entry-side gates, not exit-side ones.

---

## 9. Limitations

- **n=18 stop-hit losers (3.1); n=5 EH fills (3.2).** Single-trade contributions move buckets 5–20pp. Falsification thresholds were set with small-sample awareness; 2 more weeks would harden conclusions.
- **Tick-walk approximates the bot's bar-internal exit decision.** Walk uses every tick; bot may delay stop-firing by a few ticks for dollar-cap escalation. Affects $-saved estimates by ~±$50–100/trade, not bucket assignment.
- **Force-exit only landed Saturday 5/16.** SLE 5/15 19:17 is the sole fill that benefited; inferences about force-exit generalizing rest on n=1.
- **The 15 direct-to-stop trades are method-robust** — max_R = 0.00 means price literally never exceeded fill. That subset (entries are the defect) is the strongest finding in this report.
- **BE-rule counterfactuals assume zero exit slippage.** Penny-spread small-caps could slip 1–3 cents, reducing rescue estimates by ~30–40%.
- **MEI, FCHL, ODYS-overnight excluded per directive.** Including FCHL shifts EH P&L by −$13,453 but does not change WR or bucket distribution.
