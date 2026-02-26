"""
analyze_day.py — Extract raw price action data for trade log analysis.

Usage:
    python analyze_day.py ROLR 2026-01-14 07:00 12:00
"""

from __future__ import annotations
import sys
import os
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import pytz

load_dotenv()

ET = pytz.timezone("US/Eastern")

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest, StockTradesRequest
from alpaca.data.timeframe import TimeFrame

API_KEY = os.getenv("APCA_API_KEY_ID")
API_SECRET = os.getenv("APCA_API_SECRET_KEY")
hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)


def analyze(symbol: str, date_str: str, start_et: str, end_et: str):
    date = datetime.strptime(date_str, "%Y-%m-%d")
    sh, sm = map(int, start_et.split(":"))
    eh, em = map(int, end_et.split(":"))

    start_dt = ET.localize(date.replace(hour=sh, minute=sm, second=0))
    end_dt = ET.localize(date.replace(hour=eh, minute=em, second=0))
    # Seed from 4 AM
    seed_dt = ET.localize(date.replace(hour=4, minute=0, second=0))

    start_utc = seed_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    # Fetch 1-min bars
    print(f"Fetching 1-min bars for {symbol} on {date_str}...", flush=True)
    req = StockBarsRequest(
        symbol_or_symbols=[symbol],
        timeframe=TimeFrame.Minute,
        start=start_utc,
        end=end_utc,
        feed="sip",
    )
    bar_set = hist_client.get_stock_bars(req)
    bars = bar_set.data.get(symbol, [])
    print(f"  {len(bars)} bars fetched", flush=True)

    if not bars:
        print("No bars. Exiting.")
        return

    # Build bar list with ET timestamps
    bar_list = []
    for b in bars:
        ts = b.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ts_et = ts.astimezone(ET)
        bar_list.append({
            "time_et": ts_et.strftime("%H:%M"),
            "open": float(b.open),
            "high": float(b.high),
            "low": float(b.low),
            "close": float(b.close),
            "volume": int(b.volume),
            "ts_utc": ts,
        })

    # Filter to sim window
    sim_start_utc = start_dt.astimezone(timezone.utc)
    sim_bars = [b for b in bar_list if b["ts_utc"] >= sim_start_utc]
    all_bars = bar_list

    # === KEY METRICS ===
    print(f"\n{'='*70}")
    print(f"  RAW PRICE ACTION: {symbol} on {date_str} ({start_et} - {end_et} ET)")
    print(f"{'='*70}")

    # Day range
    day_low = min(b["low"] for b in sim_bars)
    day_high = max(b["high"] for b in sim_bars)
    day_open = sim_bars[0]["open"]
    day_close = sim_bars[-1]["close"]
    day_range_pct = (day_high - day_low) / day_low * 100

    print(f"\n  SESSION OVERVIEW")
    print(f"  Open: ${day_open:.2f}  High: ${day_high:.2f}  Low: ${day_low:.2f}  Close: ${day_close:.2f}")
    print(f"  Range: ${day_high - day_low:.2f} ({day_range_pct:.1f}%)")
    print(f"  Total Volume: {sum(b['volume'] for b in sim_bars):,}")

    # Premarket (4:00 - 7:00 or start)
    premarket = [b for b in all_bars if b["ts_utc"] < sim_start_utc]
    if premarket:
        pm_high = max(b["high"] for b in premarket)
        pm_low = min(b["low"] for b in premarket)
        pm_vol = sum(b["volume"] for b in premarket)
        print(f"\n  PREMARKET (4AM - {start_et})")
        print(f"  High: ${pm_high:.2f}  Low: ${pm_low:.2f}  Volume: {pm_vol:,}")

    # === BIG MOVES (bars with > 5% range or > 2x avg volume) ===
    avg_vol = sum(b["volume"] for b in sim_bars) / max(len(sim_bars), 1)

    print(f"\n  BIG MOVE BARS (>5% bar range or >3x avg volume)")
    print(f"  {'TIME':>6}  {'O':>8}  {'H':>8}  {'L':>8}  {'C':>8}  {'VOL':>10}  {'RANGE%':>7}  {'TYPE':>8}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*7}  {'─'*8}")

    big_moves = []
    for b in sim_bars:
        rng = b["high"] - b["low"]
        rng_pct = rng / max(b["low"], 0.01) * 100
        vol_ratio = b["volume"] / max(avg_vol, 1)
        bar_type = "GREEN" if b["close"] >= b["open"] else "RED"

        if rng_pct > 5 or vol_ratio > 3:
            big_moves.append(b | {"rng_pct": rng_pct, "vol_ratio": vol_ratio, "type": bar_type})
            print(f"  {b['time_et']:>6}  {b['open']:>8.2f}  {b['high']:>8.2f}  {b['low']:>8.2f}  {b['close']:>8.2f}  {b['volume']:>10,}  {rng_pct:>6.1f}%  {bar_type:>8}")

    # === KEY LEVELS ===
    print(f"\n  KEY PRICE LEVELS")

    # Find resistance levels (bars where high was tested multiple times)
    highs = [b["high"] for b in sim_bars]
    # Find the price at major turning points
    running_high = float("-inf")
    breakout_levels = []
    for i, b in enumerate(sim_bars):
        if b["high"] > running_high:
            if b["high"] > running_high * 1.03:  # 3% new high = breakout
                breakout_levels.append({
                    "time": b["time_et"],
                    "level": b["high"],
                    "prev_high": running_high if running_high > 0 else None,
                })
            running_high = b["high"]

    for bl in breakout_levels:
        prev = f"(from ${bl['prev_high']:.2f})" if bl["prev_high"] and bl["prev_high"] > 0 else ""
        print(f"  {bl['time']:>6}  NEW HIGH ${bl['level']:.2f} {prev}")

    # === VOLUME PROFILE (by 30-min windows) ===
    print(f"\n  VOLUME PROFILE (30-min windows)")
    print(f"  {'WINDOW':>12}  {'VOLUME':>12}  {'HIGH':>8}  {'LOW':>8}  {'MOVE':>8}")
    print(f"  {'─'*12}  {'─'*12}  {'─'*8}  {'─'*8}  {'─'*8}")

    window_start = sim_bars[0]["ts_utc"]
    window_bars = []
    for b in sim_bars:
        if b["ts_utc"] >= window_start + timedelta(minutes=30):
            if window_bars:
                w_high = max(wb["high"] for wb in window_bars)
                w_low = min(wb["low"] for wb in window_bars)
                w_vol = sum(wb["volume"] for wb in window_bars)
                w_move = (w_high - w_low) / w_low * 100
                t1 = window_bars[0]["time_et"]
                t2 = window_bars[-1]["time_et"]
                print(f"  {t1}-{t2}  {w_vol:>12,}  {w_high:>8.2f}  {w_low:>8.2f}  {w_move:>7.1f}%")
            window_start = b["ts_utc"]
            window_bars = []
        window_bars.append(b)
    # Last window
    if window_bars:
        w_high = max(wb["high"] for wb in window_bars)
        w_low = min(wb["low"] for wb in window_bars)
        w_vol = sum(wb["volume"] for wb in window_bars)
        w_move = (w_high - w_low) / w_low * 100
        t1 = window_bars[0]["time_et"]
        t2 = window_bars[-1]["time_et"]
        print(f"  {t1}-{t2}  {w_vol:>12,}  {w_high:>8.2f}  {w_low:>8.2f}  {w_move:>7.1f}%")

    # === CONSECUTIVE GREEN/RED RUNS ===
    print(f"\n  CONSECUTIVE CANDLE RUNS")
    streak_type = None
    streak_count = 0
    streak_start = None
    streak_start_price = 0
    runs = []

    for b in sim_bars:
        is_green = b["close"] >= b["open"]
        cur_type = "GREEN" if is_green else "RED"

        if cur_type == streak_type:
            streak_count += 1
        else:
            if streak_count >= 4 and streak_type:
                runs.append({
                    "type": streak_type,
                    "count": streak_count,
                    "start": streak_start,
                    "start_price": streak_start_price,
                    "end": b["time_et"],
                    "end_price": sim_bars[sim_bars.index(b) - 1]["close"],
                })
            streak_type = cur_type
            streak_count = 1
            streak_start = b["time_et"]
            streak_start_price = b["open"]

    if streak_count >= 4 and streak_type:
        runs.append({
            "type": streak_type,
            "count": streak_count,
            "start": streak_start,
            "start_price": streak_start_price,
            "end": sim_bars[-1]["time_et"],
            "end_price": sim_bars[-1]["close"],
        })

    for r in runs:
        move = r["end_price"] - r["start_price"]
        move_pct = move / max(r["start_price"], 0.01) * 100
        direction = "↑" if move > 0 else "↓"
        print(f"  {r['start']}-{r['end']}  {r['count']} {r['type']} bars  ${r['start_price']:.2f} → ${r['end_price']:.2f} ({direction}{abs(move_pct):.1f}%)")

    # === FULL 1-MIN BAR TABLE ===
    print(f"\n  FULL 1-MIN BAR DATA ({start_et} - {end_et} ET)")
    print(f"  {'TIME':>6}  {'O':>8}  {'H':>8}  {'L':>8}  {'C':>8}  {'VOL':>10}  {'RNG%':>6}  {'TYPE':>5}")
    print(f"  {'─'*6}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*6}  {'─'*5}")
    for b in sim_bars:
        rng_pct = (b["high"] - b["low"]) / max(b["low"], 0.01) * 100
        bar_type = "G" if b["close"] >= b["open"] else "R"
        print(f"  {b['time_et']:>6}  {b['open']:>8.4f}  {b['high']:>8.4f}  {b['low']:>8.4f}  {b['close']:>8.4f}  {b['volume']:>10,}  {rng_pct:>5.1f}%  {bar_type:>5}")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python analyze_day.py SYMBOL DATE START_ET END_ET")
        sys.exit(1)
    analyze(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4])
