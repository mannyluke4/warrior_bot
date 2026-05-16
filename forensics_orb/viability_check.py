"""
Final viability checks on top filter candidates.
Reports:
 - Quarterly concentration (max single-quarter % of total P&L)
 - Equity curve, MaxDD, worst losing streak, worst 6-month rolling
 - Trades per year
 - Recommended config
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


def viability(s, eq0=25000):
    if s.empty:
        return {}
    s = s.sort_values("entry_ts").copy()
    s["cum_pnl"] = s["pnl"].cumsum()
    equity = eq0 + s["cum_pnl"]
    peak = equity.cummax()
    dd_pct = float(((equity - peak) / peak).min())
    dd_dollars = float((equity - peak).min())
    # Quarterly concentration
    qpnl = s.groupby("quarter")["pnl"].sum()
    qpnl_pos = qpnl[qpnl > 0]
    max_q = float(qpnl_pos.max() / qpnl_pos.sum()) if qpnl_pos.sum() > 0 else None
    # Worst losing streak
    streak = 0; cur = 0
    for r in s["r_multiple"].values:
        if r > 0:
            cur = 0
        else:
            cur += 1
            streak = max(streak, cur)
    # Worst 6-month rolling
    s2 = s.set_index(pd.to_datetime(s["entry_ts"]))
    rolling = s2["pnl"].rolling("180D").sum()
    return {
        "n_trades": int(len(s)),
        "trades_per_year": float(len(s) / 5.0),
        "net_pnl": float(s["pnl"].sum()),
        "wr": float((s["r_multiple"] > 0).mean()),
        "avg_r": float(s["r_multiple"].mean()),
        "sharpe_daily": sharpe_daily(s),
        "max_dd_pct": dd_pct,
        "max_dd_dollars": dd_dollars,
        "max_q_concentration": max_q,
        "ending_equity": eq0 + float(s["pnl"].sum()),
        "ending_equity_multiple": (eq0 + float(s["pnl"].sum())) / eq0,
        "worst_losing_streak": int(streak),
        "worst_6mo_pnl": float(rolling.min()),
    }


candidates = {
    "A_tier_300plus": df[df["tier"] == "$300+"],
    "B_gap4_rvol2": df[(df["abs_gap"] > 4.0) & (df["or5_rvol"] > 2.0)],
    "E_tier300_aligned": df[(df["tier"] == "$300+") & (df["or5_align"] == "aligned")],
    "F_tier300_or_200": df[df["tier"].isin(["$300+", "$200-300"])],
    "G_full_stack": df[(df["tier"] == "$300+") & (df["or5_align"].isin(["aligned","doji"])) & (df["mins_from_open"] <= 60)],
}

results = {}
for k, s in candidates.items():
    v = viability(s)
    results[k] = v
    print(f"\n=== {k} (n={v.get('n_trades',0)}) ===")
    print(json.dumps(v, indent=2, default=str))

with open(ROOT / "forensics_orb" / "viability.json", "w") as fp:
    json.dump(results, fp, indent=2, default=str)
print("\nWritten viability.json")
