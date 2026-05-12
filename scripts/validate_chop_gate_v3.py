#!/usr/bin/env python3
"""validate_chop_gate_v3.py — historical-replay validation of chop_gate_v3.

For each closed WB trade in May 2026, reconstruct the moment-of-arm state
(1m bars, MACD, prior-session history) and check whether chop_gate_v3
would have blocked it. Bucket outcomes:

  (blocked, was_winner)  → false-positive (bad)
  (blocked, was_loser)   → saved trade (good)
  (passed,  was_winner)  → preserved (good)
  (passed,  was_loser)   → not caught (acceptable in moderation)

Acceptance criteria (per DIRECTIVE_CHOP_GATE_V3_BUILD.md):
  1. blocked-losers / total-losers >= 60%
  2. passed-winners / total-winners >= 90%
  3. top-3 winners by P&L all preserved
  4. all 3 FATN losses (cited 5/6, 5/8, 5/12) blocked

Output: cowork_reports/2026-05-12_chop_gate_v3_validation.md

Data sources (per directive):
  - cowork_reports/daily_trades/*.md         (context only)
  - logs/2026-05-*_subbot_alpaca.log         (Setup A WB fills + exits)
  - ~/warrior_bot_v2_engine/logs/2026-05-12_wb_bot.log
                                              (Setup B WB fills + exits)
  - tick_cache_alpaca/<date>/<symbol>.json.gz
    (with tick_cache/<date>/ as fallback)
"""

from __future__ import annotations

import gzip
import json
import os
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field  # noqa: F401
from datetime import date as _date, datetime, time as _time, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

# Make the repo root importable so we can pull in chop_gate_v3 / session_history / macd.
_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Point SessionHistory at a per-run temp file so this script doesn't pollute
# live state. Must be set BEFORE importing chop_gate_v3.
_TMP_HISTORY = tempfile.NamedTemporaryFile(
    prefix="chop_gate_v3_validate_",
    suffix=".json",
    delete=False,
)
_TMP_HISTORY.close()
os.environ["WB_V3_SESSION_HISTORY_FILE"] = _TMP_HISTORY.name
# Pre-clear so the first SessionHistory instance starts empty.
Path(_TMP_HISTORY.name).write_text("{}")

from chop_gate_v3 import (  # noqa: E402
    chop_gate_v3,
    failed_hod_attempts,
    macd_rolling_over,
    has_volume_followthrough,
    sub_gate_macd,
    sub_gate_hod_recent,
    sub_gate_dead_bounce,
    sub_gate_vol_followthrough,
    sub_gate_xsession_bl,
    _set_session_history,
)
from session_history import SessionHistory  # noqa: E402
from macd import MACDState  # noqa: E402

# Sub-gate registry used for per-sub-gate validation passes.
# dead_bounce retired per DIRECTIVE_CHOP_GATE_V3_DEAD_BOUNCE_RETIRE.md (2026-05-12).
SUB_GATES = [
    ("macd",              sub_gate_macd),
    ("hod_recent",        sub_gate_hod_recent),
    ("vol_followthrough", sub_gate_vol_followthrough),
    ("xsession_bl",       sub_gate_xsession_bl),
]

ET = ZoneInfo("America/New_York")
UTC = timezone.utc


# ══════════════════════════════════════════════════════════════════════
# Data classes
# ══════════════════════════════════════════════════════════════════════


@dataclass
class _Bar:
    """Minimal Bar shape used during replay; matches the attribute names
    chop_gate_v3 reads (open/high/low/close/volume + start_utc)."""
    symbol: str
    start_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass
class Trade:
    date: str           # YYYY-MM-DD (ET)
    symbol: str
    entry_time_utc: datetime
    entry_price: float
    stop_price: float
    score: int
    qty: int
    fill_price: Optional[float] = None
    exit_price: Optional[float] = None
    exit_time_utc: Optional[datetime] = None
    pnl: Optional[float] = None
    r_multiple: Optional[float] = None
    source: str = ""      # log file basename
    setup: str = ""       # subbot or wb_bot
    passed_v2: bool = True  # any trade that fired had passed v2 (or score>=9 bypass)


# ══════════════════════════════════════════════════════════════════════
# Log parsing
# ══════════════════════════════════════════════════════════════════════

# Setup A subbot timestamps in the WB section are written without an
# ISO prefix (lines start "[WB] ..."), so we anchor on file dates instead
# and accept either "FILL @ $X.XX qty=N" or "ENTER qty=N entry=$..." for
# entry parameters.

_SUBBOT_ENTER_RE = re.compile(
    r"^\[WB\] (?P<sym>[A-Z][A-Z0-9.]+) ENTER qty=(?P<qty>\d+) "
    r"entry=\$(?P<entry>[\d.]+) stop=\$(?P<stop>[\d.]+) "
    r"risk=\$(?P<risk>[\d.]+) notional=\$[\d,]+ score=(?P<score>\d+)"
)
_SUBBOT_FILL_RE = re.compile(
    r"^\[WB\] (?P<sym>[A-Z][A-Z0-9.]+) FILL @ \$(?P<fill>[\d.]+) qty=(?P<qty>\d+)"
)
_SUBBOT_EXIT_RE = re.compile(
    r"^\[WB\] (?P<sym>[A-Z][A-Z0-9.]+) EXITED @ \$(?P<exit>[\d.]+) "
    r"pnl=\$(?P<pnl>[+\-,\d.]+) r_mult=(?P<r>[+\-\d.]+)"
)

# Subbot WB_ARMED line carries ET clock time, useful as entry-time anchor.
# Format: "[WB] [HH:MM ET] SYM WB_ARMED: score=N wave_id=W prov_entry=X stop=Y"
_SUBBOT_ARMED_RE = re.compile(
    r"^\[WB\] \[(?P<hh>\d{2}):(?P<mm>\d{2}) ET\] (?P<sym>[A-Z][A-Z0-9.]+) "
    r"WB_ARMED: score=(?P<score>\d+) wave_id=(?P<wid>\d+) "
    r"prov_entry=(?P<entry>[\d.]+) stop=(?P<stop>[\d.]+)"
)

# Engine wb_bot lines carry an explicit ISO timestamp.
_ENGINE_ENTRY_RE = re.compile(
    r"^\[WB\] (?P<ts>\S+) (?P<sym>[A-Z][A-Z0-9.]+) ENTRY qty=(?P<qty>\d+) "
    r"ibkr_signal=\$(?P<entry>[\d.]+) stop=\$(?P<stop>[\d.]+) "
    r"R=\$(?P<r>[\d.]+) risk=\$(?P<risk>[\d.]+) notional=\$[\d,]+ "
    r"score=(?P<score>\d+)"
)
_ENGINE_FILL_RE = re.compile(
    r"^\[WB\] (?P<ts>\S+) (?P<sym>[A-Z][A-Z0-9.]+) FILL @ "
    r"\$(?P<fill>[\d.]+) qty=(?P<qty>\d+)"
)
_ENGINE_CLOSE_RE = re.compile(
    r"^\[WB\] (?P<ts>\S+) (?P<sym>[A-Z][A-Z0-9.]+) CLOSED @ "
    r"\$(?P<exit>[\d.]+) pnl=\$(?P<pnl>[+\-,\d.]+) reason=\S+ "
    r"daily_pnl=\$[+\-,\d.]+"
)


def _date_from_log_filename(path: Path) -> str:
    """Extract 'YYYY-MM-DD' prefix from a log filename like
    '2026-05-08_subbot_alpaca.log' or '2026-05-12_wb_bot.log'."""
    m = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
    if not m:
        raise ValueError(f"Cannot extract date from {path.name}")
    return m.group(1)


def _et_time_to_utc(date_str: str, hh: int, mm: int) -> datetime:
    """Construct a UTC datetime from an ET date + clock time."""
    d = _date.fromisoformat(date_str)
    et_dt = datetime(d.year, d.month, d.day, hh, mm, 0, tzinfo=ET)
    return et_dt.astimezone(UTC)


def parse_subbot_log(path: Path) -> List[Trade]:
    """Walk one subbot log and emit Trade objects: ENTER → FILL → EXITED.

    The subbot doesn't print ISO timestamps on the WB lines, but the
    preceding WB_ARMED line carries the ET clock time. We use the most-
    recent WB_ARMED for that symbol as the entry-time anchor.
    """
    date_str = _date_from_log_filename(path)
    last_armed: Dict[str, datetime] = {}   # symbol → entry_time_utc
    last_armed_score: Dict[str, int] = {}
    pending_entry: Dict[str, dict] = {}     # symbol → parsed ENTER record
    filled: Dict[str, dict] = {}            # symbol → parsed FILL record + entry meta
    trades: List[Trade] = []

    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m_armed = _SUBBOT_ARMED_RE.match(line)
            if m_armed:
                sym = m_armed.group("sym")
                hh = int(m_armed.group("hh"))
                mm = int(m_armed.group("mm"))
                last_armed[sym] = _et_time_to_utc(date_str, hh, mm)
                last_armed_score[sym] = int(m_armed.group("score"))
                continue

            m_enter = _SUBBOT_ENTER_RE.match(line)
            if m_enter:
                sym = m_enter.group("sym")
                pending_entry[sym] = {
                    "entry": float(m_enter.group("entry")),
                    "stop": float(m_enter.group("stop")),
                    "qty": int(m_enter.group("qty")),
                    "score": int(m_enter.group("score")),
                    "entry_time_utc": last_armed.get(sym, _et_time_to_utc(date_str, 9, 30)),
                }
                continue

            m_fill = _SUBBOT_FILL_RE.match(line)
            if m_fill:
                sym = m_fill.group("sym")
                if sym not in pending_entry:
                    # Adopted-orphan FILL line w/o preceding ENTER — skip.
                    continue
                pe = pending_entry[sym]
                filled[sym] = {
                    **pe,
                    "fill_price": float(m_fill.group("fill")),
                }
                # Don't pop; the same symbol can have multiple intraday trades.
                # We pop on EXITED.
                continue

            m_exit = _SUBBOT_EXIT_RE.match(line)
            if m_exit:
                sym = m_exit.group("sym")
                if sym not in filled:
                    continue
                f_rec = filled.pop(sym)
                pnl_str = m_exit.group("pnl").replace(",", "")
                trades.append(Trade(
                    date=date_str,
                    symbol=sym,
                    entry_time_utc=f_rec["entry_time_utc"],
                    entry_price=f_rec["entry"],
                    stop_price=f_rec["stop"],
                    score=f_rec["score"],
                    qty=f_rec["qty"],
                    fill_price=f_rec["fill_price"],
                    exit_price=float(m_exit.group("exit")),
                    pnl=float(pnl_str),
                    r_multiple=float(m_exit.group("r")),
                    source=path.name,
                    setup="subbot",
                ))
                # Clear pending_entry so a subsequent ENTER on the same
                # symbol gets a fresh anchor.
                pending_entry.pop(sym, None)
                continue

    return trades


def parse_engine_log(path: Path) -> List[Trade]:
    """Walk one engine wb_bot log and emit Trade objects: ENTRY → FILL → CLOSED.

    Engine prints explicit ISO timestamps on every WB line, so the
    entry_time anchor is exact.
    """
    pending_entry: Dict[str, dict] = {}
    filled: Dict[str, dict] = {}
    trades: List[Trade] = []
    date_str = _date_from_log_filename(path)

    with open(path, errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m_e = _ENGINE_ENTRY_RE.match(line)
            if m_e:
                sym = m_e.group("sym")
                ts_str = m_e.group("ts")
                try:
                    ts_dt = datetime.fromisoformat(ts_str)
                    if ts_dt.tzinfo is None:
                        ts_dt = ts_dt.replace(tzinfo=UTC)
                    entry_time_utc = ts_dt.astimezone(UTC)
                except ValueError:
                    entry_time_utc = _et_time_to_utc(date_str, 9, 30)
                pending_entry[sym] = {
                    "entry": float(m_e.group("entry")),
                    "stop": float(m_e.group("stop")),
                    "qty": int(m_e.group("qty")),
                    "score": int(m_e.group("score")),
                    "entry_time_utc": entry_time_utc,
                }
                continue
            m_f = _ENGINE_FILL_RE.match(line)
            if m_f:
                sym = m_f.group("sym")
                if sym not in pending_entry:
                    continue
                pe = pending_entry[sym]
                filled[sym] = {
                    **pe,
                    "fill_price": float(m_f.group("fill")),
                }
                continue
            m_c = _ENGINE_CLOSE_RE.match(line)
            if m_c:
                sym = m_c.group("sym")
                if sym not in filled:
                    continue
                f_rec = filled.pop(sym)
                pnl_str = m_c.group("pnl").replace(",", "")
                exit_price = float(m_c.group("exit"))
                fill_p = f_rec["fill_price"]
                stop_p = f_rec["stop"]
                r_per_share = max(fill_p - stop_p, 1e-6)
                r_mult = (exit_price - fill_p) / r_per_share
                trades.append(Trade(
                    date=date_str,
                    symbol=sym,
                    entry_time_utc=f_rec["entry_time_utc"],
                    entry_price=f_rec["entry"],
                    stop_price=f_rec["stop"],
                    score=f_rec["score"],
                    qty=f_rec["qty"],
                    fill_price=fill_p,
                    exit_price=exit_price,
                    pnl=float(pnl_str),
                    r_multiple=r_mult,
                    source=path.name,
                    setup="wb_bot",
                ))
                pending_entry.pop(sym, None)
                continue

    return trades


# ══════════════════════════════════════════════════════════════════════
# Tick cache + bar reconstruction
# ══════════════════════════════════════════════════════════════════════


def _tick_cache_candidates(date_str: str, symbol: str) -> List[Path]:
    return [
        _ROOT / "tick_cache_alpaca" / date_str / f"{symbol}.json.gz",
        _ROOT / "tick_cache" / date_str / f"{symbol}.json.gz",
        _ROOT / "tick_cache_historical" / date_str / f"{symbol}.json.gz",
    ]


def load_ticks(date_str: str, symbol: str) -> List[Tuple[datetime, float, int]]:
    """Returns [(ts_utc, price, size)] sorted by timestamp. Empty list if
    no cache exists."""
    for p in _tick_cache_candidates(date_str, symbol):
        if not p.exists():
            continue
        try:
            with gzip.open(p, "rb") as f:
                raw = json.loads(f.read())
        except (OSError, json.JSONDecodeError):
            continue
        out: List[Tuple[datetime, float, int]] = []
        for rec in raw:
            try:
                ts_str = rec["t"]
                ts = datetime.fromisoformat(ts_str)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=UTC)
                else:
                    ts = ts.astimezone(UTC)
                out.append((ts, float(rec["p"]), int(rec.get("s", 0))))
            except (KeyError, ValueError, TypeError):
                continue
        out.sort(key=lambda r: r[0])
        return out
    return []


def build_bars_up_to(
    ticks: List[Tuple[datetime, float, int]],
    cutoff_utc: datetime,
    symbol: str,
) -> List[_Bar]:
    """Build closed 1-minute bars from ticks up to (but not including)
    cutoff_utc. Returns bars in chronological order."""
    if not ticks:
        return []
    bars_by_bucket: Dict[datetime, dict] = {}
    for ts, price, size in ticks:
        if ts >= cutoff_utc:
            break
        epoch = int(ts.timestamp())
        bucket = epoch - (epoch % 60)
        bucket_dt = datetime.fromtimestamp(bucket, tz=UTC)
        b = bars_by_bucket.get(bucket_dt)
        if b is None:
            bars_by_bucket[bucket_dt] = {
                "open": price, "high": price, "low": price,
                "close": price, "volume": size,
            }
        else:
            b["high"] = max(b["high"], price)
            b["low"] = min(b["low"], price)
            b["close"] = price
            b["volume"] += size
    # Sort and emit. Only include CLOSED buckets — every bucket here is
    # closed because we stopped reading ticks at cutoff_utc.
    out: List[_Bar] = []
    for bucket_dt in sorted(bars_by_bucket.keys()):
        b = bars_by_bucket[bucket_dt]
        out.append(_Bar(
            symbol=symbol,
            start_utc=bucket_dt,
            open=b["open"], high=b["high"],
            low=b["low"], close=b["close"],
            volume=int(b["volume"]),
        ))
    return out


def macd_from_bars(bars: List[_Bar]) -> MACDState:
    """Replay closes through a fresh MACDState. After the extension,
    MACDState records the rolling (line, signal, hist) history needed
    by macd_rolling_over."""
    macd = MACDState()
    for b in bars:
        macd.update(float(b.close))
    return macd


# ══════════════════════════════════════════════════════════════════════
# Replay
# ══════════════════════════════════════════════════════════════════════


@dataclass
class ReplayDecision:
    trade: Trade
    bars_count: int
    macd_ready: bool
    failed_hod: int
    macd_curl: bool
    no_followthrough: bool
    blacklisted: bool
    blacklist_reason: str
    passes: bool
    reason: str
    # Per-sub-gate verdicts captured during the same replay pass. Each
    # entry is (passes, reason) — passes=True means this sub-gate would
    # NOT veto the entry; passes=False means it WOULD veto.
    sub_gate_verdicts: Dict[str, Tuple[bool, str]] = field(default_factory=dict)


def replay_trades(trades: List[Trade]) -> List[ReplayDecision]:
    """Chronologically replay trades through chop_gate_v3.

    Each trade is evaluated TWICE:
      1) Through the composite orchestrator (`chop_gate_v3`), respecting
         the currently-active env flags.
      2) Through every sub-gate individually (regardless of env flags), so
         each sub-gate's would-veto / would-pass verdict is captured for
         downstream per-sub-gate reports.

    Cross-session blacklist is built incrementally: each trade's v3
    decision is computed BEFORE that trade's outcome is recorded into
    SessionHistory. This mirrors live behavior — the blacklist for
    today's entry reflects only trades that closed on PRIOR days.
    """
    # Fresh SessionHistory pointed at our temp file.
    Path(_TMP_HISTORY.name).write_text("{}")
    history = SessionHistory(history_file=_TMP_HISTORY.name)
    _set_session_history(history)

    decisions: List[ReplayDecision] = []
    sorted_trades = sorted(trades, key=lambda t: (t.entry_time_utc, t.source, t.symbol))

    for trade in sorted_trades:
        ticks = load_ticks(trade.date, trade.symbol)
        bars = build_bars_up_to(ticks, trade.entry_time_utc, trade.symbol)
        macd = macd_from_bars(bars)

        fhc = failed_hod_attempts(bars)
        curl = macd_rolling_over(macd) if macd.has_history(3) else False
        no_ft = not has_volume_followthrough(bars)
        is_black, black_reason = history.is_blacklisted(
            trade.symbol, trade.date,
        )

        # Composite orchestrator (env-aware).
        passes, reason = chop_gate_v3(
            trade.symbol, bars, macd, trade.date,
        )

        # Per-sub-gate verdicts (independent of env flags).
        sub_verdicts: Dict[str, Tuple[bool, str]] = {}
        for name, fn in SUB_GATES:
            try:
                sg_pass, sg_reason = fn(
                    trade.symbol, bars, macd, history, trade.date,
                )
            except Exception as e:
                sg_pass, sg_reason = True, f"error:{e!r}"
            sub_verdicts[name] = (sg_pass, sg_reason)

        decisions.append(ReplayDecision(
            trade=trade,
            bars_count=len(bars),
            macd_ready=macd.has_history(3),
            failed_hod=fhc,
            macd_curl=curl,
            no_followthrough=no_ft,
            blacklisted=is_black,
            blacklist_reason=black_reason,
            passes=passes,
            reason=reason,
            sub_gate_verdicts=sub_verdicts,
        ))

        if trade.pnl is not None and trade.r_multiple is not None:
            history.record_trade(
                symbol=trade.symbol,
                date=trade.date,
                pnl=float(trade.pnl),
                r_multiple=float(trade.r_multiple),
            )

    return decisions


# ══════════════════════════════════════════════════════════════════════
# Report
# ══════════════════════════════════════════════════════════════════════


def _format_money(x: Optional[float]) -> str:
    if x is None:
        return "n/a"
    return f"${x:+,.2f}"


def _bucket_counts(decisions: List[ReplayDecision]) -> Dict[str, int]:
    out = {
        "blocked_winner": 0, "blocked_loser": 0,
        "passed_winner": 0,  "passed_loser":  0,
    }
    for d in decisions:
        t = d.trade
        is_winner = (t.pnl or 0) > 0
        key_prefix = "passed_" if d.passes else "blocked_"
        key_suffix = "winner" if is_winner else "loser"
        out[key_prefix + key_suffix] += 1
    return out


def _check_criteria(decisions: List[ReplayDecision]) -> List[Tuple[str, bool, str]]:
    """Run the 4 acceptance criteria; return [(label, pass, detail)]."""
    buckets = _bucket_counts(decisions)
    total_losers = buckets["blocked_loser"] + buckets["passed_loser"]
    total_winners = buckets["blocked_winner"] + buckets["passed_winner"]

    # Criterion 1 — blocked-losers fraction
    if total_losers == 0:
        crit1 = (True, "no losers in dataset (vacuously true)")
    else:
        frac = buckets["blocked_loser"] / total_losers
        crit1 = (frac >= 0.60,
                 f"{buckets['blocked_loser']}/{total_losers} = {frac:.0%} "
                 f"(threshold 60%)")

    # Criterion 2 — passed-winners fraction
    if total_winners == 0:
        crit2 = (True, "no winners in dataset (vacuously true)")
    else:
        frac = buckets["passed_winner"] / total_winners
        crit2 = (frac >= 0.90,
                 f"{buckets['passed_winner']}/{total_winners} = {frac:.0%} "
                 f"(threshold 90%)")

    # Criterion 3 — top-3 winners by P&L all preserved
    winners = [d for d in decisions if (d.trade.pnl or 0) > 0]
    winners_sorted = sorted(
        winners, key=lambda d: (d.trade.pnl or 0), reverse=True,
    )
    top3 = winners_sorted[:3]
    if not top3:
        crit3 = (True, "no winners in dataset (vacuously true)")
    else:
        all_preserved = all(d.passes for d in top3)
        names = ", ".join(
            f"{d.trade.symbol} {d.trade.date} "
            f"{_format_money(d.trade.pnl)} ({'PASS' if d.passes else 'BLOCK'})"
            for d in top3
        )
        crit3 = (all_preserved, names)

    # Criterion 4 — all FATN losses (5/6, 5/8, 5/12) blocked. We accept
    # any FATN loss in the dataset whose date is in {2026-05-05, 06, 07,
    # 08, 11, 12} (the directive cites 5/6, 5/8, 5/12; live history shows
    # FATN also lost on adjacent days). The strict ask: every dated-FATN
    # LOSS in the dataset must be blocked. Wins are not penalized here.
    fatn_losses = [
        d for d in decisions
        if d.trade.symbol == "FATN" and (d.trade.pnl or 0) <= 0
    ]
    if not fatn_losses:
        crit4 = (False, "NO FATN losses found in dataset (cannot verify)")
    else:
        all_blocked = all(not d.passes for d in fatn_losses)
        details = ", ".join(
            f"{d.trade.date} {_format_money(d.trade.pnl)} "
            f"{'BLOCK ('+d.reason+')' if not d.passes else 'PASS'}"
            for d in fatn_losses
        )
        crit4 = (all_blocked, details)

    return [
        ("Criterion 1: blocked losers / total losers >= 60%",  crit1[0], crit1[1]),
        ("Criterion 2: passed winners / total winners >= 90%", crit2[0], crit2[1]),
        ("Criterion 3: top-3 winners by P&L all preserved",    crit3[0], crit3[1]),
        ("Criterion 4: all FATN losses blocked",               crit4[0], crit4[1]),
    ]


def write_report(
    decisions: List[ReplayDecision],
    out_path: Path,
) -> None:
    buckets = _bucket_counts(decisions)
    crits = _check_criteria(decisions)
    total = sum(buckets.values())

    lines: List[str] = []
    lines.append("# Chop Gate v3 — Historical Validation Report")
    lines.append("")
    lines.append(f"**Date generated:** {datetime.now(ET).isoformat(timespec='seconds')}")
    lines.append(f"**Source repo:** {_ROOT}")
    lines.append(f"**Sample size:** {total} closed WB trades")
    lines.append("")
    lines.append("## Bucket counts")
    lines.append("")
    lines.append("| Outcome | Count |")
    lines.append("|---|---:|")
    lines.append(f"| blocked, was loser (saved) | {buckets['blocked_loser']} |")
    lines.append(f"| blocked, was winner (false positive) | {buckets['blocked_winner']} |")
    lines.append(f"| passed, was winner (preserved) | {buckets['passed_winner']} |")
    lines.append(f"| passed, was loser (not caught) | {buckets['passed_loser']} |")
    lines.append("")
    lines.append("## Acceptance criteria")
    lines.append("")
    lines.append("| # | Criterion | Result | Detail |")
    lines.append("|---|---|---|---|")
    for i, (label, ok, detail) in enumerate(crits, start=1):
        verdict = "PASS" if ok else "FAIL"
        lines.append(f"| {i} | {label} | {verdict} | {detail} |")
    lines.append("")
    overall = all(ok for _, ok, _ in crits)
    lines.append(f"**Overall:** {'PASS' if overall else 'FAIL'}")
    lines.append("")
    lines.append("## Per-trade decisions (chronological)")
    lines.append("")
    lines.append(
        "| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | "
        "Bars | MACD-ready | failed_HOD | MACD-curl | no-followthrough | "
        "Blacklisted | v3 decision | Reason |"
    )
    lines.append("|" + "|".join(["---"] * 16) + "|")
    for d in sorted(decisions, key=lambda d: (d.trade.entry_time_utc, d.trade.source)):
        t = d.trade
        et_time = t.entry_time_utc.astimezone(ET).strftime("%H:%M")
        outcome = "WIN" if (t.pnl or 0) > 0 else ("LOSS" if (t.pnl or 0) < 0 else "FLAT")
        decision = "PASS" if d.passes else "BLOCK"
        lines.append(
            f"| {t.date} | {et_time} | {t.symbol} | {t.setup} | {t.score} | "
            f"{outcome} | {_format_money(t.pnl)} | {t.r_multiple:+.2f} | "
            f"{d.bars_count} | {'Y' if d.macd_ready else 'N'} | "
            f"{d.failed_hod} | {'Y' if d.macd_curl else 'N'} | "
            f"{'Y' if d.no_followthrough else 'N'} | "
            f"{'Y' if d.blacklisted else 'N'} | {decision} | {d.reason} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append(
        "- Cross-session blacklist is built CHRONOLOGICALLY: a trade's "
        "v3 decision sees only prior-day trades, never same-day or "
        "future-day outcomes."
    )
    lines.append(
        "- Tick cache: tries `tick_cache_alpaca/<date>/<sym>.json.gz` first "
        "(Setup A's isolated cache), then `tick_cache/<date>/` (main bot), "
        "then `tick_cache_historical/`. A `Bars` count of 0 means no cache "
        "was found for that symbol/date — v3 still runs but with no "
        "intraday signal (all three metrics return their no-warning default)."
    )
    lines.append(
        "- 'MACD-ready=N' means there weren't enough closed bars to build "
        "3 history points, so macd_rolling_over returns False by default. "
        "This is the same fail-OPEN behavior live bots will see early "
        "in the session before bar history accumulates."
    )
    lines.append(
        "- 'passed_v2' is implicit: every trade in this dataset got a "
        "broker fill, so v2 (or the score>=9 chop_bypass) must have let "
        "it through. v3 is therefore evaluated only against the v2-pass "
        "population — the population it would actually see in live."
    )
    out_path.write_text("\n".join(lines) + "\n")


# ══════════════════════════════════════════════════════════════════════
# Per-sub-gate validation
# ══════════════════════════════════════════════════════════════════════


def _macd_acceptance(
    decisions: List[ReplayDecision],
) -> List[Tuple[str, bool, str]]:
    """MACD-only acceptance criteria (per modular directive §2):
      1. Top-3 winners by P&L preserved — 100%
      2. All 4 winners in dataset preserved — 100%
      3. >= 2 losers blocked by MACD alone
      4. Zero false positives (no winner blocked)
    """
    winners = [d for d in decisions if (d.trade.pnl or 0) > 0]
    losers = [d for d in decisions if (d.trade.pnl or 0) <= 0]

    def macd_blocks(d: ReplayDecision) -> bool:
        v = d.sub_gate_verdicts.get("macd")
        return v is not None and not v[0]

    # Criterion 1
    winners_sorted = sorted(winners, key=lambda d: (d.trade.pnl or 0), reverse=True)
    top3 = winners_sorted[:3]
    top3_ok = all(not macd_blocks(d) for d in top3) if top3 else True
    top3_detail = ", ".join(
        f"{d.trade.symbol} {d.trade.date} {_format_money(d.trade.pnl)} "
        f"({'BLOCK' if macd_blocks(d) else 'PASS'})"
        for d in top3
    ) or "no winners in dataset"

    # Criterion 2
    all_win_ok = all(not macd_blocks(d) for d in winners)
    win_detail = (
        f"{sum(1 for d in winners if not macd_blocks(d))}/{len(winners)} preserved"
    )

    # Criterion 3
    macd_loser_blocks = sum(1 for d in losers if macd_blocks(d))
    crit3 = (macd_loser_blocks >= 2,
             f"{macd_loser_blocks} losers blocked by MACD (threshold >= 2)")

    # Criterion 4 — zero winners blocked
    fps = sum(1 for d in winners if macd_blocks(d))
    crit4 = (fps == 0, f"{fps} false positives (winners blocked)")

    return [
        ("Criterion 1: top-3 winners by P&L preserved (100%)", top3_ok, top3_detail),
        ("Criterion 2: all winners preserved (100%)",         all_win_ok, win_detail),
        ("Criterion 3: >= 2 losers blocked by MACD alone",    crit3[0], crit3[1]),
        ("Criterion 4: zero false positives",                  crit4[0], crit4[1]),
    ]


def _generic_sub_gate_acceptance(
    decisions: List[ReplayDecision],
    sub_name: str,
) -> List[Tuple[str, bool, str]]:
    """Advisory acceptance summary for non-MACD sub-gates.

    Mirrors the modular directive's expected-outcomes wording. These are
    NOT blocking gates (Phase 5 of the build directive — user reviews
    the report before flipping the env flag).
    """
    winners = [d for d in decisions if (d.trade.pnl or 0) > 0]
    losers = [d for d in decisions if (d.trade.pnl or 0) <= 0]

    def blocks(d: ReplayDecision) -> bool:
        v = d.sub_gate_verdicts.get(sub_name)
        return v is not None and not v[0]

    losers_blocked = sum(1 for d in losers if blocks(d))
    winners_blocked = sum(1 for d in winners if blocks(d))
    winners_passed = len(winners) - winners_blocked

    # Top-3 preservation is the same hard discipline.
    winners_sorted = sorted(winners, key=lambda d: (d.trade.pnl or 0), reverse=True)
    top3 = winners_sorted[:3]
    top3_ok = all(not blocks(d) for d in top3) if top3 else True
    top3_detail = ", ".join(
        f"{d.trade.symbol} {d.trade.date} {_format_money(d.trade.pnl)} "
        f"({'BLOCK' if blocks(d) else 'PASS'})"
        for d in top3
    ) or "no winners in dataset"

    crit_losers = (
        losers_blocked >= 1,
        f"{losers_blocked}/{len(losers)} losers blocked",
    )
    crit_winners = (
        winners_blocked == 0,
        f"{winners_passed}/{len(winners)} winners preserved",
    )

    return [
        ("Advisory 1: zero winners blocked", crit_winners[0], crit_winners[1]),
        ("Advisory 2: at least 1 loser blocked", crit_losers[0], crit_losers[1]),
        ("Advisory 3: top-3 winners preserved", top3_ok, top3_detail),
    ]


def _write_sub_gate_report(
    decisions: List[ReplayDecision],
    sub_name: str,
    out_path: Path,
    extra_notes: List[str],
) -> Tuple[List[Tuple[str, bool, str]], Dict[str, int]]:
    """Render a per-sub-gate validation report. Returns the acceptance
    rows (so the caller can decide whether to block on MACD failures)
    plus a summary counts dict."""
    if sub_name == "macd":
        crits = _macd_acceptance(decisions)
    else:
        crits = _generic_sub_gate_acceptance(decisions, sub_name)

    def blocks(d: ReplayDecision) -> bool:
        v = d.sub_gate_verdicts.get(sub_name)
        return v is not None and not v[0]

    counts = {
        "blocked_winner": sum(1 for d in decisions if blocks(d) and (d.trade.pnl or 0) > 0),
        "blocked_loser":  sum(1 for d in decisions if blocks(d) and (d.trade.pnl or 0) <= 0),
        "passed_winner":  sum(1 for d in decisions if not blocks(d) and (d.trade.pnl or 0) > 0),
        "passed_loser":   sum(1 for d in decisions if not blocks(d) and (d.trade.pnl or 0) <= 0),
    }

    lines: List[str] = []
    lines.append(f"# Chop Gate v3 — `{sub_name}` Sub-Gate Validation Report")
    lines.append("")
    lines.append(f"**Date generated:** {datetime.now(ET).isoformat(timespec='seconds')}")
    lines.append(f"**Source repo:** {_ROOT}")
    lines.append(f"**Sub-gate under test:** `{sub_name}` (others = observe-only)")
    lines.append(f"**Sample size:** {len(decisions)} closed WB trades")
    lines.append("")
    lines.append("## Counts (this sub-gate alone)")
    lines.append("")
    lines.append("| Outcome | Count |")
    lines.append("|---|---:|")
    lines.append(f"| blocked, was loser (saved) | {counts['blocked_loser']} |")
    lines.append(f"| blocked, was winner (false positive) | {counts['blocked_winner']} |")
    lines.append(f"| passed, was winner (preserved) | {counts['passed_winner']} |")
    lines.append(f"| passed, was loser (not caught) | {counts['passed_loser']} |")
    lines.append("")
    lines.append("## Acceptance criteria")
    lines.append("")
    lines.append("| # | Criterion | Result | Detail |")
    lines.append("|---|---|---|---|")
    for i, (label, ok, detail) in enumerate(crits, start=1):
        verdict = "PASS" if ok else "FAIL"
        lines.append(f"| {i} | {label} | {verdict} | {detail} |")
    lines.append("")
    overall = all(ok for _, ok, _ in crits)
    lines.append(f"**Overall:** {'PASS' if overall else 'FAIL'}")
    lines.append("")
    lines.append("## Per-trade decisions (chronological)")
    lines.append("")
    lines.append(
        "| Date | Time ET | Sym | Setup | Score | Outcome | P&L | R | Bars | "
        f"`{sub_name}` verdict | Reason |"
    )
    lines.append("|" + "|".join(["---"] * 11) + "|")
    for d in sorted(decisions, key=lambda d: (d.trade.entry_time_utc, d.trade.source)):
        t = d.trade
        et_time = t.entry_time_utc.astimezone(ET).strftime("%H:%M")
        outcome = "WIN" if (t.pnl or 0) > 0 else ("LOSS" if (t.pnl or 0) < 0 else "FLAT")
        sg = d.sub_gate_verdicts.get(sub_name, (True, "no_verdict"))
        verdict = "PASS" if sg[0] else "BLOCK"
        lines.append(
            f"| {t.date} | {et_time} | {t.symbol} | {t.setup} | {t.score} | "
            f"{outcome} | {_format_money(t.pnl)} | {t.r_multiple:+.2f} | "
            f"{d.bars_count} | {verdict} | {sg[1]} |"
        )
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    for n in extra_notes:
        lines.append(f"- {n}")
    out_path.write_text("\n".join(lines) + "\n")
    return crits, counts


# ══════════════════════════════════════════════════════════════════════
# Entrypoint
# ══════════════════════════════════════════════════════════════════════


def collect_trades() -> List[Trade]:
    trades: List[Trade] = []
    # Setup A subbot logs.
    subbot_log_dir = _ROOT / "logs"
    if subbot_log_dir.is_dir():
        for p in sorted(subbot_log_dir.glob("2026-05-*_subbot_alpaca.log")):
            try:
                trades.extend(parse_subbot_log(p))
            except Exception as e:
                print(f"WARN: failed to parse {p}: {e!r}", file=sys.stderr)

    # Engine wb_bot logs — sibling worktree.
    engine_log_dir = Path("/Users/duffy/warrior_bot_v2_engine/logs")
    if engine_log_dir.is_dir():
        for p in sorted(engine_log_dir.glob("2026-05-*_wb_bot.log")):
            try:
                trades.extend(parse_engine_log(p))
            except Exception as e:
                print(f"WARN: failed to parse {p}: {e!r}", file=sys.stderr)

    return trades


def main() -> int:
    trades = collect_trades()
    print(f"Collected {len(trades)} closed WB trades from logs", flush=True)
    if not trades:
        print("ERROR: no trades found — aborting validation", file=sys.stderr)
        return 1
    decisions = replay_trades(trades)
    out_dir = _ROOT / "cowork_reports"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Composite (legacy/orchestrator) report ─────────────────────────
    composite_path = out_dir / "2026-05-12_chop_gate_v3_validation.md"
    write_report(decisions, composite_path)
    print(f"Wrote {composite_path}", flush=True)

    # ── Per-sub-gate reports (Phase 3 of modular rollout) ──────────────
    # dead_bounce retired per DIRECTIVE_CHOP_GATE_V3_DEAD_BOUNCE_RETIRE.md.
    report_paths = {
        "macd":              out_dir / "2026-05-13_chop_gate_v3_macd_only_validation.md",
        "hod_recent":        out_dir / "2026-05-13_chop_gate_v3_hod_recent_validation.md",
        "xsession_bl":       out_dir / "2026-05-13_chop_gate_v3_xsession_validation.md",
    }
    notes_common = [
        "Per-sub-gate validation runs each sub-gate INDEPENDENTLY (other sub-gates "
        "in observe-only). Bars + MACD reconstructed from tick cache up to the "
        "exact moment of arm (no future leakage).",
        "Cross-session blacklist is built incrementally — each trade's decision "
        "sees only prior-day trades closed in the dataset.",
    ]

    macd_crits, macd_counts = _write_sub_gate_report(
        decisions, "macd", report_paths["macd"],
        extra_notes=notes_common + [
            "MACD-only is the gate going LIVE Wednesday 5/13 (default ON). "
            "Failing criterion 1, 2, or 4 = DO NOT ship.",
        ],
    )
    hod_crits, hod_counts = _write_sub_gate_report(
        decisions, "hod_recent", report_paths["hod_recent"],
        extra_notes=notes_common + [
            "Advisory only — user reviews report before flipping "
            "WB_CG3_HOD_RECENT_ENABLED=1. Expected: FATN 5/12 entries blocked, "
            "FATN 5/5 14:39 winner passed.",
        ],
    )
    # dead_bounce retired per DIRECTIVE_CHOP_GATE_V3_DEAD_BOUNCE_RETIRE.md.
    xb_crits, xb_counts = _write_sub_gate_report(
        decisions, "xsession_bl", report_paths["xsession_bl"],
        extra_notes=notes_common + [
            "Advisory only — flipping WB_CG3_XSESSION_BL_ENABLED=1 is Monday 5/18. "
            "Expected: FATN blacklisted by 5/12, ATRA never blacklisted, CLNN "
            "not blacklisted by THIS gate (CLNN handled by MACD same-day).",
        ],
    )

    for p in report_paths.values():
        print(f"Wrote {p}", flush=True)

    # ── CI summary ─────────────────────────────────────────────────────
    crits = _check_criteria(decisions)
    print("\nLegacy composite acceptance summary:")
    for label, ok, detail in crits:
        verdict = "PASS" if ok else "FAIL"
        print(f"  [{verdict}] {label} — {detail}")

    print("\nMACD-only acceptance summary (DIRECTIVE §2 — BLOCKING):")
    for label, ok, detail in macd_crits:
        verdict = "PASS" if ok else "FAIL"
        print(f"  [{verdict}] {label} — {detail}")

    print("\nhod_recent advisory summary:")
    for label, ok, detail in hod_crits:
        print(f"  [{'PASS' if ok else 'INFO'}] {label} — {detail}")
    print("\nxsession_bl advisory summary:")
    for label, ok, detail in xb_crits:
        print(f"  [{'PASS' if ok else 'INFO'}] {label} — {detail}")

    # MACD criteria 1, 2, 4 are BLOCKING. Criterion 3 (>= 2 losers blocked)
    # is informational: if it passes weakly (exactly 2), the rollout
    # directive says to push but note in commit message. The caller
    # (CI / commit pipeline) should read the exit code:
    #     0 → all blocking MACD criteria pass
    #     2 → at least one blocking MACD criterion failed → DO NOT PUSH
    macd_labels = [label for label, _, _ in macd_crits]
    macd_pass = [ok for _, ok, _ in macd_crits]
    blocking_idx = [
        i for i, lbl in enumerate(macd_labels)
        if "Criterion 1" in lbl or "Criterion 2" in lbl or "Criterion 4" in lbl
    ]
    macd_blocking_ok = all(macd_pass[i] for i in blocking_idx)
    print(f"\nMACD blocking-criteria result: "
          f"{'PASS' if macd_blocking_ok else 'FAIL'}")
    return 0 if macd_blocking_ok else 2


if __name__ == "__main__":
    sys.exit(main())
