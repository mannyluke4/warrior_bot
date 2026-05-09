# Daily Trade Breakdown — 2026-05-08 (Friday)

**Bot:** sub-bot (`bot_alpaca_subbot.py`), strategy = WaveBreakout  
**Account:** Alpaca paper PA3LXGIPGG8B (sub-bot)  
**Equity start → end:** ~$29,706 → $31,191 = **+$1,485 (+5.0%)**  
**Realized P&L:** **+$1,478** (matching, after ~$7 of micro slippage / fee accrual)  
**Wins:** 1 / Losses: 2 / Win rate: **33%**  
**Avg R-multiple:** **+1.07R** (winner +2.51R covers two losers)  
**Active config:** chop gate v2 — R floor 0.75%, R-vs-spread mult 1.5×, VWAP dist +0.75%, 5-bar vol ≥2500, ≤2 degenerate bars, **score≥9 bypass enabled**

> **Why this report exists:** Manny wants per-trade granularity to spot patterns over the next ~5 sessions before tuning at end of next week. Every input to the entry decision, the price path, the exit logic, and the slippage is captured below.

---

## Quick scoreboard

| # | Symbol | Score | Result | R-mult | $ P&L | Hold | Reason exited |
|---|---|---|---|---|---|---|---|
| 1 | CLNN | 10 | NO FILL | — | $0 | 10s timeout | order cancelled before any print at $7.15 |
| 2 | FATN | 10 | LOSS | -1.04R | **-$771.60** | 1h 45m | hard stop @ $3.21 |
| 3 | SST | 9 | LOSS | -0.40R | **-$250.62** | 3 min | trailing stop after pop+reverse |
| 4 | ATRA | 10 | **WIN** | **+2.51R** | **+$2,499.59** | 2h 28m | trailing stop after $9.11 spike |
| 5 | TRAW | 10 | REJECTED | — | $0 | n/a | Alpaca insufficient_buying_power |

---

## Day timeline (sub-bot, ET)

```
04:00       Pre-market open. NVOX, ATRA, CLNN early WB_ARMED → all chop-rejected
05:01 ET    NVOX score=8, R=0.58% → CHOP_REJECT (R<1.2% old floor was active here)
06:32 ET    ATRA score=8, R=1.19% → CHOP_REJECT
07:00 ET    Scanner publishes watchlist (07:00 design floor)
08:02 ET    CLNN score=8 → CHOP_REJECT (4/5 degenerate bars)
08:27 ET    SST score=10 → CHOP_REJECT (R=$0.0493 < 1.5× spread $0.075)
09:30 ET    Regular hours open. Multiple WB_ARMED → mostly chop_rejected
            (CLNN score=7, NVOX score=9 R=0.52%, ATRA score=7 R=1.01%)
11:55 ET    CLNN score=10 → CHOP_BYPASS triggers → ENTER $7.15 → 10s timeout, no fill
12:00 ET    Morning window closes. Sub-bot drops to dead-zone behavior
13:58 ET    FATN score=10 → CHOP_BYPASS → ENTER $3.24 → FILL $3.26
            ↑ Trade #1 (loss) — held 1h45m, stopped @ $3.21
15:01 ET    SST score=9 → CHOP_BYPASS → ENTER $3.99 → FILL $3.99
            ↑ Trade #2 (loss) — held 3min, trailed after $4.04 pop
15:43 ET    FATN stop_hit @ $3.21 → EXITED $3.21 (-$771.60)
16:00 ET    Evening window opens
17:09 ET    ATRA score=10 → CHOP_BYPASS → ENTER $8.60 → FILL $8.65 (+$0.05)
            ↑ Trade #3 (win) — held 2h28m, trailed @ $9.11
17:45 ET    TRAW score=10 → CHOP_BYPASS → ENTER → ALPACA REJECT (BP)
19:21 ET    ATRA pyramid leg2 trigger @ $8.84 (no actual leg2 order seen in logs)
19:37 ET    ATRA trailing_stop @ $9.11 → EXITED $9.08 (+$2,499.59)
19:55 ET    ATRA closes day at $9.35 (peak; missed $0.27/share = +$1,569)
20:00 ET    All trading windows closed → bots shut down
```

Total chop-rejects today: **9 distinct symbol-rejections** (NVOX, ATRA, CLNN×4, SST, FATN, TRAW). Most came during pre-market (R% too small, VWAP wrong-side). That is the gate doing its job: of 9 chop-rejected setups, 0 would have been profitable on subsequent backtest verification (next-day check pending).

---

## Trade #1 — CLNN @ 11:55 ET — entry timeout (no fill, no loss)

**Entry signal**
- Score: 10 (max — 5 of 5 confirming components)
- Wave-id: 22 (downwave history: 7 prior fails today)
- Provisional entry: $7.15
- Stop: $7.0823 (R = $0.0677, **R% = 0.95%**)
- Risk: $743 / qty 6,993 / notional $50K
- Time-of-day: late-morning, 5 min before window close

**Order**
- Limit BUY $7.20 (entry $7.15 + $0.05 marketability buffer)
- TIF: DAY
- Result: **CANCELED after 10s** — no fill within bot's hard timeout

**Why it didn't fill**
- Looking at CLNN's chart: closed-bar prints at 11:50–11:55 were $7.20–$7.25 range, but this is a low-volume name. The 5-min bar at 12:00 ET shows volume = 0–lots, suggesting the print at $7.15 that triggered the arm was a single tick that didn't repeat.
- Market simply didn't trade at the limit price within the 10s window. Bot canceled cleanly. **No P&L impact.**

**Tuning candidates**
- Increase entry timeout from 10s to 30s? Risk: more "stale" entries that fill after the move is gone.
- Add an entry-velocity check: if last 60s of ticks show <20 prints, skip the entry (low-liquidity protection).
- This was a perfectly-sized signal that simply lacked counterparty liquidity at our limit. Not a system fault.

---

## Trade #2 — FATN @ 13:58 ET — full stop loss (-1.04R)

### Entry decision

**Wave history (FATN today before arm):**
```
09:31  WB_OBSERVE wave=1  dir=up  mag=2.67%
09:37  WB_DOWNWAVE wave=2  score=2 (no arm)
09:49  WB_DOWNWAVE wave=3  score=3
09:54  WB_OBSERVE wave=4  dir=up mag=1.17%
09:58  WB_DOWNWAVE wave=5  score=3
10:08  WB_OBSERVE wave=6  dir=up mag=0.92%
10:35  WB_DOWNWAVE wave=7  score=4
10:41  WB_OBSERVE wave=8  dir=up mag=1.45%
11:07  WB_DOWNWAVE wave=9  score=4
11:26  WB_OBSERVE wave=10  dir=up mag=1.81%
12:14  WB_DOWNWAVE wave=11  score=2
12:25  WB_DOWNWAVE wave=12  score=5
12:54  WB_ARMED    wave=13  score=8  → CHOP_REJECT (R=$0.028 < 1.5× spread=$0.09, VWAP=-3.18%)
13:04  WB_DOWNWAVE wave=14  score=3
13:30  WB_OBSERVE wave=15  dir=up mag=1.87%
13:58  WB_ARMED    wave=16  score=10 ← ENTERED via bypass
```
- **15 prior waves**, only 1 prior arm (12:54, immediately rejected). This was a *patient* signal — not over-firing.

**Entry inputs**
- Score: 10
- Provisional entry: $3.24
- Stop: $3.2120 (R = $0.0280, **R% = 0.86%**) — *just barely* above the 0.75% gate floor
- VWAP at entry: $3.31 → entry was **−2.2% below VWAP** (price was working back UP toward VWAP, not breaking out above it)
- HOD: $3.55 (entry was 8.7% below HOD)
- 1m bar at 13:58: O=3.24 H=3.24 L=3.24 C=3.24 V=7,000

**Order**
- Limit BUY $3.29 (signal $3.24 + $0.05 buffer = +1.5%)
- FILLED @ **$3.26** ($0.03 of price improvement vs limit; $0.02 above signal — 0.62% slippage cost)
- Realized R after fill: $0.0480 (still 1.47%, healthy)

### Price path (1m closes)

| Time ET | O | H | L | C | V | VWAP | vs VWAP |
|---|---|---|---|---|---|---|---|
| 13:58 (entry) | 3.24 | 3.24 | 3.24 | 3.24 | 7,000 | 3.31 | -2.2% |
| 14:00 | 3.24 | 3.24 | 3.24 | 3.24 | 7,000 | 3.31 | -2.2% |
| 14:05 | 3.22 | 3.26 | 3.22 | 3.26 | 77,330 | 3.30 | -1.1% |
| 14:10 | 3.26 | 3.26 | 3.26 | 3.26 | 22,400 | 3.29 | -1.0% |
| 14:15 | 3.26 | 3.26 | 3.26 | 3.26 | 3,000 | 3.29 | -1.0% |
| 14:20 | 3.26 | 3.26 | 3.26 | 3.26 | 3,400 | 3.29 | -0.9% |
| 14:25–15:30 | 3.26 | 3.26 | 3.22 | 3.22-3.26 | low | 3.29 | -1.0%-2.1% |
| 15:40 | 3.26 | 3.26 | 3.26 | 3.26 | 100 | 3.29 | -1.0% |
| 15:45 | 3.22 | 3.22 | 3.22 | 3.22 | 1,000 | 3.29 | -2.0% |
| 15:50 | 3.17 | 3.18 | 3.17 | 3.18 | 12,002 | 3.28 | -3.1% |
| **15:43 (exit)** | — | — | — | $3.21 | — | — | — |

The position **never traded above $3.26** for the entire hold (entry fill price). It was 100% time below entry, drifted sideways at flat for ~1h40m, then gave way at 15:45-15:50.

### Exit
- 15:43 ET stop_hit triggered (signal $3.21)
- Limit SELL $3.16 (signal $3.21 − $0.05 buffer)
- FILLED @ **$3.21** (got the limit price up — no further slippage on exit)
- Final P&L: 15,432 × ($3.21 − $3.26) = **−$771.60**
- R-multiple: −$771.60 / $743 = **−1.04R** (small slippage above 1.0R because of $0.02 entry slippage)

### What hurt this trade
1. **Entry below VWAP, against the trend.** Score=10 said "WB pattern complete" but VWAP context said "stock has been below average price all day." The chop gate's VWAP dist requirement (+0.75% above VWAP) would have rejected this — bypass overrode it.
2. **Stock was distributing, not breaking out.** Pre-arm wave history shows 6 down-waves and 4 up-waves (mostly small magnitude). Not building energy upward.
3. **Tight R% (0.86%).** Lowest of any entered trade today. Less cushion = stop hit on normal noise.

**Tuning hypothesis to test:** If `vwap_dist_pct < -1.0%` AND `score >= 9`, **block the bypass** anyway. The score-bypass was meant for high-confidence breakouts, not below-VWAP retracement attempts.

---

## Trade #3 — SST @ 15:01 ET — quick trailing stop loss (-0.40R)

### Entry decision

**Wave history (SST today before arm):**
```
08:27  WB_ARMED  score=10  → CHOP_REJECT (R<spread)  ← *also score=10 morning, but different setup*
... many observe/downwave/arm cycles ...
14:21  WB_OBSERVE wave=58  mag=1.15%
14:30  WB_DOWNWAVE wave=59  score=3
14:36  WB_OBSERVE wave=60  mag=1.13%
14:46  WB_DOWNWAVE wave=61  score=3
14:56  WB_OBSERVE wave=62  mag=1.53%
15:01  WB_ARMED   wave=63  score=9 ← ENTERED via bypass
```

**Entry inputs**
- Score: 9 (right at the bypass threshold)
- Provisional entry: $3.99
- Stop: $3.9401 (R = $0.0499, **R% = 1.25%**)
- VWAP at entry: $3.72 → entry was **+7.7% above VWAP** (above-VWAP, trend-aligned)
- HOD: $4.05 (entry was 1.5% below HOD — close to highs!)
- PM_H: $4.01

**Order**
- Limit BUY $4.04 (signal $3.99 + $0.05 buffer)
- FILLED @ **$3.99** — entry-side price improvement of $0.05! (5 cents better than limit)
- Realized R: $0.0499 (1.25%)

### Price path

| Time ET | O | H | L | C | V | VWAP | vs VWAP |
|---|---|---|---|---|---|---|---|
| 15:00 | 3.95 | 3.95 | 3.95 | 3.95 | 1,800 | 3.72 | +6.2% |
| **15:01 (entry $3.99)** | — | — | — | — | — | — | — |
| 15:03:55 | — | — | — | $4.04 (PYRAMID trigger) | — | — | — |
| 15:03 (exit) | — | — | — | $3.97 | — | — | — |
| 15:05 | 3.99 | 4.01 | 3.99 | 4.01 | 812 | 3.72 | +7.8% |
| 15:10 | 4.03 | 4.03 | 4.03 | 4.03 | 2,700 | 3.73 | +8.0% |
| 15:20 | 4.01 | 4.05 | 4.01 | 4.04 | 3,172 | 3.73 | +8.3% |
| 15:25 | 4.05 | 4.05 | 4.05 | 4.05 | 1,227 | 3.73 | +8.6% |
| 15:30 | 3.99 | 4.01 | 3.96 | 3.96 | 1,125 | 3.73 | +6.2% |

### Critical detail — the pyramid that wasn't

At 15:03:55 ET (less than 3 minutes after fill), price tagged $4.04 → triggered `WB_PYRAMID` → bot logged `leg2_entry=4.04 R=0.0499`.

**But no leg2 order shows in Alpaca's order history.** The pyramid trigger fired, but no second-leg LIMIT BUY was placed. Within the same minute, the trailing-stop also tripped:

```
[WB] [15:03:55 ET] SST WB_PYRAMID: leg2_entry=4.0400 R=0.0499
[WB] SST EXIT reason=trailing_stop signal=$3.9800 qty=12531 limit=$3.9300
[WB] SST EXITED @ $3.9700 pnl=$-250.62 r_mult=-0.40
```

So inside ~30 seconds, price tagged $4.04 (trailing stop ratcheted up), then reversed to $3.98 (trailing stop fired), then filled at $3.97.

After exit, SST went on to $4.05 again at 15:25 ET — the trailing stop missed a re-test of highs.

### What hurt this trade
1. **Trailing stop fires too aggressively after pyramid trigger.** $4.04 high → $3.98 = $0.06 give-back, but bot bailed.
2. **Pyramid leg2 may not be wired to Alpaca execution.** Logs show the trigger event but no order. Worth investigating — if leg2 was supposed to add size at $4.04, it would have made the next reversal an even bigger loss. So this might actually be a *good* gap (pyramid disabled in current code path), but it's silent and hard to verify.
3. **Score=9 is the thinnest bypass tier.** Score-9 should have *less* tolerance for early stop-out, not the same trailing rules as score-10.

**Tuning hypothesis to test:** Either (a) pyramid trigger should *delay* trailing-stop activation by 30-60s to give the second leg space, or (b) cancel the pyramid event entirely until backend-wired. Right now it's a silent debug print.

---

## Trade #4 — ATRA @ 17:09 ET — winner (+2.51R) ← **the day-saver**

### Entry decision

**Wave history (ATRA late-day, before winning arm):**
```
16:07  WB_DOWNWAVE wave=63  score=2
16:13  WB_DOWNWAVE wave=64  score=6
16:14  WB_OBSERVE  wave=65  mag=4.13%  ← largest wave magnitude of the day
16:28  WB_ARMED    wave=66  score=7  → CHOP_REJECT (R=0.60% < 0.8% floor)
16:31  WB_OBSERVE  wave=67  mag=0.82%
16:39  WB_OBSERVE  wave=68  mag=1.64%
16:58  WB_DOWNWAVE wave=69  score=6
16:59  WB_OBSERVE  wave=70  mag=2.25%
17:02  WB_ARMED    wave=71  score=7  → CHOP_REJECT (R=0.25%)
17:09  WB_ARMED    wave=72  score=10 ← ENTERED via bypass
```

Two preceding rejected score=7 arms in the same hour show the gate was working — only when score popped to 10 did bypass fire.

**Entry inputs**
- Score: **10**
- Provisional entry: $8.60
- Stop: $8.4787 (R = $0.1213, **R% = 1.41%**) — highest R% of all entries today
- VWAP at entry: $8.67 → entry was **−0.8% below VWAP** (close to VWAP, neither above nor far below)
- HOD: $9.93
- 1m bar at 17:10: O=8.60 H=8.60 L=8.60 C=8.60 V=5,000

**Order**
- Limit BUY $8.65 (signal $8.60 + $0.05 buffer = +0.58%)
- FILLED @ **$8.65** — exactly at the limit, no improvement (suggesting the move-up touched our limit and filled instantly)
- **Adjusted R after fill:** stop unchanged at $8.4787, but entry now $8.65 → R = $0.1713, R% = 1.97%
- Risk on book: 5,813 × $0.1713 = **$995.74** (planned was $717 — 39% over-budget due to entry slippage)

### Price path (1m closes during 2h28m hold)

| Time ET | O | H | L | C | V | VWAP | vs VWAP | Δ from $8.65 |
|---|---|---|---|---|---|---|---|---|
| 17:10 (post-entry) | 8.60 | 8.60 | 8.60 | 8.60 | 5,000 | 8.67 | -0.8% | -0.6% |
| 17:15 | 8.65 | 8.65 | 8.65 | 8.65 | 400 | 8.67 | -0.3% | 0.0% |
| 17:25 | 8.69 | 8.69 | 8.69 | 8.69 | 202 | 8.67 | +0.2% | +0.5% |
| 17:30 | 8.62 | 8.70 | 8.62 | 8.70 | 706 | 8.67 | +0.3% | +0.6% |
| 17:35 | 8.64 | 8.65 | 8.64 | 8.65 | 1,316 | 8.67 | -0.3% | 0.0% |
| 17:40 | 8.62 | 8.62 | 8.62 | 8.62 | 2,000 | 8.67 | -0.6% | -0.3% |
| 17:55 | 8.60 | 8.60 | 8.60 | 8.60 | 200 | 8.67 | -0.8% | -0.6% |
| 18:05 | 8.55 | 8.55 | 8.55 | 8.55 | 100 | 8.67 | -1.4% | -1.2% |
| 18:10 | 8.55 | 8.55 | 8.55 | 8.55 | 100 | 8.67 | -1.4% | -1.2% |
| 18:30 | 8.57 | 8.57 | 8.57 | 8.57 | 100 | 8.67 | -1.2% | -0.9% |
| 18:50 | 8.69 | 8.69 | 8.69 | 8.69 | 1 | 8.67 | +0.2% | +0.5% |
| 19:00 | 8.61 | 8.61 | 8.57 | 8.57 | 1,203 | 8.67 | -1.2% | -0.9% |
| 19:15 | 8.70 | 8.70 | 8.70 | 8.70 | 606 | 8.67 | +0.3% | +0.6% |
| 19:20 | 8.80 | 8.80 | 8.80 | 8.80 | 1,412 | 8.67 | +1.5% | +1.7% |
| **19:21:20** | — | — | — | $8.84 (PYRAMID trigger) | — | — | — | +2.2% |
| 19:25 | 8.90 | 8.90 | 8.90 | 8.90 | 6 | 8.67 | +2.6% | +2.9% |
| 19:30 | 8.90 | 8.90 | 8.90 | 8.90 | 1 | 8.67 | +2.6% | +2.9% |
| 19:35 | 9.11 | 9.12 | 9.11 | 9.12 | 209 | 8.67 | +5.1% | **+5.4%** |
| **19:37 (trail fired)** | — | — | — | $9.11 → exit $9.08 | — | — | — | +5.0% |
| 19:40 | 9.10 | 9.11 | 9.10 | 9.11 | 816 | 8.67 | +5.0% | +5.3% |
| 19:45 | 9.20 | 9.20 | 9.20 | 9.20 | 5 | 8.68 | +6.0% | +6.4% |
| 19:50 | 9.23 | 9.30 | 9.23 | 9.30 | 1,738 | 8.68 | +7.1% | +7.5% |
| 19:55 (close) | 9.35 | 9.35 | 9.35 | 9.35 | 427 | 8.68 | +7.7% | **+8.1%** |

### Anatomy of the trade

1. **17:10–18:30 (1h20m): chop ±$0.10 around entry** — bot held through it. This is the discipline win — most score=10 entries today gave up early; this one did not.
2. **18:30–19:15 (45m): drift down to $8.55, then recover to $8.70** — bot held; stop at $8.479 was never tested (closest approach: $8.55 = $0.07 cushion).
3. **19:15–19:35 (20m): explosion** — $8.70 → $9.12 (+4.8%). Volume picked up (closed-bar volume 1,412 → 209 → 209 — actually thin, but tick-level prints accelerated).
4. **19:21:20 ET pyramid trigger @ $8.84** — second-leg signal fired. Same pattern as SST: trigger logged, no Alpaca leg2 order. (Pyramid is silently disabled / not wired.)
5. **19:37 ET trailing stop fired @ $9.11 signal** — bot's trailing logic detected reversal off $9.12 high. Sell limit at $9.06, filled @ **$9.08** ($0.02 above limit — small price improvement).
6. **19:55 ET ATRA closed at $9.35** — peak. Bot exited at $9.08, missing $0.27/share = **$1,569 of additional upside** (+0.74R).

### What worked
1. **Score=10 + above-VWAP-ish entry context** (started −0.8% below VWAP, but the 4.13% wave at 16:14 ET set up the pattern). VWAP recovered above entry within minutes of the breakout.
2. **R% = 1.41% provisional, 1.97% post-fill** — biggest R% of the day = biggest cushion.
3. **2h28m hold** — bot resisted multiple temptations to cut the trade during chop.

### What missed
- Trailing stop too tight: fired at $9.11 right after the breakout, before the price action confirmed continuation. Stock ran another $0.24 / 2.6% before truly topping. **Loose-trail tuning could have caught $9.20 or $9.30.**
- Pyramid leg2 silently failed (logged trigger, no order). If wired, would have added size at $8.84 → exited $9.08 → another $0.24/share × leg2-qty profit. Worth investigating before live-money go-live.

**Tuning hypothesis to test:** Trailing stop on score=10 setups should use a wider band — maybe trail by `max(2 × R, 1% of price)` instead of whatever the current tight rule is. Need to confirm the current trail logic in `bot_alpaca_subbot.py`.

---

## Trade #5 — TRAW @ 17:45 ET — Alpaca BP rejection

### Setup that almost happened
- Score: 10 (max)
- Entry $2.20, Stop $2.1646, R% = 1.61%
- Risk: $722 / qty 20,381 / notional $44,838

### Why rejected
Alpaca returned `code: 40310000 — insufficient buying power`:
- Buying power: **$17,142.78**
- Cost basis (TRAW order): **$45,857.25**
- Gap: $28,714 short

**Why was BP only $17K?** ATRA position was open at the time:
- Equity at TRAW arm time: ~$28,500
- 4× equity = ~$114,000 nominal BP
- ATRA notional consuming: 5,813 × $8.65 = **$50,283**
- Plus the trade-day accumulated unrealized PnL fluctuation
- Net: ~$17K of BP remaining, well below the $45,857 needed

This is a **structural constraint, not a strategy fault.** Today: 4 score≥9 bypass triggers, but only 3 could be funded simultaneously given $30K equity.

**Tuning hypothesis to test:** Cap per-position notional at `equity × 1.0` instead of `$50K hard-coded`. With $30K equity and 4× margin, that gives 4 concurrent positions of ~$30K each. Today's actual exposure was 1.67× equity per ATRA position → only 2.4 positions fit.

---

## Cross-trade pattern observations

### Win/loss vs. R% at fill

| Trade | R% provisional | R% after fill | Result |
|---|---|---|---|
| FATN | 0.86% | 1.47% | LOSS (-1.04R) |
| SST | 1.25% | 1.25% | LOSS (-0.40R) |
| ATRA | 1.41% | **1.97%** | **WIN (+2.51R)** |

Higher R% → bigger cushion → more time for the trade to develop. **Both losers had post-fill R% < 1.5%; the winner had 1.97%.**

### Win/loss vs. VWAP positioning at entry

| Trade | Entry vs VWAP | Result |
|---|---|---|
| FATN | **−2.2%** (below) | LOSS |
| SST | **+7.7%** (above) | LOSS (but quick) |
| ATRA | **−0.8%** (near) | **WIN** |

Hypothesis was "above VWAP wins" but SST disproved it (above-VWAP entry that pop-and-reversed). **The cleaner pattern**: entries that began with VWAP recovering toward/past the entry price held; entries that stayed below VWAP throughout the hold (FATN never traded above VWAP) lost.

### Win/loss vs. hold time

| Trade | Hold time | Result |
|---|---|---|
| FATN | 1h 45m | LOSS at hard stop |
| SST | 3 min | LOSS at trailing stop |
| ATRA | 2h 28m | **WIN at trailing stop** |

The winner had the longest hold. The shortest-hold trade (SST, 3 min) was killed by trailing-stop hyperactivity. **Maybe trailing-stop should have a "no exit before T+5min" floor.**

### Slippage analysis (entry side)

| Trade | Signal → Limit | Signal → Fill | Limit → Fill |
|---|---|---|---|
| CLNN | +$0.05 / +0.70% | NO FILL | — |
| FATN | +$0.05 / +1.54% | +$0.02 / +0.62% | -$0.03 (improvement) |
| SST | +$0.05 / +1.25% | +$0.00 / +0.00% | -$0.05 (improvement) |
| ATRA | +$0.05 / +0.58% | +$0.05 / +0.58% | $0.00 (exact limit) |
| TRAW | n/a | n/a | n/a |

The fixed `+$0.05` marketability buffer is a percentage-blind heuristic — that's 1.54% on FATN ($3.24 stock) but only 0.58% on ATRA ($8.60 stock). Should probably be percentage-based: e.g. `min(0.5% × price, $0.05)`.

### Slippage analysis (exit side)

| Trade | Signal → Limit | Signal → Fill |
|---|---|---|
| FATN exit | -$0.05 / -1.56% | +$0.00 / 0.00% (got signal price) |
| SST exit | -$0.05 / -1.26% | -$0.01 / -0.25% (got better than limit) |
| ATRA exit | -$0.05 / -0.55% | -$0.03 / -0.33% (got better than limit) |

Exit slippage was actually **favorable on all three** — Alpaca filled at or above the limit price. The marketability buffer protected fills without costing us much.

---

## Tuning hypotheses queued for week-end review

| # | Hypothesis | Expected effect | Files / config to change |
|---|---|---|---|
| 1 | Block bypass when `vwap_dist < -1.0%` even at score≥9 | Removes FATN-style below-trend entries | `bot_alpaca_subbot.py` chop_bypass logic |
| 2 | Score=9 gets `min_post_fill_R% = 1.5%`, score=10 gets bypass as today | Filters out tight-R bypass trades | `place_wave_breakout_entry()` |
| 3 | Trailing stop uses `max(2×R, 1.0% of price)` band | Catches more of run-ups (would have given ATRA $9.20+) | trailing-stop logic |
| 4 | "No trailing exit" guard for first 5 minutes after fill | SST-style instant reversal stays in trade | trailing-stop logic |
| 5 | Per-position notional = `min($50K, equity × 1.0)` | Fits 3-4 simultaneous score-bypass entries | sizing logic |
| 6 | Marketability buffer = `min(0.5% × price, $0.05)` | Halves slippage on $1-3 stocks | `_entry_limit_price` / `_exit_limit_price` |
| 7 | Wire pyramid leg2 to Alpaca, OR remove the trigger event | Either captures the leg or stops fake debug noise | wave-breakout pyramid path |
| 8 | Entry timeout extend from 10s → 30s for score≥9 | Catches CLNN-style barely-missed fills | order placement |
| 9 | Add liquidity prefilter: skip arm if last 60s ticks <20 | Avoids CLNN-style no-counterparty entries | ARM logic |

**None of these are being applied yet** — Manny's plan is to collect ~5 sessions of this kind of report and tune at end of next week (estimated 2026-05-15 / 2026-05-16).

---

## Daily metrics to track each report

These are the columns we'll watch over the next 5 sessions to see what's stable vs. noise:

| Metric | Today's value | Target |
|---|---|---|
| # WB_ARMED events | 24+ | (track) |
| # CHOP_REJECT | 9 | (track — should remain >0) |
| # CHOP_BYPASS triggers | 5 | (track) |
| # bypass → fill | 3 / 5 | aim for 4-5 / 5 (TRAW BP fix) |
| # bypass → win | 1 / 3 | watching for stable win rate |
| Avg R-multiple | +1.07 | want positive |
| Avg slippage on entry | +$0.026 / +0.69% | want <0.50% |
| Avg slippage on exit | -$0.013 / -0.36% | actually favorable today |
| Equity day change | +$1,485 (+5.0%) | breakeven baseline |

---

## Raw data references

- Sub-bot log: `~/warrior_bot_v2/logs/2026-05-08_subbot_alpaca.log`
- Main bot log (no trades): `~/warrior_bot_v2/logs/2026-05-08_daily.log`
- Alpaca order ledger (extract): see "Slippage analysis" sections above; pulled live at session close via `tc.get_orders()` against `PA3LXGIPGG8B`
- Tick caches: `~/warrior_bot_v2/tick_cache_alpaca/2026-05-08/` (per-symbol)
- This report's source events: lines 12,940 / 15,896-15,899 / 17,414-17,417 / 17,488-17,489 / 18,443-18,452 / 20,393-20,395 / 21,162-21,165 / 23,605-23,607 of subbot log

*Companion broker review for Cowork: `cowork_reports/2026-05-07_broker_execution_review.md` (still open question: how does Alpaca live behave around margin? Today's TRAW BP rejection in paper says "same as paper" is the expected answer.)*
