# Directive: Squeeze Parabolic Mode

## Priority: HIGH
## Owner: CC
## Created: 2026-03-19

---

## Context

Squeeze V1 is working — VERO gained +$1,259 extra from a second-leg squeeze entry.
But on parabolic first legs (ARTL $4.59→$8.19), the R-cap blocks ALL squeeze entries
because consolidation-based stops produce R values far exceeding the $0.80 cap.

The root cause: `_stop_from_consolidation()` looks back 3 bars, but on a parabolic move
every bar is a massive green candle. The lowest low of those bars is $0.50-$1.50 below
entry — way too wide for the R-cap.

**Solution: Parabolic mode.** When standard stop exceeds R-cap, fall through to a
level-based stop (just below the breakout level). Tight stop, probe sizing, tighter trail.

This is how Ross actually trades squeezes: "stop just below the support level" +
"trade small and add to winners" + "expect multiple small stopouts."

---

## Pre-Flight

```bash
cd ~/warrior_bot
source venv/bin/activate
git pull origin v6-dynamic-sizing
```

Read `STRATEGY_2_SQUEEZE_DESIGN.md` Section 5.2 for full rationale.

---

## Change 1: Add Parabolic Mode to `squeeze_detector.py`

### New Env Vars (read in `__init__`)
```python
self.para_enabled = os.getenv("WB_SQ_PARA_ENABLED", "1") == "1"
self.para_stop_offset = float(os.getenv("WB_SQ_PARA_STOP_OFFSET", "0.10"))
self.para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
```

### New Field on ArmedTrade

We need to know at exit time whether this is a parabolic entry. Add to the armed trade's
score_detail a `[PARABOLIC]` tag. Also track it so sim_mgr can use the tighter trail.

**Option A (minimal):** Encode in `score_detail` string — sim exit logic parses for `[PARABOLIC]`
**Option B (cleaner):** Add `parabolic: bool = False` field to ArmedTrade dataclass

Go with **Option A** for now to avoid touching micro_pullback.py's ArmedTrade dataclass.
The sim exit logic can check `"[PARABOLIC]" in trade.score_detail` to apply tighter trail.

### Modify `_try_arm()` in squeeze_detector.py

Current logic (lines ~280-288):
```python
if r > effective_max_r:
    self._reset("max_r_exceeded")
    return f"SQ_NO_ARM: max_r_exceeded ..."
```

New logic — instead of blocking, fall through to parabolic mode:
```python
if r > effective_max_r:
    if not self.para_enabled:
        self._reset("max_r_exceeded")
        return f"SQ_NO_ARM: max_r_exceeded R={r:.4f} > max={effective_max_r:.4f} ..."

    # --- Parabolic mode: level-based stop ---
    para_stop = level_price - self.para_stop_offset
    breakout_bar_low = bar["l"]
    para_stop = max(para_stop, breakout_bar_low)  # use tighter of the two
    para_r = entry_price - para_stop

    if para_r <= 0:
        self._reset("para_invalid_r")
        return f"SQ_NO_ARM: para_invalid_r (entry={entry_price:.4f} stop={para_stop:.4f})"

    # Even parabolic mode has a sanity cap (prevent absurd entries)
    if para_r > self.max_r:
        self._reset("para_max_r_exceeded")
        return (
            f"SQ_NO_ARM: para_max_r_exceeded R={para_r:.4f} > max={self.max_r:.4f} "
            f"(entry={entry_price:.4f} stop={para_stop:.4f})"
        )

    # Score with parabolic tag
    score, detail = self._score_setup(bar, vwap, level_name)
    detail += ";[PARABOLIC]"

    # Parabolic ALWAYS uses probe sizing
    size_mult = self.probe_size_mult

    self.armed = ArmedTrade(
        trigger_high=entry_price,
        stop_low=para_stop,
        entry_price=entry_price,
        r=para_r,
        score=score,
        score_detail=detail,
        setup_type="squeeze",
        size_mult=size_mult,
    )
    self._state = "ARMED"

    return (
        f"ARMED entry={entry_price:.4f} stop={para_stop:.4f} R={para_r:.4f} "
        f"score={score:.1f} level={level_name} setup_type=squeeze "
        f"[PARABOLIC] [PROBE={size_mult:.0%}] why={detail}"
    )
```

### Verbose Messages
```
[HH:MM] SQ_PRIMED: vol=X.Xx avg, bar_vol=Y, price=$Z above VWAP ($W)
[HH:MM] ARMED entry=$X stop=$Y R=$Z score=S level=pm_high setup_type=squeeze [PARABOLIC] [PROBE=50%]
```

---

## Change 2: Parabolic Exit Routing in `simulate.py`

In `_squeeze_tick_exits()`, when the trade has `[PARABOLIC]` in its score_detail,
use the tighter trailing stop:

### In SimTradeManager.__init__
```python
self.sq_para_trail_r = float(os.getenv("WB_SQ_PARA_TRAIL_R", "1.0"))
```

### In `_squeeze_tick_exits()`, pre-target trailing stop section (~line 500):
```python
# 3) Trailing stop (pre-target)
if t.r > 0:
    # Use tighter trail for parabolic entries
    is_parabolic = "[PARABOLIC]" in (t.score_detail or "")
    trail_r = self.sq_para_trail_r if is_parabolic else self.sq_trail_r
    trail_price = t.peak - (trail_r * t.r)
    if price <= trail_price:
        reason = "sq_para_trail_exit" if is_parabolic else "sq_trail_exit"
        ...
```

Also in the post-target runner section: parabolic runners should use `sq_para_trail_r`
for the runner trail too (instead of `sq_runner_trail_r`), since the R is so small that
2.5R is still very tight.

Actually, reconsider: with para R = $0.10, the runner trail at 2.5R = $0.25 below peak.
That's reasonable for a $5+ stock. Keep the standard runner trail for parabolic too.
The tighter pre-target trail (1.0R) is the main protection.

---

## Change 3: New Verbose Sim Directive

After implementing, we need CC to run verbose sims with squeeze+parabolic ON to see
exactly what happens. Create a diagnostic run:

```bash
# ARTL — the parabolic first-leg case
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py ARTL 2026-03-18 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/ARTL_2026-03-18_squeeze_para.log

# VERO — verify standard squeeze still works, check if para fires on early move
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/VERO_2026-01-16_squeeze_para.log

# ROLR — another parabolic runner
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/ROLR_2026-01-14_squeeze_para.log

# SXTC — moderate mover, verify squeeze doesn't interfere with MP cascading
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
python simulate.py SXTC 2026-01-08 07:00 12:00 --ticks --tick-cache tick_cache/ -v \
2>&1 | tee verbose_logs/SXTC_2026-01-08_squeeze_para.log
```

---

## Regression

**CRITICAL**: Squeeze OFF must still reproduce:
```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

Also verify squeeze ON (para OFF) still matches V1 results:
```bash
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=0 \
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$19,842 (MP +$18,583, squeeze +$1,259)
```

---

## Post-Flight

```bash
git add squeeze_detector.py simulate.py verbose_logs/
git commit -m "Squeeze parabolic mode: level-based stops for first-leg entries

When standard consolidation-based stop exceeds R-cap, fall through to
parabolic mode: stop just below the breakout level ($0.10 offset).

- WB_SQ_PARA_ENABLED=1 (ON by default when squeeze is enabled)
- WB_SQ_PARA_STOP_OFFSET=0.10 (stop = level - offset)
- WB_SQ_PARA_TRAIL_R=1.0 (tighter trail than standard 1.5R)
- Always probe sizing on parabolic entries (never full size)
- [PARABOLIC] tag in score_detail for tracking/exit routing

Designed to capture ARTL-style first-leg moves blocked by R-cap in V1.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

## Notes for CC

- **Only touch `squeeze_detector.py` and `simulate.py`** — no changes to MP
- The parabolic fallback is in `_try_arm()` only — the rest of the state machine is unchanged
- `[PARABOLIC]` tag is checked via string match in score_detail — simple but effective
- Parabolic entries ALWAYS use probe sizing regardless of `_has_winner`
- Save all 4 verbose logs to `verbose_logs/` — we need to analyze them
- If breakout bar low is ABOVE `level - offset`, use the bar low (it's tighter)
- Parabolic mode still respects max_r as a sanity cap — just uses the new para_r not the old consolidation R
