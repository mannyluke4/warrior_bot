# DIRECTIVE: Chop Gate v3 — Three Intraday Gates + Cross-Session Memory

**Date:** May 12, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P1 — build this week, paper-test Wed-Fri, decide promotion Friday EOD  
**Branch:** `v2-ibkr-migration`  
**Predecessor:** `cowork_reports/2026-05-12_fatn_chart_review_questionnaire.md`

---

## Decision

Build `chop_gate_v3` as an **additional gate layer behind chop_gate_v2** (v2 runs first, v3 runs second). Environment-gated, defaults OFF, paper-tested for 5 sessions before promotion consideration.

Based on visual analysis of FATN charts and cross-comparison with the SST 5/11 winner, three intraday metrics cleanly separate the loser from the winner. A fourth cross-session memory rule addresses FATN's 3-loss streak across 5/6, 5/8, 5/12.

---

## What Gets Built

A new module `chop_gate_v3.py` containing four functions and a session-history persistence layer. Each function is a standalone metric with a deterministic threshold. The composite gate uses AND logic on the three intraday checks plus the cross-session veto.

### Intraday Metric 1: Failed HOD Attempts

The strongest single signal from the FATN chart. Two distinct attempts at session high that got rejected back, within the 120 minutes preceding entry.

```python
def failed_hod_attempts(bars_1m: list, lookback_minutes: int = 120) -> int:
    """Count distinct attempts at session HOD that got rejected.
    
    An 'attempt' is a bar whose high reached within 1% of session HOD.
    A 'rejection' means all 3 subsequent bars closed >0.5% below the attempt's high.
    """
    if len(bars_1m) < 4:
        return 0
    
    hod = max(b.high for b in bars_1m)
    recent = bars_1m[-lookback_minutes:] if len(bars_1m) > lookback_minutes else bars_1m
    
    attempts = 0
    i = 0
    while i < len(recent) - 3:
        bar = recent[i]
        if bar.high >= hod * 0.99:
            next3 = recent[i+1:i+4]
            if all(b.close < bar.high * 0.995 for b in next3):
                attempts += 1
                i += 4  # skip the 3-bar rejection window so we don't double-count
                continue
        i += 1
    
    return attempts
```

**Veto threshold: `failed_hod_attempts >= 2`** within last 120 minutes.

### Intraday Metric 2: MACD Curling Over

A stock with MACD curling over at the moment of arm is exhaling, not inhaling. Entering long into that is fighting the immediate momentum.

```python
def macd_rolling_over(macd_state) -> bool:
    """True if MACD is in early bearish curl-over phase.
    
    Two trigger conditions (OR):
    1. MACD line crossed below signal line in the last 2 bars
    2. Histogram has decreased for 3 consecutive bars while starting positive
    """
    # Required: last 3 bars of MACD line, signal line, histogram
    if not macd_state.has_history(bars=3):
        return False
    
    line_now = macd_state.line_at(0)
    line_1ago = macd_state.line_at(1)
    line_2ago = macd_state.line_at(2)
    sig_now = macd_state.signal_at(0)
    sig_2ago = macd_state.signal_at(2)
    hist_now = macd_state.histogram_at(0)
    hist_1ago = macd_state.histogram_at(1)
    hist_2ago = macd_state.histogram_at(2)
    
    # Trigger 1: line crossed below signal in last 2 bars
    crossed_down = (line_2ago > sig_2ago) and (line_now < sig_now)
    
    # Trigger 2: histogram decreasing for 3 consecutive bars after being positive
    decreasing_from_positive = (
        hist_2ago > 0 and 
        hist_2ago > hist_1ago > hist_now
    )
    
    return crossed_down or decreasing_from_positive
```

**Veto threshold: `macd_rolling_over == True` at moment of arm.**

The bot already maintains MACD state per symbol for the WB detector. Confirm the existing implementation exposes per-bar history. If not, extend `MACDState` to keep the last 4 bars of `(line, signal, histogram)` tuples.

### Intraday Metric 3: Volume Follow-Through

A real breakout has sustained volume on the breakout bar AND the following bars. A fake breakout has a single fat-volume spike followed by dead bars.

```python
def has_volume_followthrough(bars_1m: list, lookback: int = 10) -> bool:
    """True if recent breakout-sized bars had at least 30% volume follow-through.
    
    A 'breakout-sized bar' is one with body >= 1.5% of price AND volume >= 3x recent avg.
    'Follow-through' means the next 2 bars each had >= 30% of the breakout bar's volume.
    
    If no breakout-sized bars exist in the lookback, returns True (no warning).
    """
    if len(bars_1m) < lookback + 2:
        return True  # Not enough history to evaluate
    
    recent = bars_1m[-(lookback + 2):]
    eval_window = recent[:-2]  # bars we'll check, leaving room for "next 2"
    avg_vol = sum(b.volume for b in eval_window) / len(eval_window) if eval_window else 0
    
    if avg_vol == 0:
        return True  # No volume to compare against
    
    # Find the most recent breakout-sized bar
    for i in range(len(eval_window) - 1, -1, -1):
        bar = eval_window[i]
        body_pct = abs(bar.close - bar.open) / bar.open if bar.open > 0 else 0
        if body_pct >= 0.015 and bar.volume >= 3 * avg_vol:
            # Found one — check follow-through
            next2 = recent[i+1:i+3]
            if len(next2) >= 2:
                if all(b.volume < 0.3 * bar.volume for b in next2):
                    return False  # Failed follow-through
            return True  # Most recent breakout had OK follow-through
    
    return True  # No breakout-sized bar found
```

**Veto threshold: `has_volume_followthrough == False`.**

### Cross-Session Memory

FATN has lost on 5/6, 5/8, and 5/12 across three different scoring tiers. The pattern is the symbol itself, not any single intraday metric.

```python
# In a new file: session_history.py

import json
import os
from pathlib import Path
from datetime import datetime, timedelta

class SessionHistory:
    """Tracks per-symbol win/loss history across sessions.
    
    Persists to state/symbol_session_history.json.
    Survives bot restarts. Updated after every closed trade.
    """
    
    def __init__(self, history_file: str = "state/symbol_session_history.json"):
        self.path = Path(history_file)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()
    
    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    
    def _save(self):
        self.path.write_text(json.dumps(self._data, indent=2, default=str))
    
    def record_trade(self, symbol: str, date: str, pnl: float, r_multiple: float):
        """Record a closed trade. Call from the exit-handling path."""
        if symbol not in self._data:
            self._data[symbol] = {"trades": [], "blacklisted_until": None}
        self._data[symbol]["trades"].append({
            "date": date,
            "pnl": pnl,
            "r_multiple": r_multiple,
            "win": pnl > 0,
        })
        # Keep only the last 30 trades per symbol (storage hygiene)
        self._data[symbol]["trades"] = self._data[symbol]["trades"][-30:]
        self._maybe_update_blacklist(symbol)
        self._save()
    
    def _maybe_update_blacklist(self, symbol: str):
        """Apply blacklist if recent loss pattern matches the rule."""
        trades = self._data[symbol]["trades"]
        if not trades:
            return
        
        # Look at last 10 trades on this symbol
        recent = trades[-10:]
        losses = sum(1 for t in recent if not t["win"])
        wins = sum(1 for t in recent if t["win"])
        
        # Veto if 3+ losses in last 10 sessions AND fewer wins than losses
        if losses >= 3 and wins < losses:
            # Set blacklist for 5 sessions from latest trade date
            latest_date = datetime.fromisoformat(recent[-1]["date"]).date()
            self._data[symbol]["blacklisted_until"] = (
                latest_date + timedelta(days=7)  # ~5 trading days
            ).isoformat()
        else:
            # Clear blacklist if conditions no longer met
            self._data[symbol]["blacklisted_until"] = None
    
    def is_blacklisted(self, symbol: str, today: str) -> tuple[bool, str]:
        """Returns (is_blacklisted, reason)."""
        entry = self._data.get(symbol)
        if not entry or not entry.get("blacklisted_until"):
            return False, ""
        
        until = entry["blacklisted_until"]
        today_date = datetime.fromisoformat(today).date()
        until_date = datetime.fromisoformat(until).date()
        
        if today_date >= until_date:
            # Blacklist expired, clear it
            self._data[symbol]["blacklisted_until"] = None
            self._save()
            return False, ""
        
        return True, f"recent_loss_pattern (3+ losses in last 10, blacklisted until {until})"
    
    def manual_unblacklist(self, symbol: str):
        """Manual override — e.g., if a stock has clearly changed character."""
        if symbol in self._data:
            self._data[symbol]["blacklisted_until"] = None
            self._save()
```

### Composite Gate

```python
# In chop_gate_v3.py

from session_history import SessionHistory

_session_history = SessionHistory()

def chop_gate_v3(symbol: str, bars_1m: list, macd_state, today: str) -> tuple[bool, str]:
    """Returns (passes, reason).
    
    Runs AFTER chop_gate_v2 has already passed. This is a second-layer check.
    All four conditions must clear for entry to fire.
    """
    # Cross-session veto (hard veto, no override)
    is_blacklisted, reason = _session_history.is_blacklisted(symbol, today)
    if is_blacklisted:
        return False, reason
    
    # Intraday gates — AND logic, all must pass
    if failed_hod_attempts(bars_1m) >= 2:
        return False, "failed_hod_attempts_>=2"
    
    if macd_rolling_over(macd_state):
        return False, "macd_rolling_over"
    
    if not has_volume_followthrough(bars_1m):
        return False, "no_volume_followthrough"
    
    return True, "passed"
```

---

## Wiring Into the Bot

### In `bot_alpaca_subbot.py` (and the engine's `wb_bot.py` if it exists)

Find the place where `chop_gate_v2` is currently called for WB entries. Add the v3 call IMMEDIATELY AFTER v2 passes:

```python
# Existing v2 check
v2_passes, v2_reason = chop_gate_v2(symbol, ...)
if not v2_passes:
    log.info(f"[CHOP_REJECT] {symbol}: v2 {v2_reason}")
    return

# NEW: v3 check
if os.getenv("WB_CHOP_GATE_V3_ENABLED", "0") == "1":
    v3_passes, v3_reason = chop_gate_v3(symbol, bars_1m, macd_state, today)
    if not v3_passes:
        log.info(f"[CHOP_REJECT_V3] {symbol}: {v3_reason}")
        return

# Existing entry logic continues
```

### In the trade-closing path

After every WB exit, record the outcome:

```python
# In exit handling, after pnl is finalized:
from session_history import SessionHistory
SessionHistory().record_trade(
    symbol=position.symbol,
    date=datetime.now(ET).date().isoformat(),
    pnl=realized_pnl,
    r_multiple=realized_pnl / risk_dollars if risk_dollars else 0,
)
```

This should run regardless of whether v3 is enabled — we want the history populated either way so when we DO promote v3 to ON, it has the prior session data.

### What about chop_bypass at score≥9?

**Critical decision:** chop_gate_v3 also vetoes chop_bypass setups. The whole point is "this symbol/setup is bad regardless of how high the score is." If score-10 setups bypass v3, we won't catch FATN-style problems.

In the bypass path:
```python
if score >= 9 and chop_bypass_enabled:
    # NEW: v3 still applies to bypass
    if os.getenv("WB_CHOP_GATE_V3_ENABLED", "0") == "1":
        v3_passes, v3_reason = chop_gate_v3(symbol, bars_1m, macd_state, today)
        if not v3_passes:
            log.info(f"[CHOP_REJECT_V3] {symbol}: bypass blocked by v3: {v3_reason}")
            return
    # Existing bypass logic
```

---

## Validation Before Live (MANDATORY)

Before paper-testing, run the gate against historical data to confirm it doesn't kill the existing winners.

```python
# scripts/validate_chop_gate_v3.py
# Replay every WB entry signal from May 1 - May 12 against chop_gate_v3
# For each one, determine: would v3 have blocked it?
# Bucket the outcomes:
#   - Blocked, was a loser → saved (good)
#   - Blocked, was a winner → false positive (bad)
#   - Passed, was a winner → preserved (good)
#   - Passed, was a loser → not caught by v3 (acceptable in moderation)
```

**Acceptance criteria for paper-test promotion:**

| # | Metric | Threshold |
|---:|---|:---:|
| 1 | Historical losers blocked by v3 | ≥ 60% |
| 2 | Historical winners preserved by v3 | ≥ 90% |
| 3 | Top-3 winners by P&L (ATRA 5/8, SST 5/11, FATN 5/8 N/A — it's a loser) preserved | 100% |
| 4 | All three FATN losses blocked | 100% (this is the validation point) |

If criterion 3 fails (any major winner blocked), the gate thresholds are wrong. Loosen and retry.

If criterion 2 falls below 90%, we're losing too many winners. The likely culprit is `macd_rolling_over` being too sensitive — loosen the histogram-decreasing trigger first.

Save validation results to: `cowork_reports/2026-05-XX_chop_gate_v3_validation.md`

---

## Paper Test Plan

**Wednesday May 13 — Friday May 15: paper-test with `WB_CHOP_GATE_V3_ENABLED=1`**

Both setups run. Setup A and Setup B both pick up the env var. Compare daily output:

- Counts: WB_ARMED, CHOP_REJECT (v2), CHOP_REJECT_V3, fills, wins, losses
- P&L: total per session, with v3 active vs the 5/8 and 5/11 baselines
- Specific symbols: does v3 reject any setups that turn out to be winners?
- Cross-session blacklist hits: does anything get blacklisted? Anything get UNblacklisted?

Daily EOD report from CC: `cowork_reports/daily_trades/2026-05-XX_v3_paper_test.md` summarizing the day.

**Friday EOD decision:** Promote v3 to live-money architecture (off paper, into the June 4 readiness path) IF:
1. WR over Wed-Fri ≥ historical Wed-Fri WR baseline
2. No major winner was vetoed by v3 (visible from daily logs)
3. The FATN-style symbols got blocked when they appeared

---

## Env Vars

```bash
# Master toggle (default OFF)
WB_CHOP_GATE_V3_ENABLED=0

# Thresholds (all tunable from .env without code changes)
WB_V3_HOD_LOOKBACK_MINUTES=120
WB_V3_HOD_FAIL_THRESHOLD=2
WB_V3_VOL_LOOKBACK_BARS=10
WB_V3_VOL_FOLLOWTHROUGH_MIN_PCT=0.30
WB_V3_BREAKOUT_BODY_MIN_PCT=0.015
WB_V3_BREAKOUT_VOL_MIN_MULT=3.0

# Cross-session memory
WB_V3_SESSION_HISTORY_LOOKBACK=10
WB_V3_SESSION_HISTORY_LOSS_THRESHOLD=3
WB_V3_SESSION_HISTORY_BLACKLIST_DAYS=7  # ~5 trading days
WB_V3_SESSION_HISTORY_FILE=state/symbol_session_history.json
```

---

## What NOT to Do

- ❌ Do NOT replace v2. v3 is an additional layer behind v2, not a substitute.
- ❌ Do NOT enable v3 live without the historical validation passing all 4 criteria.
- ❌ Do NOT modify the squeeze bot — chop gate v3 is WB-specific (squeeze has its own gating).
- ❌ Do NOT change WB scoring or detection logic.
- ❌ Do NOT skip the cross-session memory layer just because it's new code — it's the only mechanism that catches FATN's repeat-loser pattern.
- ❌ Do NOT make the chop_bypass at score≥9 skip v3. The whole point is v3 catches problems that scoring misses.
- ❌ Do NOT change Setup A while Setup B is the active experimentation surface.

---

## Reversal Path

If v3 produces a bad outcome:

```bash
# Disable instantly via env var
WB_CHOP_GATE_V3_ENABLED=0

# OR manual unblacklist if a symbol is unfairly stuck:
python -c "from session_history import SessionHistory; SessionHistory().manual_unblacklist('FATN')"
```

No code revert needed. v3 is purely additive and env-controlled.

---

## Files Touched

```
[NEW]   chop_gate_v3.py
[NEW]   session_history.py
[NEW]   scripts/validate_chop_gate_v3.py
[EDIT]  bot_alpaca_subbot.py        # wire v3 into chop check, record trade history on close
[EDIT]  wb_bot.py (engine)           # mirror the same wiring
[EDIT]  .env.example                 # add v3 env vars
[NEW]   state/symbol_session_history.json   # auto-created at first trade
[NEW]   cowork_reports/2026-05-XX_chop_gate_v3_validation.md
[NEW]   cowork_reports/daily_trades/2026-05-XX_v3_paper_test.md  (per session)
```

---

## Acceptance Gate Summary

**Wednesday May 13:**
- v3 code shipped to repo
- Validation script run on May 1-12 historical data
- All 4 validation criteria pass → green light for Wednesday afternoon paper enable
- If criterion 3 fails → loosen thresholds, re-validate, do not enable until passing

**Friday May 15 EOD:**
- 3 paper-test sessions complete (5/13, 5/14, 5/15)
- WR and P&L analyzed vs 5/8 and 5/11 baselines
- No major winner blocked
- FATN-style symbols correctly blocked
- → Promotion decision for the June 4 live-money path

---

*The bot can't see what the eye sees. v3 codifies three of the most consistent visual cues into numbers. v2 catches the obvious chop. v3 catches the chart-shape failures.*
