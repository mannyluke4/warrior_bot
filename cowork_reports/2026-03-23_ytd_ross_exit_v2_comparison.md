# CC Report: YTD 2026 Backtest — Ross Exit V2 vs Baseline
## Date: 2026-03-23

---

## 1. Top-Line Comparison

| Metric | Baseline (Ross Exit OFF) | V2 (Ross Exit ON) | Delta |
|--------|--------------------------|---------------------|-------|
| Total P&L | **+$25,709** | +$14,910 | **-$10,799** |
| Total Trades | 33 | 28 | -5 |
| Win Rate | 17/33 (52%) | 10/27 (37%) | -15pp |
| Profit Factor | 5.42 | 3.94 | -1.48 |
| Max Drawdown $ | $3,277 | $1,804 | -$1,473 (better) |
| Max Drawdown % | 5.9% | 3.9% | -2.0pp (better) |
| Largest Win | +$14,642 | +$12,981 | -$1,661 |
| Largest Loss | -$1,250 | -$806 | +$444 (better) |
| Avg Win | +$1,855 | +$1,998 | +$143 |
| Avg Loss | -$364 | -$298 | +$66 (better) |

**Verdict: V2 underperforms by -$10,799. DO NOT enable in live yet.**

---

## 2. Monthly Breakdown

| Month | Baseline P&L | V2 P&L | Delta |
|-------|-------------|--------|-------|
| Jan | +$18,170 | +$14,703 | -$3,467 |
| Feb | -$1,419 | -$827 | +$592 |
| Mar | +$8,958 | +$1,034 | -$7,924 |
| **Total** | **+$25,709** | **+$14,910** | **-$10,799** |

March is the worst month — V2 loses $7,924 vs baseline. The two biggest contributors are:
- CRE 2026-03-06: Baseline +$7,156 (sq_target_hit), V2 $0 (no trade — ross exit reduced trade count)
- MXC 2026-03-03: Baseline +$1,476 vs V2 +$519 (-$957)

---

## 3. Exit Reason Distribution

### Baseline (Ross Exit OFF)
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| bearish_engulfing_exit_full | 8 | +$12,515 | +$1,564 |
| sq_target_hit | 6 | +$12,832 | +$2,139 |
| topping_wicky_exit_full | 6 | +$2,928 | +$488 |
| sq_para_trail_exit | 7 | +$489 | +$70 |
| sq_max_loss_hit | 2 | -$425 | -$212 |

### V2 (Ross Exit ON)
| Exit Reason | Count | Total P&L | Avg P&L |
|-------------|-------|-----------|---------|
| ross_cuc_exit | 9 | +$1,163 | +$129 |
| ross_shooting_star | 4 | +$14,829 | +$3,707 |
| sq_stop_hit | 3 | -$1,105 | -$368 |
| ross_doji_partial | 3 | +$1,721 | +$574 |
| sq_max_loss_hit | 2 | -$415 | -$208 |
| max_loss_hit | 3 | -$656 | -$219 |
| ross_topping_tail_warning | 1 | -$6 | -$6 |
| ross_gravestone_doji | 1 | $0 | $0 |

**Key observation:** `sq_target_hit` generated +$12,832 in baseline but doesn't exist in V2. Ross exit disables it. This is the same architecture issue found in the targeted backtest — sq_target_hit is a tick-level exit that Ross exit blocks.

---

## 4. Head-to-Head: Biggest Deltas

| Date | Symbol | Baseline | V2 | Delta | Why |
|------|--------|--------:|-------:|------:|-----|
| 2026-01-21 | SLGB | +$3,690 | +$1,914 | -$1,776 | sq_target_hit → ross_cuc_exit (held too long) |
| 2026-01-16 | VERO | +$14,642 | +$12,981 | -$1,661 | BE at 18.6R → shooting_star at 17.3R |
| 2026-01-08 | ACON | +$582 | -$375 | -$957 | sq_target_hit → sq_stop_hit (target blocked) |
| 2026-03-03 | MXC | +$1,476 | +$519 | -$957 | TW exit at $16.30 → shooting_star at $16.00 |
| 2026-01-15 | SPHL | +$245 | -$364 | -$609 | sq_para_trail → sq_stop_hit (target blocked) |
| 2026-01-15 | CJMB | +$736 | +$1,171 | **+$435** | sq_target_hit → shooting_star (held longer, won!) |
| 2026-01-20 | POLA | +$165 | +$804 | **+$639** | sq_para_trail → ross_cuc (held longer, won!) |
| 2026-01-26 | BATL | +$730 | +$963 | **+$233** | 3 trades → 1 trade (doji partial, cleaner) |
| 2026-02-19 | RUBI | -$141 | +$53 | **+$194** | TW exit → CUC + shooting_star (2 trades, profitable) |

V2 wins: 7 dates | V2 loses: 17 dates

---

## 5. Robustness Check

| Metric | Baseline | V2 |
|--------|---------|-----|
| P&L without top 3 wins | +$1,771 | -$649 |
| Top 3 wins total | +$23,938 | +$15,559 |
| Longest losing streak (days) | 7 | 5 |
| Win/Loss count | 17W / 14L | 10W / 17L |

V2 goes negative without top 3 winners. Baseline stays positive. This indicates V2 is not robust enough yet.

---

## 6. Root Cause Analysis

### Primary cause: sq_target_hit disabled (-$12,832 lost revenue)

When `WB_ROSS_EXIT_ENABLED=1`, simulate.py line 666 skips the squeeze target check. Squeeze trades that would have hit their target (2R) within the entry bar instead run to their hard stop or dollar loss cap. This explains:
- ACON: +$582 → -$375 (target blocked)
- SPHL: +$245 → -$364 (target blocked)
- SLGB: +$3,690 → +$1,914 (target blocked, CUC caught later but at a lower price)
- SPRC: +$54 → -$366 (target blocked)

**sq_target_hit accounts for +$12,832 in baseline and $0 in V2.** If we re-enable sq_target_hit while keeping Ross exit for non-squeeze exits, the gap would narrow by roughly $6-8K (not all sq_target_hit trades would survive unchanged, but most would).

### Secondary cause: fewer trades in V2 (-5 trades)

V2 has 28 trades vs baseline's 33. Ross exit changes trade sequencing — a different exit time on trade 1 can prevent trade 2 from entering (cooldown, max entries). This cost V2 on profitable days like CRE 2026-03-06 (+$7,156 in baseline, $0 in V2).

### Tertiary cause: CUC fires too aggressively

`ross_cuc_exit` fires 9 times for only +$1,163 total (+$129 avg). Several CUC exits cut winners short:
- SLGB: CUC at +$1,914 when baseline held to sq_target +$3,690
- MOVE: CUC at -$806 when baseline BE at -$661

The strengthened CUC (≥2 higher-highs) is better than V1's single green bar check, but still fires on consolidation patterns that aren't true reversals.

---

## 7. Recommendations

### Must-fix before re-testing:

1. **Re-enable sq_target_hit when Ross exit is ON.** This is the single biggest fix. Keep `sq_target_hit` active as a tick-level mechanical exit (like hard stop, max_loss_hit). Ross exit handles everything AFTER the squeeze target fires. Estimated impact: +$6,000 to +$8,000.

2. **Investigate CUC false positives.** CUC fires 9 times at +$129 avg — barely profitable. Consider:
   - Increasing higher-highs requirement to ≥3
   - Adding a minimum R threshold before CUC can fire (e.g., only fire CUC below 2R)
   - Adding bar count minimum (CUC shouldn't fire in the first 5 minutes of a trade)

### Nice-to-have:

3. **VERO gap investigation.** Baseline gets +$14,642 (BE at 18.6R), V2 gets +$12,981 (shooting_star at 17.3R). The shooting_star fired 5 minutes before the BE would have. This is a correct signal — Ross would take the shooting star. The $1,661 gap is the cost of earlier exit, but it's the right methodology.

4. **Dynamic equity divergence.** Because V2 trails from day 1, its risk per trade is lower (2.5% of smaller equity). Over 55 days, this compounding effect amplifies the gap. A flat-risk comparison would show a smaller delta.

---

## 8. Summary

Ross Exit V2 is **not ready for live** in its current form. The -$10,799 underperformance is primarily caused by disabling `sq_target_hit` for squeeze trades, not by the signal hierarchy changes themselves.

The signal hierarchy (candles first, backstops last) is working correctly — shooting_star caught VERO at 17.3R, doji_partial caught BATL at the right time, and CUC prevented some losses. But the architecture issue of blocking squeeze targets overwhelms these gains.

**Next step: Fix sq_target_hit coexistence, then re-run this YTD comparison.**
