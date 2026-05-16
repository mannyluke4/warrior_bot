# Squeeze Historical Data Audit — Phase D2 (Combined Portfolio Backtest)

**Date:** 2026-05-16
**Branch:** `v2-ibkr-migration` (read-only audit; no code touched)
**Driving directive:** `DIRECTIVE_2026-05-17_GO_FOR_BUILD.md` Phase D2 + `DIRECTIVE_2026-05-17_COMBINED_PORTFOLIO_BACKTEST.md` §2.3 / §4 Agent 3
**Scope:** Verify Databento + local cache coverage for backtesting the squeeze strategy 2020-01-02 → 2024-12-31 alongside the framework
**Verdict (TL;DR):** **NO-GO without remediation.** Phase D2 finds material data gaps. Per directive §90, pausing and reporting before Phase D3 (combined backtest harness) is the correct call.

---

## 1. Verdict (one screen)

| Question | Answer |
|---|---|
| Can D3 run today on existing data? | **No.** |
| Is there a partial-coverage path? | **Yes, with caveats** — 2025-2026 only (~318 trading days, scanner_results + `tick_cache/`). Gives ~1.3 years of squeeze data, not 5. |
| Largest gap | **No squeeze universe seed for 2020-2024** (zero `scanner_results/*.json` pre-2025), **and** zero tick coverage in `tick_cache_databento/` for any small-cap squeeze candidate. |
| Estimated Databento data volume for a full 2020-2024 fetch (1k symbol-days, trades+bbo) | ~3 GB (cheap on Standard plan) |
| Larger blocker | **API quota is not the binding constraint.** The universe seeding + historical float problem is. |
| Recommended path | (1) Run D3 on 2025-2026 only as a Phase-D3a sanity run, OR (2) build a one-shot `EQUS.SUMMARY` historical scanner + Databento fetcher to reconstruct 2020-2024. Estimate Path 2 = ~1-2 days CC + ~3 GB data quota. |

---

## 2. Squeeze universe per day (estimate)

### 2.1 Source inventory

| Source | Path | Years covered | Usefulness for D3 |
|---|---|---|---|
| Live scanner output (per-date JSON) | `scanner_results/YYYY-MM-DD.json` | 2025-01-02 → 2026-05-15 (318 trading days w/ JSON) | Direct universe seed — only 1.3 years |
| IBKR scanner output | `scanner_results_ibkr/` | 2026-01-02 → 2026-03-25 (177 entries) | Subset of above |
| Historical scanner script | `ibkr_scanner.py::scan_premarket_historical` | Requires existing seed JSON — **cannot bootstrap pre-2025** | Dead-end without a seed source |
| Databento `EQUS.SUMMARY` ohlcv-1d ALL_SYMBOLS | API | 2018+ confirmed in `live_scanner.py:298-340` | **Bootstrap candidate** for historical universe |
| Float cache | `scanner_results/float_cache.json` (4,464 syms) + `universe_cache/framework_float_cache.json` (mega-cap 363 entries) | **Single snapshot; no date axis** | Look-ahead bias risk — see §5 |

### 2.2 Squeeze-passing candidates per quarter (2025 baseline)

Applied `.env`-default filters (`pm_price∈[$2,$20]`, `gap_pct≥10`, `relative_volume≥2`, `pm_volume≥50k`, `float_millions<30`) to the 318 days of `scanner_results/*.json`:

| Quarter | Trading days | Median symbols/day | Mean | P25 | P75 | Min | Max |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2025Q1 | 61 | 1 | 0.69 | 0 | 1 | 0 | 3 |
| 2025Q2 | 62 | 1 | 1.18 | 0 | 2 | 0 | 7 |
| 2025Q3 | 57 | 1 | 1.79 | 1 | 3 | 0 | 5 |
| 2025Q4 | 64 | 1 | 1.80 | 1 | 3 | 0 | 7 |
| 2026Q1 | 62 | 0 | 0.05 | 0 | 0 | 0 | 1 |
| 2026Q2 | 12 | 0 | 0.17 | 0 | 0 | 0 | 2 |

- **253 unique squeeze-passing symbols across 2025-2026.** That maps to ~430 sym-day events.
- 2026Q1/Q2 are anomalously sparse — the unified scanner v3 became markedly more selective. (Not a data gap; a config gap. Confirms the scanner's been tuned; doesn't help us pre-2025.)
- Extrapolating 2025-rate to 2020-2024 (1,259 trading days, mean ~1.4 sym/day): **~1,750 sym-day events, ~700-1,050 unique symbols** over the five-year window. This is the universe D3 needs and **none of it currently exists on disk.**

### 2.3 Why we can't just synthesize from `EQUS.SUMMARY`

`live_scanner.py` line 296-343 already calls `EQUS.SUMMARY` with `symbols="ALL_SYMBOLS"` for 21-day OHLCV + ADV at boot. The same call extended back to 2020 would provide:
- prev_close (gap calc)
- daily volume → ADV → RVOL proxy

But it's a 1-day cadence; we lose **premarket-only gap, premarket volume, and intraday RVOL-at-discovery-time**. Those need 1-second tbbo/trades pulls. That's the heavy lift in §3.

---

## 3. `tick_cache_databento/` coverage check

### 3.1 Existing inventory

36 symbol directories present — all mega/large-cap framework universe. Per-symbol audit:

```
Symbols with full ~5-year 1m bar coverage  (~1305 trading days): 26
Symbols with partial coverage (4-1321 1m days):  4   (JPM=4, MSFT=1321)
Symbols with NO bars (AMC, COST, KO, MA, MRK, PFE, T, VZ, WMT): 9
Symbols with trades schema present:  1  (AAPL, single day 2024-01-02)
Symbols with bbo-1s schema present:  1  (AAPL, same day)
```

**The framework cache is bar-only.** Per-symbol disk footprint for AAPL (1m × 5 yrs): ~32 MB. Trades for a single day: 1.16 MB. BBO for one day: 0.4 MB.

### 3.2 Squeeze-candidate cohort: 20-symbol probe

Sampled candidates documented in `CLAUDE.md` regression targets + `project_tick_cache_persistence_gap.md`:

| Symbol | Last seen in live | Cache in `tick_cache_databento/` |
|---|---|---|
| VERO | 2026-01-16 | **MISSING** |
| ROLR | 2026-01-14 | **MISSING** |
| KIDZ | 2026-04-15 | **MISSING** |
| MEI | 2026-05-13 | **MISSING** |
| ATRA | 2026-05-08 | **MISSING** |
| FCHL | 2026-05-15 | **MISSING** |
| MYSE | 2026-04-16 | **MISSING** |
| WLDS | 2026-04-20 | **MISSING** |
| QTTB | 2025-12-01 | **MISSING** |
| AHMA | 2026-01-13 | **MISSING** |
| AEI, CRIS, HOOK, MTVA, AGEN, GCDT, ICON, KBSX, FATN, ANPA | various 2025-2026 | **MISSING (20/20)** |

**0% squeeze candidate coverage in the Databento cache.** All historical squeeze ticks live in `tick_cache/` (IBKR `reqHistoricalTicks`, 273 date-folders 2025-01-02 → 2026-05-15, organized as `tick_cache/YYYY-MM-DD/<SYM>.json.gz`).

### 3.3 What this means for D3

The framework `BacktestEngine` consumes `TradeTick` / `QuoteTick` via `framework/data_adapters/databento_adapter.py:319-388`. Today that adapter only knows about parquet under `tick_cache_databento/<SYM>/{trades,bbo-1s}_<date>.parquet`. **It cannot read the IBKR `tick_cache/<DATE>/<SYM>.json.gz` shape.** Two options for D3:

1. Write a second adapter (`framework/data_adapters/ibkr_tick_cache_adapter.py`) that reads the IBKR shape and yields `TradeTick`s. This **unlocks 2025-2026 squeeze immediately** with no new fetches.
2. Re-fetch every squeeze-candidate sym-day from Databento `XNAS.ITCH` trades + `bbo-1s` and write to the existing parquet location. Cost analysis in §4.

Option 1 is the right move for the D3a sanity run. Option 2 is the right move for 5-year coverage.

---

## 4. Gap inventory + fetch budget

### 4.1 What's missing for 5-year coverage

| Slice | Sym-days est. | Schemas | Approx data size | Notes |
|---|---:|---|---:|---|
| Squeeze candidates 2020-2024 (per-day list TBD via §3) | ~1,750 | `trades`, `bbo-1s`, `ohlcv-1m` | ~2.8 GB trades+bbo, ~35 MB bars | Bottleneck: we don't know the symbol list yet |
| Daily universe seed (gap/ADV) 2020-2024 ALL_SYMBOLS | 1,259 days × 1 call | `ohlcv-1d` from EQUS.SUMMARY | ~50-200 MB | One bulk pull; same pattern as `live_scanner.py:307` |
| Squeeze candidates 2025 historical refetch | ~430 known sym-days | trades + bbo | ~700 MB | Optional — already have IBKR ticks; Databento for parity |

### 4.2 Estimated Databento API cost

Standard plan billing is per-GB returned. Conservatively:
- **Universe bootstrap:** 1,259 × ohlcv-1d × ALL_SYMBOLS ≈ 100 MB. <$10.
- **Per-candidate trades:** 1,750 sym-days × ~1.2 MB ≈ 2.1 GB.
- **Per-candidate bbo-1s:** 1,750 sym-days × ~0.4 MB ≈ 0.7 GB.
- **Per-candidate 1m bars:** 1,750 × ~20 KB ≈ 35 MB.
- **Total raw:** ~3 GB. On Standard plan billing, well under $100 budget. **Quota is not the constraint.**

### 4.3 Recommended pull strategy

1. **Phase D3a — sanity slice (2-3 hours CC):** stand up `ibkr_tick_cache_adapter.py`, run combined backtest on the 273 days we already have for 2025-2026. Validates harness wiring + squeeze-as-framework-plugin (Agent 1) end-to-end with **zero new fetches**.
2. **Phase D3b — universe reconstruction (overnight job, ~6-12 hours wall time):**
   - Pull `EQUS.SUMMARY` ohlcv-1d ALL_SYMBOLS for 2020-01-01 → 2024-12-31.
   - For each trading day, apply the live_scanner gap/RVOL filters → candidate list per day.
   - For each (sym, date) in the union, pull trades + bbo-1s.
   - Park parquet under `tick_cache_databento/<SYM>/{trades,bbo-1s}_<DATE>.parquet` to match the existing adapter.
3. **Phase D3c — combined backtest on 5-year data:** the harness already reads from the cache; Agent 4 just runs.

D3a is the right next step. D3b is overnight + one decision (§5 below). D3c is unblocked once D3b lands.

---

## 5. Float / fundamentals data gap

This is the **subtle but material risk**, separate from tick data.

### 5.1 Current state

- `scanner_results/float_cache.json` — 4,464 ticker → float entries. **No date dimension.** Single point-in-time snapshot.
- `universe_cache/framework_float_cache.json` — 363 mega-cap floats. Same shape, single snapshot.
- `float_cache.py` chain: FMP → yfinance → EDGAR → AlphaVantage. All four return **current** float. EDGAR has historical filings but `float_cache.py` doesn't use the date axis.
- `KNOWN_FLOATS` in `float_cache.py` lines 38-62: hand-curated snapshot of ~24 symbols (VERO, ROLR, ANPA, etc.) from Ross's recap research.

### 5.2 The look-ahead problem

The squeeze universe filter is `float < 30M`. For a 2021-Q2 backtest, we need the float **as it was on that date**, not the 2026 snapshot. Three sources of bias:

| Problem | Direction of bias |
|---|---|
| Survivorship — delisted/merged tickers absent from FMP today | Inflates returns (we only "see" surviving small-caps, which had a better post-listing outcome distribution than the full cohort) |
| Float drift — a 2021 stock with 5M float may have done a follow-on raise to 25M by 2026 | Mostly hurts squeeze coverage (some 2021 candidates filtered out as "too big now"); occasionally helps (post-2021 reverse split makes a then-50M now-3M) |
| Ticker reuse — old ticker, different company | Random noise; small effect |

### 5.3 Three options for D3

| Option | Cost | Bias risk | Implementation |
|---|---|---|---|
| **(a)** Fetch historical floats from Polygon (`/v3/reference/tickers/{ticker}` returns share_class_shares_outstanding with `date`) or EDGAR forms 10-Q / 10-K for asof-date float | Polygon Starter $29/mo or one-day burst; EDGAR free but slow | **Lowest** — true asof | Build a `float_cache_historical.py` keyed by `(sym, date)`. ~1 day CC. |
| **(b)** Use end-of-period (e.g. 2024) float as a proxy for the whole window | $0 | **Medium** — survivorship intact, drift skews coverage. Tilts toward "would-be candidates today." | 30-minute hack |
| **(c)** Skip the float filter entirely in the backtest | $0 | **High** — relaxes the universe by 5-10× (every $2-$20 gapper qualifies). Squeeze edge in-sample becomes diluted; results not comparable to live | trivial; degrade flag |

**Recommendation: (a).** Polygon's free tier serves 5 calls/min — sufficient overnight for ~1,000 candidates. Combined with a `KNOWN_FLOATS_HISTORICAL` table for the ~50 most-impactful Ross-traded names we already have float history for. (b) is acceptable for the D3a sanity run but must not be the final 5-year answer. (c) is unacceptable — it kills squeeze parity entirely.

---

## 6. Other data integrity findings

1. **`scanner_results_box/` and `scanner_results_ibkr/`** contain different schemas and don't extend coverage backward.
2. **`tick_cache_historical/` only has 2 days** (2026-04-06/07) — appears to be a backfill experiment, not a 5-year archive.
3. **`tick_cache_alpaca/`** has 8 days (2026-05-06 → 2026-05-15) from the subbot — same as above, not relevant pre-2025.
4. **Per `feedback_use_standard_backtester.md`:** "Don't build one-off backtest scripts. Extend run_ytd_backtest.py / simulate.py." Phase D3b should park its fetcher under `scripts/` and call into existing primitives, not duplicate them.
5. **Per `feedback_fill_optimism_disregard.md`:** any backtest of squeeze on Databento ticks must seed from ticks, not Alpaca bars; the 04-14 sim-fill-optimism reports were proven wrong by precisely this seeding choice. The `framework/data_adapters/databento_adapter.py` does it right (tick-level).

---

## 7. Recommendations

### 7.1 Immediate (this week)

- **PAUSE D3 (combined backtest harness on 5-year window)** per directive §90.
- Approve **Phase D3a — 2025-2026 sanity slice** as the unblock-the-harness step. Deliverable: combined backtest on 273 trading days using existing IBKR tick cache + new lightweight adapter. ~2-3 hours CC. Gives us a functional harness and validates Agent 1 (squeeze framework plugin) end-to-end **without any new fetches.**
- Decision needed: which historical float strategy (5.3-a/b/c) for the 5-year run? Cowork recommends (a) but it costs ~1 CC-day to implement.

### 7.2 Overnight / next 48h

- **Phase D3b — universe reconstruction.** Script:
  1. `EQUS.SUMMARY` ohlcv-1d ALL_SYMBOLS 2020-01-01 → 2024-12-31 → derive per-day gap, ADV.
  2. Apply `.env`-default filters → per-day candidate list.
  3. Persist `scanner_results/YYYY-MM-DD.json` for each day (matches existing format → no harness change).
  4. Pull `trades` + `bbo-1s` + `ohlcv-1m` for each (sym, date) → `tick_cache_databento/<SYM>/`.
  5. Estimated wall time: 6-12 hours overnight; ~3 GB data quota; well under $100 on Standard plan.
- Concurrent: historical float fetcher (5.3-a) for the candidate symbol list emerging from step (3).

### 7.3 Then D3c

Once D3b + historical float land, Agent 4's combined harness runs on the full 5-year window. Expect 1-2 hours of CC walltime to produce the report.

### 7.4 If Manny says "ship D3 on the 2025-2026 slice anyway"

That's a viable Wave-4-prep deliverable. It cannot answer the directive's headline question ("does tiered sizing scale a $25K account to $250K over 5 years?") — there isn't 5 years of data. But it **can** answer "does combined squeeze + framework + TieredSizer mechanics work as designed?" That's still valuable; just be explicit it's a harness-validation run, not a strategy-validation run.

---

## 8. Acceptance verdict

Per directive §90: **"If Phase D2 finds material data gaps, pause and report."**

- Material gap #1: **No squeeze universe exists for 2020-2024.** All 1,259 trading days missing scanner_results seed.
- Material gap #2: **No squeeze-candidate tick data on disk.** All 20 sampled symbols missing from `tick_cache_databento/`.
- Material gap #3: **Float data has no asof-date dimension.** Backtest will leak look-ahead unless remediated.

**Verdict: NO-GO for D3 as scoped (5-year combined backtest).** Three concrete remediation paths laid out (§4.3 + §5.3). Recommended sequence: D3a (sanity, today) → decision on float strategy → D3b (overnight fetch) → D3c (full run). Total clock time to ship a real 5-year combined backtest: ~3-4 days assuming the overnight fetch lands clean.

If Manny prefers a faster but caveated answer: D3a alone delivers a tier-aware combined backtest on 2025-2026 data with current squeeze coverage in ~3 hours, and is honest about its scope.

---

## 9. File-path index (absolute)

- Directive — Phase D2 spec: `/Users/duffy/warrior_bot_v2/DIRECTIVE_2026-05-17_GO_FOR_BUILD.md`
- Directive — combined backtest spec: `/Users/duffy/warrior_bot_v2/DIRECTIVE_2026-05-17_COMBINED_PORTFOLIO_BACKTEST.md`
- Adapter — Databento: `/Users/duffy/warrior_bot_v2/framework/data_adapters/databento_adapter.py`
- Scanner — historical reconstruction entry point: `/Users/duffy/warrior_bot_v2/ibkr_scanner.py` (line 380+ scan_premarket_historical; **requires seed**)
- Scanner — live: `/Users/duffy/warrior_bot_v2/live_scanner.py` (lines 296-343 for the `EQUS.SUMMARY` bootstrap pattern to clone for 2020-2024)
- Float chain: `/Users/duffy/warrior_bot_v2/float_cache.py`
- Float cache (point-in-time): `/Users/duffy/warrior_bot_v2/scanner_results/float_cache.json`
- Squeeze-candidate ticks (IBKR): `/Users/duffy/warrior_bot_v2/tick_cache/<DATE>/<SYM>.json.gz` — 273 dates 2025-01-02 → 2026-05-15
- Framework ticks (Databento): `/Users/duffy/warrior_bot_v2/tick_cache_databento/<SYM>/` — 36 mega-caps, mostly bars only
- Scanner result JSONs: `/Users/duffy/warrior_bot_v2/scanner_results/YYYY-MM-DD.json` — 2025-01-02 → 2026-05-15 only
- Prior data audit (Jan 2025 misses, OTC/SPAC gaps): `/Users/duffy/warrior_bot_v2/cowork_reports/2026-03-24_data_gap_investigation.md`
- Tick-data parity (live RTVolume vs historical): `/Users/duffy/warrior_bot_v2/cowork_reports/2026-04-07_tick_data_parity_findings.md`

— End of audit.
