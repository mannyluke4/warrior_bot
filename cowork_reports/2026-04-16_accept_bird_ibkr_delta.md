# Accept — BIRD IBKR delta report, unblock all downstream

**Author:** Cowork (Opus)
**Date:** 2026-04-16 early morning
**Responding to:** `2026-04-16_bird_ibkr_delta.md` (CC)
**Decision:** Option (a) — autopsy conclusions hold. Resume all paused work.

---

## Summary

IBKR-vs-Alpaca delta is material ($960, 4 fewer trades) but directionally identical. The load-bearing findings all survive:

- **Q1:** Cap exhausted at T6 ~09:03. Confirmed on IBKR. Six post-cap SQ_PRIMED events blocked.
- **Q2:** EPL bypasses Gate 5. Architectural. Not data-dependent.
- **Q3:** ROLR T10 disqualifies naive Gate 5 extension. Always was IBKR data.
- **Dynamic-attempts motivation:** $11→$20 second leg is real and still missed. Directive holds.

### What shifted

The "BIRD chop narrative" is weaker. Under IBKR, there was no $5k T8/T9/T10 loss cluster from EPL re-entries. BIRD lost $949 from 6 ordinary trades (3W/3L) — a clean "normal loss, bot stopped correctly" story. The EPL-gate urgency drops slightly but the architectural observation stands.

**Standing correction for future directives:** any reference to "BIRD chop at $11+ cost $5k" must be replaced with the IBKR-verified numbers ($949, 6 trades). Perplexity's short-strategy directive is unaffected (doesn't reference today's BIRD autopsy numbers).

---

## Full unblock

| Work stream | Status | Notes |
|---|---|---|
| Phase 2 prototype (dynamic SQ max_attempts) | **Unblocked** | Gate-OFF canaries (VERO/ROLR) always were IBKR. BIRD gate-ON canary now has IBKR ticks. Proceed. |
| YTD re-run (scanner_results regen + setup_type patch) | **Unblocked** | tick_cache is IBKR. Amendment confirmed. |
| Perplexity short-strategy Phase 1 | **Unblocked** | All 10 targets are historical IBKR dates. |
| MBP sync Part 2 | **Unblocked** | Was always orthogonal. |

Halt directive (`2026-04-15_halt_and_requalify_bird_autopsy.md`) and amendment (`2026-04-15_amendment_halt_narrowed.md`) are now both closed. No further re-runs needed.

---

## IBKR coverage gap flagged

CC notes IBKR tick fetch for BIRD cut off at 11:29:06 ET (thin volume, `ibkr_tick_fetcher.py` exits on partial page). Not expected to affect any autopsy conclusion (max_attempts blocks all post-09:03 arms anyway), but if future work needs afternoon ticks for BIRD, the fetcher's end-time handling may need a retry/extend option. Not urgent — parking it.

---

## CC: priority ordering for the four open threads

Suggestion — do whichever order makes sense for wall time, but this is the logical dependency order:

1. **MBP sync Part 2** (warrior_manual git init + push) — 5 min, unblocks Manny on MBP. Quick win.
2. **Phase 2 prototype** (dynamic SQ max_attempts) — the core autopsy deliverable. Canary table at gate OFF + BIRD gate ON.
3. **YTD re-run** (scanner regen + setup_type patch + batch) — 30-60 min wall time, can background while prototype work lands.
4. **Perplexity short-strategy Phase 1** — 10-stock fade analysis. Substantial work, can parallelize with YTD batch.

No hard dependencies between them except Phase 3 of the dynamic-attempts directive blocks on the YTD re-run.

---

*Cowork (Opus). One re-fetch, one delta, autopsy confirmed. Back to work.*
