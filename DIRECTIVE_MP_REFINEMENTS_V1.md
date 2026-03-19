# Directive: Micro Pullback Refinements V1

## Priority: HIGH
## Owner: CC
## Created: 2026-03-19

---

## Context

Analyzed verbose simulation logs for 6 key stocks (VERO, ROLR, SXTC, ARTL, INKT, FUTG).
The micro pullback strategy is performing well — VERO +18.6R, ROLR +6.5R, SXTC cascading
+1.4R/+0.8R. The big missed opportunities (VERO $5.81→$12, ROLR $16.43→$22, ARTL squeeze)
belong to future strategy modules (squeeze, dip-buy, curl), NOT micro pullback fixes.

Two actionable improvements identified:

1. **Thin stock / minimum liquidity filter** — FUTG and INKT both had 312 ticks across 5 hours.
   These illiquid stocks produce unreliable setups. The bot should not ARM on stocks with
   insufficient trading activity.

2. **Trade setup tagging** — When we add squeeze, dip-buy, VWAP reclaim, and curl modules,
   each trade needs to carry metadata identifying which strategy produced it. This plumbing
   should be added now so it's ready.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin v6-dynamic-sizing
```

---

## Change 1: Minimum Session Volume Gate at ARM Time

### What
Add an env-gated check in `micro_pullback.py` that blocks ARM if cumulative session volume
(sum of all 1m bar volumes seen so far) is below a threshold.

### Why
FUTG: 312 ticks, 35 sim bars, negligible volume → -$1,538 (max_loss_hit)
INKT: 312 ticks, BE exit same minute as entry → -$349
Both had plenty of bars but almost no actual trading activity.

### Implementation

In `micro_pullback.py`:

1. Add env vars:
```python
self.min_session_volume = int(os.getenv("WB_MIN_SESSION_VOLUME", "0"))  # 0 = off
```

2. Track cumulative session volume (should already be available from `bars_1m`):
```python
def _session_volume(self) -> int:
    """Total volume across all 1m bars seen so far."""
    return sum(b["v"] for b in self.bars_1m)
```

3. Add check in the ARM logic, right after the existing stale stock check, before returning
   the ARMED message. If `min_session_volume > 0` and `_session_volume() < min_session_volume`,
   return a NO_ARM message like:
```
f"1M NO_ARM low_session_volume: {self._session_volume()} < {self.min_session_volume}"
```

### Env var
```
WB_MIN_SESSION_VOLUME=10000    # Minimum cumulative 1m bar volume before ARM allowed
```

Start with 10,000 as default when enabled. This would block FUTG (had barely any volume)
but not affect VERO (26M+ PM volume), ROLR (10M+ PM volume), etc.

**Gate: OFF by default (0).** Enable with `WB_MIN_SESSION_VOLUME=10000`.

### Testing
- Verify FUTG 2026-01-02 is blocked (no ARM) with threshold at 10,000
- Verify VERO 2026-01-16 is NOT affected (volume far exceeds threshold)
- Verify ROLR 2026-01-14 is NOT affected
- Verify SXTC 2026-01-08 is NOT affected

---

## Change 2: Trade Setup Type Tagging

### What
Add a `setup_type` field to `OpenTrade` and propagate it through trade logging.

### Why
When we add squeeze, dip-buy, VWAP reclaim, and curl strategies, every trade needs to
identify which strategy produced it. Adding the plumbing now means future strategy modules
just set `setup_type="squeeze"` etc. at entry time.

### Implementation

1. In `trade_manager.py`, add to `OpenTrade` dataclass:
```python
setup_type: str = "micro_pullback"  # Strategy that produced this trade
```

2. In `trade_manager.py`, add to `PendingEntry` dataclass:
```python
setup_type: str = "micro_pullback"
```

3. Wherever `OpenTrade` is created from a `PendingEntry`, propagate `setup_type`.

4. In `simulate.py`, when parsing/logging trade results, include `setup_type` in the output.
   In the verbose trade table, add a column or note.

5. In `bot.py`, same — log `setup_type` in trade completion messages.

### No env var needed — this is always-on metadata.

---

## Change 3: Log Setup Type in Backtest State JSON

### What
Include `setup_type` in the trade dictionaries written to `ytd_v2_backtest_state.json`
and the backtest report.

### Why
When the batch runner processes multiple strategies, we need to filter results by strategy.

### Implementation
In `run_ytd_v2_backtest.py`, add `"setup_type": "micro_pullback"` to the trade dict
in `run_sim()` (around line 210). For now it's always `"micro_pullback"`. Future strategy
modules will pass their own type.

---

## Regression

After implementing, run:
```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
```

**Expected:** VERO +$18,583, ROLR +$6,444 (unchanged — new filter is OFF by default).

Then test with filter ON:
```bash
WB_MIN_SESSION_VOLUME=10000 python simulate.py FUTG 2026-01-02 07:00 12:00 --ticks -v 2>&1 | grep -E "ARM|ENTRY|NO_ARM"
```

**Expected:** FUTG should show `NO_ARM low_session_volume` and produce 0 trades.

---

## Post-Flight

```bash
git add -A
git commit -m "MP refinements V1: min session volume gate + setup type tagging

Change 1: WB_MIN_SESSION_VOLUME gate blocks ARM on illiquid stocks (OFF by default)
Change 2: setup_type field on OpenTrade/PendingEntry for multi-strategy support
Change 3: setup_type propagated to backtest state JSON and reports

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```
