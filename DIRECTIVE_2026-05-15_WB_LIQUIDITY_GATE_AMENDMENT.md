# WB Liquidity Gate — Reasoning Amendment

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC
**Amends:** `DIRECTIVE_2026-05-15_WB_LIQUIDITY_GATE.md`
**Trigger:** Manny correctly flagged that "we are the liquidity event" framing doesn't apply to paper accounts. Alpaca paper fills don't hit the real order book and don't move price. The bars on the chart after our entry are exactly what the real market did, with or without our order.

---

## What this amendment changes

The **fix (ship A and B) stays the same.** The **reasoning** changes, and the strategic implications shift in important ways.

### Old framing (incorrect for paper)

> "We were the liquidity event. We bought 5,524 shares on a bar that traded 4,700 shares total. Our order pushed price and there was no opposing flow to carry the trade."

### Correct framing

> "The detector's '4.33× volume ratio' is statistical noise — 4.33× of a 1,090-share/min baseline is still 4,700 shares, which is meaningless flow. The bar that scored as a 'surge' is just one print on an otherwise dead tape. The signal itself is unreliable on thin volume. Whether or not our (paper) order existed, there is no real flow to carry the position to profit, so it drifts."

**Both framings point at the same fix.** The detector needs a floor on absolute bar volume so it doesn't score statistical noise as a real signal. The math is identical; the *reason* is "filter out unreliable signals" not "stop being the market."

---

## Why this matters for B (sizing cap)

**Proposal A's reasoning is unchanged: the detector's signal is unreliable on thin tape regardless of fill mechanism.** Ship A.

**Proposal B's value depends on account type:**

- **On paper (Alpaca):** B mostly helps by making losing trades smaller. We won't move the market because we're not on the real book. The win/loss outcome of any single trade is determined by the real market's behavior, not our position size.
- **On real money (post-June 4):** B becomes critical. Real orders on the book at our position-to-bar ratio would (a) suffer slippage on entry, (b) suffer slippage on stop-out, (c) potentially partial-fill leaving orphan size, (d) actively move price against us when liquidity is below our size.

**Implication for ship order:**

| Proposal | Paper account value | Real money value | Ship priority |
|---|---|---|---|
| A (veto on thin bar) | High — kills unreliable signals | High — same plus avoids real-money slippage | Saturday |
| B (sizing cap) | Modest — limits loss size when trade fails | Critical — avoids being the print | Sunday or before June 4 |

A still ships first. B still ships but its urgency is "before real money" not "before Monday."

---

## What this means for CC's Q3 (the strategic question)

The old framing said: "persistence-layer winners may have been profitable because our position happened to match available flow at the time." That was wrong for paper.

**Correct framing:** Persistence-layer winners (FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13) were paper fills. They "won" because the real market moved up after our simulated entry, and Alpaca filled us cleanly at quoted prices without slippage. **The real question for go-live is:** would those same setups have produced wins in REAL money where:
- Our entry order sat on the real book and possibly moved the bid up before filling
- Our stop-loss order would sit on the bid and possibly fail to fill cleanly if price gaps through
- Other paper participants (us and the market makers' inventory algos) might have behaved differently

We genuinely don't know the answer. The Stage 1 backtest now needs to do TWO things:

1. **Liquidity-aware execution simulation** — model entry fill price as a function of (position size / bar volume). If bar volume < position × 2, model slippage proportional to imbalance. If bar volume < position, treat as worst-case fill at next-bar high (longs).
2. **Stop-out slippage simulation** — model stop fills with same logic. Many "winners" might become break-even or losers if the stop slips when price gaps through on thin tape.

Without these, the backtest reports optimistic paper-style P&L that won't survive real money. **CC: update the Stage 1 backtest spec to include both.**

---

## What this DOESN'T change

1. **A still ships Saturday with `WB_MIN_BOUNCE_BAR_VOLUME=15000`.** Detector signal unreliability is paper-agnostic.
2. **B still ships, but the deadline is "before real money" not "before Monday."** OK to land Sunday or even next week.
3. **Validation against the 4 known WB winners is still required.** If A would veto known winners, that tells us either (a) the winners were noise from unreliable signals (bad news for WB) or (b) the threshold is too tight (lower it).
4. **The persistence layer continues to run.** Generate the data, see what the backtest says.
5. **The intraday adder continues observe-only.** Same.
6. **Current ATRA position decision unchanged.** I still recommend flatten — but for the corrected reason: it's a trade that entered on an unreliable signal (statistical noise mistaken for volume surge), and the chart shows no real flow to carry it. The reason to flatten is "the setup was bad" not "we're stuck with our own order."

---

## Updated tone on the persistence-layer question

Earlier I said: "The illiquidity that filtered WB winners out of squeeze scanner is the same illiquidity that makes them risky to trade at our notional." That's still true on real money. On paper, the more accurate framing is:

**"The illiquidity that filtered WB winners out of squeeze scanner is the same illiquidity that makes the detector's signal unreliable in the first place — and is independently the same illiquidity that will cause execution friction the moment we go real."**

Two related problems, both pointing at the same fix, both ranked the same priority for go-live.

---

## Action: minor edits, not a rewrite

The original directive's ship plan is correct. CC should:

1. **Ship Phase 1 (A veto) Saturday** as specified
2. **Ship Phase 2 (B sizing cap) Sunday OR before June 4** — call it; either works
3. **Update Phase 3 validation report** to note the corrected reasoning. The validation logic itself doesn't change; the rationale text should reflect "detector signal unreliable on thin tape" rather than "we are the liquidity event"
4. **Update the Stage 1 backtest commission spec** to require both liquidity-aware entry fills AND stop-out slippage simulation
5. **Telemetry unchanged** — log bar-volume on every WB_ARM regardless of pass/veto, same as before

No code change differences from the original directive. The thinking is what needed correction.

---

## Tone note

Manny caught this in real-time and it's the right correction. The right time to fix sloppy reasoning is before the team builds on it. "Paper accounts don't move markets" is exactly the kind of mechanism difference that's easy to forget mid-flow when you're staring at a chart that looks like a textbook slippage failure. The chart pattern is real — but the cause-and-effect was inverted.

The fix still ships. The reasoning is sharper. The June 4 transition planning gets the right framing for what changes when paper → real.
