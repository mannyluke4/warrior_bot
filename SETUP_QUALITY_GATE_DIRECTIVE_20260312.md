# SETUP QUALITY GATE — Replacing the Scoring Gate with Ross-Aligned Logic
## March 12, 2026 | For Claude Code (Duffy)

---

## THE CORE PROBLEM

The bot currently has **no per-stock quality judgment**. The old scoring gate was removed because it wasn't predictive. But now the bot will trade ANY stock that passes the 4 ARM gates (R≥$0.03, stale, exhaustion, warmup) — including stocks Ross would never touch.

Evidence from 5-date backtest (24 trades, -$6,426):
- **0 of 24 trades** were on stocks Ross actually won on (except AEI, which the bot lost)
- **5 trades** on Feb 3 were on stocks Ross explicitly rejected that day
- The bot is trading the WRONG stocks, and even on the right stocks, taking LOW-QUALITY entries

Two parallel problems need solving:
1. **Scanner** — not surfacing Ross's stocks (separate directive already sent)
2. **Setup quality** — not filtering out bad setups on whatever stocks ARE on the list

This document addresses #2: **What makes Ross say "yes" to a setup vs. "no"?**

---

## ROSS'S PER-STOCK DECISION CRITERIA (Extracted from 47 Trades + 2 Video Transcripts)

### CRITERION 1: DOMINANT VOLUME — "Is This THE Stock?"

Ross focuses on the **#1 or #2 leading gainer**. He doesn't spread across 6 stocks — he watches the one that's clearly winning the attention battle.

**Evidence:**
- From Zero video: *"I focus on the #1 leading percentage gainer in the market"*
- Feb 3 no-trade day: Rejected all 6 stocks because *"dispersed volume — 5-6 stocks, none dominant"*
- Ross's big wins (ZOZ $247K, RORL $86K, CF $32K) were all THE dominant stock of the day
- Small account series: Always targeted the single highest-momentum stock

**What this means for the bot:**
The bot should rank all scanner candidates by a dominance score and strongly prefer the top 1-2 stocks. If no stock is clearly dominant, that itself is a quality signal (bearish for the day).

**Measurable by bot:** YES
- Compare relative volume across all watchlist stocks
- Identify if one stock has 2-3x more volume than the second highest
- Track percentage of total scanner-list volume held by the top stock
- If volume is spread evenly across 4+ stocks → quality flag: LOW

---

### CRITERION 2: FRESH CATALYST — "Why Is It Moving?"

Ross requires **real breaking news**. Price action alone is not enough. He explicitly reads the headline and assesses whether it justifies the move.

**Evidence:**
- Playbook: News present in 43/47 trades (91%)
- From Zero video: *"Why would a stock go up 30% or 50% in one day? It's because it has breaking news"*
- Feb 3 rejections: *"No strong news catalyst — just price action"* was a specific rejection reason
- CCTG loss (-$900): Chinese pump stock with no real news
- Ross checks SEC filings for cash position and dilution risk

**What this means for the bot:**
The bot can't read news. But it CAN check whether a catalyst flag exists in the data. More importantly, this is about **which stocks get on the watchlist** — scanner-level, not entry-level. For the quality gate, the proxy is: does the stock's behavior match a catalyst pattern (gap up with sustained volume) vs. a grinder pattern (slow drift up, no surge)?

**Measurable by bot:** PARTIALLY
- Gap percentage at open: Higher gaps (20%+) correlate with real catalysts
- Pre-market volume surge: Real catalysts show concentrated pre-market volume
- Volume shape: Catalyst stocks have volume front-loaded (spikes at 7-8AM); grinders have flat volume
- If the stock is gapping <10% with flat volume profile → quality flag: LOW

---

### CRITERION 3: CLEAN CHART PATTERN — "Is the Pullback Clean?"

This is the most important criterion. Ross distinguishes between clean bull flags/micro pullbacks and messy/choppy action. He explicitly describes what makes a "clean" vs "messy" chart.

**Evidence:**
- Strategy context: *"Clean = clear flag pole, defined pullback, obvious entry trigger, high volume on buying, lower volume on pullback, no overlapping candles or choppy sideways action"*
- Strategy context: *"Messy = no clear direction, equal volume on up and down candles, overlapping wicks, extended/parabolic move without a clean pullback"*
- Feb 3 rejection: *"Thickly traded grinder — can't move the price easily"* (messy, no clean pattern)
- VTA loss (-$7,000): *"Multiple VWAP break attempts, 4-5 entries all failed — choppy"*
- SHMD loss (-$3,000): *"Multiple rejections, no new high"*
- GOVX loss ($0): *"Flush to stop — emotional add"*

**Ross's clean pullback checklist:**
1. Clear impulse (flag pole) — strong green candle(s) above EMA/VWAP
2. Light volume on pullback (1-3 red candles)
3. Pullback holds in upper 50-70% of the flag pole range
4. First candle to make a new high = entry trigger
5. No overlapping wicks or sideways chop during pullback

**What this means for the bot:**
The bot already detects impulse → pullback → confirmation. But it doesn't assess the QUALITY of the pullback. A pullback that retraces 80% of the impulse is ugly. A pullback with heavy selling volume is ugly. A pullback where candles overlap and chop is ugly.

**Measurable by bot:** YES — This is the most impactful gate
- **Pullback depth**: How far did the pullback retrace the impulse?
  - Clean: Holds above 50% of impulse range (retraces <50%)
  - Messy: Retraces >70% of impulse
- **Pullback volume ratio**: Compare average volume on pullback candles vs. impulse candles
  - Clean: Pullback volume < 50% of impulse volume
  - Messy: Pullback volume ≥ impulse volume (equal selling pressure)
- **Pullback candle count**: Ross likes 1-3 candle pullbacks
  - Clean: 1-3 candles
  - Messy: >5 candles (indecision, not a pullback)
- **Candle overlap**: During pullback, do candle bodies overlap heavily?
  - Clean: Each candle's close is within or near the prior candle's range
  - Messy: Wide wicks, doji candles, mixed green/red during "pullback"

---

### CRITERION 4: PRE-MARKET CUSHION — "Has It Proven Itself?"

Ross wants to see the stock already moving strongly BEFORE he enters. He doesn't want to be the first buyer hoping something happens.

**Evidence:**
- Feb 3 rejection: *"No pre-market cushion — hasn't broken the ice, can't afford to be wrong"*
- From Zero video: Start at 25% size *"until I'm up over $1,000"*
- Ross's winners almost all had significant pre-market action before he entered:
  - AGRI: 130% gap, already running at 7AM
  - ZOZ: Already surging before his entry at $3.80
  - CF: Already moving hard in early morning
  - QCLS: Already at $8.47 by 7AM with clear momentum

**What this means for the bot:**
Before taking a trade, the stock should already have shown convincing upward momentum. The impulse candle in the pullback pattern IS this evidence — but the question is whether the impulse was strong enough.

**Measurable by bot:** YES
- **Impulse strength**: Size of the flag pole relative to the stock's price
  - Strong: Impulse moved 5%+ of stock price in the flag pole
  - Weak: Impulse moved <2% (barely perceptible)
- **Impulse volume**: Was the impulse candle(s) on above-average volume?
  - Strong: Volume on impulse candle > 2x average bar volume
  - Weak: Volume on impulse candle below average
- **Prior bars context**: Did the stock already have multiple green bars before this impulse?
  - Establishes the stock is "in play" and not just a random blip

---

### CRITERION 5: FLOAT AND PRICE SWEET SPOT — "Can This Actually Move?"

Ross has a clear sweet spot where his strategy works best.

**Evidence:**
- From Zero video: Avoid stocks over $10 as beginner (his own metrics showed it)
- Playbook: Sweet spot is $3-$10, float under 5M ideal
- ANPA loss (-$11,000): $55 stock, expensive per share — *"Chinese stock, no news"*
- MLGO loss (-$500): $17.50-$19 stock, *"expensive stock"*
- Ross's biggest wins are almost all in $3-$10 range:
  - ZOZ: $3.80-$9 → $247K
  - CF: $5.25-$13.50 → $32K
  - WHLR: $5-$7 → $28K
  - MSS: $2.10-$3.50 → $9.2K
- LNAI at $1.17 = too thin, hard to fill (only got partial 3000 of 10000 shares)
- Trader Rehab: Smaller size + A-quality setups = best risk-adjusted returns

**What this means for the bot:**
The bot's scanner already filters $2-$20. But within that range, $3-$10 with float under 10M should get a quality bonus. Stocks at the extremes ($2 or $15-$20) should get a quality penalty.

**Measurable by bot:** YES — already has this data from scanner
- Price sweet spot: $3-$10 = full quality, $2-$3 or $10-$15 = reduced, $15-$20 = further reduced
- Float sweet spot: Under 5M = full quality, 5-10M = good, 10-20M = acceptable, 20M+ = penalty
- Combined: Low float + sweet spot price = highest quality

---

### CRITERION 6: RELATIVE VOLUME CONFIRMATION — "Is There Real Participation?"

Ross requires high relative volume — this confirms that the stock has attracted real institutional/crowd attention, not just a few retail traders pushing the price around.

**Evidence:**
- From Zero video: *"At least two times but preferably five times or higher relative volume"*
- Playbook: *"First on scanner"* = highest relative volume
- Feb 3 rejection: Stocks with dispersed volume = no single stock dominating
- Ross's winners all had massive relative volume:
  - ZOZ: "Blue sky" = enormous participation
  - CF: Short squeeze = extremely high volume
  - QCLS: Hit scanner early at 7AM with vol burst

**What this means for the bot:**
The bot should check relative volume at the moment of potential entry, not just at scanner time. A stock that was 5x rvol at 7AM might be 1.5x by 9AM (volume faded).

**Measurable by bot:** YES
- Relative volume at entry moment vs. scanner time
- Is volume INCREASING or DECREASING as the setup forms?
- Volume on the impulse candle specifically — is it a volume spike or just average?

---

### CRITERION 7: NO RECENT FAILURE ON TICKER — "Has This Already Failed?"

Ross avoids stocks that recently popped and reversed. He also avoids re-entering after a loss on the same stock (his #1 loss driver).

**Evidence:**
- Feb 3 rejection: *"Recent failure on ticker — stock popped and reversed last week"*
- Playbook: Revenge trading (re-entries after loss) = #1 loss category (-$18,113 from 6 losses)
- LNAI: 3 entries, progressively worse (-$1,200 then -$2,913 after initial $187 win)
- VTA: 4-5 entries, all failed (-$7,000 total)
- QCLS: Re-entry after win → -$3,000 loss

**What this means for the bot:**
The consecutive loser stop already handles part of this (3 losses → stop for day). But the bot also needs per-SYMBOL re-entry limits. After 1 loss on a symbol, don't re-enter that symbol.

**Measurable by bot:** YES
- Track per-symbol trade results within the session
- After 1 loss on a symbol: BLOCK further entries on that symbol
- This is already partially implemented in the exit logic but should be explicit

---

## THE QUALITY GATE STRUCTURE

### How It Works

The quality gate runs AFTER the pullback is detected and BEFORE the ARM stage. It replaces the old scoring gate with Ross-aligned criteria.

Each criterion produces a simple pass/fail or penalty score. The total determines whether the setup gets armed.

### Proposed Implementation: Binary Pass/Fail Filters (Not a Score)

Based on user's direction (*"We don't trade unless the setup tells us to"*), this should be a **hard gate**, not a soft score. If the setup doesn't meet minimum quality, it doesn't get armed. Period.

### THE 5 MEASURABLE GATES (ordered by impact)

**GATE 1: CLEAN PULLBACK (highest impact — this IS the strategy)**
```
PASS if ALL of:
  - Pullback retraces ≤ 60% of impulse range
  - Pullback volume avg ≤ 70% of impulse volume avg  
  - Pullback is 1-4 candles (1-min)
  - Confirmation candle shows buying pressure (already checked)
FAIL if ANY of:
  - Pullback retraces > 75% of impulse
  - Pullback volume equals or exceeds impulse volume
  - Pullback is > 5 candles (choppy, not a flag)
```

**GATE 2: IMPULSE STRENGTH (pre-market cushion proxy)**
```
PASS if ALL of:
  - Impulse bar(s) moved price ≥ 3% from low to high
  - Impulse volume > 1.5x the average bar volume for this stock today
FAIL if:
  - Impulse moved < 1.5% (barely a move)
  - Impulse volume below average (no participation)
```

**GATE 3: VOLUME DOMINANCE (is this THE stock?)**
```
PASS if:
  - This stock's current volume is in the top 3 of all watchlist stocks
  OR this stock's relative volume is > 3x its daily average
WARN (don't block, but log) if:
  - Volume is evenly distributed across 5+ stocks (no dominant mover)
```

**GATE 4: PRICE/FLOAT SWEET SPOT**
```
PASS if:
  - Price $3-$15 (core range)
  - Float available (not critical to block, but log)
REDUCE SIZE if:
  - Price $2-$3 or $15-$20 (edge of range — use 50% position)
FAIL if:
  - Price > $20 (Ross says don't for small accounts)
  - Price < $2 (fill problems, penny territory)
```

**GATE 5: NO SYMBOL RE-ENTRY AFTER LOSS**
```
FAIL if:
  - This symbol already had 1+ losing trade today
  - Bot already traded this symbol 2+ times today (win or lose)
```

### Flow Diagram
```
Scanner → Watchlist → Detector created
  ↓
1-min bar → IMPULSE detected → PULLBACK phase
  ↓
PULLBACK complete → CONFIRMATION candle
  ↓
═══════════════════════════════════════
  QUALITY GATE (NEW — replaces old scoring gate)
    Gate 1: Clean Pullback? ─── FAIL → skip, log reason
    Gate 2: Impulse Strong? ─── FAIL → skip, log reason  
    Gate 3: Volume Dominant? ── WARN → log, continue
    Gate 4: Price/Float OK? ─── FAIL → skip / REDUCE → half size
    Gate 5: No Re-entry? ────── FAIL → skip, log reason
═══════════════════════════════════════
  ↓ ALL PASS
ARM GATES (existing 4):
  R ≥ $0.03 | Stale | Exhaustion | Warmup
  ↓
ARM → trigger price set → wait for tick
  ↓
ENTRY
```

---

## WHAT THIS WOULD HAVE DONE TO THE 24 BACKTEST TRADES

### Date 1 (2025-01-02): 6 trades → probably 3-4 trades
- AEI: Depends on pullback quality (Ross won on this stock, so setup was valid)
- APM: 4 trades → Gate 5 (re-entry limit) would cap at 2 trades max

### Date 2 (2025-11-05): 2 trades → probably 0-1 trades  
- BQ: Likely fails Gate 2 (impulse strength) or Gate 3 (volume dominance) — this wasn't THE stock

### Date 3 (2025-11-06): 6 trades → probably 2-3 trades
- CRWU/CRWG/AVX/NHTC: Multiple trades across many symbols suggests dispersed volume — Gate 3 would flag this
- Gate 5 would prevent the bot from trying 6 different mediocre stocks

### Date 4 (2026-01-06): 5 trades → probably 3 trades
- UXRP: Likely fails quality checks
- Gate 5 caps CRDU at 1 entry

### Date 5 (2026-02-03): 5 trades → probably 0-1 trades (massive improvement)
- MOVE, GLGG, BIYA, DRCT, ELAB: On Ross's no-trade day, Gate 1 (pullback quality) and Gate 2 (impulse strength) would likely filter most of these
- If any passed, Gate 3 (volume dominance) would flag the dispersed volume
- This is the single biggest improvement — stopping the bot from trading on garbage days

### Estimated impact:
- Before: 24 trades, 5 wins, -$6,426
- After (conservative): ~12-15 trades, 4-5 wins, probably -$2,000 to -$3,500
- The quality gate doesn't add winners, but it ELIMINATES the worst losers

---

## IMPLEMENTATION NOTES FOR CLAUDE CODE

### Where to add the quality gate
In `micro_pullback.py`, after the confirmation candle is detected and before the ARM stage. The method `_pullback_entry_check()` currently goes:
1. Check pullback phase progression (impulse → pullback → confirmation)
2. Run ARM gates
3. Set trigger price

The quality gate inserts between steps 1 and 2.

### Data already available
- Impulse candle data (price, volume) — already tracked for the pullback pattern
- Pullback candle data (how many, how deep) — already tracked
- Current relative volume — available from scanner data  
- Price and float — available from scanner data
- Per-symbol trade history — available from trade_manager

### Data that needs to be computed
- Pullback depth as percentage of impulse range
- Average volume ratio (pullback bars vs. impulse bars)
- Candle overlap metric (how choppy the pullback is)
- Volume dominance ranking across watchlist

### Config variables to add
```
WB_QUALITY_GATE_ENABLED=1
WB_MAX_PULLBACK_RETRACE_PCT=65    # Max % of impulse that pullback can retrace
WB_MAX_PB_VOL_RATIO=70            # Max pullback volume as % of impulse volume
WB_MAX_PB_CANDLES=4               # Max candles in pullback before it's "choppy"
WB_MIN_IMPULSE_PCT=2.0            # Min impulse move as % of stock price
WB_MIN_IMPULSE_VOL_MULT=1.5       # Min impulse volume as multiple of avg bar vol
WB_MAX_SYMBOL_LOSSES=1            # Max losses per symbol before blocking re-entry
WB_MAX_SYMBOL_TRADES=2            # Max total trades per symbol per day
WB_PRICE_SWEET_LOW=3.0            # Lower bound of sweet spot
WB_PRICE_SWEET_HIGH=15.0          # Upper bound of sweet spot
```

### Logging
Every quality gate check should log its result so we can analyze in backtest:
```
QUALITY_GATE symbol=MOVE gate=clean_pullback result=FAIL reason="retrace_78pct > max_65pct"
QUALITY_GATE symbol=MOVE gate=impulse_strength result=FAIL reason="impulse_1.2pct < min_2.0pct"
```

This lets us tune thresholds without changing code — just change config values.

### What NOT to do
- Do NOT add news checking / API calls — keep it data-only
- Do NOT add complex machine learning or classification
- Do NOT add day-level quality scores (no "sit out" logic)  
- Do NOT re-introduce profiles or per-stock config overrides
- Keep it simple: 5 binary checks, each with one or two numeric thresholds

---

## PRIORITY ORDER FOR IMPLEMENTATION

1. **Gate 1 (Clean Pullback)** — Highest impact, addresses the core "messy chart" problem
2. **Gate 5 (No Re-entry)** — Easy to implement, prevents the #1 loss pattern
3. **Gate 2 (Impulse Strength)** — Filters weak/fake setups
4. **Gate 4 (Price/Float)** — Already has the data, quick to add
5. **Gate 3 (Volume Dominance)** — Most complex, save for last

Start with Gates 1, 5, and 2. These three alone would likely eliminate 40-50% of the losing trades from the backtest while preserving most of the winning trades.

---

*Analysis by Perplexity Computer — Source data: Ross Cameron 47-trade dataset, "From Zero" video transcript, Warrior Bot playbook synthesis, 5-date backtest results (24 trades)*
