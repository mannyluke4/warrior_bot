# CC Report: Ross Exit V2 Targeted Backtest — Jan 2025 Overlap Stocks
## Date: 2026-03-23

---

### Results Table

| Symbol | Date | Baseline P&L | V2 P&L | Delta | Ross P&L | V2/Ross % | Key Exit Signals |
|--------|------|-------------|--------|-------|----------|-----------|------------------|
| **ALUR** | 2025-01-24 | +$1,989 | **+$7,578** | **+$5,589** | +$47,000 | 16.1% | ross_doji_partial at 18R (was sq_target at 4R) |
| **AIFF** | 2025-01-14 | +$8,592 | **+$7,632** | -$960 | -$2,000 | Won | ross_doji_partial (10.3R, 5.8R); MACD backstop caught trade 2 |
| **INM** | 2025-01-21 | +$2,414 | **-$799** | -$3,213 | +$12,000 | -6.7% | sq_max_loss_hit x2 — Ross exit blocked sq_target_hit |
| **VMAR** | 2025-01-10 | +$107 | **-$500** | -$607 | +$1,361 | -36.8% | sq_stop_hit — Ross exit blocked sq_para_trail |
| **SLXN** | 2025-01-29 | +$255 | **+$466** | **+$211** | ~+$5,000 | 9.3% | ross_topping_tail_warning, ross_cuc_exit |
| YIBO | 2025-01-28 | $0 (0 trades) | $0 (0 trades) | $0 | +$5,724 | N/A | No entry signals — detector issue, not exit |
| WHLR | 2025-01-16 | $0 (0 trades) | $0 (0 trades) | $0 | +$3,800 | N/A | No entry signals — detector issue, not exit |
| ATPC | 2025-01-13 | $0 (0 trades) | $0 (0 trades) | $0 | ~BE | N/A | No entry signals — detector issue, not exit |
| **Totals (traded)** | — | **+$13,357** | **+$14,377** | **+$1,020** | — | — | — |

### Regression (from prior directive, Ross V2 ON)
- VERO: +$17,447 (baseline +$18,583 with Ross OFF — not comparable; V1 was +$13,433)
- ROLR: +$24,191 (baseline +$6,444 with Ross OFF — V2 dramatically outperforms; V1 was +$238)

---

### Key Observations

#### 1. ALUR — THE Win (+$5,589 improvement)
V2 dramatically improved ALUR. Trade 1 entered at $8.04 via squeeze and:
- **Baseline**: sq_target_hit at $8.40 (4.1R) — mechanical target exit
- **V2**: ross_doji_partial at $10.61 (18.0R) — held through the run, doji warning at the right time

This is exactly what V2 was designed for. The squeeze target was cutting the runner at 4R, while Ross exit let it ride to 18R. Still far from Ross's $47K but that gap is entry timing + scaling, not exit logic.

#### 2. INM/VMAR — Regression (design issue, not V2 bug)
Both regressions are caused by the same root issue: **Ross exit disables `sq_target_hit` (tick-level exit)**. When Ross exit is ON, squeeze trades skip the target check at line 666 of simulate.py. The trade hits its hard stop or dollar loss cap before the 1m bar closes and Ross exit gets to evaluate.

INM trade 1: entered $7.04, price spiked to ~$7.83 (would have hit sq_target) then reversed within the same 1m bar. Ross exit only evaluates on bar close, by which time the trade was underwater.

**Root cause**: Ross exit replaces ALL exit logic for squeeze trades, but squeeze trades have very fast intra-bar targets that must fire on ticks. This is a design gap — Ross exit should coexist with squeeze targets, not replace them.

**Recommended fix**: Keep `sq_target_hit` active even when Ross exit is ON. Ross exit handles everything AFTER the squeeze target fires (runner management, re-entry timing, etc.). The sq_target_hit is a pre-target mechanical exit that prevents giving back gains on fast spikes.

#### 3. AIFF — Slight regression (-$960)
Trade 1 improved: ross_doji_partial at $3.50 (10.3R) vs sq_target_hit at $2.66 (5.8R) — +$2,263 better.
Trade 2 regressed: ross_macd_negative at $4.02 (-0.4R) vs topping_wicky at $4.18 (-0.1R) — -$363 worse (MACD backstop fired).
Trade 4 from baseline doesn't appear in V2 (different trade sequencing after earlier exits).
Net: slight regression but within noise.

#### 4. SLXN — Improvement (+$211)
V2 replaced squeeze para_trail and topping_wicky exits with ross_topping_tail_warning and ross_cuc_exit. Small improvement. Trade 2 loss reduced from -$381 to -$238.

#### 5. YIBO/WHLR/ATPC — No trades
These stocks produced 0 entries in both baseline and V2. The gap vs Ross is an entry/detection issue, not exit timing.

---

### Verbose Log Summary (Priority 1)

#### ALUR (THE case study)
- **Baseline trade 1**: SQ entry $8.04 → sq_target_hit $8.40 at 07:04 (4.1R, +$1,765)
- **V2 trade 1**: SQ entry $8.04 → ross_doji_partial $10.61 at 07:20 (18.0R, +$7,850)
- V2 held 16 minutes longer, rode 14R more. Doji partial fired correctly on indecision candle.
- V2 trade 2: SQ entry $11.04 → sq_max_loss_hit at $10.92 (-$272). Quick reversal, dollar cap caught it.

#### INM (regression explained)
- **Baseline trade 1**: SQ entry $7.04 → sq_target_hit $7.83 at 07:33 (5.6R, +$2,788)
- **V2 trade 1**: SQ entry $7.04 → sq_max_loss_hit $6.92 at 07:33 (-0.9R, -$426)
- Same entry, same minute, opposite outcome. Price spiked to $7.83 then reversed below entry within the bar. sq_target_hit would have caught the spike; Ross exit waited for bar close and missed it.

#### AIFF
- **V2 trade 1**: $2.04 → ross_doji_partial $3.50 at 07:49 (10.3R, +$5,160) — excellent
- **V2 trade 2**: $4.21 → ross_macd_negative $4.02 at 09:14 (-0.4R, -$431) — MACD backstop correct but slightly worse than baseline's TW exit
- **V2 trade 3**: $4.61 → ross_doji_partial $5.38 at 09:37 (5.8R, +$2,903) — good

---

### Architecture Issue Found: Ross Exit vs Squeeze Targets

**Problem**: `simulate.py` line 666 gates squeeze target exits behind `not self.ross_exit_enabled`. When Ross exit is ON, squeeze trades lose their tick-level target exit and rely entirely on 1m bar-close signals. Fast intra-bar spikes (INM, VMAR) are missed.

**Impact**: INM: -$3,213 regression. VMAR: -$607 regression.

**Proposed fix**: Allow `sq_target_hit` to fire even when Ross exit is ON. Treat it as a hard mechanical exit (like stop_hit, max_loss_hit) that Ross exit does not replace. After the target fires, Ross exit manages the runner portion via 1m candle signals.

**This fix should be implemented before running the full YTD backtest with Ross exit ON.**

---

### Summary

| Metric | Value |
|--------|-------|
| Total baseline (5 stocks with trades) | +$13,357 |
| Total V2 (5 stocks with trades) | +$14,377 |
| V2 delta | **+$1,020 (+7.6%)** |
| V2 wins (improved) | 2 of 5 (ALUR +$5,589, SLXN +$211) |
| V2 losses (regressed) | 3 of 5 (AIFF -$960, INM -$3,213, VMAR -$607) |
| Root cause of regressions | Ross exit blocks sq_target_hit (design gap) |
| Potential if fix applied | +$4,840 (reverse INM/VMAR regression + keep ALUR/SLXN gains) |

**Verdict**: V2 exit timing is correct for MP trades (ALUR proves the concept). The regression on squeeze trades is a fixable architecture issue, not a signal hierarchy problem. Fix sq_target_hit coexistence before YTD run.
