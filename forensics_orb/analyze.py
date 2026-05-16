"""
ORB-5min forensic — hypothesis testing + filter design.

Inputs: forensics_orb/trades_with_features.parquet (9,790 enriched trades).

For each of 10 pre-registered hypotheses, partition the trades, compute
Sharpe / WR / avg-R / N / net P&L per bucket, and decide whether the
hypothesis is supported.

Plus: loser top-10 profile, winner top-10 profile, big-winner attribution,
catalyst-day filter validation, walk-forward 2020-2022 train / 2023-2024 test,
viability at $25K equity.

Notes on Sharpe: we use trade-level Sharpe = mean(R) / std(R) * sqrt(252)
where R = r_multiple. This is what the wave 3 portfolio runner uses
(per metrics_fixed_dollar.json all five strategies' Sharpe values are
order-1, consistent with trade-level annualization on ~9,790 trades over
1,258 sessions ~= 7.8 trades/day -> sqrt(252*7.8) overcompounds, so
likely they used daily-aggregated. We'll report both forms to be safe.)
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/Users/duffy/warrior_bot_v2")
IN_PATH = ROOT / "forensics_orb" / "trades_with_features.parquet"
OUT_JSON = ROOT / "forensics_orb" / "analysis_results.json"

TRADING_DAYS = 252


def sharpe_trade(r: pd.Series) -> float:
    """Trade-level Sharpe, annualized with sqrt(trades_per_year)."""
    r = r.dropna()
    if len(r) < 2:
        return float("nan")
    sd = r.std(ddof=1)
    if sd == 0:
        return float("nan")
    return float(r.mean() / sd * np.sqrt(TRADING_DAYS))


def sharpe_daily(df: pd.DataFrame, equity_col: str = "pnl") -> float:
    """Aggregate trades into daily P&L and compute annualized daily-return Sharpe.
    Used by the wave-3 portfolio runner."""
    if df.empty:
        return float("nan")
    df = df.copy()
    df["d"] = pd.to_datetime(df["session_date"])
    daily = df.groupby("d")[equity_col].sum()
    # Assume $25K starting equity for daily-return Sharpe
    eq = 25000.0
    rets = daily / eq
    if len(rets) < 2 or rets.std(ddof=1) == 0:
        return float("nan")
    return float(rets.mean() / rets.std(ddof=1) * np.sqrt(TRADING_DAYS))


def bucket_stats(df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    grp = df.groupby(group_col)
    out = pd.DataFrame({
        "n": grp.size(),
        "net_pnl": grp["pnl"].sum(),
        "win_rate": grp.apply(lambda g: (g["r_multiple"] > 0).mean()),
        "avg_r": grp["r_multiple"].mean(),
        "median_r": grp["r_multiple"].median(),
        "std_r": grp["r_multiple"].std(),
        "sharpe_trade": grp["r_multiple"].apply(sharpe_trade),
        "sharpe_daily": grp.apply(sharpe_daily),
    }).round(4)
    return out.sort_values("sharpe_daily", ascending=False, na_position="last")


def main() -> None:
    df = pd.read_parquet(IN_PATH)
    print(f"Loaded {len(df)} trades")

    # ----- Baseline reproduction -----
    baseline = {
        "n_trades": int(len(df)),
        "net_pnl": float(df["pnl"].sum()),
        "win_rate": float((df["r_multiple"] > 0).mean()),
        "avg_r": float(df["r_multiple"].mean()),
        "sharpe_trade": sharpe_trade(df["r_multiple"]),
        "sharpe_daily": sharpe_daily(df),
        "max_dd_dollars_estimate": None,  # computed below
    }

    # Estimate MaxDD from equity curve (fixed_dollar, $25K starting)
    df_sorted = df.sort_values("entry_ts").copy()
    df_sorted["cum_pnl"] = df_sorted["pnl"].cumsum()
    eq = 25000 + df_sorted["cum_pnl"]
    peak = eq.cummax()
    dd_dollars = float((eq - peak).min())
    dd_pct = float(((eq - peak) / peak).min())
    baseline["max_dd_dollars_estimate"] = dd_dollars
    baseline["max_dd_pct_estimate"] = dd_pct
    print("Baseline:", json.dumps(baseline, indent=2, default=str))

    results: dict = {"baseline": baseline}

    # ===== Hypothesis 1: catalyst-day filter =====
    # Catalyst = |pm_gap_pct| > 2% AND or5_rvol > 2.0
    df["abs_gap"] = df["pm_gap_pct"].abs()
    catalyst = (df["abs_gap"] > 2.0) & (df["or5_rvol"] > 2.0)
    df["catalyst_day"] = catalyst
    h1 = bucket_stats(df, "catalyst_day")
    print("\n=== H1: Catalyst day (|gap|>2 AND or5_rvol>2) ===")
    print(h1)
    results["h1_catalyst"] = h1.reset_index().to_dict(orient="records")

    # Also report relaxed variants for the filter spec
    for gap_thr, rvol_thr in [(1.0, 1.5), (2.0, 1.5), (2.0, 2.0), (3.0, 2.0), (2.0, 3.0), (4.0, 2.0)]:
        flag = (df["abs_gap"] > gap_thr) & (df["or5_rvol"] > rvol_thr)
        sub = df[flag]
        if len(sub) < 50:
            stats = {"n": int(len(sub)), "note": "n<50 — sparse"}
        else:
            stats = {
                "gap_thr": gap_thr,
                "rvol_thr": rvol_thr,
                "n": int(len(sub)),
                "win_rate": float((sub["r_multiple"] > 0).mean()),
                "avg_r": float(sub["r_multiple"].mean()),
                "net_pnl": float(sub["pnl"].sum()),
                "sharpe_trade": sharpe_trade(sub["r_multiple"]),
                "sharpe_daily": sharpe_daily(sub),
            }
        results.setdefault("h1_grid", []).append(stats)
        print(f"  gap>{gap_thr} & rvol>{rvol_thr}: {stats}")

    # ===== Hypothesis 2: opening-bar volume =====
    df["or5_vol_ratio"] = df["or5_volume"] / df["or5_vol_baseline_20d"]
    df["or5_high_vol"] = df["or5_vol_ratio"] > 1.5
    h2 = bucket_stats(df, "or5_high_vol")
    print("\n=== H2: 5-min OR volume > 1.5x baseline ===")
    print(h2)
    results["h2_or5_vol"] = h2.reset_index().to_dict(orient="records")

    # ===== Hypothesis 3: opening-bar direction alignment =====
    # Alignment: long + green, short + red. Misalignment is the inverse.
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
    h3 = bucket_stats(df, "or5_align")
    print("\n=== H3: ORB direction vs opening-bar color ===")
    print(h3)
    results["h3_align"] = h3.reset_index().to_dict(orient="records")

    # ===== Hypothesis 4: distance from VWAP at breakout =====
    def vwap_bucket(row):
        v = row["dist_vwap_pct"]
        if pd.isna(v):
            return "unknown"
        # For shorts the relevant direction is reversed: a short "above VWAP" is
        # actually a fade setup, which Zarattini says is fine. Use signed dist
        # but bucket by absolute distance favoring the direction:
        # signed_for_breakout = +dist for long, -dist for short (so >1% means
        # the breakout is already extended on its own side).
        if row["direction"] == "long":
            ext = v
        else:
            ext = -v
        if ext > 1.0:
            return ">1% extended"
        if ext > 0.3:
            return "0.3-1% extended"
        if ext > -0.3:
            return "near-VWAP +-0.3%"
        return "wrong-side of VWAP"
    df["vwap_bucket"] = df.apply(vwap_bucket, axis=1)
    h4 = bucket_stats(df, "vwap_bucket")
    print("\n=== H4: Distance from VWAP ===")
    print(h4)
    results["h4_vwap"] = h4.reset_index().to_dict(orient="records")

    # ===== Hypothesis 5: time from open =====
    def tfo_bucket(m):
        if pd.isna(m):
            return "unknown"
        if m <= 30:
            return "0-30min"
        if m <= 60:
            return "30-60min"
        if m <= 120:
            return "60-120min"
        return ">120min"
    df["tfo_bucket"] = df["mins_from_open"].apply(tfo_bucket)
    h5 = bucket_stats(df, "tfo_bucket")
    print("\n=== H5: Time from open ===")
    print(h5)
    results["h5_tfo"] = h5.reset_index().to_dict(orient="records")

    # ===== Hypothesis 6: failed-ORB reversal meta-pattern =====
    # For ORB-long trades that stopped out: did the symbol close below entry by
    # more than entry-stop magnitude that day (i.e. the fade would have worked)?
    # We approximate: r_multiple <= -1.0 and exit_reason == 'stop' means the
    # ORB-long failed cleanly. If we then check whether the symbol's session
    # close was meaningfully below the stop, this is the "fade-the-fail" edge.
    # We don't have intraday post-stop data here, but we can use the
    # session_close exit reason as the relevant follow-through observation.
    failed = df[(df["exit_reason"] == "stop")].copy()
    failed["failed_orb"] = True
    print(f"\n=== H6: Failed-ORB count: {len(failed)} ({len(failed)/len(df)*100:.1f}%)")
    # Direction-conditioned stop rate
    stop_dir = failed.groupby("direction").size()
    print("Failed-ORB by direction:")
    print(stop_dir)
    results["h6_failed_orb"] = {
        "n_failed": int(len(failed)),
        "pct_failed": float(len(failed) / len(df)),
        "by_direction": stop_dir.to_dict(),
    }

    # ===== Hypothesis 7: price tier =====
    h7 = bucket_stats(df, "tier")
    print("\n=== H7: Price tier ===")
    print(h7)
    results["h7_tier"] = h7.reset_index().to_dict(orient="records")

    # ===== Hypothesis 8: VIX regime overlay =====
    # We don't have VIX series, so use a proxy: 20-day cross-symbol realized
    # vol (avg daily range %) as a regime indicator.
    daily_vol_proxy = (df.groupby("session_date")
                        .apply(lambda g: g["abs_gap"].median())
                        .rename("daily_gap_proxy"))
    df = df.merge(daily_vol_proxy.to_frame(), left_on="session_date", right_index=True, how="left")
    df["vix_proxy_bucket"] = pd.cut(df["daily_gap_proxy"],
                                    bins=[-0.001, 0.5, 1.0, 2.0, 5.0, 100],
                                    labels=["<0.5%", "0.5-1%", "1-2%", "2-5%", ">5%"])
    h8 = bucket_stats(df, "vix_proxy_bucket")
    print("\n=== H8: VIX-proxy regime (median cross-symbol gap) ===")
    print(h8)
    results["h8_vix_proxy"] = h8.reset_index().to_dict(orient="records")

    # ===== Hypothesis 9: day of week =====
    h9 = bucket_stats(df, "day_of_week")
    print("\n=== H9: Day of week (0=Mon..4=Fri) ===")
    print(h9)
    results["h9_dow"] = h9.reset_index().to_dict(orient="records")

    # ===== Hypothesis 10: float / market-cap proxy =====
    # No fundamental data in the trades — use symbol as proxy for cap class.
    # Already covered in §7 wave-2 report. Cluster by tier (mega vs mid).
    mega = ["AAPL","MSFT","NVDA","META","TSLA","AVGO","AMD","NFLX","ADBE","CRM","ORCL","INTC","QCOM","CSCO","DIS","MU"]
    mid = ["BAC","WFC","JPM","NKE","F","DAL","AAL","SNAP","ROKU","PLTR","SOFI"]
    def cap_class(s):
        if s in mega:
            return "mega"
        if s in mid:
            return "mid"
        return "other"
    df["cap_class"] = df["symbol"].apply(cap_class)
    h10 = bucket_stats(df, "cap_class")
    print("\n=== H10: Cap class proxy ===")
    print(h10)
    results["h10_cap_class"] = h10.reset_index().to_dict(orient="records")

    # ===== Loser profile / winner profile =====
    df_sorted_pnl = df.sort_values("pnl")
    losers = df_sorted_pnl.head(10)
    winners = df_sorted_pnl.tail(10).iloc[::-1]
    print("\n=== Top 10 LOSERS ===")
    print(losers[["symbol","session_date","direction","entry_price","exit_price","pnl","r_multiple","pm_gap_pct","or5_rvol","dist_vwap_pct","tier","exit_reason"]].to_string())
    print("\n=== Top 10 WINNERS ===")
    print(winners[["symbol","session_date","direction","entry_price","exit_price","pnl","r_multiple","pm_gap_pct","or5_rvol","dist_vwap_pct","tier","exit_reason"]].to_string())
    results["top10_losers"] = losers.assign(
        session_date=losers["session_date"].astype(str),
        entry_ts=losers["entry_ts"].astype(str),
        exit_ts=losers["exit_ts"].astype(str),
    ).to_dict(orient="records")
    results["top10_winners"] = winners.assign(
        session_date=winners["session_date"].astype(str),
        entry_ts=winners["entry_ts"].astype(str),
        exit_ts=winners["exit_ts"].astype(str),
    ).to_dict(orient="records")

    # ===== Big winner attribution =====
    # Top 1% winners (n ~= 98)
    top1pct_n = max(int(len(df) * 0.01), 50)
    big_winners = df.sort_values("pnl", ascending=False).head(top1pct_n)
    big_attr = {
        "n": int(len(big_winners)),
        "total_pnl_share_of_strategy": float(big_winners["pnl"].sum() / df["pnl"].sum()),
        "win_pnl_share_of_winners": float(big_winners["pnl"].sum() / df[df["pnl"] > 0]["pnl"].sum()),
        "mean_r": float(big_winners["r_multiple"].mean()),
        "mean_gap_pct": float(big_winners["pm_gap_pct"].mean()),
        "median_gap_pct": float(big_winners["pm_gap_pct"].median()),
        "pct_catalyst": float(big_winners["catalyst_day"].mean()),
        "tier_dist": big_winners["tier"].value_counts(normalize=True).to_dict(),
        "or5_align_dist": big_winners["or5_align"].value_counts(normalize=True).to_dict(),
        "tfo_dist": big_winners["tfo_bucket"].value_counts(normalize=True).to_dict(),
        "direction_dist": big_winners["direction"].value_counts(normalize=True).to_dict(),
        "top_symbols": big_winners["symbol"].value_counts().head(8).to_dict(),
    }
    print("\n=== BIG WINNER (top 1%) ATTRIBUTION ===")
    print(json.dumps(big_attr, indent=2, default=str))
    results["big_winner_attribution"] = big_attr

    # ===== Catalyst-day filter Sharpe + walk-forward =====
    # Filter spec (FINAL): |pm_gap_pct| > 2 AND or5_rvol > 2 AND mins_from_open <= 60
    filt = df[(df["abs_gap"] > 2.0) & (df["or5_rvol"] > 2.0) & (df["mins_from_open"] <= 60)]
    filt_stats = {
        "n": int(len(filt)),
        "pct_of_total": float(len(filt) / len(df)),
        "net_pnl": float(filt["pnl"].sum()),
        "win_rate": float((filt["r_multiple"] > 0).mean()),
        "avg_r": float(filt["r_multiple"].mean()),
        "sharpe_trade": sharpe_trade(filt["r_multiple"]),
        "sharpe_daily": sharpe_daily(filt),
    }
    print("\n=== Catalyst-day filter (gap>2% AND or5_rvol>2 AND mins<=60) ===")
    print(json.dumps(filt_stats, indent=2, default=str))
    results["catalyst_filter_final"] = filt_stats

    # Walk-forward: calibrate on 2020-2022, test 2023-2024
    train = df[df["year"] <= 2022]
    test = df[df["year"] >= 2023]
    print(f"\nTrain (2020-2022): n={len(train)}, Test (2023-2024): n={len(test)}")

    # On train, scan a grid to find best (gap_thr, rvol_thr) by sharpe_daily
    best = None
    grid_results = []
    for g in [1.0, 1.5, 2.0, 2.5, 3.0]:
        for v in [1.25, 1.5, 2.0, 2.5, 3.0]:
            for tfo in [60, 90, 120]:
                cand = train[(train["abs_gap"] > g) & (train["or5_rvol"] > v) & (train["mins_from_open"] <= tfo)]
                if len(cand) < 100:
                    continue
                sd = sharpe_daily(cand)
                grid_results.append({
                    "gap": g, "rvol": v, "tfo": tfo,
                    "n_train": int(len(cand)),
                    "sharpe_train": sd,
                    "avg_r_train": float(cand["r_multiple"].mean()),
                    "wr_train": float((cand["r_multiple"]>0).mean()),
                })
                if best is None or (not np.isnan(sd) and sd > best["sharpe_train"]):
                    best = {"gap": g, "rvol": v, "tfo": tfo, "sharpe_train": sd,
                            "n_train": int(len(cand))}
    results["walk_forward_grid"] = sorted(grid_results, key=lambda r: -(r["sharpe_train"] or -99))[:20]
    print("\nWalk-forward top-20 train-set filters:")
    for r in results["walk_forward_grid"][:10]:
        print(r)

    if best is not None:
        # Apply best to test
        g, v, t = best["gap"], best["rvol"], best["tfo"]
        test_sub = test[(test["abs_gap"] > g) & (test["or5_rvol"] > v) & (test["mins_from_open"] <= t)]
        wf = {
            "best_train": best,
            "test_n": int(len(test_sub)),
            "test_sharpe_daily": sharpe_daily(test_sub),
            "test_sharpe_trade": sharpe_trade(test_sub["r_multiple"]),
            "test_avg_r": float(test_sub["r_multiple"].mean()) if len(test_sub) else None,
            "test_wr": float((test_sub["r_multiple"]>0).mean()) if len(test_sub) else None,
            "test_net_pnl": float(test_sub["pnl"].sum()) if len(test_sub) else None,
        }
        results["walk_forward_final"] = wf
        print("\nWalk-forward (best from train, applied to test):")
        print(json.dumps(wf, indent=2, default=str))

    # ===== Multi-filter stack (best-in-show) =====
    # Combine catalyst + align + tier + tfo (the four hypotheses that show edge)
    # Test on the *whole* dataset to find the highest-Sharpe filtered subset.
    stack_grid = []
    for catalyst_on in [True, False]:
        for tier_filter in [None, ["$300+","$100-200","$200-300"], ["$300+"]]:
            for align_filter in [None, ["aligned"], ["aligned","doji"]]:
                for tfo in [60, 90, 120, 360]:
                    sub = df[(df["mins_from_open"] <= tfo)]
                    if catalyst_on:
                        sub = sub[(sub["abs_gap"] > 2) & (sub["or5_rvol"] > 2)]
                    if tier_filter is not None:
                        sub = sub[sub["tier"].isin(tier_filter)]
                    if align_filter is not None:
                        sub = sub[sub["or5_align"].isin(align_filter)]
                    if len(sub) < 100:
                        continue
                    stack_grid.append({
                        "catalyst": catalyst_on,
                        "tier": tier_filter,
                        "align": align_filter,
                        "tfo": tfo,
                        "n": int(len(sub)),
                        "wr": float((sub["r_multiple"]>0).mean()),
                        "avg_r": float(sub["r_multiple"].mean()),
                        "sharpe_daily": sharpe_daily(sub),
                        "net_pnl": float(sub["pnl"].sum()),
                    })
    stack_grid_sorted = sorted([s for s in stack_grid if s["sharpe_daily"] is not None and not np.isnan(s["sharpe_daily"])],
                                key=lambda r: -r["sharpe_daily"])
    results["stack_grid_top20"] = stack_grid_sorted[:20]
    print("\n=== Top-20 multi-filter stacks (by daily Sharpe) ===")
    for r in stack_grid_sorted[:20]:
        print(r)

    # ===== Viability at $25K =====
    # For the catalyst-day filter, simulate equity curve fixed-$1000 risk.
    if len(filt) > 50:
        f_sorted = filt.sort_values("entry_ts").copy()
        f_sorted["cum_pnl"] = f_sorted["pnl"].cumsum()
        eq = 25000 + f_sorted["cum_pnl"]
        peak = eq.cummax()
        f_dd_pct = float(((eq - peak) / peak).min())
        f_dd_dollars = float((eq - peak).min())
        # Worst losing streak
        signs = (f_sorted["pnl"] > 0).astype(int).values
        worst_streak = 0
        current = 0
        for s in signs:
            if s == 0:
                current += 1
                worst_streak = max(worst_streak, current)
            else:
                current = 0
        # 6-month worst rolling P&L
        f_sorted["entry_dt"] = pd.to_datetime(f_sorted["entry_ts"])
        f_sorted = f_sorted.set_index("entry_dt")
        rolling = f_sorted["pnl"].rolling("180D").sum()
        worst_6mo = float(rolling.min())
        viability = {
            "filter": "gap>2% AND or5_rvol>2 AND mins<=60",
            "starting_equity": 25000,
            "n_trades": int(len(f_sorted)),
            "trades_per_year": float(len(f_sorted) / 5.0),
            "ending_equity": float(25000 + f_sorted["pnl"].sum()),
            "max_dd_pct": f_dd_pct,
            "max_dd_dollars": f_dd_dollars,
            "worst_losing_streak": int(worst_streak),
            "worst_6mo_pnl": worst_6mo,
            "annualized_pnl": float(f_sorted["pnl"].sum() / 5.0),
        }
        print("\n=== VIABILITY @ $25K ===")
        print(json.dumps(viability, indent=2, default=str))
        results["viability_25k"] = viability

    with open(OUT_JSON, "w") as fp:
        json.dump(results, fp, indent=2, default=str)
    print(f"\nWrote analysis to {OUT_JSON}")


if __name__ == "__main__":
    main()
