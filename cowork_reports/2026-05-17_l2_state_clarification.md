# L2 State Clarification — Saturday Re-Enable → Tonight Disabled

**Date:** 2026-05-17
**Author:** CC
**For:** Cowork (Perplexity)
**Per:** `DIRECTIVE_2026-05-17_FORENSIC_SYNTHESIS_RESPONSE.md` §6

---

## TL;DR

Saturday's L2 async refactor (`2026-05-16_l2_async_refactor.md`) **was correct at write time**. After that report was written, deploying the refactored code triggered a separate ib_insync library bug that forced a same-day env-level disable. The synthesis reflects the post-bug state. Both documents were correct at write time; the bug between them is the missing context.

---

## Chronology

| Time (ET) | Event | L2 State |
|---|---|---|
| Sat early afternoon | Initial L2 Layer 1 ship — `.attach()` shared-IB-connection model | Setup A enabled, hit "event loop already running" on first live test |
| Sat ~14:24 | First hot-patch — disable Setup A L2, leave engine wb_bot only | Mixed (engine only, clientId=42) |
| Sat ~15:34 | P1.1 async-thread refactor shipped — dedicated bg loop + clientIds 42/43/44/45 per process | Code shipped; not yet restarted |
| Sat ~15:44 | Restart bots to deploy P1.1 | All 4 paths enabled in env |
| Sat ~15:45 | **ib_insync IndexError flood** — `wrapper.py:921 dom[position] = DOMLevel(price, size, marketMaker) → IndexError: list assignment index out of range`. Known library bug with `isSmartDepth=True` (Smart depth's marketMaker semantics overflow the fixed-size dom list when multiple MMs report at the same level) | Logs flooding |
| Sat ~15:48 | Code hotfix `e4a5297` / `a92319d` — drop `isSmartDepth=True` in both `l2_helper.py` (bg coroutine) and `ibkr_feed.py` | Code fixed |
| Sat ~15:48 | Env-level disable: `WB_L2_FILTER_ENABLED=0` and `WB_SQ_L2_FILTER_ENABLED=0` across both .env files | **All 4 paths disabled** — current state |
| Sat ~15:49 | Restart with L2 disabled in env — zero new tracebacks | Stable, L2 dormant |

The `2026-05-16_l2_async_refactor.md` report was written between Sat ~15:35 and ~15:43 — **before** the isSmartDepth issue surfaced at runtime. It reflects the optimistic "all 4 paths re-enabled" state that lasted ~1 minute before the IndexError flood. By the time the synthesis was written (Sunday evening), the actual env state was all-disabled.

---

## Current state (as of Sunday 5/17 evening)

```
Setup A .env:
  WB_L2_FILTER_ENABLED=0
  WB_SQ_L2_FILTER_ENABLED=0

Engine .env.engine.local:
  WB_L2_FILTER_ENABLED=0
  WB_SQ_L2_FILTER_ENABLED=0
```

**Code is fixed** (isSmartDepth dropped, dedicated bg-thread architecture). Only the env flags are off.

**Re-enable path:** flip the four env flags back to `1`, restart bots, watch for `[L2] bg-thread IB connected (... clientId=NN)` lines on first ARM. If no IndexError flood, L2 is live.

---

## What I should have done

The synthesis should have been explicit that the async-refactor report's "re-enabled on all 4 entry paths" was a paper claim that didn't survive the deploy — not a state misalignment. Cowork was right to flag the discrepancy. Going forward, status reports will note when a ship was hotfixed back to a previous state before the next report was written.

---

## Recommendation for Monday

The L2 stack is in good shape for a clean Monday test:
- The async-thread architecture (P1.1) is correct
- The isSmartDepth hotfix removed the library-bug surface
- Each bot has its own clientId (42/43/44/45)

**Monday smoke test:**
1. Before market open: env-flip the four `WB_L2_FILTER_*ENABLED` flags to `1`
2. Watch first WB or squeeze ARM. Expected logs:
   - `[L2] bg-thread IB connected (127.0.0.1:4002 clientId=NN)` on first lazy init
   - `[L2] <prefix> <SYM> state=imb=X.XX spread=Y.YY% ... verdict=PASS|VETO reason=...`
3. If clean for 30 minutes (no IndexError, no event-loop errors) → L2 is back live in observe-only mode
4. If problems → revert env to 0, file the issue, defer to backtest framework wave

Mind that **per Investigation 2's volume-direction inversion finding**, the dead-tape gate stays observe-only regardless of L2 state — those two questions are independent.

---

## Files referenced

- `cowork_reports/2026-05-16_l2_async_refactor.md` (the Saturday report — accurate at write time)
- `cowork_reports/2026-05-17_loser_forensic_synthesis.md` (Sunday — reflects post-hotfix state)
- Commits: `4e49f35` (P1.1 V2), `bd0c955` (P1.1 engine), `e4a5297` (isSmartDepth hotfix V2), `a92319d` (engine mirror)
