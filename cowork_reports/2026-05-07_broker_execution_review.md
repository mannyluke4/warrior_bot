# Broker Execution Review — IBKR Limitations & Alpaca Migration
## 2026-05-07

**Author:** CC
**For:** Cowork (Perplexity) review
**Status:** P1 — switching main bot's execution to Alpaca tonight, but need Cowork to evaluate whether this is the right long-term path before live-money go-live (June 4)
**Trigger:** Repeated IBKR paper-account execution failures across multiple incidents

---

## TL;DR

We've been running a hybrid stack — **IBKR for data, IBKR for execution on main bot, Alpaca for execution on sub-bot**. The IBKR execution path keeps hitting limits that block real trades:

- **2026-05-06 morning**: TBT subscription cap = 5/account (cross-bot collision, 10190 errors)
- **2026-05-07 morning**: Margin rejection on legitimate squeeze entry (ATRA: required Initial Margin $30,649 > Equity-with-Loan-Value $30,447, by **$202**). Stopped a +$36 sim trade live.
- **Pattern observed across testing**: IBKR paper enforces tighter margin than Reg-T 4× (likely 100% cash-account-style on small caps). Sizing logic that assumes 4× BP repeatedly mis-estimates available funds.

We're moving execution to **per-bot dedicated Alpaca paper accounts** tonight (main → `PA3VP0LB4OID`, sub already on `PA3LXGIPGG8B`). IBKR retains the data role only.

**The question for Cowork:** Will Alpaca **live** (real-money) have similar restrictions when we go live June 4? Are there brokers better-suited for active small-cap day trading? Is there a hybrid that beats this one?

---

## What we're currently running (effective tonight's commit)

```
                    ┌────────────────────┐    ┌──────────────────────────┐
                    │  IB Gateway (4002) │    │   Alpaca Paper API       │
                    │  market data only  │    │   execution only         │
                    └─────────┬──────────┘    └─────────────┬────────────┘
                              │                              │
                  reqMktData('233') / reqTickByTickData       │
                  for both bots (clientId 1 + 2)              │
                              │                              │
            ┌─────────────────┴───────┐    ┌────────────────┴──────────────┐
            │                         │    │                                │
            ▼                         ▼    ▼                                ▼
   ┌────────────────┐         ┌──────────────────┐              ┌──────────────────┐
   │  bot_v3_hybrid │         │ bot_alpaca_subbot│              │ Alpaca live data │
   │  Main / Squeeze│         │ Sub  / WaveBreak │              │  (NOT used)      │
   │  account       │         │  account         │              └──────────────────┘
   │  PA3VP0LB4OID  │         │  PA3LXGIPGG8B    │
   │  (NEW 5/7)     │         │  (existing)      │
   └────────────────┘         └──────────────────┘
```

**Per-bot config (post-tonight):**

| | Main (Squeeze) | Sub-bot (WaveBreakout) |
|---|---|---|
| Data feed | IBKR Gateway, clientId=1, reqMktData + reqTickByTickData | IBKR Gateway, clientId=2, reqMktData only |
| TBT (per-print stream) | ✓ enabled, 5 slots | ✗ disabled (per-account TBT cap) |
| Execution | **Alpaca paper, account PA3VP0LB4OID** (new, 0 daytrades) | Alpaca paper, account PA3LXGIPGG8B (existing) |
| Strategy | Squeeze + level-break + parabolic trail | Wave breakout + chop gate + auto-blacklist |

**Why split data and execution this way:**
- IBKR offers the deepest tick stream we've found via reqTickByTickData ('AllLast') — confirmed via the drain-fix probe (4–6 ticks/sec sustained on active small caps). Alpaca's `iex` SIP feed gives ~1/10 the print density (we A/B'd this on 2026-05-04).
- IBKR's *execution* path keeps producing surprises (margin, TBT cap, "competing live session" 10197 races, scanner subscription churn 162). We've spent multiple morning sessions debugging IBKR-side rejections that have nothing to do with strategy or risk math.
- Alpaca's execution surface, by contrast, has been consistently predictable. Order-place → fill or reject with clear reason, no silent margin recalculation, no per-account quotas (other than the well-known PDT 4-in-5 rule under $25K).

**Net theory:** IBKR is a data provider with a brokerage tacked on. Alpaca is a brokerage with a (weaker) data feed tacked on. Hybridize.

---

## Documented IBKR limitations (this paper account, last week)

### 1. Per-account TBT subscription cap = 5
- Confirmed via probe script `scripts/probe_tickbytick_capacity.py` 2026-05-05.
- When two bots both enable TBT, they fight for 5 slots → 10190 errors → silent data-blindness on whichever bot lost the race.
- Worked around by putting only main bot on TBT (sub-bot uses snapshot reqMktData).

### 2. Tighter margin than Reg-T 4× day-trading buying power
- ATRA squeeze 2026-05-07: bot computed BP=$122,125 (= 4× $30,540 equity), sized within that, IBKR rejected because "Equity-with-Loan-Value [$30,446.98] must exceed new total Initial Margin [$30,649.18]".
- This implies IBKR is enforcing margin closer to 100% (cash-account style) on this stock, not the standard 25% maintenance margin most retail brokers offer for marginable equities.
- Possibilities: stock-specific (small cap, hard-to-borrow flag, special margin requirement), account-type-specific (paper account in a more conservative mode), or feature-specific (something about the order type / TIF / outsideRth flag).

### 3. "Competing live session" error 10197
- Triggered when one client (e.g., a fresh login) takes data-feed authority from another in the same paper account. Both bots saw cascading 10197 errors on 2026-05-04 afternoon.
- Recovery is non-trivial — bot's data subscriptions can silently fail without re-establishment.

### 4. Historical Market Data Service errors 162/165 during scanner runs
- Routine background noise; scanner subscriptions get cancelled with these codes intermittently. Doesn't typically block trading but pollutes logs and obscures real signals.

### 5. Watchdog / connection cleanups around restarts
- IBKR server-side session takes ~30s to clear after a hard kill, blocking fresh logins. Required workaround in `daily_run_v3.sh` (sleep 30 + retry on fresh launch).

None of these are catastrophic individually. Collectively, they've cost us **3 morning sessions** in the past week (2026-05-04 sub-bot data-blind, 2026-05-05 ditto, 2026-05-06 TBT-drain-blind). Today is the first full clean session — and even today, IBKR rejected the only legitimate squeeze entry on margin grounds.

---

## Questions for Cowork

### 1. Does Alpaca **live** (real-money) have the same characteristics as Alpaca **paper**?
We've been testing on Alpaca paper. Alpaca paper:
- Granted 4× day-trading buying power on $30K equity (= $120K BP)
- No PDT restriction visible at $25K+ equity
- Order rejections are limited to: insufficient buying power (clear math), wash-trade detection (rare, opposite-side existing orders), code 40310000 patterns we've seen.

**Specifically need to know:**
- Does Alpaca's live execution use the same margin math as paper, or does it apply real Reg-T rules?
- Do they enforce stricter requirements on stocks with low float, hard-to-borrow status, or recent volatility (the way IBKR seems to)?
- Are there per-symbol concentration limits, max-shares-per-order limits, or pattern-day-trader override fees?
- What's their behavior around halt resumes, IPO-day stocks, or stocks under "T" suffix flagging?

If Alpaca live behaves the same as paper for our universe, the migration sticks. If not, we have a problem June 4.

### 2. Are there **better brokers** for this specific use case?
Our use case:
- Day-trading small-cap movers, mostly $1–$30 price range
- 5-50 trades per day target, mostly intraday round-trips
- Tick-level event-driven entries (sub-second order placement after detector triggers)
- Need ≥ 4× BP to size meaningfully on $30K starting equity
- No options, no shorts (yet), no after-hours specific dependence

**Candidates worth Cowork researching:**
- **Tradier** — claimed strong API, low latency, decent margin for active traders
- **TradeStation** — historic active-trader brand, has API
- **Lightspeed / Centerpoint / Cobra** — direct-access, claimed-best-for-shorts (relevant for the short-strategy planned later)
- **WeBull** — retail-friendly API
- **Kraken / Coinbase** — different asset class but fast execution surface

For each, the questions are:
- Programmable order placement (REST/WebSocket API quality)
- Margin requirements on small caps in $1–$30 range
- Day-trade rules / PDT exceptions
- Borrow availability (for the planned short side)
- Per-symbol or per-day quotas
- Market data quality (do we still need IBKR for ticks, or can we collapse to one broker?)

### 3. Is there a **hybrid** that beats our current data=IBKR/exec=Alpaca?
- Could we collapse to **one provider** without losing the per-print tick fidelity that the WB and squeeze detectors depend on?
- Is there a fast-data + cheap-execution combo we're missing? (Polygon + Alpaca? Databento + Alpaca? Databento gives us premium ticks; we already use it for the live scanner.)
- Should the live scanner's data feed (Databento) become the bot's data feed too, removing the IBKR Gateway entirely?

### 4. **Architecture for live-money rollout** (June 4)
Once on real money:
- One account or per-strategy accounts? (Tax / accounting / risk-isolation tradeoffs.)
- Margin vs. cash account?
- What's a recommended risk-per-trade and max daily-loss for a $30K starting bankroll given the win-rate / R-multiple stats from our backtest population?
- Does Cowork's research on similar bot setups suggest a different starting bankroll?

---

## What we're shipping tonight regardless

Without waiting for Cowork's input, we're shipping the dual-Alpaca-account setup tonight to unblock tomorrow's session:

1. New env vars in `.env`: `MAIN_APCA_API_KEY_ID`, `MAIN_APCA_API_SECRET_KEY`
2. `daily_run_v3.sh` extracts those and launches main bot with:
   ```bash
   APCA_API_KEY_ID="$MAIN_APCA_KEY" APCA_API_SECRET_KEY="$MAIN_APCA_SECRET" \
   WB_BROKER=alpaca \
     python3 bot_v3_hybrid.py
   ```
3. Sub-bot launch unchanged (continues using `APCA_API_KEY_ID` from .env).

**Reversal path:** if Cowork's research recommends a different broker, we just flip `WB_BROKER=alpaca` back to `WB_BROKER=ibkr` in the script and the main bot reverts to IBKR execution. The keys stay in `.env` either way.

---

## Files modified

- `.env` — added `MAIN_APCA_API_KEY_ID` / `MAIN_APCA_API_SECRET_KEY` block
- `daily_run_v3.sh` — main bot launch line modified to inject Alpaca credentials + `WB_BROKER=alpaca`
- This report: `cowork_reports/2026-05-07_broker_execution_review.md`

Daily report companion: `cowork_reports/2026-05-07_morning_choppy_stock_analysis.md` describes today's session in detail, including the chop-gate validation results and the ATRA margin-rejection event.

---

*IBKR has been a high-fidelity data feed and a frustrating execution venue. Cowork: please research whether the second half of that statement also applies to Alpaca for live trading, or whether we've got a different broker problem incoming on June 4.*
