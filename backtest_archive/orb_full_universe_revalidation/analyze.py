"""ORB 36-name full-universe revalidation — analytics.

Reads the trades parquet produced by `backtest.portfolio_backtest`,
applies the forensic-2 Sharpe methodology, and produces per-year /
per-tier breakdowns + acceptance-gate verdict.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/Users/duffy/warrior_bot_v2")
ARCHIVE = ROOT / "backtest_archive" / "orb_full_universe_revalidation"
STARTING_EQUITY = 100_000.0


def runner_sharpe(sub: pd.DataFrame, starting: float = STARTING_EQUITY) -> float:
    """Wave-3 runner Sharpe: cum P&L → daily-last equity → pct_change × √252."""
    if sub.empty:
        return float("nan")
    s = sub.sort_values("exit_ts").copy()
    eq = starting + s["pnl"].cumsum()
    daily_eq = eq.groupby(s["exit_ts"].dt.date).last()
    rets = daily_eq.pct_change().dropna()
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return float("nan")
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))


def metrics(sub: pd.DataFrame, label: str) -> dict:
    if sub.empty:
        return {"filter": label, "n": 0}
    s = sub.sort_values("exit_ts").copy()
    eq = STARTING_EQUITY + s["pnl"].cumsum()
    peak = eq.cummax()
    dd_pct = float(((eq - peak) / peak).min())
    dd_dollars = float((eq - peak).min())
    qpnl = s.groupby(s["entry_ts"].dt.to_period("Q"))["pnl"].sum()
    qpnl_pos = qpnl[qpnl > 0]
    max_q = float(qpnl_pos.max() / qpnl_pos.sum()) if qpnl_pos.sum() > 0 else None
    pf = None
    if (s["pnl"] < 0).any():
        pf = float(s[s["pnl"] > 0]["pnl"].sum() / abs(s[s["pnl"] < 0]["pnl"].sum()))
    return {
        "filter": label,
        "n": int(len(s)),
        "trades_per_year": float(len(s) / 5.0),
        "wr": float((s["r_multiple"] > 0).mean()),
        "avg_r": float(s["r_multiple"].mean()),
        "net_pnl": float(s["pnl"].sum()),
        "sharpe": runner_sharpe(s),
        "max_dd_pct": dd_pct,
        "max_dd_dollars": dd_dollars,
        "max_q_concentration": max_q,
        "profit_factor": pf,
    }


def tier_label(price: float) -> str:
    if price < 10:
        return "<$10"
    if price < 20:
        return "$10-20"
    if price < 50:
        return "$20-50"
    if price < 100:
        return "$50-100"
    if price < 200:
        return "$100-200"
    if price < 300:
        return "$200-300"
    return "$300+"


def main() -> None:
    parquet_path = ARCHIVE / "trades_ORB-Aligned-300Plus-MonSkip_fixed_dollar.parquet"
    csv_path = ARCHIVE / "trades_ORB-Aligned-300Plus-MonSkip_fixed_dollar.csv"
    if parquet_path.exists():
        df = pd.read_parquet(parquet_path)
    elif csv_path.exists():
        df = pd.read_csv(csv_path)
    else:
        print("No trades file found at:", parquet_path)
        return

    print(f"loaded {len(df)} trades from {parquet_path.name if parquet_path.exists() else csv_path.name}")

    # Type coerce
    df["entry_ts"] = pd.to_datetime(df["entry_ts"])
    df["exit_ts"] = pd.to_datetime(df["exit_ts"])
    df["session_date"] = pd.to_datetime(df["session_date"]).dt.date
    df["year"] = df["entry_ts"].dt.year
    df["dow"] = df["entry_ts"].dt.dayofweek
    df["tier"] = df["entry_price"].apply(tier_label)

    out = {}

    # === Filter verification ===
    print("\n=== FILTER VERIFICATION ===")
    print(f"Min entry_price: ${df['entry_price'].min():.2f}")
    print(f"Max entry_price: ${df['entry_price'].max():.2f}")
    sub_under_300 = df[df["entry_price"] < 300.0]
    print(f"Trades with entry_price < $300: {len(sub_under_300)} (should be 0)")
    monday_trades = df[df["dow"] == 0]
    print(f"Monday entries: {len(monday_trades)} (should be 0)")
    dow_dist = df.groupby("dow")["pnl"].agg(["count", "sum"])
    print(f"Day-of-week distribution:\n{dow_dist}")
    out["filter_verification"] = {
        "min_entry_price": float(df["entry_price"].min()),
        "max_entry_price": float(df["entry_price"].max()),
        "trades_under_300": int(len(sub_under_300)),
        "monday_trades": int(len(monday_trades)),
        "dow_distribution": {int(k): int(v) for k, v in df["dow"].value_counts().to_dict().items()},
    }

    # === Overall metrics ===
    print("\n=== OVERALL METRICS ===")
    overall = metrics(df, "full_sample_2020_2024")
    for k, v in overall.items():
        print(f"  {k}: {v}")
    out["overall"] = overall

    # === IS / OOS split ===
    print("\n=== IS (2020-2022) / OOS (2023-2024) ===")
    is_df = df[df["year"] <= 2022]
    oos_df = df[df["year"] >= 2023]
    is_m = metrics(is_df, "IS_2020_2022")
    oos_m = metrics(oos_df, "OOS_2023_2024")
    for label, m in [("IS", is_m), ("OOS", oos_m)]:
        print(f"  {label}: n={m['n']} Sharpe={m['sharpe']:.3f} maxDD%={m['max_dd_pct']*100:.1f} netPnL=${m['net_pnl']:.0f} WR={m['wr']:.3f} avgR={m['avg_r']:.3f}")
    out["is"] = is_m
    out["oos"] = oos_m

    # === Per-year ===
    print("\n=== PER-YEAR METRICS ===")
    print(f"{'year':>6} {'n':>5} {'WR':>6} {'avgR':>7} {'PnL':>9} {'Sharpe':>7} {'DD%':>7}")
    per_year = {}
    for y in [2020, 2021, 2022, 2023, 2024]:
        yr_df = df[df["year"] == y]
        m = metrics(yr_df, f"year_{y}")
        per_year[y] = m
        if m["n"] == 0:
            print(f"{y:>6} (no trades)")
            continue
        print(f"{y:>6} {m['n']:>5} {m['wr']:>6.3f} {m['avg_r']:>7.4f} {m['net_pnl']:>9.0f} {m['sharpe']:>7.3f} {m['max_dd_pct']*100:>7.1f}")
    out["per_year"] = per_year

    # === Per-tier ===
    print("\n=== PER-TIER METRICS ===")
    print(f"{'tier':>10} {'n':>5} {'WR':>6} {'avgR':>7} {'PnL':>9} {'Sharpe':>7}")
    per_tier = {}
    for t in ["<$10", "$10-20", "$20-50", "$50-100", "$100-200", "$200-300", "$300+"]:
        sub = df[df["tier"] == t]
        m = metrics(sub, f"tier_{t}")
        per_tier[t] = m
        if m["n"] == 0:
            print(f"{t:>10} (no trades)")
            continue
        print(f"{t:>10} {m['n']:>5} {m['wr']:>6.3f} {m['avg_r']:>7.4f} {m['net_pnl']:>9.0f} {m['sharpe']:>7.3f}")
    out["per_tier"] = per_tier

    # === Per-symbol ===
    print("\n=== PER-SYMBOL METRICS ===")
    per_sym = {}
    for sym in sorted(df["symbol"].unique()):
        sub = df[df["symbol"] == sym]
        m = metrics(sub, f"sym_{sym}")
        per_sym[sym] = m
    print(f"{'sym':>6} {'n':>5} {'WR':>6} {'avgR':>7} {'PnL':>9}")
    for sym, m in sorted(per_sym.items(), key=lambda kv: -kv[1].get("net_pnl", 0)):
        if m["n"] == 0:
            continue
        print(f"{sym:>6} {m['n']:>5} {m['wr']:>6.3f} {m['avg_r']:>7.4f} {m['net_pnl']:>9.0f}")
    out["per_symbol"] = per_sym

    # === Sample trades for verification ===
    print("\n=== SAMPLE TRADES (10 random) ===")
    if len(df) >= 10:
        sample = df.sample(n=10, random_state=42).sort_values("entry_ts")
    else:
        sample = df.sort_values("entry_ts")
    sample_records = []
    for _, row in sample.iterrows():
        d = {
            "symbol": row["symbol"],
            "session_date": str(row["session_date"]),
            "dow": int(pd.Timestamp(row["entry_ts"]).dayofweek),
            "direction": row["direction"],
            "entry_price": float(row["entry_price"]),
            "exit_price": float(row["exit_price"]),
            "tier": tier_label(float(row["entry_price"])),
            "pnl": float(row["pnl"]),
            "r_multiple": float(row["r_multiple"]),
            "exit_reason": row["exit_reason"],
        }
        sample_records.append(d)
        print(f"  {d['symbol']:>5} {d['session_date']} dow={d['dow']} {d['direction']:>5} entry=${d['entry_price']:.2f} ({d['tier']}) pnl=${d['pnl']:.0f} R={d['r_multiple']:.2f} exit={d['exit_reason']}")
    out["sample_trades"] = sample_records

    # === Acceptance gates ===
    print("\n=== ACCEPTANCE GATES ===")
    gates = {
        "OOS_Sharpe_>=_1.5": oos_m["sharpe"] >= 1.5,
        "OOS_n_trades_>=_100": oos_m["n"] >= 100,
        "max_DD_<=_15pct": abs(overall["max_dd_pct"]) <= 0.15,
        "every_year_positive": all(
            (per_year[y]["n"] == 0) or (per_year[y]["sharpe"] > 0)
            for y in [2020, 2021, 2022, 2023, 2024]
        ),
    }
    for g, p in gates.items():
        print(f"  {g}: {'PASS' if p else 'FAIL'}")
    out["gates"] = gates

    # === Verdict ===
    oos_sharpe = oos_m["sharpe"]
    if oos_sharpe >= 1.5:
        verdict = "GREEN"
    elif oos_sharpe >= 1.0:
        verdict = "YELLOW"
    else:
        verdict = "RED"
    print(f"\n=== VERDICT: {verdict} (OOS Sharpe {oos_sharpe:.3f}) ===")
    out["verdict"] = verdict
    out["oos_sharpe"] = float(oos_sharpe) if oos_sharpe == oos_sharpe else None

    with open(ARCHIVE / "analysis.json", "w") as fp:
        json.dump(out, fp, indent=2, default=str)
    print(f"\nWrote {ARCHIVE / 'analysis.json'}")


if __name__ == "__main__":
    main()
