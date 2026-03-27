# Jan 15, 2025 — Ross vs Bot Comparison

## Summary
- **Ross P&L:** +$4,977.63
- **Bot P&L:** $0 (no trades taken)
- **Gap:** -$4,977.63

## Bot Scanner Results (3 tickers found)

| Ticker | Gap% | PM Price | Float | Profile | Discovery | PM Volume |
|--------|------|----------|-------|---------|-----------|-----------|
| BKYI | +65.7% | $2.27 | 9.6M | B | 08:07 | 27.8M |
| RENX | +16.0% | $2.83 | N/A | X | 04:26 | 7.8M |
| MGIH | +39.7% | $2.50 | 1.25M | A | 05:50 | 10.0M |

## Ross's Scanner Tickers (10 total)
OSTX, EVAX, XXI, SGBX, BKYI, QBTS, VMAR, MASS, COMP, LAES

## Cross-Reference: Overlap

### Scanner found + Ross saw
- **BKYI** — Bot scanner found it (Profile B, 9.6M float, +65.7% gap). Ross also saw it but **passed** (negative prior experience, pop-and-reverse history). Neither bot nor Ross traded it profitably — Ross's decision to pass was vindicated by the pop-and-reverse pattern.

### Scanner found + Ross did NOT mention
- **RENX** — Profile X (no float data), bot could not trade. Not on Ross's radar.
- **MGIH** — Profile A (1.25M float), bot found it but took 0 trades. Not mentioned by Ross.

## What the Bot Missed

### Stocks Ross traded that the bot's scanner missed entirely

| Ticker | Ross P&L | Setup | Why Scanner Likely Missed |
|--------|----------|-------|--------------------------|
| OSTX | ~+$3,000+ | News squeeze | Phase 2 clinical trial news at 7:41 AM, $4→$8.50 spike, 17M float — may not have met gap% or PM volume threshold at scan time |
| EVAX | Small profit | Momentum scalp | Quick pop to $5.40, partial fill only — likely didn't meet scanner thresholds |
| XXI | +$730 | Dip buy (recurring) | Recurring name with recycled headlines, $7.70→$9.20 — may not have gapped enough |
| SGBX | Small winner | Gap-and-go attempt | Open-bell attempt, fizzled — likely marginal scanner candidate |

### Stocks on Ross's watchlist the bot missed
- QBTS, VMAR, MASS, COMP, LAES — all on Ross's scanner but not traded by Ross either

## Bot Trades on Stocks Ross Didn't Trade
None — the bot took 0 trades on Jan 15 across both MP and SQ strategies.

## Key Takeaways

1. **Complete scanner miss on all 4 Ross trades.** The bot found only BKYI from Ross's 10-ticker watchlist, and BKYI was the one stock Ross deliberately passed on. The bot's 3 scanner results (BKYI, RENX, MGIH) had zero overlap with Ross's actual trades.

2. **Zero bot trades.** Despite finding 3 candidates, the bot executed 0 trades. RENX was Profile X (unreadable). MGIH was Profile A but generated no trade signals. BKYI was Profile B but also no trades triggered.

3. **OSTX was the biggest miss.** Ross's biggest winner (~$3,000+) came from a 7:41 AM Phase 2 clinical trial catalyst. The stock went $4→$8.50. This is exactly the kind of news-driven squeeze the bot should catch.

4. **Macro headwind context.** Ross noted CPI below expectations caused S&P to gap up, which paradoxically hurt small-cap momentum by dispersing buyer attention. This may partly explain the thin scanner results — fewer small caps were moving with conviction.

5. **Bot found 3 tickers, Ross found 10.** The scanner coverage gap remains significant. Ross's broader watchlist surface area gives him access to opportunities the bot never sees.
