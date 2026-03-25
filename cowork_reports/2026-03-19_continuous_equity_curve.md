# Continuous Equity Curve: Sep 2025 → Mar 2026
## Generated 2026-03-19

Simulates a single account running the Warrior Bot strategy continuously from
September 2025 through March 2026. The Sep-Dec 2025 out-of-sample results feed
directly into Jan-Mar 2026 in-sample results, with position sizes rescaled to
reflect the compounded account balance.

---

## Headline Numbers

| Metric | Value |
|--------|-------|
| Starting Balance | $30,000 |
| Ending Balance | $134,163 |
| Total P&L | +$104,163 |
| Total Return | +347.2% |
| Peak Equity | $134,163 |
| Max Drawdown | $5,188 (3.9%) |
| Total Trades | 119 |
| Win Rate | 64/119 (54%) |
| Avg P&L/Trade | +$875 |

---

## Position Sizing

- Risk per trade: 2.5% of current equity
- Max notional: $50,000 (caps position size on large accounts)
- Daily loss limit: -$1,500
- Max 5 trades/day

The notional cap becomes binding once equity exceeds ~$64K (at which point
2.5% × equity > implied notional). Several Jan-Mar trades hit this cap,
which is why the rescaling factor is <1.0x for some large positions.

---

## Monthly Breakdown

| Month | Phase | Start Equity | End Equity | P&L | Return | Trades | Win Rate |
|-------|-------|-------------|-----------|-----|--------|--------|----------|
| 2025-09 | OOS | $30,000 | $54,069 | +$24,069 | +80.2% | 35 | 60% |
| 2025-10 | OOS | $54,069 | $72,753 | +$18,684 | +34.6% | 27 | 56% |
| 2025-11 | OOS | $72,753 | $71,602 | +$-1,151 | -1.6% | 6 | 50% |
| 2025-12 | OOS | $71,602 | $73,886 | +$2,284 | +3.2% | 13 | 38% |
| 2026-01 | IS | $73,886 | $127,487 | +$53,601 | +72.5% | 24 | 54% |
| 2026-02 | IS | $127,487 | $126,713 | +$-774 | -0.6% | 7 | 43% |
| 2026-03 | IS | $126,713 | $134,163 | +$7,450 | +5.9% | 7 | 57% |
| **TOTAL** | | **$30,000** | **$134,163** | **+$104,163** | **+347.2%** | **119** | **54%** |

---

## Quarter Breakdown

| Quarter | Phase | Trades | P&L | Equity Range |
|---------|-------|--------|-----|-------------|
| Q4 2025 | OOS (unseen data) | 81 | +$43,886 | $30,000 → $73,886 |
| Q1 2026 | IS (rescaled) | 38 | +$60,277 | $73,886 → $134,163 |

---

## Top 10 Rescaled In-Sample Trades (Jan-Mar 2026)

These are the original in-sample trades re-sized with the compounded OOS ending balance.

| Date | Ticker | Strategy | Time | Orig P&L | Scale | Rescaled P&L | R-Mult |
|------|--------|----------|------|----------|-------|-------------|--------|
| 2026-01-16 | VERO | MP | 07:14 | +$16,966 | 1.84x | +$31,144 | +18.6R |
| 2026-01-14 | ROLR | MP | 08:26 | +$4,634 | 2.50x | +$11,607 | +6.5R |
| 2026-03-18 | ARTL | Squeeze | 07:42 | +$9,512 | 1.02x | +$9,671 | +13.9R |
| 2026-01-21 | SLGB | Squeeze | 07:17 | +$4,277 | 1.72x | +$7,339 | +6.4R |
| 2026-01-14 | ROLR | Squeeze | 08:19 | +$3,044 | 2.41x | +$7,336 | +8.5R |
| 2026-01-30 | PMN | MP | 08:37 | +$507 | 2.26x | +$1,145 | +0.4R |
| 2026-01-26 | BATL | Squeeze | 07:02 | +$423 | 2.26x | +$955 | +3.4R |
| 2026-03-19 | SER | Squeeze | 09:31 | +$535 | 1.68x | +$901 | +0.7R |
| 2026-02-09 | UOKA | Squeeze | 09:36 | +$502 | 1.79x | +$899 | +0.7R |
| 2026-01-08 | ACON | Squeeze | 07:01 | +$553 | 1.22x | +$676 | +1.6R |

---

## Daily Equity Progression

| Date | Phase | Trades | Day P&L | Equity |
|------|-------|--------|---------|--------|
| 2025-09-02 | OOS | 3 | $+4,223 | $34,223 |
| 2025-09-03 | OOS | 2 | $+147 | $34,370 |
| 2025-09-04 | OOS | 2 | $-92 | $34,278 |
| 2025-09-05 | OOS | 2 | $+879 | $35,157 |
| 2025-09-09 | OOS | 5 | $+3,465 | $38,622 |
| 2025-09-10 | OOS | 2 | $+817 | $39,439 |
| 2025-09-11 | OOS | 2 | $+2,640 | $42,079 |
| 2025-09-12 | OOS | 3 | $+230 | $42,309 |
| 2025-09-15 | OOS | 2 | $-89 | $42,220 |
| 2025-09-16 | OOS | 3 | $+2,392 | $44,612 |
| 2025-09-17 | OOS | 1 | $-1,002 | $43,610 |
| 2025-09-18 | OOS | 1 | $+2,616 | $46,226 |
| 2025-09-19 | OOS | 1 | $+1,093 | $47,319 |
| 2025-09-22 | OOS | 2 | $+7,279 | $54,598 |
| 2025-09-24 | OOS | 2 | $-584 | $54,014 |
| 2025-09-26 | OOS | 1 | $-250 | $53,764 |
| 2025-09-29 | OOS | 1 | $+305 | $54,069 |
| 2025-10-01 | OOS | 2 | $+3,116 | $57,185 |
| 2025-10-06 | OOS | 1 | $+371 | $57,556 |
| 2025-10-07 | OOS | 1 | $-404 | $57,152 |
| 2025-10-13 | OOS | 2 | $-685 | $56,467 |
| 2025-10-14 | OOS | 1 | $+1,260 | $57,727 |
| 2025-10-15 | OOS | 5 | $-74 | $57,653 |
| 2025-10-20 | OOS | 1 | $+12,003 | $69,656 |
| 2025-10-21 | OOS | 2 | $-109 | $69,547 |
| 2025-10-23 | OOS | 1 | $+310 | $69,857 |
| 2025-10-27 | OOS | 3 | $+252 | $70,109 |
| 2025-10-28 | OOS | 3 | $+1,998 | $72,107 |
| 2025-10-29 | OOS | 2 | $-142 | $71,965 |
| 2025-10-31 | OOS | 3 | $+788 | $72,753 |
| 2025-11-06 | OOS | 1 | $+1,502 | $74,255 |
| 2025-11-10 | OOS | 1 | $+265 | $74,520 |
| 2025-11-11 | OOS | 1 | $+198 | $74,718 |
| 2025-11-12 | OOS | 1 | $-933 | $73,785 |
| 2025-11-18 | OOS | 1 | $-1,277 | $72,508 |
| 2025-11-21 | OOS | 1 | $-906 | $71,602 |
| 2025-12-01 | OOS | 1 | $-231 | $71,371 |
| 2025-12-03 | OOS | 1 | $-1,784 | $69,587 |
| 2025-12-09 | OOS | 1 | $+0 | $69,587 |
| 2025-12-12 | OOS | 1 | $+1,938 | $71,525 |
| 2025-12-16 | OOS | 1 | $+0 | $71,525 |
| 2025-12-18 | OOS | 1 | $+350 | $71,875 |
| 2025-12-23 | OOS | 1 | $-1,539 | $70,336 |
| 2025-12-24 | OOS | 1 | $+565 | $70,901 |
| 2025-12-29 | OOS | 3 | $+1,602 | $72,503 |
| 2025-12-30 | OOS | 1 | $+1,731 | $74,234 |
| 2025-12-31 | OOS | 1 | $-348 | $73,886 |
| 2026-01-02 | IS | 1 | $-1,538 | $72,348 |
| 2026-01-07 | IS | 1 | $-672 | $71,676 |
| 2026-01-08 | IS | 1 | $+676 | $72,352 |
| 2026-01-12 | IS | 1 | $-361 | $71,991 |
| 2026-01-13 | IS | 2 | $+93 | $72,084 |
| 2026-01-14 | IS | 2 | $+18,943 | $91,027 |
| 2026-01-15 | IS | 3 | $+177 | $91,204 |
| 2026-01-16 | IS | 1 | $+31,144 | $122,348 |
| 2026-01-20 | IS | 1 | $+345 | $122,693 |
| 2026-01-21 | IS | 2 | $+6,057 | $128,750 |
| 2026-01-22 | IS | 1 | $-986 | $127,764 |
| 2026-01-23 | IS | 2 | $-1,212 | $126,552 |
| 2026-01-26 | IS | 3 | $+1,648 | $128,200 |
| 2026-01-27 | IS | 2 | $-1,858 | $126,342 |
| 2026-01-30 | IS | 1 | $+1,145 | $127,487 |
| 2026-02-04 | IS | 1 | $-682 | $126,805 |
| 2026-02-06 | IS | 1 | $+221 | $127,026 |
| 2026-02-09 | IS | 1 | $+899 | $127,925 |
| 2026-02-17 | IS | 1 | $-498 | $127,427 |
| 2026-02-19 | IS | 1 | $-379 | $127,048 |
| 2026-02-20 | IS | 1 | $+123 | $127,171 |
| 2026-02-23 | IS | 1 | $-458 | $126,713 |
| 2026-03-06 | IS | 1 | $-1,483 | $125,230 |
| 2026-03-10 | IS | 1 | $-1,668 | $123,562 |
| 2026-03-12 | IS | 1 | $+43 | $123,605 |
| 2026-03-13 | IS | 1 | $+246 | $123,851 |
| 2026-03-18 | IS | 1 | $+9,671 | $133,522 |
| 2026-03-19 | IS | 2 | $+641 | $134,163 |

---

## Key Observations

1. **The strategy compounds aggressively.** Starting with $30K and reinvesting profits,
   the account reaches $134,163 in ~7 months — a 347% return.

2. **Max drawdown stays tiny.** Only $5,188 (3.9% of peak), meaning the strategy
   never gives back more than a few percent even with full compounding.

3. **The notional cap is doing real work.** Several Jan-Mar trades show scale factors
   well below the equity ratio because the $50K cap limits position size. This is a
   feature, not a bug — it prevents outsized losses on the larger account.

4. **VERO alone rescales to +$31K.** The monster 18.6R trade on Jan 16 was originally
   +$16,966 on a $30K account. With the compounded $73K+ balance, it becomes +$31,144.

5. **Nov-Dec was quiet but not damaging.** Only -$1,151 in November and +$2,284 in
   December — the bot correctly sat out low-opportunity periods rather than forcing trades.

## Methodology

- Sep-Dec 2025 trades replayed exactly as produced by the OOS runner (Config B, no VWAP gate)
- Jan-Mar 2026 trades rescaled proportionally: `new_pnl = orig_pnl × (current_equity / orig_equity_at_trade_time)`
- Notional cap of $50,000 applied after rescaling (some trades capped below the equity-based scale)
- Both phases use identical strategy config (squeeze + MP, classifier enabled)