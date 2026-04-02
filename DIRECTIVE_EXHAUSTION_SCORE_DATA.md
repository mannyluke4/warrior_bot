# Directive: Exhaustion Score — Full Data Gather

**Date:** 2026-04-02
**Author:** Cowork (Opus)
**Purpose:** DATA ONLY — no code changes. Gather the indicator data needed to design and validate an exhaustion score that gates whether 2R is treated as an exit or a promotion.
**Priority:** Before any implementation

---

## Background

Cowork's correct-exit study (see `cowork_reports/2026-04-02_correct_exit_study.md`) found that at the 2R target-hit moment:
- MACD, candle patterns, volume climax → do NOT distinguish done from runner
- **VWAP distance** (done +34.7% vs runner +9.7%) → STRONGEST signal
- **Bars into session** (done 120 vs runner 32) → STRONG signal

But the study only covered 2 done stocks and 8 runners (tick cache limitations). We need the FULL picture across all 35 target-hit trades before we can set thresholds.

---

## Task 1: Fetch Missing Tick Data

Three done stocks have no tick cache. Fetch from Databento and save to tick_cache:

```bash
# These are 3 of the 5 "correct exit" stocks — critical for threshold setting
# GV  2025-03-05   (GOOD_EXIT, +0.4R post)
# SNES 2025-03-13  (GOOD_EXIT, +0.0R post)
# DRMA 2025-03-27  (PERFECT_EXIT, -0.9R post)
```

Save as `tick_cache/YYYY-MM-DD/SYMBOL.json.gz` in the standard format.

If Databento doesn't cover these symbols (SPAC/micro-cap gap), document it and move on.

---

## Task 2: Run compare_exit_indicators.py on ALL 35 Target-Hit Trades

The script `compare_exit_indicators.py` already exists in the project root. It reads tick cache, builds 1m bars, and extracts MACD/volume/VWAP/candle state at the 2R bar.

Update the stock lists in the script to include ALL 35 sq_target_hit trades from `cowork_reports/post_exit_analysis.md`. Here they are, grouped by category:

### Done stocks (5 total — the ones that CORRECTLY stopped)

```python
done_stocks = [
    # (date, symbol, exit_time_utc_approx, entry_price, r_value, category, post_r)
    ("2025-03-28", "ATON", "11:07", 12.04, 0.47, "MODEST", 1.1),
    ("2025-05-29", "BOSC", "12:52", 6.04, 0.14, "MODEST", 0.6),
    ("2025-03-05", "GV",   "13:38", 2.39, 0.14, "GOOD_EXIT", 0.4),
    ("2025-03-13", "SNES", "11:09", 3.04, 0.14, "GOOD_EXIT", 0.0),
    ("2025-03-27", "DRMA", "12:32", 2.04, 0.14, "PERFECT_EXIT", -0.9),
]
```

### Runner stocks (30 total — the ones where 2R exit left money on table)

```python
runner_stocks = [
    ("2025-06-26", "CYN",  "11:06", 6.04, 0.14, "RUNNER", 242.0),
    ("2025-06-26", "CYN",  "11:07", 8.04, 0.14, "RUNNER", 234.9),  # 2nd entry
    ("2025-06-26", "CYN",  "11:16", 9.04, 0.14, "RUNNER", 228.1),  # 3rd entry
    ("2026-01-14", "ROLR", "12:19", 4.04, 0.14, "RUNNER", 121.4),
    ("2025-01-24", "ALUR", "11:04", 8.04, 0.14, "RUNNER", 84.7),
    ("2025-06-16", "STAK", "11:10", 3.04, 0.14, "RUNNER", 37.1),
    ("2025-06-02", "INM",  "11:01", 4.04, 0.14, "RUNNER", 32.3),
    ("2025-03-04", "RDGT", "13:01", 3.04, 0.14, "RUNNER", 12.5),
    ("2025-06-16", "STAK", "11:15", 7.04, 0.14, "RUNNER", 11.0),  # 2nd entry
    ("2025-02-04", "QNTM", "11:05", 5.04, 0.14, "RUNNER", 10.4),
    ("2026-03-18", "ARTL", "11:42", 5.04, 0.14, "RUNNER", 9.8),
    ("2025-07-17", "BSLK", "11:04", 3.04, 0.14, "RUNNER", 8.6),
    ("2026-01-08", "ACON", "11:01", 8.04, 0.14, "RUNNER", 8.0),
    ("2025-03-04", "RDGT", "13:03", 4.04, 0.14, "RUNNER", 7.4),   # 2nd entry
    ("2025-07-15", "SXTP", "11:02", 2.04, 0.11, "RUNNER", 7.2),
    ("2025-09-16", "APVO", "12:32", 2.04, 0.14, "RUNNER", 6.8),
    ("2025-02-03", "REBN", "11:01", 7.04, 0.14, "RUNNER", 6.3),
    ("2025-01-14", "AIFF", "13:31", 4.61, 0.13, "RUNNER", 5.5),
    ("2025-03-17", "GLMD", "13:43", 2.44, 0.14, "RUNNER", 5.5),
    ("2025-05-16", "AMST", "11:02", 4.04, 0.14, "RUNNER", 5.1),
    ("2025-08-19", "PRFX", "12:31", 2.04, 0.14, "RUNNER", 5.1),
    ("2025-02-24", "GSUN", "13:44", 4.28, 0.14, "RUNNER", 4.9),
    ("2026-01-26", "BATL", "11:05", 6.04, 0.14, "RUNNER", 4.1),
    ("2025-02-04", "QNTM", "11:06", 6.04, 0.11, "RUNNER", 4.0),   # 2nd entry
    ("2026-01-21", "SLGB", "11:17", 3.04, 0.14, "RUNNER", 3.7),
    ("2025-02-26", "ENVB", "13:38", 3.60, 0.14, "RUNNER", 3.6),
    ("2025-06-13", "AGIG", "14:38", 18.54, 0.14, "RUNNER", 3.3),
    ("2025-04-09", "VERO", "11:04", 12.04, 0.47, "RUNNER", 3.2),
    ("2025-08-01", "MSW",  "12:31", 2.04, 0.14, "RUNNER", 2.9),
    ("2025-06-13", "ICON", "11:26", 3.04, 0.14, "RUNNER", 2.7),
]
```

**NOTE:** The exit_time_utc values above are approximations (ET + 4 hours for EDT, +5 for EST). Cross-reference with the post_exit_analysis.md "ExitT" column which is in ET. Adjust for DST:
- Jan-Mar before 2nd Sunday: EST = UTC-5
- Mar 2nd Sunday onward: EDT = UTC-4
- Nov 1st Sunday onward: EST = UTC-5

The script finds the 2R bar by PRICE (`entry + 2*R`), so the approximate times are just fallback — price-based matching is more reliable.

---

## Task 3: For Every Stock, Extract These Fields

At the bar where price first hits the 2R target, capture:

| Field | Description | Source |
|-------|-------------|--------|
| `vwap_dist_pct` | `(close - cumVWAP) / cumVWAP * 100` | Built from ticks |
| `bars_into_session` | Number of 1m bars from first tick to 2R bar | Counter |
| `minutes_to_2r` | Wall-clock minutes from entry bar to 2R bar | Timestamps |
| `macd_val` | MACD line value | EMA(12) - EMA(26) |
| `macd_hist` | MACD histogram | MACD - Signal(9) |
| `hist_declining_3bar` | Were last 3 histogram values monotonically decreasing? | Boolean |
| `exit_vol` | Volume of the 2R bar | Ticks |
| `avg_vol_5bar` | Avg volume of 5 bars before 2R | Ticks |
| `vol_ratio` | `exit_vol / avg_vol_5bar` | Calculated |
| `pre_breakout_vol_avg` | Avg volume of 10 bars before the breakout bar (not the exit bar — the bar that started the move) | Ticks |
| `r_at_exit` | `(close - entry) / R` at the 2R bar | Calculated |
| `dist_from_hod_pct` | `(session_high - close) / session_high * 100` | HOD tracking |
| `candle_patterns` | List of patterns at exit bar (doji, shooting_star, bearish_engulfing, etc.) | Pattern detection |
| `prior_bar_patterns` | Candle patterns on the bar before exit | Pattern detection |
| `post_exit_vol_3bar` | Avg volume of 3 bars AFTER exit | Ticks |
| `vol_expanding_post` | Is post_exit_vol_3bar > exit_vol? | Boolean |
| `price_above_entry_3bar_later` | Is close 3 bars after exit still above entry? | Boolean |
| `float_m` | Float in millions (if available from sim fundamentals) | Alpaca/stored |
| `gap_pct` | Premarket gap % from prior close | Stored/calculated |
| `score` | Squeeze score at entry | Detector |

The last three (float, gap, score) may not be extractable from tick cache alone. If you can get them from the sim's detector output (run sim in verbose/debug mode), include them. If not, skip and note it.

---

## Task 4: Output Format

Save results as a JSON file AND a markdown summary table.

### JSON: `cowork_reports/exhaustion_score_dataset.json`

```json
{
  "generated": "2026-04-02T...",
  "trades": [
    {
      "symbol": "ATON",
      "date": "2025-03-28",
      "category": "MODEST",
      "post_r": 1.1,
      "vwap_dist_pct": 18.5,
      "bars_into_session": 180,
      "minutes_to_2r": null,
      "macd_val": 0.4524,
      "macd_hist": 0.0434,
      "hist_declining_3bar": false,
      "exit_vol": 422888,
      "avg_vol_5bar": 124259,
      "vol_ratio": 3.4,
      "pre_breakout_vol_avg": null,
      "r_at_exit": 1.5,
      "dist_from_hod_pct": 2.8,
      "candle_patterns": [],
      "prior_bar_patterns": ["doji", "bearish_close_low"],
      "post_exit_vol_3bar": null,
      "vol_expanding_post": null,
      "price_above_entry_3bar_later": null,
      "float_m": null,
      "gap_pct": null,
      "score": null
    }
  ]
}
```

Use `null` for any field you can't populate. Don't skip the trade.

### Markdown: `cowork_reports/exhaustion_score_summary.md`

A table with one row per trade, sorted by post_r (ascending — done stocks first, biggest runners last). Include columns: symbol, date, category, post_r, vwap_dist_pct, bars_into_session, vol_ratio, macd_hist, candle_patterns.

Then add a section that tests the proposed exhaustion score at different thresholds:

```
For threshold = 3:
  - Done stocks correctly flagged: X/5
  - Runner stocks incorrectly flagged (false exits): Y/30
  - Net $ impact: ...

For threshold = 4:
  - Done stocks correctly flagged: X/5
  - Runner stocks incorrectly flagged: Y/30
  - Net $ impact: ...
```

Calculate exhaustion score as:
```
score = 0
if vwap_dist_pct > 30: score += 3
elif vwap_dist_pct > 20: score += 2
elif vwap_dist_pct > 15: score += 1

if bars_into_session > 90: score += 2
elif bars_into_session > 60: score += 1

if pre_breakout_vol_avg and pre_breakout_vol_avg > 10000: score += 1
if r_at_exit > 8: score += 1
```

---

## Task 5: Also Run on Para Trail Exits (Bonus)

The 58 `sq_para_trail_exit` trades are 84% runners too. If time permits, run the same analysis on those trades to see if VWAP distance and time also predict runner status for para trail exits. Same output format — append to the JSON as separate entries.

This would give us data to decide: should the exhaustion score also gate para trail exits, or is it only relevant to target-hit exits?

---

## What NOT To Do

- **No code changes to any .py file**
- **No new env vars**
- **No changes to the bot, sim, or detector**
- Do NOT change any existing backtest behavior
- Do NOT run regression tests — this is purely data gathering

This directive produces DATA that Cowork will use to design the final exit strategy. Implementation comes in a separate directive after we review the numbers.

---

## Tick Cache Availability Checklist

From Cowork's scan, these stocks already have tick cache:

| Symbol | Date | Tick Cache? |
|--------|------|------------|
| ATON | 2025-03-28 | YES |
| BOSC | 2025-05-29 | YES |
| GV | 2025-03-05 | NO — fetch |
| SNES | 2025-03-13 | NO — fetch |
| DRMA | 2025-03-27 | NO — fetch |
| ROLR | 2026-01-14 | YES |
| CYN | 2025-06-26 | YES |
| STAK | 2025-06-16 | YES |
| ALUR | 2025-01-24 | YES |
| QNTM | 2025-02-04 | YES |
| ARTL | 2026-03-18 | YES |
| BSLK | 2025-07-17 | YES |
| INM | 2025-06-02 | YES |

For the remaining ~22 runner stocks, check `tick_cache/DATE/SYMBOL.json.gz`. If missing, fetch from Databento. If Databento doesn't have the symbol, note it as `"data_unavailable": true` in the JSON and move on.

---

## Deliverables

1. `cowork_reports/exhaustion_score_dataset.json` — full dataset, all 35 trades
2. `cowork_reports/exhaustion_score_summary.md` — sorted table + threshold analysis
3. Any newly fetched tick data saved to `tick_cache/`
4. Commit with message referencing this directive

---

*This directive is DATA GATHERING ONLY. Cowork (Opus) will review the output and write the implementation directive.*
