# WB Winner-Template Forensic — Do the 5 Historical Winners Share a Replicable Pattern?

**Date:** 2026-05-17
**Author:** CC (cowork forensic)
**For:** Cowork (Perplexity) per `DIRECTIVE_2026-05-16_LOSER_FORENSIC.md` Investigation 4
**Scope:** The 5 named WB winners — FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13, ATRA 5/15
**Companion to:** `2026-05-16_wb_strategy_audit_weekly.md` (loser-side audit)
**Falsification target:** If winners do *not* share distinguishing features, WB has no replicable positive pattern and the strategy should be retired or pivoted.

---

## 1. Hypothesis

The five WB winners catalogued over 5/5–5/15 share positive structural features distinct from the 15-loser cohort: specifically, they should exhibit (a) entry-bar volume materially above the prior 5-bar average, (b) sustained price above VWAP through the entry zone, (c) entry inside a tight pre-arm consolidation rather than chasing a vertical bar, and (d) clustering in the same intraday window (afternoon RTH or controlled extended-hours). If ≥4 of 5 winners share ≥3 of these features, we can codify a score-boost or pre-arm gate. If the winners look as different from each other as they do from the losers, the strategy is event-randomness and should be retired.

---

## 2. Method

- Pulled `CHART` 1m bar lines from the relevant `2026-05-DD_subbot_alpaca.log` (FATN, ATRA 5/8, SST, MEI; ATRA 5/15 cross-referenced against `2026-05-15_wb_bot.log` for entry timing). For each winner, extracted 5 pre-entry bars + entry bar + 5 post-entry bars (skipping zero-print bars, which the builder omits — that absence is itself a feature).
- Recorded per bar: O/H/L/C, volume, VWAP, %-from-VWAP, HOD.
- Extracted score, wave#, R%, fill price, exit reason from `WB_ARMED` / `ENTER` / `FILL` / `EXIT` log events.
- Computed candidate features: vol_pre_avg, entry_bar_vol, vol_mult, %above_VWAP_at_entry, HOD_distance, pre-bar_range_compression, post-entry_5bar_drift.
- Defined "shared feature" as **present in ≥4 of 5 winners**. Defined "weak template" as 3 of 5. Anything ≤2 is noise.

Caveats embedded in §9.

---

## 3. Per-winner 11-bar profiles

Bars labeled relative to entry (−5 .. 0 .. +5). Empty cells = no bar emitted that minute (zero ticks). VWAP-Δ = %from-VWAP. All times ET.

### 3.1 FATN 5/5 — 14:39 ET ARM, fill $3.28, exit $3.35 (+$1,074, +1.46R)

| Bar | Time | O | H | L | C | Vol | VWAP | VWAP-Δ | HOD |
|---|---|---|---|---|---|---|---|---|---|
| −5 | 14:15 | 3.24 | 3.25 | 3.24 | 3.25 | 507 | 3.19 | +2.0% | 3.31 |
| −4 | 14:20 | 3.24 | 3.24 | 3.24 | 3.24 | 1,403 | 3.19 | +1.7% | 3.31 |
| −3 | 14:25 | 3.24 | 3.24 | 3.24 | 3.24 | 200 | 3.19 | +1.7% | 3.31 |
| −2 | 14:30 | 3.25 | 3.25 | 3.25 | 3.25 | 202 | 3.19 | +2.0% | 3.31 |
| −1 | 14:35 | 3.24 | 3.24 | 3.24 | 3.24 | 309 | 3.19 | +1.7% | 3.31 |
| **0** | **14:40** | **3.26** | **3.28** | **3.26** | **3.28** | **2,219** | **3.19** | **+2.9%** | **3.31** |
| +1 | 14:45 | 3.35 | 3.42 | 3.35 | 3.38 | 4,073 | 3.20 | +5.7% | 3.42 |
| +2 | 14:50 | 3.40 | 3.40 | 3.40 | 3.40 | 318 | 3.20 | +6.2% | 3.42 |
| +3 | 14:55 | 3.37 | 3.40 | 3.37 | 3.39 | 4,125 | 3.20 | +5.8% | 3.42 |
| +4 | 15:00 | 3.40 | 3.40 | 3.39 | 3.39 | 904 | 3.21 | +5.7% | 3.42 |
| +5 | 15:05 | (no bar) | | | | 0 | | | |

**Pattern:** 5 pre-bars in a 1¢ range ($3.24–$3.25), avg vol 524 sh. Entry bar = 4.2× pre-avg vol AND a 2¢ breakout above pre-range high. +1 bar breaks HOD ($3.31 → $3.42) on 4,073 sh = ~8× pre-avg vol. Sustained above VWAP every bar. **Classic compression-then-pop.**

### 3.2 ATRA 5/8 — 17:09 ET ARM, fill $8.65, exit $9.08 (+$2,500, +2.51R)

| Bar | Time | O | H | L | C | Vol | VWAP | VWAP-Δ | HOD |
|---|---|---|---|---|---|---|---|---|---|
| −5 | 16:35 | 8.53 | 8.53 | 8.53 | 8.53 | 600 | 8.68 | −1.7% | 9.93 |
| −4 | 16:40 | 8.67 | 8.67 | 8.67 | 8.67 | 1,908 | 8.68 | −0.1% | 9.93 |
| −3 | 16:45 | 8.64 | 8.64 | 8.64 | 8.64 | 3 | 8.68 | −0.4% | 9.93 |
| −2 | 16:50 | (no bar) | | | | 0 | | | |
| −1 | 16:55 | (no bar) | | | | 0 | | | |
| **0** | **17:10** | **8.60** | **8.60** | **8.60** | **8.60** | **5,000** | **8.67** | **−0.8%** | **9.93** |
| +1 | 17:15 | 8.65 | 8.65 | 8.65 | 8.65 | 400 | 8.67 | −0.3% | 9.93 |
| +2 | 17:20 | (no bar) | | | | 0 | | | |
| +3 | 17:25 | 8.69 | 8.69 | 8.69 | 8.69 | 202 | 8.67 | +0.2% | 9.93 |
| +4 | 17:30 | 8.62 | 8.70 | 8.62 | 8.70 | 706 | 8.67 | +0.3% | 9.93 |
| +5 | 17:35 | 8.64 | 8.65 | 8.64 | 8.65 | 1,316 | 8.67 | −0.3% | 9.93 |

**Pattern:** Extended-hours dead tape. 3 of 5 pre-bars zero-print. Entry bar 5,000 sh is anomalous high — but it is *the fill itself* (5,813 share order). Price is **below VWAP** at entry (−0.8%), 12.6% **below HOD**. Post-entry drift is microscopic; the winning move came 2.5 hours later (final exit at 19:35 ET, +5% above VWAP). This is a multi-hour overnight-style hold that happened to trigger trailing_stop on the post-market push. **Nothing about bars −5..+5 indicates a winning setup; the only "feature" is the operator letting the position breathe across a 2.5-hour dead-tape window.**

### 3.3 SST 5/11 — 14:18 ET ARM, fill $3.83, exit $4.09 (+$2,090, +3.28R)

| Bar | Time | O | H | L | C | Vol | VWAP | VWAP-Δ | HOD |
|---|---|---|---|---|---|---|---|---|---|
| −5 | 13:55 | 3.82 | 3.82 | 3.82 | 3.82 | 6 | 3.79 | +0.9% | 4.08 |
| −4 | 14:00 | 3.81 | 3.81 | 3.81 | 3.81 | 200 | 3.79 | +0.6% | 4.08 |
| −3 | 14:05 | 3.77 | 3.77 | 3.77 | 3.77 | 400 | 3.79 | −0.4% | 4.08 |
| −2 | 14:10 | (no bar) | | | | 0 | | | |
| −1 | 14:15 | 3.79 | 3.79 | 3.79 | 3.79 | 800 | 3.79 | +0.1% | 4.08 |
| **0** | **14:20** | (no bar at 14:20; 14:18 fill triggered) | | | | | | | |
| +0\* | 14:25 | 3.82 | 3.82 | 3.82 | 3.82 | 400 | 3.79 | +0.9% | 4.08 |
| +1 | 14:30 | 3.79 | 3.79 | 3.79 | 3.79 | 1,010 | 3.79 | +0.1% | 4.08 |
| +2 | 14:35 | 3.81 | 3.81 | 3.81 | 3.81 | 4,800 | 3.79 | +0.7% | 4.08 |
| +3 | 14:40 | 3.81 | 3.81 | 3.81 | 3.81 | 4,400 | 3.79 | +0.7% | 4.08 |
| +4 | 14:45 | 3.81 | 3.81 | 3.81 | 3.81 | 2,700 | 3.79 | +0.7% | 4.08 |
| +5 | 14:50 | 3.77 | 3.77 | 3.77 | 3.77 | 900 | 3.79 | −0.6% | 4.08 |

**Pattern:** 5 pre-bars span $3.77–$3.82 (1.3% range), avg vol 281 sh excluding the −2 zero bar. Pre-arm entirely flat consolidation. Entry bar volume not visible (entry falls between 14:15 and 14:25 bars). Post-entry +5 bars never close higher than $3.82 — the winning push to $4.09 occurred at 15:00 (~42 minutes after fill) on a vol-spike bar that *post-dates* this window. **Like ATRA 5/8, this is a slow-burn winner; the +5 bar window shows nothing distinguishing.** The fill was 6.1% below HOD; price was at VWAP (within +0.1%).

### 3.4 MEI 5/13 — 16:06 ET ARM, fill $14.05, exit $14.23 (+$366, +0.77R)

| Bar | Time | O | H | L | C | Vol | VWAP | VWAP-Δ | HOD |
|---|---|---|---|---|---|---|---|---|---|
| −5 | 15:40 | 14.04 | 14.08 | 13.98 | 13.99 | 50,299 | 13.53 | +3.4% | 15.54 |
| −4 | 15:45 | 13.91 | 14.00 | 13.91 | 13.99 | 18,412 | 13.54 | +3.3% | 15.54 |
| −3 | 15:50 | 13.90 | 13.91 | 13.88 | 13.88 | 22,646 | 13.54 | +2.5% | 15.54 |
| −2 | 15:55 | 13.82 | 13.88 | 13.82 | 13.88 | 16,921 | 13.55 | +2.5% | 15.54 |
| −1 | 16:00 | 13.90 | 13.93 | 13.85 | 13.86 | 31,858 | 13.55 | +2.3% | 15.54 |
| **0** | **16:05** | **13.85** | **13.85** | **13.85** | **13.85** | **101** | **13.57** | **+2.0%** | **15.54** |
| +1 | 16:10 | 13.95 | 13.95 | 13.91 | 13.91 | 1,439 | 13.57 | +2.5% | 15.54 |
| +2 | 16:15 | 13.97 | 13.99 | 13.97 | 13.99 | 1,486 | 13.57 | +3.1% | 15.54 |
| +3 | 16:20 | 14.34 | 14.34 | 14.21 | 14.28 | 820 | 13.57 | +5.2% | 15.54 |
| +4 | 16:25 | 14.23 | 14.23 | 14.23 | 14.23 | 200 | 13.57 | +4.8% | 15.54 |
| +5 | 16:30 | 14.10 | 14.10 | 14.10 | 14.10 | 2 | 13.57 | +3.9% | 15.54 |

**Pattern:** Pre-entry window has real volume — 50K, 18K, 22K, 17K, 32K — a momentum day, biggest of the 5 by 3 orders of magnitude. **But** by the entry bar (16:05), the market closed and volume collapses to 101 sh. Entry bar is on a 101-share bar; exit 16:18 ET runs through 1,400-share bars. Always above VWAP (+2.0% to +5.2%). 9.6% below HOD at fill. **This is the only winner where the pre-entry tape was actually liquid; the entry itself was on a near-dead bar but at the back of a real momentum day.**

### 3.5 ATRA 5/15 — 13:21 ET ARM, fill $9.10, exit $9.31 (+$1,160, +1.00R)

| Bar | Time | O | H | L | C | Vol | VWAP | VWAP-Δ | HOD |
|---|---|---|---|---|---|---|---|---|---|
| −5 | 12:50 | 8.78 | 8.78 | 8.71 | 8.71 | 607 | 9.22 | −5.5% | 9.81 |
| −4 | 12:55 | 8.72 | 8.76 | 8.70 | 8.73 | 5,015 | 9.20 | −5.1% | 9.81 |
| −3 | 13:00 | 8.71 | 8.73 | 8.71 | 8.73 | 906 | 9.20 | −5.1% | 9.81 |
| −2 | 13:05 | 8.79 | 8.88 | 8.79 | 8.88 | 751 | 9.18 | −3.3% | 9.81 |
| −1 | 13:15 | 8.81 | 8.85 | 8.81 | 8.85 | 302 | 9.18 | −3.6% | 9.81 |
| **0** | **13:20** | **8.82** | **8.82** | **8.82** | **8.82** | **1,400** | **9.17** | **−3.9%** | **9.81** |
| +1 | 13:25 | 9.00 | 9.00 | 9.00 | 9.00 | 1 | 9.17 | −1.9% | 9.81 |
| +2 | 13:30 | 8.93 | 8.93 | 8.93 | 8.93 | 12,600 | 9.16 | −2.5% | 9.81 |
| +3 | 13:35 | 8.94 | 9.03 | 8.94 | 9.03 | 209 | 9.15 | −1.3% | 9.81 |
| +4 | 13:40 | 9.06 | 9.06 | 9.06 | 9.06 | 1 | 9.15 | −1.0% | 9.81 |
| +5 | 13:45 | 8.97 | 9.02 | 8.97 | 9.02 | 1,003 | 9.15 | −1.4% | 9.81 |

**Pattern:** Pre-entry is the dead-tape case from the 5/15 postmortem. Avg pre-vol 1,316 sh (skewed by the one 5,015-bar at −4). Entry on a 1,400-share bar. Price is **below VWAP every bar of the window** (−5.5% to −1.0%). 7.2% below HOD at fill. The +1 bar is a 1-share print at $9.00. The "winner" is a 2.5-hour drift from $9.10 → $9.31. **This is the postmortem's "we are the liquidity" trade — and the very setup the dead-tape gate that shipped 5/16 now blocks.**

---

## 4. Qualitative narrative per winner

**FATN 5/5 — afternoon HOD reclaim, the only textbook winner.** Day-2 dip-after-pump pattern. Bot watched the morning sell-off from $3.31 HOD down to $3.07 VWAP, observed five 1¢ consolidation bars at $3.24–$3.25, then armed at the moment the bar finally closed above the consolidation high. Entry bar was the first 2¢ green bar with 4.2× the pre-window volume; +1 bar carried HOD to $3.42 on 8× volume. This is the only one of the five winners that looks like a standard breakout-trader entry. **Time bucket: post-12 ET RTH. Score 8 at ARM, R%=1.5%.**

**ATRA 5/8 — extended-hours fade rescue.** ATRA was the day's biggest mover (68% gap, peak $9.93). By 17:09 the stock had given back the gains and was trading $8.60, **below VWAP, 13% below HOD**, on 5,000-share lots in a half-empty extended-hours session. The arm fired on score=10 because the WB scorer rewarded the "deep pullback to the gap level" structure; the win came from holding through 2.5h of dead tape until a late EH push to $9.08 hit the trailing stop. **This is not a "winning setup" — it's a position the bot opened and survived. The same setup on most days would orphan into a next-AM gap-down.** Time bucket: late-EH (17:00+).

**SST 5/11 — wave-60 mid-afternoon outlier.** SST had been trading in a $3.78–$3.84 box for ~3 hours when the bot armed at 14:18 ET. Pre-entry volume was thin (avg 281 sh). Entry filled at $3.83, +0.1% above VWAP, 6% below HOD. The post-entry +5 window is unremarkable — the winning push to $4.09 happened at 15:00 on a wave that came 40 minutes after fill. The system is given credit because the trailing_stop didn't trigger early. **Time bucket: post-12 ET RTH. Score 9 at ARM (highest of the 5), R%=1.0% (lowest of the 5).**

**MEI 5/13 — manual injection on a momentum day, late-day fade.** MEI was added to the watchlist manually during a Databento outage (`2026-05-14_mei_bypass_trace.md`). The day was a real 50%+ momentum runner — 50K–32K share bars in the 5 pre-entry minutes. By 16:06 the market had closed and bars collapsed to 100–800 shares, but the bot scored a +2.0% above VWAP setup as wave-20 and entered. Trailing_stop fired 12 minutes later on the $14.21 push. **Not a strategy-found winner; the strategy executed correctly on a setup the operator chose.** Time bucket: post-RTH transition (16:00–16:30).

**ATRA 5/15 — the dead-tape misfire that printed.** The postmortem trade. Pre-entry: 5 bars of 300–5,000 share prints, all below VWAP, all below HOD. Score=8 wave-25 arm fired on a 4.33× ratio bar that was 4,700 actual shares — the bot bought more than the bar that triggered it. Price held essentially flat for 2 hours then drifted up to the trailing stop at $9.31. **Per the 5/15 postmortem: the bot ran exactly to spec and made a trade no human would. The dead-tape gate that shipped 5/16 would have vetoed this.** Time bucket: post-12 ET RTH. Score 8, R%=2.34%.

---

## 5. Candidate-feature analysis (rows: features, columns: winners, marking which winner has which)

Y = present (per definition below). N = absent. (?) = ambiguous/borderline.

| Feature | Definition | FATN 5/5 | ATRA 5/8 | SST 5/11 | MEI 5/13 | ATRA 5/15 | Count |
|---|---|:-:|:-:|:-:|:-:|:-:|:-:|
| F1: Entry-bar vol > 2× pre-5-avg | volume confirmation on entry | **Y** (4.2×) | (?) — bar = fill itself | N (similar) | N (101 vs 28K avg) | (?) (1.07× incl 5K outlier) | 1 of 5 |
| F2: Sustained above VWAP through pre-5 | 5 of 5 pre-bars VWAP-Δ > 0 | **Y** (+1.7% to +2.0%) | N (all below) | **Y** (4 of 5 positive) | **Y** (all +2.3 to +3.4%) | **N** (all below) | 3 of 5 |
| F3: ≤2% below HOD at fill | HOD proximity | N (6% below) | N (13% below) | N (6% below) | N (9.6% below) | N (7.2% below) | **0 of 5** |
| F4: Tight pre-arm consolidation (5-bar range ≤2% of price) | pre-bar compression | **Y** (range $3.24-$3.25 = 0.3%) | (?) zero-print bars | **Y** ($3.77-$3.82 = 1.3%) | N ($13.82-$14.08 = 1.9% but on trending down move) | N ($8.70-$8.88 = 2.1%) | 2 of 5 |
| F5: Entry-bar vol ≥ 1,000 sh absolute | absolute liquidity floor | **Y** (2,219) | **Y** (5,000) | (?) — entry-bar straddles 14:15/14:25 (800/400) | N (101) | **Y** (1,400) | 3 of 5 |
| F6: Time bucket 12:00–16:00 ET | RTH afternoon | **Y** (14:39) | N (17:09) | **Y** (14:18) | (?) (16:06, edge) | **Y** (13:21) | 3 of 5 |
| F7: Score ≥ 8 at ARM | scoring floor | **Y** (8) | **Y** (10) | **Y** (9) | N (7) | **Y** (8) | 4 of 5 |
| F8: R% ≥ 1.5% | reward-to-risk floor | (?) (FATN R=$0.048 on $3.28 = 1.46%) | **Y** (R%=1.7-2.0%) | N (1.0%) | **Y** (1.7%) | **Y** (2.34%) | 3 of 5 |
| F9: Pre-entry 5-bar avg vol ≥ 1,000 sh | overall liquidity | N (524) | (?) (mixed, ~500 incl zero-bars) | N (281) | **Y** (28K avg) | N (1,316, single bar carrying) | 1 of 5 |
| F10: Post-entry +1 bar holds above entry price | immediate confirmation | **Y** (close $3.38 > fill $3.28) | **Y** ($8.65 vs $8.60) | **Y** ($3.82 vs $3.83 ≈ flat) | **Y** ($13.91 > drift but holds) | **Y** ($9.00 > $8.82 entry-bar close; fill was $9.10 → drift below briefly per postmortem) | 4 of 5 (loose) |
| F11: Post-entry +5 bar closes higher than entry | sustained drift | (?) $3.39 vs fill $3.28: Y (+3.4%) | (?) $8.65 vs fill $8.65: 0% (winner came later) | N ($3.77 vs $3.83) | **Y** ($14.10 vs $14.05) | N ($9.02 vs $9.10) | 1 of 5 (strict), 3 of 5 (loose) |
| F12: Exit reason = trailing_stop | not stop-hit | **Y** | **Y** | **Y** | **Y** | **Y** | **5 of 5** |
| F13: Catalyst — gap day / sympathy / momentum | qualitative | N (Day-2 dip-reclaim) | **Y** (68% gap day) | N (3-hour box) | **Y** (50%+ runner) | N (post-momentum fade) | 2 of 5 |
| F14: Hold time > 30 min | slow-burn winner | N (~6 min to exit) | **Y** (2.5h) | **Y** (~42m) | N (~12m) | **Y** (~148m) | 3 of 5 |

---

## 6. Shared features (≥4 of 5)

Only **two** features clear the ≥4-of-5 bar:

- **F7 — Score ≥ 8 at ARM (4 of 5):** MEI is the lone score=7 winner. But the weekly audit shows score=10 was 0/5 winners and score=8 was 2/9 — so "score ≥ 8" is a necessary-but-not-sufficient feature that already exists as the WB_MIN_SCORE floor. Raising the floor to 8 removes MEI without obvious upside.
- **F12 — Exit reason = trailing_stop (5 of 5):** This is tautological: it is the *definition* of a winner under current exit rules. It tells us nothing about entries.

**The honest count of entry-side shared features is one (F7 score≥8), and that floor is already in place.**

Two **near-misses at 3 of 5** that the directive asked about:

- **F6 — Time bucket 12:00–16:00 ET RTH afternoon (3 of 5):** ATRA 5/8 is EH and MEI is right at the close edge. Aligns with the weekly audit's "14:00–18:00 is the only positive bucket" finding, but is not strong enough to be a template feature.
- **F2 — Sustained above VWAP (3 of 5):** Two winners (ATRA 5/8 and ATRA 5/15) printed every bar of their entry window *below* VWAP. A VWAP-required gate would have blocked 40% of the wins.

**Features that fail outright:**

- **F1 entry-volume confirmation:** 1 of 5. The "vol_mult on entry bar" the WB scorer rewards is statistically absent in this winner set.
- **F3 HOD proximity:** **0 of 5.** Every winner filled 6%–13% below session HOD. The WB strategy explicitly enters on pullbacks; this is by design, but it means no HOD-proximity gate helps.
- **F9 pre-entry liquidity:** 1 of 5. Four of the five winners ran on average pre-entry volume below 1,500 sh/min — the exact dead-tape profile the new gate now blocks.

---

## 7. Falsification check

**The hypothesis is disproven.**

The 5 winners do not share an entry-side template. Reading down the per-winner narratives:

- **FATN 5/5** is a textbook afternoon HOD-reclaim breakout — tight pre-bar consolidation, vol confirmation, immediate follow-through.
- **ATRA 5/8** is an extended-hours dead-tape position held through 2.5h of nothing until a late-EH push.
- **SST 5/11** is a flat-box mid-afternoon entry whose winning push came 40 minutes after fill.
- **MEI 5/13** is a manual injection on a momentum day, entered at the post-RTH transition with the day's volume already gone.
- **ATRA 5/15** is the dead-tape misfire the new postmortem-driven gate now blocks.

Three of the five winners (ATRA 5/8, ATRA 5/15, and SST 5/11 in part) are stocks whose winning move occurred 40+ minutes after fill on tape that the +5 bar window says nothing about. The +5 bar window — which the directive proposes as the template substrate — captures the winning move for only one of the five (FATN). For the other four, the winning move post-dates the window.

The four "shared feature" patterns the directive asked about — VWAP behavior, volume confirmation, HOD proximity, day-range expansion — fire in **at most 3 of 5** winners (VWAP) and as low as **0 of 5** (HOD proximity). Two winners (ATRA 5/8 and ATRA 5/15) share *zero* of the four directive-listed positive features.

**Read structurally:** ATRA 5/8 (EH dead-tape fade-and-hold) and FATN 5/5 (RTH compression-breakout) have **nothing in common as entries**. They are two different trades that happened to print positive P&L through different mechanisms — one through patience across a dead window, the other through textbook breakout follow-through.

---

## 8. Proposed action

**No replicable winner template exists.** The data does not support a positive scoring gate.

Three honest options follow:

### Option A — Retire WB as a standalone strategy

The 5-day audit shows 19% win rate and net −$9.1K excluding manual/infra/overnight events. The 5-winner forensic shows the wins are heterogeneous events, not a pattern. Combined: there is no statistical basis for expecting WB to produce repeatable winners under real money. **Recommendation: pause WB at real-money go-live; keep squeeze as the sole strategy.**

### Option B — Pivot WB to a narrow "FATN-pattern only" sub-strategy

The single replicable winner type in the dataset is the FATN 5/5 profile: post-12 ET, score≥8, R%≥1.5%, pre-arm 5-bar range ≤1% of price, entry-bar vol ≥ 2× pre-5 avg AND ≥ 1,000 sh absolute. This filter would have:
- **Caught:** FATN 5/5 only.
- **Rejected:** ATRA 5/8 (below VWAP), MEI 5/13 (entry bar 101 sh fails vol absolute), ATRA 5/15 (below VWAP and ratio-not-absolute fails), SST 5/11 (R%=1.0% fails).
- **Result:** 1 of 5 winners retained, ~$1K/week revenue at the same loser-rejection profile of the dead-tape + liquidity gates that already shipped.

This is a narrow-edge sub-strategy. It might be worth running in observe-only mode for 2 weeks to confirm the FATN pattern reproduces. **Recommendation: gate WB to FATN-pattern only, observe-mode for 5–10 sessions before re-enabling real fills.**

### Option C — Keep WB running unchanged with the new gates and accept that wins are random

The dead-tape gate, liquidity gate, dead_bounce sub-gate, and post-11 time gate (already shipped or staged) will reduce loser fills meaningfully. They will also block ATRA 5/15 (40% of the post-5/8 winner P&L). If the remaining 60% (FATN, MEI, ATRA 5/8) survive the new gates, WB might break even. The audit's loser-side data suggests it will not, but this option keeps optionality alive for one more week of data.

**My recommendation: Option B.** Option A throws away the FATN template, which is the one thing that does look reproducible. Option C is the path the prior week's audit already cast doubt on. Option B is the smallest-surface-area path that preserves the one positive pattern in the dataset.

---

## 9. Limitations

- **n=5 winners across a 10-trading-day window.** Any conclusion drawn from this dataset is descriptive, not predictive. The hypothesis-falsification call (no template) is robust at n=5 because the winners differ qualitatively, not just quantitatively — but the option-B FATN-template recommendation has n=1 supporting it and is itself low-confidence.
- **Mix of pre- and post-strategy-change days.** The persistence layer (deployed 5/01), dead-tape gate (5/16), liquidity gate (5/15 amendment), and intra-day adder (5/15 ship) all happened mid-window. ATRA 5/15 and MEI 5/13 happened under different rule sets than FATN 5/5 and ATRA 5/8. The "winners" are not produced by a uniform pipeline.
- **ATRA 5/15 is borderline.** The dead-tape gate that shipped 2026-05-16 would have vetoed it. Reading it as a "winner" credits a setup the strategy is now built to reject. If ATRA 5/15 is excluded from the winners list, the n drops to 4 and the template question gets harder, not easier — but the FATN pattern would still be the sole reproducible one.
- **MEI 5/13 is manual.** The strategy did not select MEI; the operator did during a Databento outage. Including it counts an operator-injection as a strategy win. Excluding it drops n to 4 again.
- **Stripping ATRA 5/15 and MEI 5/13 (both contested) leaves n=3 unambiguous strategy-selected winners: FATN 5/5, ATRA 5/8, SST 5/11.** Of these three, only FATN matches the directive's expected template. The other two share *zero* of the directive's listed positive features.
- **+5 post-entry bar window is too short for the slow-burn winners.** ATRA 5/8 (148m hold), SST 5/11 (42m hold), and ATRA 5/15 (148m hold) all earned their P&L on bars that fall outside the +5 window. A +60-bar window might surface a different "winning post-entry pattern" — but it would also conflate the winning move with the trailing_stop exit. The 11-bar profile is fundamentally the wrong instrument for slow-burn winners.
- **No "winning move" timestamp captured.** The audit framework records exit price but not the peak-MFE bar. A future investigation could compute time-to-MFE per winner; this report did not.

---

## Bottom line

The 5-winner cohort does not share a replicable entry-side template. Four of the five could not be selected by any combination of pre-entry bar features without also catching the bulk of the losers. The one exception (FATN 5/5) is a single observation, not a pattern.

The strategy's apparent winners are heterogeneous events: one breakout, one fade-and-hold, one box-break, one manual injection, one dead-tape misfire. They are not five instances of the same setup.

This is the highest-leverage finding the forensic could surface: **WB does not have a positive replicable pattern at the n we can measure**. The most honest path forward is either to retire WB or to gate it to the FATN-pattern only, run in observe-mode for 2 weeks, and revisit on fresh data.
