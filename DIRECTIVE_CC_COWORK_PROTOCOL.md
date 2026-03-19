# Directive: CC ↔ Cowork Communication Protocol

## Priority: IMMEDIATE — Read before starting any work
## Updated: 2026-03-19

---

## The Problem

Cowork (Opus) runs in a VM that **directly mounts** `~/warrior_bot/` from the host Mac.
It can see every file in the repo in real-time — no git pull needed. BUT:

1. Cowork **cannot reach GitHub** (DNS fails), so `git pull` is impossible from the VM.
2. If CC runs on a **different machine** than where Cowork's mount originates, Cowork
   cannot see CC's work until it's committed AND the mount is on the same machine.
3. Verbose logs, backtest results, and session reports are critical for Cowork's analysis
   but have been getting lost between machines.

---

## The Protocol

### Rule 1: Always Write Recaps to `cowork_reports/`

After completing any directive, backtest, or significant task, CC MUST write a recap
markdown file to `cowork_reports/` with the results:

```
cowork_reports/
  YYYY-MM-DD_<short-description>.md
```

**Example filenames:**
- `2026-03-19_chnr_backtest.md`
- `2026-03-19_squeeze_ytd_overnight.md`
- `2026-03-19_scanner_timing_fix.md`

### Rule 2: Recap Format

Every recap MUST include:

```markdown
# CC Report: <Title>
## Date: YYYY-MM-DD
## Machine: Mac Mini / MBP

### What Was Done
<1-3 sentences>

### Commands Run
<Exact commands with env vars>

### Results
<Copy/paste the full backtest summary table>
<Or paste relevant terminal output>

### Key Observations
<Any patterns, surprises, or issues noticed>

### Files Changed
<List of files modified/created>
```

### Rule 3: Verbose Logs Go in `verbose_logs/`

All verbose backtest output MUST be saved:
```bash
python simulate.py SYMBOL DATE START END --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/SYMBOL_DATE_description.log
```

### Rule 4: Always Commit + Push After Work

```bash
git add cowork_reports/ verbose_logs/ <any changed files>
git commit -m "descriptive message

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

### Rule 5: If Running on a Different Machine Than Cowork's Mount

If CC is running on a machine where the warrior_bot folder is NOT the same physical
folder Cowork sees (i.e., CC is on MBP but Cowork is mounted from Mac Mini), then
git push is the ONLY way Cowork can see results. In this case:

- Push frequently (after each significant result, not just at end of session)
- Include all output files in the commit (logs, reports, state files)
- Cowork will note in chat when it can't see expected files

---

## What Cowork Needs to Analyze Results

For backtests, Cowork needs these files to do its job:

1. **Verbose log** (`verbose_logs/SYMBOL_DATE_*.log`) — full sim output with detector
   states, arm/trigger events, exit reasons
2. **Recap** (`cowork_reports/YYYY-MM-DD_*.md`) — summary with the backtest report table
3. **State file** (for YTD runs: `ytd_v2_backtest_state*.json`) — per-day breakdown

Without these, Cowork has to ask Manny to paste results manually, which slows everything down.

---

## Current Outstanding Request

CC ran a CHNR 2026-03-19 backtest but the results are not visible to Cowork.
Please re-run (or find the output) and save:

```bash
# Run from 07:00 (not 08:00!) with squeeze V2:
WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py CHNR 2026-03-19 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/CHNR_2026-03-19_squeeze_v2.log

# Also run MP-only for comparison:
WB_SQUEEZE_ENABLED=0 \
python simulate.py CHNR 2026-03-19 07:00 12:00 --ticks --tick-cache tick_cache/ --verbose 2>&1 \
| tee verbose_logs/CHNR_2026-03-19_mp_only.log

# Write recap:
# cowork_reports/2026-03-19_chnr_backtest.md

# Commit and push everything
git add verbose_logs/CHNR* cowork_reports/
git commit -m "CHNR 2026-03-19 backtest: MP-only and squeeze V2 from 07:00

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

*Protocol established by Cowork — 2026-03-19*
