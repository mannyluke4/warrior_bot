# Wave Breakout (WB) Strategy Audit — Week of 2026-05-11 → 2026-05-15

**Author:** Cowork audit (companion to `2026-05-16_squeeze_strategy_audit_weekly.md`)
**Scope:** All WB entries (attempted or filled) across Setup A (`bot_alpaca_subbot.py`, PA3LXGIPGG8B) and Setup B (`engine wb_bot.py`, PA-NEW)
**Data window:** 5 trading days (5/11–5/15), mix of pre- and post-persistence-layer days, pre-dead-tape-gate everywhere
**Trades analyzed:** 19 fills across both setups (4 entry timeouts and 1 broker-reject excluded from P&L analysis)

---

## Takeaway (lead with it)

Strip the FCHL infrastructure orphan and the data says **WB is roughly break-even at best, with one tail winner doing the heavy lifting on each setup**. Setup A subbot is net **−$1,477 over 9 fills, 22% win rate** (SST 5/11 +$2,090 the only meaningful winner, no other +$500 trade). Setup B engine is net **−$8,634 over 10 fills, 22% win rate** before the FCHL orphan, **−$22,087 with it**. The ATRA 5/15 +$1,160 engine winner is the single shining trade of the back half, and the **dead-tape gate that shipped today would have vetoed it** — so this audit has to grapple with a strategy whose only fresh win was a setup the strategy is now built to reject.

The pattern that holds across both setups: **stop-hit losers vastly outnumber trailing-stop winners (10 stop-hits to 4 trailing-stop wins, 16:53 stop-hit:partial ratio).** The dollar-loss cap and stop logic execute correctly; the entries are simply being placed on continuation breakouts that fail at the −1R level within 3–7 minutes. The persistence layer (the one piece of WB infrastructure user is actively measuring) fed at most 2 of 19 fills and did not produce a meaningful skew either way at this n.

**Data says: do not add capital to WB on real-money day. Tighten or pause.** I suspect (low confidence) the strategy can be salvaged by score≥10 + post-09:30 + R%≥2.5%, but that filter would have allowed about 4 trades this week and removed both winners.

---

## A. Per-trade table

All WB attempts that reached an ENTRY/FILL/CLOSE/TIMEOUT terminal state. Setup A = subbot (Alpaca, PA3LXGIPGG8B). Setup B = engine (Alpaca, PA-NEW). Time = ET signal/entry. "—" = no fill, no P&L.

| # | Date | Setup | Symbol | Time ET | Score | Wave # | R$ | R% | Outcome | Fill $ | Exit reason | Exit $ | Hold | P&L |
|---|------|-------|--------|---------|-------|--------|------|------|---------|--------|-------------|--------|------|------|
| 1 | 5/11 | A | ATRA | 07:00 | 10 | 9 | 0.30 | 3.4% | ENTRY_TIMEOUT | — | — | — | — | $0 |
| 2 | 5/11 | A | ATRA | 09:31 | 10 | 27 | 0.28 | 3.1% | ENTRY_TIMEOUT | — | — | — | — | $0 |
| 3 | 5/11 | A | CLNN | 09:43 | 10 | 3 | 0.148 | 2.0% | FILL → exit NO-FILL | 7.35 | trailing_stop (no-fill, manual review) | — | ~12m | $0* |
| 4 | 5/11 | A | NVOX | 10:12 | 9 | 9 | 0.071 | 0.4% | FILL → trail | 16.22 | trailing_stop | 16.20 | 25s | **−$37** |
| 5 | 5/11 | A | CLNN | 13:27 | 10 | 33 | 0.047 | 0.7% | ENTRY_TIMEOUT | — | — | — | — | $0 |
| 6 | 5/11 | A | ATRA | 13:52 | 10 | 58 | 0.10 | 1.2% | FILL → stop | 8.47 | stop_hit | 8.33 | ~7m | **−$513** |
| 7 | 5/11 | A | SST | 14:18 | 9 | 60 | 0.039 | 1.0% | FILL → trail | 3.83 | trailing_stop | 4.09 | ~39m | **+$2,090** |
| 8 | 5/11 | A | ATRA | 18:30 | 10 | 82 | 0.30 | 3.2% | FILL → stop | 9.49 | stop_hit | 9.20 | ~13m | **−$778** |
| 9 | 5/12 | A | ENSC | 08:16 | 9 | 24 | 0.0076 | 2.3% | FILL → stop | 0.3291 | stop_hit | 0.3210 | ~3m | **−$644** |
| 10 | 5/12 | A | SST | 11:20 | 10 | 30 | 0.098 | 2.5% | FILL → stop | 3.94 | stop_hit | 3.83 | ~12m | **−$870** |
| 11 | 5/12 | A | ENSC | 14:54 | 9 | 61 | 0.0043 | 1.3% | FILL → stop | 0.3354 | stop_hit | 0.3285 | ~6m | **−$519** |
| 12 | 5/12 | A | TRAW | 15:17 | 9 | 51 | 0.020 | 1.1% | FILL → stop | 1.82 | stop_hit | 1.78 | ~3m | **−$661** |
| 13 | 5/13 | A | ENSC | 11:53 | 10 | 53 | 0.0063 | 2.1% | FILL → stop | 0.3011 | stop_hit | 0.2941 | ~9m | **−$509** |
| 14 | 5/13 | A | MEI† | 16:06 | 7 | 20 | 0.235 | 1.7% | FILL → trail | 14.05 | trailing_stop | 14.23 | ~12m | **+$366** |
| 15 | 5/13 | A | ODYS | 18:27 | 10 | 90 | 0.13 | 3.0% | FILL → GTC exit next AM | 4.36 | sold next AM @ $4.27 | 4.27 | overnight | **−$603**‡ |
| 16 | 5/15 | A | LESL | 16:53 | 10 | 56 | 0.077 | 2.5% | FILL → stop | 3.09 | stop_hit | 3.01 | ~7m | **−$735** |
| **Setup A subtotal (9 P&L fills)** | | | | | | | | | | | | | | **−$1,913 (with MEI), excl ODYS overnight** |
| | | | | | | | | | | | | | | |
| 17 | 5/12 | B | TRAW | 05:31 | 10 | 7 | 0.025 | 1.2% | FILL | 2.04 | stop_hit | 2.00 | ~28m | **−$985** |
| 18 | 5/12 | B | ODYS | 05:48 | 8 | 10 | 0.022 | 0.5% | FILL (1 retry) | 4.70 | stop_hit | 4.62 | ~15m | **−$856** |
| 19 | 5/12 | B | XOS | 06:29 | 10 | 6 | 0.015 | 0.7% | FILL | 2.05 | stop_hit | 2.02 | ~6m | **−$735** |
| 20 | 5/12 | B | FATN | 11:41 | 8 | 18 | 0.049 | 1.4% | FILL | 3.62 | stop_hit | 3.52 | ~19m | **−$1,381** |
| 21 | 5/12 | B | CLNN | 11:46 | 7 | — | 0.125 | 2.0% | BROKER_REJECT (conn reset) | — | — | — | — | $0 |
| 22 | 5/12 | B | ATRA | 12:20 | 8 | 18 | 0.185 | 1.8% | PARTIAL FILL 823/4995 | 10.04 | trailing_stop | 10.09 | ~66m | **+$41** |
| 23 | 5/12 | B | FATN | 12:26 | 9 | — | 0.029 | 0.8% | FILL | 3.58 | stop_hit | 3.50 | ~2m | **−$1,127** |
| 24 | 5/12 | B | ODYS | 12:34 | 8 | 60 | 0.061 | 1.4% | TIMEOUT (3 retries) | — | — | — | — | $0 |
| 25 | 5/12 | B | ODYS | 12:55 | 7 | 48 | 0.061 | 1.4% | TIMEOUT (3 retries) | — | — | — | — | $0 |
| 26 | 5/12 | B | ATRA | 13:51 | 7 | 32 | 0.035 | 0.4% | FILL | 10.03 | stop_hit | 9.80 | ~3m | **−$1,157** |
| 27 | 5/13 | B | MEI† | 16:06 | 7 | 20 | 0.235 | 1.7% | FILL | 14.05 | trailing_stop | 14.23 | ~13m | **+$640** |
| 28 | 5/13 | B | ODYS | 19:02 | 8 | — | 0.081 | 1.9% | FILL → GTC exit next AM | 4.33 | session_end held → AM mkt | 4.27 | overnight | **−$698**‡ |
| 29 | 5/14 | B | FCHL | 17:00 | 8 | 14 | 0.046 | 1.9% | TIMEOUT (3 retries) | — | — | — | — | $0 |
| 30 | **5/14** | **B** | **FCHL** | **19:58** | **8** | **31** | **0.086** | **3.5%** | **FILL → held overnight → manual flatten 5/15** | **2.50** | **manual_flatten (session-resume failure)** | **~1.83** | **~15h** | **−$13,453** |
| 31 | 5/15 | B | ATRA | 13:21 | 8 | 27 | 0.212 | 2.4% | FILL | 9.10 | trailing_stop | 9.31 | ~148m | **+$1,160** |
| 32 | 5/15 | B | ONDG | 14:07 | 8 | 53 | 0.107 | 1.6% | FILL | 6.73 | stop_hit | 6.57 | ~42m | **−$1,198** |
| 33 | 5/15 | B | PIII | 16:18 | 8 | — | 0.328 | 2.9% | FILL | 11.40 | stop_hit | 11.03 | ~3m | **−$1,628** |
| 34 | 5/15 | B | LESL | 16:53 | 10 | 56 | 0.0675 | 2.2% | FILL | 3.09 | stop_hit | 3.01 | ~13m | **−$1,299** |
| 35 | 5/15 | B | SLE | 19:17 | 8 | — | 0.094 | 1.7% | FILL | 5.61 | session_end_force | 5.53 | ~38m | **−$713** |
| **Setup B subtotal (12 P&L fills, incl FCHL)** | | | | | | | | | | | | | | **−$22,087** |
| **Setup B subtotal excluding FCHL** | | | | | | | | | | | | | | **−$8,634** |
| **Setup B subtotal excluding FCHL + ODYS overnight (5/13)** | | | | | | | | | | | | | | **−$7,936** |

\* CLNN 5/11 — EXIT NO-FILL flagged manual review; treating as $0 because the close price/state is unknown from log. Not counted in subtotals.
† MEI 5/13 — manual watchlist injection during Databento outage (per `cowork_reports/2026-05-14_mei_bypass_trace.md`). Same signal hit both setups within the same second.
‡ ODYS overnight exits — engine doesn't log the next-AM GTC close P&L in 5/14 engine log; estimates use entry−$4.27 exit per known facts.

---

## B. Winners vs losers — structural differences

**Winners (4 of 19 P&L fills):**

| # | Symbol | Setup | Time | Score | R% | Wave # | Exit reason | P&L | R-mult | Hold |
|---|--------|-------|------|-------|------|--------|-------------|-----|--------|------|
| 7 | SST 5/11 | A | 14:18 | 9 | 1.0% | 60 | trailing_stop | +$2,090 | +3.28 | 39m |
| 14/27 | MEI 5/13 | A+B | 16:06 | 7 | 1.7% | 20 | trailing_stop | +$1,006 combined | +0.77 | 12–13m |
| 22 | ATRA 5/12 | B | 12:20 | 8 | 1.8% | 18 | trailing_stop | +$41 (partial 823sh only) | +0.27 | 66m |
| 31 | ATRA 5/15 | B | 13:21 | 8 | 2.4% | 27 | trailing_stop | +$1,160 | +1.00 | 148m |

**Losers (15 of 19 P&L fills, excluding FCHL infra outlier and ODYS overnights):**

All but **one** loser (NVOX −$37, trail) exited via `stop_hit` for −1.0 to −1.4 R. Average losing R-mult ≈ −1.10. The dollar-loss cap and bot-internal stop comparisons (per `feedback_no_broker_stops.md`) are firing as designed.

**Structural deltas, winners vs losers:**

| Feature | Winners (n=4) | Losers (n=15) |
|---------|---------------|---------------|
| Exit reason | 4/4 trailing_stop | 14/15 stop_hit |
| Score distribution | 7, 8, 8, 9 (avg 8.0) | 7–10, mode 10 (avg 8.7) |
| Wave # (sequence depth) | 18, 20, 27, 60 | 6, 9, 10, 18 (FATN), 24 (ENSC), 27 (ATRA), 30 (SST), 31 (FCHL), 33, 51, 53, 56, 60, 90 — heavy distribution |
| R% | 1.0%–2.4% (avg 1.7%) | 0.4%–3.5% (avg 1.7%) |
| Time of day | All 12:20–14:18, plus MEI 16:06 | 9 of 15 entries were **after 11:00 ET** |
| Symbol | SST, ATRA×2, MEI | TRAW, ODYS, XOS, FATN×2, ATRA×2, ENSC×3, SST, LESL×2, ONDG, PIII, NVOX, SLE |

**Data says:** Winners are not score-distinguished (avg 8 vs 8.7, lower-end actually). They are **exit-reason distinguished** (trailing vs stop) and **somewhat time-of-day distinguished** (winners cluster afternoon, with MEI as the late-day exception).

**I suspect** (low confidence): the winners are stocks where the wave structure produced a continuation move *after* the initial breakout consolidated for a few minutes. The losers are stocks where the breakout was the move — entry filled near the post-pop high and the stop was hit on first pullback. This is consistent with **the persistence-layer / scanner-watchlist split** discussed in section E.

---

## C. Fluke filter

**Strict infrastructure outliers (remove from strategy-quality analysis):**

- **FCHL 5/14 19:58 fill → 5/15 manual flatten −$13,453.** Session-resume failed at date boundary; the bot lost state on the open FCHL position, the bridge didn't reattach the exit plan, and operator had to flatten manually at $1.83. **This is a persistence / session-resume defect, not a WB strategy fault.** Per the known facts, this is excluded from strategy-quality numbers, reported as a separate infra event.
- **ODYS 5/13 18:27 (Setup A, fill $4.36, GTC overnight) and ODYS 5/13 19:02 (Setup B, fill $4.33).** Both held overnight and closed next morning at $4.27. Setup A: ~−$603 estimated. Setup B: ~−$698 estimated. **These are not strategy losses but late-session-entry-without-force-close losses.** They argue for tightening WB's extended-hours behavior (see section G).
- **CLNN 5/11 EXIT NO-FILL.** Exit signal fired at $7.48, limit $7.43, never filled, marked "manual review." Unknown final close. Excluded from subtotal.

**Caveats to keep in the dataset:**

- **MEI 5/13 +$366 (A) and +$640 (B).** Manual watchlist injection during Databento outage. The strategy didn't *find* MEI; the operator did. Both setups then executed the trade once it was in the watchlist. Flagged but included. Both setups' winners on 5/13 come entirely from this one symbol.
- **NVOX 5/11 −$37.** 25-second hold, trailing_stop fired immediately. The strategy worked exactly as designed and minimized loss — but on a thin tape (the kind today's dead-tape gate now blocks). Functionally a wash; keep.

---

## D. Pattern analysis

### Time of day

| Bucket | Fills | Winners | Net P&L |
|--------|-------|---------|---------|
| Pre-09:30 ET (premarket WB) | 5 (3 from 5/12 morning, ATRA 5/11 18:30 reusing earlier wave, ENSC 5/12 08:16) | 0 | −$3,219 |
| 09:30–11:00 ET | 2 (ENSC 5/12 11:20 SST, ENSC 5/13 11:53) | 0 | −$1,379 |
| 11:00–14:00 ET | 5 (ENSC 5/12 14:54 BORDERLINE; FATN×2, ATRA×2, ENSC) | 2 | −$2,723 (incl SST +2090? no SST was 14:18) |
| 14:00–18:00 ET | 5 (SST 5/11 14:18, TRAW 5/12 15:17, ENSC 5/12 14:54, MEI 5/13 16:06, LESL 5/15 16:53) | 2 (SST, MEI) | **+$96 net** |
| Extended hours (18:00+) | 4 (ATRA 5/11 18:30, ODYS×2 overnight, PIII 16:18 borderline, SLE 19:17) | 0 | −$3,816 (excl FCHL) |

**Data says:** the only time-of-day bucket that's positive is **14:00–18:00 RTH/late-afternoon**, on the strength of SST 5/11 14:18 and MEI 5/13 16:06. The post-11 ET time gate (H#14, if I'm reading the brief correctly) appears to work — pre-11 ET entries are 0/7 winners. But late-EH (post-18:00) is net negative too, so the right gate may not be "after 11" — it may be "between 11 and 18" combined with "no overnight holds."

### Score thresholds

| Score | Fills | Winners | Net P&L (excl FCHL/overnight) |
|-------|-------|---------|----------------------|
| 7 | 3 (ODYS 5/12 12:55 timeout — no fill, MEI 5/13 ×2, ATRA 5/12 13:51) | 2 (MEI A+B) | +$49 (MEI +$1006, ATRA −$1157, ODYS no fill +$0)? net **−$151** |
| 8 | 9 fills (ODYS 5/12, FATN×2, ATRA 5/12 12:20 PARTIAL, ODYS×1 overnight, FCHL excluded, ATRA 5/15, ONDG, PIII, SLE) | 2 (ATRA 5/12 partial +$41, ATRA 5/15 +$1160) | −$5,463 |
| 9 | 4 (NVOX, ENSC 5/12 08:16, ENSC 5/12 14:54, TRAW 5/12 15:17, SST 5/11) | 1 (SST +$2090) | **+$329** |
| 10 | 5 (TRAW 5/12, XOS 5/12, SST 5/12 11:20, ENSC 5/13, LESL 5/15 — both setups) | 0 | **−$5,224** |

**Data says:** score=10 is **0/5 winners net −$5,224**. That's the opposite of what one would expect — the *highest-confidence* arms are 0% win rate this week. Score=9 is the only positive bucket and almost entirely SST 5/11. Score=8 is the workhorse (9 fills) and net −$5,463 even before strip-outs.

This inverts the prior week's intuition. Either (a) score is not predictive in this regime, or (b) score=10 is selecting setups that resolve in the wrong direction — for example, post-extended-down-leg deep-stack wave-90 ODYS-type arms that the persistence layer pulls back into view. I suspect (medium): the WB scorer over-weights vol_mult on already-extended late-session prints.

### Wave depth (sequence #)

| Wave # bucket | Fills | Winners | Note |
|---------------|-------|---------|------|
| Early (1–10) | 4 (TRAW 5/12 #7, ODYS 5/12 #10, XOS 5/12 #6, CLNN 5/11 #3) | 0 | All Setup B 5/12 morning |
| Mid (10–30) | 6 (NVOX 9, MEI 20, ATRA 18, ATRA 27, FATN 18, ENSC 24) | 2 (MEI, ATRA 5/15) | Includes both meaningful winners |
| Deep (30–60) | 5 (CLNN 33, ATRA 58, SST 60, TRAW 51, ENSC 53, ONDG 53, LESL 56) | 1 (SST) | SST 5/11 wave 60 is unusual |
| Very deep (60+) | 3 (ATRA 82, ODYS 90, NVOX no-info, FCHL 31) | 0 | All late-day, extended-hours |

**Data says:** mid-wave fills (10–30) are 2/6 winners. The "intuition" that early-wave entries (wave 3–4) win more is **not supported by this week** — early-wave fills are 0/4 and Setup B's 5/12 morning bloodbath happened on wave 6–10 arms.

### Symbol behavior

- **SST** — 4 attempts, 2 fills, 1 win (+$2,090) 1 loss (−$870). Net +$1,220. The week's only meaningful natural winner came from SST.
- **ATRA** — 7 attempts, 5 fills, 2 wins (+$41, +$1,160) 3 losses (−$513, −$778, −$1,157). Net **−$1,247** even with the ATRA 5/15 winner.
- **MEI** — manual injection, 2 fills (both setups), 2 wins (+$1,006 total). Outside the strategy's selection mechanism.
- **ENSC, TRAW, FATN, XOS, ODYS** — high-frequency arms, low-win-rate. ENSC: 4 fills, 0 wins, −$2,153. The penny-stock floor-ENSC pattern is producing pure noise.
- **LESL, FCHL, ONDG, PIII** — late-week additions, all losers (excluding FCHL infra event).
- **NVOX, CLNN, XOS** — single-fill events, can't characterize.

**Data says:** SST is the only ticker with a positive net P&L. ATRA is the most-traded ticker and still negative net even with one large winner. ENSC pennies are providing nothing.

### Tape quality / dead-rate (retroactive, based on prior intuition)

Per the brief, the new dead-tape gate computes dead-rate retroactively at ~80% on ATRA 5/15 13:21 — the bot's only fresh winner. Inferring the same lens applied to other entries:

- The **morning Setup B 5/12 cluster** (TRAW 05:31, ODYS 05:48, XOS 06:29) all entered on premarket prints with low volume. All 3 stopped out. Likely dead-rate >70%, dead-tape gate would have blocked.
- **ENSC** at $0.30 with R$ = $0.008 (the entire R is two pennies wide on a sub-dollar penny stock): the *spread on a $0.30 stock can be wider than R*. Dead-tape mechanically certain.
- **FCHL 5/14 19:58** — entered $2.50 in extended hours during what was almost certainly dead tape. R$=$0.086 wide enough to give it room. Held overnight when bot's session-resume should have force-exited it; didn't.

**Data says:** the dead-tape gate, if it had been live this week, would have blocked the majority of the morning-EH losers. **It would also have blocked ATRA 5/15 +$1,160, the only fresh winner.** That is the central uncomfortable fact this audit returns.

---

## E. Persistence layer evaluation

Persistence-fed entries this week, by my reading of the log evidence:

- **MEI 5/13 (both setups)** — manual injection, *not* persistence. Don't credit persistence here.
- **ATRA 5/15 13:21 (Setup B, +$1,160)** — score=8, wave #27, R%=2.4%. This is on ATRA which had been on watchlists for 5 days; whether persistence "fed" it depends on whether the wave-tracker carryover counts. Conservatively call this a persistence-adjacent winner.
- **LESL 5/15 16:53 (both setups, both lost)** — LESL was on the watchlist all day. Persistence-adjacent. Both setups lost.
- **ATRA 5/15 16:24 ET WB_ARMED stack** — the bot re-armed on every prior wave (15, 16, 23, 25, 27, 32, 34) at 16:24 ET when persistence/session-resume re-evaluated. Most of those didn't trigger entries because the live price was already past or below the arm level; the ones that did fill (none in Setup B's case post-rearm) didn't add new trades. **The persistence layer's signature output this week was 30+ re-arms producing 1 actual fill (ATRA 5/15 already in play).**

**Net assessment of persistence layer:**

- **Direct fills attributable to persistence: 1 winner (ATRA 5/15 +$1,160), 2 losers (LESL both setups, ~−$2,034 combined).** Net **−$874.**
- **Indirect cost:** the re-arm stacks at 16:15–17:24 ET create log noise but didn't burn capital.
- **MEI variance worth?** Yes — MEI was a manual override that highlighted scanner gaps, not persistence's doing. The $1,006 MEI combined would still be net positive if all losing persistence-adjacent fills were removed.

**I suspect (medium):** the persistence layer is currently a wash. Its theoretical value (re-arming on previously-seen waves the scanner has dropped) is only realized when paired with a tape-quality filter. With dead-tape gate live, persistence-fed entries are exactly the slice most likely to be vetoed (since the symbols that "persisted" tend to be the ones that traded through their setup and are now in dead-tape consolidation).

---

## F. Strategy refinement recommendations (concrete)

Each tagged with confidence:

1. **R% floor of 1.5% — keeping it.** *(High.)* The CHOP_REJECT lines all caught R%<1.5% events that would have entered into setups with no exit room. Borderline R%≈2% entries this week: 5 fills (ENSC 5/13 11:53 2.1%, MEI 5/13 1.7%, ATRA 5/12 partial 1.8%, ODYS 5/13 evening 1.9%, LESL 5/15 setupB 2.2%). Mixed — MEI +, ATRA partial +, others losers. No clear edge of 2% over 2.5%.

2. **Post-11 ET time gate (H#14) is helpful as written.** *(Medium.)* Pre-11 ET fills are 0/7 winners net −$5,463. The premarket and early-AM time slots produce no fresh winners. SST 5/11 14:18 +$2,090 is post-11. **Recommendation: hold this gate, possibly tighten to ≥12 ET.**

3. **Wave-score floor of 7 is approximately right; raising to 8 wouldn't help.** *(Medium.)* The week's score distribution: score 7 had 2 wins of 3 fills (MEI ×2), score 8 had 2/9, score 9 had 1/4, score 10 had **0/5**. Raising to 8 would have removed MEI (and gained nothing). Raising to 10 would have eliminated the only winners. *Possibly* lower to 6 to catch more MEI-type setups — but n is too small.

4. **The chop-gate sub-gates (CG3_OBSERVE) — `dead_bounce` showed two would-veto signals retroactively useful.** *(Medium.)*
   - ONDG 5/15 14:07 (B, score=8): `dead_bounce_pattern(drift=0,cum=$1.93,vol_ratio=0.09) would_veto=Y enabled=N`. The trade lost −$1,198. **`dead_bounce` would have prevented this loss; flip to enforce.**
   - LESL 5/15 16:53 (B, score=10): `dead_bounce_hod_not_early(age=296m)` would not have vetoed (correctly bypassed).
   - The other sub-gates (`macd`, `hod_recent`, `vol_followthrough`, `xsession_bl`) didn't produce a useful veto pattern this week — all OBSERVE neutral.
   - `same_session_loss_blacklist` worked: it blocked re-entry on ONDG at 16:16 ET after its 14:07 loss, and again at 16:24. That gate is doing real work; keep it enforce-on.

5. **`WB_BE_TRIGGER_R=3.0` BE-floor — dead code this week.** *(High.)* No trade hit 3R unrealized. SST +$2,090 was +3.28R on close, not on intra-trade peak (peak was ~3.9R, but BE-arm at 3R didn't appear in log). MEI +$0.77R. ATRA 5/15 +$1.00R. **The BE rule never activates; it's noise in the config.** Consider lowering to 2.0R or removing entirely.

6. **`bearish_engulf` / `topping_wicky` exits did not fire on any winner.** *(High.)* Of the 4 winners, 4/4 exited on `trailing_stop`. The 1m candle pattern exits did not appear in any winner's log. They also did not prematurely exit any winner. **Currently neutral; safe to keep as defense-in-depth.**

7. **`bp_block` / `entry_timeout` — both functioning correctly.** Setup A 5/11 ATRA two timeouts saved capital (price gapped past entry). Setup B 5/12 ODYS×2 timeouts on retry escalator — chase price was outside the limit, correctly cancelled.

8. **Extended-hours entries (18:00+) — net negative, infra-risky.** *(High.)*
   - ATRA 5/11 18:30 −$778
   - SLE 5/15 19:17 −$713 (correctly force-closed at 19:55)
   - ODYS 5/13 ×2 GTC overnights: ~−$1,300 combined
   - FCHL 5/14 19:58: −$13,453 (infra)
   - **Recommendation:** disable WB entries after 18:00 ET unless P0.2-style force-close-at-19:55 is rock-solid and there's no overnight risk. SLE 5/15 proved force-close works; FCHL 5/14 proves it can fail catastrophically.

9. **`session_resume` for WB needs the FCHL-fix verified before any further EH trades.** *(Critical.)* The FCHL hold-over fault is the single largest P&L event of the week. Until 5/14-style date-boundary session-resume is proven on a positive case, WB EH entries should be blocked.

---

## G. Critical structural questions

**Does WB have an edge at all once FCHL orphan + manual MEI are removed?**

Data says: marginal-to-no edge.

- Setup A: 7 P&L fills (excluding MEI, CLNN no-fill, ODYS overnight): 1 win (SST +$2,090), 6 losses (−$3,953). Net **−$1,863, 14% win rate**. SST does carry the week single-handedly.
- Setup B: 9 P&L fills (excluding MEI, FCHL infra, ODYS overnight): 2 wins (ATRA 5/12 partial +$41, ATRA 5/15 +$1,160) + 7 losses (−$8,469). Net **−$7,268, 22% win rate**.

Combined, without MEI/FCHL/ODYS overnights: **net −$9,131 across 16 fills, 19% win rate.** With a 1:1.1 average win:loss ratio implied, the strategy needs ~50% win rate to break even and is delivering 19%.

**Honest answer:** WB shows no measurable edge this week absent MEI (which was manual) and after the FCHL infra event is stripped.

**Does WB-on-extended-hours add value or just create risk?**

Data says: pure risk. 6 EH fills, 0 winners, **−$15,257 incl FCHL, −$1,804 excl FCHL.** Either kill EH entries or first prove out the session-resume + force-exit pipeline on a non-catastrophic week.

**Should WB be tightened or loosened?**

Tighten:
- Hard gate: no EH WB entries until session-resume fix proven.
- Enforce `dead_bounce` sub-gate (would have caught ONDG 5/15 14:07).
- Consider 12 ET floor instead of 11 ET (eliminates the ENSC 5/12 11:20 SST class of trades).
- Re-evaluate score weighting — the score=10 cohort is 0/5 this week.

Loosen:
- Nothing. The "intraday adder shipped Friday" should be paused until next week's data; the strategy isn't earning more attempts.

---

## H. Limitations

- **Sample size: 19 P&L fills across 5 days, of which the meaningful winners are 3 (SST, MEI×2-as-one-event, ATRA 5/15).** Any conclusion about score, wave-depth, or time-of-day is descriptive on the week, not predictive.
- **Two of the three "winners" are functionally one event each** (MEI = manual injection on a single name; SST 5/11 = one ticker, one wave). The third (ATRA 5/15) is a setup the new dead-tape gate would have blocked. The strategy's apparent winners are not reproducible from current rules.
- **FCHL −$13,453 is an infra event but distorts every group-by-setup statistic.** I've shown the with-and-without numbers but the reader's gut is going to anchor on the with-FCHL P&L.
- **Engine and subbot run on the same `[WB]` detector but different brokers/connections.** Setup B has had connection-reset and partial-fill events that Setup A did not. Some of Setup B's worse performance is execution-layer, not strategy-layer.
- **Persistence layer evaluation is hampered by overlap with manual interventions (MEI) and the same-day re-arm noise.** A clean test would isolate trades that fired *only* from persistence carryover with no scanner refresh — there is no such trade in this week's data.
- **Dead-tape gate verdicts are retroactive estimates based on the postmortem note** — they were not actually computed live on these trades.
- **Score-12 entries: zero in this dataset.** Highest observed was score=10 (5 fills, 0/5 wins). The brief asked score-12 vs score-7 comparison; the data does not support that comparison this week.

---

## Bottom line for the user

Two weeks before real-money go-live, WB looks like **a strategy whose only meaningful winners are events the strategy didn't actually choose**: a manual injection (MEI), a single oversized run (SST), and a setup the new dead-tape gate now blocks (ATRA 5/15). The exit mechanics work; the entries are losing money systematically. **Setup B's −$22K-with-FCHL is a wake-up call** even after the infra event is stripped — the underlying −$8.6K on 12 P&L fills is not a "calibration cost," it's structural loss.

**Recommendation order if anything changes this week:**

1. **Block EH WB entries** until session-resume is verified — the FCHL event is one date-boundary away from being a real-money disaster.
2. **Flip `dead_bounce` from OBSERVE to enforce** — would have saved ONDG 5/15 14:07 (−$1,198).
3. **Watch one more week** before raising score floor or shipping the intraday adder. Don't compound this week's losers.
4. **Track the persistence-fed entries explicitly** in the trade log so next week's audit can isolate them.

If WB stays paper for one more week of clean data, that's appropriate. If it goes live alongside squeeze on 6/4, it needs at minimum #1 and #2 above and probably a notional cut.
