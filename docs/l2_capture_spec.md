# L2 Production Capture Spec — Wave 6 Enabler

**Date:** 2026-05-16
**Author:** CC (Wave 5 Agent N)
**For:** Cowork (Perplexity), Wave 6 implementor
**Per:** `DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md` §5 Agent N

---

## Problem

Wave 5 Agent N built a 3-mode L2 confirmation plugin
(`framework/confirmations/l2_confirm.py`) but had to validate it with
**synthetic L2** derived from candle wicks — Databento Standard does not
include L2 history. Real edge validation is queued for Wave 6 once we
capture live L2 events ourselves. This document specifies exactly what
must be captured.

## Capture source

`l2_helper.py` (production live code, untouched) already opens IBKR L2
streams via `ib_insync` with the post-Saturday hotfix:

```python
ib.reqMktDepth(contract, numRows=10, isSmartDepth=False)
```

- `numRows=10` — top 10 levels each side
- `isSmartDepth=False` — **mandatory** per the 2026-05-17
  `2026-05-16_l2_async_refactor.md` fix. Smart-depth caused
  `IndexError` flood (multiple MMs at same level overflow the fixed
  10-slot `dom[]` list)
- Per-process `clientId` 42/43/44/45 to avoid IBKR session collision

Each `ib_insync.ticker.domBids[i]` / `domAsks[i]` event has fields:
`position` (level 0-9), `marketMaker` (exchange string), `price`,
`size`. Updates fire on every change.

## Schema (parquet)

Path: `l2_cache/<SYMBOL>/<YYYY-MM-DD>.parquet`

| Column | Type | Notes |
|---|---|---|
| `ts_event` | timestamp[ns, tz=UTC] | event time from IBKR (ns precision) |
| `symbol` | string | trading symbol |
| `side` | category | `bid` or `ask` |
| `level` | int8 | book level 0-9 (0 = top-of-book) |
| `market_maker` | string | exchange/MM string |
| `price` | float64 | quote price |
| `size` | int64 | shares quoted at level |
| `operation` | category | `insert` / `update` / `delete` |
| `book_id` | string | optional aggregation key (per-(symbol, ts) snapshot id) |

Partition by `(symbol, date)` for fast point reads. Compress with snappy.

## Sampling

**Decision: capture every event.**

Rationale:
- For a single symbol, IBKR L2 fires 5-50 events per second during RTH.
  Even at 50/s × 23,400 RTH-seconds = ~1.2M rows/day. At ~50 bytes/row
  parquet compressed, ~60MB/symbol/day. For the 36-symbol shortlist,
  ~2GB/day. Manageable on local disk.
- Snapshot-only sampling loses the inter-event ordering required for
  the `momentum_vacuum` mode (it needs to know when opposite-side
  size dropped, not just current state).
- Disk is cheaper than re-running the backtest with wrong data.

Periodic snapshots are a fallback if event-stream capture proves
infeasible (e.g. IBKR rate limit). Snapshot cadence: 1s, derived by
rolling-up events into the current top-10 state at each second
boundary. Loses some momentum-vacuum signal; preserves
depth_imbalance and stacked_bids/asks.

## Backtest reader (Wave 6)

```python
# framework/data_adapters/l2_replay.py  (Wave 6 build)
def stream_l2(symbol: str, date: date) -> Iterator[dict]:
    """Yield synthetic state dicts matching synth_l2_state() shape."""
    df = pd.read_parquet(f"l2_cache/{symbol}/{date.isoformat()}.parquet")
    # ... event-by-event walk, build top-N state, yield dict
```

The L2Confirm plugin consumes the same shape (`bids`/`asks` tuples +
`timestamp` + `history`) regardless of source — synthetic vs real. So
**no plugin code changes** once the real-data adapter is in place.

## Storage budget

| Universe | Days | Disk |
|---|---|---|
| 36 symbols, 1 month live | 21 | ~40 GB |
| 36 symbols, 1 year backfill (if IBKR provides hist via tick replay) | 252 | ~500 GB |
| 100 symbols, 6 months live | 126 | ~750 GB |

IBKR does not provide L2 history — only live. Wave 6 will capture
forward from go-live; **synthetic-L2 backtest remains the only
historical evidence until real L2 accumulates over 6+ weeks**.

## Catalysts that justify scaling capture

The plugin's three modes have different cost / value tradeoffs:

- `depth_imbalance` — needs top-10 snapshot only, low storage burden,
  Wave-5 synthetic harness already validated directional behavior.
- `stacked_bids/asks` — needs top-10 snapshot, identical burden.
- `momentum_vacuum` — needs event-stream resolution. **5-second window
  requires per-event timestamps; periodic snapshots lose this.**

If storage becomes a constraint, capture events for top-3 levels only
(95% of imbalance/stacking signal lives in top-3) and accept some loss
on momentum_vacuum precision.

## Validation pipeline

Once live L2 has accumulated for 30 trading days:

1. Re-run `backtest/pdh_fade_l2_backtest.py` with `--source real`
   pointing at `l2_cache/`.
2. Compare real-L2 trade-count reduction vs synthetic baseline.
   Expected: synthetic over-filters at the 1.5 threshold (~70%
   reduction); real L2 should be more selective (15-40% per the
   directive's gate).
3. Compute Sharpe delta. Synthetic showed +14% Sharpe at imbalance=1.2.
   Real L2 hypothesis: +20-40% Sharpe given tighter signal.
4. Compare directional metadata across modes; flag the mode that
   correlates best with real PDH-Fade winners.

## Hard rules (per CLAUDE.md + L2 state clarification)

- **No isSmartDepth=True** — known `ib_insync` bug, hotfixed Saturday.
- **No L2 capture on the same clientId as live bots.** Use a dedicated
  capture-only process with clientId 50+ to avoid session collision.
- **L2 events must never block the order path.** Capture writes to a
  ring buffer; a separate flush thread persists to parquet every 60s
  or 100K rows.
- **No live deploy of the L2-enhanced PDH-Fade strategy until at least
  30 sessions of real-L2 + 60 days of paper validation.** Per the
  directive §9 hard stop, this entire wave is backtest-only.

## Wave 6 acceptance gates

When real L2 capture is online:

- ≥ 90% event capture rate (vs IBKR's own event count, sampled per session).
- ≤ 1s end-to-end latency from event to parquet flush.
- Per-symbol-per-day parquet exists every RTH session.
- PDH-Fade-L2 backtest on real data shows:
  - Trade-count reduction in **15-40%** range (per directive gate)
  - Sharpe ≥ 1.40 (no regression from synthetic baseline)
  - Same direction of effect as synthetic (positive Sharpe lift,
    DD improvement)

If any of those fails, the L2 plugin reverts to optional-rule status
in the YAML registry and the synthetic-L2 finding (no real signal)
becomes the published verdict.
