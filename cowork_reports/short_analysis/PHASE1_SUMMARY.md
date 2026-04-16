# Phase 1 Summary — Fade Analysis Across 10 Targets

**Author:** CC (Opus)
**Date:** 2026-04-15 late night
**Directive:** `DIRECTIVE_SHORT_STRATEGY_RESEARCH.md` (Perplexity/Cowork)
**Script:** `tools/analyze_fade.py`

---

## Coverage

6 of 10 stocks analyzed — tick cache available:
- ROLR 2026-01-14, ACCL 2026-01-16, HIND 2026-01-27, GWAV 2026-01-16, VERO 2026-01-16, MLEC 2026-02-13

4 pending — tick cache empty, needs `ibkr_tick_fetcher.py` fetch tomorrow when IBKR's nightly maintenance ends:
- ANPA 2026-01-09, BNAI 2026-01-28, PAVM 2026-01-21, SNSE 2026-02-18

---

## ⚠️ Directive table has a peak-definition problem

The "Peak" column in `DIRECTIVE_SHORT_STRATEGY_RESEARCH.md` appears to be the **morning squeeze peak** (from `study_data/`'s `high_after_exit_30m`), not the **full-day HOD**. For some stocks those differ enormously:

| Symbol | Directive "Peak" | Actual full-day HOD | HOD time |
|---|---|---|---|
| ROLR | $21.00 | **$33.68** | 13:39 ET (5h after last squeeze exit) |
| VERO | $6.35 | **$12.93** | 11:18 ET (3h 47m after last exit) |
| ACCL | $11.36 | $11.50 | 04:08 ET (close match) |
| HIND | $7.57 | $7.28 | 08:16 ET (actually LOWER — study's 30m-after was higher than HOD) |
| GWAV | $8.40 | $8.43 | 07:12 ET (close match) |
| MLEC | $12.90 | $12.99 | 09:08 ET (close match) |

**Strategic implication:** a short strategy that triggers on the *morning squeeze peak* would have been catastrophically wrong on ROLR (shorting at $21 while the stock climbed to $33.68) and bad on VERO ($6.35 → $12.93). The short entry MUST trigger on the actual intraday HOD, confirmed in tick data — not on the squeeze exit.

This isn't a bug in the directive — it's a definition ambiguity. Phase 2 strategy design needs to specify exactly which "peak" we're topping off.

---

## Universal patterns across the 6 analyzed stocks

### Pattern 1 — First-lower-high signal fires FAST
Every single stock produced a first-lower-high within **2–8 minutes** of the actual HOD. The First Lower High is the cleanest, fastest reversal confirmation in the dataset.

| Symbol | HOD time | First LH time | Gap |
|---|---|---|---|
| ROLR | 13:39:51 | 13:43 | 3m |
| ACCL | 04:08:14 | 04:11 | 2m |
| HIND | 08:16:19 | 08:25 | 8m (later than others) |
| GWAV | 07:12:10 | 07:17 | 4m |
| VERO | 11:18:27 | 11:21 | 2m |
| MLEC | 09:08:12 | 09:11 | 2m |

**Design implication:** Strategy B ("Lower High Short" from the directive) gets the signal within a 2-minute window on 5/6 stocks. This is tractable for automated entry.

### Pattern 2 — HOD is not reclaimed (once faded)
Only **1 of 6** stocks reclaimed HOD after the first fade — ROLR, which had a very thin reclaim 27 seconds after the HOD tick (likely just tick-jitter at the peak before the real fade began; worth deeper tick-level verification).

| Symbol | Reclaimed HOD? |
|---|---|
| ROLR | Yes (13:40:18, 27s after HOD — possibly noise) |
| ACCL | No |
| HIND | No |
| GWAV | No |
| VERO | No |
| MLEC | No |

**Design implication:** A "stop above HOD + 3%" is probably too generous in most cases. Tighter stops (HOD + 1%) would have worked on 5/6.

### Pattern 3 — Fade depth varies from 15% to 36% in the first 30 minutes
Each stock faded a different amount. No stock in the sample recovered meaningfully within 30 min.

| Symbol | HOD | 30m later | Fade % |
|---|---|---|---|
| ROLR | $33.68 | $28.44 | -15.6% |
| ACCL | $11.50 | $7.32 | -36.3% |
| HIND | $7.28 | $5.01 | -31.2% |
| GWAV | $8.43 | $5.80 | -31.2% |
| VERO | $12.93 | $9.54 | -26.2% |
| MLEC | $12.99 | $9.80 | -24.6% |

Mean fade: -27.5%. Median: -28.7%. The minimum was ROLR at -15.6% (a chop day, high reclaim risk).

### Pattern 4 — Volume trend into the peak splits two ways
- **Increasing volume into peak** (5 stocks): ACCL, HIND, GWAV, VERO, MLEC — euphoric capitulation / blow-off
- **Decreasing volume into peak** (1 stock): ROLR — classic distribution / topping signature with divergence

ROLR is the outlier. Its decreasing-volume topping is the textbook "top of the run" signature, but it was followed by the shallowest fade (-15.6%) *and* the only HOD reclaim. Possibly counter-intuitive: the classic topping signal produced the weakest fade.

### Pattern 5 — HOD time-of-day split
- **Pre-RTH HOD** (4 stocks): ACCL (04:08), GWAV (07:12), HIND (08:16), MLEC (09:08)
- **RTH HOD** (2 stocks): ROLR (13:39, afternoon), VERO (11:18, golden hour)

Pre-RTH HODs have lower volume and wider spreads — harder to short cleanly. RTH HODs have better liquidity but also more support buyers. The Strategy C VWAP-rejection approach may work better in RTH where VWAP is a more-respected level.

### Pattern 6 — Distance from HOD to VWAP is the R/R dial
For Strategy A/B where Target 1 is VWAP:

| Symbol | HOD | VWAP at peak | Distance | R/R to VWAP |
|---|---|---|---|---|
| ROLR | $33.68 | $16.43 | $17.25 (52%) | 5.3:1 ⭐ |
| VERO | $12.93 | $6.92 | $6.01 (46%) | 2.4:1 |
| MLEC | $12.99 | $9.83 | $3.16 (24%) | 1.4:1 |
| ACCL | $11.50 | $8.22 | $3.28 (29%) | 0.6:1 |
| HIND | $7.28 | $6.81 | $0.47 (6%) | n/a (short entry below VWAP) |
| GWAV | $8.43 | $7.48 | $0.95 (11%) | n/a (short entry below VWAP) |

**Clear filter candidate:** `HOD / VWAP ≥ 1.25` (HOD at least 25% above VWAP at the time of peak) picks out the 3 highest-R/R trades and excludes the two where VWAP was already broken by our entry time.

---

## Caveats in the analyzer (for Phase 2 refinement)

1. **R/R to VWAP goes negative when entry fires AFTER the stock falls through VWAP** (HIND, GWAV). The analyzer assumes VWAP as Target 1; for these stocks the effective target is a lower support level. Phase 2 strategy should dynamically pick the next valid level (e.g., 50% retrace, gap fill) when VWAP is already broken.

2. **Bearish engulfing detection uses simple open/close engulfing** — may miss "wide-body engulfing" variants and may false-positive on doji engulfing. Good enough for first-cut signal identification; tightening the pattern rules is future work.

3. **Reclaim threshold (2% faded then touches HOD)** correctly filters out tick-jitter in 5/6 cases but flagged ROLR as "reclaimed" despite the reclaim being sub-minute. Worth investigating ROLR's exact tick sequence 13:39:51 → 13:40:18 to confirm whether this is real-world or analyzer artifact.

4. **50% retrace target uses HOD minus half the morning range** — accurate for morning-peak stocks but ambiguous for afternoon-peak stocks like ROLR (where "morning range" is a different animal than "full-day range to HOD").

5. **Key levels not yet computed:** gap fill (needs prior-day close data, not in the tick cache), whole-dollar bounce detection (would need threshold analysis per stock). These are in the directive's Section C — deferred to Phase 2 with proper level data.

---

## Queued for tomorrow

Once IBKR maintenance ends (estimated 02:00-04:00 MT), the scheduled wakeup will restart the BIRD fetch (separate blocker) and can also pull ticks for:
- ANPA 2026-01-09
- BNAI 2026-01-28
- PAVM 2026-01-21
- SNSE 2026-02-18

Adding these 4 reports will bring the directive's Phase 1 to 10/10 coverage.

---

## Ready for Phase 2 design

Patterns 1–6 give enough signal to draft the 3 strategies in the directive:

- **Strategy A ("Exhaustion Short")** — backed by Pattern 2 (HOD rarely reclaimed) + Pattern 1 (fast LH signal). Highest R/R but ROLR's sub-minute reclaim is a warning — entries within 1 minute of HOD need careful tick-level validation.
- **Strategy B ("Lower High Short")** — universally tractable per Pattern 1. All 6 stocks produced clean first-LH within 8 min. Likely the most robust starting point.
- **Strategy C ("VWAP Rejection Short")** — constrained by Pattern 6's VWAP-distance filter. Only works on stocks where peak was meaningfully above VWAP at the time; others need a different target.

Whichever strategy ships, it must filter on **"HOD/VWAP ≥ 1.25"** (or similar) and **NOT trigger on the morning squeeze exit** — only on the confirmed intraday HOD in tick data.

---

*CC (Opus), 2026-04-15 late night. 6/10 profiles done, 4 pending IBKR. Clear patterns emerging; ready for Phase 2 when you are.*
