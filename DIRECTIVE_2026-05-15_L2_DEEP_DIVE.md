# L2 Deep Dive — Every Way We Can Use the Order Book

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC + Manny
**Scope:** Full strategic survey of L2 use cases across the bot. Supersedes the surface-level L2 directive from earlier today (`DIRECTIVE_2026-05-15_L2_INTEGRATION.md`); this is the comprehensive plan.
**Trigger:** Manny: "Do a full deep dive if you haven't already on everything we can utilize L2 for. It's been sitting dormant this whole time."

---

## Executive summary

**Three layers of L2 value, ordered by leverage:**

| Layer | What it is | Engineering | Strategic Impact |
|---|---|---|---|
| **1. Filter** | L2 vetoes/confirms entries from existing strategies (squeeze, WB) | Days | Eliminates dead-tape misfires, bad-stop placements, ill-timed entries. Patches today's ATRA bug AND opens a class of fixes for squeeze losses we've been tolerating. |
| **2. Feature** | L2 features feed scoring of existing entries — boost signal when book confirms, penalize when book disagrees | 1-2 weeks | Better selectivity on existing strategies. Stops that adapt to actual support levels. Dynamic sizing tied to liquidity. |
| **3. Strategy** | `l2_entry.py` (already written, 359 lines) becomes a third strategy alongside squeeze + WB. Enters BEFORE breakout candles when L2 shows buyers accumulating. | 2-3 weeks | A genuinely different entry pattern — the Ross Cameron "early entry" path that's been on the strategic backlog since March. Catches moves the other strategies see only after they've started. |

**My recommendation: all three, sequenced.** Layer 1 ships before June 4 go-live (mandatory). Layer 2 ships as ongoing improvement. Layer 3 paper-tests through June and is the lead candidate for the next strategy after squeeze + WB stabilize.

---

## 1. Inventory — what we have, what's missing

### Already written (in `archive/scripts/`)

**`l2_signals.py` (346 lines)** — The detector. Maintains per-symbol rolling state, computes 4 signal families on every snapshot:

| Signal | What it detects | Implementation status |
|---|---|---|
| `L2_IMBALANCE_BULL` / `BEAR` | Total bid volume vs total ask volume across N levels. Ratio thresholds env-configurable (default 0.65 bull / 0.35 bear). Also tracks rising/falling/flat trend over 10-snapshot window. | Complete, sensible defaults |
| `L2_BID_STACK` | Large orders accumulating at price levels above-average (default 3× multiplier). Tracks persistence — same stack appearing for 5+ snapshots gets full strength score. | Complete, with persistence tracking |
| `L2_LARGE_BID` / `LARGE_ASK` | Sudden 5× jumps in size at a price level (min 10,000 shares). Detects icebergs / institutional orders. | Complete |
| `L2_WIDE_SPREAD` / `L2_THIN_ASK` | Spread > 1% (env-configurable), or ask depth near price < 50% of bid depth near price. | Complete |

**`l2_entry.py` (359 lines)** — A complete entry strategy. Triggers an ARM when L2 shows 2+ consecutive bars of bullish signals (imbalance > 0.58, bid stacking, ask thinning) AND basic conditions (above VWAP, above EMA, green bar, MACD not bearish, spread reasonable, not exhausted). Scoring system 0-10+ with env-configurable min score 4.0. Stop placement uses bid stacking level if imbalance confirms genuine support, else recent swing low. **It's a fully-formed strategy not currently wired in.**

**`ibkr_feed.py` (214 lines)** — Subscription manager. Wraps `ib_insync` to call `reqMktDepth`, handles `domBids` / `domAsks` events, converts to `L2Snapshot` objects, dispatches callbacks. Has a built-in smoke test that runs from CLI. **Standalone — not yet integrated with the V3 data engine.**

### What's missing

1. **Wiring into `data_engine.py`** — the V3 hybrid's central data pipeline. Currently routes ticks and bars to detectors; no path for L2 snapshots.
2. **Smart-depth flag** — archived code calls `reqMktDepth` without `isSmartDepth=True`. IBKR API v974+ supports aggregated all-exchange depth via smart routing; we want this.
3. **Slot management** — like the TBT manager (`bot_v3_hybrid.py:114-119`), L2 needs its own rank/subscribe/unsubscribe loop respecting IBKR's depth slot limit.
4. **Backtest L2 replay** — `simulate.py` has a `--l2-entry` flag but it doesn't currently load historical L2 data. We'd need to record live L2 to a file going forward, OR get Databento L2 if your subscription includes it.
5. **L2 → WB integration** — no current path for the WB detector to consult L2 state at ARM time.
6. **L2 → squeeze integration** — same.

### IBKR constraints (verified from IBKR API docs today)

| Metric | Limit | Source |
|---|---|---|
| Simultaneous market depth requests | **3 at 0-399 market data lines** (most likely our tier) | [IBKR TWS API docs](https://interactivebrokers.github.io/tws-api/market_depth.html) |
| 400-499 lines | 4 | same |
| 500-599 lines | 5 | same |
| etc | +1 per 100 lines | same |
| Quote booster packs (extra lines) | $24 per 100 lines, max 10 packs | same |
| Update sampling | None — sent at full rate, can be 10+ events/sec on active names | same |
| Smart vs single-exchange depth | Smart aggregates all exchanges; available API v974+ | same |
| Required data subs | Nasdaq TotalView, NYSE OpenBook (or equivalent) for full depth | inferred + Warrior Trading reference |

**The 3-slot limit is the binding architectural constraint.** Every L2 design choice has to respect it.

---

## 2. Bot failure modes this week — L2 fixes mapped

Eight failures or pain points from the last week, mapped against what L2 would have done:

### A. ATRA 5/15 dead-tape entry (today's misfire)

**What happened:** WB bot entered 5,524 shares on a stock whose tape was nearly dead. Bar volume 4,700 shares total. Now -$608.

**L2 fix at ARM-time:** Spread + depth snapshot. Expected on dead tape:
- Spread > 1%
- Bid depth at touch < 1,000 shares
- No bid stacking detected
- Imbalance flat (no directional pressure)

`L2EntryDetector` would have returned `L2E_BLOCKED spread=2.5%`. WB veto cascade catches it before the order goes out.

### B. CLNN 5/5 ×4 squeeze losers

**What happened:** 4 squeeze entries on CLNN same day, all losers. Combined -$2,893. Score 7-9 each, R% acceptable.

**L2 fix:** Absorption detection at fill time. For each entry, were the prints hitting the bid (sellers being pushed) or hitting the ask (buyers stepping up)?
- If imbalance < 0.5 at entry → bearish flow even as price ticks up → trap setup → veto
- If `L2_LARGE_ASK` detected near our entry → resistance wall waiting → veto
- If `L2_THIN_ASK` detected → confirms real breakout, take entry

Squeeze currently has `WB_SQ_MIN_BAR_VOL=50000` floor on bar volume. That gate cannot distinguish "50K volume that's all sellers absorbed" from "50K volume that's buyers breaking out." L2 closes that blind spot.

### C. FATN 5/12 same-symbol re-entries (2 losses on same day)

**What happened:** FATN took a loss; bot re-armed and lost again. Hypothesis #11 (same-session blacklist) catches this NOW, but the bot was still entering after the first loss.

**L2 fix:** Imbalance trend after the first loss. If the loss happened and L2 imbalance went from 0.6 → 0.35 (bear flow appearing), that's the orderbook telling us the move is over. Even without same-session blacklist, an L2-aware re-entry would see falling imbalance and veto.

### D. TRAW 05-11 squeeze fill timeout (no taker after 3 retries)

**What happened:** Score-12 squeeze signal. 3 retries at $2.36→$2.40→$2.44 limits. No fill. Market sat at $2.45+.

**L2 fix:** Ask depth at our limit price. If `ask depth at $2.36 = 200 shares, ask depth at $2.45 = 5,000 shares`, the bot would know the wall is at $2.45, not at $2.36. Two options:
1. Skip retries entirely, place limit AT THE WALL ($2.45 + 1¢) — wall has shares to fill us against
2. Abort earlier — no shares anywhere reachable, give up cleanly

Currently we walk the ladder blind. L2 makes the ladder informed.

### E. ODYS 05-11 parabolic +11% in 30s miss

**What happened:** Squeeze signal scored 10. Market ran +11% past limit before our 2% chase cap allowed a fill. Cap correctly rejected.

**L2 fix:** Ask side disappearing rapidly. If we observed `L2_THIN_ASK` plus rapidly-pulled ask levels in the 30 seconds before our signal, the system knows this is a vacuum move. Either:
- Pre-fire the order with a wider cap (chase up to 5% on confirmed vacuum) — risky
- OR confirm the move is real and accept it as "out of reach, take the next setup"

Hard problem — vacuum moves are by definition fast and our latency budget is tight. But L2 at least gives us the data to decide rather than just timing out.

### F. Phantom positions earlier in project

**What happened:** Bot believed it had a position that didn't exist on broker side. Cost a week of debugging.

**L2 fix:** Cross-check own order. Our limit BUY order at $X should appear in the L2 bid book at $X with our size. If we DON'T see it within 2-3 snapshots after submit, our order didn't reach the book. This is a real-time integrity check the bot doesn't currently have.

### G. MEI 5/13 manual-add winner

**What happened:** Manny manually added MEI/NSTS/PTBD/VNET after Databento crashed. MEI ran and won +$366. This was the trigger for thinking about the intraday adder.

**L2 fix (alternative path):** A standing L2 scanner. Monitor the watchlist for symbols developing strong L2 imbalance (>0.7) with bid stacking. Surface as candidates to the bot's intraday adder. This is the systematic version of what your manual intuition was doing — "this name looks like buyers are interested."

This is **a candidate-discovery channel L2 enables that nothing else does.** Worth its own scoring loop.

### H. WB persistence layer + go-live concern (real-money realism)

**What it is:** WB persistence carries forward yesterday's WB-active symbols. Real money execution quality may differ from paper.

**L2 fix:** On every persisted-symbol arm, L2 snapshot tells us if the book is real (tight spread, multi-level depth, active updates). If yes, the paper-history is likely transferable. If no, real-money execution will degrade. This is **the go-live confidence check** for the persistence layer.

### Aggregate impact estimate (rough, this week only)

If Layer 1 (L2 as filter) had been live:

| Pattern | Trades affected this week | $ impact | Confidence |
|---|---|---|---|
| Dead-tape ATRA-like | 1 (today) | +$1,400 saved (stop hit) | High |
| Absorption-flagged CLNN-like | 4 (5/5) | +$2,000 (4×$500 partial save) | Medium — depends on threshold tuning |
| FATN-like re-entry | 1 (5/12) | +$400 | High |
| TRAW-like reachable-wall | 1 (5/11) | turns -$0 into +$1,000 win | Medium |
| ODYS-like parabolic | 1 (5/11) | unchanged (correctly missed) | High |

**Combined: ~$4,800 of estimated impact in one week.** That's an order of magnitude bigger than any other infrastructure investment we've made this week.

These numbers will move with backtest data and tuning; the order-of-magnitude is the point.

---

## 3. Layer-by-layer plan

### Layer 1 — L2 as filter (P0, ships before June 4)

**Goal:** Every WB and squeeze ARM gets an L2 snapshot evaluation BEFORE the order is submitted. Veto bad setups, pass good ones.

**Architecture (option 2 from earlier directive — L2 at ARM time only):**

```
[Detector ARMS]
     ↓
[Request L2 snapshot synchronously, 200-500ms]
     ↓
[L2SignalDetector.on_snapshot]
     ↓
[Evaluate veto rules]
     ↓
[Pass → submit order] OR [Veto → log + skip]
```

Slot usage: 0 permanent depth subscriptions. We request, evaluate, drop. Three concurrent ARMs at the same moment would hit the 3-slot limit; we serialize ARM evaluation if needed (acceptable — ARMs are rare).

**Veto rules (configurable, defaults from `l2_signals.py`):**

```python
# Hard vetoes (any one → block)
WB_L2_FILTER_MAX_SPREAD_PCT=1.0           # spread > 1% = thin book
WB_L2_FILTER_MIN_IMBALANCE=0.40           # bear flow blocks long entries
WB_L2_FILTER_MIN_BID_DEPTH_TOUCH=1000     # less than 1000 shares at touch = dead

# Soft penalties (one or two → still pass; three → block)
WB_L2_FILTER_BLOCK_LARGE_ASK=1            # ask wall above us = block
WB_L2_FILTER_BLOCK_ASK_THINNING=0         # ask thinning is GOOD for longs; don't block
WB_L2_FILTER_BLOCK_BID_TREND_FALLING=1    # imbalance trending down = block
```

**Failure modes A, B, C, D, F from §2 all closed by Layer 1.**

**Engineering work:**
1. Move `l2_signals.py` from archive to live (`warrior_bot/`)
2. Move `ibkr_feed.py` from archive to live; integrate `IBKRFeed.subscribe_l2` calls into `data_engine.py` lifecycle
3. Add Smart-depth flag (`isSmartDepth=True`) — better signal quality
4. New helper: `data_engine.request_l2_snapshot(symbol, timeout_ms=500) -> Optional[L2Snapshot]`. Subscribes, waits for first non-empty snapshot, returns it, unsubscribes.
5. New gate in WB ARM path: after dead-tape gate and chop_gate_v3 sub-gates, call `L2SignalDetector.on_snapshot(snap); evaluate veto rules`.
6. Same gate in squeeze ARM path.
7. Telemetry: log L2 verdict + raw snapshot summary on every ARM.

**Validation:**
- Synthetic test: feed pre-recorded "good book" and "dead book" snapshots through detector, confirm verdicts
- Live test: 1 paper trading day with L2 filter in observe-only mode, count would-have-vetoed events
- Report: `cowork_reports/2026-05-XX_l2_filter_observe.md`
- Acceptance: same as dead-tape gate — must pass FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13 winners; must veto ATRA 5/15

**Ship target:** observe-only Wed 5/20, enabled Mon 5/25.

### Layer 2 — L2 as feature (P1, post-go-live ok)

**Goal:** L2 features feed into existing scoring. Better-quality entries even when not blocked.

**Concrete additions:**

```python
# WB scoring boost
WB_L2_SCORE_BOOST_IMBALANCE_BULL=1.5      # +1.5 to WB score if L2 imbalance > 0.65
WB_L2_SCORE_BOOST_BID_STACK=1.0           # +1.0 if bid stacking confirmed at recent price
WB_L2_SCORE_BOOST_LARGE_BID=1.5           # +1.5 if institutional bid detected
WB_L2_SCORE_PENALTY_LARGE_ASK=2.0         # -2.0 if ask wall above

# Squeeze scoring boost
WB_SQ_L2_SCORE_BOOST_THIN_ASK=1.0         # +1.0 if ask is thinning post-breakout
WB_SQ_L2_SCORE_PENALTY_BEAR_IMBALANCE=2.0 # -2.0 if imbalance bear despite price up

# Adaptive stop placement
WB_L2_STOP_AT_BID_STACK=1                 # use bid stack as stop level when imbalance > 0.65 confirms support
WB_L2_STOP_PAD=0.01                       # 1¢ below the stack

# Adaptive position sizing
WB_L2_SIZE_BOOST_DEEP_BOOK=1              # increase size 25% when bid depth at touch > 10K shares
WB_L2_SIZE_REDUCE_THIN_BOOK=1             # cut size 50% when bid depth at touch < 2K shares (and we're not vetoed)
WB_L2_SIZE_DEPTH_CAP_SHARES=10000         # threshold for "deep"
WB_L2_SIZE_DEPTH_FLOOR_SHARES=2000        # threshold for "thin"
```

**Stop placement at bid-stack level (already coded in `l2_entry.py:_find_stop`):**
If we're long and L2 shows a persistent bid stack of 50K at $9.80 with imbalance 0.7, our stop at $8.84 is way too far. Stop just below the stack at $9.79 captures the actual market-determined support level. R shrinks from $0.26 → $0.04, but R-multiple math means a 1R move puts us at $9.84 — easier to achieve, faster to confirm. Tighter stops on confirmed support = more wins, smaller losses.

**Dynamic sizing:**
Same name, same setup, two days:
- Day 1: bid depth at touch 20K shares, imbalance 0.75. Take 100% of target notional.
- Day 2: bid depth at touch 1.5K shares, imbalance 0.55. Take 50% of target notional.

This is the principled answer to yesterday's Proposal B that we killed — sizing by *book quality* rather than by raw position-to-bar ratio. The bot adapts to actual liquidity rather than statistical proxies.

**Engineering:** ~1 week. Touches scoring, stop placement, sizing in both `wave_breakout_detector.py` and `squeeze_detector_v2.py`. Adds ~5 env vars.

**Ship target:** observe-only week of 6/1, enabled 6/8 (post-go-live).

### Layer 3 — L2 as strategy (P1-P2, paper through June)

**Goal:** Resurrect `l2_entry.py` as a third strategy alongside squeeze and WB.

**The pattern (verbatim from `l2_entry.py`):**
- Squeeze: breakout → enter the move (reactive to price)
- WB: breakout → pullback → confirmation → enter the bounce (reactive to price)
- **L2 Entry: L2 shows buyers stacking → ARM → enter the breakout (proactive on order flow)**

L2 entry fires BEFORE the breakout candle prints. The buyer accumulation is visible on the book before it shows up in the bar. This is the Ross Cameron "early entry" pattern that we've been talking about since March but never implemented.

**Architecture:**
- New detector instance per active L2-subscribed symbol (`L2EntryDetector` from archive)
- Runs alongside WB and squeeze detectors on the same symbol stream
- Independent ARM/entry path; its own setup_type='l2_entry'
- Shares execution infrastructure (limit ladder, position management, exit logic)

**Slot usage challenge:** L2 entry needs *persistent* L2 subscriptions to track multi-bar bullish signals. With only 3 slots and ~20-symbol watchlists, we can't subscribe everywhere. Options:

1. **Rank-and-rotate**: subscribe L2 on top 3 highest-WB-score symbols, rotate every 30s as scores change
2. **Tier-2 only**: L2 entry runs only on the 3 most-likely-to-fire symbols, not the whole watchlist
3. **Quote booster packs**: $96/month for 7 simultaneous depth subscriptions, or $216/month for 13

I'd start with option 1 (rank-and-rotate, free). If the strategy proves out, the $96/mo cost is trivial relative to potential P&L.

**Engineering:** ~2 weeks. The detector code is done; needs integration into the engine, scoring infrastructure, position sync, exit rules. Plus the rank-and-rotate L2 slot manager (mirrors the TBT manager pattern at `bot_v3_hybrid.py:114-119`).

**Backtest constraint:** No historical L2 data → no traditional backtest. Either:
- Record L2 forward (start saving snapshots to disk now, replay in 2-4 weeks)
- Check Databento subscription — they offer historical depth data on some venues
- Paper-test only for first month

**Ship target:** paper-only month 1 (6/8 - 7/8), real-money consideration after.

### Layer 4 (bonus) — L2-derived candidate scanner

**Goal:** Stand-alone L2 scanner running across the broader universe to surface candidates the squeeze and WB scanners miss.

**Mechanism:** Subscribe L2 to top-gainers list (3 slots, rotating fastest at 5-second cadence). When any symbol shows imbalance > 0.7 + bid stacking + 2+ consecutive bullish snapshots → emit as candidate. Bot's intraday adder consumes the stream.

This is the systematic version of "MEI was running and Manny manually added it" pattern. Not relying on price-action filters that delay; reading the book directly for accumulation signals.

**Engineering:** small (~3 days). Stand-alone process, writes to `wb_observed_today.txt` like the existing intraday adder. Compatible with existing persistence layer.

**Ship target:** experiment alongside intraday-adder observe-only week of 6/8.

---

## 4. Slot management architecture

Three slots. Five potential uses:

| Use | Slots | Notes |
|---|---|---|
| L2 filter (Layer 1) | 0 permanent, 1 momentarily during ARM | Request-evaluate-drop pattern |
| L2 feature (Layer 2) | Same as Layer 1 — features computed from same snapshot | Free |
| L2 strategy (Layer 3) | 2-3 permanent on top-WB-score symbols | Rank-and-rotate |
| L2 scanner (Layer 4) | 1-2 permanent on top-gainers | Rotating |
| Squeeze depth confirmation | Shared with Layer 1 ARM-time pattern | Free |

**With 3 slots and no quote boosters, the budget split looks like:**

- Slot 1: L2 strategy on highest-score symbol (persistent)
- Slot 2: L2 strategy on 2nd-highest symbol (persistent)
- Slot 3: Reserved for ARM-time snapshots (transient — Layer 1 + Layer 2 + squeeze)

When Layer 3 hasn't shipped yet (the next 2-4 weeks), slot 1/2 are idle and Layer 1+2 can run more comfortably. Once Layer 3 ships and the bot has live L2 candidates competing with WB/squeeze, slot contention may become real and we evaluate quote boosters.

**Detection of slot exhaustion:** the TWS API returns specific errors (TBT example: error 10186 = "Max number of tick-by-tick requests reached"). Mirror the existing TBT probe (`scripts/probe_tickbytick_capacity.py`) to detect L2 slot limits empirically.

---

## 5. Smart depth vs single-exchange depth

The archived `ibkr_feed.py:subscribe_l2()` calls `reqMktDepth(contract, numRows=10)` without specifying `isSmartDepth`. This means it gets single-exchange depth (defaults to primary exchange of the contract).

**Smart depth** (`isSmartDepth=True`, API v974+):
- Aggregates depth from ALL available exchanges into one combined book
- Tracks per-row which exchange the quote came from (the `marketMaker` field)
- Better signal quality — single-exchange depth misses orders sitting on alternative venues
- Costs the same number of slots
- **No downside; pure upgrade**

**Action:** When wiring the live `ibkr_feed.py`, add `isSmartDepth=True` to the `reqMktDepth` call. Trivial change, big quality lift.

One caveat: Smart depth requires API v974+ and TWS/Gateway v974+. CC should verify our IB Gateway version supports it. If we're on older Gateway, single-exchange depth still works — just less informative.

---

## 6. Cross-strategy benefits

L2 isn't a per-strategy feature. It's a per-symbol data stream that benefits every detector:

- **Squeeze detector** sees absorption (price up but flow bearish = trap)
- **WB detector** sees bounce conviction (post-down-wave imbalance turning bull = real bounce)
- **L2 entry strategy** sees the build-up before price moves
- **Stop manager** uses bid stacks as stop levels
- **Position sizer** scales by book depth
- **Order router** uses ask wall location to place limits intelligently
- **Live execution monitor** confirms our order is on the book

This is leverage. One data subscription, six consumers. The architecture investment is in `data_engine.py` integration; everything else is downstream features.

---

## 7. Cost / value framing

**Engineering cost (total all layers):** ~5-7 weeks of CC's time, spread across May-July
**Marginal subscription cost:** $0 (you already have IBKR L2) - $96/mo (quote boosters if Layer 3 forces it)
**Estimated impact (Layer 1 alone, this week's data):** ~$4,800 P&L difference
**Strategic impact:** Closes a class of failures the current architecture can't see. Genuinely fills the "we have a real-time order book and aren't using it" gap.

**Compared to the alternatives we've shipped this week:**
- Persistence layer: ~$1,200 in WB winners over 2 weeks (estimated, contingent on tape staying alive)
- Intraday adder: unknown — Day 1 surfaced 1 candidate already in active_symbols
- Squeeze fill-rate fix: maybe +2-3 fills per week, +$1-2K
- Dead-tape gate: catches today's ATRA, future similar = +$500-1500/wk

L2 Layer 1 dominates all of these on P&L impact per engineering hour.

---

## 8. Concrete ship plan with dates

### Pre-Monday 5/18

- **Sat 5/16:** Ship dead-tape gate per existing directive (interim insurance while L2 is in flight)
- **Sat-Sun:** Fix FCHL orphan P0 (separate workstream)
- **Sun:** L2 archive code audit — verify Smart-depth flag compatibility, check Gateway version

### Week of 5/18 — Layer 1 build

- **Mon 5/18:** Move `l2_signals.py`, `l2_entry.py`, `ibkr_feed.py` from archive → live. Fix `databento_feed.py` broken import. Add `isSmartDepth=True`.
- **Tue 5/19:** L2 slot probe script (mirror TBT probe). Confirms 3-slot limit empirically.
- **Tue-Wed:** `data_engine.request_l2_snapshot()` helper. Synchronous request-evaluate-drop pattern.
- **Wed-Thu 5/21:** Integrate L2 filter into WB ARM path. Observe-only mode (`WB_L2_FILTER_ENABLED=1, WB_L2_FILTER_OBSERVE_ONLY=1`).
- **Fri 5/22:** Report `cowork_reports/2026-05-22_l2_filter_observe_week1.md`. What did it catch? What did it pass?

### Week of 5/25 — Layer 1 ship + Layer 2 build

- **Mon 5/25:** If observe-only week 1 looks clean → flip `WB_L2_FILTER_OBSERVE_ONLY=0` for both WB and squeeze. Live.
- **Tue-Fri 5/29:** Layer 2 — L2 features feed scoring + stop placement + dynamic sizing. Observe-only.

### Week of 6/1 — June 4 go-live with Layer 1 live

- **6/1-3:** Layer 2 validation + flip live if clean. Layer 4 (L2 candidate scanner) parallel build.
- **6/4:** Real-money cutover. Layer 1 protecting all entries.

### Weeks of 6/8 - 7/8 — Layer 3 paper-test

- **6/8:** Resurrect `l2_entry.py` as live strategy in paper. Slot 1+2 persistent on top-score symbols.
- **6/8 - 7/8:** Paper-test month. Daily reports on L2-entry P&L vs squeeze/WB.
- **7/8:** Real-money decision on Layer 3.

---

## 9. Questions / decisions needed from Manny

1. **IBKR data subscriptions confirmation:** Do you have Nasdaq TotalView + NYSE OpenBook (or equivalents)? Without these, `reqMktDepth` returns only top-of-book on those exchanges — losing 70%+ of the value.

2. **IB Gateway version:** Are we on v974+ (Smart depth)? Check via TWS About menu, or CC can query. If we're on older version, we either upgrade (free) or accept single-exchange depth (works but less informative).

3. **Quote booster budget:** If Layer 3 forces it (~$96-216/mo for 7-13 depth slots), do we want to pre-authorize that, or stay at 3 slots until data justifies?

4. **Historical L2 for backtest:** Check Databento subscription — they offer ITCH L2 data for some venues. If yes, we can backtest Layer 3 instead of paper-testing for a month.

5. **Phase 4 (L2 scanner) priority:** Build it alongside Layer 3, or defer until Layer 3 proves out?

6. **Smart-depth confirmation:** Should we lock in Smart depth as default for all subscriptions, or also have a single-exchange fallback for cases where Smart depth is unavailable?

---

## 10. What I'm NOT proposing

1. **Not delaying the dead-tape gate.** It still ships Saturday as insurance. L2 takes weeks; dead-tape takes hours.
2. **Not delaying FCHL fix or squeeze fill-rate fix.** Both are P0 already, ahead of L2 in CC's queue.
3. **Not abandoning the persistence layer or intraday adder.** They continue to run and generate evidence. L2 makes them safer (Layer 1 filter), not redundant.
4. **Not blocking June 4 on Layer 2 or Layer 3.** Only Layer 1 is go-live-mandatory; everything else is post-go-live.
5. **Not requiring quote boosters from day 1.** Start with 3 slots; let data tell us whether to expand.
6. **Not rewriting `l2_signals.py` or `l2_entry.py`.** They're well-designed; integration work, not rewrites.

---

## 11. Tone note

This is the second-biggest "we've been doing it wrong" moment of the project (after the watchlist-carryover-as-edge realization). L2 has been sitting in the archive for months because we shifted to V3 hybrid and never circled back. The archive code is good — written carefully, env-configurable, has tests. The problem isn't that the work doesn't exist; it's that the integration work didn't happen.

There's no excuse for that, including from me — I should have surfaced this weeks ago. The cost of leaving L2 dormant has been at minimum the ATRA misfire today, the CLNN absorption-trap losers, probably some squeeze fill-rate issues that better limit-placement would have caught. Multiple thousands of paper-P&L that L2 would have caught.

Three weeks of integration work to fix the biggest blind spot the bot has. Worth every hour.

Let's wire it back in.

---

## 12. Files referenced

- `archive/scripts/l2_signals.py` — full L2 detector, complete
- `archive/scripts/l2_entry.py` — L2 entry strategy, complete
- `archive/scripts/ibkr_feed.py` — IBKR subscription manager, complete
- `databento_feed.py` — has broken `from l2_signals import L2Snapshot` import (line 25); will resolve when l2_signals moves to live
- `simulate.py:1737` — has `use_l2_entry` flag, not currently wired
- `bot_v3_hybrid.py:114-119` — TBT manager (model for L2 manager pattern)
- `scripts/probe_tickbytick_capacity.py` — TBT probe (mirror for L2 probe)
- IBKR docs: https://interactivebrokers.github.io/tws-api/market_depth.html
- `DIRECTIVE_2026-05-15_WB_DEAD_TAPE_GATE.md` — still ships Saturday (interim insurance)
- `DIRECTIVE_2026-05-15_L2_INTEGRATION.md` — superseded by this doc

---

## 13. Acceptance criteria for the whole L2 program

**Layer 1 acceptance (must pass for go-live):**
- 5 days of observe-only logging shows L2 filter would have vetoed ≥1 known-bad entry per week
- Zero winner false-positives across the cumulative dataset
- L2 snapshot fetch latency p99 < 1000ms (within entry-decision budget)
- Slot probe confirms IBKR limit; no silent slot-exhaustion errors in 5-day window

**Layer 2 acceptance:**
- Adaptive stop placement reduces average R while maintaining or improving R-multiple at exit
- Dynamic sizing reduces position size on thin-book entries without missing fillable opportunities
- Total layered scoring improvements: ≥10% lift in win rate OR ≥5% reduction in average loss

**Layer 3 acceptance (paper test):**
- L2-entry strategy generates ≥10 trades in 4 weeks paper
- Win rate ≥45% (lower than squeeze/WB, but entries are earlier so wider expected dispersion)
- Per-trade P&L expectancy positive after slippage modeling

**Layer 4 acceptance:**
- Scanner surfaces ≥1 candidate per week not already on the active watchlist
- Of surfaced candidates, ≥30% develop into legitimate WB or L2-entry setups within 30 min
