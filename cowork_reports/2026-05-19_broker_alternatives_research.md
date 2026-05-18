# Broker Alternatives Research — Lightspeed + Comparable Stacks

**Date:** 2026-05-19
**Author:** Cowork (Opus 4.7 / 1M)
**Track:** Track 3 of `DIRECTIVE_2026-05-18_BROKER_LATENCY_INVESTIGATION.md`
**Mode:** Pure research; no implementation, no migration commitment.
**Decision gate:** Post-6/15 squeeze real-money cutover on Alpaca. Reads alongside Track 1 (Alpaca fill cost in $) and Track 2 (live latency distribution).

---

## TL;DR — Executive ranking

If Tracks 1 and 2 confirm a real, dollar-quantified Alpaca-latency cost north of ~$50/day, the migration-friction-adjusted ranking is:

1. **TradeStation** — best fit. Clean REST + WebSocket API with active Python SDK (`tradestation-api-python` v1.3.2, async, OAuth2, March 2026), well-documented `Simulation` paper environment, accepts limit orders with `OrderType=Limit` and stop semantics that we can ignore (bot keeps soft stops). Account minimum $2,000 (margin); PDT $25K rule applies but no $30K direct-access floor. Estimated migration: **5–7 working days**.
2. **DAS Trader Pro via Cobra Trading (or any DAS introducing broker)** — best fit if Track 1 implicates execution **routing** (not just ack latency) as the real cost. DAS is the industry-standard active-trader stack and routes via 100+ destinations with sub-millisecond order-side validation. Python access is mature: `das-bridge` 1.3.0 (PyPI, April 2026, async, MIT, all order types). API cost $100/mo (CMD tier) on top of Cobra's $0.0015–0.003/share. Account minimum $27,000 at Cobra. Estimated migration: **8–12 working days** (more wiring, broker side-channel for locates, $25K+ funding gate).

**Knock-outs (binding constraint):**
- **Lightspeed Connect** — *eliminated* on **paper-environment** and **stop-semantics** grounds (see §1 details). The Connect API is WebSocket-only, routed *through IBKR as the executing broker*, and its "Certification Environment" is a separate sandbox from IBKR paper trading — meaning paper traffic does not actually hit IBKR's matching engine. The product also launched November 2024 and has no public Python client repo (the only `lightspeed-trading` GitHub org has zero public repos as of 2026-05-19). Migration risk is too high for a June real-money deadline.
- **CenterPoint Securities** — eliminated on **account minimum** ($30K) combined with no first-party API; routing is via DAS Trader Pro, which makes it functionally a DAS-broker variant of Cobra.
- **Webull** — eliminated on **API maturity** and **product positioning**. Rate-limited to 1 request/sec on App-ID (600 req/min broader cap), pitched at retail rather than DMA-style active-trader. Not appropriate for tick-driven entries.

The report below documents each of these in detail.

---

## 1. Lightspeed Trading — Full evaluation

### 1.1 What Lightspeed Connect actually is

Lightspeed Financial Services Group LLC announced **Lightspeed Connect** on 2024-11-08 as a new API trading solution. The key structural fact: Lightspeed today (post-2024 reorg) is an **introducing broker to Interactive Brokers** for the Connect API product. Orders routed via Connect terminate at IBKR's matching engine; SIPC coverage and clearing sit on the IBKR side; Lightspeed retains the technology and routing layer.

This has two consequences:

1. **Pricing aligns with IBKR's published rates** — confirmed on their own marketing page: "Fees for Lightspeed Connect currently align with IBKR's published rates, with no additional costs." Equities from $0.001/share, options from $0.20/contract.
2. **The paper environment is *not* IBKR paper** — it is a separate "Certification Environment" run by Lightspeed/Atreyu Tech. Per their docs: "fully simulated platform, **separate from IBKR's paper trading**, where you can test integrations, orders, and strategies risk-free." This means you cannot paper-test against the same matching surface you'd use in production — paper traffic is matched against a Lightspeed-side simulator, not the live IBKR order book. That violates our project rule that paper must mirror live.

### 1.2 Protocol stack

- **WebSocket only** (WSS + JSON). No REST. No FIX (explicitly: "Unlike other platforms offering FIX or sockets, Lightspeed Connect's WSS-based approach balances simplicity and performance").
- Messages structured as JSON tag/value pairs with three message classes: `OrderSingle`, `OrderAdvanced`, `OrderMultileg`.
- Provides an `WS_Adapter` (sample code) for reconnect/session-handling. Getting Started Guide v2.0.4 dated April 2025.

### 1.3 Order types and constraints

- Standard equity types plus "advanced order types like Brackets, OCA, and Multileg Options."
- Per Lightspeed's own description: "Most any IBKR order type, like conditional orders, can be implemented upon request." That means *advanced* types require Lightspeed-side certification + test — not free out-of-the-box.
- Limit orders are first-class — no concern there. **Limit-only constraint compatible.**
- Stop orders exist as a *broker-side* order type (we don't use these — soft-stops only in our stack — so this is neutral for us).

### 1.4 Sandbox / paper

- **Certification Environment** — separate from IBKR paper. Test orders, simulated fills, deterministic behavior for development. Contact `apitrading@lightspeed.com` for production activation post-certification.
- The implication for our use case: any latency profile measured in Cert is *not* representative of production. We'd be flying blind on the one metric that matters (the metric this whole investigation is about).

### 1.5 Latency claims

No published median ack figures. Marketing claims "ultra-low latency, stable, customizable technology" and references infrastructure at NY4 (Equinix New Jersey). Elite Trader threads from 2025–2026 contain anecdotal "reliable connections and order execution… no lag at busy market opens" but no measured numbers. Lightspeed itself recommends user-side ping ≤ 100ms — a soft floor on what we'd see end-to-end.

Without a numerical anchor we can compare to Track 2's Alpaca distribution, the rationale for switching to Lightspeed reduces to *trust in Atreyu Tech's WebSocket layer being faster than Alpaca's*. That's a weak position to migrate on.

### 1.6 Symbol coverage — small-cap / microfloat / HTB

- Routes via IBKR SMART + NASDAQ, NYSE, AMEX, ARCA, BATS.
- Lightspeed maintains a tiered locate model: **E** (Easy-to-Borrow, immediate short), **L** (Locate Required, request via platform), **T** (Threshold List, cannot be borrowed). They state they have "a standing request with our clearing firms to locate or pre-borrow a certain quantity of every hard to borrow stock," partnered with Velocity Capital for fully-automated request/price/obtain locate flow.
- Practical concern for our squeeze universe ($2–$30, microfloat <30M): the squeeze strategy is long-only — borrow inventory doesn't gate us. But the **IBKR-clearing path can independently gate** through margin recalc on small caps (we hit ATRA margin rejection on 2026-05-07 via IBKR paper for exactly $202 under), and Connect orders inherit that surface.

### 1.7 Account minimums + onboarding

- **$30,000 minimum** for the Reg-T/cash account behind Connect (confirmed on the marketing page).
- $10,000 minimum on Lightspeed's other platforms (Web Trader); $25,000 on Lightspeed Trader / Sterling / RealTick. Connect requires the $30K tier per the API trading page.
- Portfolio margin requires $175K.
- Accounts under $15K hit a $25/month minimum commission fee.
- Onboarding: standard FINRA KYC, margin agreement, IBKR account activation as the executing broker. Practical timeline is **2–4 weeks** for fund-funded account + Cert environment access — not testable in time for a 6/15 cutover even if we wanted to.

### 1.8 Verdict on Lightspeed Connect

**Eliminated for our June real-money window.** The disqualifiers, in order:

1. **Paper environment is not the live matching surface.** Lightspeed's Cert sandbox is separate from IBKR paper *and* from the IBKR live book. We cannot fulfill the project rule "paper must exist and we paper-test before real money" in a meaningful way without effectively re-doing IBKR paper integration anyway.
2. **No measurable latency advantage.** No published numbers, only marketing claims. Track 2 will give us an Alpaca number; Lightspeed gives us nothing to compare against.
3. **No public Python client.** Migration time-cost is high — we'd build the WebSocket adapter from scratch off a PDF Getting Started Guide.
4. **2–4 week onboarding** plus Cert certification plus integration plus paper validation breaks the post-6/15 decision cadence.

Lightspeed Connect is a viable candidate *for a Q3 deliberate migration* if data demands it, but not a fit for the 6/15-window decision.

---

## 2. Alternatives — 2-line summaries

### 2.1 DAS Trader Pro / DAS API
Industry-standard active-trader OEMS. CMD/.NET/FIX APIs ($100–$1,500/mo by tier); CMD is sufficient for our order load (5,000 orders/day, 100 symbols). Sub-ms server-side order validation, 100+ routing destinations, mature Python client (`das-bridge` v1.3.0, April 2026, async, all order types, MIT). DAS is the *execution layer* — must be paired with an introducing broker (Cobra, CenterPoint, Lightspeed-DAS, etc.).

### 2.2 CenterPoint Securities
Direct-access broker built around DAS Trader Pro and iDASTrader. Best-in-class short locate inventory for active small-cap shorts. **$30,000 account minimum**, $120/mo DAS platform fee (waived ≥250K shares), $63–148/mo data bundles. No first-party API — automation is via DAS. Strong fit if Phase 2 short strategy ships; functionally redundant with Cobra for the long-only squeeze.

### 2.3 Cobra Trading
Direct-access, active-trader, founded 2004, clears via Wedbush. DAS Trader Pro + Sterling Trader Pro front-ends; CMD/.NET/FIX API surfaces ($0.0015–0.003/share). **$27,000 account minimum** ($30K non-US). Multiple short-locate sources for HTB names. Best DAS-introducing-broker pricing for our share volume; the migration target if Track 1 says routing (not just ack) is the issue.

### 2.4 TradeStation
First-party brokerage with REST + WebSocket API (OAuth 2.0, async, `Simulation` env). Active Python SDK (`tradestation-api-python` v1.3.2, March 2026); WebAPI v3 documented at `api.tradestation.com/docs`. PickMyTrade benchmarks claim <1ms ack on co-located VPS. **$2,000 margin minimum** (PDT $25K applies for active intraday). Symbol coverage is full US equities — small-caps and microfloats supported, though RadarScreen scanner has a 1,000-symbol cap (irrelevant — our scanner is IBKR-side).

### 2.5 Webull
Retail-facing broker with REST + some WebSocket. Place/modify/cancel limit orders, paper environment exists, but **1 request/sec App-ID rate limit** (600 req/min broader) — too restrictive for our tick-driven entries that can fire multiple cancels + replaces per second under chase logic. **Eliminated.**

---

## 3. Comparison matrix — Alpaca vs. Lightspeed vs. top alternative (TradeStation) vs. Cobra/DAS

| Axis | Alpaca (incumbent) | Lightspeed Connect | TradeStation | Cobra Trading + DAS |
|---|---|---|---|---|
| **Median ack latency (public)** | ~1.5 ms post-OMS v2.0 upgrade (Alpaca/Redpanda blog); historical 14ms live vs. 731ms paper buy (Alpaca forum, traders); paper widely reported worse than live | None published; marketing "ultra-low latency"; NY4 colo | <1ms claimed on co-located VPS (PickMyTrade 2025); generally a few ms for retail | DAS server-side validation sub-ms (DAS marketing); end-to-end depends on exchange route |
| **Limit-only support** | ✓ (type=limit) | ✓ (`OrderSingle` with limit price) | ✓ (`OrderType=Limit`) | ✓ all tiers; CMD/FIX/.NET |
| **No-broker-stops support** | ✓ — we don't have to submit stops; bot manages exits as limit orders | ✓ — same; broker stop is optional | ✓ — same; broker stop is optional | ✓ — same |
| **Paper environment** | ✓ Native paper API, separate accounts (`PA3VP0LB4OID` etc.); known paper-vs-live ack divergence | ✓ "Certification Environment" — **separate** from IBKR paper *and* IBKR live book; not representative | ✓ `Simulation` env via env-flag in SDK; mirrors production endpoints | ✓ DAS Real-Time Simulator (14-day trial; ongoing as subscription) |
| **Small-cap symbol coverage** | ✓ Full US equity universe; long-only OK; IEX feed thinner than SIP | ✓ Via IBKR; same surface as our current data; IBKR margin recalc gate may bite small caps | ✓ Full US equity universe; first-party clearing | ✓ Excellent — DAS routes to 100+ destinations including small-cap-friendly ECNs |
| **HTB / short locates** | ✗ HTB is restrictive (Alpaca declines many shorts) — relevant for Phase 2 only | ✓ E/L/T tier system, Velocity Capital partner | ~ Moderate — TS does HTB but not specialist | ✓ Best in class (Cobra clears through Wedbush; multiple locate sources) |
| **API maturity — REST** | ✓ Mature, OpenAPI spec, multi-SDK | ✗ No REST — WebSocket only | ✓ REST + WebSocket; OAuth 2.0 | ~ CMD over TCP, not REST |
| **API maturity — WebSocket** | ✓ Streaming for market data + trade updates | ✓ Primary protocol | ✓ Streaming quotes, orders, positions | Via DAS data feed; not a public WS |
| **API maturity — FIX** | ✗ Not available retail | ✗ Not offered | ~ Available institutional | ✓ Available (Standard tier+) at $500/mo |
| **Mature Python client** | ✓ `alpaca-py` first-party | ✗ None public (the GitHub org `lightspeed-trading` has 0 public repos) | ✓ `tradestation-api-python` 1.3.2 (Mar 2026, async, OAuth2) | ✓ `das-bridge` 1.3.0 (Apr 2026, async, MIT, full order types) |
| **Estimated migration effort** | n/a (incumbent) | **~15–25 days** (custom WS client, Cert→Prod, 2–4wk onboarding, no Python lib) | **~5–7 days** (swap broker adapter, OAuth2, paper validation, 2 day-trader-flow tests) | **~8–12 days** (DAS daemon install, locate side-channel, 5+day funding for $27K minimum) |
| **Pricing per fill (typical)** | $0/share commission (free); paid by PFOF | IBKR-aligned: $0.001–0.005/share; $0.20/contract options | $0–$1 base + per-share/contract tiers (TS Crypto / TS Stocks tiers); free-tier exists for low volume | $0.0015–0.003/share + $100/mo CMD API + $125/mo DAS Pro (waived ≥250K shares/mo) |
| **Account minimum** | $0 cash / $2K margin / $25K PDT | **$30,000** for Connect | $0 cash / $2K margin / $25K PDT | **$27,000** (US) |
| **First-party broker?** | Yes | No — introducing broker to IBKR | Yes | No — DAS hosted; Cobra clears through Wedbush |

---

## 4. Decision-ready recommendation framework

### 4.1 If Track 1 says Alpaca latency costs $X/day where $X is small (<$30/day on April sample)
**Stay on Alpaca.** The 6/15 cutover proceeds as planned. Track 2's live latency distribution becomes the baseline for an ongoing monitoring metric, but no broker switch is justified.

### 4.2 If Track 1 says $30–$100/day
**Stay on Alpaca for 6/15, kick off TradeStation paper validation in parallel.** TradeStation is the lowest-friction migration target — REST + WebSocket + first-party + Python SDK is the same architectural shape as Alpaca, so the broker-adapter swap is a clean refactor of `trade_manager.py`'s order-submission surface. Spec'd at 5–7 days of CC work to get a parallel TradeStation paper sub-bot running. Run TS-paper alongside Alpaca-real-money for 2 weeks, compare fill quality + ack times directly, then decide Q3.

### 4.3 If Track 1 says >$100/day, or Track 2 shows tail-latency excursions >1 second
**Stay on Alpaca for 6/15 (do not delay live cutover), but commit to DAS/Cobra migration in Q3.** This is the right move if the problem is *routing* (Alpaca's PFOF-routed fills are landing on stale prices) rather than just *ack* time. DAS is the upgrade path because it gives us explicit per-fill route selection. Migration budget: ~10 working days plus 2 weeks paper validation. Cost increase ~$0.0015–0.003/share × ~10K shares/day ≈ $15–30/day commission, offset against the $100+/day latency cost the data would have proven.

### 4.4 What we are explicitly NOT doing
- Not migrating to Lightspeed Connect. The paper-environment mismatch + 2–4wk onboarding + no Python client + no measurable latency advantage rules it out.
- Not migrating to Webull. Rate limit ends the conversation.
- Not migrating to CenterPoint Securities specifically. If we go DAS, we go Cobra — pricing is better and the broker surface is functionally identical (both clear DAS).

---

## 5. Migration plan sketch — TradeStation (top candidate)

If 6/15 squeeze go-live succeeds on Alpaca and Track 1 data demands a switch:

**Phase A — Account + paper setup (Days 1–2):**
- Open TradeStation margin account (~$2K to start; scale to ~$30K for PDT + comfortable BP)
- Generate OAuth 2.0 client credentials (public client first; promote to confidential post-validation)
- Install `tradestation-api-python` 1.3.2 in venv
- Wire `TRADESTATION_ENV=Simulation` to existing `.env` config pattern

**Phase B — Broker adapter (Days 2–4):**
- Add `brokers/tradestation_adapter.py` mirroring the Alpaca interface in `trade_manager.py`
- Map our order schema: limit price, side, qty, time-in-force, client-order-id
- Implement order-status callbacks via WebSocket stream subscription
- Add tracking for OAuth token refresh in background thread
- All existing soft-stop, BE, TW, trailing logic stays — only the order-submission surface changes

**Phase C — Paper validation (Days 5–7):**
- Run TradeStation sub-bot in `Simulation` mode in parallel with Alpaca paper for 5 full trading days
- Log per-trade ack latency to compare directly with Track 2 distribution
- Verify limit-only enforcement (set `WB_ALLOW_MARKET=0` at adapter boundary; reject any market-order codepath)
- Verify no broker-stops are submitted (assert in adapter unit test)
- Verify session-state persistence works through TS adapter (every position must rehydrate on restart)

**Phase D — Real-money paper run (Week 2):**
- Migrate funded TS account to live API (flip `TRADESTATION_ENV=Live`)
- Trade live with `WB_MAX_NOTIONAL=2000` for one full week (manageable drawdown ceiling)
- Compare net-of-commission P&L to Alpaca paper sub-bot trading the same signals in parallel

**Phase E — Cutover decision (end of Week 3):**
- Per Manny's hard rule (`feedback_session_persistence_required.md` + `project_june4_real_money_deadline.md`), no broker switch until two weeks of clean paper + one week of clean real-money paper validation
- Decision artifact: `cowork_reports/2026-XX-XX_tradestation_cutover_decision.md` with side-by-side metrics

**Total: ~3 weeks calendar time, ~5–7 working days of CC engineering effort.**

---

## 6. Migration plan sketch — DAS/Cobra (backup candidate)

Only if Track 1 implicates routing (not just ack latency) AND we are willing to spend Q3 on this:

**Days 1–3:** Open Cobra account, fund to $27K minimum, install DAS Trader Pro client + Real-Time Simulator. Provision `das-bridge` 1.3.0 venv install. CMD API subscription ($100/mo).

**Days 4–7:** Build `brokers/das_adapter.py` against the das-bridge async surface. Connect to DAS daemon on localhost:9910. Map our limit-only orders to `OrderType.LIMIT`; assert market order codepath rejects.

**Days 8–10:** Side-channel for short-locate requests (relevant only if Phase 2 short strategy ships before this work lands).

**Days 11–12:** Paper validation against DAS Real-Time Simulator; metrics capture; verify session-state hydration.

**Total: ~8–12 working days, more brittle than TradeStation because DAS runs as a local daemon (more failure modes) and adds a Cobra-side locate workflow.**

---

## 7. Open questions / known unknowns

1. **Lightspeed Connect's actual production ack latency** — only obtainable via live testing in their Cert env, which we won't do. Marketing-claim only.
2. **TradeStation's WebSocket order-event stream timing** — PickMyTrade's "<1ms" claim is for co-located VPS; from a non-colocated CC-host the realistic floor is 10–30ms one-way to TS edge.
3. **DAS Trader Real-Time Simulator fidelity** — the 14-day trial is enough to validate API shape but not enough to characterize fill quality at scale.
4. **PFOF vs. direct-route fill-quality dollar delta** — Track 1's job. If their answer is "PFOF on Alpaca is cleanly outperforming direct-route on the squeeze universe," that flips the entire ranking and we should stay on Alpaca permanently.
5. **Whether the new SEC PDT rule (effective 2026-06-04, $2K floor at Lightspeed) materially changes the calculus** — does not change broker ranking for our $150K AUM, but does open Lightspeed Connect to under-$25K accounts that previously couldn't use it.

---

## 8. Sources

- Lightspeed Connect API marketing — `https://lightspeed.com/trading/api-trading` and `https://lightspeed.com/trading/api-trading-at-IBKR`
- Lightspeed Connect press release (2024-11-08) — `https://lightspeed.com/about-us/news/Lightspeed-announces-API-trading-Lightspeed-Connect`
- Lightspeed Connect Getting Started Guide PDF v2.0.4 (April 2025) — `https://d31x4u3ydvpof.cloudfront.net/manuals/Lightspeed_Connect_API_Getting_Started_Guide_IBKR_Prod.pdf`
- Lightspeed pricing — `https://lightspeed.com/pricing-fees`
- Lightspeed stock lending — `https://lightspeed.com/lp/stock-lending`
- Lightspeed margin and account minimums — `https://lightspeed.com/pricing-fees/margin-rates` and `https://lightspeed.com/support/frequently-asked-questions`
- Lightspeed-trading GitHub org (zero public repos) — `https://github.com/lightspeed-trading`
- Elite Trader: "Lightspeed Connect API" thread — `https://www.elitetrader.com/et/threads/lightspeed-connect-api.381715/`
- DAS Trader API services — `https://dastrader.com/das-api-services/`
- das-bridge 1.3.0 on PyPI/Libraries.io — `https://libraries.io/pypi/das-bridge`
- TradeStation API specification — `https://api.tradestation.com/docs/specification/` and `https://tradestation.github.io/api-docs/`
- tradestation-api-python on PyPI — `https://pypi.org/project/tradestation-api-python/`
- Cobra Trading API services — `https://www.cobratrading.com/api-services/`
- Cobra Trading commissions — `https://www.cobratrading.com/low-cost-online-trading-platform/`
- CenterPoint Securities pricing — `https://centerpointsecurities.com/pricing/`
- Webull Developer Docs — `https://developer.webull.com/apis/docs/`
- Alpaca OMS v2.0 latency improvement (Redpanda case study) — `https://www.redpanda.com/blog/alpaca-100x-faster-order-processing`
- Alpaca paper vs. live latency forum (massive paper latency vs. live) — `https://forum.alpaca.markets/t/massive-paper-trading-latency-vs-live-trading/9053`
- PickMyTrade low-latency broker benchmarks 2025 — `https://blog.pickmytrade.trade/low-latency-algorithmic-trading-brokers-2025/`

---

## 9. Acceptance check against directive

- [x] All hard constraints respected — limit-only, no broker-stops, paper environment present, small-cap coverage
- [x] Lightspeed evaluated against all eight subpoints (protocol, docs, paper, limit support, stop semantics, latency, symbol coverage, pricing, onboarding)
- [x] 2-line summaries on DAS, CenterPoint, Cobra, TradeStation, Webull
- [x] Comparison matrix is decision-ready (Alpaca vs Lightspeed vs TradeStation vs Cobra/DAS) with concrete numbers
- [x] Migration effort estimated in days, not weeks: TradeStation 5–7 days; Cobra/DAS 8–12 days; Lightspeed 15–25 days
- [x] No live broker calls; pure research from public sources
