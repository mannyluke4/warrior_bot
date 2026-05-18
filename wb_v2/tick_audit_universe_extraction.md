# WB v2 Stage 0 — Tick-Audit Universe Extraction

**Deliverable:** 3 (per `DIRECTIVE_2026-05-18_WB_V2_STAGE_0.md`)
**Date:** 2026-05-18
**Branch:** `v2-ibkr-migration`
**Author:** Cowork (Opus 4.7 / 1M context)
**Scope:** Research only. Read-only against production tick caches and bot heartbeat logs.
**Output:** `wb_v2/extracted_universe.csv` (993 rows, 81 sessions, 583 unique symbols).

---

## 1. Why this document exists

Manny, verbatim:

> "While I was watching what the squeeze bot was trading, I simply opened the chart on the stocks that had the most ticks that appeared in the tick audits."

That is the universe-selection mechanism Manny used to source WB v2 trades by hand. Stage 0 needs that selection mechanism captured in *tabular* form so Stage 1 can backtest the strategy against the same population Manny was already trading from his eye-ball.

This deliverable does the mining and produces the rankings under five candidate definitions of "most active":

| Candidate | Metric |
| --- | --- |
| `tick_rate_rank` | Total session ticks per symbol (this is the literal Manny-eyeball metric) |
| `volume_rank` | Total session dollar volume |
| `rvol_rank` | Current session volume / mean of prior 5 sessions' volume |
| `range_rank` | Intraday range as `(high − low) / open` |
| `composite_score` | Min-max-normalized average of the above four |

---

## 2. Data sources

### 2.1 Primary: `tick_cache/<DATE>/<SYM>.json.gz`

The squeeze-bot tick cache persists every raw trade record (price `p`, size `s`,
timestamp `t`) the bot observed per (date, symbol). The format is a gzipped
JSON array of `{"p": float, "s": int, "t": ISO-8601}` records. This is the
authoritative source for tick count, traded volume, OHLC, and intraday range
**for symbols the bot was subscribed to that day** (subscription comes from
the daily scanner watchlist + intra-day adder).

Coverage by date (qualifying ≥5 symbols cached):

| Date range | Sessions | Median symbols/session | Note |
| --- | --- | --- | --- |
| 2026-01-02 → 2026-03-12 | 50 | 6 | Sparse — pre-production backfill; only the daily winner symbol(s) cached |
| 2026-03-26 → 2026-04-22 | 17 | 50 | Production tick cache + the project_tick_cache_persistence_gap.md backfill |
| 2026-04-28 → 2026-05-18 | 14 | 75 | Live production, current state |

Of the 81 sessions captured, **31 have ≥15 fully-ranked symbols** (i.e. enough
to populate a meaningful top-20). All 30 most-recent qualifying sessions
(2026-03-30 → 2026-05-18) are in that 31. This satisfies the directive
acceptance criterion of 30+ sessions.

### 2.2 Cross-reference: `logs/<DATE>_daily.log`

The bot's per-minute heartbeat line carries per-symbol tick counts in the form
`SYM:NNNt/STATE`. Example from 2026-05-15:

```
[04:02:01 ET] ACTIVE | flat | daily=$+0 (0t) | conn=OK | ticks=115 | AEHL:10t/IDLE ATRA:1t/IDLE FCHL:1t/IDLE ...
```

41 such logs exist (2026-03-17 → 2026-05-18). Heartbeat tokens were parsed and
summed per (date, symbol) and recorded as `heartbeat_ticks` in the CSV for any
symbol that appeared in both the tick cache and the heartbeats.

The heartbeat is a sanity-check, not the primary source, because:

- The heartbeat universe is only the 10-15 symbols the bot was *actively
  watching*, not the broader cached universe.
- Heartbeats sample the live IBKR feed counter, which can drop ticks during
  reconnects (cf. `project_tick_cache_persistence_gap.md`).

Nonetheless, **on the 26 sessions where ≥4 symbols overlap both sources, the
Spearman rank correlation between heartbeat-derived tick counts and tick-cache
tick counts is 0.855**. The two agree about which symbol was busiest on a given
day. Heartbeat-derived ticks are kept in the CSV for transparency.

### 2.3 Sources NOT used and why

- `tick_cache_databento/` contains only mega-caps (AAPL, AMD, COST, …) cached
  for separate research. The bot's actual small-cap squeeze universe is not in
  there. Ignored.
- `tick_cache_alpaca/` only has 2026-05-06 → 2026-05-15 (the parallel Alpaca
  sub-bot ran for 8 sessions, per `project_alpaca_subbot.md`). Lower coverage
  than the primary cache and uses a different file naming scheme. Ignored to
  keep the comparison apples-to-apples.

---

## 3. Methodology

### 3.1 Tick-cache parsing

For every (`DATE`, `SYM`.json.gz) in 2026:

1. Decompress and JSON-parse the tick array.
2. Filter to regular trading hours: 09:30:00 ET → 19:59:59 ET inclusive (the
   bot trades the full 4 AM–8 PM ET extended session, but the universe ranking
   targets the RTH window Manny actually watches charts during; force-exit is
   19:55 ET so post-RTH activity is in any case excluded from the next-day
   universe).

   *Implementation note:* the regex above is keyed on UTC 13:30–19:59 since
   the bot writes timestamps in UTC. DST handling is correct because all
   covered sessions are in EDT (UTC−4) and the cutoff is checked in UTC.
3. Compute:
   - `total_ticks` = count of in-window records
   - `total_volume` = Σ `s`
   - `dollar_volume` = Σ `p × s`
   - `high / low / open / close` from RTH records
   - `range_pct` = `(high − low) / open`
4. Reject symbols with zero RTH ticks (sometimes the bot subscribed but the
   tape was dead all session).

### 3.2 RVOL approximation

The classic intraday-time-of-day RVOL would need bar-level history per
minute. We approximate by:

`rvol = today_total_volume / mean(prior_5_sessions_total_volume_for_same_symbol)`

This is computed in a single sequential pass over date-sorted sessions,
building per-symbol volume history on the fly. If fewer than 1 prior session
exists for a symbol, `rvol` is `NaN`. This is documented as a limitation;
**~40% of top-20 rows in the most recent month have NaN RVOL** because the
squeeze universe is fast-rotating (most symbols only appear once or twice).

For ranking purposes, NaN values sort last (`rvol_rank` = sentinel 9999 →
in the composite, NaN is imputed as the daily median for fairness).

### 3.3 Per-session ranking and composite

For each session, each of the four metrics is independently ranked descending
(min method for ties; rank 1 = most active). The composite score is then
computed by min-max normalizing each metric within the session to `[0, 1]` and
averaging:

```
composite_score = (norm_ticks + norm_dollar_vol + norm_rvol + norm_range) / 4
```

Higher composite = more active. Top-20 by composite per session is what gets
written to the CSV.

### 3.4 CSV output schema

`wb_v2/extracted_universe.csv` columns (in order):

| Column | Type | Description |
| --- | --- | --- |
| `date` | str | Session date, YYYY-MM-DD |
| `symbol` | str | Ticker |
| `total_ticks` | int | RTH tick count from tick_cache |
| `heartbeat_ticks` | int | RTH tick count summed from `<date>_daily.log` heartbeats (0 if no overlap) |
| `total_volume` | int | RTH shares traded |
| `dollar_volume` | float | RTH dollar volume |
| `rvol` | float | volume / mean(prior-5-sessions); blank if N/A |
| `range_pct` | float | (high − low) / open |
| `tick_rate_rank` | int | 1 = most ticks in session |
| `volume_rank` | int | 1 = most dollar volume in session |
| `rvol_rank` | int | 1 = highest RVOL; 9999 = NaN sentinel |
| `range_rank` | int | 1 = widest range |
| `composite_score` | float | min-max-normalized average, [0, 1] |

Sort order is `(date asc, composite_score desc)`.

---

## 4. Distribution statistics

### 4.1 Universe scale

| Metric | Value |
| --- | --- |
| Sessions covered | **81** (Jan 02 → May 18, 2026) |
| Sessions with ≥15 ranked symbols | **31** |
| Rows written | **993** |
| Unique symbols across the period | **583** |
| Median symbols ranked per session | 12 |
| Symbols / session for most recent 30 sessions (2026-03-30+) | 20 (full top-20) |

### 4.2 Top-15 most frequently in top-20

| Rank | Symbol | Top-20 appearances |
| --- | --- | --- |
| 1 | FATN | 13 |
| 2 | SST | 13 |
| 3 | KIDZ | 12 |
| 4 | ELAB | 7 |
| 5 | BATL | 7 |
| 6 | SKYQ | 7 |
| 7 | CLNN | 7 |
| 8 | FEED | 6 |
| 9 | CISS | 6 |
| 10 | CRCG | 6 |
| 11 | AEHL | 6 |
| 12 | SMX | 5 |
| 13 | MNTS | 5 |
| 14 | ELPW | 5 |
| 15 | RBNE | 5 |

**Reading.** The squeeze universe is highly rotating. The most "frequent" symbol
appears in only 13 of 81 sessions — 16%. **No symbol is a stable resident of the
top-20 universe.** This is consistent with how Manny actually trades: he doesn't
have a fixed watchlist; he chases that day's most-active.

### 4.3 Top-5 daily turnover

For each adjacent session pair (n=80), we compute
`turnover = 1 − |yesterday_top5 ∩ today_top5| / 5`.

| Statistic | Value |
| --- | --- |
| Mean top-5 turnover | **0.958** |
| Median top-5 turnover | **1.000** |

In words: on a typical day, **4.8 of yesterday's top-5 are gone from today's
top-5**. The universe is essentially fresh every session. This is the key
operational insight for Stage 1 — the universe selector must rebuild
intra-session, not run off a fixed list.

---

## 5. Rank-metric correlation (do the metrics agree?)

This is the methodological question Stage 1 hangs on: if all four metrics rank
the same symbols at the top, the composite is redundant and we just pick one.
If they diverge, the composite is doing real work and each candidate definition
is exploring a different universe.

### 5.1 Spearman correlation on the **full population** (every symbol in every cached session, n ≈ 2,400)

```
                tick_rate_rank  volume_rank  rvol_rank  range_rank
tick_rate_rank           1.000        0.911      0.628       0.880
volume_rank              0.911        1.000      0.653       0.790
rvol_rank                0.628        0.653      1.000       0.602
range_rank               0.880        0.790      0.602       1.000
```

### 5.2 Spearman correlation on the **top-20 subset only** (n = 993)

```
                tick_rate_rank  volume_rank  rvol_rank  range_rank
tick_rate_rank           1.000        0.921      0.397       0.547
volume_rank              0.921        1.000      0.448       0.470
rvol_rank                0.397        0.448      1.000       0.303
range_rank               0.547        0.470      0.303       1.000
```

**Key findings.**

1. **`tick_rate_rank` and `volume_rank` are 0.92 correlated.** They are almost
   the same metric. This is good news for Manny's eye-ball: the symbol he saw
   "most ticks on the audit" was almost always also the highest-dollar-volume
   symbol. Picking one or the other for the Stage 1 universe selector won't
   change the population much.

2. **`rvol_rank` is the outlier.** Correlation with tick_rate drops to 0.40 on
   the top-20 subset and 0.63 on the full population. RVOL surfaces *previously
   sleepy* symbols whose volume just woke up — these are not necessarily today's
   absolute high-tick names. RVOL is the candidate definition most likely to
   *disagree* with Manny's eye-ball.

3. **`range_rank` partially agrees with ticks/volume (0.55 / 0.88).** The
   highest-tick symbols tend to also be the widest-ranging, but not always —
   some high-range symbols are low-tick choppers (a wide range on light volume
   is the classic fluctuation candidate, which is interesting for WB v2 in its
   own right).

4. Restricting to top-20 compresses the rank ladder and *reduces* correlations
   — the top-20 are already a busy population, so the differentiation gets
   noisier. The full-population numbers are the more honest read.

### 5.3 Heartbeat-vs-tick-cache agreement

For the 26 sessions where the bot's heartbeat captured ≥4 symbols that also
appeared in the cache, mean Spearman between heartbeat tick rank and
tick-cache tick rank is **0.855**. The two sources tell the same story about
which symbol was busiest.

---

## 6. Sample rows (5 most-recent full-coverage sessions, top-5 each)

### 2026-05-12

| Sym | Ticks | Vol | RVOL | Range% | Comp | tick_rk | vol_rk | rvol_rk | rng_rk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CNCK | 70,732 | 14,411,181 | 26.71 | 0.184 | 0.570 | 1 | 2 | 3 | 12 |
| NVOX | 24,734 | 2,034,951 | 1.13 | 0.034 | 0.349 | 2 | 1 | 13 | 48 |
| SNDQ | 79 | 44,700 | 447.00 | 0.146 | 0.299 | 21 | 14 | 1 | 19 |
| BWEN | 154 | 86,100 | (NaN) | 0.801 | 0.253 | 12 | 23 | 36 | 1 |
| ERNA | 113 | 28,500 | 0.003 | 0.743 | 0.235 | 15 | 16 | 31 | 2 |

### 2026-05-13

| Sym | Ticks | Vol | RVOL | Range% | Comp | tick_rk | vol_rk | rvol_rk | rng_rk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| VNET | 231,171 | 59,620,426 | 298,102.13 | 0.101 | 0.755 | 1 | 1 | 1 | 26 |
| TDIC | 141 | 83,700 | 2.64 | 4.988 | 0.250 | 17 | 15 | 9 | 1 |
| MEI | 70,189 | 7,444,633 | (NaN) | 0.624 | 0.143 | 2 | 2 | 42 | 2 |
| NVOX | 18,379 | 1,339,541 | 0.72 | 0.024 | 0.029 | 3 | 3 | 15 | 48 |
| PLSM | 48 | 12,500 | (NaN) | 0.436 | 0.022 | 34 | 42 | 42 | 3 |

### 2026-05-14

| Sym | Ticks | Vol | RVOL | Range% | Comp | tick_rk | vol_rk | rvol_rk | rng_rk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QUCY | 103,328 | 28,373,217 | (NaN) | 0.233 | 0.563 | 1 | 1 | 52 | 6 |
| AEHL | 35,172 | 5,285,375 | 121.32 | 0.540 | 0.518 | 4 | 4 | 3 | 3 |
| LESL | 78,176 | 11,987,120 | (NaN) | 0.364 | 0.438 | 2 | 2 | 52 | 4 |
| MOBX | 44,421 | 11,258,067 | (NaN) | 0.272 | 0.297 | 3 | 3 | 52 | 5 |
| AIIO | 117 | 138,000 | 3.26 | 0.945 | 0.258 | 10 | 12 | 9 | 1 |

### 2026-05-15

| Sym | Ticks | Vol | RVOL | Range% | Comp | tick_rk | vol_rk | rvol_rk | rng_rk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QUCY | 322,173 | 76,418,330 | 2.69 | 1.004 | 0.671 | 1 | 1 | 23 | 2 |
| ONDG | 20,780 | 7,277,132 | 319.64 | 0.302 | 0.362 | 4 | 4 | 1 | 9 |
| CORD | 20,138 | 11,332,175 | 302.35 | 0.058 | 0.321 | 5 | 3 | 2 | 43 |
| SLE | 169,615 | 19,769,331 | 6.18 | 0.249 | 0.287 | 2 | 2 | 14 | 11 |
| PIII | 205 | 53,400 | 0.53 | 1.490 | 0.251 | 13 | 18 | 35 | 1 |

### 2026-05-18

| Sym | Ticks | Vol | RVOL | Range% | Comp | tick_rk | vol_rk | rvol_rk | rng_rk |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GOVX | 442,523 | 84,087,666 | (NaN) | 0.731 | 0.734 | 1 | 1 | 65 | 2 |
| SBFM | 164,687 | 58,392,411 | (NaN) | 0.783 | 0.421 | 2 | 2 | 65 | 1 |
| RBLU | 61 | 16,000 | 53.33 | 0.081 | 0.276 | 26 | 32 | 1 | 30 |
| SEGG | 84 | 45,700 | 26.88 | 0.190 | 0.187 | 21 | 34 | 3 | 11 |
| HIVE | 96 | 122,800 | 29.24 | 0.135 | 0.181 | 19 | 17 | 2 | 18 |

A few interpretive notes on the samples:

- 2026-05-13: VNET is the textbook case — top by every metric except range (it
  ran ranks 1/1/1/26). MEI is what a known winner looks like in the data
  (ranked 2/2 by ticks and volume, big range, and aligns with the documented
  MEI 2026-05-13 winner from CLAUDE.md).
- 2026-05-15: QUCY's *Project tick cache persistence gap* day — 322K cached
  ticks. ONDG and CORD show how RVOL can surface a previously sleepy name
  that would not have made the top-5 on a pure tick-count basis.
- 2026-05-18: GOVX and SBFM are big-volume/ticks but RVOL is NaN (no prior
  cached volume history). RBLU at tick-rank 26 is in the top-5 *only because
  of RVOL* — 53× its prior baseline despite tiny absolute volume. This is
  exactly the kind of disagreement between metrics Stage 1 needs to resolve.

---

## 7. Which metric most closely matches Manny's eye-ball?

**The literal answer, per Manny's own description, is `tick_rate_rank`** — he
said "stocks that had the most ticks." That is hard-coded as the top column to
sort by if we are mirroring what he was doing manually.

The empirical answer adds nuance:

- `tick_rate_rank` and `volume_rank` are so correlated (0.92) that they're
  functionally interchangeable for top-of-day selection. The squeeze tick audit
  uses tick count, so we stay with `tick_rate_rank` for direct equivalence with
  what was on Manny's screen.
- `rvol_rank` and `range_rank` find *different* names that are interesting but
  not the same names Manny was watching. They're useful as **secondary** sorts
  for finding fluctuation candidates the squeeze universe hasn't yet flagged —
  i.e. an exploration arm for Stage 1, not the primary recommendation.

**Recommendation, surfaced for Manny's review:**

1. **Primary universe definition for Stage 1 backtest:** top-N by
   `tick_rate_rank` (matches what Manny was doing). N = 10 keeps the universe
   tight; N = 20 widens it to include borderline names.
2. **Secondary track:** the composite top-N. Tests whether adding RVOL/range
   broadens the winners.
3. **Diagnostic-only:** RVOL-only and range-only top-N. Probably surfaces
   different stocks; not the recommended primary because they don't reflect
   the population Manny was actually trading from.

This recommendation is itself a Stage 1 hypothesis to test, not a foregone
conclusion. The deliverable here is the data to enable the test, not the
test's verdict.

---

## 8. Limitations and caveats

1. **RVOL is approximate.** A real time-of-day RVOL needs minute-bar history
   matched to the current minute of session. Our proxy is total-day-volume
   ratio over a 5-session window. For Stage 1 backtests we should rebuild RVOL
   from 1m bars (already feasible from the same tick cache by binning).
2. **Universe is bot-subscribed, not market-wide.** We are mining the bot's
   tick cache, which is gated by the squeeze scanner's watchlist (gap ≥ 10%,
   price 2-20, float ≤ 15M, etc., per CLAUDE.md). A stock that didn't pass the
   squeeze scanner but was a fluctuation winner is **not in this CSV**. WB v2
   should consider broadening the upstream scanner gates as a Stage 1 question.
3. **Pre-production sessions are sparse.** 2026-01 / 02 / early-03 sessions
   have only the bot's winning symbol(s) cached because the production tick
   cache only started persisting full universes from late March onward (see
   `project_tick_cache_persistence_gap.md`). The 31 sessions from 2026-03-26
   through 2026-05-18 are the high-quality window.
4. **Tick cache persistence gap.** Per memory, the live tick cache historically
   under-captured ~60% of session ticks. The 2026-04-30 IBKR backfill closed
   most of that gap on backfilled days. Sessions before the backfill have
   slightly suppressed tick counts; sessions after are clean. The ranking is
   robust to this because it's per-session ordinal.
5. **Heartbeat universe is narrower than tick cache.** The 0.855 heartbeat-vs-
   cache rank correlation is good, but heartbeat-only would only surface ~10-15
   symbols/day vs the 50-100 the tick cache holds. Tick cache is the right
   primary.
6. **Extended-hours activity is excluded** from the ranking metrics by design
   (RTH only) but premarket activity does drive who the bot subscribed to in
   the first place. If a stock was a 4-9 AM mover that calmed down by 09:30, it
   shows up with low RTH ticks here. For WB v2 charting Manny watches the 1m
   chart from market open, so RTH is the correct window.
7. **No survivorship bias correction:** delisted tickers within the window
   (none observed in this period) would not appear. Halt resumption symbols
   are included as-is.
8. **Adjacent-session top-5 turnover (95.8%)** is computed across the full set
   of 81 sessions including the early sparse months. Recomputing on just the
   31 well-populated sessions yields turnover ≈ 0.85 — still very high. The
   universe is genuinely fresh daily.

---

## 9. Files produced

| Path | Purpose |
| --- | --- |
| `wb_v2/extracted_universe.csv` | 993 rows of per-session top-20 with all 4 ranks + composite |
| `wb_v2/extracted_universe_stats.json` | Machine-readable distribution + correlation stats |
| `wb_v2/build_extracted_universe.py` | Reproducible build script (read-only on prod data) |
| `wb_v2/tick_audit_universe_extraction.md` | This document |

To reproduce:

```bash
cd /Users/duffy/warrior_bot_v2
venv/bin/python wb_v2/build_extracted_universe.py
```

The script is idempotent — re-running just overwrites the three output files.

---

## 10. What this enables for Stage 1

1. **Backtest universe defined.** Stage 1 entry-signal backtests can iterate
   over `extracted_universe.csv`, joining symbol/date back to the tick cache
   for the actual 1m bars and tick stream. No fresh scanning needed.
2. **Universe-selector hypothesis testing.** Stage 1 can A/B/C/D the four
   ranking metrics + composite to determine which best separates winners from
   losers on the wave-reversal setup. The CSV already carries all five rankings
   in one row, so this is a `groupby` operation, not a re-extraction.
3. **Symbol-frequency floor.** The 583-unique-symbols-across-81-sessions number
   tells us Stage 1 needs a strategy that generalizes across symbols — there's
   not enough per-symbol data for a per-ticker model. The strategy must be
   *symbol-agnostic* and key off setup geometry, exactly the v2 thesis.
4. **Daily refresh confirmed mandatory.** 95.8% top-5 turnover means the
   universe selector cannot be a static watchlist. Stage 1 backtests should
   refresh the universe every session morning before market open.

---

## 11. For Manny's review

Two questions for the next sync, both explicit:

> **(a)** Is `tick_rate_rank` the right primary universe selector for the
> Stage 1 backtest, given it's the literal metric you eyeballed? Or do you
> want the composite as primary (and tick-rate as a secondary)?

> **(b)** Should the Stage 1 backtest universe be top-10, top-20, or
> something else? Top-10 is a tighter, higher-conviction list; top-20 covers
> more of the daily activity and gives the strategy more shots. The CSV holds
> top-20 already; trimming to top-10 in the backtest is a one-line filter.

Both answers go directly into the Stage 1 directive.

---

**End of Deliverable 3.**
