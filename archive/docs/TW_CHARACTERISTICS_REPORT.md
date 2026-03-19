# TW Exit Characteristics — Follow-Up Report
## Generated: 2026-03-18

Detailed characteristics for all 7 topping wicky exits to identify what separates TW-helped from TW-hurt trades.

---

## Table A: Full Characteristics

| # | Symbol | TW Helped? | Float (M) | Gap% | Score | Price ($) | R ($) | R% of Price | Min Held | R at TW Exit | TW Suppressions | Cont Hold Active? |
|---|--------|-----------|-----------|------|-------|-----------|-------|-------------|----------|-------------|-----------------|-------------------|
| 1 | VERO | **NO** | 1.6 | -9.1% | 11.1 | 3.58 | 0.12 | 3.4% | **~3** | **+9.2R** | 0 | No |
| 2 | ROLR | **NO** | 4.6 | -6.0% | 11.0 | 9.33 | 1.10 | 11.8% | **~3** | **+3.2R** | 6 | Yes (held through) |
| 3 | BMNZ | **NO** | N/A | +13.4% | 10.1 | 16.99 | 0.19 | 1.1% | **~3** | +0.2R | 0 | No |
| 4 | AGPU | YES | 1.8 | -10.2% | 11.0 | 8.32 | 0.30 | 3.6% | **~3** | +1.1R | 0 | No |
| 5 | TLYS | YES | 9.2 | +21.1% | 12.0 | 2.72 | 0.13 | 4.8% | **~3** | +0.1R | 7 | Yes (failed) |
| 6 | BIAF | YES | 4.3 | -12.8% | 12.5 | 2.85 | 0.24 | 8.4% | **~3** | -0.1R | 7 | Yes (failed) |
| 7 | LUNL | YES | 0.17 | -4.4% | 14.0 | 13.00 | 0.28 | 2.2% | **~36** | +0.5R | 0 | No |

---

## Table B: Group Comparison — TW Hurt vs TW Helped

| Characteristic | TW Hurt (avg) | TW Helped (avg) | Difference | Notable? |
|----------------|---------------|-----------------|------------|----------|
| **Float (M)** | 3.1 (VERO 1.6, ROLR 4.6, BMNZ N/A) | 3.8 (AGPU 1.8, TLYS 9.2, BIAF 4.3, LUNL 0.17) | -0.7 | No clear pattern |
| **Gap %** | -0.6% (-9.1, -6.0, +13.4) | -1.6% (-10.2, +21.1, -12.8, -4.4) | +1.0% | No |
| **Score** | 10.7 (11.1, 11.0, 10.1) | 12.4 (11.0, 12.0, 12.5, 14.0) | -1.7 | Slight — helped group has higher scores |
| **Entry Price ($)** | $9.97 (3.58, 9.33, 16.99) | $6.72 (8.32, 2.72, 2.85, 13.00) | +$3.25 | No |
| **R ($)** | $0.47 (0.12, 1.10, 0.19) | $0.24 (0.30, 0.13, 0.24, 0.28) | +$0.23 | No |
| **R as % of Price** | 5.4% (3.4, 11.8, 1.1) | 4.8% (3.6, 4.8, 8.4, 2.2) | +0.6% | No |
| **Minutes Held** | **~3 min** (all three) | **~11 min** (3, 3, 3, 36) | -8 min | LUNL is the outlier |
| **R-mult at TW Exit** | **+4.2R** (9.2, 3.2, 0.2) | **+0.4R** (1.1, 0.1, -0.1, 0.5) | **+3.8R** | **YES — KEY FINDING** |
| **TW Suppressions** | 2.0 (0, 6, 0) | 3.5 (0, 7, 7, 0) | -1.5 | No |
| **Cont Hold Active?** | 1 of 3 | 2 of 4 | — | No |

---

## Table C: Timing Breakdown

| Timing Bucket | Count | TW Helped | TW Hurt | Avg Delta |
|---------------|-------|-----------|---------|-----------|
| **Min 3 (grace expiry)** | **6** | 3 | 3 | -$1,574 |
| Min 5-10 | 0 | 0 | 0 | — |
| Min 10-30 | 0 | 0 | 0 | — |
| Min 30+ | 1 | 1 (LUNL) | 0 | +$1,750 |

**6 of 7 TW exits fired at exactly minute 3** — the grace period expiry (`WB_TOPPING_WICKY_GRACE_MIN=3`). The only exception is LUNL which held 36 minutes. This means TW is essentially a "3-minute timeout exit" rather than a genuine topping pattern detector.

---

## The Key Finding: R-Multiple at Exit Separates Winners from Losers

The single clearest differentiator between TW-hurt and TW-helped trades:

| Group | Avg R-Mult at TW Exit | Trades |
|-------|----------------------|--------|
| **TW Hurt** (left money on table) | **+4.2R** | VERO +9.2R, ROLR +3.2R, BMNZ +0.2R |
| **TW Helped** (saved money) | **+0.4R** | AGPU +1.1R, TLYS +0.1R, BIAF -0.1R, LUNL +0.5R |

When TW fires on a trade that's deep in profit (>1R), it's usually wrong — the stock is running and TW cuts the move short. When TW fires on a trade that's barely profitable or underwater (<1R), it's usually right — the stock is struggling and TW gets out before a worse exit.

**The exceptions:**
- BMNZ (+0.2R, TW hurt): Low R-mult but TW still cost $206. Would have been +0.6R via BE.
- AGPU (+1.1R, TW helped): Higher R-mult but TW correctly exited — stock dropped to BE exit at +0.5R.

---

## Detailed TW Signal Flow

### TW Hurt Trades — What Happened After

**VERO** (TW at +9.2R, cost $9,417):
- Entry 07:14 at $3.58 → TW exit 07:17 at $4.68 (+$1.10, +9.2R)
- Without TW: BE exit would have fired at ~$7.76 (+$4.18, +18.6R)
- Stock ran from $4.68 to $7.76+ before reversing
- TW fired at minute 3 with zero suppressions — immediate grace expiry

**ROLR** (TW at +3.2R, cost $3,202):
- Entry 08:26 at $9.33 → TW exit 08:29 at $12.90 (+$3.57, +3.2R)
- 6 TW suppressions by continuation hold (vol_dom=3.6x) at prices $11.95-$12.90
- Cont hold let it ride from ~$12.06 to $12.90 but then TW finally fired
- Without TW: BE exit at ~$16.37 (+$7.04, +6.4R)
- Cont hold saved +$0.84 worth of ride but TW still cut $3,202 short

**BMNZ** (TW at +0.2R, cost $206):
- Entry 08:45 at $16.99 → TW exit 08:48 at $17.03 (+$0.04, +0.2R)
- Without TW: BE exit at $17.10 (+$0.11, +0.6R)
- Small difference but TW still exited prematurely

### TW Helped Trades — What Would Have Happened

**LUNL** (TW at +0.5R, saved $1,750):
- Entry 09:59 at $13.00 → TW exit 10:35 at $13.13 (+$0.13, +0.5R)
- Without TW: stock crashed to stop_hit at $12.72 → -$1,286
- TW held for 36 minutes (not at grace expiry!) — genuine pattern detection
- The only TW that fired AFTER the grace window

**AGPU** (TW at +1.1R, saved $567):
- Entry 07:16 at $8.32 → TW exit 07:19 at $8.65 (+$0.33, +1.1R)
- Without TW: BE exit at $8.48 (+$0.16, +0.5R)
- Stock peaked at $8.65 then faded — TW caught the top

**TLYS** (TW at +0.1R, saved $462):
- Entry 07:03 at $2.72 → TW exit 07:06 at $2.73 (+$0.01, +0.1R)
- 7 TW suppressions (cont hold vol_dom=4.0x), but stock couldn't sustain
- Without TW: BE exit at $2.67 (-$0.05, -0.4R) — much worse
- TW got out before the stock rolled over

**BIAF** (TW at -0.1R, saved $352):
- Entry 09:50 at $2.85 → TW exit 09:53 at $2.83 (-$0.02, -0.1R)
- 7 TW suppressions (cont hold vol_dom=3.3x), wild oscillation $2.74-$3.01
- Without TW: BE exit at $2.75 (-$0.10, -0.4R) — stock crashed further
- TW limited the loss

---

## Conclusions

### 1. TW is essentially a "3-minute timer" — not a pattern detector
6 of 7 exits happened at exactly minute 3 (grace expiry). The one genuine pattern exit (LUNL at 36 min) was the most valuable save (+$1,750). The grace period is too short — TW fires before the setup has time to develop.

### 2. R-multiple at exit is the key discriminator
- TW exits at **>1R profit: usually wrong** (VERO, ROLR — stocks are running, let them run)
- TW exits at **<1R profit: usually right** (TLYS, BIAF, LUNL — stocks are struggling, get out)
- **Proposed gate: suppress TW when unrealized > 1.5R**

### 3. The biggest money is in NOT firing TW on runners
VERO alone: +$9,166 actual vs +$18,583 without TW. That's $9,417 left on the table from a single TW exit. ROLR adds another $3,202. Combined: **$12,619 left on the table on just 2 trades.**

### 4. Extending the grace period would help but not enough
If grace were 10 minutes instead of 3, VERO would still have TW fire at ~10min and miss the $18K exit. The fix needs to be profit-aware, not time-aware.

### 5. Continuation hold partially works but can't save runners
ROLR's cont hold suppressed 6 TW signals and squeezed out extra profit ($12.06 → $12.90). But it still ultimately let TW fire. Without TW entirely, ROLR would have reached $16.37 via BE.
