# DIRECTIVE: Live Bot Alignment — Add-On: Scanner Parity

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — Queue after DIRECTIVE_LIVE_BOT_ALIGNMENT.md completes
**Depends on**: DIRECTIVE_SCANNER_CHECKPOINT_OVERHAUL.md (float cap already raised to 15M there)

---

## Problem

The bot has THREE independent scanner/filter implementations with hardcoded thresholds that have drifted apart. A change in one doesn't propagate to the others:

| Threshold | `scanner_sim.py` | `live_scanner.py` | `stock_filter.py` (bot rescan) |
|-----------|------------------|--------------------|-------------------------------|
| **Min gap %** | 10% (hardcoded line 394) | 10% (hardcoded `MIN_GAP_PCT` line 53) | 10% (from `WB_MIN_GAP_PCT` env) |
| **Price range** | $2-$20 (hardcoded line 396) | $2-$20 (hardcoded lines 56-57) | $2-$20 (from `WB_MIN/MAX_PRICE` env) |
| **Max float** | 10M → "skip" (hardcoded `classify_profile` line 265) | 10M (hardcoded `MAX_FLOAT` line 63) | 10M (from `WB_MAX_FLOAT` env) |
| **Min RVOL** | No RVOL gate on initial scan | 2.0x (hardcoded `MIN_RVOL` line 65) | 2.0x (from `WB_MIN_REL_VOLUME` env) |
| **Min PM volume** | No PM volume gate on initial scan | 50K (hardcoded `MIN_PM_VOLUME` line 64) | No gate (uses Alpaca snapshot) |
| **Unknown float** | Pass through as "unknown" (line 258) | Pass through (line 244-245) | Depends on `WB_MAX_FLOAT` — blocks if float resolved > max |
| **Config source** | Hardcoded in Python | Hardcoded in Python | `.env` via `os.getenv()` |

**The core issue**: `scanner_sim.py` and `live_scanner.py` ignore `.env` for their filter thresholds. When we change `WB_MAX_FLOAT=15` in `.env`, only `stock_filter.py` picks it up. The other two keep their hardcoded values.

---

## Step 0: Git Pull

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

---

## Task 1: Make `live_scanner.py` Read Thresholds from `.env`

Replace the hardcoded constants (lines 53-66) with env-aware defaults:

**Find:**
```python
# Filter thresholds (Phase 1 simplification: widened to match Ross Cameron criteria)
MIN_GAP_PCT = 10.0           # 10%+ gaps only
MAX_GAP_PCT_A = 999.0       # No gap ceiling (Ross traded 500%+ gaps)
MAX_GAP_PCT_B = 999.0       # Same — no gap ceiling
MIN_PRICE = 2.0             # Ross trades $2+
MAX_PRICE = 20.0            # Ross's stated range for small account
WINDOW_START_HOUR = 7
WINDOW_START_MINUTE = 0
WINDOW_END_HOUR = 11         # Extended to 11:00 AM ET
WINDOW_END_MINUTE = 0
MIN_FLOAT = 100_000          # 100K (sane floor)
MAX_FLOAT = 10_000_000       # 10M float ceiling
MIN_PM_VOLUME = 50_000       # Minimum pre-market volume
MIN_RVOL = 2.0               # Minimum relative volume (vs 20-day avg)
MAX_SCANNER_SYMBOLS = 8      # Cap total symbols across all writes
```

**Replace with:**
```python
# Filter thresholds — read from .env (shared with stock_filter.py / scanner_sim.py)
# Fallback defaults match Ross Cameron criteria
MIN_GAP_PCT = float(os.getenv("WB_MIN_GAP_PCT", "10"))
MAX_GAP_PCT_A = 999.0       # No gap ceiling (Ross traded 500%+ gaps)
MAX_GAP_PCT_B = 999.0       # Same — no gap ceiling
MIN_PRICE = float(os.getenv("WB_MIN_PRICE", "2.00"))
MAX_PRICE = float(os.getenv("WB_MAX_PRICE", "20.00"))
WINDOW_START_HOUR = 7
WINDOW_START_MINUTE = 0
WINDOW_END_HOUR = 11         # Scanner runs until 11:00 AM (tracks existing symbols)
                             # New symbol additions cut off at 9:30 (see write_watchlist)
WINDOW_END_MINUTE = 0
MIN_FLOAT = int(float(os.getenv("WB_MIN_FLOAT", "0.5")) * 1_000_000)   # Convert millions to shares
MAX_FLOAT = int(float(os.getenv("WB_MAX_FLOAT", "15")) * 1_000_000)    # 15M (was 10M hardcoded)
MIN_PM_VOLUME = int(os.getenv("WB_MIN_PM_VOLUME", "50000"))
MIN_RVOL = float(os.getenv("WB_MIN_REL_VOLUME", "2.0"))
MAX_SCANNER_SYMBOLS = int(os.getenv("WB_MAX_SCANNER_SYMBOLS", "8"))
```

**Note on MIN_FLOAT**: `.env` has `WB_MIN_FLOAT=0.5` (in millions). `live_scanner.py` used `MIN_FLOAT=100_000` (in shares). The conversion `0.5 * 1_000_000 = 500_000` is slightly different from the old 100K floor. Check if the 500K floor is intentional — the `.env` comment says "Min float in millions (blocks micro-float disasters)". Use the `.env` value as the source of truth.

---

## Task 2: Make `scanner_sim.py` Read Thresholds from `.env`

### 2a: Update `compute_gap_candidates()` (~line 380)

**Find:**
```python
def compute_gap_candidates(prev_close: dict, pm_bars: dict) -> list[dict]:
    """Find stocks gapping up >= 10% with price $2-$20."""
```

The hardcoded thresholds are at lines 394-397:
```python
        if gap_pct < 10:
            continue
        if pm_price < 2.0 or pm_price > 20.0:
            continue
```

**Replace with env-aware values** at the top of the function:
```python
def compute_gap_candidates(prev_close: dict, pm_bars: dict) -> list[dict]:
    """Find stocks gapping up with price and gap filters from .env."""
    _min_gap = float(os.getenv("WB_MIN_GAP_PCT", "10"))
    _min_price = float(os.getenv("WB_MIN_PRICE", "2.00"))
    _max_price = float(os.getenv("WB_MAX_PRICE", "20.00"))
```

And use those in the filter:
```python
        if gap_pct < _min_gap:
            continue
        if pm_price < _min_price or pm_price > _max_price:
            continue
```

### 2b: Update `classify_profile()` (~line 255)

The checkpoint overhaul directive already changes this to 15M. Verify it reads from `.env` instead of being hardcoded. If the checkpoint overhaul hardcoded 15M, change it to read from env:

```python
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float profile. Thresholds from .env."""
    if float_shares is None:
        return "unknown"
    _max_float_m = float(os.getenv("WB_MAX_FLOAT", "15"))
    millions = float_shares / 1_000_000
    if millions < 5:
        return "A"
    elif millions <= _max_float_m:
        return "B"
    else:
        return "skip"
```

---

## Task 3: Add Missing Env Vars to `.env`

Add these new vars (used by live_scanner.py now, previously hardcoded):

```bash
# --- Live Scanner Tuning ---
WB_MIN_PM_VOLUME=50000           # Minimum pre-market volume for live scanner
WB_MAX_SCANNER_SYMBOLS=8         # Max symbols on live watchlist
```

These already existed as hardcoded values — now they're configurable via `.env` like everything else.

---

## Task 4: Verify Filter Parity

After changes, run a quick sanity check. All three should now agree:

```bash
python3 -c "
import os
from dotenv import load_dotenv
load_dotenv()
print('=== .env Scanner Thresholds ===')
print(f'  MIN_GAP:   {os.getenv(\"WB_MIN_GAP_PCT\", \"10\")}%')
print(f'  PRICE:     \${os.getenv(\"WB_MIN_PRICE\", \"2.00\")} - \${os.getenv(\"WB_MAX_PRICE\", \"20.00\")}')
print(f'  MAX_FLOAT: {os.getenv(\"WB_MAX_FLOAT\", \"15\")}M')
print(f'  MIN_RVOL:  {os.getenv(\"WB_MIN_REL_VOLUME\", \"2.0\")}x')
print(f'  MIN_PM_VOL: {os.getenv(\"WB_MIN_PM_VOLUME\", \"50000\")}')

# Verify live_scanner reads same values
from live_scanner import MIN_GAP_PCT, MIN_PRICE, MAX_PRICE, MAX_FLOAT, MIN_RVOL, MIN_PM_VOLUME
print(f'\\n=== live_scanner.py ===')
print(f'  MIN_GAP:   {MIN_GAP_PCT}%')
print(f'  PRICE:     \${MIN_PRICE} - \${MAX_PRICE}')
print(f'  MAX_FLOAT: {MAX_FLOAT/1e6:.0f}M')
print(f'  MIN_RVOL:  {MIN_RVOL}x')
print(f'  MIN_PM_VOL: {MIN_PM_VOLUME}')

# Verify stock_filter reads same values
from stock_filter import StockFilter
sf = StockFilter('x','x')
print(f'\\n=== stock_filter.py ===')
print(f'  MIN_GAP:   {sf.min_gap_pct}%')
print(f'  PRICE:     \${sf.min_price} - \${sf.max_price}')
print(f'  MAX_FLOAT: {sf.max_float}M')
print(f'  MIN_RVOL:  {sf.min_rel_volume}x')
print()
print('All three should show identical values.')
"
```

---

## Task 5: Regression Test

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$18,583

```bash
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$6,444

---

## Task 6: Commit + Push

```bash
git add live_scanner.py scanner_sim.py .env
git commit -m "$(cat <<'EOF'
Scanner filter parity: all three scanners now read from .env

live_scanner.py and scanner_sim.py had hardcoded filter thresholds
(gap%, price range, float cap, RVOL) that drifted from .env values.
Now all three scanner paths read from the same .env config:
- live_scanner.py: MIN_GAP_PCT, price, float, RVOL, PM volume from env
- scanner_sim.py: compute_gap_candidates() and classify_profile() from env
- stock_filter.py: already read from env (no changes needed)

Single source of truth = change .env once, all scanners update.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Files Modified

| File | What Changed |
|------|-------------|
| `live_scanner.py` | Hardcoded thresholds → `os.getenv()` with same defaults |
| `scanner_sim.py` | `compute_gap_candidates()` and `classify_profile()` read from `.env` |
| `.env` | Added `WB_MIN_PM_VOLUME`, `WB_MAX_SCANNER_SYMBOLS` |

---

*Add-on to DIRECTIVE_LIVE_BOT_ALIGNMENT.md. After this, all three scanner paths (live_scanner.py, scanner_sim.py, stock_filter.py) read from the same `.env` config. Change once, apply everywhere.*
