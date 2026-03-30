#!/usr/bin/env python3
"""
Wave Analysis for Runner Stocks.

Loads tick data from tick_cache, builds 1-min bars, runs the squeeze sim
to find SQ entry/exit points, then detects price waves (alternating up/down
swings) after the first sq_target_hit. Computes per-wave metrics and saves
JSON + human-readable MD reports.

Usage:
    python analyze_runner_waves.py STOCK DATE --tick-cache tick_cache/
"""

import argparse
import gzip
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone


# ─── Helpers ────────────────────────────────────────────────────────────────

def time_str_to_min(ts: str) -> int:
    """HH:MM -> minutes since midnight."""
    parts = ts.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def min_to_time_str(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


# ─── Load tick data ────────────────────────────────────────────────────────

def load_ticks(symbol: str, date_str: str, tick_cache: str):
    """Load raw ticks from tick_cache/DATE/SYMBOL.json.gz."""
    path = os.path.join(tick_cache, date_str, f"{symbol}.json.gz")
    if not os.path.exists(path):
        print(f"ERROR: No tick cache file at {path}")
        sys.exit(1)
    with gzip.open(path, "rt") as f:
        raw = json.load(f)
    ticks = []
    for t in raw:
        ts = datetime.fromisoformat(t["t"])
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ticks.append({"price": t["p"], "size": t["s"], "ts": ts})
    return ticks


# ─── Build 1-min bars from ticks ───────────────────────────────────────────

def build_1m_bars(ticks, tz_offset_hours=-5):
    """Build 1-minute OHLCV bars from tick data. Returns list of dicts."""
    from zoneinfo import ZoneInfo
    et = ZoneInfo("America/New_York")

    bars_by_minute = defaultdict(list)
    for t in ticks:
        ts_et = t["ts"].astimezone(et)
        minute = ts_et.hour * 60 + ts_et.minute
        bars_by_minute[minute].append(t)

    bars = []
    for minute in sorted(bars_by_minute.keys()):
        tick_list = bars_by_minute[minute]
        prices = [t["price"] for t in tick_list]
        volumes = [t["size"] for t in tick_list]
        bars.append({
            "minute": minute,
            "time_str": min_to_time_str(minute),
            "o": prices[0],
            "h": max(prices),
            "l": min(prices),
            "c": prices[-1],
            "v": sum(volumes),
            "tick_count": len(tick_list),
        })
    return bars


# ─── Compute running VWAP ──────────────────────────────────────────────────

def compute_vwap_series(bars):
    """Compute cumulative VWAP at each bar close. Returns dict: minute -> vwap."""
    cum_pv = 0.0
    cum_vol = 0
    vwap_map = {}
    for b in bars:
        typical = (b["h"] + b["l"] + b["c"]) / 3.0
        cum_pv += typical * b["v"]
        cum_vol += b["v"]
        vwap_map[b["minute"]] = cum_pv / cum_vol if cum_vol > 0 else b["c"]
    return vwap_map


# ─── Compute EMA ────────────────────────────────────────────────────────────

def compute_ema_series(bars, period=9):
    """Compute EMA on close prices. Returns dict: minute -> ema."""
    ema_map = {}
    k = 2.0 / (period + 1)
    ema = None
    for b in bars:
        if ema is None:
            ema = b["c"]
        else:
            ema = b["c"] * k + ema * (1 - k)
        ema_map[b["minute"]] = ema
    return ema_map


# ─── Run SQ sim to find entry/exit points ──────────────────────────────────

def run_sim_for_exits(symbol: str, date_str: str, tick_cache: str):
    """Run simulate.py and parse output for SQ entry/exit info."""
    cmd = [
        sys.executable, "simulate.py", symbol, date_str,
        "07:00", "12:00", "--ticks", "--tick-cache", tick_cache, "--verbose", "--no-fundamentals",
    ]
    env = os.environ.copy()
    # Ensure squeeze is enabled and default config (no runner mode)
    env["WB_SQUEEZE_ENABLED"] = "1"
    env["WB_MP_ENABLED"] = "0"
    env["WB_CT_ENABLED"] = "0"
    env["WB_MP_V2_ENABLED"] = "0"
    env["WB_BAIL_TIMER_ENABLED"] = "1"
    env["WB_BAIL_TIMER_MINUTES"] = "5"
    env["WB_EXHAUSTION_ENABLED"] = "1"
    env["WB_WARMUP_BARS"] = "5"
    env.pop("WB_SQ_RUNNER_TRAIL_MODE", None)
    env.pop("WB_SQ_PARTIAL_EXIT_ENABLED", None)

    result = subprocess.run(cmd, capture_output=True, text=True, env=env,
                            cwd=os.path.dirname(os.path.abspath(__file__)))

    output = result.stdout + result.stderr

    # Debug: check if sim produced output
    sq_lines = [l for l in output.split("\n") if "SQ_ENTRY" in l]
    pnl_lines = [l for l in output.split("\n") if "Gross P&L" in l]
    if not sq_lines:
        print(f"  DEBUG: returncode={result.returncode}, stdout_len={len(result.stdout)}, stderr_len={len(result.stderr)}")
        if result.stderr:
            print(f"  DEBUG stderr (last 300): {result.stderr[-300:]}")

    # Parse the trade summary table (same format as run_backtest_v2.py)
    import re
    TRADE_PAT = re.compile(
        r'^\s*(\d+)\s+(\d{2}:\d{2})\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+'
        r'([\d.]+)\s+([\d.]+)\s+(\S+)\s+([+-]?\d+)\s+([+-]?[\d.]+R)',
        re.MULTILINE
    )

    trades = []
    for m in TRADE_PAT.finditer(output):
        trades.append({
            "entry_time": m.group(2),
            "entry_price": float(m.group(3)),
            "stop": float(m.group(4)),
            "r": float(m.group(5)),
            "score": float(m.group(6)),
            "exit_price": float(m.group(7)),
            "exit_reason": m.group(8),
            "pnl": int(float(m.group(9))),
            "r_mult": m.group(10),
        })

    return trades


# ─── Swing detection ───────────────────────────────────────────────────────

def detect_swings(bars):
    """
    Detect swing highs and lows on 1-min bars.
    Swing high: bar.high > prior.high AND bar.high > next.high
    Swing low:  bar.low  < prior.low  AND bar.low  < next.low
    Returns list of {'type': 'high'|'low', 'price': float, 'minute': int, 'bar_idx': int}
    """
    swings = []
    for i in range(1, len(bars) - 1):
        b = bars[i]
        prev = bars[i - 1]
        nxt = bars[i + 1]
        if b["h"] > prev["h"] and b["h"] > nxt["h"]:
            swings.append({"type": "high", "price": b["h"], "minute": b["minute"], "bar_idx": i})
        if b["l"] < prev["l"] and b["l"] < nxt["l"]:
            swings.append({"type": "low", "price": b["l"], "minute": b["minute"], "bar_idx": i})
    # Sort by minute (bar index)
    swings.sort(key=lambda s: s["minute"])
    return swings


def build_alternating_swings(swings):
    """Filter swings to alternate high/low. When consecutive same type, keep the extreme."""
    if not swings:
        return []
    result = [swings[0]]
    for s in swings[1:]:
        if s["type"] == result[-1]["type"]:
            # Same type — keep the more extreme one
            if s["type"] == "high" and s["price"] > result[-1]["price"]:
                result[-1] = s
            elif s["type"] == "low" and s["price"] < result[-1]["price"]:
                result[-1] = s
        else:
            result.append(s)
    return result


# ─── Wave building ──────────────────────────────────────────────────────────

def build_waves(bars, swings, start_minute, start_price, vwap_map, ema_map):
    """
    Build alternating up/down waves from swing points.
    Start from the given start_minute and start_price (SQ exit point).
    """
    # Filter swings to those after start_minute
    future_swings = [s for s in swings if s["minute"] > start_minute]
    if not future_swings:
        return []

    waves = []
    current_price = start_price
    current_minute = start_minute
    session_high = start_price
    wave_num = 0

    for swing in future_swings:
        wave_num += 1
        end_price = swing["price"]
        end_minute = swing["minute"]

        if swing["type"] == "high":
            wave_type = "up"
        else:
            wave_type = "down"

        duration = end_minute - current_minute

        # Compute move %
        if current_price > 0:
            move_pct = ((end_price - current_price) / current_price) * 100
        else:
            move_pct = 0

        # Get bars in this wave's time range
        wave_bars = [b for b in bars if current_minute <= b["minute"] <= end_minute]
        total_vol = sum(b["v"] for b in wave_bars)
        total_ticks = sum(b.get("tick_count", 0) for b in wave_bars)
        avg_vol_per_min = total_vol / max(duration, 1)

        # New HOD
        new_hod = False
        if wave_type == "up" and end_price > session_high:
            new_hod = True
            session_high = end_price

        # VWAP position at end of wave
        vwap_at_end = vwap_map.get(end_minute, 0)
        held_above_vwap = end_price > vwap_at_end if vwap_at_end > 0 else None

        # EMA position at end of wave
        ema_at_end = ema_map.get(end_minute, 0)
        held_above_ema = end_price > ema_at_end if ema_at_end > 0 else None

        # Retrace % (only for down waves — how much of prior up wave was retraced)
        retrace_pct = None
        if wave_type == "down" and waves:
            # Find the most recent up wave
            prior_up = None
            for w in reversed(waves):
                if w["type"] == "up":
                    prior_up = w
                    break
            if prior_up:
                up_move = prior_up["end_price"] - prior_up["start_price"]
                down_move = current_price - end_price  # how much we dropped
                if up_move > 0:
                    retrace_pct = (down_move / up_move) * 100

        # Volume ratio vs prior wave
        volume_ratio = None
        if waves and waves[-1].get("avg_volume_per_min", 0) > 0:
            volume_ratio = avg_vol_per_min / waves[-1]["avg_volume_per_min"]

        # Whole dollar interaction
        whole_dollars = []
        low_price = min(current_price, end_price)
        high_price = max(current_price, end_price)
        for d in range(int(math.floor(low_price)), int(math.ceil(high_price)) + 1):
            if low_price <= d <= high_price and d > 0:
                whole_dollars.append(d)

        wave = {
            "wave": wave_num,
            "type": wave_type,
            "start_price": round(current_price, 4),
            "end_price": round(end_price, 4),
            "start_time": min_to_time_str(current_minute),
            "end_time": min_to_time_str(end_minute),
            "duration_min": duration,
            "move_pct": round(move_pct, 2),
            "avg_volume_per_min": round(avg_vol_per_min),
            "tick_count": total_ticks,
            "total_volume": total_vol,
            "new_hod": new_hod,
            "held_above_vwap": held_above_vwap,
            "held_above_ema9": held_above_ema,
            "retrace_pct": round(retrace_pct, 1) if retrace_pct is not None else None,
            "volume_ratio_vs_prior": round(volume_ratio, 2) if volume_ratio is not None else None,
            "whole_dollar_levels": whole_dollars,
            "vwap_at_end": round(vwap_at_end, 4) if vwap_at_end else None,
            "ema9_at_end": round(ema_at_end, 4) if ema_at_end else None,
        }
        waves.append(wave)

        current_price = end_price
        current_minute = end_minute

    return waves


# ─── Summary stats ──────────────────────────────────────────────────────────

def compute_summary(waves, sq_exit_price, bars):
    """Compute summary stats across all waves."""
    up_waves = [w for w in waves if w["type"] == "up"]
    down_waves = [w for w in waves if w["type"] == "down"]

    # Find HOD from bars
    hod = max(b["h"] for b in bars) if bars else 0
    hod_bar = max(bars, key=lambda b: b["h"]) if bars else None
    hod_time = hod_bar["time_str"] if hod_bar else ""

    continuation_pct = ((hod - sq_exit_price) / sq_exit_price * 100) if sq_exit_price > 0 else 0

    summary = {
        "total_up_waves": len(up_waves),
        "total_down_waves": len(down_waves),
        "avg_up_wave_pct": round(sum(w["move_pct"] for w in up_waves) / len(up_waves), 2) if up_waves else 0,
        "avg_down_wave_retrace_pct": round(
            sum(w["retrace_pct"] for w in down_waves if w["retrace_pct"] is not None)
            / max(sum(1 for w in down_waves if w["retrace_pct"] is not None), 1), 1),
        "avg_dip_duration_min": round(
            sum(w["duration_min"] for w in down_waves) / len(down_waves), 1) if down_waves else 0,
        "avg_dip_volume_vs_rally": round(
            sum(w["volume_ratio_vs_prior"] for w in down_waves if w["volume_ratio_vs_prior"] is not None)
            / max(sum(1 for w in down_waves if w["volume_ratio_vs_prior"] is not None), 1), 2),
        "hod": round(hod, 4),
        "hod_time": hod_time,
        "continuation_range_pct": round(continuation_pct, 1),
    }

    # Final wave analysis (the reversal)
    if waves:
        final = waves[-1]
        summary["final_wave_type"] = final["type"]
        summary["final_wave_retrace_pct"] = final.get("retrace_pct")
        summary["final_wave_volume_vs_rally"] = final.get("volume_ratio_vs_prior")

    return summary


# ─── Generate MD report ────────────────────────────────────────────────────

def generate_md(data: dict) -> str:
    """Generate human-readable markdown from the analysis data."""
    lines = []
    lines.append(f"# Wave Analysis: {data['stock']} {data['date']}")
    lines.append("")
    lines.append(f"**SQ Exit:** ${data['sq_exit_price']:.2f} at {data['sq_exit_time']} ({data.get('sq_exit_reason', 'sq_target_hit')})")
    lines.append(f"**HOD:** ${data['hod']:.2f} at {data['hod_time']}")
    lines.append(f"**Continuation Range:** {data['continuation_range_pct']:.1f}%")
    lines.append(f"**SQ Entry:** ${data.get('sq_entry_price', 0):.2f} at {data.get('sq_entry_time', '?')}")
    lines.append("")

    # Summary
    s = data.get("summary", {})
    lines.append("## Summary")
    lines.append(f"- Up waves: {s.get('total_up_waves', 0)}")
    lines.append(f"- Down waves: {s.get('total_down_waves', 0)}")
    lines.append(f"- Avg up wave: {s.get('avg_up_wave_pct', 0):.1f}%")
    lines.append(f"- Avg dip retrace: {s.get('avg_down_wave_retrace_pct', 0):.1f}%")
    lines.append(f"- Avg dip duration: {s.get('avg_dip_duration_min', 0):.1f} min")
    lines.append(f"- Avg dip vol ratio: {s.get('avg_dip_volume_vs_rally', 0):.2f}x")
    final_type = s.get("final_wave_type", "?")
    final_retrace = s.get("final_wave_retrace_pct")
    final_vol = s.get("final_wave_volume_vs_rally")
    lines.append(f"- Final wave: {final_type} (retrace={final_retrace}%, vol_ratio={final_vol})")
    lines.append("")

    # Wave table
    lines.append("## Waves")
    lines.append("")
    lines.append("| # | Type | Start | End | Price | Move% | Duration | Retrace% | VolRatio | VWAP | EMA9 | HOD |")
    lines.append("|---|------|-------|-----|-------|-------|----------|----------|----------|------|------|-----|")
    for w in data.get("waves", []):
        vwap_str = "above" if w.get("held_above_vwap") else ("below" if w.get("held_above_vwap") is False else "?")
        ema_str = "above" if w.get("held_above_ema9") else ("below" if w.get("held_above_ema9") is False else "?")
        hod_str = "NEW" if w.get("new_hod") else ""
        retrace = f"{w['retrace_pct']:.0f}%" if w.get("retrace_pct") is not None else "-"
        vol_r = f"{w['volume_ratio_vs_prior']:.2f}" if w.get("volume_ratio_vs_prior") is not None else "-"
        lines.append(
            f"| {w['wave']} | {w['type'].upper()} | {w['start_time']} ${w['start_price']:.2f} "
            f"| {w['end_time']} ${w['end_price']:.2f} | ${w['start_price']:.2f}-${w['end_price']:.2f} "
            f"| {w['move_pct']:+.1f}% | {w['duration_min']}m | {retrace} | {vol_r} "
            f"| {vwap_str} | {ema_str} | {hod_str} |"
        )
    lines.append("")

    # Detailed wave descriptions
    lines.append("## Wave Details")
    lines.append("")
    for w in data.get("waves", []):
        emoji = "UP" if w["type"] == "up" else "DOWN"
        lines.append(f"### Wave {w['wave']}: {emoji}")
        lines.append(f"- Time: {w['start_time']} -> {w['end_time']} ({w['duration_min']} min)")
        lines.append(f"- Price: ${w['start_price']:.2f} -> ${w['end_price']:.2f} ({w['move_pct']:+.1f}%)")
        lines.append(f"- Volume: {w['avg_volume_per_min']:,}/min, {w['total_volume']:,} total, {w['tick_count']} ticks")
        if w.get("retrace_pct") is not None:
            lines.append(f"- Retrace: {w['retrace_pct']:.1f}% of prior up wave")
        if w.get("volume_ratio_vs_prior") is not None:
            lines.append(f"- Vol ratio vs prior: {w['volume_ratio_vs_prior']:.2f}x")
        if w.get("held_above_vwap") is not None:
            lines.append(f"- VWAP: {'held above' if w['held_above_vwap'] else 'broke below'} (VWAP={w.get('vwap_at_end', '?')})")
        if w.get("held_above_ema9") is not None:
            lines.append(f"- EMA9: {'held above' if w['held_above_ema9'] else 'broke below'} (EMA9={w.get('ema9_at_end', '?')})")
        if w.get("new_hod"):
            lines.append(f"- NEW HIGH OF DAY")
        if w.get("whole_dollar_levels"):
            lines.append(f"- Whole dollar levels: {w['whole_dollar_levels']}")
        lines.append("")

    return "\n".join(lines)


# ─── Main ───────────────────────────────────────────────────────────────────

def analyze(symbol: str, date_str: str, tick_cache: str):
    """Run full wave analysis for a stock/date."""
    print(f"\n{'='*60}")
    print(f"  Wave Analysis: {symbol} {date_str}")
    print(f"{'='*60}")

    # 1) Load ticks
    ticks = load_ticks(symbol, date_str, tick_cache)
    print(f"  Loaded {len(ticks)} ticks")

    # 2) Build 1m bars
    bars = build_1m_bars(ticks)
    print(f"  Built {len(bars)} 1-min bars")

    if not bars:
        print("  ERROR: No bars built from ticks")
        return None

    # 3) Compute VWAP and EMA
    vwap_map = compute_vwap_series(bars)
    ema_map = compute_ema_series(bars, period=9)

    # 4) Run sim to find SQ entry/exit
    print("  Running squeeze sim to find entry/exit points...")
    trades = run_sim_for_exits(symbol, date_str, tick_cache)

    # Find first trade with sq_target_hit exit
    sq_trade = None
    for t in trades:
        if "sq_target_hit" in t.get("exit_reason", ""):
            sq_trade = t
            break

    if not sq_trade:
        # Fall back to first trade regardless of exit reason
        if trades:
            sq_trade = trades[0]
            print(f"  WARNING: No sq_target_hit found. Using first trade exit: {sq_trade.get('exit_reason', '?')}")
        else:
            print("  ERROR: No trades found in sim output")
            return None

    sq_exit_price = sq_trade.get("entry_price", 0)  # Use entry for the continuation start if no exit
    sq_exit_time = sq_trade.get("exit_time", sq_trade.get("entry_time", "07:00"))
    sq_exit_reason = sq_trade.get("exit_reason", "unknown")

    # For sq_target_hit, exit price = entry + 2R
    if "sq_target_hit" in sq_exit_reason:
        r_val = sq_trade.get("r", 0)
        sq_exit_price = sq_trade["entry_price"] + 2.0 * r_val
    else:
        # Use the last known trade price near exit time
        exit_min = time_str_to_min(sq_exit_time)
        exit_bar = None
        for b in bars:
            if b["minute"] == exit_min:
                exit_bar = b
                break
        if exit_bar:
            sq_exit_price = exit_bar["c"]

    sq_exit_min = time_str_to_min(sq_exit_time)
    print(f"  SQ exit: ${sq_exit_price:.2f} at {sq_exit_time} ({sq_exit_reason})")

    # 5) Detect swings on post-exit bars
    # Use ALL bars for swing detection (context matters)
    swings = detect_swings(bars)
    alt_swings = build_alternating_swings(swings)
    print(f"  Detected {len(swings)} raw swings, {len(alt_swings)} alternating")

    # 6) Build waves from the exit point
    waves = build_waves(bars, alt_swings, sq_exit_min, sq_exit_price, vwap_map, ema_map)
    print(f"  Built {len(waves)} waves")

    # 7) Compute summary
    # Use bars after exit for HOD calculation
    post_exit_bars = [b for b in bars if b["minute"] >= sq_exit_min]
    summary = compute_summary(waves, sq_exit_price, post_exit_bars if post_exit_bars else bars)

    # 8) Build output data
    hod = max(b["h"] for b in bars) if bars else 0
    hod_bar = max(bars, key=lambda b: b["h"]) if bars else None

    data = {
        "stock": symbol,
        "date": date_str,
        "sq_entry_price": round(sq_trade.get("entry_price", 0), 4),
        "sq_entry_time": sq_trade.get("entry_time", "?"),
        "sq_exit_price": round(sq_exit_price, 4),
        "sq_exit_time": sq_exit_time,
        "sq_exit_reason": sq_exit_reason,
        "hod": round(hod, 4),
        "hod_time": hod_bar["time_str"] if hod_bar else "",
        "continuation_range_pct": round(
            ((hod - sq_exit_price) / sq_exit_price * 100) if sq_exit_price > 0 else 0, 1),
        "waves": waves,
        "summary": summary,
        "total_trades_in_sim": len(trades),
    }

    # 9) Save JSON
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wave_analysis")
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, f"{symbol}_{date_str}.json")
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved JSON: {json_path}")

    # 10) Save MD
    md_path = os.path.join(out_dir, f"{symbol}_{date_str}.md")
    md_content = generate_md(data)
    with open(md_path, "w") as f:
        f.write(md_content)
    print(f"  Saved MD:   {md_path}")

    return data


# ─── CLI ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Analyze runner waves from tick data")
    parser.add_argument("symbol", help="Stock symbol (e.g. ALUR)")
    parser.add_argument("date", help="Date (YYYY-MM-DD)")
    parser.add_argument("--tick-cache", default="tick_cache/", help="Path to tick cache directory")
    args = parser.parse_args()

    analyze(args.symbol, args.date, args.tick_cache)


if __name__ == "__main__":
    main()
