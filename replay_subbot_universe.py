#!/usr/bin/env python3
"""replay_subbot_universe.py — sub-bot YTD backtest harness.

Per cowork_reports/2026-05-27_subbot_harness_rebuild_directive.md Phase 2.

Replaces `replay_live_universe.py` for sub-bot strategy research. Key
differences from the legacy harness:

  1. Universe source: reads `scanner_results/<date>.json` (156 snapshots/day
     at 5-min cadence) instead of the MAIN BOT's `logs/<date>_daily.log`.
     This captures the FULL sub-bot universe (100+ symbols/day) instead of
     the main bot's narrow 4-10 symbol focus list.

  2. Simulator: invokes `simulate_subbot.py` (which subclasses the live
     sub-bot decision tree from `move_strike_subbot.py`) instead of
     `simulate.py` (squeeze main-bot logic with MOVE_STRIKE bolted on).
     No squeeze-tick-exit fallthrough, no parallel HWM implementation
     drift, regime_shift threshold defaults match live.

  3. Per-symbol discovery windows: computed from the scanner_results
     snapshots that include the symbol. First snapshot containing the
     symbol's candidate row → start of replay window; last such snapshot
     → end. This matches live behavior: the sub-bot only sees ticks for
     symbols the engine is currently publishing.

Usage:
    ./venv/bin/python replay_subbot_universe.py --start 2026-05-27 --end 2026-05-27
    ./venv/bin/python replay_subbot_universe.py --start 2026-05-22 --end 2026-05-26 \\
        --label "DAYS_22_TO_26"

Env vars (propagated to simulate_subbot.py via subprocess env):
    All WB_BT_MOVE_*, WB_REGIME_SHIFT_*, WB_MOVE_FADE_* vars from move_strike_subbot.py.
    Set them on the command line just like the legacy harness:
      WB_REGIME_SHIFT_ENABLED=1 WB_MOVE_FADE_VWAP_ENABLED=1 \\
        ./venv/bin/python replay_subbot_universe.py --start ... --end ...
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

WORKDIR = Path(__file__).parent.resolve()

# Trade-line format emitted by simulate_subbot.py — same regex as
# replay_live_universe.py used for simulate.py output.
# 2026-05-28 (Phase 3): optional trailing `setup=<type>` for FT attribution.
TRADE_LINE_RE = re.compile(
    r"^\s+\d+\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
    r"([\d.]+)\s+([\d.]+)\s+(\S+)\s+([-+]?\d+)(?:\s+setup=(\S+))?"
)


def daterange(start: str, end: str):
    d0 = datetime.strptime(start, "%Y-%m-%d").date()
    d1 = datetime.strptime(end, "%Y-%m-%d").date()
    while d0 <= d1:
        yield d0.strftime("%Y-%m-%d")
        d0 += timedelta(days=1)


SUBBOT_NEW_SYM_RE = re.compile(
    r"\[MOVE_SUB(?:_\w)?\] \[(\d{2}:\d{2}:\d{2})\] new symbol ([A-Z][A-Z0-9]*)"
)


def compute_symbol_windows_from_subbot_log(log_dir: Path, date: str,
                                            end_cap: str) -> dict[str, tuple[str, str]]:
    """Primary universe source: parse sub-bot log "new symbol X" lines.

    Sub-bot logs are the authoritative record of which symbols the live
    sub-bot subscribed to during the session. Each line is emitted when
    the bot's `_ensure_symbol` runs for a new symbol — i.e., when the
    engine socket first delivered a tick for that symbol.

    Window: first-seen time → end_cap. Sub-bot doesn't unsubscribe
    intraday, so the symbol remains in the universe for the rest of
    the session.

    Returns {} if no sub-bot log exists for the date — caller should
    fall back to scanner_results.
    """
    # Try Variant A first (control, no fade-gate skew); fall back B then C.
    for variant in ("A", "B", "C"):
        log_path = log_dir / f"{date}_move_strike_subbot_{variant}.log"
        if not log_path.exists():
            continue
        first: dict[str, str] = {}
        try:
            with open(log_path, "r", errors="replace") as f:
                for line in f:
                    m = SUBBOT_NEW_SYM_RE.search(line)
                    if not m:
                        continue
                    t_hhmmss, sym = m.group(1), m.group(2)
                    if sym not in first:
                        first[sym] = t_hhmmss[:5]  # HH:MM
        except Exception:
            continue
        if first:
            return {s: (first[s], end_cap) for s in first}
    return {}


def compute_symbol_windows_from_scanner(scanner_json_path: Path) -> dict[str, tuple[str, str]]:
    """Fallback universe source: parse scanner_results/<date>.json.

    Returns {symbol: (first_HH:MM, last_HH:MM)} for every symbol that
    appeared in any snapshot's `candidates` list. Less complete than
    sub-bot log — scanner_results only captures pre-market gapper-style
    candidates, not the full engine-published universe.
    """
    if not scanner_json_path.exists():
        return {}
    try:
        with open(scanner_json_path, "r") as f:
            payload = json.load(f)
    except Exception:
        return {}
    if not isinstance(payload, list) or not payload:
        return {}

    first: dict[str, str] = {}
    last: dict[str, str] = {}

    # Two on-disk formats:
    #   A (current): list of SNAPSHOTS, each {scan_time_et, candidates:[...]}
    #   B (pre-May): a FLAT list of candidate dicts — no snapshot wrapper,
    #                no scan_time_et; the whole file is one scan.
    # Before 2026-07-21 format B silently parsed to {} (every row failed the
    # scan_time_et check), so the caller fell through to the raw tick_cache
    # glob. That is how 63% of YTD days ended up replaying EVERY symbol in
    # the cache instead of the scanner's actual picks — e.g. 2026-01-16 had
    # a 1-symbol scanner list but the sim traded all 14 cached symbols.
    is_snapshots = any(
        isinstance(s, dict) and "candidates" in s for s in payload
    )

    if is_snapshots:
        for snap in payload:
            if not isinstance(snap, dict):
                continue
            scan_time = snap.get("scan_time_et", "")
            if len(scan_time) < 5:
                continue
            hhmm = scan_time[:5]
            for cand in snap.get("candidates", []) or []:
                sym = cand.get("symbol") if isinstance(cand, dict) else None
                if not sym:
                    continue
                if sym not in first:
                    first[sym] = hhmm
                last[sym] = hhmm
    else:
        for cand in payload:
            if not isinstance(cand, dict):
                continue
            sym = cand.get("symbol")
            if not sym:
                continue
            # Flat rows carry their own discovery stamp.
            hhmm = str(cand.get("sim_start") or cand.get("first_seen_et")
                       or cand.get("discovery_time") or "09:30")[:5]
            if len(hhmm) < 5:
                hhmm = "09:30"
            if sym not in first or hhmm < first[sym]:
                first[sym] = hhmm
            last[sym] = "16:00"

    return {s: (first[s], last[s]) for s in first}


def compute_symbol_windows_from_tick_cache(date: str, start_default: str,
                                           end_cap: str) -> dict[str, tuple[str, str]]:
    """Fallback universe source #3: list tick_cache/<date>/*.json.gz files.

    Use case: pre-May days when scanner_results files exist but are empty
    (the YTD scanner-snapshot logger wasn't capturing candidates back then)
    and no sub-bot log exists (sub-bots are May-onward). Tick-cache file
    presence is the most reliable signal that the symbol was subscribed
    that day.

    Window: full session [start_default, end_cap]. We don't know the
    actual first-tick time per symbol without reading each file, and the
    simulate_subbot pre-window seeding handles arbitrary start times
    anyway.
    """
    cache_dir = WORKDIR / "tick_cache" / date
    if not cache_dir.is_dir():
        return {}
    syms: dict[str, tuple[str, str]] = {}
    for p in cache_dir.glob("*.json.gz"):
        # p.stem of "CYCN.json.gz" is "CYCN.json" — strip the trailing .json.
        sym = p.name[:-len(".json.gz")]
        if sym:
            syms[sym] = (start_default, end_cap)
    return syms


# ─── Data-provenance guards (2026-07-21 audit) ──────────────────────────
#
# FIRST_LIVE_CAPTURE_DATE — before this, tick_cache holds a bulk BACKFILL,
# not a live recording. Every 2026-01-02..2026-03-23 cache file was written
# in one pass at 2026-03-25 13:15; the repo's first commit is 2026-02-26,
# so no live scanner or bot existed to produce those days. `scanner_results`
# for those dates were likewise reconstructed after the fact (the
# 2026-01-16 file was written 2026-05-06).
FIRST_LIVE_CAPTURE_DATE = "2026-03-24"
# FIRST_SUBBOT_LOG_DATE — before this there is no sub-bot log, so no record
# of which symbols the sub-bot actually saw. This is the only universe
# source that is genuinely authoritative.
FIRST_SUBBOT_LOG_DATE = "2026-05-20"
# The raw tick_cache glob is NOT a watchlist — it is every symbol the engine
# ever subscribed to that day (100-144 on live days). Using it silently
# overstates how selective the strategy was. Opt in explicitly.
ALLOW_GLOB_UNIVERSE = os.getenv("WB_REPLAY_ALLOW_GLOB_UNIVERSE", "0") == "1"


def compute_symbol_windows(date: str, end_cap: str,
                           tick_cache_start: str = "07:00") -> tuple[dict[str, tuple[str, str]], str]:
    """Combined universe source. Returns (windows, source_name)."""
    log_dir = WORKDIR / "logs"
    windows = compute_symbol_windows_from_subbot_log(log_dir, date, end_cap)
    if windows:
        return windows, "subbot_log"
    scanner_json = WORKDIR / "scanner_results" / f"{date}.json"
    windows = compute_symbol_windows_from_scanner(scanner_json)
    if windows:
        return windows, "scanner_results"
    # Last resort: enumerate tick_cache/<date>/*.json.gz. This is NOT a
    # watchlist — see ALLOW_GLOB_UNIVERSE above. Gated OFF so a day with no
    # real universe is SKIPPED rather than silently replaying everything.
    windows = compute_symbol_windows_from_tick_cache(date, tick_cache_start, end_cap)
    if windows:
        if not ALLOW_GLOB_UNIVERSE:
            return {}, "skipped_no_universe"
        return windows, "tick_cache"
    return {}, "none"


def run_sim_for_symbol(
    symbol: str, date: str, start_et: str, end_et: str,
    slippage: float = 0.07, extra_env: dict | None = None,
    timeout_sec: int = 180, bars: bool = False, variant: str = "A",
) -> list[dict]:
    """Run simulate_subbot.py for one (symbol, date, window) tuple.
    Returns list of trade dicts (matches TRADE_LINE_RE captures)."""
    cmd = [
        sys.executable, str(WORKDIR / "simulate_subbot.py"),
        symbol, date, start_et, end_et,
        "--ticks", "--tick-cache", "tick_cache/",
        "--slippage", str(slippage), "--no-fundamentals",
    ]
    if bars:
        cmd += ["--bars", "--variant", variant]
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout_sec,
            cwd=str(WORKDIR), env=env,
        )
    except subprocess.TimeoutExpired:
        print(f"  [{symbol}] {date} sim TIMEOUT after {timeout_sec}s", flush=True)
        return []
    # Surface non-zero exit codes — these are real failures the legacy
    # replay_live_universe harness silently swallowed.
    if result.returncode != 0:
        # Trim stderr to first 200 chars for legibility.
        err_excerpt = (result.stderr or "")[:200].replace("\n", " | ")
        print(f"  [{symbol}] {date} sim exit={result.returncode} err={err_excerpt}",
              flush=True)
        # Still try to parse any trades that did make it to stdout.

    trades = []
    for line in (result.stdout + (result.stderr or "")).splitlines():
        m = TRADE_LINE_RE.match(line)
        if m:
            trades.append({
                "time": m.group(1),
                "entry": float(m.group(2)),
                "stop": float(m.group(3)),
                "r": float(m.group(4)),
                "score": float(m.group(5)),
                "exit": float(m.group(6)),
                "reason": m.group(7),
                "pnl": int(m.group(8)),
                "setup": m.group(9) if m.lastindex and m.lastindex >= 9 else None,
            })
    return trades


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--start", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--end", required=True, help="YYYY-MM-DD inclusive")
    p.add_argument("--label", default="subbot_replay",
                   help="Label for report file naming")
    p.add_argument("--slippage", type=float, default=0.07)
    p.add_argument("--end-cap", default="20:00",
                   help="Cap window end at this ET time (default 20:00 — sub-bot "
                        "trades through evening session)")
    p.add_argument("--max-symbols-per-day", type=int, default=0,
                   help="If >0, cap symbols replayed per day (debug only)")
    p.add_argument("--bars", action="store_true",
                   help="Replay from the recorded live bar_stream (trade-for-trade "
                        "parity) instead of the full tick cache. Requires a sub-bot "
                        "bar_stream for the day.")
    p.add_argument("--variant", default="A",
                   help="bar_stream variant suffix (A or C) when --bars is set.")
    args = p.parse_args()

    overall_trades: list[dict] = []
    per_day: list[dict] = []
    skipped: dict[str, list[str]] = defaultdict(list)

    source_counts: dict[str, int] = defaultdict(int)

    for date in daterange(args.start, args.end):
        windows, source = compute_symbol_windows(date, args.end_cap)
        source_counts[source] += 1
        if source == "skipped_no_universe":
            print(f"[{date}] SKIPPED — no real universe (only a raw tick_cache "
                  f"glob, which is every symbol the engine subscribed to, not "
                  f"a watchlist). Set WB_REPLAY_ALLOW_GLOB_UNIVERSE=1 to "
                  f"replay it anyway.", flush=True)
            continue
        if not windows:
            print(f"[{date}] no universe source available — skip", flush=True)
            continue
        if source == "scanner_results":
            print(f"[{date}] universe from scanner_results "
                  f"(no sub-bot log — coverage may be incomplete)", flush=True)
        if source == "tick_cache":
            print(f"[{date}] ⚠️  universe from RAW TICK_CACHE GLOB "
                  f"({len(windows)} symbols) — this is NOT a watchlist; "
                  f"selectivity is overstated.", flush=True)
        # Provenance warnings — see the constants above for the evidence.
        if date < FIRST_LIVE_CAPTURE_DATE:
            print(f"[{date}] ⚠️  PRE-LIVE DATA — tick_cache for this date is a "
                  f"bulk backfill written 2026-03-25, not a live recording "
                  f"(repo's first commit is 2026-02-26). Treat as "
                  f"illustrative, not evidence.", flush=True)
        elif date < FIRST_SUBBOT_LOG_DATE:
            print(f"[{date}] ⚠️  no sub-bot log exists before "
                  f"{FIRST_SUBBOT_LOG_DATE} — universe is inferred, not the "
                  f"symbol set the sub-bot actually saw.", flush=True)

        # Optional cap for fast iteration
        if args.max_symbols_per_day > 0:
            sorted_syms = sorted(windows.keys())[: args.max_symbols_per_day]
            windows = {s: windows[s] for s in sorted_syms}

        day_pnl = 0
        day_trades_count = 0
        day_syms_traded: set[str] = set()
        day_syms_skipped: list[str] = []

        for sym, (t0, t1) in sorted(windows.items()):
            # Cap window end at end_cap (e.g., evening session cutoff).
            end_capped = min(t1, args.end_cap)
            if t0 >= end_capped:
                day_syms_skipped.append(f"{sym} (window after cap)")
                continue
            if not args.bars:
                tick_cache_path = WORKDIR / "tick_cache" / date / f"{sym}.json.gz"
                if not tick_cache_path.exists():
                    day_syms_skipped.append(f"{sym} (no tick cache)")
                    continue

            trades = run_sim_for_symbol(
                sym, date, t0, end_capped, slippage=args.slippage,
                bars=args.bars, variant=args.variant,
            )
            for t in trades:
                t["symbol"] = sym
                t["date"] = date
                day_pnl += t["pnl"]
                day_trades_count += 1
                day_syms_traded.add(sym)
                overall_trades.append(t)

        per_day.append({
            "date": date,
            "trades": day_trades_count,
            "pnl": day_pnl,
            "symbols_watched": len(windows),
            "symbols_traded": len(day_syms_traded),
            "symbols_skipped": len(day_syms_skipped),
        })
        skipped[date] = day_syms_skipped
        print(f"[{date}] {day_trades_count} trades, P&L=${day_pnl:+,} "
              f"({len(windows)} symbols watched, {len(day_syms_traded)} traded, "
              f"{len(day_syms_skipped)} skipped)", flush=True)

    # --- Aggregate summary ---
    total_pnl = sum(t["pnl"] for t in overall_trades)
    wins = [t for t in overall_trades if t["pnl"] > 0]
    losses = [t for t in overall_trades if t["pnl"] <= 0]

    print("")
    print(f"=== {args.label} | {args.start} → {args.end} ===")
    print(f"Total: {len(overall_trades)} trades, "
          f"{len(wins)}W / {len(losses)}L "
          f"({100*len(wins)/max(1,len(overall_trades)):.0f}% WR)")
    print(f"Gross P&L: ${total_pnl:+,}")
    if wins:
        print(f"Avg winner: ${sum(t['pnl'] for t in wins)//len(wins):+,}")
    if losses:
        print(f"Avg loser:  ${sum(t['pnl'] for t in losses)//len(losses):+,}")
    print("")
    print("Per-day:")
    for d in per_day:
        print(f"  {d['date']}: {d['trades']} trades, ${d['pnl']:+,} "
              f"({d['symbols_watched']} watched, {d['symbols_traded']} traded, "
              f"{d['symbols_skipped']} skipped)")

    # --- Universe provenance (2026-07-21 audit) ---
    # Recorded in the output so a result can never again be quoted without
    # the caveat about where its universe came from.
    print("")
    print("Universe provenance:")
    for src, n in sorted(source_counts.items(), key=lambda kv: -kv[1]):
        note = {
            "subbot_log": "authoritative — what the sub-bot actually saw",
            "scanner_results": "scanner picks (no sub-bot log)",
            "tick_cache": "RAW GLOB — not a watchlist, selectivity overstated",
            "skipped_no_universe": "skipped: no real universe available",
            "none": "no data",
        }.get(src, "")
        print(f"  {src:22} {n:4} day(s)   {note}")

    # --- Write JSON detail ---
    out_path = WORKDIR / "backtest_status" / f"replay_subbot_{args.label}_{args.start}_{args.end}.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({
            "label": args.label, "start": args.start, "end": args.end,
            "trades": overall_trades, "per_day": per_day,
            "skipped_by_date": dict(skipped),
            "universe_sources": dict(source_counts),
            "badprint_filter": os.getenv("WB_SIM_BADPRINT_FILTER", "0"),
            "allow_glob_universe": os.getenv("WB_REPLAY_ALLOW_GLOB_UNIVERSE", "0"),
            "total_pnl": total_pnl,
        }, f, indent=2)
    print(f"\nDetail: {out_path}")


if __name__ == "__main__":
    main()
