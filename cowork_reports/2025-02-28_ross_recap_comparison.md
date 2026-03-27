# CC Report: Ross Recap Comparison — 2025-02-28
## Date: 2025-02-28 (analyzed 2026-03-20)
## Status: COMPLETE

---

### Side-by-Side Summary

| Metric | Ross (Live) | Bot (Backtest) |
|--------|-------------|----------------|
| Stocks traded | 3–4 (BTII, ZOZ, NVVE, +1 small scalp) | 0 trades |
| Total P&L | **+$23,931.91** | **$0** |
| Scanner overlap | — | 2 of 3 main stocks found (ZOZ, NVVE) |
| Scanner miss | — | BTII (compliance/reverse split play) |
| Account context | — | $24.2K, mid 5-day losing streak |

Ross had a monster day. The bot would have had $0 even if it was running — micro pullback was the only strategy at the time, and neither ZOZ nor NVVE set up for MP. Squeeze V2 didn't exist yet.

---

### Ross's Trades

**1. BTII — +~$1,500 (Curl/Pullback-to-Support)**
- Hit Ross's scanner at **7:00 AM ET**. NASDAQ compliance regained after reverse split.
- Popped from $2.00 to $2.30, pulled back, curled back up at 7:30.
- Entry: pullback-to-support around $2.00. Rode to $2.40–2.60 (25% in 2 min).
- Strategy: 10-second chart, quick profit-take on curl pattern.
- **Bot scanner**: DID NOT FIND. See §Scanner Miss Analysis below.

**2. ZOZ — +~$10,000 (Pure Momentum / No Catalyst)**
- Hit Ross's scanner at **8:30 AM ET**. Up 40–50%, no clear catalyst.
- Hotkeyed in at $2.38, added at $3.40 and $3.55 on strength.
- Stock later round-tripped to $1.95 — Ross recognized this as market cycle cooling signal.
- Strategy: momentum chase with aggressive adds. No setup pattern — pure scanner-strength play.
- **Bot scanner**: FOUND as ZOOZ at **8:27 AM** (3 min BEFORE Ross). Gap +67.5%, $2.58, 8.0M float, RVOL 183x.
- **Bot trades**: 0. MP didn't trigger. Squeeze V2 would likely have entered on the volume explosion through $2.50–3.00 levels.

**3. NVVE — +~$12,000+ (Breakout + Scalps)**
- Hit Ross's scanner at **~8:30 AM ET**. Real news, moved $2.80 to $4.40.
- Hesitated after ZOZ reversal, missed initial move. Scalped dips around $3.50.
- Then took 40,000 shares on breakout through resistance → $4.70.
- Stopped before the open (premarket only).
- **Bot scanner**: FOUND at **8:35 AM** (5 min AFTER Ross). Gap +66.2%, $3.99, 0.2M float, RVOL 14.6x.
- **Bot trades**: 0. MP didn't trigger. Ultra-low float (0.2M) + massive gap = prime squeeze territory.

**4. Unknown 4th Stock — small scalp**
- Ross went green on 4/4 stocks. Details not in recap.

---

### Scanner Miss Analysis: BTII

BTII was not found by our scanner. Multiple factors likely contributed:

**1. Timing gap (PRIMARY).** Ross found BTII at 7:00 AM. Our scanner's first pass uses 4:00–7:15 AM premarket bars. The first rescan checkpoint is 8:00 AM (covering the 7:15–8:00 window). If BTII's pop from $2.00 to $2.30 happened at/after 7:00, the 7:15 scan may have seen the stock before the move, and the 8:00 rescan may have caught it too late — the 25% move was already done by 7:32.

**2. Gap % uncertainty.** Ross says BTII "popped from $2.00 to $2.30." If prev_close was ~$2.00 (post reverse split), a premarket price of $2.30 = 15% gap, which passes the 10% threshold. But reverse splits create data issues — the prev_close in Databento may reflect the pre-split price, making the gap calculation unreliable. If prev_close was already $2.00+ (compliance threshold) and the stock was at $2.05 at 7:15, that's only a 2.5% gap = filtered out.

**3. Reverse split data quality.** Compliance-regain plays after reverse splits are inherently tricky for gap scanners. The "catalyst" is the compliance news, not a price gap. Our scanner is gap-first; Ross's scanner may have a news/compliance filter we don't have.

**Diagnosis**: Most likely a combination of timing (7:00 AM move, scanner doesn't run until 7:15) and gap threshold (move may not have been large enough at scan time). This is NOT a parameter tuning fix — it's a scan architecture gap. A streaming/real-time mode or earlier first scan would help.

---

### Scanner Performance: Discovery Timing

| Stock | Ross Found | Bot Found | Delta | Notes |
|-------|------------|-----------|-------|-------|
| BTII | 7:00 AM | NOT FOUND | — | Pre-7:15 move, reverse split data issues |
| ZOZ/ZOOZ | 8:30 AM | **8:27 AM** | **+3 min** | Bot found it FIRST. Same stock, ticker format difference (ZOZ vs ZOOZ). |
| NVVE | ~8:30 AM | 8:35 AM | -5 min | Bot 5 min late. Both found in same scan window. |

The bot matched or beat Ross's discovery timing on the two stocks it found. The miss was a stock the bot structurally couldn't find (pre-7:15 move + reverse split edge case).

---

### Strategy Gap Analysis

| Ross's Trade | Ross's Strategy | Bot Strategy Match | Gap |
|---|---|---|---|
| BTII curl at $2.00 | Pullback-to-support / curl | **Strategy 5 (Curl/Extension)** — NOT BUILT | Bot has no curl detector. This is the 4th data point for Strategy 5 (after ARTL 3/18, CHNR 3/19, ARTL 3/20). |
| ZOZ momentum | Hotkey-in + adds on strength | **Squeeze V2** — would likely enter on volume explosion. Adds = architectural gap. | Bot can't add on strength. Fixed position sizing. |
| NVVE breakout | Breakout through resistance + scalps | **Squeeze V2** — breakout entry. Scalps = re-entry gap. | Bot can't scalp dips. No re-entry after exit. |
| ZOZ + NVVE sizing | 40K shares, aggressive adds | N/A | Ross's sizing on conviction plays ($10K+ on ZOZ) is 5–10x what the bot would take with probe sizing. |

**Key insight**: Even with squeeze V2 available, the bot would have captured a fraction of Ross's $23.9K day. The gaps are the same ones identified in the ARTL 3/20 comparison: no adds on strength, no re-entry/scalping, no curl detector, and conservative fixed sizing vs Ross's conviction-based scaling.

---

### What Would Squeeze V2 Have Done? (Estimated)

No backtest has been run (tick data may not be cached), but based on the stock profiles:

| Stock | Squeeze V2 Likelihood | Estimated Outcome | Reasoning |
|---|---|---|---|
| BTII | LOW | $0 | Scanner miss = no entry possible |
| ZOZ/ZOOZ | HIGH | +$500–1,500 | 67.5% gap, 183x RVOL, 8M float. Volume explosion through $2.50 would trigger squeeze. Probe sizing (0.5x) limits upside. 3 max attempts. |
| NVVE | HIGH | +$500–2,000 | 66.2% gap, 0.2M float (ultra-low). Breakout through $4.00 would trigger. Parabolic mode likely. |
| **Estimated total** | — | **+$1,000–3,500** | **4–15% of Ross's $23.9K** |

→ **Action**: Cache tick data for ZOOZ and NVVE on 2025-02-28 and run squeeze V2 backtest to get real numbers.

---

### BTII as Strategy 5 Evidence

Ross's BTII trade is another textbook curl/pullback-to-support:
- Stock pops (impulse), pulls back (consolidation), curls back up (rounded recovery), breaks through prior high.
- Entry at support ($2.00), ride the curl to $2.40–2.60.
- 10-second chart = extremely tight timeframe, quick profit-take.

This is now the **4th data point** for Strategy 5 (Curl/Extension):

| Date | Stock | Ross's Curl P&L | Notes |
|------|-------|-----------------|-------|
| 2025-02-28 | BTII | +$1,500 | Pullback-to-support after compliance pop |
| 2026-03-18 | ARTL | Best trade | Gradual recovery into prior HOD |
| 2026-03-19 | CHNR | +$2,000 | Curl from $5.00 support → squeeze to $6.00 |
| 2026-03-20 | ARTL | +$6,100 | Pullback and curl through HOD at 8.37 |

---

### Bottom Line

Ross: +$23,932 on 3–4 stocks (momentum, adds, scalps, conviction sizing, curl entry)
Bot: $0 (scanner found 2/3 but MP-only strategy had no entries)
Bot w/ squeeze V2 (est.): +$1,000–3,500 (4–15% of Ross)

The $20K+ gap is not a scanner problem — the scanner actually found ZOZ 3 minutes before Ross. It's a strategy and execution gap: no curl detector, no adds on strength, no re-entry/scalping, no conviction sizing. These are the same gaps identified in every Ross comparison so far.

---

### Next Steps

- [ ] Cache tick data for ZOOZ and NVVE 2025-02-28
- [ ] Run squeeze V2 backtest on both stocks
- [ ] Update this report with actual (not estimated) squeeze V2 results
- [ ] Log BTII miss in `scanner_refinements.md` (done)

---

*See `scanner_refinements.md` for the running cross-day analysis.*
