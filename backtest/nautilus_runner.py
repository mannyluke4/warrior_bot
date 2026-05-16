"""
backtest.nautilus_runner
========================

Thin wrapper around NautilusTrader's ``BacktestEngine`` that the Healthy
Fluctuation Framework calls into.

Goals
-----
* Hide the BacktestEngine wiring boilerplate (venue, account, instruments,
  data, fill model, fee model, strategy) behind a single function.
* Accept a *strategy spec* — for Wave 1 this is just a callable that yields
  a ``Strategy`` instance. Wave 2 (YAML registry) plugs in here.
* Return a standardized ``MetricsResult`` so all backtest output is
  comparable across engines / waves.

Defaults from research §3
-------------------------
* Fill modeling: 5% of bar volume cap (``liquidity_consumption=True``).
* Queue position 20-40% discount per research §3 — modelled via
  ``prob_fill_on_limit=0.7`` (single tuneable knob; richer queue modelling
  belongs in Wave 4 with L2 replay).
* Bar/trade execution both enabled so the engine can use whichever data
  stream is loaded.

Public surface
--------------
``run_backtest(strategy_factory, instrument, data, ...)`` is the only
function callers need. See its docstring for the signature.

Author: Agent A (Wave 1 — Healthy Fluctuation Framework)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Sequence

import pandas as pd

from nautilus_trader.backtest.engine import BacktestEngine, BacktestEngineConfig
from nautilus_trader.backtest.models import FillModel
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AccountType, OmsType, BookType
from nautilus_trader.model.identifiers import Venue, TraderId
from nautilus_trader.model.objects import Money

from backtest.metrics import MetricsResult, summarize


__all__ = ["run_backtest", "BacktestSpec", "NautilusRunner"]


log = logging.getLogger(__name__)


def _coerce_float(value: Any) -> float:
    """Coerce a possibly-NA pandas cell to a float (default 0.0)."""
    if value is None:
        return 0.0
    try:
        if pd.isna(value):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        try:
            return float(str(value).split()[0])
        except (ValueError, TypeError, IndexError):
            return 0.0


def _coerce_ts(value: Any) -> pd.Timestamp | None:
    """Coerce a possibly-NA pandas cell to a Timestamp (or None)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    try:
        return pd.Timestamp(value)
    except (TypeError, ValueError):
        return None


def _coerce_pnl(value: Any) -> float:
    """Coerce a Nautilus PnL value to a float.

    Nautilus emits ``Money`` objects formatted as ``"<amount> <currency>"`` in
    pandas reports (e.g. ``"123.45 USD"``). Handle that, float, int, and None.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        if not value:
            return 0.0
        # "<num> <currency>" form
        head = value.split()[0]
        try:
            return float(head)
        except ValueError:
            return 0.0
    # Fall through to str()
    try:
        return float(str(value).split()[0])
    except (ValueError, TypeError):
        return 0.0


@dataclass
class BacktestSpec:
    """All inputs the Nautilus runner needs.

    Wave 2 will wrap this in a richer YAML-driven ``StrategySpec``; for now we
    keep it minimal so tests don't depend on yet-unwritten code.
    """

    strategy_factory: Callable[[], Any]
    """Zero-arg callable that returns a NautilusTrader ``Strategy`` instance."""

    instrument: Any
    """A nautilus_trader Instrument (e.g. Equity)."""

    data: Sequence[Any]
    """Sequence of Data objects: TradeTick, QuoteTick, Bar, ..."""

    starting_balance: float = 100_000.0
    venue_name: str = "XNAS"
    trader_id: str = "BACKTESTER-001"

    # Fill modeling per research §3
    prob_fill_on_limit: float = 0.7   # ~30% queue-position discount
    prob_slippage: float = 0.0
    bar_execution: bool = True
    trade_execution: bool = True
    liquidity_consumption: bool = True   # 5% of bar volume cap is engine-internal default

    # Optional date filters (None = use all loaded data)
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None


class NautilusRunner:
    """Stateful runner wrapping ``BacktestEngine``.

    Most callers should use :func:`run_backtest` (functional wrapper). Reach
    for ``NautilusRunner`` directly when you want to keep the engine alive
    across multiple ``run`` calls (e.g. parameter sweeps that share data).
    """

    def __init__(self, spec: BacktestSpec):
        self.spec = spec
        self.engine: BacktestEngine | None = None
        self.venue = Venue(spec.venue_name)

    def build(self) -> BacktestEngine:
        config = BacktestEngineConfig(
            trader_id=TraderId(self.spec.trader_id),
        )
        engine = BacktestEngine(config=config)
        engine.add_venue(
            venue=self.venue,
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=USD,
            starting_balances=[Money(self.spec.starting_balance, USD)],
            fill_model=FillModel(
                prob_fill_on_limit=self.spec.prob_fill_on_limit,
                prob_slippage=self.spec.prob_slippage,
                random_seed=42,
            ),
            bar_execution=self.spec.bar_execution,
            trade_execution=self.spec.trade_execution,
            liquidity_consumption=self.spec.liquidity_consumption,
            book_type=BookType.L1_MBP,
        )
        engine.add_instrument(self.spec.instrument)
        if self.spec.data:
            engine.add_data(list(self.spec.data))
        engine.add_strategy(self.spec.strategy_factory())
        self.engine = engine
        return engine

    def run(self) -> MetricsResult:
        if self.engine is None:
            self.build()
        assert self.engine is not None

        t0 = time.perf_counter()
        kwargs: dict[str, Any] = {}
        if self.spec.start is not None:
            kwargs["start"] = self.spec.start
        if self.spec.end is not None:
            kwargs["end"] = self.spec.end
        self.engine.run(**kwargs)
        elapsed = time.perf_counter() - t0
        log.info("[nautilus_runner] engine run completed in %.2fs", elapsed)
        return self._extract_metrics()

    # ---- result extraction ---------------------------------------------

    def _extract_metrics(self) -> MetricsResult:
        assert self.engine is not None
        trades: list[dict] = []
        positions_report = self.engine.trader.generate_positions_report()
        fills_report = self.engine.trader.generate_order_fills_report()

        # Build trade records from closed positions when available; fall back
        # to fill pairs when positions report is sparse.
        if not positions_report.empty:
            for _, p in positions_report.iterrows():
                pnl = _coerce_pnl(p.get("realized_pnl"))
                trades.append({
                    "symbol": str(p.get("instrument_id", "")),
                    "side": "long" if p.get("entry") == "BUY" else "short",
                    "entry_ts": _coerce_ts(p.get("ts_opened")),
                    "exit_ts":  _coerce_ts(p.get("ts_closed")),
                    "entry_price": _coerce_float(p.get("avg_px_open")),
                    "exit_price":  _coerce_float(p.get("avg_px_close")),
                    "qty": int(_coerce_float(p.get("quantity"))),
                    "pnl": pnl,
                    "r_multiple": None,
                })

        # Equity curve from account report (best-effort — Nautilus emits one
        # snapshot per account event)
        equity_curve: pd.Series | None = None
        try:
            acct_report = self.engine.trader.generate_account_report(self.venue)
            if not acct_report.empty and "total" in acct_report.columns:
                vals = pd.to_numeric(
                    acct_report["total"].astype(str).str.split().str[0],
                    errors="coerce",
                ).dropna()
                if not vals.empty:
                    equity_curve = vals.reset_index(drop=True)
        except Exception as exc:
            log.warning("[nautilus_runner] could not build equity curve: %s", exc)

        return summarize(trades=trades, equity_curve=equity_curve)

    def dispose(self) -> None:
        if self.engine is not None:
            self.engine.dispose()
            self.engine = None


def run_backtest(spec: BacktestSpec) -> MetricsResult:
    """One-shot helper: build engine, run, extract metrics, dispose."""
    runner = NautilusRunner(spec)
    try:
        return runner.run()
    finally:
        runner.dispose()
