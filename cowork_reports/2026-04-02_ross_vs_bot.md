# Ross vs Bot — April 2, 2026

**Ross P&L:** -$57,000 | **Bot P&L:** $0 | **Bot edge:** +$57,000

---

## Market Context

Cold day. One stock dominated: **SKYQ**, an energy name trading as a derivative of USO (oil). SKYQ had a clean parabolic move from ~$3.00 to $4.39 between 7:00-7:38 AM (11 consecutive green 1m candles), then spent the rest of the session producing false breakouts on the backside as USO peaked at 9:00 AM and rolled over.

Ross's biggest single-day loss of 2026. Wiped out +$57K earned the prior Thursday/Friday.

---

## What the Bot Saw

| Stock | Activity | Result |
|-------|----------|--------|
| **SKYQ** | 128.6x volume explosion at 07:38. Bot was NOT subscribed — scanner-move paradox. Discovered ~07:50, move already done. | No entry possible |
| **BATL** | SQ_PRIMED at 07:10 (3.3x vol), RESET after 3 bars — price needed $0.22 more to break PM high | No trade |
| **TURB** | SQ_PRIMED at 09:40 (6.4x vol), never ARMED — $4.00 whole dollar was +9% away | No trade |
| **KIDZ** | Dead tape, 0-22 ticks/min | No trade |

**Bot result: 0 trades, $0 P&L.** Confirmed by backtest — correct outcome from actual discovery times.

---

## What Ross Did on SKYQ

### The Clean Move He Skipped (7:00-7:38)
SKYQ popped toward $3.00, pulled back, curled up to $3.15-$3.17. Ross checked the daily chart — 200 MA overhead at $4.17, felt the reward wasn't worth the risk. Passed.

Stock then produced 11 consecutive green 1m candles to $4.39 without him. This was the only clean trade of the day.

### The Backside Trades (7:38-9:00+)

| # | Entry | Size | Setup | Result | Running P&L |
|---|-------|------|-------|--------|-------------|
| 1 | ~$4.23-4.28 | 30K shares | First 1m new high after run to $4.39 | +$1,200 (~4¢/share) | +$1,200 |
| 2 | ~$4.85 avg | 60K shares (30K + 30K add) | First 1m new high, targeting $5.00 squeeze | +$1,500 (hit $5.01, flushed) | +$2,700 |
| 3 | $5.50 → add at $6.25 | 30K → 70K shares | Squeeze to $6.00, added for continuation | -$14K swing (+$6K to -$8K) | -$8,000 |
| 4 | $5.80 | ~30K shares | Base at $5.75, first new high | -$6,000 (false breakout) | -$14,000 |
| 5 | ~$5.75 | ~30K shares | Curl back to $6.00 | +$5,000 | -$9,000 |
| 6 | $6.50 | **75K shares** | Full size for rip to $7.00 | **-$47,000** (USO peaked at 9:00, SKYQ tanked) | **-$57,000** |

### Why Ross Lost

Three compounding factors:

1. **Backside trading.** Every trade after Trade 1 was on the backside of an extended move. The "first 1m candle to make a new high" pattern — Ross's bread-and-butter — kept failing because the stock was already extended 46%+ from the morning base.

2. **Derivative risk.** SKYQ trades as an oil proxy. USO peaked at exactly 9:00 AM and dropped. Trade 6 at $6.50 with 75K shares was perfectly timed to catch the oil reversal. Ross knew about the correlation but traded through it.

3. **Psychological spiral.** Missed the clean early move → frustration → sized up from 30K to 60K to 70K to 75K shares while already red $10K. He admits he "snapped" and crossed his emotional control line. Added full size at $6.50 because he "didn't want to jump off and then watch it rip" — revenge psychology.

---

## Structural Takeaways for the Bot

### 1. Scanner-Move Paradox Was Protective Today
The bot couldn't trade SKYQ because the volume spike that created the opportunity was the same spike that triggered scanner discovery. By 07:50, the clean move was over. Any trade after that was backside — exactly where Ross lost $57K.

**Key insight from Manny:** The first move is the catalyst that gets us looking at the stock. Ross says in his book that he only cares about the moves that come AFTER that. The scanner discovering SKYQ late and not finding a setup is correct behavior — there was no clean setup to find.

CC ran the backtest on SKYQ from 7:00 AM (as if the bot had been watching from the start). Result: **$36 total P&L.** Even with perfect timing, the bot correctly identified that the post-initial-move setups were garbage. The scanner timing didn't matter.

### 2. The Bot's Lack of Emotion Is Worth $57K Today
Ross sized up because he was frustrated. The bot can't be frustrated. It can't revenge trade. It can't add 75K shares at $6.50 because it "just needs one good setup." On days like this, mechanical discipline is the entire edge.

### 3. "First 1m New High" Fails on Extended Backside
Ross's primary entry signal — the exact pattern we're building into the V2 exit system — failed 4 out of 6 times on SKYQ. All failures were on the backside of an already-extended move. The pattern works on fresh breakouts, not on stocks that have already run 46%+ and are curling back up for another attempt.

This has implications for entry quality scoring: a "first 1m new high" at 7:05 AM on a fresh breakout is a fundamentally different trade than a "first 1m new high" at 8:30 AM after the stock has already run from $3.00 to $5.40 and pulled back.

### 4. Derivative/Correlation Risk Is Invisible
SKYQ tanked because oil tanked, not because of anything on SKYQ's own chart. The bot has no concept of sector correlation. However, the bot's mechanical stops (max_loss, hard stop) would have limited any single-trade loss far below $47K. The bot can't hold through a $47K drawdown because it "doesn't want to miss the rip" — it just stops out.

### 5. Scanner Status: Leave As-Is
The scanner-move paradox is a known limitation but today's data confirms it's not the priority. The first move is the catalyst; money is made on the subsequent setups. The bot already does this correctly — it discovers the stock via the initial spike, then looks for squeeze setups in the price action that follows. When no setup exists (SKYQ today), it correctly sits out.

---

## Performance Context

| Metric | Value |
|--------|-------|
| Bot April 2 | $0 (0 trades) |
| Ross April 2 | -$57,000 (6 trades on SKYQ) |
| Bot edge today | +$57,000 |
| Ross YTD (before today) | ~$800K (funded $100K) |
| Ross post-today | ~$743K |
| Ross recovery plan | Max 20K shares next week, size down until half the loss is recovered |

---

*Generated: April 2, 2026 | Cowork (Opus)*
