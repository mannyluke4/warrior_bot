# DIRECTIVE: Wave Scalp Strategy — Stage 1 (Research & Pattern Validation)

**Date:** May 4, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code) / Cowork  
**Priority:** P1 — Research first, no code yet  
**Branch:** `v2-ibkr-migration`

---

## Context & Thesis

Manny has been paper-trading on TradingView for the past two weeks, hand-scalping the same stocks the bot puts on its watchlist. **Result: +$37K in 14 days** — entirely from trading consolidation waves on the post-squeeze tape, NOT from squeeze entries themselves.

His pattern (translated from intuition into rules):

1. Watchlist stock is "alive" — high volume, high tick count, gap-up small-cap (already qualified by our scanner)
2. Stock is fluctuating — at least one full up-down-up cycle since RTH open
3. 1-min MACD turns positive OR is in the process of flipping up (histogram rising)
4. Price tests a recent wave low and HOLDS (forms a higher low)
5. Entry on the bounce as price leaves the wave bottom
6. Target: the recent wave high (established resistance)
7. Stop: below the wave low that triggered the entry

## Why This Could Outperform Squeeze

- **Squeeze fires 1-2x per stock per day** (the initial breakout moments)
- **Wave Scalp could fire 5-10x per stock per day** (every consolidation oscillation)
- **Lower R per trade, much higher frequency**, only on stocks that have ALREADY proven they can move
- **Complementary, not competing** — Wave Scalp activates AFTER squeeze has either fired or been rejected for that stock

The strategy doesn't fight the squeeze; it harvests the choppy aftermath that squeeze ignores.

---

## Stage 1 Goal

**Validate the wave-scalp thesis on existing tick data BEFORE writing any strategy code.**

We need to answer four questions, in order:

1. **Do the patterns Manny describes actually appear in our YTD tick cache?**
2. **How often do they appear per stock per day?**
3. **If a bot mechanically traded them, would it have been profitable?**
4. **Which exact rules produced the best risk-adjusted returns?**

Only after all four are answered with real data do we proceed to Stage 2 (strategy build).

---

## Required Deliverables

### Deliverable 1: Wave Detection Algorithm (`wave_detector.py`)

A new file that processes 1-minute bars and identifies waves. **No trading logic yet** — just pattern detection and labeling.

A "wave" is defined as:
- A price swing of **at least 0.75%** from a local extreme (high or low)
- Duration: **3-15 minutes** between extremes
- Confirmation: must be followed by a reversal of at least 0.5% in the opposite direction

Output for each detected wave:
```python
{
    "symbol": "RECT",
    "date": "2026-04-13",
    "wave_id": 4,
    "direction": "up",                    # 'up' or 'down'
    "start_time": "10:23:00 ET",
    "start_price": 1.98,
    "end_time": "10:31:00 ET",
    "end_price": 2.04,
    "duration_minutes": 8,
    "magnitude_pct": 3.03,
    "magnitude_dollars": 0.06,
    "max_volume_bar": 12500,
    "avg_volume": 6800,
}
```

### Deliverable 2: YTD Wave Census

Run `wave_detector.py` across **all dates in `tick_cache/`** for the YTD-cached symbols. For each (symbol, date) pair, output a summary:

```json
{
  "symbol": "RECT",
  "date": "2026-04-13",
  "session_start": "07:00 ET",
  "session_end": "20:00 ET",
  "total_waves": 47,
  "waves_per_hour": 4.3,
  "avg_wave_magnitude_pct": 1.4,
  "median_wave_magnitude_pct": 1.1,
  "max_wave_magnitude_pct": 6.2,
  "wave_count_after_first_squeeze": 38,
  "first_squeeze_time": "09:14:30 ET",
  "first_squeeze_outcome": "bearish_engulfing_exit (-$173)"
}
```

Save to: `wave_research/ytd_wave_census.csv`

### Deliverable 3: Pattern-Match Scoring

For each detected wave, identify whether it matches Manny's entry pattern. Score it on these mechanical criteria:

```python
def score_wave_setup(wave_low_bar, prior_waves, macd_state):
    score = 0
    
    # 1. At least 2 prior waves observed (proves stock is oscillating)
    if len(prior_waves) >= 2:
        score += 1
    
    # 2. Current bar is near a recent wave low (within 1%)
    recent_low = min(w.start_price if w.direction == 'down' else w.end_price 
                     for w in prior_waves[-3:])
    if abs(wave_low_bar.low - recent_low) / recent_low <= 0.01:
        score += 2
    
    # 3. MACD line is rising (histogram positive and increasing for 2 bars)
    if macd_state.histogram_rising:
        score += 2
    
    # 4. Higher low forming (current low > previous wave's low)
    prev_wave_low = min(w.end_price for w in prior_waves[-2:] if w.direction == 'down')
    if wave_low_bar.low > prev_wave_low:
        score += 2
    
    # 5. Volume confirmation on the bouncing bar
    if wave_low_bar.volume > avg_5_bar_volume:
        score += 1
    
    # 6. Bounce candle is green (close > open)
    if wave_low_bar.close > wave_low_bar.open:
        score += 1
    
    # 7. Bounce candle has minimal upper wick (not topped)
    upper_wick = wave_low_bar.high - max(wave_low_bar.open, wave_low_bar.close)
    body = abs(wave_low_bar.close - wave_low_bar.open)
    if body > 0 and upper_wick / body < 0.5:
        score += 1
    
    return score  # max = 10
```

For each cached date, count how many waves scored ≥ 7 (high-quality setups).

### Deliverable 4: Hypothetical Backtest

For every wave that scored ≥ 7, simulate the trade:

- **Entry:** Open of next 1-min bar after the qualifying bar
- **Target:** Highest price of the most recent up-wave (established resistance)
- **Stop:** Low of the qualifying wave - 0.25% (just below the support that triggered entry)
- **Time stop:** 10 minutes — if neither target nor stop hit, exit at market
- **Position size:** $1,000 risk per trade (fixed for now, sizing optimization comes later)

Output for each trade:
```json
{
  "symbol": "RECT",
  "date": "2026-04-13",
  "entry_time": "10:33:00",
  "entry_price": 2.05,
  "target": 2.18,
  "stop": 1.96,
  "exit_time": "10:39:00",
  "exit_price": 2.18,
  "exit_reason": "target_hit",
  "pnl_per_share": 0.13,
  "shares": 11111,    # $1000 / $0.09 risk = 11111
  "pnl": 1444,
}
```

Save to: `wave_research/ytd_hypothetical_trades.csv`

### Deliverable 5: Written Analysis Report

Save to: `cowork_reports/2026-05-XX_wave_scalp_research.md`

Required sections:

**Section A: Wave Frequency**
- Average waves per stock per day
- Distribution of wave magnitudes (1%? 2%? 5%?)
- Time-of-day patterns (do waves cluster pre-RTH? post-open? lunch?)
- Comparison: stocks that squeezed vs stocks that gapped but didn't squeeze

**Section B: Pattern Match Rate**
- What % of detected waves score ≥ 7?
- Of those, what % occur AFTER the first squeeze attempt?
- Which scoring criteria are most predictive of profitable trades?

**Section C: Hypothetical Performance**
- Total hypothetical P&L across all YTD dates
- Win rate
- Avg winner / avg loser
- Profit factor
- Max drawdown
- Trades per day distribution
- Performance by stock type (what makes a good wave-scalp stock?)

**Section D: Key Findings & Recommendations**
- Is the thesis validated? Yes/No with evidence
- Should we proceed to Stage 2 (build the strategy)?
- What rule changes would improve the results?
- What stock filters should activate Wave Scalp on (vs deactivate)?

---

## What NOT to Do

- ❌ Do NOT modify any existing strategy files (`squeeze_detector.py`, `bot_v3_hybrid.py`, etc.)
- ❌ Do NOT build a strategy module yet — research and validate first
- ❌ Do NOT fetch new data from Databento or IBKR — use only what's already in `tick_cache/`
- ❌ Do NOT optimize parameters by curve-fitting to a few stocks — use the full YTD population
- ❌ Do NOT skip the written analysis — the deliverable is INSIGHT, not just code

## Important Caveats

1. **The tick cache is the IBKR-sourced cache (post-cleanup commit `19671c0`).** Trust this data. Do NOT silently fall back to other sources.
2. **Manny is up $37K in 2 weeks paper trading.** That's the bar to beat, but human discretion will always have advantages a bot doesn't (skipping bad-looking setups, reading market context). The bot's first version should fire LESS often than Manny does — start strict, loosen later if results justify it.
3. **Watchlist context matters.** This strategy is meant to run ONLY on stocks that the bot has already qualified (high volume, gap-up, on the watchlist). It's not a standalone scanner — it's a second-stage strategy that activates on already-vetted symbols.

## Timeline

- **Stage 1 (this directive):** Research and validation — 1-3 days
- **Stage 2 (next directive, contingent on Stage 1 results):** Build `wave_scalp_detector.py` and integrate as optional strategy
- **Stage 3:** Backtest on full YTD with squeeze + wave-scalp combined
- **Stage 4:** Live paper test alongside squeeze bot
- **Stage 5:** Real money if both stages produce consistent results

## Acceptance Criteria for Stage 2 Approval

Stage 1 results must show ALL of:

- [ ] Wave detection algorithm correctly identifies oscillations on at least 5 known-good stocks (manually verified by Manny)
- [ ] At least 100 hypothetical trades across the YTD census
- [ ] Hypothetical win rate ≥ 50%
- [ ] Hypothetical profit factor ≥ 1.4
- [ ] Distribution of trade outcomes is not dominated by 1-2 outlier days
- [ ] Pattern is observable on a meaningful percentage of watchlist stocks (≥ 30%)

If any criterion fails, document why and propose specific changes before retrying.

---

*The squeeze hunts the rocket. Wave Scalp harvests the chop. Both edges, same stocks, complementary timing.*
