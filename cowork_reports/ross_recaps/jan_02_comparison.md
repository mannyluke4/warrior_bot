# Jan 2, 2025 — Ross vs Bot Comparison

## Scanner Overlap

| Ticker | Ross Scanner | Bot Scanner | Notes |
|--------|-------------|-------------|-------|
| AEI    | Yes         | Yes         | Bot ranked #1 (score 0.96). +114.7% gap, 3.86M float, 15M PM vol |
| OST    | Yes         | **No**      | Low float ~700K, no news — bot likely filtered out (no catalyst?) |
| SPCB   | Yes         | **No**      | Not in bot's scanner results |
| HOO    | Yes         | **No**      | Not in bot's scanner results |
| XPON   | Yes         | **No**      | The likely +$12K winner — not in bot's scanner at all |
| VSME   | No          | Yes         | Bot found at 08:00, +53.9% gap, 2.43M float |
| ORIS   | No          | Yes         | Bot found at 04:00, +76.5% gap, 0.2M float |
| KALA   | No          | Yes         | Bot found at 09:47, +12.7% gap, 7.66M float (Profile B) |

**Overlap: 1 of 5 Ross tickers (AEI only).** Bot found 3 tickers Ross didn't mention. Bot missed 4 of Ross's 5 tickers.

## Bot Trades on Jan 2

### Micro-Pullback Strategy (MP)
- **ORIS**: Entry 2.80 @ 08:42, exit 2.78 @ 08:44 → **-$107** (-0.1R)
  - Bearish engulfing exit, quick loss, $15K notional

### Squeeze Strategy (SQ)
- **ORIS trade 1**: Entry 3.04 @ 07:13, exit 2.92 @ 07:13 → **-$321** (-0.9R)
  - Parabolic trail exit, instant stop-out
- **ORIS trade 2**: Entry 3.04 @ 07:24, exit 3.08 @ 07:24 → **+$115** (+0.3R)
  - Parabolic trail exit, small winner

### Bot Daily Totals
- MP: **-$107**
- SQ: **-$206** (net of both ORIS trades)
- Combined: **-$313**

## Ross's Trades on Jan 2
- AEI: +$852
- OST (x2): -$3,000
- XPON (breaking news): +$12,000 (likely — confirmed from monthly summary)
- **Daily total: +$12,000** (per recap) / +$9,852 net from listed trades

## Key Comparison Points

### 1. The XPON Miss — Biggest Story of the Day
Ross's +$12K winner was almost certainly XPON (monthly summary confirms +$15K on XPON in Jan, with Jan 2 being the day). The bot **never saw XPON** — it didn't appear in scanner results at all. This was a mid-morning breaking news catalyst with a 100% squeeze on a low float stock. The bot's scanner likely didn't pick it up because:
- It may have appeared after the bot's rescan window
- It was news-driven rather than gap-driven (KALA was the only late addition at 09:47)
- Scanner found only 4 candidates total that day

**This is the single biggest edge gap on Jan 2.** Ross made $12K on a stock the bot didn't even know existed.

### 2. AEI — Both Saw It, Only Ross Traded It
Bot ranked AEI #1 with a 0.96 score — the highest-ranked ticker of the day. But the bot traded ORIS instead (ranked #3). Ross traded AEI at 7:00 AM for +$852. Questions:
- Why did the bot skip AEI (its own top pick) and trade ORIS?
- Possibly ORIS triggered first on the bot's entry criteria while AEI didn't fire a setup signal

### 3. ORIS — Bot Traded It, Ross Didn't
Bot went 1-for-3 on ORIS across both strategies for a net -$313. ORIS had a tiny float (0.2M) and 76.5% gap. Ross didn't mention ORIS at all. The bot found a setup the human ignored — and lost on it.

### 4. Conviction Sizing
Ross sized up heavily on XPON (full conviction on news + low float) and made $12K on that single trade. The bot uses flat $15-17.5K notional regardless of conviction. Even if the bot had seen XPON, it would have traded the same size as its losing ORIS trades.

### 5. "Know When to Stop" vs Always-On
Ross stopped trading after the XPON win, recognizing post-9:30 was lower quality (halt territory, pops and drops). The bot has no concept of quitting while ahead — it would keep scanning and potentially give back gains.

### 6. OST — Ross's Losing Trades
Ross lost $3K on OST (no news, low float momentum play). The bot never saw OST, so it avoided this loss. Sometimes the scanner's conservatism is protective.

## Summary Scorecard

| Metric | Ross | Bot (MP+SQ) |
|--------|------|-------------|
| Daily P&L | +$12,000 | -$313 |
| Trades taken | 4 | 3 |
| Win rate | 2/4 (50%) | 1/3 (33%) |
| Biggest winner | +$12,000 (XPON) | +$115 (ORIS) |
| Biggest loser | -$3,000 (OST) | -$321 (ORIS) |
| Scanner tickers | 5 | 4 |
| Overlap | 1 (AEI) | 1 (AEI) |

**Delta: -$12,313.** Almost entirely explained by the XPON miss. Without XPON, Ross would have been -$2,148 vs the bot's -$313, and the bot would have actually won the day.
