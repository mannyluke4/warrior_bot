#!/usr/bin/env python3
"""
WB v2 Stage 0 — Deliverable 3
Tick-audit universe extraction.

Mines the squeeze-bot tick cache (`tick_cache/<DATE>/<SYM>.json.gz`) plus
heartbeat logs (`logs/<DATE>_daily.log`) to produce a per-session "most active
stocks" ranking, mirroring what Manny was eyeballing in the heartbeat audits.

READ-ONLY on production data. Writes only under wb_v2/.
"""
from __future__ import annotations

import gzip
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

import pandas as pd
import numpy as np

REPO = Path("/Users/duffy/warrior_bot_v2")
TICK_CACHE = REPO / "tick_cache"
LOGS_DIR = REPO / "logs"
OUT_DIR = REPO / "wb_v2"
OUT_CSV = OUT_DIR / "extracted_universe.csv"
OUT_STATS_JSON = OUT_DIR / "extracted_universe_stats.json"

# ------------------------------------------------------------------
# Heartbeat parsing — recovers SYM:NNNt tokens per minute and sums
# per-day per-symbol bot-observed tick counts.
# ------------------------------------------------------------------
HEARTBEAT_TOKEN = re.compile(r"\b([A-Z]{2,6}):(\d+)t\b")
HEARTBEAT_LINE = re.compile(r"^\[\d{2}:\d{2}:\d{2} ET\].*ticks=")


def parse_heartbeats(log_path: Path) -> dict[str, int]:
    """Sum SYM:NNNt occurrences over the whole log -> {SYM: total_ticks}."""
    totals: dict[str, int] = defaultdict(int)
    try:
        with log_path.open("r", errors="ignore") as fh:
            for line in fh:
                if not HEARTBEAT_LINE.match(line):
                    continue
                for m in HEARTBEAT_TOKEN.finditer(line):
                    sym, n = m.group(1), int(m.group(2))
                    totals[sym] += n
    except FileNotFoundError:
        pass
    return dict(totals)


# ------------------------------------------------------------------
# Tick cache parsing — produces per-symbol per-day stats from raw ticks.
# ------------------------------------------------------------------
def parse_tick_file(path: Path) -> dict | None:
    """Read a SYM.json.gz tick file. Return None if unusable."""
    try:
        with gzip.open(path, "rt") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, EOFError):
        return None
    if not isinstance(data, list) or len(data) == 0:
        return None

    # Filter to regular-session ticks (09:30–16:00 ET = 13:30–20:00 UTC),
    # though we'll also keep extended-hours for the volume rank.
    # Tick records: {"p": price, "s": size, "t": ISO timestamp (UTC)}.
    prices: list[float] = []
    sizes: list[int] = []
    rth_prices: list[float] = []
    rth_sizes: list[int] = []
    rth_open: float | None = None
    for rec in data:
        try:
            p = float(rec["p"])
            s = int(rec["s"])
            ts = rec["t"]
        except (KeyError, TypeError, ValueError):
            continue
        prices.append(p)
        sizes.append(s)
        # Strip suffix and parse; tolerate +00:00 or Z.
        try:
            ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        utc_minute = ts_dt.astimezone(timezone.utc)
        # RTH: 13:30:00–20:00:00 UTC inclusive of 13:30, exclusive of 20:00.
        h, m = utc_minute.hour, utc_minute.minute
        if (h == 13 and m >= 30) or (14 <= h <= 19):
            rth_prices.append(p)
            rth_sizes.append(s)
            if rth_open is None:
                rth_open = p

    if not rth_prices:
        return None

    total_ticks = len(rth_prices)
    total_volume = int(sum(rth_sizes))
    dollar_volume = float(sum(p * s for p, s in zip(rth_prices, rth_sizes)))
    high = max(rth_prices)
    low = min(rth_prices)
    open_p = rth_open
    close_p = rth_prices[-1]
    range_pct = (high - low) / open_p if open_p else float("nan")
    vwap = dollar_volume / total_volume if total_volume else float("nan")

    return {
        "total_ticks": total_ticks,
        "total_volume": total_volume,
        "dollar_volume": dollar_volume,
        "high": high,
        "low": low,
        "open": open_p,
        "close": close_p,
        "vwap": vwap,
        "range_pct": range_pct,
    }


# ------------------------------------------------------------------
# Per-session aggregation
# ------------------------------------------------------------------
def session_stats(date_str: str) -> pd.DataFrame:
    """Return DataFrame of per-symbol stats for one session."""
    day_dir = TICK_CACHE / date_str
    rows = []
    if day_dir.is_dir():
        for f in sorted(day_dir.iterdir()):
            if not f.name.endswith(".json.gz"):
                continue
            sym = f.name[: -len(".json.gz")]
            stats = parse_tick_file(f)
            if stats is None:
                continue
            stats["symbol"] = sym
            rows.append(stats)

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    # Cross-reference with heartbeat tick counts for the day, where available.
    log_path = LOGS_DIR / f"{date_str}_daily.log"
    hb = parse_heartbeats(log_path) if log_path.exists() else {}
    df["heartbeat_ticks"] = df["symbol"].map(lambda s: hb.get(s, 0)).astype(int)
    df["date"] = date_str
    return df


def rank_session(df: pd.DataFrame) -> pd.DataFrame:
    """Add ranks + composite_score within one session."""
    if df.empty:
        return df

    df = df.copy()
    # Higher value = better rank (1 = most active). Use min method for ties.
    df["tick_rate_rank"] = df["total_ticks"].rank(method="min", ascending=False).astype(int)
    df["volume_rank"] = df["dollar_volume"].rank(method="min", ascending=False).astype(int)
    # RVOL filled in caller (needs prior days).
    df["range_rank"] = df["range_pct"].rank(method="min", ascending=False).astype(int)
    return df


def add_rvol(per_day: dict[str, pd.DataFrame], date_order: list[str]) -> None:
    """For each session, compute RVOL = today_vol / mean of prior-5 sessions
    per symbol. Mutates DataFrames in-place to add rvol + rvol_rank."""
    # Build a per-symbol rolling history of total_volume by date.
    hist: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for d in date_order:
        df = per_day.get(d)
        if df is None or df.empty:
            continue
        for _, row in df.iterrows():
            hist[row["symbol"]].append((d, int(row["total_volume"])))

    for d in date_order:
        df = per_day.get(d)
        if df is None or df.empty:
            continue
        rvol = []
        for _, row in df.iterrows():
            sym = row["symbol"]
            past = [v for (dd, v) in hist[sym] if dd < d][-5:]
            if len(past) >= 1 and mean(past) > 0:
                rvol.append(int(row["total_volume"]) / mean(past))
            else:
                rvol.append(float("nan"))
        df["rvol"] = rvol
        # Rank — NaN ties go last.
        df["rvol_rank"] = (
            df["rvol"]
            .rank(method="min", ascending=False, na_option="bottom")
            .fillna(9999)
            .astype(int)
        )


def composite(df: pd.DataFrame) -> pd.DataFrame:
    """Min-max normalize the four primary metrics within the session and
    average to a composite_score in [0, 1]. Higher = more active. RVOL
    NaN values are imputed as the median for the day for fairness."""
    if df.empty:
        return df

    df = df.copy()
    metrics = {
        "ticks_n": df["total_ticks"].astype(float),
        "dvol_n": df["dollar_volume"].astype(float),
        "rvol_n": df["rvol"].astype(float),
        "range_n": df["range_pct"].astype(float),
    }
    norm = {}
    for k, s in metrics.items():
        s2 = s.copy()
        if s2.isna().all():
            norm[k] = pd.Series([0.0] * len(s2), index=s2.index)
            continue
        med = s2.median(skipna=True)
        s2 = s2.fillna(med)
        lo, hi = s2.min(), s2.max()
        if hi - lo == 0:
            norm[k] = pd.Series([0.0] * len(s2), index=s2.index)
        else:
            norm[k] = (s2 - lo) / (hi - lo)
    df["composite_score"] = (
        norm["ticks_n"] + norm["dvol_n"] + norm["rvol_n"] + norm["range_n"]
    ) / 4.0
    return df


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------
def main(top_n_per_day: int = 20):
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Discover all dates with non-empty tick caches in 2026.
    all_dates: list[str] = []
    for d in sorted(p.name for p in TICK_CACHE.iterdir() if p.is_dir()):
        if not re.match(r"^2026-\d{2}-\d{2}$", d):
            continue
        # Skip the BROKEN dir and any 0-symbol days.
        try:
            n = sum(1 for f in (TICK_CACHE / d).iterdir() if f.name.endswith(".json.gz"))
        except OSError:
            continue
        if n < 5:  # require at least 5 symbols on the day
            continue
        all_dates.append(d)

    print(f"Found {len(all_dates)} qualifying tick-cache sessions in 2026")

    per_day: dict[str, pd.DataFrame] = {}
    for d in all_dates:
        df = session_stats(d)
        if df.empty:
            continue
        per_day[d] = rank_session(df)
        print(f"  {d}: {len(df)} symbols processed")

    # Compute RVOL using rolling history (needs sequential pass).
    add_rvol(per_day, sorted(per_day.keys()))

    # Composite + top-N selection
    rows_out = []
    for d, df in per_day.items():
        df = composite(df)
        # Top-N per session by composite (we keep tick_rate_rank etc. for context).
        df_top = df.nlargest(top_n_per_day, "composite_score")
        for _, r in df_top.iterrows():
            rows_out.append(
                {
                    "date": d,
                    "symbol": r["symbol"],
                    "total_ticks": int(r["total_ticks"]),
                    "heartbeat_ticks": int(r.get("heartbeat_ticks", 0)),
                    "total_volume": int(r["total_volume"]),
                    "dollar_volume": round(float(r["dollar_volume"]), 2),
                    "rvol": (round(float(r["rvol"]), 3) if pd.notna(r["rvol"]) else ""),
                    "range_pct": round(float(r["range_pct"]), 4),
                    "tick_rate_rank": int(r["tick_rate_rank"]),
                    "volume_rank": int(r["volume_rank"]),
                    "rvol_rank": int(r["rvol_rank"]),
                    "range_rank": int(r["range_rank"]),
                    "composite_score": round(float(r["composite_score"]), 4),
                }
            )

    out_df = pd.DataFrame(rows_out).sort_values(["date", "composite_score"], ascending=[True, False])
    out_df.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(out_df)} rows to {OUT_CSV}")

    # ----- Stats for the markdown report -----
    sessions_count = out_df["date"].nunique()
    unique_syms = out_df["symbol"].nunique()
    sym_freq = out_df["symbol"].value_counts()
    top_appearances = sym_freq.head(15).to_dict()
    # Top-5 turnover: how often a symbol in today's top-5 was also in yesterday's top-5.
    sessions_sorted = sorted(out_df["date"].unique())
    top5_by_day = {
        d: set(out_df[(out_df["date"] == d)].sort_values("composite_score", ascending=False).head(5)["symbol"])
        for d in sessions_sorted
    }
    turnover_rates = []
    for i in range(1, len(sessions_sorted)):
        prev = top5_by_day[sessions_sorted[i - 1]]
        cur = top5_by_day[sessions_sorted[i]]
        if not prev:
            continue
        churn = 1 - (len(prev & cur) / 5)
        turnover_rates.append(churn)

    # Correlation matrix between the 4 ranking metrics across the whole file.
    # Use Spearman on the rank columns.
    rank_cols = ["tick_rate_rank", "volume_rank", "rvol_rank", "range_rank"]
    # Replace 9999 (the rvol-NaN sentinel) with NaN for honest correlation.
    corr_df = out_df[rank_cols].replace({9999: np.nan})
    corr = corr_df.corr(method="spearman")

    stats = {
        "sessions": int(sessions_count),
        "rows": int(len(out_df)),
        "unique_symbols": int(unique_syms),
        "top_15_most_frequent_top20": top_appearances,
        "mean_top5_turnover_rate": float(np.mean(turnover_rates)) if turnover_rates else None,
        "median_top5_turnover_rate": float(np.median(turnover_rates)) if turnover_rates else None,
        "n_pairs_for_turnover": len(turnover_rates),
        "spearman_correlation_top20_ranks": {
            k: {kk: (None if pd.isna(v) else round(float(v), 3)) for kk, v in row.items()}
            for k, row in corr.to_dict().items()
        },
        "sessions_list": sessions_sorted,
    }

    # Also compute correlation on the full per-day population (not just top-20),
    # since restricting to top-20 truncates rank correlation.
    full_rows = []
    for d, df in per_day.items():
        df = composite(df)
        for _, r in df.iterrows():
            full_rows.append(
                {
                    "tick_rate_rank": int(r["tick_rate_rank"]),
                    "volume_rank": int(r["volume_rank"]),
                    "rvol_rank": int(r["rvol_rank"]) if r["rvol_rank"] != 9999 else np.nan,
                    "range_rank": int(r["range_rank"]),
                }
            )
    full_df = pd.DataFrame(full_rows)
    full_corr = full_df.corr(method="spearman")
    stats["spearman_correlation_full_population"] = {
        k: {kk: (None if pd.isna(v) else round(float(v), 3)) for kk, v in row.items()}
        for k, row in full_corr.to_dict().items()
    }

    # Heartbeat-vs-tick-cache correlation per day (when bot was watching them).
    hb_ranks_compare = []
    for d, df in per_day.items():
        df2 = df[df["heartbeat_ticks"] > 0].copy()
        if len(df2) < 4:
            continue
        df2["hb_rank"] = df2["heartbeat_ticks"].rank(method="min", ascending=False)
        df2["tc_rank"] = df2["total_ticks"].rank(method="min", ascending=False)
        c = df2[["hb_rank", "tc_rank"]].corr(method="spearman").iloc[0, 1]
        if not pd.isna(c):
            hb_ranks_compare.append(float(c))
    stats["heartbeat_vs_tick_cache_rank_correlation_mean"] = (
        float(np.mean(hb_ranks_compare)) if hb_ranks_compare else None
    )
    stats["heartbeat_vs_tick_cache_correlation_sample_size"] = len(hb_ranks_compare)

    with OUT_STATS_JSON.open("w") as fh:
        json.dump(stats, fh, indent=2)
    print(f"Wrote stats to {OUT_STATS_JSON}")

    # Print a couple of sample rows.
    print("\nSample (first 5 rows of CSV):")
    print(out_df.head().to_string(index=False))
    print("\nSpearman rank correlation (top-20 subset):")
    print(corr.round(3).to_string())
    print("\nSpearman rank correlation (full population):")
    print(full_corr.round(3).to_string())


if __name__ == "__main__":
    main()
