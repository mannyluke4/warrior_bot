# CC Report: Squeeze V2 Enabled in Live .env
## Date: 2026-03-19
## Machine: Mac Mini

### What Was Done
Added 22 squeeze V2 env vars to .env for tomorrow's live paper session (2026-03-20).

### Verification
- All vars load correctly:
  - `WB_SQUEEZE_ENABLED=1`
  - `WB_SQ_NEW_HOD_REQUIRED=1` (HOD gate)
  - `WB_SQ_PARA_ENABLED=1` (parabolic mode)
  - `WB_SQ_PROBE_SIZE_MULT=0.5` (half size probes)
  - `WB_SQ_MAX_LOSS_DOLLARS=500` (dollar loss cap)
- Regression: VERO +$18,583, ROLR +$6,444 (pass)

### Squeeze V2 Config Summary
| Setting | Value | Purpose |
|---------|-------|---------|
| Detection: vol mult | 3.0x | Bar volume must be 3x average |
| Detection: min bar vol | 50,000 | Absolute volume floor |
| Detection: body pct | 1.5% | Minimum candle body size |
| Detection: prime bars | 3 | Max bars waiting for level break |
| Risk: max R | $0.80 | Cap on risk per share |
| Risk: probe size | 0.5x | Half size on first attempts |
| Risk: max attempts | 3 | Per stock per day |
| Risk: dollar cap | $500 | Max loss per squeeze trade |
| Exit: trail R | 1.5R | Pre-target trailing stop |
| Exit: target R | 2.0R | Core profit target (75% exit) |
| Exit: runner trail | 2.5R | Post-target runner trail |
| Exit: stall bars | 5 | Time stop if no new high |
| Exit: VWAP loss | ON | Exit on close below VWAP |
| Parabolic: enabled | ON | Level-based stops when R-cap exceeded |
| Parabolic: stop offset | $0.10 | Stop below breakout level |
| Parabolic: trail R | 1.0R | Tighter trail for para entries |
| HOD gate | ON | Bar must be making new session highs |

### Kill Switch
If anything looks off: change `WB_SQUEEZE_ENABLED=1` to `0` in `.env` and restart bot.

### Files Changed
- `.env` — added squeeze V2 block (not committed, gitignored)
- `cowork_reports/2026-03-19_squeeze_live_enable.md` (this file)
