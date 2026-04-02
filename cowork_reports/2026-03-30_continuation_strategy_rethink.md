# Continuation Strategy Rethink: It's Not the Entries — It's the Exits

**Date:** 2026-03-30
**Author:** Cowork (Opus)
**Sources:** Jan 2025 IBKR backtest (commit 880eaf0), 18 Ross comparison files, CT V2/V2.1/V2.2 test results, 2026 YTD backtest data

---

## The Revelation

After a full day of CT (Continuation Trading) iteration — V2, V2.1, V2.2-A, V2.2-B — the best CT result was +$413 on a single stock across 59 days. Meanwhile, on Jan 24, the bot and Ross Cameron entered the exact same stock (ALUR) at the exact same time ($8.04 at 7:01 AM). Ross made **+$47,000**. The bot made **+$586**. An 80x difference.

**CT was solving the wrong problem.** The bot doesn't need a separate strategy to detect continuation. The squeeze cascade already detects continuation — the SQ detector fires PRIMED/ARMED at progressively higher levels after our first exit. The cascade re-enters. On ALUR, the bot DID re-enter at $10.04 (twice). But then it exited at $10.03 and $10.14. The stock went to $20.

**The problem is the exits, not the entries.**

---

## The Evidence: Jan 2025 Head-to-Head

CC ran the full January 2025 backtest on freshly-fetched IBKR ticks. The bot made **+$15,395** across 6 active days, 19 trades, 68% win rate. We have Ross recaps for all those days plus most of the days the bot missed.

### Days Where Both Traded the Same Stock

| Date | Stock | Bot P&L | Ross P&L | Bot Entry | Stock HOD | What Happened |
|------|-------|---------|----------|-----------|-----------|---------------|
| Jan 6 | GDTC | +$4,352 | +$5,300 | $6.68 zone | $9.50 | Bot cascaded 2 entries, both sq_target_hit. **Captured ~82% of Ross.** |
| Jan 13 | PHIO | +$1,442 | small | $2.69 | ~$5 | Bot cascaded 3 entries (1 loss, 1 small win, 1 target hit). Beat Ross on this stock. |
| Jan 21 | INM | +$2,123 | +$12,000 | ~$7 | $9.20 | Bot 2 entries (1 target +$2,506, 1 max_loss -$383). Ross scaled 6-10K shares, rode to $9.20. |
| Jan 24 | ALUR | +$2,306 | +$47,000 | $8.04 | $20.00 | **THE case study.** Bot target hit at $8.40, cascade at $10.04 gave back to trail. Ross rode $8.24→$20. |
| Jan 30 | AMOD | +$3,788 | positive | $2.77 zone | — | Bot cascaded 3 entries (2 target hits, 1 trail). Good capture. |

### What the Data Shows

**When the cascade works (GDTC, PHIO, AMOD):** The bot captures 70-100% of Ross's P&L on that stock. The squeeze cascade at 2R target hits is effective. These are stocks that move $2-3 from entry.

**When the move is massive (ALUR, INM):** The bot captures 5-20% of Ross's P&L. The 2R target exits at $0.36 profit when the stock has a $12 runway. The cascade re-entries get stopped by the parabolic trail within pennies of entry. These are stocks that move $5-12+ from entry.

**The pattern:** The bigger the runner, the worse our capture rate. Our exits are calibrated for $2-3 moves. On $5-12 moves, we leave 80-95% on the table.

---

## The ALUR Anatomy: Why 2R Fails on Big Runners

ALUR on Jan 24 is the definitive case study. Here's every bot trade:

| # | Entry | Exit | Reason | P&L | Stock Price 30 Min Later |
|---|-------|------|--------|-----|--------------------------|
| 1 | $8.04 | $8.40 | sq_target_hit (2R) | +$1,990 | ~$12+ |
| 2 | $10.04 | $10.03 | sq_para_trail_exit | -$35 | ~$14+ |
| 3 | $10.04 | $10.14 | sq_para_trail_exit | +$351 | ~$16+ |

**Trade 1:** Clean 2R hit, +$1,990. Good trade. But ALUR was a +181% gap, 12.8M PM volume, GLP-1 biotech catalyst. This is the highest-conviction setup possible. A 2R target ($0.36 from $8.04) captures 3% of a $12 move.

**Trades 2-3:** The cascade correctly re-entered at $10.04. But the parabolic trail stop is too tight for a stock in full breakout mode. Trade 2 lost $35 (exited $10.03 — essentially breakeven). Trade 3 made $351 (exited $10.14). The stock went to $20. The parabolic trail gives back everything because it tightens too fast on volatile moves.

**What Ross did:** Entered $8.24-$8.49, held conviction, added on dips, rode to $20. No fixed target. No mechanical trail. Tape reading + conviction = $47,000.

**What the bot should have done:**
- Trade 1: Take 50% off at 2R ($8.40). Hold 50% runner with trail below 5m low or VWAP.
- If runner portion held: $8.04 entry × 50% position → exit at $12 (conservative) = ~$5,000+ more
- Trades 2-3: Cascade entries on a proven runner should use a wider trail. Below the prior 5m candle low, not the tight parabolic.

---

## The Cascade IS Our Continuation Strategy

Here's the key insight: **we don't need CT as a separate detector.** The SQ cascade mechanism already does what CT was trying to do:

| What CT Tries to Do | What SQ Cascade Already Does |
|---------------------|------------------------------|
| Detect post-SQ continuation | SQ detector fires PRIMED/ARMED at higher levels |
| Re-enter after pullback | Cascade entries at $10.04 on ALUR, higher levels on GDTC/AMOD |
| Use SQ exit system | Cascade trades already use SQ exits |
| Avoid interfering with SQ | It IS the SQ system |

CT added a complex state machine (7 states, 15 env vars, MACD/VWAP/EMA/volume gates) that produced +$413 in the best case and -$596 in the worst case. Meanwhile, the SQ cascade produced +$4,352 on GDTC, +$3,788 on AMOD, +$2,306 on ALUR — and would have produced much more with better exits.

**The continuation opportunity isn't from finding new entries. It's from holding the positions we already have longer.**

---

## What Ross Does That We Don't (Exit Analysis)

From 18 Ross recap comparison files covering January 2025:

### Ross's Exit Approach
1. **No fixed target:** Ross doesn't exit at 2R. He reads the tape — strong bids, thin asks, new highs = hold. Weakening bids, thick asks, lower highs = exit.
2. **Partial exits:** Takes some profit when uncertain, holds a runner portion. If the stock keeps going, he still has shares.
3. **Trail below structure:** Stops are below intraday support (prior 5m low, VWAP, whole dollars), not a mechanical % trail.
4. **Conviction sizing:** On A+ setups (ALUR: GLP-1 + low float + massive volume), Ross sizes up significantly.
5. **20% drawdown rule:** After giving back 20% of day's peak profit, Ross stops trading. Protects the gains.

### What We CAN Implement
1. **Partial exit at 2R** — Take 50% off, hold 50% runner. The sq_target_hit mechanism already exists. We just need to split it.
2. **Wider trail on runner portion** — Trail below the prior 5-minute candle low instead of the tight parabolic trail. Gives the stock room to breathe.
3. **Escalating targets on cascade entries** — 1st entry: 2R target. 2nd entry: 3R (stock already proved it runs). 3rd entry: 4R.
4. **Wider trail on cascade entries** — Proven runner = wider trail. Trail below VWAP or 5m EMA instead of parabolic.

### What We CAN'T Implement (Yet)
- L2 tape reading (requires market depth data)
- Conviction-based sizing (requires catalyst quality scoring)
- Intraday support/resistance tracking (flagged in Known Gaps)

---

## Proposed Strategy: "Runner Mode" Exit Enhancement

Instead of CT (a separate entry detector), enhance the SQ exit system with a "runner mode" that activates after sq_target_hit:

### How It Works

**Phase 1: Standard SQ Trade**
- Entry: same as today (squeeze breakout)
- Exit: same as today (dollar cap → hard stop → tiered max_loss → pre-target trail → 2R target)
- **At 2R target: sell 50%, activate Runner Mode on remaining 50%**

**Phase 2: Runner Mode (50% position)**
- Trail stop: below the prior completed 5-minute candle's low (NOT the tight parabolic trail)
- Update: trail only tightens when a new 5m candle completes higher
- Hard floor: never trail below the original entry price (breakeven protection)
- Time limit: exit runner at 12:00 ET regardless (no holding into afternoon)

**Phase 3: Cascade Enhancement**
- On cascade re-entries (2nd, 3rd SQ trade on same stock):
- Target: 3R on 2nd entry, 4R on 3rd entry (stock has proven itself)
- Trail: use 5m-low trail from the start (wider than standard parabolic)
- Still use standard dollar cap and hard stop for risk management

### Why This Is Better Than CT

| | CT Approach | Runner Mode Approach |
|--|-------------|---------------------|
| Complexity | 7 states, 15 env vars, separate detector | Enhancement to existing exit system |
| Entry mechanism | New pullback detection (failed on 4/4 test stocks) | Same SQ entries that already work |
| Risk | Separate trades that can lose money (ASTC -$596, RUBI -$307) | Holding positions we already have (worst case: give back some 2R profit) |
| Regression risk | CT code execution during SQ affected VERO/ROLR | Zero — SQ entries identical, only exit behavior changes post-target |
| Testability | Required cascade lockout + trade count gates + soft/hard gates | Simple: does the 5m-low trail capture more than the parabolic trail? |
| Estimated upside | +$413 (best CT result across 59 days) | +$5K-$15K (ALUR alone could be +$5K with runner; SHPH, ROLR add more) |

---

## Estimated Impact

Using the Jan 2025 + 2026 YTD data to estimate runner mode impact:

### ALUR Jan 24 (2025)
- Current: sq_target_hit at $8.40, +$1,990 on full position
- Runner mode: sell 50% at $8.40 (+$995), hold 50% with 5m-low trail
- 5m-low trail on ALUR: stock was making new 5m highs continuously from $8.40 to ~$15+ before first meaningful pullback
- Conservative exit at $14 on runner: +$995 + (50% × ($14-$8.04) × shares) ≈ +$995 + $3,700 = **+$4,695**
- Delta vs current: **+$2,705**

### SHPH Jan 20 (2026)
- Current SQ P&L: +$3,115 (3 cascade entries)
- Stock went $2.75 → $25. Even a runner portion held from $3.50 to $8 adds thousands.
- Estimated runner delta: **+$2,000-$5,000**

### ROLR Jan 14 (2026)
- Current SQ P&L: +$12,601 (3 cascade entries)
- Each cascade entry hits sq_target_hit. Runner portions could capture more of the $21+ HOD.
- Estimated runner delta: **+$1,000-$3,000**

### YTD 2026 Aggregate
- 47 sq_target_hit trades across 2026 YTD. If runner mode captures even $200 average additional on 30% of them (14 trades): 14 × $200 = **+$2,800**
- On the big runners (SHPH, ROLR, VERO, EEIQ, ASTC — ~6 stocks): **+$5,000-$15,000**

**Total estimated uplift: +$8,000-$18,000 across YTD** — similar to original CT estimate but with far simpler implementation and near-zero regression risk.

---

## Implementation Path

### Phase 1: Partial Exit at 2R (Safest Change)
1. When sq_target_hit fires, sell 50% of position instead of 100%
2. Move stop on remaining 50% to entry price (breakeven floor)
3. Set trail on runner to prior 5m candle low
4. Exit runner at 12:00 ET or when trail is hit
5. Gate behind `WB_RUNNER_MODE=0` (OFF by default)

### Phase 2: Wider Cascade Trails
1. On 2nd SQ entry (same stock same session): use 3R target, 5m-low trail
2. On 3rd SQ entry: use 4R target, 5m-low trail
3. Gate behind `WB_CASCADE_WIDE_TARGET=0`

### Phase 3: Validation
1. Regression: VERO, ROLR must show same or better P&L with runner mode
2. Value-add: ALUR, SHPH, GDTC should show clear improvement
3. Edge case: Stocks that reverse after 2R (the ones where sq_target_hit IS the top) — runner portion should lose minimal due to breakeven floor

### Testing the Risk
The key risk is: on some stocks, $8.40 IS the top. The stock hits 2R and reverses hard. Currently, sq_target_hit captures the full 2R. With runner mode, we capture 1R on 50% (from the partial) and potentially $0 on the runner 50% (breakeven exit). So the worst case is: we make $995 instead of $1,990 on that trade.

**How often does this happen?** From 2026 YTD: sq_target_hit is 47/47 winners. If 30-40% of those reverse immediately after target, the runner portions lose ~$0-$200 each (breakeven floor protects). But the 60-70% that keep running add $200-$5,000 each. The expected value is strongly positive.

---

## CT vs Runner Mode: The Decision

| | CT (V2 best) | Runner Mode |
|--|-------------|-------------|
| Development effort | Already built, 4 iterations | New implementation needed |
| Test results | +$413 (1 stock, 59 days) | Untested (estimated +$8K-$18K) |
| Regression risk | $0 with cascade gate (proven) | Near-zero (breakeven floor on runners) |
| Code complexity | 335-line detector + 15 env vars | ~50 lines of exit logic + 3-4 env vars |
| Stocks it helps | Only single-SQ stocks (EEIQ) | All SQ stocks, especially big runners |
| Can coexist? | Yes — CT is entry, runner is exit | Yes — but runner mode may eliminate the need for CT |

**Recommendation: Implement runner mode first.** It's simpler, higher-EV, and helps on the stocks where we leave the most money (ALUR, SHPH, ROLR). If runner mode captures the continuation, CT becomes unnecessary. If runner mode alone isn't enough, CT can be layered on top later — and it would benefit from wider runner trails too.

---

## The Bottom Line

We spent a day trying to build a new entry strategy (CT) to capture continuation moves. The data shows the bot already enters at the right levels — the SQ cascade is working. The problem is it can't hold the positions. ALUR: entered at $8.04, exited at $8.40, stock went to $20. That's not an entry problem. That's an exit problem.

Runner mode — partial exit at 2R with a wider trail on the remaining position — is the simplest, safest, highest-EV path to capturing the continuation money we're leaving on the table. One exit enhancement instead of an entire separate strategy.

The squeeze works. Let it run.
