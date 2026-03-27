# Dynamic Notional Cap Simulation: $30K Start, All Strategies
## Generated 2026-03-19

Simulates the full Warrior Bot strategy (squeeze + MP) with a dynamic notional cap that
scales with account equity, compared to the static $50K cap baseline. The dynamic cap
stays $20K above the current account balance until hitting a $150K hard ceiling.

**Cap formula:** `notional_cap = min(equity + $20K, $150K)`

This means the bot can take progressively larger positions as the account grows, rather
than being artificially constrained at $50K once equity exceeds ~$64K.

---

## Head-to-Head Comparison

| Metric | Dynamic Cap | Static $50K Cap | Delta |
|--------|-------------|-----------------|-------|
| Starting Balance | $30,000 | $30,000 | — |
| **Ending Balance** | **$162,419** | **$135,764** | **+$26,655** |
| **Total P&L** | **+$132,419** | **+$105,764** | **+$26,655** |
| Total Return | +441.4% | +352.5% | +88.9pp |
| Peak Equity | $162,419 | $135,764 | +$26,655 |
| Max Drawdown | $7,219 (4.4%) | $5,205 (3.8%) | +$2,014 |
| Total Trades | 119 | 119 | 0 |
| Win Rate | 54% | 54% | 0pp |
| Profit Factor | 5.05 | 4.76 | +0.29 |
| Avg Win | $2,580 | $2,092 | +$488 |
| Avg Loss | $617 | $531 | +$86 |

The dynamic cap adds +$26,655 (25% more P&L) while only increasing max drawdown by
$2,014 — from 3.8% to 4.4% of peak. The profit factor actually improves from 4.76 to
5.05 because wins scale up more than losses (the biggest winners tend to run far beyond
the entry price, so larger positions capture disproportionately more).

---

## Monthly Breakdown — Dynamic Cap

| Month | Start Equity | End Equity | P&L | Return | Trades | WR | Cap Start | Cap End |
|-------|-------------|-----------|-----|--------|--------|-----|-----------|---------|
| 2025-09 | $30,000 | $54,459 | +$24,459 | +81.5% | 35 | 60% | $50,000 | $74,459 |
| 2025-10 | $54,459 | $73,223 | +$18,764 | +34.5% | 27 | 56% | $74,459 | $93,223 |
| 2025-11 | $73,223 | $72,065 | -$1,158 | -1.6% | 6 | 50% | $93,223 | $92,065 |
| 2025-12 | $72,065 | $74,357 | +$2,292 | +3.2% | 13 | 38% | $92,065 | $94,357 |
| 2026-01 | $74,357 | $141,968 | +$67,611 | +90.9% | 24 | 54% | $94,357 | **$150,000** |
| 2026-02 | $141,968 | $141,082 | -$886 | -0.6% | 7 | 43% | $150,000 | $150,000 |
| 2026-03 | $141,082 | $162,419 | +$21,337 | +15.1% | 7 | 57% | $150,000 | $150,000 |
| **TOTAL** | **$30,000** | **$162,419** | **+$132,419** | **+441.4%** | **119** | | | |

---

## Notional Cap Evolution

The cap starts at $50K (matching the static baseline at $30K equity) and grows organically:

| Phase | Date Range | Equity Range | Cap Range | Notes |
|-------|-----------|-------------|-----------|-------|
| Early growth | Sep 2–Sep 22 | $30K–$55K | $50K–$75K | Cap grows 1:1 with equity |
| Mid growth | Sep 22–Jan 14 | $55K–$91K | $75K–$111K | Cap well above static $50K |
| Acceleration | Jan 14–Jan 20 | $91K–$135K | $111K–$150K | VERO drives massive jump |
| **Hard cap hit** | **Jan 20** | **$135K** | **$150K** | Cap ceases to grow |
| At ceiling | Jan 20–Mar 19 | $135K–$162K | $150K fixed | All remaining trades at $150K max |

The $150K hard cap kicks in on January 20, 2026 when the VERO mega-trade pushes equity
to $134,586. From that point forward, the cap is fixed — but at 3x the static $50K cap,
allowing substantially larger positions on subsequent winners.

---

## Where the Extra $26,655 Comes From

The delta is concentrated in just two months — January and March 2026:

| Month | Dynamic P&L | Static P&L | Delta | Explanation |
|-------|-----------|----------|-------|-------------|
| Sep 2025 | +$24,459 | +$24,454 | +$5 | Caps identical early on |
| Oct 2025 | +$18,764 | +$18,763 | +$1 | Still minimal difference |
| Nov 2025 | -$1,158 | -$1,158 | $0 | Quiet month, no impact |
| Dec 2025 | +$2,292 | +$2,292 | $0 | Still minimal |
| **Jan 2026** | **+$67,611** | **+$54,779** | **+$12,832** | VERO/SLGB at higher cap |
| Feb 2026 | -$886 | -$790 | -$96 | Larger losses too |
| **Mar 2026** | **+$21,337** | **+$7,424** | **+$13,913** | ARTL at $150K cap vs $50K |

**Two trades drive almost all the delta:**

| Trade | Dynamic P&L | Static P&L | Delta | Why |
|-------|-----------|----------|-------|-----|
| ARTL (Mar 18, +13.9R SQ) | +$23,916 | +$9,671 | +$14,245 | $150K cap vs $50K → 2.5x larger position |
| VERO (Jan 16, +18.6R MP) | +$42,686 | +$31,144 | +$11,542 | $112K cap vs $50K → 2.2x larger position |
| All others combined | — | — | +$868 | Mostly wash |

---

## Top 15 Trades (Dynamic Cap)

| # | Date | Ticker | Strategy | R-Mult | P&L | Notional | Cap |
|---|------|--------|----------|--------|-----|----------|-----|
| 1 | 2026-01-16 | **VERO** | MP | +18.6R | **+$42,686** | $68,529 | $111,900 |
| 2 | 2026-03-18 | **ARTL** | Squeeze | +13.9R | **+$23,916** | $123,642 | $150,000 |
| 3 | 2026-01-14 | ROLR | MP | +6.5R | +$12,722 | $16,737 | $99,003 |
| 4 | 2025-10-20 | GNLN | Squeeze | +16.7R | +$12,079 | $41,847 | $78,019 |
| 5 | 2026-01-21 | SLGB | Squeeze | +6.4R | +$10,761 | $73,317 | $150,000 |
| 6 | 2026-01-14 | ROLR | Squeeze | +8.5R | +$7,557 | $51,511 | $91,446 |
| 7 | 2025-09-22 | AVX | Squeeze | +12.5R | +$7,465 | $42,874 | $67,677 |
| 8 | 2025-10-01 | AKAN | MP | +5.6R | +$3,821 | $19,164 | $74,459 |
| 9 | 2025-09-18 | MAMO | MP | +2.4R | +$2,636 | $25,186 | $63,940 |
| 10 | 2025-09-02 | SHFS | Squeeze | +6.7R | +$2,524 | $16,286 | $50,000 |
| 11 | 2025-09-09 | CWD | Squeeze | +19.9R | +$2,502 | $5,452 | $55,311 |
| 12 | 2025-12-12 | KPLT | MP | +1.1R | +$1,951 | $44,556 | $90,037 |
| 13 | 2025-12-29 | BNAI | Squeeze | +2.1R | +$1,888 | $24,775 | $91,169 |
| 14 | 2025-09-16 | APVO | Squeeze | +3.3R | +$1,754 | $15,480 | $62,515 |
| 15 | 2025-12-30 | AEHL | Squeeze | +1.9R | +$1,742 | $25,530 | $92,965 |

---

## Risk Analysis

| Risk Metric | Dynamic Cap | Static Cap | Assessment |
|-------------|-------------|------------|------------|
| Max Drawdown $ | $7,219 | $5,205 | +39% larger |
| Max Drawdown % | 4.4% | 3.8% | +0.6pp |
| Largest Loss | ~$2,900 | ~$1,500 | ~2x larger |
| Avg Loss | $617 | $531 | +16% |
| Worst Month | -$1,158 (Nov) | -$1,158 (Nov) | Identical |
| Profit Factor | 5.05 | 4.76 | Improved |

The dynamic cap increases risk modestly — max DD goes from 3.8% to 4.4%, and average
losses grow by $86. But the reward side grows much faster: average wins jump by $488.
The profit factor actually improves because the strategy's positive skew (fat-tail winners)
benefits disproportionately from larger position sizes.

---

## Key Observations

1. **+$26,655 extra P&L (+25%) for only +0.6pp more drawdown.** The risk/reward tradeoff
   is clearly favorable. The dynamic cap lets winners run bigger without proportionally
   increasing the downside.

2. **The $150K hard cap is binding from Jan 20 onward.** Once equity crosses ~$130K, the
   cap freezes at $150K. The March ARTL trade (+$23,916) shows the cap doing real work —
   without it, that trade would have been $180K+ notional.

3. **Almost all the delta comes from 2 trades.** VERO and ARTL together account for
   $25,787 of the $26,655 delta. This is expected — the dynamic cap only matters when
   both (a) the cap is significantly above $50K and (b) a monster winner occurs.

4. **Losses scale too, but less.** The largest loss in the dynamic sim is ~$2,900 vs
   ~$1,500 static. But since the account is much larger by that point, the percentage
   impact is similar.

5. **Sep-Oct 2025 is nearly identical** between the two sims because the cap doesn't
   diverge meaningfully until equity passes ~$50K (at which point dynamic cap = $70K
   vs static $50K, but most positions are still under $50K notional anyway).

---

## Methodology

- All trades (squeeze + MP) from Sep 2025–Mar 2026 combined dataset
- Position sizing: 2.5% of equity per trade
- Dynamic cap: `min(equity + $20K, $150K)` — evaluated at start of each trade
- Static baseline: fixed $50K cap (same as prior continuous equity run)
- P&L rescaled from original $30K-start backtest proportionally
- Both sims use identical trade selection (same 119 trades), only position sizes differ
