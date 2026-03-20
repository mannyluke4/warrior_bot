# CC Report: 2026-03-20 — What Should Have Been
## Date: 2026-03-20
## Machine: Mac Mini

### What Happened
The bot crashed on startup at 4:00 AM ET due to `ModuleNotFoundError: No module named 'market_scanner'` (file was in `archive/scripts/`, stale `.pyc` invalidated by overnight OOS commits). Bot was manually restarted at 11:40 AM ET — all morning setups were long gone.

### What Should Have Been (backtest simulation)

Scanner found 2 candidates with aligned Pillar criteria + precise discovery:
- **ANNA**: gap +21%, RVOL 2.2x, float 9.4M (Profile B), discovered premarket
- **RDGT**: gap +17%, RVOL 3.8x, float 5.1M (Profile B), precise discovery 10:03

The live bot also found **ARTL** (gap +18%, RVOL 3.0x, float 0.7M) at 11:40 but too late to trade.

### Backtest Results

| Stock | Gap | RVOL | Trades | P&L | Strategy |
|-------|-----|------|--------|-----|----------|
| ARTL | +18% | 3.0x | 3 | **+$1,054** | Squeeze |
| ANNA | +21% | 2.2x | 3 | **+$528** | Squeeze |
| RDGT | +17% | 3.8x | 0 | $0 | — |
| **Total** | | | **6** | **+$1,582** | |

### Trade Detail

**ARTL (3 trades, +$1,054):**
```
    #    TIME    ENTRY     STOP       R  SCORE     EXIT  REASON                     P&L  R-MULT
    1   09:09   8.0400   7.6600  0.3800   11.0   8.8000  sq_target_hit             +904    +1.8R
    2   09:41   9.5000   9.3600  0.1400   12.0   9.6200  sq_para_trail_exit        +316    +0.9R
    3   09:42   9.5000   9.3600  0.1400   10.7   9.4370  sq_para_trail_exit        -166    -0.5R
```

**ANNA (3 trades, +$528):**
```
    #    TIME    ENTRY     STOP       R  SCORE     EXIT  REASON                     P&L  R-MULT
    1   07:08   5.0400   4.9000  0.1400   12.0   4.9300  sq_max_loss_hit           -393    -0.8R
    2   10:14   5.0400   4.8300  0.2100    9.3   4.9600  sq_trail_exit             -190    -0.4R
    3   10:20   5.1300   4.9500  0.1800   10.5   5.4900  sq_target_hit            +1111    +2.2R
```

**RDGT (0 trades):**
- Exhaustion filter blocked MP (13.5% above VWAP)
- Squeeze had invalid R (no whole-dollar level in range)

### Key Observations

1. **All $1,582 came from squeeze** — micro pullback never armed on any stock today. Without squeeze, the day would have been $0 even if the bot had been running.

2. **ARTL squeeze at 09:09** was the money trade (+$904). Bot restart at 11:40 ET missed it by 2.5 hours.

3. **ANNA showed classic probe pattern**: two small losses (-$393, -$190) then one winner (+$1,111) that covered both. This is exactly how Ross trades — small stops, let the winner run.

4. **The `market_scanner.py` crash cost us +$1,582 today.** Fix is committed and pushed. Monday should run clean.

5. **Precise discovery worked**: RDGT was checkpoint-discovered at 10:30 but precisely discovered at 10:03 — 27 minutes earlier.

### Commands Run
```bash
# Scanner with precise discovery
python scanner_sim.py --date 2026-03-20

# Backtests (full settings, squeeze V2)
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py ARTL 2026-03-20 07:00 12:00 --ticks -v
python simulate.py ANNA 2026-03-20 07:00 12:00 --ticks -v
python simulate.py RDGT 2026-03-20 10:03 12:00 --ticks -v
```

### Files Changed
- `scanner_results/2026-03-20.json` — fresh scan with precise discovery
- `cowork_reports/2026-03-20_what_should_have_been.md` (this file)
