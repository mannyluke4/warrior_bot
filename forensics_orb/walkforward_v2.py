"""
Walk-forward stability check for the strongest filter candidates:
  A: tier == "$300+" (Sharpe 1.72 in-sample)
  B: gap>4% AND or5_rvol>2 (Sharpe 1.97 in-sample, n=162)
  C: gap>3% AND or5_rvol>2 (Sharpe 1.66 in-sample, n=227)
  D: catalyst (gap>2 AND rvol>2) AND tier in {$300+,$200-300,$100-200}
  E: tier $300+ AND aligned

For each, train on 2020-2022, test on 2023-2024.
Also year-by-year stability table.
"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/Users/duffy/warrior_bot_v2")
df = pd.read_parquet(ROOT / "forensics_orb" / "trades_with_features.parquet")
df["abs_gap"] = df["pm_gap_pct"].abs()
df["entry_ts"] = pd.to_datetime(df["entry_ts"])
df["year"] = df["entry_ts"].dt.year

# Recompute align
def align_label(row):
    d, c = row["direction"], row["or5_dir"]
    if d == "long" and c == "green":
        return "aligned"
    if d == "short" and c == "red":
        return "aligned"
    if c == "doji":
        return "doji"
    return "misaligned"
df["or5_align"] = df.apply(align_label, axis=1)


def sharpe_daily(s):
    if s.empty:
        return float("nan")
    d = s.copy()
    d["d"] = pd.to_datetime(d["session_date"])
    daily = d.groupby("d")["pnl"].sum()
    eq = 25000.0
    rets = daily / eq
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return float("nan")
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))


def stats(s, label):
    return {
        "filter": label,
        "n": int(len(s)),
        "wr": float((s["r_multiple"] > 0).mean()) if len(s) else None,
        "avg_r": float(s["r_multiple"].mean()) if len(s) else None,
        "net_pnl": float(s["pnl"].sum()) if len(s) else None,
        "sharpe_daily": sharpe_daily(s) if len(s) else None,
    }


filters = {
    "A_tier_300plus": lambda d: d[d["tier"] == "$300+"],
    "B_gap4_rvol2": lambda d: d[(d["abs_gap"] > 4.0) & (d["or5_rvol"] > 2.0)],
    "C_gap3_rvol2": lambda d: d[(d["abs_gap"] > 3.0) & (d["or5_rvol"] > 2.0)],
    "D_catalyst_top_tiers": lambda d: d[(d["abs_gap"] > 2.0) & (d["or5_rvol"] > 2.0) & (d["tier"].isin(["$300+","$200-300","$100-200"]))],
    "E_tier300_aligned": lambda d: d[(d["tier"] == "$300+") & (d["or5_align"] == "aligned")],
    "F_tier300_or_200": lambda d: d[d["tier"].isin(["$300+","$200-300"])],
    "G_canonical_zarattini": lambda d: d[(d["abs_gap"] > 2.0) & (d["or5_rvol"] > 1.5) & (d["mins_from_open"] <= 90)],
    "H_paper_catalyst": lambda d: d[(d["abs_gap"] > 2.0) & (d["or5_rvol"] > 2.0)],
}

out = {"baseline": stats(df, "baseline_all_trades")}

for k, f in filters.items():
    sub = f(df)
    out[k] = {"overall": stats(sub, k)}
    train = sub[sub["year"] <= 2022]
    test = sub[sub["year"] >= 2023]
    out[k]["train_2020_2022"] = stats(train, k + " train")
    out[k]["test_2023_2024"] = stats(test, k + " test")
    # Year-by-year
    yearly = {}
    for y in sorted(sub["year"].unique()):
        s = sub[sub["year"] == y]
        yearly[int(y)] = stats(s, f"{k} {y}")
    out[k]["yearly"] = yearly

with open(ROOT / "forensics_orb" / "walkforward_v2.json", "w") as fp:
    json.dump(out, fp, indent=2, default=str)

# Pretty print
print(f"{'Filter':<28} {'N':>5} {'WR':>6} {'AvgR':>7} {'NetPnL':>10} {'Sharpe':>7}")
print("-" * 80)
for k, v in out.items():
    if k == "baseline":
        s = v
        print(f"{'baseline (all 9,790)':<28} {s['n']:>5} {s['wr']:>6.3f} {s['avg_r']:>7.4f} {s['net_pnl']:>10.0f} {s['sharpe_daily']:>7.3f}")
        continue
    overall = v["overall"]
    train = v["train_2020_2022"]
    test = v["test_2023_2024"]
    sharpe_o = overall["sharpe_daily"] or float("nan")
    sharpe_tr = train["sharpe_daily"] or float("nan")
    sharpe_te = test["sharpe_daily"] or float("nan")
    print(f"{k+' (overall)':<28} {overall['n']:>5} {overall['wr']:>6.3f} {overall['avg_r']:>7.4f} {overall['net_pnl']:>10.0f} {sharpe_o:>7.3f}")
    print(f"  train 2020-22{'':<13} {train['n']:>5} {train['wr']:>6.3f} {train['avg_r']:>7.4f} {train['net_pnl']:>10.0f} {sharpe_tr:>7.3f}")
    print(f"  test  2023-24{'':<13} {test['n']:>5} {test['wr']:>6.3f} {test['avg_r']:>7.4f} {test['net_pnl']:>10.0f} {sharpe_te:>7.3f}")
    print(f"  yearly: ", end="")
    for y, s in v["yearly"].items():
        sh = s["sharpe_daily"] if s["sharpe_daily"] is not None else float("nan")
        sh_str = f"{sh:.2f}" if not (sh is None or (isinstance(sh, float) and (sh != sh))) else "NaN"
        print(f"{y}: n={s['n']} S={sh_str} | ", end="")
    print()
    print()
