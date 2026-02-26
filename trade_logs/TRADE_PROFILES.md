# Trade Profiles — Emerging Patterns

**Purpose**: Identify recurring stock behavior profiles so the bot can (1) RECOGNIZE which profile a stock fits, and (2) TRADE to that profile's strengths.

**Status**: Data collection phase. Adding cases as we study them. Will tune bot after 25-30 cases.

---

## Profile A: "Early Bird Premarket Ramp"
**Bot verdict: STRENGTH — bot can beat Ross here**

### Identifying Characteristics
- Stock begins moving in premarket (before 7:30 AM) with building volume
- Low price ($3-$6 range), micro float
- Steady green bars with increasing volume — not a sudden spike
- Strong pattern signals fire early (ASC_TRIANGLE, FLAT_TOP, R2G, VOL_SURGE)
- Score 10+ with multiple structural pattern tags

### How the Bot Wins
- Early detection at 07:00-07:15 catches the initial ramp before Ross even sees it on scanners
- Bot enters at low price with tight R and rides the first leg
- No hesitation or "feeling late" — mechanical advantage over human psychology

### How the Bot Loses on This Profile
- TW exit cuts winners short (VERO: exited $4.68, stock went to $12.93)
- Pullback re-entry stops too tight for post-ramp volatility (VERO Trade 2: stopped by $0.21)
- Can't re-enter after circuit breaker chaos destroys state machine

### Cases
| Stock | Date | Bot P&L | Ross P&L | Notes |
|-------|------|---------|----------|-------|
| VERO | 01/16 | **+$6,890** | +$3,400 | Bot BE exits freed re-entry → Trade 3 at $3.60 caught +$7,713. Bot +$3,490 edge |
| ROLR (early) | 01/14 | +$873 (T3) | — | Trade 3 at $5.91 caught explosion but BE exit at $7.71 cut winner short (was +$1,183 with TW) |
| FLYX | 01/08 | -$703 | Positive | Bot entered $4.91 (1 min after scanner, $0.98 BETTER than Ross's $5.89). BE exit at $5.23 cut winner that went to $6.50 (+$2,090 potential). Trade 3 at $5.99 stopped $0.01 before breakout |

### What to Tune (Later)
- Wider TW exit tolerance on strong first-leg moves
- Wider pullback stops after parabolic first legs
- Post-halt state recovery mechanism
- BE exit grace period during parabolic ramps (FLYX, ROLR, VERO all cut winners)

---

## Profile B: "Fast Premarket Mover — Bot Too Slow"
**Bot verdict: WEAKNESS — bot gets destroyed, enters hours late at 2x the price**

### Identifying Characteristics
- Stock hits scanner around 8:00-8:15 AM, already up big
- Strong catalyst (news, earnings, sector theme)
- Ross enters at 8:00-8:15 during the initial impulse
- Stock runs hard for 30-60 min then chops/fades
- Bot doesn't detect until mid-morning or later, enters near the top

### How Ross Wins
- Scanner alert → reads headline → checks L2 → enters within minutes
- Aggressive scaling in/out during the initial move
- Takes profit into strength, stops when momentum dies

### How the Bot Loses
- State machine needs bars to build structure — can't enter on the first impulse
- By the time patterns confirm (10:00-12:00), stock is fading
- Enters at 2x the price Ross got, near the top

### Cases
| Stock | Date | Bot P&L | Ross P&L | Notes |
|-------|------|---------|----------|-------|
| MLEC | 02/13 | +$478 | +$43,000 | BE exits enabled 6 trades (was 2). Trade 2 caught +$1,821. Still small vs Ross |
| TWG | 01/20 | $0 | +$20,790 | 155% PM run. Bot got ZERO trades — MACD gate blocked, then too slow |
| PAVM | 01/21 | -$2,800 | +$43,950 | Bot got early entry ($10.05 vs Ross $12.31) but tiny size (381 shares vs 15K). BE exit saved $651 on Trade 4 |
| MNTS | 02/06 | -$1,236 | +$9,000 | Ross at ~$8 at 8:00. Bot at $6.07 at 12:05 — 4 hrs late, stock faded from $9 |

### What to Tune (Later)
- MACD gate override for strong PM momentum
- VWAP reclaim entry type (don't need full structure rebuild)
- "Scanner alert" equivalent — detect sudden volume/price spikes faster
- Max entry delay: if stock already up 100%+ and bot hasn't entered, don't chase

---

## Profile C: "Resistance Chopper — Bot Buys Into Walls"
**Bot verdict: WEAKNESS — bot enters at wrong levels, gets chopped repeatedly**

### Identifying Characteristics
- Stock has a clear resistance zone (often at half/whole dollar)
- Stock tests resistance 2-3 times, gets rejected each time
- Eventually breaks through (or doesn't) — but the bot keeps buying INTO resistance
- Ross buys the DIP after rejection, waits for the BREAK of resistance
- Bot enters on the approach to resistance, not the break of it

### How Ross Wins
- Identifies resistance levels (half/whole dollars, prior highs)
- Buys the pullback/dip BELOW resistance
- Sizes up massively on the confirmed BREAK (30K shares on LCFY $7 break)
- Takes quick profit (30-75 cents/share)

### How the Bot Loses
- No resistance tracking — treats each setup independently
- Enters $6.14, $6.23, $6.21 (all into the same $6.00-$6.50 ceiling)
- MACD lag locks bot out right before the actual breakout
- No catalyst awareness to boost conviction for the break

### Cases
| Stock | Date | Bot P&L | Ross P&L | Notes |
|-------|------|---------|----------|-------|
| LCFY | 01/16 | -$1,627 | +$10,000 | Bot entered $6.14-$6.23 into resistance. BE exit saved on Trade 2. Ross bought $6.50 dip, then $7 break with 30K shares |
| TNMG | 01/16 | -$1,481 | +$2,000 | BE exit saved $519 on Trade 1 ($3.71 vs $3.44 stop). Still a loss — Ross bought dip for $4 break |
| ACON | 01/08 | -$2,630 | +$9,293 | Bot entered $8.22-$8.86 into $8.50 resistance 4 times. Ross dip-bought at $7.60 BELOW breakout. BE exits saved ~$1,370. Extended move guard killed $9 push (+$2K for Ross) |

### What to Tune (Later)
- Track rejection levels — if price rejected at X twice, don't enter below X again
- Half/whole dollar awareness for entry triggers
- "Dip buy" entry type — enter on pullback from resistance, not approach to it
- Catalyst-boosted conviction for confirmed level breaks
- Pre-position below breakout level (Ross placed order at $8, filled at $7.60 on dip)

---

## Profile D: "Flash Spike Ghost — Illiquid One-Shot"
**Bot verdict: STRENGTH with BE exits — bot captures the spike and exits before collapse**

### Identifying Characteristics
- Ultra micro float (<1M shares)
- Near-zero premarket volume (<1K shares)
- Opens dead quiet, then sudden 40-60% spike in 2-3 minutes
- Immediate collapse — gives back 50%+ of spike within 5 minutes
- Volume dies 97% within an hour
- Only 3-4 new highs, all compressed into the spike window
- No news / FOMO-driven

### How the Bot Wins (with BE exits)
- Enters PRE-spike with large position (7,142 shares due to tight R)
- Bearish engulfing exit on 10s bars catches the spike reversal perfectly
- Exits at $6.57 during the spike, locking in +$7,713 before the collapse
- Post-halt Trade 2 still loses, but overall a big win

### How Ross Wins
- Enters DURING the spike at half/whole dollar levels ($6.50, $7.00)
- Sizes small — recognizes no catalyst = no sustained move
- Takes quick profit (75 cents/share) and moves on

### Cases
| Stock | Date | Bot P&L | Ross P&L | Notes |
|-------|------|---------|----------|-------|
| GWAV | 01/16 | **+$6,735** | +$4,000 | BOT WON. BE exit at $6.57 captured spike (+$7,713). Trade 2 halt-auction still lost (-$979) |

### What to Tune (Later)
- Halt-auction detection: discard LULD reopening prints from entry calculations (Trade 2 issue remains)
- This profile may actually be a bot strength with BE exits — the mechanical exit catches the spike reversal faster than human reaction

---

## Profile E: "Morning Spike Trap — Looks Like a Runner, Fades All Day"
**Bot verdict: AVOID — need better filters to recognize this early**

### Identifying Characteristics
- Micro float, gapped up, looks like a runner on scanner
- Spikes in first 1-2 bars then immediately reverses (RED bar within 2 min)
- Cannot reclaim premarket high
- Loses VWAP within 3 minutes of open
- Volume dies quickly — most volume in first 30 minutes
- Consecutive RED runs dominate (6-8 bar streaks)
- Closes significantly below open

### How to Distinguish from Real Runner
| Metric | Real Runner (VERO) | Trap (TNMG) |
|--------|-------------------|--------------|
| Session new highs | 18 | 3 |
| Close vs Open | +208% | -20% |
| VWAP relationship | Above all session | Lost in 3 minutes |
| Post-halt recovery | Settled 1.8x open, ran | Settled below open |
| Volume trend | Sustained all day | Died after 30 min |

### Cases
| Stock | Date | Bot P&L | Ross P&L | Notes |
|-------|------|---------|----------|-------|
| TNMG | 01/16 | -$1,481 | +$2,000 | Score 4.0 with zero pattern tags. BE exit saved $519 on Trade 1. PM high $4.49 never reclaimed. Bot also re-entered 3 hrs later |

### What to Tune (Later)
- Raise min score or require at least 1 structural pattern tag
- PM high awareness: if spike < PM high, reduce conviction
- Session trend filter: stock down 20%+ from open → no more longs
- "One and done" rule: if first trade on a stock loses, don't re-enter same session on the same stock without significantly changed conditions

---

## Profile F: "Post-Halt Crash Recovery"
**Bot verdict: MISSED OPPORTUNITY — bot can't trade post-halt recoveries**

### Identifying Characteristics
- Micro float with halt on open (stock jumps 50-100%+ in first candle)
- Immediate crash: gives back 50-70% of halt spike within 15 minutes
- Hits a hard LOD (often near/below pre-halt open)
- Real recovery begins: 10+ consecutive green bars building from LOD
- Recovery hits resistance at 50-60% of halt spike range
- Breakout above resistance is the real trade

### How Ross Wins
- Recognizes the crash as opportunity, not danger
- Buys the dip after the recovery establishes direction
- Sizes up on the confirmed breakout above resistance
- Catalyst awareness gives conviction to hold through the recovery

### How the Bot Loses
- Zero seed bars = no EMA, no structure → misses the entire 10-bar recovery run
- When it finally engages, enters into the resistance zone (not the breakout)
- MACD bearish cross locks it out 1 bar before the actual breakout

### Cases
| Stock | Date | Bot P&L | Ross P&L | Notes |
|-------|------|---------|----------|-------|
| LCFY | 01/16 | -$1,627 | +$10,000 | No PM bars. Missed $3.74→$5.58 (10-bar run). Entered resistance zone. BE exit saved on Trade 2. MACD locked out of $7.22 breakout |

### What to Tune (Later)
- Cold start acceleration: build state faster when first bars arrive
- "Buy the crash" framework: detect LOD bounce + sustained green bars
- Override MACD gate when volume breakout confirms direction

---

## Tracking Summary

| Profile | Bot Verdict | Cases | Win Rate |
|---------|------------|-------|----------|
| A: Early Bird PM Ramp | STRENGTH | 3 | 67% (2/3 — FLYX bot had better entry but exits killed it) |
| B: Fast PM Mover | WEAKNESS | 4 | 25% (1/4 — MLEC now +$478) |
| C: Resistance Chopper | WEAKNESS | 3 | 0% (0/3) |
| D: Flash Spike Ghost | **STRENGTH** | 1 | **100% (1/1 — GWAV +$6,735)** |
| E: Morning Spike Trap | AVOID | 1 | 0% (0/1) |
| F: Post-Halt Recovery | MISSED | 1 | 0% (0/1) |

*All results updated 2026-02-25 after adding bearish engulfing exit to backtester. GWAV flipped from AVOID to STRENGTH — BE exits are critical for flash spike profiles.*

**Next steps**: Continue adding cases. Some stocks may fit multiple profiles. As counts grow, patterns will sharpen and we'll know which profiles to prioritize for bot tuning.
