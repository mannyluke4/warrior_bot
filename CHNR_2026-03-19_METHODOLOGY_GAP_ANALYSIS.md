# CHNR 2026-03-19 — Methodology Gap Analysis
## Bot vs Ross Cameron: Scanner Caught It, Bot Took 0 Trades

**Date**: 2026-03-19
**Stock**: CHNR (Chinese acquisition news, 7:15 AM ET)
**Scanner**: +70.5% gap, 0.52M float, 381x RVOL, 16.6M PM volume, Profile A
**Ross Result**: +$2,506 (peaked at +$5,000, gave back ~$2,500 on failed breakout)
**Bot Result**: 0 trades

---

## 1. Timeline: Scanner vs Reality

| Time | Event | Ross | Our Scanner | Our Bot |
|------|-------|------|-------------|---------|
| 7:15 | News hits | — | — | — |
| 7:16 | First alert at $4.34 | Scanner fires | **NOT YET** | — |
| 7:16-8:00 | Stair-step $4.34→$6.00 | Makes tea, misses it | **NOT YET** | — |
| 8:00 | Rescan discovers CHNR | — | **FOUND at $5.63** | Sim starts, state machine COLD |
| 8:00-8:05 | Warmup period | — | — | 5-bar warmup blocks ARM |
| ~8:05+ | Consolidation/pullback phase | Takes VWAP curl trade | — | Exhaustion + stale filter block |

**Scanner gap: 44 minutes late.** Ross's scanner caught CHNR at 7:16. Ours found it at 8:00 via rescan. The entire first leg ($3.50 → $6.00) happened in that window.

Even if squeeze V2 were enabled, starting at 08:00 means HOD was already set during the 7:15-8:00 run. The HOD gate would block squeeze entries on any bar that doesn't make a new session high — and by 8:00, CHNR was consolidating below its earlier peak.

---

## 2. Ross's Actual Trades Mapped to Our Strategies

### Trade 1: VWAP Curl (scratched at -$67)
- **What**: Break of VWAP → curl back up → entered ~$5.15, flushed to $5.00, exited breakeven
- **Our strategy**: **Strategy 4 — VWAP Reclaim** (NOT BUILT)
- **Would MP catch this?** No. This isn't a pullback-after-impulse. It's a reclaim of a key level from below.
- **Would Squeeze catch this?** No. No volume explosion or new HOD — this is a consolidation-phase trade.

### Trade 2: Curl From Support (+~$2,000)
- **What**: Stock curls up from ~$5.00 support after deeper pullback, enters ~$5.00-5.20, rides to $6.00
- **Our strategy**: **Strategy 5 — Curl/Extension** (NOT BUILT)
- **Would MP catch this?** Unlikely. The pullback was extended (multiple bars), and the recovery is a gradual curl, not a sharp impulse→pullback→breakout. The MP detector's 3-bar pullback limit and MACD filter would reset multiple times during this slow curl.
- **Would Squeeze catch this?** No. Not a volume explosion — it's a gradual recovery.
- **Key insight**: Ross entered on a *rounded bottom* approaching prior support, looking for re-ignited momentum. This is the textbook "curl" pattern we identified in the ARTL gap analysis.

### Trade 3: VWAP Break + $6.00 Whole Dollar Break (+~$2,000)
- **What**: VWAP reclaim → break through $6.00 whole dollar → squeeze to $6.60
- **Our strategy**: **Strategy 4 (VWAP Reclaim) → Strategy 2 (Squeeze/Breakout) hybrid**
- **Would Squeeze catch the $6.00 break?** Possibly — IF the bot had been watching since 7:16 AND the stock was making new HOD at that point. But at 08:00+, the $6.00 level was already tested and CHNR was below its prior HOD of ~$6.00+. HOD gate blocks.
- **Key insight**: Ross uses VWAP reclaim as a *lead-in signal* that the stock is ready for a breakout through whole-dollar resistance. The VWAP reclaim is the setup; the whole-dollar break is the entry. We'd need both Strategy 4 and Strategy 2 to replicate this.

### Trade 4: Oversized Add at Highs (gave back ~$2,500)
- **What**: Added 20k shares at $6.50 for $6.50→$7.00 break, stock topped at $6.60 and flushed
- **Our strategy**: Strategy 2 (Squeeze) would attempt this — but with **probe sizing** (0.5x) and **$500 dollar cap**
- **Bot advantage**: Ross sized up aggressively (20k shares) at the tipping point and gave back $2,500. Our probe sizing + dollar cap would have limited this to ~$250-500 loss. **This is where our risk management outperforms Ross's gut instinct.**

---

## 3. Root Cause Analysis: Why 0 Trades

### Cause 1: Scanner Timing (PRIMARY)
- Found at 08:00, 44 minutes after news. First leg completely missed.
- The `discovery_method: "rescan"` means CHNR wasn't caught in premarket — it only appeared when the continuous rescan cycle checked.
- Ross's scanner fires in real-time on price/volume explosions. Our `scanner_sim.py` runs at fixed intervals.
- **Fix needed**: Real-time streaming scanner that catches intra-premarket moves, not just gap-up rankings at 7:00 AM.

### Cause 2: No Strategy for Ross's Actual Setups
Even with perfect scanner timing, Ross's 3 winning sequences were:
1. VWAP Reclaim → **Strategy 4 (not built)**
2. Curl from support → **Strategy 5 (not built)**
3. VWAP reclaim + whole dollar break → **Strategy 4+2 combo (partially built)**

The only thing our existing strategies COULD have caught was the first leg stair-step ($4.34→$6.00), which Ross himself missed. That's a textbook squeeze — and our squeeze V2 would have attempted it if the scanner had found CHNR by 7:16.

### Cause 3: Bot Infrastructure Blocks (secondary, would apply even with perfect timing)
- **Warmup gate**: 5 bars after sim_start before any ARM possible
- **Exhaustion filter**: 70% gap = VWAP distance at ~50%+ above VWAP — blocked by dynamic scaling
- **Stale filter**: After 30+ minutes without new HOD, blocks all new entries
- **Extended move reset**: 5+ consecutive green bars resets impulse structure

---

## 4. Strategy Priority Reassessment

Based on CHNR + ARTL data (our two live-day analyses):

| Strategy | ARTL Gap (Ross $9,653 vs Bot $922) | CHNR Gap (Ross $2,506 vs Bot $0) | Priority |
|----------|-------------------------------------|-------------------------------------|----------|
| **Strategy 2: Squeeze** | Would catch first leg (+$6,963 in V2) | Would catch first leg IF scanner was earlier | **HIGH — V2 done, needs YTD validation** |
| **Strategy 4: VWAP Reclaim** | Ross used it on ARTL reclaim | Ross's bread-and-butter on CHNR (2 of 3 trades) | **HIGH — Should be NEXT to build** |
| **Strategy 5: Curl/Extension** | Ross's best ARTL trade was a curl | Ross's biggest CHNR winner was curl from support | **HIGH — Pattern shows up in BOTH analyses** |
| **Strategy 3: Dip-Buy** | Ross bought ARTL dip at $6.73 | Not applicable on CHNR | MEDIUM |

**Key insight**: Strategy 4 (VWAP Reclaim) and Strategy 5 (Curl/Extension) are the two most consistent patterns across both live-day analyses. Ross uses them repeatedly. These are NOT micro-pullback variants — they're fundamentally different setups that our MP detector can't catch even with tuning.

---

## 5. Scanner Timing Deep Dive

### Current Scanner Architecture
- `scanner_sim.py` generates scanner_results at fixed intervals
- Premarket scan at ~6:25-7:00 catches gap-up stocks ranked by RVOL/float/gap
- Continuous rescan catches late-breaking movers

### CHNR's Problem
- CHNR's prev_close was $3.30, so before 7:15 AM it was a low-gap stock (maybe 10-15%)
- At 7:15, acquisition news dropped → price exploded from ~$3.50 to $4.34 in 1 minute
- By 7:16, it qualified as a 30%+ gapper — but the premarket scan had already run
- The rescan cycle didn't catch it until 08:00

### What Needs to Change
1. **Streaming scanner**: Instead of fixed-interval rescans, the scanner should stream price/volume data and fire alerts when a stock crosses thresholds in real-time.
2. **News integration**: The bot has no awareness of news catalysts. Ross's first signal was the headline, not the price.
3. **Faster rescan interval**: Even without streaming, a 5-minute rescan interval (vs the current interval) would have caught CHNR by ~7:20.

---

## 6. What the Bot Did Right (Important!)

Despite 0 trades, the system performed well in several ways:

1. **Scanner caught the right stock**: CHNR was #1 ranked with 70.5% gap, 0.52M float, 381x RVOL. The scanner criteria are solid.
2. **Risk management would outperform**: Ross gave back $2,500 on the failed $6.50 breakout. Our probe sizing + dollar cap limits this to ~$500.
3. **MACD filter alignment**: Ross explicitly skipped a trade because MACD was negative. Our MP detector does the same thing.
4. **Single-stock focus**: The scanner identified 4 candidates and CHNR was the clear #1. Ross also focused exclusively on CHNR.

---

## 7. Actionable Next Steps

### Immediate (this week)
- [x] Run 55-day YTD backtest with squeeze V2 (directive written)
- [ ] Have CC cache CHNR tick data for 2026-03-19 so we can backtest it

### Near-term (next 1-2 weeks)
- [ ] **Design Strategy 4: VWAP Reclaim** — Ross's most-used pattern. Trigger: price crosses above VWAP from below, first candle makes new high. This is a specific, implementable signal.
- [ ] **Design Strategy 5: Curl/Extension** — Rounded bottom approaching prior HOD/resistance. More complex — needs concept of "support zone" and "gradual recovery."
- [ ] **Scanner timing improvement** — Reduce rescan interval or add streaming mode for real-time news-driven detection.

### Longer-term
- [ ] News integration (news API + catalyst scoring)
- [ ] Multi-timeframe analysis (5m chart for trend, 1m for entry — Ross uses both)

---

## Appendix: Ross's CHNR Execution Stats
- Total volume: ~279,000-300,000 shares across 66 tickets
- Commission estimate: ~$400 (0.002/share blended)
- Peak P&L: +$5,000 | Realized: +$2,506
- Biggest size: 30,000-34,000 shares on VWAP curl, 20,000 share add at highs
- Key levels used: VWAP, $5.00 (support), $6.00 (whole dollar), $6.50-7.00 (attempted breakout)

---

*Analysis by Cowork (Opus) — 2026-03-19*
