# WB Loser Behavioral Profile — 11-Bar Forensic

**Author:** Cowork (Opus) investigation per `DIRECTIVE_2026-05-16_LOSER_FORENSIC.md` Investigation 2
**Companion:** `2026-05-16_wb_strategy_audit_weekly.md`
**Data window:** 5/11–5/15, Setup A (subbot Alpaca) + Setup B (engine Alpaca)
**Trades reconstructed:** 23 fills (2 winners + 21 losers; FCHL/MEI excluded as outliers per directive)

---

## 1. Hypothesis

> WB losers share visible behavioral signatures in the 5 bars pre/post entry that distinguish them from winners. Losers enter on noise spikes that don't sustain; winners enter on moves with multi-bar confirmation.

**Falsification criterion:** If the 11-bar (5 pre + entry + 5 post) profile is statistically indistinguishable between winners and losers, the hypothesis is rejected.

## 2. Method

For every WB fill across 5/11–5/15 (excluding the FCHL infra orphan and the MEI manual-injection edge case), I aggregated 1-minute OHLCV bars from the per-day tick caches:

- Subbot: `/Users/duffy/warrior_bot_v2/tick_cache/<date>/<sym>.json.gz`
- Engine: `/Users/duffy/warrior_bot_v2_engine/tick_cache_engine/<date>/<sym>.json.gz`

For each fill I computed:

- **Pre-entry (bars −5..−1):** mean/median/max volume, mean range, tick count
- **Entry bar (bar 0):** volume, range, vol-mult vs prior 25 min, distance from VWAP at fill, distance from HOD at fill
- **Post-entry (bars +1..+5):** vol of +1 bar vs entry bar, +1 close vs VWAP, bars above entry close, peak unrealized R, cumulative 5-min move, time-to-first-bar-below-stop, post/entry range collapse

Tool: `/tmp/wb_forensic_bars.py` (one-shot analyzer; not committed — per directive, this is investigation, not a script we'll ship).

**Data caveats**

- Tick cache is the live tick stream the bot received. It is more accurate than `[WB] CHART` log lines (which sample at ~5 min and are summarized). I used tick cache exclusively.
- Some trades have **no ticks on the entry minute** (engine-detected fill bars where the only print was the bot's own order) — these show as zero-volume entry bars. This is meaningful, not missing data.
- I treat "winner" as a positive-P&L closed fill. The audit's 2 WB-attributable winners in the n=23 set are SST 5/11 (+$2,090) and ATRA 5/15 (+$1,160). ATRA 5/12 partial-fill +$41 is excluded — too small to be diagnostic.

## 3. Per-trade 11-bar metrics

Compact view (all 23 trades). `vol_mult` = entry bar volume ÷ mean of prior 25 min. `p1/entry` = bar+1 volume ÷ entry bar volume. `peak_R` = best unrealized R during +1..+5. `cum5%` = (+5 close − fill) / fill. `TTS` = minutes until first bar low ≤ stop level. `range_coll` = mean range of bars +1..+3 ÷ entry range.

| Date | Sym | S | Time | Out | P&L | Fill | R% | preV_mean | entry_v | vol_mult | vwap% | distHOD% | p1_v | p1/entry | bars>fill | peakR | cum5% | TTS | rangeColl |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 5/11 | NVOX | A | 10:12 | L | -37 | 16.22 | 0.44 | 4962 | 684 | 0.08 | +0.2 | -3.4 | 1772 | 2.59 | 5 | +2.82 | +1.2 | — | 1.25 |
| 5/11 | ATRA | A | 13:52 | L | -513 | 8.47 | 1.18 | 356 | 702 | 0.90 | -0.1 | -7.9 | 502 | 0.72 | 0 | -0.30 | -0.4 | 5 | 0.08 |
| **5/11** | **SST** | **A** | **14:18** | **W** | **+2090** | **3.83** | **1.02** | **2302** | **100** | **0.05** | **+1.2** | **-6.2** | **0** | **0.00** | **0** | **0.00** | **-0.3** | **2** | **n/a** |
| 5/11 | ATRA | A | 18:30 | L | -778 | 9.49 | 3.16 | 444 | 400 | 0.42 | +10.3 | -3.6 | 400 | 1.00 | 3 | +0.33 | -1.3 | — | n/a |
| 5/12 | ENSC | A | 08:16 | L | -644 | 0.329 | 2.31 | 2278 | 2824 | 0.53 | +1.9 | -11.9 | 4004 | 1.42 | 0 | -0.34 | -1.4 | 3 | 16.00 |
| 5/12 | SST | A | 11:20 | L | -870 | 3.94 | 2.49 | 407 | 1017 | 0.75 | +1.7 | -2.2 | 625 | 0.61 | 0 | -0.41 | -2.8 | 1 | 0.77 |
| 5/12 | ENSC | A | 14:54 | L | -519 | 0.335 | 1.28 | 4251 | 21853 | 5.16 | +1.1 | -10.2 | 6534 | 0.30 | 2 | +0.42 | -0.8 | 3 | 1.63 |
| 5/12 | TRAW | A | 15:17 | L | -661 | 1.82 | 1.10 | 6351 | 2673 | 0.68 | -1.9 | -15.4 | 1611 | 0.60 | 0 | -1.25 | -2.2 | 1 | 22.22 |
| 5/13 | ENSC | A | 11:53 | L | -509 | 0.301 | 2.09 | 3715 | 10 | 0.00 | +1.9 | -5.9 | 0 | 0.00 | 0 | -0.13 | -0.8 | — | n/a |
| 5/13 | ODYS | A | 18:27 | L_o | -603 | 4.36 | 2.98 | 181 | 200 | 2.11 | -0.9 | -11.6 | 200 | 1.00 | 0 | -0.31 | -3.0 | 2 | n/a |
| 5/15 | LESL | A | 16:53 | L | -735 | 3.09 | 2.49 | 120 | 94 | 0.16 | -7.1 | -26.4 | 0 | 0.00 | 0 | -1.04 | -2.6 | 3 | n/a |
| 5/12 | TRAW | B | 05:31 | L | -985 | 2.04 | 1.23 | 1452 | 3 | 0.00 | -0.0 | -5.1 | 1 | 0.33 | 0 | -0.40 | -0.5 | — | n/a |
| 5/12 | ODYS | B | 05:48 | L | -856 | 4.70 | 0.47 | 1178 | 400 | 0.73 | +0.4 | -2.3 | 602 | 1.50 | 3 | +2.27 | +0.9 | 1 | n/a |
| 5/12 | XOS | B | 06:29 | L | -735 | 2.05 | 0.73 | 1421 | 4105 | 1.23 | -15.4 | -31.2 | 3884 | 0.95 | 0 | 0.00 | -1.0 | 1 | 0.86 |
| 5/12 | FATN | B | 11:41 | L | -1381 | 3.62 | 1.35 | 2033 | 200 | 0.10 | +2.6 | -3.2 | 0 | 0.00 | 0 | 0.00 | -0.8 | — | n/a |
| 5/12 | FATN | B | 12:26 | L | -1127 | 3.58 | 0.81 | 161 | 102 | 0.07 | +1.4 | -4.3 | 0 | 0.00 | 0 | -0.09 | -1.1 | 2 | 1.42 |
| 5/12 | ATRA | B | 13:51 | L | -1157 | 10.03 | 0.35 | 492 | 305 | 0.18 | +2.3 | -5.6 | 1922 | 6.30 | 0 | -0.86 | -2.6 | 1 | n/a |
| 5/13 | ODYS | B | 19:02 | L_o | -698 | 4.33 | 1.87 | 202 | 3000 | 11.34 | -1.6 | -12.2 | 1000 | 0.33 | 0 | -0.25 | -2.3 | 2 | n/a |
| **5/15** | **ATRA** | **B** | **13:21** | **W** | **+1160** | **9.10** | **2.33** | **1780** | **7** | **0.00** | **-1.0** | **-7.2** | **6** | **0.86** | **0** | **-0.19** | **-0.8** | **—** | **n/a** |
| 5/15 | ONDG | B | 14:07 | L | -1198 | 6.73 | 1.59 | 4280 | 5221 | 0.69 | -4.8 | -19.9 | 4904 | 0.94 | 1 | +0.19 | 0.0 | — | 0.53 |
| 5/15 | PIII | B | 16:18 | L | -1628 | 11.40 | 2.88 | 4538 | 18353 | 2.29 | +22.2 | -13.8 | 7515 | 0.41 | 0 | -0.15 | -3.0 | 1 | 1.20 |
| 5/15 | LESL | B | 16:53 | L | -1299 | 3.09 | 2.18 | 120 | 94 | 0.16 | -7.1 | -26.4 | 0 | 0.00 | 0 | -1.19 | -2.6 | 3 | n/a |
| 5/15 | SLE | B | 19:17 | L_f | -713 | 5.61 | 1.68 | 3384 | 3510 | 2.56 | -8.6 | -21.0 | 320 | 0.09 | 0 | -0.32 | -1.1 | — | 0.39 |

`Out` legend: W=winner, L=loser (stop_hit), L_o=loser overnight, L_f=loser session-force-close. **Winners highlighted bold.**

### Selected 11-bar windows (illustrative)

**SST 5/11 14:18 — WINNER +$2,090 (R%=1.02)**
```
14:13  O=3.7899  H=3.7899  L=3.7899  C=3.7899  V= 5,600
14:14  O=3.7899  H=3.7899  L=3.7899  C=3.7899  V=   800
14:15  DEAD (no ticks)
14:16  O=3.7899  H=3.7899  L=3.7600  C=3.7601  V= 3,506
14:17  O=3.7601  H=3.7900  L=3.7601  C=3.7900  V= 1,604
14:18  O=3.7900  H=3.7900  L=3.7900  C=3.7900  V=   100   <-- ENTRY (filled at 3.83 limit but tick says 3.79)
14:19  DEAD (no ticks)
14:20  O=3.7900  H=3.7900  L=3.7900  C=3.7900  V=   100
14:21  O=3.7900  H=3.8300  L=3.7803  C=3.8299  V= 1,322
14:22  O=3.8299  H=3.8299  L=3.8200  C=3.8200  V= 2,210
14:23  O=3.8200  H=3.8200  L=3.8200  C=3.8200  V=   800
```
Entry bar: 100 shares (0.05× prior mean). Bar +1 dead. Move develops slowly over the next 39 min. **Entered into a vacuum, sat, then drifted up.**

**ATRA 5/15 13:21 — WINNER +$1,160 (R%=2.33)**
```
13:16  O=8.8400  H=8.8400  L=8.8200  C=8.8300  V= 3,521
13:17  DEAD
13:18  O=8.8200  H=8.8200  L=8.8200  C=8.8200  V= 1,400
13:19  DEAD
13:20  O=8.8200  H=9.0600  L=8.8200  C=9.0600  V= 3,978   <-- 2.4% pop, ARM bar
13:21  O=9.0500  H=9.0500  L=8.9900  C=8.9900  V=     7   <-- ENTRY (7 shares!)
13:22  O=9.0000  H=9.0000  L=9.0000  C=9.0000  V=     6
13:23  DEAD
13:24  O=9.0600  H=9.0600  L=9.0600  C=9.0600  V=   900
13:25  DEAD
13:26  O=9.0600  H=9.0600  L=9.0300  C=9.0300  V= 1,802
```
**Even more dramatic vacuum.** 7-share entry bar. 5 dead bars in the 11-bar window. The bot is essentially alone in the order book.

**ONDG 5/15 14:07 — LOSER −$1,198 (R%=1.59)**
```
14:02  O=6.6100  H=6.6100  L=6.5700  C=6.5700  V= 4,910
14:03  O=6.5700  H=6.5900  L=6.5700  C=6.5900  V= 2,204
14:04  O=6.5900  H=6.5900  L=6.5900  C=6.5900  V= 5,615
14:05  O=6.5900  H=6.5900  L=6.5900  C=6.5900  V=    43
14:06  O=6.5900  H=6.6800  L=6.5900  C=6.6800  V= 8,626   <-- ARM bar
14:07  O=6.6800  H=6.7300  L=6.6800  C=6.7200  V= 5,221   <-- ENTRY (5K vol)
14:08  O=6.7200  H=6.7500  L=6.7100  C=6.7500  V= 4,904
14:09  O=6.7500  H=6.7500  L=6.7100  C=6.7200  V= 3,910
14:10  O=6.7200  H=6.7200  L=6.7200  C=6.7200  V= 6,200
14:11  O=6.7200  H=6.7200  L=6.7200  C=6.7200  V= 4,200
14:12  O=6.7200  H=6.7300  L=6.7200  C=6.7300  V= 6,220
```
Healthy 5K-vol entry, healthy follow-through, but never breaks fill+R. Fades from $6.73 to $6.57. **Looks "good" by every classical chart heuristic and still loses.**

**PIII 5/15 16:18 — LOSER −$1,628 (R%=2.88) — the one-print spike**
```
16:13  V=    400 @ 11.10
16:14  DEAD
16:15  DEAD
16:16  V=  4,000 @ 10.98
16:17  V= 18,290 H=11.39   <-- huge ARM bar in EH
16:18  V= 18,353 H=11.40   <-- ENTRY at top of spike
16:19  V=  7,515 L=11.04   <-- immediate -3R retrace
16:20  V= 11,684 L=11.01
```
This is the canonical extended-hours one-print pattern: 2 dead bars → ARM spike → entry at literal high → −$1,628.

## 4. Cluster summary statistics

**WINNERS (n=2) vs LOSERS (n=21):**

| Metric | Winners (mean) | Losers (mean) | Losers (median) | Direction |
|---|---|---|---|---|
| Entry bar `vol_mult` (vs 25-min avg) | **0.025** | **1.44** | 0.68 | Losers 27× hotter entry |
| Entry bar volume (shares) | **53** | **3,300** | 702 | Losers 62× larger |
| Bar +1 ratio to entry | 0.43 | 0.91 | 0.60 | Losers have similar +1 vol — confirms no follow-through |
| Bars >fill in +1..+5 | **0** | **0.67** | 0 | Winners are *initially* underwater |
| Peak R in +1..+5 | **-0.09** | **-0.05** | -0.25 | Both negative early |
| Cum 5m % move | **-0.52%** | **-1.33%** | -1.12% | Losers fade harder |
| Dist from HOD% at fill | -6.7% | -11.6% | -10.2% | Losers further below HOD |
| R% | 1.67 | 1.65 | 1.59 | Indistinguishable |

**The single dominant feature: entry-bar volume.** Winners entered on 53-share / 100-share / 7-share bars. Losers entered on 700–18,000-share bars. The 27× gap on `vol_mult` is the most lopsided number in this dataset.

**Cluster breakdown:**

| Cluster | n | Mean vol_mult | Mean cum5% | Mean dist_HOD% | Mean R% | Median TTS (min) |
|---|---|---|---|---|---|---|
| Penny (<$1) — ENSC ×3 | 3 | 1.90 | -0.96% | -9.3% | 1.90 | 3 |
| Midcap RTH fade ($2-15, 09:30-16:00) | 6 | 0.45 | -1.28% | -7.2% | 1.30 | 1 |
| Extended hours (≥16:00) | 7 | **2.72** | **-2.26%** | **-16.4%** | 2.46 | ~3 (varies) |
| Premarket (<09:30) | 4 | 0.62 | -0.50% | -12.6% | 1.18 | 1 |
| Winners (RTH 13:21 + 14:18) | 2 | **0.025** | -0.52% | -6.7% | 1.67 | — |

EH is the worst cluster on every metric. Median time-to-stop for RTH-fade losers is **1 minute** — the stop fires on the bar immediately after entry.

## 5. Findings — what distinguishes winners from losers

1. **Entry-bar volume is the strongest discriminator (huge effect size, n is small).**
   Winners: 53 / 7 shares (≈ 0% of prior 25-min mean). Losers: median 702 shares (68% of mean), with several entries on 5,000–18,000-share spike bars. **The two winners entered into thin tape vacuums; the losers entered into prints that were already moving.** This is the inverse of the directive's "one-print spike" hypothesis as applied to *losers* — losers had volume *on the entry bar*, but it doesn't sustain. Winners had no volume at all on the entry bar.

2. **Bar +1 volume tells you almost nothing.** Mean +1/entry ratio: 0.43 winners, 0.91 losers. Median 0.60 losers. The "+1 collapse" hypothesis (entry bar hot, +1 dead) does happen on some losers (FATN ×2: +1 ratio 0.00; ATRA 5/11 13:52: 0.72; LESL ×2: 0.00) but doesn't separate them from winners cleanly because winners' entry bars are too tiny to make a ratio meaningful.

3. **Distance from HOD is mildly predictive.** Losers' mean dist_HOD = −11.6%; winners' = −6.7%. The losers cluster further down the day's range — many are entering after the move has already happened and is now consolidating mid-range. EH losers are −16.4% from HOD, the worst slice.

4. **VWAP-reject pattern (`p1_vs_vwap_pct`)** is present in some losers (PIII +18.5% above VWAP at +1; XOS −16.2%; SLE −9.6%) but not consistent. Both losers and winners average close to VWAP. **Not a reliable single-feature filter.**

5. **Time-to-stop is brutal on losers:** median 1 min for midcap fades, ~3 min for penny and EH. The R-zone is hit on the immediate next bar in 6 of 21 losers. **This is the −1R-in-3-minutes signature the audit identified at the trade-table level — and it shows up on bar +1 in the tick reconstruction.**

6. **Range-collapse pattern is real but inconsistent.** Losers with high `range_collapse` (entry-bar range >> mean post bars +1..+3): TRAW 5/12 14:54 (22.2×), ENSC 5/12 08:16 (16×), SST 5/12 11:20 (high). But other losers show range *expansion* post-entry (ONDG 0.53), and ATRA 5/15 winner has DEAD post bars so range_collapse is undefined.

7. **Cum 5-min move:** losers' median cum5% is −1.12% — half of an R$ in the wrong direction within 5 minutes. Winners' cum5% is −0.52%, also negative. **Both winners are underwater at +5 min.** This is the most counter-intuitive finding: the winners did not look like winners at the 5-bar horizon. Both winners' 39-min and 148-min holds let the trade work through extended dead periods. Any filter that vetoes on "no move in 5 bars" would have flagged both winners as losers.

## 6. Falsification check

The hypothesis stated **losers enter on noise spikes that don't sustain; winners enter on moves with multi-bar confirmation.** What the tick data actually shows:

- **Inverted on entry bar:** *winners* entered on near-empty bars, *losers* entered on populated bars. The "noise spike" framing fits a subset of losers (PIII, XOS, ENSC 5/12 14:54, ODYS 5/13 19:02) but not most. Several losers (ATRA 5/11 13:52, FATN ×2, ATRA 5/12 13:51) had quiet entry bars and still lost.
- **No multi-bar confirmation on either side:** winners did not have a clean 3-bar uptrend before entry. SST 5/11 had ticks at exact same $3.7899 for 5 consecutive bars; ATRA 5/15 had 2 dead bars in the pre-window.
- **The actual distinguishing feature is structural, not behavioral on the entry bar itself:** winners entered when nobody else was trading (dead-tape vacuum), held through dead bars, and benefited from a slow drift up. Losers entered when the tape was active, and the active tape immediately reversed.

**Verdict: the hypothesis is partially supported but in an inverted form.** The "noise spike" pattern exists in a sub-cluster of losers (~30%, the EH and early-AM groups). The "multi-bar confirmation = winner" half is **falsified** — winners had no such confirmation. The only feature that cleanly separates is **entry-bar volume**, and it separates in the *opposite direction* from what the hypothesis predicted: lower vol → winner.

## 7. Proposed action

**Concrete proposal — vol-vacuum-prefer gate (LOW confidence):** add a soft gate that *prefers* (does not strictly require) entries where the trigger-bar tick volume in the 60 seconds before fill is < 30% of the prior 5-bar mean. Two of two natural winners this week pass this gate; ~12 of 21 losers fail it. This would have:

- Vetoed: PIII −$1,628, ONDG −$1,198, SLE −$713, ODYS 5/13 19:02 −$698, ENSC 5/12 14:54 −$519, XOS −$735 → ≈ −$5,500 saved
- Kept: SST +$2,090, ATRA 5/15 +$1,160 → both winners retained
- Mixed: NVOX (low entry vol, low cost loser — kept, −$37)

**Caveat (high importance):** n=2 winners is not a statistical population. This gate could be a sample-size artifact. The "dead-tape gate" already shipping (per the audit) addresses the same phenomenon from a different angle (low *bot-wide* tape activity, not low *entry-bar* volume) and the audit already flagged that it would have blocked ATRA 5/15. **A vol-vacuum gate is the inverse of the dead-tape gate**, which is alarming — they shouldn't both ship without resolving the conflict.

**Stronger, higher-confidence proposal (MEDIUM):** **block extended-hours WB entries entirely** until n>5 of EH winners exists. EH is 7/21 losers, mean −$1,026 each, mean cum5% −2.26%, peak_R −0.42. This cluster has no winners and the worst per-trade behavioral profile. The audit already recommended this; the tick-level data corroborates it strongly.

**Highest-confidence proposal (HIGH):** **the strategy has no clean entry-quality discriminator at n=2 winners.** Don't ship a filter; instead, gate WB to paper-only until either (a) more winners accumulate to validate the vol-vacuum signal or (b) the strategy is re-conceived. The trade table shows 21/23 losers — that is not a calibration problem, it's a structural one.

## 8. Limitations

- **n=2 winners is too few to validate any "winner profile" feature.** Every cluster statistic that uses winners is descriptive, not predictive. The entry-bar-volume difference (27× gap) is striking but on n=2 vs n=21 it's anecdote-strength, not edge-strength.
- **Entry-minute zero-volume can be an artifact of fill-tick-not-printing-to-tape.** Alpaca's tick feed may not include the bot's own fill. Both winners may have had a few hundred shares of "real" entry-bar volume that I'm missing. This shrinks the discrimination signal but does not flip it.
- **Tick cache may be incomplete on thin EH tape** (per `project_tick_cache_persistence_gap.md` — known 60% gap on some live data). The EH cluster's behavioral metrics could be systematically biased low on volume.
- **"Winner" definition.** Both winners are trailing_stop exits — they didn't hit a target, they were trailed by the bot's exit logic. The "winner" label is therefore a function of post-entry path luck combined with exit-mechanic correctness, not entry quality per se.
- **ATRA 5/15 is the controversial winner.** The audit flagged that the new dead-tape gate would have vetoed it. If the vol-vacuum-prefer gate I propose above is the inverse of that, the system would oscillate. This forensic does not resolve that tension; it sharpens it.
- **No `wave_id` was reconstructed from ticks.** The directive asked about deep-wave (30+) losers; I used time-of-day and price-bucket clusters as proxies. The audit's per-trade table already has the wave numbers.
- **Bar-reconstruction limitation:** 1-minute bars miss sub-minute mechanics. The PIII pattern (huge bar 16:17, larger bar 16:18, immediate retrace 16:19) is plausibly a 5-second slingshot; we wouldn't see the sub-bar fill mechanics here.
- **MEI and FCHL excluded per directive.** MEI was a manual injection; FCHL was a session-resume infra orphan. Including either would distort behavioral statistics.

---

**Bottom line:** the dataset of 23 WB fills (5/11–5/15) has *two* winners, and they share *one* unusual feature — they entered into tape vacuums where nobody else was trading. This is not what the original "winners have multi-bar confirmation" hypothesis predicted. The hypothesis is partially falsified. The strongest action this analysis supports is **blocking extended-hours WB entries** and **treating any "winner profile" filter with extreme caution given n=2.**
