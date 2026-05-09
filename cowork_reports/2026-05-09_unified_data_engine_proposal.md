# Unified Data Engine Proposal — One Pipe, Time-Sliced TBT Priority

**Date:** 2026-05-09 (Saturday, no-trading day)
**Author:** CC
**For:** Cowork (Perplexity) — request for third-perspective design review and build plan
**Branch target (when greenlit):** new `data-engine-unified` worktree off `v2-ibkr-migration`
**Context predecessors:**
- `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` (per-trade detail showing how today actually played out)
- `cowork_reports/2026-05-07_broker_execution_review.md` (the broker question Cowork is already on)
- `DIRECTIVE_CORRECTNESS_FIXES_MONDAY.md` (the two correctness fixes shipped to v2-ibkr-migration on 2026-05-08)

---

## TL;DR / Trigger

Manny's read after seeing 2026-05-08's session: we're leaving money on the table because the two-bot architecture is racing for a per-account resource (TBT subscription slots) without a coordination layer. He wants to consolidate to **one data collection engine** that owns the IBKR connection, with **time-sliced TBT priority** based on which strategy is actually working that part of the day:

- **04:00 → 10:00 ET**: Squeeze owns TBT priority. Squeeze decides which 5 symbols hold Tier 1 slots. WB still operates, but on Tier 2 (snapshot) data.
- **10:00 → 20:00 ET**: WB owns TBT priority. WB decides which 5 symbols hold Tier 1 slots. Squeeze winds down (it's never traded after 10:00 ET in our data anyway).

**Critical revision (Manny, 2026-05-09):** We are NOT replacing the current dual-bot setup. Manny is provisioning a **third Alpaca paper account** specifically to host the unified-engine-driven version. That setup will run in **parallel** with the current dual-bot setup so we can do a clean A/B over the same trading sessions, on the same watchlist, against the same scanner, with the same time windows. Decision to flip to live-money on June 4 will be informed by the comparison results, not by the calendar. **The current dual-bot architecture stays untouched and unmodified for the duration of the A/B period.**

We need Cowork's third perspective on:
1. **Is this the right architecture?** Or is there a cleaner pattern we're missing?
2. **How do we resolve the IBKR data-side contention?** (See "The IBKR Account Problem" section below — this is the most important open question.) Both setups want IBKR data; we have one IBKR paper account. The third Alpaca account fixes execution-side, not data-side.
3. **What's the cleanest A/B comparison protocol?** Same watchlist + same windows + same scanner output is the easy part. The hard part is making sure neither setup's IBKR-side activity contaminates the other.
4. **Edge cases we may not have thought of**, especially around the handoff protocol, crash recovery, and live-money behavior.

---

## What we have today (current architecture)

Two independent Python processes, both connecting to the same IB Gateway:

```
                                 ┌──────────────────────────┐
                                 │   IB Gateway (port 4002) │
                                 │   ONE account.            │
                                 │   reqTickByTickData cap   │
                                 │   = 5 simultaneous slots  │
                                 │   PER ACCOUNT             │
                                 └────────────┬──────────────┘
                                              │
                              ┌───────────────┴───────────────┐
                              │                               │
                  clientId=1  │                               │  clientId=2
                              ▼                               ▼
                ┌──────────────────────────┐    ┌──────────────────────────┐
                │  bot_v3_hybrid.py        │    │  bot_alpaca_subbot.py    │
                │  (main / squeeze)        │    │  (sub-bot / WB)          │
                │                           │    │                           │
                │  Owns its own:            │    │  Owns its own:            │
                │   - reqMktData subs       │    │   - reqMktData subs       │
                │   - tier1/tier2 state     │    │   - tier1/tier2 state     │
                │   - tick callbacks        │    │   - tick callbacks        │
                │   - tick_cache/ writer    │    │   - tick_cache_alpaca/    │
                │   - watchlist re-read     │    │   - watchlist re-read     │
                │   - reconnect logic       │    │   - reconnect logic       │
                │   - WATCHDOG              │    │   - WATCHDOG              │
                │                           │    │                           │
                │  Strategies:              │    │  Strategies:              │
                │   - Squeeze (primary)     │    │   - WaveBreakout (primary)│
                │   - WaveBreakout (parallel)│   │                           │
                │                           │    │  Execution:               │
                │  Execution:               │    │   - Alpaca PA3LXGIPGG8B   │
                │   - Alpaca PA3VP0LB4OID   │    │     (paper)               │
                │     (paper, switched      │    │                           │
                │     from IBKR exec        │    │                           │
                │     2026-05-07)           │    │                           │
                └──────────────────────────┘    └──────────────────────────┘
```

**Same watchlist.txt is read by both bots** (currently 6-7 symbols/day from the live scanner). Same prints arrive on both clientIds. But each bot independently decides:
- Which symbols to subscribe to (always all of them, today)
- Which symbols to promote to Tier 1 / TBT (5-slot cap)
- Which symbols to demote
- When to retry on data drought

### What we currently know about IBKR's behavior

Documented in `cowork_reports/2026-05-07_broker_execution_review.md` (read it for the full version), but the load-bearing facts for *this* report:

1. **TBT cap is per-account, not per-clientId.** Confirmed empirically by `scripts/probe_tickbytick_capacity.py` on 2026-05-05 and reinforced by the 2026-05-06 cross-bot 10190 collision (both bots subscribed past the shared cap → silent data-blindness).
2. **`reqMktData('233')` (snapshot, ~250ms aggregated) has no documented per-account cap** at our subscription levels. Sub-bot subscribes to all 7 symbols today without complaint.
3. **`reqTickByTickData('AllLast')` is the real per-print stream**, and that's the resource fight.
4. **Each clientId has its own subscription pool**, but at the data-farm/account level the entitlement counter is shared. So clientId 1 + clientId 2 both subscribing to TBT for ATRA = 2 of the 5 slots consumed, not 1.

Today's mitigation: **sub-bot has TBT disabled (`WB_TBT_ENABLED=0`)**, so all 5 TBT slots are free for the main bot. Sub-bot runs everything on Tier 2.

---

## The problem we're trying to solve

### Today's data (2026-05-08), the concrete instance

Sub-bot took 3 entries, 2 losses + 1 winner:
- FATN at 13:58 ET — main bot's Tier 1 at that moment was `['ATRA', 'TRAW']`
- SST at 15:01 ET — main bot's Tier 1 at that moment was `['FATN', 'TRAW']`
- ATRA at 17:09 ET — main bot's Tier 1 at that moment was `['CLNN', 'TRAW']`

The **+$2,499.59 ATRA winner** was a Tier 2 (snapshot) detection from the sub-bot's perspective. Main bot didn't have ATRA in Tier 1 at that arm. Meanwhile, main bot held **TRAW in Tier 1 for 8.8 hours and made $0** on it (TRAW got chop-rejected during the morning, then BP-rejected in the afternoon score-bypass attempt).

**Manny's read:** TRAW, the largest-volume symbol of the day, monopolized a high-fidelity slot the entire session and didn't translate to P&L. The actual money-maker (ATRA) ran on snapshot data. We can't *prove* ATRA would have done better with TBT, but we also can't prove it wouldn't have. And the architecture has no policy for "give the better-aimed strategy the priority"; it just lets the squeeze bot's promotion logic win whatever it wants because it's the one that has TBT enabled.

### The structural issues

1. **TBT slot allocation is implicit.** Today, "main bot has TBT, sub-bot doesn't" is a workaround for the 10190 cross-bot collision. It's not a strategy decision — it's a deconfliction patch.

2. **No time-of-day awareness.** Our own data (CLAUDE.md, `study_results/`) shows squeeze setups are profitable from 08:00-09:30 ET (71% WR, +$26,875) and *negative* after 09:30 (post-09:30 = -$2,430, 25% WR). The TBT slots stay tuned for squeeze even after 10:00 when squeeze is done for the day.

3. **Watchlist is consumed twice.** Each bot reads `watchlist.txt`, builds its own subscription list, and re-fetches the same prints. This was never what we wanted — it was just convenient. Tick-caches diverge (`tick_cache/` vs `tick_cache_alpaca/`), making backtest reproduction harder.

4. **Promotion logic is per-bot, not per-strategy.** Main bot promotes by "open position > armed > primed > wave_observing > volume_top". That logic was written for squeeze. WaveBreakout doesn't get a vote on what gets Tier 1 because its bot doesn't run TBT.

5. **Two reconnect / watchdog stacks.** Anything that can go wrong with the IBKR connection has to be handled twice, by both bots, and they can independently fail.

---

## Proposed architecture: one engine, time-sliced priority

### Conceptual diagram

```
                    ┌──────────────────────────────────────────┐
                    │   IB Gateway (port 4002) — ONE account  │
                    └──────────────────────┬───────────────────┘
                                           │
                                           │  clientId=1 (engine only)
                                           │
                  ┌────────────────────────▼────────────────────────┐
                  │      data_engine.py  (NEW PROCESS)              │
                  │                                                  │
                  │  Owns:                                           │
                  │   - The single IB connection                    │
                  │   - reqMktData('233') for every watchlist sym   │
                  │   - reqTickByTickData('AllLast') for ≤5 sym     │
                  │   - The TBT promotion/demotion policy           │
                  │   - tick_cache/ unified writer                  │
                  │   - reconnect / watchdog                         │
                  │                                                  │
                  │  Time-sliced TBT priority policy:                │
                  │   - 04:00-10:00 ET → Squeeze policy module      │
                  │   - 10:00-20:00 ET → WaveBreakout policy module │
                  │   - Boundary handoff (see below)                 │
                  │                                                  │
                  │  Publishes (IPC):                                │
                  │   - Tick stream (per-symbol, per-print)         │
                  │   - Subscription state (Tier 1 / Tier 2)        │
                  │   - Heartbeat                                   │
                  │   - Watchlist version                            │
                  └──────────────┬─────────────────┬─────────────────┘
                                 │                 │
                           Tick subscriber  │  Tick subscriber
                                 │                 │
                                 ▼                 ▼
              ┌───────────────────────┐    ┌──────────────────────┐
              │  squeeze_bot.py       │    │  wb_bot.py           │
              │  (logic only)         │    │  (logic only)        │
              │                       │    │                      │
              │  - Reads tick stream  │    │  - Reads tick stream │
              │  - Runs SQ detector   │    │  - Runs WB detector  │
              │  - Submits SQ orders  │    │  - Submits WB orders │
              │  - Owns its risk &    │    │  - Owns its risk &   │
              │    daily P&L state    │    │    daily P&L state   │
              │                       │    │                      │
              │  Account: PA3VP0LB4OID│    │ Account: PA3LXGIPGG8B│
              └───────────────────────┘    └──────────────────────┘
```

**Key separation:** the engine doesn't know about strategies' P&L, risk math, or order flow. The bots don't know about IBKR connections, subscriptions, or TBT slots. They only know "what's the current price for symbol X, what's the latest tick, what's the watchlist."

### Time-sliced TBT priority

The 5 TBT slots are owned by exactly one strategy at a time:

| Window | Owner | Why |
|---|---|---|
| 04:00-10:00 ET | Squeeze | Squeeze has data-confirmed edge during 08:00-09:30 ET (71% WR per analysis); pre-market 04-08 builds its priming. After 10:00 ET, squeeze setups go negative-EV (-$2,430, 25% WR per existing study). |
| 10:00-20:00 ET | WaveBreakout | WB pattern is most active during the regular-hours grind and into the evening session. Today's only winner (ATRA +$2.5K) fired at 17:09 ET. WB has been quiet pre-09:30 ET in our data. |

**What "owns priority" means in practice:**
- The owning strategy's promotion/demotion module is what the engine calls when deciding which symbols fill the 5 slots
- Squeeze's promotion logic ranks by squeeze-relevance (volume + body + level proximity)
- WB's promotion logic ranks by WB-relevance (open WB position > armed > observing > volume_top2)
- The non-owning strategy still runs and still gets Tier 2 (snapshot) data on every watchlist symbol — it just doesn't influence which symbols are in Tier 1

### The 10:00 ET handoff

This is the hardest part of the design. Open questions for Cowork:

1. **Hard handoff or soft handoff?**
   - Hard: at 10:00:00 ET, drop all current Tier 1 slots and let WB re-promote from scratch.
   - Soft: at 10:00 ET, switch the policy module but let TRAW (or whoever) coast in their slot for one full cooldown cycle so we don't lose data on a stock that's still moving.
   - Manny's instinct seems to favor a clean break, but soft has reconnect-cost benefits.

2. **Open positions across the boundary.** If squeeze has an open position in symbol X at 09:55 ET and the engine demotes X at 10:00, squeeze loses its tick-level exit precision. Probably fix: any open position from any strategy *automatically* holds a TBT slot until exited, regardless of which strategy "owns" priority. That uses 1 of 5 slots; the other 4 follow the time policy.

3. **Boundary tick rate.** When the engine simultaneously cancels 5 TBT subscriptions and starts 5 new ones, the IBKR connection sees a burst of subscribe/unsubscribe traffic. We've hit error 162/165 in those bursts before. Need rate-limiting or a stagger.

4. **Configurable boundary?** 10:00 ET feels right to Manny, but should we let Cowork's research suggest a different break-point? E.g., 09:30 ET (regular open) or 11:00 ET (after most squeeze runners have completed). Or make it data-driven: switch when squeeze has had no arm in N minutes.

### What the engine does NOT do

- Does **not** make trade decisions. Strategy bots own that.
- Does **not** know about Alpaca / brokers / orders. That's per-strategy.
- Does **not** own the WaveBreakout detector, Squeeze detector, scanner, or any classifier. Those live in the strategy bots and consume engine output.
- Does **not** persist trade state. Each bot still owns its own `session_state/`, `risk.json`, `open_trades.json`, etc.

### What the engine DOES do that we're not doing today

- One unified `tick_cache/` with both bots' tick history merged (right now we have two parallel caches that disagree on ~30-40% of prints because of timing differences in callbacks).
- One reconnect path. If the engine loses IBKR, both bots see a "stream paused" event simultaneously and both pause new entries until the engine flags itself healthy again.
- One watchdog. Bots become simpler — they're pure logic + execution, no infrastructure.
- Explicit policy for "who's the priority strategy right now." Today, that's hidden in env vars.

---

## A/B test plan — the third Alpaca paper account

This is the load-bearing change in the 2026-05-09 revision. Instead of replacing the current setup, we run both architectures **side-by-side** during weekday paper sessions and compare:

```
Setup A (CURRENT — unchanged for A/B duration)              Setup B (NEW — engine-driven)
┌────────────────────────────────────┐                      ┌────────────────────────────────────┐
│ IB Gateway (port 4002)             │                      │ IB Gateway — see "IBKR Problem"   │
│   clientId=1 → main bot (squeeze)  │                      │   clientId=3 → data_engine.py     │
│   clientId=2 → sub-bot (WB)        │                      │                                    │
│                                    │                      │ Strategy bots (logic only):        │
│ Alpaca:                            │                      │   squeeze_bot.py                  │
│   PA3VP0LB4OID ← main bot orders   │                      │   wb_bot.py                       │
│   PA3LXGIPGG8B ← sub-bot orders    │                      │                                    │
└────────────────────────────────────┘                      │ Alpaca:                            │
                                                            │   PA-NEW-3rd-ACCOUNT ← all orders  │
                                                            │   from both engine-driven          │
                                                            │   strategies                       │
                                                            └────────────────────────────────────┘

         Daily P&L = sum(PA3VP0LB4OID, PA3LXGIPGG8B)              Daily P&L = PA-NEW-3rd-ACCOUNT
                            │                                                  │
                            └─────────── A/B comparison ────────────────────────┘
                                          (same watchlist,
                                           same scanner,
                                           same windows)
```

### What we measure

| Metric | Setup A (sum of 2 accts) | Setup B (engine acct) |
|---|---|---|
| Daily P&L (realized) | from Alpaca order ledger | from Alpaca order ledger |
| Number of entries fired | from logs | from logs |
| Number of entries filled vs rejected | from logs + Alpaca | from logs + Alpaca |
| Avg slippage on entry/exit | from log + Alpaca fills | from log + Alpaca fills |
| Tick density seen per symbol | from tick cache | from engine tick stream |
| BP rejections | from Alpaca error codes | from Alpaca error codes |
| TBT slot utilization | from `[TIER]` log lines | from engine policy log |
| Time-to-fill (signal → fill) | from order timestamps | from order timestamps |

### What we control for

- **Same watchlist** — both setups read `watchlist.txt` (live scanner writes once, both consume).
- **Same trading windows** — both run 04:00-12:00 ET morning + 16:00-20:00 ET evening.
- **Same chop gate config** — both bots read same `.env`.
- **Same WaveBreakout detector code** — only the data plumbing differs.
- **Same Squeeze detector code** — only the data plumbing differs.
- **Same scanner output cadence** — `live_scanner.py` runs once per day, output consumed by both.

### What we CANNOT control for

- **TBT slot allocation will differ** by design. That's literally what we're testing.
- **Tick reception timing** may differ by milliseconds between the two stacks. For tick-level entry triggers (squeeze), this could swing fills.
- **Order placement timing** could differ if engine adds non-trivial IPC latency.

### What "winning" looks like

After ~5 sessions:
- Setup B P&L ≥ Setup A P&L *and* engine had no infrastructure incidents → **Engine wins, plan to flip live-money June 4 to engine architecture**.
- Setup B P&L < Setup A P&L by a margin (define how much) → **Stay on dual-bot for June 4 live**.
- Mixed / inconclusive → **Extend A/B for another 5 sessions, push live-money decision to follow-up review**.

This is the right framing because it removes "did we time the cutover correctly?" from the question. We never cut over until the data justifies it.

---

## The IBKR Account Problem (most important open question)

Manny gets a third Alpaca paper account easily — confirmed in his message. The issue is the **data side**. We have ONE IBKR paper account. With Setup A using clientIds 1+2 (main bot + sub-bot), Setup B's data engine would need clientId=3 against the same IBKR account → **all three would compete for the same 5-slot per-account TBT pool**. That's the cross-bot 10190 collision we already had on 2026-05-06.

### Options to resolve

| Option | Description | Pros | Cons |
|---|---|---|---|
| **A. Second IBKR paper account** | Manny provisions a separate IBKR paper account. Engine uses that. Setup A keeps the original. | Clean A/B with full TBT on both sides | Requires Manny to set up another IBKR account. Unknown if same broker permissions / data entitlements transfer. Two paper accounts to keep the demo seats current. |
| **B. Engine runs without TBT during A/B** | Engine subscribes only to `reqMktData('233')` snapshots; no TBT until the comparison concludes. | Zero IBKR contention with current setup. Validates engine architecture cleanly. | We can't actually validate the time-sliced TBT priority feature during A/B — we'd be testing "engine architecture without its main differentiator". |
| **C. Time-share the day** | Setup A runs Mon/Wed/Fri, Setup B runs Tue/Thu. They never overlap on IBKR. | Full TBT for whichever's running. | Halves the data per setup. A/B comparison is now Mon vs Tue, Wed vs Thu — not the same session. |
| **D. Engine runs on Alpaca data feed** | `data_engine.py` subscribes to Alpaca's `iex` SIP feed instead of IBKR. | Total decoupling — current setup gets full IBKR, engine gets Alpaca. | Alpaca SIP is ~10% the print density of IBKR TBT (we A/B'd it 2026-05-04). Tick-level entries fire on different prices. The comparison is contaminated by data-source quality, not architecture. |
| **E. Engine runs in tick-cache replay mode** | Engine validates correctness against historical tick caches at real-time speed. No live IBKR connection. | Zero contention. Lets us harden the engine code before live deployment. | Doesn't validate live behavior. Doesn't measure live P&L. Best as a *pre*-A/B step, not the A/B itself. |

### Cowork: this is the question we most need your perspective on

Recommendation we're leaning toward (subject to Cowork's input):
- **Phase 1 (May 11-15, weekdays):** Build the engine, validate via Option E (tick-cache replay). No live IBKR conflict. Engine architecture proved correct against today's session and prior days.
- **Phase 2 (May 18-22, weekdays):** Decide between Option A and Option B based on Manny's IBKR-account capacity:
  - If Manny can get a second IBKR paper account → **Option A** (full A/B with TBT on both sides).
  - If not → **Option B** (engine runs without TBT during A/B, we accept the limited test).
- **Phase 3 (May 26-30):** Whichever option held in Phase 2, gather 5 sessions of head-to-head data.
- **June 1-3:** Final review. Either flip to engine for June 4 live, or keep dual-bot.

**Cowork research questions:**
1. Can a single IBKR retail-paper user open multiple paper accounts? Or does the second require a separate user?
2. Is there a way to ask IBKR for an increased TBT-slot quota on a paper account (worth the conversation, even if unlikely)?
3. For multi-process trading systems running against a single IBKR account, what's the standard pattern for sharing the data subscription pool? Is there a published library or pattern?
4. Are there known ways to multiplex one IBKR connection across multiple consumer processes that don't trigger 10190 collisions? (We know clientId multiplexing doesn't work because the cap is per-account.)

---

## Why this weekend is the right time to plan

- **Markets closed** through Sunday night. We can think and design without missing a paper session.
- **The current setup keeps producing data.** Daily trade-breakdown reports continue Mon-Fri. We're not under pressure to finalize the engine architecture before any specific weekday.
- **Weekend lets Cowork research** in parallel with us drafting code.
- **The A/B framing means no urgency on a hard cutover date.** We can take the time to build the engine right and let the comparison data drive the live-money decision.
- **June 4 deadline** still applies, but it's now a "decide based on data" deadline, not a "ship the new architecture" deadline. If Setup B isn't beating Setup A by June 4, we go live with Setup A.

---

## Specific questions for Cowork's research

### A. Architecture pattern

1. **Single process or separate engine process?**
   - Single process: import both strategy bots into a master script that owns the engine. Simpler IPC (function calls / shared memory). Bigger blast radius if anything in the master script crashes.
   - Separate process: `data_engine.py` runs as a daemon, strategy bots connect via Unix socket / Redis pub-sub / shared memory. More isolation. More moving parts.
   - **Cowork: which pattern do similar trading systems use? Is there a "right answer" for our scale (≤7 symbols, ≤5 TBT slots, ≤2 strategies)?**

2. **Tick stream IPC mechanism.**
   - Unix socket with newline-delimited JSON: simple, well-understood.
   - Redis pub/sub: nice for multi-subscriber, adds a dependency.
   - Shared memory ring buffer: lowest latency, hardest to get right.
   - At our throughput (peak ~5K ticks/min across all symbols, today's busiest day), even Unix socket JSON is well within bandwidth. The question is: does latency matter? For Squeeze breakouts especially, a 50ms delay vs 5ms delay could change a fill price.
   - **Cowork: what's the typical pattern for tick distribution from a market-data daemon to N consumer strategies in a Python trading stack? Anything we should reach for vs build ourselves?**

3. **Subscription management API surface.**
   - Engine needs to know "watchlist of N symbols" — it gets this from the scanner output (already on disk).
   - Strategy bots need to declare "I want to know about symbol X" so the engine knows which Tier 2 subscriptions to keep alive even when the symbol is irrelevant to the priority owner.
   - Today: every symbol on the watchlist gets Tier 2 in both bots regardless of strategy interest. We probably keep that simple model.

### B. Time-handoff mechanics

4. **Handoff smoothness vs cleanliness.** Per the open question above. Cowork: research how other multi-strategy systems handle priority transitions for a shared subscription resource (the "5-slot cap" pattern is common in market-data feeds beyond IBKR — e.g., L2 book subscriptions, Polygon's multi-stream limits, etc.).

5. **Open-position protection.** Should an active position automatically pin a TBT slot regardless of priority owner? Tradeoff: 1 slot pinned = 4 slots for the priority strategy. If both bots are concurrently in trades, we're at 3 slots for active priority. Is that acceptable?

6. **What's "ownership" the right primitive?** Or should we go finer-grained, e.g.:
   - 3 slots for the priority strategy
   - 1 slot reserved for any open position
   - 1 slot for any arm event from either strategy (first-come-first-served)
   - **Cowork: any patterns from research on hybrid data-priority systems we should consider?**

### C. Reliability & failure modes

7. **Engine crash recovery.** If the engine dies, both bots are blind. What's the right resilience pattern?
   - Heartbeat with auto-restart via supervisor (systemd/pm2/manual cron watchdog)?
   - Hot standby engine that takes over on heartbeat loss?
   - Strategy bots fail-open (keep trading from cached state) for N seconds before flagging blind?
   - Strategy bots fail-closed (refuse new entries) if engine heartbeat gone for >X seconds?

8. **IBKR disconnect handling.** Today each bot has its own reconnect. With one engine, only the engine reconnects; how do bots know to pause/resume new entries during a reconnect window?

9. **Tick-cache contract.** Today both bots write to disk independently. With unified engine writing the cache, the strategy bots are now *consumers* of the cache for backtesting. Need to make sure the cache format is stable / versioned.

### D. Live-money implications

10. **Single point of failure.** Today, if main bot crashes, sub-bot keeps trading and vice versa. With one engine, an engine crash takes both bots offline. For paper that's fine; for real money on June 4, is this an acceptable risk? What are the standard mitigations?

11. **Per-bot Alpaca account separation stays.** The engine doesn't touch Alpaca. Each strategy bot still has its own paper account today (PA3LXGIPGG8B for WB, PA3VP0LB4OID for squeeze) and will have its own real account for live. That's deliberate — strategy-level P&L attribution. Cowork: is that the right model for live, or should we collapse to one account?

### E. Backtest implications

12. **Single tick cache simplifies backtests.** Today, simulate.py reads `tick_cache/`. The unified engine writes the same format. This actually fixes a long-standing divergence problem (`tick_cache/` vs `tick_cache_alpaca/`).

13. **The engine itself is a candidate for backtest replay.** A "replay engine" mode that streams ticks from a cache file at real-time speed (or accelerated) would let us paper-validate the engine and the bots together against historical sessions. Worth considering as part of the build.

---

## What we're NOT proposing in this directive

These are explicit non-goals so Cowork's plan stays scoped:

- ❌ Changing strategy logic (squeeze, WB) — they're black boxes to the engine
- ❌ Changing the Alpaca execution layer — bots own their orders
- ❌ Adding a new strategy — although the architecture should make adding one straightforward
- ❌ Replacing IBKR as the data source — Databento and Alpaca data are out of scope here
- ❌ Tuning chop gate, trailing stops, etc. — that's the May 15-16 review, not this directive
- ❌ Wiring pyramid leg2 — already deferred to a separate post-tuning directive
- ❌ Real-money rollout details — that's a follow-on directive after the engine is paper-validated

---

## Tentative timeline (revised for A/B framing)

| Date | Setup A (current dual-bot) | Setup B (new engine) | Notes |
|---|---|---|---|
| 2026-05-09 (today) | Off (Saturday) | Off — proposal to Cowork | This document |
| 2026-05-10 (Sun) | Off | Cowork research + design directive | |
| 2026-05-11 (Mon) | **Live paper as usual** | Dev: bootstrap `data_engine.py` + IPC scaffold | Current setup unchanged. Daily trade report generated. |
| 2026-05-12 (Tue) | **Live paper as usual** | Dev: tick distribution to consumer bots; replay-mode validation | Current setup unchanged. Daily trade report generated. |
| 2026-05-13 (Wed) | **Live paper as usual** | Dev: time-sliced priority module; promotion/demotion policy | Current setup unchanged. Daily trade report generated. |
| 2026-05-14 (Thu) | **Live paper as usual** | Dev: handoff protocol + open-position protection | Current setup unchanged. Daily trade report generated. |
| 2026-05-15 (Fri) | **Live paper as usual** | Dev: 3rd Alpaca account wiring + paper trading harness | Current setup unchanged. Daily trade report generated. |
| 2026-05-16 (Sat) | Off | Engine replay-validation against the 5 days of tick caches | + tuning review using 5 days of A-side trade-breakdown data |
| 2026-05-17 (Sun) | Off | Final pre-flight; bug fixes | |
| 2026-05-18 (Mon) | **Live paper as usual** | **First live paper session — engine + 3rd Alpaca account** | A/B begins. Both setups run same watchlist same windows. |
| 2026-05-19 (Tue) | Live paper | Live paper (engine) | Day 2 of A/B |
| 2026-05-20 (Wed) | Live paper | Live paper (engine) | Day 3 of A/B |
| 2026-05-21 (Thu) | Live paper | Live paper (engine) | Day 4 of A/B |
| 2026-05-22 (Fri) | Live paper | Live paper (engine) | Day 5 of A/B → **comparison report** |
| 2026-05-23 to 05-31 | Continue running A/B in parallel | Continue running A/B in parallel | Decision-readiness window. Tune both based on data. |
| 2026-06-01 to 06-03 | Final stabilization | Final stabilization | Pick winner based on accumulated A/B data. |
| 2026-06-04 | **Real-money go-live on the winning architecture** | | |

**Cowork: tear apart this timeline. If it's too aggressive, where? If we're missing a step, what?** Specifically: is May 11-15 enough to build the engine to live-paper-quality? If not, push everything back a week and accept the smaller A/B sample before June 4.

---

## Decision criteria — two distinct gates

### Gate 1: Greenlight the build (after Cowork's response)

We greenlight building the engine if Cowork's research surfaces:
1. **No fundamental design flaw** in the single-engine + time-sliced approach.
2. **A concrete IPC + process pattern** (ours or theirs) that handles our scale safely.
3. **A handoff protocol** that doesn't risk losing TBT data during the transition.
4. **A failure-mode plan** that's acceptable for live money.
5. **A workable answer to "The IBKR Account Problem"** (Section above) — even if it's "use Option B with limited scope," that's actionable.

If any of those come back as "no, this is wrong because ___", we step back and reconsider before writing any code.

### Gate 2: Flip to engine for June 4 live (after A/B data)

We flip live-money to Setup B (engine) on June 4 only if, by June 3:
1. **Setup B's accumulated paper P&L beats Setup A's** by a margin we agree on with Cowork (suggest: ≥10% better and statistically meaningful given sample size).
2. **Setup B has had no infrastructure incidents** that took both strategies offline simultaneously.
3. **Setup B's slippage is no worse than Setup A's** by more than ~5 bps on average.
4. **Setup B's BP rejection count is zero or matches Setup A's** (proves the equity-tied notional cap fix from 2026-05-08 was sufficient).
5. **The June 1-3 stabilization window has zero unresolved code defects.**

If any of these fail → **June 4 live-money goes on Setup A (current dual-bot)**, and Setup B continues paper validation through June.

The A/B framing means there is no scenario where we ship untested architecture into live money. That's the load-bearing improvement vs the original "flip live-paper" plan.

---

## What we're NOT doing while we wait for Cowork's response

- Setup A bots continue running on the current dual-architecture every weekday morning at 02:00 MT — **untouched, no modifications, no experimental knobs**. This is the baseline against which Setup B will be measured.
- The two correctness fixes shipped 2026-05-08 (pyramid silenced + equity-tied notional cap) take effect on Monday 2026-05-11 — that's our first session of clean paper data on the new caps. Both setups will eventually share these fixes, so they don't contaminate the A/B.
- Daily trade-breakdown reports continue (the format established by `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md`) — five sessions of data is the minimum sample size for the May 15-16 tuning review.
- **No experimental architecture changes during weekday Setup A sessions.** Whatever Cowork comes back with for the engine build happens in a separate worktree, on a separate Alpaca paper account, with its own scheduling. Setup A is sacred.

---

## Files referenced in this proposal

- `bot_v3_hybrid.py` — current main bot (squeeze + parallel WB)
- `bot_alpaca_subbot.py` — current sub-bot (WB only, TBT disabled)
- `wave_breakout_detector.py` — WB detection logic (engine-agnostic)
- `squeeze_detector.py` — Squeeze detection logic (engine-agnostic)
- `live_scanner.py` — Databento scanner that writes `watchlist.txt` (engine-agnostic)
- `daily_run_v3.sh` — cron launcher (will need to launch the engine + 2 bots, not 2 bots)
- `scripts/probe_tickbytick_capacity.py` — confirmed 5-slot per-account TBT cap (2026-05-05)
- `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` — yesterday's per-trade detail
- `cowork_reports/2026-05-07_broker_execution_review.md` — open broker question Cowork already has

---

*Manny's words on the original trigger: "we cant know that for sure. here is my proposal: we need to think about this differently. we need one data collection engine. this is what both bots read simultaniously. one profile. no conflicts."*

*Manny's revision (2026-05-09): "i can actually get a third alpaca paper account. so well use that to test this and leave current one as is and comoare results."*

*Net effect of the revision: the architecture proposal is unchanged, but the deployment path is now A/B head-to-head against the working setup, on a separate Alpaca paper account, with go-live decision driven by accumulated comparison data instead of a calendar cutover. The current dual-bot setup is untouched until Setup B has empirically earned the live-money slot.*

*Cowork: come back with what you'd change, what's missing, your answer on the IBKR Account Problem, and a build directive we can hand to CC on Monday.*
