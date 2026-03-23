# Directive: Scanner Fixes V1 — Unknown-Float Trading + Rescan Fix + EDGAR Float + Terminology Cleanup

**Date:** 2026-03-23
**From:** Cowork (Opus)
**To:** CC (Sonnet)
**Priority:** HIGH — #1 project priority (scanner coverage)

---

## Context

The January 2025 missed stocks backtest proved the scanner is our #1 bottleneck: +$42,818 potential vs $5,543 actual (7.7x multiplier). This directive addresses the two most immediately actionable scanner fixes, plus a terminology cleanup that Manny explicitly requested.

**Reports to read first:**
- `cowork_reports/2026-03-23_scanner_gap_analysis.md` — Full gap analysis
- `cowork_reports/2025-01_missed_stocks_backtest_results.md` — Backtest results

---

## Item 1: Enable Unknown-Float Stock Trading

### What
Flip the existing gate ON so the bot can trade stocks where float data is unavailable but all other signals are strong. This was previously called "Profile X" — see Item 3 for the rename.

### Why
GDTC (+$4,393 bot P&L, +93.6% gap, 94x RVOL) and AMOD (+$3,642 bot P&L, +79.9% gap, 42x RVOL) were **already found by the scanner** but couldn't trade because the gate was OFF. Combined: +$8,035 from a config change.

### Steps

1. **In `.env`**, change:
   ```
   WB_ALLOW_PROFILE_X=0
   ```
   to (after Item 3 rename):
   ```
   WB_ALLOW_UNKNOWN_FLOAT=1
   ```
   Keep the existing safety thresholds — they're already conservative:
   - gap ≥ 50%
   - pm_vol ≥ 1,000,000
   - rvol ≥ 10x
   - 50% notional cap

2. **Validation backtest:** Run the January 2025 missed stocks backtest (or the full YTD megatest) with unknown-float trading ON. Verify GDTC and AMOD produce positive results. Check that no new garbage stocks slip through.

3. **Update `run_ytd_v2_backtest.py`** to respect the unknown-float gate (currently line 142 hard-skips `profile == "X"` with no gate check). It should match the `run_megatest.py` logic (lines 174-186) that checks the env var and applies the safety thresholds.

### Acceptance Criteria
- GDTC Jan 6 produces trades with positive P&L
- AMOD Jan 30 produces trades with positive P&L
- VERO regression still passes (+$18,583 with `WB_MP_ENABLED=1`)
- No new trades on junk stocks (check that safety gates filter effectively)

---

## Item 2: Fix Continuous Rescan in scanner_sim.py

### What
The `find_emerging_movers()` function in scanner_sim.py found **zero** stocks via rescan across ALL of January 2025 (66 total candidates, 0 via "rescan" method, all via "premarket" or "precise"). This means the continuous rescan system is not working.

### Why
Stocks like ZENA (news at 7:30 AM, 8M float, +$1,865 bot P&L), SGN (3.7M float, +$1,625 bot P&L), and NEHC (+$839 bot P&L) had valid fundamentals but weren't found by the 7:15 AM premarket scan. They should have been caught by the continuous rescan at 8:00, 8:30, 9:00, or 9:30 AM checkpoints.

### Diagnosis

The `find_emerging_movers()` function (lines 425-508) fetches 30-minute bar windows at each checkpoint. The issue is likely one or more of these:

1. **RVOL/PM volume gates applied to rescan candidates** (lines 651-654): The rescan candidates get the same RVOL ≥ 2.0 and PM vol ≥ 50K gates applied, but their "pm_volume" is calculated from only the 30-minute window — not cumulative from 4 AM. A stock that's been building volume all morning won't get credit for earlier volume in the rescan.

2. **`avg_daily_vol` may be zero for rescan candidates**: If a stock wasn't in the initial `fetch_avg_daily_volume()` universe (because it had no prior-day close data), RVOL can't be calculated.

3. **Gap threshold still 10% at rescan**: Some stocks start the day flat and develop momentum after open. The 10% gap requirement may be too high for intraday movers found via rescan.

4. **`existing_candidates` parameter**: `find_emerging_movers()` receives the premarket candidates list and skips those symbols. But `resolve_precise_discovery()` runs AFTER the rescan (line 661), and it re-timestamps candidates. There may be an ordering issue where precise discovery is stealing candidates that would have been rescan candidates.

### Steps

1. **Debug**: Add logging to `find_emerging_movers()` to show:
   - How many symbols are checked at each checkpoint
   - How many pass the gap/price filter
   - How many get rejected by RVOL/PM vol gates
   - Which specific symbols were close but missed

2. **Fix cumulative volume**: Change rescan volume calculation to use cumulative volume from 4 AM to checkpoint time, not just the 30-minute window volume. This means fetching bars from `4:00 AM to checkpoint_time` for new candidates (or at minimum, from the start of the day's activity).

3. **Fix RVOL calculation**: Ensure `avg_daily_vol` is available for ALL active symbols checked in the rescan, not just the ones that had premarket bars.

4. **Consider lowering rescan gap threshold**: For the rescan specifically (not the initial premarket scan), consider accepting stocks at ≥ 5% gap if they have very high RVOL (≥ 10x) and strong PM volume (≥ 200K). This would catch momentum/continuation plays that don't have a massive premarket gap.

5. **Validation**: Re-run scanner_sim for January 2025 and verify:
   - Rescan now finds ≥ 5 new candidates across the month
   - ZENA (Jan 7, 7:30 AM), SGN (Jan 29/31), NEHC (Jan 22) appear in results
   - No regression on existing premarket candidates

### Acceptance Criteria
- `find_emerging_movers()` returns > 0 candidates for at least 5 days in January 2025
- ZENA appears as a candidate on Jan 7
- VERO regression still passes (+$18,583 with `WB_MP_ENABLED=1`)

---

## Item 3: Rename "Profile X" to "Unknown Float" Everywhere

### What
Remove ALL references to "Profile X" in the codebase. Replace with "unknown float" or "unknown-float" as appropriate. This is a terminology cleanup that Manny explicitly requested — the term causes confusion.

### Why
"Profile X" sounds like a special trading profile. It's not. It just means "we don't have float data for this stock." The new name should be self-explanatory.

### Rename Map

**Environment variables (.env):**
```
OLD: WB_ALLOW_PROFILE_X=0   # Allow unknown-float (Profile X) stocks...
NEW: WB_ALLOW_UNKNOWN_FLOAT=1   # Allow stocks with unknown float if gap>=50%, pm_vol>=1M, rvol>=10x (50% notional cap)
```

**Python constants (run_megatest.py, lines 34-39):**
```python
# OLD:
ALLOW_PROFILE_X = int(os.environ.get("WB_ALLOW_PROFILE_X", "0")) == 1
PROFILE_X_MIN_GAP = 50.0
PROFILE_X_MIN_PM_VOL = 1_000_000
PROFILE_X_MIN_RVOL = 10.0
PROFILE_X_NOTIONAL_FACTOR = 0.5

# NEW:
ALLOW_UNKNOWN_FLOAT = int(os.environ.get("WB_ALLOW_UNKNOWN_FLOAT", "0")) == 1
UNKNOWN_FLOAT_MIN_GAP = 50.0
UNKNOWN_FLOAT_MIN_PM_VOL = 1_000_000
UNKNOWN_FLOAT_MIN_RVOL = 10.0
UNKNOWN_FLOAT_NOTIONAL_FACTOR = 0.5
```

**Profile classification (scanner_sim.py, line 160-170):**
```python
# OLD:
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), X (>10M or unknown)."""
    if float_shares is None:
        return "X"

# NEW:
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), unknown (no data)."""
    if float_shares is None:
        return "unknown"
```

**All code comparisons — change `"X"` to `"unknown"`:**

Active files to change (NOT archive/ or .claude/worktrees/):

| File | Line(s) | Change |
|------|---------|--------|
| `scanner_sim.py` | 163 | `return "X"` → `return "unknown"` |
| `run_megatest.py` | 34-39 | Constants renamed (see above) |
| `run_megatest.py` | 175 | `profile == "X"` → `profile == "unknown"` |
| `run_megatest.py` | 176 | `ALLOW_PROFILE_X` → `ALLOW_UNKNOWN_FLOAT` |
| `run_megatest.py` | 184 | `"_profile_x"` → `"_unknown_float"` |
| `run_megatest.py` | 484-487 | Comment + `"_profile_x"` → `"_unknown_float"`, constant rename |
| `run_ytd_v2_backtest.py` | 142 | `profile == "X"` → `profile == "unknown"` (+ add gate logic from Item 1) |
| `run_ytd_v2_profile_backtest.py` | 155 | `profile == "X"` → `profile == "unknown"` |
| `run_oos_2025q4_backtest.py` | 148 | `profile == "X"` → `profile == "unknown"` |
| `run_jan_compare.py` | 85, 125 | `"WB_ALLOW_PROFILE_X"` → `"WB_ALLOW_UNKNOWN_FLOAT"`, `profile == "X"` → `profile == "unknown"` |
| `run_jan_comparison.py` | 39, 51 | `"WB_ALLOW_PROFILE_X"` → `"WB_ALLOW_UNKNOWN_FLOAT"` |
| `cache_tick_data.py` | 100, 105 | `profile == "X"` → `profile == "unknown"` |
| `.env` | line 78 | Full line replacement (see above) |

**Documentation files to update:**

| File | What to Change |
|------|---------------|
| `CLAUDE.md` | Replace "Profile X" with "unknown-float" in all mentions |
| `COWORK_HANDOFF.md` | Replace "Profile X" with "unknown-float" in scanner miss categories and config sections |
| `MASTER_TODO.md` | Replace "Profile X" with "unknown-float" |

**DO NOT touch:**
- `archive/` directory (historical, leave as-is)
- `.claude/worktrees/` (transient, will be cleaned up)
- `scanner_results/*.json` (historical data — old JSONs will have `"profile": "X"`, new ones will have `"profile": "unknown"`)
- `cowork_reports/` (historical analysis — leave as-is, the reports describe what existed at the time)

**Backward compatibility:** Since old scanner JSON files contain `"profile": "X"`, all code that checks for unknown-float must check for BOTH values during the transition:
```python
if profile in ("X", "unknown") or float_m is None or float_m == 0:
```
This ensures old cached scanner results still work. Add a comment: `# "X" is legacy name for unknown-float, kept for backward compat with old scanner JSONs`

### Acceptance Criteria
- `grep -r "Profile X" *.py *.md .env` returns zero hits (excluding archive/, .claude/worktrees/, cowork_reports/)
- `grep -r "PROFILE_X" *.py .env` returns zero hits (excluding archive/, .claude/worktrees/)
- All backtests produce identical results before and after rename
- VERO regression still passes (+$18,583 with `WB_MP_ENABLED=1`)

---

## Item 4: Add SEC EDGAR as Tier 5 Float Fallback (FREE)

### What
Add SEC EDGAR XBRL API as a fallback float lookup after FMP and yfinance both fail. Uses `EntityCommonStockSharesOutstanding` as a float proxy. Free, 10 requests/second, no API key — just needs a User-Agent header.

### Why
Perplexity research confirmed: 3 of 4 "float missing" tickers (XPON, VRME, AMOD) are resolvable through EDGAR. XPON had 10,846,135 shares outstanding in its March 2026 filing — well within our 10M ceiling. FMP and yfinance both returned None for it, costing us +$3,321 in bot P&L.

GDTC (the 4th ticker) is a foreign filer (Singapore, 20-F) and EDGAR's `EntityPublicFloat` returns 404 for those. But `EntityCommonStockSharesOutstanding` returns 11,540,000. Since GDTC is already covered by the unknown-float gate (Item 1), EDGAR is a bonus for it, not critical.

### Implementation

Add this to BOTH `scanner_sim.py` and `live_scanner.py` in the `get_float()` function, as Tier 5 after yfinance:

```python
import requests

# --- SEC EDGAR ticker→CIK map (load once at startup) ---
_EDGAR_CIK_MAP = {}

def _load_edgar_cik_map():
    global _EDGAR_CIK_MAP
    if _EDGAR_CIK_MAP:
        return _EDGAR_CIK_MAP
    try:
        resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers={"User-Agent": "WarriorBot luke@delightedpath.net"},
            timeout=10
        )
        data = resp.json()
        _EDGAR_CIK_MAP = {
            v['ticker'].upper(): str(v['cik_str']).zfill(10)
            for v in data.values()
        }
    except Exception as e:
        print(f"  [EDGAR] Failed to load CIK map: {e}")
    return _EDGAR_CIK_MAP


def get_edgar_shares_outstanding(symbol: str) -> float | None:
    """Tier 5: SEC EDGAR shares outstanding as float proxy. Free, 10 req/s."""
    cik_map = _load_edgar_cik_map()
    cik = cik_map.get(symbol.upper())
    if not cik:
        return None
    try:
        url = (f"https://data.sec.gov/api/xbrl/companyconcept/"
               f"CIK{cik}/dei/EntityCommonStockSharesOutstanding.json")
        resp = requests.get(url, headers={
            "User-Agent": "WarriorBot luke@delightedpath.net"
        }, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        shares_list = data.get("units", {}).get("shares", [])
        if not shares_list:
            return None
        # Get most recent filing
        latest = sorted(shares_list, key=lambda x: x.get("end", ""), reverse=True)[0]
        shares = latest.get("val", 0)
        if shares > 0:
            print(f"  [EDGAR] {symbol}: {shares/1e6:.2f}M shares outstanding")
            return shares
    except Exception as e:
        print(f"  [EDGAR] {symbol}: {e}")
    return None
```

Then update `get_float()` in both files to add the EDGAR call after the yfinance block:

```python
def get_float(symbol: str, cache: dict) -> float | None:
    # ... existing code: KNOWN_FLOATS → cache → FMP → yfinance ...

    # 5. SEC EDGAR fallback (free, 10 req/s)
    if float_shares is None:
        float_shares = get_edgar_shares_outstanding(symbol)

    cache[symbol] = float_shares
    save_float_cache(cache)
    return float_shares
```

### Notes
- The CIK map is ~13K tickers. Load it once at scanner startup (takes ~1-2 seconds).
- EDGAR returns shares outstanding, not true float. For small-caps with <10M shares outstanding, this is close enough — insiders/institutions typically hold a small %. The existing float ceiling filter handles the rest.
- Rate limit: 10 req/s. The scanner processes candidates sequentially, so this is never hit.
- Foreign filers (20-F) may not have `EntityCommonStockSharesOutstanding` either. In that case, EDGAR returns 404 and we fall through to the unknown-float gate.

### Acceptance Criteria
- XPON resolves to ~10.8M shares via EDGAR (would be classified as "skip" since >10M, but close — shows the lookup works)
- VRME resolves to ~12.4M shares via EDGAR
- AMOD resolves to ~42M shares via EDGAR (confirms it's a large-float stock — unknown-float gate is the right path for this one)
- GDTC returns None from EDGAR (foreign filer) — falls through to unknown-float gate correctly

---

## Item 5: Float Cache Invalidation for Stale None Entries (FREE)

### What
When `float_cache.json` contains a `None` value for a ticker, that None blocks the ticker forever — even if FMP/yfinance/EDGAR can resolve it now. Add a mechanism to re-attempt None lookups periodically.

### Why
Float data providers update at different times. A ticker that returned None from FMP last week (between an offering and the next quarterly filing) may now be resolvable. Caching None permanently means we never discover this.

### Implementation

In `load_float_cache()` (both `scanner_sim.py` and `live_scanner.py`), add a filter that drops None entries older than 7 days:

```python
import time

def load_float_cache() -> dict:
    if os.path.exists(FLOAT_CACHE_PATH):
        with open(FLOAT_CACHE_PATH) as f:
            raw = json.load(f)
        # Drop stale None entries older than 7 days
        # Format: cache stores {symbol: float_or_none}
        # To track age, we need to add timestamps. Simple approach:
        # Just clear ALL None entries on each load — forces re-lookup.
        # This is fine because the lookup chain (FMP→yfinance→EDGAR) is fast
        # and we only have ~5-15 None entries per month.
        cleaned = {k: v for k, v in raw.items() if v is not None}
        dropped = len(raw) - len(cleaned)
        if dropped > 0:
            print(f"  [float_cache] Cleared {dropped} stale None entries — will re-attempt lookups")
            save_float_cache(cleaned)
        return cleaned
    return {}
```

**Simpler alternative (preferred):** Just clear None entries every time. With the EDGAR fallback added (Item 4), most previously-None tickers will now resolve successfully. The cache only holds ~300 tickers, so re-looking up 10-20 None entries adds <10 seconds.

### Acceptance Criteria
- After clearing, previously-None tickers get re-looked-up through the full chain (FMP → yfinance → EDGAR)
- Tickers that still can't be resolved get re-cached as None (will be cleared again next run)
- No regression on scanner performance or speed

---

## Item 6: Alpha Vantage Free Tier as Tier 6 Float Fallback (FREE — 25 calls/day)

### What
Add Alpha Vantage OVERVIEW endpoint as a final fallback for float data. Their `SharesFloat` field returns actual tradeable float (not shares outstanding). Free tier: 25 API calls/day, 5/minute.

### Why
For the rare cases where FMP, yfinance, AND EDGAR all fail (foreign 20-F filers like GDTC), Alpha Vantage may have the data. Their OVERVIEW endpoint was verified to return float: e.g., IBM `SharesFloat=936,083,000`. 25 calls/day is tight for a full scanner run but more than enough as a last-resort fallback — we typically have <5 None entries per day after the first three tiers.

### Implementation

Get a free API key from https://www.alphavantage.co/support/#api-key

Add after EDGAR in `get_float()`:

```python
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

def get_alpha_vantage_float(symbol: str) -> float | None:
    """Tier 6: Alpha Vantage OVERVIEW — true float. Free tier: 25 calls/day."""
    if not ALPHA_VANTAGE_KEY:
        return None
    try:
        url = (f"https://www.alphavantage.co/query?function=OVERVIEW"
               f"&symbol={symbol}&apikey={ALPHA_VANTAGE_KEY}")
        resp = requests.get(url, timeout=10)
        data = resp.json()
        shares_float = data.get("SharesFloat")
        if shares_float and shares_float != "None" and shares_float != "0":
            val = float(shares_float)
            if val > 0:
                print(f"  [AlphaVantage] {symbol}: {val/1e6:.2f}M float")
                return val
    except Exception as e:
        print(f"  [AlphaVantage] {symbol}: {e}")
    return None
```

Then in `get_float()`, after EDGAR:

```python
    # 6. Alpha Vantage free tier (25 calls/day, true float)
    if float_shares is None:
        float_shares = get_alpha_vantage_float(symbol)
```

Add to `.env`:
```
ALPHA_VANTAGE_API_KEY=           # Free tier: https://www.alphavantage.co/support/#api-key
```

### Notes
- 25 calls/day limit means this ONLY fires as a last resort. With KNOWN_FLOATS + cache + FMP + yfinance + EDGAR covering ~95% of tickers, Alpha Vantage handles the remaining ~5%.
- If the free tier quota is exhausted, the function returns None silently — no crash, no retry.
- `time.sleep(0.5)` between calls to stay under the 5/min limit.

### Acceptance Criteria
- GDTC resolves to ~3.7M float via Alpha Vantage (matches yfinance current value)
- Rate limit is respected (no more than 5 calls per minute)
- Graceful degradation when quota exhausted

---

## Execution Order

1. **Item 3 first** (rename) — pure refactor, no behavior change. Commit.
2. **Item 1 second** (enable unknown-float) — .env already updated. Update `run_ytd_v2_backtest.py` to respect the gate. Commit.
3. **Item 4 third** (EDGAR fallback) — add to both scanner files. Commit.
4. **Item 5 fourth** (cache invalidation) — add to both scanner files. Commit.
5. **Item 6 fifth** (Alpha Vantage) — add to both scanner files + .env key. Commit.
6. **Item 2 sixth** (rescan fix) — debugging + code change in `scanner_sim.py`. Commit.
7. **Run regression** after all items: VERO +$18,583 (with `WB_MP_ENABLED=1`).
8. **Validation:** Re-run `scanner_sim.py --date 2025-01-06` and verify GDTC now appears as a tradeable candidate (not unknown-float blocked).
9. **Push to origin main.**

---

## Regression

After all changes:
```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

---

*Directive created 2026-03-23 by Cowork (Opus). Reference: cowork_reports/2026-03-23_scanner_gap_analysis.md*
