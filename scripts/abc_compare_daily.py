#!/usr/bin/env python3
"""abc_compare_daily.py — A/B/C fade-gate test daily comparison report.

Per cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md.

For each of the 3 variant sub-bots (A=control, B=VWAP, C=BodyCV):
  - Pull Alpaca paper account equity + day's realized P&L
  - Parse the variant's log file (logs/<DATE>_move_strike_subbot_<X>.log)
  - Count trades, fade-gate blocks, regime-shift fires

Writes: cowork_reports/<DATE>_abc_daily_report.md
Updates: cowork_reports/abc_running_totals.json (cumulative)

Usage:
    ./venv/bin/python scripts/abc_compare_daily.py           # today
    ./venv/bin/python scripts/abc_compare_daily.py 2026-05-26
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, date as date_t
from pathlib import Path

from dotenv import dotenv_values

WORKDIR = Path(__file__).parent.parent.resolve()
ENV_PATH = WORKDIR / ".env"
LOG_DIR = WORKDIR / "logs"
REPORT_DIR = WORKDIR / "cowork_reports"
RUNNING_TOTALS_PATH = REPORT_DIR / "abc_running_totals.json"

VARIANTS = [
    ("A", "control",  "APCA_API_KEY_ID",      "APCA_API_SECRET_KEY"),
    ("B", "V1 VWAP",  "MAIN_APCA_API_KEY_ID", "MAIN_APCA_API_SECRET_KEY"),
    ("C", "V4 BodyCV", "VARIANT_C_APCA_API_KEY_ID", "VARIANT_C_APCA_API_SECRET_KEY"),
]


def get_alpaca_day_stats(api_key: str, api_secret: str, target_date: str) -> dict:
    """Pull equity + day's realized P&L via Alpaca get_account.

    Returns: {equity, day_pnl, error?}. Trade counts come from the log
    file (more reliable than the API activities endpoint, which varies
    by alpaca-py version).
    """
    try:
        from alpaca.trading.client import TradingClient
    except Exception as e:
        return {"error": f"alpaca-py not available: {e}"}
    if not api_key or not api_secret:
        return {"error": "no_keys"}
    try:
        client = TradingClient(api_key, api_secret, paper=True)
        account = client.get_account()
        equity = float(account.equity or 0)
        last_equity = float(account.last_equity or 0)
        day_pnl = equity - last_equity if last_equity else 0
        # Number of orders submitted for the day (any status). Filtered
        # client-side because Alpaca's get_orders status filter is
        # version-dependent.
        try:
            from alpaca.trading.requests import GetOrdersRequest
            req = GetOrdersRequest(status="all", limit=500)
            orders = client.get_orders(filter=req)
        except Exception:
            orders = []
        day_orders = [
            o for o in orders
            if hasattr(o, "submitted_at")
            and getattr(o, "submitted_at", None) is not None
            and str(o.submitted_at)[:10] == target_date
        ]
        buy_orders = sum(1 for o in day_orders
                         if str(getattr(o, "side", "")).lower().endswith("buy"))
        return {
            "equity": equity,
            "last_equity": last_equity,
            "day_pnl": day_pnl,
            "day_orders": len(day_orders),
            "day_buy_orders": buy_orders,
        }
    except Exception as e:
        return {"error": str(e)}


# Log-parsing regexes — match move_strike_subbot.py log output.
ENTRY_LINE_RE = re.compile(
    r"\[MOVE_SUB(?:_\w)?\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
    r"(🟩 ENTRY|🚀 ENTRY REGIME_SHIFT)\s+(?:REENTRY\([^)]*\)\s+)?(\w+)"
)
EXIT_LINE_RE = re.compile(
    r"\[MOVE_SUB(?:_\w)?\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
    r"🟥 EXIT (?:REGIME_SHIFT |MOVE_STRIKE )?(\w+) qty=(\d+) "
    r"limit=\$[\d.]+ \(ref=\$([\d.]+)\) reason=(\S+)"
)
PARTIAL_LINE_RE = re.compile(
    r"\[MOVE_SUB(?:_\w)?\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
    r"🎯 PARTIAL REGIME_SHIFT (\w+) qty=(\d+)"
)
FADE_BLOCK_LINE_RE = re.compile(
    r"\[MOVE_SUB(?:_\w)?\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
    r"MOVE_FADE_GATE_BLOCK (\w+) reason=(\S+)"
)
REGIME_TRIGGER_RE = re.compile(
    r"\[MOVE_SUB(?:_\w)?\] \[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\] "
    r"REGIME_SHIFT_TRIGGER (\w+) bar_body=\$([\d.]+) baseline=\$([\d.]+) "
    r"ratio=([\d.]+)"
)


def parse_log(log_path: Path) -> dict:
    """Return {entries, exits, fade_blocks_unique_syms, fade_blocks_total,
                regime_triggers, partials, symbols_traded}."""
    if not log_path.exists():
        return {"error": "no_log", "log_path": str(log_path)}
    entries = []
    exits = []
    fade_blocks = []
    regime_triggers = []
    partials = []
    try:
        with open(log_path, "r", errors="replace") as f:
            for line in f:
                if m := ENTRY_LINE_RE.search(line):
                    entries.append({"type": m.group(1), "symbol": m.group(2)})
                elif m := EXIT_LINE_RE.search(line):
                    exits.append({"symbol": m.group(1), "qty": int(m.group(2)),
                                  "reason": m.group(4)})
                elif m := FADE_BLOCK_LINE_RE.search(line):
                    fade_blocks.append({"symbol": m.group(1), "reason": m.group(2)})
                elif m := REGIME_TRIGGER_RE.search(line):
                    regime_triggers.append({
                        "symbol": m.group(1),
                        "body": float(m.group(2)),
                        "ratio": float(m.group(4)),
                    })
                elif m := PARTIAL_LINE_RE.search(line):
                    partials.append({"symbol": m.group(1), "qty": int(m.group(2))})
    except Exception as e:
        return {"error": str(e), "log_path": str(log_path)}
    return {
        "entries": len(entries),
        "regime_entries": sum(1 for e in entries if "REGIME_SHIFT" in e["type"]),
        "movestrike_entries": sum(1 for e in entries if "🟩 ENTRY" in e["type"]),
        "exits": len(exits),
        "fade_blocks_total": len(fade_blocks),
        "fade_blocks_unique_syms": len({b["symbol"] for b in fade_blocks}),
        "regime_triggers": len(regime_triggers),
        "partials": len(partials),
        "symbols_traded": sorted({e["symbol"] for e in entries}),
        "log_path": str(log_path),
    }


SUBSCRIPTION_AUDIT_PREFIX = "SUBSCRIPTION_AUDIT "


def parse_subscription_audit(log_path: Path) -> dict:
    """Scan the main bot daily log for SUBSCRIPTION_AUDIT JSON lines.
    Returns aggregated per-symbol stats for the Data Quality Audit
    section of the report. Per cowork_reports/2026-05-26_subscription_watchdog_directive.md.
    """
    if not log_path.exists():
        return {"error": "no_main_bot_log", "log_path": str(log_path)}

    per_sym: dict[str, dict] = {}
    total_lines = 0
    parse_errors = 0
    try:
        with open(log_path, "r", errors="replace") as f:
            for line in f:
                idx = line.find(SUBSCRIPTION_AUDIT_PREFIX)
                if idx < 0:
                    continue
                payload_str = line[idx + len(SUBSCRIPTION_AUDIT_PREFIX):].strip()
                try:
                    p = json.loads(payload_str)
                except Exception:
                    parse_errors += 1
                    continue
                total_lines += 1
                sym = p.get("sym")
                if not sym:
                    continue
                rec = per_sym.setdefault(sym, {
                    "ok": 0, "suspect": 0, "wedge": 0,
                    "min_ratio_obs_to_truth": None,
                    "max_ratio_obs_to_median": None,
                    "last_truth_v_5m": None,
                    "last_obs_v_5m": None,
                })
                status = p.get("status", "")
                if status == "OK":
                    rec["ok"] += 1
                elif status == "HEURISTIC_SUSPECT":
                    rec["suspect"] += 1
                elif status == "DIRECT_QUERY_WEDGE":
                    rec["wedge"] += 1
                elif status == "DIRECT_QUERY_OK":
                    rec["ok"] += 1
                r_obs_truth = p.get("ratio_obs_to_truth")
                if r_obs_truth is not None:
                    cur = rec["min_ratio_obs_to_truth"]
                    if cur is None or r_obs_truth < cur:
                        rec["min_ratio_obs_to_truth"] = r_obs_truth
                    rec["last_truth_v_5m"] = p.get("truth_v_5m")
                r_obs_med = p.get("ratio_obs_to_median")
                if r_obs_med is not None:
                    cur = rec["max_ratio_obs_to_median"]
                    if cur is None or r_obs_med > cur:
                        rec["max_ratio_obs_to_median"] = r_obs_med
                if p.get("obs_v_5m") is not None:
                    rec["last_obs_v_5m"] = p["obs_v_5m"]
    except Exception as e:
        return {"error": str(e), "log_path": str(log_path)}

    suspect_syms = sorted(s for s, r in per_sym.items() if r["suspect"] > 0)
    wedge_syms = sorted(s for s, r in per_sym.items() if r["wedge"] > 0)
    return {
        "per_sym": per_sym,
        "total_audit_lines": total_lines,
        "parse_errors": parse_errors,
        "suspect_symbols": suspect_syms,
        "wedge_symbols": wedge_syms,
        "any_wedge": bool(wedge_syms),
        "log_path": str(log_path),
    }


def load_running_totals() -> dict:
    if RUNNING_TOTALS_PATH.exists():
        with open(RUNNING_TOTALS_PATH) as f:
            return json.load(f)
    return {"days": []}


def save_running_totals(data: dict) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(RUNNING_TOTALS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def fmt_money(x):
    if x is None:
        return "n/a"
    sign = "+" if x >= 0 else "-"
    return f"{sign}${abs(x):,.2f}"


def main():
    target_date = sys.argv[1] if len(sys.argv) > 1 else date_t.today().isoformat()
    env = dotenv_values(ENV_PATH) if ENV_PATH.exists() else {}
    # Per-variant data
    rows = []
    for suffix, label, key_var, secret_var in VARIANTS:
        key = env.get(key_var, "")
        secret = env.get(secret_var, "")
        log_path = LOG_DIR / f"{target_date}_move_strike_subbot_{suffix}.log"
        alpaca = get_alpaca_day_stats(key, secret, target_date)
        logs = parse_log(log_path)
        rows.append({
            "suffix": suffix, "label": label,
            "alpaca": alpaca, "logs": logs,
        })

    # Subscription watchdog audit (main bot log, not per-variant)
    main_bot_log = LOG_DIR / f"{target_date}_daily.log"
    sub_audit = parse_subscription_audit(main_bot_log)

    # Build report
    lines = []
    lines.append(f"# A/B/C Daily Report — {target_date}")
    lines.append("")
    lines.append("Per `cowork_reports/2026-05-23_live_abc_fade_gate_test_directive.md`.")
    lines.append("")
    # Top-line data-quality flag — banner only if direct-query wedges occurred.
    if sub_audit.get("any_wedge"):
        lines.append(
            "⚠️ **DATA QUALITY DEGRADED** — one or more symbols had "
            "`DIRECT_QUERY_WEDGE` audit events today. Variant comparison "
            "below reflects partial data. See Data Quality Audit section."
        )
        lines.append("")
    lines.append("## Account / log snapshot")
    lines.append("")
    lines.append("| Variant | Label | Equity | Day P&L | Day orders (buy/total) | Log entries | Fade blocks | Regime triggers |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
    for r in rows:
        a = r["alpaca"]
        l = r["logs"]
        equity = fmt_money(a.get("equity"))
        day_pnl = fmt_money(a.get("day_pnl"))
        orders = "n/a"
        if "day_orders" in a:
            orders = f"{a['day_buy_orders']} / {a['day_orders']}"
        if a.get("error"):
            equity = day_pnl = orders = f"err: {a['error'][:20]}"
        log_entries = l.get("entries", "—")
        fade_blocks = l.get("fade_blocks_total", "—")
        regime = l.get("regime_triggers", "—")
        lines.append(
            f"| {r['suffix']} | {r['label']} | {equity} | {day_pnl} | "
            f"{orders} | {log_entries} | {fade_blocks} | {regime} |"
        )
    lines.append("")

    # Per-variant detail
    for r in rows:
        l = r["logs"]
        lines.append(f"### Variant {r['suffix']} — {r['label']}")
        lines.append("")
        if l.get("error"):
            lines.append(f"- log error: `{l['error']}` (path: `{l.get('log_path')}`)")
        else:
            lines.append(f"- MOVE_STRIKE entries: {l.get('movestrike_entries', 0)}")
            lines.append(f"- REGIME_SHIFT entries: {l.get('regime_entries', 0)}")
            lines.append(f"- Exits: {l.get('exits', 0)}")
            lines.append(f"- Regime-shift partials fired: {l.get('partials', 0)}")
            lines.append(f"- Fade-gate blocks: {l.get('fade_blocks_total', 0)} "
                         f"({l.get('fade_blocks_unique_syms', 0)} unique symbols)")
            syms = l.get("symbols_traded", [])
            if syms:
                lines.append(f"- Symbols traded: {', '.join(syms)}")
        lines.append("")

    # Data Quality Audit (subscription watchdog ingest)
    lines.append("## Data Quality Audit")
    lines.append("")
    if sub_audit.get("error"):
        lines.append(f"- audit log error: `{sub_audit['error']}` "
                     f"(path: `{sub_audit.get('log_path')}`)")
        lines.append("")
    elif sub_audit.get("total_audit_lines", 0) == 0:
        lines.append("- No `SUBSCRIPTION_AUDIT` lines found in the main bot log. "
                     "Watchdog likely disabled (`WB_SUB_WATCHDOG_ENABLED=0`) "
                     "or bot not started.")
        lines.append("")
    else:
        suspect_syms = sub_audit.get("suspect_symbols", [])
        wedge_syms = sub_audit.get("wedge_symbols", [])
        lines.append(
            f"- Audit lines parsed: {sub_audit['total_audit_lines']}"
            + (f" (parse errors: {sub_audit['parse_errors']})"
               if sub_audit.get("parse_errors") else "")
        )
        lines.append(f"- Symbols flagged HEURISTIC_SUSPECT: {len(suspect_syms)}")
        lines.append(f"- Symbols with DIRECT_QUERY_WEDGE events: {len(wedge_syms)}")
        lines.append("")
        # Per-symbol detail table — sorted by wedge count desc, then suspect count desc.
        per_sym = sub_audit.get("per_sym", {}) or {}
        flagged = [
            (s, r) for s, r in per_sym.items()
            if r["suspect"] > 0 or r["wedge"] > 0
        ]
        if flagged:
            flagged.sort(key=lambda x: (-x[1]["wedge"], -x[1]["suspect"], x[0]))
            lines.append("| Symbol | OK | Suspect | Wedge | Min obs/truth | Last obs vs truth |")
            lines.append("|---|---:|---:|---:|---:|---|")
            for sym, r in flagged:
                obs_truth = (
                    "n/a" if r["min_ratio_obs_to_truth"] is None
                    else f"{r['min_ratio_obs_to_truth']:.3f}"
                )
                last_pair = "n/a"
                if r.get("last_obs_v_5m") is not None and r.get("last_truth_v_5m") is not None:
                    last_pair = f"{r['last_obs_v_5m']} / {r['last_truth_v_5m']}"
                lines.append(
                    f"| {sym} | {r['ok']} | {r['suspect']} | {r['wedge']} | "
                    f"{obs_truth} | {last_pair} |"
                )
            lines.append("")
        else:
            lines.append("All symbols clean — no `SUBSCRIPTION_AUDIT` flags fired today.")
            lines.append("")

    # Running totals
    totals = load_running_totals()
    day_record = {
        "date": target_date,
        "variants": {
            r["suffix"]: {
                "day_pnl": r["alpaca"].get("day_pnl", 0),
                "equity": r["alpaca"].get("equity"),
                "entries": r["logs"].get("entries", 0),
                "fade_blocks": r["logs"].get("fade_blocks_total", 0),
            }
            for r in rows
        },
    }
    # Replace existing entry for this date if any
    totals["days"] = [d for d in totals["days"] if d["date"] != target_date]
    totals["days"].append(day_record)
    totals["days"].sort(key=lambda d: d["date"])
    save_running_totals(totals)

    # Cumulative totals
    cum = {"A": 0.0, "B": 0.0, "C": 0.0}
    for d in totals["days"]:
        for s, v in d["variants"].items():
            cum[s] += float(v.get("day_pnl") or 0)
    lines.append("## Running totals (cumulative)")
    lines.append("")
    lines.append("| Variant | Days | Cumulative P&L |")
    lines.append("|---|---:|---:|")
    n_days = len(totals["days"])
    for s in ["A", "B", "C"]:
        lines.append(f"| {s} | {n_days} | {fmt_money(cum[s])} |")
    lines.append("")

    out_path = REPORT_DIR / f"{target_date}_abc_daily_report.md"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Wrote: {out_path}")
    # Also print to stdout for cron tail
    print("\n".join(lines))


if __name__ == "__main__":
    main()
