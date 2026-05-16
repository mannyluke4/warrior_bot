"""Bulk pre-fetcher: pull 1m bars for the ORB universe across 2020-2024.

Run this once to populate `tick_cache_databento/<symbol>/1m_<date>.parquet`.
Subsequent backtest runs replay from cache.

Usage:
    python -m backtest.orb_fetch_all                       # full universe, 2020-2024
    python -m backtest.orb_fetch_all --start 2024-01-01 --end 2024-12-31  # one year
    python -m backtest.orb_fetch_all --symbols AAPL MSFT   # subset

The fetcher is idempotent (cache-aware). Empty-day markers are cached so
non-trading days don't get refetched.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.orb_data_fetcher import ORB_UNIVERSE, fetch_1m_bars_range


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default="2024-12-31")
    parser.add_argument("--symbols", nargs="*", default=None)
    parser.add_argument("--dataset", default="XNAS.ITCH")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    log = logging.getLogger("orb_fetch_all")

    symbols = args.symbols or ORB_UNIVERSE
    start = date.fromisoformat(args.start)
    end = date.fromisoformat(args.end)

    log.info("Fetching %d symbols %s..%s on %s", len(symbols), start, end, args.dataset)
    t0 = time.time()

    total_days = 0
    for i, sym in enumerate(symbols, 1):
        t_sym = time.time()
        try:
            res = fetch_1m_bars_range([sym], start, end, dataset=args.dataset)
        except Exception as e:
            log.warning("[%s] failed: %s", sym, e)
            continue
        elapsed_sym = time.time() - t_sym
        total_days += len(res)
        log.info("[%d/%d] %s: %d days (%.1fs)", i, len(symbols), sym, len(res), elapsed_sym)

    elapsed = time.time() - t0
    log.info("Done. Total %d symbol-days fetched in %.1fs", total_days, elapsed)


if __name__ == "__main__":
    main()
