#!/usr/bin/env python3
"""
Exhaustion Score Dataset Builder
Reads tick cache, builds 1m bars, calculates indicators at the 2R price level.
Outputs JSON dataset and summary markdown.
"""

import json, gzip, os
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import math

# ─── Trade definitions ───────────────────────────────────────────────────────
# (date, symbol, entry, risk_per_share, label, post_r)
TRADES = [
    # Done
    ("2025-03-28", "ATON", 12.04, 0.47, "DONE", 1.1),
    ("2025-05-29", "BOSC", 6.04, 0.14, "DONE", 0.6),
    ("2025-03-05", "GV", 2.39, 0.14, "DONE", 0.4),
    ("2025-03-13", "SNES", 3.04, 0.14, "DONE", 0.0),
    ("2025-03-27", "DRMA", 2.04, 0.14, "DONE", -0.9),
    # Runners
    ("2025-06-26", "CYN", 6.04, 0.14, "RUNNER", 242.0),
    ("2025-06-26", "CYN", 8.04, 0.14, "RUNNER", 234.9),
    ("2025-06-26", "CYN", 9.04, 0.14, "RUNNER", 228.1),
    ("2026-01-14", "ROLR", 4.04, 0.14, "RUNNER", 121.4),
    ("2025-01-24", "ALUR", 8.04, 0.14, "RUNNER", 84.7),
    ("2025-06-16", "STAK", 3.04, 0.14, "RUNNER", 37.1),
    ("2025-06-02", "INM", 4.04, 0.14, "RUNNER", 32.3),
    ("2025-03-04", "RDGT", 3.04, 0.14, "RUNNER", 12.5),
    ("2025-06-16", "STAK", 7.04, 0.14, "RUNNER", 11.0),
    ("2025-02-04", "QNTM", 5.04, 0.14, "RUNNER", 10.4),
    ("2026-03-18", "ARTL", 5.04, 0.14, "RUNNER", 9.8),
    ("2025-07-17", "BSLK", 3.04, 0.14, "RUNNER", 8.6),
    ("2026-01-08", "ACON", 8.04, 0.14, "RUNNER", 8.0),
    ("2025-03-04", "RDGT", 4.04, 0.14, "RUNNER", 7.4),
    ("2025-07-15", "SXTP", 2.04, 0.11, "RUNNER", 7.2),
    ("2025-09-16", "APVO", 2.04, 0.14, "RUNNER", 6.8),
    ("2025-02-03", "REBN", 7.04, 0.14, "RUNNER", 6.3),
    ("2025-01-14", "AIFF", 4.61, 0.13, "RUNNER", 5.5),
    ("2025-03-17", "GLMD", 2.44, 0.14, "RUNNER", 5.5),
    ("2025-05-16", "AMST", 4.04, 0.14, "RUNNER", 5.1),
    ("2025-08-19", "PRFX", 2.04, 0.14, "RUNNER", 5.1),
    ("2025-02-24", "GSUN", 4.28, 0.14, "RUNNER", 4.9),
    ("2026-01-26", "BATL", 6.04, 0.14, "RUNNER", 4.1),
    ("2025-02-04", "QNTM", 6.04, 0.11, "RUNNER", 4.0),
    ("2026-01-21", "SLGB", 3.04, 0.14, "RUNNER", 3.7),
    ("2025-02-26", "ENVB", 3.60, 0.14, "RUNNER", 3.6),
    ("2025-06-13", "AGIG", 18.54, 0.14, "RUNNER", 3.3),
    ("2025-04-09", "VERO", 12.04, 0.47, "RUNNER", 3.2),
    ("2025-08-01", "MSW", 2.04, 0.14, "RUNNER", 2.9),
    ("2025-06-13", "ICON", 3.04, 0.14, "RUNNER", 2.7),
]


def load_ticks(date_str, symbol):
    """Load ticks from gzipped JSON cache."""
    path = f"tick_cache/{date_str}/{symbol}.json.gz"
    if not os.path.exists(path):
        return None
    with gzip.open(path, 'rt') as f:
        return json.load(f)


def build_1m_bars(ticks, market_open_utc):
    """
    Build 1-minute OHLCV bars from ticks.
    market_open_utc: datetime for 9:30 AM ET in UTC.
    Returns list of bar dicts sorted by time.
    """
    # Bucket ticks into 1-minute intervals starting from first tick
    bars_dict = defaultdict(list)
    for tick in ticks:
        dt = datetime.fromisoformat(tick['t'])
        # Floor to minute
        bar_time = dt.replace(second=0, microsecond=0)
        bars_dict[bar_time].append(tick)

    bars = []
    for bar_time in sorted(bars_dict.keys()):
        bucket = bars_dict[bar_time]
        prices = [t['p'] for t in bucket]
        sizes = [t['s'] for t in bucket]
        vol = sum(sizes)
        dollar_vol = sum(t['p'] * t['s'] for t in bucket)
        bars.append({
            'time': bar_time,
            'open': prices[0],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': vol,
            'dollar_vol': dollar_vol,
            'vwap_contrib_pv': dollar_vol,
            'vwap_contrib_v': vol,
        })
    return bars


def compute_ema(values, period):
    """Compute EMA for a list of values."""
    if not values:
        return []
    ema = [values[0]]
    k = 2.0 / (period + 1)
    for v in values[1:]:
        ema.append(v * k + ema[-1] * (1 - k))
    return ema


def compute_macd(closes):
    """Compute MACD(12,26,9). Returns (macd_line, signal, histogram) lists."""
    if len(closes) < 26:
        return None, None, None
    ema12 = compute_ema(closes, 12)
    ema26 = compute_ema(closes, 26)
    macd_line = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
    signal = compute_ema(macd_line, 9)
    histogram = [m - s for m, s in zip(macd_line, signal)]
    return macd_line, signal, histogram


def compute_running_vwap(bars):
    """Compute cumulative VWAP from market open."""
    cum_pv = 0.0
    cum_v = 0
    vwaps = []
    for bar in bars:
        cum_pv += bar['vwap_contrib_pv']
        cum_v += bar['vwap_contrib_v']
        vwaps.append(cum_pv / cum_v if cum_v > 0 else bar['close'])
    return vwaps


def detect_candle_patterns(bars, idx):
    """Detect candle patterns at given bar index."""
    patterns = []
    bar = bars[idx]
    body = abs(bar['close'] - bar['open'])
    total_range = bar['high'] - bar['low']

    if total_range == 0:
        return patterns

    # Doji: body < 10% of range
    if body / total_range < 0.10:
        patterns.append('doji')

    # Shooting star: small body at bottom, long upper wick
    upper_wick = bar['high'] - max(bar['open'], bar['close'])
    lower_wick = min(bar['open'], bar['close']) - bar['low']
    if upper_wick > 2 * body and lower_wick < body:
        patterns.append('shooting_star')

    # Bearish engulfing
    if idx > 0:
        prev = bars[idx - 1]
        if (prev['close'] > prev['open'] and  # prev green
            bar['close'] < bar['open'] and     # current red
            bar['open'] >= prev['close'] and
            bar['close'] <= prev['open']):
            patterns.append('bearish_engulfing')

    # Hammer (bullish, but worth noting)
    if lower_wick > 2 * body and upper_wick < body:
        patterns.append('hammer')

    # Long upper shadow (topping tail)
    if upper_wick > 0.6 * total_range:
        patterns.append('topping_tail')

    return patterns


def analyze_trade(date_str, symbol, entry, risk, label, post_r):
    """Analyze a single trade and return exhaustion fields at 2R."""
    ticks = load_ticks(date_str, symbol)
    if ticks is None:
        return {
            'date': date_str, 'symbol': symbol, 'entry': entry,
            'risk': risk, 'label': label, 'post_r': post_r,
            'error': 'no_tick_data',
        }

    if len(ticks) < 10:
        return {
            'date': date_str, 'symbol': symbol, 'entry': entry,
            'risk': risk, 'label': label, 'post_r': post_r,
            'error': 'insufficient_ticks',
        }

    # Parse date for market open (9:30 AM ET = 14:30 UTC for EST, 13:30 UTC for EDT)
    dt_date = datetime.strptime(date_str, '%Y-%m-%d')
    # Approximate: Mar-Nov is EDT (UTC-4), else EST (UTC-5)
    month = dt_date.month
    if 3 <= month <= 11:
        market_open_utc = dt_date.replace(hour=13, minute=30, tzinfo=timezone.utc)
    else:
        market_open_utc = dt_date.replace(hour=14, minute=30, tzinfo=timezone.utc)

    bars = build_1m_bars(ticks, market_open_utc)
    if len(bars) < 5:
        return {
            'date': date_str, 'symbol': symbol, 'entry': entry,
            'risk': risk, 'label': label, 'post_r': post_r,
            'error': 'insufficient_bars',
        }

    # Compute indicators
    closes = [b['close'] for b in bars]
    vwaps = compute_running_vwap(bars)
    macd_line, macd_signal, macd_hist = compute_macd(closes)

    # Target: entry + 2*risk
    target_2r = entry + 2 * risk

    # Find the first bar where price reaches 2R
    bar_2r_idx = None
    for i, bar in enumerate(bars):
        if bar['high'] >= target_2r:
            bar_2r_idx = i
            break

    if bar_2r_idx is None:
        return {
            'date': date_str, 'symbol': symbol, 'entry': entry,
            'risk': risk, 'label': label, 'post_r': post_r,
            'error': 'never_reached_2r',
        }

    # Session bar count (from market open)
    bar_time = bars[bar_2r_idx]['time']
    bars_into_session = bar_2r_idx  # Approximate, from first bar

    # More accurate: count from market open
    if bar_time.tzinfo is None:
        bar_time_aware = bar_time.replace(tzinfo=timezone.utc)
    else:
        bar_time_aware = bar_time
    minutes_from_open = (bar_time_aware - market_open_utc).total_seconds() / 60
    if minutes_from_open < 0:
        minutes_from_open = 0

    # VWAP distance
    vwap_at_2r = vwaps[bar_2r_idx]
    vwap_dist_pct = ((target_2r - vwap_at_2r) / vwap_at_2r) * 100 if vwap_at_2r > 0 else None

    # MACD
    macd_val = macd_line[bar_2r_idx] if macd_line and bar_2r_idx < len(macd_line) else None
    macd_hist_val = macd_hist[bar_2r_idx] if macd_hist and bar_2r_idx < len(macd_hist) else None

    # Histogram declining 3 bars
    hist_declining_3bar = None
    if macd_hist and bar_2r_idx >= 2:
        h = macd_hist
        hist_declining_3bar = (h[bar_2r_idx] < h[bar_2r_idx-1] < h[bar_2r_idx-2])

    # Volume at exit bar
    exit_vol = bars[bar_2r_idx]['volume']

    # Average volume over prior 5 bars
    start_avg = max(0, bar_2r_idx - 5)
    prior_vols = [bars[j]['volume'] for j in range(start_avg, bar_2r_idx)]
    avg_vol_5bar = sum(prior_vols) / len(prior_vols) if prior_vols else None
    vol_ratio = exit_vol / avg_vol_5bar if avg_vol_5bar and avg_vol_5bar > 0 else None

    # R at exit
    r_at_exit = (target_2r - entry) / risk if risk > 0 else None  # Should be 2.0

    # Distance from HOD
    hod = max(b['high'] for b in bars[:bar_2r_idx + 1])
    dist_from_hod_pct = ((hod - target_2r) / hod) * 100 if hod > 0 else None

    # Candle patterns
    candle_patterns = detect_candle_patterns(bars, bar_2r_idx)
    prior_bar_patterns = detect_candle_patterns(bars, bar_2r_idx - 1) if bar_2r_idx > 0 else []

    # Post-exit analysis (3 bars after)
    post_exit_vol_3bar = None
    vol_expanding_post = None
    price_above_entry_3bar_later = None

    if bar_2r_idx + 3 < len(bars):
        post_vols = [bars[bar_2r_idx + j]['volume'] for j in range(1, 4)]
        post_exit_vol_3bar = sum(post_vols) / 3
        vol_expanding_post = all(post_vols[j] > post_vols[j-1] for j in range(1, 3))
        price_above_entry_3bar_later = bars[bar_2r_idx + 3]['close'] > entry

    # Minutes to 2R from entry (approximate: from first bar where price >= entry)
    entry_bar_idx = None
    for i, bar in enumerate(bars):
        if bar['high'] >= entry:
            entry_bar_idx = i
            break
    minutes_to_2r = (bar_2r_idx - entry_bar_idx) if entry_bar_idx is not None else None

    return {
        'date': date_str,
        'symbol': symbol,
        'entry': entry,
        'risk': risk,
        'label': label,
        'post_r': post_r,
        'target_2r': round(target_2r, 2),
        'vwap_dist_pct': round(vwap_dist_pct, 2) if vwap_dist_pct is not None else None,
        'bars_into_session': bars_into_session,
        'minutes_to_2r': minutes_to_2r,
        'macd_val': round(macd_val, 6) if macd_val is not None else None,
        'macd_hist': round(macd_hist_val, 6) if macd_hist_val is not None else None,
        'hist_declining_3bar': hist_declining_3bar,
        'exit_vol': exit_vol,
        'avg_vol_5bar': round(avg_vol_5bar, 1) if avg_vol_5bar is not None else None,
        'vol_ratio': round(vol_ratio, 2) if vol_ratio is not None else None,
        'r_at_exit': round(r_at_exit, 1) if r_at_exit is not None else None,
        'dist_from_hod_pct': round(dist_from_hod_pct, 2) if dist_from_hod_pct is not None else None,
        'candle_patterns': candle_patterns,
        'prior_bar_patterns': prior_bar_patterns,
        'post_exit_vol_3bar': round(post_exit_vol_3bar, 1) if post_exit_vol_3bar is not None else None,
        'vol_expanding_post': vol_expanding_post,
        'price_above_entry_3bar_later': price_above_entry_3bar_later,
    }


def compute_exhaustion_score(rec):
    """Compute exhaustion score based on thresholds."""
    score = 0
    vwap = rec.get('vwap_dist_pct')
    bars = rec.get('bars_into_session')
    hist_dec = rec.get('hist_declining_3bar')
    vol_ratio = rec.get('vol_ratio')
    candle = rec.get('candle_patterns', [])
    hod_dist = rec.get('dist_from_hod_pct')

    # VWAP distance
    if vwap is not None:
        if vwap > 30:
            score += 3
        elif vwap > 20:
            score += 2
        elif vwap > 15:
            score += 1

    # Bars into session
    if bars is not None:
        if bars > 90:
            score += 2
        elif bars > 60:
            score += 1

    # MACD histogram declining
    if hist_dec:
        score += 1

    # Volume ratio (high vol ratio = exhaustion selling)
    if vol_ratio is not None:
        if vol_ratio < 0.5:
            score += 2  # Volume drying up
        elif vol_ratio < 0.8:
            score += 1

    # Bearish candle patterns
    bearish = {'shooting_star', 'bearish_engulfing', 'topping_tail', 'doji'}
    if candle:
        matched = set(candle) & bearish
        score += len(matched)

    # Near HOD (if close to HOD, less exhausted)
    if hod_dist is not None and hod_dist > 5:
        score += 1  # Already pulled back from HOD

    return score


def threshold_analysis(results):
    """Test exhaustion score at thresholds 3, 4, 5."""
    valid = [r for r in results if 'error' not in r]
    for r in valid:
        r['exhaustion_score'] = compute_exhaustion_score(r)

    analysis = {}
    for threshold in [3, 4, 5]:
        done_flagged = sum(1 for r in valid if r['label'] == 'DONE' and r['exhaustion_score'] >= threshold)
        done_total = sum(1 for r in valid if r['label'] == 'DONE')
        runner_flagged = sum(1 for r in valid if r['label'] == 'RUNNER' and r['exhaustion_score'] >= threshold)
        runner_total = sum(1 for r in valid if r['label'] == 'RUNNER')
        analysis[threshold] = {
            'done_flagged': done_flagged,
            'done_total': done_total,
            'done_pct': round(done_flagged / done_total * 100, 1) if done_total > 0 else 0,
            'runner_flagged': runner_flagged,
            'runner_total': runner_total,
            'runner_pct': round(runner_flagged / runner_total * 100, 1) if runner_total > 0 else 0,
        }
    return analysis


def build_summary_md(results, thresh_analysis):
    """Build markdown summary."""
    valid = sorted([r for r in results if 'error' not in r], key=lambda x: -x['post_r'])
    errors = [r for r in results if 'error' in r]

    lines = []
    lines.append("# Exhaustion Score Dataset Summary")
    lines.append("")
    lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total trades: {len(results)}, Valid: {len(valid)}, Errors: {len(errors)}")
    lines.append("")

    if errors:
        lines.append("## Errors")
        for e in errors:
            lines.append(f"- {e['date']} {e['symbol']}: {e['error']}")
        lines.append("")

    # Main table
    lines.append("## Trade Data (sorted by post_r descending)")
    lines.append("")
    lines.append("| Date | Symbol | Label | Entry | 2R | Post R | Exh Score | VWAP Dist% | Bars | Min to 2R | MACD Hist | Hist Dec 3 | Vol Ratio | HOD Dist% | Candle Patterns |")
    lines.append("|------|--------|-------|-------|----|--------|-----------|------------|------|-----------|-----------|------------|-----------|-----------|-----------------|")
    for r in valid:
        cp = ', '.join(r.get('candle_patterns', [])) or '-'
        lines.append(
            f"| {r['date']} | {r['symbol']} | {r['label']} | {r['entry']} | {r['target_2r']} | {r['post_r']} | "
            f"{r.get('exhaustion_score', '-')} | {r.get('vwap_dist_pct', '-')} | {r.get('bars_into_session', '-')} | "
            f"{r.get('minutes_to_2r', '-')} | {r.get('macd_hist', '-')} | {r.get('hist_declining_3bar', '-')} | "
            f"{r.get('vol_ratio', '-')} | {r.get('dist_from_hod_pct', '-')} | {cp} |"
        )
    lines.append("")

    # Threshold analysis
    lines.append("## Threshold Analysis")
    lines.append("")
    lines.append("Exhaustion score components:")
    lines.append("- VWAP dist > 30%: +3, > 20%: +2, > 15%: +1")
    lines.append("- Bars into session > 90: +2, > 60: +1")
    lines.append("- MACD histogram declining 3 bars: +1")
    lines.append("- Volume ratio < 0.5: +2, < 0.8: +1")
    lines.append("- Each bearish candle pattern (doji, shooting_star, bearish_engulfing, topping_tail): +1")
    lines.append("- Pulled back > 5% from HOD: +1")
    lines.append("")
    lines.append("| Threshold | Done Flagged | Done Total | Done % | Runner Flagged | Runner Total | Runner % | Notes |")
    lines.append("|-----------|-------------|------------|--------|----------------|--------------|----------|-------|")
    for t in [3, 4, 5]:
        a = thresh_analysis[t]
        # Ideal: high done%, low runner%
        note = ""
        if a['done_pct'] > 60 and a['runner_pct'] < 30:
            note = "GOOD separation"
        elif a['done_pct'] > a['runner_pct']:
            note = "Moderate separation"
        else:
            note = "Poor separation"
        lines.append(
            f"| {t} | {a['done_flagged']} | {a['done_total']} | {a['done_pct']}% | "
            f"{a['runner_flagged']} | {a['runner_total']} | {a['runner_pct']}% | {note} |"
        )
    lines.append("")

    # Post-exit analysis
    lines.append("## Post-Exit Behavior")
    lines.append("")
    lines.append("| Date | Symbol | Label | Post R | Price Above Entry 3 Bars Later | Vol Expanding Post | Post Exit Avg Vol |")
    lines.append("|------|--------|-------|--------|-------------------------------|-------------------|-------------------|")
    for r in valid:
        lines.append(
            f"| {r['date']} | {r['symbol']} | {r['label']} | {r['post_r']} | "
            f"{r.get('price_above_entry_3bar_later', '-')} | {r.get('vol_expanding_post', '-')} | "
            f"{r.get('post_exit_vol_3bar', '-')} |"
        )
    lines.append("")

    return '\n'.join(lines)


def main():
    print("Analyzing exhaustion data for 35 trades...")
    results = []
    for date_str, symbol, entry, risk, label, post_r in TRADES:
        print(f"  Processing {date_str} {symbol} (entry={entry}, risk={risk})...")
        rec = analyze_trade(date_str, symbol, entry, risk, label, post_r)
        results.append(rec)
        if 'error' in rec:
            print(f"    ERROR: {rec['error']}")
        else:
            print(f"    OK: exh_score={compute_exhaustion_score(rec)}, vwap_dist={rec.get('vwap_dist_pct')}%")

    # Compute exhaustion scores
    for r in results:
        if 'error' not in r:
            r['exhaustion_score'] = compute_exhaustion_score(r)

    # Threshold analysis
    thresh = threshold_analysis(results)

    # Save JSON
    os.makedirs("cowork_reports", exist_ok=True)
    with open("cowork_reports/exhaustion_score_dataset.json", 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nSaved JSON: cowork_reports/exhaustion_score_dataset.json")

    # Save markdown
    md = build_summary_md(results, thresh)
    with open("cowork_reports/exhaustion_score_summary.md", 'w') as f:
        f.write(md)
    print(f"Saved MD:   cowork_reports/exhaustion_score_summary.md")

    # Print threshold summary
    print("\n=== Threshold Analysis ===")
    for t in [3, 4, 5]:
        a = thresh[t]
        print(f"  Threshold {t}: Done flagged {a['done_flagged']}/{a['done_total']} ({a['done_pct']}%) | "
              f"Runner flagged {a['runner_flagged']}/{a['runner_total']} ({a['runner_pct']}%)")


if __name__ == '__main__':
    main()
