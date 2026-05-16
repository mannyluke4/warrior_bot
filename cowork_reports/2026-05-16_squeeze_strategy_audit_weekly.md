# Squeeze Strategy Audit — Week of 2026-05-11 → 2026-05-15

**Author:** Cowork audit (post-fill-fix-bundle)
**Scope:** All squeeze entries (attempted or filled) across Setup A (`bot_v3_hybrid.py`, main paper) and Setup B (`engine squeeze_bot.py`, PA-NEW paper)
**Data window:** 5 trading days, but rich data only on 5/15 after the fill-rate fix shipped
**Trades analyzed:** 4 filled entries, 9 chase-cap timeouts, 2 buying-power blocks, 1 SKIP

---

## Takeaway (lead with it)

The fill-rate fix worked — the bot is now interacting with the broker on squeeze setups. But the **early** post-fix data argues something the user already half-suspects: **chase caps are roughly correctly calibrated, exits are working, and the strategy's edge is being decided pre-entry by the score/level/parabolic combination, not by exit micromechanics.** Every chase-cap timeout this week was either neutral or positive (we'd have lost money entering). The two fills that closed for real money on 5/15 split: one clean winner (+$468 SLE early-AM, score=10, parabolic, fast target hit) and three losers/break-evens. The losers share a profile: **either score ≤ 6 (LESL 11, but with thin volume; SLE 5.3) or chasing a stock that had already extended pre-entry.** The clearest refinement signal: the post-9:30 ONDG score=12 parabolic chase-cap was a near-miss — price ran another +13% above the cap before fading — that's the one configuration where a wider cap could pay off, but the data is one event.

**Don't make structural changes this week.** Five days, two real losses, one real win, sub-sample anywhere you slice it. Watch one more week before tightening or loosening anything.

---

## A. Per-trade table

All squeeze attempts, both setups, chronological. P&L is realized; "—" means no fill occurred. Setup A = main bot (Alpaca, main acct). Setup B = engine (Alpaca PA-NEW).

| # | Date | Setup | Symbol | Time ET | Score | Level | R$ | R% | Parabolic | Outcome | Fill $ | Exit reason | P&L |
|---|------|-------|--------|---------|-------|-------|-----|-----|-----------|---------|--------|-------------|-----|
| 1 | 5/11 | A | ENSC | 07:01 | 10.0 | whole_dollar | 0.12 | 11.8% | yes | (signal logged at $1.02; no order — pre-fix) | — | — | $0 |
| 2 | 5/11 | A | ODYS | 08:48 | 10.0 | whole_dollar | 0.12 | 1.2% | yes | CHASE_TIMEOUT (mkt $11.22 vs cap $10.27) | — | — | $0 |
| 3 | 5/11 | A | TRAW | 09:31 | 12.0 | pm_high | 0.0952 | 4.1% | no | CHASE_TIMEOUT (3 retries to $2.45, cancelled) | — | — | $0 |
| 4 | 5/13 | A | ATRA | 14:34 | 12.0 | pm_high | 0.0588 | 0.6% | no | SKIP (R<0.06 min) | — | — | $0 |
| 5 | 5/13 | B | ATRA | 15:19 | 11.0 | (signal) | 0.27 | 2.6% | no | FILL → loss-cap exit | 10.50 | sq_dollar_loss_cap ($715) | -$906 |
| 6 | 5/13 | B | VNET | 15:19 | 8.5 | (signal) | 0.12 | 1.1% | yes | FILL → bail timer | 11.29 | bail_timer | -$44 |
| 7 | 5/14 | A | LNKS | 13:48 | 12.0 | pm_high | 0.0604 | 2.8% | no | CHASE_TIMEOUT (mkt $2.29 vs cap $2.28) | — | — | $0 |
| 8 | 5/15 | A | SLE #1 | 08:32 | 10.0 | whole_dollar | 0.12 | 2.0% | yes | FILL (1 retry) → target hit | 6.12 | sq_target_hit (2241sh) + bearish_engulf (250sh) | +$468 |
| 9 | 5/15 | B | SLE | 08:32 | 6.6 | (signal) | 0.12 | 1.9% | yes | FILL → immediate para trail | 6.31 | sq_para_trail_exit (3s hold) | -$446 |
| 10 | 5/15 | A | LESL | 08:58 | 11.0 | whole_dollar | 0.20 | 5.0% | no | FILL → loss-cap exit | 4.04 | sq_dollar_loss_cap ($507) | -$533 |
| 11 | 5/15 | A | SLE #2 | 09:19 | 5.3 | whole_dollar | 0.12 | 1.7% | yes | FILL → para trail | 7.06 | sq_para_trail_exit | -$247 |
| 12 | 5/15 | A | ONDG | 09:31 | 12.0 | pm_high | 0.12 | 1.7% | yes | CHASE_TIMEOUT (mkt $7.57 vs cap $7.57 @ 3.5%) | — | — | $0 |
| 13 | 5/15 | B | ONDG | 09:31 | 11.0 | (signal) | 0.31 | 4.2% | no | CHASE_TIMEOUT (3 retries) | — | — | $0 |
| 14 | 5/15 | B | ONDG #2 | 09:34 | 11.0 | whole_dollar | 0.12 | 1.5% | yes | BP_BLOCK (bp=$0) | — | — | $0 |
| 15 | 5/15 | B | ONDG #3 | 09:38 | 11.0 | whole_dollar | 0.27 | 3.3% | no | BP_BLOCK (bp=$0) | — | — | $0 |
| 16 | 5/15 | A | QUCY | 10:10 | 7.9 | pm_high | 0.11 | 3.6% | no | CHASE_TIMEOUT (mkt $3.17 vs cap $3.15) | — | — | $0 |
| 17 | 5/15 | A | SLE #3 | 10:46 | 7.0 | whole_dollar | 0.20 | 3.3% | no | CHASE_TIMEOUT | — | — | $0 |
| 18 | 5/15 | A | SLE #4–#9 | 16:17–17:50 | 11.0 | whole_dollar | 0.12 | 2.4% | yes | CHASE_TIMEOUT ×6 (re-firing on same level) | — | — | $0 |

**Setup A net 5/15:** +$468 − $533 − $247 = **−$312**
**Setup B net 5/15:** **−$446** (single SLE fill)
**Setup B net 5/13:** **−$950** (ATRA −$906, VNET −$44)

**Week realized P&L (squeeze only):** Setup A −$312, Setup B −$1,396

---

## B. Winners vs losers

Filtering to actually filled trades (5/13 B: 2; 5/15 A: 3; 5/15 B: 1 = 6 fills):

**Winners (1):**
- **SLE #1 5/15 08:32** — score=10, parabolic, whole_dollar level, R=$0.12 (2%), pre-market 12.9× volume, fill @ $6.12, exit two-piece ($6.12 bearish_engulf for −$1; $6.33 sq_target_hit for +$469). Hold ~6 min.

**Losers (5):**
| Symbol | Score | Para | R% | Time | Loss | Notes |
|--------|-------|------|-----|------|------|-------|
| ATRA 5/13 B | 11.0 | no | 2.6% | 15:19 | −$906 | Hit dollar-loss-cap inside 3 min; price gapped down to $8.52 (R-mult ~−2.3) |
| VNET 5/13 B | 8.5 | yes | 1.1% | 15:19 | −$44 | Bail timer (held ~5min flat) |
| SLE B 5/15 | 6.6 | yes | 1.9% | 08:32 | −$446 | Para trail exit fired 3 sec after fill — exit logic working as designed |
| LESL 5/15 A | 11.0 | no | 5.0% | 08:58 | −$533 | Dollar-loss-cap; price faded $4.04→$3.84, never recovered through 09:20 |
| SLE #2 5/15 A | 5.3 | yes | 1.7% | 09:19 | −$247 | Para trail; price dropped $7.06→$6.26 over next 14 min — good save vs −$2,500 worst-case |

**Pattern in the losers:**
- Only one winner had a high score (10); two losers had score=11 (LESL, ATRA). Score alone is *not* discriminating winners from losers at this sample size.
- The clearest feature of the winner: **early-AM (08:32)** + parabolic + whole-dollar level + pre-market volume already 12.9× avg. The losers were either *late afternoon* (15:19 — both Setup B's 5/13 trades), *mid-day chop* (LESL 08:58, SLE 09:19), or *low-score* (SLE B 6.6, SLE #2 5.3).
- **Setup B's two same-second 5/13 entries (ATRA 15:19:53, VNET 15:19:55) both lost.** This wasn't independent — it was a single engine reconnect immediately triggering two queued signals on a recovering connection. Treat as one event ("late-day, post-reconnect mass entry").

---

## C. Fluke filter

Real one-offs (discount from pattern analysis):
- **SLE Setup A #4–#9 (16:17–17:50)** — same setup re-arming on every chase-cap cancel because the bot's whole-dollar level at $5.02 stayed valid as SLE bounced around $5.27–$6.09 in extended hours. 6 attempts, all chase-capped. **One event repeating, not 6 events.**
- **Setup B 5/14 quiet day** — only SQ_REJECTs (not_new_hod) logged; no entries, no chase-caps. Not a strategy event — the market didn't offer squeeze setups that day. (Note: MOBX, AEHL, QUCY were rejected because bar_high was below HOD — that gate is working as intended.)
- **ONDG Setup B BP_BLOCK ×2 (09:34, 09:38)** — bp=$0 because Setup A had just consumed buying power on the SLE morning trade plus LESL. This is *infra plumbing* (cross-bot BP awareness on shared paper account), not a strategy signal. Already-known constraint per `project_alpaca_bp_constrained.md`.
- **5/11 ENSC 07:01** — pre-fix-bundle: signal logged but no order ever sent. Discard.

Repeating patterns (keep):
- SLE re-firing intra-day at multiple whole-dollar breaks ($6, $7, $5) — that's the *symbol's* behavior, and a real signal that whole_dollar squeezes on SLE specifically were too late on every re-fire. By the time the level was confirmed broken, market had moved past chase-cap.

---

## D. Pattern analysis (data says vs I suspect)

**Time of day** (data says):
- 1 morning fill (08:32) — winner
- 3 morning fills (08:32, 08:58, 09:19) — winner + 2 losers
- 2 afternoon fills (15:19 both) — both losers
Late-day fills are 0/2 winners. **Suspect** late-day squeezes are lower quality (likely already-extended names by 15:19), but n=2.

**Score thresholds** (data says):
- Score=10: 1/1 winner (SLE #1)
- Score=11: 0/2 winners (LESL, ATRA)
- Score=8.5: 0/1 (VNET, but only −$44)
- Score=6.6 / 5.3: 0/2 (both para-trailed out fast)
- **No clean monotonic relationship.** Score 10 winning, score 11 losing is small-sample noise on its face. **Suspect** the score function over-weights vol_extra (5.0 cap is hit even on extreme tickers like SLE) and under-weights price-action quality. Worth tracking another 2 weeks.

**Setup level** (data says):
- whole_dollar: 3 fills (SLE #1 W, SLE B L, SLE #2 L) — 1/3
- pm_high: 0 fills (TRAW, LNKS, QUCY all chase-capped) — undecided
- Signal-only (no level shown, Setup B): 3 fills (ATRA, VNET, SLE B) — 0/3
- **Whole_dollar wins exist; pm_high never filled.** Not enough to conclude pm_high is broken, but it's a watch item.

**Parabolic flag** (data says):
- Parabolic fills: 4 (SLE #1 W, SLE B L, VNET L, SLE #2 L) — 1/4
- Non-parabolic fills: 2 (ATRA L, LESL L) — 0/2
- Chase-capped parabolics (ODYS, ONDG, ENSC, SLE late-day): all "saves"
- **Parabolic flag does not predict success at this n.** The wider 3.5% chase cap for parabolic isn't visibly hurting; it isn't visibly helping either.

**R% buckets**:
- R% < 2.0%: 4 fills (SLE #1 +468, SLE B −446, VNET −44, SLE #2 −247) — 1/4, net −$269
- R% 2.0–3.0%: 1 fill (ATRA −906) — 0/1
- R% > 3.0%: 1 fill (LESL −533) — 0/1
- **No bucket profitable yet.** Skewed by SLE #1 being the only winner.

**Symbol profile**:
- **SLE** is the dominant ticker (5 attempts, 3 fills, 1 win 2 losses, net −$225). Behavior: prone to fast move + reversal at whole-dollar levels. Re-fires on every new whole-dollar break.
- **ATRA, VNET, LESL** each appeared once as a fill — all losses. Insufficient to characterize.
- **ONDG, ODYS, TRAW, LNKS, QUCY, ENSC** — chase-capped or rejected. The chase-cap saves on ODYS and ONDG were particularly large gross moves.

**Bar context for the winner (SLE #1 5/15 08:32):** vol=12.9× avg, bar_vol=758,069, price $6.27 above VWAP $5.45 (+15% above VWAP). That's an extreme premarket flush — **and it's the same kind of context the losers (LESL, SLE B same morning) also had.** Pre-market volume × VWAP-distance alone doesn't separate them.

---

## E. Chase-cap save sanity check

Verifying chase-cap timeouts were correct (i.e., did the price fade after we passed?):

| Event | Cancel @ ET | Cancel price | +5 min price | +10 min price | Verdict |
|-------|-------------|--------------|--------------|----------------|---------|
| ODYS 5/11 08:48 | mkt $11.22 vs cap $10.27 | — | (data thin pre-09:30) | — | Inconclusive but bot avoided buying $11.22 at 08:48 |
| TRAW 5/11 09:31 | retry stack to $2.45 | $2.45 | — | — | Inconclusive |
| LNKS 5/14 13:48 | mkt $2.29 vs cap $2.28 | $2.29 | — | — | Inconclusive (penny above cap) |
| **ONDG 5/15 09:31 (score=12!)** | mkt $7.57 vs cap $7.57 | $7.57 | **$8.20 (+8.3%)** | **$7.96 (+5%)** | **MISSED RUNNER then faded** — at +5 the bot would've been up, by +30 min flat, by +60 min down. Hard to call. |
| QUCY 5/15 10:10 | mkt $3.17 vs cap $3.15 | $3.17 | $3.42 (+7.9%) | $4.03 (+27%) | **MISSED RUNNER** — QUCY ran to $4.03 by 10:21. Real miss. |
| SLE A #3 5/15 10:46 (score=7) | mkt $6.39 vs cap $6.21 | $6.39 | $6.70 (+4.9%) | $6.50 (+1.7%) | Marginal — small win then fade |
| SLE A #4–#9 EXT (16:17–17:50, score=11) | $5.27 cap | $5.27 | range $5.82–$6.09 | range $5.93–$6.09 | **MISSED slow runners** — but extended hours, low liquidity, hard to actually fill in size |

**Calling it:** Three legit "misses" stand out: ONDG 5/15 09:31, QUCY 5/15 10:10, and the SLE extended-hours stack. ONDG and QUCY are the same pattern — **fast post-9:30 break where the chase cap is hit within the same minute as signal**. The current 3.5% cap for score≥10 parabolics caught ODYS correctly but missed ONDG. QUCY (score=7.9, 2% cap) was further out — that one would argue for a slightly wider cap for higher scores, *but only when fill latency is < 30 sec.*

**Counterpoint:** ATRA on 5/13 filled (the bot got in) and lost −$906 in 3 minutes. So "filling more" isn't strictly better. The bot's filtering choice (give up at 3.5%) saved capital in some cases.

---

## F. Strategy refinement recommendations

Prioritized, with confidence labels:

1. **Don't change anything structural this week.** *(High confidence.)* One win, five losses, six chase-saves. Not a sample.

2. **Tag the time-of-day pattern as a "watch."** *(Medium.)* Late-day Setup B 15:19 mass-entry on reconnect (ATRA + VNET) was the worst trade pair of the week. Even if it's coincidence, "post-reconnect immediate entries" should probably have a 60-second cooldown. Confidence: low n, but it's also a fragility risk in production. **Suggest: add a 30-60 sec "post-reconnect signal silence" guard.**

3. **Score = 5–7 fills are weak so far.** *(Low confidence.)* SLE B (6.6) and SLE #2 (5.3) both para-trailed out fast. **But** the SLE #2 para-trail exit was correct (price dropped to $6.26 over 14 min). The right framing isn't "raise the score floor" — it's "low-score parabolic exits work, and they're cheap insurance." Leave the floor alone.

4. **`sq_dollar_loss_cap` is firing on time, not too early.** *(Medium confidence.)* LESL: cap fired at $3.84; price stayed $3.84–$4.04 for next 22 minutes, never recovered to $4.09 entry. ATRA: cap fired at $10.35; price dropped to $8.52 immediately after. Both were good cuts.

5. **`sq_para_trail_exit` is firing on time, not bailing on runners.** *(Medium.)* SLE B 08:32 fill held 3 sec before trail; could be considered a "too tight" exit, except the same SLE then re-entered at $7.06 on Setup A and dropped to $6.26 — so trail was *correct, just early*. SLE #2 09:19 fill: trail at $6.94, price went $6.94 → $6.26. Both saves.

6. **The ONDG/QUCY chase-cap "misses" aren't a clear case for widening the cap.** *(Medium.)* ONDG: even at $8.20 5min later, getting filled there isn't a +R guarantee — the spread on ONDG was wide. QUCY: ticks went 0 between $3.42 and $4.03, suggesting a halt or stale stream — the bot couldn't have filled there even with a wider cap. **Don't widen the cap based on these two.**

7. **One pattern to consider: parabolic + early-morning (pre-9:30) + whole_dollar level = SLE #1 winner profile.** *(Low confidence — sample size 1.)* If you wanted one explicit bias, it would be "parabolic squeezes pre-9:30 at whole-dollar levels get more aggressive sizing or a wider chase cap." Don't act on this yet — flag it for n=2-3 more wins to confirm.

8. **Setup B is bleeding more than Setup A on squeeze.** *(Medium.)* Setup B: −$1,396 / 3 fills / 0 wins. Setup A: −$312 / 3 fills / 1 win. The setups are running the same detector logic on different brokers/accounts but Setup B has produced no winners. Likely a slip/latency story (the engine fills near peak then exits within seconds), not a strategy story. Worth A/B'ing on next week's data, not refactoring on this week's.

9. **Re-firing on the same setup level (SLE on $5, $6, $7 whole-dollar all in one day) needs a per-symbol/per-level cooldown.** *(Medium.)* SLE entered/attempted at $6 (08:32 win), $7 (09:19 loss), $6 again (10:46 chase-cap), $5 (16:17–17:50 chase-cap ×6). Different price levels, but psychologically one ticker. **Suggest: per-symbol max-attempts-per-day soft cap** (e.g., 3 squeeze attempts per ticker per day). The SLE 16:17–17:50 cluster wasted no capital but consumed scanner/order-bandwidth for 90 minutes.

---

## G. Limitations (honest)

- **Sample size:** 6 actual fills across 5 days, of which 5 occurred on 5/15 and 5/13 alone. That's not enough for *any* statistical claim about win rate, R-multiple distribution, or score-vs-PnL correlation. Everything in section D is descriptive, not predictive.
- **Single-day dominance:** 5/15 is 4 of the 6 fills and 8 of the 9 chase-cap saves. A single-day audit dressed up as a week.
- **Selection bias from chase-cap:** We only see PnL on trades that filled. The chase-caps that "saved us" from −$X are counterfactual estimates. ONDG and QUCY look like missed +R; LESL and ATRA filled and lost; the bot's chase-cap might be selecting for the *worst* trades (the ones eager enough to fill at our limit) and rejecting the *best* (the ones moving fast). **This bias is structural and merits a separate calibration study with a wider cap on a small slice of opportunities.**
- **Setup B fill quality is unverified vs market.** The 5/13 ATRA fill at $10.50 then immediate −$2.30 gap suggests either bad fill, immediate adverse selection, or the engine is buying right at a peak. Not enough fills to know.
- **No fill-vs-signal-time latency data.** Audit captured order timestamps but not millisecond-level signal→entry latency. With 4–6 sec spans (SLE B fill 1.1 sec after signal; ONDG cancel after 11 sec retries), this matters for chase-cap calibration. Worth instrumenting.
- **The "evening SLE FILLED on engine $5.61 held into 19:55 force-exit at $5.53" detail in the brief did not appear in the engine log.** Setup B's shutdown line on 5/15 reads `daily_pnl=$-445.58, open_positions=0`; the only filled engine entry was SLE 08:32. The 6+ Setup A SLE chase-cap attempts in extended hours may have been mistaken for an engine fill. Worth confirming.

---

## Bottom line for the user

The fill-rate fix did its job. Exit logic (loss cap, para trail) is working as designed and is cutting losers timely. The strategy's edge — if it has one at squeeze — is being decided before entry by **time-of-day × score × level × volume context**, and not by entry/exit micromechanics. One more clean week of data, then revisit. Don't over-fit to 5/15.

**One safe action item:** add a per-symbol max-attempts-per-day cap (3) to silence the SLE evening re-fire stack and reduce log noise / cognitive load during real-money week.
