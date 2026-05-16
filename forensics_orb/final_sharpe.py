"""
Recompute Sharpe using the wave-3 runner's method:
  equity_curve at exit_ts (cumulative pnl on $100K base) -> last per date -> pct_change.
Plus reproduce key filter Sharpes and validate matches.
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path("/Users/duffy/warrior_bot_v2")
STARTING_EQUITY = 100_000.0

df = pd.read_parquet(ROOT / "forensics_orb" / "trades_with_features.parquet")
df["abs_gap"] = df["pm_gap_pct"].abs()
df["entry_ts"] = pd.to_datetime(df["entry_ts"])
df["exit_ts"] = pd.to_datetime(df["exit_ts"])
df["session_date"] = pd.to_datetime(df["session_date"])
df["year"] = df["entry_ts"].dt.year
df["quarter"] = df["entry_ts"].dt.to_period("Q")

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


def runner_sharpe(sub: pd.DataFrame, starting: float = STARTING_EQUITY) -> float:
    if sub.empty:
        return float("nan")
    s = sub.sort_values("exit_ts").copy()
    eq = starting + s["pnl"].cumsum()
    daily_eq = eq.groupby(s["exit_ts"].dt.date).last()
    rets = daily_eq.pct_change().dropna()
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return float("nan")
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(252))


def metrics(sub, label):
    if sub.empty:
        return {"filter": label, "n": 0}
    # MaxDD with the runner's equity_curve
    s = sub.sort_values("exit_ts").copy()
    eq = STARTING_EQUITY + s["pnl"].cumsum()
    peak = eq.cummax()
    dd_pct = float(((eq - peak) / peak).min())
    dd_dollars = float((eq - peak).min())
    qpnl = s.groupby("quarter")["pnl"].sum()
    qpnl_pos = qpnl[qpnl > 0]
    max_q = float(qpnl_pos.max() / qpnl_pos.sum()) if qpnl_pos.sum() > 0 else None
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
        "profit_factor": float(s[s["pnl"]>0]["pnl"].sum() / abs(s[s["pnl"]<0]["pnl"].sum())) if (s["pnl"]<0).any() else None,
    }


candidates = {
    "baseline_all_orb": df,
    "H1_catalyst_paper": df[(df["abs_gap"] > 2) & (df["or5_rvol"] > 2)],
    "H1_catalyst_relaxed": df[(df["abs_gap"] > 1) & (df["or5_rvol"] > 1.5)],
    "H1_catalyst_strict": df[(df["abs_gap"] > 4) & (df["or5_rvol"] > 2)],
    "H2_or5_highvol_only": df[df["or5_volume"] / df["or5_vol_baseline_20d"] > 1.5],
    "H3_aligned_only": df[df["or5_align"] == "aligned"],
    "H4_vwap_extended": df[(df["dist_vwap_pct"].abs() > 0.3) & (df["dist_vwap_pct"].abs() <= 1.0)],
    "H5_first_60min": df[df["mins_from_open"] <= 60],
    "H5_first_30min": df[df["mins_from_open"] <= 30],
    "H7_tier_300plus": df[df["tier"] == "$300+"],
    "H7_tier_200_300plus": df[df["tier"].isin(["$200-300","$300+"])],
    "H7_tier_100_300plus": df[df["tier"].isin(["$100-200","$200-300","$300+"])],
    "H9_thu_fri": df[df["day_of_week"].isin([3,4])],
    "H9_mon": df[df["day_of_week"] == 0],
    "H10_mega": df["symbol"].isin(["AAPL","MSFT","NVDA","META","TSLA","AVGO","AMD","NFLX","ADBE","CRM","ORCL","INTC","QCOM","CSCO","DIS","MU"]).pipe(lambda m: df[m]),
    "Combo_tier300_aligned": df[(df["tier"] == "$300+") & (df["or5_align"] == "aligned")],
    "Combo_tier300_first60": df[(df["tier"] == "$300+") & (df["mins_from_open"] <= 60)],
    "Combo_paper_full_zarattini": df[(df["abs_gap"] > 2) & (df["or5_rvol"] > 2) & (df["or5_align"] == "aligned") & (df["mins_from_open"] <= 60)],
    "Combo_strict_gap_tier300": df[(df["abs_gap"] > 4) & (df["or5_rvol"] > 2) & (df["tier"] == "$300+")],
    "Combo_tier300_aligned_thufri": df[(df["tier"] == "$300+") & (df["or5_align"] == "aligned") & (df["day_of_week"].isin([3,4]))],
}

# walk-forward
print(f"{'filter':<40} {'n':>5} {'WR':>6} {'avgR':>7} {'PnL':>9} {'Sharpe':>7} {'DD%':>7} {'maxQ%':>6}")
print("-" * 100)
results = {}
for k, sub in candidates.items():
    m = metrics(sub, k)
    if m["n"] == 0:
        print(f"{k:<40} (no trades)")
        continue
    print(f"{k:<40} {m['n']:>5} {m['wr']:>6.3f} {m['avg_r']:>7.4f} {m['net_pnl']:>9.0f} {m['sharpe']:>7.3f} {m['max_dd_pct']*100:>7.1f} {(m['max_q_concentration'] or 0)*100:>6.1f}")
    results[k] = m

# Walk-forward train 2020-2022 / test 2023-2024 on the top 4
print("\nWalk-forward (train 2020-2022 / test 2023-2024):")
print(f"{'filter':<40} {'tr_n':>5} {'tr_Sh':>6} {'te_n':>5} {'te_Sh':>6}")
print("-" * 70)
for k, sub in candidates.items():
    tr = sub[sub["year"] <= 2022]
    te = sub[sub["year"] >= 2023]
    if len(tr) < 50 or len(te) < 50:
        continue
    s_tr = runner_sharpe(tr)
    s_te = runner_sharpe(te)
    results.setdefault(k, {})["sharpe_train_2020_2022"] = s_tr
    results.setdefault(k, {})["sharpe_test_2023_2024"] = s_te
    print(f"{k:<40} {len(tr):>5} {s_tr:>6.3f} {len(te):>5} {s_te:>6.3f}")

# Per-year sharpe table for the top filter (tier $300+)
print("\nPer-year Sharpe (using runner method):")
print(f"{'filter':<40} {'2020':>7} {'2021':>7} {'2022':>7} {'2023':>7} {'2024':>7}")
print("-" * 80)
for k, sub in candidates.items():
    yrs = {}
    for y in [2020,2021,2022,2023,2024]:
        yr = sub[sub["year"] == y]
        if len(yr) < 20:
            yrs[y] = None
            continue
        yrs[y] = runner_sharpe(yr)
    row = f"{k:<40}"
    for y in [2020,2021,2022,2023,2024]:
        v = yrs.get(y)
        row += f" {('  n/a' if v is None else f'{v:6.2f}')}"
    print(row)
    results.setdefault(k, {})["sharpe_by_year"] = yrs

with open(ROOT / "forensics_orb" / "final_sharpe.json", "w") as fp:
    json.dump(results, fp, indent=2, default=str)
print("\nWritten final_sharpe.json")
