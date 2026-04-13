# Directive — Decouple Nightly Tick Batch from the Bot Process

**Priority:** P0
**Author:** Cowork (Opus), 2026-04-11
**Greenlit by:** Manny
**Scope:** The schedule and process tree of the nightly tick-cache populator. **Do not touch bot logic, X01 config, exit rules, detector gates, or scanner thresholds.**

---

## Read this first — context that changes how you should approach this task

**Manny was right all day on 2026-04-10.** He kept flagging that the backtest results in the morning report were inconsistent with the bot's documented behavior against the price action he knew from Ross's recap and from his own chart. CC and Cowork kept pushing back and trying to "fix" a working system based on those bad backtest numbers. The bot did exactly what it was supposed to do — the simulator was wrong because its tick input was wrong.

The *proximate* reason the simulator had bad input was the silent Alpaca fallback in `simulate.py` (see sibling directive `2026-04-11_directive_kill_alpaca_fallback.md`). The *upstream* reason that fallback was exercised at all is the subject of this directive: **the nightly tick cache batch did not run on 2026-04-10 because the bot was frozen.** When CC later ran a post-mortem sim, the cache file didn't exist, and the now-infamous fallback branch fired.

If the nightly batch had been on its own schedule — independent of whether the bot process was alive — the cache would have been populated as usual, `simulate.py` would have loaded from cache, and none of the 2026-04-10 data-integrity scramble would have happened. This directive is about that decoupling.

**This directive changes scheduling and process wiring. That is all it changes.** Do not use it as an excuse to rewrite the batch script, port it between feeds, add features, or "clean it up while you're in there." Minimal, targeted, reversible change.

---

## What we know

Evidence from the repo as of 2026-04-11 morning:

- Every trading day from 2026-04-01 through 2026-04-09 has a full tick cache: 113–131 files per date, directory mtime stamped at ~18:00:00–18:00:04 local time. That's a cron or scheduled job firing at 6:00 PM local (end of evening session + a beat) and taking a few seconds to create the directory.
- 2026-04-10 has only 3 files, and those files were not written by the nightly — they were written by `simulate.py`'s silent Alpaca fallback at 14:02 and 14:10 local time during CC's morning post-mortem. The real nightly run for 2026-04-10 never happened.
- The bot froze on 2026-04-10 ~05:34 ET on a stale Alpaca SSL socket (fix committed `cab9754`). The bot PID was kept alive by the `daily_run_v3.sh` watchdog until the normal shutdown sequence, but the bot itself was not processing anything.
- `daily_run_v3.sh` ends its watchdog loop at 18:05 MT, then runs its shutdown + log push block. It does **not** call any tick cache batch script, so the 18:00 mtime on the cache dirs is not coming from `daily_run_v3.sh`. It has to be coming from something else.

What we don't know (this is for you to find out):

- What script populates the nightly tick cache. Candidates include `cache_tick_data.py`, `ibkr_tick_fetcher.py` driven by an unknown wrapper, `run_box_scanner_ytd.py`, `run_scanner_batch.py`, or a launchd plist / cron entry we haven't grep'd yet.
- How that script is scheduled. Possibilities: user crontab, launchd plist in `~/Library/LaunchAgents/`, a systemd-style wrapper, a trailing step inside `daily_run_v3.sh` we missed, a manual-only script Manny runs himself (unlikely given the clean 18:00 mtimes every weekday).
- Whether that script depends on the bot process in any way. Hypotheses: it's sequenced *after* bot shutdown in `daily_run_v3.sh` or `check_bot.sh` via an exit-trap step; it reads the bot's in-memory state via some IPC; it checks for the presence of a `bot_v3_hybrid.py` PID file before starting; it's `nohup`'d by the bot itself as a child process and dies when the parent does.

Your first job is to find these two answers, then decouple.

## What to do — Phase 1: find the populator and its schedule

1. **Grep the repo.** Start with the cleanest signals:
   ```bash
   grep -rln "tick_cache/.*\.json\.gz" --include="*.sh" --include="*.py" .
   grep -rln "ibkr_tick_fetcher" --include="*.sh" --include="*.py" .
   grep -rln "cache_tick_data" --include="*.sh" --include="*.py" .
   ```
   Anything in `.claude/worktrees/` is noise — ignore it.

2. **Check cron and launchd on the Mac.**
   ```bash
   crontab -l
   ls ~/Library/LaunchAgents/ 2>/dev/null
   ls /Library/LaunchDaemons/ 2>/dev/null | grep -i warrior
   ```
   Look for anything referencing `warrior_bot_v2`, `tick`, `cache`, or `fetch`.

3. **Check `daily_run_v3.sh` and `check_bot.sh` end-to-end** for any trailing step or trap handler that invokes a tick fetch. The version of `daily_run_v3.sh` Cowork read only shows log push in the cleanup trap, but there may be more in `check_bot.sh` or a sibling script.

4. **Check `~/warrior_bot_v2/logs/` for a nightly batch log.** If there's a `cache_batch_*.log` or similar, it'll show you what ran at 18:00 on the days where the cache did populate, and (importantly) what didn't run or errored on 2026-04-10.

5. **Write what you find to `cowork_reports/2026-04-11_nightly_batch_investigation.md` before making any change.** Include:
   - Script name and path
   - Schedule mechanism (cron / launchd / daily_run_v3.sh step / manual)
   - Feed source (IBKR via `ibkr_tick_fetcher.py` or Alpaca via `cache_tick_data.py` — this matters given Manny's confirmation that the corpus is IBKR)
   - Why it didn't run on 2026-04-10 (dependency on bot state, or something else)
   - Whether `cache_tick_data.py` at repo root is live or dead code (see open question from the sibling directive)

Do not proceed to Phase 2 until Phase 1 is written up. Manny and Cowork need to see the answers before you start moving cron entries around.

## What to do — Phase 2: decouple

The target architecture is simple and should not require new infrastructure:

- The nightly tick batch runs on its own schedule (cron or launchd), independent of `daily_run_v3.sh` and of any running bot process.
- Its only dependency on the bot is that IBKR Gateway must be up. If Gateway is up, the batch runs. If Gateway is down, the batch fails loudly and logs an error — it does not silently skip.
- The batch's schedule is **18:00 local weekdays**, matching the existing mtime pattern so nothing downstream changes.
- The batch writes to `tick_cache/{YYYY-MM-DD}/` the same way it does today. Same directory layout, same filename format, same gzip JSON payload. No consumer should need to change.

Implementation options (choose the one that fits what Phase 1 uncovered — do not default to "the most elegant one"):

- **If the populator is currently a step in `daily_run_v3.sh`** (most likely): move the invocation out of `daily_run_v3.sh` into its own cron entry or launchd plist. Make sure the cron entry activates the venv and `cd`s into `~/warrior_bot_v2/` before running. Capture stdout/stderr to `logs/cache_batch_{YYYY-MM-DD}.log`.
- **If the populator is its own cron entry already** (less likely given today's failure): figure out why it failed on 2026-04-10 specifically. If the failure was "couldn't find the bot's PID file" or "bot process not alive, aborting", gut the dependency check. If the failure was "Gateway not reachable" because Gateway was killed during the bot freeze cleanup, add a pre-flight Gateway health check that starts Gateway if needed (reuse logic from `daily_run_v3.sh` step 5).
- **If the populator is running as a child of `bot_v3_hybrid.py`** (unlikely but possible): reparent it. `nohup` + `disown`, or launchd-managed, or cron — just not inside the bot process.

For all three options: the batch must not require `bot_v3_hybrid.py` to be running. `pkill bot_v3_hybrid.py; run nightly batch` should work.

## Testing

1. **Dry-run the decoupled schedule before committing.** If cron: add the entry, wait for it to fire once (or fake it with `at` / a manual run using the same env), and verify the cache directory appears with the right file count and mtime pattern.
2. **Explicit kill test.** With no bot running at all: manually trigger the nightly batch. Expected: it runs to completion, populates `tick_cache/{today}/` with the scanner's universe, writes a log to `logs/cache_batch_*.log`.
3. **Gateway-down test.** Stop Gateway cleanly (`pkill -9 -f "java.*ibgateway"` or equivalent), trigger the batch. Expected: loud error in the batch log, non-zero exit status, no partial writes to `tick_cache/`.
4. **Normal trading day test.** Let `daily_run_v3.sh` run as usual on the next trading day, verify the bot runs the normal session AND the nightly batch still populates the cache at 18:00 in a separate process tree.
5. **Do not run the regression suite (VERO/ROLR) to "validate" this change.** Same reason as the sibling directive — bot behavior is out of scope.

## Rollback

If anything in Phase 2 breaks the day-of trading flow (morning run, bot startup, Gateway auth, scanner boot), revert the scheduling change immediately and leave the bot on the old wiring. The nightly batch failing for one day is recoverable (the sibling `simulate.py` hard-fail fix will prevent bad data from silently entering the cache); the bot failing to start for one day is not.

Keep the `daily_run_v3.sh` change minimal so rollback is a clean `git revert`.

## Explicit non-goals

Don't touch:

- `bot_v3_hybrid.py`, `bot.py`, or any detector pipeline file
- `trade_manager.py`, `micro_pullback.py`, `squeeze_detector.py`
- `.env` — no config, no tuning knobs
- `simulate.py` — separate directive handles that
- Scanner thresholds, scanner scripts, scanner checkpoints
- Bot exit rules, entry rules, level map, exhaustion filter, classifier gate

The only files you should be editing are:

- The nightly batch script itself (only if Phase 1 shows it has a bot-process dependency to remove)
- `daily_run_v3.sh` (only to remove a tick-batch invocation if one exists there)
- A cron entry or launchd plist (new or modified, outside the repo or committed as a plist file if Manny wants that in version control — ask before committing plist files)

## Open question tied to the sibling directive

`cache_tick_data.py` still exists at the repo root with an Alpaca-based implementation. Commit `842752b` on 2026-04-07 said tick cache repopulation was done via `ibkr_tick_fetcher.py`, but didn't say `cache_tick_data.py` was removed or disabled. If Phase 1 uncovers that `cache_tick_data.py` IS the current nightly populator, then:

- Manny's confirmation that "the X01 tuning corpus is IBKR" is wrong, and we need to re-open the audit question (contra Cowork's revised action list this morning).
- The 2026-04-10 BENF incident may not be unique — every day's cache could have Alpaca contamination.

Flag this in your Phase 1 writeup as a **P0 escalation trigger**. If `cache_tick_data.py` is live, stop Phase 2 and tell Cowork/Manny before making any change. Do not proceed to decoupling until the feed source question is resolved.

If `cache_tick_data.py` is dead code (unused, superseded by something that actually calls `ibkr_tick_fetcher.py`), note that in the Phase 1 writeup and proceed to Phase 2 normally. We can clean up the dead file in a later housekeeping directive.

## Success criteria

1. Phase 1 writeup exists at `cowork_reports/2026-04-11_nightly_batch_investigation.md` and clearly identifies:
   - What populates the tick cache
   - How it's scheduled
   - Why it didn't run on 2026-04-10
   - Whether `cache_tick_data.py` is live or dead code
2. Phase 2 decoupling is implemented with the minimal change needed. No drive-by refactors.
3. The nightly batch can be started with `bot_v3_hybrid.py` stopped — verified by the explicit kill test.
4. Gateway-down case fails loudly instead of silently skipping — verified by the Gateway-down test.
5. Next trading day (2026-04-13, Monday) runs both the bot and the nightly batch correctly in independent process trees.
6. Results file at `cowork_reports/2026-04-11_nightly_batch_decoupled.md` with commits, test outputs, and the final process/schedule topology.

## Do NOT do

- Do not change `bot_v3_hybrid.py` or any bot-side file to "make it more robust to nightly-batch timing". The bot doesn't depend on the nightly batch at all — the dependency only runs the other direction, and that's what we're cutting.
- Do not treat this directive as permission to reorganize `daily_run_v3.sh`, move the venv, change the logging structure, or rework the launch sequence beyond what's minimally needed to pull the nightly batch out.
- Do not "while you're at it" add retry logic, alerting, or monitoring. Those are follow-ups, not this directive.
- Do not re-run the X01 tuning corpus based on Phase 1 findings **unless** Phase 1 uncovers that `cache_tick_data.py` is the live populator. In that case, stop and escalate — do not unilaterally kick off a rerun.
- Do not delete `tick_cache/2026-04-10.BROKEN_EVIDENCE_DO_NOT_DELETE/`.
