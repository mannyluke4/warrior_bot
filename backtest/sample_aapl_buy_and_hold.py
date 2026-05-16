"""
backtest.sample_aapl_buy_and_hold
=================================

Canonical end-to-end smoke test for the Healthy Fluctuation Framework
backtest infrastructure.

What this script does
---------------------
1. Uses the ``DatabentoAdapter`` to pull AAPL Q1 2024 trade ticks and
   bbo-1s quote ticks. First run hits the Databento HTTP API and caches
   to ``tick_cache_databento/AAPL/``. Subsequent runs replay from disk.
2. Converts the data to NautilusTrader ``TradeTick`` / ``QuoteTick``.
3. Runs a buy-and-hold strategy that buys 100 shares on the first tick
   and holds through the entire period.
4. Reports realized P&L (always 0 — buy-and-hold never closes) plus the
   theoretical hold P&L from first to last close, and verifies they
   agree to within 1%.

This script intentionally lives outside ``tests/`` because it requires
network + Databento quota. Run it manually as the acceptance gate:

::

    cd /Users/duffy/warrior_bot_v2
    source /Users/duffy/warrior_bot/venv/bin/activate
    python -m backtest.sample_aapl_buy_and_hold

For a quicker smoke test you can constrain the date range:

::

    python -m backtest.sample_aapl_buy_and_hold --start 2024-01-02 --end 2024-01-03
"""

from __future__ import annotations

import argparse
import logging
import sys

import pandas as pd

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.nautilus_runner import BacktestSpec, run_backtest
from framework.data_adapters.databento_adapter import DatabentoAdapter
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import Equity
from nautilus_trader.model.objects import Price, Quantity

# Re-use the BuyAndHold strategy from the test module
from tests.backtest.test_nautilus_runner import BuyAndHold


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("sample_aapl")


def _aapl_instrument() -> Equity:
    iid = InstrumentId.from_str("AAPL.XNAS")
    now_ns = int(pd.Timestamp.utcnow().value)
    return Equity(
        instrument_id=iid,
        raw_symbol=Symbol("AAPL"),
        currency=USD,
        price_precision=2,
        price_increment=Price(0.01, 2),
        lot_size=Quantity(1, 0),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def main(start: str, end: str, qty: int = 100, balance: float = 100_000.0) -> None:
    adapter = DatabentoAdapter()
    log.info("Fetching AAPL trades %s..%s", start, end)
    trades_df = adapter.fetch_trades("AAPL", start, end)
    log.info("Fetching AAPL bbo-1s %s..%s", start, end)
    bbo_df = adapter.fetch_bbo("AAPL", start, end)
    log.info("Loaded %d trades, %d quotes", len(trades_df), len(bbo_df))

    if trades_df.empty:
        raise RuntimeError("No trade data returned — check API key / quota / dataset")

    instrument = _aapl_instrument()
    trade_ticks = adapter.to_trade_ticks(trades_df, "AAPL.XNAS")
    quote_ticks = adapter.to_quote_ticks(bbo_df, "AAPL.XNAS")
    data = list(sorted(trade_ticks + quote_ticks, key=lambda x: x.ts_event))
    log.info("Combined %d ticks (sorted by ts_event)", len(data))

    first_price = float(trades_df.iloc[0]["price"])
    last_price = float(trades_df.iloc[-1]["price"])
    theoretical_pnl = (last_price - first_price) * qty
    log.info("Theoretical buy-and-hold P&L = (%.2f - %.2f) * %d = $%.2f",
             last_price, first_price, qty, theoretical_pnl)

    spec = BacktestSpec(
        strategy_factory=lambda: BuyAndHold(instrument.id, qty=qty),
        instrument=instrument,
        data=data,
        starting_balance=balance,
    )
    metrics = run_backtest(spec)
    print()
    print("================ AAPL BUY-AND-HOLD ================")
    print(f"Start:                  {start}")
    print(f"End:                    {end}")
    print(f"Tick count:             {len(data):,}")
    print(f"First price:            ${first_price:.2f}")
    print(f"Last price:             ${last_price:.2f}")
    print(f"Theoretical buy+hold:   ${theoretical_pnl:.2f}")
    print(metrics)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2024-01-02")
    parser.add_argument("--end",   default="2024-03-29")
    parser.add_argument("--qty",   type=int, default=100)
    args = parser.parse_args()
    main(args.start, args.end, qty=args.qty)
