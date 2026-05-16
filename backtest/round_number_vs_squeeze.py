"""Cross-strategy comparison: Round Number vs existing Squeeze.

For each shared (symbol, date) where BOTH strategies fire, compare:
  - Whose entry was earlier in the day
  - Hold duration
  - Outcome quality (R-multiple, exit reason)

Universe overlap analysis: how often does Round Number signal on a
symbol/day that Squeeze ALSO traded that day? In practice these two
strategies operate on largely disjoint universes (squeeze hunts
small-cap gappers $2-$20 with <15M float; round number runs $10-$300
with $20M+ float), so the overlap is expected to be small.

This module reads:
  - Round Number trade log from backtest_archive/round_number_*/trades.json
  - Squeeze trade log from existing backtest result JSONs

Squeeze backtest result JSON shape (per ytd_v2_backtest_state_baseline.json):
  {
    "DATE": {
      "trades": [
        {"symbol": "...", "entry_ts": "...", "exit_ts": "...",
         "entry": ..., "exit": ..., "pnl": ..., ...},
        ...
      ],
      ...
    },
    ...
  }
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
log = logging.getLogger("round_number_vs_squeeze")


def load_round_number_trades(path: Path) -> pd.DataFrame:
    """Load Round Number trade log from a backtest output dir."""
    records = json.loads(path.read_text())
    if not records:
        return pd.DataFrame(columns=[
            "symbol", "session_date", "tier", "entry_ts", "exit_ts",
            "side", "r_multiple", "exit_reason", "pattern",
        ])
    df = pd.DataFrame(records)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
    return df


def load_squeeze_trades_from_state(state_path: Path) -> pd.DataFrame:
    """Best-effort loader for the squeeze backtest state files.

    These are large JSON files with per-date trade arrays. We try a few
    shapes; if a file doesn't match, returns empty.
    """
    if not state_path.exists():
        return pd.DataFrame()
    try:
        data = json.loads(state_path.read_text())
    except Exception as e:
        log.warning("failed to parse %s: %s", state_path, e)
        return pd.DataFrame()
    records: list[dict] = []
    # Top-level may be {date: {...}}, {"trades": [...]}, or
    # {"config_a": {"trades": [...]}, "config_b": {...}}.
    if isinstance(data, dict):
        if "trades" in data and isinstance(data["trades"], list):
            for t in data["trades"]:
                records.append(t)
        elif "config_a" in data and isinstance(data["config_a"], dict):
            # Squeeze v2 state-file shape — pick config_a as canonical.
            for cfg_name in ("config_a", "config_b"):
                cfg = data.get(cfg_name) or {}
                for t in cfg.get("trades", []) or []:
                    t = dict(t)
                    t.setdefault("_source_config", cfg_name)
                    records.append(t)
        else:
            for date_key, day in data.items():
                if isinstance(day, dict) and "trades" in day:
                    for t in day["trades"]:
                        t = dict(t)
                        t.setdefault("session_date", date_key)
                        records.append(t)
                elif isinstance(day, list):
                    for t in day:
                        t = dict(t)
                        t.setdefault("session_date", date_key)
                        records.append(t)
    elif isinstance(data, list):
        records = list(data)
    if not records:
        return pd.DataFrame()
    df = pd.DataFrame(records)
    # Normalize column names — squeeze trades use {"time": "HH:MM", "date": "YYYY-MM-DD"}
    if "date" in df.columns and "session_date" not in df.columns:
        df["session_date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    if "time" in df.columns and "entry_ts" not in df.columns:
        # Compose entry_ts from date + time (treat as ET, convert to UTC)
        def _combine(row):
            try:
                return pd.to_datetime(
                    f"{row['date']} {row['time']}",
                    errors="coerce",
                ).tz_localize("US/Eastern").tz_convert("UTC")
            except Exception:
                return pd.NaT
        df["entry_ts"] = df.apply(_combine, axis=1)
    if "entry_time" in df.columns and "entry_ts" not in df.columns:
        df["entry_ts"] = pd.to_datetime(df["entry_time"], errors="coerce", utc=True)
    elif "entry_ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["entry_ts"]):
        df["entry_ts"] = pd.to_datetime(df["entry_ts"], errors="coerce", utc=True)
    if "exit_time" in df.columns and "exit_ts" not in df.columns:
        df["exit_ts"] = pd.to_datetime(df["exit_time"], errors="coerce", utc=True)
    elif "exit_ts" in df.columns and not pd.api.types.is_datetime64_any_dtype(df["exit_ts"]):
        df["exit_ts"] = pd.to_datetime(df["exit_ts"], errors="coerce", utc=True)
    if "session_date" not in df.columns and "entry_ts" in df.columns:
        df["session_date"] = df["entry_ts"].dt.tz_convert("US/Eastern").dt.date
    return df


def compare_overlap(
    round_df: pd.DataFrame,
    squeeze_df: pd.DataFrame,
) -> dict:
    """Compute symbol-day overlap and entry-timing comparison."""
    if round_df.empty:
        return {
            "round_n": 0, "squeeze_n": int(len(squeeze_df)),
            "overlap_symbol_days": 0,
            "overlap_records": [],
            "round_symbols": [],
            "squeeze_symbols": list(squeeze_df.get("symbol", pd.Series([])).unique()),
        }
    round_keys = set(zip(round_df["symbol"], round_df["session_date"]))
    squeeze_keys = (
        set(zip(squeeze_df["symbol"], squeeze_df["session_date"]))
        if not squeeze_df.empty else set()
    )
    overlap = round_keys & squeeze_keys

    overlap_records: list[dict] = []
    for sym, d in sorted(overlap, key=lambda x: (x[1], x[0])):
        r_rows = round_df[(round_df["symbol"] == sym) & (round_df["session_date"] == d)]
        s_rows = squeeze_df[(squeeze_df["symbol"] == sym) & (squeeze_df["session_date"] == d)]
        r_first = r_rows["entry_ts"].min()
        s_first = s_rows["entry_ts"].min()
        overlap_records.append({
            "symbol": sym,
            "session_date": d.isoformat() if isinstance(d, date) else str(d),
            "round_entry": r_first.isoformat() if pd.notna(r_first) else None,
            "squeeze_entry": s_first.isoformat() if pd.notna(s_first) else None,
            "round_first": (pd.notna(r_first) and pd.notna(s_first) and r_first < s_first),
            "round_trades_today": len(r_rows),
            "squeeze_trades_today": len(s_rows),
        })

    # Universe disjointness summary
    round_symbols = sorted(set(round_df["symbol"]))
    squeeze_symbols = (
        sorted(set(squeeze_df["symbol"])) if not squeeze_df.empty else []
    )
    only_round = set(round_symbols) - set(squeeze_symbols)
    only_squeeze = set(squeeze_symbols) - set(round_symbols)
    both = set(round_symbols) & set(squeeze_symbols)
    return {
        "round_n": int(len(round_df)),
        "squeeze_n": int(len(squeeze_df)),
        "overlap_symbol_days": int(len(overlap)),
        "n_unique_round_symbols": len(round_symbols),
        "n_unique_squeeze_symbols": len(squeeze_symbols),
        "n_overlap_symbols": len(both),
        "only_round_symbols": sorted(only_round)[:20],
        "only_squeeze_symbols": sorted(only_squeeze)[:20],
        "overlap_records": overlap_records[:50],  # cap output
    }


def summarize_disjointness(comp: dict) -> str:
    return (
        f"Round Number universe: {comp['n_unique_round_symbols']} symbols, "
        f"{comp['round_n']} trades\n"
        f"Squeeze universe:      {comp['n_unique_squeeze_symbols']} symbols, "
        f"{comp['squeeze_n']} trades\n"
        f"Symbol overlap:        {comp['n_overlap_symbols']} symbols\n"
        f"Same-day overlap:      {comp['overlap_symbol_days']} (symbol, date) pairs"
    )


def main() -> None:
    import argparse
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--round-trades",
                        default="backtest_archive/round_number_2026-05-16/trades.json")
    parser.add_argument("--squeeze-state",
                        default="ytd_v2_backtest_state_baseline.json",
                        help="Path to squeeze backtest state (relative to repo root)")
    parser.add_argument("--output",
                        default="backtest_archive/round_number_2026-05-16/vs_squeeze.json")
    args = parser.parse_args()

    round_path = ROOT / args.round_trades
    squeeze_path = ROOT / args.squeeze_state
    output_path = ROOT / args.output

    round_df = load_round_number_trades(round_path)
    log.info("Loaded %d Round Number trades from %s", len(round_df), round_path)

    squeeze_df = load_squeeze_trades_from_state(squeeze_path)
    log.info("Loaded %d Squeeze trades from %s", len(squeeze_df), squeeze_path)

    comp = compare_overlap(round_df, squeeze_df)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(comp, indent=2, default=str))
    print(summarize_disjointness(comp))
    print(f"\nDetailed comparison written to {output_path}")


if __name__ == "__main__":
    main()
