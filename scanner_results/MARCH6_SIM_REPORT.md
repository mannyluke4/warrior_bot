# March 6, 2026 — Scanner Simulation Report
**Reconstructed post-mortem** — launchd plist was never installed, autonomous morning routine did not run.

---

## Scanner Output

- **Date**: 2026-03-06 (Friday)
- **Data source**: Alpaca (pre-market OHLCV bars, 4:00–7:15 AM ET)
- **Raw candidates** (gap ≥10%, price $2–$20): 38 symbols
- **After float lookup**: 34 classified (4 skipped >50M float)
- **Time window filter**: 7:00–7:14 AM ET (scanner window)

---

## Profile Assignment — All 34 Candidates

| Ticker | Float | PM Price | Gap% | Scanner Profile | Live Filter Result |
|--------|-------|----------|------|-----------------|-------------------|
| VCIG   | 0.11M | $4.83 | +26.9% | A | **SKIP** — float <0.5M |
| TMDE   | 3.56M | $3.56 | +26.6% | A | **TRADE** Profile A ✅ |
| OWLT   | 9.70M | $9.18 | +25.8% | B | **SKIP** — gap >25% (B cap) |
| FTCI   | 10.35M | $5.31 | +23.5% | B | **TRADE** Profile B ✅ (top 1) |
| TURB   | 1.29M | $4.13 | +23.1% | A | **TRADE** Profile A ✅ |
| ALOY   | 3.14M | $19.90 | +22.5% | A | **SKIP** — price >$10 |
| SBTU   | unknown | $5.01 | +18.6% | X | **SKIP** — Profile X |
| OPRX   | 14.37M | $7.92 | +18.2% | B | **TRADE** Profile B ✅ (top 2) |
| PLUL   | unknown | $12.86 | +15.3% | X | **SKIP** — Profile X |
| RBNE   | 2.68M | $2.98 | +14.6% | A | **SKIP** — price <$3 |
| ANNA   | 9.39M | $4.27 | +13.9% | B | **SKIP** — B cap at top 2 |
| RIOX   | 1.08M | $8.14 | +13.9% | A | **TRADE** Profile A ✅ |
| SHMD   | 13.93M | $6.80 | +13.7% | B | **SKIP** — B cap at top 2 |
| GLXU   | unknown | $8.00 | +13.6% | X | **SKIP** — Profile X |
| PMTS   | 6.00M | $18.47 | +13.6% | B | **SKIP** — price >$10 |
| CIFG   | 0.24M | $7.22 | +13.5% | A | **SKIP** — float <0.5M |
| NTRP   | 6.29M | $3.35 | +13.2% | B | **SKIP** — B cap at top 2 |
| USGG   | unknown | $13.50 | +13.0% | X | **SKIP** — Profile X |
| BAER   | 36.83M | $2.51 | +12.8% | B | **SKIP** — price <$3 |
| WOLF   | 28.23M | $18.86 | +12.8% | B | **SKIP** — price >$10 |
| GLGG   | 0.06M | $6.80 | +12.8% | A | **SKIP** — float <0.5M |
| MRAL   | 2.96M | $3.33 | +12.3% | A | **TRADE** Profile A ✅ |
| IBG    | 0.20M | $6.01 | +11.9% | A | **SKIP** — float <0.5M |
| VMET   | unknown | $12.39 | +11.8% | X | **SKIP** — Profile X |
| PTRN   | 32.35M | $12.40 | +11.8% | B | **SKIP** — price >$10 |
| OMDA   | 4.45M | $15.55 | +11.5% | A | **SKIP** — price >$10 |
| MARPS  | 1.51M | $5.86 | +11.4% | A | **TRADE** Profile A ✅ |
| RKLZ   | 0.16M | $3.44 | +11.4% | A | **SKIP** — float <0.5M |
| DJTU   | unknown | $2.27 | +11.1% | X | **SKIP** — Profile X |
| CNVS   | 17.91M | $3.30 | +11.0% | B | **SKIP** — B cap at top 2 |
| CRMX   | 0.60M | $6.60 | +10.6% | A | **TRADE** Profile A ✅ |
| TPET   | 7.59M | $2.12 | +10.5% | B | **SKIP** — price <$3 |
| CLSX   | unknown | $11.55 | +10.1% | X | **SKIP** — Profile X |
| NKLR   | 21.74M | $4.51 | +10.0% | B | **SKIP** — B cap at top 2 |

**Live watchlist would have been:**
```
TMDE:A
TURB:A
RIOX:A
MRAL:A
MARPS:A
CRMX:A
FTCI:B
OPRX:B
```

---

## Simulation Results

| Ticker | Profile | Data Source | Ticks | EMA9 | VWAP | Armed | Signals | P&L | Notes |
|--------|---------|-------------|-------|------|------|-------|---------|-----|-------|
| TMDE   | A | Alpaca | 25,471 | 3.09 | 3.42 | 0 | 0 | $0 | No setup formed |
| TURB   | A | Alpaca | 107,757 | 4.29 | 4.34 | 1 | 0 | $0 | Armed @ 08:02 → VWAP loss reset |
| RIOX   | A | Alpaca | 1,896 | 7.19 | 7.42 | 0 | 0 | $0 | Very thin volume |
| MRAL   | A | Alpaca | 2,134 | 3.05 | 3.15 | 0 | 0 | $0 | Classifier blocked @ 07:10 |
| MARPS  | A | Alpaca | 1,220 | 5.73 | 6.04 | 1 | 0 | $0 | Armed, no signal fired |
| CRMX   | A | Alpaca | 989 | 6.39 | 6.50 | 1 | 1 | $0 | Signal fired but classifier blocked @ 07:17 |
| FTCI   | B | Alpaca¹ | 2,089 | 4.44 | 4.67 | 0 | 0 | $0 | Classifier blocked @ 07:58; appeared at 7:11 ET |
| OPRX   | B | Alpaca¹ | 9,666 | 6.18 | 6.53 | 1 | 0 | $0 | Classifier blocked @ 07:13 |

¹ *Databento unavailable for same-day data (requires live license — error 403 license_not_found_unauthorized on XNAS.ITCH and XNYS.PILLAR). Profile B sims ran with Alpaca ticks and no L2.*

---

## Summary

- **Total P&L (Profile A)**: $0
- **Total P&L (Profile B)**: $0
- **Combined P&L**: **$0**
- **Stocks traded**: 0 of 8 candidates
- **Stocks skipped (Profile X / out-of-filter)**: 26 of 34

---

## Key Observations

### 1. Quiet/Choppy Friday — Classifier Blocked 4 of 8 Stocks
The classifier's AVOID gate fired on MRAL, CRMX, FTCI, and OPRX. All were blocked because:
- VWAP distance < 7% (stocks weren't running away from VWAP)
- Range < 10% intraday range
- New Highs count < 2 (weak follow-through)

This is exactly the behavior we want — the classifier is designed to keep the bot out of stocks that look good on a gap screen but aren't actually trending in session.

### 2. TURB Was the Most Interesting Setup
TURB had the highest volume (107,757 ticks), a score-12.0 setup that armed at 08:02:
- Entry: $5.05 | Stop: $4.74 | R: $0.31
- Signal detail: MACD(7.5)×0.6 + bull_struct + vol_surge + R2G + R≥0.08
- But then lost VWAP → full reset
- Post-reset max high in 5m: $5.02 — stock didn't recover above entry
- **Correct to not take this trade** — VWAP loss was a real failure of structure

### 3. CRMX Had a Signal But Was Blocked by Classifier
CRMX had both an armed setup (1) and a fired signal (1), but the classifier called AVOID at 07:17 (VWAP dist 3.2%, range 1.7%, NH=1). This prevented what would likely have been a losing trade — CRMX was near VWAP all session with no real momentum.

### 4. Databento Same-Day Data Limitation
Profile B simulation could not use Databento ticks for today's data. The standard historical plan requires a live license for data after 5:00 AM ET on the same day. **This is a known constraint for same-day post-mortems**. Re-running FTCI/OPRX tomorrow with Databento ticks will give the true Profile B result.

### 5. March 6 Was Simply a No-Trade Day
This is a valid outcome. The scanner found 8 qualified candidates but:
- Thin volume on most A stocks (RIOX 1,896 ticks, MARPS 1,220 ticks, CRMX 989 ticks)
- No clean impulse-pullback structures formed
- Classifier correctly identified choppy/mean-reverting conditions

**The bot not trading is NOT a failure. Staying flat on a quiet Friday is the right call.**

---

## Databento Profile B Re-Run (Recommended Tomorrow)

Run these with Databento once historical access unlocks (tomorrow or Monday):
```bash
python simulate.py FTCI 2026-03-06 07:00 12:00 --ticks --feed databento --profile B --no-fundamentals
python simulate.py OPRX 2026-03-06 07:00 12:00 --ticks --feed databento --profile B --no-fundamentals
```

---

*Report generated by Claude Code — 2026-03-06*
*Directive: MARCH6_SIM_DIRECTIVE.md*
