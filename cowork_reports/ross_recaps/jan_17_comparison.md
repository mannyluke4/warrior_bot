# Jan 17, 2025 — Ross vs Bot Comparison

## Day Context
- Friday before 3-day weekend (MLK Monday + Inauguration Tuesday)
- Ross traded defensively, conservative size, fewer than 10 trades
- Ross P&L: ~$4,864 (5th consecutive green day)

## Scanner Overlap

### Ross's Full Scanner List (11 tickers)
NUKK, VSS, ZEO, BCAI, XCUR, LAES, INTC, ZO, AIMX, BTCT, BDMD

### Bot's Scanner Results (4 tickers)
| Symbol | Gap% | PM Price | Float | Profile | Discovered |
|--------|------|----------|-------|---------|------------|
| VS | +70.8% | $3.28 | 1.76M | A | 04:00 |
| ZEO | +72.7% | $4.04 | N/A | X | 06:32 |
| ISPC | +28.1% | $3.65 | 9.77M | B | 04:00 |
| BTCT | +26.7% | $6.03 | 7.18M | B | 08:24 |

### Overlap: 2 of 11 Ross tickers found by bot scanner
- **ZEO** — Bot found (Profile X, no float data). Ross saw it but avoided it (sector strength, no catalyst, prior pop-and-drops). Correct pass by both.
- **BTCT** — Bot found (Profile B, 7.18M float). Ross traded it for small profit (squeeze $5→$7.50, dip buy, bounced to $7.20).

### Bot found but NOT on Ross's radar: 2 tickers
- **VS** — +70.8% gap, 1.76M float, Profile A, rank #1. Not mentioned by Ross at all.
- **ISPC** — +28.1% gap, 9.77M float, Profile B, rank #2. Not mentioned by Ross at all.

### Ross had but bot missed: 9 tickers
- **ZO** — Ross's best trade, VWAP reclaim + range trading $3.82-$4.20, bulk of ~$4,864 profit
- **AIMX** — Net +$1,200, news catalyst, low float, dip buy $3.50→$4.00
- **NUKK** — Up 73%, $36-38, 1M float, avoided (wide spreads, weak catalyst)
- **VSS** — Avoided (below VWAP all morning)
- **BCAI** — Avoided (pop-and-drop history)
- **XCUR** — Avoided (pop-and-drop history)
- **LAES** — Avoided (pop-and-drop history)
- **INTC** — Avoided (large cap, no retail edge)
- **BDMD** — On scanner only, not traded

## Bot Trade Activity

### Megatest Selection (both MP and SQ identical)
- Selected: VS (#1, rank 0.952), ISPC (#2, rank 0.613), BTCT (#3, rank 0.443)
- **Trades executed: 0** across both MP and SQ strategies
- No missed_opportunities logged for this date

### Bot P&L: $0.00

## Ross's Trades vs Bot

| Ticker | Ross Result | Bot Scanner? | Bot Traded? | Bot Result |
|--------|-------------|-------------|-------------|------------|
| ZO | Bulk of ~$4,864 (best trade) | NO | N/A | $0 |
| AIMX | +$1,200 net | NO | N/A | $0 |
| BTCT | Small profit | YES (rank #3) | NO | $0 |

## Key Findings

### 1. Scanner Miss on ZO — Biggest Gap
ZO was Ross's best trade of the day (VWAP reclaim, range trading $3.82-$4.20, 4-5 re-entries). The bot scanner completely missed it. This is the largest single missed opportunity for Jan 17. Need to investigate why ZO didn't appear — likely didn't meet gap% or volume thresholds at scan time.

### 2. Scanner Miss on AIMX — News Catalyst
AIMX had real news catalyst at 8 AM, low float. Bot's scanner missed it entirely. Ross made +$1,200 net despite first trade stopping out. This is a mid-morning news-driven discovery the scanner's continuous rescan should theoretically catch.

### 3. BTCT Found but Not Traded
The bot correctly identified BTCT (rank #3) but took zero trades. Ross made a small profit on it. The bot found the right stock but failed to generate a trade signal. Worth investigating whether price action met entry criteria.

### 4. VS and ISPC — Bot-Only Tickers
The bot's top two selections (VS and ISPC) didn't even appear on Ross's radar. This suggests the bot's scanner criteria may be finding different types of stocks than Ross focuses on — or Ross had reasons to pass that aren't captured in the recap.

### 5. Zero Bot Trades on a $4,864 Ross Day
Despite having 3 stocks selected and ready, the bot generated zero trades. On a day Ross explicitly described as "trading on defense" with conservative sizing, the bot was even more defensive — it was completely idle. This pattern of 0-trade days continues to be the bot's biggest issue.

## Scanner Gap Analysis
- Bot scanner found 4 tickers total, Ross mentioned 11
- Only 2/11 (18%) of Ross's tickers were found by the bot
- The bot's two unique finds (VS, ISPC) were not part of Ross's universe at all
- Of Ross's 3 actual trades, the bot found only 1 (BTCT) and missed the 2 most profitable (ZO, AIMX)
- Scanner miss rate on Ross's traded tickers: 2/3 (67%)
