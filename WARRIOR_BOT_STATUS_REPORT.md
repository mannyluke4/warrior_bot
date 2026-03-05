# Warrior Bot — Project Status Report
## Updated: 2026-03-05 (Post-Session)

---

## Executive Summary

Major infrastructure day. No live trading P&L, but the three-agent workflow is now significantly more autonomous. Duffy can run backtests, talk directly to Claude Code, and read/write the watchlist live. The remaining blocker is autonomous scanner access.

---

## Current Architecture State

### Recent Commits

| Commit | Date | What It Did |
|--------|------|-------------|
| `80fa4c1` | Mar 3 | Reconcile grace period fix + trailing stop system (validated) |
| `9675dfd` | Mar 3 | EDSA trade report: final outcome +$3,525 net |
| `93e67f7` | Mar 3 | Scanner time window directive + status report update |

### Current Live Config (.env)

```
WB_EXIT_MODE=signal
WB_CLASSIFIER_ENABLED=1
WB_CLASSIFIER_SUPPRESS_ENABLED=0
WB_ENABLE_L2=0
WB_TRAILING_STOP_ENABLED=0  (implemented, off by default)
```

---

## Infrastructure — What Changed 2026-03-05

### ✅ Duffy Can Now Run Backtests Directly
- Linux venv built at `/Users/mannyluke/warrior_bot/venv`
- All packages installed: alpaca-py, databento, pandas, pytz, python-dotenv, yfinance, etc.
- Swap added to VM — tick mode backtests no longer OOM
- Correct invocation confirmed:
  ```bash
  cd /Users/mannyluke/warrior_bot && source venv/bin/activate
  python simulate.py TICKER DATE 07:00 12:00 --profile A --ticks --no-fundamentals
  ```
- All 6 Profile A regressions verified independently by Duffy ✅

### ✅ Duffy Can Talk Directly to Claude Code (ACP)
- `acpx` plugin installed and configured
- `acp` config block added to `openclaw.json`
- `acpx` binary installed to user-writable path (permission workaround)
- ACP spawn confirmed working: `sessions_spawn` with `runtime: "acp"`, `agentId: "claude"`
- Exec approval bug fixed: `tools.elevated` stuck-flag bug (OpenClaw 2026.3.2) resolved by explicitly setting `elevated.enabled: false` + `elevatedDefault: "off"`

### ✅ Duffy Can Read/Write Watchlist Live
- `/Users/mannyluke/warrior_bot/watchlist.txt` — full read/write access confirmed
- Ready for autonomous watchlist management during live sessions

### ❌ Scanner Access — Still Manual
- CDP approach requires Luke to launch Chrome with `--remote-debugging-port=9222` manually
- Socket.IO direct auth (no browser) not yet implemented — this is the target solution
- Today's session: scanner data pasted manually by Luke

---

## Multi-Profile System

### Profile Status

| Profile | Tag | Status | Description |
|---|---|---|---|
| A | `:A` (default) | **PROVEN** ✅ | Micro-float <5M, 7am scanner, L2 OFF, 44% WR, +$24,737 |
| B | `:B` | **VALIDATED** ✅ | Mid-float 5-50M, 7am scanner, L2 ON, +$4,859 Databento |
| C | `:C` | **NOT VALIDATED** ❌ | Do not use |
| X | `:X` | **SKIP IN LIVE** ⚠️ | Net negative, skip in live trading |

---

## Regression Benchmarks (All Verified by Duffy 2026-03-05)

### Profile A (Alpaca ticks, 07:00-12:00 ET, --no-fundamentals)

| Stock | Date | Expected P&L | Verified |
|-------|------|-------------|---------|
| VERO | 2026-01-16 | +$6,890 | ✅ |
| GWAV | 2026-01-16 | +$6,735 | ✅ |
| APVO | 2026-01-09 | +$7,622 | ✅ |
| BNAI | 2026-01-28 | +$5,610 | ✅ |
| MOVE | 2026-01-27 | +$5,502 | ✅ |
| ANPA | 2026-01-09 | +$2,088 | ✅ |

---

## JZXN Study — 2026-03-04

Ross's big day (~$50k+). JZXN was the only Profile A qualifier on the scanner.

- Float: 1.32M | Scanner: 7:16 AM ET | Gap: 57-91%
- Bot result (simulated): **+$333 (+0.3R)**
- Entry: $1.36 @ 7:17 AM | Exit: $1.45 @ 7:19 AM (bearish engulfing)
- **Root cause of small capture:** Bearish engulfing exit fired too early on first 3-minute candle of a fast micro-float move
- **Missed re-entry:** 7:54 AM signal scored 12.5 (ABCD + Volume Surge + Red-to-Green) — blocked by VWAP loss reset
- Full study: `JZXN_TRADE_STUDY_20260304.md`
- Sent to Perplexity for tuning analysis

---

## Immediate Priorities

1. **CRITICAL — Autonomous scanner access** — Socket.IO direct auth. See `DUFFY_INFRASTRUCTURE_STATUS_20260305.md`
2. **HIGH — Scanner time window directive** — `SCANNER_TIME_WINDOW_DIRECTIVE.md` — ready for Claude Code
3. **HIGH — JZXN tuning** — Perplexity analyzing bearish engulfing suppression + high-score VWAP override. See `JZXN_TRADE_STUDY_20260304.md`
4. **MEDIUM — Trailing stop ON/OFF decision** — passed regressions, not yet tested live
5. **MEDIUM — YouTube unblocked in VM** — needed for Ross video analysis

## Known Issues / Open Items

1. **Scanner access** — highest priority blocker for full autonomy
2. **Exec approvals** — fixed (elevatedDefault bug), config: `tools.elevated.enabled=false, elevatedDefault=off`
3. **ports.ubuntu.com blocked** — apt installs require limactl shell from Mac. Swap added manually.
4. **Profile A = Alpaca ticks only** — use `--ticks --no-fundamentals` for regressions
5. **ACP sessions don't push results back** — Duffy checks results files directly rather than waiting for push

---

## User Preferences (CRITICAL)

- **Signal mode cascading exits must NEVER be suppressed**
- "I'd rather have consistent $200-500 hits every day than losing 20k, then getting one good 5k hit"
- Scanner TIME matters — pre-scanner profits don't count
- Regressions are non-negotiable — all 6 Profile A baselines must hold after every change
- **"Let's leave nothing on the table!"**

---

*Report updated by Duffy — 2026-03-05 post-session*
