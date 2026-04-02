# Extended Play List (EPL) — Architecture Design

## Last Updated: 2026-04-02

---

## The Concept

When SQ hits its 2R target, that's not an exit signal — it's a **graduation signal**. 86% of 2R hits are runners. Instead of trying to hold one position through the entire run (which requires solving the unsolvable "when to exit" problem), we:

1. **Take 100% profit at 2R.** Lock in the win. SQ's job is done.
2. **Add the stock to the Extended Play List (EPL).** This is a watchlist of "proven runners" — stocks that just demonstrated real momentum.
3. **Independent strategies watch the EPL** for their own setups. Each strategy has its own entry criteria, its own stops, its own exits. No shared position management.

This is architecturally different from MP V2, which shared positions with SQ, used SQ exits, and activated on any SQ close (not just 2R). The EPL is a clean separation of concerns.

---

## Why This Works Better Than Holding

The core insight from the post-exit analysis:

| Approach | Problem |
|----------|---------|
| Hold past 2R with static trail | Trail too tight = stopped out on pullback. Trail too loose = give back gains. |
| Hold past 2R with candle exits | Exhaustion score doesn't work (28x more damage from false exits on runners than savings from correct exits on done stocks). |
| 2R partials (75% exit, 25% runner) | Just going back to what we have. Leaves the same money on the table, just 25% of it. |
| **EPL: full exit + independent re-entry** | Each re-entry is a **new trade** with a **new stop** at the pullback low. Risk is defined. Upside is unlimited. Multiple bites at the apple. |

The key advantage: after a pullback following 2R, the re-entry stop is at the pullback low — much tighter than the original SQ stop. So R:R on re-entries is actually better than holding.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                     POSITION ARBITRATOR                       │
│  • One position at a time (Alpaca constraint)                │
│  • Priority: SQ cascading > EPL strategies                   │
│  • Tracks which strategy owns current position               │
└───────────────────────┬──────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│   SQUEEZE    │ │     EPL      │ │   STRATEGY   │
│  DETECTOR    │ │  WATCHLIST   │ │   REGISTRY   │
│              │ │              │ │              │
│ (primary     │ │ Graduated    │ │ MP Re-entry  │
│  strategy,   │ │ stocks with  │ │ VWAP Reclaim │
│  unchanged)  │ │ context      │ │ Curl/Ext     │
│              │ │              │ │ Dip-Buy      │
└──────┬───────┘ └──────┬───────┘ └──────┬───────┘
       │                │                │
       │  graduates     │  feeds         │
       │  stocks ──────►│  strategies ──►│
       │                │                │
       └────────────────┴────────────────┘
                        │
                ┌───────┴───────┐
                ▼               ▼
         ┌────────────┐  ┌────────────┐
         │ SQ EXITS   │  │ EPL EXITS  │
         │ (V1 mech)  │  │ (per-strat)│
         │ unchanged  │  │ own rules  │
         └────────────┘  └────────────┘
```

---

## Component 1: EPL Watchlist

An in-memory list of stocks that graduated from SQ at 2R. Lives for the session (no persistence needed — graduation only matters intraday).

### Graduation Event

Triggered when: `exit_reason == "sq_target_hit"` AND `realized_r >= 2.0`

NOT triggered on: para_trail, max_loss, stop_hit, bail_timer, or any non-target exit. Those stocks didn't prove they're runners.

### Graduation Context (passed to strategies)

```python
@dataclass
class GraduationContext:
    symbol: str
    graduation_time: datetime          # When SQ exited at 2R
    graduation_price: float            # Price at SQ 2R exit
    sq_entry_price: float              # Original SQ entry
    sq_stop_price: float               # Original SQ stop (context for R calc)
    hod_at_graduation: float           # Session HOD when graduated
    vwap_at_graduation: float          # VWAP level at graduation
    pm_high: float                     # Premarket high (key level)
    avg_volume_at_graduation: float    # Running avg vol for vol comparison
    sq_trade_count: int                # How many SQ trades on this symbol so far
    r_value: float                     # Dollar value of 1R for this stock
```

This context gives EPL strategies everything they need to assess the stock without re-deriving it.

### Watchlist Rules

- Max stocks on EPL: configurable (default 5). Oldest graduates first-out.
- EPL stocks expire after configurable time (default 60 minutes). Late-session re-entries are low quality.
- A stock can graduate multiple times (SQ cascading re-entry hits 2R again → re-added with fresh context).

### Env Vars

```bash
WB_EPL_ENABLED=0                  # Master gate (OFF by default)
WB_EPL_MAX_STOCKS=5               # Max simultaneous graduated stocks
WB_EPL_EXPIRY_MINUTES=60          # Graduation expires after N minutes
WB_EPL_MIN_GRADUATION_R=2.0       # Minimum realized R to graduate (default = 2R target)
```

---

## Component 2: Strategy Registry

A pluggable system where independent strategy modules register to receive EPL events. Each strategy is a self-contained module.

### Strategy Interface

```python
class EPLStrategy(ABC):
    """Base class for all Extended Play List strategies."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy identifier: 'mp_reentry', 'vwap_reclaim', 'curl', 'dip_buy'"""

    @property
    @abstractmethod
    def priority(self) -> int:
        """Entry priority (higher wins). SQ is always 100. EPL strategies < 100."""

    @abstractmethod
    def on_graduation(self, ctx: GraduationContext) -> None:
        """Called when a stock graduates to EPL. Initialize tracking state."""

    @abstractmethod
    def on_expiry(self, symbol: str) -> None:
        """Called when a graduated stock expires from EPL. Clean up state."""

    @abstractmethod
    def on_bar(self, symbol: str, bar: dict) -> Optional[EntrySignal]:
        """Process a 1-minute bar. Return entry signal or None."""

    @abstractmethod
    def on_tick(self, symbol: str, price: float, size: int) -> Optional[EntrySignal]:
        """Process a tick. Return entry signal or None (most strategies = None)."""

    @abstractmethod
    def manage_exit(self, symbol: str, price: float, bar: dict) -> Optional[ExitSignal]:
        """Manage exit for a position THIS strategy owns. Return exit or None."""

    @abstractmethod
    def reset(self, symbol: str) -> None:
        """Full reset for symbol (position closed, start fresh)."""
```

### Entry Signal

```python
@dataclass
class EntrySignal:
    symbol: str
    strategy: str              # Which EPL strategy
    entry_price: float         # Limit or market
    stop_price: float          # Strategy's own stop
    target_price: float        # Strategy's own target (can be None for trail-only)
    position_size_pct: float   # % of max notional (allows probe sizing)
    reason: str                # Human-readable entry reason
    confidence: float          # 0-1 score for prioritization
```

### Exit Signal

```python
@dataclass
class ExitSignal:
    symbol: str
    strategy: str
    exit_price: float
    exit_reason: str           # Strategy-specific reason
    exit_pct: float            # % of position to exit (allows partials)
```

### Registration

```python
class StrategyRegistry:
    def __init__(self):
        self.strategies: List[EPLStrategy] = []

    def register(self, strategy: EPLStrategy):
        self.strategies.append(strategy)
        self.strategies.sort(key=lambda s: s.priority, reverse=True)

    def notify_graduation(self, ctx: GraduationContext):
        for s in self.strategies:
            s.on_graduation(ctx)

    def collect_entry_signals(self, symbol, bar, tick_price) -> List[EntrySignal]:
        signals = []
        for s in self.strategies:
            sig = s.on_bar(symbol, bar)
            if sig:
                signals.append(sig)
        return sorted(signals, key=lambda s: s.confidence, reverse=True)
```

---

## Component 3: Position Arbitrator

The single-position constraint is real — Alpaca sees one position per symbol, and the bot processes one symbol's ticks at a time. The arbitrator decides who gets to trade.

### Rules

1. **SQ always wins.** If SQ is PRIMED or ARMED on a symbol, no EPL strategy can enter. SQ's cascading re-entry is proven profitable and takes priority.

2. **One position at a time.** If ANY strategy (SQ or EPL) holds a position on ANY symbol, no new entries. This matches the current architecture and avoids the multi-position refactor.

3. **Highest-confidence EPL signal wins.** If multiple EPL strategies want to enter different symbols at the same time, the one with the highest `confidence` score goes.

4. **Exit ownership is absolute.** Once a strategy enters, ONLY that strategy manages the exit. No other strategy can interfere. The arbitrator routes tick/bar data to the owning strategy's `manage_exit()`.

### Why single-position is actually fine

The EPL strategies fire on pullbacks AFTER SQ's 2R exit. By the time a pullback forms (3-10 bars), SQ has already exited and is unlikely to immediately re-arm on the same bar. The sequential nature of squeeze → pullback → re-entry means position conflicts are rare in practice.

If SQ does re-arm during an EPL cooldown/lookback period, SQ wins (rule 1). This is correct — SQ's cascading edge is the primary profit driver.

### State Machine

```
                    ┌─────────────────┐
                    │      IDLE       │
                    │  (no position)  │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        SQ enters      EPL enters     No signal
              │              │              │
              ▼              ▼              │
        ┌──────────┐  ┌──────────┐         │
        │ SQ OWNS  │  │EPL OWNS  │         │
        │ position │  │ position │         │
        │          │  │          │         │
        │ SQ exits │  │ strategy │         │
        │ manage   │  │ exits    │         │
        │ exit()   │  │ manage   │         │
        │          │  │ exit()   │         │
        └────┬─────┘  └────┬─────┘         │
             │              │              │
             ▼              ▼              │
        ┌─────────────────────────────────┘
        │
        ▼
   Back to IDLE
```

### Env Vars

```bash
WB_EPL_SQ_PRIORITY=1              # SQ blocks EPL when PRIMED/ARMED (default ON)
WB_EPL_COOLDOWN_BARS=3            # Bars after graduation before EPL strategies can enter
WB_EPL_MAX_TRADES_PER_GRAD=3      # Max EPL trades per graduated stock
```

---

## Component 4: Strategy Modules (What Slots In)

Each of these is a separate .py file implementing `EPLStrategy`. They are fully independent — own entry logic, own exits, own state machines.

### Strategy A: MP Re-Entry (salvage from existing MP V2)

**What it does:** Detects micro-pullback pattern after SQ graduation.

**Entry:** After 3+ bar pullback from graduation price, green recovery candle with volume, price breaks pullback high.

**Stop:** Pullback low minus ATR buffer.

**Exit (OWN, not SQ exits):**
- Hard stop at pullback low
- Trail at 1.5R once profitable
- VWAP loss = exit
- Time stop: 5 bars without new high = exit

**Salvageable from MP V2:** Pullback detection logic, ARM trigger logic, cooldown timer. Throw away: SQ exit routing, DORMANT→unlock mechanism (replaced by EPL graduation), impulse detection (not needed).

**Env:** `WB_EPL_MP_ENABLED=0`

### Strategy B: VWAP Reclaim

**What it does:** After a post-squeeze pullback drops below VWAP, waits for price to reclaim VWAP with volume, then enters on first 1m candle making a new high.

**Entry:** Price crosses above VWAP from below + first 1m candle new high + volume > 1.5x avg.

**Stop:** Below VWAP (or below the reclaim candle low).

**Exit (OWN):**
- VWAP loss = immediate exit
- Prior HOD or whole dollar = target
- Trail at 1R once at target

**Evidence:** CHNR 2026-03-19 — Ross's bread-and-butter pattern. Two of his three trade sequences were VWAP reclaim.

**Env:** `WB_EPL_VWAP_ENABLED=0`

### Strategy C: Curl / Extension

**What it does:** Detects rounded-bottom recovery approaching prior HOD. Multi-bar pattern: stock bases, forms higher lows, curls up toward resistance.

**Entry:** 3+ bars of higher lows + price within 3% of prior resistance + volume increasing on approach.

**Stop:** Below the curl's lowest low.

**Exit (OWN):**
- Break of prior HOD = trail tightens
- Failure to break HOD within 3 bars of reaching it = exit
- New HOD with volume = hold with trailing stop

**Evidence:** CHNR 2026-03-19 — Ross's +$2,000 curl from $5.00 support was the day's best trade.

**Env:** `WB_EPL_CURL_ENABLED=0`

### Strategy D: Dip-Buy Into Support

**What it does:** Countertrend buy on sharp pullback to known support level (VWAP, whole dollar, prior consolidation).

**Entry:** Sharp pullback (3%+ in 2-3 bars) + bounce off support level + hammer/engulfing candle.

**Stop:** Below support level.

**Exit (OWN):**
- Tight target: 50% of the pullback range (countertrend = smaller target)
- Quick time stop: 3 bars without progress = exit (countertrend can't stall)
- Any new low below entry bar = immediate exit

**Evidence:** ARTL 2026-03-18 — Ross bought dip from $8.20 to $5.63, entered at $6.73, rode to $7.60 (+$5K).

**Env:** `WB_EPL_DIP_ENABLED=0`

---

## Integration With Current Codebase

### bot_v3_hybrid.py Changes (minimal)

The bot's main loop already processes bars and ticks per symbol. The integration points:

1. **Graduation hook:** In the exit handler, when `exit_reason == "sq_target_hit"`:
   ```python
   if exit_reason == "sq_target_hit" and EPL_ENABLED:
       ctx = build_graduation_context(symbol, trade, state)
       epl_watchlist.add(ctx)
       strategy_registry.notify_graduation(ctx)
   ```

2. **Bar processing:** After SQ detector processes a bar, if symbol is on EPL:
   ```python
   if symbol in epl_watchlist and not state.open_position:
       signals = strategy_registry.collect_entry_signals(symbol, bar, None)
       if signals and not sq_is_active(symbol):
           execute_entry(signals[0])  # Highest confidence
   ```

3. **Exit routing:** When position owner is an EPL strategy:
   ```python
   if state.open_position and state.open_position["setup_type"].startswith("epl_"):
       strategy = registry.get_strategy(state.open_position["setup_type"])
       exit_sig = strategy.manage_exit(symbol, price, bar)
   ```

### No refactor of single-position model needed

The EPL strategies enter after SQ exits. They use the same `state.open_position` slot. The only addition is routing exit management to the EPL strategy instead of SQ's exits when the position is EPL-owned.

### simulate.py Changes

Same pattern — graduation hook in exit handler, EPL bar processing after SQ, exit routing by setup_type.

---

## Risk Management

### Risk Budgets

```bash
WB_EPL_MAX_NOTIONAL=50000         # Same as SQ — goal is consistency, not downsizing
WB_EPL_MAX_LOSS_SESSION=1000      # Hard daily loss cap for ALL EPL trades combined
```

**Sizing decision (Manny, 2026-04-02):** EPL uses the same max notional as SQ. The goal is to build strategies that win consistently — if they meet that bar, there's no reason to handicap them with smaller size. The session loss cap protects SQ's proven wins while EPL strategies are being validated.

### Graduation doesn't guarantee success

Just because a stock hit 2R doesn't mean the next setup works. The stock could be done (14% of 2R hits are). EPL trades need their own tight risk management — that's why each strategy defines its own stop and the per-session loss cap exists.

---

## Implementation Phases

### Phase 1: Framework + MP Re-entry (salvage existing code)

1. Build EPL watchlist + graduation hook
2. Build strategy registry + position arbitrator
3. Port MP V2 detection into EPL strategy interface (own exits, not SQ exits)
4. Backtest on the 30 known runners from post-exit analysis
5. Gate: `WB_EPL_ENABLED=0`, `WB_EPL_MP_ENABLED=0`

### Phase 2: VWAP Reclaim

1. Build VWAP reclaim strategy module
2. Backtest on CHNR, ARTL, and other stocks with known VWAP reclaim patterns
3. Gate: `WB_EPL_VWAP_ENABLED=0`

### Phase 3: Curl / Extension

1. Build curl detection (multi-bar higher-low pattern)
2. Backtest on CHNR, ARTL curl patterns
3. Gate: `WB_EPL_CURL_ENABLED=0`

### Phase 4: Dip-Buy

1. Build dip-buy strategy (countertrend, tighter risk)
2. Backtest on ARTL dip-buy pattern
3. Gate: `WB_EPL_DIP_ENABLED=0`

### Phase 5: Live Paper + Tuning

1. Enable EPL framework live (all strategies OFF individually)
2. Turn on one strategy at a time, observe for 1 week each
3. Compare EPL trades vs SQ-only baseline

---

## How This Differs From MP V2

| Aspect | MP V2 (old) | EPL Architecture (new) |
|--------|-------------|----------------------|
| Activation trigger | Any SQ trade close (win or loss) | Only sq_target_hit at 2R+ |
| Position management | Shared with SQ | Independent (same slot, but EPL owns it) |
| Exit logic | Routed through SQ V1 mechanical | Each strategy has own exits |
| Strategy count | Just MP | 4 strategies, pluggable framework |
| Risk budget | Shared with SQ | Separate, with session loss cap |
| SQ interference | MP entry blocks SQ re-entry | SQ always has priority, EPL defers |
| State coupling | MP dormant until SQ unlocks | EPL watchlist is decoupled — strategies check it independently |

---

## Decisions (Manny, 2026-04-02)

1. **SQ cascading re-entry works alongside EPL.** SQ has priority. EPL fills gaps where SQ doesn't re-arm. Worth testing whether EPL strategies can outperform SQ re-entries on specific patterns — if so, priority can be revisited.

2. **Session loss cap: $1,000.** Protects known SQ wins that re-arm.

3. **Build order: MP re-entry first, VWAP reclaim second.** Start MP backtest, then build VR in parallel while waiting on results. Note: standalone VR was tested weeks ago (0 wins, 0 losses) — likely same root cause as standalone MP (not truly independent, building off squeeze instead of own play).

4. **EPL sizing = SQ sizing.** Full max notional ($50K). Goal is consistency across the board, not downsizing. If strategies prove consistent, no reason to handicap them.

5. **No regression testing against old targets.** EPL is a new system — evaluate it fresh on its own merits.

---

*This document is the architectural blueprint. No code changes until reviewed and approved.*
