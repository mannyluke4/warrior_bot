# WB Dead-Tape Gate — Revised Directive

**Date:** 2026-05-15
**Author:** Cowork (Perplexity)
**For:** CC
**Supersedes:** `DIRECTIVE_2026-05-15_WB_LIQUIDITY_GATE.md` and `DIRECTIVE_2026-05-15_WB_LIQUIDITY_GATE_AMENDMENT.md`
**Trigger:** Manny clarified: at $1-20M market caps, $50K orders don't meaningfully move the tape. The "we are the liquidity event" concern was overblown even for real money. The real problem is the bot entering DEAD stocks — names whose tape is noise, not movement.

---

## What changes

1. **Drop Proposal B entirely.** Sizing-as-fraction-of-bar-volume was a solution to a problem that mostly doesn't exist at our scale on $5-20M cap stocks. Even at $50K into a $5M cap name, real-money slippage is a few cents, not a meltdown. Remove B from the work queue.

2. **Reframe Proposal A.** Don't ship the simple "minimum bounce bar volume" floor I originally specified. Ship a smarter dead-tape detector instead. The goal: identify stocks where the tape itself is dead, not stocks where one specific bar happened to be thin.

3. **The fix is one gate, not two.** Focus all engineering on getting this one right.

---

## What "dead tape" actually looks like

Per your description: "bars are literally little dots that are plastered around the chart." That visual maps to specific measurable properties of the prior 30-60 minutes of 1m data:

1. **Bar emptiness rate**: fraction of 1m bars with volume < some floor (e.g., 500 shares)
2. **Tick frequency**: trades per minute, averaged over the window
3. **Bar-volume coefficient of variation**: high CV means a few noise spikes drowning in zeros
4. **Spread between consecutive prints**: dead tape has 5-10¢ gaps between trades, live tape has continuous prints

The cleanest single signal is **bar emptiness rate**. It directly measures what you see on the chart: most bars are visually invisible because volume is near zero.

### Proposed metric

```python
def is_dead_tape(bars_1m_last_30min, threshold=0.5):
    """
    Returns True if more than `threshold` fraction of bars in the
    lookback window have volume below the dead-bar floor.
    """
    DEAD_BAR_VOL = 500  # shares; below this, a bar is "essentially no trading"
    if len(bars_1m_last_30min) < 20:
        return True  # not enough data = treat as dead

    dead_bars = sum(1 for b in bars_1m_last_30min if b.volume < DEAD_BAR_VOL)
    dead_rate = dead_bars / len(bars_1m_last_30min)

    return dead_rate > threshold
```

For ATRA today: in the 30 minutes leading up to the 13:21 entry, CC's tick audit showed bars like:
- 13:18:10  0 ticks in 60s
- 13:20:00  one print (1,400 shares)
- 13:21:01  15 ticks (the noise spike)
- 13:21:56  6 ticks (drifting back down)
- 13:24:26  0 ticks

If we assume the pattern was consistent for the prior 30 min (CC can confirm from logs), the dead-bar rate is easily >50%. Gate would veto.

For a real WB candidate (FATN 5/5, SST 5/11): CC should pull the 30-min pre-entry tape for these from logs. My expectation: dead-bar rate <20%. If higher, the metric needs tuning.

---

## Ship plan

### Phase 1 — Saturday: build and validate

**File:** `wave_breakout_detector.py` (or a new `tape_quality.py` if cleaner)

```python
# Env vars
WB_DEAD_TAPE_GATE_ENABLED=1
WB_DEAD_TAPE_LOOKBACK_MIN=30        # window of bars to evaluate
WB_DEAD_TAPE_BAR_VOL_FLOOR=500      # bar < this = "dead bar"
WB_DEAD_TAPE_MAX_DEAD_RATE=0.5      # if >50% of bars are dead, veto
WB_DEAD_TAPE_MIN_BARS=20            # need at least this many bars; else veto
```

Pre-ARM check:
```python
def _check_tape_alive(self, symbol, bars_1m) -> tuple[bool, str]:
    if not WB_DEAD_TAPE_GATE_ENABLED:
        return (True, "tape_check_disabled")

    lookback_bars = bars_1m[-WB_DEAD_TAPE_LOOKBACK_MIN:]
    if len(lookback_bars) < WB_DEAD_TAPE_MIN_BARS:
        return (False, f"insufficient_bars({len(lookback_bars)}<{WB_DEAD_TAPE_MIN_BARS})")

    dead_bars = sum(1 for b in lookback_bars if b.volume < WB_DEAD_TAPE_BAR_VOL_FLOOR)
    dead_rate = dead_bars / len(lookback_bars)

    if dead_rate > WB_DEAD_TAPE_MAX_DEAD_RATE:
        return (False, f"dead_tape(dead_rate={dead_rate:.2f},dead_bars={dead_bars}/{len(lookback_bars)})")

    return (True, f"tape_alive(dead_rate={dead_rate:.2f})")
```

**Where it sits in the gate stack:** AFTER score floor, AFTER R% floor, BEFORE chop_gate_v3 sub-gates. Same position I'd put the old liquidity gate. Reasoning: tape quality is more fundamental than chart-pattern checks. If the tape is dead, no pattern matters.

**Telemetry:** log dead_rate on every WB_ARM, pass or veto. We need the data to tune the threshold over the next 2 weeks.

### Phase 2 — Saturday: validation against known cases

CC pulls 30-min pre-entry tape for:
- **Today's ATRA misfire** — expected dead_rate >50%, should veto
- **FATN 5/5 winner** — expected <30%, should pass
- **ATRA 5/8 winner (+$2,499)** — expected <30%, should pass (this was a 68% gap day, very active tape)
- **SST 5/11 winner** — expected <30%, should pass
- **MEI 5/13 winner** — expected ??? (manual addition during Databento crash; tape may have been thin). Worth measuring.
- **CLNN 5/5 losers (×4)** — expected <30%, these were normal squeeze candidates with real flow
- **NVOX 5/11 loser (the 25-second stop)** — expected ??? Worth measuring.

Save to `cowork_reports/2026-05-16_dead_tape_gate_validation.md`. Tabulated like:

```
Symbol | Date | Entry time | Dead-rate (30m pre) | Outcome | Gate verdict
ATRA   | 5/8  | 17:09 ET   | 0.10               | WIN     | PASS
ATRA   | 5/15 | 13:21 ET   | 0.65               | LOSS    | VETO
...
```

**Acceptance:**
1. ATRA 5/15 must VETO
2. ATRA 5/8 and SST 5/11 must PASS (these are clean wins on real tape)
3. FATN 5/5 must PASS (the persistence-layer prototype winner)
4. If any clean winner gets vetoed, raise `WB_DEAD_TAPE_MAX_DEAD_RATE` to 0.6 or 0.7 and re-validate

If we can't find a threshold that PASSES the 3 clean winners and VETOES the ATRA 5/15 misfire, the dead-bar rate metric isn't load-bearing. Then we try tick frequency or bar-volume CV. CC can iterate on the metric until one works.

### Phase 3 — Monday open: live in paper

If Phase 2 validation passes: flip `WB_DEAD_TAPE_GATE_ENABLED=1` for Monday cron.

If validation fails: report findings, propose alternative metric, do not ship.

### Phase 4 — Permanent inclusion (after 5 days of paper data, 5/22)

Same acceptance criteria as before:
1. At least 1 WB_ARM blocked by dead-tape gate
2. Zero false positives on known winner patterns
3. Better than -$5K cumulative WB P&L baseline

If pass → permanent stack member.

---

## What this kills off

- **Proposal B (sizing cap)**: gone. Not shipping.
- **Original liquidity gate framing**: superseded.
- **"15,000 share absolute bar volume floor"**: replaced by dead-rate metric.
- **Backtest's liquidity-aware execution simulation requirement**: scaled back. Still useful for go-live confidence but not P0. The strategy's bigger problem is signal noise, not execution friction.

---

## What still ships from previous directives

- **Persistence layer** (`wb_persistence.py`) — continues running
- **Intraday adder** (Stage 0.3) — continues observe-only through Monday review
- **Squeeze fill-rate fix** (#1 + #2 + #3 from yesterday) — ships per existing plan
- **FCHL orphan fix** — still P0, separate directive pending your confirmation

---

## Implications for the persistence layer (revised Q3 answer)

Earlier I framed Q3 as "persistence winners may not survive real-money execution." Per your clarification, that concern was overstated. The corrected framing:

**Persistence winners may have been profitable because the tape was alive on those days, not because of any execution accident.** If FATN 5/5, ATRA 5/8, SST 5/11, MEI 5/13 all show dead_rate <30% at their entry times, the persistence layer is working as intended — it's surfacing names whose tape was alive enough to support a real move.

If some of them show high dead_rate, that tells us the persistence layer needs the dead-tape gate as a downstream filter — but the layer itself is still doing useful work.

Either way, **the dead-tape gate makes the persistence layer SAFER**, not redundant.

---

## Today's ATRA position

Recommendation unchanged: flatten now. Reasoning corrected to:
- Setup was bad (signal was statistical noise on a dead tape)
- No real flow to drive the trade either direction
- Risk of overnight orphan until FCHL bug is fixed
- Locked -$608 is better than uncertain expected value on a bad setup

Your call.

---

## Reports CC owes

| When | Report | Status |
|---|---|---|
| Sat 5/16 | `2026-05-16_dead_tape_gate_validation.md` | new (replaces liquidity-gate validation) |
| Sat-Sun | FCHL orphan fix (separate workstream) | pending |
| Mon EOD 5/18 | Stage 0.3 3-day observe summary | per existing plan |
| Mon EOD 5/18 | Daily breakdown with dead-tape gate behavior section | new |
| Fri 5/22 | `2026-05-22_dead_tape_gate_5day_results.md` | new |

---

## Tone note

Two directive revisions in a row on the same problem is unusual but the right outcome. First framing said "we move the market" (wrong, paper). Second said "detector signal is noise on thin tape" (right but the proposed fix was over-engineered). Third (this one) keeps the right diagnosis and drops the unnecessary fix: just detect when the tape is dead and don't trade those.

The simpler version is more likely to work, easier to validate, easier to tune, and doesn't carry the strategic implications about real-money slippage that aren't actually problems at our scale.

Drop B. Build A as a dead-tape detector. Validate against known winners and the ATRA misfire. Ship Monday if it passes.
