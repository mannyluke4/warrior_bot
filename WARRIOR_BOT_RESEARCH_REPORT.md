# Warrior Bot — Comprehensive Research Report
**Date: February 26, 2026**
**Prepared for: Luke (delightedpath.net)**

---

## Executive Summary

The Warrior Bot is an automated day trading system designed to replicate Ross Cameron's (Warrior Trading) micro-pullback strategy on small-cap momentum stocks. After 11 completed trade studies comparing the bot's backtested performance against Ross's actual trades, the project has produced actionable data on where the bot excels, where it fails, and what needs to change.

| Metric | Value |
|--------|-------|
| **Bot net P&L across 11 studies** | **+$5,041** |
| Bot wins | 3 outright wins (VERO +$6,890, GWAV +$6,735, ANPA +$4,368) |
| Bot losses | 5 losses (ROLR, TNMG, LCFY, PAVM, ACON) |
| Bot breakeven/minimal | 3 (MLEC +$178, TWG $0, FLYX -$703) |
| **Ross net P&L across same 11 stocks** | **~$265,000** |
| P&L gap explanation | Ross trades with $500K+ buying power vs bot's $30K; scales into 30K-50K share positions |
| Trade profiles identified | 6 (A through F) |
| Code fixes implemented | 6 (net +$2,203 improvement, +26% across all studies) |
| Core weaknesses identified | 6, each with researched algorithmic solutions |
| New stock candidates for studies | 19 stocks from recap video research |
| Ross's YTD 2026 | ~$555K profit, 73% win rate, avg 3-min hold on winners |

**Key takeaway:** The bot's 3 wins share a common thread — early premarket detection (VERO) or mechanical discipline beating human emotion (ANPA, GWAV). The bot's losses cluster in two failure modes: entering too late on fast movers (Profile B) and buying into resistance without level awareness (Profile C). Both are solvable with targeted algorithmic improvements.

---

## Section 1: Statistical Analysis of 11 Trade Studies

### 1.1 Complete Study Results

| # | Stock | Date | Float | Gap% | Bot P&L | Ross P&L | Profile | Key Finding |
|---|-------|------|-------|------|---------|----------|---------|-------------|
| 1 | ROLR | 01/14 | 4.2M | +16% | -$889 | +$85,000 | A: Early Bird | BE exits killed parabolic runner mid-move |
| 2 | MLEC | 02/13 | 0.3M | +94% | +$178 | +$43,000 | B: Fast PM | Entry 10 min late, 2x the price Ross got |
| 3 | TWG | 01/20 | 1.1M | +155% | $0 | +$20,790 | B: Fast PM | Bot completely shut out — zero trades |
| 4 | VERO | 01/16 | 0.8M | +36% | **+$6,890** | +$3,400 | A: Early Bird | **BOT WON** — 07:03 entry beat Ross |
| 5 | TNMG | 01/16 | 5.5M | +25% | -$481 | +$2,000 | E: Trap | Stale filter saved $1K on late re-entry |
| 6 | GWAV | 01/16 | 0.4M | +22% | **+$6,735** | +$4,000 | D: Flash Spike | **BOT WON** — BE exit captured spike perfectly |
| 7 | LCFY | 01/16 | — | halt | -$1,627 | +$10,000 | C/F: Resistance+Halt | Bot chopped at $6-$6.50 resistance 3 times |
| 8 | PAVM | 01/21 | 0.8M | +80% | -$2,800 | +$43,950 | B: Fast PM | Entered 30x available volume at session low |
| 9 | ACON | 01/08 | 2.2M | +30% | -$2,630 | +$9,293 | C: Resistance | Entry $8.22 vs Ross $7.60 — $0.62 gap = $4K+ edge |
| 10 | FLYX | 01/08 | 3.5M | +15% | -$703 | positive | A: Early Bird | Bot had BETTER entry ($4.91 vs $5.89) but BE exit killed winner |
| 11 | ANPA | 01/09 | 1.8M | +40% | **+$4,368** | -$11,000 | — | **BOT WON** — MACD gate saved from crash, caught 2nd breakout |

### 1.2 Win/Loss Breakdown by Profile Type

| Profile | Stocks | Bot Wins | Bot Losses | Bot B/E | Net Bot P&L | Net Ross P&L | Verdict |
|---------|--------|----------|------------|---------|-------------|--------------|---------|
| **A: Early Bird** | VERO, ROLR, FLYX | 1 | 2 | 0 | +$5,298 | +$88,400+ | Bot strength — losses from BE exits killing winners, not bad entries |
| **B: Fast PM** | MLEC, TWG, PAVM | 0 | 1 | 2 | -$2,622 | +$107,740 | Biggest weakness — bot structurally too slow |
| **C: Resistance** | ACON, (LCFY partial) | 0 | 1 | 0 | -$2,630 | +$9,293 | No level awareness — enters INTO resistance |
| **C/F: Resistance+Halt** | LCFY | 0 | 1 | 0 | -$1,627 | +$10,000 | Dual failure: resistance + post-halt blindness |
| **D: Flash Spike** | GWAV | 1 | 0 | 0 | +$6,735 | +$4,000 | Bot excels — mechanical speed beats human reaction |
| **E: Trap** | TNMG | 0 | 1 | 0 | -$481 | +$2,000 | Stale filter prevented deeper loss |
| **Unclassified** | ANPA | 1 | 0 | 0 | +$4,368 | -$11,000 | Bot discipline > human emotion |

### 1.3 Average P&L by Profile

| Profile | Avg Bot P&L | Avg Ross P&L | Bot Edge? |
|---------|-------------|--------------|-----------|
| A: Early Bird (n=3) | +$1,766 | +$29,467+ | Potential — 2 of 3 losses were fixable (parabolic exit issue) |
| B: Fast PM (n=3) | -$874 | +$35,913 | No — structural speed disadvantage |
| C/C+F: Resistance (n=2) | -$2,129 | +$9,647 | No — needs level tracking |
| D: Flash Spike (n=1) | +$6,735 | +$4,000 | **Yes** — bot beat Ross |
| E: Trap (n=1) | -$481 | +$2,000 | No — but stale filter limits damage |
| Unclassified (n=1) | +$4,368 | -$11,000 | **Yes** — bot discipline wins |

### 1.4 Float Correlation with Bot Performance

| Float Range | Stocks | Bot Avg P&L | Observation |
|-------------|--------|-------------|-------------|
| < 1M (micro) | MLEC (0.3M), VERO (0.8M), GWAV (0.4M), PAVM (0.8M) | +$2,751 | Mixed — includes 2 of 3 wins but also PAVM disaster |
| 1M – 2M | TWG (1.1M), ANPA (1.8M) | +$2,184 | ANPA win carried this bucket |
| 2M – 4M | ACON (2.2M), FLYX (3.5M) | -$1,667 | Both losses — resistance and exit issues |
| 4M+ | ROLR (4.2M), TNMG (5.5M) | -$685 | Moderate losses |
| Unknown | LCFY | -$1,627 | Halt scenario, float not available |

**Finding:** The bot performs best on micro-float stocks (<1M shares) — average P&L of +$2,751. This makes sense: micro-float stocks produce the most extreme moves, giving the bot's mechanical entry speed an edge. However, micro-float also includes the bot's biggest weakness (PAVM at -$2,800), suggesting that float alone isn't predictive — the profile type matters more.

### 1.5 Gap% Correlation with Bot Performance

| Gap% Range | Stocks | Bot Avg P&L | Observation |
|------------|--------|-------------|-------------|
| 10-25% | ROLR (+16%), GWAV (+22%), FLYX (+15%), TNMG (+25%) | +$1,166 | Moderate gaps — includes GWAV win |
| 26-50% | VERO (+36%), ACON (+30%), ANPA (+40%) | +$2,876 | Sweet spot — includes 2 of 3 bot wins |
| 51-100% | MLEC (+94%), PAVM (+80%) | -$1,311 | High gaps hurt — bot enters too late on already-extended stocks |
| 100%+ | TWG (+155%) | $0 | Extreme gap — bot completely shut out |

**Finding:** The bot performs best on moderate gaps (26-50%). Stocks with extreme gaps (80%+) tend to be Profile B (fast movers) where the bot can't keep up. The 26-50% range likely represents stocks with enough momentum to trigger the state machine but not so much that the move is already over before entry.

### 1.6 Common Traits of Bot Wins

All three bot wins share identifiable characteristics:

1. **VERO (+$6,890):** Early premarket detection at 07:03 AM — beat Ross to the punch. Bot's scanner advantage on a slowly building PM ramp.
2. **GWAV (+$6,735):** Flash spike on ultra-micro float. BE exit on 10-second bars caught the reversal faster than human reaction time. Mechanical speed advantage.
3. **ANPA (+$4,368):** MACD gate prevented entry on the first spike (where Ross lost -$11,000), then caught the second breakout. Mechanical discipline > human emotion.

**Pattern:** The bot wins when it can either (a) detect early and act before humans, or (b) enforce mechanical rules that protect against emotional trading mistakes.

### 1.7 Common Traits of Bot Losses

The five clear losses share patterns too:

1. **Profile B losses (MLEC, TWG, PAVM):** The state machine requires bars to build structure. By the time a pattern confirms, the move is fading. Average entry delay: 10 min to 2+ hours late.
2. **Profile C losses (ACON, LCFY):** Bot enters at resistance without knowing it's resistance. ACON entered $8.22 (Ross at $7.60). LCFY entered $6-$6.50 three times — same resistance zone.
3. **Profile A losses with fixable cause (ROLR, FLYX):** Both had good entries but BE exits killed winning positions during genuine parabolic momentum. FLYX bot actually had a BETTER entry than Ross ($4.91 vs $5.89) but still lost.

---

## Section 2: Ross Cameron's Methodology — Key Findings

*Based on 757 lines of methodology research compiled from Ross's book "How to Day Trade", Warrior Trading YouTube channel, warriortrading.com documentation, and community analysis. Full details in `/home/user/workspace/research/ross_cameron_methodology.md`.*

### 2.1 Scanner & Stock Selection (5 Pillars)

All five pillars must be met before considering any trade:

| Pillar | Criteria | Preferred / Ideal | Notes |
|--------|----------|-------------------|-------|
| **1. Float** | < 20M shares | < 10M preferred, < 5M ideal | Low float = limited supply = bigger moves on same demand |
| **2. Price** | $2–$20 | Sweet spot $5–$10 | Avoids sub-$1 (moves in thousandths). Rarely above $20 |
| **3. Gap%** | ≥ 4% pre-market | Prefer 10%+, best 20-100%+ | Gaps under 4% tend to fill |
| **4. Relative Volume** | ≥ 5× daily average | 50-500× on best trades | Measured against 50-day average. 134× cited as strong example |
| **5. Catalyst** | News required | Biotech/FDA = strongest | Clinical trials, contracts, FDA approvals, acquisitions |

**Ranking among candidates:** When multiple stocks qualify on the same day, Ross picks the one with: highest relative volume → lowest float → cleanest chart → strongest catalyst.

### 2.2 Entry Methodology

**3-Tranche Scaling:**
- **Tranche 1:** 33-50% starter position on first setup confirmation
- **Tranche 2:** Add on pullback confirmation (micro-pullback to VWAP or 9 EMA)
- **Tranche 3:** Add on continuation/breakout to new HOD

**Order Types:**
- Limit orders ONLY — at the ask or slightly above
- Never market orders (avoids slippage on illiquid small caps)
- Uses Level 2 and Time & Sales as **confirmation**, not primary signal — "chart pattern is primary"

**Entry Philosophy:**
- "Breakout or bailout" — if the trade doesn't work within 60-120 seconds, exit immediately
- Buys the first micro-pullback after initial squeeze, NOT the initial pop itself
- Uses 10-second charts for entries on fast-moving stocks
- Pre-positions on dips near support/VWAP, not chasing breakouts

### 2.3 Exit Methodology

**Scale-Out Framework:**
- Sell 50% at first target (1:1 risk/reward)
- Hold 50% as a "runner" with trailing stop

**Trailing Stop:**
- 9 EMA on 5-minute chart is primary trailing indicator
- Tightens stop as position moves further into profit

**Full Exit Triggers (any one = close the trade):**
1. Large red candle (bearish engulfing on 1-min or 5-min)
2. Topping tail / shooting star pattern
3. Close below 9 EMA on 5-minute chart
4. Thick Level 2 seller appearing (large block on the ask)
5. 3rd halt up (momentum exhaustion signal)
6. MACD crossover on 5-minute chart (bearish cross)

### 2.4 Risk Management

| Rule | Detail |
|------|--------|
| **Quarter-size start** | Trade at 25% of normal size until up $1K on the day |
| **Daily max loss** | $5K hard stop — done trading for the day |
| **3-loss rule** | After 3 consecutive losses: stop for the day OR trade minimum size only |
| **Never average down** | Never add to a losing position |
| **Target ratio** | 2:1 profit/loss ratio minimum |
| **Position sizing** | Based on stop distance, not fixed dollar amount. Risk = entry price minus stop, size = max_risk / risk_per_share |

### 2.5 Session Management

| Time Window (ET) | Activity | Notes |
|------------------|----------|-------|
| 4:00-7:00 AM | Scanner review | WT scanners available from 4 AM; building watchlist |
| 7:00-9:30 AM | **Pre-market trading** | ~50% of Ross's trading occurs here. Early movers get entered |
| 9:30-10:30 AM | **Primary trading window** | 80% of profitable trades in first 30-60 min after open |
| 10:30-11:00 AM | Reduced activity | Momentum fading; tighter criteria |
| 11:00 AM-4:00 PM | Generally done | Rare exceptions for afternoon squeezes |

**Key stat:** Ross's average hold time is 3 minutes on winners and 2 minutes on losers. This is an extremely fast-twitch style that maximizes the opening momentum window.

### 2.6 Methodology Gaps Between Bot and Ross

| Feature | Ross Cameron | Warrior Bot | Gap Impact |
|---------|-------------|-------------|------------|
| **Position sizing** | 3-tranche pyramid (25%→35%→40%) | All-or-nothing single entry | **HIGH** — missed adds on winners, oversized on losers |
| **Entry type** | Limit at ask + dip buys near support | Market/limit on breakout confirmation | **HIGH** — enters $0.50-$1.00 higher than Ross |
| **Resistance awareness** | Tracks whole/half dollars, PM high, HOD, VWAP | None | **HIGH** — bot buys INTO resistance repeatedly |
| **Exit scaling** | Sell 50% at 1:1, trail rest with 9 EMA | All-or-nothing exit | **MEDIUM** — misses runners, can't lock in partial profit |
| **Speed** | Enters on first micro pullback (10s chart) | Waits for 1-min state machine confirmation | **HIGH** — 10+ min late on fast movers (Profile B) |
| **Post-halt** | Watches L2, buys first green tape after reopen | State machine breaks on halt | **MEDIUM** — misses recovery trades entirely |
| **Daily risk management** | Quarter-size start, scale up after +$1K | Fixed size all day | **LOW** — bot uses fixed $1K max risk (acceptable for now) |
| **L2/Time & Sales** | Uses for confirmation + detecting large sellers | No L2 data feed | **MEDIUM** — missing confirmation signal |
| **Chart timeframe** | 10-second for entry, 1-min + 5-min for management | 1-min primary, 10-second for exits only | **MEDIUM** — slower entry detection |
| **Catalyst assessment** | Grades news quality (FDA > PR > no news) | Binary news check only | **LOW** — most filtered stocks have news anyway |

---

## Section 3: New Stock Candidates for Studies

*From research of 11 Ross Cameron recap videos covering January-February 2026. 19 new stocks identified. Full details in `/home/user/workspace/research/ross_cameron_recaps.md`.*

### Priority 1: Profile A (Early Bird) Candidates — Confirm Bot Strength

These stocks had characteristics matching the bot's strongest profile: early premarket ramp, moderate gap, news catalyst. Studies would confirm whether the bot's early detection advantage is reproducible.

| Stock | Date | Setup | Ross Entry | Ross P&L | Why Study This |
|-------|------|-------|-----------|----------|----------------|
| **ELAB** | Jan 6 | News-driven, break through high after dip | ~$10.50 | +$3,500 | Classic dip-buy entry; test if bot enters early and holds |
| **BCTX** | Jan 27 | Breaking news (phase 2 breast cancer trial) | ~$5.00 | Profitable | Micro pullback for $5 break; bot's state machine should catch this |
| **SXTP** | Jan 28 | Biotech reverse split, inverted H&S | $5.80 | +$1,900 | 2-min hold time; fast in/out matches bot style |

### Priority 2: Profile B (Fast PM) Candidates — Understand Bot Weakness

These stocks test the bot's biggest weakness: fast premarket movers where the state machine can't confirm a pattern before the move is over. Critical for validating the "fast mode" solution.

| Stock | Date | Setup | Ross Entry | Ross P&L | Why Study This |
|-------|------|-------|-----------|----------|----------------|
| **HIND** | Jan 27 | Breaking news, two squeezes | ~$5 first, ~$7 second | Majority of +$59K day | $725K position, 45-50K shares; tests bot vs massive scaling |
| **GRI** | Jan 28 | Biotech reverse split + breaking news | $5.97-$6+ | ~+$33,500 | $4.50→$12 rip; bot likely misses entirely; confirms speed problem |
| **SNSE** | Feb 18 | Biotech halt, $200M placement | $27.53 | +$9,373 | Bought first pullback after 200%+ move; tests post-halt entry |
| **ALMS** | Jan 6 | News squeeze $10→$18 | ~$17 | +$5,146 | 61M float (outside normal range); tests float filter edge case |

### Priority 3: Profile C (Resistance) Candidates — Test Level Awareness

These stocks featured clear resistance levels that Ross navigated and the bot would likely have bought into. Studies would validate the LevelMap solution before implementation.

| Stock | Date | Setup | Ross Entry | Ross P&L | Why Study This |
|-------|------|-------|-----------|----------|----------------|
| **RYA** | Jan 23 | VWAP break after pullback, double top resistance | ~$3.80 | ~$3,800 | 25K shares; clear double top test case |
| **MOVE** | Jan 23 | Break through PM high $20.90, double top at $21.23 | $19.54 | ~$7,500 | Daily resistance at $21.23; would bot enter above it? |
| **SLE** | Jan 23 | Curl pattern, squeeze to $11.50 double top | ~$9.30 | ~$8,000 gross | Gave back $1,800 on failed add; tests resistance + sizing |

### Priority 4: Ross's Losses — Confirm Bot Mechanical Advantage

These are stocks where Ross lost money due to emotional decisions. The bot's mechanical discipline might produce better results.

| Stock | Date | Setup | Ross Entry | Ross P&L | Why Study This |
|-------|------|-------|-----------|----------|----------------|
| **BNAI** | Feb 5 | US tech, reverse split, news: terminated $50M equity agreement | $33.81 | -$7,900 | Ross hit huge seller, stopped out. Bot's $1K max risk = smaller loss? |
| **RVSN** | Feb 5 | Israeli reverse split, "Hail Mary" position | ~$5.50 | -$3,000 | Ross admitted small reckless position. Bot would likely skip entirely |

### Priority 5: Additional Candidates

These fill gaps in profile understanding or test edge cases:

| Stock | Date | Setup | Notes |
|-------|------|-------|-------|
| **OPTX** | Jan 6 | Low float, breaking news 8:26am | Sellers at $3.50-$3.75; couldn't break $4. Tests resistance + failed breakout |
| **APVO** | Jan 9 | Biotech sub-1M float, news | Ross gave back 30% from $9K peak. Round-trip fade test case |
| **ARNA** | Feb 5 | Spike, sell-off, rally back | 20K-share sellers reloading; tests tape-reading vs bot |
| **VNDA** | Feb 22 watchlist | Biotech FDA approval, +44% AH | Upcoming trade; watchlist candidate for live paper test |
| **VHUB** | Feb 22 watchlist | Recent IPO | Upcoming; limited float history |
| **NCI** | Feb 22 watchlist | Chinese luxury apparel IPO, watch >$11 | Upcoming; high-priced for bot's range |

### Study Completion Roadmap

| Phase | Studies | Target Count | Purpose |
|-------|---------|-------------|---------|
| Completed | 11 studies | 11 | Initial profile identification |
| Next batch (Priority 1+4) | ELAB, BCTX, SXTP, BNAI, RVSN | 5 | Confirm bot strengths + test loss avoidance |
| Second batch (Priority 2) | HIND, GRI, SNSE, ALMS | 4 | Quantify speed problem for fast mode design |
| Third batch (Priority 3+5) | RYA, MOVE, SLE, OPTX, APVO, ARNA | 6 | Validate resistance tracking before implementation |
| Watchlist (live) | VNDA, VHUB, NCI | 3 | Forward-looking live paper tests |
| **Total target** | | **29** | Statistically significant dataset |

---

## Section 4: Algorithmic Solutions — Implementation Guides

*Six core problems identified from the 11 trade studies. Each has a researched algorithmic solution with pseudocode. Full 1,275-line solution document at `/home/user/workspace/research/algo_solutions.md`.*

### Problem 1: Slow Detection on Fast Movers (Profile B Fix)

**Impact:** MLEC entered 10 min late at 2× Ross's price. PAVM entered 2+ hours late at session low. TWG was a complete miss — zero trades.

**Root Cause:** The state machine requires 3+ bars to confirm a setup (impulse → pullback → arm → entry). On stocks that gap and run immediately, the move is over before confirmation completes.

**Solution: Parallel "Fast Mode" Detector**

A second detection system runs alongside (not replacing) the existing state machine. It fires an early entry signal based on raw velocity metrics without requiring state machine confirmation.

Key components:
- **Volume spike trigger:** 5× average volume on a single 10-second bar + closing at high of bar + green bar = fast entry signal
- **L2 imbalance pre-signal:** bid_depth > 2× ask_depth within $0.25 of ask (requires L2 data feed)
- **Entry size:** 25% of normal position (small starter on unconfirmed signal)
- **Confirmation add:** If state machine subsequently confirms, add remaining 75%

```
# Fast Mode Trigger (simplified)
if (rvol_10s_bar >= 5.0x
    AND gap_pct >= 4%
    AND bar.close == bar.high     # closing at HOD
    AND bar.close > bar.open      # green bar
    AND float_pct_traded >= 2%):
    → FAST_ENTRY signal at 25% size
    → Stop = bar.low
    → Runs PARALLEL to state machine
```

| Attribute | Value |
|-----------|-------|
| **Priority** | 4th (needs tuning; backtest against MLEC, PAVM, TWG first) |
| **Effort** | High — new parallel detection system |
| **Risk** | Medium — small position sizes limit downside on false signals |
| **Backtest cases** | MLEC, PAVM, TWG |

---

### Problem 2: Resistance Blindness (Profile C Fix)

**Impact:** LCFY — bot entered the $6-$6.50 resistance zone 3 separate times. ACON — bot entered $8.50 resistance 4 times. No memory between attempts; each setup treated independently.

**Root Cause:** No concept of price levels. The state machine fires a signal whenever pattern conditions are met, regardless of whether the stock is sitting directly below a level it already failed to break.

**Solution: Persistent LevelMap with Failure Tracking + Entry Gate**

A registry of known price levels (pre-loaded + dynamically discovered) that tracks how many times price has tested and failed at each level. An entry gate blocks new entries near levels with 2+ failures.

Key components:
- **LevelMap loads at session start:** PM high (strength 4), whole dollars (strength 2), half dollars (strength 2), intraday pivots (strength 1)
- **Dynamic level discovery:** Volume Profile HVN detection for 30+ bar sessions
- **Failure tracking:** Each level has: `fail_count`, `touch_count`, `zone_width` (0.5% of price)
- **Entry gate:** Blocks entry if current price is within the zone of a level that has `fail_count ≥ 2`
- **Level break detection:** 2 consecutive closes above level with volume → reclassify as support

```
# Entry Gate (simplified)
class LevelMap:
    levels = [
        Level(price=PM_HIGH, strength=4, fail_count=0),
        Level(price=round_dollar, strength=2, fail_count=0),
        Level(price=half_dollar, strength=2, fail_count=0),
    ]

def entry_allowed(price):
    for level in LevelMap.levels:
        zone = level.price * 0.005  # 0.5% zone width
        if abs(price - level.price) < zone AND level.fail_count >= 2:
            return False  # BLOCKED — price near failed resistance
    return True
```

| Attribute | Value |
|-----------|-------|
| **Priority** | **1st — FOUNDATIONAL** (needed by Problems 1, 3, and 5) |
| **Effort** | Medium — add registry + gate to existing entry logic |
| **Risk** | Low — gate only blocks; never forces a trade |
| **Backtest cases** | LCFY, ACON |

---

### Problem 3: All-or-Nothing Position Sizing (Fix for All Profiles)

**Impact:** Every study reveals this gap. Ross enters 5K shares, adds 10K on confirmation, adds 15K on breakout. Bot enters full size or nothing. This means: oversized entries on unconfirmed signals, no ability to add to winners, no partial exits to lock in profit.

**Root Cause:** Position sizing module uses a single `max_risk_dollars / risk_per_share = shares` calculation. No concept of tranches, adds, or partial exits.

**Solution: 3-Tranche Pyramid Tied to State Machine States**

Map each tranche to a specific state machine event:

| Tranche | Size | Trigger | State Machine State |
|---------|------|---------|-------------------|
| **Tranche 1** | 25% of max position | First impulse / fast mode entry | `IMPULSE` → `ARM` |
| **Tranche 2** | 35% of max position | Pullback confirmation | `ARM` → `ENTRY` (confirmed) |
| **Tranche 3** | 40% of max position | Breakout to new HOD | New `HOD_BREAK` event |

**Exit tranches:**

| Exit | Size | Trigger |
|------|------|---------|
| **Exit 1** | 40% of position | At 1R (1:1 risk/reward) |
| **Exit 2** | 35% of position | At 2R (2:1 risk/reward) |
| **Exit 3 (runner)** | 25% of position | ATR Chandelier trailing stop |

**Stop management progression:**
- After Tranche 2 added → move stop to breakeven
- After Tranche 3 added → move stop to small profit (0.5R)
- Risk cap: Never exceed `max_risk_dollars` across all tranches combined

```
# Pyramid Sizer (simplified)
class PyramidSizer:
    TRANCHE_1_PCT = 0.25  # 25% on impulse
    TRANCHE_2_PCT = 0.35  # 35% on confirmation
    TRANCHE_3_PCT = 0.40  # 40% on HOD break

    def calc_tranche(self, tranche_num, entry_price, stop_price):
        risk_per_share = entry_price - stop_price
        max_shares = self.max_risk / risk_per_share
        return int(max_shares * getattr(self, f'TRANCHE_{tranche_num}_PCT'))
```

| Attribute | Value |
|-----------|-------|
| **Priority** | **2nd** (high leverage, modular change) |
| **Effort** | Medium — refactor position sizing module in `trade_manager.py` |
| **Risk** | Low — same total risk budget, just distributed differently |
| **Backtest cases** | VERO, ROLR (test if pyramid captures runners) |

---

### Problem 4: Premature Exit on Parabolic Moves (Profile A Fix)

**Impact:** Three studies show the same pattern — bot enters a winning trade during parabolic momentum, then a bearish engulfing or topping wicky pattern on 10-second bars triggers an exit, killing the trade mid-move. ROLR: BE exit during $86K run. FLYX: BE exit despite having a better entry than Ross. VERO: Would have been even bigger without premature exits.

**Root Cause:** The 10-second bar exit logic doesn't distinguish between a genuine reversal and normal volatility within a parabolic trend. All bearish patterns are treated equally regardless of context.

**Solution: Multi-Signal Parabolic Regime Detector + Chandelier Exit Switching**

Detect when the stock is in a parabolic regime (sustained acceleration) and switch to a wider, trend-following exit method instead of the tight pattern-based exits.

**Parabolic regime = 3 of 4 signals active:**
1. Consecutive new highs (3+ bars making new HOD)
2. Rate of change acceleration (ROC increasing bar over bar)
3. Volume expansion (each bar > prior bar volume)
4. ATR expansion (volatility increasing, not contracting)

**When parabolic regime is active:**
- Suppress BE exits and topping wicky exits
- Switch to ATR Chandelier trailing stop (2.5× ATR multiplier — wider than normal)
- Monitor for exhaustion signals

**Exhaustion detection (exit triggers in parabolic mode):**
| Signal | Weight |
|--------|--------|
| RSI > 80 on 1-min chart | 1 point |
| Shooting star / doji on 1-min | 1 point |
| Volume divergence (new price high + lower volume) | 1 point |
| Volume contraction on new high | 1 point |
| **Score ≥ 3** | **Trim 50% immediately** |
| **Score ≥ 2** | **Tighten trail to 1.5× ATR** |
| **Score < 2** | **Ride it — keep 2.5× ATR trail** |

**Minimum hold times (prevents premature exits):**

| Entry Mode | Min Hold |
|-----------|----------|
| Fast mode entry | 60 seconds |
| Normal state machine entry | 30 seconds |
| Parabolic regime active | 120 seconds |

```
# Parabolic Regime Detector (simplified)
def is_parabolic(bars_1min, lookback=5):
    signals = 0
    if consecutive_new_highs(bars_1min, n=3): signals += 1
    if roc_accelerating(bars_1min, lookback): signals += 1
    if volume_expanding(bars_1min, lookback): signals += 1
    if atr_expanding(bars_1min, lookback): signals += 1
    return signals >= 3

# In exit logic:
if is_parabolic(bars):
    use_chandelier_trail(multiplier=2.5)
    suppress_be_exits()
    check_exhaustion_score()
else:
    use_normal_exits()  # existing BE/TW logic
```

| Attribute | Value |
|-----------|-------|
| **Priority** | **3rd** (protect existing winners, low risk to add) |
| **Effort** | Medium — add regime layer to exit logic in `trade_manager.py` |
| **Risk** | Low — worst case is holding slightly longer on a reversal |
| **Backtest cases** | ROLR, FLYX, VERO |

---

### Problem 5: Breakout Chase vs. Dip Buy Entry

**Impact:** On ACON, the bot entered at $8.22 chasing a breakout. Ross entered at $7.60 on a dip buy near VWAP. The $0.62/share gap on a multi-thousand-share position = $4K+ edge to Ross. This pattern repeats across studies — the bot always enters AFTER the breakout, Ross enters BEFORE.

**Root Cause:** The state machine is a breakout-confirmation system by design. It waits for price to break above resistance before entering. Ross pre-positions below resistance during consolidation and catches the breakout from a better price.

**Solution: Anticipation Entry System with Dip-Buy-into-Structure**

A new entry mode that scans for stocks consolidating near resistance and places limit orders in the lower portion of the consolidation range.

**Anticipation entry conditions (all must be met):**
1. Price above VWAP
2. Within 2% of a known resistance level (from LevelMap — requires Problem 2)
3. Volume contracting (consolidation, not distribution)
4. Tight price range (high-low range < 1.5% for 5+ bars)
5. L2 showing accumulation (bid depth building — requires L2 feed)

**Entry mechanics:**
- Place limit order in lower 30% of consolidation range (NOT market order chasing breakout)
- Initial size: 20% of normal (higher risk pre-confirmation entry)
- Add on breakout confirmation: +150% of initial size when resistance breaks with 2×+ RVOL
- Timeout: If breakout doesn't happen in 10 bars, exit anticipation position at market

**Dip-buy adds (post-breakout):**
- When stock pulls back to VWAP or to flipped resistance (now support) on low volume
- RSI between 35-58 (oversold enough to bounce, not so weak it's breaking down)
- Add 25% of max position on dip-buy confirmation

```
# Anticipation Entry (simplified)
def check_anticipation(bars, level_map):
    nearest_resistance = level_map.nearest_above(bars[-1].close)
    distance_pct = (nearest_resistance - bars[-1].close) / bars[-1].close

    if (bars[-1].close > vwap
        AND distance_pct < 0.02
        AND volume_contracting(bars, lookback=5)
        AND price_range_tight(bars, lookback=5, max_pct=1.5)):

        limit_price = bars[-1].low + (bars[-1].high - bars[-1].low) * 0.30
        return Signal(type="ANTICIPATION", price=limit_price, size=0.20 * max_size)
```

| Attribute | Value |
|-----------|-------|
| **Priority** | 5th (requires L2 data feed capability — wait for IBKR/Databento) |
| **Effort** | High — new entry mode with L2 dependency |
| **Risk** | Medium — pre-confirmation entries carry higher false positive rate |
| **Backtest cases** | ACON (primary), LCFY |

---

### Problem 6: Post-Halt Recovery (Profile F Fix)

**Impact:** VERO missed $5.50→$12.93 (135% gain) after a trading halt. LCFY missed the entire $3.74→$5.58 recovery. When a halt occurs, the state machine's bar-building pipeline breaks — partially completed bars become invalid, and the state machine has no protocol for resuming.

**Root Cause:** No halt detection. No state machine reset protocol. The bot treats post-halt trading as if the pre-halt context is still valid, leading to stale signals or complete inactivity.

**Solution: Halt Detector + State Machine Reset Protocol**

**Halt detection:**
- Monitor for LULD halt messages from data feed
- Fallback: If no trades for 30+ seconds during market hours on a stock with prior activity, assume halt

**On halt detected:**
1. Cancel all open orders immediately
2. Snapshot current state (position, unrealized P&L, bars, indicators)
3. Save halt context (pre-halt price, direction, volume trend)

**Post-halt decision tree:**

| Condition | Action |
|-----------|--------|
| No position + reopens higher + volume surge | Treat as virtual session open → 2-min observation → fast mode |
| No position + reopens lower | WATCH_ONLY for 10 minutes |
| Long position + reopens higher | Hold; set new trailing stop based on reopen price |
| Long position + reopens lower | Immediate exit at market |

**Recovery entry patterns:**
1. **First Pullback (most common):** After halt reopen, wait for first pullback to VWAP or 50% retrace of reopen candle. Enter on first green bar after pullback.
2. **Momentum Continuation:** For stocks that halted up with 50%+ pre-halt gains, the reopen candle often continues higher. Fast mode trigger applies.

**Safety rule:** After 2 consecutive halts on the same stock → `WATCH_ONLY` mode for 10+ minutes (multiple halts often signal distribution, not accumulation).

```
# Halt Handler (simplified)
def on_halt_detected(symbol, context):
    cancel_all_orders(symbol)
    snapshot = save_state(symbol)
    context.halt_count += 1

    if context.halt_count >= 2:
        set_mode(symbol, WATCH_ONLY, duration=600)
        return

def on_halt_resume(symbol, reopen_price, context):
    reset_state_machine(symbol)  # Clear all bar buffers, reset states
    start_observation_timer(symbol, duration=120)  # 2-min observation
    activate_fast_mode(symbol)  # Allow fast entry if conditions met
```

| Attribute | Value |
|-----------|-------|
| **Priority** | 6th (implement in parallel with other work) |
| **Effort** | Low — add halt handler to event loop |
| **Risk** | Low — isolated subsystem, can be toggled off |
| **Backtest cases** | LCFY, VERO (halt scenarios) |

---

### Recommended Implementation Sequence

```
Phase 1: Level Map (Problem 2)    → Foundational — needed by Problems 1, 3, and 5
Phase 2: Pyramid Sizing (Problem 3) → High leverage, modular refactor
Phase 3: Parabolic Exits (Problem 4) → Protect existing winners, low risk addition
Phase 4: Fast Mode (Problem 1)    → Needs tuning + extensive backtesting
Phase 5: Anticipation Entry (Problem 5) → Requires L2 data feed (IBKR/Databento)
Phase 6: Post-Halt Recovery (Problem 6) → Implement in parallel, activate after testing
```

**Dependency graph:**
```
Problem 2 (LevelMap) ──┬──→ Problem 3 (Pyramid Sizing)
                       ├──→ Problem 5 (Anticipation Entry) ──→ Problem 1 (Fast Mode L2 component)
                       └──→ Problem 1 (Fast Mode level awareness)

Problem 4 (Parabolic Exits) ──→ standalone, no dependencies
Problem 6 (Post-Halt) ──→ standalone, no dependencies
```

---

## Section 5: Prioritized Action Items for Claude Code

*This section is the implementation handoff. Each item is specific, references exact files and functions, and includes acceptance criteria.*

---

### Phase 1: Foundation — LevelMap (Before Next Studies)

**Goal:** Give the bot awareness of price levels so it stops buying into resistance.

**Item 1: Implement LevelMap class**
- **File:** Create new `/warrior_bot/levels.py` (or add to `micro_pullback.py`)
- **Class:** `LevelMap` with methods: `load_session_levels()`, `add_level()`, `update_on_bar()`, `nearest_above()`, `nearest_below()`, `is_near_failed_resistance()`
- **Level types to track:**
  - Pre-market high (strength 4)
  - Whole dollar levels within ±20% of current price (strength 2)
  - Half dollar levels within ±20% of current price (strength 2)
  - VWAP (strength 3, dynamic — updates every bar)
  - Intraday pivot points discovered during session (strength 1)
- **Each level stores:** `price`, `strength`, `fail_count`, `touch_count`, `zone_width` (0.5% of price), `last_touch_time`
- **Failure detection:** Price enters zone, then closes below zone on next bar → `fail_count += 1`
- **Break detection:** 2 consecutive closes above level with volume → reclassify as support
- **Reference:** See Problem 2 solution above; full pseudocode in `algo_solutions.md` lines ~200-400
- **Acceptance criteria:** LevelMap correctly identifies PM high, whole/half dollar levels for LCFY on 01/16 and ACON on 01/08 when loaded with their historical data

**Item 2: Add entry gate**
- **File:** `trade_manager.py`, in the `on_signal()` method
- **Logic:** Before executing any entry, call `level_map.is_near_failed_resistance(current_price)`. If True, log "ENTRY BLOCKED: near failed resistance at ${level}" and skip the entry.
- **Config:** Add `WB_RESISTANCE_GATE_ENABLED=True` and `WB_RESISTANCE_FAIL_THRESHOLD=2` to `.env`
- **Acceptance criteria:** Gate blocks entries on LCFY at $6-$6.50 after 2nd failed touch. Gate blocks entries on ACON at $8.50 after 2nd failed touch.

**Item 3: Run backtests with entry gate**
- **Stocks:** LCFY (01/16), ACON (01/08)
- **Expected outcome:** LCFY: eliminates 2 of 3 losing entries (-$1,000+ improvement). ACON: eliminates 2+ of 4 losing entries (-$1,500+ improvement).
- **Regression check:** Run all 11 studied stocks to verify no winning trades are blocked.

---

### Phase 2: Position Sizing — Pyramid (After Phase 1)

**Goal:** Replace all-or-nothing entries with 3-tranche scaling.

**Item 4: Implement PyramidSizer class**
- **File:** New class in `trade_manager.py` (or new `sizing.py`)
- **Core logic:** See Problem 3 solution above
- **Tranche percentages:** 25% / 35% / 40% (configurable via .env)
- **Tranche triggers:** Map to state machine events (impulse/ARM/HOD break)
- **Config:** `WB_PYRAMID_ENABLED=True`, `WB_TRANCHE_1_PCT=0.25`, `WB_TRANCHE_2_PCT=0.35`, `WB_TRANCHE_3_PCT=0.40`
- **Key constraint:** Total risk across all tranches must never exceed `max_risk_dollars`
- **Acceptance criteria:** On VERO, Tranche 1 fires at 07:03 entry. Tranche 2 fires on pullback confirmation. Tranche 3 fires on HOD break. Total shares ≤ max_risk / risk_per_share.

**Item 5: Add partial exit logic**
- **File:** `trade_manager.py`, exit execution
- **Logic:** Replace single full exit with staged exits:
  - Sell 40% of position at 1R (1:1 risk/reward from average entry)
  - Sell 35% of position at 2R
  - Trail remaining 25% with ATR Chandelier stop (1.5× ATR default)
- **Stop progression:** After Tranche 2 → stop to breakeven. After Tranche 3 → stop to 0.5R profit.
- **Config:** `WB_EXIT_1R_PCT=0.40`, `WB_EXIT_2R_PCT=0.35`, `WB_RUNNER_PCT=0.25`, `WB_CHANDELIER_MULT=1.5`
- **Acceptance criteria:** Partial exits fire at correct R-multiple levels. Runner position trails with ATR stop.

**Item 6: Backtest VERO and ROLR with pyramid sizing**
- **VERO expected:** Pyramid captures more of the $5.50→$12.93 run. Tranche 3 catches HOD breakout. Runner trails the parabolic move.
- **ROLR expected:** Smaller initial position (-25% of current). Adds on confirmation increase size. Partial exit at 1R locks profit. Runner trails instead of BE exit killing the position.
- **Regression check:** Run all 11 studied stocks.

---

### Phase 3: Exit Improvements — Parabolic Regime (After Phase 2)

**Goal:** Stop cutting winners short during parabolic momentum.

**Item 7: Implement ParabolicRegimeDetector**
- **File:** New class in `trade_manager.py` or new `regime.py`
- **Logic:** See Problem 4 solution above. Evaluate 4 signals on every 1-minute bar close. Return `is_parabolic` boolean + `exhaustion_score`.
- **Signals:** Consecutive new highs (3+), ROC acceleration, volume expansion, ATR expansion
- **Runs on:** 1-minute bars (more stable than 10-second)
- **Config:** `WB_PARABOLIC_DETECTION_ENABLED=True`, `WB_PARABOLIC_MIN_SIGNALS=3`

**Item 8: Replace fixed BE exit with regime-switched logic**
- **File:** `trade_manager.py`, exit logic (and `simulate.py` for backtester)
- **Logic:**
  - Normal mode (not parabolic): Use existing BE exit + topping wicky logic (unchanged)
  - Parabolic mode: Suppress BE exits entirely. Switch to Chandelier trailing stop at 2.5× ATR multiplier.
  - Exhaustion detected (score ≥ 3): Trim 50% immediately, tighten trail to 1.5× ATR.
- **Config:** `WB_PARABOLIC_CHANDELIER_MULT=2.5`, `WB_EXHAUSTION_TRIM_PCT=0.50`

**Item 9: Add minimum hold times per entry mode**
- **File:** `trade_manager.py`
- **Logic:** After entry, suppress ALL exit signals (except hard stop loss) for the minimum hold period:
  - Fast mode entry: 60 seconds
  - Normal state machine entry: 30 seconds
  - Parabolic regime active: 120 seconds
- **Config:** `WB_MIN_HOLD_FAST=60`, `WB_MIN_HOLD_NORMAL=30`, `WB_MIN_HOLD_PARABOLIC=120`

**Item 10: Backtest ROLR, FLYX, VERO with parabolic regime detector**
- **ROLR expected:** Parabolic regime suppresses BE exit during the initial $86K run. Chandelier trail rides the move further.
- **FLYX expected:** Parabolic regime keeps position alive after 07:03 entry. Bot's better entry ($4.91 vs Ross's $5.89) translates to actual profit instead of BE-exit loss.
- **VERO expected:** Larger captured move on the $5.50→$12.93 run.

---

### Phase 4: Speed & Entry Improvements (After Data Feed Upgrade)

**Goal:** Enable the bot to act on fast-moving stocks before the state machine confirms.

**Item 11: Implement fast mode detector**
- **File:** New parallel detection in `micro_pullback.py` or new `fast_mode.py`
- **Logic:** See Problem 1 solution. Runs on every 10-second bar close. Independent of state machine.
- **Trigger conditions:** 5× RVOL on single bar + closing at HOD + green bar + 2% float turnover
- **Position size:** 25% of normal (small starter)
- **Integration:** Fire `FAST_ENTRY` signal that trade_manager handles identically to normal signals but with smaller size
- **Config:** `WB_FAST_MODE_ENABLED=True`, `WB_FAST_MODE_SIZE_PCT=0.25`, `WB_FAST_MODE_RVOL_THRESHOLD=5.0`

**Item 12: Add anticipation entry mode**
- **File:** New entry logic in `trade_manager.py`
- **Logic:** See Problem 5 solution. Requires LevelMap (Phase 1) and L2 data feed (IBKR or Databento).
- **Key behavior:** Places limit order in lower 30% of consolidation range near resistance, NOT market order chasing breakout.
- **Size:** 20% of normal on anticipation; add +150% on confirmed breakout.
- **Timeout:** Exit anticipation position after 10 bars if no breakout.
- **Dependency:** Requires L2 feed — defer until IBKR approval or Databento subscription.

**Item 13: Implement dip-buy add logic**
- **File:** `trade_manager.py`, add-to-position logic
- **Trigger:** Stock pulls back to VWAP or to flipped resistance (now support) on low volume, RSI 35-58
- **Size:** 25% of max position on each dip-buy confirmation
- **Integration:** Works with pyramid sizing (Item 4) — dip-buy add counts as Tranche 2 or 3.

**Item 14: Backtest MLEC, PAVM, TWG with fast mode**
- **MLEC expected:** Fast mode detects the initial volume spike and enters at ~$7.90 instead of 10 min later at $9+.
- **PAVM expected:** Fast mode detects the 8:00 AM spike instead of waiting until 10:30 AM.
- **TWG expected:** Fast mode produces at least one entry instead of zero trades.

---

### Phase 5: Halt Recovery (Implement in Parallel)

**Goal:** Handle trading halts gracefully and capture post-halt recovery patterns.

**Item 15: Add HaltDetector**
- **File:** `bot.py` (event loop) or new `halt_detector.py`
- **Detection methods:**
  1. LULD halt message from data feed (primary)
  2. No trades for 30+ seconds on an active stock during market hours (fallback)
- **On halt:** Cancel all orders, snapshot state, increment halt counter
- **Config:** `WB_HALT_DETECTION_ENABLED=True`, `WB_HALT_TIMEOUT_SEC=30`

**Item 16: Implement state machine reset on halt detection**
- **File:** `micro_pullback.py`
- **Logic:** On halt resume signal → clear all bar buffers → reset state to `IDLE` → treat reopen as virtual session open → start 2-minute observation period
- **Preserve:** Position data, P&L tracking, session statistics (only reset detection state)

**Item 17: Add post-halt first-pullback entry pattern**
- **File:** `micro_pullback.py` or `fast_mode.py`
- **Logic:** After 2-minute observation period post-halt → if stock is above halt price and making higher lows → activate fast mode for first pullback entry
- **Safety:** After 2 consecutive halts on same stock → `WATCH_ONLY` mode for 10+ minutes

**Item 18: Backtest LCFY and VERO halt scenarios**
- **LCFY expected:** Bot stops re-entering the $6-$6.50 resistance zone. Post-halt recovery from $3.74→$5.58 is captured with first-pullback entry.
- **VERO expected:** Post-halt entry captures portion of $5.50→$12.93 move instead of missing it entirely.

---

### Ongoing: Trade Studies

**Item 19: Complete 14-19 more trade studies**
- Use the 19 new stock candidates identified in Section 3.
- Target total: 25-30 studies for statistically significant dataset.
- Each study follows the established methodology: run backtester → watch Ross's recap → document comparison → classify profile.

**Item 20: Priority study order**
1. Profile A confirmation: ELAB, BCTX, SXTP (confirm bot strength pattern)
2. Ross loss cases: BNAI, RVSN (confirm bot mechanical advantage)
3. Profile B quantification: HIND, GRI, SNSE (measure speed problem precisely)
4. Profile C testing: RYA, MOVE, SLE (validate LevelMap design before implementation)
5. Remaining: OPTX, APVO, ARNA, ALMS, VNDA, VHUB, NCI

**Item 21: Sign up for Databento when ready**
- Addresses fundamental data feed quality gap (see `/home/user/workspace/DATA_FEED_SOLUTION.md`)
- $200/month for real-time + historical tick data
- Enables L2 implementation (required for Problems 1 and 5)
- Alternative: Wait for IBKR approval (application pending)

---

### Implementation Effort Summary

| Phase | Items | Estimated Effort | Dependencies | Expected Impact |
|-------|-------|-----------------|--------------|----------------|
| Phase 1: LevelMap | Items 1-3 | 1-2 days | None | Eliminate Profile C losses (est. +$4,000 across studies) |
| Phase 2: Pyramid | Items 4-6 | 2-3 days | Phase 1 | Capture runners + reduce entry size (est. +$3,000) |
| Phase 3: Parabolic | Items 7-10 | 1-2 days | Phase 2 | Protect Profile A winners (est. +$2,000-$5,000) |
| Phase 4: Speed | Items 11-14 | 3-5 days | Phases 1-3 + data feed | Address Profile B (est. +$5,000-$10,000) |
| Phase 5: Halt | Items 15-18 | 1-2 days | None (parallel) | Capture post-halt moves (est. +$3,000) |
| **Total** | **18 items** | **8-14 days** | Sequential | **Est. +$17,000-$24,000 across 11 studies** |

---

## Appendix A: Ross Cameron's Jan-Feb 2026 Trading Summary

### Monthly Performance

| Month | Profit | Win Rate | Avg Daily | Best Day | Worst Day |
|-------|--------|----------|-----------|----------|-----------|
| January | $400,000 | 80% | $23,000 | +$86K (ROLR, Jan 14) | -$4,921 (ANPA, Jan 9) |
| February (thru ~Feb 22) | ~$152,000 | 53% | ~$11,000 | ~+$80K (Feb 3 squeeze) | -$9,300 (Feb 5 red day) |
| **YTD** | **~$555,000** | **73%** | **~$18,000** | — | — |

### Key Statistics

| Metric | Value |
|--------|-------|
| Starting account (Jan 1) | ~$96,000-$100,000 |
| Current account (late Feb) | ~$555,000+ |
| Account growth YTD | ~+455% |
| Average hold time (winners) | 3 minutes |
| Average hold time (losers) | 2 minutes |
| January avg winners | ~$5,000 |
| January avg losers | ~$2,000 |
| Feb avg daily (excl. Feb 3) | ~$6,000/day |

### Notable Trading Days

| Date | P&L | Stocks | Notes |
|------|-----|--------|-------|
| Jan 6 | +$7,550 | ALMS, OPTX, ELAB | Day 2 of 2026; 3 trades |
| Jan 9 | -$4,921 | APVO (+$6K), ANPA (-$11K) | Biggest loss of January |
| Jan 14 | +$86,000 | ROLR | Crypto.com prediction markets catalyst |
| Jan 16 | +$20,000 | TNMG, GWAV, VERO, LCFY | "4 Base Hits" — all 4 stocks in bot studies |
| Jan 23 | +$16,919 | RYA, MOVE, SLE | Leading percentage gainers day |
| Jan 27 | +$59,753 | BCTX, HIND | Breaking news day; HIND = $725K position |
| Jan 28 | +$33,500 | SXTP, GRI | Gave back 25% of GRI unrealized gains |
| Feb 3 | ~+$80,000 | Unknown | "Tuesday short squeeze" — biggest Feb day |
| Feb 5 | -$9,300 | BNAI (-$7.9K), ARNA (+$1.7K), RVSN (-$3K) | Red day |
| Feb 13 | +$43,000 | MLEC | "Wildcard Friday" — $43K in ~3 minutes |
| Feb 18 | +$9,373 | SNSE | 300% short squeeze; Roth IRA trade |

### January vs. February Contrast

| Metric | January | February |
|--------|---------|----------|
| Win rate | 80% | 53% |
| Avg daily | $23,000 | ~$11,000 |
| Market conditions | Hot — "January effect" + prediction market theme | Cold — fewer catalysts |
| Key lesson | Scale up when market is hot | Reduce size when accuracy drops |

---

## Appendix B: Source Videos

| Date | Video Title | URL |
|------|-------------|-----|
| Jan 6 | +$7,549.61 on DAY 2 of 2026 | https://www.youtube.com/watch?v=tDb0WPsRZT4 |
| Jan 9 | Red Day | https://www.youtube.com/watch?v=BUJQPzYCtJ0 |
| Jan 16 | 4 Base Hits Day | https://www.youtube.com/watch?v=ZKsNP11rU1Y |
| Jan 18 | Mid-Month Recap | https://www.youtube.com/watch?v=-jSYkNsGwcc |
| Jan 23 | Leading Percentage Gainers | https://www.youtube.com/watch?v=WImLVayOwRo |
| Jan 27 | Day Trading Breaking News | https://www.youtube.com/watch?v=RAJXknk-VI4 |
| Jan 28 | Gave Back 25% of Profit | https://www.youtube.com/watch?v=WYB5jmTDBO4 |
| Feb 5 | Red Day | https://www.youtube.com/watch?v=HGATds95-p4 |
| Feb 13 | Wildcard Friday | https://www.youtube.com/watch?v=xiSYeo2p76g |
| Feb 18 | +$9,373.32 on 300% Short Squeeze | https://www.youtube.com/watch?v=hxIw63KWMZI |
| Feb 22 | Watch List for Feb 23 | https://www.youtube.com/watch?v=p5JkC4K8upc |

---

## Appendix C: Full Research Files

These workspace files contain the complete, unabridged research behind this report:

| File | Contents | Size |
|------|----------|------|
| `/home/user/workspace/research/ross_cameron_methodology.md` | Ross's exact trading rules — 5 pillars, entry criteria, exit strategy, risk management, scanner settings, halt protocol | 757 lines |
| `/home/user/workspace/research/algo_solutions.md` | Complete algorithmic solutions with full pseudocode for all 6 problems | 1,275 lines |
| `/home/user/workspace/research/ross_cameron_recaps.md` | 30+ stock trades extracted from Jan-Feb 2026 recap videos, daily breakdowns, monthly summaries | 338 lines |
| `/home/user/workspace/PROJECT_STATUS.md` | Current project status — architecture, all 11 trade studies, 6 code fixes, open issues, next steps | 262 lines |
| `/home/user/workspace/DATA_FEED_SOLUTION.md` | Data feed recommendation: IBKR + Databento comparison, pricing, integration notes | — |
| `/home/user/workspace/DYNAMIC_SCANNER_IMPLEMENTATION.md` | Dynamic scanner implementation details | — |
| `/home/user/workspace/GAP_AND_GO_IMPLEMENTATION.md` | Gap and Go strategy implementation | — |
| `/home/user/workspace/STOCK_FILTERING_IMPLEMENTATION.md` | Stock filtering criteria implementation | — |
| `/home/user/workspace/FLOAT_DATA_INTEGRATION.md` | Float data source integration | — |
| `/home/user/workspace/IMPLEMENTATION_SUMMARY.md` | Overall implementation summary | — |

---

## Appendix D: Bot Architecture Quick Reference

| Component | File | Purpose |
|-----------|------|---------|
| Main bot | `bot.py` | Dual bar builders, websocket data ingestion, live trading loop |
| Core detector | `micro_pullback.py` | 1-min state machine: impulse → pullback → ARM → entry |
| Trade manager | `trade_manager.py` | Order execution, entries, exits, chase logic, position tracking |
| Backtester | `simulate.py` | Runs historical tick data through detector for trade studies |
| Bar builder | `bars.py` | VWAP, HOD, PM_HIGH calculations |
| Pattern recognition | `patterns.py` | ASC_TRIANGLE, FLAT_TOP, R2G, VOL_SURGE |
| Configuration | `.env` | ~160 settings controlling all bot behavior |

### Account Configuration

| Setting | Value |
|---------|-------|
| Funded capital | $30,000 |
| Buying power | $60,000 |
| Max risk per trade | $1,000 |
| Platform | Alpaca (paper trading) |
| Status | Paper trading only — not live money |

### State Machine Flow

```
IDLE → IMPULSE → PULLBACK → ARM → ENTRY → POSITION_OPEN → EXIT
  ↑                                                            |
  └────────────────────────────────────────────────────────────┘
```

- **IMPULSE:** 1-min green bar with above-average volume + price making new highs
- **PULLBACK:** Price retraces from impulse high (1-3 red/doji bars, declining volume)
- **ARM:** Pullback holds above key level (VWAP, prior support); tight consolidation
- **ENTRY:** Break above ARM high on volume → trigger signal to trade_manager
- **EXIT:** Managed by trade_manager using 10-second bars (BE exit, TW exit, stop loss, take profit)

---

*End of report. This document should be treated as the single source of truth for the Warrior Bot project status, research findings, and implementation roadmap as of February 26, 2026.*
