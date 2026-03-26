# Backtest Report: YTD 2026 Morning Sessions (IBKR Data)
## Date: 2026-03-26
## Branch: v2-ibkr-migration

---

## Overview

YTD 2026 squeeze-only backtest on IBKR data, morning window (scanner sim_start to 12:00 ET), $30K starting balance, dynamic 2.5% equity risk per trade.

---

## Results: $30K → $150,221 (+400.7%)

| Metric | Value |
|--------|-------|
| Total P&L | +$120,221 |
| Return | +400.7% |
| Trades | 36 |
| Win Rate | 97% (34W / 1L) |
| Avg Winner | +$3,545 |
| Avg Loser | -$321 |

---

## Exit Reasons

| Reason | Count | Wins | P&L |
|--------|-------|------|-----|
| sq_target_hit | 24 | 24 | +$110,924 |
| sq_para_trail_exit | 11 | 10 | +$3,789 |
| sq_max_loss_hit | 1 | 0 | -$321 |

---

## Full Year Mega Backtest (Jan 2025 - Mar 2026)

Also completed overnight — 301 trading days on IBKR data:

| Metric | Value |
|--------|-------|
| Final Equity | $1,378,605 |
| Total P&L | +$1,348,605 (+4,495%) |
| Trades | 321 |
| Win Rate | 90% (285W / 31L) |
| Avg Winner | +$4,756 |
| Avg Loser | -$221 |
| sq_target_hit | 209/209 winners (+$1,303,721) |
| sq_para_trail_exit | 103 (72W/31L, +$41,707) |

---

## Context

These are the **baseline numbers** against which the evening session and dual-window results are compared (see `2026-03-26_session_windows_backtest.md`). All numbers use IBKR data — the unified scanner eliminates the Alpaca RVOL bug that invalidated all V1 batch backtests.
