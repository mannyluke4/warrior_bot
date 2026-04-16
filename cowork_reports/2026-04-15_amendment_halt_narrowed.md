# Amendment — halt narrowed: tick_cache is IBKR, only today's BIRD was Alpaca

**Author:** Cowork (Opus)
**Date:** 2026-04-15 late evening
**Amends:** `2026-04-15_halt_and_requalify_bird_autopsy.md`
**Triggered by:** Manny's clarification — `tick_cache/` and `tick_cache_historical/` are IBKR-sourced. Today's contamination was a one-off: CC pulled fresh Alpaca ticks for this morning's stocks (BIRD and likely related) because they didn't know about the IBKR-only procedure.

---

## What actually happened

CC didn't pull from a tainted cache. CC made a *new* Alpaca fetch for 2026-04-15 ticks because the cache didn't have today's bars yet and CC didn't know `ibkr_tick_fetcher.py` is the only acceptable path.

**Contamination scope: today's backtest only.** Specifically whatever files CC wrote for 2026-04-15 via an Alpaca fetch. Historical dates in `tick_cache/` (January and February 2026) are IBKR-clean.

## What this changes

### Narrows the halt

Previous halt assumed broad cache contamination and blocked all downstream work. Revised scope:

- **Historical canary replays stand.** VERO 2026-01-16, ROLR 2026-01-14, BATL 2026-01-26, MOVE 2026-01-23, ARLO — all ran on historical IBKR ticks. Those numbers are valid.
- **Autopsy's ROLR T10 "disqualifying" finding stands.** Historical date, IBKR data. The "naive Gate 5 extension breaks ROLR T10" conclusion is real.
- **Only the BIRD 2026-04-15 number (-$1,909) is suspect.** Everything built specifically on that number (the "cap exhausted at T6 at 09:03" timing, the "missed $11→$20 afternoon leg" framing, cumR trajectory) needs re-verification on IBKR ticks.

### What remains paused

- **Phase 2 prototype of dynamic SQ max_attempts** — canary gate-OFF (VERO/ROLR) is unblocked (historical + IBKR). Canary gate-ON (BIRD 2026-04-15) is blocked until CC refetches BIRD via `ibkr_tick_fetcher.py`.
- **YTD re-run (scanner_results regen + setup_type patch)** — unblocked. `tick_cache/` is IBKR, the batch runner reads from it, no Alpaca in the path.

### What unblocks

- **Perplexity's `DIRECTIVE_SHORT_STRATEGY_RESEARCH.md`** — all 10 targets are historical dates (Jan/Feb 2026). IBKR ticks exist for them. Phase 1 fade analysis can proceed whenever CC has a slot. The directive itself is well-designed research work.
- **`simulate.py:1981` fix** — was never blocked. Already landed (`89e52c5`).
- **Session-resume work** — orthogonal, never blocked.
- **MBP sync Part 2** — orthogonal, never blocked.

---

## Revised ask for CC

Replaces steps 1-5 of the original halt directive:

### Step 1 — Requalify today's BIRD only

1. Identify and delete (or clearly quarantine) the Alpaca-sourced tick files CC wrote for 2026-04-15. Recommend moving them to a `tick_cache_quarantine_alpaca/2026-04-15/` path rather than `rm` — keeps an audit trail.
2. Refetch BIRD 2026-04-15 via `ibkr_tick_fetcher.py` into `tick_cache/2026-04-15/BIRD.json.gz` (the standard path).
3. If other symbols were also Alpaca-fetched today, list them and refetch each from IBKR. Flag if any symbol isn't available on IBKR for 2026-04-15 — that's its own blocker, different conversation.

### Step 2 — Re-run the BIRD autopsy backtest

Same command the autopsy used, now against IBKR ticks. Produce a trade-by-trade table. Compare to the Alpaca-derived version.

### Step 3 — Short delta report

At `cowork_reports/2026-04-16_bird_ibkr_delta.md`:
- Total P&L delta (Alpaca BIRD vs IBKR BIRD for 2026-04-15)
- Trade-by-trade side-by-side: which trades appear in one but not the other, which have different entries/exits due to tick differences
- **The load-bearing question:** does T6 still exhaust the cap at 09:03 on IBKR ticks? Does the $11→$20 leg still get missed? If the tick streams diverge meaningfully, the autopsy's mechanical framing shifts.
- Recommendation: (a) autopsy conclusions still hold → resume Phase 2 prototype work as planned; (b) conclusions shift → Cowork re-reads the autopsy against IBKR data and may rewrite the dynamic-attempts directive.

---

## Standing procedure — never forget again

**For CC, now and going forward:** any time the tick cache doesn't have a date/symbol you need, use `ibkr_tick_fetcher.py`. Never call Alpaca for historical ticks. If `ibkr_tick_fetcher.py` fails or doesn't have coverage, stop and report — don't silently substitute Alpaca.

**For Cowork directives going forward:** every backtest-producing directive will explicitly state "IBKR ticks only — if cache miss, use `ibkr_tick_fetcher.py`, never Alpaca" as a hard rule in the body. Will not be left as an assumed standing order again.

---

## Net impact on today's work

Minimal. One stock, one day, one re-fetch. The broader autopsy, canary findings, design memo reasoning, and Perplexity's short-strategy research all remain structurally valid. The BIRD-specific numbers may or may not shift materially — that's what the delta report will tell us.

---

*Cowork (Opus). Scope was one bad fetch, not a poisoned cache. Re-run BIRD, keep moving.*
