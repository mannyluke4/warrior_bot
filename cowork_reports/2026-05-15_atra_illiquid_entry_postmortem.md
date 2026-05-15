# ATRA WB Entry — Illiquid-Tape Misfire Postmortem

**Date:** 2026-05-15
**Author:** CC
**For:** Cowork (Perplexity)
**Severity:** P1 — strategy gap that will cost real money when scaled up. Same trade today is ~−$600 unrealized at the time of writing; the same pattern with the same sizing on a thinner tape could easily be −$5–10K.
**Trigger:** Manny flagged the entry mid-session — "extremely low-volume stock, did not take its entrance at the bottom of any wave that I can see on the chart, candles are extremely thin."

---

## TL;DR

The engine wb_bot took a Wave Breakout long on ATRA at 13:21:04 ET — 5,524 shares @ $9.10, ~$50,000 notional. It is a **technically correct** entry per every existing rule: WB down-wave scored 8 ≥ 7 floor, R% 2.34% ≥ 1.5% floor, all chop-gate-v3 sub-gates returned `would_veto=N`, no in-session blacklist, post-09:45 cutoff.

It is **strategically wrong** for one reason that's not currently gated: **absolute liquidity was insufficient for the position size**. Avg bar volume = 1,090 shares/min. We bought 5× that in one limit. The "spike" the bot detected (4.33× relative volume) was a single thin-tape print, not real flow. Within 60 seconds of fill, price drifted back below entry on essentially zero volume.

This is a recurrent failure class — every WB winner from yesterday's persistence list (ATRA, SST, FCHL, etc.) has a low-float, low-absolute-volume midday profile. Today's MEI-shape directive recommendation will surface MORE of them. We need an absolute-liquidity floor before the next batch fires.

Current state: 5,524 ATRA @ $9.10 entry, last tick $8.99, **unreal ≈ −$608**. Stop $8.84 still ~1.7% below.

---

## What the bot saw

### Sequence of events

```
12:49:24  WB_ARMED  score=10  prov_entry=8.78  stop=8.7182  →  R%=0.70%  REJECT (R-floor)
13:00:17  WB_ARMED  score=7   prov_entry=8.73  stop=8.6882  →  R%=0.48%  REJECT (R-floor)
13:21:01  WB_ARMED  score=8   prov_entry=9.06  stop=8.8378  →  R%=2.34%  PASS
13:21:01  CG3 sub-gates (all pass):
            macd            = macd_ok           (enabled=Y)
            hod_recent      = hod_recent_ok     (enabled=N)
            dead_bounce     = strong_volume(ratio=4.33≥0.70)
                                                 (enabled=N — OBSERVE only)
            vol_followthrough = vol_ft_ok       (enabled=N)
            xsession_bl     = insufficient_history(0<3)
                                                 (enabled=N)
13:21:01  ENTRY  qty=5524  ibkr_signal=$9.05  R=$0.21  risk=$2199  notional=$49,992
13:21:01  FALLBACK BUY limit=$9.14  reason=stale_quote  (1% buffer above ibkr signal)
13:21:02  BROKER ORDER BUY 5524 @ $9.14
13:21:04  FILL @ $9.10  (4¢ price improvement vs limit)
```

The detector's WB strategy is: **observe up-waves to build context, score down-waves as long-entry setups, enter on the bounce that confirms the reversal.** This is well-documented and sane on liquid runners.

### The wave that the bot scored

The detector ran through 25 wave events on ATRA today:
- 9 up-wave observations (waves 1–17)
- 11 down-waves, 8 of them scored 3–6 (rejected)
- 1 down-wave scored 8 at 13:21:01 → ARM → ENTRY

The "8" score for wave 25:
- ~2% magnitude prior up-wave ✓
- HOD context (still below session HOD $9.81) ✓
- MACD direction OK ✓
- **Bounce-bar volume ratio 4.33×** ← this is what put it over the line

### What the bot didn't see

**The "4.33× volume" is a relative ratio on a 1,090-share baseline.** The bounce bar itself was ~4,700 shares — barely larger than our 5,524-share entry size. There was no actual liquidity surge; the multiplier is a fraction-of-a-fraction.

Setup A's tick audits around the same time:
```
13:18:10  ATRA  0 ticks in last 60s   last_price=$8.82
13:20:00  ATRA  CHART | O=8.82 H=8.82 L=8.82 C=8.82 V=1,400  vol_ratio=1.3x
13:21:01  ATRA  15 ticks in last 60s  last_price=$9.05    ← signal/entry bar
13:21:56  ATRA  6  ticks in last 60s  last_price=$8.99    ← drifted back below entry within 60s
13:22:56  ATRA  6  ticks in last 60s  last_price=$9.00
13:24:26  ATRA  3  ticks in last 60s  last_price=$9.06
13:24:26  ATRA  0  ticks in last 60s  (next minute)
```

**Price moved from $8.82 → $9.05 in ~3 minutes on essentially zero ticks**, then drifted back below entry on zero ticks. Classic thin-tape print spike. The bot's bar builder saw a 4.33× volume bar; the human eye sees three minutes of one trade prints over a 23¢ range.

---

## Why each gate passed

| Gate | Status | Reason it didn't catch this | What it would need to do |
|---|---|---|---|
| `WB_MIN_SCORE=7` | Pass (score=8) | Score weights wave structure + relative volume + MACD. None penalize absolute volume. | Add absolute-volume term to scoring, or veto outside scoring. |
| `WB_MIN_R_PCT=1.5%` | Pass (R%=2.34%) | The wider R came from a higher stop, not a wider real range — stop $8.84 is roughly the prior bar low. | R% is correct as a fill-quality check; not a liquidity check. Leave alone. |
| H#14 (pre-11 ET) | Pass (13:21 ET) | Past 11 ET. | Time-of-day gate is doing its job. |
| H#16 (`MIN_ENTRY_PRICE=$2`) | Pass ($9.06) | Price OK. | Leave alone. |
| H#11 (same-session BL) | Pass | First ATRA trade today. | Leave alone. |
| CG3 macd | Pass | MACD direction was fine. | Leave alone. |
| CG3 dead_bounce (enabled=N) | Observe only — `strong_volume` PASS classifier | "Strong volume" classified on RATIO not on absolute size. | Add absolute floor. |
| CG3 vol_followthrough (enabled=N) | `vol_ft_ok` | Designed for the next-bar volume *direction*, not absolute size. | Different sub-gate. |
| Pre-submit BP check (new today) | Pass | $50K notional ≤ available BP. | Working as designed. |
| `WB_ENTRY_TIME_CUTOFF_ET=19:30` | Pass (13:21) | Far from cutoff. | Working as designed. |
| **Absolute liquidity floor** | **DOES NOT EXIST FOR WB** | — | Need to add. |

The squeeze strategy has `WB_SQ_MIN_BAR_VOL=50000`. WB has no equivalent. The squeeze gate would have rejected this bar outright (4,700 shares < 50,000).

---

## The "we are the liquidity event" trap

Position sizing relative to ATRA's recent flow:

| Window | Volume |
|---|---|
| avg per minute (50-bar average) | ~1,090 sh |
| Bounce bar (the one that scored 4.33×) | ~4,700 sh |
| **Our BUY order** | **5,524 sh** |
| First minute after fill (13:21:56) | 6 ticks of unknown small lots, last_price down to $8.99 |

We bought MORE than the bar we thought was a "volume surge." Once the order rests on the book, market price *is* our limit until enough opposing flow shows up. In thin tape, that opposing flow doesn't arrive in the next 60-300 seconds, so we're stuck holding the highest print of the move and watching the bid drift down with no participation.

This is structurally indistinguishable from a deliberate pump-and-fade by a small player, except in this case the bot is the only player. **The strategy was designed for situations where we're a small fraction of the bar, not the bar itself.**

---

## What a fix would look like

### Proposal A — Absolute minimum bar volume on the bounce bar

```
WB_WB_MIN_BOUNCE_BAR_VOLUME=20000  # default
```

The bounce bar (the one that triggers the ARM after a scored down-wave) must have at least N shares traded. The ratio gate stays — it catches the case where N is met but flow is below recent norm. The absolute floor catches the case where ratio is met but everything is thin.

For today's ATRA: bounce bar ~4,700 < 20,000 → rejected before ARM. Saves the trade.

Tradeoff: misses some real opportunities on thin-but-real movers. 20,000 / minute is a conservative starting point; can be tuned by backtest. Cowork's WB-strategy backtest queue (Stage 1 of the WB scanner directive) could resolve this empirically.

### Proposal B — Sizing-as-fraction-of-recent-bar-volume

```
WB_WB_MAX_NOTIONAL_PCT_OF_AVG_BAR_VOL=0.5  # max position notional ≤ 50% of avg bar notional
```

For each candidate, compute `recent_bar_notional = avg_vol_50 × current_price`. Cap our position notional at 50% of that. For ATRA: 1,090 × $9.05 = $9,865 average per minute × 0.5 = $4,932 max position. We bought $50K — way over.

Pros: directly addresses the "we are the liquidity" problem. Self-tuning to each stock's regime.
Cons: WB winners on thin tape can still have value (yesterday's MEI was thin but a real winner); aggressive sizing-down here may cancel the persistence layer's edge entirely.

### Proposal C — Both A and B

Floor (A) rejects clearly-untradeable setups. Sizing (B) caps the rest. Catches both the "we are the only print" case AND the "we'd be 90% of the print" case. Defensive in depth.

### What I'd ship absent Cowork input

Proposal A only, gated env-disabled by default for the first 3 sessions:
```
WB_WB_MIN_BOUNCE_BAR_VOLUME_ENABLED=0
WB_WB_MIN_BOUNCE_BAR_VOLUME=20000
```

Observe-only, log "would have vetoed" for any current-design entries to validate the threshold. Then flip enabled=1 on Monday. Same pattern as the WB intraday adder rollout.

---

## Questions for Cowork

### Q1 — Which proposal (A / B / C / something else)?
A alone is simplest. B is more principled but interferes with persistence layer's design intent.

### Q2 — Threshold values
20,000 shares/bounce for A. 50% of avg bar notional for B. Where do these numbers come from? Currently: my intuition. Cowork's WB backtest queue could ground these in historical data.

### Q3 — Does this invalidate ATRA-class persistence carryovers?
The WB winners we identified yesterday (ATRA 5/8, SST 5/11, MEI 5/13, FATN 5/5) all had thin midday tape. If we add an absolute-volume floor, we'd block these too. **The persistence layer's value may be fundamentally smaller than the analysis suggested**, because the same illiquidity that filtered them out of the squeeze scanner is the thing that makes them risky to actually trade.

### Q4 — Current ATRA position
Should we manually flatten now? Position is −$608 unreal, stop is at $8.84 (~1.7% below current $8.99). Bot may manage it down to stop or recover. Defer to Manny's call.

### Q5 — Same logic on Setup A's squeeze
Squeeze already has `WB_SQ_MIN_BAR_VOL=50000`. Did today's SLE / LESL / QUCY entries pass that gate? Quick check: SLE morning bar vol 60K, LESL ~80K, QUCY ~250K. All comfortably above 50K. Squeeze gate is doing the right thing; we just need the analogue for WB.

---

## Files referenced

- `logs/2026-05-15_wb_bot.log` (the ATRA WB_ARMED + CG3 + ENTRY sequence)
- `logs/2026-05-15_daily.log` (Setup A's TICK AUDIT + CHART for ATRA showing the thin tape)
- `wave_breakout_detector.py` (where the scoring would need to gain an absolute-volume term)
- `bot_v3_hybrid.py:WB_SQ_MIN_BAR_VOL` (the squeeze analogue)
- `cowork_reports/2026-05-15_fchl_orphan_session_resume_failure.md` (today's other P0)
- `cowork_reports/2026-05-14_wb_filter_gap_feedback.md` (persistence-layer rationale)

---

## Status / Action

- ⏳ Position open at $9.10 / current $8.99, stop $8.84 — bot is managing per current rules
- ⏳ Cowork verdict on Proposal A vs B vs C
- ⏳ Threshold tuning awaits WB backtest data
- ⏳ Manny attaching chart screenshot for context

This is a quieter P0 than the FCHL orphan because no dollars are out of the budget yet — but the architectural lesson is identical: **the bot ran exactly to spec and made a trade no human would.** The spec was missing a check, and that check is what stands between "paper" and "real."
