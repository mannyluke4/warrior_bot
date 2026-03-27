# Directive: Backtest Today's Session — 2026-03-20

## Priority: URGENT — Manny wants results before Ross recap video drops
## Owner: CC

---

## Task

Run the full scan + backtest for today (2026-03-20) so we can compare our bot's potential
trades against Ross Cameron's actual trades when his recap comes out.

The live bot crashed at startup and missed the entire morning. We need to know what we
WOULD have caught.

## Step 1: Scan today

```bash
cd ~/warrior_bot
source venv/bin/activate
python scanner_sim.py --date 2026-03-20
```

Check the output in `scanner_results/2026-03-20.json` — list all candidates.

## Step 2: Backtest each candidate that passes filters

For each stock that passes the scanner filter (gap >= 10%, PM vol >= 50K, float <= 10M,
RVOL >= 2.0), run:

```bash
# Squeeze V2 + MP (full config):
WB_CLASSIFIER_ENABLED=1 WB_CLASSIFIER_RECLASS_ENABLED=1 WB_EXHAUSTION_ENABLED=1 \
WB_WARMUP_BARS=5 WB_CONTINUATION_HOLD_ENABLED=1 WB_CONT_HOLD_5M_TREND_GUARD=1 \
WB_MAX_NOTIONAL=50000 WB_MAX_LOSS_R=0.75 WB_NO_REENTRY_ENABLED=1 \
WB_TW_MIN_PROFIT_R=1.5 WB_MAX_LOSS_R_TIERED=1 WB_MAX_LOSS_TRIGGERS_COOLDOWN=1 \
WB_CONT_HOLD_DIRECTION_CHECK=1 WB_SQUEEZE_ENABLED=1 WB_SQ_PARA_ENABLED=1 \
WB_SQ_NEW_HOD_REQUIRED=1 WB_SQ_MAX_LOSS_DOLLARS=500 \
python simulate.py SYMBOL 2026-03-20 07:00 12:00 --ticks -v \
2>&1 | tee verbose_logs/SYMBOL_2026-03-20_full.log
```

Replace SYMBOL with each passing stock.

**IMPORTANT**: Use `sim_start` from the scanner results for each stock (respect discovery time).
If a stock was discovered at 08:00, sim from 08:00 not 07:00.
But ALSO run from 07:00 to check if earlier discovery would have helped.

## Step 3: Write recap

Save to `cowork_reports/2026-03-20_backtest.md` with:
- Scanner results (all candidates, which passed, which didn't)
- Trade table for each stock (entry, exit, reason, P&L)
- Total P&L across all stocks
- Which strategy fired (MP vs squeeze) for each trade
- Key observations (what worked, what didn't)

## Step 4: Push results

```bash
git add scanner_results/2026-03-20.* verbose_logs/*2026-03-20* cowork_reports/2026-03-20*
git commit -m "Backtest 2026-03-20: scan + sim for Ross comparison

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
git push origin v6-dynamic-sizing
```

---

*Directive created by Cowork — 2026-03-20*
