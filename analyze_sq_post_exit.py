"""
Post-exit analysis for all SQ (Squeeze) trades.

For each SQ trade: what happened to the stock AFTER the bot exited?
How much money was left on the table?

Sources:
  - megatest_results/megatest_state_sq_only_v2.json  (116 trades, 2025+)
  - ytd_v2_backtest_state.json                        (17 SQ trades, 2026)

Output: ~/warrior_bot/cowork_reports/post_exit_analysis.md
"""

import json
import os
import sys
import gzip
import time as _time
from datetime import datetime, timedelta, timezone
from collections import Counter, defaultdict

# ─── Load .env ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

API_KEY    = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY")
API_SECRET = os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_SECRET_KEY")

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests  import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

hist_client = StockHistoricalDataClient(API_KEY, API_SECRET)

# ─── Helpers ─────────────────────────────────────────────────────────────────

ET = timezone(timedelta(hours=-5))  # approximate (DST handled separately)

def et_offset_for_date(date_str: str) -> int:
    """Return hours offset from UTC for ET on the given date (handles DST)."""
    from zoneinfo import ZoneInfo
    import datetime as dt
    d = dt.date.fromisoformat(date_str)
    noon_et = dt.datetime(d.year, d.month, d.day, 12, 0, tzinfo=ZoneInfo("America/New_York"))
    offset = noon_et.utcoffset().total_seconds() / 3600
    return int(offset)  # -5 or -4


def et_to_utc(date_str: str, time_str: str) -> datetime:
    """Convert 'YYYY-MM-DD' + 'HH:MM' ET to UTC datetime."""
    from zoneinfo import ZoneInfo
    import datetime as dt
    hour, minute = map(int, time_str.split(":"))
    d = dt.date.fromisoformat(date_str)
    local = dt.datetime(d.year, d.month, d.day, hour, minute, tzinfo=ZoneInfo("America/New_York"))
    return local.astimezone(timezone.utc)


def fetch_day_bars(symbol: str, date_str: str) -> list:
    """Fetch 1-min bars for entire session (07:00–12:00 ET) for symbol/date."""
    start_utc = et_to_utc(date_str, "07:00")
    end_utc   = et_to_utc(date_str, "12:05")  # small buffer
    for attempt in range(3):
        try:
            req = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Minute,
                start=start_utc,
                end=end_utc,
                feed="sip",
            )
            return hist_client.get_stock_bars(req).data.get(symbol, [])
        except Exception as e:
            if attempt < 2:
                _time.sleep(2 ** attempt)
            else:
                print(f"  [WARN] fetch_bars failed for {symbol} {date_str}: {e}")
                return []


def tick_cache_path(symbol: str, date_str: str) -> str:
    return f"tick_cache/{date_str}/{symbol}.json.gz"


def post_exit_from_ticks(symbol: str, date_str: str, exit_time_str: str,
                          exit_price: float, r: float) -> dict | None:
    """Use tick cache for post-exit analysis (2026 data)."""
    path = tick_cache_path(symbol, date_str)
    if not os.path.exists(path):
        return None
    with gzip.open(path) as f:
        ticks = json.load(f)
    ticks.sort(key=lambda x: x["t"])

    exit_utc_str = et_to_utc(date_str, exit_time_str).strftime("%Y-%m-%dT%H:%M")
    session_end  = et_to_utc(date_str, "12:00").strftime("%Y-%m-%dT%H:%M")

    after = [t for t in ticks if exit_utc_str <= t["t"] < session_end + ":00"]
    if not after:
        return None

    prices = [t["p"] for t in after]
    timestamps = [t["t"] for t in after]

    max_p   = max(prices)
    max_idx = prices.index(max_p)
    max_t   = timestamps[max_idx]

    # Time to peak in minutes
    exit_dt  = et_to_utc(date_str, exit_time_str)
    peak_dt  = datetime.fromisoformat(max_t.replace("Z", "+00:00"))
    mins_to_peak = (peak_dt - exit_dt).total_seconds() / 60

    # Did it come back below exit_price after the peak?
    post_peak_prices = prices[max_idx:]
    came_back = any(p < exit_price for p in post_peak_prices)

    additional = max_p - exit_price
    add_r      = additional / r if r > 0 else 0

    return {
        "post_exit_high": round(max_p, 4),
        "additional_move": round(additional, 4),
        "additional_r": round(add_r, 2),
        "mins_to_peak": round(mins_to_peak, 1),
        "came_back_below_exit": came_back,
        "source": "tick_cache",
        "n_ticks": len(after),
    }


def post_exit_from_bars(symbol: str, date_str: str, exit_time_str: str,
                         exit_price: float, r: float) -> dict | None:
    """Use Alpaca 1-min bars for post-exit analysis."""
    bars = fetch_day_bars(symbol, date_str)
    if not bars:
        return None

    exit_utc = et_to_utc(date_str, exit_time_str)

    # Filter bars that START at or after the exit minute
    after = []
    for b in bars:
        bar_ts = b.timestamp
        if hasattr(bar_ts, "tzinfo") and bar_ts.tzinfo is None:
            bar_ts = bar_ts.replace(tzinfo=timezone.utc)
        elif not hasattr(bar_ts, "tzinfo"):
            bar_ts = datetime.fromisoformat(str(bar_ts)).replace(tzinfo=timezone.utc)
        if bar_ts >= exit_utc:
            after.append(b)

    if not after:
        return None

    # High is the max of bar.high values
    highs      = [b.high for b in after]
    max_h      = max(highs)
    max_idx    = highs.index(max_h)
    peak_bar   = after[max_idx]
    peak_ts    = peak_bar.timestamp
    if hasattr(peak_ts, "tzinfo") and peak_ts.tzinfo is None:
        peak_ts = peak_ts.replace(tzinfo=timezone.utc)

    mins_to_peak = (peak_ts - exit_utc).total_seconds() / 60

    # Did any bar's LOW go below exit_price after the peak?
    post_peak_lows = [b.low for b in after[max_idx:]]
    came_back = any(l < exit_price for l in post_peak_lows)

    additional = max_h - exit_price
    add_r      = additional / r if r > 0 else 0

    return {
        "post_exit_high": round(max_h, 4),
        "additional_move": round(additional, 4),
        "additional_r": round(add_r, 2),
        "mins_to_peak": round(mins_to_peak, 1),
        "came_back_below_exit": came_back,
        "source": "alpaca_bars",
        "n_bars": len(after),
    }


# ─── Load all SQ trades ───────────────────────────────────────────────────────

def load_all_sq_trades() -> list:
    all_trades = []

    with open("megatest_results/megatest_state_sq_only_v2.json") as f:
        d = json.load(f)
    for t in d["config_a"]["trades"]:
        t["_source"]    = "megatest_sq_v2"
        t["exit_t"]     = t.get("exit_time", t.get("time", ""))
        all_trades.append(t)

    with open("ytd_v2_backtest_state.json") as f:
        d = json.load(f)
    for t in d["config_a"]["trades"]:
        if t.get("setup_type") == "squeeze" or "sq" in t.get("reason", ""):
            t["_source"] = "ytd_v2"
            t["exit_t"]  = t.get("exit_time", t.get("time", ""))
            all_trades.append(t)

    # Deduplicate by symbol+date+entry
    seen, unique = set(), []
    for t in all_trades:
        key = (t["symbol"], t["date"], t["entry"])
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return unique


# ─── Main analysis ────────────────────────────────────────────────────────────

def categorize(add_r: float) -> str:
    if add_r >= 2.0:
        return "RUNNER"
    elif add_r >= 0.5:
        return "MODEST"
    elif add_r >= 0:
        return "GOOD_EXIT"
    else:
        return "PERFECT_EXIT"


def run_analysis():
    trades = load_all_sq_trades()
    print(f"Loaded {len(trades)} unique SQ trades")

    results = []
    bar_cache = {}  # (symbol, date) -> bars, to avoid re-fetching

    for i, t in enumerate(trades):
        sym        = t["symbol"]
        date       = t["date"]
        exit_time  = t["exit_t"]
        exit_price = t["exit_price"]
        r          = t["r"]
        reason     = t["reason"]

        print(f"  [{i+1}/{len(trades)}] {sym} {date} exit={exit_time} @ {exit_price:.2f} r={r:.2f} [{reason}]", end=" ", flush=True)

        if r <= 0:
            print("SKIP (r=0)")
            continue

        # Try tick cache first (faster, more precise)
        px = post_exit_from_ticks(sym, date, exit_time, exit_price, r)

        # Fall back to Alpaca bars
        if px is None:
            cache_key = (sym, date)
            if cache_key not in bar_cache:
                bar_cache[cache_key] = fetch_day_bars(sym, date)
                _time.sleep(0.15)  # gentle rate limiting

            bars = bar_cache.get(cache_key, [])
            if bars:
                exit_utc = et_to_utc(date, exit_time)
                after_bars = []
                for b in bars:
                    bar_ts = b.timestamp
                    if hasattr(bar_ts, "tzinfo") and bar_ts.tzinfo is None:
                        bar_ts = bar_ts.replace(tzinfo=timezone.utc)
                    if bar_ts >= exit_utc:
                        after_bars.append(b)

                if after_bars:
                    highs    = [b.high for b in after_bars]
                    max_h    = max(highs)
                    max_idx  = highs.index(max_h)
                    peak_bar = after_bars[max_idx]
                    peak_ts  = peak_bar.timestamp
                    if hasattr(peak_ts, "tzinfo") and peak_ts.tzinfo is None:
                        peak_ts = peak_ts.replace(tzinfo=timezone.utc)
                    mins_to_peak = (peak_ts - exit_utc).total_seconds() / 60
                    post_peak_lows = [b.low for b in after_bars[max_idx:]]
                    came_back = any(l < exit_price for l in post_peak_lows)
                    additional = max_h - exit_price
                    add_r = additional / r
                    px = {
                        "post_exit_high": round(max_h, 4),
                        "additional_move": round(additional, 4),
                        "additional_r": round(add_r, 2),
                        "mins_to_peak": round(mins_to_peak, 1),
                        "came_back_below_exit": came_back,
                        "source": "alpaca_bars",
                        "n_bars": len(after_bars),
                    }

        if px is None:
            print("NO DATA")
            continue

        category = categorize(px["additional_r"])
        # "left on table" in dollars: qty * additional_move (but capped if came back)
        # qty is implied by notional / entry
        qty = int(t.get("notional", 0) / t["entry"]) if t.get("notional") else 0
        left_on_table = round(qty * px["additional_move"], 0) if not px["came_back_below_exit"] else 0
        left_on_table_optimistic = round(qty * px["additional_move"], 0)  # if we had perfect exit

        result = {
            "symbol": sym,
            "date": date,
            "exit_time": exit_time,
            "entry": t["entry"],
            "exit_price": exit_price,
            "r": r,
            "reason": reason,
            "score": t.get("score", 0),
            "pnl_as_taken": t.get("pnl", 0),
            "r_mult_taken": t.get("r_mult", ""),
            "qty": qty,
            "source": t["_source"],
            **px,
            "category": category,
            "left_on_table": left_on_table_optimistic,
        }
        results.append(result)
        print(f"+{px['additional_r']:.1f}R post-exit ({category}) {px['mins_to_peak']:.0f}m to peak")

    return results


# ─── Report generation ────────────────────────────────────────────────────────

def build_report(results: list) -> str:
    lines = []

    # ── Summary stats ──
    total = len(results)
    by_cat = Counter(r["category"] for r in results)
    by_reason = Counter(r["reason"] for r in results)

    # Trades where we left money (stock kept going, not came_back)
    true_runners = [r for r in results if r["category"] == "RUNNER"]
    modest       = [r for r in results if r["category"] == "MODEST"]
    good_exits   = [r for r in results if r["category"] == "GOOD_EXIT"]
    perfect      = [r for r in results if r["category"] == "PERFECT_EXIT"]

    total_left = sum(r["left_on_table"] for r in results)
    runner_left = sum(r["left_on_table"] for r in true_runners)
    modest_left  = sum(r["left_on_table"] for r in modest)

    lines.append("# SQ Post-Exit Analysis")
    lines.append("")
    lines.append(f"**Date generated:** 2026-03-22  ")
    lines.append(f"**Trades analyzed:** {total}  ")
    lines.append(f"**Sources:** megatest_sq_only_v2 + ytd_v2_backtest_state  ")
    lines.append("")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append(f"| Category | Count | % | Avg add. R | $ left on table |")
    lines.append(f"|----------|-------|---|------------|-----------------|")
    for cat, trades_in_cat in [("RUNNER", true_runners), ("MODEST", modest), ("GOOD_EXIT", good_exits), ("PERFECT_EXIT", perfect)]:
        n = len(trades_in_cat)
        pct = 100 * n / total if total else 0
        avg_r = sum(r["additional_r"] for r in trades_in_cat) / n if n else 0
        dollars = sum(r["left_on_table"] for r in trades_in_cat)
        lines.append(f"| {cat} | {n} | {pct:.0f}% | +{avg_r:.1f}R | ${dollars:,.0f} |")

    lines.append(f"| **TOTAL** | **{total}** | | | **${total_left:,.0f}** |")
    lines.append("")
    lines.append(f"> **Total $ left on table (optimistic, all exit categories):** ${total_left:,.0f}")
    lines.append(f"> **From RUNNERS alone:** ${runner_left:,.0f}")
    lines.append(f"> **From MODEST continuations:** ${modest_left:,.0f}")
    lines.append("")

    # ── Exit reason breakdown ──
    lines.append("## Exit Reason Breakdown")
    lines.append("")
    lines.append("| Exit Reason | Count | RUNNER% | MODEST% | GOOD_EXIT% | Avg add. R | Avg $ left |")
    lines.append("|-------------|-------|---------|---------|------------|------------|------------|")
    for reason in sorted(by_reason, key=by_reason.get, reverse=True):
        group = [r for r in results if r["reason"] == reason]
        n = len(group)
        r_pct  = 100 * sum(1 for r in group if r["category"] == "RUNNER")  / n
        m_pct  = 100 * sum(1 for r in group if r["category"] == "MODEST")  / n
        g_pct  = 100 * sum(1 for r in group if r["category"] == "GOOD_EXIT") / n
        avg_r  = sum(r["additional_r"] for r in group) / n
        avg_d  = sum(r["left_on_table"] for r in group) / n
        lines.append(f"| {reason} | {n} | {r_pct:.0f}% | {m_pct:.0f}% | {g_pct:.0f}% | +{avg_r:.1f}R | ${avg_d:,.0f} |")
    lines.append("")

    # ── Runner deep-dive ──
    lines.append("## Runner Deep-Dive (2R+ post-exit continuation)")
    lines.append("")
    lines.append(f"**{len(true_runners)} trades** kept running 2R+ above exit price")
    lines.append("")
    if true_runners:
        lines.append("| Symbol | Date | Exit | Exit Price | +R avail | mins to peak | came back | Exit Reason | Score | $ left |")
        lines.append("|--------|------|------|------------|----------|--------------|-----------|-------------|-------|--------|")
        for r in sorted(true_runners, key=lambda x: x["additional_r"], reverse=True):
            cb = "Y" if r["came_back_below_exit"] else "N"
            lines.append(
                f"| {r['symbol']} | {r['date']} | {r['exit_time']} | "
                f"{r['exit_price']:.2f} | +{r['additional_r']:.1f}R | "
                f"{r['mins_to_peak']:.0f}m | {cb} | {r['reason']} | "
                f"{r['score']} | ${r['left_on_table']:,.0f} |"
            )
        lines.append("")

        # Runner characteristics
        lines.append("### Runner Characteristics")
        lines.append("")
        by_reason_runner = Counter(r["reason"] for r in true_runners)
        lines.append(f"**Exit reason distribution in runners:**")
        for k, v in by_reason_runner.most_common():
            lines.append(f"- {k}: {v} ({100*v/len(true_runners):.0f}%)")
        lines.append("")

        avg_score_runner = sum(r["score"] for r in true_runners) / len(true_runners)
        avg_score_all    = sum(r["score"] for r in results) / len(results)
        avg_r_runner     = sum(r["r"] for r in true_runners) / len(true_runners)
        avg_r_all        = sum(r["r"] for r in results) / len(results)
        avg_exit_r_runner = sum(float(r["r_mult_taken"].replace("R","").replace("+","")) for r in true_runners if r["r_mult_taken"] and r["r_mult_taken"] != "" and "R" in str(r["r_mult_taken"])) / len(true_runners)
        avg_exit_r_all    = sum(float(r["r_mult_taken"].replace("R","").replace("+","")) for r in results if r["r_mult_taken"] and r["r_mult_taken"] != "" and "R" in str(r["r_mult_taken"])) / len(results)

        lines.append(f"| Metric | Runners | All SQ trades |")
        lines.append(f"|--------|---------|---------------|")
        lines.append(f"| Avg score at entry | {avg_score_runner:.1f} | {avg_score_all:.1f} |")
        lines.append(f"| Avg R size ($) | ${avg_r_runner:.3f} | ${avg_r_all:.3f} |")
        lines.append(f"| Avg R taken at exit | +{avg_exit_r_runner:.1f}R | +{avg_exit_r_all:.1f}R |")
        lines.append("")

        # Early vs late exit
        early_runners = [r for r in true_runners if r["exit_time"] < "09:00"]
        lines.append(f"**Timing:** {len(early_runners)}/{len(true_runners)} runner exits happen before 9 AM ET")
        lines.append("")

    # ── Modest continuation ──
    lines.append("## Modest Continuation (0.5–2R post-exit)")
    lines.append("")
    if modest:
        lines.append("| Symbol | Date | Exit | Exit Price | +R avail | mins to peak | came back | Exit Reason |")
        lines.append("|--------|------|------|------------|----------|--------------|-----------|-------------|")
        for r in sorted(modest, key=lambda x: x["additional_r"], reverse=True):
            cb = "Y" if r["came_back_below_exit"] else "N"
            lines.append(
                f"| {r['symbol']} | {r['date']} | {r['exit_time']} | "
                f"{r['exit_price']:.2f} | +{r['additional_r']:.1f}R | "
                f"{r['mins_to_peak']:.0f}m | {cb} | {r['reason']} |"
            )
        lines.append("")

    # ── Perfect / Good exits ──
    lines.append("## Good Exits & Perfect Exits (exit roughly correct)")
    lines.append("")
    lines.append(f"- **Good exits** (<0.5R above exit): {len(good_exits)} trades")
    lines.append(f"- **Perfect exits** (stock below exit): {len(perfect)} trades")
    lines.append(f"- Combined: {len(good_exits)+len(perfect)} trades ({100*(len(good_exits)+len(perfect))/total:.0f}% of all SQ exits)")
    lines.append("")

    # ── Pattern: sq_target_hit ──
    target_hits = [r for r in results if r["reason"] == "sq_target_hit"]
    if target_hits:
        lines.append("## Focus: sq_target_hit exits")
        lines.append("")
        lines.append("These are the fixed-target exits where the bot capped profit. How often was that a mistake?")
        lines.append("")
        th_runner = [r for r in target_hits if r["category"] == "RUNNER"]
        th_modest = [r for r in target_hits if r["category"] == "MODEST"]
        th_good   = [r for r in target_hits if r["category"] in ("GOOD_EXIT", "PERFECT_EXIT")]
        lines.append(f"- Runner after target hit: {len(th_runner)}/{len(target_hits)} ({100*len(th_runner)/len(target_hits):.0f}%)")
        lines.append(f"- Modest continuation: {len(th_modest)}/{len(target_hits)} ({100*len(th_modest)/len(target_hits):.0f}%)")
        lines.append(f"- Good/perfect exit: {len(th_good)}/{len(target_hits)} ({100*len(th_good)/len(target_hits):.0f}%)")
        lines.append("")
        th_runner_left = sum(r["left_on_table"] for r in th_runner)
        th_modest_left = sum(r["left_on_table"] for r in th_modest)
        lines.append(f"Total $ left by exiting at target (runners): **${th_runner_left:,.0f}**")
        lines.append(f"Total $ left by exiting at target (modest):  ${th_modest_left:,.0f}")
        lines.append("")
        lines.append("| Symbol | Date | R taken | +R available | Verdict |")
        lines.append("|--------|------|---------|-------------|---------|")
        for r in sorted(target_hits, key=lambda x: x["additional_r"], reverse=True)[:20]:
            lines.append(
                f"| {r['symbol']} | {r['date']} | {r['r_mult_taken']} | "
                f"+{r['additional_r']:.1f}R | {r['category']} |"
            )
        lines.append("")

    # ── Pattern: sq_para_trail_exit ──
    para_exits = [r for r in results if r["reason"] == "sq_para_trail_exit"]
    if para_exits:
        lines.append("## Focus: sq_para_trail_exit exits")
        lines.append("")
        lines.append("Para trail exits — trailing stop got hit. Did the stock recover?")
        lines.append("")
        pt_runner = [r for r in para_exits if r["category"] == "RUNNER"]
        pt_modest = [r for r in para_exits if r["category"] == "MODEST"]
        pt_good   = [r for r in para_exits if r["category"] in ("GOOD_EXIT", "PERFECT_EXIT")]
        lines.append(f"- Runner after para trail: {len(pt_runner)}/{len(para_exits)} ({100*len(pt_runner)/len(para_exits):.0f}%)")
        lines.append(f"- Modest continuation: {len(pt_modest)}/{len(para_exits)} ({100*len(pt_modest)/len(para_exits):.0f}%)")
        lines.append(f"- Good/perfect exit: {len(pt_good)}/{len(para_exits)} ({100*len(pt_good)/len(para_exits):.0f}%)")
        lines.append("")

    # ── Key signal candidates ──
    lines.append("## Key Signal Analysis: What Distinguishes Runners?")
    lines.append("")
    lines.append("At the moment of exit, what features predict a runner vs a good exit?")
    lines.append("")

    # Score distribution
    if true_runners and good_exits:
        high_score_runners = sum(1 for r in true_runners if r["score"] >= 10)
        high_score_good    = sum(1 for r in good_exits if r["score"] >= 10)
        lines.append(f"**Score >= 10:**")
        lines.append(f"- In runners: {high_score_runners}/{len(true_runners)} ({100*high_score_runners/len(true_runners):.0f}%)")
        lines.append(f"- In good exits: {high_score_good}/{len(good_exits)} ({100*high_score_good/len(good_exits):.0f}%)")
        lines.append("")

    # Exit time distribution
    lines.append("**Exit time buckets:**")
    buckets = [("07:00-07:30", "07:00", "07:30"),
               ("07:30-08:00", "07:30", "08:00"),
               ("08:00-09:00", "08:00", "09:00"),
               ("09:00-10:00", "09:00", "10:00"),
               ("10:00+",      "10:00", "24:00")]
    lines.append("")
    lines.append("| Time bucket | Total | Runners | RUNNER% |")
    lines.append("|-------------|-------|---------|---------|")
    for label, start, end in buckets:
        group = [r for r in results if start <= r["exit_time"] < end]
        rg = [r for r in group if r["category"] == "RUNNER"]
        if group:
            lines.append(f"| {label} | {len(group)} | {len(rg)} | {100*len(rg)/len(group):.0f}% |")
    lines.append("")

    # R multiple at exit vs runner probability
    lines.append("**R multiple at exit vs runner rate:**")
    lines.append("")
    lines.append("| R taken at exit | Total | Runners | RUNNER% |")
    lines.append("|-----------------|-------|---------|---------|")
    r_buckets = [("<0R", None, 0), ("0-1R", 0, 1), ("1-3R", 1, 3), ("3-6R", 3, 6), ("6R+", 6, 999)]
    for label, lo, hi in r_buckets:
        def in_bucket(r_str):
            try:
                val = float(str(r_str).replace("R","").replace("+","").strip())
                if lo is None:
                    return val < hi
                return lo <= val < hi
            except:
                return False
        group = [r for r in results if in_bucket(r["r_mult_taken"])]
        rg = [r for r in group if r["category"] == "RUNNER"]
        if group:
            lines.append(f"| {label} | {len(group)} | {len(rg)} | {100*len(rg)/len(group):.0f}% |")
    lines.append("")

    # ── Simple rule candidate ──
    lines.append("## Candidate Exit Rule: \"Let It Run\" Signal")
    lines.append("")
    lines.append("Based on the data above, when should we NOT exit at the SQ target?")
    lines.append("")
    lines.append("Looking for a rule of the form:")
    lines.append("> *If [condition], extend target / trail instead of taking fixed profit*")
    lines.append("")

    # Check: early exits with high score
    early_high_score = [r for r in results if r["exit_time"] < "08:00" and r["score"] >= 10]
    early_high_score_runners = [r for r in early_high_score if r["category"] == "RUNNER"]
    if early_high_score:
        lines.append(f"**Rule candidate: Exit before 8 AM AND score >= 10**")
        lines.append(f"- {len(early_high_score)} trades match")
        lines.append(f"- {len(early_high_score_runners)} are runners ({100*len(early_high_score_runners)/len(early_high_score):.0f}%)")
        lines.append(f"- $ at risk: ${sum(r['left_on_table'] for r in early_high_score_runners):,.0f} recoverable")
        lines.append("")

    # Check: target hits only with high score
    th_high = [r for r in target_hits if r["score"] >= 10]
    th_high_runners = [r for r in th_high if r["category"] == "RUNNER"]
    if th_high:
        lines.append(f"**Rule candidate: sq_target_hit AND score >= 10**")
        lines.append(f"- {len(th_high)} trades match")
        lines.append(f"- {len(th_high_runners)} are runners ({100*len(th_high_runners)/len(th_high):.0f}%)")
        lines.append(f"- $ recoverable (in runners): ${sum(r['left_on_table'] for r in th_high_runners):,.0f}")
        lines.append("")

    lines.append("## Detailed Trade Log")
    lines.append("")
    lines.append("| # | Symbol | Date | ExitT | Entry | Exit$ | R | R-taken | +R post | minsToPeak | CameBack | Reason | Category |")
    lines.append("|---|--------|------|-------|-------|-------|---|---------|---------|------------|----------|--------|----------|")
    for i, r in enumerate(sorted(results, key=lambda x: x["additional_r"], reverse=True), 1):
        cb = "Y" if r["came_back_below_exit"] else "N"
        lines.append(
            f"| {i} | {r['symbol']} | {r['date']} | {r['exit_time']} | "
            f"{r['entry']:.2f} | {r['exit_price']:.2f} | {r['r']:.2f} | "
            f"{r['r_mult_taken']} | +{r['additional_r']:.1f}R | "
            f"{r['mins_to_peak']:.0f}m | {cb} | {r['reason']} | **{r['category']}** |"
        )
    lines.append("")
    lines.append("---")
    lines.append("*Generated by analyze_sq_post_exit.py*")

    return "\n".join(lines)


if __name__ == "__main__":
    print("=== SQ Post-Exit Analysis ===")
    print()
    results = run_analysis()

    print()
    print(f"Analysis complete: {len(results)} trades processed")

    # Save raw results as JSON for reference
    with open("cowork_reports/sq_post_exit_raw.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Raw results saved to cowork_reports/sq_post_exit_raw.json")

    report = build_report(results)

    os.makedirs("cowork_reports", exist_ok=True)
    out_path = "cowork_reports/post_exit_analysis.md"
    with open(out_path, "w") as f:
        f.write(report)

    print(f"Report saved to {out_path}")
