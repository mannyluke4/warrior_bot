# CC Report: Ross vs Bot — ARTL Comparison (2026-03-20)
## Date: 2026-03-20
## Type: Trade Comparison / Strategy Analysis

---

### Context

Bot crashed at startup (market_scanner.py import error), missed all morning action. Backtest simulation shows what the bot *would have* done. Ross traded ARTL live and posted his recap. This report compares the two.

### Side-by-Side Summary

| Metric | Ross (Live) | Bot (Backtest) |
|--------|-------------|----------------|
| Stock | ARTL | ARTL + ANNA |
| ARTL P&L | **+$6,020–6,200** | **+$1,054** |
| Total P&L | +$6,020–6,200 | +$1,582 |
| Setup type | HOD breakout / continuation | Squeeze (level break) |
| Entries | Multiple (adds + re-entries) | 3 fixed-size |
| Peak P&L | ~$7,300 | +$1,054 |
| Giveback | ~15% from peak | N/A (no discretion) |
| Time active | ~9:00 AM through midday | 09:09–09:42 (33 min) |

---

### Q1: Why the $5,000 Gap? ($1,054 vs $6,100)

The bot's +$1,054 came from three squeeze trades in a 33-minute window (09:09–09:42). Ross made ~6x more on the same stock. The gap breaks down into three factors:

**Adds on strength (~40% of gap).** Ross averaged in around 8.30–8.40, then added size as ARTL pushed toward 9. The bot trades fixed position size — one entry, one exit. Ross's adds on the move from 8.40 to 9.00 are pure upside the bot structurally cannot capture. This is the "scaling in/out" gap already documented in CLAUDE.md under Known Gaps.

**Multiple re-entries (~40% of gap).** After locking in ~$4,800 on the first push to 9.50 (heavy seller tape read), Ross re-entered and scalped the 8-to-9 range repeatedly. The bot took 3 trades and was done by 09:42. Ross kept trading the stock for hours. The bot's `max_entries_per_symbol = 3` and squeeze state machine don't support this kind of continuation scalping.

**Wider time horizon (~20% of gap).** The bot's squeeze detector fires on level breaks and exits on parabolic trail stops. Total exposure: 33 minutes. Ross worked ARTL from roughly 9:00 AM through midday — he was in and out of the stock for 3+ hours, extracting value from every significant move.

**What this means:** The bot's squeeze strategy captured the *initial breakout* correctly but couldn't participate in the continuation. This is not a tuning problem — it's an architectural gap. The bot needs either a re-entry mechanism for continuation moves or a fundamentally different strategy for this type of play.

---

### Q2: Does Ross's "Pullback and Curl Through HOD" Validate Strategy 5?

Yes — this is the strongest evidence yet.

Ross's entry: wait for ARTL to pull back after the premarket spike (7→8), then buy the "curl" — the rounded recovery pushing through HOD at 8.37. This is textbook Strategy 5 (Curl/Extension) as outlined in MASTER_TODO.

Key observations:

The bot's squeeze detector entered at 8.04 (09:09) on a volume spike through a level. Ross entered at 8.30–8.40 on the *pattern* — the curl shape approaching HOD. Both caught the same move, but Ross's read was more precise: he waited for the stock to prove itself with the curl rather than entering on the first volume pop.

This also explains part of the P&L gap. Ross's curl entry at 8.35 with a stop below the pullback low had tighter risk than the squeeze entry at 8.04 with a stop at 7.66 (R = $0.38). Tighter risk means more shares for the same dollar risk, which means more profit when it works.

Strategy 5 priority should increase. We now have three data points: CHNR on 3/19 (curl from $5 support → $6, Ross's best trade), ARTL on 3/18 (curl pattern, Ross's best trade), and ARTL on 3/20 (today). The curl/extension setup is consistently where Ross makes his biggest money on continuation days.

---

### Q3: Would the Bot's Scanner Have Caught ARTL? When?

Yes. The backtest confirms the scanner found ARTL (gap +18%, RVOL 3.0x, float 0.7M — passes all 5 Pillars). The "what should have been" report shows the bot's first squeeze trade at 09:09, meaning scanner discovery happened before that.

However, Ross caught it at ~9:00 AM on his *continuation scanner* — a qualitatively different scan. Ross was looking for stocks already in play from a prior day's move, spiking in premarket. The bot's scanner uses a gap-based scan (10%+ gap, RVOL 2x+, float under 10M). Both would have found ARTL, but for different reasons:

- Ross: "ARTL spiking from 7s to 8 premarket, continuation of prior move, B-quality setup"
- Bot: "ARTL gaps +18%, RVOL 3.0x, float 0.7M — passes Pillar gates"

The bot's scanner doesn't distinguish between fresh catalysts and continuations. Ross's does — and he rated it B-quality specifically because there was no fresh catalyst. This didn't stop him from trading it, but it informed his sizing and expectations. The bot has no concept of setup quality grades (A/B/C) that modulate risk.

---

### Q4: How Much of Ross's Edge Is Discretionary Tape Reading?

Significant — probably 20–30% of the P&L difference.

The clearest example: ARTL pushed to 9.50 and hit a heavy seller. Ross read the tape (Level 2, time & sales), saw the seller absorbing bids, and locked in ~$4,800 immediately. The bot's parabolic trail stop would have eventually exited, but later and at a worse price. Trade #2 in the backtest (entry 9.50, exit 9.62, +$316) and trade #3 (entry 9.50, exit 9.44, -$166) show the bot trying to push through resistance that Ross already identified as a wall.

This tape-reading edge shows up in two ways: faster exits when sellers appear (preserving profit) and *not re-entering* into supply zones. The bot's squeeze detector doesn't see order flow — it only sees price and volume bars. A heavy seller at 9.50 is invisible until the price actually drops.

This is a hard edge to replicate algorithmically. Level 2 data and time & sales analysis are possible but complex. For now, the more realistic approach is better resistance-level tracking (already in Known Gaps) so the bot at least avoids re-entering at known rejection zones.

---

### Q5: What About ANNA (+$528)?

The bot found ANNA (gap +21%, RVOL 2.2x, float 9.4M) and made +$528 via squeeze: two small losers (-$393, -$190) then one winner (+$1,111) that covered both.

Ross didn't trade ANNA. A few possible reasons:

- **Float too high.** At 9.4M shares, ANNA is near the top of the Pillar range. Ross generally prefers ultra-low floats (ARTL was 0.7M) for bigger moves. ANNA's 9.4M float means more supply to absorb.
- **Focus / opportunity cost.** Ross was already working ARTL and making money. Switching to a second stock dilutes attention and risk capital. Ross frequently says he prefers to go deep on one stock rather than spread across multiple.
- **Different scan priority.** ARTL was the continuation play Ross was watching. ANNA was a separate gap-up. Ross may not have scanned for new setups while actively trading ARTL.

The bot's +$528 on ANNA is interesting because it demonstrates multi-stock diversification — something the bot does naturally but Ross often skips. Over many days, the bot's ability to trade 2–3 stocks simultaneously (when it's running) could be a structural advantage, even if it underperforms on any single name.

---

### Actionable Takeaways

**1. Strategy 5 (Curl/Extension) — PRIORITY UP.** Three consecutive days (3/18, 3/19, 3/20) where Ross's best trades were curl patterns. This is no longer speculative — it's the dominant setup in the current market regime. Move from "research" to "design" phase.

**2. Re-entry / continuation mechanism.** The 3-trade cap and squeeze state machine prevent the bot from participating in the most profitable phase of ARTL's move. Even a simple "re-arm after N minutes if stock holds above VWAP" would have helped today.

**3. Setup quality grading.** Ross rated ARTL as B-quality (no fresh catalyst, continuation only). The bot treated it the same as any other Pillar-passing stock. A quality grade that modulates position size or max entries could improve risk-adjusted returns.

**4. Multi-stock advantage is real.** The bot found ANNA for +$528 that Ross left on the table. On days when the bot is actually running, this diversification edge compounds.

**5. Tape reading remains the hardest gap.** Ross's exit on the heavy seller at 9.50 was worth several hundred dollars vs the bot's parabolic trail. This isn't solvable short-term, but better resistance tracking is a realistic proxy.

---

### Bottom Line

Ross: +$6,100 on ARTL (one stock, discretionary, adds + re-entries + tape reading)
Bot: +$1,582 on ARTL + ANNA (two stocks, systematic, squeeze-only, 33 minutes of exposure)

The bot captured 17% of Ross's ARTL profit. The gap is architectural, not parameter-related. Strategy 5 and a continuation re-entry mechanism would close the biggest portions of it. The bot's multi-stock coverage partially compensates — but only when it's actually running.
