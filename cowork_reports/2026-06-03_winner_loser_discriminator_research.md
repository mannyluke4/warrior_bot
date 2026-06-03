# Winner/Loser Discriminator — XOS vs WCT, and Why FIRESTORM Doesn't Separate Them

**Date:** 2026-06-03 (intraday snapshot ~17:00 ET, session ongoing)
**Author:** CC live-monitoring session
**Status:** Research / brainstorm starter — NO code changes proposed yet. For deep-dive + solution brainstorm.
**Data quality:** Clean day. Ticks flowing all session (active drought monitor, zero incidents). All P&L below is **broker-verified** (Alpaca `equity − last_equity` and per-symbol fill reconciliation), not bot `daily_pnl` — see §6 partial-fill caveat.

---

## TL;DR

1. Today gave a clean natural experiment on **two low-float small-cap movers, WCT (~$2–3) and XOS (~$7–8)**, both of which traded on **persistently low-tick-rate bars** (neither ever hit the 6,000 ticks/min FIRESTORM threshold all day).
2. **Sub-bot C (no FIRESTORM, reentry-loss-gate) net −$363:** it lost **−$1,581 on WCT** (14 fills) and *made* **+$1,112 on XOS** (9 fills), +$106 FOXX.
3. **FIRESTORM (sub-bots A & B) blocked BOTH WCT and XOS** — A/B armed each name but the gate blocked ~20,000 entry attempts; A +$67 / B +$22, essentially by *sitting out*.
4. **The main bot (squeeze, IBKR, no FIRESTORM) ALSO caught XOS — and lost −$385** on it (3 trades, tight para-trail / bearish-engulfing exits).
5. **Therefore: tick rate (FIRESTORM) does NOT discriminate today's biggest winner from its biggest loser** — both were quiet-bar names. And **the same symbol (XOS) was +$1,112 for C but −$385 for the main bot** — so the discriminator is *also* in the exit framework, not just entry selection.
6. **Retraction:** an earlier claim that "FIRESTORM would flip C's day from −$363 to ~+$1,200" is **wrong** and is retracted here — FIRESTORM would have blocked C's XOS winner too (§4).

The open question this surfaces: **what actually separates the XOS-class winner from the WCT-class loser, given tick rate does not?** Candidate answer (to brainstorm): **price / stop-structure** (sub-$5 + tight-R = POLA-class flush loser) on the entry side, **and exit framework** on the management side.

---

## 1. The day's data (broker-verified)

Intraday snapshot, ~17:00 ET (session continues; final numbers will land in `2026-06-03_abc_daily_report.md`):

| Book | Config | Day P&L (broker) |
|---|---|---|
| Main bot | squeeze, IBKR, no FIRESTORM | **−$386** |
| Sub-bot A | FIRESTORM gate | **+$67** |
| Sub-bot B | FIRESTORM gate + Track A exit | **+$22** |
| Sub-bot C | reentry-loss-gate (no FIRESTORM) | **−$363** |

**Cumulative A/B/C thru 2026-06-02** (`abc_running_totals.json`): A **+$123** (only positive variant), B **−$3,210**, C **−$4,217**. (B/C cumulative is heavily inherited from retired pre-swap V1-VWAP / Body-CV configs.)

### Sub-bot C, per-symbol (broker fill reconciliation)

| Symbol | Price band | Fills | Realized P&L |
|---|---|---|---|
| **WCT** | $2–3 (sub-$5) | 14 | **−$1,581** |
| **XOS** | $7–8 | 9 | **+$1,112** |
| **FOXX** | $5–6 | 2 | **+$106** |
| | | | **−$363** |

C's *entire* loss is WCT. Its higher-priced names were net winners.

---

## 2. The centerpiece: XOS caught three different ways, three different outcomes

XOS is the cleanest natural experiment of the day — the same symbol, same long direction, traded (or blocked) by three different configs:

| Book | What happened on XOS | Result |
|---|---|---|
| **Sub-bot C** | entered (move_strike + regime_shift), managed with **move_hwm** exits | **+$1,112** |
| **Main bot** | entered (squeeze), managed with **sq_para_trail / bearish_engulfing** exits | **−$385** |
| **Sub-bots A/B** | armed, but **FIRESTORM blocked every entry** (~20,000 blocks) | **$0** (no fills) |

**Implication:** "catching XOS" was not sufficient to win it — the **main bot caught it and still lost −$385** because its exits (tight parabolic trail, bearish-engulfing) chopped it out, while C's HWM trail let it run. So the outcome is a function of **entry gating AND exit framework**, not symbol selection alone. Any "winner/loser" filter we design has to reckon with the fact that the *same trade* can be a win or a loss depending on management.

---

## 3. WCT — the loss-loop, and why C kept eating it

- C took **7+ WCT round-trips** (14 fills) for **−$1,581**. It kept re-engaging via fresh `regime_shift` / `move_strike` signals.
- C's **reentry-loss-gate did NOT stop it**: that gate only blocks REENTRY-GREEN within 30 min of a loss-class exit; fresh regime-shift/move-strike arms are not gated.
- WCT is **sub-$5 with tight R** (entries $2.00–$3.14, R as tight as $0.04–$0.17). This is the documented **POLA-class loss archetype** (`2026-05-28_firestorm_trigger_backtest_results.md`): good win-rate but catastrophic loss-size when a sub-$5 name flushes through a tight stop with momentum.

---

## 4. What FIRESTORM actually did (and the retraction)

FIRESTORM blocks any entry when the prior completed 1m bar had < 6,000 ticks/min (100/sec). Today, **both WCT and XOS lived below that threshold the entire session:**

| Symbol | Prior-bar ticks at C's entries | Max prior-bar ticks all day | FIRESTORM verdict |
|---|---|---|---|
| WCT | 339 (10:20 entry) | (low all day, 124–5,557) | BLOCK |
| XOS | 3,105 / 1,353 / 876 / 882 | **3,544 (never ≥ 6,000)** | BLOCK |

So A/B **armed both names but the gate blocked every entry** — A/B's near-flat P&L (+$67/+$22) came from *not trading*, not from selecting good trades.

**Retraction:** I earlier asserted that giving C the FIRESTORM gate would flip its day from −$363 to ~+$1,200 (keep XOS, drop WCT). **That is false.** XOS never exceeded 3,544 prior-bar ticks, so FIRESTORM would have blocked C's XOS winner (+$1,112) exactly as it blocked WCT. FIRESTORM-on-C ≈ **flat**, not +$1,200. **Tick rate does not discriminate today's winner from its loser.**

This is consistent with the reports' own framing of FIRESTORM as a *defensive* filter: *"stops the bleeding without (yet) producing a profitable subset"* and *"the current pipeline trades only 13.3% of YTD firestorm bars and misses 86.7%"* (`2026-05-28_firestorm_gate_impl_notes.md`, `2026-05-28_arming_research_phase2_missed_firestorm_gap.md`). It avoids loss by avoiding activity, and leaves real upside (XOS) on the table.

---

## 5. The central question for the deep-dive

**Given tick rate does NOT separate WCT (−$1,581) from XOS (+$1,112), what does?** Observable differences between the two:

| Dimension | WCT (loser) | XOS (winner, for C) |
|---|---|---|
| Price | $2–3 (sub-$5) | $7–8 |
| R / stop width | very tight ($0.04–$0.17) | wider in $ terms |
| Tick rate | low (<6k) | low (<6k) — **same** |
| Outcome dispersion | flushed through tight stops | ran far enough for HWM to capture |
| Same-name behavior | choppy whipsaw, repeated re-entry | trended after entry |

The standout structural difference is **price + stop geometry**, which is precisely the **Track A R-floor** territory (`2026-05-28_track_a_results.md`) — NOT the FIRESTORM tick filter. But note Track A is an **exit** framework; it can't rescue XOS on A/B because FIRESTORM blocks the **entry** upstream first. So none of the three live gates, as wired, both (a) lets XOS through and (b) blocks WCT.

---

## 6. Methodology note / caveat (important)

- **Do NOT sum the bot's per-`trade#` log lines for P&L.** They undercount **partial fills**: e.g., C's XOS trade entered 2,000 shares but a numbered "trade #" line logged only 200 of them; the other ~1,800 exited separately and never appeared in a numbered line. Summing trade-lines gave −$975 for C; the broker truth is −$363. **Always reconcile from the broker** (`equity − last_equity`, or sum fills per symbol).
- Bot `daily_pnl` is non-canonical per prior reports (DIRECT_QUERY_WEDGE / bot-vs-broker divergence). Today was a clean day (no wedge, books matched broker), but the rule stands.

---

## 7. Candidate hypotheses to brainstorm (NOT yet validated)

Seeds for the deep-dive — each needs backtest validation before any gating:

1. **Price/stop-structure entry filter.** Block (or down-size, or widen-stop) entries on sub-$5 names with R below some floor — the POLA/WCT archetype. This is the most direct read of today. Open: is it an entry *block*, or just Track A's R-floor applied at sizing? Does it generalize across the YTD set or is today idiosyncratic?
2. **Exit framework is half the battle.** The XOS three-way (C +$1,112 vs main −$385, same symbol) says exits dominate outcome. Worth a focused study: which exit (HWM trail vs para-trail vs engulfing) captures vs chops on low-tick trending movers? Does Track A's phased-drawdown beat both?
3. **FIRESTORM is too blunt alone.** It's a pure activity-suppressor that also kills winners (XOS). Brainstorm: a *two-factor* gate — e.g., allow a low-tick entry **if** price ≥ $X and R ≥ floor (capture XOS) while still blocking sub-$5 tight-R low-tick (kill WCT). Combine the tick filter with the structure filter rather than using tick rate alone.
4. **Re-entry discipline.** C re-entered WCT 7×. The reentry-loss-gate missed it (only gates reentry-green, not fresh regime-shift arms). Brainstorm: a per-symbol daily loss cap or "N losing trades on a symbol → block that symbol for the day" — generalizable, not symbol-specific.
5. **The long-only ceiling (standing).** WCT whipsawed both directions; long-only ate the down-flushes. Bidirectional/short-side remains the unbuilt structural fix (`2026-05-28_ft_sweep_results.md`).

---

## 8. Reproduction

- Broker P&L: `scripts/abc_compare_daily.py` style — Alpaca `get_account().equity - last_equity` per sub-bot account; per-symbol = sum filled BUY cost vs SELL proceeds from `get_orders(status=CLOSED)`.
- FIRESTORM tick counts: `grep "FIRESTORM_GATE_BLOCK <SYM>" logs/2026-06-03_move_strike_subbot_A.log | grep -oE "prior_bar_ticks=[0-9]+"`.
- Main bot XOS: `grep "EXIT: XOS" logs/2026-06-03_daily.log`.
- C per-symbol: broker fill reconciliation (account `VARIANT_C_APCA`, PA38Q69FQB6K).

## 9. Cross-references

- `2026-05-28_firestorm_gate_impl_notes.md` — FIRESTORM origin, threshold, "stops bleeding, not yet profitable subset."
- `2026-05-28_firestorm_trigger_backtest_results.md` — POLA-class tight-R + sub-$5 + flush loss archetype.
- `2026-05-28_track_a_results.md` / `2026-05-29_track_a_rebaseline_notes.md` — Track A R-floor + phased drawdown (sim-validated, not yet live-proven).
- `2026-05-28_arming_research_phase2_missed_firestorm_gap.md` — "misses 86.7% of firestorm bars"; opportunity is in high-tick bars.
- `2026-05-23_live_abc_fade_gate_test_directive.md` — A/B/C test design + decision framework (~6/15, go-live 6/22).
