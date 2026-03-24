# CC Report: SQ + Ross Exit Coexistence — V3 January Comparison
## Date: 2026-03-24
## Machine: Mac Mini

### Regression — PASS
- VERO (baseline, all off): +$18,583

### Three-Way Comparison

| Metric | V1 (SQ only) | V2 (Ross only) | V3 (SQ+Ross) | V3 vs V1 |
|--------|-------------|---------------|-------------|----------|
| **Jan 2025 P&L** | +$3,423 | +$5,837 | +$3,121 | -$302 |
| Jan 2025 Trades | 32 | 29 | 32 | 0 |
| **Jan 2026 P&L** | +$16,409 | +$12,677 | +$13,212 | -$3,197 |
| Jan 2026 Trades | 17 | 16 | 17 | 0 |
| **COMBINED P&L** | **+$19,832** | **+$18,514** | **+$16,333** | **-$3,499** |

### KEY METRIC: sq_target_hit Exits Restored
- V2: **0** sq_target_hit exits (completely blocked by Ross guards)
- V3: **9** sq_target_hit exits (7 in Jan 2025, 2 in Jan 2026) — all 9 were winners, +$7,136 total

The coexistence fix is mechanically working — SQ takes its 2R targets again.

### Exit Reason Breakdown (V3)

**Jan 2025 (32 trades):**
| Exit Reason | Count | Wins | P&L |
|-------------|-------|------|-----|
| sq_target_hit | 7 | 7 | +$6,235 |
| ross_shooting_star | 3 | 2 | +$918 |
| ross_doji_partial | 2 | 2 | +$566 |
| ross_cuc_exit | 3 | 2 | +$272 |
| sq_max_loss_hit | 5 | 0 | -$1,468 |
| max_loss_hit | 4 | 0 | -$1,415 |
| sq_para_trail_exit | 4 | 0 | -$941 |
| ross_macd_negative | 2 | 0 | -$307 |
| ross_ema20_break | 1 | 0 | -$364 |
| sq_stop_hit | 1 | 0 | -$375 |

**Jan 2026 (17 trades):**
| Exit Reason | Count | Wins | P&L |
|-------------|-------|------|-----|
| ross_shooting_star | 2 | 2 | +$14,466 |
| ross_cuc_exit | 5 | 3 | +$1,447 |
| sq_target_hit | 2 | 2 | +$901 |
| ross_doji_partial | 1 | 0 | -$295 |
| sq_para_trail_exit | 2 | 0 | -$450 |
| sq_max_loss_hit | 1 | 0 | -$321 |
| max_loss_hit | 2 | 0 | -$443 |
| stop_hit | 2 | 0 | -$2,093 |

### Analysis

**Why V3 is LOWER than V1 (-$3,499):**

V3 adds Ross exit signals (CUC, MACD backstop, shooting star, doji, EMA20) which fire on 1m bar closes. For trades that DON'T hit the SQ 2R target, Ross signals can exit earlier than V1's mechanical trail. This is a double-edged sword:

1. **Ross signals cut losers faster** (good) — MACD backstop and EMA20 break exit underwater trades sooner
2. **Ross signals also cut runners** (bad) — CUC and doji fire on 1m pullbacks during strong moves, exiting before the mechanical trail would have let them run

The net effect across these 42 days is that Ross exits give back more on cut runners than they save on cut losers.

**Why V2 beat V1 on Jan 2025 (+$5,837 vs +$3,423):**

V2's Ross-only exits (without SQ mechanical targets) let some trades run much further because they didn't take the 2R target. Instead they held until a strong 1m reversal signal. On certain parabolic days this produced bigger wins — but it's less consistent.

### Verdict

1. **V3 coexistence fix is mechanically correct** — sq_target_hit exits are restored (9 trades, all winners, +$7,136)
2. **V3 does NOT beat V1** — combined V3 +$16,333 vs V1 +$19,832 (-$3,499)
3. **V2 is the best on Jan 2025** (+$5,837) due to letting runners run
4. **V1 is the best overall** (+$19,832) due to more consistent SQ mechanical exits
5. **Should NOT enable `WB_SQ_ROSS_COEXIST=1` in live config yet** — the interaction between Ross signals and SQ runner management needs more work
6. The Ross exit signals (CUC, MACD, etc.) are cutting runners that the SQ trail would have held longer. Consider: suppress Ross signals on SQ trades above a certain R-multiple (e.g., >3R), or only use Ross for MP trades

### Files Changed
- `simulate.py` — added `WB_SQ_ROSS_COEXIST` env var and modified 4 guard lines
- `.env` — added `WB_SQ_ROSS_COEXIST=0`
- `run_jan_v3_comparison.py` — V3 runner (V2 + coexist flag)
- `jan_comparison_v3_state.json` — V3 results
- `cowork_reports/2026-03-24_jan_comparison_v3.md` (this file)
