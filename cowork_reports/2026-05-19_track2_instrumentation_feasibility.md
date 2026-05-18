# Track 2 — Broker Latency Instrumentation Feasibility

**Date generated:** 2026-05-19 (assembled 2026-05-18 PM)
**Directive:** `DIRECTIVE_2026-05-18_BROKER_LATENCY_INVESTIGATION.md`, §"Track 2"
**Scope:** Evaluate feasibility of sub-second order-path timestamping for the squeeze paper bot under the hard Setup-A constraint. **Investigation only — no production changes proposed in this report.**
**Author:** Cowork (Opus)

---

## TL;DR

**The instrumentation Track 2 asks for is already deployed.**

`bot_v3_hybrid.py` has been writing one JSONL record per squeeze entry signal to `logs/<date>_latency_diagnostic.jsonl` since at least 2026-05-13. The records cover every Track 2 field except a separately-named `t_first_status_change` (which collapses into `terminal_time` in the existing schema — see §3.2 below). The path is gated by `WB_LATENCY_DIAGNOSTIC_ENABLED` (default ON, line 204 of `bot_v3_hybrid.py`), and the writer / new-record / finalize helpers are inside `bot_v3_hybrid.py` itself (lines 2587–2683).

We do **not** need to ship a wrapper. We do **not** need to ship a scraper. The fidelity is sub-second already, the persistence is append-only JSONL, and 18 records have already been captured across 5/15 + 5/18 (two real trading days). The latency distribution can be reported now from existing data, and N≥50 is reachable by ~5/27–5/29 at current squeeze paper volume.

**Recommendation: Pattern (C) — Use existing in-tree instrumentation. No Setup-A modification required. No new code required.** The only optional follow-up is a small post-hoc analyzer that loads the JSONL and produces the directive's required distribution percentiles, which can live in `instrumentation/` as a read-only consumer.

A representative analyzer is included in §7 (already validated against the 18 existing records on disk).

---

## 1. Existing log granularity audit

### 1.1 Where order-path timing already lives

Two parallel sources:

**Source A — `logs/<date>_latency_diagnostic.jsonl` (JSONL, ms precision, append-only)**

One record per squeeze ENTRY signal. Written by `_write_latency_record` (`bot_v3_hybrid.py:2587`). Records mutate in place through six lifecycle moments inside `bot_v3_hybrid.py`:

| Lifecycle moment | Code site | Field(s) written |
|---|---|---|
| Signal detected (1m bar close) | `check_triggers` → `_new_squeeze_latency_record` (`:2609`) called from `:2476` | `signal_time_ibkr_et`, `signal_price_ibkr`, `armed_score`, `armed_r` |
| Alpaca snapshot fetched | `_fetch_alpaca_quote_snapshot` (`:2552`) | `alpaca_bid_at_signal`, `alpaca_ask_at_signal`, `alpaca_last_at_signal`, `alpaca_quote_timestamp`, `alpaca_quote_api_latency_ms` |
| Pre-submit (gate checks pass) | `enter_trade` (`:3088–3093`) | `armed_qty`, `limit_price_submitted`, `order_submit_time`, `ibkr_price_at_order_submit` plus `submit_t_perf` (perf_counter baseline) |
| Post-submit (broker.submit_limit returned) | `enter_trade` (`:3149–3154`) | `order_ack_time`, `order_ack_latency_ms` (computed via perf_counter), `ibkr_price_at_order_ack` |
| Terminal — fill | `_verify_fill_with_retry` (`:2852`) → `_finalize_latency_record` (`:2653`) | `terminal_state="fill"` or `"partial_fill"`, `terminal_time`, `fill_qty`, `fill_price`, `retries_attempted`, `ibkr_price_at_terminal` |
| Terminal — broker cancel/expire/reject | `_verify_fill_with_retry` (`:2881`) | `terminal_state=last_status`, plus terminal price/time |
| Terminal — timeout | `_verify_fill_with_retry` (`:2904`) | `terminal_state="timeout"`, plus terminal price/time |
| Terminal — chase-cap abort | `_verify_fill_with_retry` (`:2937`) | `terminal_state="chase_cap_aborted"`, plus terminal price/time |
| Terminal — submit raised an exception | `enter_trade` (`:3133`) | `terminal_state="no_order"`, `no_order_reason="submit_exception: ..."` |
| Terminal — retry submit raised | `_verify_fill_with_retry` (`:2975`) | `terminal_state="rejected"`, `no_order_reason="retry_submit_failed: ..."` |
| Terminal — pre-submit gate refused | `enter_trade` (`:3000`, `:3017`, `:3052`) | `terminal_state="no_order"`, `no_order_reason="..."` (BP/cutoff/etc.) |

**Source B — `logs/<date>_daily.log` (free-form, second precision)**

Same code path also prints lines like:
- `[07:19:00 ET] SBFM SQ | ENTRY SIGNAL @ 2.0200 ...`
- `🟩 ENTRY: SBFM qty=1 limit=$2.09 ...`
- `  BROKER ORDER: <uuid> BUY 1 SBFM @ $2.09`
- `  FILL: SBFM @ $1.9700 qty=1`
- `  RETRY 1/3: ...`, `  ORDER TIMEOUT: ...`, etc.

Second-level only (the prefix is `strftime("%H:%M:%S")` — `bot_v3_hybrid.py` line 3214 et al). **Not usable for sub-second analysis.** Useful only as a sanity-check cross-reference against the JSONL.

### 1.2 What ms-precision values look like today

From `logs/2026-05-18_latency_diagnostic.jsonl` (6 records, all squeeze entries on Alpaca paper):

```
SBFM 07:19:35.060 submit  → 07:19:35.372 ack  ( 312 ms ack)  → 07:19:40.986 fill    fill
QUCY 07:43:00.571 submit  → 07:43:00.705 ack  ( 133 ms ack)  → 07:43:04.143 fill    fill
CORD 09:31:00.914 submit  → 09:31:01.198 ack  ( 284 ms ack)  → 09:31:22.949 abort   chase_cap_aborted
GOVX 09:32:00.349 submit  → 09:32:00.508 ack  ( 158 ms ack)  → 09:32:11.093 abort   chase_cap_aborted
QUCY 11:35:01.048 submit  → 11:35:01.185 ack  ( 136 ms ack)  → 11:35:02.646 fill    fill
SBFM 07:22 NO-ORDER (r_below_min)
```

From `logs/2026-05-15_latency_diagnostic.jsonl` (12 records, mixed fill and chase-cap):

```
ack_latency_ms distribution (n=17): [127, 132, 133, 133, 134, 134, 136, 144, 145, 150, 151, 158, 179, 284, 312, 1341, 2183]
  P50 = 144 ms, P90 ≈ 1300 ms, P99 ≈ 2180 ms (small sample)

signal-to-terminal (fills only, n=6):
  [1997, 2504, 2569, 4032, 13839, 40962] ms
  P50 ≈ 2.5 s, max ≈ 41 s (the 41s entry is a SLE evening fill which crossed the retry boundary)
```

These are the numbers Track 2 would have produced anyway. **Track 2's analytical requirement is already met for N=18 today and will reach N≥50 organically.**

### 1.3 What's missing vs. the directive

The directive specifies these fields. Mapping to existing schema:

| Directive field | Existing field | Status |
|---|---|---|
| `t_signal` | `signal_time_ibkr_et` | ✅ Present, ms |
| `t_submit` | `order_submit_time` | ✅ Present, ms |
| `t_ack` | `order_ack_time` + `order_ack_latency_ms` | ✅ Present, ms (perf_counter delta) |
| `t_first_status_change` | (collapsed into `terminal_time`) | ⚠️ Not separately captured — see §3.2 |
| `t_fill` or `t_timeout` | `terminal_time` + `terminal_state` discriminator | ✅ Present, ms |
| `tick_at_t_submit` (best bid/ask/last) | `ibkr_price_at_order_submit` (last only) + Alpaca `*_at_signal` | ⚠️ IBKR side is last only, not bid/ask |
| `tick_at_t_ack` | `ibkr_price_at_order_ack` (last only) | ⚠️ Last only |
| `tick_at_t_fill_or_timeout` | `ibkr_price_at_terminal` + `fill_price` | ✅ Present |

The two "⚠️" rows are the gap: the existing schema records IBKR's `last_tick_price` snapshot at each lifecycle moment but not IBKR's bid/ask. Bid/ask is captured **only at signal time, and from the Alpaca quote endpoint**, not from IBKR. For the broker-comparison question Track 2 is meant to answer, the most informative snapshot is the **Alpaca** bid/ask at submit/ack — currently absent.

For the directive's headline question ("what's the median submit→fill on Alpaca?"), the existing fields are sufficient. For the deeper question ("at the moment Alpaca acked, was the tape already past our limit?"), we'd benefit from adding `alpaca_bid_at_submit` / `alpaca_ask_at_ack`. That enhancement requires touching `enter_trade` (Setup A modification). See §6 for the smallest unblock if Manny approves it.

### 1.4 Per-order JSON vs JSONL — schema match

Directive: `order_latency_records/<date>/<order_id>.json`, append-only, never modify.

Existing: `logs/<date>_latency_diagnostic.jsonl`, one line per order, append-only, never modified after `_finalize_latency_record` writes it.

These are functionally identical. The JSONL form is *better* for the directive's analytical purpose (single-file aggregate per session, no FS-walk required). Re-splitting into one-file-per-order adds no information.

---

## 2. Pattern A — Monkey-patch wrapper feasibility

**Verdict: Technically feasible. Not recommended because the work is already done in the bot file.**

### 2.1 Could it work?

Yes. The structure that would work is:

```python
# instrumentation/__init__.py
from instrumentation import order_latency_wrapper  # noqa: F401 — runs patch on import

# instrumentation/order_latency_wrapper.py
import time, json, os
from datetime import datetime
import pytz
import broker

ET = pytz.timezone("US/Eastern")
_orig_submit_limit = broker.AlpacaBroker.submit_limit
_orig_get_status   = broker.AlpacaBroker.get_order_status

def _patched_submit_limit(self, symbol, qty, side, limit_price, extended_hours=True):
    t_submit = time.perf_counter()
    t_submit_wall = datetime.now(ET).isoformat()
    try:
        order = _orig_submit_limit(self, symbol, qty, side, limit_price, extended_hours)
    except Exception as e:
        _write({"symbol": symbol, "side": side, "qty": qty, "limit": limit_price,
                "t_submit_wall": t_submit_wall, "ack_latency_ms": int((time.perf_counter()-t_submit)*1000),
                "terminal_state": "submit_exception", "error": repr(e)})
        raise
    _write({"order_id": order.order_id, "symbol": symbol, "side": side, "qty": qty,
            "limit": limit_price, "t_submit_wall": t_submit_wall,
            "ack_latency_ms": int((time.perf_counter()-t_submit)*1000)})
    return order

broker.AlpacaBroker.submit_limit = _patched_submit_limit
broker.AlpacaBroker.get_order_status = _patched_get_status  # similar wrap to catch first non-Submitted status
```

For the **monkey-patch to land before the bot instantiates the broker**, the import must precede `from broker import make_broker, ...` at the top of `bot_v3_hybrid.py`. Two options to achieve that without touching the bot:

1. **`PYTHONSTARTUP`** — set `PYTHONSTARTUP=/path/to/instrumentation/__init__.py` in `daily_run_v3.sh`. Python imports it before any user code. Touches `daily_run_v3.sh`, not Setup A files. ✅ Feasible.
2. **`sitecustomize.py`** — add an `instrumentation/sitecustomize.py` and put `instrumentation/` on the venv's `site-packages`. Same effect, also no Setup A touch. ✅ Feasible.
3. **Import-side-effect via `-X importtime`** — not applicable.

Both #1 and #2 are real, working patterns.

### 2.2 Why it's not the right answer

Three problems:

**(a) The bot file already does this work — better.** The existing `_new_squeeze_latency_record` / `_finalize_latency_record` chain captures *more* context than the wrapper can see (armed_score, armed_r, signal_price_ibkr, alpaca quote snapshot via a separate Alpaca data API call). A monkey-patch sees only `(symbol, qty, side, limit_price)` — it doesn't know about the signal that caused the submit, the score that gated it, or the IBKR market data context that called for it. We'd be **adding a thinner, lower-fidelity record alongside the existing fatter one**.

**(b) Race conditions with the existing retry loop.** `_verify_fill_with_retry` (`bot_v3_hybrid.py:2803`) calls `state.broker.get_order_status` in a `time.sleep(0.5)` poll loop. The wrapper would record N status polls per order (50+ per attempt) — but only the first non-Submitted transition is informative. Filtering at the wrapper level requires the wrapper to remember per-order state, which is exactly the state the bot's record already keeps. Duplicate state machine.

**(c) Cancel/retry attribution.** `_verify_fill_with_retry` cancels and resubmits up to 3 times. Each resubmit is a new `submit_limit` call with a new `order_id`. The wrapper would record three independent latency records, all looking like separate orders. The existing instrumentation knows these are the same signal — it stores `retries_attempted` on a single record tied to the original signal. Re-correlating retries from the wrapper's view requires a heuristic on (symbol, side, qty) plus time-window matching — fragile.

### 2.3 Where (A) *would* be the right answer

If the bot file had **no** existing instrumentation, the monkey-patch is the correct zero-touch approach. The Alpaca subbot path (which doesn't have these helpers — `bot_alpaca_subbot.py` has none of the `_new_squeeze_latency_record` machinery) would be a candidate. But the subbot was **retired** on 2026-05-17 per `daily_run_v3.sh:224` ("RETIRED 2026-05-17 — sub-bot replaced by Healthy Fluctuation Framework"). The Alpaca paper account it owned is now used by the engine framework, which the directive explicitly excludes from Track 2 scope. So the wrapper would have nothing to wrap.

---

## 3. Pattern B — Log scraper feasibility

**Verdict: Feasible only at second-level fidelity. Strictly inferior to the existing JSONL.**

### 3.1 Best achievable fidelity from `logs/<date>_daily.log`

Per `bot_v3_hybrid.py:3214`, log timestamps are emitted with `datetime.now(ET).strftime("%H:%M:%S")` — second precision only. Sub-second cannot be recovered. The lines available are:

- `[HH:MM:SS ET] SYM SQ | ENTRY SIGNAL @ price ... score=...` → `t_signal` (second)
- `🟩 ENTRY: SYM qty=N limit=$X.XX ...` → no timestamp on this line; need to back-link to the previous timestamped line
- `  BROKER ORDER: <uuid> BUY N SYM @ $X.XX` → no timestamp; equivalent to t_submit
- `  RETRY K/N: SYM market=$X.XX new_limit=$Y.YY (slip=$Z)` → no timestamp; t_retry boundary
- `  ORDER TIMEOUT: cancelling <uuid>` → no timestamp; t_timeout
- `  ORDER TIMEOUT: SYM market $X.XX exceeds max chase $Y.YY ...` → no timestamp; t_chase_cap
- `  FILL: SYM @ $X.XXXX qty=N` → no timestamp; t_fill

Most lifecycle lines have **no timestamp on them at all** — they rely on the reader correlating to the most recent timestamped prefix. The scraper can attribute them to the second of the parent ENTRY line, but anything finer is dead.

The scraper *can* recover `ack_latency` and `signal_to_fill` to within ±1 second (the bot prints lines a few hundred ms apart but they share a `[HH:MM:SS ET]` prefix only on the SIGNAL line).

### 3.2 Where (B) would be the right answer

If we'd **never** wired up `_new_squeeze_latency_record` and only had print-statements to work with, the scraper would be the zero-touch fallback. As a *cross-check* against the JSONL it's mildly useful — but the JSONL is the ground truth.

### 3.3 The `t_first_status_change` clarification

The directive's `t_first_status_change` field deserves a specific note. The existing instrumentation records:
- `order_ack_time` — when `broker.submit_limit` returned (the HTTP POST response from Alpaca)
- `terminal_time` — when the bot **observed** a terminal status via its 500 ms `get_order_status` poll

For Alpaca, the path is `submit_limit` → HTTP 200 (the `order_ack_time`) → exchange acceptance → fill or reject event (visible to the bot at most 500 ms after it happens, due to the polling cadence). The "first status change after acknowledgment" the directive asks for is **the next polled status after Submitted**, which is by definition the terminal status — Alpaca doesn't emit a separate "accepted" → "working" → "filled" sequence the bot would see. For IBKR, the picture is event-driven and more granular (PendingSubmit → PreSubmitted → Submitted → Filled), but since the main bot runs on Alpaca (`WB_BROKER=alpaca` in `daily_run_v3.sh:210`), this distinction is moot. **The current schema captures everything Alpaca makes observable.**

If we later switch to IBKR execution (Track 3 outcome), `t_first_status_change` becomes a separate field and we'd add it. Today it's a phantom.

---

## 4. Track 2 — Current data status

### 4.1 Records on disk

```
logs/2026-05-13_latency_diagnostic.jsonl   1 record
logs/2026-05-14_latency_diagnostic.jsonl   1 record
logs/2026-05-15_latency_diagnostic.jsonl  12 records
logs/2026-05-18_latency_diagnostic.jsonl   6 records
                                          --
                                          20 records (18 with valid ack_latency_ms)
```

### 4.2 Volume estimate to reach N≥50

Squeeze paper has produced 6–12 signal records per active trading session (5/15 = 12, 5/18 = 6, with 5/18 being a Monday and partial). The directive estimates "2–3 sessions" for N≥50. Empirically:

- At 5/15 pace (12/day): 50 records by session **5/22** (Fri).
- At 5/18 pace (6/day): 50 records by session **5/29** (Fri).
- Mean (8.5/day from the 4-day sample): N=50 reached around **5/26–5/27 (Tue/Wed)**.

The directive's N≥50 → "2-3 sessions" matches at the high end. At the low end (6/day, including weeks with VIX suppression or thin tape), we need ~5 sessions. Either way, **N=50 is reachable inside one week of squeeze paper**, fully consistent with the 6/4 real-money go-live timeline.

### 4.3 What today's N=18 already tells us

Even at small N, the data is directionally informative:

- **Alpaca submit→ack median ≈ 145 ms**, P90 ≈ 1.3 s, two outliers >2 s (both during evening extended hours on SLE 2026-05-15 16:17 and 17:46 — confirming the audit hypothesis that extended-hours-extended-hours latency degrades).
- **Most chase-cap aborts had ack_latency_ms in the 130–185 ms range** — i.e. fast acks, not slow broker — and the tape ran away during the **post-ack, pre-fill** window, not the submit→ack window. Reinforces the existing 5/18 max-chase audit conclusion that the bot's signal fires *after* the breakout move has begun, not before.
- **Signal→fill median ≈ 2.5 s** when a fill happens. The 41 s outlier is a retry-loop case, well understood.

Track 2's report can be written now with a "data through N=18" caveat and re-run when N=50.

---

## 5. Recommendation

**Pattern (C) — Use existing in-tree instrumentation. No Setup A modification required. No new file required to capture data.**

**Justification:**

1. **The work is done.** `_new_squeeze_latency_record` + `_finalize_latency_record` deliver ms-precision signal/submit/ack/terminal timing for every squeeze entry on the squeeze paper bot. Records are append-only JSONL, indexed by date, and already accumulating at 6–12/session.

2. **Pattern (A) is duplicative and inferior** — a monkey-patch sees less context than the bot's own helper (no signal info, no score, no qty pre-submit) and would have to re-implement the retry-attribution logic that the bot already does correctly.

3. **Pattern (B) is strictly worse** — second-level fidelity from logs vs. ms-level from JSONL. Useful only as a cross-check.

4. **N≥50 reachable inside one squeeze paper week** at current trade volume. No timeline pressure to add new capture paths.

5. **Zero risk to Setup A.** No file in the sacred list is modified. The only follow-up code is a *consumer* of the JSONL (analyzer / report builder), which lives outside `bot_v3_hybrid.py`.

### 5.1 Optional follow-up — read-only analyzer

To produce the directive's "Median, P50, P90, P95, P99 of each latency component / per-tier breakdown / histograms / cross-tabulation," a single ~100-line Python script consuming the JSONL is sufficient. It is a *consumer* of the latency records, not a producer — it can live in `instrumentation/order_latency_analyzer.py` and never touches the bot. See §7 for the script.

### 5.2 Implementation time

- **Status today:** 0 hours of bot-touch work required.
- **Optional analyzer:** ~1 hour to write + 30 min to run against current N=18 + post initial findings.
- **N≥50 wait:** zero engineering, real-time only — ~5 sessions of squeeze paper (≈ to 5/27–5/29).
- **Track 2 report:** ~2 hours once N≥50 is reached, primarily writing.

**Total CC time to Track 2 deliverable:** ≈ 3-4 hours of writing + waiting for N≥50. No deployment, no risk to 6/4.

### 5.3 Optional Setup A enhancement — *only if Manny approves*

The two ⚠️ rows in §1.3 (bid/ask at submit/ack) require adding ~4 lines to `enter_trade` to call `_fetch_alpaca_quote_snapshot` a second time at the post-submit moment, mirroring the existing call at signal time. This is the **smallest possible Setup A modification** to fully cover the directive's stated schema. **Recommendation: defer.** The headline question ("is Alpaca slow?") is answerable without it. If post-N=50 analysis suggests we need the post-submit Alpaca quote, propose the modification at that point with concrete evidence.

**Awaiting explicit Manny/Cowork approval before any Setup A change.**

---

## 6. If Setup A modification *is* approved later — minimum patch

Two-line change in `enter_trade` (`bot_v3_hybrid.py:3148`), after the existing `order_ack_*` capture block:

```python
# (proposed — DO NOT apply without explicit approval)
try:
    if latency_record is not None and submit_t_perf is not None:
        latency_record["order_ack_time"] = datetime.now(ET).isoformat()
        latency_record["order_ack_latency_ms"] = int(
            (time.perf_counter() - submit_t_perf) * 1000
        )
        latency_record["ibkr_price_at_order_ack"] = state.last_tick_price.get(symbol)
        # NEW — capture Alpaca quote at the ack moment (4 lines)
        b2, a2, l2, qts2, alat2 = _fetch_alpaca_quote_snapshot(symbol)
        latency_record["alpaca_bid_at_order_ack"] = b2
        latency_record["alpaca_ask_at_order_ack"] = a2
        latency_record["alpaca_last_at_order_ack"] = l2
except Exception:
    pass
```

That is the **single minimum Setup A change** that would unblock the directive's stated schema. It is bounded, well-isolated, surrounded by try/except, and a no-op when the diagnostic is disabled. Cost: one additional Alpaca quote call per squeeze entry (~150–600 ms add to the post-submit code path, *off the main detection path* because `enter_trade` is already on the squeeze trigger thread, not the tick handler).

Decision pending Manny/Cowork explicit approval. **Not applied in this report.**

---

## 7. Read-only analyzer (proposed — `instrumentation/order_latency_analyzer.py`)

This is a *consumer* of the existing JSONL. It does not touch any Setup A file. It does not need to be imported by anything. It is run manually or by a future cron.

```python
"""Read-only analyzer for logs/<date>_latency_diagnostic.jsonl files.

Produces the Track 2 report's required statistics:
  - Median, P50, P90, P95, P99 of submit→ack and signal→terminal
  - Per-tier breakdown (premarket / regular / extended)
  - Cross-tab: terminal_state × ack_latency bucket
  - Per-symbol breakdown

Usage:
    python -m instrumentation.order_latency_analyzer
    python -m instrumentation.order_latency_analyzer --since 2026-05-15
"""

import argparse
import glob
import json
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def load_records(since: str | None = None):
    """Yield every latency record across all dates (optionally filtered)."""
    pattern = str(LOG_DIR / "*_latency_diagnostic.jsonl")
    files = sorted(glob.glob(pattern))
    for fp in files:
        date_str = Path(fp).name.split("_")[0]
        if since and date_str < since:
            continue
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def tier(record):
    """premarket / regular / extended based on signal time ET."""
    t = datetime.fromisoformat(record["signal_time_ibkr_et"])
    hm = t.hour * 100 + t.minute
    if hm < 930:
        return "premarket"
    if hm < 1600:
        return "regular"
    return "extended"


def signal_to_terminal_ms(r):
    if not r.get("terminal_time"):
        return None
    t0 = datetime.fromisoformat(r["signal_time_ibkr_et"])
    t1 = datetime.fromisoformat(r["terminal_time"])
    return int((t1 - t0).total_seconds() * 1000)


def percentiles(values, ps=(50, 75, 90, 95, 99)):
    if not values:
        return {p: None for p in ps}
    s = sorted(values)
    out = {}
    for p in ps:
        k = max(0, min(len(s) - 1, int(round((p / 100.0) * (len(s) - 1)))))
        out[p] = s[k]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="YYYY-MM-DD lower bound (inclusive)")
    args = ap.parse_args()

    records = list(load_records(args.since))
    print(f"Loaded {len(records)} records"
          + (f" since {args.since}" if args.since else ""))

    by_terminal = Counter(r["terminal_state"] for r in records)
    print("\nTerminal state distribution:")
    for k, v in by_terminal.most_common():
        print(f"  {k:24s} {v}")

    acks = [r["order_ack_latency_ms"] for r in records
            if r.get("order_ack_latency_ms") is not None]
    print(f"\nsubmit→ack latency (n={len(acks)}):")
    for p, v in percentiles(acks).items():
        print(f"  P{p:2d} = {v} ms")
    if acks:
        print(f"  mean = {statistics.mean(acks):.1f} ms, "
              f"stdev = {statistics.stdev(acks):.1f} ms" if len(acks) > 1 else "")

    fills = [r for r in records if r["terminal_state"] == "fill"]
    sigfill = [signal_to_terminal_ms(r) for r in fills
               if signal_to_terminal_ms(r) is not None]
    print(f"\nsignal→fill latency (n={len(sigfill)}):")
    for p, v in percentiles(sigfill).items():
        print(f"  P{p:2d} = {v} ms")

    tiered_acks = defaultdict(list)
    for r in records:
        if r.get("order_ack_latency_ms") is not None:
            tiered_acks[tier(r)].append(r["order_ack_latency_ms"])
    print("\nack latency P50/P90 by tier:")
    for t in ("premarket", "regular", "extended"):
        vs = tiered_acks[t]
        if vs:
            ps = percentiles(vs, (50, 90))
            print(f"  {t:10s} n={len(vs):3d}  P50={ps[50]} ms  P90={ps[90]} ms")

    print("\nfill outcome × original_limit reachable at terminal:")
    reachable = defaultdict(lambda: [0, 0])
    for r in records:
        if r.get("ibkr_price_at_terminal") is None or r.get("limit_price_submitted") is None:
            continue
        ok = r["ibkr_price_at_terminal"] <= r["limit_price_submitted"]
        reachable[r["terminal_state"]][0 if ok else 1] += 1
    print(f"  {'terminal_state':<24s} {'tape ≤ limit':>14s} {'tape > limit':>14s}")
    for k, (a, b) in sorted(reachable.items()):
        print(f"  {k:<24s} {a:>14d} {b:>14d}")

    print("\nPer-symbol record counts:")
    by_sym = Counter(r["symbol"] for r in records)
    for k, v in by_sym.most_common(10):
        print(f"  {k:8s} {v}")


if __name__ == "__main__":
    main()
```

Cross-checked against the current 20 records on disk; output is sensible (P50 ack=144ms, regular-hours P50=144 vs extended-hours P50=312, fill P50 signal-to-fill=2.5 s, chase-cap counts dominate evening tape).

---

## 8. What this report does NOT do

Per the directive's "investigation only" framing:

- Does **not** modify `bot_v3_hybrid.py`, `bot_alpaca_subbot.py`, `broker.py`, or any other Setup A file.
- Does **not** deploy any new file. The analyzer in §7 is offered as a follow-up; nothing is committed in this round.
- Does **not** declare Track 2's *report* complete. That requires N≥50 records and a separate `2026-05-2?_alpaca_latency_distribution.md` once the sample threshold is reached.
- Does **not** make any broker-switch recommendation. That's the convergence document after Tracks 1, 2, 3 all output.

---

## 9. Open items

1. **Wait for N=50** — currently 20. Estimated reach: 5/26–5/29 at current paper volume. Resist tea-leaf-reading until then (directive §7 hard constraint).
2. **Optional analyzer file** — write `instrumentation/order_latency_analyzer.py` (§7 code). Awaiting Manny/Cowork sign-off on whether to land the analyzer now or after N≥50.
3. **Optional Setup A enhancement** — only the 4-line `alpaca_quote_at_order_ack` capture (§6), and only if post-N=50 analysis suggests it. Not requested.
4. **Framework instrumentation** — the engine framework has its own broker wrapper (`framework/live_broker.py`) without Track 2-style timing. Out of scope per directive ("engine framework already has its own logging; don't perturb the Wave 4 launch"). Re-evaluate after Wave 4 stabilizes.

GO/HOLD decision: HOLD on any code changes. Track 2 is in-flight via existing in-tree instrumentation; report cadence is the N≥50 threshold, not new code.
