# CJMB Jan 15 Mechanics Forensic
**Date**: 2026-03-24

---

## Executive Summary

CJMB's -$1,028 disappearance has **two causes, not one**:

1. **Primary (why it never ran)**: The batch runner's consecutive-loss gate. SPHL (rank 2) produced 2 consecutive losers before CJMB (rank 4) got a turn. `MAX_CONSEC_LOSSES=2` triggered and the daily loop broke. CJMB's simulation was never even started.

2. **Secondary (why it ranked lower)**: The cumulative window change discovered CJMB 15 minutes earlier (08:45 vs 09:00) with worse metrics — gap 85.7% vs 126.8%, volume 0.4M vs 16.6M — dropping its rank score from 1.122 (#1) to 0.679 (#4). New scanner stocks (AUID, BNKK) further displaced it.

The live bot would **not** have this problem because it runs all stocks in parallel with no execution ordering.

---

## The Two Scenarios Side-by-Side

### OLD Run (commit aef59a1)

**Scanner**: CJMB discovered at 09:00, gap=126.8%, pm_vol=16.6M, **rank #1**

**Execution order**: CJMB → SPHL → CHNR → AGPU → NUWE

| Step | Stock | Result | consec_losses |
|------|-------|--------|---------------|
| 1 | CJMB | +$1,028 (sq_target_hit) | 0 |
| 2 | SPHL | -$132 (sq_para_trail_exit) | 1 |
| — | *stopped* | *(SPHL trade 2 would be loss → consec=2 → break)* | — |

**Day total**: +$896, 2 trades

### NEW Run (current)

**Scanner**: CJMB discovered at 08:45, gap=85.7%, pm_vol=0.4M, **rank #4**

**Execution order**: AUID → SPHL → BNKK → CJMB → AGPU

| Step | Stock | Result | consec_losses |
|------|-------|--------|---------------|
| 1 | AUID | 0 trades | 0 |
| 2 | SPHL trade 1 | -$135 (sq_para_trail_exit) | 1 |
| 3 | SPHL trade 2 | -$184 (bearish_engulfing) | **2 → BREAK** |
| — | BNKK | **NEVER RAN** | — |
| — | CJMB | **NEVER RAN** | — |
| — | AGPU | **NEVER RAN** | — |

**Day total**: -$319, 2 trades

---

## Why CJMB Ranked Lower

| Metric | Old Scanner | New Scanner | Cause |
|--------|-------------|-------------|-------|
| Discovery time | 09:00 | 08:45 | Cumulative window finds it earlier |
| Gap % | 126.8% | 85.7% | At 08:45 the move is incomplete |
| PM Volume | 16.6M | 0.4M | Most volume came after 08:45 |
| Rank Score | 1.122 | 0.679 | Driven by volume (30% weight) |
| Rank | **#1** | **#4** | Plus AUID/BNKK are new entrants |

The cumulative window change means the scanner evaluates CJMB at the 08:45 checkpoint using bars from 4AM→08:45. At that point CJMB had only started moving — the real catalyst volume (16M+) came after 09:00. The old scanner's 5-minute incremental window at 09:00 (08:55→09:00) happened to capture the peak of the catalyst.

---

## Detector Mechanics: What Would Happen IF CJMB Ran at 08:45

Even though the batch runner never ran CJMB, understanding the detector behavior at different sim_starts reveals a structural issue.

### sim_start=09:00 (old, actual: +$1,028)

**Seed phase**: 18 bars (4AM→09:00) build session HOD to **$4.64** (premarket high).

**Sim phase**: The HOD gate (`new_hod_required`) blocks every volume bar from 09:00→11:25 because no bar's high exceeds the $4.64 seed HOD:

```
09:32  vol=3.8x ✓ but bar_high $3.41 < HOD $4.64 → REJECT
09:38  vol=5.2x ✓ but bar_high $3.82 < HOD $4.64 → REJECT
09:43  vol=3.2x ✓ but bar_high $4.21 < HOD $4.64 → REJECT
10:59  vol=3.2x ✓ but bar_high $3.96 < HOD $4.64 → REJECT
... (every green high-volume bar rejected for 2 hours)
11:26  vol=4.8x ✓ bar_high $4.83 > HOD $4.64 → PRIMED → PM HIGH BREAK → ARMED
       Entry $4.66, stop $4.54, R=$0.12 [PARABOLIC]
       → TRIGGER → +$1,028
```

The HOD gate acts as a **quality filter**: by forcing the detector to wait for a true new high, it skips the mid-day chop and only catches the genuine breakout above the premarket high.

### sim_start=08:45 (new, hypothetical)

**Seed phase**: 3 bars (4AM→08:45) build session HOD to only **$2.30**.

**Sim phase**: The low seed HOD means the first bar immediately qualifies:

```
08:45  vol=906x (!!!) bar_high $2.30 = HOD $2.30 → PRIMED → $2 whole dollar → ARMED
       Entry $2.02, stop $1.90, R=$0.12
       → TRIGGER at 08:46 → Target $2.26 hit at 08:47 → WIN (+$0.24/share)
       [attempt 1/3]

08:48  vol=4.5x bar_high $4.64 = NEW HOD → PRIMED → $3 whole dollar → ARMED
       Entry $3.02, stop $2.90, R=$0.12
       → TRIGGER at 08:49 → Target $3.26 hit at 08:50 → WIN (+$0.24/share)
       [attempt 2/3]

(bars 08:50-10:29: avg vol is now massive → no bar hits 3x threshold)

10:30  vol=4.8x → PRIMED → $5 whole dollar → ARMED
       → TRIGGER at 11:29 → Target $5.26 hit at 11:30 → WIN (+$0.24/share)
       [attempt 3/3 — exhausted]
```

Three small wins ($0.24/share each) vs one big win at $4.66. With probe sizing at 50%, the total P&L from the 08:45 scenario would be roughly **+$180-250** vs **+$1,028**.

### The Mechanism: Seed HOD Controls Selectivity

```
MORE seed bars → HIGHER seed HOD → MORE selective detector → WAITS for real breakout → BIG WIN
FEWER seed bars → LOWER seed HOD → LESS selective → CATCHES early noise → SMALL WINS
```

The HOD gate is calibrated by whatever the seed phase produces. With 18 seed bars up to 09:00, the seed includes the full premarket high ($4.64), and the detector can't fire until that level breaks. With 3 seed bars to 08:45, the seed only reaches $2.30, so every subsequent new high triggers the detector on progressively higher whole-dollar levels — burning through attempts on small moves before the real breakout.

---

## Live Bot Implications

### The consecutive-loss gate is a batch runner artifact

The live bot runs all top-N stocks **simultaneously via websocket subscriptions**. There's no sequential execution, no consecutive-loss ordering dependency. CJMB would have run regardless of SPHL's outcomes.

However, the **detector timing issue is real for the live bot**:

- The live bot subscribes to a stock as soon as the scanner finds it
- `sim_start` = the time the bot starts receiving data
- Seed bars = bars fetched historically from 4AM to subscription time
- If the live scanner discovers CJMB at 08:45 (like the new scanner), the live bot gets the same 3-seed-bar scenario with low HOD
- The detector would fire on the $2 break instead of waiting for the $4.64 PM high break

**The live bot would catch CJMB (no ranking gate blocks it), but it would produce a ~$250 trade instead of a $1,028 trade.** Still profitable, but 75% less.

### Broader concern

Any stock discovered in premarket before its main move will have a low seed HOD, causing the detector to fire prematurely on small whole-dollar breaks. This is **inherent to the squeeze detector's HOD gate design** — it's not a bug, it's a tradeoff:

- **Late discovery**: sees full premarket → high HOD → waits for big break → fewer but larger trades
- **Early discovery**: minimal premarket → low HOD → catches small breaks → more but smaller trades

The live scanner's 1-minute updates mean it discovers stocks early. This favors the "many small trades" mode rather than the "one big trade" mode that produced CJMB's +$1,028.

---

## Recommendations

### 1. Remove MAX_CONSEC_LOSSES from batch runner (or raise to 4)
This gate has no equivalent in the live bot and creates artificial execution-order dependencies. On Jan 15, it cost $1,028 purely because SPHL happened to rank higher than CJMB. The gate exists to prevent runaway losses, but `DAILY_LOSS_LIMIT=-$1,500` already handles that.

### 2. Consider seeding PM high from bar_builder (not from HOD)
The detector already receives `premarket_high` via `update_premarket_levels()`. The HOD gate could check against the known PM high rather than the running session HOD from seed bars. This would make the detector's behavior consistent regardless of when it starts watching:
- `if bar_high < premarket_high: reject` (instead of `if bar_high < session_hod: reject`)
- Would produce the same PM high break at $4.64 whether discovered at 08:45 or 09:00

### 3. Dynamic ranking still matters (but for different reasons)
The cumulative window's earlier discovery snapshot (gap 85.7% vs 126.8%) is an accuracy issue. CJMB's "real" gap at 09:00 was 126.8% — the 08:45 snapshot is a stale undercount. If rankings updated at each checkpoint with the latest data, CJMB would score higher as volume accumulated.
