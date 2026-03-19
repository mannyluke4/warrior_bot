# Directive: Squeeze Conflict Fixes V2

## Priority: HIGH
## Owner: CC
## Created: 2026-03-19

---

## Context

Parabolic mode works spectacularly on first-leg movers (ARTL +$7,762 vs +$922 MP-only),
but revealed three conflicts on VERO and ROLR:

1. **VERO**: Squeeze entered during pullback phase ($6.04 after stock fell from $5.81).
   Stop blown through ($5.90→$4.76) for -$4,571. The volume spike was a BOUNCE, not a new
   squeeze. Total VERO P&L dropped from +$18,583 to +$13,583.

2. **ROLR**: Two squeeze trades consumed both max_entries slots, blocking MP's $9.33→$16.43
   monster (+6.5R). Squeeze still netted +$9,751 vs MP's +$6,444, but we're leaving the
   best trade on the table.

3. **VERO**: Tight parabolic stop ($0.14 R) is meaningless when stock gaps through it.
   -9.1R on a single trade.

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin v6-dynamic-sizing
```

---

## Fix 1: HOD Proximity Gate (blocks squeeze during pullback phases)

### Problem
VERO at 07:45: stock had run to $5.81 (HOD), pulled back, then bounced to $5.88.
Squeeze detector saw green bar + volume + above VWAP = PRIMED. But $5.88 is far below
the $5.81 HOD that was set during the MP trade. This is a bounce, not a new squeeze.

### Solution
In `squeeze_detector.py`, add a check: the bar's HIGH must be within `WB_SQ_HOD_PROXIMITY_PCT`
(default 5%) of the session high-of-day. If the bar is making new highs or near the HOD,
it's a legitimate squeeze. If it's 10-15% below HOD, it's a bounce.

### Implementation

1. Add env var in `__init__`:
```python
self.hod_proximity_pct = float(os.getenv("WB_SQ_HOD_PROXIMITY_PCT", "5.0"))
```

2. Track HOD in the detector. Add to `__init__`:
```python
self._session_hod: float = 0.0
```

3. Update HOD on every bar in `on_bar_close_1m()` (before any returns):
```python
if bar.high > self._session_hod:
    self._session_hod = bar.high
```

4. Also update HOD in `seed_bar_close()`:
```python
if h > self._session_hod:
    self._session_hod = h
```

5. Add the gate in IDLE state detection (after volume/body/VWAP checks, before PRIMED transition):
```python
# HOD proximity check — reject bounces during pullbacks
if self._session_hod > 0:
    distance_from_hod = (self._session_hod - h) / self._session_hod * 100
    if distance_from_hod > self.hod_proximity_pct:
        return (
            f"SQ_REJECT: hod_proximity ({distance_from_hod:.1f}% below HOD "
            f"${self._session_hod:.4f}, max={self.hod_proximity_pct}%)"
        )
```

6. Also reset HOD in `reset()`:
```python
self._session_hod = 0.0
```

### Why this works
- ARTL: First squeeze at 07:42 = making new HOD → passes ✅
- VERO at 07:45: HOD was ~$6.10+, bar high was $5.88 → ~3.6% below HOD... hmm, that's
  within 5%. Let me recalculate.

  Actually, VERO's MP trade ran $3.58→$5.81 and exited at 07:35. The HOD at that point
  was the peak seen during the run. Looking at the verbose log, the highest TW_SUPPRESSED
  price was $6.14 at 07:33. So HOD ≈ $6.14. The squeeze PRIMED at 07:45 with bar close
  $5.88. Distance = (6.14 - 5.88) / 6.14 = 4.2%.

  With a 5% gate, this would PASS. We need a tighter gate: **3%** or we need a different
  approach.

  Better approach: **require bar high > session HOD** (i.e., the bar must be making a
  NEW session high to qualify as a squeeze). This is the strictest version.

  Even better: **require bar high > HOD OR bar high > PM high** (first leg of the day
  can't have a HOD yet, so use PM high for the first squeeze attempt).

### Revised gate (use this instead of the proximity %):
```python
# New HOD gate: bar must be at or making new session highs
# Exception: if this would be the FIRST trade of the session, use PM high comparison
if self._attempts == 0 and self._session_hod <= 0:
    # No HOD yet (first bar), allow squeeze if above PM high
    pass  # PM high check is already in level detection
elif h < self._session_hod:
    return (
        f"SQ_REJECT: not_new_hod (bar_high=${h:.4f} < HOD=${self._session_hod:.4f})"
    )
```

This is cleaner: the bar MUST be making a new session high to be a squeeze candidate.
On VERO's bounce at $5.88 with HOD at $6.14: **blocked** ✅
On ARTL's first squeeze at 07:42 with very early HOD: the bar IS the HOD → **passes** ✅
On ROLR's first squeeze at 08:18 with early HOD: bar IS the HOD → **passes** ✅

**Use the strict version: `bar.high >= self._session_hod`** (gate this behind
`WB_SQ_NEW_HOD_REQUIRED=1`, default ON).

```python
self.new_hod_required = os.getenv("WB_SQ_NEW_HOD_REQUIRED", "1") == "1"
```

---

## Fix 2: Separate Entry Counters Per Strategy

### Problem
ROLR: 2 squeeze trades consumed both `max_entries_per_symbol=2` slots, blocking the
MP's $9.33→$16.43 trade. The quality gate (`trades_2 >= max_2`) doesn't distinguish
between squeeze and MP trades.

### Solution
In `simulate.py`'s quality gate check, count entries by `setup_type`.

The quality gate lives in `SimTradeManager` and is checked before each entry. Currently
it uses a global trade count per symbol. Change it to:
- MP trades count against MP limit (default 2)
- Squeeze trades count against squeeze limit (`WB_SQ_MAX_ATTEMPTS=3`)
- They are independent — squeeze entries don't block MP entries

### Implementation

1. In `SimTradeManager`, track trades by type:
```python
self._mp_trade_count: Dict[str, int] = {}    # per-symbol MP trade count
self._sq_trade_count: Dict[str, int] = {}    # per-symbol squeeze trade count
```

2. When a trade closes, increment the appropriate counter:
```python
if t.setup_type == "squeeze":
    self._sq_trade_count[t.symbol] = self._sq_trade_count.get(t.symbol, 0) + 1
else:
    self._mp_trade_count[t.symbol] = self._mp_trade_count.get(t.symbol, 0) + 1
```

3. In the quality gate check (before allowing MP entry):
```python
# For MP entries: check MP count only
mp_count = self._mp_trade_count.get(symbol, 0)
if mp_count >= self.max_entries_per_symbol:
    return "FAIL", f"mp_trades_{mp_count}_>=_max_{self.max_entries_per_symbol}"
```

4. The squeeze detector already tracks its own `_attempts` counter, so no change
   needed there. Just make sure the sim's quality gate doesn't also block squeeze.

5. **Key change**: When checking quality gate for a new entry, pass `setup_type`:
```python
def quality_gate_check(self, symbol: str, setup_type: str = "micro_pullback"):
    if setup_type == "squeeze":
        # Squeeze has its own limit handled by detector._attempts
        return "PASS", ""
    # Existing MP logic
    ...
```

### Effect on ROLR
- Squeeze trade 1 at 08:19: enters, counted as squeeze (not MP)
- Squeeze trade 2 at 08:20: enters, counted as squeeze (not MP)
- MP ARM at 08:26: quality gate checks MP count = 0 → **PASSES** ✅
- ROLR gets squeeze +$9,751 PLUS MP's big move

---

## Fix 3: Absolute Dollar Loss Cap on Squeeze Trades

### Problem
VERO squeeze: R=$0.14, stop=$5.90, but stock gapped to $4.76. Loss = $1.28/share × 3,571
shares = -$4,571 = -9.1R. The tight parabolic stop is meaningless in a gap-down.

### Solution
Add `WB_SQ_MAX_LOSS_DOLLARS` (default $500). On every tick, if the squeeze trade's
unrealized loss exceeds this dollar amount, exit immediately.

### Implementation

1. Add env var in `SimTradeManager.__init__`:
```python
self.sq_max_loss_dollars = float(os.getenv("WB_SQ_MAX_LOSS_DOLLARS", "500"))
```

2. In `_squeeze_tick_exits()`, add check BEFORE the hard stop (make it the FIRST exit check):
```python
def _squeeze_tick_exits(self, t: SimTrade, price: float, time_str: str):
    # 0) Absolute dollar loss cap (catches gap-throughs)
    if self.sq_max_loss_dollars > 0:
        unrealized_loss = (t.entry - price) * t.qty_total
        if unrealized_loss >= self.sq_max_loss_dollars:
            reason = f"sq_dollar_loss_cap (${unrealized_loss:,.0f} >= ${self.sq_max_loss_dollars:,.0f})"
            t.core_exit_price = price
            t.core_exit_time = time_str
            t.core_exit_reason = reason
            if t.qty_runner > 0:
                t.runner_exit_price = price
                t.runner_exit_time = time_str
                t.runner_exit_reason = reason
            self._close(t)
            return

    # 1) Hard stop (existing)
    ...
```

### Effect on VERO
- Squeeze entry at 08:00: $6.04, 3,571 shares
- At $5.90 (original stop): loss = $0.14 × 3,571 = $500 → exits here! ✅
- Instead of riding to $4.76 for -$4,571, capped at -$500
- VERO total: +$18,583 - $500 - $429 = **+$17,654** (vs +$13,583 without this fix)

---

## Regression

After all 3 fixes:

```bash
# Squeeze OFF — must be unchanged
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

Then run all 4 stocks with squeeze + parabolic + fixes:
```bash
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/ARTL_2026-03-18_squeeze_v2.log

WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/VERO_2026-01-16_squeeze_v2.log

WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/ROLR_2026-01-14_squeeze_v2.log

WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py SXTC 2026-01-08 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/SXTC_2026-01-08_squeeze_v2.log
```

### Expected Results (optimistic)
| Stock | MP-Only | Squeeze V1 (para) | Squeeze V2 (fixes) | Notes |
|-------|---------|--------------------|--------------------|-------|
| ARTL | +$922 | +$7,762 | +$7,762 | HOD gate doesn't affect (squeezes ARE the HOD) |
| VERO | +$18,583 | +$13,583 | ~+$18,083 | HOD blocks bad $6.04 entry; dollar cap limits damage if it slips through |
| ROLR | +$6,444 | +$9,751 | ~+$16,000+ | Separate counters let MP's 6.5R trade fire too |
| SXTC | +$2,213 | +$2,213 | +$2,213 | No squeeze activity |

---

## Post-Flight

```bash
git add squeeze_detector.py simulate.py verbose_logs/
git commit -m "Squeeze V2 fixes: HOD gate, separate entry counters, dollar loss cap

Fix 1: WB_SQ_NEW_HOD_REQUIRED=1 — squeeze bar must be making new session high.
  Blocks VERO's bounce-phase entry ($5.88 < HOD $6.14).
  ARTL/ROLR first-leg squeezes unaffected (they ARE the HOD).

Fix 2: Separate entry counters per strategy type.
  Squeeze trades don't consume MP's max_entries_per_symbol slots.
  ROLR gets squeeze +\$9,751 AND MP's 6.5R trade.

Fix 3: WB_SQ_MAX_LOSS_DOLLARS=500 — absolute dollar cap on squeeze losses.
  Catches gap-throughs where tight parabolic stop is meaningless.
  VERO's -\$4,571 loss capped at -\$500.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

## Env Vars Added

| Var | Default | Purpose |
|-----|---------|---------|
| `WB_SQ_NEW_HOD_REQUIRED` | `1` (on) | Squeeze bar must be at/making new session HOD |
| `WB_SQ_MAX_LOSS_DOLLARS` | `500` | Absolute dollar cap on squeeze trade loss |

---

## Notes for CC

- Fix 1 goes in `squeeze_detector.py` — add `_session_hod` tracking and gate
- Fix 2 goes in `simulate.py` — quality gate needs `setup_type` awareness
- Fix 3 goes in `simulate.py` — `_squeeze_tick_exits()` gets new first check
- **Do NOT change micro_pullback.py or trade_manager.py**
- The HOD gate uses `>=` (bar high >= session HOD), meaning the bar can EQUAL the HOD
- Save all 4 verbose logs — we need to verify each fix individually
- If ROLR now shows 4 trades (2 squeeze + 2 MP), that's correct behavior
