# Pipeline Audit: Preliminary Findings

**Date**: 2026-03-21
**Scope**: Full simulation pipeline — scanner_sim.py → simulate.py → detectors → run_megatest.py
**Known reference bug**: `resolve_precise_discovery()` sets sim_start too early (4:00 AM instead of checkpoint time)

---

## CRITICAL — Issues that directly corrupt backtest results

### 1. Megatest allows overlapping trades across stocks (inflates P&L)

**File**: `run_megatest.py` → `_run_config_day()` (line 415)

**What happens**: The megatest simulates each stock independently via subprocess, then collects all trades. Stock A might have a trade open from 09:32–09:40, and stock B might have a trade from 09:35–09:42. Both trades are counted. But the live bot is single-position — you can only hold ONE trade at a time. If you're in stock A at 09:35, you can't also enter stock B.

**Why it matters**: The megatest sums P&L from all stocks' trades as if they were sequential, but they overlap in time. This inflates both the total number of trades and total P&L. On busy days with 3-5 stocks, this could double-count 2-3 trades that would be mutually exclusive in live trading.

**Evidence**: In `_run_config_day()`, trades are appended stock-by-stock, not sorted by time:
```python
for c in top5:
    all_trades = run_sim(sym, date, sim_start, stock_risk, min_score, candidate=c)
    for t in all_trades:
        day_trades.append(t)
```
No check for temporal overlap between stocks.

**Severity**: CRITICAL — backtest P&L is systematically inflated

**Verification test**: Add entry_time to each trade, sort all day's trades chronologically, and check how many would be blocked by "position already open" from a prior stock's trade. Compare trade count and P&L before/after filtering.

---

### 2. Megatest cumulative notional never releases (undercounts trades)

**File**: `run_megatest.py` → `_run_config_day()` (lines 421, 448)

**What happens**: `day_notional` accumulates with each trade but never decreases when trades close:
```python
day_notional = 0  # line 421
# ...
if day_notional + t["notional"] > MAX_NOTIONAL:  # line 448
    continue
day_notional += t["notional"]  # line 453 (implicit via append)
```
After 2 trades of ~$25K notional each, `day_notional` = $50K and all subsequent trades are blocked. But in live, each position opens and closes independently — the $50K limit is per-position, not cumulative.

**Why it matters**: For a $750 risk at $5 entry with R=$0.15, shares = 5,000, notional = $25,000. Two such trades exhaust the $50K limit. A third trade would be blocked in the megatest but would execute fine in live (since prior trades are already closed). This causes the megatest to systematically undercount trades on active days.

**Severity**: CRITICAL — backtest takes fewer trades than live would

**Verification test**: Track `day_notional` with proper release on trade close. Compare trade counts with current (accumulate-only) approach. Expect 1-2 additional trades per active day.

---

### 3. No premarket entry time filter — detectors ignore `is_premarket`

**Files**: `micro_pullback.py:1272`, `squeeze_detector.py:190`, `vwap_reclaim_detector.py:241`, `simulate.py` (tick loop), `bot.py:424-430`

**What happens**: The live bot has an explicit ARM time gate in `bot.py` (line 424-430):
```python
# Time gate: no ARMs before 7:00 AM ET (premarket too thin for reliable entries)
arm_earliest_et = int(os.getenv("WB_ARM_EARLIEST_HOUR_ET", "7"))
if msg and msg.startswith("ARMED"):
    if now_et.hour < arm_earliest_et:
        msg = None  # block the ARM
```
This prevents any ARM before 7:00 AM ET. **simulate.py does NOT implement this gate.** The sim's `on_1m_close()` callback (line 1884) feeds detector output directly without any time-based ARM filtering.

Additionally, all three detectors accept `is_premarket: bool` in `on_trade_price()` but never use it, so even TRIGGER signals during premarket are processed.

If sim_start is "07:00" (common for premarket scanner), the detector can ARM on 07:05 (after warmup) and TRIGGER at 07:06 on a premarket bar. Even with `WB_ARM_EARLIEST_HOUR_ET=7`, sim would miss this gate entirely.

**Why it matters**: Premarket entries on thin liquidity would not happen in live. These phantom entries could be winners or losers, corrupting the backtest's trade selection and P&L.

**Severity**: CRITICAL — phantom trades that can't happen in live

**Verification test**: Run the megatest with verbose output and grep for trade entry times before 09:30. Count how many premarket entries exist and their aggregate P&L.

---

### 4. resolve_precise_discovery bug also affects checkpoint-discovered stocks

**File**: `scanner_sim.py` → `resolve_precise_discovery()` (line 567-573)

**What happens**: The known sim_start bug applies not just to premarket candidates but to ALL candidates, including those found by `find_emerging_movers()` at checkpoint times (08:00, 08:30, 09:00, etc.).

Example: ROLR is discovered at the 08:30 checkpoint with `sim_start = "08:30"`. Then `resolve_precise_discovery()` finds ROLR first met criteria at 08:18 and updates `sim_start = "08:18"`. But the live scanner runs on checkpoints — it would not see ROLR until the 08:30 scan. The sim then processes 12 minutes of "extra" bars (08:18–08:30) as live data.

The condition on line 571 makes this worse:
```python
if precise_start < old_start or old_start == "?":
    c["sim_start"] = precise_start
```
This ONLY replaces when precise_start is earlier, guaranteeing the most aggressive (wrong) timing.

**Severity**: CRITICAL — same class as the known bug, broader impact

**Verification test**: For each emerging mover candidate, compare `sim_start` before and after `resolve_precise_discovery()`. Any where sim_start moves earlier than the checkpoint time is affected.

---

### 5. VWAP seed calculation uses bar close price instead of typical price

**File**: `bars.py` → `seed_bar_close()` (line 163)

**What happens**: During seed phase, VWAP is computed as:
```python
self._vwap_pv[symbol] += float(c) * vv  # close price × volume
```
But the live bot's `on_trade()` uses actual trade prices:
```python
self._vwap_pv[symbol] += price * size  # actual trade price × trade size
```
For 1-minute bars, close price is a single point estimate. The actual VWAP should use `(H+L+C)/3` (typical price) as a bar-level approximation, or ideally the actual trade-level data. During premarket hours with wide bid-ask spreads, the close price can deviate significantly from the volume-weighted average trade price.

**Why it matters**: VWAP is used for multiple critical gates: MP's "above VWAP" check, squeeze's "price above VWAP" check, VR's "close below VWAP" transition, and VWAP-based exit logic. A systematically biased VWAP affects all three strategies.

**Severity**: CRITICAL — affects every VWAP-dependent decision in the pipeline

**Verification test**: Compute VWAP using `(H+L+C)/3 * V` vs `C * V` for seed bars on a sample date. Compare the resulting VWAP at sim start. Expect 1-5% divergence on volatile premarket stocks.

---

## MEDIUM — Issues that cause sim-to-live divergence

### 6. Squeeze detector _session_hod polluted by premarket seed bars

**File**: `squeeze_detector.py` → `seed_bar_close()` (line 77-78)

**What happens**: During seed, every bar's high is tracked:
```python
if h > self._session_hod:
    self._session_hod = h
```
By sim start, `_session_hod` equals the premarket high. Then the `new_hod_required` gate (line 161-165) requires a bar to exceed this premarket high before arming a squeeze. In live, the detector starts fresh when a stock is subscribed, so the first meaningful bar sets HOD from 0.

**Why it matters**: The premarket high IS valid resistance, but in live the detector wouldn't know about it (fresh subscription). This makes squeeze detection harder in sim than in live. Some squeeze entries that fire in live would be blocked in sim.

**Severity**: MEDIUM — squeeze entries biased toward undercounting

**Verification test**: Compare squeeze arm/reject counts with `_session_hod` initialized to 0 vs premarket high. Look for "SQ_REJECT: not_new_hod" messages that wouldn't occur with a fresh detector.

---

### 7. VR and Squeeze detector bars_1m pre-populated by seed (bypasses history gates)

**Files**: `squeeze_detector.py:80`, `vwap_reclaim_detector.py:78`

**What happens**: Both detectors append bars to `bars_1m` during seed:
```python
# squeeze_detector.py seed_bar_close():
self.bars_1m.append(info)  # line 80

# vwap_reclaim_detector.py seed_bar_close():
self.bars_1m.append(info)  # line 78
```
After seed, `bars_1m` has 50+ entries (maxlen=50 deque). In live, when a new stock is subscribed, the detector starts with empty `bars_1m` and needs real-time bars to accumulate.

This affects:
- Squeeze: `if len(self.bars_1m) < 3: return None` (line 128) — always passes
- Squeeze: `_avg_prior_vol()` — uses 49 seed bars of premarket volume as baseline
- VR: `if len(self.bars_1m) < 5: return None` (line 224) — always passes

**Why it matters**: The volume baseline (`_avg_prior_vol`) is computed from premarket bars, which typically have much lower volume than RTH bars. This makes the vol_mult check (`vol_ratio = v / avg_vol`) much easier to pass, potentially triggering squeezes on volume that wouldn't qualify relative to RTH averages.

**Severity**: MEDIUM — squeeze volume threshold is systematically easier to pass in sim

**Verification test**: Log `_avg_prior_vol()` at each squeeze check. Compare with what the value would be using only post-sim-start bars.

---

### 8. Daily loss limit mismatch: sim uses $-1,500, live uses $-3,000

**Files**: `run_megatest.py:23` vs `.env:193`

**What happens**:
- Megatest: `DAILY_LOSS_LIMIT = -1500`
- Live .env: `WB_MAX_DAILY_LOSS=3000`

The megatest stops trading after $1,500 daily loss, but live trading allows up to $3,000. This means the megatest misses trades that would occur in live after a $1,500 drawdown but before hitting $3,000.

Additionally, the live bot has `WB_GIVEBACK_HARD_PCT=50` (walk away at 50% giveback) and `WB_GIVEBACK_WARN_PCT=20` (halve risk at 20% giveback). Neither is replicated in the megatest.

**Severity**: MEDIUM — sim stops trading too early on bad days

**Verification test**: Rerun megatest with `DAILY_LOSS_LIMIT = -3000` and compare trade counts on losing days.

---

### 9. MP detector pattern_tags persist across seed into sim

**File**: `micro_pullback.py` → `seed_bar_close()` (line 61-64)

**What happens**: During seed, pattern signals are accumulated:
```python
pattern_sigs = self.patterns.update(o, h, l, c, v)
for s in pattern_sigs:
    self.pattern_tags.append(s.name)
self.last_patterns = list(set(self.pattern_tags))
```
`pattern_tags` is a deque(maxlen=6), so the last 6 pattern signals from seed carry into sim. These could include patterns like "TOPPING_WICKY" or "DANGER_TREND_DOWN" from late premarket bars, which could immediately trigger resets or exits at sim start.

**Severity**: MEDIUM — stale pattern tags could prevent valid entries or trigger false exits at sim start

**Verification test**: Log `last_patterns` at sim start (right after seed completes) and check for stale patterns. Count how many early sim resets are caused by patterns detected during seed.

---

### 10. cache_tick_data.py scanner filter mismatch

**File**: `cache_tick_data.py:46` vs `run_megatest.py:29`

**What happens**:
```python
# cache_tick_data.py:
MIN_GAP_PCT = 5      # <-- caches stocks with 5%+ gap
# run_megatest.py:
MIN_GAP_PCT = 10     # <-- only simulates stocks with 10%+ gap
```
The comment in cache_tick_data.py says "must match run_ytd_v2_backtest.py", but it doesn't match run_megatest.py either. While this doesn't cause incorrect results (extra cached data is just ignored), it's a maintenance risk. If someone changes one file assuming they match, silent divergence occurs.

**Severity**: MEDIUM (maintenance hazard, no direct impact on results)

**Verification test**: Diff the filter constants across all three files (cache_tick_data.py, run_megatest.py, run_ytd_v2_backtest.py).

---

## LOW — Minor issues or design limitations

### 11. No bail timer in simulation

**File**: `.env:188-189` vs `simulate.py`

**What happens**: The live bot has `WB_BAIL_TIMER_ENABLED=1` and `WB_BAIL_TIMER_MINUTES=5`, which exits a trade if it hasn't become profitable within 5 minutes. This is not implemented in simulate.py at all.

**Severity**: LOW — bail timer exits are a minority of exits, and sim's other exit logic (stall counters, VWAP loss) partially covers this

**Verification test**: Count live bot trades exited by bail timer. If >5% of exits, consider implementing in sim.

---

### 12. Megatest warmup sizing not replicated

**File**: `.env:198-200` vs `run_megatest.py`

**What happens**: Live bot uses `WB_WARMUP_SIZE_PCT=25` (25% risk until $500 daily profit), then scales to full size. The megatest starts at full risk from trade #1 each day. This means early-day trades are oversized in sim vs live.

**Severity**: LOW — affects P&L magnitude but not win/loss outcomes

**Verification test**: Track the first 1-2 trades per day and compute their P&L at 25% risk vs full risk.

---

### 13. Squeeze stall counter and VR stall counter not reset between trades

**File**: `simulate.py` → `SimTradeManager.__init__()` (lines 185-196)

**What happens**: `_sq_bars_no_new_high` and `_vr_bars_no_new_high` are initialized once in `__init__`. After a squeeze trade closes and a new one opens, these counters retain their values from the previous trade. The counters ARE reset when a new high is made (on_tick), but if the second trade immediately stalls, the counter starts from its previous value instead of 0.

Specifically, `_sq_bars_no_new_high = 0` is set on `on_tick` when `price > t.peak`, and the stall counter increments in `on_1m_bar_close_squeeze` when `h <= t.peak`. But `t.peak` is set to the fill price of the NEW trade, so the counter effectively resets when the new trade's peak exceeds the high of the first bar. Still, there's a window between trade open and first new high where the stale counter applies.

**Severity**: LOW — the counter naturally resets on any new high, so impact is minimal

**Verification test**: Log stall counter value at the start of each squeeze trade. Non-zero values indicate stale state.

---

## Summary Matrix

| # | Issue | Severity | Direction of Bias | File(s) |
|---|-------|----------|-------------------|---------|
| 1 | Overlapping trades across stocks | CRITICAL | Inflates P&L | run_megatest.py |
| 2 | Cumulative notional never releases | CRITICAL | Undercounts trades | run_megatest.py |
| 3 | No premarket entry filter | CRITICAL | Phantom trades | micro_pullback.py, squeeze_detector.py, vwap_reclaim_detector.py |
| 4 | Precise discovery affects checkpoint stocks | CRITICAL | sim_start too early | scanner_sim.py |
| 5 | VWAP seed uses close price not typical price | CRITICAL | Biased VWAP | bars.py |
| 6 | Squeeze HOD polluted by seed | MEDIUM | Undercounts squeezes | squeeze_detector.py |
| 7 | Detector bars_1m pre-populated by seed | MEDIUM | Volume baseline too low | squeeze_detector.py, vwap_reclaim_detector.py |
| 8 | Daily loss limit mismatch | MEDIUM | Stops sim too early | run_megatest.py vs .env |
| 9 | Pattern tags persist from seed | MEDIUM | Stale resets at sim start | micro_pullback.py |
| 10 | Cache tick MIN_GAP_PCT mismatch | MEDIUM | Maintenance hazard | cache_tick_data.py |
| 11 | No bail timer in sim | LOW | Missing exit path | simulate.py |
| 12 | Warmup sizing not replicated | LOW | Oversized early trades | run_megatest.py |
| 13 | Stall counters not reset between trades | LOW | Stale stall state | simulate.py |

---

## Recommended Fix Priority

**Immediate** (fix before next megatest run):
1. Bug #4 — Fix resolve_precise_discovery to use checkpoint time, not criteria-met time
2. Bug #3 — Add `if is_premarket: return None` to all three detectors' `on_trade_price()`
3. Bug #1 — Add temporal overlap detection in `_run_config_day()` to skip trades that would conflict with an already-open position

**Next sprint**:
4. Bug #2 — Release notional on trade close in `_run_config_day()`
5. Bug #5 — Use `(H+L+C)/3 * V` for VWAP in `seed_bar_close()`
6. Bug #6 — Reset squeeze `_session_hod` after seed (or don't update it during seed)
7. Bug #7 — Don't append to `bars_1m` during seed, or clear it after seed

**Backlog**:
8. Bug #8 — Align daily loss limit with live config
9. Bug #9 — Clear pattern_tags after seed
10. Bugs #11-13 — Low priority
