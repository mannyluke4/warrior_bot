#!/usr/bin/env python3
"""analyze_latency_diagnostic.py — Analyze Alpaca latency diagnostic logs.

Reads the per-signal JSONL produced by the Phase 1 diagnostic in
bot_v3_hybrid.py and emits a Markdown report containing:

  A. Latency distribution (p50/p75/p90/p99/max) across all signals
  B. Per-signal outcome table
  C. Lag-adjusted-limit simulation — how many timeouts would have filled if
     limits had been calibrated to Alpaca's pre-signal ask + buffer

Optional enrichment: pulls Alpaca trades for the [signal_time, terminal_time]
window for each signal to find the first print at or above signal price. The
enrichment column is `first_alpaca_print_above_signal`. Skips silently if the
Alpaca data SDK isn't available, credentials aren't set, or the API
rate-limits. The base report renders without enrichment.

Usage:
    python scripts/analyze_latency_diagnostic.py            # today
    python scripts/analyze_latency_diagnostic.py 2026-05-12 # specific date
    python scripts/analyze_latency_diagnostic.py --no-enrich
    python scripts/analyze_latency_diagnostic.py path/to/file.jsonl

Reads:   logs/<date>_latency_diagnostic.jsonl
Writes:  cowork_reports/<date>_latency_diagnostic.md
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timedelta
from typing import Any

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ─── I/O helpers ────────────────────────────────────────────────────────

def load_jsonl(path: str) -> list[dict]:
    """Read newline-delimited JSON. Skip malformed lines with a warning."""
    out = []
    if not os.path.exists(path):
        return out
    with open(path) as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  WARN: skipping malformed line {i}: {e}", file=sys.stderr)
    return out


def parse_iso(s: Any) -> datetime | None:
    """ET-tagged ISO string → naive datetime (best effort). Returns None on fail."""
    if not s:
        return None
    if isinstance(s, datetime):
        return s
    try:
        # fromisoformat handles "2026-05-12T09:31:00.123" and offset-tagged.
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def ms_between(a: Any, b: Any) -> float | None:
    """(b - a) in milliseconds, both ISO strings or datetimes. None on missing."""
    da = parse_iso(a)
    db = parse_iso(b)
    if da is None or db is None:
        return None
    # Both should be either tz-aware or naive; coerce by stripping tz for safety.
    if da.tzinfo is not None:
        da = da.replace(tzinfo=None)
    if db.tzinfo is not None:
        db = db.replace(tzinfo=None)
    return (db - da).total_seconds() * 1000.0


# ─── Statistics ─────────────────────────────────────────────────────────

def percentile(vals: list[float], p: float) -> float | None:
    """Linear-interp percentile. Returns None for empty input."""
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    f = int(math.floor(k))
    c = int(math.ceil(k))
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def fmt_num(v: float | None, fmt: str = "{:.1f}") -> str:
    if v is None:
        return "—"
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return "—"
    try:
        return fmt.format(v)
    except Exception:
        return str(v)


def fmt_pct(v: float | None) -> str:
    return fmt_num(v, "{:+.3f}%")


# ─── Metric extraction per record ───────────────────────────────────────

def per_signal_metrics(rec: dict) -> dict:
    """Compute the six latency/drift metrics for one signal record."""
    sp = rec.get("signal_price_ibkr")
    ask = rec.get("alpaca_ask_at_signal")
    ibk_term = rec.get("ibkr_price_at_terminal")

    # 1. Inter-feed price gap (%): how far above IBKR's signal Alpaca's ask was
    if sp and ask and sp > 0:
        inter_price_gap_pct = (ask - sp) / sp * 100.0
    else:
        inter_price_gap_pct = None

    # 2. Inter-feed timestamp gap (ms): positive = IBKR ahead of Alpaca
    inter_ts_gap_ms = ms_between(
        rec.get("alpaca_quote_timestamp"), rec.get("signal_time_ibkr_et")
    )

    # 3. Signal → order submit
    sig2sub_ms = ms_between(
        rec.get("signal_time_ibkr_et"), rec.get("order_submit_time")
    )

    # 4. Order submit → ack
    sub2ack_ms = rec.get("order_ack_latency_ms")
    if sub2ack_ms is None:
        sub2ack_ms = ms_between(
            rec.get("order_submit_time"), rec.get("order_ack_time")
        )

    # 5. Signal → ack
    sig2ack_ms = ms_between(
        rec.get("signal_time_ibkr_et"), rec.get("order_ack_time")
    )

    # 6. IBKR price drift during entry attempt (%)
    if sp and ibk_term and sp > 0:
        ibkr_drift_pct = (ibk_term - sp) / sp * 100.0
    else:
        ibkr_drift_pct = None

    return {
        "inter_price_gap_pct": inter_price_gap_pct,
        "inter_ts_gap_ms": inter_ts_gap_ms,
        "sig2sub_ms": sig2sub_ms,
        "sub2ack_ms": sub2ack_ms,
        "sig2ack_ms": sig2ack_ms,
        "ibkr_drift_pct": ibkr_drift_pct,
    }


# ─── Table A: latency distribution ──────────────────────────────────────

LATENCY_METRICS = [
    ("inter_price_gap_pct", "Inter-feed price gap at signal (% of signal price)", "{:+.3f}%"),
    ("inter_ts_gap_ms",      "Inter-feed timestamp gap (ms, +=IBKR ahead)",        "{:+.0f}"),
    ("sig2sub_ms",           "Signal → order submit (ms)",                          "{:.0f}"),
    ("sub2ack_ms",           "Order submit → ack (ms)",                             "{:.0f}"),
    ("sig2ack_ms",           "Signal → ack (total ms)",                             "{:.0f}"),
    ("ibkr_drift_pct",       "IBKR price drift during entry attempt (%)",           "{:+.3f}%"),
]


def render_table_a(per_metrics: list[dict]) -> str:
    """| metric | p50 | p75 | p90 | p99 | max | N |"""
    rows = ["| Metric | p50 | p75 | p90 | p99 | Max | N |",
            "|---|---:|---:|---:|---:|---:|---:|"]
    for key, label, fmt in LATENCY_METRICS:
        vals = [m[key] for m in per_metrics if m[key] is not None]
        if not vals:
            rows.append(f"| {label} | — | — | — | — | — | 0 |")
            continue
        p50 = percentile(vals, 50)
        p75 = percentile(vals, 75)
        p90 = percentile(vals, 90)
        p99 = percentile(vals, 99)
        mx = max(vals)
        rows.append(
            f"| {label} | "
            f"{fmt.format(p50)} | {fmt.format(p75)} | {fmt.format(p90)} | "
            f"{fmt.format(p99)} | {fmt.format(mx)} | {len(vals)} |"
        )
    return "\n".join(rows)


# ─── Table B: per-signal outcome ────────────────────────────────────────

def render_table_b(records: list[dict],
                   tape_lookups: dict[int, dict] | None = None) -> str:
    """One row per signal: symbol, prices, terminal state, lag-adjusted limit."""
    headers = [
        "Symbol", "Signal $", "Alpaca ask", "Alpaca bid", "Limit submitted",
        "Terminal state", "IBKR @ terminal", "Lag-adj limit*",
        "First Alpaca print ≥ signal**",
    ]
    rows = ["| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|"]
    for i, rec in enumerate(records):
        sym = rec.get("symbol", "?")
        sp = rec.get("signal_price_ibkr")
        ask = rec.get("alpaca_ask_at_signal")
        bid = rec.get("alpaca_bid_at_signal")
        lim = rec.get("limit_price_submitted")
        term = rec.get("terminal_state") or "?"
        ibk_term = rec.get("ibkr_price_at_terminal")
        lag_lim = lag_adjusted_limit(rec)

        first_print = "—"
        if tape_lookups is not None and i in tape_lookups:
            f = tape_lookups[i]
            if f.get("price") is not None:
                first_print = f"${f['price']:.4f} @ {f['time']}"
            else:
                first_print = "(no print ≥ signal)"

        rows.append(
            f"| {sym} | {fmt_num(sp, '${:.4f}')} | "
            f"{fmt_num(ask, '${:.4f}')} | {fmt_num(bid, '${:.4f}')} | "
            f"{fmt_num(lim, '${:.4f}')} | {term} | "
            f"{fmt_num(ibk_term, '${:.4f}')} | "
            f"{fmt_num(lag_lim, '${:.4f}')} | {first_print} |"
        )
    return "\n".join(rows)


def lag_adjusted_limit(rec: dict, buffer_pct: float = 0.005) -> float | None:
    """Recompute what the limit would have been if calibrated to Alpaca's view.

    For BUY: max(signal_price × (1+buf), alpaca_ask × (1+buf)).
    Returns None when neither input is available.
    """
    sp = rec.get("signal_price_ibkr")
    ask = rec.get("alpaca_ask_at_signal")
    if sp is None and ask is None:
        return None
    candidates = []
    if sp is not None:
        candidates.append(sp * (1 + buffer_pct))
    if ask is not None:
        candidates.append(ask * (1 + buffer_pct))
    return round(max(candidates), 2)


# ─── Table C: lag-adjusted limit simulation ─────────────────────────────

def render_table_c(records: list[dict],
                   tape_lookups: dict[int, dict] | None = None) -> tuple[str, dict]:
    """For each timed-out signal, would the lag-adjusted limit have filled?

    A "would have filled" requires a first_alpaca_print_above_signal at or
    below the lag-adjusted limit. Without tape enrichment we still compute
    a structural answer: lag-adjusted ≥ IBKR-terminal-price ⇒ would have
    chased successfully (proxy).
    """
    timeouts = [(i, r) for i, r in enumerate(records)
                if r.get("terminal_state") in ("timeout", "chase_cap_aborted")]
    headers = [
        "Symbol", "Signal $", "Submitted lim", "Lag-adj lim",
        "IBKR @ terminal", "First Alpaca print",
        "Would have filled?",
    ]
    rows = ["| " + " | ".join(headers) + " |",
            "|" + "|".join(["---"] * len(headers)) + "|"]
    would_fill = 0
    for i, rec in timeouts:
        sp = rec.get("signal_price_ibkr")
        lim = rec.get("limit_price_submitted")
        lag = lag_adjusted_limit(rec)
        ibk_term = rec.get("ibkr_price_at_terminal")
        first_print = None
        first_print_str = "—"
        if tape_lookups is not None and i in tape_lookups:
            f = tape_lookups[i]
            first_print = f.get("price")
            if first_print is not None:
                first_print_str = f"${first_print:.4f} @ {f.get('time')}"
            else:
                first_print_str = "(no print ≥ signal)"

        # Decision rule:
        #   if we have a real tape print: would-fill ⇔ lag-adj ≥ first_print
        #   else: fallback proxy: lag-adj ≥ IBKR-terminal (would have caught
        #         the drift seen in IBKR's feed during the order window)
        decision = "?"
        if lag is not None and first_print is not None:
            decision = "yes" if lag >= first_print else "no"
        elif lag is not None and ibk_term is not None:
            decision = "yes (proxy)" if lag >= ibk_term else "no (proxy)"
        if decision.startswith("yes"):
            would_fill += 1

        rows.append(
            f"| {rec.get('symbol','?')} | {fmt_num(sp,'${:.4f}')} | "
            f"{fmt_num(lim,'${:.4f}')} | {fmt_num(lag,'${:.4f}')} | "
            f"{fmt_num(ibk_term,'${:.4f}')} | {first_print_str} | "
            f"{decision} |"
        )

    return "\n".join(rows), {
        "n_timeouts": len(timeouts),
        "n_would_fill": would_fill,
    }


# ─── Alpaca tape enrichment (optional) ──────────────────────────────────

def fetch_tape_lookups(records: list[dict]) -> dict[int, dict]:
    """For each record, query Alpaca's trades for [signal, terminal] window
    and find the first print at or above signal_price. Returns {idx: {time, price}}.
    Each value's `price` is None when no qualifying print was found.

    Skips entirely on missing SDK/credentials or any API error.
    """
    out: dict[int, dict] = {}
    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockTradesRequest
    except Exception as e:
        print(f"  Tape enrichment unavailable (alpaca SDK import failed: {e})",
              file=sys.stderr)
        return out
    api_key = os.getenv("APCA_API_KEY_ID")
    api_secret = os.getenv("APCA_API_SECRET_KEY")
    if not api_key or not api_secret:
        print("  Tape enrichment skipped (APCA_API_KEY_ID / APCA_API_SECRET_KEY not set)",
              file=sys.stderr)
        return out
    try:
        client = StockHistoricalDataClient(api_key, api_secret)
    except Exception as e:
        print(f"  Tape enrichment skipped (client init failed: {e})", file=sys.stderr)
        return out

    for i, rec in enumerate(records):
        sym = rec.get("symbol")
        sp = rec.get("signal_price_ibkr")
        sig_t = parse_iso(rec.get("signal_time_ibkr_et"))
        term_t = parse_iso(rec.get("terminal_time")) or (
            sig_t + timedelta(minutes=2) if sig_t else None
        )
        if not (sym and sp and sig_t and term_t):
            continue
        try:
            # Cap the window to a reasonable upper bound — anything longer is
            # outside what's relevant for fill-decision analysis.
            window_end = min(term_t, sig_t + timedelta(minutes=5))
            req = StockTradesRequest(
                symbol_or_symbols=sym,
                start=sig_t,
                end=window_end,
                limit=200,
            )
            resp = client.get_stock_trades(req)
            trades = resp.get(sym, []) if hasattr(resp, "get") else []
            found = None
            for t in trades:
                price = float(getattr(t, "price", 0) or 0)
                ts = getattr(t, "timestamp", None)
                if price >= sp:
                    found = {
                        "price": price,
                        "time": ts.isoformat() if ts else None,
                    }
                    break
            if found is None:
                out[i] = {"price": None, "time": None}
            else:
                out[i] = found
        except Exception as e:
            # Per-symbol failure is logged but doesn't abort enrichment.
            print(f"  Tape lookup {sym}: {e}", file=sys.stderr)
            continue
    return out


# ─── Outcome A/B/C call ─────────────────────────────────────────────────

def make_outcome_call(per_metrics: list[dict]) -> str:
    """Compute p90 inter-feed gap and IBKR drift, recommend an outcome."""
    gap_vals = [m["inter_price_gap_pct"] for m in per_metrics
                if m["inter_price_gap_pct"] is not None]
    sig2ack_vals = [m["sig2ack_ms"] for m in per_metrics
                    if m["sig2ack_ms"] is not None]
    drift_vals = [m["ibkr_drift_pct"] for m in per_metrics
                  if m["ibkr_drift_pct"] is not None]

    p90_gap = percentile(gap_vals, 90)
    p90_lat = percentile(sig2ack_vals, 90)
    p90_drift = percentile(drift_vals, 90)
    var_lat = None
    if sig2ack_vals:
        try:
            import statistics
            stdev = statistics.pstdev(sig2ack_vals)
            mean = statistics.mean(sig2ack_vals)
            if mean > 0:
                var_lat = stdev / mean
        except Exception:
            var_lat = None

    # Decision tree, per the directive
    outcome = "A"
    if p90_lat is not None and (p90_lat > 500 or (var_lat is not None and var_lat > 5)):
        outcome = "C"
    elif (p90_gap is not None and abs(p90_gap) >= 0.5) or \
         (p90_lat is not None and p90_lat >= 200) or \
         (p90_drift is not None and abs(p90_drift) >= 0.5):
        outcome = "B"

    lines = [
        f"- p90 inter-feed price gap: {fmt_pct(p90_gap)}",
        f"- p90 signal→ack latency: {fmt_num(p90_lat, '{:.0f} ms')}",
        f"- p90 IBKR drift during entry attempt: {fmt_pct(p90_drift)}",
        f"- signal→ack latency CV (stdev/mean): "
        f"{fmt_num(var_lat, '{:.2f}') if var_lat is not None else '—'}",
        "",
        f"**Recommended outcome: {outcome}**",
    ]
    if outcome == "A":
        lines.append("→ Latency small + consistent. No architectural change "
                     "needed; consider lengthening chase-cap or lag-adjusted "
                     "limit as a light fix.")
    elif outcome == "B":
        lines.append("→ Latency meaningful and consistent. Activate the "
                     "Alpaca-aware limit pricing (Phase 3 helper) by setting "
                     "`WB_ALPACA_AWARE_LIMITS=1` and wire it into entry/exit.")
    else:
        lines.append("→ Latency large or wildly variable. Squeeze execution "
                     "should move to IBKR. Keep Alpaca for WB sub-bot.")
    return "\n".join(lines)


# ─── Per-signal outcome summary ─────────────────────────────────────────

def outcome_summary(records: list[dict]) -> str:
    if not records:
        return "No signals captured."
    counts: dict[str, int] = {}
    for r in records:
        s = r.get("terminal_state") or "unknown"
        counts[s] = counts.get(s, 0) + 1
    parts = [f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])]
    return f"Total signals: {len(records)} — " + ", ".join(parts)


# ─── Report assembly ────────────────────────────────────────────────────

def build_report(date: str, records: list[dict],
                 tape_lookups: dict[int, dict] | None) -> str:
    metrics = [per_signal_metrics(r) for r in records]
    body = []
    body.append(f"# Alpaca Latency Diagnostic — {date}")
    body.append("")
    body.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    body.append("")
    body.append(f"_Source: `logs/{date}_latency_diagnostic.jsonl`_")
    body.append("")
    body.append("## Summary")
    body.append("")
    body.append(outcome_summary(records))
    body.append("")
    body.append("## A. Latency distribution")
    body.append("")
    body.append(render_table_a(metrics))
    body.append("")
    body.append("## B. Per-signal outcomes")
    body.append("")
    body.append(render_table_b(records, tape_lookups))
    body.append("")
    body.append("\\* Lag-adjusted limit = max(signal_price, alpaca_ask) × (1 + 0.5%) — "
                "what the limit *would* have been if priced to Alpaca's view at signal time.")
    body.append("")
    body.append("\\*\\* First Alpaca print ≥ signal_price within [signal_time, terminal_time]. "
                "Empty when tape enrichment was skipped or no qualifying print existed.")
    body.append("")
    body.append("## C. Lag-adjusted-limit simulation (timeouts only)")
    body.append("")
    tbl_c, stats_c = render_table_c(records, tape_lookups)
    body.append(tbl_c)
    body.append("")
    if stats_c["n_timeouts"]:
        pct = stats_c["n_would_fill"] / stats_c["n_timeouts"] * 100.0
        body.append(f"**Recoverable timeouts: {stats_c['n_would_fill']}/"
                    f"{stats_c['n_timeouts']} = {pct:.0f}%** would have "
                    "filled with a lag-adjusted limit (proxy decision rule "
                    "shown in parentheses when no tape print was found).")
    else:
        body.append("No timeout/chase-cap signals in this dataset.")
    body.append("")
    body.append("## Outcome A/B/C call")
    body.append("")
    body.append(make_outcome_call(metrics))
    body.append("")
    body.append("## What this means")
    body.append("")
    body.append(
        "The squeeze entry pipeline measures four moments per signal: "
        "**(1)** when IBKR ticks above the trigger, **(2)** the Alpaca quote "
        "snapshot at that moment, **(3)** when Alpaca acknowledges our order, "
        "**(4)** the terminal state of the order. The latency-distribution "
        "table quantifies each leg; the per-signal outcome table shows what "
        "*actually* happened to each order; the lag-adjusted simulation "
        "quantifies how many timeouts would have been fills if our limit "
        "price had matched Alpaca's view of the market rather than IBKR's."
    )
    body.append("")
    body.append(
        "If p90 inter-feed gap is large and IBKR drift continues *after* "
        "submission, the limit was priced too low to fill — the move ran "
        "past us in Alpaca's order book while we waited. That's outcome B "
        "and Phase 3's `compute_alpaca_aware_limit()` is the fix. If the "
        "variance is enormous or some signals never see any matching tape "
        "print on Alpaca, that's outcome C — the routing partners simply "
        "don't have the book to fill these names, and squeeze execution "
        "must move to IBKR."
    )
    body.append("")
    return "\n".join(body)


# ─── CLI ────────────────────────────────────────────────────────────────

def resolve_input_path(arg: str | None) -> tuple[str, str]:
    """(input_path, date_str)."""
    if arg and os.path.exists(arg) and os.path.isfile(arg):
        # Explicit file path — try to extract date from filename
        base = os.path.basename(arg)
        date = base.split("_")[0] if "_" in base else datetime.now().strftime("%Y-%m-%d")
        return arg, date
    date = arg or datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(REPO, "logs", f"{date}_latency_diagnostic.jsonl")
    return path, date


def main():
    ap = argparse.ArgumentParser(
        description="Analyze Alpaca latency diagnostic JSONL.")
    ap.add_argument("date_or_path", nargs="?",
                    help="YYYY-MM-DD (default: today) or path to JSONL file")
    ap.add_argument("--no-enrich", action="store_true",
                    help="Skip the Alpaca tape lookup enrichment")
    ap.add_argument("--out", default=None,
                    help="Output path (default: cowork_reports/<date>_latency_diagnostic.md)")
    args = ap.parse_args()

    path, date = resolve_input_path(args.date_or_path)
    records = load_jsonl(path)
    print(f"Loaded {len(records)} record(s) from {path}", file=sys.stderr)

    tape_lookups = None
    if records and not args.no_enrich:
        print(f"Running Alpaca tape enrichment for {len(records)} record(s)...",
              file=sys.stderr)
        tape_lookups = fetch_tape_lookups(records)

    report = build_report(date, records, tape_lookups)

    if args.out:
        out_path = args.out
    else:
        cw_dir = os.path.join(REPO, "cowork_reports")
        os.makedirs(cw_dir, exist_ok=True)
        out_path = os.path.join(cw_dir, f"{date}_latency_diagnostic.md")
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Wrote report → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
