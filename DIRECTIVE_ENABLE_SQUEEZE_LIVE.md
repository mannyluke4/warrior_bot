# Directive: Enable Squeeze V2 in Live Paper Trading

## Priority: HIGH — do this AFTER the volume bug fix is confirmed pushed
## Owner: CC
## Created: 2026-03-19 (Cowork)

---

## Context

Squeeze V2 has been validated on CHNR (+$429, 2 trades, 100% WR) and is about to run the
full 55-day YTD backtest overnight. Manny wants it enabled for tomorrow's live paper session
to catch bugs that only surface in live execution (websocket timing, order fills, quote spreads,
state machine resets between symbols, etc.). Paper mode = zero financial risk.

---

## Task

Add the following squeeze V2 env vars to the **bottom** of `.env`, before any trailing blank lines:

```bash
# --- Strategy 2: Squeeze/Breakout (V2 — live paper test 2026-03-20) ---
WB_SQUEEZE_ENABLED=1
WB_SQ_VOL_MULT=3.0
WB_SQ_MIN_BAR_VOL=50000
WB_SQ_MIN_BODY_PCT=1.5
WB_SQ_PRIME_BARS=3
WB_SQ_MAX_R=0.80
WB_SQ_LEVEL_PRIORITY=pm_high,whole_dollar,pdh
WB_SQ_PROBE_SIZE_MULT=0.5
WB_SQ_MAX_ATTEMPTS=3
WB_SQ_CORE_PCT=75
WB_SQ_TARGET_R=2.0
WB_SQ_RUNNER_TRAIL_R=2.5
WB_SQ_TRAIL_R=1.5
WB_SQ_STALL_BARS=5
WB_SQ_VWAP_EXIT=1
WB_SQ_PARA_ENABLED=1
WB_SQ_PARA_STOP_OFFSET=0.10
WB_SQ_PARA_TRAIL_R=1.0
WB_SQ_NEW_HOD_REQUIRED=1
WB_SQ_MAX_LOSS_DOLLARS=500
WB_SQ_PM_CONFIDENCE=1
```

## Verification

After adding the vars, verify they load correctly:

```bash
cd ~/warrior_bot
source venv/bin/activate
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
sq = os.getenv('WB_SQUEEZE_ENABLED', '0')
hod = os.getenv('WB_SQ_NEW_HOD_REQUIRED', '0')
cap = os.getenv('WB_SQ_MAX_LOSS_DOLLARS', '0')
print(f'Squeeze enabled: {sq}')
print(f'HOD gate: {hod}')
print(f'Dollar loss cap: \${cap}')
assert sq == '1', 'Squeeze not enabled!'
assert hod == '1', 'HOD gate not enabled!'
assert cap == '500', 'Dollar cap wrong!'
print('All squeeze vars loaded OK')
"
```

## Regression

Run regression to confirm squeeze vars don't affect MP-only trades (they shouldn't — squeeze
is gated behind its own detector and `setup_type` routing):

```bash
python simulate.py VERO 2026-01-16 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$18,583

python simulate.py ROLR 2026-01-14 07:00 12:00 --ticks --tick-cache tick_cache/
# Expected: +$6,444
```

## Important Notes

- Do NOT commit `.env` to git (it contains API keys). The `.gitignore` should already exclude it.
- The squeeze detector runs alongside MP — they don't interfere. Squeeze entries use separate
  counters (`WB_SQ_MAX_ATTEMPTS`) and separate exit routing (`sq_` prefix reasons).
- The `WB_SQ_MAX_LOSS_DOLLARS=500` cap limits total squeeze losses per session to $500.
- If anything looks off tomorrow, disabling is instant: change `WB_SQUEEZE_ENABLED=1` to `0`.

## Commit

No git commit needed — .env is gitignored. Just write the recap:

```bash
# Write recap to cowork_reports/
cat > cowork_reports/2026-03-19_squeeze_live_enable.md << 'EOF'
# CC Report: Squeeze V2 Enabled in Live .env
## Date: 2026-03-19

### What Was Done
Added 22 squeeze V2 env vars to .env for tomorrow's live paper session.

### Verification
- All vars load correctly (squeeze=1, HOD gate=1, dollar cap=$500)
- Regression: VERO +$18,583, ROLR +$6,444 (pass)

### Files Changed
- `.env` — added squeeze V2 block (not committed, gitignored)
EOF
```

---

*Directive created by Cowork — 2026-03-19*
