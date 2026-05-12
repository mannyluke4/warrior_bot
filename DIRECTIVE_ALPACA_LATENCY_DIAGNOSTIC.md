# DIRECTIVE: Alpaca Latency Diagnostic & Dual-Data Architecture Plan

**Date:** May 11, 2026  
**Author:** Cowork (Perplexity)  
**For:** CC (Claude Code)  
**Priority:** P0 — diagnostic this week, architecture decision by Friday  
**Branch:** `v2-ibkr-migration` for diagnostic; `data-engine-unified` if architecture change is greenlit  
**Predecessors:**  
- `cowork_reports/daily_trades/2026-05-11_trade_breakdown.md` (TRAW/ODYS retry-cap failures)  
- `cowork_reports/daily_trades/2026-05-08_trade_breakdown.md` (FATN entry timing issues)

---

## The Hypothesis

The squeeze bot reads IBKR's tick stream (full consolidated tape, sub-millisecond) and identifies entry signals. The bot then submits limit orders to Alpaca. By the time those orders arrive at Alpaca's matching engine, **Alpaca's view of the market has moved past the signal price** because:

1. Alpaca's SIP feed has different consolidation latency than IBKR's tick-by-tick
2. There's measurable round-trip time between IBKR-signal and Alpaca-order-acknowledgment
3. On fast-moving small-cap breakouts (squeeze's bread and butter), even 50-150ms of drift = $0.04-0.10 of price movement

This would explain:
- ODYS 5/11: signal $10.02, market $11.22 by retry-1 (12% gap in seconds)
- TRAW 5/11: 4 retry attempts spanning ~40s, all timed out
- TRAW 5/8: similar pattern
- Sub-bot WB doesn't suffer this as badly because WB entries fire at consolidation breakouts (slower price action) rather than squeeze breakouts (parabolic action)

**Squeeze: 0 fills across two paper sessions, multiple high-conviction signals lost.** This is structural, not stochastic.

## Why Diagnostic First (Not Architecture Change First)

We have two competing explanations:
1. **Latency theory:** IBKR sees the move first, Alpaca's view lags, our orders chase
2. **Order-routing theory:** Alpaca's routing partners (Citadel, Virtu) don't have access to the small-cap order books we'd need to fill, regardless of timing

If it's (1), Option C from the conversation (latency-calibrated limit pricing) fixes it. Lightweight code change.  
If it's (2), Option C fails because no limit price will fill if liquidity isn't there. Option A (route squeeze through IBKR execution) becomes the only fix.

Measuring the gap tells us which problem we're solving. Building the architecture before measuring is shooting in the dark.

---

## Diagnostic Plan

### Step 1: Data Collection (Tuesday May 12, during live session)

Modify the **main bot only** (squeeze path) to log additional fields on every entry attempt:

For every `ENTRY SIGNAL` event, capture:
```python
{
  "symbol": "TRAW",
  "signal_time_ibkr_et": "2026-05-12T09:31:00.123",
  "signal_price_ibkr": 2.305,
  "alpaca_bid_at_signal": 2.31,           # NEW: query Alpaca's snapshot quote API at signal moment
  "alpaca_ask_at_signal": 2.33,           # NEW
  "alpaca_last_at_signal": 2.32,          # NEW: most recent Alpaca trade print
  "limit_price_submitted": 2.36,
  "order_submit_time": "2026-05-12T09:31:00.245",
  "order_ack_time": "2026-05-12T09:31:00.298",  # NEW: when Alpaca confirmed receipt
  "first_alpaca_print_above_signal": {     # NEW: walk Alpaca's tape AFTER signal
    "time": "2026-05-12T09:31:00.180",
    "price": 2.34
  },
  "fill_or_timeout": "timeout",
  "fill_time": null,
  "fill_price": null,
  "ibkr_price_at_order_submit": 2.31,     # NEW: where IBKR thought price was when we sent the order
  "ibkr_price_at_order_ack": 2.34,        # NEW: where IBKR thought price was when Alpaca ack'd
  "ibkr_price_at_timeout": 2.45           # NEW: where IBKR thought price was when we gave up
}
```

The key new measurements:
- **`alpaca_*_at_signal`**: Alpaca's view of the market AT the moment IBKR signaled
- **`first_alpaca_print_above_signal`**: When did Alpaca's tape actually print AT OR ABOVE our signal price?
- **`ibkr_price_at_*`**: IBKR's view at each critical moment (signal, submit, ack, timeout)

These let us compute four things per signal:
1. **Inter-feed price gap at signal time:** Alpaca-bid vs IBKR-price → "Did Alpaca already know about the move?"
2. **Inter-feed latency:** time delta from IBKR-signal to first matching Alpaca-tick → "How far behind is Alpaca's tape?"
3. **Round-trip latency:** time from signal-detected to order-acknowledged → "How long does our pipeline take?"
4. **Total price drift:** IBKR-price-at-signal vs IBKR-price-at-timeout → "How fast did the stock move while we were trying to enter?"

### Step 2: Implementation Specifics

**Alpaca quote snapshot API** (this is the load-bearing new code):
```python
# In bot_v3_hybrid.py, just before submitting the order:
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest, StockLatestTradeRequest

quote_req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
quote = state.alpaca_data_client.get_stock_latest_quote(quote_req)[symbol]
trade_req = StockLatestTradeRequest(symbol_or_symbols=symbol)
trade = state.alpaca_data_client.get_stock_latest_trade(trade_req)[symbol]

# These four values become the diagnostic capture:
alpaca_bid_at_signal = quote.bid_price
alpaca_ask_at_signal = quote.ask_price
alpaca_last_at_signal = trade.price
alpaca_data_timestamp = quote.timestamp  # for measuring stale-quote risk
```

**IBKR price-at-moment lookup:**
```python
# We already have ticker.last in state — capture it at each of:
# 1. signal moment (just before logging the signal)
# 2. order submit moment (just before placeOrder call)
# 3. order ack moment (in the order ack callback, if available; else best-effort timestamp)
# 4. timeout moment (in the cancel-on-timeout path)
```

**Logging:** new line type `[LATENCY]` written to a dedicated file:
```
logs/2026-05-12_latency_diagnostic.jsonl
```
One JSON object per signal attempt, newline-delimited. Easy to parse with `jq` or pandas afterward.

### Step 3: Analysis Run (Wednesday May 13, off-market)

Build a single notebook or script: `scripts/analyze_latency_diagnostic.py`

For all entries in `latency_diagnostic.jsonl`, produce:

**A. The latency distribution table:**
| Metric | p50 | p75 | p90 | p99 | Max |
|---|---:|---:|---:|---:|---:|
| Inter-feed price gap at signal (% of signal price) | | | | | |
| Inter-feed timestamp gap (ms) | | | | | |
| Signal → order submit (ms) | | | | | |
| Order submit → ack (ms) | | | | | |
| Signal → ack (total ms) | | | | | |
| IBKR price drift during entry attempt (%) | | | | | |

**B. The per-signal outcome table:**
| Symbol | Signal price | Alpaca ask at signal | Limit submitted | Fill / timeout | Price at timeout | "Would have filled at $X" |
|---|---|---|---|---|---|---|

Where "$X" = the minimum limit price that WOULD have matched the first Alpaca-tape print above signal.

**C. The "lag-adjusted limit" simulation:**
For each timed-out signal, recompute what limit would have been needed:
- `signal_price + (alpaca_ask_at_signal - signal_price) + safety_buffer`

If that limit is < the actual market price during the order window, the trade would have filled. Count how many timeouts would have been wins.

### Step 4: Decision Criteria

By Wednesday EOD we'll have one of three outcomes:

**Outcome A: Latency is consistent and small (p90 < 200ms, p90 price gap < 0.5%).**  
→ Light fix: lengthen the chase-cap or pre-compute the lag-adjusted limit. No architectural change needed.

**Outcome B: Latency is consistent but meaningful (p90 < 500ms, p90 price gap 0.5-2%).**  
→ Build the dual-data-source architecture. IBKR identifies signal, Alpaca's quote API prices the limit. Order limit = `max(signal_price, alpaca_ask + small_buffer)` so we're never trying to fill below where Alpaca already is.

**Outcome C: Latency is large or wildly variable (p90 > 500ms or 5x variance), OR Alpaca routing simply can't fill these names.**  
→ Squeeze execution moves to IBKR. Accept some rejections on weird names. Keep Alpaca for WB which doesn't suffer this. Hybrid architecture (Option A from the conversation).

---

## If Outcome B: Dual-Data-Source Build

This is the most likely outcome based on the qualitative pattern. Build spec below so we're ready to ship Wednesday night if data supports it.

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│   IB Gateway (port 4002)        Alpaca Data API             │
│   - Squeeze detector input      - Quote snapshot before     │
│   - Tick-by-tick / Tier 1         every squeeze order       │
│   - Determines WHEN to enter    - Determines AT WHAT PRICE  │
└───────────────┬─────────────────────────┬───────────────────┘
                │                         │
                └────────┬────────────────┘
                         ▼
              ┌─────────────────────┐
              │   bot_v3_hybrid.py  │
              │                     │
              │   Signal: IBKR      │
              │   Pricing: Alpaca   │
              │   Execution: Alpaca │
              └─────────────────────┘
```

### Code changes (`bot_v3_hybrid.py`, surgical)

1. **Add Alpaca data client at startup** alongside the existing trading client:
```python
from alpaca.data.historical import StockHistoricalDataClient
state.alpaca_data_client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
```

2. **New helper:** `compute_alpaca_aware_limit(symbol, signal_price, side)`:
```python
def compute_alpaca_aware_limit(symbol, signal_price, side, slip_buffer_pct=0.005):
    """Returns a limit price calibrated to Alpaca's current view of the market.
    
    For BUY: max(signal_price * (1 + buffer), alpaca_ask * (1 + buffer))
    The bot will never try to fill below where Alpaca's order book already is.
    """
    quote_req = StockLatestQuoteRequest(symbol_or_symbols=symbol)
    try:
        quote = state.alpaca_data_client.get_stock_latest_quote(quote_req)[symbol]
        alpaca_ask = float(quote.ask_price) if quote.ask_price else None
    except Exception as e:
        log.warning(f"[ALPACA_QUOTE_FAIL] {symbol}: {e}, falling back to signal+buffer")
        alpaca_ask = None
    
    if side == "BUY":
        signal_limit = signal_price * (1 + slip_buffer_pct)
        if alpaca_ask is None:
            return signal_limit
        alpaca_limit = alpaca_ask * (1 + slip_buffer_pct)
        return max(signal_limit, alpaca_limit)
    else:  # SELL
        signal_limit = signal_price * (1 - slip_buffer_pct)
        if alpaca_ask is None:  # use bid for sells
            return signal_limit
        # Symmetric logic for sells (use bid)
        return min(signal_limit, alpaca_bid * (1 - slip_buffer_pct))
```

3. **Replace the existing limit-pricing in `place_squeeze_entry()`**:
```python
# OLD:
limit_price = signal_price + slip_amount

# NEW:
limit_price = compute_alpaca_aware_limit(symbol, signal_price, "BUY")
log.info(f"[LIMIT_CALC] {symbol} signal={signal_price} alpaca_ask={alpaca_ask} limit={limit_price}")
```

4. **Retry logic stays as-is** — but the initial limit is now realistic, so retries should be rare. Keep `WB_ENTRY_MAX_RETRIES=3` as a safety net.

5. **Apply same logic to exits** (`place_squeeze_exit()` and `place_wave_breakout_exit()`). Limit SELL = `min(signal_price, alpaca_bid - buffer)` so we sell at or below where Alpaca's book is, not above where we won't fill.

### Cost & rate limit considerations

Alpaca's data API: paid tier has generous rate limits (200 requests/min on basic, higher on subscribed). Our peak entry rate is ~5/min. Quote snapshots are ~1-2KB each. **No rate limit concern.**

The new Alpaca data subscription cost (~$9/month if not already on it) is trivial vs the missed-fill cost. One ODYS or TRAW fill pays for years of Alpaca data.

### Failure modes

- **Alpaca quote API timeout / error:** Fall back to signal_price + buffer (current behavior). Log `[ALPACA_QUOTE_FAIL]`. Never block an entry on Alpaca quote-call failure.
- **Alpaca quote is stale (timestamp > 5s old):** Treat as if quote API failed. Use fallback.
- **Alpaca ask is wildly different from IBKR (e.g., > 5% gap):** Likely a stale/incorrect Alpaca quote. Log `[ALPACA_QUOTE_DIVERGENT]` and use the LOWER of the two (signal_price + buffer) so we don't chase a phantom move.

---

## What CC Should Do This Week

### Tuesday May 12 (during live session)
- Ship the diagnostic logging changes to `bot_v3_hybrid.py`
- Keep all other behavior identical to today's setup
- Let the bot run normally — the new logging is read-only
- At session end, verify `logs/2026-05-12_latency_diagnostic.jsonl` exists and contains entries for every ENTRY SIGNAL the squeeze bot generated

### Wednesday May 13 (off-market or evening session)
- Run `scripts/analyze_latency_diagnostic.py` against Tuesday's data
- Produce the three analysis tables above
- Push to `cowork_reports/2026-05-13_latency_diagnostic.md`
- Make the Outcome A/B/C call

### Thursday May 14 (if Outcome B)
- Build the `compute_alpaca_aware_limit()` helper
- Wire into `place_squeeze_entry()` and `place_squeeze_exit()`
- Test in isolation (paper) for Friday's session

### Friday May 15
- First live paper session with dual-data-source pricing
- Compare squeeze fill rate vs Tuesday's baseline
- This becomes the data point for the May 15-16 tuning review

### Saturday May 16
- Full week review including the latency diagnostic and tuning hypotheses #10/#11/#12

---

## What NOT to Do

- ❌ Do NOT change the squeeze detector logic or entry signal generation
- ❌ Do NOT modify the chop gate, sizing, or strategy parameters
- ❌ Do NOT change WB execution — only squeeze suffers this latency-fill problem
- ❌ Do NOT use Alpaca's data feed for the DETECTOR — IBKR's TBT is still the right signal source
- ❌ Do NOT make the Outcome B architecture change without running the diagnostic first; we need data, not theory
- ❌ Do NOT break the existing retry-on-timeout logic — keep it as the safety net

---

## Acceptance Criteria

**Diagnostic phase (Tuesday-Wednesday):**
- [ ] Diagnostic logging captures every squeeze ENTRY SIGNAL with all 8 new fields
- [ ] Analysis script produces the three tables
- [ ] Outcome A/B/C decision is data-backed, not opinion-backed

**Dual-data-source phase (Thursday-Friday), if Outcome B or C:**
- [ ] If Outcome B: Alpaca-aware limit pricing wired into squeeze entry/exit
- [ ] If Outcome C: design directive for hybrid IBKR-execution-for-squeeze architecture
- [ ] First Friday session shows measurable improvement in squeeze fill rate
- [ ] No regression to WB fill rate or chop-gate behavior

---

*The bot's brain sees the move first. Its hands need to know where the market actually is. Measure the gap, then build the bridge.*
