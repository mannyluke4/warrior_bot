"""
VWAP-MR forensic feature enrichment.

For each trade, compute features at the entry bar:
- regime: vwap slope classification over prior 10 bars (flat/up/down)
- session vwap value at entry
- distance from vwap in σ-units (σ from cumulative volume-weighted dispersion)
- price's distance above VWAP in pct
- time-since-touch: how many minutes price has been outside the +2σ band
- intraday-range pct (today's high-low / vwap)
- entry minute-of-session (0 = 09:30)
- prior 5-bar return (momentum at entry)
- bar volume vs prior 20-bar median (volume confirmation)

Writes enriched parquet to backtest_archive/wave3_portfolio/trades_VWAP-MR_enriched.parquet
"""
import pandas as pd
import numpy as np
from pathlib import Path
import sys

TRADES_CSV = Path("backtest_archive/wave3_portfolio/trades_VWAP-Mean-Reversion_fixed_dollar.csv")
TICK_DIR = Path("tick_cache_databento")
OUT_PATH = Path("backtest_archive/wave3_portfolio/trades_VWAP-MR_enriched.parquet")

# --- Session window: 09:30 - 16:00 ET (regular hours) for VWAP computation
SESSION_START_HOUR = 9
SESSION_START_MIN = 30
SESSION_END_HOUR = 16
SESSION_END_MIN = 0


def compute_session_vwap(bars: pd.DataFrame) -> pd.DataFrame:
    """Filter to regular hours; compute cumulative VWAP, σ (volume-weighted), slope_10bar."""
    if bars.empty:
        return bars
    # Filter to RTH 09:30-16:00 (assume ts_event is in ET-naive)
    t = bars["ts_event"]
    mins = t.dt.hour * 60 + t.dt.minute
    rth_mask = (mins >= 9 * 60 + 30) & (mins < 16 * 60)
    b = bars.loc[rth_mask].copy().reset_index(drop=True)
    if b.empty:
        return b
    typ = (b["high"] + b["low"] + b["close"]) / 3.0
    vol = b["volume"].astype(float).clip(lower=0)
    cum_v = vol.cumsum().replace(0, np.nan)
    cum_pv = (typ * vol).cumsum()
    vwap = cum_pv / cum_v
    # volume-weighted running σ vs running vwap
    sq = ((typ - vwap) ** 2) * vol
    cum_var = sq.cumsum() / cum_v
    sigma = np.sqrt(cum_var.clip(lower=0))
    b["vwap"] = vwap
    b["sigma"] = sigma
    b["typical"] = typ
    # slope over last 10 bars: (vwap_now - vwap_{n-10}) / vwap_now / 10
    n = 10
    b["vwap_slope_pct_per_bar"] = (b["vwap"] - b["vwap"].shift(n)) / b["vwap"] / n
    # day's running min/max
    b["day_high"] = b["high"].cummax()
    b["day_low"] = b["low"].cummin()
    return b


def classify_regime(slope_pct_per_bar: float, threshold: float = 2e-5) -> str:
    if slope_pct_per_bar is None or np.isnan(slope_pct_per_bar):
        return "unknown"
    if slope_pct_per_bar >= threshold:
        return "trending_up"
    if slope_pct_per_bar <= -threshold:
        return "trending_down"
    return "flat"


def time_since_above_2sigma(b: pd.DataFrame, idx: int) -> int:
    """Look back; count consecutive minutes prior where close was >= vwap + 2σ.

    Returns number of bars (inclusive of current) where condition holds going
    backwards from idx. 1 = just touched now."""
    cnt = 0
    for j in range(idx, -1, -1):
        if b["close"].iat[j] >= b["vwap"].iat[j] + 2 * b["sigma"].iat[j]:
            cnt += 1
        else:
            break
    return cnt


def enrich():
    trades = pd.read_csv(TRADES_CSV, parse_dates=["entry_ts", "exit_ts", "session_date"])
    # All shorts — confirm
    assert (trades["direction"] == "short").all(), "Expected all shorts"

    rows = []
    # Group by (symbol, session_date) to load parquet once per session
    grp = trades.groupby([trades["symbol"], trades["session_date"].dt.strftime("%Y-%m-%d")])
    total = len(grp)
    done = 0
    for (sym, dstr), tr_grp in grp:
        done += 1
        if done % 250 == 0:
            print(f"  {done}/{total} session-symbols", file=sys.stderr)
        path = TICK_DIR / sym / f"1m_{dstr}.parquet"
        if not path.exists():
            for _, row in tr_grp.iterrows():
                d = row.to_dict()
                d["features_ok"] = False
                rows.append(d)
            continue
        try:
            bars = pd.read_parquet(path)
        except Exception:
            for _, row in tr_grp.iterrows():
                d = row.to_dict()
                d["features_ok"] = False
                rows.append(d)
            continue
        b = compute_session_vwap(bars)
        if b.empty:
            for _, row in tr_grp.iterrows():
                d = row.to_dict()
                d["features_ok"] = False
                rows.append(d)
            continue
        # Build lookup by ts
        b_index = pd.Index(b["ts_event"])
        for _, row in tr_grp.iterrows():
            ts = row["entry_ts"]
            try:
                idx = b_index.get_loc(ts)
                if isinstance(idx, slice):
                    idx = idx.start
            except KeyError:
                # find nearest within 1m
                diffs = (b["ts_event"] - ts).abs()
                idx = diffs.idxmin()
                if diffs.iat[idx] > pd.Timedelta(minutes=1):
                    d = row.to_dict()
                    d["features_ok"] = False
                    rows.append(d)
                    continue
            entry_price = row["entry_price"]
            vwap_v = b["vwap"].iat[idx]
            sigma_v = b["sigma"].iat[idx]
            slope = b["vwap_slope_pct_per_bar"].iat[idx]
            regime = classify_regime(slope)
            # σ-distance: price above vwap in σ units (will be ≥2 typically for entry)
            sigma_dist = (entry_price - vwap_v) / sigma_v if sigma_v and sigma_v > 0 else np.nan
            pct_above_vwap = (entry_price - vwap_v) / vwap_v * 100 if vwap_v else np.nan
            t_since = time_since_above_2sigma(b, idx)
            # day's range pct so far
            dh = b["day_high"].iat[idx]
            dl = b["day_low"].iat[idx]
            day_range_pct = (dh - dl) / vwap_v * 100 if vwap_v else np.nan
            # 5-bar momentum prior to entry
            prior_5 = b["close"].iat[max(0, idx - 5)]
            momentum_5_pct = (entry_price - prior_5) / prior_5 * 100 if prior_5 else np.nan
            # bar volume vs prior 20-bar median
            vols = b["volume"].iloc[max(0, idx - 20):idx]
            v_med = vols.median() if len(vols) else np.nan
            bar_vol_ratio = b["volume"].iat[idx] / v_med if v_med and v_med > 0 else np.nan
            min_of_sess = int(idx)  # since b starts at 9:30 in RTH window, idx ~ minutes from 09:30
            # also expose entry minute of day in actual session terms
            entry_mins = ts.hour * 60 + ts.minute - (9 * 60 + 30)

            d = row.to_dict()
            d["features_ok"] = True
            d["vwap_at_entry"] = vwap_v
            d["sigma_at_entry"] = sigma_v
            d["vwap_slope"] = slope
            d["regime"] = regime
            d["sigma_dist"] = sigma_dist
            d["pct_above_vwap"] = pct_above_vwap
            d["time_since_2sigma_bars"] = t_since
            d["day_range_pct"] = day_range_pct
            d["momentum_5bar_pct"] = momentum_5_pct
            d["bar_vol_ratio"] = bar_vol_ratio
            d["min_of_session"] = entry_mins
            rows.append(d)

    out = pd.DataFrame(rows)
    print(f"Enriched {len(out)} rows; features_ok={out['features_ok'].sum()}", file=sys.stderr)
    out.to_parquet(OUT_PATH, index=False)
    print(f"Wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    enrich()
