# ROLR Case Study — 2026-01-14 (Scanner Fix + Simulation)

## A. Scanner Fix Summary

```
BEFORE: Scanner found 9 candidates on Jan 14. ROLR not included.
        (Original scanner had no results for Jan 14 — scan window ended at 7:15 AM,
         ROLR catalyst broke at 8:18 AM)

AFTER:  Scanner found 107 candidates on Jan 14. ROLR found at checkpoint 08:30.
        ROLR discovery_time: 08:30
        ROLR gap_pct at discovery: +288.6%
        ROLR price at discovery: $13.68
        ROLR discovery_method: rescan
        ROLR float: 3.6M (Profile A)
        ROLR sim_start: 08:30
```

### What Changed

1. **Continuous re-scan** added with 6 checkpoints: 08:00, 08:30, 09:00, 09:30, 10:00, 10:30 AM ET
2. **`find_emerging_movers()`** replaces `find_late_movers()` as the primary catch-all for mid-session gappers
3. **`fetch_prev_close()` bug fixed** — daily bars could include the current trading day's bar, causing prev_close to use TODAY's close instead of yesterday's. Now filters to bars strictly before target date.
4. **Discovery metadata** added: `discovery_time` and `discovery_method` fields on all candidates

### Candidate Breakdown (Jan 14)

| Discovery Method | Count |
|-----------------|-------|
| Premarket (7:15 AM) | 12 |
| Continuous rescan | 95 |
| **Total** | **107** |

### Why ROLR Was Missed Before

1. PM scan window ends at 7:15 AM — ROLR was $3.65 at 7:15 (gap ~3.7%, below 5% threshold)
2. No re-scan between 7:15 AM and 9:30 AM — 2+ hour blind spot
3. Catalyst broke at 8:18 AM — stock went $3.86 → $5.32 in one minute
4. `find_late_movers()` only checked at 9:30 AM — by then ROLR was $15.50 (still in range, but the old code had the prev_close bug too)

---

## B. Stock Profile

```
Symbol:     ROLR
Date:       2026-01-14
Catalyst:   Crypto.com prediction market LOI (news ~8:18 AM ET)
Prev close: $3.52 (Jan 13)
Open:       $15.50 (+340% gap)
Day high:   $33.68
Day low:    $12.33
Close:      $18.89
Volume:     80,267,470
Float:      3.6M (Profile A)
Ross P&L:   ~$86,000
```

---

## C. Price Action Timeline

### Pre-Catalyst Baseline (4:00 AM - 8:17 AM)

```
TIME    PRICE   VOLUME   EVENT
04:29   $3.56        1,700   Minor premarket print
07:00   $3.64          567   Early AM — no gap
07:28   $3.65          683   Still flat, ~3.7% vs prev close
08:00   $3.65       12,990   Start of 8:00 checkpoint — NO gap detected (3.7% < 5%)
08:05   $3.75        2,504   Slight uptick
08:15   $3.89        1,170   Small ramp, but still under 5% gap
08:17   $3.87        3,763   Last calm bar before catalyst
```

### Catalyst Explosion (8:18 AM - 8:34 AM)

```
TIME    PRICE   VOLUME   EVENT
08:18   $5.32      278,281   *** CATALYST: $3.86 → $5.89 high in 1 minute ***
08:19   $7.67    1,119,048   Immediate follow-through
08:20   $8.19      770,333   Continuing ramp
08:22   $6.68      940,522   First big pullback (H: $8.36 → L: $6.40)
08:23   $9.10      966,597   V-bounce
08:24   $8.35    1,354,630   Volatile — hit $10.43 high
08:28   $12.09   1,249,757   Major breakout leg ($9.34 → $12.22)
08:29   $13.00   1,171,008   Continuation
08:30   $13.68     749,622   *** 8:30 CHECKPOINT — ROLR DETECTED ($13.68, +288.6%) ***
08:31   $12.57     716,743   Pullback from $14.00 high
08:33   $17.77   1,323,017   Explosive move $13.15 → $17.90
08:34   $16.88     979,298   Hit $20.84 high! Would be filtered at $20 cap from here
```

### Key Scanner Checkpoints

| Checkpoint | ROLR Price | Gap vs $3.52 | In $2-$20 Range? | Detected? |
|-----------|-----------|-------------|-----------------|----------|
| 7:15 AM | ~$3.65 | +3.7% | Yes | No (gap < 5%) |
| 8:00 AM | $3.65 | +3.7% | Yes | No (gap < 5%) |
| **8:30 AM** | **$13.68** | **+288.6%** | **Yes** | **YES** |
| 9:00 AM | $17.22 | +389% | Yes | Already found |
| 9:30 AM | $16.10 | +357% | Yes | Already found |

### Post-Detection Trading Window (8:30 AM - 12:00 PM)

```
TIME    PRICE   VOLUME   KEY LEVELS
08:30   $13.68     749K   SIM STARTS — EMA9 = $9.73 (seed from 4AM-8:30)
08:31   $12.57     717K   IMPULSE detected → RESET (bearish engulfing)
08:32   $13.37     502K   New IMPULSE
08:34   $16.88     979K   PULLBACK 1/3 (but price at $17.04)
08:35   $17.20     483K   PULLBACK 2/3
08:36   $17.04     352K   PULLBACK 3/3 → QUALITY GATE FAIL
08:37   $17.38     515K   NO_ARM — gate blocked
08:39   $15.90     481K   Pullback to $15.15
08:40   $17.51     410K   IMPULSE → PULLBACK 1/3
08:42   $16.93     245K   RESET (MACD bearish cross)
08:43   $16.10     275K   Consolidation begins
08:47   $15.13     144K   Drift lower
09:00   $17.22     152K   Bounce attempt
09:15   $15.34     301K   Failed push
09:30   $16.10     935K   Market open — volatile
09:33   $14.65     348K   Sharp selloff
09:51   $12.86     758K   Day low area ($12.33)
10:05   $14.43     237K   Recovery starts
10:34   $15.37     363K   Push through $15
11:27   $17.63     445K   Late breakout leg
11:28   $18.63     772K   Push toward HOD retest
11:39   $19.34   1,025K   Push past $20 (would be filtered from here)
```

---

## D. Detector + Gate Analysis

### State Machine Log (Pullback Mode, Gates ON)

| Time | Event | Detail |
|------|-------|--------|
| 08:30 | IMPULSE | Bar: O=$12.92 H=$13.88 C=$13.68 — first sim bar |
| 08:31 | RESET | Bearish engulfing (H=$14.00 → C=$12.57) |
| 08:32 | IMPULSE | Bar: C=$13.37 — green recovery |
| 08:34 | PULLBACK 1/3 | Price pulling back from $17.90 high |
| 08:35 | PULLBACK 2/3 | Continued pullback |
| 08:36 | PULLBACK 3/3 | Ready to ARM... |
| **08:37** | **NO_ARM** | **Quality gate FAILED** |
| 08:40 | IMPULSE | New cycle attempt |
| 08:41 | PULLBACK 1/3 | |
| 08:42 | RESET | MACD bearish cross |
| 08:43 | RESET | Topping wicky |
| 08:44 | RESET | Topping wicky |
| *2+ hour gap* | *No impulses detected* | *Price consolidating $13-$17* |
| 10:50 | IMPULSE | Late recovery attempt |
| 10:51 | RESET | Topping wicky |
| 11:21 | IMPULSE | Final push attempt |
| 11:22 | PULLBACK 1/3 | |
| 11:23 | RESET | Topping wicky |
| 11:24-11:29 | Multiple IMPULSE/RESET | Extended green candles, weak triggers |
| 11:40 | IMPULSE | |
| 11:41-11:43 | PULLBACK 1-3/3 | Full pullback completed... |
| 11:44 | RESET | Pullback too long |

### Gate Check Detail (08:36-08:37, the ONE setup attempt)

| Gate | Result | Detail |
|------|--------|--------|
| G0: no_reentry | PASS | losses=0/1, trades=0/10 |
| G1: clean_pullback | **FAIL** | pb_vol=121% > max_70% — pullback had MORE volume than impulse |
| G2: impulse_strength | **FAIL** | impulse_vol=1.4x < min_1.5x — impulse volume below threshold |
| G3: volume_dominance | PASS | vol_ratio=2.0x recent vs avg |
| G4: price_float | REDUCE | price=$18.40 outside $3-$15 sweet spot (0.5x size) |

**Why the gates are arguably wrong here:** ROLR's price action at this point is extremely chaotic — the stock went from $3.52 to $17+ in 18 minutes. The "impulse" and "pullback" as measured by the 1-minute detector are really just noise within a parabolic move. The high pullback volume (121% > 70% max) reflects genuine selling pressure during a wild swing, and the low impulse volume multiplier (1.4x < 1.5x min) reflects that the baseline volume was already astronomically high from the catalyst.

**But the gates are arguably right too:** The stock IS extremely volatile and the first entry attempt in direct mode at 08:31 @ $13.90 lost $646 on a bearish engulfing exit to $12.84. The consolidation range of $12-$18 in the first 15 minutes is a $6 range on a $15 stock (40%). This is not a clean setup.

---

## E. Three-Way Comparison Table

### Primary Configurations

| Mode | Trades | Entry | Exit | P&L | Notes |
|------|--------|-------|------|-----|-------|
| Pullback + Gates ON | 0 | — | — | $0 | Gate G1 (clean_pullback) and G2 (impulse_strength) blocked the only setup at 08:36 |
| Pullback + Gates OFF | 0 | — | — | $0 | Detector arms once at 08:36 but never triggers — no clean breakout |
| Direct + no_reentry ON | 1 | $13.90 @ 08:31 | $12.84 | -$646 | Bearish engulfing exit. no_reentry blocks further entries. |
| **Direct + no_reentry OFF** | **2** | **$13.90, $13.49** | **$12.84, $16.75** | **+$2,024** | **Second entry catches the $17+ push** |

### Key Insight: Direct Mode with Re-Entry

The bot's best result comes from **direct mode with re-entry allowed**:
- Trade 1: Entry $13.90 → Exit $12.84 (bearish engulfing) = **-$646**
- Trade 2: Entry $13.49 @ 08:33 → Exit $16.75 (bearish engulfing) = **+$2,670**
- Net: **+$2,024**

This is ~2.4% of Ross's $86,000, which is realistic given:
- Ross uses $200K+ buying power vs our $10K max notional
- Ross scales in/out (partials) vs our all-or-nothing
- Ross has 20+ years pattern recognition vs our rule-based detector

---

## F. Key Findings

### 1. Did the scanner fix successfully catch ROLR?
**YES.** ROLR detected at the 08:30 checkpoint at $13.68 (+288.6% gap). Profile A (3.6M float). The continuous scan working exactly as designed.

### 2. At what time/price was ROLR discoverable?
- At 08:00: NOT detectable (gap only 3.7%)
- At **08:30**: Detectable at **$13.68** (gap 288.6%, price under $20)
- At 08:34: Price hits $20.84 — would be FILTERED OUT at next checkpoint
- **Window to catch ROLR: exactly the 08:30 checkpoint.** Any earlier = no gap, any later = above $20.

### 3. Did the bot trade ROLR once it was on the watchlist?
**Pullback mode: NO** — the detector couldn't find a clean impulse→pullback→breakout in the parabolic move. The one setup attempt was blocked by quality gates (high pullback volume, low relative impulse volume).

**Direct mode: YES** — took 1-2 trades depending on no_reentry setting.

### 4. What's the bottleneck?
**The detector itself.** Even with gates OFF, pullback mode armed once but never triggered. The stock's price action is too chaotic for clean micro-pullback detection:
- Immediate bearish engulfing after impulses
- MACD bearish crosses during pullbacks
- Topping wicky resets cutting off setups
- 2+ hour gap (08:44 → 10:50) with no impulses detected despite $4+ range

The fundamental issue: **ROLR's move is a news-driven parabolic spike, not a technical breakout.** The micro-pullback detector is designed for orderly gap-up → consolidation → breakout patterns. ROLR went from $3.52 to $20+ in 16 minutes — there's no "consolidation" to detect.

### 5. How much of the $86K move could the bot realistically have captured?
- **Pullback mode: $0** — detector can't handle parabolic moves
- **Direct mode (with re-entry): +$2,024** — catches a $3.26 move on 2 trades
- **Theoretical max with $10K notional at $13.68 entry** (~730 shares): If held to $20, that's ~$4,600. If held to $33.68 peak, ~$14,600. But no realistic exit strategy would capture the full move.

### Additional Discovery: `fetch_prev_close()` Bug

The scanner had a latent bug where daily bars could include the current trading day's close. For ROLR on Jan 14, `prev_close` was returning $18.89 (Jan 14 close) instead of $3.52 (Jan 13 close). This caused the gap calculation to be negative, hiding ROLR even if the re-scan would have found it. **Fixed by filtering daily bars to dates strictly before the target date.**

---

## G. Recommendations

1. **Scanner fix is solid.** The continuous re-scan with 6 checkpoints covers the 7:15 AM → 10:30 AM window. ROLR caught at the exact right moment ($13.68, still under $20).

2. **The micro-pullback detector is not designed for parabolic moves.** This is by design — parabolic moves are extremely high risk. The detector's resets (bearish engulfing, topping wicky, MACD cross) are PROTECTING the bot from the wild $6 swings between $12 and $18.

3. **Direct mode with re-entry shows the ceiling.** +$2,024 is achievable but requires accepting an initial -$646 loss and re-entering. The no_reentry gate (which blocks after 1 loss) is the specific gate that prevents this.

4. **Phase 3 recommendation:** Re-run the 15-date expanded backtest with the scanner fix to see how many new candidates are found and whether overall P&L improves. The ROLR case study confirms the scanner fix works for the exact scenario it was designed for.

---

*Generated 2026-03-12 | Scanner: continuous re-scan v1 | Sim: tick mode, Alpaca feed*
