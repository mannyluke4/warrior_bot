"""Daily universe filter for the Healthy Fluctuation Framework.

This module produces the symbol list every strategy in the framework operates
on. It is **research/backtest infrastructure** — it does not touch the live
stack. It is intentionally distinct from `live_scanner.py`, which targets a
much narrower universe (small-cap gappers, ~$2-$20, <15M float). The framework
universe is broader: any mid-priced stock with healthy fluctuation potential
in the $10-$300 band with real participation.

Design source: DESIGN_HEALTHY_FLUCTUATION_FRAMEWORK.md §2 + Manny 5/17 review
(data-driven, no pre-imposed sector exclusions).
Build directive: DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3 Agent C.

Data source: Databento `EQUS.MINI` dataset (free OHLCV-1d + definition).
Float source: `scanner_results/float_cache.json` (read-only; live code's cache).

Symbols missing float info are excluded by default (`require_float=True`).
This is deliberate — the float band is a defining property of the universe
("not too tight, not too loose"). The live float_cache.json grows daily as
the live scanner runs, so coverage improves over time. Tests can set
`require_float=False` to relax this.

Output: `universe_cache/<date>.parquet` with one row per qualifying symbol:
    symbol, prev_close, adv_dollar, float_shares, day_range_pct,
    relative_volume, sector

Idempotent: re-running for a date reads from cache unless `force=True`.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

# Roots — pinned to repo layout. Universe lives next to the bot data.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_FLOAT_CACHE_PATH = _REPO_ROOT / "scanner_results" / "float_cache.json"
_UNIVERSE_CACHE_DIR = _REPO_ROOT / "universe_cache"
# Framework-owned float cache — augments the live scanner's cache.
# We do NOT modify scanner_results/float_cache.json (live code's domain).
_FRAMEWORK_FLOAT_CACHE_PATH = _UNIVERSE_CACHE_DIR / "framework_float_cache.json"


# ── Config ────────────────────────────────────────────────────────────────


@dataclass
class UniverseConfig:
    """Filter thresholds. Defaults locked per Manny 5/17 decisions."""

    price_min: float = 10.0
    price_max: float = 300.0
    adv_dollar_min: float = 10_000_000.0  # $10M 20-day average daily $ volume
    float_min: int = 20_000_000           # 20M float shares
    # 2026-05-18 Manny decision: float_max raised 200M → 10B to admit mega-caps
    # (AAPL, NVDA, TSLA etc) and reach the ~400-800-name/day universe size the
    # design doc estimated. The research-backed 200M ceiling produced only
    # ~10 names/day (e.g. 2024-01-16: SPXL/GOLD/SPOT/DKS) — too thin for Wave 2
    # backtest sample sizes. Path #1 from the universe validation note.
    float_max: int = 10_000_000_000       # 10B float shares (was 200M)
    min_day_range_pct: float = 0.02       # 2% intraday range minimum
    min_relative_volume: float = 1.5      # today / 20-day baseline
    sector_exclusions: list[str] = field(default_factory=list)  # EMPTY per Manny

    # Operational knobs (not part of the formal filter spec, but useful).
    lookback_trading_days: int = 20        # ADV / relative_volume window
    require_float: bool = True             # exclude symbols with no float data
    backfill_missing_floats: bool = True   # use yfinance to fill float gaps
    dataset: str = "EQUS.MINI"             # Databento dataset
    cache_dir: Path = field(default_factory=lambda: _UNIVERSE_CACHE_DIR)


# ── Helpers ───────────────────────────────────────────────────────────────


def _trading_days_before(target: dt.date, n: int) -> dt.date:
    """Approximate `n` trading days before `target` by walking back calendar
    days at 7/5 ratio + a small safety pad. The OHLCV result is then filtered
    to the actual prior `n` sessions. Pad guards against long holiday gaps.
    """
    # 7/5 ratio approximates the weekend skip; +7 days pads for holidays.
    calendar_days = int(n * 7 / 5) + 7
    return target - dt.timedelta(days=calendar_days)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            raw = json.load(f)
        return raw if isinstance(raw, dict) else {}
    except Exception as e:
        logger.error("Failed to read %s: %s", path, e)
        return {}


def _load_float_cache() -> dict[str, Optional[float]]:
    """Combined float cache: live scanner cache (read-only) + framework cache.

    The live scanner's `scanner_results/float_cache.json` is shared with
    `live_scanner.py` and `float_cache.py`. We treat it as read-only.

    The framework's own cache at `universe_cache/framework_float_cache.json`
    holds floats for symbols the live cache doesn't cover (e.g. AAPL/NVDA/SPY).
    Both Nones are filtered; the framework cache wins on collision.
    """
    live = _load_json(_FLOAT_CACHE_PATH)
    fw = _load_json(_FRAMEWORK_FLOAT_CACHE_PATH)
    merged: dict[str, float] = {}
    for k, v in {**live, **fw}.items():
        if v is None:
            continue
        try:
            merged[k] = float(v)
        except (TypeError, ValueError):
            continue
    return merged


def _save_framework_float_cache(cache: dict[str, Optional[float]]) -> None:
    """Persist the framework-owned float cache. Atomic write."""
    _FRAMEWORK_FLOAT_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _FRAMEWORK_FLOAT_CACHE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)
    tmp.replace(_FRAMEWORK_FLOAT_CACHE_PATH)


def _fetch_floats_yfinance(
    symbols: Sequence[str],
    timeout_per_symbol: float = 2.0,
) -> dict[str, Optional[float]]:
    """Bulk fetch float (shares outstanding) for symbols via yfinance.

    Returns a dict {symbol: float_or_None}. Symbols that error or return no
    data map to None so we don't retry them every run.

    Used as the framework's fundamentals source. The live stack uses
    FMP / EDGAR / AlphaVantage in `float_cache.py`; the framework leans on
    yfinance because (a) it's free, (b) it covers the broader $10-300
    universe, (c) it's used in research contexts and doesn't impact live
    paths. We never call this from live code.
    """
    try:
        import yfinance as yf  # noqa: WPS433
    except ImportError:
        logger.warning(
            "yfinance not available; framework float backfill skipped",
        )
        return {s: None for s in symbols}

    result: dict[str, Optional[float]] = {}
    # yfinance Tickers handles batches well in groups of ~50 to stay polite.
    batch_size = 50
    for i in range(0, len(symbols), batch_size):
        chunk = list(symbols[i:i + batch_size])
        try:
            tickers = yf.Tickers(" ".join(chunk))
            for s in chunk:
                try:
                    fi = tickers.tickers[s].fast_info
                    shares = fi.get("shares")
                    result[s] = float(shares) if shares else None
                except Exception:
                    result[s] = None
        except Exception as e:
            logger.warning("yfinance batch %d failed: %s", i, e)
            for s in chunk:
                result.setdefault(s, None)
    return result


def _is_etf_or_junk_symbol(sym: str) -> bool:
    """Heuristic junk filter — preferred shares, warrants, units, rights.

    The framework operates on common stock only. We don't have a clean
    SIC/CFI tag from EQUS.MINI definitions (those fields come back empty),
    so we fall back to symbol-suffix heuristics that live_scanner uses.
    Common-stock false positives in this filter are rare (<0.5%) at the
    cost of catching almost all preferred/warrant/unit suffixes.
    """
    if not sym or not isinstance(sym, str):
        return True
    s = sym.upper()
    # 5+ letter symbols ending in W/U/R/P are usually warrant/unit/right/preferred.
    if len(s) >= 5:
        if s[-1] in ("W", "R"):
            return True
        if s[-1] == "U" and not s.endswith("LU"):  # CLU, etc. are valid
            return True
        # Preferred suffix patterns: PRA, PRB, PFD, etc.
        if s[-2:] in ("PA", "PB", "PC", "PD", "PE", "PF", "PG", "PH"):
            return True
    # Embedded periods / dashes for class shares (we don't trade these)
    if "." in s or "-" in s:
        return True
    return False


def _databento_client():
    """Lazy import + construct. Databento is required for live use, but tests
    can monkeypatch the data-fetch methods to skip the dependency entirely.
    """
    try:
        import databento as db  # noqa: WPS433
    except ImportError as e:
        raise RuntimeError(
            "databento package required for UniverseFilter.filter_for_date. "
            "Install with: pip install databento"
        ) from e
    api_key = os.getenv("DATABENTO_API_KEY")
    if not api_key:
        # Try .env explicitly (callers may not have loaded it).
        try:
            from dotenv import load_dotenv  # noqa: WPS433
            load_dotenv(_REPO_ROOT / ".env")
            api_key = os.getenv("DATABENTO_API_KEY")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError(
            "DATABENTO_API_KEY not set. Set it in .env or environment."
        )
    return db.Historical(api_key)


# ── Filter ────────────────────────────────────────────────────────────────


class UniverseFilter:
    """Daily universe scanner.

    Usage:
        cfg = UniverseConfig()  # defaults locked per Manny 5/17 review
        uf = UniverseFilter(cfg)
        symbols = uf.filter_for_date(dt.date(2024, 1, 15))

    The returned list is the set of symbols passing every filter on `date`.
    Results are also cached to `universe_cache/<date>.parquet` for replay.
    """

    def __init__(self, config: Optional[UniverseConfig] = None):
        self.config = config or UniverseConfig()
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._float_cache = _load_float_cache()

    # ── public API ────────────────────────────────────────────────────────

    def filter_for_date(
        self,
        date: dt.date,
        force: bool = False,
    ) -> list[str]:
        """Return symbols passing all filters for `date`.

        Side effect: writes `universe_cache/<date>.parquet` with the full
        attribute row per qualifying symbol.

        If a cached parquet already exists for `date` and `force` is False,
        loads from cache. Cache file is keyed only by date — changing the
        config requires `force=True` or manually clearing the cache file.
        """
        cache_path = self._cache_path(date)
        if cache_path.exists() and not force:
            df = self.from_parquet(cache_path)
            logger.info(
                "universe[%s]: loaded %d symbols from cache (%s)",
                date, len(df), cache_path.name,
            )
            return df["symbol"].tolist()

        df = self.compute_for_date(date)
        self.to_parquet(df, cache_path)
        return df["symbol"].tolist()

    def compute_for_date(self, date: dt.date) -> pd.DataFrame:
        """Compute the full attribute table for `date` (no caching).

        Returns the per-symbol DataFrame with all filter columns populated.
        Public so callers can inspect attributes without reading cache.
        """
        # 1. Pull OHLCV-1d for [date - lookback_window, date + 1]
        cfg = self.config
        start = _trading_days_before(date, cfg.lookback_trading_days + 1)
        end = date + dt.timedelta(days=1)
        ohlcv = self._fetch_ohlcv(start, end)
        if ohlcv.empty:
            logger.warning("No OHLCV returned for %s..%s", start, end)
            return pd.DataFrame(columns=self._output_columns())

        # 2. Resolve instrument_id → raw_symbol via definitions on `date`
        defs = self._fetch_definitions(date)
        if defs.empty:
            logger.warning("No definitions returned for %s", date)
            return pd.DataFrame(columns=self._output_columns())

        ohlcv = ohlcv.merge(
            defs[["instrument_id", "raw_symbol"]].drop_duplicates("instrument_id"),
            on="instrument_id",
            how="left",
        )
        ohlcv = ohlcv.dropna(subset=["raw_symbol"]).rename(
            columns={"raw_symbol": "symbol"},
        )
        # Drop junk symbol patterns up front to keep downstream math cheap.
        ohlcv = ohlcv[~ohlcv["symbol"].apply(_is_etf_or_junk_symbol)]

        # 3. Compute per-symbol features for the target date
        df = self._compute_features(ohlcv, date)
        if df.empty:
            return pd.DataFrame(columns=self._output_columns())

        # 4. Attach float + sector. Backfill missing floats via yfinance
        # *after* the cheap filters have narrowed the candidate set — we only
        # need float data for symbols passing price + ADV + day-range + RV.
        df = self._prefilter_for_float(df)
        df["float_shares"] = df["symbol"].map(self._float_cache)
        if cfg.require_float and self.config.backfill_missing_floats:
            missing = df.loc[df["float_shares"].isna(), "symbol"].tolist()
            if missing:
                self._backfill_floats(missing)
                df["float_shares"] = df["symbol"].map(self._float_cache)

        df["sector"] = None  # sector data not available from EQUS.MINI; placeholder

        # 5. Apply filters
        return self._apply_filters(df)

    def _prefilter_for_float(self, df: pd.DataFrame) -> pd.DataFrame:
        """Drop rows that can't pass the static filters (price + ADV) before
        we spend network calls backfilling float data. We keep day-range and
        relative-volume filters for AFTER float — those vary day-to-day and a
        symbol's float doesn't, so we want it cached even if today's RV is
        low. This keeps yfinance calls bounded to ~500 symbols/day rather
        than ~10K, and the float cache accumulates across runs.
        """
        cfg = self.config
        if df.empty:
            return df
        return df.dropna(subset=[
            "prev_close", "today_open", "today_high", "today_low",
            "today_close", "today_volume", "adv_dollar", "avg_volume_20d",
        ]).query(
            "prev_close >= @cfg.price_min and prev_close <= @cfg.price_max "
            "and adv_dollar >= @cfg.adv_dollar_min"
        ).copy()

    def _backfill_floats(self, symbols: Sequence[str]) -> None:
        """Fetch float for missing symbols and persist to the framework cache."""
        if not symbols:
            return
        logger.info(
            "universe: backfilling float for %d symbols via yfinance", len(symbols),
        )
        fresh = _fetch_floats_yfinance(symbols)
        # Update in-memory + on-disk caches.
        fw_cache = _load_json(_FRAMEWORK_FLOAT_CACHE_PATH)
        fw_cache.update(fresh)
        _save_framework_float_cache(fw_cache)
        # Refresh combined cache from disk.
        self._float_cache = _load_float_cache()

    def to_parquet(self, df: pd.DataFrame, path: Path) -> None:
        """Persist the filtered universe to parquet."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, index=False)
        logger.info("universe: wrote %d rows to %s", len(df), path)

    def from_parquet(self, path: Path) -> pd.DataFrame:
        """Load a previously cached universe parquet."""
        return pd.read_parquet(path)

    # ── data fetching (databento-backed; monkeypatched in tests) ─────────

    def _fetch_ohlcv(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        """Fetch OHLCV-1d for ALL_SYMBOLS over [start, end)."""
        client = _databento_client()
        data = client.timeseries.get_range(
            dataset=self.config.dataset,
            schema="ohlcv-1d",
            symbols="ALL_SYMBOLS",
            start=start.isoformat(),
            end=end.isoformat(),
            stype_in="raw_symbol",
        )
        df = data.to_df()
        if df.empty:
            return df
        df = df.reset_index()  # bring ts_event out of the index
        # Numeric columns come back as scaled ints in some databento builds;
        # the OHLCV-1d schema decodes to float automatically in 0.78+ via
        # `pretty_*` fields, but `to_df` already maps them to plain columns.
        return df[["ts_event", "instrument_id", "open", "high", "low", "close", "volume"]]

    def _fetch_definitions(self, date: dt.date) -> pd.DataFrame:
        """Fetch definition records for `date` (used for instrument_id ↔ symbol)."""
        client = _databento_client()
        data = client.timeseries.get_range(
            dataset=self.config.dataset,
            schema="definition",
            symbols="ALL_SYMBOLS",
            start=date.isoformat(),
            end=(date + dt.timedelta(days=1)).isoformat(),
            stype_in="raw_symbol",
        )
        df = data.to_df()
        if df.empty:
            return df
        return df.reset_index()[["instrument_id", "raw_symbol", "instrument_class"]]

    # ── feature computation ──────────────────────────────────────────────

    def _compute_features(
        self,
        ohlcv: pd.DataFrame,
        target_date: dt.date,
    ) -> pd.DataFrame:
        """Build per-symbol feature table indexed by symbol.

        Features:
            prev_close       — close on `target_date`'s prior trading day
            today_open/high/low/close/volume  — on `target_date`
            day_range_pct    — (high - low) / open on `target_date`
            adv_dollar       — mean(close*volume) over 20 prior trading days
            relative_volume  — today's volume / 20-day mean daily volume
        """
        ohlcv = ohlcv.copy()
        # Pandas `Timestamp` -> date for grouping; the OHLCV-1d ts_event is
        # midnight UTC on the trading day.
        ohlcv["date"] = pd.to_datetime(ohlcv["ts_event"]).dt.date
        ohlcv["dollar_vol"] = ohlcv["close"] * ohlcv["volume"]

        # Split today vs prior.
        today = ohlcv[ohlcv["date"] == target_date].copy()
        prior = ohlcv[ohlcv["date"] < target_date]

        if today.empty:
            logger.warning(
                "compute_features: no OHLCV rows for target_date=%s; "
                "is it a market holiday?", target_date,
            )
            return pd.DataFrame(columns=self._output_columns())

        # 20-day stats over prior sessions (each symbol's own history).
        # Use the last `lookback_trading_days` sessions per symbol.
        n = self.config.lookback_trading_days

        def _last_n(group: pd.DataFrame) -> pd.Series:
            g = group.sort_values("date").tail(n)
            return pd.Series({
                "adv_dollar": g["dollar_vol"].mean() if len(g) else float("nan"),
                "avg_volume_20d": g["volume"].mean() if len(g) else float("nan"),
                "n_prior_sessions": len(g),
                "prev_close": g["close"].iloc[-1] if len(g) else float("nan"),
            })

        # Group + apply is slow but readable on ~10K symbols. Vectorizable
        # later if needed (the cost is one-shot per backtest day).
        prior_stats = (
            prior.groupby("symbol", group_keys=False)
            .apply(_last_n)
            .reset_index()
        )

        today = today[[
            "symbol", "open", "high", "low", "close", "volume", "dollar_vol",
        ]].rename(columns={
            "open": "today_open",
            "high": "today_high",
            "low": "today_low",
            "close": "today_close",
            "volume": "today_volume",
            "dollar_vol": "today_dollar_vol",
        })

        df = today.merge(prior_stats, on="symbol", how="left")

        # Day range vs open (matches research spec).
        df["day_range_pct"] = (
            (df["today_high"] - df["today_low"]) / df["today_open"]
        )
        # Relative volume vs the 20-day average.
        df["relative_volume"] = df["today_volume"] / df["avg_volume_20d"]

        return df

    # ── filter application ────────────────────────────────────────────────

    def _apply_filters(self, df: pd.DataFrame) -> pd.DataFrame:
        cfg = self.config
        if df.empty:
            return df
        df = df.copy()

        # Drop NaNs gracefully — missing data == excluded.
        n0 = len(df)
        df = df.dropna(subset=[
            "prev_close", "today_open", "today_high", "today_low",
            "today_close", "today_volume", "adv_dollar", "avg_volume_20d",
        ])
        n_after_data = len(df)

        # Price band — applied on prev_close per spec ("prior session close").
        df = df[(df["prev_close"] >= cfg.price_min) & (df["prev_close"] <= cfg.price_max)]
        n_after_price = len(df)

        # ADV (20-day dollar volume average).
        df = df[df["adv_dollar"] >= cfg.adv_dollar_min]
        n_after_adv = len(df)

        # Float — None counts as missing; gate via `require_float`.
        if cfg.require_float:
            df = df[df["float_shares"].notna()]
            df = df[
                (df["float_shares"] >= cfg.float_min)
                & (df["float_shares"] <= cfg.float_max)
            ]
        else:
            # If a symbol HAS float data, apply the band; otherwise pass through.
            has_float = df["float_shares"].notna()
            in_band = (
                (df["float_shares"] >= cfg.float_min)
                & (df["float_shares"] <= cfg.float_max)
            )
            df = df[~has_float | in_band]
        n_after_float = len(df)

        # Day range %.
        df = df[df["day_range_pct"] >= cfg.min_day_range_pct]
        n_after_range = len(df)

        # Relative volume.
        df = df[df["relative_volume"] >= cfg.min_relative_volume]
        n_after_rv = len(df)

        # Sector exclusions — default empty list per Manny 5/17.
        if cfg.sector_exclusions:
            df = df[~df["sector"].isin(cfg.sector_exclusions)]
        n_after_sector = len(df)

        logger.info(
            "universe filter funnel: start=%d data_valid=%d price=%d adv=%d "
            "float=%d range=%d rvol=%d sector=%d",
            n0, n_after_data, n_after_price, n_after_adv,
            n_after_float, n_after_range, n_after_rv, n_after_sector,
        )

        # Output columns per spec.
        return df[self._output_columns()].sort_values(
            "adv_dollar", ascending=False,
        ).reset_index(drop=True)

    @staticmethod
    def _output_columns() -> list[str]:
        return [
            "symbol",
            "prev_close",
            "adv_dollar",
            "float_shares",
            "day_range_pct",
            "relative_volume",
            "sector",
        ]

    def _cache_path(self, date: dt.date) -> Path:
        return self.config.cache_dir / f"{date.isoformat()}.parquet"


# ── CLI smoke test ────────────────────────────────────────────────────────


def _print_summary(symbols: Sequence[str], df: pd.DataFrame) -> None:
    print(f"\nUniverse size: {len(symbols)} symbols")
    if df.empty:
        return
    print("\nTop 20 by 20-day ADV dollar volume:")
    print(
        df.head(20)[[
            "symbol", "prev_close", "adv_dollar", "float_shares",
            "day_range_pct", "relative_volume",
        ]].to_string(index=False)
    )
    print("\nPrice tier distribution:")
    tiers = pd.cut(
        df["prev_close"],
        bins=[10, 20, 50, 100, 200, 300],
        labels=["$10-20", "$20-50", "$50-100", "$100-200", "$200-300"],
    )
    print(tiers.value_counts().sort_index().to_string())
    print(f"\nMedian day range: {df['day_range_pct'].median():.2%}")
    print(f"Median relative volume: {df['relative_volume'].median():.2f}x")
    print(f"Median float: {df['float_shares'].median()/1e6:.1f}M shares")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="Universe filter smoke test")
    parser.add_argument(
        "--date", default="2024-01-16",
        help="Trading day to scan (YYYY-MM-DD). Default: 2024-01-16.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Recompute even if cache exists.",
    )
    parser.add_argument(
        "--no-require-float", action="store_true",
        help="Don't require float data (pass through unknown floats).",
    )
    args = parser.parse_args()

    target = dt.date.fromisoformat(args.date)
    cfg = UniverseConfig(require_float=not args.no_require_float)
    uf = UniverseFilter(cfg)
    print(f"Computing universe for {target}...")
    print(f"Config: {asdict(cfg) | {'cache_dir': str(cfg.cache_dir)}}")

    symbols = uf.filter_for_date(target, force=args.force)
    df = uf.from_parquet(uf._cache_path(target))
    _print_summary(symbols, df)
