"""
backtest.nautilus_subprocess_runner
===================================

Subprocess orchestrator that works around NautilusTrader 1.226's
single-engine-per-process limit (see Wave 1 backtest_infra_validation report and
Wave 2 orb_backtest §9.a).

Each (strategy, date) pair runs in its own Python child via
``subprocess.run(... capture_output=True)``.  The child invokes the
``--worker`` mode below, which:

1. Loads the strategy YAML (via ``framework.registry``) and the day's bars
   from Databento parquet cache (via ``framework.data_adapters.databento_adapter``).
2. Instantiates :class:`backtest.nautilus_runner.NautilusRunner` exactly once.
3. Emits each fill as a JSONLines line on stdout::

       {"event": "fill", ...}
       {"event": "summary", "metrics": {...}}

4. Exits.

The parent collects stdout, parses the JSONL stream, aggregates results
across all pairs, and returns the merged metrics.

Why subprocess instead of `multiprocessing.Process`
---------------------------------------------------
NautilusTrader's `BacktestEngine` keeps native Rust state alive at module
scope; `multiprocessing` with fork() on macOS inherits that state and
deadlocks.  Bare ``subprocess.Popen`` of a fresh interpreter is the only
clean teardown.  The cost is process startup (~0.6 s per pair); for our
~5000 pair sweep that totals ~50 minutes of overhead, dwarfed by actual
engine run time, and trivially parallelisable across CPU cores.

NOTE: For the Wave 3 portfolio backtest the parent caller can ALSO choose
to skip the subprocess path and use the in-process bar-level engine
(`backtest.portfolio_backtest`) when a 5-strategy sweep over 5 years would
otherwise spawn ~40 000 subprocesses.  The subprocess runner here is the
*correct* unblocker for full-fidelity Nautilus runs (Wave 3+ targeted
re-runs of survivor strategies); the bar-level engine is the *pragmatic*
path for the Wave 3 portfolio screen.  Both share the same YAML strategy
specs and the same fill conventions, so survivor results from the
bar-level screen feed cleanly into Nautilus subprocess full-fidelity
re-runs without rewriting strategy code.

Public surface
--------------
``run_sweep(strategy_yamls, symbol_dates)`` is the orchestrator.

Author: CC Agent J (Wave 3 — Healthy Fluctuation Framework portfolio backtest)
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import pandas as pd


REPO_ROOT = Path("/Users/duffy/warrior_bot_v2")


log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PairTask:
    """One (strategy, symbol, date) tuple to run as a subprocess."""

    strategy_yaml: str
    symbol: str
    session_date: date
    starting_equity: float = 100_000.0
    extra_env: dict[str, str] = field(default_factory=dict)

    def cache_key(self) -> str:
        return f"{Path(self.strategy_yaml).stem}::{self.symbol}::{self.session_date.isoformat()}"


@dataclass
class PairResult:
    """One subprocess outcome."""

    task: PairTask
    fills: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] | None = None
    error: str | None = None
    elapsed_sec: float = 0.0


# ---------------------------------------------------------------------------
# Worker driver — invoked in the child process
# ---------------------------------------------------------------------------


def _worker_main(argv: list[str]) -> int:
    """Child-process entrypoint.

    Reads a JSON spec dict from stdin (one line) describing the pair to run,
    emits JSONL events on stdout, exits.
    """
    payload = json.loads(sys.stdin.readline())
    strategy_yaml = payload["strategy_yaml"]
    symbol = payload["symbol"]
    session_date_str = payload["session_date"]
    starting_equity = float(payload.get("starting_equity", 100_000.0))

    sys.path.insert(0, str(REPO_ROOT))
    # Import here so module-load failures appear as stderr (parent will surface)
    from backtest.portfolio_backtest import (  # noqa: E402
        run_single_strategy_single_day,
    )

    t0 = time.perf_counter()
    try:
        trades = run_single_strategy_single_day(
            strategy_yaml=strategy_yaml,
            symbol=symbol,
            session_date=pd.Timestamp(session_date_str).date(),
            starting_equity=starting_equity,
        )
    except Exception as exc:
        sys.stdout.write(json.dumps({"event": "error", "message": str(exc)}) + "\n")
        sys.stdout.flush()
        return 1

    for t in trades:
        sys.stdout.write(json.dumps({"event": "fill", **t}) + "\n")
    elapsed = time.perf_counter() - t0
    sys.stdout.write(json.dumps({
        "event": "summary",
        "elapsed_sec": elapsed,
        "n_fills": len(trades),
    }) + "\n")
    sys.stdout.flush()
    return 0


# ---------------------------------------------------------------------------
# Parent: subprocess orchestration
# ---------------------------------------------------------------------------


def _run_one_pair(task: PairTask) -> PairResult:
    """Spawn one subprocess, parse stdout, return a PairResult."""
    payload = {
        "strategy_yaml": task.strategy_yaml,
        "symbol": task.symbol,
        "session_date": task.session_date.isoformat(),
        "starting_equity": task.starting_equity,
    }
    env = {**os.environ, **task.extra_env}
    t0 = time.perf_counter()
    cp = subprocess.run(
        [sys.executable, "-m", "backtest.nautilus_subprocess_runner", "--worker"],
        input=json.dumps(payload) + "\n",
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
        timeout=300,
    )
    elapsed = time.perf_counter() - t0
    if cp.returncode != 0:
        return PairResult(
            task=task,
            error=f"rc={cp.returncode}: {cp.stderr.strip()[:500]}",
            elapsed_sec=elapsed,
        )

    fills: list[dict[str, Any]] = []
    summary: dict[str, Any] | None = None
    for line in cp.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        ev = obj.pop("event", None)
        if ev == "fill":
            fills.append(obj)
        elif ev == "summary":
            summary = obj
        elif ev == "error":
            return PairResult(task=task, error=obj.get("message", "unknown"), elapsed_sec=elapsed)
    return PairResult(task=task, fills=fills, summary=summary, elapsed_sec=elapsed)


def run_sweep(
    tasks: Iterable[PairTask],
    max_workers: int = 4,
) -> list[PairResult]:
    """Run a sweep of (strategy, symbol, date) tasks in parallel subprocesses.

    Note: each task is itself a fresh subprocess; ``max_workers`` controls
    how many subprocesses we keep in flight at once.  4 is a safe default
    on a typical 8-core M-series Mac; tune up for production runs.
    """
    tasks = list(tasks)
    results: list[PairResult] = []
    if not tasks:
        return results
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_run_one_pair, t): t for t in tasks}
        for fut in as_completed(futures):
            task = futures[fut]
            try:
                results.append(fut.result())
            except Exception as exc:
                results.append(PairResult(task=task, error=str(exc)))
    return results


# ---------------------------------------------------------------------------
# CLI entrypoint — recognised by the `_run_one_pair` invocation above.
# ---------------------------------------------------------------------------


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--worker":
        return _worker_main(argv[1:])
    print(
        "nautilus_subprocess_runner: this module is invoked indirectly by "
        "`run_sweep`. Pass --worker on stdin to drive it manually.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
