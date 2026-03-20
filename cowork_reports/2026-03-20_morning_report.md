# CC Report: Morning Report 2026-03-20
## Date: 2026-03-20
## Machine: Mac Mini

### Overnight Results

**55-day YTD Backtest (Squeeze V2):**
- Total P&L: +$34,600 (+115.3%) on $30K
- 38 trades: 21 MP (+$15,330), 17 squeeze (+$19,270, 88% WR)

**85-day OOS Backtest (Sep-Dec 2025):**
- Total P&L: +$43,886 (+146.3%) on $30K
- 81 trades: 30 MP (-$799), 51 squeeze (+$44,685, 67% WR)
- Verdict: NOT OVERFIT — OOS exceeds in-sample

**Combined 139 days: +$78,486 on $30K starting equity**

### Live Bot Status — 2026-03-20

**Issue: Bot crashed on startup**
- Root cause: `market_scanner.py` was in `archive/scripts/`, `bot.py` line 20 imports it
- Stale `.pyc` in `__pycache__` was masking this; OOS commits invalidated the cache
- Error: `ModuleNotFoundError: No module named 'market_scanner'`
- Fix: Restored `market_scanner.py` to project root
- Bot restarted manually at 11:40 AM ET

**Current status (11:40 AM ET restart):**
- ARTL passed scanner: gap +21.5%, RVOL 3.0x, float 0.7M
- Bot subscribed and seeded (207 bars, EMA9=8.57, PM_HIGH=9.46)
- Rescan running for additional candidates
- Volume bug fix from yesterday confirmed working (ARTL passed RVOL filter)

### Discovery Timing Bias (P0 — identified by Cowork)

Cowork analysis revealed batch runners hardcode `sim_start="07:00"` ignoring per-stock discovery times. 40% of backtest trades (48/119) have lookahead bias worth +$35,787 in P&L. Fix is one-line change in both runners. Re-runs queued.

### Files Changed This Morning
- `market_scanner.py` — restored to project root (import fix)
- `cowork_reports/2026-03-20_morning_report.md` (this file)
