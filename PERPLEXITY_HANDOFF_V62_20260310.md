# Perplexity Handoff — V6.2 Expanded Backtest Results
**Date:** 2026-03-10
**Prepared by:** Duffy
**For:** Next research session / directive

---

## Current State of the System (V6.2)

All changes are on branch `v6-dynamic-sizing`. The current bot uses:

| Component | Status | Detail |
|-----------|--------|--------|
| V4 tier system | ✅ Active | SQS 7-9=Shelved $250, 5-6=A $750, 4=B $250, 0-3=Skip |
| V6.1 toxic filters | ✅ Active | Filter 1 hard block, Filter 2 half-risk |
| V6.2 Profile B risk cap | ✅ Active | Profile B max $250 regardless of SQS |
| V6 dynamic sizing | ✅ Coded, OFF by default | WB_DYNAMIC_SIZING_ENABLED=0 |

---

## What Was Tested — Two Data Windows

### Window 1: Oct 2025–Feb 2026 (102 days) — V6.2 Results
| Metric | Value |
|--------|-------|
| Total P&L | **+$7,955** (estimated with B cap) |
| Profile A P&L | +$7,885 |
| Profile B P&L | **~+$70** (was -$2,460 before cap) |
| Win Rate | 46.4% |
| Max Drawdown | **~-$3,073 (~9.9%)** (was -$5,355) |
| Equity: $30K → | **~$37,955** |

### Window 2: Jan–Aug 2025 (158 days) — NEW DATA
| Metric | Value |
|--------|-------|
| Total P&L | **-$4,824** |
| Profile A P&L | -$6,218 |
| Profile B P&L | **+$1,394** (2W/1L, 66.7% WR) |
| Win Rate | 26.7% (8W/22L on 30 active trades) |
| Cold Market Skips | **52 days** (~33% of all days) |
| Max Drawdown | Unknown (not computed) |
| Profitable Days | 8/65 |

---

## Key Finding #1 — Profile B Filter Width Problem

**The sample size problem is confirmed.** Across 14 months of data (Jan 2025–Feb 2026, 260 trading days), Profile B had:

| Window | B Sims | B Active Trades | B P&L |
|--------|--------|----------------|-------|
| Oct 2025–Feb 2026 | 16 | 2 active | +$70 |
| Jan–Aug 2025 | 10 | 3 active | +$1,394 |
| **Combined** | **26** | **5 active** | **+$1,464** |

**5 active trades in 14 months is not enough to make any tuning decisions.** The funnel analysis shows why:

| Filter Stage | Jan-Aug Count |
|-------------|---------------|
| Scanner B candidates (float 5-10M) | 644 |
| Pass price + gap + PM vol | 173 |
| Survive SQS + B-gate | 31 |
| Actually simulate | 10 |
| Active trades (P&L ≠ $0) | 3 |

**The B-gate (gap>=14% AND pm_vol>=10k) is blocking 79 out of 110 SQS=4 B candidates (~72%).** That's the primary bottleneck. The 5-10M float ceiling is also limiting the universe.

---

## Key Finding #2 — Jan-Aug 2025 Was a Fundamentally Different Market

Jan-Aug 2025 produced **-$4,824** on Profile A. This is NOT a system failure — it's a market regime issue:

| Month | P&L | Notable Event |
|-------|-----|---------------|
| Jan | -$910 | Slow start, 0 winners |
| Feb | +$278 | Small positive |
| Mar | -$839 | GV repeat loser (-$750 twice) |
| Apr | **-$1,665** | **Tariff shock (Apr 2-11)** — SOBR -$1,500 on Apr 8 |
| May | +$855 | AMST +$855 (only real winner) |
| Jun | **-$2,468** | Summer chop — 8 losses, 2 small wins |
| Jul | -$159 | Near flat |
| Aug | +$84 | Small positive |

**April 7-11 specifically:** The market was in freefall during the tariff shock. The bot correctly had the cold market gate skip 52 days total, but it still entered on several days that looked like valid setups and got chopped. No GWAV-type monster appeared to offset the losses.

**The cold market gate caught 52/158 days (33%) as skips** — this is a much higher skip rate than Oct-Feb (8/102 = 8%). Jan-Aug 2025 was much harder market conditions overall.

---

## Key Finding #3 — Profile A Win Rate vs Expected

Jan-Aug 2025 Profile A: **22.2% win rate** (6W/21L, -$6,218)

Compare to Oct-Feb 2026 Profile A: **~50% win rate** (12W/12L, +$7,885)

The same system, same rules, 28pp difference in win rate depending on market regime. This reinforces:
1. The system is GWAV-dependent (Jan-Aug had no GWAV equivalent)
2. Win rate varies dramatically by market conditions
3. Hot months (Jan/Feb 2026) rescue the system; cold months drag it down

Without a monster trade in Jan-Aug 2025, the -$4,824 is essentially the base drag from being in the market during a tough period.

---

## What Needs to Be Answered (Questions for Perplexity)

### Q1: Should we widen Profile B filters?
The directive specified: if <6 B trades → widen filters. We have 5 across 14 months.

Proposed widening options (needs Perplexity analysis):
- Float ceiling: 10M → 15M shares
- Gap cap: 25% → 35%
- Max per day: 2 → 3
- B-gate adjustment: gap>=14% AND pm_vol>=10k → maybe pm_vol>=5k?

**Risk:** Widening may introduce the same Tier A problem that V6.1 saw (CRWG/IONZ at $750). All B trades must remain capped at $250.

### Q2: Is the cold market gate too aggressive for Jan-Aug 2025?
52 skips out of 158 days = 33% skip rate. That's high. But 2025 was a genuinely cold/choppy year for small caps. 

**Key question:** How many of those 52 skipped days would have been profitable vs losing? We don't know because the sims weren't run on those days. A retrospective analysis of the "would-have-traded" candidates on cold-skipped days would tell us if the gate is correctly calibrated or if it's over-filtering.

### Q3: How do we handle regime detection?
Jan-Aug 2025 (-$4,824) vs Oct-Feb 2026 (+$7,955) is an extreme divergence. The bot performs very differently across regimes. 

Options:
- Accept it as inherent market variance (the 14-month average is still positive once combined)
- Build a pre-market "market regime" check beyond the cold market gate
- Use a trailing-loss window to reduce position sizing during drawdown streaks

### Q4: What is the full 14-month combined P&L?
We need the Sep-Oct 2025 gap filled (30 dates still missing) to have the complete picture. The 6 PM cron tonight will fill those in and generate the unified full-year report.

**Preliminary estimate** (Jan-Aug 2025 + Oct-Feb 2026, excluding Sep 2025 gap):
- Jan-Aug: -$4,824
- Oct-Feb: +$7,955
- **Combined (14 months minus Sep): ~+$3,131**

This is still positive but much more modest than the Oct-Feb window alone would suggest.

---

## Completed Work — What's on GitHub

Branch `v6-dynamic-sizing`:

| Commit | What |
|--------|------|
| `d8138ce` | V6.2: Profile B risk cap ($250 max) |
| `34ae7ec` | V6.2 backtest report (CRWG + IONZ spot checks) |
| `0027407` | 154 scanner dates (Jan-Aug 2025 cached) |
| `b244108` | V6.1 Oct-Feb full re-run (+$5,425 net) |
| `b5b168a` | V6.1 toxic entry filters |
| `225ca4e` | V6 dynamic sizing |

Full report: `PROFILE_B_EXPANDED_BACKTEST_RESULTS.md`
V6.2 cap baseline: `PROFILE_B_RISK_CAP_BASELINE.md`

---

## Pending (Tonight's 6 PM MT Job)
- Scan + sim remaining Sep 2025 + Aug 18-30 2025 (~31 dates)
- Generate `FULL_YEAR_V62_REPORT.md` (Jan 2025–Feb 2026, ~287 days)
- Full-year equity curve on $30K

---

## Bottom Line for Perplexity

The system is profitable over the Oct-Feb window (+$7,955 V6.2) but negative over the Jan-Aug 2025 window (-$4,824). The 14-month combined is modestly positive (~+$3,131 excluding Sep).

**The two biggest levers remaining:**
1. **Profile B filter widening** — 5 active trades in 14 months is insufficient data. Need wider filters to build real sample size.
2. **Regime adaptation** — The system bleeds significantly in choppy/cold markets (Jun 2025 was brutal at -$2,468). Whether to address this via filter changes, pre-market regime scoring, or dynamic risk reduction is the key strategic question.

V5 exit optimization was tested and failed (GWAV was destroyed). V6 dynamic sizing is coded but off by default. The next meaningful lever is Profile B expansion.

---

*Prepared by Duffy — 2026-03-10*
