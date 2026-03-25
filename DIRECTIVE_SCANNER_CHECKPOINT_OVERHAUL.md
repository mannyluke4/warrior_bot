# DIRECTIVE: Scanner Checkpoint Overhaul + Live Bot Alignment

**Author**: Cowork (Opus)
**Date**: 2026-03-24
**For**: CC (Sonnet)
**Priority**: HIGH — Replaces DIRECTIVE_RESCAN_AND_BACKTEST.md (kill that run if still active)
**Replaces**: DIRECTIVE_RESCAN_AND_BACKTEST.md (old 5-min checkpoint rescan)

---

## Background

WT scanner comparison data (91 stocks, 10 trading days) revealed:
- **08:00-08:30 is the golden hour**: 71% WR, +$26,875
- **Post-09:30 is negative EV**: -$2,430, 25% WR — every stock discovered after 9:30 lost money
- **Our scanner captures 80% of P&L with 12% of stocks** — filters are working, but timing matters

Current state of scanning infrastructure:
- `scanner_sim.py`: 5-min checkpoints from 07:15-10:30 (39 checkpoints) — too many, scans dead zone
- `bot.py` rescan thread: 30-min checkpoints (7:30, 8:00, 8:30, 9:00, 9:30, 10:00, 10:30) — too sparse in golden hour, too late in dead zone
- `live_scanner.py`: writes watchlist every 5 min from 7:00-11:00 — needs 1-min writes and 9:30 cutoff for new symbols

---

## Step 0: Git Pull + Kill Running Rescan

```bash
cd /Users/mannyluke/warrior_bot
git pull
source venv/bin/activate
```

If the old DIRECTIVE_RESCAN_AND_BACKTEST is still running in another CC instance, kill it (Ctrl+C). This directive supersedes it — we're changing the checkpoint schedule before rescanning.

---

## Step 1: Update `scanner_sim.py` Checkpoints

Replace the `_build_checkpoints()` function and the `SCAN_CHECKPOINTS` generation with a hardcoded custom schedule.

**Find this block** (around line 498-518):
```python
# Continuous scanning checkpoints (all times ET)
# Generate 5-minute rescan checkpoints from 07:20 to 10:30
def _build_checkpoints(start_h=7, start_m=15, end_h=10, end_m=30, step_min=5):
    checkpoints = []
    windows = []
    h, m = start_h, start_m
    prev_h, prev_m = start_h, start_m
    while True:
        m += step_min
        if m >= 60:
            h += 1
            m -= 60
        if h > end_h or (h == end_h and m > end_m):
            break
        label = f"{h:02d}:{m:02d}"
        checkpoints.append((label, h, m))
        windows.append((label, prev_h, prev_m, h, m))
        prev_h, prev_m = h, m
    return checkpoints, windows

SCAN_CHECKPOINTS, _CHECKPOINT_WINDOWS = _build_checkpoints()
```

**Replace with:**
```python
# Continuous scanning checkpoints (all times ET)
# Custom schedule based on WT scanner comparison data (2026-03-24):
#   - Dense in golden hour (08:00-08:30): 71% WR, +$26,875
#   - Taper after 09:00
#   - Hard cutoff at 09:30: post-09:30 discoveries are negative EV (-$2,430, 25% WR)
# 12 checkpoints total (was 39 at 5-min intervals)
_CUSTOM_CHECKPOINTS = [
    ("07:00",  7,  0),
    ("07:15",  7, 15),
    ("07:30",  7, 30),
    ("07:45",  7, 45),
    ("08:00",  8,  0),
    ("08:15",  8, 15),
    ("08:30",  8, 30),
    ("08:45",  8, 45),
    ("09:00",  9,  0),
    ("09:15",  9, 15),
    ("09:30",  9, 30),   # FINAL — hard cutoff, no new discoveries after this
]

def _build_checkpoint_windows(checkpoints):
    """Build (label, prev_h, prev_m, h, m) windows from checkpoint list."""
    windows = []
    for i, (label, h, m) in enumerate(checkpoints):
        if i == 0:
            prev_h, prev_m = 7, 0  # Window starts at 07:00
        else:
            _, prev_h, prev_m = checkpoints[i - 1]
        windows.append((label, prev_h, prev_m, h, m))
    return windows

SCAN_CHECKPOINTS = _CUSTOM_CHECKPOINTS
_CHECKPOINT_WINDOWS = _build_checkpoint_windows(_CUSTOM_CHECKPOINTS)
```

**IMPORTANT**: The `_CHECKPOINT_WINDOWS` list must stay in the same format that the rest of `scanner_sim.py` expects: `(label, prev_h, prev_m, h, m)`. Grep for `_CHECKPOINT_WINDOWS` to confirm all usages are compatible. There's also a `CHECKPOINTS` reference around line 673 that builds from `SCAN_CHECKPOINTS` — it should just work since the tuple format `(label, h, m)` is preserved.

Also fix the hardcoded fallback default around line 677:
```python
                correct_start = "10:30"  # default to last checkpoint
```
Change to:
```python
                correct_start = CHECKPOINTS[-1]  # default to last checkpoint
```
This ensures the fallback always uses the actual last checkpoint (now "09:30") instead of a hardcoded "10:30".

---

## Step 2: Update `bot.py` Rescan Checkpoints

**Find this block** (around line 625-628):
```python
# Checkpoints in ET hours — scanner re-runs at each to catch emerging movers
RESCAN_CHECKPOINTS_ET = [
    (7, 30), (8, 0), (8, 30), (9, 0), (9, 30), (10, 0), (10, 30),
]
```

**Replace with:**
```python
# Checkpoints in ET hours — scanner re-runs at each to catch emerging movers
# Custom schedule based on WT scanner comparison data (2026-03-24):
#   - Dense in golden hour (08:00-08:30): 71% WR, +$26,875
#   - Taper after 09:00
#   - Hard cutoff at 09:30: post-09:30 discoveries are negative EV (-$2,430, 25% WR)
RESCAN_CHECKPOINTS_ET = [
    (7,  0), (7, 15), (7, 30), (7, 45),
    (8,  0), (8, 15), (8, 30), (8, 45),
    (9,  0), (9, 15), (9, 30),   # FINAL — no rescans after 9:30
]
```

Also update the docstring in `rescan_thread()` (around line 636-638):
```python
    """
    Periodically re-run the MarketScanner + StockFilter to catch stocks that
    start gapping after the initial 4 AM scan. Mirrors the backtest's 30-minute
    checkpoint approach from scanner_sim.py.
```
Change to:
```python
    """
    Periodically re-run the MarketScanner + StockFilter to catch stocks that
    start gapping after the initial scan. Uses custom checkpoint schedule
    (dense in 08:00-08:30 golden hour, hard cutoff at 09:30).
```

---

## Step 3: Update `live_scanner.py` — 1-Minute Writes + 9:30 New-Symbol Cutoff

### 3a: Change watchlist write frequency from 5 min to 1 min

**Find this block** in the `run()` method (around line 647-653):
```python
                # After 7:14, continue writing every 5 minutes until 11:00 AM
                if self._final_watchlist_written and h < WINDOW_END_HOUR:
                    current_5min = (h * 60 + m) // 5
                    last_5min = (h * 60 + last_update_minute) // 5 if last_update_minute >= 0 else -1
                    if current_5min > last_5min:
                        self.write_watchlist(f"update_{h:02d}{m:02d}")
                        last_update_minute = m
```

**Replace with:**
```python
                # After 7:14, write every 1 minute until window closes
                if self._final_watchlist_written and h < WINDOW_END_HOUR:
                    current_min = h * 60 + m
                    last_min = (h * 60 + last_update_minute) if last_update_minute >= 0 else -1
                    if current_min > last_min:
                        self.write_watchlist(f"update_{h:02d}{m:02d}")
                        last_update_minute = m
```

### 3b: Add 9:30 cutoff for NEW symbols (existing watchlist symbols stay)

In the `write_watchlist()` method, after the candidate filtering loop but before writing, add a cutoff check. **Find this section** (around line 540-552):
```python
        # Sort by composite rank score descending
        scored_candidates.sort(key=lambda x: x["rank_score"], reverse=True)

        # Apply MAX_SCANNER_SYMBOLS cap (existing symbols count toward the cap)
        all_final = []
        total_count = len(existing_symbols)
        for c in scored_candidates:
            if c["symbol"] in existing_symbols:
                all_final.append(c)  # already in watchlist, always include
                continue
            if total_count < MAX_SCANNER_SYMBOLS:
                all_final.append(c)
                total_count += 1
```

**Replace with:**
```python
        # Sort by composite rank score descending
        scored_candidates.sort(key=lambda x: x["rank_score"], reverse=True)

        # 9:30 ET cutoff: no NEW symbols after 9:30 (existing watchlist preserved)
        # Data shows post-09:30 discoveries are negative EV (-$2,430, 25% WR)
        now_et = datetime.now(ET)
        past_cutoff = (now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30))

        # Apply MAX_SCANNER_SYMBOLS cap (existing symbols count toward the cap)
        all_final = []
        total_count = len(existing_symbols)
        for c in scored_candidates:
            if c["symbol"] in existing_symbols:
                all_final.append(c)  # already in watchlist, always include
                continue
            if past_cutoff:
                continue  # Block new symbols after 9:30 ET
            if total_count < MAX_SCANNER_SYMBOLS:
                all_final.append(c)
                total_count += 1

        if past_cutoff and scored_candidates:
            new_blocked = [c["symbol"] for c in scored_candidates if c["symbol"] not in existing_symbols]
            if new_blocked:
                self.log.info(f"  [9:30 CUTOFF] Blocked {len(new_blocked)} new symbols: {new_blocked}")
```

### 3c: Update the WINDOW_END_HOUR comment (it stays at 11 for tracking existing symbols)

The live scanner still runs until 11:00 AM to keep tracking existing watchlist symbols and writing updates. Only NEW symbol additions stop at 9:30. Add a comment to clarify:

**Find** (line 60):
```python
WINDOW_END_HOUR = 11         # Extended to 11:00 AM ET
```
**Replace with:**
```python
WINDOW_END_HOUR = 11         # Scanner runs until 11:00 AM (tracks existing symbols)
                             # New symbol additions cut off at 9:30 (see write_watchlist)
```

### 3d: Update the docstring (line 6-7)

**Find:**
```python
are gapping 10%+ with price $2-$20, float under 10M, RVOL >= 2x, and PM volume
>= 50K. Ranks by composite score and writes to watchlist.txt from 7:00-11:00 AM ET.
```
**Replace with:**
```python
are gapping 10%+ with price $2-$20, RVOL >= 2x, and PM volume >= 50K.
Ranks by composite score and writes to watchlist.txt every minute from 7:00 AM.
New symbol additions cut off at 9:30 AM ET (post-09:30 = negative EV).
Scanner continues tracking existing symbols until 11:00 AM ET.
```

---

## Step 4: Raise Float Cap from 10M to 15M in `scanner_sim.py`

WT comparison showed AMIX (+$4,111, 8.2R, 12.9M float) would be captured at 15M. The data supports it.

**Find** the `classify_profile` function (around line 255-265):
```python
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-10M), unknown (no data)."""
    if float_shares is None:
        return "unknown"
    millions = float_shares / 1_000_000
    if millions < 5:
        return "A"
    elif millions <= 10:
        return "B"
    else:
        return "skip"
```

**Replace with:**
```python
def classify_profile(float_shares: float | None) -> str:
    """Classify stock by float: A (<5M), B (5-15M), unknown (no data).

    Float cap raised from 10M to 15M based on WT scanner comparison (2026-03-24):
    AMIX at 12.9M float produced +$4,111 (8.2R). Data shows diminishing returns
    above 15M but the 10-15M bucket still has positive EV.
    """
    if float_shares is None:
        return "unknown"
    millions = float_shares / 1_000_000
    if millions < 5:
        return "A"
    elif millions <= 15:
        return "B"
    else:
        return "skip"
```

Also update `live_scanner.py` to match — **find** (line 63):
```python
MAX_FLOAT = 10_000_000       # 10M float ceiling
```
**Replace with:**
```python
MAX_FLOAT = 15_000_000       # 15M float ceiling (raised from 10M per WT comparison 2026-03-24)
```

And update `.env` — **find**:
```
WB_MAX_FLOAT=10                 # Tightened (was 50M)
WB_PREFERRED_MAX_FLOAT=10
```
**Replace with:**
```
WB_MAX_FLOAT=15                 # Raised from 10M (WT comparison: AMIX 12.9M float = +$4,111)
WB_PREFERRED_MAX_FLOAT=15
```

---

## Step 5: Regression Test

Run the standard regression to make sure nothing broke:

```bash
WB_MP_ENABLED=1 python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$18,583

```bash
WB_MP_ENABLED=1 python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```
**Expected**: +$6,444

If either regresses, stop and investigate. The checkpoint changes should not affect simulate.py tick-mode results (checkpoints are only used by scanner_sim.py for discovery timing, not by simulate.py for trade execution).

---

## Step 6: Rescan All January Dates with New Checkpoints

This replaces the old DIRECTIVE_RESCAN_AND_BACKTEST.md run. Back up first:

```bash
mkdir -p scanner_results/backup_pre_custom_checkpoints
for f in scanner_results/2025-01-*.json scanner_results/2026-01-*.json; do
    [ -f "$f" ] && cp "$f" scanner_results/backup_pre_custom_checkpoints/
done
echo "Backed up $(ls scanner_results/backup_pre_custom_checkpoints/*.json 2>/dev/null | wc -l) files"
```

**Jan 2025 (21 trading days):**
```bash
for d in 2025-01-02 2025-01-03 2025-01-06 2025-01-07 2025-01-08 2025-01-09 2025-01-10 2025-01-13 2025-01-14 2025-01-15 2025-01-16 2025-01-17 2025-01-21 2025-01-22 2025-01-23 2025-01-24 2025-01-27 2025-01-28 2025-01-29 2025-01-30 2025-01-31; do
    echo "=== Scanning $d ==="
    python scanner_sim.py "$d" 2>&1 | tail -5
    echo ""
done
```

**Jan 2026 (21 trading days):**
```bash
for d in 2026-01-02 2026-01-05 2026-01-06 2026-01-07 2026-01-08 2026-01-09 2026-01-12 2026-01-13 2026-01-14 2026-01-15 2026-01-16 2026-01-20 2026-01-21 2026-01-22 2026-01-23 2026-01-26 2026-01-27 2026-01-28 2026-01-29 2026-01-30; do
    echo "=== Scanning $d ==="
    python scanner_sim.py "$d" 2>&1 | tail -5
    echo ""
done
```

---

## Step 7: Run YTD V2 Backtest with New Scanner Data

```bash
python run_ytd_v2_backtest.py 2>&1 | tee /tmp/ytd_v2_custom_checkpoints.txt
```

Compare the total P&L against the previous run. The new checkpoints + 15M float cap should:
- Add stocks like AMIX (previously blocked at 10M)
- Discover more stocks in the 08:00-08:30 golden hour window
- Stop discovering negative-EV stocks after 09:30

---

## Step 8: Commit + Push

```bash
git add scanner_sim.py bot.py live_scanner.py .env
git commit -m "$(cat <<'EOF'
Scanner checkpoint overhaul: custom 12-point schedule + 9:30 cutoff

Based on WT scanner comparison (91 stocks, 10 days):
- scanner_sim.py: Replace 39x 5-min checkpoints with 12 custom checkpoints
  (dense in 08:00-08:30 golden hour, hard cutoff at 09:30)
- bot.py: Update RESCAN_CHECKPOINTS_ET to match (was 7x 30-min)
- live_scanner.py: 1-min watchlist writes (was 5-min), block new symbols after 9:30
- Float cap raised from 10M to 15M (AMIX at 12.9M = +$4,111)

Data: 08:00-08:30 = 71% WR, +$26,875. Post-09:30 = -$2,430, 25% WR.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
git push origin main
```

---

## Step 9: Write Report

Save a brief report to `cowork_reports/2026-03-24_scanner_checkpoint_overhaul.md` with:
- What changed (3 files, 4 areas)
- Regression results (VERO, ROLR)
- YTD V2 backtest comparison (old checkpoints vs new)
- Any stocks newly captured by the 15M float cap
- Any stocks that disappeared due to 09:30 cutoff (expected: losers)

---

## Files Modified

| File | What Changed |
|------|-------------|
| `scanner_sim.py` | 12 custom checkpoints (was 39), float cap 15M (was 10M) |
| `bot.py` | `RESCAN_CHECKPOINTS_ET` → 11 checkpoints with 9:30 cutoff (was 7 at 30-min) |
| `live_scanner.py` | 1-min writes (was 5-min), 9:30 new-symbol cutoff, 15M float cap |
| `.env` | `WB_MAX_FLOAT=15`, `WB_PREFERRED_MAX_FLOAT=15` |

## Validation Checklist

- [ ] Regression: VERO +$18,583
- [ ] Regression: ROLR +$6,444
- [ ] scanner_sim.py uses 12 checkpoints (verify with a quick `python -c "from scanner_sim import SCAN_CHECKPOINTS; print(len(SCAN_CHECKPOINTS), SCAN_CHECKPOINTS)"`)
- [ ] bot.py RESCAN_CHECKPOINTS_ET has 11 entries ending at (9, 30)
- [ ] live_scanner.py write frequency is 1 min
- [ ] live_scanner.py blocks new symbols after 9:30
- [ ] All Jan dates rescanned with new checkpoints
- [ ] YTD V2 backtest completed and compared
