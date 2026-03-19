# CC Report: CHNR 2026-03-19 Backtest
## Date: 2026-03-19
## Machine: Mac Mini

### What Was Done
Ran CHNR backtest for 2026-03-19 (07:00-12:00 ET) in two modes: squeeze V2 (with parabolic + HOD gate + dollar cap) and MP-only for comparison. CHNR was today's top scanner candidate (gap 71%, RVOL 381x, float 0.52M).

### Commands Run

```bash
# Squeeze V2 (full settings):
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
WB_SCANNER_GAP_PCT=70.5 WB_SCANNER_RVOL=380.9 WB_SCANNER_FLOAT_M=0.52 \
python simulate.py CHNR 2026-03-19 07:00 12:00 --ticks -v \
2>&1 | tee verbose_logs/CHNR_2026-03-19_squeeze_v2.log

# MP-only (squeeze disabled):
WB_SQUEEZE_ENABLED=0 \
python simulate.py CHNR 2026-03-19 07:00 12:00 --ticks -v \
2>&1 | tee verbose_logs/CHNR_2026-03-19_mp_only.log
```

### Results

**Squeeze V2:**
```
    #    TIME    ENTRY     STOP       R  SCORE     EXIT  REASON                     P&L  R-MULT
  ───  ──────  ───────  ───────  ──────  ─────  ───────  ────────────────────  ────────  ──────
    1   07:18   5.0400   4.9000  0.1400    7.9   5.0400  sq_para_trail_exit          +0    +0.0R
    2   07:48   6.0400   5.9000  0.1400    6.7   6.1600  sq_para_trail_exit        +429    +0.9R

  Trades: 2  |  Wins: 2  |  Losses: 0  |  Win Rate: 100.0%
  Gross P&L: $+429  |  Avg R-Multiple: +0.2R
```

**MP-only:**
```
  No trades taken.
  Armed: 0  |  Signals: 0
```

### Key Observations

1. **Squeeze was the only way to trade CHNR.** MP never armed — the stock was too parabolic (extended green candles) and then fell below VWAP permanently after 08:00. Classic gap-and-fade.

2. **Trade 1 (07:18):** Volume explosion at $5.19 (3.9x avg), armed at $5.02 whole-dollar break. Entered $5.04 but the move stalled immediately — para trail exited at breakeven. No damage.

3. **Trade 2 (07:48):** Second volume spike at $6.17 (3.7x avg), armed at $6.02 whole-dollar break. Stock ran to $6.61 HOD, para trail locked in +$429 at $6.16. This was the last real momentum push.

4. **HOD gate correctly blocked everything after 08:00.** Multiple squeeze PRIMED events were rejected because bar highs were below the $6.61 HOD. The stock faded from $6.61 to $4.18 — any entry after 08:00 would have been a loss.

5. **Stock profile:** 573K ticks, 0 seed bars (no premarket bar data before 07:00). Gap was +30.9% by the time bars started. Float 0.52M = ultra-low, which explains the parabolic action and sharp fade.

6. **Scanner timing:** The aligned scanner discovered CHNR at the 08:00 rescan with gap +70.5%. By then, the best moves were already over (07:18 and 07:48). A premarket scanner would have caught it earlier — CHNR had 16.6M PM volume.

### Files Changed
- `verbose_logs/CHNR_2026-03-19_squeeze_v2.log` (new)
- `verbose_logs/CHNR_2026-03-19_mp_only.log` (new)
- `cowork_reports/2026-03-19_chnr_backtest.md` (this file)
