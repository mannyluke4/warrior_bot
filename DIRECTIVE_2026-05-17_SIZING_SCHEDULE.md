# Sizing Schedule — From $300 Baseline to $2500 Target Risk

**Date:** 2026-05-17
**Author:** Cowork (Perplexity)
**For:** Manny + CC
**Trigger:** Manny: "Is this a permanent $300 risk across all trades? Or can it scale? We should gradually move to $2500 risk."
**Augments:** `DIRECTIVE_2026-05-17_FORENSIC_RESPONSE.md` §4

---

## TL;DR

$300 isn't a ceiling. It's the starting baseline for a scaling schedule that takes us to $2500 per signal — but tied to equity growth and stability metrics, not calendar time.

**At $25K equity, $300 per signal = 1.2% per trade.** This is healthy. **At $25K equity, $2500 per signal = 10% per trade.** This is account-killing on an 18.8% WR strategy.

**The right scaling: $2500 risk becomes appropriate when equity reaches ~$250K** — same 1% risk, larger absolute dollars. Until then, scaling per-tier in steps tied to equity milestones with drawdown protection.

---

## 1. Why $300 isn't a ceiling

The forensic-response directive specified $300 fixed-dollar risk for Wave 4 paper deployment. The reasoning was deployment safety, not strategic ceiling:

- **Half of $1K backtest test value** for DD safety margin
- **1.2% of $25K starting equity** — within "new strategy in paper" risk norms
- **Bounded portfolio risk** when 3 strategies run concurrently (max $900/session = 3.6%)

But **fixed-dollar sizing only makes sense at the starting equity tier.** As equity grows, $300 represents a smaller percentage of the account — under-utilizing the strategy's edge. The HalfKellySizer was supposed to handle scaling but has a bug that suppresses sizing 6-7× (Wave 5 P1 work).

**Scaling is architecturally supported and operationally desirable.** The question is what scaling schedule keeps us safe.

---

## 2. Why $2500 at $25K is wrong, and when it's right

### Per-trade risk as % of equity

| Equity | $300 risk = | $2500 risk = | Verdict at $2500 |
|---|---:|---:|---|
| $25K | 1.2% | 10% | **Account-killing.** A 35-trade losing streak (PDH-Fade has these) would draw down 35-70%+ depending on stop-fire rate. |
| $50K | 0.6% | 5% | Still aggressive. Drawdown risk -25% to -40%. |
| $100K | 0.3% | 2.5% | Reasonable for proven strategy. -10% to -20% expected drawdown. |
| **$250K** | 0.12% | **1%** | **Exactly right.** Same percentage as $300 at $25K. |
| $500K | 0.06% | 0.5% | Conservative — could increase tier or open new strategies. |

The correct framing isn't "always $2500" or "always $300." It's **"always ~1% of current equity"** — which produces $2500 at $250K equity.

### The convex-payoff complication

Percentage sizing on PDH-Fade has a specific failure mode: during a 35-trade losing streak, equity draws down 25-30%. At "1% of current equity" sizing, the next winner hits at the lower-equity sizing — capturing fewer absolute dollars than if sizing had been set when equity was at peak.

This means **strict percentage sizing slightly under-captures the convex tail**. Mitigation options:

- **Peak-equity sizing:** size based on equity-from-peak, not current equity. Maintains absolute risk during drawdown. *Risk: doesn't reduce on actual losses, harder DD discipline.*
- **Tiered baseline:** advance to next tier on equity milestones, only retreat on -15% from new tier baseline. *Cleaner ratchet, captures most upside, has DD protection.*
- **Hybrid:** percentage during drawdown, tier-based during expansion. *Complex, hard to reason about.*

**Recommendation: tiered baseline with drawdown protection.** Cleanest implementation, easiest operator psychology, captures most of the convex upside.

---

## 3. The proposed scaling schedule

### Tier table

| Tier | Equity floor | Risk per signal | % per trade | Combined max (3 strats) | % session max |
|---:|---:|---:|---:|---:|---:|
| **1** | $25K (start) | $300 | 1.2% | $900 | 3.6% |
| **2** | $40K | $500 | 1.25% | $1,500 | 3.75% |
| **3** | $60K | $750 | 1.25% | $2,250 | 3.75% |
| **4** | $100K | $1,000 | 1.0% | $3,000 | 3.0% |
| **5** | $150K | $1,500 | 1.0% | $4,500 | 3.0% |
| **6** | $200K | $2,000 | 1.0% | $6,000 | 3.0% |
| **7** | $250K | **$2,500** | 1.0% | $7,500 | 3.0% |
| **8** | $400K | $3,500 | 0.875% | $10,500 | 2.625% |
| **9** | $750K | $5,000 | 0.667% | $15,000 | 2.0% |

**Why these specific levels:**

- **Tiers 1-3 increment more aggressively** (small % steps). Early growth captures compounding while strategies prove out in live markets.
- **Tier 4 onward holds at 1% per trade.** This is the proven institutional benchmark for active strategies.
- **Tiers 8-9 reduce % as account grows.** Once equity is large enough to matter, capital preservation trumps capture rate. Same dollar growth from smaller percentage exposure.
- **Combined session max stays ≤3.75%** at all tiers. This is the binding portfolio risk constraint.

### Tier advancement rules

**To advance one tier:**

1. **Equity milestone met:** account equity ≥ next tier's floor for ≥3 consecutive sessions
2. **Stability check:** rolling 30-session Sharpe ≥ 1.0 across portfolio
3. **No active drawdown:** current equity must be at or above the prior 5-session average
4. **Forced minimum window:** cannot advance more than one tier per 14 calendar days regardless of equity (prevents lottery-ticket-style tier jumps from a single big winner)

### Tier retreat rules (drawdown protection)

**To retreat one tier:**

1. **Equity drops 15% from current tier's high-water mark** → automatic retreat to previous tier
2. **OR rolling 30-session Sharpe < 0.3** → retreat regardless of equity
3. **OR 3 consecutive losing weeks** → retreat to investigate

After retreat: re-advancement requires meeting *both* equity milestone AND stability check at the previous tier first. No skipping back up.

### Tier 1 → Tier 7 expected timeline

Per PDH-Fade-filtered backtest (+$192K over 5y at $25K start with $300 risk):

- **Year 1:** $25K → ~$60K (grows past Tier 3 milestone). Mid-Year-1 sizing at $750/signal.
- **Year 2:** $60K → ~$110K (Tier 4 reached mid-year). Sizing at $1,000/signal end of year.
- **Year 3:** $110K → ~$180K (Tier 5). Sizing at $1,500/signal.
- **Year 4:** $180K → ~$240K (still Tier 5/6).
- **Year 5:** $240K → ~$280K (Tier 7 reached). **Sizing at $2,500/signal end of year.**

This is approximate — strategy variance means some years grow faster, some flat or down. But ~5 years to reach Tier 7 ($2500) under the backtest's 47% annualized return is the baseline expectation.

**With portfolio diversification (3 strategies vs PDH-Fade alone), expected timeline is faster** — projected $250K-$300K over 5y means Tier 7 reached around Year 4.

---

## 4. Why not jump to $2500 sooner?

### The math problem

**A 35-trade losing streak at $2500 risk per trade = $87,500 max loss (worst case, all stops fire at full risk).** On a $25K account, that's not a drawdown — that's a wipe.

In practice losers fire at less than full risk (median PDH-Fade loser: -$127 on $1000 risk = 12.7% of risk). But the math still produces:

- 35 losers × 12.7% of $2500 risk = -$11,113 paper loss
- Plus the abandon-rule's ~$300/$500 cap interactions
- Plus correlated-loss days where multiple strategies fire and lose together

Realistic 35-trade losing streak loss at $2500 risk = $15K-$30K. **At $25K equity, that's 60-120% of the account.** Game over before the first winner.

### The psychology problem

At $25K with $300 per trade, a $300 loss is uncomfortable but not fatal — you can absorb 50+ in a row before a real DD problem.

At $25K with $2500 per trade, a single $2500 loss is 10% of the account in one trade. By trade #5 of a streak you're down 50%. **The operator override pressure becomes unbearable** — you'll start manually closing, manually skipping signals, manually overriding. That destroys the edge.

The whole forensic-response directive's emphasis on "zero discretionary overrides" assumes sizing that doesn't trigger panic responses. $300 at $25K stays well below the panic threshold. $2500 at $25K is *all* panic.

### The validation problem

Wave 4 paper is 60 days of validation. We need data on:
- Is the 18.8% WR holding live?
- Is the abandon-rule's $300 exit assumption valid?
- Is the release-on-stop conflict rule producing the $427K estimated lift?
- Is Monday-skip still the right call in 2026 regime?

**Sizing decisions before this data is in are guesses.** $300 baseline lets us collect data without bet-the-farm risk. After 60 days of clean paper, we know whether to actually size up — and if the data is bad, we know to retire the strategy entirely.

---

## 5. Concrete implementation plan

### Phase 1 — Wave 4 paper deployment (immediate, 60 days)

- Tier 1 sizing: **$300/signal fixed-dollar**
- HalfKellySizer disabled (Wave 5 P1 work fixes the bug)
- Daily reports track equity progression, drawdown depth, tier-trigger events
- After 60 days clean paper: tier advancement *available* but not required for paper

### Phase 2 — Real-money cutover (post-paper, conditional)

When 60-day paper validates clean (Sharpe ≥ 1.5, MaxDD ≤ 15%, zero override breaches):
- **Real money starts at Tier 1** ($300/signal)
- 30-session real-money validation period — **no tier advancement during this window** regardless of equity
- After 30 sessions clean: tier advancement rules go live

### Phase 3 — Tier advancement (live operation)

- Implementation: `framework/sizing.py` gets a new `TieredSizer` plugin
- Per-session check at market open: equity vs current tier rules → advance/retreat/hold
- Daily report includes current tier, equity-from-peak, days-in-tier, advancement progress
- Manual overrides logged but not blocked (you can pause advancement; you can't accelerate beyond tier rules)

### Phase 4 — Wave 5 HalfKellySizer fix (parallel work, separate sizing path)

The HalfKellySizer fix per Wave 5 P0 priorities produces **per-trade Kelly-optimal sizing within a tier's risk budget.** Not "Kelly says size 1500 shares" → that's tier-bypass. Rather: "tier risk allows $300 max per signal; Kelly says optimal allocation within that budget is X%."

Tiered sizing is the *outer* envelope. Kelly is the *inner* allocation. The two work together once both are in.

---

## 6. What this changes about the forensic-response directive

The original directive's `WB_FIXED_DOLLAR_RISK=300` config is correct as **the Tier 1 setting**, not as a permanent value. Add three new configs:

```
WB_SIZING_MODE=tiered                    # was: fixed_dollar
WB_TIER_INITIAL=1                        # start at Tier 1
WB_TIER_AUTO_ADVANCE=0                   # disabled during Wave 4 paper; flip on after real-money 30-session validation
```

Then the tier table from §3 lives in `framework/sizing_tiers.yaml` — a config file CC ships with the framework.

**Wave 4 deployment unchanged in practice** (still $300 risk, still fixed). The change is architectural — the system now knows about tiers and is ready to scale once the validation requirements are met.

---

## 7. The honest tradeoffs

### What this proposal preserves
- Account safety at $25K starting equity
- 60-day paper validation period
- Operator psychology during the 18.8% WR experience
- Clean drawdown protection via tier retreat rules

### What this proposal trades away
- Speed-to-$2500. Earliest realistic timeline is ~Year 4 (post-paper, with diversified portfolio). If you want $2500 risk in 6 months, you'd need either (a) start with $250K equity, or (b) accept much higher % risk on smaller equity, which kills the strategy.
- Tier-jumping on lottery-ticket winners. The 14-day minimum window prevents one +$50K NVDA trade from ratcheting you up two tiers prematurely.

### What this proposal explicitly rejects
- Fixed-dollar permanent sizing (under-utilizes edge as equity grows)
- Pure percentage sizing without tiers (under-captures convex tail during drawdowns)
- Discretionary tier advancement (operator-decision violations of advancement rules destroy the edge)

---

## 8. The two questions inside Manny's question

### "Is $300 permanent across all trades?"

**No.** $300 is the Tier 1 risk per signal. Same risk-per-signal across all 3 strategies for clean accounting. Moves up to $500/$750/$1000/etc. as equity grows through tiers.

### "Can it scale to $2500?"

**Yes, when equity reaches ~$250K.** At that point $2500 per signal = 1% per trade, which is the proven institutional risk size for active strategies. Reaching $250K starts at Tier 7 in the schedule above, expected ~Year 4-5 with diversified portfolio.

If you want $2500 sooner, the path is starting equity, not faster scaling. $25K → $2500 in months requires risk per trade levels that empirically destroy the strategies.

---

## 9. Decisions for Manny

This adds two more yes/no calls to the prior 5:

**Decision 6:** Approve the tier-based scaling schedule (Tiers 1-9, advancement and retreat rules per §3)?
- Yes = ship as the framework's sizing model
- No = pick a different approach (fixed-dollar permanent, percentage continuous, custom)

**Decision 7:** Approve disabling tier-auto-advancement during Wave 4 paper (60 days at Tier 1 $300 regardless of paper equity growth)?
- Yes = paper period is data-collection only, no sizing changes
- No = let paper account auto-advance (paper equity could move several tiers in 60 days, providing scaling validation data)

**Cowork recommendation: Yes to both.** Tier-based with drawdown protection is the cleanest pattern. Auto-advancement in paper would generate noise about tier behavior we'd then have to disentangle from strategy validation. Better to validate strategies clean at Tier 1, then validate scaling separately post-real-money cutover.

---

## 10. What Cowork is NOT recommending

- **Not** $2500 at $25K equity. Account-killing.
- **Not** lump-sum graduation (e.g., "after paper, jump to $2500"). Equity-based progression captures actual capital growth.
- **Not** per-strategy variable risk (e.g., "PDH-Breakout at lower risk because lower trade count"). Same risk per signal across strategies for clean accounting and equal portfolio contribution.
- **Not** larger combined-session caps. 3-strategy concurrent at 3.6% session max is already at the high end for new framework.
- **Not** tier advancement during Wave 4 paper. Validate strategies first, scaling second.

---

## 11. Files referenced

- `DIRECTIVE_2026-05-17_FORENSIC_RESPONSE.md` (the prior directive this augments)
- `framework/sizing.py` (existing — has the buggy HalfKellySizer; gains TieredSizer)
- `framework/sizing_tiers.yaml` (new — config file for tier table)
- All Phase 1 strategy YAML specs reference `WB_SIZING_MODE=tiered`
