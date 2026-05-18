#!/usr/bin/env python3
"""compare_subbot_vs_main.py — Setup A vs Setup B parity-validation harness.

Compares two paired log files from a single trading day:

  - Setup A: `logs/<DATE>_daily.log`           (main bot — IBKR data feed)
  - Setup B: `logs/<DATE>_subbot_alpaca.log`   (sub-bot — Databento data feed
                                                tomorrow, IBKR data today/baseline)

Five comparison dimensions (per DIRECTIVE_2026-05-18_DATABENTO_SUBBOT.md §4):

  1. Tick density per symbol per minute
     - parse `TICK AUDIT: <SYM>: N ticks in last 60s, last_tick_time=HH:MM:SS`
     - report median, p95 per (symbol, feed)

  2. First-tick timing
     - delta between `✅ Subscribed: <SYM>` (or `[TIER] PROMOTE <SYM>`) and the
       first `TICK AUDIT` for that symbol with N>0

  3. Trigger detection latency
     - match `ENTRY SIGNAL @ <px>` events across feeds on (symbol, price ±$0.01)
     - report HH:MM:SS delta in milliseconds (second-resolution, expect ≥1s
       granularity)

  4. Signal-to-fill latency
     - per ENTRY: time between `🟩 ENTRY:` and `FILL:` for the same symbol
     - both bots execute on Alpaca, so this is informational-only

  5. Trade counts and symbol overlap
     - ENTRY counts per bot; A-only / B-only / both sets

Outputs:
  - cowork_reports/<DATE>_databento_vs_ibkr_subbot_comparison.md
  - cowork_reports/<DATE>_databento_vs_ibkr_subbot_per_symbol.csv
  - 8-12 line synthesis to stdout

Usage:
    ./venv/bin/python scripts/compare_subbot_vs_main.py
    ./venv/bin/python scripts/compare_subbot_vs_main.py 2026-05-15
    ./venv/bin/python scripts/compare_subbot_vs_main.py --baseline-only
    ./venv/bin/python scripts/compare_subbot_vs_main.py --setup-a logs/x.log --setup-b logs/y.log
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ─── Regexes ────────────────────────────────────────────────────────────

# Heartbeat-style timestamp embedded in many lines: "[HH:MM:SS ET] ..." or
# "[HH:MM ET] ...". The main-bot's status lines use the seconds form; the
# 1-minute CHART lines use the minute form.
TS_HHMMSS = re.compile(r"\[(\d{2}):(\d{2}):(\d{2}) ET\]")
TS_HHMM   = re.compile(r"\[(\d{2}):(\d{2}) ET\]")

# TICK AUDIT line — captures symbol, tick count, last_tick_time (HH:MM:SS).
TICK_AUDIT = re.compile(
    r"TICK AUDIT:\s+([A-Z][A-Z0-9.\-]*?):\s+(\d+)\s+ticks in last 60s,"
    r"\s+last_price=\$([\d.]+),\s+last_tick_time=(\d{2}):(\d{2}):(\d{2})"
)

# ENTRY SIGNAL — fires at signal-detection moment; line has its own timestamp.
#   [HH:MM:SS ET] SYM SQ | ENTRY SIGNAL @ 6.0200 (break 6.0200) stop=...
# minute-only form:
#   [HH:MM ET] SYM SQ | ENTRY SIGNAL @ 6.0200 ...
ENTRY_SIGNAL_SS = re.compile(
    r"\[(\d{2}):(\d{2}):(\d{2}) ET\]\s+([A-Z][A-Z0-9.\-]*)\s+\S+\s+\|\s+ENTRY SIGNAL\s+@\s+([\d.]+)"
)
ENTRY_SIGNAL_MM = re.compile(
    r"\[(\d{2}):(\d{2}) ET\]\s+([A-Z][A-Z0-9.\-]*)\s+\S+\s+\|\s+ENTRY SIGNAL\s+@\s+([\d.]+)"
)

# 🟩 ENTRY line — no inline timestamp; we anchor with nearest preceding heartbeat.
#   🟩 ENTRY: SLE qty=2491 limit=$6.09 (slip=$0.070) stop=...
ENTRY_LINE = re.compile(
    r"🟩 ENTRY:\s+([A-Z][A-Z0-9.\-]*)\s+qty=(\d+)\s+limit=\$([\d.]+)"
)

# FILL line — no inline timestamp.
#   FILL: SLE @ $6.1229 qty=2491 (after 1 retries)
FILL_LINE = re.compile(
    r"FILL:\s+([A-Z][A-Z0-9.\-]*)\s+@\s+\$([\d.]+)\s+qty=(\d+)"
)

# Subscribed line — anchors first-tick timing.
SUBSCRIBED_LINE = re.compile(r"✅ Subscribed:\s+([A-Z][A-Z0-9.\-]*)")
PROMOTE_LINE = re.compile(r"\[TIER\] PROMOTE\s+([A-Z][A-Z0-9.\-]*)\s+reason=")


# ─── Helpers ────────────────────────────────────────────────────────────

def parse_hms(h: str, m: str, s: str) -> int:
    """HH:MM:SS → seconds since midnight."""
    return int(h) * 3600 + int(m) * 60 + int(s)


def fmt_hms(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def percentile(vals: list[float], p: float) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return float(s[0])
    k = (len(s) - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def fmt_num(v: float | int | None, fmt: str = "{:.1f}") -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "—"
    try:
        return fmt.format(v)
    except Exception:
        return str(v)


# ─── Log parsing ────────────────────────────────────────────────────────

def parse_log(path: str) -> dict[str, Any]:
    """Walk the log once, accumulating all five-dimension input events.

    Returns:
        {
            "tick_audits":    [{symbol, count, minute_sec, last_tick_sec}],
            "subscribes":     [{symbol, anchor_sec}],
            "entry_signals":  [{symbol, price, signal_sec}],
            "entries":        [{symbol, qty, limit, anchor_sec}],
            "fills":          [{symbol, price, qty, anchor_sec}],
            "n_lines":        int,
        }
    """
    out: dict[str, Any] = {
        "tick_audits":   [],
        "subscribes":    [],
        "entry_signals": [],
        "entries":       [],
        "fills":         [],
        "n_lines":       0,
    }
    if not os.path.exists(path):
        print(f"  WARN: log not found: {path}", file=sys.stderr)
        return out

    last_ts_sec: int | None = None  # nearest preceding heartbeat timestamp
    pending_no_ts: list[dict] = []  # events seen before first heartbeat

    with open(path, errors="replace") as f:
        for raw in f:
            out["n_lines"] += 1
            line = raw.rstrip("\n")

            # Update heartbeat ts from anything that has [HH:MM:SS ET] or [HH:MM ET]
            new_ts: int | None = None
            m = TS_HHMMSS.search(line)
            if m:
                new_ts = parse_hms(m.group(1), m.group(2), m.group(3))
            else:
                m = TS_HHMM.search(line)
                if m:
                    new_ts = parse_hms(m.group(1), m.group(2), "0")
            if new_ts is not None:
                last_ts_sec = new_ts
                # Back-fill any boot-time events that lacked a preceding heartbeat
                if pending_no_ts:
                    for ev in pending_no_ts:
                        ev["anchor_sec"] = new_ts
                    pending_no_ts.clear()

            # TICK AUDIT
            m = TICK_AUDIT.search(line)
            if m:
                sym = m.group(1)
                count = int(m.group(2))
                last_t = parse_hms(m.group(4), m.group(5), m.group(6))
                # Bucket by minute of last_tick_time. When count=0, last_tick_time
                # is from a previous minute — bucket by the nearest heartbeat
                # minute if available, else by last_tick_time.
                if count == 0 and last_ts_sec is not None:
                    bucket_sec = (last_ts_sec // 60) * 60
                else:
                    bucket_sec = (last_t // 60) * 60
                out["tick_audits"].append({
                    "symbol":         sym,
                    "count":          count,
                    "minute_sec":     bucket_sec,
                    "last_tick_sec":  last_t,
                })
                continue

            # ENTRY SIGNAL — has inline timestamp
            m = ENTRY_SIGNAL_SS.search(line)
            if m:
                out["entry_signals"].append({
                    "symbol":     m.group(4),
                    "price":      float(m.group(5)),
                    "signal_sec": parse_hms(m.group(1), m.group(2), m.group(3)),
                })
                continue
            m = ENTRY_SIGNAL_MM.search(line)
            if m:
                out["entry_signals"].append({
                    "symbol":     m.group(3),
                    "price":      float(m.group(4)),
                    "signal_sec": parse_hms(m.group(1), m.group(2), "0"),
                })
                continue

            # 🟩 ENTRY:
            m = ENTRY_LINE.search(line)
            if m:
                ev = {
                    "symbol":     m.group(1),
                    "qty":        int(m.group(2)),
                    "limit":      float(m.group(3)),
                    "anchor_sec": last_ts_sec,
                }
                out["entries"].append(ev)
                if last_ts_sec is None:
                    pending_no_ts.append(ev)
                continue

            # FILL:
            m = FILL_LINE.search(line)
            if m:
                ev = {
                    "symbol":     m.group(1),
                    "price":      float(m.group(2)),
                    "qty":        int(m.group(3)),
                    "anchor_sec": last_ts_sec,
                }
                out["fills"].append(ev)
                if last_ts_sec is None:
                    pending_no_ts.append(ev)
                continue

            # ✅ Subscribed:  / [TIER] PROMOTE
            m = SUBSCRIBED_LINE.search(line)
            if m:
                ev = {"symbol": m.group(1), "anchor_sec": last_ts_sec}
                out["subscribes"].append(ev)
                if last_ts_sec is None:
                    pending_no_ts.append(ev)
                continue
            m = PROMOTE_LINE.search(line)
            if m:
                ev = {"symbol": m.group(1), "anchor_sec": last_ts_sec}
                out["subscribes"].append(ev)
                if last_ts_sec is None:
                    pending_no_ts.append(ev)
                continue

    return out


# ─── Dimension 1: Tick density per symbol per minute ────────────────────

def build_tick_density(audits: list[dict]) -> dict[str, list[int]]:
    """{symbol: [tick_count_for_minute_1, ..., minute_N]} — keyed by minute_sec.

    Deduplicates multiple audits in the same minute by keeping the max count
    (audits within the same minute typically report overlapping rolling 60s
    windows; max gives the best estimate of "ticks observed for this minute").
    """
    by_sym_minute: dict[tuple[str, int], int] = {}
    for a in audits:
        key = (a["symbol"], a["minute_sec"])
        if key in by_sym_minute:
            by_sym_minute[key] = max(by_sym_minute[key], a["count"])
        else:
            by_sym_minute[key] = a["count"]
    out: dict[str, list[int]] = defaultdict(list)
    for (sym, _), cnt in by_sym_minute.items():
        out[sym].append(cnt)
    return out


def dim1_table(a: dict[str, list[int]], b: dict[str, list[int]]) -> tuple[str, list[dict]]:
    """Markdown table + per-symbol CSV rows."""
    all_syms = sorted(set(a.keys()) | set(b.keys()))
    rows = [
        "| Symbol | A median | A p95 | A max | A minutes | B median | B p95 | B max | B minutes | B/A density |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    csv_rows: list[dict] = []
    a_meds_all: list[float] = []
    b_meds_all: list[float] = []
    for sym in all_syms:
        av = a.get(sym, [])
        bv = b.get(sym, [])
        am = percentile(av, 50)
        bm = percentile(bv, 50)
        a95 = percentile(av, 95)
        b95 = percentile(bv, 95)
        amax = max(av) if av else None
        bmax = max(bv) if bv else None
        ratio = None
        if am is not None and bm is not None and am > 0:
            ratio = bm / am
        if am is not None:
            a_meds_all.append(am)
        if bm is not None:
            b_meds_all.append(bm)
        rows.append(
            f"| {sym} | {fmt_num(am, '{:.0f}')} | {fmt_num(a95, '{:.0f}')} | "
            f"{fmt_num(amax, '{:.0f}')} | {len(av)} | "
            f"{fmt_num(bm, '{:.0f}')} | {fmt_num(b95, '{:.0f}')} | "
            f"{fmt_num(bmax, '{:.0f}')} | {len(bv)} | "
            f"{fmt_num(ratio, '{:.2f}×')} |"
        )
        csv_rows.append({
            "symbol":      sym,
            "dimension":   "tick_density",
            "a_median":    am, "a_p95": a95, "a_max": amax, "a_minutes": len(av),
            "b_median":    bm, "b_p95": b95, "b_max": bmax, "b_minutes": len(bv),
            "b_over_a":    ratio,
        })

    # Aggregate footer
    summary = {
        "a_overall_median": percentile(a_meds_all, 50),
        "b_overall_median": percentile(b_meds_all, 50),
    }
    rows.append("")
    rows.append(
        f"**Overall median-of-per-symbol-medians:** "
        f"Setup A = {fmt_num(summary['a_overall_median'], '{:.0f}')} ticks/min, "
        f"Setup B = {fmt_num(summary['b_overall_median'], '{:.0f}')} ticks/min"
    )
    return "\n".join(rows), csv_rows


# ─── Dimension 2: First-tick timing ─────────────────────────────────────

def first_tick_delta(subs: list[dict], audits: list[dict]) -> dict[str, int]:
    """For each symbol, find time from first `Subscribed`/`PROMOTE` to first
    TICK AUDIT showing nonzero ticks. Returns {symbol: seconds_delta}."""
    first_sub: dict[str, int] = {}
    for s in subs:
        if s["anchor_sec"] is None:
            continue
        if s["symbol"] not in first_sub:
            first_sub[s["symbol"]] = s["anchor_sec"]

    first_tick: dict[str, int] = {}
    # Use last_tick_sec (the actual tick timestamp) for the most accurate
    # measurement; fall back to minute_sec if last_tick_sec is unusable.
    for a in audits:
        if a["count"] <= 0:
            continue
        when = a["last_tick_sec"]
        sym = a["symbol"]
        if sym not in first_tick or when < first_tick[sym]:
            first_tick[sym] = when

    out: dict[str, int] = {}
    for sym, t0 in first_sub.items():
        if sym in first_tick:
            out[sym] = first_tick[sym] - t0
    return out


def dim2_table(a_delta: dict[str, int], b_delta: dict[str, int]) -> tuple[str, list[dict]]:
    all_syms = sorted(set(a_delta.keys()) | set(b_delta.keys()))
    rows = [
        "| Symbol | A: subscribe → first tick (s) | B: subscribe → first tick (s) | Δ (B − A) |",
        "|---|---:|---:|---:|",
    ]
    csv_rows: list[dict] = []
    diffs: list[float] = []
    for sym in all_syms:
        ad = a_delta.get(sym)
        bd = b_delta.get(sym)
        diff = None
        if ad is not None and bd is not None:
            diff = bd - ad
            diffs.append(diff)
        rows.append(
            f"| {sym} | {fmt_num(ad, '{:+d}') if ad is not None else '—'} | "
            f"{fmt_num(bd, '{:+d}') if bd is not None else '—'} | "
            f"{fmt_num(diff, '{:+d}') if diff is not None else '—'} |"
        )
        csv_rows.append({
            "symbol":    sym,
            "dimension": "first_tick_delta_s",
            "a_value":   ad,
            "b_value":   bd,
            "delta":     diff,
        })
    if diffs:
        rows.append("")
        rows.append(
            f"**Median Δ:** {fmt_num(percentile(diffs, 50), '{:+.1f}')} s "
            f"(positive = B slower to first tick than A; N={len(diffs)})"
        )
    return "\n".join(rows), csv_rows


# ─── Dimension 3: Trigger detection latency ─────────────────────────────

def match_entry_signals(a: list[dict], b: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Match A and B entry signals on (symbol, price ±$0.01). Returns:
        - matched: [{symbol, price, a_sec, b_sec, delta_sec}]
        - a_only:  [{symbol, price, a_sec}]
        - b_only:  [{symbol, price, b_sec}]
    Greedy: each A is paired to the closest-in-time B with same symbol within
    a 5-minute window and price within $0.01.
    """
    matched: list[dict] = []
    used_b: set[int] = set()
    for ae in a:
        best_j = None
        best_dt = None
        for j, be in enumerate(b):
            if j in used_b:
                continue
            if be["symbol"] != ae["symbol"]:
                continue
            if abs(be["price"] - ae["price"]) > 0.01:
                continue
            dt = abs(be["signal_sec"] - ae["signal_sec"])
            if dt > 300:
                continue
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best_j = j
        if best_j is not None:
            be = b[best_j]
            used_b.add(best_j)
            matched.append({
                "symbol":    ae["symbol"],
                "price":     ae["price"],
                "a_sec":     ae["signal_sec"],
                "b_sec":     be["signal_sec"],
                "delta_sec": be["signal_sec"] - ae["signal_sec"],
            })
    a_only = [
        {"symbol": ae["symbol"], "price": ae["price"], "a_sec": ae["signal_sec"]}
        for ae in a
        if not any(m["a_sec"] == ae["signal_sec"] and m["symbol"] == ae["symbol"]
                   and abs(m["price"] - ae["price"]) < 0.001 for m in matched)
    ]
    b_only = [
        {"symbol": be["symbol"], "price": be["price"], "b_sec": be["signal_sec"]}
        for j, be in enumerate(b) if j not in used_b
    ]
    return matched, a_only, b_only


def dim3_table(matched: list[dict], a_only: list[dict], b_only: list[dict]) -> tuple[str, list[dict]]:
    rows = [
        "| Symbol | Price | A signal time | B signal time | Δ (B − A, s) |",
        "|---|---:|---|---|---:|",
    ]
    csv_rows: list[dict] = []
    for m in sorted(matched, key=lambda x: x["a_sec"]):
        rows.append(
            f"| {m['symbol']} | ${m['price']:.4f} | "
            f"{fmt_hms(m['a_sec'])} | {fmt_hms(m['b_sec'])} | "
            f"{m['delta_sec']:+d} |"
        )
        csv_rows.append({
            "symbol":    m["symbol"],
            "dimension": "trigger_latency_s",
            "price":     m["price"],
            "a_value":   m["a_sec"],
            "b_value":   m["b_sec"],
            "delta":     m["delta_sec"],
        })
    if matched:
        deltas = [m["delta_sec"] for m in matched]
        rows.append("")
        rows.append(
            f"**Matched signals: {len(matched)}** — median Δ = "
            f"{fmt_num(percentile(deltas, 50), '{:+.1f}')} s, "
            f"p95 |Δ| = {fmt_num(percentile([abs(x) for x in deltas], 95), '{:.1f}')} s"
        )

    if a_only:
        rows.append("")
        rows.append(f"### Setup A only ({len(a_only)})")
        rows.append("")
        rows.append("| Symbol | Price | A signal time |")
        rows.append("|---|---:|---|")
        for r in sorted(a_only, key=lambda x: x["a_sec"]):
            rows.append(f"| {r['symbol']} | ${r['price']:.4f} | {fmt_hms(r['a_sec'])} |")
            csv_rows.append({
                "symbol":    r["symbol"],
                "dimension": "trigger_a_only",
                "price":     r["price"],
                "a_value":   r["a_sec"],
                "b_value":   None,
                "delta":     None,
            })
    if b_only:
        rows.append("")
        rows.append(f"### Setup B only ({len(b_only)})")
        rows.append("")
        rows.append("| Symbol | Price | B signal time |")
        rows.append("|---|---:|---|")
        for r in sorted(b_only, key=lambda x: x["b_sec"]):
            rows.append(f"| {r['symbol']} | ${r['price']:.4f} | {fmt_hms(r['b_sec'])} |")
            csv_rows.append({
                "symbol":    r["symbol"],
                "dimension": "trigger_b_only",
                "price":     r["price"],
                "a_value":   None,
                "b_value":   r["b_sec"],
                "delta":     None,
            })
    return "\n".join(rows), csv_rows


# ─── Dimension 4: Signal-to-fill latency ────────────────────────────────

def signal_to_fill(entries: list[dict], fills: list[dict]) -> list[dict]:
    """Pair each `🟩 ENTRY:` with the next `FILL:` for the same symbol whose
    anchor_sec is ≥ entry's anchor_sec. Returns
    [{symbol, entry_sec, fill_sec, delta_sec, qty, limit, fill_price}].
    """
    out: list[dict] = []
    used: set[int] = set()
    for e in entries:
        if e["anchor_sec"] is None:
            continue
        best_j = None
        best_dt = None
        for j, fi in enumerate(fills):
            if j in used:
                continue
            if fi["symbol"] != e["symbol"]:
                continue
            if fi["anchor_sec"] is None:
                continue
            dt = fi["anchor_sec"] - e["anchor_sec"]
            if dt < 0 or dt > 300:
                continue
            if best_dt is None or dt < best_dt:
                best_dt = dt
                best_j = j
        if best_j is not None:
            fi = fills[best_j]
            used.add(best_j)
            out.append({
                "symbol":     e["symbol"],
                "entry_sec":  e["anchor_sec"],
                "fill_sec":   fi["anchor_sec"],
                "delta_sec":  fi["anchor_sec"] - e["anchor_sec"],
                "qty":        e["qty"],
                "limit":      e["limit"],
                "fill_price": fi["price"],
            })
    return out


def dim4_table(a_pairs: list[dict], b_pairs: list[dict]) -> tuple[str, list[dict]]:
    rows = []
    csv_rows: list[dict] = []
    for label, pairs in (("Setup A", a_pairs), ("Setup B", b_pairs)):
        if not pairs:
            rows.append(f"### {label}")
            rows.append("")
            rows.append("_No entry→fill pairs in this log._")
            rows.append("")
            continue
        deltas = [p["delta_sec"] for p in pairs]
        rows.append(f"### {label}")
        rows.append("")
        rows.append(f"N = {len(pairs)}, "
                    f"median = {fmt_num(percentile(deltas, 50), '{:.1f}')} s, "
                    f"p90 = {fmt_num(percentile(deltas, 90), '{:.1f}')} s, "
                    f"p99 = {fmt_num(percentile(deltas, 99), '{:.1f}')} s, "
                    f"max = {max(deltas)} s")
        rows.append("")
        rows.append("| Symbol | Entry time | Fill time | Δ (s) | Limit | Fill px |")
        rows.append("|---|---|---|---:|---:|---:|")
        for p in pairs:
            rows.append(
                f"| {p['symbol']} | {fmt_hms(p['entry_sec'])} | "
                f"{fmt_hms(p['fill_sec'])} | {p['delta_sec']} | "
                f"${p['limit']:.2f} | ${p['fill_price']:.4f} |"
            )
            csv_rows.append({
                "symbol":    p["symbol"],
                "dimension": f"signal_to_fill_s_{label.split()[1].lower()}",
                "a_value":   p["entry_sec"] if label == "Setup A" else None,
                "b_value":   p["entry_sec"] if label == "Setup B" else None,
                "delta":     p["delta_sec"],
                "limit":     p["limit"],
                "fill_px":   p["fill_price"],
            })
        rows.append("")
    return "\n".join(rows), csv_rows


# ─── Dimension 5: Trade counts and symbol overlap ───────────────────────

def dim5_table(a_entries: list[dict], b_entries: list[dict]) -> tuple[str, list[dict], dict]:
    a_syms = defaultdict(int)
    b_syms = defaultdict(int)
    for e in a_entries:
        a_syms[e["symbol"]] += 1
    for e in b_entries:
        b_syms[e["symbol"]] += 1
    all_syms = sorted(set(a_syms.keys()) | set(b_syms.keys()))
    both = sorted(set(a_syms) & set(b_syms))
    a_only = sorted(set(a_syms) - set(b_syms))
    b_only = sorted(set(b_syms) - set(a_syms))

    rows = [
        f"- Setup A entries: **{len(a_entries)}** across {len(a_syms)} symbols",
        f"- Setup B entries: **{len(b_entries)}** across {len(b_syms)} symbols",
        f"- Shared symbols: **{len(both)}** — {', '.join(both) if both else '(none)'}",
        f"- A only ({len(a_only)}): {', '.join(a_only) if a_only else '(none)'}",
        f"- B only ({len(b_only)}): {', '.join(b_only) if b_only else '(none)'}",
        "",
        "| Symbol | A entries | B entries |",
        "|---|---:|---:|",
    ]
    csv_rows: list[dict] = []
    for sym in all_syms:
        rows.append(f"| {sym} | {a_syms.get(sym, 0)} | {b_syms.get(sym, 0)} |")
        csv_rows.append({
            "symbol":    sym,
            "dimension": "trade_count",
            "a_value":   a_syms.get(sym, 0),
            "b_value":   b_syms.get(sym, 0),
            "delta":     b_syms.get(sym, 0) - a_syms.get(sym, 0),
        })
    summary = {
        "n_a": len(a_entries), "n_b": len(b_entries),
        "n_both": len(both),   "n_a_only": len(a_only),  "n_b_only": len(b_only),
    }
    return "\n".join(rows), csv_rows, summary


# ─── Verdict ────────────────────────────────────────────────────────────

def build_verdict(
    a_density: dict[str, list[int]], b_density: dict[str, list[int]],
    a_first: dict[str, int],          b_first: dict[str, int],
    matched: list[dict],
    a_pairs: list[dict],              b_pairs: list[dict],
    counts: dict,
) -> list[str]:
    lines: list[str] = []

    # Density ratio (median of per-symbol medians)
    a_meds = [percentile(v, 50) for v in a_density.values() if v]
    b_meds = [percentile(v, 50) for v in b_density.values() if v]
    a_overall = percentile([x for x in a_meds if x is not None], 50)
    b_overall = percentile([x for x in b_meds if x is not None], 50)
    if a_overall and b_overall and a_overall > 0:
        ratio = b_overall / a_overall
        denser = "denser" if ratio >= 1 else "sparser"
        pct = (ratio - 1) * 100
        lines.append(
            f"- **Tick density:** Setup B median {fmt_num(b_overall, '{:.0f}')} ticks/min "
            f"vs Setup A {fmt_num(a_overall, '{:.0f}')} → "
            f"B is {abs(pct):.0f}% {denser}"
        )
    else:
        lines.append("- **Tick density:** insufficient data")

    # First-tick speed
    common = set(a_first) & set(b_first)
    if common:
        diffs = [b_first[s] - a_first[s] for s in common]
        med = percentile(diffs, 50)
        faster = "faster" if med < 0 else "slower"
        lines.append(
            f"- **First-tick timing:** Setup B median {abs(med):.0f}s {faster} than A "
            f"to first nonzero tick (N={len(common)})"
        )
    else:
        lines.append("- **First-tick timing:** no symbols comparable")

    # Trigger latency
    if matched:
        deltas = [m["delta_sec"] for m in matched]
        med = percentile(deltas, 50)
        if med == 0:
            lines.append(
                f"- **Trigger latency:** {len(matched)} matched signals, "
                f"median Δ = 0s (second-resolution)"
            )
        else:
            faster = "faster" if med < 0 else "slower"
            lines.append(
                f"- **Trigger latency:** {len(matched)} matched signals, "
                f"Setup B median {abs(med):.0f}s {faster} than A"
            )
    else:
        lines.append("- **Trigger latency:** no matched signals (likely no overlap in entries)")

    # Signal-to-fill latency
    if a_pairs and b_pairs:
        a_med = percentile([p["delta_sec"] for p in a_pairs], 50)
        b_med = percentile([p["delta_sec"] for p in b_pairs], 50)
        lines.append(
            f"- **Signal→fill latency (Alpaca broker, informational):** "
            f"A median {a_med:.0f}s (N={len(a_pairs)}), "
            f"B median {b_med:.0f}s (N={len(b_pairs)})"
        )
    elif a_pairs:
        a_med = percentile([p["delta_sec"] for p in a_pairs], 50)
        lines.append(
            f"- **Signal→fill latency:** Setup A median {a_med:.0f}s "
            f"(N={len(a_pairs)}); Setup B had no fills"
        )
    elif b_pairs:
        b_med = percentile([p["delta_sec"] for p in b_pairs], 50)
        lines.append(
            f"- **Signal→fill latency:** Setup B median {b_med:.0f}s "
            f"(N={len(b_pairs)}); Setup A had no fills"
        )
    else:
        lines.append("- **Signal→fill latency:** no entry/fill pairs in either log")

    # Trade counts
    lines.append(
        f"- **Trade counts:** A={counts['n_a']}, B={counts['n_b']}, "
        f"shared={counts['n_both']}, A-only={counts['n_a_only']}, "
        f"B-only={counts['n_b_only']}"
    )
    return lines


# ─── Report assembly ────────────────────────────────────────────────────

def build_report(
    date_str: str, a_path: str, b_path: str,
    a: dict, b: dict, baseline_mode: bool,
) -> tuple[str, list[dict], list[str]]:
    """Returns (markdown_body, csv_rows, verdict_lines)."""
    a_density = build_tick_density(a["tick_audits"])
    b_density = build_tick_density(b["tick_audits"])

    a_first = first_tick_delta(a["subscribes"], a["tick_audits"])
    b_first = first_tick_delta(b["subscribes"], b["tick_audits"])

    matched, a_only_sig, b_only_sig = match_entry_signals(
        a["entry_signals"], b["entry_signals"])

    a_pairs = signal_to_fill(a["entries"], a["fills"])
    b_pairs = signal_to_fill(b["entries"], b["fills"])

    dim1_md, dim1_csv = dim1_table(a_density, b_density)
    dim2_md, dim2_csv = dim2_table(a_first, b_first)
    dim3_md, dim3_csv = dim3_table(matched, a_only_sig, b_only_sig)
    dim4_md, dim4_csv = dim4_table(a_pairs, b_pairs)
    dim5_md, dim5_csv, counts = dim5_table(a["entries"], b["entries"])

    verdict = build_verdict(
        a_density, b_density, a_first, b_first,
        matched, a_pairs, b_pairs, counts,
    )

    title_a = "IBKR data (main bot)"
    title_b = "Databento data (sub-bot, tomorrow)" if not baseline_mode \
              else "IBKR data (sub-bot, baseline)"

    body: list[str] = []
    body.append(f"# Setup A vs Setup B comparison — {date_str}")
    body.append("")
    body.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    body.append("")
    body.append(f"- **Setup A:** {title_a} — `{os.path.relpath(a_path, REPO)}` "
                f"({a['n_lines']:,} lines)")
    body.append(f"- **Setup B:** {title_b} — `{os.path.relpath(b_path, REPO)}` "
                f"({b['n_lines']:,} lines)")
    body.append("")
    if baseline_mode:
        body.append("> **Baseline mode.** Both feeds are IBKR; near-identity is expected. "
                    "Use this report as a control for tomorrow's Databento-vs-IBKR run.")
        body.append("")
    body.append("## Verdict")
    body.append("")
    body.extend(verdict)
    body.append("")
    body.append("## 1. Tick density per symbol per minute")
    body.append("")
    body.append(dim1_md)
    body.append("")
    body.append("## 2. First-tick timing (subscribe → first nonzero tick)")
    body.append("")
    body.append(dim2_md)
    body.append("")
    body.append("## 3. Trigger detection latency")
    body.append("")
    body.append("Match key: (symbol, price ±$0.01), |Δt| ≤ 5 min. "
                "Resolution is 1 second (logs are second-grained).")
    body.append("")
    body.append(dim3_md)
    body.append("")
    body.append("## 4. Signal-to-fill latency")
    body.append("")
    body.append("Time from `🟩 ENTRY:` line to next matching `FILL:` line, "
                "anchored to the nearest preceding `[HH:MM:SS ET]` heartbeat. "
                "Both bots use Alpaca for execution — divergence here is "
                "informational (broker-side variance) and not data-feed signal.")
    body.append("")
    body.append(dim4_md)
    body.append("")
    body.append("## 5. Trade counts and symbol overlap")
    body.append("")
    body.append(dim5_md)
    body.append("")
    body.append("## Methodology notes")
    body.append("")
    body.append("- TICK AUDIT lines lack inline timestamps; the per-minute bucket is "
                "derived from the `last_tick_time=` field when count>0, and from "
                "the nearest preceding heartbeat when count=0.")
    body.append("- `🟩 ENTRY:` and `FILL:` lines also lack inline timestamps; we "
                "back-fill from the nearest preceding `[HH:MM:SS ET]` line. On a "
                "busy day this is accurate to ±1 second.")
    body.append("- `Subscribed` and `[TIER] PROMOTE` are treated as equivalent "
                "first-tick anchors.")
    body.append("- Resolution caveats: trigger-latency reporting is per-second, "
                "since the source `ENTRY SIGNAL` timestamps are HH:MM:SS only. "
                "Sub-second precision is unavailable without a code-side change.")
    body.append("")
    csv_rows = dim1_csv + dim2_csv + dim3_csv + dim4_csv + dim5_csv
    return "\n".join(body), csv_rows, verdict


# ─── CSV writer ─────────────────────────────────────────────────────────

CSV_COLUMNS = [
    "symbol", "dimension",
    "a_median", "a_p95", "a_max", "a_minutes",
    "b_median", "b_p95", "b_max", "b_minutes",
    "b_over_a",
    "a_value", "b_value", "delta",
    "price", "limit", "fill_px",
]


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ─── CLI ────────────────────────────────────────────────────────────────

def default_paths(date_str: str) -> tuple[str, str]:
    a = os.path.join(REPO, "logs", f"{date_str}_daily.log")
    b = os.path.join(REPO, "logs", f"{date_str}_subbot_alpaca.log")
    return a, b


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Setup A (main bot) vs Setup B (sub-bot) parity comparison.")
    ap.add_argument("date", nargs="?",
                    help="YYYY-MM-DD (default: today). Loads logs/<date>_daily.log "
                         "and logs/<date>_subbot_alpaca.log.")
    ap.add_argument("--setup-a", default=None,
                    help="Override Setup A log path.")
    ap.add_argument("--setup-b", default=None,
                    help="Override Setup B log path.")
    ap.add_argument("--baseline-only", action="store_true",
                    help="Force baseline mode: run against 2026-05-15 paired logs "
                         "(both bots on IBKR) for the control comparison.")
    ap.add_argument("--out-dir", default=None,
                    help="Override output dir (default: cowork_reports/).")
    args = ap.parse_args()

    if args.baseline_only:
        date_str = "2026-05-15"
    elif args.date:
        date_str = args.date
    else:
        date_str = date.today().isoformat()

    a_path = args.setup_a or default_paths(date_str)[0]
    b_path = args.setup_b or default_paths(date_str)[1]

    if not os.path.exists(a_path):
        print(f"ERROR: Setup A log not found: {a_path}", file=sys.stderr)
        return 1
    if not os.path.exists(b_path):
        print(f"ERROR: Setup B log not found: {b_path}", file=sys.stderr)
        return 1

    print(f"Reading Setup A: {a_path}", file=sys.stderr)
    a = parse_log(a_path)
    print(f"Reading Setup B: {b_path}", file=sys.stderr)
    b = parse_log(b_path)

    body, csv_rows, verdict = build_report(
        date_str, a_path, b_path, a, b, baseline_mode=args.baseline_only,
    )

    out_dir = args.out_dir or os.path.join(REPO, "cowork_reports")
    os.makedirs(out_dir, exist_ok=True)
    md_path = os.path.join(out_dir, f"{date_str}_databento_vs_ibkr_subbot_comparison.md")
    csv_path = os.path.join(out_dir, f"{date_str}_databento_vs_ibkr_subbot_per_symbol.csv")

    with open(md_path, "w") as f:
        f.write(body)
    write_csv(csv_path, csv_rows)

    # stdout synthesis
    print()
    print(f"=== Setup A vs Setup B — {date_str} ===")
    for line in verdict:
        print(line)
    print(f"- Report: {md_path}")
    print(f"- CSV:    {csv_path}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
