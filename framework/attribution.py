"""Per-strategy attribution — trade log + aggregated stats.

Wave 1, Agent E, deliverable 3 (DIRECTIVE_2026-05-17_FRAMEWORK_BUILD.md §3).

Records each closed trade to a JSON-lines file at
    framework_state/trade_log_<YYYY-MM-DD>.jsonl

Computes per-trade:
  - signed P&L (qty * (exit - entry) for long; flipped for short)
  - R-multiple (relative to per-trade risk if provided, else None)
  - hold duration in seconds

Aggregates per strategy:
  - total trades, wins, win rate
  - gross P&L, avg R, profit factor
  - Sharpe (annualized, daily-bar approximation)
  - max drawdown (intra-day, equity-curve approximation)

The aggregated stats follow conventional formulas (e.g. Sharpe = mean/std *
sqrt(252)) so they match a manual scipy reference.
"""
from __future__ import annotations

import json
import math
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import pytz

ET = pytz.timezone("US/Eastern")

_DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent / "framework_state"
TRADING_DAYS_PER_YEAR = 252


@dataclass
class TradeRecord:
    """Normalized trade record for attribution."""

    strategy_name: str
    symbol: str
    entry_time: str  # ISO-8601 string
    exit_time: str
    entry_price: float
    exit_price: float
    qty: int
    side: str  # 'long' or 'short'
    exit_reason: str
    pnl: float
    r_multiple: Optional[float] = None
    hold_seconds: float = 0.0
    risk_per_share: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)


def _to_iso(t: Any) -> str:
    """Coerce a timestamp (datetime, str, epoch) to ISO-8601 string."""
    if t is None:
        return ""
    if isinstance(t, str):
        return t
    if isinstance(t, datetime):
        return t.isoformat()
    try:
        return datetime.fromtimestamp(float(t), tz=ET).isoformat()
    except (TypeError, ValueError, OSError):
        return str(t)


def _parse_iso(s: str) -> Optional[datetime]:
    """Parse an ISO-8601 string back to datetime. Tolerant of trailing Z."""
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def _today_str() -> str:
    return datetime.now(ET).strftime("%Y-%m-%d")


def _trade_log_path(date_str: str, base_dir: Optional[Path] = None) -> Path:
    base = base_dir if base_dir is not None else _DEFAULT_STATE_DIR
    return base / f"trade_log_{date_str}.jsonl"


def _compute_pnl(
    qty: int, entry_price: float, exit_price: float, side: str
) -> float:
    sign = 1.0 if side.lower() == "long" else -1.0
    return sign * qty * (exit_price - entry_price)


class StrategyAttribution:
    """Per-strategy P&L tracker with JSONL trade log."""

    def __init__(self, state_dir: Optional[Path | str] = None) -> None:
        self.state_dir = (
            Path(state_dir) if state_dir else _DEFAULT_STATE_DIR
        )
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Trade ingestion
    # ------------------------------------------------------------------ #
    def record_trade(
        self,
        strategy_name: str,
        symbol: str,
        entry_time: Any,
        exit_time: Any,
        entry_price: float,
        exit_price: float,
        qty: int,
        side: str,
        exit_reason: str,
        risk_per_share: Optional[float] = None,
    ) -> Optional[TradeRecord]:
        """Append a closed-trade record to the daily JSON-lines log.

        Returns the TradeRecord on success, or None if inputs were invalid.
        Never raises.
        """
        try:
            if not strategy_name or not symbol:
                return None
            qty_i = int(qty)
            if qty_i <= 0:
                return None
            entry_f = float(entry_price)
            exit_f = float(exit_price)
            if not (math.isfinite(entry_f) and math.isfinite(exit_f)):
                return None
            if side.lower() not in ("long", "short"):
                return None
        except (TypeError, ValueError):
            return None

        pnl = _compute_pnl(qty_i, entry_f, exit_f, side)
        r_multiple: Optional[float] = None
        if risk_per_share is not None:
            try:
                rps = float(risk_per_share)
                if math.isfinite(rps) and rps > 0:
                    r_multiple = (
                        (exit_f - entry_f)
                        * (1.0 if side.lower() == "long" else -1.0)
                        / rps
                    )
            except (TypeError, ValueError):
                r_multiple = None

        entry_iso = _to_iso(entry_time)
        exit_iso = _to_iso(exit_time)
        hold_s = 0.0
        e_dt = _parse_iso(entry_iso)
        x_dt = _parse_iso(exit_iso)
        if e_dt and x_dt:
            try:
                hold_s = max(0.0, (x_dt - e_dt).total_seconds())
            except (TypeError, ValueError):
                hold_s = 0.0

        rec = TradeRecord(
            strategy_name=strategy_name,
            symbol=symbol,
            entry_time=entry_iso,
            exit_time=exit_iso,
            entry_price=entry_f,
            exit_price=exit_f,
            qty=qty_i,
            side=side.lower(),
            exit_reason=exit_reason or "",
            pnl=pnl,
            r_multiple=r_multiple,
            hold_seconds=hold_s,
            risk_per_share=risk_per_share,
        )

        date_str = (
            e_dt.strftime("%Y-%m-%d") if e_dt else _today_str()
        )
        path = _trade_log_path(date_str, self.state_dir)
        with self._lock:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Append-line writes are atomic for small lines on POSIX.
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(rec.to_dict()) + "\n")
            except OSError as e:
                print(
                    f"[ATTRIB] append failed for {strategy_name}: {e!r}",
                    flush=True,
                )
                return rec
        return rec

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #
    def _read_trades(self, date: str) -> list[TradeRecord]:
        path = _trade_log_path(date, self.state_dir)
        if not path.exists():
            return []
        out: list[TradeRecord] = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        out.append(
                            TradeRecord(
                                strategy_name=d.get("strategy_name", ""),
                                symbol=d.get("symbol", ""),
                                entry_time=d.get("entry_time", ""),
                                exit_time=d.get("exit_time", ""),
                                entry_price=float(
                                    d.get("entry_price", 0.0)
                                ),
                                exit_price=float(
                                    d.get("exit_price", 0.0)
                                ),
                                qty=int(d.get("qty", 0)),
                                side=d.get("side", "long"),
                                exit_reason=d.get("exit_reason", ""),
                                pnl=float(d.get("pnl", 0.0)),
                                r_multiple=d.get("r_multiple"),
                                hold_seconds=float(
                                    d.get("hold_seconds", 0.0)
                                ),
                                risk_per_share=d.get("risk_per_share"),
                            )
                        )
                    except (json.JSONDecodeError, TypeError, ValueError):
                        continue
        except OSError:
            return []
        return out

    # ------------------------------------------------------------------ #
    # Aggregation
    # ------------------------------------------------------------------ #
    @staticmethod
    def _aggregate(trades: list[TradeRecord]) -> dict:
        n = len(trades)
        if n == 0:
            return {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "gross_pnl": 0.0,
                "avg_pnl": 0.0,
                "avg_r": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0,
                "profit_factor": 0.0,
                "total_hold_seconds": 0.0,
            }
        pnls = [t.pnl for t in trades]
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        gross_pnl = sum(pnls)
        avg_pnl = gross_pnl / n
        gross_wins = sum(p for p in pnls if p > 0)
        gross_losses = -sum(p for p in pnls if p < 0)
        profit_factor = (
            (gross_wins / gross_losses)
            if gross_losses > 0
            else (math.inf if gross_wins > 0 else 0.0)
        )

        r_vals = [
            t.r_multiple for t in trades if t.r_multiple is not None
        ]
        avg_r = (sum(r_vals) / len(r_vals)) if r_vals else 0.0

        # Sharpe: per-trade returns std + sqrt(N) annualization.
        # We treat each trade's P&L as a return sample and annualize by
        # sqrt(TRADING_DAYS_PER_YEAR). This matches the conventional
        # daily-Sharpe formula when trades are 1 per day; it overstates
        # for multi-trade days but is a reproducible reference number.
        if n >= 2:
            mean = avg_pnl
            var = sum((p - mean) ** 2 for p in pnls) / (n - 1)
            std = math.sqrt(var)
            sharpe = (
                (mean / std) * math.sqrt(TRADING_DAYS_PER_YEAR)
                if std > 0
                else 0.0
            )
        else:
            sharpe = 0.0

        # Max drawdown across trade-order equity curve.
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for p in pnls:
            equity += p
            if equity > peak:
                peak = equity
            dd = peak - equity
            if dd > max_dd:
                max_dd = dd

        total_hold = sum(t.hold_seconds for t in trades)
        return {
            "trades": n,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / n,
            "gross_pnl": gross_pnl,
            "avg_pnl": avg_pnl,
            "avg_r": avg_r,
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "profit_factor": profit_factor,
            "total_hold_seconds": total_hold,
        }

    def strategy_attribution_summary(
        self, date: Optional[str] = None
    ) -> dict:
        """Return per-strategy aggregate stats for `date`. Default: today."""
        d = date if date else _today_str()
        trades = self._read_trades(d)
        out: dict[str, dict] = {}
        by_strategy: dict[str, list[TradeRecord]] = {}
        for t in trades:
            by_strategy.setdefault(t.strategy_name, []).append(t)
        for name, recs in by_strategy.items():
            out[name] = self._aggregate(recs)
        # Portfolio-wide row
        out["__portfolio__"] = self._aggregate(trades)
        return out

    def list_strategies(self, date: Optional[str] = None) -> list[str]:
        d = date if date else _today_str()
        return sorted({t.strategy_name for t in self._read_trades(d)})


__all__ = ["StrategyAttribution", "TradeRecord"]
