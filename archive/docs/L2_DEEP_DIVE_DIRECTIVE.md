# L2 DEEP DIVE DIRECTIVE
**Date**: March 2, 2026  
**From**: Research Team (Perplexity)  
**To**: Claude Code  
**Priority**: HIGH — This determines whether we build the pre-trade filtration gate with or without L2  

---

## CONTEXT

We completed the Scanner Study 30 — the bot lost -$10,388 across 41 trades (32% WR) when running scanner-timed backtests on 30 randomly sampled stocks. We identified strong pre-screening filters (float, scanner time, strategy type) but before building a filtration gate, we need to know: **does L2 data change the picture?**

The L2 subsystem (`l2_signals.py`, `l2_entry.py`, `databento_feed.py`) is complete but has been dormant (`WB_ENABLE_L2=0`). We've audited the full infrastructure. This directive activates and tests it.

**Key question**: If L2 had been active during the scanner study trades, would it have:
- Saved the losers (vetoed bad entries via hard gate or score penalty)?
- Boosted the winners (better stops via bid stacking, higher conviction entries)?
- Changed the filtration criteria (book quality > float/time as a predictor)?

---

## PHASE 1: Quick Wins (Do First)

### 1a. Add Missing .env Variables

Add these 11 undocumented L2 variables to `.env.example` with descriptions. They have working defaults in code but operators can't see or tune them:

```bash
# --- L2 Acceleration ---
# WB_L2_ACCEL_IMPULSE=1        # Allow L2 to waive rising-close impulse requirement (0=off, 1=on)
# WB_L2_ACCEL_CONFIRM=1        # Allow L2 to waive weak trigger candle at confirmation (0=off, 1=on)
# WB_L2_HARD_GATE=1            # Block entry when book is strongly bearish (0=off, 1=on)
# WB_L2_MIN_BULLISH_ACCEL=3    # Min bullish signal count to trigger acceleration (1-5)

# --- L2 Entry Strategy (l2_entry.py) ---
# WB_L2E_MIN_BULLISH_BARS=2    # Consecutive bullish bars before L2 entry can arm
# WB_L2E_MIN_SIGNALS=2         # Min bullish L2 signals per bar to count as "bullish"
# WB_L2E_IMBALANCE_MIN=0.58    # Lower imbalance threshold for L2 entry (vs 0.65 for scoring)
# WB_L2E_MAX_SPREAD=3.0        # Max spread % allowed for L2 entry
# WB_L2E_MAX_VWAP_PCT=15       # Exhaustion gate: max % above VWAP
# WB_L2E_MAX_MOVE_PCT=60       # Exhaustion gate: max % from session low
# WB_L2E_MIN_SCORE=4.0         # Minimum score to arm L2 entry

# --- L2 Cache ---
# WB_L2_CACHE_DIR=l2_cache     # Local directory for Databento .dbn.zst cached files
```

### 1b. Fix Exchange Auto-Detection

In `databento_feed.py`, the `_resolve_dataset()` function is hardcoded to `XNAS.ITCH` with a TODO. Fix it:

```python
# Known NYSE-listed exchanges — expand as needed
NYSE_EXCHANGES = {"XNYS", "ARCX", "XASE"}  # NYSE, Arca, AMEX

def _resolve_dataset(symbol: str) -> str:
    """
    Resolve the correct Databento dataset for a symbol.
    Uses Alpaca metadata if available, otherwise defaults to XNAS.ITCH
    with fallback to XNYS.PILLAR on fetch failure (existing behavior).
    """
    # Try Alpaca asset lookup first
    try:
        from alpaca.trading.client import TradingClient
        client = TradingClient(os.getenv("APCA_API_KEY_ID"), os.getenv("APCA_API_SECRET_KEY"))
        asset = client.get_asset(symbol)
        if asset.exchange in NYSE_EXCHANGES:
            return "XNYS.PILLAR"
    except Exception:
        pass
    return "XNAS.ITCH"  # Default with existing fallback on failure
```

If Alpaca isn't available in the backtest context, the existing fallback behavior (try XNAS, fall back to XNYS on error) is acceptable — just add a log line so we can see when fallback fires.

### 1c. Verify Databento Historical Access

Before running any backtests, confirm the API key works for historical MBP-10:

```python
import databento as db

client = db.Historical(os.getenv("DATABENTO_API_KEY"))

# Check cost for one stock, one day, MBP-10
cost = client.metadata.get_cost(
    dataset="XNAS.ITCH",
    symbols=["NCI"],
    schema="mbp-10",
    start="2026-02-13T07:00",
    end="2026-02-13T12:00"
)
print(f"Estimated cost for NCI 2026-02-13 MBP-10: ${cost:.4f}")
```

Report the per-stock cost estimate so we can budget the full study.

---

## PHASE 2: L2 Pilot Test (10 Stocks)

### Objective

Run the same 10 stocks from the Scanner Study 30 **twice**:
1. **Without L2** (`simulate.py SYMBOL DATE --ticks --sim-start HH:MM`) — should reproduce the Scanner Study 30 results
2. **With L2** (`simulate.py SYMBOL DATE --ticks --l2 --sim-start HH:MM`) — same stocks, now with Databento MBP-10 data

Compare the results trade-by-trade to measure L2's impact.

### The 10 Pilot Stocks

**Winners (5):**

| Symbol | Date | Scanner Time | Sim Start | Without-L2 P&L | Gap% | Float |
|--------|------|-------------|-----------|-----------------|------|-------|
| NCI | 2026-02-13 | 08:43 | 08:43 | +$577 | 11.9% | 1.08M |
| VOR | 2026-01-12 | 08:23 | 08:23 | +$501 | 6.5% | 8.06M |
| FSLY | 2026-02-12 | 07:26 | 07:26 | +$176 | 46.5% | 139.39M |
| MCRB | 2026-02-13 | 09:30 | 09:30 | +$113 | 7.8% | 7.42M |
| BDSX | 2026-01-12 | 07:00 | 07:00 | -$45 | 38.3% | 3.85M |

**Losers (5):**

| Symbol | Date | Scanner Time | Sim Start | Without-L2 P&L | Gap% | Float |
|--------|------|-------------|-----------|-----------------|------|-------|
| CRSR | 2026-02-13 | 08:41 | 08:41 | -$1,939 | 36.2% | 44.36M |
| AUID | 2026-01-15 | 08:57 | 08:57 | -$1,683 | 101.5% | 9.84M |
| FJET | 2026-01-13 | 08:10 | 08:10 | -$1,263 | 5.1% | 17.36M |
| QMCO | 2026-01-15 | 08:31 | 08:31 | -$1,193 | 5.2% | 13.58M |
| PMAX | 2026-01-13 | 07:00 | 07:00 | -$1,098 | 34.4% | 5.09M |

### Execution Steps

1. **Verify baseline** — Run each stock WITHOUT `--l2` and confirm P&L matches the Scanner Study 30 results above. If any don't match (due to code changes since the study), note the difference.

2. **Fetch L2 data** — For each stock, fetch Databento MBP-10 historical data. The data will be cached locally in `l2_cache/`. Monitor API costs.

3. **Run with L2** — Run each stock WITH `--l2` flag. Use the same sim-start times. Record:
   - Number of trades (did L2 gate block any entries?)
   - Each trade's entry score (did L2 change the score?)
   - Each trade's stop level (did bid stacking change the stop?)
   - P&L per trade
   - Any L2 exit signals that fired
   - Full log output (we need to see every L2 log line)

4. **Also run L2 Entry Strategy** — For each stock, run with `--l2-entry` to see if the standalone L2 entry detector finds any setups the regular detector missed. This is exploratory — just report what it finds.

### Report Format

Create `L2_PILOT_RESULTS.md` with:

```markdown
# L2 Pilot Test Results

## Summary Table
| Symbol | Date | Without L2 P&L | With L2 P&L | Delta | Trades Changed | Key L2 Impact |
|--------|------|----------------|-------------|-------|----------------|---------------|
| NCI    | ... | +$577 | ??? | ??? | ??? | (what L2 did) |
| ...    |     |       |     |     |     |               |

## Per-Stock Deep Dive

### NCI (2026-02-13)
**Without L2:** (trade-by-trade from baseline)
**With L2:** (trade-by-trade with L2 log lines)
**L2 Impact:** (what specifically changed and why)
**L2 Entry Strategy:** (any setups found?)

### VOR (2026-01-12)
(repeat for all 10)
...

## L2 Book Quality at Entry Time
For each trade taken (with or without L2), record the L2 state at the moment of entry:
| Symbol | Trade# | Entry Time | Imbalance | Trend | Bid Stack? | Ask Thin? | Spread% | Score Impact |
(This data is critical — it tells us whether book quality at entry predicts trade outcome)

## Findings
1. Did L2 save any losing trades? Which ones and how?
2. Did L2 improve any winning trades? How?
3. Did L2 hurt any trades? (false gates, missed entries?)
4. Is book quality at entry correlated with trade outcome?
5. Databento API cost for 10 stocks: $???

## Recommendation
Based on this pilot, should we:
(a) Run the full 93 remaining scanner stocks with L2?
(b) Build the filtration gate WITH L2 pre-screening?
(c) Improve the L2 logic first before scaling up?
```

---

## PHASE 3: Enhancements (Only If Phase 2 Shows Promise)

**DO NOT implement Phase 3 until Phase 2 results are reviewed by the team.** This section documents planned improvements for reference.

### 3a. L2 Pre-Trade Book Quality Score

Add a function that can evaluate a stock's L2 quality in the first N minutes of trading, BEFORE any trade decision:

```python
def compute_book_quality_score(symbol: str, date: str, start: str, minutes: int = 5) -> dict:
    """
    Fetch L2 data for the first N minutes of a stock's session.
    Returns a quality score that can be used for pre-trade filtering.
    
    Returns:
        {
            "avg_imbalance": float,        # avg imbalance over the window
            "imbalance_trend": str,         # "rising"/"falling"/"flat"
            "bid_stacking_detected": bool,  # any stacking in the window?
            "avg_spread_pct": float,        # avg spread
            "min_near_depth": int,          # minimum total depth at top 3 levels
            "book_quality_score": float,    # composite score 0-10
            "recommendation": str           # "DO_TRADE" / "CAUTION" / "NO_TRADE"
        }
    """
```

This would slot into the filtration gate:
- **DO_TRADE**: Book quality score >= 6 — strong bid support, tight spread, bullish imbalance
- **CAUTION**: Score 3-6 — mixed signals, trade with reduced size or higher score requirement
- **NO_TRADE**: Score < 3 — thin book, bearish imbalance, wide spread

### 3b. Enhanced Exit Signals

Add to `check_l2_exit()`:

```python
# Falling imbalance trend + below neutral (early warning)
if l2_state.get("imbalance_trend") == "falling" and l2_state.get("imbalance", 0.5) < 0.45:
    return "l2_trend_shift"

# Sudden spread widening (liquidity event)
if l2_state.get("spread_pct", 0) > WB_L2_EXIT_SPREAD_MAX:
    return "l2_spread_spike"
```

Add env vars:
```bash
WB_L2_EXIT_TREND_ENABLED=1      # Enable falling-trend exit
WB_L2_EXIT_SPREAD_MAX=2.0       # Spread % that triggers exit
```

### 3c. Level-Aware Stacking

Enhance `_SymbolL2State.update()` to check if bid stacking aligns with key levels:

```python
# After detecting bid_stacking, check if stack is at a key level
if self.bid_stacking and vwap is not None:
    for price, size in self.bid_stack_levels:
        if abs(price - vwap) / vwap < 0.005:  # within 0.5% of VWAP
            self.signals.append(L2Signal("L2_BID_STACK_AT_VWAP", f"stack at {price} near VWAP {vwap}", 1.0))
```

This requires passing VWAP into the L2 signal detector, which is currently not done. The interface change:
```python
def on_snapshot(self, snap: L2Snapshot, vwap: float = None):
```

### 3d. Sub-Second Sampling for First 30 Minutes

In `databento_feed.py`, change the sampling strategy:

```python
# First 30 minutes: sample every 100ms (critical setup window)
# After 30 minutes: sample every 1 second (as currently)
if snap_time < session_start + timedelta(minutes=30):
    sample_interval_ms = 100
else:
    sample_interval_ms = 1000
```

This increases data volume ~10x for the first 30 minutes but covers the window where most entries happen.

---

## REGRESSION PROTECTION

After Phase 1 (quick wins), verify the three regression benchmarks still pass:

```bash
python simulate.py VERO 2026-01-16 --ticks     # Expected: +$6,890
python simulate.py GWAV 2026-01-16 --ticks     # Expected: +$6,735
python simulate.py ANPA 2026-01-09 --ticks     # Expected: +$2,088
```

These should be **unchanged** since Phase 1 only adds .env documentation and exchange detection — no logic changes.

After Phase 2, run the same regressions both WITH and WITHOUT `--l2` to verify L2 doesn't break them:

```bash
# Without L2 (must match baseline)
python simulate.py VERO 2026-01-16 --ticks
python simulate.py GWAV 2026-01-16 --ticks
python simulate.py ANPA 2026-01-09 --ticks

# With L2 (may differ — record the delta)
python simulate.py VERO 2026-01-16 --ticks --l2
python simulate.py GWAV 2026-01-16 --ticks --l2
python simulate.py ANPA 2026-01-09 --ticks --l2
```

---

## DELIVERABLES

| Phase | Deliverable | Priority |
|-------|-------------|----------|
| 1 | Updated `.env.example` with 11 L2 vars | Must |
| 1 | Fixed `_resolve_dataset()` with Alpaca lookup | Must |
| 1 | Databento cost estimate for pilot | Must |
| 1 | Regression check (3 stocks, no change) | Must |
| 2 | `L2_PILOT_RESULTS.md` — full comparison report | Must |
| 2 | L2 book quality data at each entry time | Must |
| 2 | L2 Entry Strategy results (exploratory) | Should |
| 2 | Regression check with `--l2` (3 stocks) | Must |
| 3 | Not yet — wait for team review of Phase 2 | Hold |

---

## IMPORTANT NOTES

- **Databento API key** is required for all L2 backtesting. It should be set in `.env` as `DATABENTO_API_KEY`. If the key doesn't work or there are access issues, report immediately — don't try to work around it.
- **Cost monitoring**: After fetching L2 data for the first stock, report the cost. If it's more than ~$2/stock, pause and report before continuing.
- **Cache the data**: All L2 data fetched should be cached in `l2_cache/` so we don't re-fetch on subsequent runs.
- **Don't modify `l2_signals.py` or `l2_entry.py` in Phase 1 or 2** — we're testing the existing infrastructure as-is first.
- **Signal mode cascading exits must NOT be suppressed** — this is the bot's core edge. L2 enhancements (Phase 3) must work WITH signal exits, not replace them.

---

*Directive authored by Research Team — March 2, 2026*
*Reference: L2_INFRASTRUCTURE_AUDIT.md, scanner_study_results.md*