# Directive — Kill the Silent Alpaca Fallback in `simulate.py`

**Priority:** P0
**Author:** Cowork (Opus), 2026-04-11
**Greenlit by:** Manny
**Scope:** `simulate.py` tick-loading branch only. **Do not touch bot logic, X01 config, exit rules, detector gates, or scanner thresholds.**

---

## Read this first — context that changes how you should approach this task

**Manny was right all day on 2026-04-10.** He kept flagging that the backtest results in the morning report were inconsistent with the bot's documented behavior against the price action he knew from Ross's recap and from his own chart. CC and Cowork kept pushing back and trying to "fix" a working system based on those bad backtest numbers. The bot did exactly what it was supposed to do — the simulator was wrong because its tick input was wrong.

The root cause is not in the bot and not in X01. It is entirely in the data layer: `simulate.py`'s fallback branch silently fetched bad BENF data from Alpaca, wrote it into the IBKR cache directory as if it belonged there, and every downstream analysis for the rest of the day was built on poisoned data.

**This directive fixes the sim/data layer. That is all it fixes.** Do not use this directive as an excuse to revisit bot behavior, exit policy, tuning config, scanner thresholds, or detector gates. If you find something else that looks wrong while you're in `simulate.py`, write it down and leave it alone. Stay in your lane.

---

## The bug

`simulate.py` lines 2854–2885 (verified against the tree at `HEAD` as of commit `95865c4`):

```python
if tick_cache:
    _cache_file = os.path.join(tick_cache, date_str, f"{symbol}.json.gz")
    if os.path.exists(_cache_file):
        # load from cache ← happy path
    else:
        print(f"  WARNING: No cache file {_cache_file} — falling back to API", flush=True)
        tick_trades = fetch_trades(symbol, sim_start_utc, sim_end_utc)   # ← Alpaca

        # ── Write fetched ticks to cache so future runs don't re-fetch ──
        if tick_trades:
            _cache_dir = os.path.join(tick_cache, date_str)
            os.makedirs(_cache_dir, exist_ok=True)
            _cache_payload = [...]
            with _gzip.open(_cache_file, "wt") as _cf:
                json.dump(_cache_payload, _cf)
            print(f"  Cached {len(_cache_payload)} ticks → {_cache_file}", flush=True)
```

Two things make this dangerous:

1. **It falls back to Alpaca silently.** A `WARNING:` line in stdout is not a fail. Any script that calls `simulate.py` and parses only the final `P&L:` line will happily proceed on bad data. That's exactly what happened on 2026-04-10 when CC ran `run_backtest_v2.py`.
2. **It writes the Alpaca-fetched ticks back into the cache directory.** The cache directory is otherwise populated by `ibkr_tick_fetcher.py` (IBKR historical ticks). By writing Alpaca data into `tick_cache/{date}/{symbol}.json.gz`, the fallback mixes the sources in a way that no later reader can distinguish. Once written, every subsequent `simulate.py` call on that date loads the poisoned file thinking it's IBKR cache.

For BENF on 2026-04-10 specifically, Alpaca's historical data is wrong by a factor of 1.2918 (probably a corporate-action adjustment that Alpaca applied and IBKR did not) and missing ~2.5x tick volume including the first 15 minutes of premarket. The fresh IBKR refetch in `cowork_reports/2026-04-10_cache_refetch_results.md` documents this in detail.

## What to build — immediate fix (ship first)

Replace the fallback branch with a **hard fail**. The new behavior when `--tick-cache <dir>` is passed and the cache file is missing:

1. Print a loud, unambiguous error to stderr:
   ```
   FATAL: tick cache miss — tick_cache/{date}/{symbol}.json.gz does not exist.
   simulate.py will not silently fall back to Alpaca historical data.
   Populate the cache first with ibkr_tick_fetcher.py, or re-run without --tick-cache
   and add --feed alpaca explicitly if Alpaca data is what you want.
   ```
2. Exit with non-zero status (`sys.exit(2)` is a reasonable choice — distinct from the default `1` for argparse/validation errors).
3. **Do not write anything to the cache directory.** No partial files, no placeholder, no touching.

This is the minimum change that prevents the silent-poisoning class of bug. Ship it first, commit it separately from the follow-up, and push.

## What to build — follow-up (ship second, separate commit)

After the hard-fail is in and committed, add a real fallback path that uses IBKR instead of Alpaca:

1. When `--tick-cache <dir>` is passed and the cache file is missing, call `ibkr_tick_fetcher.py`'s fetch function directly (refactor the core logic out of the `__main__` block of `ibkr_tick_fetcher.py` into an importable function if needed). Fetch the window the sim needs, write the result into the cache dir the same way the nightly populator does, then proceed.
2. The fallback should still be loud — print `"  Cache miss: fetching {symbol} {date} from IBKR historical ticks ..."` and the resulting tick count. Silence is the failure mode we're eliminating.
3. If IBKR Gateway is not connected, the IBKR fetch will raise. Do **not** then fall through to Alpaca. Let it fail. The invariant we want is: cache miss → IBKR fetch or loud error, never Alpaca.

Only the existing `--feed alpaca` command-line flag should be allowed to use Alpaca, and only when `--tick-cache` is not passed. Someone running `python simulate.py SYMBOL DATE --feed alpaca` without `--tick-cache` is explicitly asking for Alpaca and gets Alpaca — that path does not need changes.

## State of the poisoned cache (verification only — no action needed)

Cowork already handled the 2026-04-10 cache cleanup on 2026-04-11. For your verification:

- `tick_cache/2026-04-10/` contains the fresh IBKR pull from last night:
  - `BENF.json.gz` 333 KB mtime 2026-04-11 00:47
  - `SQFT.json.gz` 766 KB mtime 2026-04-11 00:42
  - `IQST.json.gz` 67 KB mtime 2026-04-11 00:47
- `tick_cache/2026-04-10.BROKEN_EVIDENCE_DO_NOT_DELETE/` contains the Alpaca-poisoned files from 2026-04-10 14:02–14:10. **Do not delete this directory.** It's the before-picture.

The cache is already clean. Your task is only to fix the code path that poisoned it, not to re-clean it.

## Testing

After the hard-fail change:

1. Pick any date where the cache exists and is known good (e.g., VERO 2026-01-16). Run:
   ```bash
   python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   Expected: loads from cache, produces the expected P&L, no warning line. This verifies the happy path still works.

2. Pick a symbol/date combo where the cache does NOT exist (e.g., a random invented symbol like `XXXZZZ` for today). Run with `--tick-cache`:
   ```bash
   python simulate.py XXXZZZ 2026-04-10 07:00 12:00 --ticks --tick-cache tick_cache/
   ```
   Expected: FATAL error, exit status non-zero, nothing written to `tick_cache/2026-04-10/XXXZZZ.json.gz`. Verify the cache directory was not touched.

3. **Do not run the regression suite (VERO/ROLR) to "validate" this change.** The regression suite tests bot behavior, which you are not touching. Running regression here is noise at best and a distraction at worst.

After the IBKR fallback follow-up change:

4. Delete one symbol's cache for a known date:
   ```bash
   mv tick_cache/2026-04-09/<symbol>.json.gz /tmp/
   ```
   Then run `simulate.py` against that symbol with `--tick-cache`. Expected: loud "cache miss, fetching from IBKR" line, Gateway-backed fetch, cache populated, sim proceeds normally. Compare the P&L to what it was before the cache move — should be identical (or very close, allowing for IBKR non-determinism on repeated fetches) since both the original and the refetched cache come from IBKR.

5. Move the file back, leave `tick_cache/2026-04-09/` pristine.

## Explicit non-goals

Don't touch:

- `bot_v3_hybrid.py`, `bot.py`, or any file in the detector pipeline
- `trade_manager.py`, `micro_pullback.py`, `squeeze_detector.py`, `classifier.py`
- `.env` — no config changes, no tuning knobs
- Exit logic, entry logic, level map, exhaustion filter, classifier gate
- `scanner_sim.py`, `market_scanner.py`, `live_scanner.py`, `stock_filter.py`
- `cache_tick_data.py` (separate concern — see Directive #2 and open item below)

If you see any of the above while you're in `simulate.py` and it looks wrong, write a note to `cowork_reports/2026-04-11_sim_fallback_observations.md` and leave it alone. Don't fix it in this PR.

## Open question to flag in your results file (do not act on)

`cache_tick_data.py` at the repo root still imports `from alpaca.data.historical import StockHistoricalDataClient` and its docstring still says "Download and store Alpaca tick data locally". The 04-07 correction (commit `842752b`) said "Alpaca fetch_trades in simulate.py is dead code — tick cache was repopulated by `ibkr_tick_fetcher.py`". That repopulation wasn't `cache_tick_data.py`, which means this file is either stale-and-unused, or it's live and would write Alpaca data to the cache if invoked. We don't know which yet. Flag this in your results file and **do not touch the file** as part of this directive. It's in scope for a separate cleanup directive later.

## Success criteria

1. `simulate.py` fails loudly (non-zero exit) when `--tick-cache` is passed and the file is missing. No writes to cache directory on failure.
2. IBKR fallback added in a separate commit, fetching via the `ibkr_tick_fetcher.py` code path. Gateway-down is a hard error, not a silent Alpaca fallback.
3. Both commits pushed to `origin v2-ibkr-migration`.
4. Short results file at `cowork_reports/2026-04-11_alpaca_fallback_removed.md` with: commits, test output from the two test cases, and the open question on `cache_tick_data.py`.

## Do NOT do

- Do not revert or "improve" bot behavior based on the 2026-04-10 morning report's P&L narrative. That report was wrong because its input data was wrong. The bot was right.
- Do not re-run the X01 tuning corpus "to check". The corpus is IBKR per commit `842752b` and the past-week tick_cache mtime evidence. No contamination, no audit needed.
- Do not delete the `tick_cache/2026-04-10.BROKEN_EVIDENCE_DO_NOT_DELETE/` directory.
- Do not touch `scanner_sim.py` as part of this. Scanner-side Alpaca dependency is a separate P2 concern.
