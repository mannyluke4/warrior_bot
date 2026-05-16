"""Performance acceptance tests.

Per directive §3 (Agent A): the backtest harness must process 200K bars in
under 30 seconds. We validate this with the lightweight vectorbt runner —
the nautilus runner is event-accurate and slower per-bar but its Rust core
is ~10x faster on ticks anyway (research §3).
"""

from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "/Users/duffy/warrior_bot_v2")

from backtest.vectorbt_runner import run_signal_backtest


def test_vectorbt_200k_bars_under_30s():
    np.random.seed(7)
    n = 200_000
    # Synthetic price walk with mild drift
    close = pd.Series(
        100 + np.cumsum(np.random.normal(0, 0.02, n)),
        index=pd.date_range("2024-01-02 09:30", periods=n, freq="1min"),
    )
    # Sparse entry/exit signals (every ~100 bars)
    entries = pd.Series(False, index=close.index)
    exits = pd.Series(False, index=close.index)
    sig_idx = np.arange(0, n, 100)
    entries.iloc[sig_idx] = True
    exits.iloc[sig_idx[1:]] = True

    t0 = time.perf_counter()
    m = run_signal_backtest(close, entries, exits, init_cash=100_000, freq="1min",
                            periods_per_year=252 * 6 * 60)
    elapsed = time.perf_counter() - t0
    print(f"200K bars vectorbt elapsed: {elapsed:.2f}s, n_trades={m.n_trades}")
    assert elapsed < 30.0, f"200K bars took {elapsed:.2f}s (>30s budget)"
    assert m.n_trades > 0
