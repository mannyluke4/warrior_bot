# DIRECTIVE — Micro-Pullback Early-Entry Trade Spreadsheet (for Manny's chart review)

**Requested by:** Manny, 2026-07-17
**Owner:** Cowork (Opus)
**Priority:** high — Manny is manually reviewing charts to find loser-vs-winner
patterns the stats couldn't surface.

## Context
We found the root cause of the sub-bot bleed: arms fire too late (median 59% of
the move, buying tops). The fix — early **micro-pullback** entry + tight
pullback-low stop + a trailing/big-R exit — flips the payoff right-side-up
(backtest 6/08–7/16: +$1,769 at +2R, robust optimum ~+3R / trail-0.5–1R).
See memory `project_subbot_early_entry`.

The open problem is **cutting the losers** (57% of entries never reach +1R). The
stats found float separates (winners ~3M, losers ~8M) but nothing else obvious.
Manny wants to **eyeball every trade's chart** to spot patterns — so he needs a
per-trade spreadsheet with each row colored **green (winner) / red (loser)**.

## Deliverable
An **.xlsx** at `cowork_reports/2026-07-17_mp_early_entry_trades.xlsx`
(+ a `.csv` twin for portability). One row per micro-pullback backtest trade,
**entire row fill green if winner, red if loser**, header row bold + frozen,
sorted by `date` then `entry_time` (chronological). Also produce a second tab (or
second file) sorted by `outcome_R` descending so the best/worst cluster.

## Winner/Loser definition (color rule)
Color by **whether the setup worked**, decoupled from exit choice:
- **GREEN (winner):** the trade reached **≥ +1R MFE** (max favorable excursion in
  R) before hitting its stop — i.e., the entry was into a real move.
- **RED (loser):** never reached +1R — stopped straight out (the population we're
  trying to filter).
Put the raw `mfe_R` in a column too so Manny can see near-misses.

## Columns (in this order)
1. `ticker`
2. `date`
3. `arm_time` (ET) — when the MicroPullbackDetector armed
4. `entry_time` (ET) — resumption-break fill
5. `exit_time` (ET)
6. `hold_min` — entry→exit minutes
7. `entry_price`
8. `stop_price`
9. `exit_price`
10. `R_dollars` = entry − stop
11. `R_pct` = R/entry × 100
12. `mfe_R` — max R reached after entry (the win/loss driver)
13. `mfe_price` — highest price after entry
14. `outcome_R` — realized R-multiple under the **trail-0.5R** exit (activate at
    +1R, trail 0.5R below high-water); also a column for the **fixed +3R** outcome
15. `pnl_dollars` — as booked in the backtest (+2R run)
16. `exit_reason`
17. `float_M` — from `scanner_results/float_cache.json`
18. `tick_density` — ticks/min in the 5 min before entry (liquidity proxy; compute
    from `tick_cache/<date>/<ticker>.json.gz`, UTC timestamps → ET)
19. `score` — detector score
20. `hour` — entry hour ET
21. `chart` — a TradingView-style reference string, e.g. `SKHX 2026-07-17` (or a
    hyperlink `https://www.tradingview.com/chart/?symbol=<ticker>` if easy)

## Data sources & how to get the missing fields
- **Trade list (122 trades):** `backtest_status/replay_subbot_mp_early_2R_2026-06-08_2026-07-16.json`
  — has `time`(entry), `entry`, `stop`, `exit`, `reason`, `pnl`, `score`, `symbol`,
  `date`. **It does NOT have `arm_time` or `exit_time`** — get those below.
- **arm_time / exit_time:** re-run the sim **per (symbol, date)** with the exact
  micro-pullback config and parse the timestamped log lines
  (`… ARMED …`, `🟩 ENTRY …`, `🟥 EXIT …`). Reproduction command per symbol:
  ```
  WB_SUBBOT_ARM_MODE=micro_pullback WB_SUBBOT_RISK_PCT=0.05 WB_MOVE_TARGET_R=2.0 \
  WB_MOVE_FIRESTORM_GATE_ENABLED=0 WB_REGIME_SHIFT_ENABLED=0 \
  ./venv/bin/python simulate_subbot.py <TICKER> <DATE> 07:00 20:00 \
     --ticks --tick-cache tick_cache/ --slippage 0.07 --no-fundamentals
  ```
  (Whole-window batch was `replay_subbot_universe.py --start 2026-06-08 --end
  2026-07-16 --variant A` with the same env — same result, but per-symbol gives
  you the timestamped ARMED/ENTRY/EXIT lines to parse.)
  *Cleaner alternative:* add a one-line trade-ledger emit to `simulate_subbot.py`
  that prints `TRADE_LEDGER {json}` with arm/entry/exit ts + prices, then parse that.
- **mfe_R / mfe_price / tick_density:** compute from `tick_cache/<date>/<ticker>.json.gz`.
  Cache files are **multi-member gzip** — read with `gzip.open(path,'rt')` and, on
  `BadGzipFile`, fall back to `zlib.decompress(open(path,'rb').read(), 31)` (this is
  the fix already in `simulate_subbot.py`). Timestamps are UTC; ET = UTC−4 for this
  window.
- **float_M:** `scanner_results/float_cache.json` (values may be shares or millions —
  normalize).

## Tooling note
`openpyxl` is **not installed** in the venv. Either:
`./venv/bin/pip install openpyxl` (preferred — enables row fills + frozen header),
or build a Google Sheet, or emit CSV + a `.md` note on how to apply the row-color
conditional format. Row fill: green `FFC6EFCE`, red `FFFFC7CE` (Excel standard).

## Reference scratch scripts (already written, on the CC session box)
`/private/tmp/.../scratchpad/` has `giveback.py`, `loser_filter.py`,
`target_sweep.py` — reuse the tick-loader and outcome logic from those.

## Acceptance
- 122 rows (or however many trades the config produces), every row colored,
  all 21 columns populated (blank only where genuinely unavailable, e.g. missing
  float coverage — flag those).
- Commit the .xlsx + .csv to `cowork_reports/` and note the path back to CC/Manny.
