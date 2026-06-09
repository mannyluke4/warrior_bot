# Avoidable-Trades Audit — 2026-06-09 (Sub-bots A/B/C)

**Goal (per Manny):** today was a red day (sub-bots ≈ −$5k). One loss — the CCTG halt — is
unavoidable. This audit asks: of the *other* losers, which had **knowable-at-entry red flags**
that an "obvious avoid" filter would have caught? Each candidate filter is scored **net** (losers
avoided minus winners it would also forgo), so we don't cherry-pick. Source: today's per-variant
logs, 31 trades parsed (`/tmp/today_subbot_trades.json`).

> **Data caveat:** trade P&L is summed from log lines; bot `daily_pnl` is non-canonical
> (partial-fill undercount + bot-vs-broker divergence). Magnitudes are directional, not final —
> reconcile against broker equity before acting. This is one paper day; regime_shift wins on
> other days (e.g. 6/08 +$2,647). Treat as a hypothesis generator, not a verdict.

## Today at a glance
- **31 trades** across A/B/C, **net ≈ −$4,974**. 17 losers (−$8,353), 13 winners (+$3,379).
- A/B took 3 trades each (all losers, all halt-prone names); C churned 25.
- **Every symbol traded today halted at least once.** CCTG halted **34×**, RGNT 3×.

## The unavoidable (baseline)
**CCTG halt — A/B −$1,189 / −$1,172 (−$2,361 total).** 52-min volatility halt at 10:30
($4.22 → reopen $1.91), gapping through the $3.66 stop with zero trades. Bot detected the halt
and exited on the first post-reopen tick. Correct behavior; nothing to fix. (Full forensic in
session notes.)

## Avoidable buckets — net P&L if filtered (ranked by cleanliness)

| Filter (knowable at entry) | Skips | Losers avoided | Winners forgone | **NET** |
|---|---|---|---|---|
| **Oversize: notional > $15k** | 2 | +$2,051 | $0 | **+$2,051** |
| **Don't re-enter serially-halted name (CCTG, ≥5 halts)** | 4 | +$2,813 | $0 | **+$2,813** |
| **No deep-premarket entries (< 07:00 ET)** | 8 | +$2,036 | −$511 | **+$1,525** |
| Late/evening entries (≥ 15:30 ET) | 3 | +$547 | $0 | +$547 |
| regime_shift entries (today) | 9 | +$4,345 | −$102 | +$4,243 |
| Afternoon (≥ 11:00 ET) | 12 | +$2,990 | −$2,084 | +$906 |

**The three cleanest avoids (high net, ~zero winners forgone):**

1. **Oversized tight-R trades — +$2,051, no winners lost.** Two trades drove it:
   ZTG #16 (**10,000 sh / $33,900 notional**, −4% move → **−$1,400**) and ZTG #14 (5,005 sh /
   $16,717 → −$651). Both came from tight-R sizing (`risk_$/R` pins MAX_SHARES when R is tiny), so
   a small % move becomes a big dollar loss. **Fix already in the rebuild: Track A's R-floor
   (`max($0.10, 5% of entry)`) widens the stop → caps size → kills these.** Strongest single
   argument for R3.
2. **Serially-halted names — +$2,813, no winners lost.** *Every* CCTG trade lost (it halted 34×);
   re-entering it twice in the evening added −$143/−$309 on top of the halt loss. A **halt-count
   gate** (block new entries once a symbol has halted ≥N times today) is a clean, new, cheap guard
   — and halt count is knowable intraday.
3. **No deep-premarket (< 07:00 ET) — +$1,525 net.** The triple-flagged trade lives here:
   **RGNT 05:04 regime_shift** (A −$467 / B −$506) — a 5 AM regime_shift chase on a halt-prone name
   in thin premarket. Premarket was net-negative even counting its winners.

## Itemized avoidable losers (excl. the CCTG halt)
| V | Time | Sym | P&L | Size | Flags |
|---|---|---|---|---|---|
| C | 11:44 | ZTG | −$1,400 | 10,000sh / $33.9k | **OVERSIZE** |
| C | 06:16 | CHAI | −$686 | $11.6k | premkt<7, regime_chase |
| C | 11:25 | ZTG | −$651 | 5,005sh / $16.7k | **OVERSIZE** |
| B | 05:04 | RGNT | −$506 | $2.6k | premkt<7, halt-prone(3), regime_chase |
| A | 05:04 | RGNT | −$467 | $2.6k | premkt<7, halt-prone(3), regime_chase |
| C | 12:07 | RGNT | −$392 | $3.8k | halt-prone(3) |
| C | 05:30 | CHAI | −$377 | $7.2k | premkt<7 |
| A/B | 07:19 | CHAI | −$357/−$352 | $2.2k | *no obvious flag* (clean stop-out) |
| C | 16:40 | CCTG | −$309 | $4.5k | evening, halt-prone(34), regime |
| C | 10:56 | RGNT | −$219 | $1.3k | halt-prone(3) |
| C | 16:25 | CCTG | −$143 | $2.8k | evening, halt-prone(34) |

The two CHAI 07:19 stop-outs are the only sizeable losers with **no obvious pre-entry flag** —
normal trades that hit their stop. Everything else carried at least one knowable warning.

## Recommendations (fold into the rebuild)
1. **R3 / Track A R-floor** — already planned; this audit shows it's the single highest-value fix
   (−$2,051 of clean avoidable loss today was pure tight-R oversizing).
2. **New: halt-count entry gate** — block new entries on a symbol after it has halted ≥N times
   today (CCTG would've been skipped after halt #3-5). Cheap, knowable, zero winners lost today.
   Propose `WB_MOVE_HALT_COUNT_GATE` (off by default) for the rebuild + sub-bots observe-first.
3. **Entry-time discipline** — deep-premarket (< 07:00) and evening (≥ 15:30) were net-negative;
   the existing `WB_ENTRY_TIME_CUTOFF_ET` (and a premarket floor) can bracket the productive window.
   Note: a blunt ≥11:00 afternoon cut would forgo today's biggest winner (ZTG 15:25 +$1,166), so
   prefer the halt-gate + oversize-fix over a wide time cut.
4. **Watch regime_shift** — it was −$4,243 net today (8 of 9 trades lost), chasing parabolic
   anomaly bars into halts. Don't disable (it wins other days), but it's the entry most in need of
   the R-floor + halt-gate protection. Flag for the R5 paper-validation review.

## Caveats
One paper day; `daily_pnl` non-canonical (reconcile vs broker); regime_shift profitable other
days; "avoidable" filters are hindsight-fit to today and must be validated forward (observe-only)
before enforcement. The halt-count gate and R-floor are the most defensible because they have a
clear causal mechanism, not just a same-day correlation.
